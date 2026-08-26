#!/bin/bash
echo "🚀 启动 KnowBase Hub 本地版..."

# 获取项目根目录（脚本在 🚀 启动脚本/ 子目录中）
PROJECT_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"

cd "$PROJECT_ROOT/KnowledgeBaseTool_Local"

echo "服务将在 http://localhost:8085 启动"
exec "$PROJECT_ROOT/KnowledgeBaseTool_Local/run_server.sh"
