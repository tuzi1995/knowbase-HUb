import importlib.util
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / 'KnowledgeBaseTool_Local' / 'new_product_release.py'
SPEC = importlib.util.spec_from_file_location('new_product_release_service', MODULE_PATH)
new_product_release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(new_product_release)


def _service(clock=None, repository=None, ttl=600):
    service = new_product_release.ProductReleaseService(
        repository=repository or new_product_release.MemoryReleaseRepository(),
        token_ttl_seconds=ttl,
        clock=clock,
        token_secret='unit-test-release-secret',
    )
    service.set_enabled(True)
    return service


def test_capabilities_require_env_and_all_database_gates():
    original = os.environ.get('NEW_PRODUCT_RELEASE_ENABLED')
    try:
        os.environ.pop('NEW_PRODUCT_RELEASE_ENABLED', None)
        repository = new_product_release.MemoryReleaseRepository()
        service = new_product_release.ProductReleaseService(repository=repository)
        caps = service.capabilities()
        assert caps['enabled'] is False
        assert caps['read_only'] is True
        assert 'NEW_PRODUCT_RELEASE_ENABLED' in caps['block_reason']

        service.set_enabled(True)
        repository.gate = lambda: {
            'db_available': True,
            'exit_switch': False,
            'migration_passed': True,
            'reconciliation_passed': True,
        }
        caps = service.capabilities()
        assert caps['enabled'] is False
        assert 'exit switch' in caps['block_reason']
    finally:
        if original is not None:
            os.environ['NEW_PRODUCT_RELEASE_ENABLED'] = original


def test_register_model_defers_when_release_domain_is_not_migrated():
    repository = new_product_release.MemoryReleaseRepository()
    repository.gate = lambda: {
        'db_available': False,
        'error': 'relation "public.product_release_domain_state" does not exist',
    }
    service = _service(repository=repository)

    result = service.register_model('A-100', status='pending_release')

    assert result['persistence'] == 'deferred'
    assert result['model_id'] == 'A-100'
    assert repository.models == {}


def test_postgres_model_state_map_reads_all_models_with_one_connection():
    state = {
        'models': {
            'A-100': {'model_id': 'A-100', 'release_status': 'released'},
            'A-200': {'model_id': 'A-200', 'release_status': 'pending_release'},
        }
    }
    calls = {'connect': 0, 'sql': []}

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, _params=None):
            calls['sql'].append(sql)

        def fetchone(self):
            return {'state_json': state}

    class Connection:
        def cursor(self, **_kwargs):
            return Cursor()

        def close(self):
            pass

    repository = new_product_release.PostgresReleaseRepository()

    def connect_once():
        calls['connect'] += 1
        return Connection()

    repository._connect = connect_once

    result = repository.model_state_map()

    assert calls['connect'] == 1
    assert len(calls['sql']) == 1
    assert result == state['models']


def test_preview_token_expires_and_is_bound_to_model_digest():
    now = [1000]
    service = _service(clock=lambda: now[0], ttl=10)
    token = service.preview_model('A-100')['preview']['preview_token']

    wrong_model = service.publish({
        'model_id': 'A-101',
        'target_kb': 'KB-1',
        'preview_token': token,
        'public_kb_confirmed': True,
    })
    assert wrong_model['ok'] is False
    assert '摘要不匹配' in wrong_model['block_reason']

    now[0] = 1011
    expired = service.publish({
        'model_id': 'A-100',
        'target_kb': 'KB-1',
        'preview_token': token,
        'public_kb_confirmed': True,
    })
    assert expired['ok'] is False
    assert '已过期' in expired['block_reason']


def test_malformed_preview_token_is_a_controlled_publish_error():
    service = _service()
    result = service.publish({
        'model_id': 'A-100-malformed',
        'target_kb': 'KB-100',
        'preview_token': 'not-a-token',
        'public_kb_confirmed': True,
    })
    assert result['ok'] is False
    assert result['status_code'] == 400
    assert 'preview_token' in result['block_reason']


