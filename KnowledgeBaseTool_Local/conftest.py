"""Global pytest safety boundary for KnowBaseHub tests."""

import hashlib
import os
from pathlib import Path
import shutil
import tempfile

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent
INSTANCE_DIR = (PROJECT_ROOT / "instance").resolve()
PRODUCTION_DB = INSTANCE_DIR / "data.db"
LIVE_TEST_FILES = {
    "test_category_filter.py",
    "test_change_meta_fix.py",
    "test_fetch_limit.py",
    "test_governance_api.py",
    "test_import.py",
    "test_insert_modification.py",
    "test_jsonb_insert.py",
    "test_kb_tags_api.py",
    "test_matrix_modification_record.py",
    "test_matrix_submit_changes.py",
    "test_modification_api.py",
    "test_modification_record.py",
    "test_product_delete_cleanup.py",
    "test_supabase_select.py",
    "test_sync_endpoint.py",
}
LIVE_WRITE_TEST_FILES = {
    "test_change_meta_fix.py",
    "test_import.py",
    "test_insert_modification.py",
    "test_jsonb_insert.py",
    "test_matrix_modification_record.py",
    "test_matrix_submit_changes.py",
    "test_modification_api.py",
    "test_modification_record.py",
    "test_product_delete_cleanup.py",
    "test_sync_endpoint.py",
}


def _enabled(name):
    return str(os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _is_within(path, directory):
    try:
        return Path(path).resolve().is_relative_to(Path(directory).resolve())
    except (AttributeError, ValueError):
        path = Path(path).resolve()
        directory = Path(directory).resolve()
        return directory == path or directory in path.parents


_TEMP_ROOT = None
requested_db = str(os.environ.get("KMATRIX_SQLITE_PATH") or "").strip()
if requested_db:
    TEST_DB = Path(requested_db).expanduser().resolve()
    if _is_within(TEST_DB, INSTANCE_DIR):
        raise pytest.UsageError(
            "测试禁止使用 KnowledgeBaseTool_Local/instance 下的 SQLite；"
            "请移除 KMATRIX_SQLITE_PATH 或改为临时目录。"
        )
    if not _is_within(TEST_DB, Path(tempfile.gettempdir()).resolve()):
        raise pytest.UsageError(
            "测试只允许使用系统临时目录下的 SQLite；"
            "请移除 KMATRIX_SQLITE_PATH，让 pytest 自动创建隔离数据库。"
        )
else:
    _TEMP_ROOT = Path(tempfile.mkdtemp(prefix="kmatrix-pytest-"))
    TEST_DB = _TEMP_ROOT / "data.db"

TEST_DB.parent.mkdir(parents=True, exist_ok=True)
os.environ["KMATRIX_SQLITE_PATH"] = str(TEST_DB)
os.environ["KMATRIX_TESTING"] = "1"
# Keep legacy local fixtures using admin/123456 compatible with the isolated
# test database. Production startup never imports this pytest conftest.
os.environ.setdefault("KMATRIX_ADMIN_PASSWORD", "123456")


def _hash_file(path):
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _production_fingerprint():
    return {
        suffix: _hash_file(Path(str(PRODUCTION_DB) + suffix))
        for suffix in ("", "-wal", "-journal")
    }


_PRODUCTION_FINGERPRINT_BEFORE = _production_fingerprint()


def pytest_ignore_collect(collection_path, config):
    name = Path(str(collection_path)).name
    live_write_enabled = _enabled("KMATRIX_ALLOW_LIVE_WRITE_TESTS")
    if name in LIVE_WRITE_TEST_FILES and not live_write_enabled:
        return True
    if name in LIVE_TEST_FILES and not (_enabled("KMATRIX_ALLOW_LIVE_TESTS") or live_write_enabled):
        return True
    return False


def pytest_report_header(config):
    live_state = "enabled" if _enabled("KMATRIX_ALLOW_LIVE_TESTS") else "disabled"
    write_state = "enabled" if _enabled("KMATRIX_ALLOW_LIVE_WRITE_TESTS") else "blocked"
    return [
        f"KMatrix isolated SQLite: {TEST_DB}",
        f"KMatrix live tests: {live_state}",
        f"KMatrix live writes: {write_state}",
    ]


def pytest_sessionfinish(session, exitstatus):
    after = _production_fingerprint()
    if after != _PRODUCTION_FINGERPRINT_BEFORE:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        if reporter:
            reporter.write_sep("=", "正式 SQLite 在测试期间发生变化", red=True)
            reporter.write_line(f"before={_PRODUCTION_FINGERPRINT_BEFORE}", red=True)
            reporter.write_line(f"after={after}", red=True)
    if _TEMP_ROOT:
        shutil.rmtree(_TEMP_ROOT, ignore_errors=True)
