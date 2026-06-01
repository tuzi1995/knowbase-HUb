#!/bin/bash

# 脚本文件整理
# 将根目录的脚本文件移动到合适的目录

BASE_DIR="."

echo "开始整理脚本文件..."

# 1. Python工具脚本 -> 🔧 脚本/工具脚本/
echo "移动Python工具脚本..."
mkdir -p "🔧 脚本/工具脚本"
mv check_database_count.py "🔧 脚本/工具脚本/" 2>/dev/null
mv fix_devtools_imports.py "🔧 脚本/工具脚本/" 2>/dev/null
mv organize_files.py "🔧 脚本/工具脚本/" 2>/dev/null
mv update_doc_paths.py "🔧 脚本/工具脚本/" 2>/dev/null

# 2. Shell脚本 -> 🔧 脚本/Shell脚本/
echo "移动Shell脚本..."
mkdir -p "🔧 脚本/Shell脚本"
mv move_scripts_to_devtools.sh "🔧 脚本/Shell脚本/" 2>/dev/null
mv organize_md_files.sh "🔧 脚本/Shell脚本/" 2>/dev/null

# 3. 数据库修复脚本 -> 🗄️ 数据库/修复脚本/
echo "移动数据库修复脚本..."
mkdir -p "🗄️ 数据库/修复脚本"
mv 修复导入错误-添加缺失字段.sql "🗄️ 数据库/修复脚本/" 2>/dev/null
mv 修复导入错误.sh "🗄️ 数据库/修复脚本/" 2>/dev/null

# 4. 启动脚本保留在 🚀 启动脚本/ 目录
echo "检查启动脚本..."
if [ -f "重启应用.sh" ]; then
    mv 重启应用.sh "🚀 启动脚本/" 2>/dev/null
fi

echo "✅ 脚本文件整理完成！"
echo ""
echo "整理结果："
echo "- Python工具脚本: $(ls -1 "🔧 脚本/工具脚本/" 2>/dev/null | wc -l) 个文件"
echo "- Shell脚本: $(ls -1 "🔧 脚本/Shell脚本/" 2>/dev/null | wc -l) 个文件"
echo "- 数据库修复脚本: $(ls -1 "🗄️ 数据库/修复脚本/" 2>/dev/null | wc -l) 个文件"
echo "- 启动脚本: $(ls -1 "🚀 启动脚本/" 2>/dev/null | wc -l) 个文件"
echo "- 根目录剩余文件: $(ls -1 *.py *.sh *.sql 2>/dev/null | wc -l) 个文件"