def test_publish_is_idempotent_and_survives_service_recreation():
    repository = new_product_release.MemoryReleaseRepository()
    service = _service(repository=repository)
    preview = service.preview_model('A-200')['preview']['preview_token']
    payload = {
        'request_id': 'REQ-200',
        'model_id': 'A-200',
        'target_kb': 'KB-200',
        'preview_token': preview,
        'public_kb_confirmed': True,
    }
    first = service.publish(payload)
    duplicate = service.publish(payload)
    restarted = _service(repository=repository)

    assert first['ok'] is True
    assert duplicate['ok'] is True
    assert duplicate['request']['request_id'] == 'REQ-200'
    assert len(restarted.workspace_state()['pending_requests']) == 1
    assert len(restarted.workspace_state()['outbox']) == 1


def test_cancel_is_terminal_and_reapply_creates_new_generation():
    service = _service()
    preview = service.preview_model('A-300')['preview']['preview_token']
    first = service.publish({
        'request_id': 'REQ-300',
        'model_id': 'A-300',
        'target_kb': 'KB-300',
        'preview_token': preview,
        'public_kb_confirmed': True,
    })
    cancelled = service.cancel(first['request']['request_id'])
    reapplied = service.reapply(first['request']['request_id'])

    assert cancelled['request']['status'] == 'cancelled'
    assert reapplied['ok'] is True
    assert reapplied['request']['request_id'] != first['request']['request_id']
    assert reapplied['request']['pending_version'] == 2
    assert reapplied['request']['reapplied_from'] == first['request']['request_id']


def test_database_failure_is_not_reported_as_publish_success():
    class FailingRepository(new_product_release.MemoryReleaseRepository):
        def create_release(self, **kwargs):
            raise RuntimeError('write failed')

    service = _service(repository=FailingRepository())
    preview = service.preview_model('A-400')['preview']['preview_token']
    result = service.publish({
        'model_id': 'A-400',
        'target_kb': 'KB-400',
        'preview_token': preview,
        'public_kb_confirmed': True,
    })
    assert result['ok'] is False
    assert result['status_code'] == 503
    assert '保持未提交' in result['block_reason']


def test_save_change_strips_nul_from_new_kb_pending_model_snapshot():
    repository = new_product_release.MemoryReleaseRepository()
    repository.ensure_model('P30 Member', status='pending_release')
    payload = {
        'effect_mode': 'with_model_release',
        'model_ids': ['P30 Member'],
        'trigger_model_ids': ['P30 Member'],
        'expected_model_states': {'P30 Member': 'pending_release'},
        'changed_fields': ['question', 'answer'],
        'public_kb_confirmed': True,
        'snapshot': {
            'question': '越障高度多少?',
            'answer': '最高越障8cm\x00单门槛最高4cm',
            'similar_questions': ['能越多高\x00?'],
        },
    }

    result = repository.save_change('DRAFT-test-nul', payload)

    assert result['effect_mode'] == 'with_model_release'
    saved = repository.pending[result['pending']['pending_id']]['pending_snapshot']
    assert saved == {
        'question': '越障高度多少?',
        'answer': '最高越障8cm单门槛最高4cm',
        'similar_questions': ['能越多高?'],
    }
    assert '\x00' in payload['snapshot']['answer']
    assert '\\u0000' not in new_product_release._json(repository.export_state())


def test_pending_records_expose_content_and_model_for_new_kb_draft():
    repository = new_product_release.MemoryReleaseRepository()
    repository.ensure_model('P30 Member', status='pending_release')
    baseline = {'question': '', 'answer': ''}
    pending = {'question': '如何清洁滚刷？', 'answer': '取下滚刷后清理缠绕物。'}

    saved = repository.save_change('DRAFT-P30-1', {
        'effect_mode': 'with_model_release',
        'model_ids': ['P30 Member'],
        'trigger_model_ids': ['P30 Member'],
        'changed_fields': ['question', 'answer'],
        'baseline_snapshot': baseline,
        'snapshot': pending,
        'public_kb_confirmed': True,
        'actor': 'admin',
    })

    record = repository.pending_records()[0]
    assert record['record_id'] == saved['pending']['pending_id']
    assert record['question_wiki_id'] == 'DRAFT-P30-1'
    assert record['target_model'] == 'P30 Member'
    assert record['before'] == baseline
    assert record['after'] == pending
    assert record['created_by'] == 'admin'


