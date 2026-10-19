"""Tag maintenance uses an isolated, transactional SQLite double; no live writes."""
import sqlite3
from types import SimpleNamespace

import pytest
import server

A = '10000000-0000-0000-0000-000000000001'
B = '10000000-0000-0000-0000-000000000002'


class TagClient:
    def __init__(self):
        self.connection = sqlite3.connect(':memory:')
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript('''
            CREATE TABLE kb_tags (id TEXT PRIMARY KEY, name TEXT UNIQUE);
            CREATE TABLE kb_item_tags (library_type TEXT, question_wiki_id TEXT, tag_id TEXT, PRIMARY KEY(library_type, question_wiki_id, tag_id));
            CREATE TABLE knowledge_base_v1 (question_wiki_id TEXT, question TEXT, answer TEXT);
        ''')
        self.connection.executemany('INSERT INTO kb_tags VALUES (?,?)', [(A, '旧标签'), (B, '其他标签')])
        self.connection.executemany('INSERT INTO kb_item_tags VALUES (?,?,?)', [
            ('current', 'KB-1', A), ('current', 'KB-2', A),
            ('legacy', 'KB-3', A), ('current', 'KB-1', B),
        ])
        self.connection.execute("INSERT INTO knowledge_base_v1 VALUES ('KB-1','问题原文','答案原文')")
        self.connection.commit()
        self._defer_commit = False
        self.fail_table = None
        self.rollbacks = 0

    def begin_deferred_transaction(self):
        self.connection.execute('BEGIN')
        self._defer_commit = True

    def _execute_query(self, sql, params=None, fetch=True):
        if sql.startswith('LOCK TABLE kb_tags, kb_item_tags'):
            assert self._defer_commit
            return []
        assert sql.startswith('SELECT tag_id, COUNT(DISTINCT question_wiki_id)')
        return [dict(row) for row in self.connection.execute(sql.replace('%s', '?'), params or [])]

    def commit_deferred_transaction(self):
        self.connection.commit()
        self._defer_commit = False

    def rollback_deferred_transaction(self):
        self.connection.rollback()
        self._defer_commit = False
        self.rollbacks += 1

    def close(self):
        pass  # Keep the isolated database for assertions after each HTTP request.

    def select_all(self, table, filters=None, columns='*', **kwargs):
        clauses, values = [], []
        for key, rule in (filters or {}).items():
            assert rule.startswith('eq.')
            clauses.append(f'{key} = ?')
            values.append(rule[3:])
        sql = f'SELECT {columns} FROM {table}'
        if clauses:
            sql += ' WHERE ' + ' AND '.join(clauses)
        return [dict(row) for row in self.connection.execute(sql, values)]

    def update(self, table, data, filters):
        assert table == 'kb_tags' and self._defer_commit
        if table == self.fail_table:
            return SimpleNamespace(status_code=500)
        self.connection.execute('UPDATE kb_tags SET name=? WHERE id=?', (data['name'], filters['id'][3:]))
        return SimpleNamespace(status_code=200)

    def delete(self, table, filters):
        assert self._defer_commit
        if table == self.fail_table:
            return SimpleNamespace(status_code=500)
        key, rule = next(iter(filters.items()))
        self.connection.execute(f'DELETE FROM {table} WHERE {key}=?', (rule[3:],))
        return SimpleNamespace(status_code=200)


@pytest.fixture
def api(monkeypatch):
    database = TagClient()
    monkeypatch.setattr(server, 'get_supabase_client', lambda: database)
    monkeypatch.setattr(server, 'LocalPostgreSQLClient', TagClient)
    monkeypatch.setitem(server.app.config, 'LOGIN_DISABLED', True)
    with server.app.test_client() as http:
        yield http, database
    database.connection.close()


def payload(**extra):
    return {'expected_name': '旧标签', 'expected_count': 2, **extra}


def test_list_counts_current_knowledge_and_preserves_old_dropdown_api(api):
    http, _ = api
    response = http.get('/api/kb/tags/manage')
    assert response.status_code == 200
    tags = {tag['id']: tag for tag in response.json['tags']}
    assert tags[A] == {'id': A, 'name': '旧标签', 'knowledge_count': 2}
    assert tags[B]['knowledge_count'] == 1
    assert sorted(http.get('/api/kb/tags').json) == sorted(['旧标签', '其他标签'])


