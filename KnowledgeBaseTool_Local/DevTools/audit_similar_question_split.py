# -*- coding: utf-8 -*-
"""
审计：找出 similar_questions 中疑似被"全角逗号 ，"错误拆分的记录。

只读数据库，不做任何写入。输出：
  - DevTools/similar_question_audit.csv  （可人工复核的清单）
  - 终端摘要

判定逻辑（启发式）：
  对每条记录的 similar_questions 数组，从下标 i 起尝试把连续若干个元素
  用全角逗号 ，重新拼接。如果拼接结果作为子串出现在该条的 question 或 answer
  文本里，则认为这若干个元素原本是【一条】相似问，被错误拆开了。

置信度：
  HIGH   = 拼回的整句出现在 question/answer 原文中（强证据）
  MEDIUM = 拼回的整句未在原文出现，但后段以 请/并/或/检查/确认/然后 等
           "句中续接词"开头，且前段不以句末标点结尾（弱证据，需人工判断）
"""
import json
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from psycopg2.extras import RealDictCursor

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(os.path.dirname(HERE), 'supabase_config_local.json')
OUT_CSV = os.path.join(HERE, 'similar_question_audit.csv')

TABLES = ['knowledge_base_v1', 'knowledge_base_v1_t1']

# 句中续接词：若后段以这些词开头，说明它更可能是上一句的延续而非独立相似问
CONT_PREFIXES = ('请', '并', '或', '检查', '确认', '然后', '再', '将', '把', '需', '可')
# 句末标点：若前段以这些结尾，则不太可能是被拆开的半句
END_PUNCT = ('。', '！', '？', '?', '!', '；', ';')


def _norm(s):
    return re.sub(r'\s+', '', str(s or ''))


def _parse_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x or '').strip()]
    if isinstance(v, dict):
        out = []
        for vv in v.values():
            out.extend(_parse_list(vv))
        return out
    s = str(v).strip()
    if not s:
        return []
    if s.startswith('[') or s.startswith('{'):
        try:
            return _parse_list(json.loads(s))
        except Exception:
            pass
    return [s]


def find_merges(sims, qa_text):
    """返回 [(start_idx, end_idx, merged_str, confidence), ...]，左闭右闭。"""
    qa_norm = _norm(qa_text)
    results = []
    n = len(sims)
    i = 0
    while i < n:
        # 单元素必须先作为子串出现在原文中，才有"被拆"的可能
        base = _norm(sims[i])
        if not base or base not in qa_norm:
            i += 1
            continue
        # 贪婪扩展：i..j 用，拼接后仍是原文子串就继续
        j = i
        best_j = i
        while j + 1 < n:
            cand = '，'.join(sims[i:j + 2])
            if _norm(cand) in qa_norm:
                j += 1
                best_j = j
            else:
                break
        if best_j > i:
            merged = '，'.join(sims[i:best_j + 1])
            results.append((i, best_j, merged, 'HIGH'))
            i = best_j + 1
        else:
            i += 1
    return results


def find_medium(sims):
    """原文无匹配时的弱启发：相邻两元素疑似被拆。"""
    out = []
    for k in range(len(sims) - 1):
        a = str(sims[k]).strip()
        b = str(sims[k + 1]).strip()
        if not a or not b:
            continue
        if a.endswith(END_PUNCT):
            continue
        if b.startswith(CONT_PREFIXES):
            out.append((k, k + 1, f'{a}，{b}', 'MEDIUM'))
    return out


def main():
    cfg = json.load(open(CONFIG, encoding='utf-8'))['local_db']
    conn = psycopg2.connect(
        host=cfg['host'], port=cfg['port'], dbname=cfg['database'],
        user=cfg['user'], password=cfg['password']
    )
    rows_out = []
    # 去重：完全相同的 (table, wiki_id, suggested_merge) 只保留一条
    seen_rows = set()
    high = med = 0
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        for table in TABLES:
            cur.execute(
                f"SELECT question_wiki_id, question, answer, similar_questions "
                f"FROM {table} WHERE similar_questions IS NOT NULL"
            )
            for r in cur.fetchall():
                sims = _parse_list(r['similar_questions'])
                if len(sims) < 2:
                    continue
                # 标注：该记录的相似问数组内是否存在重复元素
                norm_seen = set()
                has_dup = False
                for x in sims:
                    nx = _norm(x)
                    if nx in norm_seen:
                        has_dup = True
                        break
                    norm_seen.add(nx)
                dup_flag = 'Y' if has_dup else ''

                qa = f"{r.get('question') or ''}\n{r.get('answer') or ''}"
                wiki_id = r['question_wiki_id']

                def _emit(conf, frag, merged):
                    nonlocal high, med
                    key = (table, wiki_id, merged)
                    if key in seen_rows:
                        return False
                    seen_rows.add(key)
                    rows_out.append({
                        'table': table,
                        'wiki_id': wiki_id,
                        'confidence': conf,
                        'array_has_dup': dup_flag,
                        'question': (r.get('question') or '')[:80],
                        'fragments': frag,
                        'suggested_merge': merged,
                        'full_similar': json.dumps(sims, ensure_ascii=False),
                    })
                    if conf == 'HIGH':
                        high += 1
                    else:
                        med += 1
                    return True

                merges = find_merges(sims, qa)
                covered = set()
                for (i, j, merged, conf) in merges:
                    for x in range(i, j + 1):
                        covered.add(x)
                    _emit(conf, ' | '.join(sims[i:j + 1]), merged)
                # 弱匹配（不与高置信重叠）
                for (i, j, merged, conf) in find_medium(sims):
                    if i in covered or j in covered:
                        continue
                    _emit(conf, ' | '.join(sims[i:j + 1]), merged)
    conn.close()

    # 排序：HIGH 在前，按表、wiki_id
    rows_out.sort(key=lambda x: (0 if x['confidence'] == 'HIGH' else 1, x['table'], x['wiki_id']))
    with open(OUT_CSV, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=[
            'table', 'wiki_id', 'confidence', 'array_has_dup', 'question',
            'fragments', 'suggested_merge', 'full_similar'
        ])
        w.writeheader()
        w.writerows(rows_out)

    print(f"=== 审计完成 ===")
    print(f"HIGH（强证据，拼回整句出现在原文）: {high}")
    print(f"MEDIUM（弱证据，需人工判断）       : {med}")
    print(f"清单已写入: {OUT_CSV}")
    print()
    print("--- HIGH 置信度预览（前 30 条）---")
    cnt = 0
    for row in rows_out:
        if row['confidence'] != 'HIGH':
            continue
        print(f"[{row['table']}] {row['wiki_id']}")
        print(f"    片段: {row['fragments']}")
        print(f"    建议合并为: {row['suggested_merge']}")
        cnt += 1
        if cnt >= 30:
            break


if __name__ == '__main__':
    main()
