#!/usr/bin/env python3
"""
Sync local AI scoring results (kb_scores) to the deployed cloud server.

The script reads kb_scores from the local app database, uploads a temporary JSON
payload over SSH, then asks the remote app to upsert rows into its own database
using server.py's configured database client.
"""

import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
import textwrap
from datetime import datetime
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
DEFAULT_REMOTE_USER = "root"
DEFAULT_REMOTE_HOST = "112.126.63.84"
DEFAULT_REMOTE_DIR = "~/k-matrix"
DEFAULT_REMOTE_TMP_DIR = "~/k-matrix/tmp_sync"
DEFAULT_BATCH_SIZE = 300

KB_SCORE_COLUMNS = [
    "kb_id",
    "question_content",
    "answer_content",
    "status",
    "total_score",
    "remarks",
    "score_data",
    "updated_at",
]


def _json_default(value):
    if isinstance(value, datetime):
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


def _load_local_rows(scored_only: bool):
    sys.path.insert(0, str(PROJECT_DIR))
    os.chdir(PROJECT_DIR)

    from server import app, get_supabase_client, init_db

    with app.app_context():
        init_db()
        client = get_supabase_client()
        if client is None:
            raise RuntimeError("本地数据库客户端不可用，请检查 supabase_config_local.json")

        rows = client.select_all(
            "kb_scores",
            columns=",".join(KB_SCORE_COLUMNS),
            order_by="kb_id",
            order_dir="asc",
            page_size=1000,
        )

    normalized = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        clean = {key: row.get(key) for key in KB_SCORE_COLUMNS if key in row}
        if not clean.get("kb_id"):
            continue
        if scored_only and str(clean.get("status") or "") != "scored":
            continue
        normalized.append(clean)
    return normalized


def _summarize(rows):
    counts = {}
    for row in rows:
        status = str(row.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _preview_rows(rows, limit=3):
    preview = []
    for row in rows[:limit]:
        preview.append(
            {
                "kb_id": row.get("kb_id"),
                "status": row.get("status"),
                "total_score": row.get("total_score"),
                "updated_at": row.get("updated_at"),
            }
        )
    return preview


def _write_remote_importer(path: Path):
    path.write_text(
        textwrap.dedent(
            r'''
            #!/usr/bin/env python3
            import json
            import os
            import sys
            from datetime import datetime
            from pathlib import Path


            def chunked(items, size):
                for i in range(0, len(items), size):
                    yield items[i:i + size]


            def main():
                if len(sys.argv) < 3:
                    print("Usage: import_kb_scores_payload.py PAYLOAD_JSON BATCH_SIZE")
                    return 2

                payload_path = Path(sys.argv[1])
                batch_size = max(1, int(sys.argv[2]))

                payload = json.loads(payload_path.read_text(encoding="utf-8"))
                rows = payload.get("rows") or []

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
                    backup_path = backup_dir / f"kb_scores_before_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                    try:
                        existing = client.select_all("kb_scores", order_by="kb_id", order_dir="asc", page_size=1000)
                        backup_path.write_text(json.dumps(existing, ensure_ascii=False, default=str), encoding="utf-8")
                        print(f"REMOTE_BACKUP={backup_path}")
                        print(f"REMOTE_BEFORE={len(existing)}")
                    except Exception as exc:
                        print(f"REMOTE_BACKUP_FAILED={exc}")
                        return 4

                    total = len(rows)
                    written = 0
                    for index, batch in enumerate(chunked(rows, batch_size), start=1):
                        clean_batch = []
                        for row in batch:
                            if not isinstance(row, dict) or not row.get("kb_id"):
                                continue
                            row = dict(row)
                            # Preserve remote auto-increment IDs; kb_id is the stable key.
                            row.pop("id", None)
                            clean_batch.append(row)

                        if not clean_batch:
                            continue

                        resp = client.upsert("kb_scores", clean_batch, on_conflict="kb_id")
                        if getattr(resp, "status_code", 500) >= 400:
                            print(f"UPSERT_FAILED batch={index} status={getattr(resp, 'status_code', '')} text={getattr(resp, 'text', '')}")
                            return 5
                        written += len(clean_batch)
                        print(f"UPSERT_BATCH={index} WRITTEN={written}/{total}")

                    after = client.select_all("kb_scores", columns="kb_id,status", order_by="kb_id", order_dir="asc", page_size=1000)
                    print(f"REMOTE_AFTER={len(after)}")
                    print(f"SYNC_WRITTEN={written}")
                    print(f"SYNC_TABLE=kb_scores")
                    return 0


            if __name__ == "__main__":
                raise SystemExit(main())
            '''
        ).lstrip(),
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser(description="同步本地 kb_scores AI 评分结果到云服务器。")
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
    parser.add_argument("--dry-run", action="store_true", help="只统计本地待同步评分，不连接云服务器")
    parser.add_argument("--scored-only", action="store_true", help="只同步 status=scored 的评分结果")
    parser.add_argument("--keep-remote-files", action="store_true", help="同步后保留云端临时 payload/importer 文件")
    args = parser.parse_args()

    rows = _load_local_rows(scored_only=args.scored_only)
    summary = _summarize(rows)
    print(f"LOCAL_KB_SCORES={len(rows)}")
    print(f"LOCAL_STATUS_COUNTS={json.dumps(summary, ensure_ascii=False, sort_keys=True)}")
    print(f"LOCAL_PREVIEW={json.dumps(_preview_rows(rows), ensure_ascii=False, default=_json_default)}")

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

    with tempfile.TemporaryDirectory(prefix="kb_scores_cloud_sync_") as tmp:
        tmp_dir = Path(tmp)
        payload_path = tmp_dir / "kb_scores_payload.json"
        importer_path = tmp_dir / "import_kb_scores_payload.py"

        payload = {
            "table": "kb_scores",
            "on_conflict": "kb_id",
            "exported_at": datetime.now().isoformat(),
            "source": "local",
            "rows": rows,
        }
        payload_path.write_text(json.dumps(payload, ensure_ascii=False, default=_json_default), encoding="utf-8")
        _write_remote_importer(importer_path)

        _run(["ssh", *ssh_opts, ssh_target, f"mkdir -p {remote_tmp_cmd}"], label=f"ssh {ssh_target} mkdir -p {args.remote_tmp_dir}")
        _run(["scp", *ssh_opts, str(payload_path), f"{ssh_target}:{remote_tmp_dir}/kb_scores_payload.json"], label="scp kb_scores payload")
        _run(["scp", *ssh_opts, str(importer_path), f"{ssh_target}:{remote_tmp_dir}/import_kb_scores_payload.py"], label="scp remote importer")

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
            "$PY" {remote_tmp_cmd}/import_kb_scores_payload.py {remote_tmp_cmd}/kb_scores_payload.json {int(args.batch_size)}
            """
        ).strip()

        if not args.keep_remote_files:
            remote_cmd += f"\nrm -f {remote_tmp_cmd}/kb_scores_payload.json {remote_tmp_cmd}/import_kb_scores_payload.py"

        _run(["ssh", *ssh_opts, ssh_target, f"bash -lc {shlex.quote(remote_cmd)}"], label="ssh remote import kb_scores")

    print("SYNC_DONE=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
