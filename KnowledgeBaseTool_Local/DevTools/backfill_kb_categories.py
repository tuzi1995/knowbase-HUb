import os
import json
import sys
import re
import pandas as pd

# 1. 设置路径，确保能导入 server.py 和 scoring_logic.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
sys.path.append(PROJECT_ROOT)

# 确保 server.py 能找到正确的配置文件
os.chdir(PROJECT_ROOT)

from server import get_supabase_client, parse_product_catalog

def backfill_kb_categories():
    print("🚀 开始修复存量数据的产品分类...")
    
    client = get_supabase_client()
    if not client:
        print("❌ 无法获取数据库客户端，请检查配置。")
        return

    # 1. 获取型号分类映射库
    try:
        catalog = parse_product_catalog() or {}
        norm_model_to_categories = {}
        for cat, models in (catalog.items() if isinstance(catalog, dict) else []):
            if not cat: continue
            if not isinstance(models, list): continue
            for m in models:
                ms = str(m).strip()
                if not ms: continue
                # 归一化处理（去空格，转小写）
                norm_key = ms.replace(" ", "").lower()
                norm_model_to_categories.setdefault(norm_key, set()).add(str(cat).strip())
        print(f"✅ 已加载型号映射库，共 {len(norm_model_to_categories)} 个型号。")
    except Exception as e:
        print(f"❌ 加载型号库失败: {e}")
        return

    # 2. 查询所有记录
    # 我们同时处理 v1 和 v1_t1
    for table in ['knowledge_base_v1', 'knowledge_base_v1_t1']:
        try:
            print(f"\n🔍 正在从 {table} 读取数据...")
            # 获取所有数据（可能较多，select_all 内部已处理分页）
            all_rows = client.select_all(table, columns='question_wiki_id,product_name,product_category_name', order_by='question_wiki_id')
            print(f"📊 共获取到 {len(all_rows)} 条记录。")
        except Exception as e:
            print(f"❌ 读取 {table} 数据失败: {e}")
            continue

        # 3. 筛选并计算需要更新的记录
        updates = []
        for row in all_rows:
            wiki_id = row.get('question_wiki_id')
            if not wiki_id: continue
            
            raw_cat = row.get('product_category_name')
            cur_cat = str(raw_cat or '').strip()
            
            # 更加激进的空值判断
            is_empty = not cur_cat or cur_cat.lower() in ('nan', 'null', 'none', '[]', '{}')
            
            if is_empty:
                raw_models = str(row.get('product_name') or '').strip()
                if not raw_models or raw_models.lower() in ('nan', 'null', 'none'):
                    continue
                    
                # split and normalize each model for matching
                parts = [p.strip() for p in re.split(r'[,，]', raw_models) if p.strip()]
                cats = set()
                for p in parts:
                    p_norm = p.replace(" ", "").lower()
                    hit = norm_model_to_categories.get(p_norm)
                    if hit:
                        cats.update(hit)
                
                if cats:
                    new_cat_str = ",".join(sorted(cats))
                    updates.append({
                        'question_wiki_id': wiki_id,
                        'product_category_name': new_cat_str
                    })

        if not updates:
            print(f"✨ {table} 没有发现需要修复的存量数据。")
            continue

        print(f"🛠️ {table} 发现 {len(updates)} 条记录需要回填分类。正在执行更新...")

        # 4. 执行更新
        batch_size = 50
        success_count = 0
        for i in range(0, len(updates), batch_size):
            batch = updates[i:i+batch_size]
            try:
                res = client.upsert(table, batch, on_conflict='question_wiki_id')
                if getattr(res, 'status_code', 0) < 300:
                    success_count += len(batch)
                    print(f"✅ {table} 已完成: {success_count}/{len(updates)}")
                else:
                    print(f"⚠️ {table} 批次更新失败 ({i}-{i+batch_size}): {res.text}")
            except Exception as e:
                print(f"❌ {table} 批次更新异常 ({i}-{i+batch_size}): {e}")

        print(f"🎉 {table} 修复完成！成功更新 {success_count} 条记录。")
    print("💡 您现在可以刷新网页查看效果了。")

if __name__ == "__main__":
    backfill_kb_categories()
