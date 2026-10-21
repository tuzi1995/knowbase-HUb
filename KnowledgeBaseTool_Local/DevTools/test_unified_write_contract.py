import io
import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

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


class _UnreleasedKnowledgeClient(_VersionedKnowledgeClient):
    """A management row that has no released product-matrix association."""

    def __init__(self, scope='formal', fallback=False, missing=False):
        super().__init__()
        self.row.update(kb_scope=scope, review_status='creating')
        self.fallback = fallback
        self.missing = missing
        self.writes = []

    def _visible_rows(self, use_formal, filters):
        if use_formal or self.missing:
            return []
        scope_filter = (filters or {}).get('kb_scope')
        if scope_filter and scope_filter != f"eq.{self.row['kb_scope']}":
            return []
        return [dict(self.row)]

    def select(self, table, use_formal=True, filters=None, **kwargs):
        assert table == 'knowledge_base_v1'
        if self.fallback:
            return _UpdateResponse(status_code=500)
        return _UpdateResponse(self._visible_rows(use_formal, filters))

    def select_all(self, table, use_formal=True, filters=None, **kwargs):
        if table == 'knowledge_base_modifications':
            return []
        assert table == 'knowledge_base_v1'
        return self._visible_rows(use_formal, filters)

    def update(self, table, data, filters, returning=False):
        self.writes.append(dict(data))
        response = super().update(table, data, filters)
        return _UpdateResponse([dict(self.row)]) if returning else response


@pytest.mark.parametrize('fallback,strict_version', [(False, False), (True, False), (False, True)])
def test_unified_update_saves_unreleased_formal_management_row(fallback, strict_version):
    client = _UnreleasedKnowledgeClient(fallback=fallback)
    payload = {
        'question_wiki_id': 'KB-VERSIONED',
        'similar_questions': ['漂洗加脱水多久'],
        'base_version': 7,
        'strict_version': strict_version,
        'operation_id': 'unreleased-management-edit',
    }
    with patch.object(server, 'get_supabase_client', return_value=client), patch.object(
        server, '_supabase_insert_drop_unknown_columns', return_value=_UpdateResponse()
    ) as insert_log, patch.object(
        server, 'invalidate_relationships_for_source_change', return_value={}
    ), server.app.test_request_context('/api/kb/update', method='POST', json=payload):
        response = server.update_kb_item.__wrapped__()

    assert not isinstance(response, tuple), response[0].get_json() if isinstance(response, tuple) else ''
    result = response.get_json()
    assert result['success'] is True
    assert result['content_version'] == 8
    assert len(client.writes) == 1
    assert json.loads(client.row['similar_questions']) == ['漂洗加脱水多久']
    record = insert_log.call_args.args[2]
    meta = record['change_meta']
    if isinstance(meta, str):
        meta = json.loads(meta)
    assert meta['before']['question'] == '原问题'
    assert meta['before']['similar_questions'] is None
    assert 'similar_questions' in meta['changed_fields']
    assert record['base_version'] == 7
    assert record['committed_version'] == 8


@pytest.mark.parametrize('scope,missing,base_version,status', [
    ('pending', False, 7, 404),
    ('shadow', False, 7, 404),
    ('formal', True, 7, 404),
    ('formal', False, 6, 409),
])
def test_unified_update_preserves_scope_missing_and_conflict_guards(scope, missing, base_version, status):
    client = _UnreleasedKnowledgeClient(scope=scope, missing=missing)
    with patch.object(server, 'get_supabase_client', return_value=client), patch.object(
        server, '_supabase_insert_drop_unknown_columns'
    ) as insert_log, server.app.test_request_context('/api/kb/update', method='POST', json={
        'question_wiki_id': 'KB-VERSIONED',
        'question': '不应写入的问题',
        'base_version': base_version,
        'operation_id': 'unreleased-guard',
    }):
        response, actual_status = server.update_kb_item.__wrapped__()

    assert actual_status == status
    assert response.get_json()['success'] is False
    assert client.writes == []
    insert_log.assert_not_called()


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


