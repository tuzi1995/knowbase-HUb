#!/bin/zsh
# 8085 云端发布：代码、SQLite 运行态与 PostgreSQL 主库合并同步。
# 默认仅预检；只有传入 --apply 才会写入云端。

set -euo pipefail

apply_release=false
resume_release_id=""
case "${1:-}" in
  ""|--preflight) ;;
  --apply) apply_release=true ;;
  --resume)
    [[ -n "${2:-}" ]] || { print -u2 "用法: $0 --resume <release_id>"; exit 2; }
    apply_release=true
    resume_release_id="$2"
    ;;
  *)
    print -u2 "用法: $0 [--preflight|--apply|--resume <release_id>]"
    exit 2
    ;;
esac

script_dir="$(cd "$(dirname "$0")" && pwd)"
project_dir="$(cd "$script_dir/.." && pwd)"
workspace_dir="$(cd "$project_dir/.." && pwd)"
startup_dir="$workspace_dir/🚀 启动脚本"
python_bin="${PYTHON_BIN:-python3}"

remote_user="root"
remote_host="112.126.63.84"
remote_dir="/root/k-matrix"
remote_target="${remote_user}@${remote_host}"
release_id="${resume_release_id:-kmatrix_$(date '+%Y%m%d_%H%M%S')}"
release_work_dir="$(mktemp -d "${TMPDIR:-/tmp}/kmatrix-cloud-release.XXXXXX")"

cleanup() {
  [[ "$release_work_dir" == "${TMPDIR:-/tmp}/kmatrix-cloud-release."* ]] || return 0
  rm -rf -- "$release_work_dir"
}
trap cleanup EXIT

local_sqlite="$project_dir/instance/data.db"
local_config="$project_dir/supabase_config_local.json"
primary_sync="$project_dir/Scripts/primary_db_sync.py"
sqlite_snapshot="$release_work_dir/data.db"
sqlite_archive="$release_work_dir/data.db.gz"
sqlite_manifest="$release_work_dir/sqlite_manifest.json"
primary_snapshot="$release_work_dir/primary.ndjson.gz"

for required in "$local_sqlite" "$local_config" "$primary_sync" "$startup_dir/package_deploy.py"; do
  [[ -f "$required" ]] || { print -u2 "缺少发布所需文件: $required"; exit 1; }
done
command -v "$python_bin" >/dev/null 2>&1 || { print -u2 "未找到 Python: $python_bin"; exit 1; }
command -v ssh >/dev/null 2>&1 || { print -u2 "未找到 ssh"; exit 1; }
command -v scp >/dev/null 2>&1 || { print -u2 "未找到 scp"; exit 1; }
command -v rsync >/dev/null 2>&1 || { print -u2 "未找到 rsync"; exit 1; }

print "[1/5] 本机 SQLite 与主库预检..."
"$python_bin" - "$local_sqlite" "$sqlite_manifest" "$sqlite_snapshot" "$sqlite_archive" "$apply_release" <<'PY'
import gzip
import json
import shutil
import sqlite3
import sys
from pathlib import Path

source_path = Path(sys.argv[1])
manifest_path = Path(sys.argv[2])
snapshot_path = Path(sys.argv[3])
archive_path = Path(sys.argv[4])
apply_release = sys.argv[5].lower() == "true"

def table_counts(connection):
    tables = [
        row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    return {name: connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] for name in tables}

with sqlite3.connect(source_path) as source:
    quick_check = source.execute("PRAGMA quick_check").fetchone()[0]
    if quick_check != "ok":
        raise SystemExit(f"source sqlite quick_check failed: {quick_check}")
    counts = table_counts(source)
    if apply_release:
        with sqlite3.connect(snapshot_path) as destination:
            source.backup(destination)
            copied_check = destination.execute("PRAGMA quick_check").fetchone()[0]
            if copied_check != "ok" or table_counts(destination) != counts:
                raise SystemExit("SQLite snapshot integrity/count verification failed")
        with snapshot_path.open("rb") as source_file, gzip.open(archive_path, "wb", compresslevel=9) as archive_file:
            shutil.copyfileobj(source_file, archive_file)

manifest_path.write_text(json.dumps({"quick_check": quick_check, "counts": counts}, ensure_ascii=False, sort_keys=True), encoding="utf-8")
print(json.dumps({"sqlite_tables": len(counts), "sqlite_rows": sum(counts.values()), "snapshot_created": apply_release}, ensure_ascii=False))
PY

"$python_bin" "$primary_sync" export --config "$local_config" --file "$primary_snapshot" --dry-run >/dev/null

if ! $apply_release; then
  print "预检通过：未向云端写入。执行 $0 --apply 才会发布。"
  exit 0
