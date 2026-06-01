#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 JSONB 字段插入
验证 LocalPostgreSQLClient 是否正确处理 JSONB 类型
"""

import json
import sys
import os

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("❌ 缺少 psycopg2 模块")
    print("请运行: pip install psycopg2-binary")
    sys.exit(1)

# 读取配置
config_path = os.path.join(os.path.dirname(__file__), '..', '..', '⚙️ 配置文件', 'supabase_config_local.json')
with open(config_path, 'r', encoding='utf-8') as f:
    config = json.load(f)

db_config = config.get('local_db', {})

print("=" * 60)
print("JSONB 字段插入测试")
print("=" * 60)
print()

# 连接数据库
try:
    conn = psycopg2.connect(
        host=db_config.get('host', 'localhost'),
        port=db_config.get('port', 5432),
        database=db_config.get('database', 'knowledgebase_local'),
        user=db_config.get('user', 'postgres'),
        password=db_config.get('password', '')
    )
    conn.autocommit = False
    print("✅ 数据库连接成功\n")
except Exception as e:
    print(f"❌ 数据库连接失败: {e}")
    sys.exit(1)

# 测试数据
test_id = 'test_jsonb_' + str(int(os.times()[4] * 1000))
test_data = {
    'question_wiki_id': test_id,
    'question': '测试问题',
    'answer': '测试答案',
    'keyword_list': ['关键词1', '关键词2', '关键词3'],
    'similar_questions': ['相似问题1', '相似问题2'],
    'error_list': ['错误1', '错误2'],
    'image_urls': ['https://example.com/1.jpg', 'https://example.com/2.jpg'],
    'video_urls': ['https://example.com/video.mp4'],
    'file_urls': ['https://example.com/file.pdf']
}

print("📝 测试数据:")
print(f"   ID: {test_id}")
print(f"   keyword_list: {test_data['keyword_list']}")
print(f"   image_urls: {test_data['image_urls']}")
print()

# 方法 1: 直接插入 Python 列表（会失败）
print("🧪 测试 1: 直接插入 Python 列表（预期失败）")
try:
    cur = conn.cursor()
    columns = list(test_data.keys())
    values = list(test_data.values())
    placeholders = ['%s'] * len(columns)
    
    sql = f"INSERT INTO knowledge_base_v1 ({', '.join(columns)}) VALUES ({', '.join(placeholders)})"
    cur.execute(sql, values)
    conn.commit()
    cur.close()
    
    print("   ❌ 意外成功（应该失败）")
except Exception as e:
    conn.rollback()
    error_msg = str(e)
    if 'jsonb but expression is of type' in error_msg:
        print("   ✅ 预期的错误（类型不匹配）")
        print(f"   错误信息: {error_msg[:100]}...")
    else:
        print(f"   ⚠️  其他错误: {e}")

print()

# 方法 2: 转换为 JSON 字符串后插入（应该成功）
print("🧪 测试 2: 转换为 JSON 字符串后插入（预期成功）")
try:
    # 转换 JSONB 字段
    jsonb_fields = ['keyword_list', 'similar_questions', 'error_list', 'image_urls', 'video_urls', 'file_urls']
    converted_data = {}
    for key, value in test_data.items():
        if key in jsonb_fields and isinstance(value, (list, dict)):
            converted_data[key] = json.dumps(value, ensure_ascii=False)
        else:
            converted_data[key] = value
    
    cur = conn.cursor()
    columns = list(converted_data.keys())
    values = list(converted_data.values())
    placeholders = ['%s'] * len(columns)
    
    sql = f"INSERT INTO knowledge_base_v1 ({', '.join(columns)}) VALUES ({', '.join(placeholders)})"
    cur.execute(sql, values)
    conn.commit()
    cur.close()
    
    print("   ✅ 插入成功")
except Exception as e:
    conn.rollback()
    print(f"   ❌ 插入失败: {e}")

print()

# 验证数据
print("🔍 验证插入的数据:")
try:
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT question_wiki_id, keyword_list, image_urls, video_urls 
        FROM knowledge_base_v1 
        WHERE question_wiki_id = %s
    """, (test_id,))
    
    row = cur.fetchone()
    cur.close()
    
    if row:
        print("   ✅ 数据读取成功")
        print(f"   ID: {row['question_wiki_id']}")
        print(f"   keyword_list 类型: {type(row['keyword_list'])}")
        print(f"   keyword_list 值: {row['keyword_list']}")
        print(f"   image_urls 类型: {type(row['image_urls'])}")
        print(f"   image_urls 值: {row['image_urls']}")
        
        # 验证类型
        if isinstance(row['keyword_list'], list):
            print("   ✅ keyword_list 是列表类型（JSONB 自动解析）")
        else:
            print(f"   ⚠️  keyword_list 不是列表类型: {type(row['keyword_list'])}")
    else:
        print("   ❌ 未找到数据")
except Exception as e:
    print(f"   ❌ 读取失败: {e}")

print()

# 清理测试数据
print("🧹 清理测试数据:")
try:
    cur = conn.cursor()
    cur.execute("DELETE FROM knowledge_base_v1 WHERE question_wiki_id = %s", (test_id,))
    conn.commit()
    cur.close()
    print("   ✅ 测试数据已删除")
except Exception as e:
    conn.rollback()
    print(f"   ⚠️  清理失败: {e}")

print()
print("=" * 60)
print("测试完成")
print("=" * 60)

conn.close()
