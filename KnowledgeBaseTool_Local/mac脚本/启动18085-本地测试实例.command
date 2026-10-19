#!/bin/zsh
set -euo pipefail

ROOT="/Users/tuzi/个人项目/One/knowbase_hub_8085"
BASE="$ROOT/KnowledgeBaseTool_Local"
export KMATRIX_BASE_DIR="$BASE"
export KMATRIX_INSTANCE_DIR="$BASE/instance-qa"
export KMATRIX_SQLITE_PATH="$BASE/instance-qa/data.db"
export KMATRIX_STATIC_DIR="$BASE/link_viewer"
export KMATRIX_CONFIG_DIR="$ROOT/⚙️ 配置文件-qa"
export KMATRIX_BACKEND_HOST="127.0.0.1"
export KMATRIX_BACKEND_PORT="18085"
export NEW_PRODUCT_RELEASE_ENABLED="1"
# Both QA endpoints use the isolated QA environment file.
LOCAL_ENV_FILE="$BASE/.kmatrix.qa.env"
if [[ -f "$LOCAL_ENV_FILE" ]]; then
  set -a
  source "$LOCAL_ENV_FILE"
  set +a
fi
# QA sends only to the isolated 18787 bridge.
export NEW_PRODUCT_RELEASE_DOWNSTREAM_URL="http://127.0.0.1:18787/api/integrations/knowbase-hub/model-released"
export NEW_PRODUCT_RELEASE_DOWNSTREAM_TOKEN="${NEW_PRODUCT_RELEASE_DOWNSTREAM_TOKEN:-}"
export KB_CONTENT_DETECTION_SYNC_URL="http://127.0.0.1:18787/api/integrations/knowbase-hub/import-sync"

if [[ -x "$BASE/.venv/bin/python" ]]; then
  exec "$BASE/.venv/bin/python" "$BASE/server.py"
fi
exec python3 "$BASE/server.py"
