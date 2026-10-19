#!/bin/bash
# Restored Mac environment (2026-10-09)
source "/Users/tuzi/个人项目/One/.restore/runtime.sh"
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_PY="$SCRIPT_DIR/server.py"

# Keep local-only credentials available to launchd and Finder-launched shells.
# The file is intentionally outside tracked configuration and is optional.
LOCAL_ENV_FILE="$SCRIPT_DIR/.kmatrix.env"
if [[ -f "$LOCAL_ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$LOCAL_ENV_FILE"
  set +a
fi

export KMATRIX_BASE_DIR="${KMATRIX_BASE_DIR:-$SCRIPT_DIR}"
export KMATRIX_INSTANCE_DIR="${KMATRIX_INSTANCE_DIR:-$SCRIPT_DIR/instance}"
export KMATRIX_SQLITE_PATH="${KMATRIX_SQLITE_PATH:-$SCRIPT_DIR/instance/data.db}"
export KMATRIX_BACKUP_ROOT="${KMATRIX_BACKUP_ROOT:-/Volumes/ORICO/database/knowbasehub-backups}"
export KMATRIX_STATIC_DIR="${KMATRIX_STATIC_DIR:-$SCRIPT_DIR/link_viewer}"
# Keep shared JSON configuration in the repository-level config directory.
# Respect an explicitly supplied directory for deployments that package their
# configuration alongside the server.
export KMATRIX_CONFIG_DIR="${KMATRIX_CONFIG_DIR:-$SCRIPT_DIR/../⚙️ 配置文件}"
# AI 配置由 ToolHub 管理，固定读取项目内的受管文件，避免旧环境变量覆盖。
export KMATRIX_AI_CONFIG_PATH="$SCRIPT_DIR/ai_config.json"

if [[ -x "$SCRIPT_DIR/venv/bin/python" ]]; then
  CANDIDATES=("$SCRIPT_DIR/venv/bin/python")
elif [[ -x "$SCRIPT_DIR/.venv/bin/python" ]]; then
  CANDIDATES=("$SCRIPT_DIR/.venv/bin/python")
else
  CANDIDATES=(
    "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3"
    "/usr/local/bin/python3"
    "$(command -v python3 2>/dev/null || true)"
  )
fi

PYEXE=""
for candidate in "${CANDIDATES[@]}"; do
  if [[ -x "$candidate" ]] && "$candidate" -c 'import hashlib; raise SystemExit(0 if hasattr(hashlib, "scrypt") else 1)' >/dev/null 2>&1; then
    PYEXE="$candidate"
    break
  fi
done

if [[ -z "$PYEXE" ]]; then
  echo "ERROR: 8085 requires a Python runtime with hashlib.scrypt (Python 3.10+)." >&2
  exit 78
fi

exec "$PYEXE" "$SERVER_PY"
