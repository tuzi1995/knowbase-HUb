import argparse
import os
import sys
import time
import traceback


def _chunked(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync local archive tables to Supabase.")
    parser.add_argument("--batch-size", type=int, default=300, help="Upsert batch size")
    parser.add_argument("--dry-run", action="store_true", help="Only print counts, do not write to Supabase")
    args = parser.parse_args()

    tool_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(tool_dir)
    sys.path.insert(0, tool_dir)

    try:
        from server import (
            app,
            init_db,
            get_supabase_client,
            SupabaseClient,
            ArchiveBatch,
            ArchiveRecord,
            _supabase_table_exists,
        )
    except Exception as e:
        print(f"Failed to import server.py dependencies: {e}")
        traceback.print_exc()
        return 2

    try:
        with app.app_context():
            init_db()

            client = get_supabase_client()
            if client is None:
                print("Supabase not configured.")
                return 3

            # Use direct write mode for manual migration: fail fast instead of enqueueing.
            sync_client = SupabaseClient(client.url, client.key, enable_outbox=False)

            if not _supabase_table_exists(sync_client, "archive_batch"):
                print("Supabase table missing: archive_batch")
                return 4
            if not _supabase_table_exists(sync_client, "archive_record"):
                print("Supabase table missing: archive_record")
                return 5

            local_batches = ArchiveBatch.query.order_by(ArchiveBatch.id.asc()).all()
            local_records = ArchiveRecord.query.order_by(ArchiveRecord.id.asc()).all()

            batch_rows = []
            for b in local_batches:
                batch_rows.append({
                    "id": int(b.id),
                    "batch_name": b.batch_name,
                    "record_count": int(b.record_count or 0),
                    "created_by": b.created_by,
                    "created_at": b.created_at.isoformat() if b.created_at else None,
                })

            record_rows = []
            for r in local_records:
                record_rows.append({
                    "id": int(r.id),
                    "batch_id": int(r.batch_id),
                    "record_json": r.record_json,
                    "modify_time": r.modify_time.isoformat() if r.modify_time else None,
                })

            print(f"Local rows: archive_batch={len(batch_rows)}, archive_record={len(record_rows)}")
            if args.dry_run:
                print("Dry run complete. No data written.")
                return 0

            bs = max(1, int(args.batch_size or 300))
            start = time.time()

            if batch_rows:
                total = len(batch_rows)
                print(f"Upserting archive_batch in batches of {bs} (total={total}) ...")
                for idx, chunk in enumerate(_chunked(batch_rows, bs), start=1):
                    resp = sync_client.upsert("archive_batch", chunk, on_conflict="id")
                    if getattr(resp, "status_code", 500) >= 400:
                        print(f"archive_batch upsert failed at chunk {idx}: {getattr(resp, 'text', '')}")
                        return 6
                    print(f"archive_batch chunk {idx}/{(total + bs - 1) // bs} done")

            if record_rows:
                total = len(record_rows)
                print(f"Upserting archive_record in batches of {bs} (total={total}) ...")
                for idx, chunk in enumerate(_chunked(record_rows, bs), start=1):
                    resp = sync_client.upsert("archive_record", chunk, on_conflict="id")
                    if getattr(resp, "status_code", 500) >= 400:
                        print(f"archive_record upsert failed at chunk {idx}: {getattr(resp, 'text', '')}")
                        return 7
                    print(f"archive_record chunk {idx}/{(total + bs - 1) // bs} done")

            elapsed = time.time() - start
            print(f"Archive sync completed successfully. Elapsed: {elapsed:.1f}s")
            return 0
    except Exception as e:
        print(f"Archive sync failed: {e}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
