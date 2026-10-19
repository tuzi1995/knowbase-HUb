"""End-to-end comparison workflow against an isolated ledger and versioned KB fake."""
from copy import deepcopy
from types import SimpleNamespace
import json

import pytest
import server
from comparison_matrix import pair_key, unpack

OLD = 'https://example.com/old.png'
NEW = 'https://example.com/new.png'
OTHER = 'https://example.com/other.png'
CATALOG = {'扫地机': ['A', 'B', 'C'], '洗地机': ['X', 'Y']}
Batch, Asset, Cell, Decision, Execution = server.COMPARISON_MODELS


def response(data=None, status=200):
    return SimpleNamespace(status_code=status, json=lambda: deepcopy(data or []), text='', headers={})


class Knowledge:
    def __init__(self):
        self.links = [{'id': 'old-link', 'url': OLD, 'tags': ['产品对比图', '原标签'], 'kb_id': 'KB1,KB2', 'type': 'image', 'created_at': '2026-10-01'}]
        self.kbs = {kb: dict(question_wiki_id=kb, question='原问题', answer='原答案',
                            product_name='A,B,C', product_category_name='扫地机', content_version=1,
                            image_urls=json.dumps([OTHER, OLD, OLD]), link_url=OTHER) for kb in ('KB1', 'KB2')}
        self.logs = []
        self.writes = []
        self.fail = set()
        self.race = False

    def select_all(self, table, filters=None, **kwargs):
        rows = {'link_previews': self.links, 'knowledge_base_v1': list(self.kbs.values()),
                'knowledge_base_modifications': self.logs}[table]
        rows = deepcopy(rows)
        for key, value in (filters or {}).items():
            if key == 'and':
                parts = value.strip('()').split(',')
                for part in parts:
                    name, op, expected = part.split('.', 2)
                    rows = [r for r in rows if str(r.get(name)) == expected]
            else:
                expected = str(value).removeprefix('eq.')
                rows = [r for r in rows if str(r.get(key)) == expected]
        return rows

    def select(self, table, **kwargs):
        return response(self.select_all(table, **kwargs))

    def upsert(self, table, data, **kwargs):
        assert table == 'link_previews'
        for item in data:
            old = next((v for v in self.links if v['id'] == item['id']), None)
            if old:
                old.update(item)
            else:
                self.links.append(deepcopy(item))
        return response(data)

    def update(self, table, data, filters, returning=False):
        assert table == 'knowledge_base_v1'
        assert returning is True  # comparison writes must check affected rows
        kb = filters['question_wiki_id'].removeprefix('eq.')
        if kb in self.fail:
            return response(status=500)
        row = self.kbs[kb]
        if self.race:
            self.race = False
            row.update(content_version=row['content_version'] + 1, image_urls=json.dumps([OTHER, 'https://example.com/concurrent.png', OLD]))
        if str(row['content_version']) != filters['content_version'].removeprefix('eq.'):
            return response([])
        row.update(deepcopy(data))
        self.writes.append((kb, deepcopy(data)))
        return response([row])

    def insert_log(self, client, table, data):
        assert table == 'knowledge_base_modifications'
        item = dict(deepcopy(data), id=len(self.logs)+1)
        self.logs.append(item)
        return response([item])


@pytest.fixture
def api(monkeypatch):
    main = Knowledge()
    monkeypatch.setattr(server, 'get_supabase_client', lambda: main)
    monkeypatch.setattr(server, 'parse_product_catalog', lambda: deepcopy(CATALOG))
    monkeypatch.setattr(server, '_supabase_insert_drop_unknown_columns', main.insert_log)
    monkeypatch.setattr(server, 'invalidate_relationships_for_source_change', lambda *a, **kw: {})
    monkeypatch.setitem(server.app.config, 'LOGIN_DISABLED', True)
    monkeypatch.setitem(server.app.config, 'TESTING', True)
    with server.app.app_context():
        for model in server.COMPARISON_MODELS:
            model.__table__.create(server.db.engine, checkfirst=True)
        for model in reversed(server.COMPARISON_MODELS):
            model.query.delete()
        server.db.session.commit()
    with server.app.test_client() as http:
        yield http, main


def post(http, path, body):
    result = http.post('/api/comparison-matrix' + path, json=body)
    assert result.status_code == 200, result.get_json()
    return result.get_json()


