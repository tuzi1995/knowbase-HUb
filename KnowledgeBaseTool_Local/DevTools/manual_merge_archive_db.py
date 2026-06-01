import argparse
import os
import sqlite3


def table_exists(cur: sqlite3.Cursor, table: str) -> bool:
    row = cur.execute(
        "select name from sqlite_master where type='table' and name=?",
        (table,),
    ).fetchone()
    return bool(row)


def ensure_archive_tables(cur: sqlite3.Cursor) -> None:
    cur.execute(
        """
        create table if not exists archive_batch (
            id integer primary key,
            batch_name varchar(200) not null,
            record_count integer default 0,
            created_by varchar(80),
            created_at datetime
        )
        """
    )
    cur.execute(
        """
        create table if not exists archive_record (
            id integer primary key,
            batch_id integer not null,
            record_json text not null,
            modify_time datetime,
            foreign key(batch_id) references archive_batch(id)
        )
        """
    )


def dedupe_batches(cur: sqlite3.Cursor) -> int:
    removed = 0
    dup_groups = cur.execute(
        "select batch_name, created_at, record_count, created_by, count(*) as c "
        "from archive_batch "
        "group by batch_name, created_at, record_count, created_by "
        "having c > 1"
    ).fetchall()
    for bname, cat, rc, cby, _c in dup_groups:
        ids = [
            r[0]
            for r in cur.execute(
                "select id from archive_batch where batch_name=? and created_at=? and record_count=? and (created_by is ? or created_by=?) order by id asc",
                (bname, cat, rc, cby, cby),
            ).fetchall()
        ]
        if len(ids) <= 1:
            continue
        drop_ids = ids[1:]
        cur.execute(
            f"delete from archive_record where batch_id in ({','.join(['?'] * len(drop_ids))})",
            drop_ids,
        )
        cur.execute(
            f"delete from archive_batch where id in ({','.join(['?'] * len(drop_ids))})",
            drop_ids,
        )
        removed += len(drop_ids)
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge archive tables from an old sqlite db into the current sqlite db.")
    parser.add_argument("--source-db", required=True, help="Old sqlite db path")
    parser.add_argument("--target-db", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "instance", "data.db"), help="Current sqlite db path")
    parser.add_argument("--dry-run", action="store_true", help="Only print what would be merged")
    args = parser.parse_args()

    source_db = os.path.abspath(args.source_db)
    target_db = os.path.abspath(args.target_db)

    if source_db == target_db:
        print("SOURCE_EQUALS_TARGET")
        return 2
    if not os.path.exists(source_db):
        print(f"SOURCE_NOT_FOUND: {source_db}")
        return 3

    src_con = sqlite3.connect(source_db)
    dst_con = sqlite3.connect(target_db)
    try:
        src = src_con.cursor()
        dst = dst_con.cursor()
        ensure_archive_tables(dst)

        if not table_exists(src, "archive_batch") or not table_exists(src, "archive_record"):
            print("SOURCE_HAS_NO_ARCHIVE_TABLES")
            return 4

        existing_batch_ids = {r[0] for r in dst.execute("select id from archive_batch").fetchall()}
        existing_record_ids = {r[0] for r in dst.execute("select id from archive_record").fetchall()}
        existing_batch_keys = {}
        for row in dst.execute("select id, batch_name, record_count, created_by, created_at from archive_batch").fetchall():
            key = (row[1], row[2], row[3], row[4])
            existing_batch_keys[key] = row[0]

        id_map = {}
        inserted_batches = 0
        reused_batches = 0

        for bid, bname, rc, cby, cat in src.execute(
            "select id, batch_name, record_count, created_by, created_at from archive_batch order by id asc"
        ).fetchall():
            key = (bname, rc, cby, cat)
            if key in existing_batch_keys:
                id_map[int(bid)] = int(existing_batch_keys[key])
                reused_batches += 1
                continue
            if bid not in existing_batch_ids:
                dst.execute(
                    "insert into archive_batch (id, batch_name, record_count, created_by, created_at) values (?, ?, ?, ?, ?)",
                    (bid, bname, rc, cby, cat),
                )
                new_id = int(bid)
            else:
                dst.execute(
                    "insert into archive_batch (batch_name, record_count, created_by, created_at) values (?, ?, ?, ?)",
                    (bname, rc, cby, cat),
                )
                new_id = int(dst.lastrowid)
            existing_batch_ids.add(new_id)
            existing_batch_keys[key] = new_id
            id_map[int(bid)] = new_id
            inserted_batches += 1

        existing_record_keys = {
            (row[0], row[1], row[2])
            for row in dst.execute("select batch_id, record_json, modify_time from archive_record").fetchall()
        }
        inserted_records = 0
        reused_records = 0

        for rid, batch_id, rjson, mt in src.execute(
            "select id, batch_id, record_json, modify_time from archive_record order by id asc"
        ).fetchall():
            mapped_batch_id = id_map.get(int(batch_id)) if batch_id is not None else None
            if mapped_batch_id is None:
                continue
            key = (mapped_batch_id, rjson, mt)
            if key in existing_record_keys:
                reused_records += 1
                continue
            if rid not in existing_record_ids:
                dst.execute(
                    "insert into archive_record (id, batch_id, record_json, modify_time) values (?, ?, ?, ?)",
                    (rid, mapped_batch_id, rjson, mt),
                )
                existing_record_ids.add(rid)
            else:
                dst.execute(
                    "insert into archive_record (batch_id, record_json, modify_time) values (?, ?, ?)",
                    (mapped_batch_id, rjson, mt),
                )
            existing_record_keys.add(key)
            inserted_records += 1

        removed_duplicates = dedupe_batches(dst)

        print(f"SOURCE_DB={source_db}")
        print(f"TARGET_DB={target_db}")
        print(f"INSERTED_BATCHES={inserted_batches}")
        print(f"REUSED_BATCHES={reused_batches}")
        print(f"INSERTED_RECORDS={inserted_records}")
        print(f"REUSED_RECORDS={reused_records}")
        print(f"REMOVED_DUPLICATE_BATCHES={removed_duplicates}")

        if args.dry_run:
            dst_con.rollback()
            print("DRY_RUN_COMPLETE")
        else:
            dst_con.commit()
            print("MERGE_COMPLETE")
        return 0
    finally:
        try:
            src_con.close()
        except Exception:
            pass
        try:
            dst_con.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
