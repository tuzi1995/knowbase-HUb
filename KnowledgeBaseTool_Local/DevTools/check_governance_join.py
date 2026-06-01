#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查知识库治理数据关联
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def check_join():
    """检查数据关联"""
    
    print("="*60)
    print("检查知识库治理数据关联")
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
        
        # 1. 检查 kb_recall 表
        print("\n1. kb_recall 表统计:")
        cur.execute("SELECT COUNT(*) FROM kb_recall;")
        recall_count = cur.fetchone()[0]
        print(f"   总记录数: {recall_count}")
        
        cur.execute("SELECT COUNT(DISTINCT kb_id) FROM kb_recall;")
        unique_kb_ids = cur.fetchone()[0]
        print(f"   唯一 kb_id 数: {unique_kb_ids}")
        
        # 2. 检查 knowledge_base_v1 表
        print("\n2. knowledge_base_v1 表统计:")
        cur.execute("SELECT COUNT(*) FROM knowledge_base_v1;")
        kb_count = cur.fetchone()[0]
        print(f"   总记录数: {kb_count}")
        
        cur.execute("SELECT COUNT(DISTINCT question_wiki_id) FROM knowledge_base_v1;")
        unique_wiki_ids = cur.fetchone()[0]
        print(f"   唯一 question_wiki_id 数: {unique_wiki_ids}")
        
        # 3. 检查关联情况
        print("\n3. 检查数据关联:")
        cur.execute("""
            SELECT COUNT(DISTINCT r.kb_id)
            FROM kb_recall r
            INNER JOIN knowledge_base_v1 k ON r.kb_id = k.question_wiki_id;
        """)
        matched_count = cur.fetchone()[0]
        print(f"   可关联的 kb_id 数: {matched_count}")
        print(f"   关联率: {matched_count / unique_kb_ids * 100:.1f}%")
        
        # 4. 查看不匹配的示例
        print("\n4. 不匹配的 kb_id 示例（前 5 个）:")
        cur.execute("""
            SELECT DISTINCT r.kb_id
            FROM kb_recall r
            LEFT JOIN knowledge_base_v1 k ON r.kb_id = k.question_wiki_id
            WHERE k.question_wiki_id IS NULL
            LIMIT 5;
        """)
        unmatched = cur.fetchall()
        for (kb_id,) in unmatched:
            print(f"   - {kb_id}")
        
        # 5. 检查 kb_scores 表
        print("\n5. kb_scores 表统计:")
        try:
            cur.execute("SELECT COUNT(*) FROM kb_scores;")
            scores_count = cur.fetchone()[0]
            print(f"   总记录数: {scores_count}")
            
            cur.execute("SELECT COUNT(DISTINCT kb_id) FROM kb_scores;")
            unique_score_ids = cur.fetchone()[0]
            print(f"   唯一 kb_id 数: {unique_score_ids}")
        except Exception as e:
            print(f"   ⚠️  kb_scores 表不存在或无法访问: {e}")
        
        # 6. 测试完整的 JOIN 查询
        print("\n6. 测试完整 JOIN 查询（2026-01 月份，前 3 条）:")
        cur.execute("""
            SELECT 
                r.kb_id,
                r.month,
                r.recall_count,
                r.valid_recall_count,
                k.question,
                CASE WHEN k.question_wiki_id IS NOT NULL THEN '使用中' ELSE '已删除' END as status
            FROM kb_recall r
            LEFT JOIN knowledge_base_v1 k ON r.kb_id = k.question_wiki_id
            WHERE r.month = '2026-01'
            ORDER BY r.recall_count DESC
            LIMIT 3;
        """)
        
        results = cur.fetchall()
        for kb_id, month, recall_count, valid_recall_count, question, status in results:
            question_preview = (question[:50] + '...') if question and len(question) > 50 else (question or '无问题内容')
            print(f"\n   kb_id: {kb_id}")
            print(f"   月份: {month}")
            print(f"   召回次数: {recall_count}")
            print(f"   有效召回: {valid_recall_count}")
            print(f"   状态: {status}")
            print(f"   问题: {question_preview}")
        
        conn.close()
        
        print("\n" + "="*60)
        print("✅ 检查完成")
        print("="*60)
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    check_join()
