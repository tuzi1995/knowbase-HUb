#!/usr/bin/env python3
"""Export or merge 8085 primary PostgreSQL data without deleting cloud-only rows."""

from __future__ import annotations

import argparse
import base64
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import psycopg2
from psycopg2 import sql
from psycopg2.extras import Json, RealDictCursor, execute_batch

IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
FORMAT_VERSION = 1
RELEASE_PARAMETER_TABLES = (
    "parameter_ai_candidate_assessment",
    "parameter_check_finding",
    "kb_parameter_claim_model",
    "kb_parameter_claim",
    "parameter_ai_scan_item",
    "parameter_ai_scan_receipt",
    "parameter_model_alias_binding",
    "parameter_check_run",
    "parameter_snapshot",
    "parameter_check_schema_migration",
)


def _identifier(value: str) -> str:
    if not IDENTIFIER.fullmatch(str(value or "")):
        raise ValueError(f"Unsafe SQL identifier: {value!r}")
    return str(value)


def _load_connection(config_path: Path):
    config = json.loads(config_path.read_text(encoding="utf-8"))
    db = config.get("local_db") if isinstance(config.get("local_db"), dict) else config
    required = ("host", "port", "database", "user")
    missing = [name for name in required if not db.get(name)]
    if missing:
        raise RuntimeError(f"database config missing: {', '.join(missing)}")
    return psycopg2.connect(
        host=db["host"], port=db["port"], database=db["database"],
        user=db["user"], password=db.get("password", ""), connect_timeout=10,
    )


def _json_default(value):
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    if isinstance(value, bytes):
        return {"__kmatrix_binary__": base64.b64encode(value).decode("ascii")}
    raise TypeError(f"Unsupported value type: {type(value).__name__}")


def _public_tables(cursor) -> list[str]:
    cursor.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname=%s ORDER BY tablename",
        ("public",),
    )
    tables = [str(row[0]) for row in cursor.fetchall()]
    known_tables = set(tables)
    dependencies = {table: set() for table in tables}
    cursor.execute(
        """
        SELECT child.relname, parent.relname
        FROM pg_constraint con
        JOIN pg_class child ON child.oid = con.conrelid
        JOIN pg_namespace child_ns ON child_ns.oid = child.relnamespace
        JOIN pg_class parent ON parent.oid = con.confrelid
        JOIN pg_namespace parent_ns ON parent_ns.oid = parent.relnamespace
        WHERE con.contype='f' AND child_ns.nspname=%s AND parent_ns.nspname=%s
        """,
        ("public", "public"),
    )
    for child, parent in cursor.fetchall():
        if child in known_tables and parent in known_tables and child != parent:
            dependencies[str(child)].add(str(parent))

    ordered = []
    remaining = set(tables)
    while remaining:
        ready = sorted(table for table in remaining if not (dependencies[table] & remaining))
        if not ready:
            raise RuntimeError(f"Foreign-key dependency cycle in primary database: {sorted(remaining)}")
        ordered.extend(ready)
        remaining.difference_update(ready)
    return ordered


def _table_metadata(cursor, table: str) -> dict:
    table = _identifier(table)
    cursor.execute(
        """
        SELECT column_name, data_type, udt_name, column_default
        FROM information_schema.columns
        WHERE table_schema=%s AND table_name=%s
        ORDER BY ordinal_position
        """,
        ("public", table),
    )
    columns = cursor.fetchall()
    if not columns:
        raise RuntimeError(f"Table metadata not found: {table}")

    cursor.execute(
        """
        SELECT con.contype, array_agg(att.attname ORDER BY key_cols.ordinality)
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        JOIN pg_namespace ns ON ns.oid = rel.relnamespace
        JOIN unnest(con.conkey) WITH ORDINALITY AS key_cols(attnum, ordinality) ON TRUE
        JOIN pg_attribute att ON att.attrelid = rel.oid AND att.attnum = key_cols.attnum
        WHERE ns.nspname=%s AND rel.relname=%s AND con.contype IN ('p', 'u')
        GROUP BY con.contype, con.conname
        ORDER BY CASE con.contype WHEN 'u' THEN 0 ELSE 1 END, con.conname
        LIMIT 1
        """,
        ("public", table),
    )
    conflict = cursor.fetchone()
    if not conflict:
        raise RuntimeError(f"Table has no primary/unique key and cannot be merged safely: {table}")

    names = [str(row[0]) for row in columns]
    serial_columns = [
        str(name) for name, _data_type, _udt_name, default in columns
        if default and "nextval(" in str(default)
    ]
    conflict_columns = [str(name) for name in conflict[1]]
    return {
        "table": table,
        "columns": names,
        # When a natural unique key is used for upsert, preserve the cloud
        # serial ID.  Sending a source ID first could collide with a different
        # cloud row before PostgreSQL reaches the natural-key conflict handler.
        "insert_columns": [
            name for name in names
            if not (name in serial_columns and name not in conflict_columns)
        ],
        "json_columns": [str(name) for name, data_type, _udt_name, _default in columns if data_type in {"json", "jsonb"}],
        "binary_columns": [str(name) for name, _data_type, udt_name, _default in columns if udt_name == "bytea"],
        "serial_columns": serial_columns,
        "conflict_columns": conflict_columns,
    }


