#!/usr/bin/env python3
"""
检查所有修改记录，按来源模块分组统计
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server import get_supabase_client

def check_modifications():
    """检查所有修改记录"""
    print("=" * 70)
    print("检查所有修改记录")
    print("=" * 70)
    
    try:
        client = get_supabase_client()
        if not client:
            print("❌ 无法连接到数据库")
            return False
        
        print("✅ 数据库连接成功\n")
        
        # 查询所有修改记录
        print("查询所有修改记录...")
        rows = client.select_all(
            'knowledge_base_modifications',
            order_by='modification_time',
            order_dir='desc',
            page_size=1000
        )
        
        if not rows:
            print("⚠️  没有找到任何修改记录")
            return True
        
        print(f"✅ 找到 {len(rows)} 条修改记录\n")
        
        # 按 source_module 分组统计
        source_stats = {}
        for row in rows:
            source = row.get('source_module') or '(空)'
            if source not in source_stats:
                source_stats[source] = []
            source_stats[source].append(row)
        
        print("按来源模块分组统计:")
        print("-" * 70)
        for source in sorted(source_stats.keys()):
            records = source_stats[source]
            print(f"\n{source}: {len(records)} 条记录")
            
            # 显示最近的3条记录
            print("  最近的记录:")
            for i, record in enumerate(records[:3], 1):
                kb_id = record.get('kb_id') or record.get('question_wiki_id') or '(无ID)'
                modifier = record.get('modifier') or '(无修改人)'
                change_type = record.get('change_type') or '(无类型)'
                mod_time = record.get('modification_time') or '(无时间)'
                
                print(f"    {i}. {kb_id} | {modifier} | {change_type} | {mod_time}")
        
        print("\n" + "=" * 70)
        print("总结")
        print("=" * 70)
        print(f"总记录数: {len(rows)}")
        print(f"来源模块数: {len(source_stats)}")
        print("\n各来源模块记录数:")
        for source in sorted(source_stats.keys(), key=lambda x: len(source_stats[x]), reverse=True):
            print(f"  {source}: {len(source_stats[source])} 条")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    check_modifications()