def initialize(http, models=None):
    post(http, '/initialize', {})
    overview = http.get('/api/comparison-matrix/overview').get_json()
    asset = next(v for v in overview['assets'] if v['url'] == OLD)
    post(http, f"/assets/{asset['id']}/models", {'models': models or ['A', 'B']})
    return asset['id']


def add(http, url=NEW, models=None):
    return post(http, '/batches', {'name': '测试批次', 'images': [{'url': url, 'models': models or ['A', 'B']}]})


def detail(http, a='A', b='B'):
    return http.get('/api/comparison-matrix/cell', query_string={'category': '扫地机', 'a': a, 'b': b}).get_json()


def confirm(http, url=NEW, targets=None, a='A', b='B', action='replace'):
    data = detail(http, a, b)
    asset = next(v for v in data['candidates'] if v['url'] == url)
    if targets is None:
        targets = [v for v in asset['targets'] if v['old_url'] == OLD and v['position'] == 1]
    return post(http, '/confirm', {'category': '扫地机', 'pair': [a,b], 'asset_id': asset['id'],
                                  'action': action, 'targets': targets, 'base_decision_id': data['cell'].get('decision_id')})['decision_id']


def apply(http, ids):
    preview = post(http, '/preview', {'decision_ids': ids})
    result = post(http, '/apply', {'decision_ids': ids, 'token': preview['token']})
    return result


def test_history_never_infers_image_models_or_activates_without_confirmation(api):
    http, main = api
    result = post(http, '/initialize', {})
    assert result['added'] == 1
    assert post(http, '/initialize', {})['added'] == 0
    overview = http.get('/api/comparison-matrix/overview').get_json()
    asset = overview['assets'][0]
    assert asset['models'] == []
    assert len(asset['references']) == 4  # each repeated URL is a distinct position
    assert asset['references'][0]['kb_models'] == 'A,B,C'
    assert overview['cells'] == []
    assert main.writes == []


def test_exact_location_multi_kb_and_idempotent_unified_write(api):
    http, main = api
    initialize(http)
    confirm(http, url=OLD, action='initialize')
    add(http)
    data = detail(http)
    targets = [t for t in next(v for v in data['candidates'] if v['url'] == NEW)['targets'] if t['kb_id']=='KB1' and t['position']==1]
    decision = confirm(http, targets=targets)
    before = detail(http)['cell']
    assert before['status'] == '已确认待写入' and before['active_url'] == OLD
    assert main.writes == []
    result = apply(http, [decision])
    assert result['cells'][0]['status'] == '已生效'
    assert json.loads(main.kbs['KB1']['image_urls']) == [OTHER, NEW, OLD]
    assert json.loads(main.kbs['KB2']['image_urls']) == [OTHER, OLD, OLD]
    assert main.kbs['KB1']['link_url'] == OTHER
    assert len(main.logs) == len(main.writes) == 1
    assert main.logs[0]['source_code'] == 'comparison_matrix'
    assert main.logs[0]['base_version'] == 1 and main.logs[0]['committed_version'] == 2
    apply(http, [decision])
    assert len(main.logs) == len(main.writes) == 1
    rows = http.get('/api/comparison-matrix/executions').get_json()['rows']
    assert rows[0]['modification_id'] == 1 and rows[0]['status'] == '成功'
    assert http.get('/api/comparison-matrix/executions?format=csv').status_code == 200


def test_partial_success_preserves_old_active_and_retry_skips_success(api):
    http, main = api
    initialize(http)
    confirm(http, url=OLD, action='initialize')
    add(http)
    d = confirm(http)
    main.fail.add('KB2')
    result = apply(http, [d])
    assert result['cells'][0]['status'] == '部分成功'
    assert result['cells'][0]['active_url'] == OLD
    assert len(main.writes) == 1
    main.fail.clear()
    result = apply(http, [d])
    assert result['cells'][0]['active_url'] == NEW
    assert len(main.writes) == len(main.logs) == 2


@pytest.mark.parametrize('change', ['version', 'url', 'race'])
def test_conflicts_never_overwrite_or_false_activate(api, change):
    http, main = api
    initialize(http); add(http)
    d = confirm(http)
    if change == 'version':
        main.kbs['KB1']['content_version'] = 2
    elif change == 'url':
        main.kbs['KB1']['image_urls'] = json.dumps([OTHER, OTHER, OLD])
    else:
        main.race = True
    result = apply(http, [d])
    assert result['cells'][0]['active_url'] is None
    assert any(g['status']=='冲突' for g in result['groups'])
    assert all(kb!='KB1' for kb, _ in main.writes)
    assert len(main.logs) == 1  # only the independently successful KB2


