#!/usr/bin/env python3
"""
测试脚本：验证修改记录功能是否正常工作
"""
import sys
import os

# 添加当前目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入必要的模块
import json
from datetime import datetime

# 从 server.py 导入函数
from server import get_supabase_client

def test_modification_record():
    """测试修改记录的插入和查询"""
    
    print("=" * 60)
    print("修改记录功能测试")
    print("=" * 60)
    
    # 1. 获取数据库客户端
    print("\n1. 连接数据库...")
    client = get_supabase_client()
    if not client:
        print("❌ 数据库连接失败")
        return False
    print("✅ 数据库连接成功")
    
    # 2. 检查表是否存在
    print("\n2. 检查 knowledge_base_modifications 表...")
    try:
        resp = client.select(
            'knowledge_base_modifications',
            page=1,
            page_size=1
        )
        if resp.status_code in (200, 206):
            print("✅ 表存在且可访问")
        else:
            print(f"❌ 表访问失败: HTTP {resp.status_code}")
            return False
    except Exception as e:
        print(f"❌ 表检查失败: {e}")
        return False
    
    # 3. 查询最近的修改记录
    print("\n3. 查询最近的修改记录...")
    try:
        resp = client.select(
            'knowledge_base_modifications',
            page=1,
            page_size=5,
            order_by='modification_time.desc'
        )
        
        if resp.status_code in (200, 206):
            records = resp.json() or []
            print(f"✅ 查询成功，共 {len(records)} 条记录")
            
            if records:
                print("\n最近的修改记录：")
                for i, record in enumerate(records, 1):
                    print(f"\n  记录 {i}:")
                    print(f"    - ID: {record.get('kb_id')}")
                    print(f"    - 问题: {record.get('question', '')[:50]}...")
                    print(f"    - 修改人: {record.get('modifier')}")
                    print(f"    - 修改时间: {record.get('modification_time')}")
                    print(f"    - 来源: {record.get('source_module')}")
                    print(f"    - 操作: {record.get('change_type')}")
            else:
                print("⚠️  没有找到任何修改记录")
        else:
            print(f"❌ 查询失败: HTTP {resp.status_code}")
            return False
    except Exception as e:
        print(f"❌ 查询失败: {e}")
        return False
    
    # 4. 测试插入一条测试记录
    print("\n4. 测试插入修改记录...")
    test_record = {
        'kb_id': 'TEST_' + datetime.now().strftime('%Y%m%d%H%M%S'),
        'question': '测试问题 - 验证修改记录功能',
        'answer': '测试答案',
        'product_name': 'IC-F3003',
        'modifier': 'test_user',
        'modification_time': datetime.utcnow().isoformat(),
        'change_type': 'test',
        'source_module': '测试脚本',
        'operation_id': 'TEST_OP_' + datetime.now().strftime('%Y%m%d%H%M%S')
    }
    
    try:
        resp = client.insert('knowledge_base_modifications', test_record)
        if resp.status_code in (200, 201):
            print("✅ 测试记录插入成功")
            
            # 验证插入
            print("\n5. 验证测试记录...")
            resp = client.select(
                'knowledge_base_modifications',
                page=1,
                page_size=1,
                filters={'kb_id': f"eq.{test_record['kb_id']}"}
            )
            
            if resp.status_code in (200, 206):
                records = resp.json() or []
                if records:
                    print("✅ 测试记录验证成功")
                    print(f"   插入的记录: {records[0].get('kb_id')}")
                    
                    # 清理测试记录
                    print("\n6. 清理测试记录...")
                    try:
                        client.delete('knowledge_base_modifications', {'kb_id': test_record['kb_id']})
                        print("✅ 测试记录已清理")
                    except:
                        print("⚠️  测试记录清理失败（不影响功能）")
                else:
                    print("❌ 测试记录验证失败：未找到插入的记录")
                    return False
            else:
                print(f"❌ 验证失败: HTTP {resp.status_code}")
                return False
        else:
            print(f"❌ 插入失败: HTTP {resp.status_code}")
            print(f"   响应: {resp.text}")
            return False
    except Exception as e:
        print(f"❌ 插入失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n" + "=" * 60)
    print("✅ 所有测试通过！修改记录功能正常工作")
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = test_modification_record()
    sys.exit(0 if success else 1)
