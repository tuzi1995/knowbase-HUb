"""Exact model scope matching for derived KB mapping tags; no live database writes."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

import server


MAPPINGS = {'双型号': ['A10', 'A20'], '单型号': ['A10'], '空分类': []}


@pytest.mark.parametrize('products,expected', [
    ('A10,A20', ['双型号']),
    ('A20,A10', ['双型号']),
    (' a 10 , a20 ,A10', ['双型号']),
    ('A10，A20', ['双型号']),
    ('A10\nA20', ['双型号']),
    ('["A20", "A10"]', ['双型号']),
    (['A20', 'A10'], ['双型号']),
    ('A10', ['单型号']),
    ('A20', []),
    ('A10,A20,A30', []),
    ('A10,A200', []),
    ('A1,A20', []),
    ('', []),
    (None, []),
])
def test_mapping_requires_equal_model_sets(products, expected):
    assert server._mapping_categories_for_product_value(products, MAPPINGS) == expected


class KnowledgeClient:
    def __init__(self):
        self.rows = [
            {'question_wiki_id': 'KB-1', 'product_name': 'A10,A20', 'similar_questions': ['如何清洁']},
            {'question_wiki_id': 'KB-2', 'product_name': 'A10', 'similar_questions': ['如何清洁']},
            {'question_wiki_id': 'KB-3', 'product_name': 'A10,A20,A30', 'similar_questions': ['如何清洁']},
            {'question_wiki_id': 'KB-4', 'product_name': 'A20,A10', 'similar_questions': ['其他问法']},
        ]
        self.tags = [{'id': 1, 'name': '双型号'}]  # Same name as a mapping, still a manual tag.
        self.relations = [{'library_type': 'current', 'question_wiki_id': 'KB-1', 'tag_id': 1}]

    def select_all(self, table, filters=None, **kwargs):
        if table == 'knowledge_base_v1':
            assert kwargs.get('use_formal') is False
            rows = self.rows
        elif table == 'kb_tags':
            rows = self.tags
        elif table == 'kb_item_tags':
            rows = self.relations
        else:
            raise AssertionError(table)
        for key, rule in (filters or {}).items():
            if rule.startswith('eq.'):
                rows = [row for row in rows if str(row.get(key)) == rule[3:]]
        return deepcopy(rows)

    def select(self, table, page=1, page_size=50, **kwargs):
        rows = self.select_all(table, **kwargs)
        start = (page - 1) * page_size
        return SimpleNamespace(status_code=200, json=lambda: rows[start:start + page_size],
                               headers={'Content-Range': f'{start}-{start + page_size - 1}/{len(rows)}'})

    def __getattr__(self, name):
        raise AssertionError(f'Derived mapping tags must not write to the database: {name}')


@pytest.fixture
def api(monkeypatch):
    database = KnowledgeClient()
    mappings = deepcopy(MAPPINGS)
    monkeypatch.setattr(server, 'get_supabase_client', lambda: database)
    monkeypatch.setattr(server, 'get_model_mappings', lambda: mappings)
    monkeypatch.setattr(server, '_formal_release_filter_enabled', lambda: False)
    monkeypatch.setitem(server.app.config, 'LOGIN_DISABLED', True)
    with server.app.test_client() as client:
        yield client, database, mappings


@pytest.mark.parametrize('query', ['', '?page=1&pageSize=50', '?similar_question=清洁&page=1&pageSize=50'])
def test_all_list_paths_return_derived_tags(api, query):
    client, _database, _mappings = api
    response = client.get('/api/kb/data' + query)
    assert response.status_code == 200
    body = response.get_json()
    rows = body['data'] if isinstance(body, dict) else body
    by_id = {row['question_wiki_id']: row for row in rows}
    assert by_id['KB-1']['kb_mapping_tags'] == ['双型号']
    assert by_id['KB-2']['kb_mapping_tags'] == ['单型号']
    assert by_id['KB-3']['kb_mapping_tags'] == []
    if query:
        assert by_id['KB-1']['kb_tags'] == ['双型号']


def test_mapping_filter_runs_before_pagination_and_combines_with_similar_search(api):
    client, _database, _mappings = api
    first = client.get('/api/kb/data', query_string={
        'mappingCategory': '双型号', 'page': 1, 'pageSize': 1,
    }).get_json()
    second = client.get('/api/kb/data', query_string={
        'mappingCategory': '双型号', 'page': 2, 'pageSize': 1,
    }).get_json()
    assert first['total'] == second['total'] == 2
    assert [first['data'][0]['question_wiki_id'], second['data'][0]['question_wiki_id']] == ['KB-1', 'KB-4']
    similar = client.get('/api/kb/data', query_string={
        'mappingCategory': '双型号', 'similar_question': '清洁', 'page': 1, 'pageSize': 50,
    }).get_json()
    assert similar['total'] == 1
    assert similar['data'][0]['question_wiki_id'] == 'KB-1'


def test_tags_recalculate_after_kb_or_mapping_changes_without_writes(api):
    client, database, mappings = api
    def tags():
        rows = client.get('/api/kb/data?page=1&pageSize=50').get_json()['data']
        return rows[0]['kb_mapping_tags']
    assert tags() == ['双型号']
    database.rows[0]['product_name'] = 'A10,A20,A30'
    assert tags() == []
    mappings['双型号'].append('A30')
    assert tags() == ['双型号']
    mappings['新名称'] = mappings.pop('双型号')
    assert tags() == ['新名称']
    del mappings['新名称']
    assert tags() == []
    assert database.tags == [{'id': 1, 'name': '双型号'}]
    assert database.relations == [{'library_type': 'current', 'question_wiki_id': 'KB-1', 'tag_id': 1}]


def test_deleted_mapping_filter_never_falls_back_to_all_rows(api):
    client, _database, _mappings = api
    result = client.get('/api/kb/data', query_string={'mappingCategory': '已删除'}).get_json()
    assert result['data'] == []
    assert result['total'] == 0


def test_item_tag_api_keeps_manual_and_automatic_tags_separate(api):
    client, database, _mappings = api
    first = client.get('/api/kb/item/tags?question_wiki_id=KB-1').get_json()
    assert first['tags'] == ['双型号']
    assert first['mapping_tags'] == ['双型号']
    database.relations.clear()
    second = client.get('/api/kb/item/tags?question_wiki_id=KB-1').get_json()
    assert second['tags'] == []
    assert second['mapping_tags'] == ['双型号']


def test_template_reference_reads_pending_v1_row_when_formal_gate_is_enabled(api, monkeypatch):
    client, database, _mappings = api
    database.rows.append({
        'question_wiki_id': 'KB-PENDING',
        'question': '待修订问题',
        'answer': '待修订答案',
        'product_name': 'A10',
        'similar_questions': [],
    })
    monkeypatch.setattr(server, '_formal_release_filter_enabled', lambda: True)

    response = client.get('/api/kb/template-reference?id=KB-PENDING')

    assert response.status_code == 200
    assert response.get_json()['data']['question'] == '待修订问题'
