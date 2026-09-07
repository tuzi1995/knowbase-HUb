import io
import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import server


class _UpdateResponse:
    def __init__(self, data=None, status_code=200, text=''):
        self._data = data if data is not None else []
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._data


class _VersionedKnowledgeClient:
    def __init__(self):
        self.row = {
            'question_wiki_id': 'KB-VERSIONED',
            'question': '原问题',
            'answer': '原答案',
            'product_name': 'G10S Pure',
            'product_category_name': '扫地机',
            'question_type': '使用',
            'answer_type': '文本',
            'if_bm25': False,
            'similar_questions': None,
            'error_list': None,
            'keyword_list': None,
            'image_urls': None,
            'video_urls': None,
            'file_urls': None,
            'link_type': '',
            'link_url': '',
            'update_time': '2026-08-19T10:00:00+08:00',
            'content_version': 7,
        }

    def select(self, table, **kwargs):
        assert table == 'knowledge_base_v1'
        return _UpdateResponse([dict(self.row)])

    def select_all(self, table, order_by='id', **kwargs):
        if table == 'knowledge_base_modifications':
            return []
        assert table == 'knowledge_base_v1'
        if order_by != 'question_wiki_id':
            raise Exception('Database Error: column "id" does not exist')
        return [{
            'question_wiki_id': self.row['question_wiki_id'],
            'content_version': self.row['content_version'],
        }]

    def update(self, table, data, filters):
        assert table == 'knowledge_base_v1'
        assert filters['content_version'] == 'eq.7'
        self.row.update(dict(data))
        return _UpdateResponse()


def test_source_code_is_stable_and_display_label_is_preserved():
    assert server._resolve_kb_source_code({'source_code': 'new_product_entry'}) == 'new_product_entry'
    assert server._resolve_kb_source_code({}, '机型矩阵管理') == 'product_matrix'

    item = server._normalize_mod_record({
        'kb_id': 'KB-1',
        'source_module': '新品录入',
        'source_code': 'new_product_entry',
        'operation_id': 'op-1',
        'base_version': 3,
        'committed_version': 4,
        'change_meta': '{}',
    })

    assert item['source_module'] == '新品录入'
    assert item['source_code'] == 'new_product_entry'
    assert item['operation_id'] == 'op-1'
    assert item['base_version'] == 3
    assert item['committed_version'] == 4


def test_archived_at_marks_event_archived_without_legacy_archive_key():
    assert server._is_archived_mod_item({'archived_at': '2026-08-17T12:00:00+08:00'}, set())
    assert not server._is_archived_mod_item({'archived_at': None}, set())


def test_unified_update_rejects_unsafe_operation_id_before_database_access():
    with server.app.test_request_context('/api/kb/update', method='POST', json={
        'question_wiki_id': 'KB-1',
        'operation_id': 'bad,operation)',
    }):
        response, status = server.update_kb_item.__wrapped__()

    assert status == 400
    assert response.get_json()['message'] == 'operation_id 格式无效'


def test_unified_update_reads_back_version_by_wiki_id_without_id_column():
    client = _VersionedKnowledgeClient()
    payload = {
        'question_wiki_id': 'KB-VERSIONED',
        'question': '恢复后的问题',
        'base_version': 7,
        'changed_fields': ['question'],
        'operation_id': 'kb-versioned-update',
    }

    with patch.object(server, 'get_supabase_client', return_value=client), patch.object(
        server, 'get_all_valid_models', return_value=({}, set())
    ), patch.object(
        server, '_supabase_insert_drop_unknown_columns', return_value=_UpdateResponse()
    ), patch.object(
        server, 'invalidate_relationships_for_source_change', return_value={}
    ), server.app.test_request_context('/api/kb/update', method='POST', json=payload):
        response = server.update_kb_item.__wrapped__()

    assert response.get_json()['success'] is True
    assert response.get_json()['content_version'] == 8