def test_new_kb_stays_create_even_when_editor_sends_blank_baseline_snapshot():
    repository = new_product_release.MemoryReleaseRepository()
    repository.ensure_model('P30 Member', status='pending_release')

    saved = repository.save_change('DRAFT-new-kb', {
        'is_create': True,
        'effect_mode': 'with_model_release',
        'model_ids': ['P30 Member'],
        'trigger_model_ids': ['P30 Member'],
        'changed_fields': ['question', 'answer'],
        'baseline_snapshot': {'question': '', 'answer': ''},
        'snapshot': {'question': '新问题', 'answer': '新答案'},
        'public_kb_confirmed': True,
    })

    assert saved['pending']['pending_change_type'] == 'create'
    assert repository.kbs['DRAFT-new-kb']['kb_scope'] == 'draft_pending_release'
    assert 'DRAFT-new-kb' not in repository.formal_records

    service = _service(repository=repository)
    preview = service.preview_model('P30 Member')['preview']['preview_token']
    published = service.publish({
        'model_id': 'P30 Member',
        'preview_token': preview,
        'public_kb_confirmed': True,
        'idempotency_key': 'publish-new-kb',
    })
    assert published['ok'] is True
    record = next(row for row in repository.formal_records if row['kb_id'] == 'DRAFT-new-kb')
    assert record['change_type'] == 'create'


def test_new_kb_create_mode_rejects_an_existing_wiki_id():
    repository = new_product_release.MemoryReleaseRepository()
    repository.ensure_model('P30 Member', status='pending_release')
    repository.seed_formal_kb('DRAFT-existing', {'question': 'old', 'answer': 'old'}, 1)

    try:
        repository.save_change('DRAFT-existing', {
            'is_create': True,
            'effect_mode': 'with_model_release',
            'model_ids': ['P30 Member'],
            'trigger_model_ids': ['P30 Member'],
            'snapshot': {'question': 'new', 'answer': 'new'},
            'public_kb_confirmed': True,
        })
    except new_product_release.ReleaseConflict as exc:
        assert exc.code == 'kb_already_exists'
    else:
        raise AssertionError('create mode must not silently update an existing KB')


def test_pending_model_association_snapshot_preserves_existing_models():
    before, after = new_product_release._association_change_snapshots(
        ['G10S Pro', 'G20S'], 'P30 Member', False, True,
    )

    assert before == {'configured': False, 'products': ['G10S Pro', 'G20S']}
    assert after == {'configured': True, 'products': ['G10S Pro', 'G20S', 'P30 Member']}


def test_release_materialization_promotes_pending_matrix_association():
    class Cursor:
        def execute(self, sql, _params=None):
            self.sql = sql

        def fetchall(self):
            if 'information_schema.columns' in self.sql:
                return [{'column_name': 'migration_batch_id'}]
            if 'SELECT product_name FROM public.product_matrix' in self.sql:
                return [{'product_name': 'G10S Pro'}, {'product_name': 'G20S'}]
            return []

        def fetchone(self):
            return {
                'question': '已有问题', 'answer': '已有答案',
                'product_category_name': '扫地机', 'product_name': 'G10S Pro, G20S',
            }

    repository = new_product_release.PostgresReleaseRepository()
    written = []
    repository._upsert_available = lambda _cur, table, payload, _keys: written.append((table, payload))
    repository._insert_available = lambda _cur, table, payload: written.append((table, payload))
    formal = {
        'record_id': 'FR-MATRIX-1', 'kb_id': 'KB-EXISTING', 'model_id': 'P30 Member',
        'change_type': 'matrix_association', 'modifier': 'admin', 'created_at': 'now',
        'before': {'configured': False}, 'after': {'configured': True},
        'source_module': '新品录入', 'source_operation_id': 'new-product-submit-1',
    }
    pending = {
        'formal_record_id': 'FR-MATRIX-1', 'question_wiki_id': 'KB-EXISTING',
        'target_model': 'P30 Member', 'change_type': 'matrix_association',
        'before': False, 'after': True, 'published_at': 'now',
    }
    state = new_product_release.MemoryReleaseRepository({
        'formal_records': [formal], 'pending_modifications': [pending],
    })
    state.seed_formal_kb('KB-EXISTING', {
        'question': '已有问题', 'answer': '已有答案', 'product_name': 'G10S Pro, G20S',
    }, 1)

    repository._materialize_release(Cursor(), state, {
        'batch_id': 'RB-MATRIX-1', 'model_id': 'P30 Member', 'formal_record_ids': ['FR-MATRIX-1'],
    })

    matrix = next(payload for table, payload in written if table == 'product_matrix')
    kb_projection = next(payload for table, payload in written if table == 'knowledge_base_v1')
    assert matrix['association_status'] == 'active'
    assert matrix['release_status'] == 'released'
    assert kb_projection['product_name'] == 'G10S Pro, G20S, P30 Member'
    materialized_formal = state.formal_records[0]
    assert materialized_formal['before']['products'] == ['G10S Pro', 'G20S']
    assert materialized_formal['after']['products'] == ['G10S Pro', 'G20S', 'P30 Member']


