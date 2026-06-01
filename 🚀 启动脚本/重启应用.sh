#!/bin/bash
# 重启 KnowBase Hub 应用

echo "=========================================="
echo "重启 KnowBase Hub 应用"
echo "=========================================="
echo ""

# 查找并停止运行在 8085 端口的进程
echo "🔍 查找运行在端口 8085 的进程..."
PID=$(lsof -ti:8085)

if [ -z "$PID" ]; then
    echo "⚠️  未找到运行在端口 8085 的进程"
else
    echo "📌 找到进程 PID: $PID"
    echo "🛑 正在停止进程..."
    kill -9 $PID
    sleep 2
    echo "✅ 进程已停止"
fi

echo ""
echo "🚀 启动 KnowBase Hub..."
echo ""

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# 进入项目根目录（脚本在 🚀 启动脚本/ 子目录中）
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

# 进入 KnowledgeBaseTool_Local 目录
cd "$PROJECT_ROOT/KnowledgeBaseTool_Local"

# 启动应用
echo "正在启动服务器..."
echo "访问地址: http://localhost:8085"
echo ""
echo "按 Ctrl+C 停止服务器"
echo "=========================================="
echo ""

# 启动 Flask 服务器
python3 server.py
