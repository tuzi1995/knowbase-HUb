#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动修复导入错误：为 knowledge_base_v1 表添加缺失字段
执行此脚本前请确保 PostgreSQL 服务正在运行
"""

import json
import sys
import os

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("❌ 缺少 psycopg2 模块")
    print("请运行: pip install psycopg2-binary")
    sys.exit(1)

# 读取配置文件
config_path = os.path.join(os.path.dirname(__file__), '..', '..', '⚙️ 配置文件', 'supabase_config_local.json')
try:
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
except FileNotFoundError:
    print(f"❌ 配置文件不存在: {config_path}")
    sys.exit(1)

# 获取数据库配置
db_config = config.get('local_db', {})
host = db_config.get('host', 'localhost')
port = db_config.get('port', 5432)
database = db_config.get('database', 'knowledgebase_local')
user = db_config.get('user', 'postgres')
password = db_config.get('password', '')

print("=" * 60)
print("知识库导入错误修复工具")
print("=" * 60)
print(f"\n📋 数据库配置:")
print(f"   Host: {host}")
print(f"   Port: {port}")
print(f"   Database: {database}")
print(f"   User: {user}")
print()

# 连接数据库
try:
    print("🔌 正在连接数据库...")
    conn = psycopg2.connect(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password
    )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)
    print("✅ 数据库连接成功\n")
except Exception as e:
    print(f"❌ 数据库连接失败: {e}")
    print("\n请检查:")
    print("1. PostgreSQL 服务是否正在运行")
    print("2. 数据库配置信息是否正确")
    print("3. 数据库是否已创建")
    sys.exit(1)

def check_column_exists(table_name, column_name):
    """检查列是否存在"""
    cur.execute("""
        SELECT EXISTS (
            SELECT 1 
            FROM information_schema.columns 
            WHERE table_name = %s AND column_name = %s
        )
    """, (table_name, column_name))
    return cur.fetchone()['exists']

def check_table_exists(table_name):
    """检查表是否存在"""
    cur.execute("""
        SELECT EXISTS (
            SELECT 1 
            FROM information_schema.tables 
            WHERE table_name = %s
        )
    """, (table_name,))
    return cur.fetchone()['exists']

# 需要添加的字段
required_fields = [
    ('image_urls', 'JSONB'),
    ('video_urls', 'JSONB'),
    ('file_urls', 'JSONB'),
    ('link_type', 'TEXT'),
    ('link_url', 'TEXT')
]

# 需要删除的旧字段
deprecated_fields = ['answer_info', 'urls']

# 需要更新的表
tables = ['knowledge_base_v1', 'knowledge_base_v1_t1']

try:
    print("🔍 检查表结构...\n")
    
    for table in tables:
        print(f"📊 检查表: {table}")
        
        # 检查表是否存在
        if not check_table_exists(table):
            print(f"   ⚠️  表不存在，跳过")
            continue
        
        # 检查缺失的字段
        missing_fields = []
        for field_name, field_type in required_fields:
            if not check_column_exists(table, field_name):
                missing_fields.append((field_name, field_type))
        
        # 检查需要删除的字段
        existing_deprecated = []
        for field_name in deprecated_fields:
            if check_column_exists(table, field_name):
                existing_deprecated.append(field_name)
        
        if missing_fields:
            print(f"   ❌ 缺少字段: {', '.join([f[0] for f in missing_fields])}")
        else:
            print(f"   ✅ 所有必需字段都存在")
        
        if existing_deprecated:
            print(f"   ⚠️  存在旧字段: {', '.join(existing_deprecated)}")
        
        print()
    
    # 询问是否继续
    print("=" * 60)
    response = input("是否执行数据库更新？(yes/no): ").strip().lower()
    if response not in ['yes', 'y', '是']:
        print("❌ 操作已取消")
        sys.exit(0)
    
    print("\n🔧 开始更新数据库结构...\n")
    
    # 执行更新
    for table in tables:
        if not check_table_exists(table):
            continue
        
        print(f"📝 更新表: {table}")
        
        # 添加新字段
        for field_name, field_type in required_fields:
            if not check_column_exists(table, field_name):
                try:
                    sql = f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {field_name} {field_type}"
                    cur.execute(sql)
                    print(f"   ✅ 添加字段: {field_name} ({field_type})")
                except Exception as e:
                    print(f"   ❌ 添加字段失败 {field_name}: {e}")
                    raise
        
        # 删除旧字段
        for field_name in deprecated_fields:
            if check_column_exists(table, field_name):
                try:
                    sql = f"ALTER TABLE {table} DROP COLUMN IF EXISTS {field_name}"
                    cur.execute(sql)
                    print(f"   ✅ 删除旧字段: {field_name}")
                except Exception as e:
                    print(f"   ⚠️  删除字段失败 {field_name}: {e}")
                    # 删除失败不影响主要功能，继续执行
        
        print()
    
    # 提交事务
    conn.commit()
    print("✅ 数据库更新成功！\n")
    
    # 验证更新
    print("🔍 验证更新结果...\n")
    for table in tables:
        if not check_table_exists(table):
            continue
        
        print(f"📊 表: {table}")
        cur.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = %s 
              AND column_name IN ('image_urls', 'video_urls', 'file_urls', 'link_type', 'link_url')
            ORDER BY column_name
        """, (table,))
        
        columns = cur.fetchall()
        for col in columns:
            print(f"   ✅ {col['column_name']}: {col['data_type']}")
        print()
    
    print("=" * 60)
    print("🎉 修复完成！现在可以重新导入 Excel 文件了。")
    print("=" * 60)

except Exception as e:
    conn.rollback()
    print(f"\n❌ 更新失败: {e}")
    print("\n请检查:")
    print("1. 是否有足够的数据库权限")
    print("2. 数据库是否被其他程序锁定")
    print("3. SQL 语句是否正确")
    sys.exit(1)

finally:
    if cur:
        cur.close()
    if conn:
        conn.close()