def test_release_materialization_removes_cancelled_association_from_v1_only():
    class Cursor:
        def execute(self, sql, _params=None):
            self.sql = sql

        def fetchall(self):
            if 'information_schema.columns' in self.sql:
                return [{'column_name': 'migration_batch_id'}]
            if 'SELECT product_name FROM public.product_matrix' in self.sql:
                return [{'product_name': 'G10S Pro'}, {'product_name': 'P30 Member'}]
            return []

        def fetchone(self):
            return {
                'question': '已有问题', 'answer': '已有答案',
                'product_category_name': '扫地机', 'product_name': 'G10S Pro, P30 Member, G20S',
            }

    repository = new_product_release.PostgresReleaseRepository()
    written = []
    repository._upsert_available = lambda _cur, table, payload, _keys: written.append((table, payload))
    repository._insert_available = lambda _cur, table, payload: written.append((table, payload))
    formal = {
        'record_id': 'FR-MATRIX-REMOVE', 'kb_id': 'KB-EXISTING', 'model_id': 'P30 Member',
        'change_type': 'matrix_association', 'modifier': 'admin', 'created_at': 'now',
        'before': {'configured': True}, 'after': {'configured': False},
    }
    pending = {
        'formal_record_id': 'FR-MATRIX-REMOVE', 'question_wiki_id': 'KB-EXISTING',
        'target_model': 'P30 Member', 'change_type': 'matrix_association',
        'before': True, 'after': False, 'published_at': 'now',
    }
    state = new_product_release.MemoryReleaseRepository({
        'formal_records': [formal], 'pending_modifications': [pending],
    })
    state.seed_formal_kb('KB-EXISTING', {
        'question': '已有问题', 'answer': '已有答案',
        'product_name': 'G10S Pro, P30 Member, G20S',
    }, 1)

    repository._materialize_release(Cursor(), state, {
        'batch_id': 'RB-MATRIX-REMOVE', 'model_id': 'P30 Member',
        'formal_record_ids': ['FR-MATRIX-REMOVE'],
    })

    kb_projection = next(payload for table, payload in written if table == 'knowledge_base_v1')
    assert kb_projection['product_name'] == 'G10S Pro, G20S'


def test_postgres_projection_adapts_list_values_to_jsonb_columns():
    class Cursor:
        def execute(self, sql, params):
            self.sql = sql
            self.params = params

        def fetchall(self):
            return [
                {'column_name': 'question_wiki_id', 'udt_name': 'text'},
                {'column_name': 'similar_questions', 'udt_name': 'jsonb'},
                {'column_name': 'change_meta', 'udt_name': 'jsonb'},
            ]

    cursor = Cursor()
    new_product_release.PostgresReleaseRepository._upsert_available(
        cursor,
        'knowledge_base_v1',
        {
            'question_wiki_id': 'DRAFT-test-jsonb',
            'similar_questions': ['问法一', '问法二'],
            'change_meta': new_product_release.Json({'effect_mode': 'immediate'}),
        },
        ('question_wiki_id',),
    )

    assert isinstance(cursor.params[1], new_product_release.Json)
    assert cursor.params[1].adapted == ['问法一', '问法二']
    assert cursor.params[2].adapted == {'effect_mode': 'immediate'}
    assert 'ON CONFLICT' in cursor.sql


def test_outbox_retry_and_reconcile_use_repository_state():
    service = _service()
    preview = service.preview_model('A-500')['preview']['preview_token']
    published = service.publish({
        'model_id': 'A-500',
        'target_kb': 'KB-500',
        'preview_token': preview,
        'public_kb_confirmed': True,
    })
    retry = service.retry_outbox(published['request']['batch_id'])
    reconcile = service.reconcile()
    assert retry['ok'] is True
    assert retry['outbox'][0]['status'] == 'sent'
    assert reconcile == {'ok': True, 'status': 'passed', 'pending_outbox': 0}


