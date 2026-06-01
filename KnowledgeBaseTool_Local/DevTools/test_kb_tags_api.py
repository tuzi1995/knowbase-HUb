#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试知识库标签API
验证 /api/kb/tags 端点是否正常工作
"""

import requests
import json

# 配置
BASE_URL = "http://localhost:8085"
API_URL = f"{BASE_URL}/api/kb/tags"

def test_kb_tags_api():
    """测试获取所有标签的API"""
    print("=" * 60)
    print("测试知识库标签API")
    print("=" * 60)
    
    try:
        # 发送GET请求
        print(f"\n1. 发送请求到: {API_URL}")
        response = requests.get(API_URL, timeout=10)
        
        print(f"   状态码: {response.status_code}")
        print(f"   响应头: {dict(response.headers)}")
        
        # 检查状态码
        if response.status_code == 401:
            print("\n❌ 需要登录才能访问此API")
            print("   请先在浏览器中登录 http://localhost:8085")
            return False
        
        if response.status_code != 200:
            print(f"\n❌ API返回错误状态码: {response.status_code}")
            print(f"   响应内容: {response.text[:500]}")
            return False
        
        # 解析响应
        print("\n2. 解析响应数据")
        try:
            data = response.json()
            print(f"   数据类型: {type(data)}")
            
            if isinstance(data, list):
                print(f"   ✅ 返回数组格式正确")
                print(f"   标签数量: {len(data)}")
                
                if len(data) > 0:
                    print(f"\n3. 标签列表（前10个）:")
                    for i, tag in enumerate(data[:10], 1):
                        print(f"   {i}. {tag}")
                    
                    if len(data) > 10:
                        print(f"   ... 还有 {len(data) - 10} 个标签")
                else:
                    print("\n   ⚠️  标签列表为空")
                    print("   这可能是正常的（如果数据库中还没有标签）")
                
                print("\n✅ API测试通过！")
                return True
            else:
                print(f"   ❌ 返回数据格式错误，期望数组，实际: {type(data)}")
                print(f"   数据内容: {json.dumps(data, ensure_ascii=False, indent=2)}")
                return False
                
        except json.JSONDecodeError as e:
            print(f"   ❌ JSON解析失败: {e}")
            print(f"   响应内容: {response.text[:500]}")
            return False
            
    except requests.exceptions.ConnectionError:
        print(f"\n❌ 无法连接到服务器: {BASE_URL}")
        print("   请确保8085服务已启动")
        return False
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_kb_item_tags_api():
    """测试获取特定项目标签的API（需要提供question_wiki_id）"""
    print("\n" + "=" * 60)
    print("测试知识库项目标签API")
    print("=" * 60)
    
    # 这个API需要question_wiki_id参数，这里只是验证端点存在
    item_tags_url = f"{BASE_URL}/api/kb/item/tags"
    
    try:
        # 不提供参数，应该返回400错误
        print(f"\n1. 测试端点: {item_tags_url}")
        response = requests.get(item_tags_url, timeout=10)
        
        print(f"   状态码: {response.status_code}")
        
        if response.status_code == 401:
            print("   ⚠️  需要登录")
            return False
        elif response.status_code == 400:
            print("   ✅ 端点存在（返回400是因为缺少必需参数）")
            return True
        else:
            print(f"   ⚠️  意外的状态码: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"   ❌ 测试失败: {e}")
        return False

if __name__ == "__main__":
    print("\n🚀 开始测试知识库标签API\n")
    
    # 测试1: 获取所有标签
    result1 = test_kb_tags_api()
    
    # 测试2: 获取项目标签端点
    result2 = test_kb_item_tags_api()
    
    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    print(f"GET /api/kb/tags: {'✅ 通过' if result1 else '❌ 失败'}")
    print(f"GET /api/kb/item/tags: {'✅ 通过' if result2 else '❌ 失败'}")
    
    if result1 and result2:
        print("\n🎉 所有测试通过！")
        print("\n下一步:")
        print("1. 重启8085服务以加载新的API端点")
        print("2. 在浏览器中测试知识库管理功能")
        print("3. 验证标签选择器是否正常工作")
    else:
        print("\n⚠️  部分测试失败，请检查上述错误信息")
