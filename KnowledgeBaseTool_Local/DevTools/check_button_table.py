#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查 button 表的结构和约束
找出主键冲突的根本原因
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import get_supabase_client

def check_button_table():
    """检查 button 表的结构"""
    print("=" * 70)
    print("检查 button 表结构")
    print("=" * 70)
    
    try:
        client = get_supabase_client()
        if not client:
            print("❌ 无法获取数据库客户端")
            return False
        
        print("✅ 成功连接数据库")
        
        # 检查表结构
        print("\n1. 查询表结构...")
        
        # 使用 PostgreSQL 系统表查询
        sql = """
        SELECT 
            column_name, 
            data_type, 
            is_nullable,
            column_default
        FROM information_schema.columns
        WHERE table_name = 'button'
        ORDER BY ordinal_position;
        """
        
        result = client._execute_query(sql, fetch=True)
        
        if result:
            print(f"\n表字段（共 {len(result)} 个）:")
            for row in result:
                col_name, data_type, nullable, default = row
                print(f"  - {col_name}: {data_type} {'NULL' if nullable == 'YES' else 'NOT NULL'} {f'DEFAULT {default}' if default else ''}")
        
        # 检查主键
        print("\n2. 查询主键约束...")
        sql_pk = """
        SELECT 
            kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        WHERE tc.constraint_type = 'PRIMARY KEY'
            AND tc.table_name = 'button';
        """
        
        pk_result = client._execute_query(sql_pk, fetch=True)
        
        if pk_result:
            pk_cols = [row[0] for row in pk_result]
            print(f"主键字段: {', '.join(pk_cols)}")
        else:
            print("没有找到主键")
        
        # 检查唯一约束
        print("\n3. 查询唯一约束...")
        sql_unique = """
        SELECT 
            tc.constraint_name,
            kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        WHERE tc.constraint_type = 'UNIQUE'
            AND tc.table_name = 'button'
        ORDER BY tc.constraint_name, kcu.ordinal_position;
        """
        
        unique_result = client._execute_query(sql_unique, fetch=True)
        
        if unique_result:
            print("唯一约束:")
            current_constraint = None
            cols = []
            for row in unique_result:
                constraint_name, col_name = row
                if constraint_name != current_constraint:
                    if current_constraint:
                        print(f"  - {current_constraint}: ({', '.join(cols)})")
                    current_constraint = constraint_name
                    cols = [col_name]
                else:
                    cols.append(col_name)
            if current_constraint:
                print(f"  - {current_constraint}: ({', '.join(cols)})")
        else:
            print("没有找到唯一约束")
        
        # 检查现有数据
        print("\n4. 查询现有数据...")
        sql_count = "SELECT COUNT(*) FROM button;"
        count_result = client._execute_query(sql_count, fetch=True)
        
        if count_result:
            count = count_result[0][0]
            print(f"当前记录数: {count}")
            
            if count > 0:
                # 查询最近的几条记录
                sql_recent = """
                SELECT id, operation_id, question_wiki_id, product_name, submitted_by, submitted_at
                FROM button
                ORDER BY id DESC
                LIMIT 5;
                """
                recent_result = client._execute_query(sql_recent, fetch=True)
                
                if recent_result:
                    print("\n最近5条记录:")
                    for row in recent_result:
                        id_val, op_id, wiki_id, prod, user, time = row
                        print(f"  ID={id_val}: op={op_id[:8]}... wiki={wiki_id} prod={prod}")
        
        # 检查 ID 序列
        print("\n5. 检查 ID 序列...")
        sql_seq = """
        SELECT 
            pg_get_serial_sequence('button', 'id') as sequence_name;
        """
        seq_result = client._execute_query(sql_seq, fetch=True)
        
        if seq_result and seq_result[0][0]:
            seq_name = seq_result[0][0]
            print(f"序列名称: {seq_name}")
            
            # 获取序列当前值
            sql_seq_val = f"SELECT last_value FROM {seq_name};"
            seq_val_result = client._execute_query(sql_seq_val, fetch=True)
            
            if seq_val_result:
                last_val = seq_val_result[0][0]
                print(f"序列当前值: {last_val}")
                
                # 获取表中最大ID
                sql_max_id = "SELECT MAX(id) FROM button;"
                max_id_result = client._execute_query(sql_max_id, fetch=True)
                
                if max_id_result and max_id_result[0][0]:
                    max_id = max_id_result[0][0]
                    print(f"表中最大ID: {max_id}")
                    
                    if last_val <= max_id:
                        print(f"\n⚠️  序列值({last_val}) <= 最大ID({max_id})")
                        print("这会导致主键冲突！")
                        print("\n修复方法:")
                        print(f"SELECT setval('{seq_name}', (SELECT MAX(id) FROM button));")
                    else:
                        print(f"\n✅ 序列值正常")
        
        return True
        
    except Exception as e:
        print(f"❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("\n🔍 检查 button 表结构和约束\n")
    
    result = check_button_table()
    
    print("\n" + "=" * 70)
    print("检查总结")
    print("=" * 70)
    
    if result:
        print("✅ 检查完成")
        print("\n如果发现序列值问题，请运行修复SQL")
    else:
        print("❌ 检查失败")

if __name__ == "__main__":
    main()
