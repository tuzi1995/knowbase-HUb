#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单检查 button 表
"""

import sys
import os
import psycopg2

# 数据库配置
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'knowledgebase_local',
    'user': 'postgres',
    'password': 'postgres'
}

def check_button_table():
    """检查 button 表"""
    print("=" * 70)
    print("检查 button 表")
    print("=" * 70)
    
    try:
        # 尝试不同的密码
        passwords = ['postgres', '', 'password', '123456']
        conn = None
        
        for pwd in passwords:
            try:
                config = DB_CONFIG.copy()
                config['password'] = pwd
                conn = psycopg2.connect(**config)
                print(f"✅ 成功连接数据库（密码: {'(空)' if not pwd else '***'}）")
                break
            except:
                continue
        
        if not conn:
            print("❌ 无法连接数据库，请检查密码")
            return False
        
        cur = conn.cursor()
        
        # 1. 检查表是否存在
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'button'
            );
        """)
        exists = cur.fetchone()[0]
        
        if not exists:
            print("❌ button 表不存在")
            return False
        
        print("✅ button 表存在")
        
        # 2. 查询表结构
        print("\n表结构:")
        cur.execute("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'button'
            ORDER BY ordinal_position;
        """)
        
        for row in cur.fetchall():
            col_name, data_type, nullable, default = row
            print(f"  {col_name}: {data_type} {'NULL' if nullable == 'YES' else 'NOT NULL'}")
        
        # 3. 查询主键
        print("\n主键:")
        cur.execute("""
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
            WHERE tc.constraint_type = 'PRIMARY KEY'
                AND tc.table_name = 'button';
        """)
        
        pk_cols = [row[0] for row in cur.fetchall()]
        if pk_cols:
            print(f"  {', '.join(pk_cols)}")
        else:
            print("  (无)")
        
        # 4. 查询唯一约束
        print("\n唯一约束:")
        cur.execute("""
            SELECT tc.constraint_name, string_agg(kcu.column_name, ', ' ORDER BY kcu.ordinal_position)
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
            WHERE tc.constraint_type = 'UNIQUE'
                AND tc.table_name = 'button'
            GROUP BY tc.constraint_name;
        """)
        
        for row in cur.fetchall():
            constraint_name, cols = row
            print(f"  {constraint_name}: ({cols})")
        
        # 5. 统计数据
        print("\n数据统计:")
        cur.execute("SELECT COUNT(*) FROM button;")
        count = cur.fetchone()[0]
        print(f"  总记录数: {count}")
        
        if count > 0:
            cur.execute("SELECT MIN(id), MAX(id) FROM button;")
            min_id, max_id = cur.fetchone()
            print(f"  ID范围: {min_id} - {max_id}")
            
            # 检查序列
            cur.execute("SELECT pg_get_serial_sequence('button', 'id');")
            seq_name = cur.fetchone()[0]
            
            if seq_name:
                print(f"\n序列信息:")
                print(f"  序列名: {seq_name}")
                
                cur.execute(f"SELECT last_value, is_called FROM {seq_name};")
                last_val, is_called = cur.fetchone()
                print(f"  当前值: {last_val}")
                print(f"  已调用: {is_called}")
                
                if last_val <= max_id:
                    print(f"\n  ⚠️  问题发现！")
                    print(f"  序列值({last_val}) <= 最大ID({max_id})")
                    print(f"  这会导致主键冲突！")
                    print(f"\n  修复SQL:")
                    print(f"  SELECT setval('{seq_name}', {max_id});")
                    
                    # 自动修复
                    print(f"\n  是否自动修复？(y/n)")
                    # 直接修复
                    cur.execute(f"SELECT setval('{seq_name}', {max_id});")
                    conn.commit()
                    print(f"  ✅ 已自动修复序列值")
                else:
                    print(f"\n  ✅ 序列值正常")
        
        cur.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("\n🔍 检查 button 表\n")
    check_button_table()
