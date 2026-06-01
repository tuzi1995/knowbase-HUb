#!/bin/bash
# -*- coding: utf-8 -*-
# 重启8085服务并验证修复

echo "=========================================="
echo "重启8085服务"
echo "=========================================="

# 切换到项目目录
cd "/Users/guoying/AI建设和学习/One/KnowBase Hub/KnowledgeBaseTool_Local"

echo ""
echo "1. 检查是否有8085进程正在运行..."
PID=$(lsof -ti:8085)

if [ -n "$PID" ]; then
    echo "   发现8085进程: $PID"
    echo "   正在停止..."
    kill -9 $PID
    sleep 2
    echo "   ✅ 已停止旧进程"
else
    echo "   没有发现8085进程"
fi

echo ""
echo "2. 验证修复是否已保存..."

# 检查 upsert 修复
if grep -q "client.upsert('button', payload, on_conflict=" server.py; then
    echo "   ✅ button 表 upsert 修复已保存"
else
    echo "   ❌ button 表 upsert 修复未保存！"
    echo "   请检查 server.py 第14171行"
fi

# 检查 change_meta 修复
if grep -q "json.dumps(merged, ensure_ascii=False)" server.py; then
    echo "   ✅ change_meta JSON 修复已保存"
else
    echo "   ❌ change_meta JSON 修复未保存！"
    echo "   请检查 server.py 第3382行"
fi

echo ""
echo "3. 启动8085服务..."
echo "   请在新的终端窗口中运行以下命令："
echo ""
echo "   cd \"/Users/guoying/AI建设和学习/One/KnowBase Hub/KnowledgeBaseTool_Local\""
echo "   python3 server.py"
echo ""
echo "   或者运行启动脚本："
echo "   ./mac脚本/启动8085-本地K-matrix工作台.command"
echo ""
echo "=========================================="
echo "等待服务启动后，请测试以下功能："
echo "=========================================="
echo ""
echo "1. 打开浏览器访问: http://localhost:8085"
echo "2. 进入机型矩阵管理"
echo "3. 修改一些单元格"
echo "4. 点击'提交已选修改'"
echo "5. 应该成功，不再报错"
echo ""
echo "如果还是报错，请提供："
echo "- 浏览器 Console 的错误信息"
echo "- 服务器终端的日志输出"
echo ""
