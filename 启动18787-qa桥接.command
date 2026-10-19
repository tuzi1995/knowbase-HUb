#!/bin/zsh
set -euo pipefail

PROJECT="/Users/tuzi/个人项目/One/knowledge_base_content_detection"
RUNTIME="/Users/tuzi/个人项目/One/knowbase_hub_8085/qa-bridge-runtime"
ROOT="/Users/tuzi/个人项目/One/knowbase_hub_8085"
mkdir -p "$RUNTIME"
export KB_CONTENT_BRIDGE_PORT="18787"
export KB_CONTENT_RUNTIME_ROOT="$RUNTIME"
export KB_CONTENT_OUTPUT_ROOT="$RUNTIME/results"
export KB_CONTENT_8085_URL="http://127.0.0.1:18085"
ENV_FILE="$ROOT/KnowledgeBaseTool_Local/.kmatrix.qa.env"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  source "$ENV_FILE"
  set +a
fi
export KB_CONTENT_MODEL_RELEASE_TOKEN="${KB_CONTENT_MODEL_RELEASE_TOKEN:-}"
export KB_8085_EMBED_ENABLED="true"
exec /Users/tuzi/Develop/volta/tools/image/node/24.21.0/bin/node "$PROJECT/webapp/server.mjs"
