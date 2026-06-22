#!/bin/bash
# 将测试和工具脚本移动到 DevTools 目录

set -e

BASE_DIR="/Users/guoying/AI建设和学习/One/knowbase_hub_8085"
PROJECT_DIR="$BASE_DIR/KnowledgeBaseTool_Local"
DEVTOOLS_DIR="$PROJECT_DIR/DevTools"

echo "======================================================================="
echo "将脚本移动到 DevTools 目录"
echo "======================================================================="
echo ""

# 检查目录是否存在
if [ ! -d "$PROJECT_DIR" ]; then
    echo "❌ 错误: 项目目录不存在: $PROJECT_DIR"
    exit 1
fi

# 创建 DevTools 目录（如果不存在）
if [ ! -d "$DEVTOOLS_DIR" ]; then
    echo "📁 创建 DevTools 目录..."
    mkdir -p "$DEVTOOLS_DIR"
    echo "✅ DevTools 目录已创建"
else
    echo "✅ DevTools 目录已存在"
fi

echo ""
echo "开始移动脚本..."
echo ""

# 计数器
moved_count=0
skipped_count=0
error_count=0

# 移动测试脚本
if [ -d "$BASE_DIR/🔧 脚本/测试脚本" ]; then
    echo "📦 移动测试脚本..."
    for file in "$BASE_DIR/🔧 脚本/测试脚本"/*.py; do
        if [ -f "$file" ]; then
            filename=$(basename "$file")
            target="$DEVTOOLS_DIR/$filename"
            
            if [ -f "$target" ]; then
                echo "  ⚠️  跳过 $filename (已存在)"
                ((skipped_count++))
            else
                mv "$file" "$target"
                echo "  ✅ $filename"
                ((moved_count++))
            fi
        fi
    done
fi

# 移动修复脚本
if [ -d "$BASE_DIR/🔧 脚本/修复脚本" ]; then
    echo ""
    echo "📦 移动修复脚本..."
    for file in "$BASE_DIR/🔧 脚本/修复脚本"/*.py; do
        if [ -f "$file" ]; then
            filename=$(basename "$file")
            target="$DEVTOOLS_DIR/$filename"
            
            if [ -f "$target" ]; then
                echo "  ⚠️  跳过 $filename (已存在)"
                ((skipped_count++))
            else
                mv "$file" "$target"
                echo "  ✅ $filename"
                ((moved_count++))
            fi
        fi
    done
fi

# 移动工具脚本
if [ -d "$BASE_DIR/🔧 脚本/工具脚本" ]; then
    echo ""
    echo "📦 移动工具脚本..."
    for file in "$BASE_DIR/🔧 脚本/工具脚本"/*.py; do
        if [ -f "$file" ]; then
            filename=$(basename "$file")
            target="$DEVTOOLS_DIR/$filename"
            
            if [ -f "$target" ]; then
                echo "  ⚠️  跳过 $filename (已存在)"
                ((skipped_count++))
            else
                mv "$file" "$target"
                echo "  ✅ $filename"
                ((moved_count++))
            fi
        fi
    done
fi

echo ""
echo "======================================================================="
echo "移动完成"
echo "======================================================================="
echo "成功移动: $moved_count 个文件"
echo "跳过: $skipped_count 个文件"
echo "错误: $error_count 个文件"
echo ""

# 验证
echo "验证移动结果..."
devtools_count=$(find "$DEVTOOLS_DIR" -name "*.py" -type f | wc -l | tr -d ' ')
echo "DevTools 目录中的 Python 文件数: $devtools_count"

echo ""
echo "✅ 完成！"
echo ""
echo "💡 下一步:"
echo "1. 测试脚本是否能正常运行:"
echo "   cd \"$PROJECT_DIR\""
echo "   python3 DevTools/check_all_modifications.py"
echo ""
echo "2. 如果导入失败，需要更新脚本中的 sys.path.insert 行"
echo ""
