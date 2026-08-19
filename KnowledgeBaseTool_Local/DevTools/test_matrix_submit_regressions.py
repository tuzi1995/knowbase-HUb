import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


_TEMP_DIR = None
if not os.environ.get("KMATRIX_SQLITE_PATH"):
    _TEMP_DIR = tempfile.TemporaryDirectory()
    os.environ["KMATRIX_SQLITE_PATH"] = os.path.join(_TEMP_DIR.name, "matrix-submit-regressions.db")

import server  # noqa: E402


class MatrixSubmitRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.app.config.update(TESTING=True)
        server.init_db()

    @classmethod
    def tearDownClass(cls):
        with server.app.app_context():
            server.db.session.remove()

    def setUp(self):
        with server.app.app_context():
            server.Button.query.delete()
            server.MatrixSubmitOperation.query.delete()
            server.MatrixCloneReviewItem.query.delete()
            server.MatrixCloneDifferenceRule.query.delete()
            server.MatrixCloneReviewBatch.query.delete()
            server.ProductMatrix.query.delete()
            server.MatrixColumn.query.delete()
            server.db.session.add_all([
                server.MatrixColumn(product_name="P30 Pro", sort_order=1),
                server.MatrixColumn(product_name="G30S Ultra", sort_order=2),
                server.ProductMatrix(
                    question_wiki_id="KB-1",
                    product_name="P30 Pro",
                    is_configured=True,
                    manual_edit=True,
                    edit_source="submitted",
                    question_content="测试问题",
                    answer_content="测试答案",
                ),
                server.ProductMatrix(
                    question_wiki_id="KB-1",
                    product_name="G30S Ultra",
                    is_configured=True,
                    manual_edit=True,
                    edit_source="bulk",
                    question_content="测试问题",
                    answer_content="测试答案",
                ),
            ])
            server.db.session.commit()

        self.client = server.app.test_client()
        login = self.client.post("/login", json={"username": "admin", "password": "123456"})
        self.assertEqual(login.status_code, 200)

    def test_snapshot_uses_complete_matrix_state_when_remote_base_is_stale(self):
        changes = [{
            "question_wiki_id": "KB-1",
            "product_name": "G30S Ultra",
            "old_is_configured": False,
            "new_is_configured": True,
            "edit_source": "bulk",
        }]
        base_map = {
            "KB-1": {
                "question_wiki_id": "KB-1",
                "question": "测试问题",
                "answer": "测试答案",
                "product_name": "P20 Ultra",
            }
        }

        with server.app.app_context():
            snapshot = server._build_matrix_submit_snapshot_map(changes, base_map)["KB-1"]

        before_products = set(server._split_product_names(snapshot["before"]["products"]))
        after_products = set(server._split_product_names(snapshot["after"]["products"]))
        self.assertIn("P30 Pro", before_products)
        self.assertNotIn("G30S Ultra", before_products)
        self.assertIn("P30 Pro", after_products)
        self.assertIn("G30S Ultra", after_products)

    def test_successful_submit_leaves_manual_difference_but_clears_pending_state(self):
        payload = {
            "operation_id": "submit-regression-1",
            "attempt": 1,
            "changes": [{
                "question_wiki_id": "KB-1",
                "product_name": "G30S Ultra",
                "old_is_configured": False,
                "new_is_configured": True,
                "edit_source": "bulk",
            }],
        }

        with patch.object(server, "_maybe_pull_matrix_and_logs_from_supabase", return_value=None), patch.object(
            server, "is_supabase_button_sync_enabled", return_value=False
        ), patch.object(server, "is_supabase_matrix_enabled", return_value=False), patch.object(
            server, "get_supabase_client", return_value=None
        ), patch.object(
            server, "_fetch_kb_products_map", return_value=({"KB-1": {"P30 Pro"}}, True)
        ):
            submitted = self.client.post("/api/matrix/submit_changes", json=payload)
            mismatch = self.client.post("/api/matrix/mismatch_changes", json={"wiki_ids": ["KB-1"]})

        self.assertEqual(submitted.status_code, 200, submitted.get_data(as_text=True))
        self.assertEqual(mismatch.status_code, 200, mismatch.get_data(as_text=True))
        self.assertEqual(mismatch.get_json()["count"], 0)

        with server.app.app_context():
            row = server.ProductMatrix.query.filter_by(
                question_wiki_id="KB-1", product_name="G30S Ultra"
            ).one()
            self.assertTrue(row.manual_edit)
            self.assertEqual(row.edit_source, "submitted")

    def test_editing_a_submitted_cell_makes_it_pending_again(self):
        with patch.object(server, "_maybe_pull_matrix_and_logs_from_supabase", return_value=None), patch.object(
            server, "is_supabase_matrix_enabled", return_value=False
        ), patch.object(
            server, "_fetch_kb_products_map", return_value=({"KB-1": {"P30 Pro"}}, True)
        ):
            updated = self.client.post("/api/matrix/update", json={
                "question_wiki_id": "KB-1",
                "product_name": "G30S Ultra",
                "is_configured": True,
            })
            mismatch = self.client.post("/api/matrix/mismatch_changes", json={"wiki_ids": ["KB-1"]})

        self.assertEqual(updated.status_code, 200, updated.get_data(as_text=True))
        self.assertEqual(mismatch.status_code, 200, mismatch.get_data(as_text=True))
        self.assertEqual(mismatch.get_json()["count"], 1)
        self.assertEqual(mismatch.get_json()["changes"][0]["edit_source"], "cell")

    def test_cell_edit_does_not_write_authoritative_matrix_before_submit(self):
        with patch.object(server, "_maybe_pull_matrix_and_logs_from_supabase", return_value=None), patch.object(
            server, "is_supabase_matrix_enabled", return_value=True
        ), patch.object(server, "get_supabase_client") as get_client:
            updated = self.client.post("/api/matrix/update", json={
                "question_wiki_id": "KB-1",
                "product_name": "G30S Ultra",
                "is_configured": False,
            })

        self.assertEqual(updated.status_code, 200, updated.get_data(as_text=True))
        get_client.assert_not_called()

    def test_batch_edit_does_not_write_authoritative_matrix_before_submit(self):
        with patch.object(server, "_maybe_pull_matrix_and_logs_from_supabase", return_value=None), patch.object(
            server, "is_supabase_matrix_enabled", return_value=True
        ), patch.object(server, "get_supabase_client") as get_client:
            updated = self.client.post("/api/matrix/batch_update", json={
                "question_wiki_ids": ["KB-1"],
                "product_name": "G30S Ultra",
                "is_configured": False,
            })

        self.assertEqual(updated.status_code, 200, updated.get_data(as_text=True))
        get_client.assert_not_called()

    def test_blocked_clone_review_does_not_call_unified_writer(self):
        payload = {
            "operation_id": "blocked-before-unified-write",
            "changes": [{
                "question_wiki_id": "KB-1",
                "product_name": "G30S Ultra",
                "old_is_configured": False,
                "new_is_configured": True,
                "edit_source": "bulk",
            }],
        }

        with patch.object(server, "_active_clone_review_batches_for_changes", return_value=[
            SimpleNamespace(batch_id="blocked-batch")
        ]), patch.object(server, "is_supabase_matrix_enabled", return_value=True), patch.object(
            server, "get_supabase_client", side_effect=AssertionError("unified writer must not run")
        ):
            response = self.client.post("/api/matrix/submit_changes", json=payload)

        self.assertEqual(response.status_code, 409, response.get_data(as_text=True))
        self.assertEqual(response.get_json()["code"], "clone_review_required")

    def test_local_postgresql_rpc_commits_function_writes(self):
        client = object.__new__(server.LocalPostgreSQLClient)
        client.connection = SimpleNamespace(commit=MagicMock())

        with patch.object(client, "_execute_query", return_value=[{"success": True}]), patch.object(
            server, "_assert_external_write_allowed", return_value=None
        ):
            response = client.rpc("public.submit_matrix_changes_unified", {
                "p_operation_id": "rpc-commit-regression",
                "p_actor": "admin",
                "p_source_code": "product_matrix",
                "p_changes": [],
            })

        self.assertEqual(response.status_code, 200)
        client.connection.commit.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
