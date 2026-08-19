#!/bin/bash
# 重启 KnowBase Hub 应用

echo "=========================================="
echo "重启 KnowBase Hub 应用"
echo "=========================================="
echo ""

# 获取项目路径后再处理端口，避免误杀同端口的其他服务。
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
APP_DIR="$PROJECT_ROOT/KnowledgeBaseTool_Local"

echo "🔍 查找运行在端口 8085 的进程..."
PIDS=$(lsof -nP -tiTCP:8085 -sTCP:LISTEN 2>/dev/null || true)
for PID in $PIDS; do
    COMMAND=$(ps -p "$PID" -o command= 2>/dev/null || true)
    CWD=$(lsof -a -p "$PID" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1)
    if [ "$CWD" != "$APP_DIR" ]; then
        echo "❌ 端口进程工作目录不匹配，已停止重启以避免误杀: PID $PID"
        exit 1
    fi
    case " $COMMAND " in
        *" server.py "*)
            echo "📌 找到 KnowBase Hub 进程 PID: $PID"
            echo "🛑 正在优雅停止进程..."
            kill -TERM "$PID" 2>/dev/null || true
            for _ in $(seq 1 20); do
                kill -0 "$PID" 2>/dev/null || break
                sleep 0.1
            done
            if kill -0 "$PID" 2>/dev/null; then
                echo "⚠️ 进程未在限定时间内退出，执行强制停止: PID $PID"
                kill -KILL "$PID" 2>/dev/null || true
            fi
            ;;
        *)
            echo "❌ 8085 已被其他进程占用，未执行停止操作: PID $PID"
            echo "   命令: $COMMAND"
            exit 1
            ;;
    esac
done

if [ -z "$PIDS" ]; then
    echo "⚠️  未找到运行在端口 8085 的进程"
fi

echo ""
echo "🚀 启动 KnowBase Hub..."
echo ""

# 进入 KnowledgeBaseTool_Local 目录
cd "$APP_DIR"

# 启动应用
echo "正在启动服务器..."
echo "访问地址: http://localhost:8085"
echo ""
echo "按 Ctrl+C 停止服务器"
echo "=========================================="
echo ""

# 启动 Flask 服务器
python3 server.py