def test_release_model_id_is_preserved_in_formal_modification_details():
    item = server._normalize_mod_record({
        'kb_id': 'KB-RELEASE-MODEL',
        'source_module': '新品录入',
        'change_type': 'matrix_association',
        'change_meta': json.dumps({
            'model_id': 'P30 Member',
            'before': {'configured': False},
            'after': {'configured': True},
        }, ensure_ascii=False),
    })

    assert item['model_id'] == 'P30 Member'
    assert item['products'] == 'P30 Member'
    assert item['before']['products'] == ''
    assert item['after']['products'] == 'P30 Member'
    assert item['changed_fields'] == ['products']


def test_hidden_product_model_is_removed_from_modification_display_only():
    item = server._normalize_mod_record({
        'kb_id': 'KB-HIDDEN-MODEL',
        'product_name': 'Z1 Ultra, Z1 Ultra 超水解, Z1 Max Ultra',
        'change_meta': json.dumps({
            'before': {'products': 'Z1 Ultra 超水解, Z1 Ultra'},
            'after': {'products': 'Z1 Ultra, Z1 Ultra 超水解, Z1 Max Ultra'},
            'changed_fields': ['products'],
        }, ensure_ascii=False),
    })

    assert item['products'] == 'Z1 Ultra, Z1 Max Ultra'
    assert item['before']['products'] == 'Z1 Ultra'
    assert item['after']['products'] == 'Z1 Ultra, Z1 Max Ultra'
    assert 'Z1 Ultra 超水解' not in json.dumps(item, ensure_ascii=False)


def test_hidden_product_filter_keeps_similar_model_names():
    assert server._without_hidden_product_models('Z1 Ultra 超水解') == ''
    assert server._without_hidden_product_models('Z1 Ultra') == 'Z1 Ultra'
    assert server._without_hidden_product_models('Z1 Max Ultra') == 'Z1 Max Ultra'


def test_hidden_product_model_is_removed_from_catalog_boundaries():
    catalog = server._without_hidden_models_in_catalog({
        '洗衣机': ['Z1 Ultra 超水解', 'Z1 Ultra', 'Z1 Max Ultra'],
    })

    assert catalog == {'洗衣机': ['Z1 Ultra', 'Z1 Max Ultra']}


def test_hidden_product_model_is_removed_from_legacy_snapshot_and_associations():
    item = server._normalize_mod_record({
        'kb_id': 'KB-HIDDEN-LEGACY',
        'product_name': 'Z1 Ultra 超水解, Z1 Ultra',
        'change_meta': json.dumps({
            'association_changes': [
                {'target_model': 'Z1 Ultra 超水解'},
                {'target_model': 'Z1 Ultra'},
            ],
        }, ensure_ascii=False),
    })

    assert item['products'] == 'Z1 Ultra'
    assert item['after']['products'] == 'Z1 Ultra'
    assert item['association_changes'] == [{'target_model': 'Z1 Ultra'}]
    assert 'Z1 Ultra 超水解' not in json.dumps(item, ensure_ascii=False)


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


def test_smart_export_uses_create_snapshot_when_current_row_is_missing(monkeypatch):
    creation = {
        'id': 1,
        'kb_id': 'ICWIKI202609220001',
        'question_wiki_id': 'ICWIKI202609220001',
        'change_type': 'create',
        'modification_time': '2026-09-22T10:00:00+08:00',
        'change_meta': json.dumps({
            'after': {
                'question': '如何开启自动清洁？',
                'question_type': '文本',
                'answer': '在 App 中打开自动清洁开关。',
                'answer_type': '文本',
                'products': 'G20,G20S',
                'if_bm25': False,
            },
        }, ensure_ascii=False),
    }

    response = _call_smart_export(monkeypatch, [creation], [])
    response.direct_passthrough = False
    frame = pd.read_excel(io.BytesIO(response.get_data()))

    row = frame.loc[frame['问题编号'] == 'ICWIKI202609220001'].iloc[0]
    assert row['操作'] == '增加'
    assert row['问题'] == '如何开启自动清洁？'
    assert row['答案'] == '在 App 中打开自动清洁开关。'
    assert row['机型'] == 'G20,G20S'


