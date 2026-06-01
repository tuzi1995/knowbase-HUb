#!/usr/bin/env bash
# macOS-friendly server starter for KnowBase Hub Local
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SERVER_PY="$PROJECT_DIR/server.py"
REQ_FILE="$PROJECT_DIR/requirements.txt"
CONFIG_FILE="$PROJECT_DIR/supabase_config_local.json"

echo "🚀 启动 KnowBase Hub 本地版..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if command -v python3 >/dev/null 2>&1; then
  PYEXE="python3"
elif command -v python >/dev/null 2>&1; then
  PYEXE="python"
else
  echo "❌ ERROR: Missing python3/python in PATH." >&2
  read -r -p "Press Enter to close..." || true
  exit 1
fi

if [[ -x "$PROJECT_DIR/venv/bin/python" ]]; then
  PYEXE="$PROJECT_DIR/venv/bin/python"
  echo "✅ 使用虚拟环境: venv"
elif [[ -x "$PROJECT_DIR/.venv/bin/python" ]]; then
  PYEXE="$PROJECT_DIR/.venv/bin/python"
  echo "✅ 使用虚拟环境: .venv"
else
  echo "ℹ️  使用系统 Python: $PYEXE"
fi

LOG_FILE="${TMPDIR:-/tmp}/knowledgebase_server_launch.log"
echo "START $(date '+%Y-%m-%d %H:%M:%S')" > "$LOG_FILE"
echo "📝 日志文件: $LOG_FILE"
echo "Resolved server path: $SERVER_PY" >> "$LOG_FILE"
echo "Using python: $PYEXE" >> "$LOG_FILE"

if [[ ! -f "$SERVER_PY" ]]; then
  echo "❌ ERROR: server.py not found: $SERVER_PY" | tee -a "$LOG_FILE" >&2
  read -r -p "Press Enter to close..." || true
  exit 1
fi

# 检查本地数据库配置（本地版必需）
if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "❌ ERROR: 未找到本地配置文件!" | tee -a "$LOG_FILE" >&2
  echo "   缺失文件: supabase_config_local.json"
  echo ""
  echo "💡 请确保配置文件存在并包含本地数据库连接信息："
  echo "   {\"local_db\": {\"host\": \"localhost\", \"port\": 5432, ...}}"
  echo ""
  read -r -p "Press Enter to close..." || true
  exit 1
fi
echo "✅ 本地数据库配置文件已就绪"

echo ""
echo "🔍 检查 PostgreSQL 服务..."

# 检查 PostgreSQL 是否运行
if command -v /Library/PostgreSQL/18/bin/pg_isready >/dev/null 2>&1; then
  if /Library/PostgreSQL/18/bin/pg_isready -h localhost -p 5432 >/dev/null 2>&1; then
    echo "✅ PostgreSQL 服务正在运行"
  else
    echo "❌ ERROR: PostgreSQL 服务未运行!" | tee -a "$LOG_FILE" >&2
    echo ""
    echo "💡 请先启动 PostgreSQL 服务："
    echo "   方法1: 使用 pgAdmin 启动"
    echo "   方法2: sudo /Library/PostgreSQL/18/bin/pg_ctl -D /Library/PostgreSQL/18/data start"
    echo ""
    read -r -p "Press Enter to close..." || true
    exit 1
  fi
else
  echo "⚠️  警告: 无法检测 PostgreSQL 状态（pg_isready 未找到）"
  echo "   如果启动失败，请确认 PostgreSQL 已安装并运行"
fi

echo ""
echo "🔍 检查依赖包..."

MISSING_DEPS=$("$PYEXE" - <<'PY'
import importlib.util
import sys

# 核心依赖检查
mods = [
    "flask", "flask_cors", "flask_sqlalchemy", "flask_login",
    "sqlalchemy", "pandas", "openpyxl", "requests",
    "psycopg2", "werkzeug", "bs4"
]
missing = []
for m in mods:
    if importlib.util.find_spec(m) is None:
        missing.append(m)

if missing:
    print(",".join(missing))
else:
    # 如果核心依赖都有，检查 psycopg2 版本
    try:
        import psycopg2
        # 测试是否可以正常导入
    except Exception as e:
        print("psycopg2")
PY
)

if [[ -n "$MISSING_DEPS" ]]; then
  echo "⚠️  缺少依赖包: $MISSING_DEPS" | tee -a "$LOG_FILE"
  if [[ -f "$REQ_FILE" ]]; then
    echo "📦 正在安装依赖包..." | tee -a "$LOG_FILE"
    if ! "$PYEXE" -m pip install -r "$REQ_FILE" >> "$LOG_FILE" 2>&1; then
      echo "❌ ERROR: pip install failed. See log: $LOG_FILE" | tee -a "$LOG_FILE" >&2
      read -r -p "Press Enter to close..." || true
      exit 1
    fi
    echo "✅ 依赖包安装完成"
  else
    echo "❌ ERROR: requirements.txt not found: $REQ_FILE" | tee -a "$LOG_FILE" >&2
    read -r -p "Press Enter to close..." || true
    exit 1
  fi
else
  echo "✅ 所有依赖包已安装"
fi

cd "$PROJECT_DIR" || {
  echo "❌ ERROR: cd failed: $PROJECT_DIR" | tee -a "$LOG_FILE" >&2
  read -r -p "Press Enter to close..." || true
  exit 1
}

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎯 启动服务器..."
echo "📍 本地访问: http://localhost:8085"
echo "📍 局域网访问: http://$(ipconfig getifaddr en0 2>/dev/null || echo "0.0.0.0"):8085"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "💡 提示: 按 Ctrl+C 停止服务器"
echo ""

"$PYEXE" "$SERVER_PY" 2>&1 | tee -a "$LOG_FILE"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🛑 服务器已停止"
echo "📝 完整日志: $LOG_FILE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Optional: open the log in default viewer (best-effort, non-fatal).
if command -v open >/dev/null 2>&1; then
  open "$LOG_FILE" >/dev/null 2>&1 || true
fi

read -r -p "按 Enter 键关闭..." || true

