#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查 kb_recall 表结构
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def check_schema():
    """检查表结构"""
    
    print("="*60)
    print("检查 kb_recall 表结构")
    print("="*60)
    
    # 读取配置
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'supabase_config_local.json')
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    try:
        import psycopg2
        
        db_config = config.get('local_db', {})
        conn = psycopg2.connect(
            host=db_config.get('host', 'localhost'),
            port=db_config.get('port', 5432),
            database=db_config.get('database', 'knowledgebase_local'),
            user=db_config.get('user', 'postgres'),
            password=db_config.get('password', '')
        )
        
        cur = conn.cursor()
        
        # 查询表结构
        cur.execute("""
            SELECT column_name, data_type, character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = 'public' 
            AND table_name = 'kb_recall'
            ORDER BY ordinal_position;
        """)
        
        columns = cur.fetchall()
        
        print("\n表字段:")
        print("-" * 60)
        for col_name, data_type, max_length in columns:
            length_info = f"({max_length})" if max_length else ""
            print(f"  {col_name:30} {data_type}{length_info}")
        
        # 查看示例数据
        print("\n" + "="*60)
        print("示例数据（前 3 条）:")
        print("="*60)
        
        cur.execute("SELECT * FROM kb_recall ORDER BY month DESC LIMIT 3;")
        rows = cur.fetchall()
        
        # 获取列名
        col_names = [desc[0] for desc in cur.description]
        
        for i, row in enumerate(rows, 1):
            print(f"\n记录 {i}:")
            for col_name, value in zip(col_names, row):
                if isinstance(value, str) and len(value) > 100:
                    value = value[:100] + "..."
                print(f"  {col_name}: {value}")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    check_schema()
