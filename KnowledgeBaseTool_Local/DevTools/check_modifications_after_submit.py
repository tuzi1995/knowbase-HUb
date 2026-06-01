#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查机型矩阵提交后的修改记录
"""

import psycopg2
from datetime import datetime, timedelta

DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'knowledgebase_local',
    'user': 'postgres',
    'password': '11111111'
}

def check_modifications():
    """检查修改记录"""
    print("=" * 70)
    print("检查修改记录")
    print("=" * 70)
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        print("✅ 成功连接数据库")
        
        cur = conn.cursor()
        
        # 1. 检查表是否存在
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'knowledge_base_modifications'
            );
        """)
        exists = cur.fetchone()[0]
        
        if not exists:
            print("❌ knowledge_base_modifications 表不存在")
            return False
        
        print("✅ knowledge_base_modifications 表存在")
        
        # 2. 统计总记录数
        cur.execute("SELECT COUNT(*) FROM knowledge_base_modifications;")
        total = cur.fetchone()[0]
        print(f"\n总记录数: {total}")
        
        # 3. 查询最近的记录
        print("\n最近10条记录:")
        cur.execute("""
            SELECT 
                id,
                kb_id,
                modifier,
                modification_time,
                change_type,
                source
            FROM knowledge_base_modifications
            ORDER BY modification_time DESC
            LIMIT 10;
        """)
        
        recent = cur.fetchall()
        if recent:
            for row in recent:
                id_val, kb_id, modifier, mod_time, change_type, source = row
                print(f"  ID={id_val}: {kb_id} | {modifier} | {mod_time} | {change_type} | {source}")
        else:
            print("  (无记录)")
        
        # 4. 查询机型矩阵相关的记录
        print("\n机型矩阵管理的记录:")
        cur.execute("""
            SELECT 
                id,
                kb_id,
                modifier,
                modification_time,
                change_type
            FROM knowledge_base_modifications
            WHERE source = '机型矩阵管理'
            ORDER BY modification_time DESC
            LIMIT 10;
        """)
        
        matrix_records = cur.fetchall()
        if matrix_records:
            print(f"  找到 {len(matrix_records)} 条记录:")
            for row in matrix_records:
                id_val, kb_id, modifier, mod_time, change_type = row
                print(f"  ID={id_val}: {kb_id} | {modifier} | {mod_time} | {change_type}")
        else:
            print("  ❌ 没有找到机型矩阵管理的记录")
            print("\n  可能的原因:")
            print("  1. 修改记录插入失败")
            print("  2. source 字段的值不是'机型矩阵管理'")
            print("  3. 代码中没有插入修改记录")
        
        # 5. 查询最近1小时的记录
        print("\n最近1小时的记录:")
        one_hour_ago = datetime.now() - timedelta(hours=1)
        cur.execute("""
            SELECT 
                id,
                kb_id,
                source,
                modification_time
            FROM knowledge_base_modifications
            WHERE modification_time > %s
            ORDER BY modification_time DESC;
        """, (one_hour_ago,))
        
        recent_hour = cur.fetchall()
        if recent_hour:
            print(f"  找到 {len(recent_hour)} 条记录:")
            for row in recent_hour:
                id_val, kb_id, source, mod_time = row
                print(f"  ID={id_val}: {kb_id} | {source} | {mod_time}")
        else:
            print("  ❌ 最近1小时没有新记录")
            print("  这说明修改记录没有被插入")
        
        cur.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("\n🔍 检查修改记录\n")
    check_modifications()
