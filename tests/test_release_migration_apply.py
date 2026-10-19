import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / 'KnowledgeBaseTool_Local' / 'release_migration_apply.py'
SPEC = importlib.util.spec_from_file_location('release_migration_apply', MODULE_PATH)
release_migration_apply = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_migration_apply)


def test_digest_is_stable_and_order_independent():
    assert release_migration_apply.digest({'b', 'a'}) == release_migration_apply.digest({'a', 'b'})


def test_migration_uses_canonical_local_config_and_sql():
    assert release_migration_apply.CONFIG.name == 'supabase_config_local.json'
    assert release_migration_apply.EXPAND.name == '20260921_new_product_release_expand.sql'
    assert release_migration_apply.CONFIG.is_file()
    assert release_migration_apply.EXPAND.is_file()