def test_shared_kb_location_different_new_urls_blocks_only_that_kb(api):
    http, main = api
    initialize(http, ['A','B','C'])
    add(http)
    add(http, url='https://example.com/ac.png', models=['A','C'])
    d1 = confirm(http)
    d2 = confirm(http, url='https://example.com/ac.png', a='A', b='C')
    preview = post(http, '/preview', {'decision_ids':[d1,d2]})
    assert all(g['conflicts'] for g in preview['groups'])
    result = apply(http, [d1,d2])
    assert all(c['status']=='冲突' for c in result['cells'])
    assert not main.writes and not main.logs


def test_same_url_shared_location_merges_kb_write_across_cells(api):
    http, main = api
    initialize(http, ['A','B','C']); add(http, models=['A','B','C'])
    d1=confirm(http); d2=confirm(http, a='B', b='C')
    result=apply(http,[d1,d2])
    assert all(c['status']=='已生效' for c in result['cells'])
    assert len(main.writes)==2  # one write per KB, not one per cell


def test_recovery_after_kb_commit_does_not_repeat_modification(api, monkeypatch):
    http, main = api
    initialize(http); add(http)
    d=confirm(http)
    original=main.select_all
    failed={'once':True}
    def fail_after_write(table, **kwargs):
        if table=='knowledge_base_modifications' and main.logs and failed['once'] and 'operation_id' in (kwargs.get('filters') or {}):
            failed['once']=False
            raise RuntimeError('模拟审计回读中断')
        return original(table, **kwargs)
    monkeypatch.setattr(main,'select_all',fail_after_write)
    first=apply(http,[d])
    assert any(g['status']=='待恢复' for g in first['groups'])
    result=apply(http,[d])
    assert result['cells'][0]['status']=='已生效'
    assert len(main.writes)==len(main.logs)==2


def test_unordered_pairs_model_order_and_recommendations(api):
    http, main = api
    initialize(http, ['B','A']); add(http, models=['A','B'])
    # Another old three-model image is a fallback, independent of click order.
    main.links.append(dict(main.links[0], id='wide', url='https://example.com/wide.png'))
    main.kbs['KB3']=dict(main.kbs['KB1'],question_wiki_id='KB3',image_urls=json.dumps(['https://example.com/wide.png']))
    post(http,'/initialize',{})
    overview=http.get('/api/comparison-matrix/overview').get_json()
    wide=next(a for a in overview['assets'] if a['url'].endswith('wide.png'))
    post(http,f"/assets/{wide['id']}/models",{'models':['C','A','B']})
    a,b=detail(http),detail(http,'B','A')
    assert a['cell']['id']==b['cell']['id']==pair_key('扫地机',['B','A'])
    candidate=next(v for v in a['candidates'] if v['url']==NEW)
    assert candidate['targets'][0]['rank']==[0,2]
    assert candidate['targets'][-1]['rank']==[1,3]
    assert candidate['targets'][0]['old_models']==['B','A']
    assert len(http.get('/api/comparison-matrix/overview').get_json()['cells'])==3


@pytest.mark.parametrize('models', [['A'], ['A','A'], ['A','X'], ['A','unknown']])
def test_invalid_coverage_does_not_write_links(api, models):
    http, main=api
    result=http.post('/api/comparison-matrix/batches',json={'images':[{'url':NEW,'models':models}]})
    assert result.status_code==400
    assert len(main.links)==1


def test_keep_persists_new_candidates_do_not_override(api):
    http, main=api
    initialize(http); add(http)
    confirm(http,action='keep')
    add(http,url='https://example.com/later.png')
    assert detail(http)['cell']['status']=='保持旧图'
    assert not main.writes


def test_historical_conflict_requires_explicit_selection_and_keeps_real_references(api):
    http, main=api
    initialize(http)
    second='https://example.com/second.png'
    main.links.append(dict(main.links[0],id='second',url=second))
    main.kbs['KB2']['image_urls']=json.dumps([second])
    post(http,'/initialize',{})
    assets=http.get('/api/comparison-matrix/overview').get_json()['assets']
    aid=next(v['id'] for v in assets if v['url']==second)
    post(http,f'/assets/{aid}/models',{'models':['A','B']})
    assert detail(http)['historical_conflict'] is True
    assert detail(http)['cell']['active_url'] is None
    confirm(http,url=OLD,action='initialize')
    assert detail(http)['cell']['active_url']==OLD
    assert next(v for v in detail(http)['candidates'] if v['url']==second)['references'][0]['kb_id']=='KB2'
    assert not main.writes