fi

print "[2/5] 创建主库合并档案与无凭据代码包..."
"$python_bin" "$primary_sync" export --config "$local_config" --file "$primary_snapshot" >/dev/null
primary_sha="$("$python_bin" - "$primary_snapshot" <<'PY'
import gzip
import hashlib
import sys
digest = hashlib.sha256()
with gzip.open(sys.argv[1], 'rb') as stream:
    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
        digest.update(chunk)
print(digest.hexdigest())
PY
)"
remote_stage="$remote_dir/.release_staging/$release_id"
if [[ -n "$resume_release_id" ]]; then
  package_name="$(ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new "$remote_target" "cd '$remote_stage' && find . -maxdepth 1 -type f -name 'KnowledgeBaseTool_Deploy_*.zip' -printf '%f\\n'")"
  [[ -n "$package_name" ]] || { print -u2 "云端暂存包不存在: $remote_stage"; exit 1; }
else
  "$python_bin" "$startup_dir/package_deploy.py" >/dev/null
  package_file="$("$python_bin" - "$startup_dir" <<'PY'
from pathlib import Path
import sys
root = Path(sys.argv[1])
latest = max(root.glob('KnowledgeBaseTool_Deploy_*.zip'), key=lambda path: path.stat().st_mtime)
print(latest)
PY
)"
  package_name="$(basename "$package_file")"
fi
sqlite_sha="$(shasum -a 256 "$sqlite_snapshot" | awk '{print $1}')"

print "[3/5] 校验云端连接和发布前备份空间..."
ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new "$remote_target" "cd '$remote_dir' && test -f supabase_config_local.json && test -f ai_config.json && test -f scoring_config.json && command -v unzip >/dev/null && command -v gzip >/dev/null && command -v pg_dump >/dev/null && command -v pg_restore >/dev/null && test -x venv/bin/python" >/dev/null
if [[ -n "$resume_release_id" ]]; then
  ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new "$remote_target" "test -f '$remote_stage/$package_name' && test -f '$remote_stage/data.db.gz' && test -f '$remote_stage/sqlite_manifest.json' && test -f '$remote_stage/primary.ndjson.gz'" >/dev/null
else
  ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new "$remote_target" "mkdir -p '$remote_stage' '$remote_dir/backups/$release_id'" >/dev/null
  for artifact in "$package_file" "$sqlite_archive" "$sqlite_manifest" "$primary_snapshot"; do
    print "上传: $(basename "$artifact")"
    rsync -az --partial --append \
      -e "ssh -o BatchMode=yes -o ConnectTimeout=30 -o StrictHostKeyChecking=accept-new" \
      "$artifact" "${remote_target}:${remote_stage}/"
  done
fi

print "[4/5] 云端备份、合并数据并重启 8085..."
ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new "$remote_target" "RELEASE_ID='$release_id' REMOTE_DIR='$remote_dir' PACKAGE_NAME='$package_name' SQLITE_SHA='$sqlite_sha' PRIMARY_SHA='$primary_sha' bash -s" <<'REMOTE'
set -Eeuo pipefail

release_stage="$REMOTE_DIR/.release_staging/$RELEASE_ID"
release_backup="$REMOTE_DIR/backups/$RELEASE_ID"
python_bin="$REMOTE_DIR/venv/bin/python"
sqlite_backup="$release_backup/data.db.before"
primary_backup="$release_backup/primary.before.dump"
runtime_backup="$release_backup/runtime.before.tgz"
sync_script="$release_stage/runtime/Scripts/primary_db_sync.py"

stop_service() {
  if [[ -s "$REMOTE_DIR/server.pid" ]]; then
    pid="$(cat "$REMOTE_DIR/server.pid")"
    kill -TERM "$pid" 2>/dev/null || true
    for _ in 1 2 3 4 5 6 7 8 9 10; do
      kill -0 "$pid" 2>/dev/null || break
      sleep 1
    done
    kill -KILL "$pid" 2>/dev/null || true
  fi
  pkill -TERM -f 'gunicorn.*server:app' 2>/dev/null || true
  rm -f "$REMOTE_DIR/server.pid"
}

start_service() {
  cd "$REMOTE_DIR"
  if [[ -f .kmatrix.env ]]; then
    set -a
    . ./.kmatrix.env
    set +a
  fi
  "$python_bin" -m gunicorn -w 2 -b 0.0.0.0:8085 server:app --daemon --pid server.pid --access-logfile server.log --error-logfile server.log --timeout 300 --graceful-timeout 60 --log-level info
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    "$python_bin" -c 'import socket,sys; s=socket.socket(); s.settimeout(1); ok=s.connect_ex(("127.0.0.1",8085))==0; s.close(); sys.exit(0 if ok else 1)' && return 0
    sleep 1
  done
  return 1
}

