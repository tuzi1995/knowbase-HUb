#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查数据库中的记录数量
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import json

# 读取数据库配置
config_path = "⚙️ 配置文件/supabase_config_local.json"
with open(config_path, 'r', encoding='utf-8') as f:
    config = json.load(f)

# 获取本地数据库配置
db_config = config['local_db']

# 连接数据库
try:
    connection = psycopg2.connect(
        host=db_config['host'],
        port=db_config['port'],
        database=db_config['database'],
        user=db_config['user'],
        password=db_config['password']
    )
    
    print("=" * 60)
    print("数据库连接成功")
    print("=" * 60)
    
    with connection.cursor(cursor_factory=RealDictCursor) as cur:
        # 查询 V1 表记录数
        cur.execute("SELECT COUNT(*) as count FROM knowledge_base_v1;")
        v1_count = cur.fetchone()['count']
        
        # 查询 V1T-1 表记录数
        cur.execute("SELECT COUNT(*) as count FROM knowledge_base_v1_t1;")
        v1_t1_count = cur.fetchone()['count']
        
        # 查询 V1 表最新的几条记录
        cur.execute("""
            SELECT question_wiki_id, question, update_time 
            FROM knowledge_base_v1 
            ORDER BY update_time DESC 
            LIMIT 5;
        """)
        latest_records = cur.fetchall()
        
        # 查询 V1T-1 表最新的几条记录
        cur.execute("""
            SELECT question_wiki_id, question, update_time 
            FROM knowledge_base_v1_t1 
            ORDER BY update_time DESC 
            LIMIT 5;
        """)
        latest_t1_records = cur.fetchall()
        
        print(f"\n📊 数据统计:")
        print(f"   knowledge_base_v1 (此刻库):    {v1_count:,} 条记录")
        print(f"   knowledge_base_v1_t1 (前刻库): {v1_t1_count:,} 条记录")
        
        if v1_count == 6131:
            print(f"\n✅ 全量覆盖导入成功！V1 表已更新为 6131 条记录")
        else:
            print(f"\n⚠️  V1 表记录数为 {v1_count}，预期为 6131 条")
        
        print(f"\n📝 V1 表最新 5 条记录:")
        for i, record in enumerate(latest_records, 1):
            wiki_id = record['question_wiki_id']
            question = record['question'][:50] + '...' if len(record['question']) > 50 else record['question']
            update_time = record['update_time']
            print(f"   {i}. ID: {wiki_id} | 问题: {question} | 更新时间: {update_time}")
        
        print(f"\n📝 V1T-1 表最新 5 条记录 (备份):")
        for i, record in enumerate(latest_t1_records, 1):
            wiki_id = record['question_wiki_id']
            question = record['question'][:50] + '...' if len(record['question']) > 50 else record['question']
            update_time = record['update_time']
            print(f"   {i}. ID: {wiki_id} | 问题: {question} | 更新时间: {update_time}")
        
        # 检查是否有 JSONB 字段数据
        cur.execute("""
            SELECT 
                COUNT(*) FILTER (WHERE keyword_list IS NOT NULL AND keyword_list::text != '[]') as has_keywords,
                COUNT(*) FILTER (WHERE image_urls IS NOT NULL AND image_urls::text != '[]') as has_images,
                COUNT(*) FILTER (WHERE video_urls IS NOT NULL AND video_urls::text != '[]') as has_videos,
                COUNT(*) FILTER (WHERE file_urls IS NOT NULL AND file_urls::text != '[]') as has_files
            FROM knowledge_base_v1;
        """)
        jsonb_stats = cur.fetchone()
        
        print(f"\n📊 JSONB 字段统计:")
        print(f"   有关键词的记录: {jsonb_stats['has_keywords']:,} 条")
        print(f"   有图片的记录:   {jsonb_stats['has_images']:,} 条")
        print(f"   有视频的记录:   {jsonb_stats['has_videos']:,} 条")
        print(f"   有文件的记录:   {jsonb_stats['has_files']:,} 条")
        
        print("\n" + "=" * 60)
        print("✅ 检查完成")
        print("=" * 60)
    
    connection.close()

except Exception as e:
    print(f"❌ 数据库连接或查询失败: {e}")
    import traceback
    traceback.print_exc()