def test_unified_update_ignores_product_separator_formatting():
    client = _VersionedKnowledgeClient()
    client.row['product_name'] = 'A20 Air,A30'
    payload = {
        'question_wiki_id': 'KB-VERSIONED',
        'product_name': 'A20 Air, A30',
        'base_version': 7,
        'changed_fields': ['product_name'],
        'operation_id': 'kb-product-format-only',
    }

    with patch.object(server, 'get_supabase_client', return_value=client), patch.object(
        server,
        'get_all_valid_models',
        return_value=({'a20air': 'A20 Air', 'a30': 'A30'}, {'A20 Air', 'A30'}),
    ), patch.object(server, '_supabase_insert_drop_unknown_columns') as insert_modification, (
        server.app.test_request_context('/api/kb/update', method='POST', json=payload)
    ):
        response = server.update_kb_item.__wrapped__()

    result = response.get_json()
    assert result['success'] is True
    assert result['no_change'] is True
    assert result['content_version'] == 7
    assert client.row['product_name'] == 'A20 Air,A30'
    insert_modification.assert_not_called()


def test_atomic_update_reads_version_by_wiki_id_without_id_column():
    client = _VersionedKnowledgeClient()

    result = server._atomic_update_kb_current(
        client,
        'KB-VERSIONED',
        {'question': '恢复后的问题'},
        base_version=7,
    )

    assert result['ok'] is True
    assert result['submitted_version'] == 8


def test_legacy_source_code_in_source_module_gets_display_label():
    item = server._normalize_mod_record({
        'kb_id': 'KB-2',
        'source_module': 'product_matrix',
        'change_meta': '{}',
    })

    assert item['source_module'] == '机型矩阵管理'
    assert item['source_code'] == 'product_matrix'


class _SmartExportClient:
    def __init__(self, modifications, current_rows):
        self.modifications = modifications
        self.current_rows = current_rows

    def select_all(self, table, **kwargs):
        if table == 'knowledge_base_modifications':
            return list(self.modifications)
        if table == 'knowledge_base_v1':
            return list(self.current_rows)
        raise AssertionError(table)


def _call_smart_export(monkeypatch, modifications, current_rows):
    monkeypatch.setattr(server, 'get_supabase_client', lambda: _SmartExportClient(modifications, current_rows))
    monkeypatch.setattr(server, '_get_archived_mod_keys', lambda: set())
    with server.app.test_request_context('/api/kb/modifications/smart_merge_export'):
        return server.export_kb_modifications_smart_merge.__wrapped__()


def test_smart_export_reads_all_current_fields_from_v1(monkeypatch):
    modification = {
        'kb_id': 'KB-3',
        'question_wiki_id': 'KB-3',
        'source_module': '机型矩阵管理',
        'change_type': 'edit',
        'modification_time': '2026-08-17T10:00:00+08:00',
        'change_meta': json.dumps({
            'source': '机型矩阵管理',
            'before': {'question': '旧问题', 'answer': '旧答案', 'products': '旧型号'},
            'after': {'question': '快照问题', 'answer': '快照答案', 'products': '快照型号'},
            'changed_fields': ['products'],
        }, ensure_ascii=False),
    }
    current = {
        'question_wiki_id': 'KB-3',
        'question': '当前问题',
        'answer': '当前答案',
        'product_name': '当前型号',
    }

    response = _call_smart_export(monkeypatch, [modification], [current])
    response.direct_passthrough = False
    frame = pd.read_excel(io.BytesIO(response.get_data()))

    assert frame.loc[0, '问题'] == '当前问题'
    assert frame.loc[0, '答案'] == '当前答案'
    assert frame.loc[0, '机型'] == '当前型号'


def test_smart_export_blocks_deleted_row_without_complete_snapshot(monkeypatch):
    deletion = {
        'kb_id': 'KB-4',
        'question_wiki_id': 'KB-4',
        'change_type': 'delete',
        'modification_time': '2026-08-17T11:00:00+08:00',
        'change_meta': json.dumps({'source': '知识库管理', 'before': {}}, ensure_ascii=False),
    }

    response, status = _call_smart_export(monkeypatch, [deletion], [])

    assert status == 409
    assert response.get_json()['repair_required'] is True


def test_new_product_frontend_sends_stable_source_code():
    frontend = (Path(server.__file__).parent / 'link_viewer' / 'app_v8.js').read_text(encoding='utf-8')

    assert "source_code: opts.sourceCode || 'product_matrix'" in frontend
    assert "sourceCode: 'new_product_entry'" in frontend