def export_data(config_path: Path, output_path: Path, dry_run: bool) -> int:
    conn = _load_connection(config_path)
    try:
        with conn.cursor() as cursor:
            tables = _public_tables(cursor)
            metadata = [_table_metadata(cursor, table) for table in tables]
            counts = {}
            for item in metadata:
                cursor.execute(sql.SQL("SELECT COUNT(*) FROM public.{}").format(sql.Identifier(item["table"])))
                counts[item["table"]] = int(cursor.fetchone()[0])
        manifest = {"format": FORMAT_VERSION, "tables": metadata, "counts": counts}
        if dry_run:
            print(json.dumps({"ok": True, "dry_run": True, **manifest}, ensure_ascii=False, sort_keys=True))
            return 0

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(output_path, "wt", encoding="utf-8") as stream, conn.cursor(cursor_factory=RealDictCursor) as cursor:
            stream.write(json.dumps({"kind": "manifest", **manifest}, ensure_ascii=False, sort_keys=True) + "\n")
            for item in metadata:
                table = item["table"]
                stream.write(json.dumps({"kind": "table", **item}, ensure_ascii=False, sort_keys=True) + "\n")
                cursor.execute(sql.SQL("SELECT * FROM public.{} ORDER BY {}").format(
                    sql.Identifier(table), sql.SQL(", ").join(sql.Identifier(column) for column in item["conflict_columns"]),
                ))
                for row in cursor:
                    values = [row[column] for column in item["columns"]]
                    stream.write(json.dumps({"kind": "row", "values": values}, ensure_ascii=False, default=_json_default) + "\n")
        print(json.dumps({"ok": True, "output": str(output_path), **manifest}, ensure_ascii=False, sort_keys=True))
        return 0
    finally:
        conn.close()


def _restore_value(value, column: str, metadata: dict):
    if isinstance(value, dict) and set(value) == {"__kmatrix_binary__"}:
        return psycopg2.Binary(base64.b64decode(value["__kmatrix_binary__"]))
    if column in metadata["json_columns"]:
        return Json(value)
    return value


def _flush_rows(cursor, metadata: dict, rows: list[list]) -> int:
    if not rows:
        return 0
    table = _identifier(metadata["table"])
    columns = [_identifier(column) for column in metadata["insert_columns"]]
    conflict_columns = [_identifier(column) for column in metadata["conflict_columns"]]
    serial_columns = set(metadata["serial_columns"])
    update_columns = [column for column in columns if column not in conflict_columns and column not in serial_columns]
    query = sql.SQL("INSERT INTO public.{} ({}) VALUES ({}) ON CONFLICT ({}) {}").format(
        sql.Identifier(table),
        sql.SQL(", ").join(sql.Identifier(column) for column in columns),
        sql.SQL(", ").join(sql.Placeholder() for _ in columns),
        sql.SQL(", ").join(sql.Identifier(column) for column in conflict_columns),
        sql.SQL("DO UPDATE SET ") + sql.SQL(", ").join(
            sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(column), sql.Identifier(column))
            for column in update_columns
        ) if update_columns else sql.SQL("DO NOTHING"),
    )
    execute_batch(cursor, query.as_string(cursor), rows, page_size=min(200, len(rows)))
    return len(rows)


def _advance_serial_sequences(cursor, metadata: dict):
    table = _identifier(metadata["table"])
    for column in metadata["serial_columns"]:
        column = _identifier(column)
        cursor.execute("SELECT pg_get_serial_sequence(%s, %s)", (f"public.{table}", column))
        sequence = cursor.fetchone()[0]
        if not sequence:
            continue
        cursor.execute(
            sql.SQL(
                "SELECT setval(%s::regclass, COALESCE((SELECT MAX({}) FROM public.{}), 1), "
                "(SELECT COUNT(*) > 0 FROM public.{}))"
            ).format(sql.Identifier(column), sql.Identifier(table), sql.Identifier(table)),
            (sequence,),
        )