def test_smart_export_paginates_tied_timestamps_without_losing_rows(monkeypatch):
    modifications = [
        {
            'id': index + 1,
            'kb_id': f'KB-{index:04d}',
            'question_wiki_id': f'KB-{index:04d}',
            'change_type': 'edit',
            'modification_time': '2026-09-17T09:26:06+08:00',
        }
        for index in range(1003)
    ]
    modifications[0]['change_type'] = 'create'
    modifications[0]['modification_time'] = '2026-09-17T10:00:00+08:00'
    modifications.append({
        'id': 1004,
        'kb_id': 'KB-0000',
        'question_wiki_id': 'KB-0000',
        'change_type': 'edit',
        'modification_time': '2026-09-17T08:00:00+08:00',
    })

    class PagedClient:
        def select_all(self, table, **kwargs):
            if table == 'knowledge_base_v1':
                return [
                    {'question_wiki_id': f'KB-{index:04d}', 'question': '问题', 'answer': '答案'}
                    for index in range(1003)
                ]
            assert table == 'knowledge_base_modifications'
            if kwargs['order_by'] != 'id':
                # A tied timestamp can overlap successive offset pages.
                return modifications[:1000] + modifications[850:854]
            return sorted(modifications, key=lambda row: row['id'], reverse=True)

    monkeypatch.setattr(server, 'get_supabase_client', PagedClient)
    monkeypatch.setattr(server, '_get_archived_mod_keys', lambda: set())
    with server.app.test_request_context('/api/kb/modifications/smart_merge_export'):
        response = server.export_kb_modifications_smart_merge.__wrapped__()
    response.direct_passthrough = False
    frame = pd.read_excel(io.BytesIO(response.get_data()))

    assert len(frame) == 1003
    assert frame.loc[frame['问题编号'] == 'KB-0000', '操作'].iloc[0] == '增加'


def test_archive_candidates_use_stable_id_order_and_dedupe_rows():
    rows = [
        {
            'id': 'mod-1',
            'kb_id': 'KB-1',
            'question_wiki_id': 'KB-1',
            'change_type': 'edit',
            'modification_time': '2026-09-17T09:26:06+08:00',
        },
        {
            'id': 'mod-2',
            'kb_id': 'KB-2',
            'question_wiki_id': 'KB-2',
            'change_type': 'edit',
            'modification_time': '2026-09-17T09:26:06+08:00',
        },
        {
            'id': 'mod-1',
            'kb_id': 'KB-1',
            'question_wiki_id': 'KB-1',
            'change_type': 'edit',
            'modification_time': '2026-09-17T09:26:06+08:00',
        },
    ]

    class ArchiveClient:
        def select_all(self, table, **kwargs):
            assert table == 'knowledge_base_modifications'
            assert kwargs['order_by'] == 'id'
            return rows

    normalized, raw_ids = server._collect_archive_candidates(ArchiveClient())

    assert [item['supabase_id'] for item in normalized] == ['mod-1', 'mod-2']
    assert raw_ids == ['mod-1', 'mod-2']


def test_new_product_frontend_sends_stable_source_code():
    frontend = (Path(server.__file__).parent / 'link_viewer' / 'app_v8.js').read_text(encoding='utf-8')

    assert "source_code: opts.sourceCode || 'product_matrix'" in frontend
    assert "sourceCode: 'new_product_entry'" in frontend


def test_matrix_submit_migration_seeds_published_products_before_applying_changes():
    sql_path = (
        Path(server.__file__).parent
        / '🗄️ 数据库'
        / 'SQL脚本'
        / '20260911_preserve_kb_products_on_matrix_submit.sql'
    )
    sql = sql_path.read_text(encoding='utf-8')

    seed_marker = "FROM regexp_split_to_table(before_products, '[,，]') AS existing_model"
    change_marker = 'FOR change IN'
    aggregate_marker = "WHERE question_wiki_id = wiki_id AND is_configured = true"

    assert seed_marker in sql
    assert sql.index(seed_marker) < sql.index(change_marker)
    assert aggregate_marker in sql
