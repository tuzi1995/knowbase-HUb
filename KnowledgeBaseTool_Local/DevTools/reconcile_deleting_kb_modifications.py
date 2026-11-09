#!/usr/bin/env python3
"""Backfill delete audit rows for KB items still marked as deleting.

Defaults to a read-only preview. Pass --apply to insert missing audit rows.
"""
import argparse
import json
import sys
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server


SOURCE = '知识库删除补偿'


def _kb_id(row):
    return server._normalize_kb_import_id(row.get('question_wiki_id')) if isinstance(row, dict) else ''


def collect_missing_delete_logs(client):
    deleting_rows = client.select_all(
        'knowledge_base_v1',
        filters={'review_status': 'eq.deleting'},
        order_by='question_wiki_id',
        page_size=1000,
        use_formal=False,
    ) or []
    existing_rows = client.select_all(
        'knowledge_base_modifications',
        order_by='id',
        page_size=1000,
        use_formal=False,
    ) or []
    already_logged = {
        str(row.get('kb_id') or row.get('question_wiki_id') or '').strip()
        for row in existing_rows
        if isinstance(row, dict)
        and str(row.get('change_type') or '').strip().lower() in {'delete', 'del', 'remove'}
    }
    return [
        row for row in deleting_rows
        if _kb_id(row) and _kb_id(row) not in already_logged
    ]


def build_recovery_records(rows, actor):
    records = []
    for row in rows:
        wiki_id = _kb_id(row)
        before = server._snapshot_mod_fields(row)
        operation_id = f'delete-recovery-{uuid.uuid4()}'
        record = server._build_kb_modification_record(
            SOURCE,
            actor,
            'delete',
            wiki_id,
            before,
            None,
            server._compute_mod_changed_fields(before, None),
            row,
        )
        server._attach_change_meta(record, {
            'source': SOURCE,
            'operation_id': operation_id,
            'before': before,
            'after': None,
            'changed_fields': server._compute_mod_changed_fields(before, None),
            'recovered_from_deleting_status': True,
        })
        records.append(record)
    return records


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='insert missing delete modification rows')
    parser.add_argument('--actor', default='system-recovery', help='modifier recorded on backfilled rows')
    args = parser.parse_args(argv)

    client = server.get_supabase_client()
    if not client:
        parser.error('database client is not configured')
    if args.apply:
        server._activity_archive_require_immediate_persistence(client)

    rows = collect_missing_delete_logs(client)
    ids = [_kb_id(row) for row in rows]
    print(json.dumps({
        'mode': 'apply' if args.apply else 'preview',
        'missing_delete_log_count': len(ids),
        'question_wiki_ids': ids,
    }, ensure_ascii=False, indent=2))
    if not args.apply or not rows:
        return 0

    records = build_recovery_records(rows, args.actor)
    response = server._supabase_insert_drop_unknown_columns(
        client, 'knowledge_base_modifications', records,
    )
    if response is None or getattr(response, 'status_code', 500) >= 400:
        print(getattr(response, 'text', '') if response is not None else 'insert returned no response', file=sys.stderr)
        return 1

    remaining = {_kb_id(row) for row in collect_missing_delete_logs(client)}
    if remaining:
        print(json.dumps({
            'error': 'verification_failed',
            'still_missing_ids': sorted(remaining),
        }, ensure_ascii=False), file=sys.stderr)
        return 1
    print(f'已补齐 {len(records)} 条删除修改记录，并通过回查验证。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
