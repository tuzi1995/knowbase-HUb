#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 change_meta 修复
验证 dict 类型是否正确转换为 JSON 字符串
"""

import sys
import os
from datetime import datetime
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import get_supabase_client, _attach_change_meta, _supabase_insert_drop_unknown_columns

def test_attach_change_meta():
    """测试 _attach_change_meta 函数"""
    print("=" * 70)
    print("测试 _attach_change_meta 函数")
    print("=" * 70)
    
    # 创建测试记录
    record = {
        'kb_id': 'TEST_123',
        'question': '测试问题',
        'answer': '测试答案'
    }
    
    # 添加 change_meta
    meta = {
        'source': '知识库管理',
        'before': {'question': '旧问题', 'answer': '旧答案'},
        'after': {'question': '新问题', 'answer': '新答案'},
        'changed_fields': ['question', 'answer']
    }
    
    print("\n原始记录:")
    print(f"  kb_id: {record['kb_id']}")
    print(f"  change_meta: {record.get('change_meta', '(无)')}")
    
    print("\n添加 meta 数据:")
    print(f"  source: {meta['source']}")
    print(f"  before: {meta['before']}")
    print(f"  after: {meta['after']}")
    
    # 调用函数
    result = _attach_change_meta(record, meta)
    
    print("\n处理后的记录:")
    print(f"  kb_id: {result['kb_id']}")
    print(f"  change_meta 类型: {type(result.get('change_meta'))}")
    print(f"  change_meta 值: {result.get('change_meta')}")
    
    # 验证类型
    change_meta = result.get('change_meta')
    if isinstance(change_meta, str):
        print("\n✅ change_meta 是字符串类型（正确）")
        
        # 尝试解析
        try:
            parsed = json.loads(change_meta)
            print(f"✅ 可以解析为 JSON")
            print(f"  解析后的类型: {type(parsed)}")
            print(f"  包含的键: {list(parsed.keys())}")
            return True
        except Exception as e:
            print(f"❌ 无法解析为 JSON: {e}")
            return False
    elif isinstance(change_meta, dict):
        print("\n❌ change_meta 是 dict 类型（错误！会导致 'can't adapt type dict' 错误）")
        return False
    else:
        print(f"\n⚠️  change_meta 是其他类型: {type(change_meta)}")
        return False

def test_full_insert():
    """测试完整的插入流程"""
    print("\n" + "=" * 70)
    print("测试完整插入流程")
    print("=" * 70)
    
    try:
        client = get_supabase_client()
        if not client:
            print("❌ 无法获取数据库客户端")
            return False
        
        print("✅ 成功连接数据库")
        
        # 创建完整的测试数据
        test_data = {
            'kb_id': 'TEST_META_' + datetime.now().strftime('%Y%m%d%H%M%S'),
            'question_wiki_id': 'TEST_META_' + datetime.now().strftime('%Y%m%d%H%M%S'),
            'modifier': 'test_user',
            'modification_time': datetime.now().isoformat(),
            'change_type': 'edit',
            'question': '测试问题',
            'answer': '测试答案',
            'similar_questions': json.dumps(['相似1', '相似2'], ensure_ascii=False),
            'error_list': json.dumps([], ensure_ascii=False),
            'keyword_list': json.dumps(['关键词1'], ensure_ascii=False),
            'image_urls': json.dumps([], ensure_ascii=False),
            'video_urls': json.dumps([], ensure_ascii=False),
            'file_urls': json.dumps([], ensure_ascii=False),
        }
        
        # 添加 change_meta
        _attach_change_meta(test_data, {
            'source': '知识库管理',
            'before': {'question': '旧问题', 'answer': '旧答案'},
            'after': {'question': '新问题', 'answer': '新答案'},
            'changed_fields': ['question', 'answer']
        })
        
        print(f"\n测试数据:")
        print(f"  kb_id: {test_data['kb_id']}")
        print(f"  change_meta 类型: {type(test_data.get('change_meta'))}")
        
        # 检查 change_meta 类型
        if isinstance(test_data.get('change_meta'), dict):
            print("  ❌ change_meta 是 dict（会失败）")
        elif isinstance(test_data.get('change_meta'), str):
            print("  ✅ change_meta 是 str（正确）")
        
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
                error_text = resp.text
                print(f"  错误信息: {error_text}")
                
                if "can't adapt type 'dict'" in error_text:
                    print("\n  分析：仍然有 dict 类型的字段！")
                    print("  需要检查是否所有 dict 字段都转换为了 JSON 字符串")
                
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
                    
                    # 检查 change_meta
                    row = rows[0]
                    change_meta = row.get('change_meta')
                    print(f"\n  数据库中的 change_meta:")
                    print(f"    类型: {type(change_meta)}")
                    if isinstance(change_meta, str):
                        print(f"    内容: {change_meta[:100]}...")
                    elif isinstance(change_meta, dict):
                        print(f"    内容: {json.dumps(change_meta, ensure_ascii=False)[:100]}...")
                    
                    # 清理
                    client.delete('knowledge_base_modifications', {'kb_id': test_data['kb_id']})
                    print("\n  ✅ 清理完成")
                    
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

def main():
    print("\n🔍 测试 change_meta 修复\n")
    
    # 测试1：_attach_change_meta 函数
    result1 = test_attach_change_meta()
    
    # 测试2：完整插入流程
    result2 = test_full_insert()
    
    # 总结
    print("\n" + "=" * 70)
    print("测试总结")
    print("=" * 70)
    
    print(f"_attach_change_meta 函数: {'✅ 通过' if result1 else '❌ 失败'}")
    print(f"完整插入流程: {'✅ 通过' if result2 else '❌ 失败'}")
    
    if result1 and result2:
        print("\n✅ 所有测试通过！")
        print("修复生效，change_meta 已正确转换为 JSON 字符串")
        print("\n下一步：")
        print("1. 重启8085服务")
        print("2. 重新测试保存知识库条目")
        print("3. 应该能看到 mod_log_ok: true")
    else:
        print("\n⚠️  部分测试失败")
        if not result1:
            print("_attach_change_meta 函数有问题，需要进一步检查")
        if not result2:
            print("插入流程有问题，可能还有其他 dict 字段")

if __name__ == "__main__":
    main()
