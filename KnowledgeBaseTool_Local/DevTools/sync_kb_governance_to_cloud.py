#!/usr/bin/env python3
"""
Sync local knowledge-base governance data (kb_recall) to the deployed cloud server.

The script reads kb_recall from the local app databases, uploads a temporary
JSON payload over SSH, then asks the remote app to replace/upsert rows into its
own database using server.py's configured database client.
"""

import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
import textwrap
from datetime import date, datetime
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
DEFAULT_REMOTE_USER = "root"
DEFAULT_REMOTE_HOST = "112.126.63.84"
DEFAULT_REMOTE_DIR = "~/k-matrix"
DEFAULT_REMOTE_TMP_DIR = "~/k-matrix/tmp_sync"
DEFAULT_BATCH_SIZE = 500

KB_RECALL_COLUMNS = [
    "kb_id",
    "month",
    "recall_count",
    "valid_recall_count",
    "created_at",
]


def _json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _remote_shell_path(path: str) -> str:
    raw = str(path or "").strip()
    if raw == "~":
        return "$HOME"
    if raw.startswith("~/"):
        return "$HOME/" + shlex.quote(raw[2:])
    return shlex.quote(raw)


def _run(cmd, *, label=None):
    shown = label or " ".join(shlex.quote(str(part)) for part in cmd)
    print(f"$ {shown}")
    return subprocess.run(cmd, check=True)


def _build_ssh_opts(args):
    known_hosts = args.known_hosts
    opts = [
        "-o",
        f"UserKnownHostsFile={known_hosts}",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "LogLevel=ERROR",
        "-o",
        str(f"ConnectTimeout={int(args.connect_timeout)}"),
    ]

    identity = args.identity
    if identity:
        opts.extend(["-i", identity, "-o", "IdentitiesOnly=yes"])
    else:
        home = Path.home()
        for candidate in (home / ".ssh" / "id_ed25519", home / ".ssh" / "id_rsa"):
            if candidate.exists():
                opts.extend(["-i", str(candidate), "-o", "IdentitiesOnly=yes"])
                break
    return opts


def _normalize_months(raw_months):
    months = []
    for raw in raw_months or []:
        month = str(raw or "").strip()
        if not month:
            continue
        if len(month) != 7 or month[4] != "-":
            raise ValueError(f"月份格式应为 YYYY-MM: {month}")
        try:
            year = int(month[:4])
            mon = int(month[5:])
        except ValueError as exc:
            raise ValueError(f"月份格式应为 YYYY-MM: {month}") from exc
        if year < 2000 or mon < 1 or mon > 12:
            raise ValueError(f"月份值不合法: {month}")
        months.append(month)
    return sorted(dict.fromkeys(months))


def _postgrest_in(values):
    encoded = []
    for value in values:
        text = str(value).replace("\\", "\\\\").replace('"', '\\"')
        encoded.append(f'"{text}"')
    return "in.(" + ",".join(encoded) + ")"


def _clean_recall_row(row):
    if not isinstance(row, dict):
        return None
    clean = {key: row.get(key) for key in KB_RECALL_COLUMNS if key in row}
    kb_id = str(clean.get("kb_id") or "").strip()
    month = str(clean.get("month") or "").strip()
    if not kb_id or not month:
        return None
    clean["kb_id"] = kb_id
    clean["month"] = month
    clean["recall_count"] = int(clean.get("recall_count") or 0)
    clean["valid_recall_count"] = int(clean.get("valid_recall_count") or 0)
    return clean


def _load_local_rows(months):
    sys.path.insert(0, str(PROJECT_DIR))
    os.chdir(PROJECT_DIR)

    from server import KBRecall, app, get_supabase_client, init_db

    rows_by_key = {}
    source_stats = {
        "primary_rows": 0,
        "sqlite_rows": 0,
        "sqlite_overrides": 0,
        "primary_error": "",
    }

    with app.app_context():
        init_db()
        client = get_supabase_client()
        if client is not None:
            filters = None
            if len(months) == 1:
                filters = {"month": f"eq.{months[0]}"}
            elif len(months) > 1:
                filters = {"month": _postgrest_in(months)}

            try:
                primary_rows = client.select_all(
                    "kb_recall",
                    filters=filters,
                    columns=",".join(KB_RECALL_COLUMNS),
                    order_by="id",
                    order_dir="asc",
                    page_size=1000,
                )
            except Exception as exc:
                primary_rows = []
                source_stats["primary_error"] = str(exc)

            for row in primary_rows or []:
                clean = _clean_recall_row(row)
                if not clean:
                    continue
                rows_by_key[(clean["kb_id"], clean["month"])] = clean
                source_stats["primary_rows"] += 1

        query = KBRecall.query
        if months:
            query = query.filter(KBRecall.month.in_(months))

        for item in query.order_by(KBRecall.month.asc(), KBRecall.kb_id.asc()).all():
            clean = _clean_recall_row(
                {
                    "kb_id": item.kb_id,
                    "month": item.month,
                    "recall_count": item.recall_count,
                    "valid_recall_count": item.valid_recall_count,
                    "created_at": item.created_at,
                }
            )
            if not clean:
                continue
            key = (clean["kb_id"], clean["month"])
            if key in rows_by_key:
                source_stats["sqlite_overrides"] += 1
            rows_by_key[key] = clean
            source_stats["sqlite_rows"] += 1

    rows = sorted(rows_by_key.values(), key=lambda row: (row["month"], row["kb_id"]))
    source_stats["merged_rows"] = len(rows)
    return rows, source_stats