def test_outbox_and_reconcile_are_available_before_reconciliation_passes():
    repository = new_product_release.MemoryReleaseRepository()
    service = _service(repository=repository)
    preview = service.preview_model('A-501')['preview']['preview_token']
    published = service.publish({
        'model_id': 'A-501',
        'target_kb': 'KB-501',
        'preview_token': preview,
        'public_kb_confirmed': True,
    })
    repository.gate = lambda: {
        'db_available': True,
        'exit_switch': True,
        'migration_passed': True,
        'reconciliation_passed': False,
    }

    retry = service.retry_outbox(published['request']['batch_id'])
    reconcile = service.reconcile()

    assert retry['ok'] is True
    assert reconcile['ok'] is True
    assert reconcile['status'] == 'passed'


def test_recovery_actions_are_allowed_before_reconciliation_but_publish_is_blocked():
    class PendingReconciliationRepository(new_product_release.MemoryReleaseRepository):
        def gate(self):
            return {
                'db_available': True,
                'exit_switch': True,
                'migration_passed': True,
                'reconciliation_passed': False,
            }

    repository = PendingReconciliationRepository()
    service = _service(repository=repository)
    preview = service.preview_model('A-501')
    assert preview['ok'] is False
    assert 'reconciliation 未通过' in preview['block_reason']

    repository.outbox.append({'batch_id': 'B-501', 'status': 'pending', 'attempts': 0})
    retry = service.retry_outbox('B-501')
    assert retry['ok'] is True
    assert retry['outbox'][0]['status'] == 'sent'
    reconcile = service.reconcile()
    assert reconcile['ok'] is True


def test_release_routes_require_login():
    source = (ROOT / 'KnowledgeBaseTool_Local' / 'server.py').read_text(encoding='utf-8')
    routes = [
        '/api/new-product-release/capabilities',
        '/api/new-product-release/workspace',
        '/api/new-product-release/models/<model_id>/preview',
        '/api/new-product-release/models/<model_id>/publish',
        '/api/new-product-release/models/<model_id>/cancel',
        '/api/new-product-release/models/<model_id>/reapply',
        '/api/new-product-release/outbox/retry',
        '/api/new-product-release/reconcile',
    ]
    for route in routes:
        marker = f"@app.route('{route}'"
        route_index = source.index(marker)
        function_index = source.index('\ndef ', route_index)
        decorators = source[route_index:function_index]
        assert '@login_required' in decorators, route


def test_postgres_repository_uses_transaction_lock_for_versions():
    source = MODULE_PATH.read_text(encoding='utf-8')
    assert 'pg_advisory_xact_lock' in source
    assert 'MAX(pending_version),0)+1 AS n FROM public.product_release_pending_version WHERE question_wiki_id=%s FOR UPDATE' not in source


def test_pending_kb_content_appears_in_pending_ledger_then_formal_log_after_release():
    repository = new_product_release.MemoryReleaseRepository()
    repository.ensure_model('PENDING-MODEL')
    for kb_id in ('KB-PENDING-1', 'KB-PENDING-2'):
        result = repository.save_change(kb_id, {
            'model_ids': ['PENDING-MODEL'],
            'trigger_model_ids': ['PENDING-MODEL'],
            'snapshot': {'question': f'问题 {kb_id}', 'answer': '新答案'},
            'changed_fields': ['question', 'answer'],
            'effect_mode': 'with_model_release',
            'public_kb_confirmed': True,
            'actor': 'tester',
        })
        assert result['pending']['status'] == 'pending_release'

    pending_records = repository.pending_records()
    assert {row['kb_id'] for row in pending_records} == {'KB-PENDING-1', 'KB-PENDING-2'}
    assert {row['target_model'] for row in pending_records} == {'PENDING-MODEL'}
    assert repository.formal_records == []

    service = _service(repository=repository)
    preview = service.preview_model('PENDING-MODEL')['preview']['preview_token']
    published = service.publish({
        'model_id': 'PENDING-MODEL',
        'preview_token': preview,
        'public_kb_confirmed': True,
        'idempotency_key': 'release-pending-model',
    })
    formal_records = repository.formal_records

    assert published['ok'] is True
    assert {row['kb_id'] for row in formal_records} == {'KB-PENDING-1', 'KB-PENDING-2'}
    assert {row['model_id'] for row in formal_records} == {'PENDING-MODEL'}
