"""Media tag management runs against an isolated SQLite transaction double."""
import json
import sqlite3

import pytest
import server


class MediaClient:
    def __init__(self):
        self.connection = sqlite3.connect(':memory:')
        self.connection.row_factory = sqlite3.Row
        self.connection.execute('CREATE TABLE link_previews(id TEXT, tags TEXT, url TEXT, kb_id TEXT)')
        self.connection.executemany('INSERT INTO link_previews VALUES (?,?,?,?)', [
            ('1', json.dumps(['来源:图片链接', '旧标签', '其他']), 'image', 'KB1'),
            ('2', json.dumps(['旧标签']), 'video', 'KB2'),
            ('3', json.dumps(['外链类型:url']), 'link', 'KB3'),
        ])
        self.connection.commit()
        self._defer_commit = False
        self.fail_update = False
        self.updates = 0

    def begin_deferred_transaction(self):
        self.connection.execute('BEGIN')
        self._defer_commit = True

    def _execute_query(self, sql, params=None, fetch=True):
        assert self._defer_commit
        if sql.startswith(('SET LOCAL', 'LOCK TABLE')):
            return []
        assert sql.startswith('UPDATE link_previews SET tags')
        self.updates += 1
        if self.fail_update and self.updates == 2:
            raise RuntimeError('injected second update failure')
        self.connection.execute('UPDATE link_previews SET tags=? WHERE id=?', params)
        return [{'id': params[1]}]

    def select_all(self, table, **kwargs):
        assert table == 'link_previews'
        columns = kwargs.get('columns', '*')
        return [{**dict(row), 'tags': json.loads(row['tags'])} for row in
                self.connection.execute(f'SELECT {columns} FROM link_previews ORDER BY id')]

    def commit_deferred_transaction(self):
        self.connection.commit()
        self._defer_commit = False

    def rollback_deferred_transaction(self):
        self.connection.rollback()
        self._defer_commit = False

    def close(self):
        pass


@pytest.fixture
def api(monkeypatch):
    database = MediaClient()
    monkeypatch.setattr(server, 'get_supabase_client', lambda: database)
    monkeypatch.setattr(server, 'LocalPostgreSQLClient', MediaClient)
    monkeypatch.setitem(server.app.config, 'LOGIN_DISABLED', True)
    with server.app.test_client() as http:
        yield http, database
    database.connection.close()


def payload(**extra):
    return {'expected_name': '旧标签', 'expected_count': 2, 'name': '新标签', **extra}


def test_list_excludes_system_tags_and_counts_records(api):
    http, _ = api
    assert http.get('/api/links/tags/manage').json['tags'] == [
        {'id': '其他', 'name': '其他', 'link_count': 1},
        {'id': '旧标签', 'name': '旧标签', 'link_count': 2},
    ]


@pytest.mark.parametrize('method', ['put', 'delete'])
def test_mutation_only_changes_target_business_tag(api, method):
    http, db = api
    before = db.select_all('link_previews')
    response = getattr(http, method)('/api/links/tags/manage', json=payload())
    assert response.status_code == 200
    assert response.json['link_count'] == 2
    after = db.select_all('link_previews')
    for old, new in zip(before, after):
        assert {k: v for k, v in old.items() if k != 'tags'} == {k: v for k, v in new.items() if k != 'tags'}
        expected = [('新标签' if tag == '旧标签' else tag) for tag in old['tags']
                    if tag != '旧标签' or method == 'put']
        assert new['tags'] == expected


@pytest.mark.parametrize('extra,code', [({'expected_count': 1}, 409), ({'name': '其他'}, 409),
    ({'name': ''}, 400), ({'name': '来源:手动'}, 400), ({'name': '外链类型:url'}, 400),
    ({'expected_name': '来源:图片链接'}, 400), ({'name': 'a\nb'}, 400),
    ({'name': 'x' * 101}, 400)])
def test_rejected_changes_preserve_all_data(api, extra, code):
    http, db = api
    before = db.select_all('link_previews')
    assert http.put('/api/links/tags/manage', json=payload(**extra)).status_code == code
    assert db.select_all('link_previews') == before


def test_partial_write_failure_rolls_back_every_record(api):
    http, db = api
    before = db.select_all('link_previews')
    db.fail_update = True
    assert http.put('/api/links/tags/manage', json=payload()).status_code == 500
    assert db.select_all('link_previews') == before


def test_requires_login(api, monkeypatch):
    http, _ = api
    monkeypatch.setitem(server.app.config, 'LOGIN_DISABLED', False)
    for method in ('get', 'put', 'delete'):
        assert getattr(http, method)('/api/links/tags/manage', json=payload()).status_code == 401