def test_rename_updates_dictionary_preserves_links_and_knowledge(api):
    http, database = api
    before_links = database.select_all('kb_item_tags')
    before_content = database.select_all('knowledge_base_v1')
    response = http.put(f'/api/kb/tags/manage/{A}', json=payload(name=' 新名称 '))
    assert response.status_code == 200
    assert response.json['old_name'] == '旧标签'
    assert response.json['name'] == '新名称'
    assert database.select_all('kb_item_tags') == before_links
    assert database.select_all('knowledge_base_v1') == before_content
    assert '新名称' in http.get('/api/kb/tags').json


def test_delete_cleans_all_links_only_for_selected_tag_preserves_content(api):
    http, database = api
    content = database.select_all('knowledge_base_v1')
    response = http.delete(f'/api/kb/tags/manage/{A}', json=payload())
    assert response.status_code == 200
    assert response.json['knowledge_count'] == 2
    assert response.json['name'] is None
    assert database.select_all('kb_tags') == [{'id': B, 'name': '其他标签'}]
    assert [row['tag_id'] for row in database.select_all('kb_item_tags')] == [B]
    assert database.select_all('knowledge_base_v1') == content


@pytest.mark.parametrize('name', ['', '  ', 'a,b', 'a，b', 'a\nb', 'a' * 101, 123])
def test_invalid_names_do_not_write(api, name):
    http, database = api
    before = database.select_all('kb_tags')
    assert http.put(f'/api/kb/tags/manage/{A}', json=payload(name=name)).status_code == 400
    assert database.select_all('kb_tags') == before


def test_duplicate_name_and_case_insensitive_duplicate_are_rejected(api):
    http, database = api
    assert http.put(f'/api/kb/tags/manage/{A}', json=payload(name='其他标签')).status_code == 409
    database.connection.execute('UPDATE kb_tags SET name=? WHERE id=?', ('Test', B))
    database.connection.commit()
    assert http.put(f'/api/kb/tags/manage/{A}', json=payload(name='test')).status_code == 409


@pytest.mark.parametrize('method', ['put', 'delete'])
@pytest.mark.parametrize('changes', [{'expected_name': 'outdated'}, {'expected_count': 0}])
def test_stale_confirmation_rejected(api, method, changes):
    http, database = api
    before = database.select_all('kb_tags'), database.select_all('kb_item_tags')
    response = getattr(http, method)(f'/api/kb/tags/manage/{A}', json=payload(name='新名称', **changes))
    assert response.status_code == 409
    assert (database.select_all('kb_tags'), database.select_all('kb_item_tags')) == before
    assert database.rollbacks == 1


def test_delete_failure_rolls_back_removed_relations(api):
    http, database = api
    before = database.select_all('kb_item_tags')
    database.fail_table = 'kb_tags'
    assert http.delete(f'/api/kb/tags/manage/{A}', json=payload()).status_code == 500
    assert database.select_all('kb_item_tags') == before
    assert len(database.select_all('kb_tags')) == 2
    assert database.rollbacks == 1


def test_rename_failure_returns_error_and_keeps_tag(api):
    http, database = api
    database.fail_table = 'kb_tags'
    assert http.put(f'/api/kb/tags/manage/{A}', json=payload(name='新名称')).status_code == 500
    assert database.select_all('kb_tags')[0]['name'] == '旧标签'


def test_missing_tag_and_missing_confirmation_are_rejected(api):
    http, _ = api
    assert http.delete('/api/kb/tags/manage/10000000-0000-0000-0000-000000000099', json=payload()).status_code == 404
    assert http.delete(f'/api/kb/tags/manage/{A}', json={}).status_code == 400
    assert http.delete('/api/kb/tags/manage/not-an-id', json=payload()).status_code in (404, 405)


def test_management_requires_login(api, monkeypatch):
    http, _ = api
    monkeypatch.setitem(server.app.config, 'LOGIN_DISABLED', False)
    assert http.get('/api/kb/tags/manage').status_code in (302, 401)
    assert http.delete(f'/api/kb/tags/manage/{A}', json=payload()).status_code in (302, 401)
