#!/usr/bin/env python3
"""
测试产品分类筛选功能
用于验证修复后的产品分类筛选是否正常工作
"""

import requests
import json

# 配置
BASE_URL = "http://localhost:8085"
API_ENDPOINT = f"{BASE_URL}/api/kb/data"

def test_category_filter(category_name, description=""):
    """测试单个分类筛选"""
    print(f"\n{'='*60}")
    print(f"测试: {description or category_name}")
    print(f"{'='*60}")
    
    params = {
        'table': 'knowledge_base_v1',
        'page': 1,
        'pageSize': 10,
        'product_categories': category_name
    }
    
    try:
        response = requests.get(API_ENDPOINT, params=params)
        
        if response.status_code == 401:
            print("❌ 错误: 需要登录")
            print("   请先在浏览器中登录 http://localhost:8085")
            return False
        
        if response.status_code != 200:
            print(f"❌ 错误: HTTP {response.status_code}")
            print(f"   响应: {response.text[:200]}")
            return False
        
        data = response.json()
        
        if isinstance(data, dict):
            success = data.get('success', True)
            items = data.get('data', [])
            total = data.get('total', len(items))
        elif isinstance(data, list):
            success = True
            items = data
            total = len(items)
        else:
            print(f"❌ 错误: 未知的响应格式")
            return False
        
        if not success:
            print(f"❌ API 返回失败: {data.get('message', '未知错误')}")
            return False
        
        print(f"✓ 成功获取数据")
        print(f"  总数: {total}")
        print(f"  当前页数据: {len(items)}")
        
        if items:
            print(f"\n  示例数据（前3条）:")
            for i, item in enumerate(items[:3], 1):
                wiki_id = item.get('question_wiki_id', 'N/A')
                question = item.get('question', 'N/A')[:50]
                category = item.get('product_category_name', 'N/A')
                print(f"    {i}. ID: {wiki_id}")
                print(f"       问题: {question}...")
                print(f"       分类: {category}")
        else:
            print(f"\n  ⚠️  暂无数据")
        
        return total > 0
        
    except requests.exceptions.ConnectionError:
        print("❌ 错误: 无法连接到服务器")
        print("   请确保服务器正在运行: http://localhost:8085")
        return False
    except Exception as e:
        print(f"❌ 错误: {str(e)}")
        return False

def test_multiple_categories(categories, description=""):
    """测试多个分类筛选"""
    category_str = ','.join(categories)
    return test_category_filter(category_str, description or f"多个分类: {category_str}")

def main():
    print("="*60)
    print("产品分类筛选功能测试")
    print("="*60)
    print("\n注意: 请确保:")
    print("1. 服务器正在运行 (http://localhost:8085)")
    print("2. 已在浏览器中登录")
    print("3. 数据库中有相应的产品分类数据")
    
    # 测试用例 - 根据实际数据库中的分类名称调整
    test_cases = [
        # 单个分类测试
        ("洗衣机", "测试单个分类: 洗衣机"),
        ("冰箱", "测试单个分类: 冰箱"),
        ("空调", "测试单个分类: 空调"),
        
        # 多个分类测试
        (["洗衣机", "冰箱"], "测试多个分类: 洗衣机,冰箱"),
    ]
    
    results = []
    for test_case in test_cases:
        if isinstance(test_case[0], list):
            result = test_multiple_categories(test_case[0], test_case[1])
        else:
            result = test_category_filter(test_case[0], test_case[1])
        results.append((test_case[1], result))
    
    # 总结
    print(f"\n{'='*60}")
    print("测试总结")
    print(f"{'='*60}")
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for desc, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{status}: {desc}")
    
    print(f"\n总计: {passed}/{total} 通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！产品分类筛选功能正常工作。")
    else:
        print("\n⚠️  部分测试失败，请检查:")
        print("   1. 数据库中是否有对应分类的数据")
        print("   2. 分类名称是否正确")
        print("   3. 服务器日志中是否有错误信息")

if __name__ == "__main__":
    main()
