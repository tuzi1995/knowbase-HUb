#!/bin/bash

# K-Matrix 前端部署脚本
# 用途：将压缩后的文件部署到生产环境

set -e

echo "🚀 开始部署..."
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查dist目录是否存在
if [ ! -d "dist" ]; then
    echo "❌ dist 目录不存在，请先运行 npm run build"
    exit 1
fi

# 备份当前文件
echo "📦 备份当前文件..."
BACKUP_DIR="backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# 备份需要替换的文件
if [ -f "index.html" ]; then
    cp index.html "$BACKUP_DIR/"
fi
if [ -f "test_optimization.html" ]; then
    cp test_optimization.html "$BACKUP_DIR/"
fi
if [ -f "app_v8.min.js" ]; then
    cp app_v8.min.js "$BACKUP_DIR/"
fi
if [ -f "styles.min.css" ]; then
    cp styles.min.css "$BACKUP_DIR/"
fi
if [ -f "extra_styles.min.css" ]; then
    cp extra_styles.min.css "$BACKUP_DIR/"
fi

echo -e "${GREEN}✅ 备份完成: $BACKUP_DIR${NC}"
echo ""

# 复制压缩后的文件
echo "📋 部署压缩文件..."
cp dist/app_v8.min.js ./
cp dist/styles.min.css ./
cp dist/extra_styles.min.css ./
cp dist/index.html ./index.prod.html
cp dist/test_optimization.html ./test_optimization.prod.html

echo -e "${GREEN}✅ 文件部署完成${NC}"
echo ""

# 显示文件大小对比
echo "📊 文件大小对比:"
echo "JavaScript:"
if [ -f "app_v8.js" ] && [ -f "app_v8.min.js" ]; then
    ORIG_SIZE=$(du -h app_v8.js | cut -f1)
    MIN_SIZE=$(du -h app_v8.min.js | cut -f1)
    echo "  app_v8.js: $ORIG_SIZE → app_v8.min.js: $MIN_SIZE"
fi

echo "CSS:"
if [ -f "styles.css" ] && [ -f "styles.min.css" ]; then
    ORIG_SIZE=$(du -h styles.css | cut -f1)
    MIN_SIZE=$(du -h styles.min.css | cut -f1)
    echo "  styles.css: $ORIG_SIZE → styles.min.css: $MIN_SIZE"
fi

if [ -f "extra_styles.css" ] && [ -f "extra_styles.min.css" ]; then
    ORIG_SIZE=$(du -h extra_styles.css | cut -f1)
    MIN_SIZE=$(du -h extra_styles.min.css | cut -f1)
    echo "  extra_styles.css: $ORIG_SIZE → extra_styles.min.css: $MIN_SIZE"
fi

echo ""
echo -e "${YELLOW}⚠️  注意事项:${NC}"
echo "1. 生产环境HTML文件: index.prod.html 和 test_optimization.prod.html"
echo "2. 如需回滚，使用备份目录: $BACKUP_DIR"
echo "3. 建议清除浏览器缓存后测试"
echo ""
echo -e "${GREEN}✅ 部署完成！${NC}"
