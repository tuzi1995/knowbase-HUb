import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'KnowledgeBaseTool_Local'))

import server


class _ScopedFakeClient:
    def __init__(self):
        self.raw_ids = ['KB-1', 'KB-2', 'KB-3']
        self.formal_ids = ['KB-1']
        self.calls = []

    def select_all(self, table, **kwargs):
        self.calls.append(('select_all', table, kwargs))
        ids = self.raw_ids if kwargs.get('use_formal') is False else self.formal_ids
        return [{'question_wiki_id': value} for value in ids]


def test_delete_missing_id_comparison_uses_physical_v1_table():
    client = _ScopedFakeClient()

    missing = server._get_v1_ids_missing_from_file(client, ['KB-1'])

    assert missing == ['KB-2', 'KB-3']
    assert client.calls[-1][2]['use_formal'] is False


def test_import_snapshot_reader_uses_physical_v1_table():
    client = _ScopedFakeClient()

    server._read_v1_sync_rows(client)

    assert client.calls[-1][2]['use_formal'] is False


def test_bulk_import_forces_records_into_formal_scope():
    source = {'question_wiki_id': 'KB-1', 'kb_scope': 'draft_pending_release'}

    normalized = server._apply_kb_import_system_fields(source)

    assert normalized['question_wiki_id'] == 'KB-1'
    assert normalized['kb_scope'] == 'formal'
    assert source['kb_scope'] == 'draft_pending_release'


def test_matrix_projection_forces_active_formal_release_fields():
    source = {
        'question_wiki_id': 'KB-1',
        'release_status': 'pending_release',
        'association_status': 'cancelled',
        'product_release_scope': 'pending',
    }

    normalized = server._apply_matrix_projection_system_fields(source)

    assert normalized['release_status'] == 'released'
    assert normalized['association_status'] == 'active'
    assert normalized['product_release_scope'] == 'formal'
    assert source['release_status'] == 'pending_release'


def test_downstream_sync_returns_json_when_a_step_raises():
    server.app.config.update(TESTING=True, LOGIN_DISABLED=True)

    with patch.object(server, '_run_matrix_sync', side_effect=RuntimeError('matrix exploded')):
        response = server.app.test_client().post('/api/kb/sync_downstream')

    payload = response.get_json()
    assert response.status_code == 500
    assert response.content_type == 'application/json'
    assert payload['success'] is False
    assert 'matrix exploded' in payload['message']