def test_exact_single_link_field_and_multiple_positions_one_kb(api):
    http, main=api
    main.kbs['KB1']['link_url']=OLD
    initialize(http); add(http)
    candidate=next(v for v in detail(http)['candidates'] if v['url']==NEW)
    targets=[v for v in candidate['targets'] if v['kb_id']=='KB1']
    d=confirm(http,targets=targets)
    apply(http,[d])
    assert main.kbs['KB1']['link_url']==NEW
    assert json.loads(main.kbs['KB1']['image_urls'])==[OTHER,NEW,NEW]
    assert len(main.writes)==1


def test_preview_stale_confirmation_and_arbitrary_kb_target_are_rejected(api):
    http, main=api
    initialize(http); add(http)
    d=confirm(http)
    preview=post(http,'/preview',{'decision_ids':[d]})
    main.kbs['KB1']['content_version']=2
    result=http.post('/api/comparison-matrix/apply',json={'decision_ids':[d],'token':preview['token']})
    assert result.status_code==409 and not main.writes
    candidate=next(v for v in detail(http)['candidates'] if v['url']==NEW)
    target=dict(candidate['targets'][0],old_url=OTHER)
    result=http.post('/api/comparison-matrix/confirm',json={'category':'扫地机','pair':['A','B'], 'asset_id':candidate['id'],
                       'action':'replace','targets':[target], 'base_decision_id':d})
    assert result.status_code==400


def test_authentication_required(api, monkeypatch):
    http, main=api
    monkeypatch.setitem(server.app.config,'LOGIN_DISABLED',False)
    response=http.post('/api/comparison-matrix/initialize',json={})
    assert response.status_code in (302,401)
    assert not main.writes


def test_started_merged_group_cannot_be_retried_with_subset(api):
    http, main=api
    initialize(http,['A','B','C']); add(http,models=['A','B','C'])
    d1=confirm(http); d2=confirm(http,a='B',b='C')
    apply(http,[d1,d2])
    response=http.post('/api/comparison-matrix/preview',json={'decision_ids':[d1]})
    assert response.status_code==400
    assert len(main.writes)==2


def test_removed_new_image_tag_blocks_application(api):
    http, main=api
    initialize(http); add(http)
    d=confirm(http)
    next(v for v in main.links if v['url']==NEW)['tags']=[]
    result=apply(http,[d])
    assert all(g['status']=='冲突' for g in result['groups'])
    assert not main.writes


def test_inflight_claim_prevents_second_writer(api):
    from comparison_matrix import now
    http, main=api
    initialize(http); add(http)
    d=confirm(http)
    plan=post(http,'/preview',{'decision_ids':[d]})
    with server.app.app_context():
        for group in plan['groups']:
            server.db.session.add(Execution(id=group['id'],kb_id=group['kb_id'],payload_json=json.dumps({'entries':group['entries']}),
                                  decision_ids_json=json.dumps([d]),status='写入中',actor='other',created_at=now(),updated_at=now()))
        server.db.session.commit()
    result=apply(http,[d])
    assert not main.writes
    assert result['cells'][0]['status']=='写入中'


def test_schema_migration_is_additive_and_idempotent(api):
    import server as s
    import comparison_matrix_migration as migration
    http, main=api
    initialize(http)
    with s.app.app_context():
        migration.upgrade(s.db,s.COMPARISON_MODELS)
        migration.upgrade(s.db,s.COMPARISON_MODELS)
        s.db.session.remove()
        assert Asset.query.count()==1
    assert not main.writes


def test_logged_in_operator_is_preserved_in_unified_audit(api, monkeypatch):
    http, main=api
    user=server.User(id=42,username='comparison-operator')
    monkeypatch.setattr(server.login_manager,'_user_callback',lambda _id:user)
    monkeypatch.setitem(server.app.config,'LOGIN_DISABLED',False)
    with http.session_transaction() as session:
        session['_user_id']='42'
        session['_fresh']=True
    initialize(http); add(http)
    d=confirm(http)
    result=apply(http,[d])
    assert all(g['status']=='成功' for g in result['groups'])
    assert all(r['modifier']=='comparison-operator' for r in main.logs)


