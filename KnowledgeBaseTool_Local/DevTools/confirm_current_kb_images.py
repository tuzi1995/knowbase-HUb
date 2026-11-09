"""Register uniquely evidenced current KB images in the local matrix ledger.

Maintenance command: reads the physical KB exactly as comparison_matrix.sources
does; only writes initialize decisions and empty cell pointers in SQLite. No KB,
link, asset coverage, authentication, or existing active image is modified.
"""
import argparse
import collections
import itertools
import json
from pathlib import Path
import sqlite3
import sys
import uuid

import psycopg2
from psycopg2.extras import RealDictCursor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from comparison_matrix import dump, image_list, now, pair_key, question_match_fields, unpack


def snapshot():
    config = json.loads((ROOT / 'supabase_config_local.json').read_text())['local_db']
    connection = psycopg2.connect(
        host=config.get('host', 'localhost'), port=config.get('port', 5432),
        dbname=config.get('database', 'knowledgebase_local'),
        user=config.get('user', 'postgres'), password=config.get('password', ''))
    connection.set_session(readonly=True, isolation_level='REPEATABLE READ')
    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('SELECT question_wiki_id,question,similar_questions,product_name,'
                           'product_category_name,image_urls,link_url,content_version '
                           'FROM knowledge_base_v1 ORDER BY question_wiki_id')
            rows = [dict(row) for row in cursor.fetchall()]
            cursor.execute('SELECT url,tags FROM link_previews')
            links = [dict(row) for row in cursor.fetchall()]
            cursor.execute("SELECT count(*) AS count, md5(string_agg(md5(row_to_json(k)::text),'' "
                           "ORDER BY question_wiki_id)) AS hash FROM knowledge_base_v1 k")
            fingerprint = dict(cursor.fetchone())
        return rows, links, fingerprint
    finally:
        connection.close()


