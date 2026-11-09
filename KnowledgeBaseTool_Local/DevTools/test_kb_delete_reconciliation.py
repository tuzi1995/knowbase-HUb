import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server
from DevTools import reconcile_deleting_kb_modifications as recovery


class Response:
    def __init__(self, rows=None, status_code=200, text=''):
        self.rows = rows or []
        self.status_code = status_code
        self.text = text

    def json(self):
        return self.rows


class DeleteClient:
    def __init__(self):
        self.row = {
            'question_wiki_id': 'KB-DELETE-1',
            'question': '测试问题',
            'answer': '测试答案',
            'review_status': 'modifying',
        }
        self.status_writes = []

    def select(self, table, **kwargs):
        assert table == 'knowledge_base_v1'
        return Response([dict(self.row)])

    def update(self, table, data, filters):
        assert table == 'knowledge_base_v1'
        self.status_writes.append(data['review_status'])
        self.row.update(data)
        return Response()


def test_delete_rolls_back_status_when_modification_insert_fails():
    client = DeleteClient()
    with patch.object(server, 'get_supabase_client', return_value=client), patch.object(
        server, '_activity_archive_require_immediate_persistence'
    ), patch.object(
        server, '_supabase_insert_drop_unknown_columns', return_value=Response(status_code=500, text='insert failed')
    ), server.app.test_request_context('/api/kb/delete', method='POST', json={'ids': ['KB-DELETE-1']}):
        response, status = server.delete_kb_item.__wrapped__()

    assert status == 500
    assert response.get_json()['code'] == 'delete_modification_write_failed'
    assert response.get_json()['rollback_failures'] == []
    assert client.status_writes == ['deleting', 'modifying']
    assert client.row['review_status'] == 'modifying'


class RecoveryClient:
    def __init__(self):
        self.tables = {
            'knowledge_base_v1': [
                {'question_wiki_id': 'KB-MISSING', 'review_status': 'deleting', 'question': 'Q', 'answer': 'A'},
                {'question_wiki_id': 'KB-LOGGED', 'review_status': 'deleting', 'question': 'Q2', 'answer': 'A2'},
            ],
            'knowledge_base_modifications': [
                {'kb_id': 'KB-LOGGED', 'change_type': 'delete'},
            ],
        }

    def select_all(self, table, **kwargs):
        rows = self.tables[table]
        if table == 'knowledge_base_v1':
            rows = [row for row in rows if row['review_status'] == 'deleting']
        return [dict(row) for row in rows]


def test_recovery_selects_only_deleting_rows_without_delete_logs():
    rows = recovery.collect_missing_delete_logs(RecoveryClient())
    assert [row['question_wiki_id'] for row in rows] == ['KB-MISSING']
    records = recovery.build_recovery_records(rows, 'operator')
    assert records[0]['change_type'] == 'delete'
    assert records[0]['kb_id'] == 'KB-MISSING'
    assert records[0]['record_scope'] == 'formal'

