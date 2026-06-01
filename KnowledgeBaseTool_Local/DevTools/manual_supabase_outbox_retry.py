import json
import sys
import time
import traceback


def main() -> int:
    # Import server (Flask app + SQLAlchemy models + SupabaseClient)
    from server import app, db, init_db, get_supabase_client, SupabaseOutbox, SupabaseClient, _json_loads_safe

    try:
        with app.app_context():
            init_db()

            # Disable outbox during replay to avoid duplicating records.
            # We construct a new client directly to override enable_outbox.
            client = get_supabase_client()
            if client is None:
                print("Supabase not configured.")
                return 2

            # Rebuild client with enable_outbox=False
            retry_client = SupabaseClient(client.url, client.key, enable_outbox=False)

            manual_after_seconds = 4 * 3600
            now_ts = time.time()

            pending = (
                SupabaseOutbox.query
                .filter(SupabaseOutbox.status.in_(["pending", "needs_manual_sync"]))
                .order_by(SupabaseOutbox.created_ts.asc())
                .limit(200)
                .all()
            )

            if not pending:
                print("No pending outbox items.")
                return 0

            ok = 0
            failed = 0

            def _is_duplicate_error(err_text: str) -> bool:
                s = str(err_text or '').lower()
                return (
                    'duplicate key' in s
                    or 'unique constraint' in s
                    or 'violates unique constraint' in s
                    or 'already exists' in s
                )

            for item in pending:
                # Mark old ones for manual attention
                try:
                    if item.status == "pending" and (now_ts - float(item.created_ts or 0)) >= manual_after_seconds:
                        item.status = "needs_manual_sync"
                        db.session.commit()
                except Exception:
                    pass

                op_type = item.op_type
                table = item.table_name
                payload = _json_loads_safe(item.payload_json)
                filters = _json_loads_safe(item.filters_json)
                extra = _json_loads_safe(item.extra_json) or {}

                try:
                    if op_type == "insert":
                        ignore_duplicates = bool(extra.get("ignore_duplicates", False))
                        resp = retry_client.insert(table, payload or [], ignore_duplicates=ignore_duplicates)
                    elif op_type == "upsert":
                        on_conflict = extra.get("on_conflict")
                        resp = retry_client.upsert(table, payload or [], on_conflict=on_conflict)
                    elif op_type == "update":
                        resp = retry_client.update(table, payload or {}, filters or {})
                    elif op_type == "delete":
                        resp = retry_client.delete(table, filters or {})
                    elif op_type == "delete_in":
                        column = extra.get("column")
                        values = (filters or {}).get("values") if isinstance(filters, dict) else None
                        if values is None:
                            # stored in filters_json: {"column":..., "values":[...]}
                            values = (filters or {}).get("values")
                        resp = retry_client.delete_in(table, column, values or [])
                    else:
                        raise RuntimeError(f"Unknown op_type: {op_type}")

                    sc = getattr(resp, "status_code", 500)
                    if sc >= 400:
                        raise RuntimeError(f"Replay failed status_code={sc}, text={getattr(resp,'text','')}")

                    item.status = "done"
                    item.last_error = ""
                    item.attempts = int(item.attempts or 0) + 1
                    item.updated_ts = time.time()
                    db.session.commit()
                    ok += 1
                    print(f"[Outbox] done id={item.id} {op_type} {table}")
                except Exception as e:
                    item.attempts = int(item.attempts or 0) + 1
                    item.last_error = str(e)[:4000]
                    item.updated_ts = time.time()
                    db.session.commit()
                    if _is_duplicate_error(str(e)):
                        item.status = "done"
                        item.last_error = ""
                        db.session.commit()
                        ok += 1
                        print(f"[Outbox] done(idempotent-duplicate) id={item.id} {op_type} {table}")
                    else:
                        failed += 1
                        print(f"[Outbox] failed id={item.id} {op_type} {table}: {e}")

            print(f"Outbox replay finished. ok={ok} failed={failed} (attempted={len(pending)})")
            return 0 if failed == 0 else 1
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

