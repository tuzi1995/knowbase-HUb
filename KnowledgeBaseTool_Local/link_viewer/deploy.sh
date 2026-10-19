#!/bin/bash
# Prepare frontend output locally. Activation is an explicit runtime setting.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
npm run build
echo "前端已准备到 $SCRIPT_DIR/dist；没有改写源码或重启服务。"
echo "需要使用压缩入口时，设置该实例的 KMATRIX_STATIC_DIR 指向 dist，再安排重启。"
