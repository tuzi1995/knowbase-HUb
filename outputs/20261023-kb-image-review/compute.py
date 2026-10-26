#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""产品对比图录入：核心计算引擎。

从当前 DB (KnowledgeBaseTool_Local/instance/data.db) 与 CSV 输入，
按主文档规则做选图、候选生成、缺口、母图分组、链接汇总。
只读计算，不写回 DB。
"""
import csv, json, sqlite3, os
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(os.path.dirname(HERE))
DB = os.path.join(PROJ, "KnowledgeBaseTool_Local", "instance", "data.db")
CSV = "/Users/tuzi/Downloads/20261023_s01_kb8085_kb_export_v1.csv"
MM = os.path.join(PROJ, "KnowledgeBaseTool_Local", "model_mappings.json")
OUT = os.path.join(HERE, "compute_result.json")

def parse_img(s):
    if not s or not s.strip():
        return []
    try:
        v = json.loads(s)
    except Exception:
        return [s.strip()]
    if isinstance(v, list):
        return [x for x in v if isinstance(x, str)]
    return [str(v)]

def load_model_order():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    cur = con.cursor()
    cur.execute("SELECT product_name, sort_order FROM matrix_column ORDER BY sort_order")
    order = {}
    for name, o in cur.fetchall():
        order[name] = o
    con.close()
    return order

def load_model_category():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    cur = con.cursor()
    cur.execute("SELECT business_key, properties_json FROM kg_nodes WHERE node_type='product_model'")
    mc = {}
    for k, pj in cur.fetchall():
        try:
            cat = json.loads(pj or '{}').get('product_category', '')
        except Exception:
            cat = ''
        mc[k] = cat
    con.close()
    return mc

def load_assets():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("SELECT id, url, link_id, category, models_json, confirmed_by, confirmed_at, historical FROM comparison_image_asset")
    assets = []
    for r in cur.fetchall():
        a = dict(r)
        a['models'] = json.loads(a['models_json'] or '[]')
        a['models_set'] = frozenset(a['models'])
        assets.append(a)
    con.close()
    return assets

def load_cells():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("SELECT id, category, pair_json, active_asset_id FROM comparison_image_cell")
    cells = []
    for r in cur.fetchall():
        c = dict(r)
        c['pair'] = json.loads(c['pair_json'] or '[]')
        cells.append(c)
    con.close()
    return cells

def load_kb_full():
    """完整现有 KB：product_matrix 的 question_wiki_id ↔ 对比问题（用于重复判断）。"""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("SELECT question_wiki_id, product_name, question_content, product_category FROM product_matrix")
    rows = cur.fetchall()
    con.close()
    # 按 question_wiki_id 聚合
    kb = defaultdict(lambda: {"models": set(), "question": None, "category": None})
    for r in rows:
        qid = r['question_wiki_id']
        kb[qid]['question'] = r['question_content']
        kb[qid]['category'] = r['product_category']
        for m in (r['product_name'] or '').split(','):
            m = m.strip()
            if m:
                kb[qid]['models'].add(m)
    return kb

def main():
    order = load_model_order()          # name -> order
    model_cat = load_model_category()   # name -> category str
    assets = load_assets()
    cells = load_cells()
    kb_full = load_kb_full()

    # canonical model set
    canonical = set(order.keys())

    # 型号库：order 排序
    # 每个资产的最新型号 = 其覆盖型号中 order 最大者
    for a in assets:
        orders = [order[m] for m in a['models'] if m in order]
        a['newest_order'] = max(orders) if orders else -1
        a['model_count'] = len(a['models_set'])

    # 读取 CSV 133 条
    rows = list(csv.DictReader(open(CSV, encoding='utf-8-sig')))
    assert len(rows) == 133, f"CSV rows = {len(rows)}"

    kbs = []
    for r in rows:
        qid = r['question_wiki_id']
        cat = r['product_category_name']
        pn = r['product_name']
        models = [t.strip() for t in pn.split(',') if t.strip()]
        # 标准化：token 是否都在 canonical
        std = set(models)
        # 别名标准化：若是系列名（不在 canonical）需展开；这里先检查
        unknown = [m for m in models if m not in canonical]
        imgs = parse_img(r['image_urls'])
        kbs.append({
            'qid': qid, 'question': r['question'], 'category': cat,
            'question_type': r['question_type'], 'answer_type': r['answer_type'],
            'models_csv': models, 'models_set': std,
            'unknown_tokens': unknown,
            'images_csv': imgs, 'image_csv': imgs[0] if imgs else '',
            'review_status': r['review_status'], 'release_status': r['release_status'],
            'kb_scope': r['kb_scope'], 'content_lifecycle_status': r['content_lifecycle_status'],
        })

    result = {
        'model_order_count': len(order),
        'model_order': {k: v for k, v in sorted(order.items(), key=lambda x: x[1])},
        'model_category': model_cat,
        'asset_count': len(assets),
        'cell_count': len(cells),
        'csv_count': len(kbs),
        'kbs': kbs,
    }

    # ---- Sheet1: 存量 KB 处理 ----
    processed = []
    for kb in kbs:
        S_kb = kb['models_set']
        cat = kb['category']
        # 候选资产：品类适用 && 完整覆盖
        cand = []
        for a in assets:
            if a['category'] != cat:
                continue
            if not S_kb <= a['models_set']:
                continue
            cand.append(a)
        # 排序：最新型号 order 降序 -> 覆盖数量降序 -> （用定义稳定的 id）
        cand.sort(key=lambda a: (-a['newest_order'], -a['model_count'], a['id']))
        chosen = cand[0] if cand else None
        reason = ''
        if chosen:
            newest = [m for m in chosen['models'] if m in order and order[m] == chosen['newest_order']]
            reason = (f"完整覆盖S_kb={len(S_kb)}型号；候选{len(cand)}张；"
                      f"最新型号 {','.join(newest)}(序{chosen['newest_order']})；覆盖{chosen['model_count']}型号")
        # 处理结论
        if kb['image_csv']:
            cur_asset = next((a for a in assets if a['url'] == kb['image_csv']), None)
            if chosen and cur_asset and chosen['id'] == cur_asset['id']:
                conclusion = '保留'
            else:
                conclusion = '修改' if chosen else '移除配图（无可用图）'
        else:
            conclusion = '补充' if (chosen and kb['answer_type'] == '图片') else \
                          ('补充' if chosen else '待补图')
        if not chosen:
            conclusion = '待补图'
        processed.append({
            'qid': kb['qid'], 'question': kb['question'], 'category': cat,
            'models_csv': kb['models_csv'], 'models_set': sorted(S_kb, key=lambda m: order.get(m, 1e9)),
            'unknown_tokens': kb['unknown_tokens'],
            'image_csv': kb['image_csv'],
            'chosen': (chosen['url'] if chosen else None), 'chosen_id': (chosen['id'] if chosen else None),
            'chosen_models': (sorted(chosen['models']) if chosen else None),
            'reason': reason, 'cand_count': len(cand),
            'conclusion': conclusion,
        })
    result['processed'] = processed

    # ---- Sheet4: 母图标准 URL 对照（按 覆盖型号集合+品类 分组） ----
    groups = defaultdict(list)
    for a in assets:
        key = (a['category'], tuple(sorted(a['models_set'])))
        groups[key].append(a)
    mother = []
    for (cat, mset), lst in sorted(groups.items(), key=lambda x: (x[0][0], -len(x[0][1]))):
        # 标准链接 = 该组首选（按 latest order/最先确认）；备选 = 其余
        lst_sorted = sorted(lst, key=lambda a: (-a['newest_order'], -a['model_count'], a.get('confirmed_at') or '', a['id']))
        std = lst_sorted[0]
        newest = [m for m in std['models'] if m in order and order[m] == std['newest_order']]
        mother.append({
            'category': cat,
            'models_set': sorted(mset),
            'model_count': len(mset),
            'std_url': std['url'],
            'alt_urls': [a['url'] for a in lst_sorted[1:]],
            'newest': sorted(newest),
            'newest_order': std['newest_order'],
            'all_historical': all(a['historical'] for a in lst),
            'group_size': len(lst),
        })
    result['mother_groups'] = mother

    # ---- Sheet5: 图片链接维度汇总 ----
    link_rows = []
    for a in assets:
        link_rows.append({
            'url': a['url'], 'category': a['category'],
            'models': sorted(a['models_set']),
            'model_count': len(a['models_set']),
            'newest_order': a['newest_order'],
            'historical': bool(a['historical']),
            'confirmed_at': a['confirmed_at'],
        })
    result['link_rows'] = link_rows

    result['assets'] = [{'id': a['id'], 'url': a['url'], 'category': a['category'],
                         'models': sorted(a['models_set']), 'newest_order': a['newest_order'],
                         'model_count': a['model_count'], 'historical': bool(a['historical']),
                         'confirmed_at': a['confirmed_at']} for a in assets]
    result['cells'] = [{'id': c['id'], 'category': c['category'], 'pair': sorted(c['pair']),
                        'active_asset_id': c['active_asset_id']} for c in cells]

    def _ser(o):
        if isinstance(o, (set, frozenset)):
            return sorted(o)
        if isinstance(o, dict):
            return {k: _ser(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [_ser(v) for v in o]
        return o


    json.dump(_ser(result), open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print("DONE. processed KBs:", len(processed), "mother groups:", len(mother), "links:", len(link_rows))
    print("conclusion distribution:", Counter(p['conclusion'] for p in processed))
    return result

if __name__ == '__main__':
    main()