def test_postgres_conditional_update_returns_actual_rows_and_commits(monkeypatch):
    calls=[]
    commits=[]
    client=server.LocalPostgreSQLClient({})
    client.connection=SimpleNamespace(commit=lambda:commits.append(True))
    monkeypatch.setattr(server,'_assert_external_write_allowed',lambda _op:None)
    def execute(sql, values, fetch):
        calls.append((sql,values,fetch))
        return []  # lost CAS: no row matched
    monkeypatch.setattr(client,'_execute_query',execute)
    result=client.update('knowledge_base_v1',{'image_urls':['new']},
                         {'question_wiki_id':'KB1','content_version':'eq.1'},returning=True)
    assert result.status_code==200 and result.json()==[]
    assert calls[0][0].endswith(' RETURNING *')
    assert calls[0][2] is True and commits==[True]


def test_remote_conditional_write_never_queues_on_network_failure(monkeypatch):
    client=server.SupabaseClient('https://example.com','test-only-key')
    client.enable_outbox=True
    monkeypatch.setattr(server,'_assert_external_write_allowed',lambda _op:None)
    monkeypatch.setattr(client.session,'patch',lambda *a,**kw: (_ for _ in ()).throw(RuntimeError('network failure')))
    queued=[]
    monkeypatch.setattr(server,'_outbox_enqueue',lambda *a,**kw:queued.append(kw))
    result=client.update('knowledge_base_v1',{'image_urls':['new']},{'content_version':'eq.1'},returning=True)
    assert result.status_code==500 and not queued


def test_link_only_write_preserves_unrelated_blank_category(api):
    http, main=api
    main.kbs['KB1']['product_category_name']=''
    initialize(http); add(http)
    d=confirm(http)
    apply(http,[d])
    assert main.kbs['KB1']['product_category_name']==''
    history=detail(http)['history']
    assert history[0]['action']=='replace' and history[0]['targets'][0]['field']=='image_urls'


def test_noncanonical_image_array_does_not_silently_normalize_other_positions(api):
    http, main=api
    main.kbs['KB1']['image_urls']=json.dumps(['null',OLD])
    initialize(http); add(http)
    candidate=next(v for v in detail(http)['candidates'] if v['url']==NEW)
    assert all(t['kb_id']!='KB1' for t in candidate['targets'])
    assert not main.writes


def test_link_index_associations_show_per_kb_models_without_inventing_targets(api):
    http, main = api
    main.kbs['KB1']['image_urls'] = json.dumps([OTHER])
    main.kbs['KB2']['image_urls'] = json.dumps([OTHER])
    main.kbs['KB1']['product_name'] = 'A,B'
    main.kbs['KB2']['product_name'] = 'A,C'
    initialize(http)
    asset = http.get('/api/comparison-matrix/overview').get_json()['assets'][0]
    assert asset['references'] == []
    assert {r['kb_id']: r['kb_models'] for r in asset['kb_associations']} == {'KB1': 'A,B', 'KB2': 'A,C'}
    assert all(not r['reference_verified'] for r in asset['kb_associations'])
    add(http)
    candidate = next(a for a in detail(http)['candidates'] if a['url'] == NEW)
    assert candidate['targets'] == []


def test_actual_references_are_found_without_link_index_and_no_models_inferred(api):
    http, main = api
    main.links[0]['kb_id'] = None
    post(http, '/initialize', {})
    asset = http.get('/api/comparison-matrix/overview').get_json()['assets'][0]
    assert asset['models'] == []
    assert {r['kb_id'] for r in asset['kb_associations']} == {'KB1', 'KB2'}
    assert all(r['reference_verified'] for r in asset['kb_associations'])


def test_association_reads_physical_v1_like_link_sync_and_handles_stale_ids(api, monkeypatch):
    http, main = api
    original = main.select_all
    def formal_filtered(table, **kwargs):
        if table == 'knowledge_base_v1' and kwargs.get('use_formal') is not False:
            return []
        return original(table, **kwargs)
    monkeypatch.setattr(main, 'select_all', formal_filtered)
    main.links[0]['kb_id'] = 'KB1，KB2;MISSING'
    post(http, '/initialize', {})
    asset = http.get('/api/comparison-matrix/overview').get_json()['assets'][0]
    assert len(asset['references']) == 4
    by_id = {r['kb_id']: r for r in asset['kb_associations']}
    assert by_id['KB1']['kb_models'] == 'A,B,C'
    assert by_id['MISSING']['kb_exists'] is False
    assert by_id['MISSING']['reference_verified'] is False