def _summarize(rows):
    summary = {}
    for row in rows:
        month = str(row.get("month") or "unknown")
        bucket = summary.setdefault(month, {"rows": 0, "recall_count": 0, "valid_recall_count": 0})
        bucket["rows"] += 1
        bucket["recall_count"] += int(row.get("recall_count") or 0)
        bucket["valid_recall_count"] += int(row.get("valid_recall_count") or 0)
    return summary


def _preview_rows(rows, limit=3):
    preview = []
    for row in rows[:limit]:
        preview.append(
            {
                "kb_id": row.get("kb_id"),
                "month": row.get("month"),
                "recall_count": row.get("recall_count"),
                "valid_recall_count": row.get("valid_recall_count"),
            }
        )
    return preview


def _write_remote_importer(path: Path):
    path.write_text(
        textwrap.dedent(
            r'''
            #!/usr/bin/env python3
            import json
            import sys
            from datetime import datetime
            from pathlib import Path


            def chunked(items, size):
                for i in range(0, len(items), size):
                    yield items[i:i + size]


            def main():
                if len(sys.argv) < 3:
                    print("Usage: import_kb_recall_payload.py PAYLOAD_JSON BATCH_SIZE")
                    return 2

                payload_path = Path(sys.argv[1])
                batch_size = max(1, int(sys.argv[2]))

                payload = json.loads(payload_path.read_text(encoding="utf-8"))
                rows = payload.get("rows") or []
                months = sorted({str(row.get("month") or "").strip() for row in rows if isinstance(row, dict) and row.get("month")})
                replace_months = bool(payload.get("replace_months", True))

                sys.path.insert(0, str(Path.cwd()))
                from server import app, get_supabase_client, init_db

                with app.app_context():
                    init_db()
                    client = get_supabase_client()
                    if client is None:
                        print("Remote database client unavailable.")
                        return 3

                    backup_dir = Path("sync_backups")
                    backup_dir.mkdir(parents=True, exist_ok=True)
                    backup_path = backup_dir / f"kb_recall_before_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                    try:
                        existing = []
                        for month in months:
                            month_rows = client.select_all(
                                "kb_recall",
                                filters={"month": f"eq.{month}"},
                                columns="kb_id,month,recall_count,valid_recall_count,created_at",
                                order_by="kb_id",
                                order_dir="asc",
                                page_size=1000,
                            )
                            existing.extend(month_rows or [])
                        backup_path.write_text(json.dumps(existing, ensure_ascii=False, default=str), encoding="utf-8")
                        print(f"REMOTE_BACKUP={backup_path}")
                        print(f"REMOTE_BEFORE_SELECTED_MONTHS={len(existing)}")
                    except Exception as exc:
                        print(f"REMOTE_BACKUP_FAILED={exc}")
                        return 4

                    if replace_months:
                        for month in months:
                            resp = client.delete("kb_recall", {"month": f"eq.{month}"})
                            if resp is None or getattr(resp, "status_code", 500) >= 400:
                                print(f"DELETE_FAILED month={month} status={getattr(resp, 'status_code', '')} text={getattr(resp, 'text', '')}")
                                return 5
                        print(f"REMOTE_REPLACED_MONTHS={','.join(months)}")

                    total = len(rows)
                    written = 0
                    for index, batch in enumerate(chunked(rows, batch_size), start=1):
                        clean_batch = []
                        for row in batch:
                            if not isinstance(row, dict) or not row.get("kb_id") or not row.get("month"):
                                continue
                            row = dict(row)
                            # Preserve remote auto-increment IDs; (kb_id, month) is the stable key.
                            row.pop("id", None)
                            clean_batch.append(row)

                        if not clean_batch:
                            continue

                        resp = client.upsert("kb_recall", clean_batch, on_conflict="kb_id,month")
                        if getattr(resp, "status_code", 500) >= 400:
                            print(f"UPSERT_FAILED batch={index} status={getattr(resp, 'status_code', '')} text={getattr(resp, 'text', '')}")
                            return 6
                        written += len(clean_batch)
                        print(f"UPSERT_BATCH={index} WRITTEN={written}/{total}")

                    after = []
                    for month in months:
                        month_rows = client.select_all(
                            "kb_recall",
                            filters={"month": f"eq.{month}"},
                            columns="kb_id,month",
                            order_by="kb_id",
                            order_dir="asc",
                            page_size=1000,
                        )
                        after.extend(month_rows or [])
                    print(f"REMOTE_AFTER_SELECTED_MONTHS={len(after)}")
                    print(f"SYNC_WRITTEN={written}")
                    print("SYNC_TABLE=kb_recall")
                    return 0


            if __name__ == "__main__":
                raise SystemExit(main())
            '''
        ).lstrip(),
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser(description="同步本地 kb_recall 知识库治理数据到云服务器。")
    parser.add_argument("--host", default=DEFAULT_REMOTE_HOST, help="云服务器 IP/域名")
    parser.add_argument("--user", default=DEFAULT_REMOTE_USER, help="SSH 用户")
    parser.add_argument("--remote-dir", default=DEFAULT_REMOTE_DIR, help="云端项目目录")
    parser.add_argument("--remote-tmp-dir", default=DEFAULT_REMOTE_TMP_DIR, help="云端临时同步目录")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="云端 upsert 批大小")
    parser.add_argument("--identity", default="", help="SSH 私钥路径；默认自动找 ~/.ssh/id_ed25519 或 id_rsa")
    parser.add_argument(
        "--known-hosts",
        default=str(PROJECT_DIR / "mac脚本" / "known_hosts"),
        help="SSH known_hosts 文件",
    )
    parser.add_argument("--connect-timeout", type=int, default=8, help="SSH 连接超时秒数")
    parser.add_argument("--dry-run", action="store_true", help="只统计本地待同步治理数据，不连接云服务器")
    parser.add_argument("--month", action="append", default=[], help="只同步指定月份 YYYY-MM；可重复传入")
    parser.add_argument(
        "--no-replace",
        dest="replace_months",
        action="store_false",
        help="不先删除云端同月份旧数据，只按 (kb_id, month) upsert",
    )
    parser.add_argument("--keep-remote-files", action="store_true", help="同步后保留云端临时 payload/importer 文件")
    parser.set_defaults(replace_months=True)
    args = parser.parse_args()

    months = _normalize_months(args.month)
    rows, source_stats = _load_local_rows(months=months)
    summary = _summarize(rows)
    print(f"LOCAL_KB_RECALL_ROWS={len(rows)}")
    print(f"LOCAL_SOURCE_COUNTS={json.dumps(source_stats, ensure_ascii=False, sort_keys=True, default=_json_default)}")
    print(f"LOCAL_MONTHS={','.join(sorted(summary.keys()))}")
    print(f"LOCAL_MONTH_SUMMARY={json.dumps(summary, ensure_ascii=False, sort_keys=True, default=_json_default)}")
    print(f"LOCAL_PREVIEW={json.dumps(_preview_rows(rows), ensure_ascii=False, default=_json_default)}")
    print(f"REPLACE_MONTHS={1 if args.replace_months else 0}")

    if args.dry_run:
        print("DRY_RUN=1")
        return 0
    if not rows:
        print("NO_ROWS_TO_SYNC")
        return 0

    ssh_target = f"{args.user}@{args.host}"
    ssh_opts = _build_ssh_opts(args)
    remote_tmp_dir = args.remote_tmp_dir.rstrip("/")
    remote_dir_cmd = _remote_shell_path(args.remote_dir)
    remote_tmp_cmd = _remote_shell_path(remote_tmp_dir)

    with tempfile.TemporaryDirectory(prefix="kb_recall_cloud_sync_") as tmp:
        tmp_dir = Path(tmp)
        payload_path = tmp_dir / "kb_recall_payload.json"
        importer_path = tmp_dir / "import_kb_recall_payload.py"

        payload = {
            "table": "kb_recall",
            "on_conflict": "kb_id,month",
            "replace_months": args.replace_months,
            "exported_at": datetime.now().isoformat(),
            "source": "local",
            "rows": rows,
        }
        payload_path.write_text(json.dumps(payload, ensure_ascii=False, default=_json_default), encoding="utf-8")
        _write_remote_importer(importer_path)

        _run(["ssh", *ssh_opts, ssh_target, f"mkdir -p {remote_tmp_cmd}"], label=f"ssh {ssh_target} mkdir -p {args.remote_tmp_dir}")
        _run(["scp", *ssh_opts, str(payload_path), f"{ssh_target}:{remote_tmp_dir}/kb_recall_payload.json"], label="scp kb_recall payload")
        _run(["scp", *ssh_opts, str(importer_path), f"{ssh_target}:{remote_tmp_dir}/import_kb_recall_payload.py"], label="scp remote importer")

        remote_cmd = textwrap.dedent(
            f"""
            set -e
            cd {remote_dir_cmd}
            if [ -x venv/bin/python ]; then
              PY=venv/bin/python
            elif [ -x venv/bin/python3 ]; then
              PY=venv/bin/python3
            elif command -v python3 >/dev/null 2>&1; then
              PY=python3
            else
              PY=python
            fi
            "$PY" {remote_tmp_cmd}/import_kb_recall_payload.py {remote_tmp_cmd}/kb_recall_payload.json {int(args.batch_size)}
            """
        ).strip()

        if not args.keep_remote_files:
            remote_cmd += f"\nrm -f {remote_tmp_cmd}/kb_recall_payload.json {remote_tmp_cmd}/import_kb_recall_payload.py"

        _run(["ssh", *ssh_opts, ssh_target, f"bash -lc {shlex.quote(remote_cmd)}"], label="ssh remote import kb_recall")

    print("SYNC_DONE=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
