#!/usr/bin/env python3
"""
检查修改记录表的数据
"""
import json
import psycopg2
from psycopg2.extras import RealDictCursor

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
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # 1. 检查表是否存在
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM pg_tables 
            WHERE tablename = 'knowledge_base_modifications'
        );
    """)
    table_exists = cursor.fetchone()['exists']
    print(f"\n✅ 表是否存在: {table_exists}")
    
    if not table_exists:
        print("❌ knowledge_base_modifications 表不存在！")
        exit(1)
    
    # 2. 检查记录数量
    cursor.execute("SELECT COUNT(*) as count FROM knowledge_base_modifications;")
    count = cursor.fetchone()['count']
    print(f"📊 修改记录总数: {count}")
    
    # 3. 查看最近的10条记录
    cursor.execute("""
        SELECT 
            id,
            kb_id,
            question_wiki_id,
            modifier,
            modification_time,
            change_type,
            product_name,
            question,
            answer
        FROM knowledge_base_modifications
        ORDER BY modification_time DESC
        LIMIT 10;
    """)
    
    records = cursor.fetchall()
    
    if records:
        print(f"\n📝 最近的 {len(records)} 条修改记录:")
        print("-" * 100)
        for i, rec in enumerate(records, 1):
            print(f"\n{i}. ID: {rec['id']}")
            print(f"   KB ID: {rec['kb_id'] or rec['question_wiki_id']}")
            print(f"   修改人: {rec['modifier']}")
            print(f"   修改时间: {rec['modification_time']}")
            print(f"   操作类型: {rec['change_type']}")
            print(f"   产品: {rec['product_name']}")
            print(f"   问题: {(rec['question'] or '')[:50]}...")
    else:
        print("\n⚠️  没有找到任何修改记录！")
    
    # 4. 检查表结构
    cursor.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'knowledge_base_modifications'
        ORDER BY ordinal_position;
    """)
    
    columns = cursor.fetchall()
    print(f"\n📋 表结构 ({len(columns)} 个字段):")
    for col in columns:
        print(f"   - {col['column_name']}: {col['data_type']}")
    
    cursor.close()
    conn.close()
    
    print("\n✅ 检查完成！")
    
except Exception as e:
    print(f"\n❌ 错误: {e}")
    import traceback
    traceback.print_exc()
