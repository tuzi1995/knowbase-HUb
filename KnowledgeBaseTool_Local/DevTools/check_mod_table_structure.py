#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查 knowledge_base_modifications 表结构
"""

import psycopg2

DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'knowledgebase_local',
    'user': 'postgres',
    'password': '11111111'
}

def check_table_structure():
    """检查表结构"""
    print("=" * 70)
    print("检查 knowledge_base_modifications 表结构")
    print("=" * 70)
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        print("✅ 成功连接数据库")
        
        cur = conn.cursor()
        
        # 查询表结构
        cur.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'knowledge_base_modifications'
            ORDER BY ordinal_position;
        """)
        
        columns = cur.fetchall()
        
        print(f"\n表字段（共 {len(columns)} 个）:")
        for col_name, data_type, nullable in columns:
            print(f"  {col_name}: {data_type} {'NULL' if nullable == 'YES' else 'NOT NULL'}")
        
        # 检查是否有 source 字段
        col_names = [col[0] for col in columns]
        
        print("\n字段检查:")
        required_fields = ['source', 'change_meta', 'kb_id', 'modifier', 'modification_time', 'change_type']
        
        for field in required_fields:
            if field in col_names:
                print(f"  ✅ {field}")
            else:
                print(f"  ❌ {field} (缺失)")
        
        # 查询现有记录
        print("\n现有记录:")
        cur.execute("SELECT COUNT(*) FROM knowledge_base_modifications;")
        count = cur.fetchone()[0]
        print(f"  总数: {count}")
        
        if count > 0:
            # 查询第一条记录的所有字段
            cur.execute("SELECT * FROM knowledge_base_modifications LIMIT 1;")
            record = cur.fetchone()
            
            print("\n  第一条记录的字段值:")
            for i, col_name in enumerate(col_names):
                value = record[i] if i < len(record) else None
                value_str = str(value)[:50] if value else '(NULL)'
                print(f"    {col_name}: {value_str}")
        
        cur.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("\n🔍 检查表结构\n")
    check_table_structure()
