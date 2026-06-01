#!/usr/bin/env python3
"""
创建 knowledge_base_modifications 表
"""
import json
import psycopg2

# 读取配置
with open('supabase_config_local.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

db_config = config.get('local_db', {})
host = db_config.get('host', 'localhost')
port = db_config.get('port', 5432)
database = db_config.get('database', 'knowledgebase_local')
user = db_config.get('user', 'postgres')
password = db_config.get('password', '')

print(f"连接数据库: {host}:{port}/{database}")

try:
    conn = psycopg2.connect(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password
    )
    
    cursor = conn.cursor()
    
    # 读取SQL文件
    with open('create_modifications_table_local.sql', 'r', encoding='utf-8') as f:
        sql = f.read()
    
    print("\n执行SQL脚本...")
    cursor.execute(sql)
    conn.commit()
    
    print("\n✅ 表创建成功！")
    
    # 验证表是否创建
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM pg_tables 
            WHERE tablename = 'knowledge_base_modifications'
        );
    """)
    exists = cursor.fetchone()[0]
    print(f"✅ 表存在验证: {exists}")
    
    # 查看表结构
    cursor.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'knowledge_base_modifications'
        ORDER BY ordinal_position;
    """)
    
    columns = cursor.fetchall()
    print(f"\n📋 表结构 ({len(columns)} 个字段):")
    for col_name, col_type in columns:
        print(f"   - {col_name}: {col_type}")
    
    cursor.close()
    conn.close()
    
    print("\n🎉 完成！现在可以正常记录修改历史了。")
    
except Exception as e:
    print(f"\n❌ 错误: {e}")
    import traceback
    traceback.print_exc()