def collect(connection, rows, links, catalog):
    assets = [dict(row) for row in connection.execute('SELECT * FROM comparison_image_asset')]
    cells = {row['id']: dict(row) for row in connection.execute('SELECT * FROM comparison_image_cell')}
    tagged = {row['url'] for row in links if '产品对比图' in unpack(row['tags'], [])}
    references = collections.defaultdict(list)
    for row in rows:
        fields = [('link_url', 0, row.get('link_url'))]
        try:
            fields.extend(('image_urls', index, url) for index, url in enumerate(image_list(row.get('image_urls'))))
        except ValueError:
            pass
        for field, position, url in fields:
            if url:
                references[url].append((row, field, position))
    candidates = collections.defaultdict(list)
    covered = set()
    for asset in assets:
        category = asset['category']
        models = unpack(asset['models_json'], [])
        if not asset['confirmed_by'] or asset['url'] not in tagged:
            continue
        for pair in itertools.combinations(models, 2):
            if any(model not in catalog.get(category, []) for model in pair):
                continue
            key = pair_key(category, pair)
            covered.add(key)
            evidence = []
            for row, field, position in references[asset['url']]:
                match = question_match_fields(row, category, pair, catalog)
                if match['question_match_sources']:
                    evidence.append(dict(kb_id=str(row['question_wiki_id']), field=field,
                                         position=position, content_version=row['content_version'], **match))
            if evidence:
                candidates[key].append(dict(cell_id=key, category=category, pair=sorted(pair),
                                            asset_id=asset['id'], url=asset['url'], evidence=evidence))
    ready, ambiguous, remaining = [], [], []
    for key in sorted(covered):
        cell = cells.get(key, {})
        if cell.get('active_asset_id'):
            continue
        choices = candidates.get(key, [])
        if len({item['url'] for item in choices}) == 1:
            item = choices[0]
            item['base_decision_id'] = cell.get('latest_decision_id')
            if item['base_decision_id']:
                previous = connection.execute('SELECT action,status FROM comparison_image_decision WHERE id=?',
                                              (item['base_decision_id'],)).fetchone()
                if previous is None or previous['status'] in ('写入中', '待恢复', '部分成功') or previous['action'] == 'replace':
                    remaining.append(dict(cell_id=key, reason='存在需保留或恢复的决定'))
                    continue
            ready.append(item)
        elif choices:
            ambiguous.append(dict(cell_id=key, choices=choices))
        else:
            remaining.append(dict(cell_id=key, category=cell.get('category'),
                                  pair=unpack(cell.get('pair_json'), []),
                                  reason='当前 KB 实际引用与主问题/相似问题未形成精确型号对证据'))
    return ready, ambiguous, remaining


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    catalog = json.loads((ROOT / 'product_catalog.json').read_text())
    catalog = {category: [model for model in models if model != 'Z1 Ultra 超水解']
               for category, models in catalog.items()}
    rows, links, before = snapshot()
    connection = sqlite3.connect(ROOT / 'instance/data.db', timeout=30)
    connection.row_factory = sqlite3.Row
    ready, ambiguous, remaining = collect(connection, rows, links, catalog)
    selected = ready[:args.limit] if args.limit else ready
    stamp = now().replace(':', '').replace('.', '')
    report = dict(created_at=now(), kb_before=before, ready=len(ready),
                  by_category=dict(collections.Counter(item['category'] for item in ready)),
                  selected=selected, ambiguous=ambiguous, remaining=remaining, applied=[])
    report_path = args.output / f'confirmation-{stamp}.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    if args.apply and selected:
        backup_path = args.output / f'ledger-before-{stamp}.db'
        with sqlite3.connect(backup_path) as backup:
            connection.backup(backup)
        # Recheck the live source before mutation, and revalidate all ledger state
        # under a write lock. Existing active images are never overwritten.
        new_rows, new_links, fresh = snapshot()
        if fresh != before:
            raise RuntimeError('KB changed during preflight; run again against current evidence')
        connection.execute('BEGIN IMMEDIATE')
        try:
            fresh_ready, _, _ = collect(connection, new_rows, new_links, catalog)
            expected = {item['cell_id']: item for item in fresh_ready}
            for item in selected:
                if expected.get(item['cell_id']) != item:
                    raise RuntimeError(f"Ledger/evidence changed: {item['pair']}")
                key = item['cell_id']
                connection.execute('INSERT OR IGNORE INTO comparison_image_cell '
                                   '(id,category,pair_json) VALUES (?,?,?)',
                                   (key, item['category'], dump(item['pair'])))
                decision_id = str(uuid.uuid4())
                connection.execute('INSERT INTO comparison_image_decision '
                                   '(id,cell_id,asset_id,action,targets_json,status,actor,created_at,started) '
                                   "VALUES (?,?,?,'initialize','[]','已生效',?,?,0)",
                                   (decision_id, key, item['asset_id'], 'codex:current-kb-confirmation', now()))
                changed = connection.execute('UPDATE comparison_image_cell SET active_asset_id=?,latest_decision_id=? '
                                             'WHERE id=? AND active_asset_id IS NULL AND latest_decision_id IS ?',
                                             (item['asset_id'], decision_id, key, item['base_decision_id']))
                if changed.rowcount != 1:
                    raise RuntimeError(f"Concurrent cell update: {item['pair']}")
                report['applied'].append(dict(cell_id=key, decision_id=decision_id))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        for item, applied in zip(selected, report['applied']):
            persisted = connection.execute('SELECT active_asset_id,latest_decision_id FROM comparison_image_cell WHERE id=?',
                                           (item['cell_id'],)).fetchone()
            assert persisted['active_asset_id'] == item['asset_id']
            assert persisted['latest_decision_id'] == applied['decision_id']
        _, _, after = snapshot()
        report['kb_after'] = after
        report['kb_unchanged'] = after == before
        report['backup'] = str(backup_path.resolve())
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    print(json.dumps(dict(report=str(report_path.resolve()), ready=report['ready'],
                          by_category=report['by_category'], applied=len(report['applied']),
                          ambiguous=len(ambiguous), remaining=len(remaining),
                          kb_unchanged=report.get('kb_unchanged')), ensure_ascii=False))
    connection.close()


if __name__ == '__main__':
    main()
