#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试修改记录插入
模拟实际的插入过程，找出失败原因
"""

import sys
import os
from datetime import datetime
import json

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import get_supabase_client, _supabase_insert_drop_unknown_columns

def test_simple_insert():
    """测试简单插入"""
    print("=" * 70)
    print("测试1：简单插入")
    print("=" * 70)
    
    try:
        client = get_supabase_client()
        if not client:
            print("❌ 无法获取数据库客户端")
            return False
        
        print("✅ 成功连接数据库")
        
        # 创建测试数据
        test_data = {
            'kb_id': 'TEST_' + datetime.now().strftime('%Y%m%d%H%M%S'),
            'question_wiki_id': 'TEST_' + datetime.now().strftime('%Y%m%d%H%M%S'),
            'modifier': 'test_user',
            'modification_time': datetime.now().isoformat(),
            'change_type': 'edit',
            'source': '测试插入',
            'question': '测试问题',
            'answer': '测试答案'
        }
        
        print(f"\n测试数据:")
        print(f"  kb_id: {test_data['kb_id']}")
        print(f"  modifier: {test_data['modifier']}")
        print(f"  change_type: {test_data['change_type']}")
        
        # 尝试插入
        print("\n执行插入...")
        resp = _supabase_insert_drop_unknown_columns(client, 'knowledge_base_modifications', test_data)
        
        print(f"\n插入响应:")
        print(f"  类型: {type(resp)}")
        
        if resp is None:
            print("  ❌ 返回 None")
            return False
        
        if hasattr(resp, 'status_code'):
            print(f"  状态码: {resp.status_code}")
            
            if resp.status_code >= 400:
                print(f"  ❌ 插入失败")
                print(f"  错误信息: {resp.text[:500]}")
                return False
            else:
                print(f"  ✅ 插入成功")
                
                # 验证插入
                print("\n验证插入...")
                rows = client.select_all(
                    'knowledge_base_modifications',
                    filters={'kb_id': f"eq.{test_data['kb_id']}"},
                    page_size=1
                )
                
                if rows and len(rows) > 0:
                    print(f"  ✅ 验证成功，找到记录")
                    
                    # 清理测试数据
                    print("\n清理测试数据...")
                    client.delete('knowledge_base_modifications', {'kb_id': test_data['kb_id']})
                    print("  ✅ 清理完成")
                    
                    return True
                else:
                    print(f"  ❌ 验证失败，找不到记录")
                    print("  这很奇怪：插入返回成功，但查询不到数据")
                    return False
        else:
            print(f"  ⚠️  响应对象没有 status_code 属性")
            print(f"  响应内容: {resp}")
            return False
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_full_record_insert():
    """测试完整记录插入（模拟实际保存）"""
    print("\n" + "=" * 70)
    print("测试2：完整记录插入（模拟实际保存）")
    print("=" * 70)
    
    try:
        client = get_supabase_client()
        if not client:
            print("❌ 无法获取数据库客户端")
            return False
        
        # 创建完整的测试数据（模拟实际保存时的数据结构）
        test_data = {
            'kb_id': 'TEST_FULL_' + datetime.now().strftime('%Y%m%d%H%M%S'),
            'question_wiki_id': 'TEST_FULL_' + datetime.now().strftime('%Y%m%d%H%M%S'),
            'modifier': 'test_user',
            'modification_time': datetime.now().isoformat(),
            'change_type': 'edit',
            'source': '知识库管理',
            'question': '这是一个测试问题',
            'answer': '这是一个测试答案',
            'question_type': 'text',
            'answer_type': 'text',
            'if_bm25': True,
            'similar_questions': json.dumps(['相似问题1', '相似问题2'], ensure_ascii=False),
            'error_list': json.dumps(['错误1'], ensure_ascii=False),
            'keyword_list': json.dumps(['关键词1', '关键词2'], ensure_ascii=False),
            'image_urls': json.dumps([], ensure_ascii=False),
            'video_urls': json.dumps([], ensure_ascii=False),
            'file_urls': json.dumps([], ensure_ascii=False),
            'link_type': 'none',
            'link_url': '',
            'product_name': '测试产品',
            'product_category_name': '测试分类',
            'update_time': datetime.now().isoformat(),
            'change_meta': json.dumps({
                'source': '知识库管理',
                'before': {'question': '旧问题', 'answer': '旧答案'},
                'after': {'question': '新问题', 'answer': '新答案'},
                'changed_fields': ['question', 'answer']
            }, ensure_ascii=False)
        }
        
        print(f"\n测试数据（完整记录）:")
        print(f"  kb_id: {test_data['kb_id']}")
        print(f"  字段数量: {len(test_data)}")
        
        # 尝试插入
        print("\n执行插入...")
        resp = _supabase_insert_drop_unknown_columns(client, 'knowledge_base_modifications', test_data)
        
        if resp is None:
            print("  ❌ 返回 None")
            return False
        
        if hasattr(resp, 'status_code'):
            print(f"  状态码: {resp.status_code}")
            
            if resp.status_code >= 400:
                print(f"  ❌ 插入失败")
                print(f"  错误信息: {resp.text}")
                
                # 分析错误
                error_text = resp.text
                if 'column' in error_text.lower() and 'does not exist' in error_text.lower():
                    print("\n  分析：字段不存在错误")
                    print("  _supabase_insert_drop_unknown_columns 应该会自动删除不存在的字段")
                    print("  但可能删除了太多字段或者遇到了其他问题")
                elif 'null value' in error_text.lower():
                    print("\n  分析：必填字段为空")
                    print("  需要检查哪些字段是必填的")
                
                return False
            else:
                print(f"  ✅ 插入成功")
                
                # 验证
                rows = client.select_all(
                    'knowledge_base_modifications',
                    filters={'kb_id': f"eq.{test_data['kb_id']}"},
                    page_size=1
                )
                
                if rows and len(rows) > 0:
                    print(f"  ✅ 验证成功")
                    
                    # 清理
                    client.delete('knowledge_base_modifications', {'kb_id': test_data['kb_id']})
                    print("  ✅ 清理完成")
                    
                    return True
                else:
                    print(f"  ❌ 验证失败")
                    return False
        else:
            print(f"  ⚠️  响应对象没有 status_code 属性")
            return False
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_table_columns():
    """检查表的实际字段"""
    print("\n" + "=" * 70)
    print("测试3：检查表字段")
    print("=" * 70)
    
    try:
        client = get_supabase_client()
        if not client:
            print("❌ 无法获取数据库客户端")
            return False
        
        # 尝试插入一个空记录来触发字段错误
        print("\n尝试插入空记录以获取字段信息...")
        
        test_data = {
            'kb_id': 'TEMP_TEST',
            'modifier': 'test',
            'modification_time': datetime.now().isoformat(),
            'change_type': 'test'
        }
        
        resp = client.insert('knowledge_base_modifications', test_data)
        
        if hasattr(resp, 'status_code'):
            print(f"状态码: {resp.status_code}")
            
            if resp.status_code >= 400:
                error_text = resp.text
                print(f"\n错误信息:")
                print(error_text)
                
                # 分析错误找出必填字段
                if 'null value' in error_text.lower():
                    print("\n发现必填字段约束")
            else:
                print("✅ 插入成功（意外）")
                # 清理
                client.delete('knowledge_base_modifications', {'kb_id': 'TEMP_TEST'})
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("\n🔍 测试修改记录插入\n")
    
    # 测试1：简单插入
    result1 = test_simple_insert()
    
    # 测试2：完整记录插入
    result2 = test_full_record_insert()
    
    # 测试3：检查表字段
    result3 = check_table_columns()
    
    # 总结
    print("\n" + "=" * 70)
    print("测试总结")
    print("=" * 70)
    
    print(f"简单插入: {'✅ 通过' if result1 else '❌ 失败'}")
    print(f"完整记录插入: {'✅ 通过' if result2 else '❌ 失败'}")
    print(f"表字段检查: {'✅ 通过' if result3 else '❌ 失败'}")
    
    if result1 and result2:
        print("\n✅ 所有测试通过！")
        print("插入功能正常，问题可能在实际保存时的数据准备")
    elif result1:
        print("\n⚠️  简单插入成功，但完整记录插入失败")
        print("问题可能在某些字段的数据格式或必填字段")
    else:
        print("\n❌ 插入功能有问题")
        print("需要检查表结构和权限")

if __name__ == "__main__":
    main()
