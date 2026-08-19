"""Immutable V1 import snapshots and downstream delivery receipts.

This module deliberately owns only local metadata and snapshot artifacts.  It
never writes the authoritative knowledge_base_v1 table.
"""
import csv
import hashlib
import json
import os
import sqlite3
import tempfile
import uuid
from datetime import datetime, timezone
from runtime_safety import is_test_process, validate_test_sqlite_path


SYNC_FIELDS = (
    'question_wiki_id', 'question', 'answer', 'product_name',
    'product_category_name', 'question_type', 'answer_type',
    'similar_questions', 'if_bm25', 'error_list', 'keyword_list',
    'image_urls', 'video_urls', 'file_urls', 'link_type', 'link_url',
)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _normal(value):
    if value is None:
        return ''
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value]
    if isinstance(value, dict):
        return {str(key): _normal(item) for key, item in sorted(value.items())}
    if isinstance(value, bool):
        return value
    return str(value).strip()


def content_hash(row):
    payload = {field: _normal(row.get(field)) for field in SYNC_FIELDS}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


def _rows_by_id(rows):
    result = {}
    duplicate_ids = set()
    for row in rows or []:
        wiki_id = str(row.get('question_wiki_id') or '').strip()
        if wiki_id:
            if wiki_id in result:
                duplicate_ids.add(wiki_id)
            result[wiki_id] = dict(row)
    if duplicate_ids:
        sample = ', '.join(sorted(duplicate_ids)[:10])
        suffix = '…' if len(duplicate_ids) > 10 else ''
        raise ValueError(
            f'V1 导入包含重复 question_wiki_id，已拒绝生成快照: {sample}{suffix}'
        )
    return result


def _connect(db_path):
    if is_test_process():
        db_path = validate_test_sqlite_path(db_path, os.path.dirname(os.path.abspath(__file__)))
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.execute('''CREATE TABLE IF NOT EXISTS kb_v1_sync_snapshots (
        snapshot_id TEXT PRIMARY KEY, snapshot_hash TEXT NOT NULL, record_count INTEGER NOT NULL,
        artifact_path TEXT NOT NULL, created_at TEXT NOT NULL, created_by TEXT NOT NULL,
        source_import_mode TEXT NOT NULL
    )''')
    con.execute('''CREATE TABLE IF NOT EXISTS kb_v1_sync_events (
        sync_id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL, base_snapshot_id TEXT,
        added_ids_json TEXT NOT NULL, updated_ids_json TEXT NOT NULL, deleted_ids_json TEXT NOT NULL,
        status TEXT NOT NULL, dispatched_at TEXT, consumed_at TEXT, created_at TEXT NOT NULL,
        last_error TEXT NOT NULL DEFAULT ''
    )''')
    return con


def create_import_snapshot(db_path, artifact_dir, before_rows, after_rows, import_mode, created_by):
    before = _rows_by_id(before_rows)
    after = _rows_by_id(after_rows)
    before_hashes = {key: content_hash(row) for key, row in before.items()}
    after_hashes = {key: content_hash(row) for key, row in after.items()}
    added = sorted(set(after_hashes) - set(before_hashes))
    deleted = sorted(set(before_hashes) - set(after_hashes))
    updated = sorted(key for key in set(before_hashes) & set(after_hashes) if before_hashes[key] != after_hashes[key])
    ordered_rows = [after[key] for key in sorted(after)]
    manifest = '\n'.join(f'{key}:{after_hashes[key]}' for key in sorted(after_hashes))
    snapshot_hash = hashlib.sha256(manifest.encode('utf-8')).hexdigest()
    snapshot_id = str(uuid.uuid4())
    sync_id = str(uuid.uuid4())
    os.makedirs(artifact_dir, exist_ok=True)
    artifact_path = os.path.join(artifact_dir, f'{snapshot_id}.csv')

    fd, temp_path = tempfile.mkstemp(prefix=f'.{snapshot_id}.', suffix='.csv', dir=artifact_dir)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(SYNC_FIELDS), extrasaction='ignore')
            writer.writeheader()
            for row in ordered_rows:
                writer.writerow({field: json.dumps(_normal(row.get(field)), ensure_ascii=False) if isinstance(_normal(row.get(field)), (list, dict)) else _normal(row.get(field)) for field in SYNC_FIELDS})
        os.replace(temp_path, artifact_path)
    except Exception:
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass
        raise

    con = _connect(db_path)
    try:
        base = con.execute('SELECT snapshot_id FROM kb_v1_sync_snapshots ORDER BY created_at DESC LIMIT 1').fetchone()
        created_at = _now()
        con.execute('INSERT INTO kb_v1_sync_snapshots VALUES (?, ?, ?, ?, ?, ?, ?)', (
            snapshot_id, snapshot_hash, len(ordered_rows), artifact_path, created_at,
            str(created_by or 'system'), str(import_mode or 'upsert'),
        ))
        con.execute('INSERT INTO kb_v1_sync_events VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, \'\')', (
            sync_id, snapshot_id, base['snapshot_id'] if base else None,
            json.dumps(added, ensure_ascii=False), json.dumps(updated, ensure_ascii=False),
            json.dumps(deleted, ensure_ascii=False), 'ready', created_at,
        ))
        con.commit()
    finally:
        con.close()
    return {
        'sync_id': sync_id, 'snapshot_id': snapshot_id, 'snapshot_hash': snapshot_hash,
        'record_count': len(ordered_rows), 'added_ids': added, 'updated_ids': updated,
        'deleted_ids': deleted, 'status': 'ready',
    }


def get_sync_event(db_path, sync_id):
    con = _connect(db_path)
    try:
        row = con.execute('''SELECT e.*, s.snapshot_hash, s.record_count, s.created_at AS snapshot_created_at
            FROM kb_v1_sync_events e JOIN kb_v1_sync_snapshots s ON s.snapshot_id=e.snapshot_id
            WHERE e.sync_id=?''', (sync_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        for key in ('added_ids_json', 'updated_ids_json', 'deleted_ids_json'):
            result[key.replace('_json', '')] = json.loads(result.pop(key) or '[]')
        return result
    finally:
        con.close()


def get_snapshot(db_path, snapshot_id):
    con = _connect(db_path)
    try:
        row = con.execute('SELECT * FROM kb_v1_sync_snapshots WHERE snapshot_id=?', (snapshot_id,)).fetchone()
        return dict(row) if row else None
    finally:
        con.close()


def update_event_status(db_path, sync_id, status, error=''):
    con = _connect(db_path)
    try:
        fields = ['status=?', 'last_error=?']
        values = [status, str(error or '')[:1000]]
        if status == 'dispatched':
            fields.append('dispatched_at=?')
            values.append(_now())
        if status == 'consumed':
            fields.append('consumed_at=?')
            values.append(_now())
        values.append(sync_id)
        con.execute(f"UPDATE kb_v1_sync_events SET {', '.join(fields)} WHERE sync_id=?", values)
        con.commit()
    finally:
        con.close()
