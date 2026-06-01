#!/usr/bin/env python3
"""
测试机型矩阵提交后修改记录是否正常显示
"""
import sys
import os
import json
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import (
    get_supabase_client, 
    _attach_change_meta, 
    _supabase_insert_drop_unknown_columns,
    _snapshot_mod_fields,
    _compute_mod_changed_fields
)

def test_matrix_modification_insert():
    """测试机型矩阵修改记录插入"""
    print("=" * 70)
    print("测试机型矩阵修改记录插入")
    print("=" * 70)
    
    try:
        client = get_supabase_client()
        if not client:
            print("❌ 无法连接到数据库")
            return False
        
        print("✅ 数据库连接成功")
        
        # 模拟机型矩阵提交的修改记录
        operation_id = f"TEST_MATRIX_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        kb_id = f"TEST_KB_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # 模拟修改前后的数据
        before_obj = {
            'question': '测试问题',
            'answer': '测试答案',
            'products': 'A,B'
        }
        
        after_obj = {
            'question': '测试问题',
            'answer': '测试答案',
            'products': 'A,B,C'
        }
        
        changed_fields = _compute_mod_changed_fields(before_obj, after_obj)
        
        # 创建修改记录
        rec = {
            'kb_id': kb_id,
            'modifier': '测试用户',
            'modification_time': datetime.utcnow().isoformat(),
            'change_type': 'edit',
            'question': '测试问题',
            'answer': '测试答案',
            'product_name': 'A,B,C'
        }
        
        # 调用 _attach_change_meta（模拟机型矩阵提交的代码）
        _attach_change_meta(rec, {
            'source': '机型矩阵管理',
            'operation_id': operation_id,
            'edit_source': '全量修改',
            'changed_products': ['C'],
            'before': before_obj,
            'after': after_obj,
            'changed_fields': changed_fields
        })
        
        print("\n准备插入的记录:")
        print(json.dumps(rec, indent=2, ensure_ascii=False))
        
        # 检查必要字段
        print("\n检查必要字段:")
        required_fields = ['kb_id', 'modifier', 'modification_time', 'change_type', 'source_module', 'change_meta']
        all_present = True
        for field in required_fields:
            if field in rec:
                print(f"  ✅ {field}: {rec[field][:50] if isinstance(rec[field], str) and len(rec[field]) > 50 else rec[field]}")
            else:
                print(f"  ❌ 缺少字段: {field}")
                all_present = False
        
        if not all_present:
            print("\n❌ 缺少必要字段，无法插入")
            return False
        
        # 插入数据库
        print("\n执行插入...")
        resp = _supabase_insert_drop_unknown_columns(client, 'knowledge_base_modifications', [rec])
        
        if resp is None:
            print("❌ 插入失败：返回 None")
            return False
        
        status_code = getattr(resp, 'status_code', None)
        print(f"\n插入响应状态码: {status_code}")
        
        if status_code not in (200, 201):
            print(f"❌ 插入失败")
            print(f"响应文本: {getattr(resp, 'text', '')}")
            return False
        
        print("✅ 插入成功")
        
        # 验证插入
        print("\n验证插入...")
        rows = client.select_all(
            'knowledge_base_modifications',
            filters={'kb_id': f"eq.{kb_id}"},
            page_size=1
        )
        
        if not rows:
            print("❌ 未找到插入的记录")
            return False
        
        print(f"✅ 找到 {len(rows)} 条记录")
        
        record = rows[0]
        print("\n插入的记录:")
        print(f"  kb_id: {record.get('kb_id')}")
        print(f"  modifier: {record.get('modifier')}")
        print(f"  source_module: {record.get('source_module')}")
        print(f"  change_type: {record.get('change_type')}")
        print(f"  modification_time: {record.get('modification_time')}")
        
        # 检查 source_module
        if record.get('source_module') == '机型矩阵管理':
            print("\n✅ source_module 字段正确")
        else:
            print(f"\n❌ source_module 字段错误: {record.get('source_module')}")
            return False
        
        # 检查 change_meta
        change_meta = record.get('change_meta')
        if change_meta:
            print("\n✅ change_meta 字段存在")
            if isinstance(change_meta, str):
                try:
                    parsed = json.loads(change_meta)
                    print("✅ change_meta 可以解析为 JSON")
                    print(f"   source: {parsed.get('source')}")
                    print(f"   operation_id: {parsed.get('operation_id')}")
                except:
                    print("❌ change_meta 无法解析为 JSON")
            elif isinstance(change_meta, dict):
                print("✅ change_meta 是 dict 类型（PostgreSQL jsonb）")
                print(f"   source: {change_meta.get('source')}")
                print(f"   operation_id: {change_meta.get('operation_id')}")
        else:
            print("\n❌ change_meta 字段为空")
        
        # 清理测试数据
        print("\n清理测试数据...")
        client.delete('knowledge_base_modifications', {'kb_id': kb_id})
        print("✅ 清理完成")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_query_matrix_modifications():
    """测试查询机型矩阵的修改记录"""
    print("\n" + "=" * 70)
    print("测试查询机型矩阵修改记录")
    print("=" * 70)
    
    try:
        client = get_supabase_client()
        if not client:
            print("❌ 无法连接到数据库")
            return False
        
        # 查询最近的机型矩阵修改记录
        print("\n查询 source_module = '机型矩阵管理' 的记录...")
        rows = client.select_all(
            'knowledge_base_modifications',
            filters={'source_module': 'eq.机型矩阵管理'},
            order_by='modification_time',
            order_dir='desc',
            page_size=5
        )
        
        if not rows:
            print("⚠️  未找到机型矩阵的修改记录")
            print("   这可能是因为：")
            print("   1. 还没有提交过机型矩阵修改")
            print("   2. 之前的记录没有正确设置 source_module 字段")
            return True  # 不算失败
        
        print(f"\n✅ 找到 {len(rows)} 条记录")
        
        for i, record in enumerate(rows, 1):
            print(f"\n记录 {i}:")
            print(f"  kb_id: {record.get('kb_id')}")
            print(f"  modifier: {record.get('modifier')}")
            print(f"  source_module: {record.get('source_module')}")
            print(f"  change_type: {record.get('change_type')}")
            print(f"  modification_time: {record.get('modification_time')}")
            
            change_meta = record.get('change_meta')
            if change_meta:
                if isinstance(change_meta, dict):
                    print(f"  operation_id: {change_meta.get('operation_id')}")
                elif isinstance(change_meta, str):
                    try:
                        parsed = json.loads(change_meta)
                        print(f"  operation_id: {parsed.get('operation_id')}")
                    except:
                        pass
        
        return True
        
    except Exception as e:
        print(f"\n❌ 查询失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    print("\n🔍 测试机型矩阵修改记录\n")
    
    # 测试1：插入修改记录
    result1 = test_matrix_modification_insert()
    
    # 测试2：查询修改记录
    result2 = test_query_matrix_modifications()
    
    print("\n" + "=" * 70)
    print("测试结果汇总")
    print("=" * 70)
    
    print(f"插入修改记录: {'✅ 通过' if result1 else '❌ 失败'}")
    print(f"查询修改记录: {'✅ 通过' if result2 else '❌ 失败'}")
    
    if result1 and result2:
        print("\n✅ 所有测试通过！")
        print("\n现在可以：")
        print("1. 重启服务：python3 server.py")
        print("2. 在机型矩阵管理中提交修改")
        print("3. 在修改记录中查看提交的记录")
        sys.exit(0)
    else:
        print("\n⚠️  部分测试失败")
        sys.exit(1)
