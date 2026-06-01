#!/bin/bash
# 快速修复导入错误脚本

echo "=========================================="
echo "知识库导入错误修复工具"
echo "=========================================="
echo ""

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# 获取项目根目录（脚本在 🗄️ 数据库/修复脚本/ 子目录中）
PROJECT_ROOT="$( cd "$SCRIPT_DIR/../.." && pwd )"

# 检查 Python 是否安装
if ! command -v python3 &> /dev/null; then
    echo "❌ 未找到 Python3，请先安装 Python"
    exit 1
fi

# 检查 psycopg2 是否安装
python3 -c "import psycopg2" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "⚠️  缺少 psycopg2 模块"
    echo "正在安装..."
    pip3 install psycopg2-binary
    if [ $? -ne 0 ]; then
        echo "❌ 安装失败，请手动运行: pip3 install psycopg2-binary"
        exit 1
    fi
fi

# 检查 PostgreSQL 是否运行
echo "🔍 检查 PostgreSQL 服务..."
pg_isready -h localhost -p 5432 &> /dev/null
if [ $? -ne 0 ]; then
    echo "⚠️  PostgreSQL 服务未运行或无法连接"
    echo "请确保 PostgreSQL 已启动"
    echo ""
    read -p "是否继续尝试修复？(y/n): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo "✅ PostgreSQL 服务正常"
fi

echo ""
echo "🚀 开始执行修复脚本..."
echo ""

# 运行修复脚本
cd "$PROJECT_ROOT/KnowledgeBaseTool_Local/DevTools"
python3 fix_import_schema.py

echo ""
echo "=========================================="
echo "修复完成！"
echo "=========================================="
