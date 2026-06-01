#!/usr/bin/env bash
# macOS-friendly server starter (replacement for the original .bat)
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if command -v python3 >/dev/null 2>&1; then
  PYEXE="python3"
elif command -v python >/dev/null 2>&1; then
  PYEXE="python"
else
  echo "ERROR: Missing python3/python in PATH." >&2
  exit 1
fi

LOG_FILE="${TMPDIR:-/tmp}/server_launch.log"
echo "START $(date '+%Y-%m-%d %H:%M:%S')" > "$LOG_FILE"
echo "Starting server.py... (log=$LOG_FILE)"

"$PYEXE" "$SCRIPT_DIR/server.py" >> "$LOG_FILE" 2>&1

echo
echo "server.py exited. Please check log:"
echo "$LOG_FILE"

# Optional: open the log in default viewer (best-effort, non-fatal).
if command -v open >/dev/null 2>&1; then
  open "$LOG_FILE" >/dev/null 2>&1 || true
fi

read -r -p "Press Enter to close..." || true

