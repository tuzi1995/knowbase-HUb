#!/bin/bash
# -*- coding: utf-8 -*-
# 快速验证知识库标签API修复

echo "=========================================="
echo "知识库标签API修复验证"
echo "=========================================="
echo ""

# 检查服务是否运行
echo "1. 检查8085服务状态..."
if curl -s http://localhost:8085 > /dev/null 2>&1; then
    echo "   ✅ 8085服务正在运行"
else
    echo "   ❌ 8085服务未运行"
    echo "   请先启动服务："
    echo "   ./mac脚本/启动8085-本地K-matrix工作台.command"
    exit 1
fi

echo ""
echo "2. 测试 /api/kb/tags 端点..."

# 测试API端点
response=$(curl -s -w "\n%{http_code}" http://localhost:8085/api/kb/tags)
http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')

if [ "$http_code" = "200" ]; then
    echo "   ✅ API返回200状态码"
    
    # 检查是否返回JSON数组
    if echo "$body" | python3 -c "import sys, json; data=json.load(sys.stdin); exit(0 if isinstance(data, list) else 1)" 2>/dev/null; then
        echo "   ✅ 返回格式正确（JSON数组）"
        
        # 统计标签数量
        tag_count=$(echo "$body" | python3 -c "import sys, json; print(len(json.load(sys.stdin)))" 2>/dev/null)
        echo "   ✅ 标签数量: $tag_count"
        
        # 显示前5个标签
        if [ "$tag_count" -gt 0 ]; then
            echo ""
            echo "   前5个标签："
            echo "$body" | python3 -c "import sys, json; tags=json.load(sys.stdin); [print(f'   - {tag}') for tag in tags[:5]]" 2>/dev/null
        fi
    else
        echo "   ⚠️  返回格式不正确"
        echo "   响应内容: $body"
    fi
elif [ "$http_code" = "401" ]; then
    echo "   ⚠️  需要登录（401）"
    echo "   这是正常的，请在浏览器中登录后再测试"
elif [ "$http_code" = "404" ]; then
    echo "   ❌ API端点不存在（404）"
    echo "   请确保已重启8085服务以加载新的API端点"
else
    echo "   ❌ API返回错误状态码: $http_code"
    echo "   响应内容: $body"
fi

echo ""
echo "3. 测试 /api/kb/item/tags 端点..."
response2=$(curl -s -w "\n%{http_code}" "http://localhost:8085/api/kb/item/tags?question_wiki_id=test")
http_code2=$(echo "$response2" | tail -n1)

if [ "$http_code2" = "200" ] || [ "$http_code2" = "400" ] || [ "$http_code2" = "401" ]; then
    echo "   ✅ 端点存在（状态码: $http_code2）"
else
    echo "   ⚠️  端点状态异常（状态码: $http_code2）"
fi

echo ""
echo "=========================================="
echo "验证总结"
echo "=========================================="

if [ "$http_code" = "200" ]; then
    echo "✅ 修复成功！标签API正常工作"
    echo ""
    echo "下一步："
    echo "1. 在浏览器中打开 http://localhost:8085"
    echo "2. 登录系统"
    echo "3. 进入知识库管理"
    echo "4. 点击编辑按钮测试标签选择器"
elif [ "$http_code" = "401" ]; then
    echo "⚠️  API端点存在，但需要登录"
    echo ""
    echo "下一步："
    echo "1. 在浏览器中打开 http://localhost:8085"
    echo "2. 登录系统"
    echo "3. 运行: python3 test_kb_tags_api.py"
elif [ "$http_code" = "404" ]; then
    echo "❌ API端点不存在，需要重启服务"
    echo ""
    echo "请执行："
    echo "1. 停止当前8085服务（Ctrl+C）"
    echo "2. 重新启动: ./mac脚本/启动8085-本地K-matrix工作台.command"
    echo "3. 再次运行此脚本验证"
else
    echo "⚠️  验证未完全通过，请检查上述错误信息"
fi

echo ""
