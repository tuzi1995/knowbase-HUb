#!/usr/bin/env python3
"""
测试 source_module 字段修复
验证 _attach_change_meta 函数是否正确设置 source_module 字段
"""
import sys
import os
import json

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import _attach_change_meta

def test_attach_change_meta_with_source_module():
    """测试 _attach_change_meta 是否正确设置 source_module"""
    print("=" * 70)
    print("测试 _attach_change_meta 函数 - source_module 字段")
    print("=" * 70)
    
    # 测试记录
    record = {
        'kb_id': 'TEST_KB_001',
        'modifier': '测试用户',
        'modification_time': '2026-04-22T13:30:00',
        'change_type': 'edit'
    }
    
    # 测试元数据
    meta = {
        'source': '机型矩阵管理',
        'operation_id': 'TEST_OP_001',
        'before': {'products': 'A,B'},
        'after': {'products': 'A,B,C'},
        'changed_fields': ['products']
    }
    
    print("\n原始记录:")
    print(json.dumps(record, indent=2, ensure_ascii=False))
    
    print("\n元数据:")
    print(json.dumps(meta, indent=2, ensure_ascii=False))
    
    # 调用函数
    result = _attach_change_meta(record, meta)
    
    print("\n处理后的记录:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # 验证
    success = True
    
    # 1. 检查 change_meta 字段
    if 'change_meta' not in result:
        print("\n❌ 缺少 change_meta 字段")
        success = False
    else:
        print("\n✅ change_meta 字段存在")
        
        # 检查是否是字符串
        if not isinstance(result['change_meta'], str):
            print(f"❌ change_meta 应该是字符串，实际是 {type(result['change_meta'])}")
            success = False
        else:
            print("✅ change_meta 是字符串类型")
            
            # 尝试解析 JSON
            try:
                parsed = json.loads(result['change_meta'])
                print("✅ change_meta 可以解析为 JSON")
                print(f"   内容: {json.dumps(parsed, indent=2, ensure_ascii=False)}")
                
                # 检查 source 字段
                if 'source' in parsed and parsed['source'] == '机型矩阵管理':
                    print("✅ change_meta 中包含正确的 source 字段")
                else:
                    print("❌ change_meta 中缺少或错误的 source 字段")
                    success = False
            except Exception as e:
                print(f"❌ change_meta 无法解析为 JSON: {e}")
                success = False
    
    # 2. 检查 source_module 字段
    if 'source_module' not in result:
        print("\n❌ 缺少 source_module 字段")
        success = False
    else:
        print("\n✅ source_module 字段存在")
        
        if result['source_module'] == '机型矩阵管理':
            print("✅ source_module 值正确")
        else:
            print(f"❌ source_module 值错误: {result['source_module']}")
            success = False
    
    return success


def test_different_sources():
    """测试不同来源的 source_module 设置"""
    print("\n" + "=" * 70)
    print("测试不同来源的 source_module")
    print("=" * 70)
    
    sources = [
        '知识库管理',
        '机型矩阵管理',
        '智能映射'
    ]
    
    all_success = True
    
    for source in sources:
        print(f"\n测试来源: {source}")
        
        record = {
            'kb_id': f'TEST_{source}',
            'modifier': '测试用户',
            'change_type': 'edit'
        }
        
        meta = {
            'source': source,
            'before': {},
            'after': {}
        }
        
        result = _attach_change_meta(record, meta)
        
        if 'source_module' in result and result['source_module'] == source:
            print(f"  ✅ source_module 正确设置为: {source}")
        else:
            print(f"  ❌ source_module 设置失败")
            all_success = False
    
    return all_success


if __name__ == '__main__':
    print("\n🔍 测试 source_module 字段修复\n")
    
    # 测试1：基本功能
    result1 = test_attach_change_meta_with_source_module()
    
    # 测试2：不同来源
    result2 = test_different_sources()
    
    print("\n" + "=" * 70)
    print("测试结果汇总")
    print("=" * 70)
    
    print(f"基本功能测试: {'✅ 通过' if result1 else '❌ 失败'}")
    print(f"不同来源测试: {'✅ 通过' if result2 else '❌ 失败'}")
    
    if result1 and result2:
        print("\n✅ 所有测试通过！")
        print("\n修复说明：")
        print("- _attach_change_meta 函数现在会同时设置 source_module 字段")
        print("- source_module 的值从 meta['source'] 中提取")
        print("- 这样插入 knowledge_base_modifications 表时就不会缺少字段")
        sys.exit(0)
    else:
        print("\n⚠️  部分测试失败")
        sys.exit(1)
