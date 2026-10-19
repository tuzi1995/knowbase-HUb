from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / 'KnowledgeBaseTool_Local' / '🗄️ 数据库' / 'SQL脚本'


def test_matrix_submit_functions_write_record_source():
    for filename in (
        '20260817_unified_write_contract.sql',
        '20260911_preserve_kb_products_on_matrix_submit.sql',
    ):
        sql = (SQL_DIR / filename).read_text(encoding='utf-8')
        assert 'record_source' in sql
        assert 'record_scope' in sql
        assert 'source_code, source_module, record_scope, record_source' in sql
        assert 'source_code,\n            CASE source_code WHEN' in sql


def test_record_source_compatibility_migration_backfills_and_guards_old_writer():
    sql = (SQL_DIR / '20261009_fix_matrix_submit_record_source.sql').read_text(encoding='utf-8')
    assert 'ADD COLUMN IF NOT EXISTS record_source text' in sql
    assert 'ALTER COLUMN record_source SET NOT NULL' in sql
    assert 'ALTER COLUMN record_scope SET NOT NULL' in sql
    assert 'populate_kb_modification_record_source' in sql
    assert 'BEFORE INSERT OR UPDATE OF record_source, source_code, source_module' in sql
