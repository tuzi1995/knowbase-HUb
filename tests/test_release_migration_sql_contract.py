from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPAND_SQL = (ROOT / 'KnowledgeBaseTool_Local' / '🗄️ 数据库' / 'SQL脚本' / '20260921_new_product_release_expand.sql').read_text(encoding='utf-8')
CONTRACT_SQL = (ROOT / 'KnowledgeBaseTool_Local' / '🗄️ 数据库' / 'SQL脚本' / '20260921_new_product_release_contract.sql').read_text(encoding='utf-8')


def test_expand_sql_contains_required_release_objects():
    required_objects = [
        'CREATE TABLE IF NOT EXISTS public.product_release_request',
        'CREATE TABLE IF NOT EXISTS public.product_release_pending_version',
        'CREATE TABLE IF NOT EXISTS public.product_release_model_binding',
        'CREATE TABLE IF NOT EXISTS public.product_release_batch',
        'CREATE TABLE IF NOT EXISTS public.product_release_business_outbox',
        'CREATE TABLE IF NOT EXISTS public.product_release_migration_batch',
        'CREATE TABLE IF NOT EXISTS public.product_release_reconciliation',
        'CREATE TABLE IF NOT EXISTS public.release_migration_exit_switch',
    ]
    for object_sql in required_objects:
        assert object_sql in EXPAND_SQL

    assert 'ALTER TABLE public.knowledge_base_v1' in EXPAND_SQL
    assert 'ALTER TABLE public.knowledge_base_modifications' in EXPAND_SQL
    assert 'ALTER TABLE public.product_matrix' in EXPAND_SQL
    assert 'ADD COLUMN IF NOT EXISTS association_status text' in EXPAND_SQL
    assert 'ALTER TABLE public.matrix_submit_operation' in EXPAND_SQL

    assert 'pending_version integer NOT NULL DEFAULT 1' in EXPAND_SQL
    assert 'migration_batch_id text NOT NULL DEFAULT' in EXPAND_SQL
    assert 'enabled boolean NOT NULL DEFAULT false' in EXPAND_SQL
    assert "('new_product_release', false, '')" in EXPAND_SQL
    assert 'enabled = false' in EXPAND_SQL


def test_contract_sql_is_idempotent_and_default_deny():
    assert 'DROP CONSTRAINT IF EXISTS' in CONTRACT_SQL
    assert 'ADD CONSTRAINT' in CONTRACT_SQL
    assert 'NOT VALID' in CONTRACT_SQL
    assert 'VALIDATE CONSTRAINT' in CONTRACT_SQL

    assert 'release_migration_exit_switch' in CONTRACT_SQL
    assert 'IS DISTINCT FROM false' in CONTRACT_SQL
    assert "enabled IN (true, false)" in CONTRACT_SQL

    assert 'migration_batch_id IS NULL OR migration_batch_id =' in CONTRACT_SQL
    assert 'reconciliation_status NOT IN (' in CONTRACT_SQL
    assert 'status NOT IN (' in CONTRACT_SQL

    assert 'WHERE release_status IS NULL' in CONTRACT_SQL
    assert 'WHERE kb_scope IS NULL' in CONTRACT_SQL
    assert 'WHERE record_scope IS NULL' in CONTRACT_SQL
    assert 'HAVING COUNT(*) > 1' in CONTRACT_SQL

    assert 'ALTER TABLE public.knowledge_base_v1' in CONTRACT_SQL
    assert 'ALTER TABLE public.knowledge_base_modifications' in CONTRACT_SQL
    assert 'ALTER TABLE public.product_matrix' in CONTRACT_SQL
    assert 'ALTER COLUMN association_status SET NOT NULL' in CONTRACT_SQL
    assert 'ALTER TABLE public.release_migration_exit_switch' in CONTRACT_SQL
    assert 'SET NOT NULL' in CONTRACT_SQL


def test_contract_sql_rejects_empty_enum_and_duplicate_defects():
    assert "OR release_status = ''" in CONTRACT_SQL
    assert "release_status NOT IN ('pending', 'approved', 'released', 'rejected')" in CONTRACT_SQL
    assert 'product_release_request contains duplicate rows' in CONTRACT_SQL
    assert 'product_release_model_binding contains duplicate rows' in CONTRACT_SQL
    assert 'release_migration_exit_switch must remain false until an explicit approval step' in CONTRACT_SQL
