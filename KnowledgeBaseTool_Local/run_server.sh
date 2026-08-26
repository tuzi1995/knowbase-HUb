#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_PY="$SCRIPT_DIR/server.py"

export KMATRIX_BASE_DIR="${KMATRIX_BASE_DIR:-$SCRIPT_DIR}"
export KMATRIX_INSTANCE_DIR="${KMATRIX_INSTANCE_DIR:-$SCRIPT_DIR/instance}"
export KMATRIX_SQLITE_PATH="${KMATRIX_SQLITE_PATH:-$SCRIPT_DIR/instance/data.db}"
export KMATRIX_BACKUP_ROOT="${KMATRIX_BACKUP_ROOT:-/Volumes/ORICO/database/knowbasehub-backups}"
export KMATRIX_STATIC_DIR="${KMATRIX_STATIC_DIR:-$SCRIPT_DIR/link_viewer}"
export KMATRIX_CONFIG_DIR="${KMATRIX_CONFIG_DIR:-$SCRIPT_DIR/../⚙️ 配置文件}"

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
