import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server
import kb_v1_sync
import knowledge_graph
import parameter_check


class DatabaseIsolationTests(unittest.TestCase):
    def test_backup_root_honors_external_override(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"KMATRIX_BACKUP_ROOT": temp_dir}, clear=False):
                self.assertEqual(server._resolve_backup_root(), os.path.abspath(temp_dir))

    def test_test_process_rejects_instance_database(self):
        instance_db = Path(server._BASE_DIR) / "instance" / "data.db"
        with patch.dict(os.environ, {
            "KMATRIX_TESTING": "1",
            "KMATRIX_SQLITE_PATH": str(instance_db),
        }, clear=False):
            with self.assertRaisesRegex(RuntimeError, "测试进程禁止"):
                server._resolve_sqlite_database_path()

    def test_test_process_accepts_external_temporary_database(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            expected = Path(temp_dir) / "data.db"
            with patch.dict(os.environ, {
                "KMATRIX_TESTING": "1",
                "KMATRIX_SQLITE_PATH": str(expected),
            }, clear=False):
                self.assertEqual(server._resolve_sqlite_database_path(), str(expected))

    def test_test_process_rejects_non_temporary_database(self):
        outside_temp = Path(server._BASE_DIR).parent / "test-data.db"
        with patch.dict(os.environ, {
            "KMATRIX_TESTING": "1",
            "KMATRIX_SQLITE_PATH": str(outside_temp),
        }, clear=False):
            with self.assertRaisesRegex(RuntimeError, "只允许使用系统临时目录"):
                server._resolve_sqlite_database_path()

    def test_external_write_is_blocked_by_default_in_tests(self):
        with patch.dict(os.environ, {
            "KMATRIX_TESTING": "1",
            "KMATRIX_ALLOW_LIVE_WRITE_TESTS": "0",
        }, clear=False):
            with self.assertRaisesRegex(RuntimeError, "阻止真实外部写入"):
                server._assert_external_write_allowed("test operation")

    def test_external_write_requires_explicit_opt_in(self):
        with patch.dict(os.environ, {
            "KMATRIX_TESTING": "1",
            "KMATRIX_ALLOW_LIVE_WRITE_TESTS": "1",
        }, clear=False):
            server._assert_external_write_allowed("test operation")

    def test_local_postgresql_rpc_is_blocked_by_default(self):
        client = object.__new__(server.LocalPostgreSQLClient)
        with patch.dict(os.environ, {
            "KMATRIX_TESTING": "1",
            "KMATRIX_ALLOW_LIVE_WRITE_TESTS": "0",
        }, clear=False):
            with self.assertRaisesRegex(RuntimeError, "Local PostgreSQL rpc"):
                client.rpc("potentially_writable_function")

    def test_local_storage_upload_is_blocked_by_default(self):
        client = object.__new__(server.LocalPostgreSQLClient)
        with patch.dict(os.environ, {
            "KMATRIX_TESTING": "1",
            "KMATRIX_ALLOW_LIVE_WRITE_TESTS": "0",
        }, clear=False):
            with self.assertRaisesRegex(RuntimeError, "Local storage upload"):
                client.storage_upload("test", "object.txt", b"content")

    def test_lower_level_sqlite_adapters_reject_production_path(self):
        production_db = Path(server._BASE_DIR) / "instance" / "data.db"
        with patch.dict(os.environ, {"KMATRIX_TESTING": "1"}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "测试进程禁止"):
                knowledge_graph.connect_sqlite(production_db)
            with self.assertRaisesRegex(RuntimeError, "测试进程禁止"):
                kb_v1_sync._connect(str(production_db))

    def test_sync_artifacts_follow_isolated_database(self):
        self.assertTrue(server._is_temporary_path(server._KB_V1_SYNC_ARTIFACT_DIR))

    def test_parameter_database_is_read_only_in_tests(self):
        fake_connection = Mock()
        with patch.object(parameter_check, "_load_local_database_config", return_value={
            "host": "localhost", "port": 5432, "database": "test", "user": "test", "password": "test",
        }), patch.object(parameter_check.psycopg2, "connect", return_value=fake_connection):
            with patch.dict(os.environ, {
                "KMATRIX_TESTING": "1",
                "KMATRIX_ALLOW_LIVE_WRITE_TESTS": "0",
            }, clear=False):
                self.assertIs(parameter_check.connect_main_database(), fake_connection)
        fake_connection.set_session.assert_called_once_with(readonly=True)


if __name__ == "__main__":
    unittest.main()
