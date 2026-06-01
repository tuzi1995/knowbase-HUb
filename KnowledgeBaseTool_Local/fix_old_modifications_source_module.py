#!/usr/bin/env python3
"""
修复旧的修改记录，从 change_meta 中提取 source 并设置到 source_module 字段
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server import get_supabase_client, _parse_change_meta

def fix_old_modifications():
    """修复旧的修改记录"""
    print("=" * 70)
    print("修复旧修改记录的 source_module 字段")
    print("=" * 70)
    
    try:
        client = get_supabase_client()
        if not client:
            print("❌ 无法连接到数据库")
            return False
        
        print("✅ 数据库连接成功\n")
        
        # 查询所有 source_module 为空的记录
        print("查询 source_module 为空的记录...")
        rows = client.select_all(
            'knowledge_base_modifications',
            filters={'source_module': 'is.null'},
            order_by='modification_time',
            order_dir='desc',
            page_size=1000
        )
        
        if not rows:
            print("✅ 没有需要修复的记录")
            return True
        
        print(f"找到 {len(rows)} 条需要修复的记录\n")
        
        # 统计
        fixed_count = 0
        skipped_count = 0
        error_count = 0
        
        for i, row in enumerate(rows, 1):
            kb_id = row.get('kb_id') or row.get('question_wiki_id') or '(无ID)'
            record_id = row.get('id')
            
            if not record_id:
                print(f"  {i}. {kb_id} - ❌ 跳过（无ID）")
                skipped_count += 1
                continue
            
            # 从 change_meta 中提取 source
            change_meta = row.get('change_meta')
            if not change_meta:
                print(f"  {i}. {kb_id} - ⚠️  跳过（无 change_meta）")
                skipped_count += 1
                continue
            
            # 解析 change_meta
            meta = _parse_change_meta(change_meta)
            source = meta.get('source') if isinstance(meta, dict) else None
            
            if not source:
                # 尝试根据其他信息推断来源
                # 如果有 operation_id，可能是机型矩阵
                # 否则默认为知识库管理
                source = '知识库管理'
                print(f"  {i}. {kb_id} - ⚠️  change_meta 中无 source，默认设置为: {source}")
            else:
                print(f"  {i}. {kb_id} - ✅ 从 change_meta 提取 source: {source}")
            
            # 更新记录
            try:
                resp = client.update(
                    'knowledge_base_modifications',
                    {'source_module': source},
                    {'id': record_id}
                )
                
                if resp.status_code in (200, 201):
                    fixed_count += 1
                else:
                    print(f"       ❌ 更新失败: {resp.text}")
                    error_count += 1
            except Exception as e:
                print(f"       ❌ 更新异常: {e}")
                error_count += 1
        
        print("\n" + "=" * 70)
        print("修复完成")
        print("=" * 70)
        print(f"总记录数: {len(rows)}")
        print(f"成功修复: {fixed_count}")
        print(f"跳过: {skipped_count}")
        print(f"失败: {error_count}")
        
        if fixed_count > 0:
            print("\n✅ 修复成功！现在所有修改记录都有 source_module 字段了")
            print("\n建议：")
            print("1. 重启服务")
            print("2. 刷新修改记录页面")
            print("3. 确认可以看到所有来源的记录")
        
        return error_count == 0
        
    except Exception as e:
        print(f"\n❌ 修复失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = fix_old_modifications()
    sys.exit(0 if success else 1)
