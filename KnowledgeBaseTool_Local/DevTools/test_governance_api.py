#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试知识库治理 API
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_api():
    """测试 API"""
    
    print("="*60)
    print("测试知识库治理 API")
    print("="*60)
    
    # 导入必要的模块
    from server import app, get_supabase_client, is_supabase_governance_enabled
    
    # 1. 检查配置
    print("\n1. 检查配置:")
    print(f"   use_supabase_governance: {is_supabase_governance_enabled()}")
    
    # 2. 测试获取月份列表
    print("\n2. 测试 /api/governance/months:")
    
    client = get_supabase_client()
    if not client:
        print("   ❌ Supabase client 不可用")
        return
    
    rows = client.select_all('kb_recall', columns='month', order_by='month', order_dir='desc', page_size=1000) or []
    months_set = set()
    for r in rows:
        m = str((r or {}).get('month') or '').strip()
        if m:
            months_set.add(m)
    months = sorted(list(months_set), reverse=True)
    
    print(f"   找到 {len(months)} 个月份:")
    for m in months[:5]:
        print(f"   - {m}")
    if len(months) > 5:
        print(f"   ... 还有 {len(months) - 5} 个月份")
    
    # 3. 测试获取数据
    if not months:
        print("\n   ⚠️  没有月份数据，无法继续测试")
        return
    
    test_month = months[0]
    print(f"\n3. 测试 /api/governance/data?month={test_month}:")
    
    # 获取召回数据
    rows = client.select_all(
        'kb_recall',
        filters={'month': f"eq.{test_month}"},
        columns='kb_id,month,recall_count,valid_recall_count',
        order_by='kb_id',
        order_dir='asc',
        page_size=1000
    ) or []
    
    print(f"   召回记录数: {len(rows)}")
    
    # 组织数据
    monthly_map = {}
    monthly_totals = {}
    
    for r in rows:
        kb_id = str(r.get('kb_id') or '').strip()
        month = str(r.get('month') or '').strip()
        recall_count = int(r.get('recall_count') or 0)
        valid_recall_count = int(r.get('valid_recall_count') or 0)
        
        if not kb_id or not month:
            continue
        
        if kb_id not in monthly_map:
            monthly_map[kb_id] = {}
        
        monthly_map[kb_id][month] = {
            'recall_count': recall_count,
            'valid_recall_count': valid_recall_count
        }
        
        if month not in monthly_totals:
            monthly_totals[month] = {'total_recall': 0, 'total_valid': 0}
        
        monthly_totals[month]['total_recall'] += recall_count
        monthly_totals[month]['total_valid'] += valid_recall_count
    
    print(f"   唯一 kb_id 数: {len(monthly_map)}")
    print(f"   月度汇总: {monthly_totals}")
    
    # 获取 kb_scores
    kb_scores_resp = client.select_all('kb_scores', columns='kb_id,total_score,question_content')
    score_map = {}
    if kb_scores_resp:
        for s in kb_scores_resp:
            score_map[str(s.get('kb_id')).strip()] = s
    print(f"   kb_scores 记录数: {len(score_map)}")
    
    # 获取 knowledge_base_v1
    v1_resp = client.select_all('knowledge_base_v1', columns='question_wiki_id,question', order_by='question_wiki_id')
    v1_map = {}
    if v1_resp:
        for v in v1_resp:
            v1_map[str(v.get('question_wiki_id')).strip()] = v
    print(f"   knowledge_base_v1 记录数: {len(v1_map)}")
    
    # 构建结果
    all_ids = set(monthly_map.keys()) | set(v1_map.keys())
    print(f"   合并后的 ID 数: {len(all_ids)}")
    
    result = []
    for kb_id in list(all_ids)[:5]:  # 只处理前 5 个
        score_entry = score_map.get(kb_id)
        v1_entry = v1_map.get(kb_id)
        
        status = '使用中' if v1_entry else '已删除'
        
        id_monthly_data = {}
        m_data = monthly_map.get(kb_id, {}).get(test_month)
        m_total = monthly_totals.get(test_month, {'total_recall': 0, 'total_valid': 0})
        
        recall_count = 0
        valid_recall_count = 0
        
        if m_data:
            recall_count = m_data['recall_count']
            valid_recall_count = m_data['valid_recall_count']
        
        id_monthly_data[test_month] = {
            'recall_count': recall_count,
            'valid_recall_count': valid_recall_count
        }
        
        question = v1_entry.get('question', "未知问题") if v1_entry else (score_entry.get('question_content', "未知问题") if score_entry else "未知问题")
        ai_score = score_entry.get('total_score') if score_entry else None
        
        result.append({
            'id': kb_id,
            'question': question,
            'ai_score': ai_score,
            'status': status,
            'monthly_data': id_monthly_data
        })
    
    print(f"\n4. 结果示例（前 3 条）:")
    for item in result[:3]:
        print(f"\n   ID: {item['id']}")
        print(f"   问题: {item['question'][:50]}...")
        print(f"   AI评分: {item['ai_score']}")
        print(f"   状态: {item['status']}")
        print(f"   月度数据: {item['monthly_data']}")
    
    print("\n" + "="*60)
    print("✅ API 测试完成")
    print("="*60)

if __name__ == '__main__':
    test_api()