rollback() {
  trap - ERR
  echo "RELEASE_FAILED_ROLLING_BACK" >&2
  stop_service || true
  [[ -f "$runtime_backup" ]] && tar -xzf "$runtime_backup" -C "$REMOTE_DIR" || true
  [[ -f "$sqlite_backup" ]] && cp -f "$sqlite_backup" "$REMOTE_DIR/instance/data.db" || true
  [[ -f "$primary_backup" ]] && "$python_bin" "$sync_script" restore --config "$REMOTE_DIR/supabase_config_local.json" --file "$primary_backup" || true
  start_service || true
  exit 1
}
trap rollback ERR

cd "$REMOTE_DIR"
test -f "$release_stage/$PACKAGE_NAME"
test -f "$release_stage/data.db.gz"
test -f "$release_stage/sqlite_manifest.json"
test -f "$release_stage/primary.ndjson.gz"
primary_actual_sha="$("$python_bin" - "$release_stage/primary.ndjson.gz" <<'PY'
import gzip
import hashlib
import sys
digest = hashlib.sha256()
with gzip.open(sys.argv[1], 'rb') as stream:
    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
        digest.update(chunk)
print(digest.hexdigest())
PY
)"
test "$primary_actual_sha" = "$PRIMARY_SHA"
gzip -t "$release_stage/data.db.gz"
gzip -dc "$release_stage/data.db.gz" > "$release_stage/data.db"
test "$(sha256sum "$release_stage/data.db" | awk '{print $1}')" = "$SQLITE_SHA"
mkdir -p "$release_stage/runtime"
unzip -q -o "$release_stage/$PACKAGE_NAME" -d "$release_stage/runtime"
test -f "$sync_script"
"$python_bin" - "$release_stage/data.db" <<'PY'
import sqlite3
import sys
with sqlite3.connect(sys.argv[1]) as connection:
    check = connection.execute("PRAGMA quick_check").fetchone()[0]
    if check != "ok":
        raise SystemExit(check)
print("SQLITE_STAGING_OK")
PY

config_hash_before="$(sha256sum supabase_config_local.json ai_config.json scoring_config.json | sha256sum | awk '{print $1}')"
"$python_bin" "$sync_script" backup --config supabase_config_local.json --file "$primary_backup"
cp -f instance/data.db "$sqlite_backup"
runtime_items=()
for path in \
  server.py scoring_logic.py llm_score_evaluator.py matrix_submit_validation.py \
  parameter_check.py knowledge_graph.py kb_v1_sync.py requirements.txt \
  product_catalog.json model_mappings.json link_viewer prompt Scripts/migrate_parameter_check_postgres.py Scripts/primary_db_sync.py; do
  [[ -e "$path" ]] && runtime_items+=("$path")
done
(( ${#runtime_items[@]} > 0 ))
tar -czf "$runtime_backup" "${runtime_items[@]}"

stop_service
unzip -q -o "$release_stage/$PACKAGE_NAME" -d "$REMOTE_DIR"
config_hash_after="$(sha256sum supabase_config_local.json ai_config.json scoring_config.json | sha256sum | awk '{print $1}')"
test "$config_hash_before" = "$config_hash_after"
cp -f "$release_stage/data.db" instance/data.db
"$python_bin" -c 'import server; server.init_db(); print("RUNTIME_IMPORT_OK")'
"$python_bin" Scripts/migrate_parameter_check_postgres.py --config supabase_config_local.json
"$python_bin" "$sync_script" import --config supabase_config_local.json --file "$release_stage/primary.ndjson.gz"

"$python_bin" - "$release_stage/sqlite_manifest.json" instance/data.db <<'PY'
import json
import sqlite3
import sys
expected = json.load(open(sys.argv[1], encoding="utf-8"))["counts"]
with sqlite3.connect(sys.argv[2]) as connection:
    actual = {name: connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] for name in expected}
if actual != expected:
    raise SystemExit("cloud sqlite counts do not match source snapshot")
print("SQLITE_COUNTS_OK")
PY

start_service
"$python_bin" - <<'PY'
from urllib.request import urlopen
response = urlopen('http://127.0.0.1:8085/', timeout=10)
if response.status != 200:
    raise SystemExit(f'HTTP {response.status}')
print('HTTP_ROOT_OK')
PY
rm -rf -- "$release_stage"
trap - ERR
echo "RELEASE_OK $RELEASE_ID"
REMOTE

print "[5/5] 云端发布完成。已保留云端发布前备份：$remote_dir/backups/$release_id"