def import_data(config_path: Path, input_path: Path) -> int:
    conn = _load_connection(config_path)
    imported = {}
    try:
        with gzip.open(input_path, "rt", encoding="utf-8") as stream, conn.cursor() as cursor:
            manifest = json.loads(next(stream))
            if manifest.get("kind") != "manifest" or manifest.get("format") != FORMAT_VERSION:
                raise RuntimeError("Unsupported primary database sync archive")
            expected_counts = manifest.get("counts") or {}
            current = None
            rows: list[list] = []

            def flush_current():
                nonlocal rows
                if current is not None:
                    count = _flush_rows(cursor, current, rows)
                    imported[current["table"]] = imported.get(current["table"], 0) + count
                    rows = []

            for raw_line in stream:
                record = json.loads(raw_line)
                if record.get("kind") == "table":
                    flush_current()
                    current = {key: record[key] for key in (
                        "table", "columns", "insert_columns", "json_columns", "binary_columns", "serial_columns", "conflict_columns"
                    )}
                    for value in [current["table"], *current["columns"], *current["conflict_columns"]]:
                        _identifier(value)
                elif record.get("kind") == "row":
                    if current is None:
                        raise RuntimeError("Archive row appears before table metadata")
                    values = record.get("values")
                    if not isinstance(values, list) or len(values) != len(current["columns"]):
                        raise RuntimeError(f"Invalid row payload for {current['table']}")
                    restored = {
                        column: _restore_value(value, column, current)
                        for column, value in zip(current["columns"], values)
                    }
                    rows.append([restored[column] for column in current["insert_columns"]])
                    if len(rows) >= 200:
                        flush_current()
                else:
                    raise RuntimeError("Invalid record in primary database sync archive")
            flush_current()

            for table_record in manifest.get("tables") or []:
                _advance_serial_sequences(cursor, table_record)
            conn.commit()

            verified_counts = {}
            for table, expected in expected_counts.items():
                table = _identifier(table)
                cursor.execute(sql.SQL("SELECT COUNT(*) FROM public.{}").format(sql.Identifier(table)))
                actual = int(cursor.fetchone()[0])
                if actual < int(expected):
                    raise RuntimeError(f"Cloud table row count is lower than source after sync: {table} {actual} < {expected}")
                verified_counts[table] = actual
        print(json.dumps({"ok": True, "upserted": imported, "cloud_counts": verified_counts}, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _database_env(config_path: Path) -> tuple[dict, dict]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    db = config.get("local_db") if isinstance(config.get("local_db"), dict) else config
    required = ("host", "port", "database", "user")
    missing = [name for name in required if not db.get(name)]
    if missing:
        raise RuntimeError(f"database config missing: {', '.join(missing)}")
    env = dict(os.environ)
    env["PGPASSWORD"] = str(db.get("password") or "")
    return db, env


def backup_database(config_path: Path, output_path: Path) -> int:
    db, env = _database_env(config_path)
    executable = shutil.which("pg_dump")
    if not executable:
        raise RuntimeError("pg_dump is not available")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        executable, "--format=custom", "--file", str(output_path),
        "--host", str(db["host"]), "--port", str(db["port"]),
        "--username", str(db["user"]), str(db["database"]),
    ], env=env, check=True, stdout=subprocess.DEVNULL)
    print(json.dumps({"ok": True, "backup": str(output_path), "bytes": output_path.stat().st_size}, ensure_ascii=False))
    return 0


def restore_database(config_path: Path, input_path: Path) -> int:
    db, env = _database_env(config_path)
    executable = shutil.which("pg_restore")
    if not executable:
        raise RuntimeError("pg_restore is not available")
    if not input_path.is_file():
        raise RuntimeError(f"backup file not found: {input_path}")
    # A failed release can have created parameter-check tables that did not
    # exist when its backup was taken.  Remove that bounded release schema
    # first so pg_restore --clean can restore the original constraint graph.
    connection = _load_connection(config_path)
    try:
        with connection.cursor() as cursor:
            for table in RELEASE_PARAMETER_TABLES:
                cursor.execute(sql.SQL("DROP TABLE IF EXISTS public.{} CASCADE").format(sql.Identifier(table)))
        connection.commit()
    finally:
        connection.close()
    subprocess.run([
        executable, "--clean", "--if-exists", "--no-owner", "--no-privileges",
        "--host", str(db["host"]), "--port", str(db["port"]),
        "--username", str(db["user"]), "--dbname", str(db["database"]), str(input_path),
    ], env=env, check=True, stdout=subprocess.DEVNULL)
    print(json.dumps({"ok": True, "restored": str(input_path)}, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="8085 PostgreSQL export / non-destructive cloud merge")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("export", "import", "backup", "restore"):
        sub = subparsers.add_parser(command)
        sub.add_argument("--config", default="supabase_config_local.json")
        sub.add_argument("--file", required=True)
        if command == "export":
            sub.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    config_path = Path(args.config).resolve()
    if args.command == "export":
        return export_data(config_path, Path(args.file).resolve(), args.dry_run)
    if args.command == "import":
        return import_data(config_path, Path(args.file).resolve())
    if args.command == "backup":
        return backup_database(config_path, Path(args.file).resolve())
    return restore_database(config_path, Path(args.file).resolve())


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
