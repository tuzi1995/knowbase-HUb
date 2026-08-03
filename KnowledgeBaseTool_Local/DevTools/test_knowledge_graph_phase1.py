import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import sys

from flask import Flask
from flask_login import LoginManager

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knowledge_graph import (
    GraphStore,
    apply_sqlite_schema,
    backup_sqlite_database,
    compare_scopes,
    connect_sqlite,
    derive_candidate_relations,
    derive_candidate_relation,
    graph_schema_status,
    migrate_sqlite_relation_schema,
    product_catalog_snapshot,
    rollback_sqlite_relation_schema,
    rollback_sqlite_revision_schema,
    rollback_sqlite_schema,
    register_knowledge_graph_routes,
)


def claims(conclusion, coverage_evidence="覆盖说明", **extra):
    return {"conclusion": conclusion, "coverage_evidence": coverage_evidence, **extra}


class KnowledgeGraphRulesTests(unittest.TestCase):
    catalog = {"扫地机": ["G10", "G20", "P20"], "洗地机": ["A10", "A20"]}

    def test_password_specific_knowledge_specializes_general_knowledge(self):
        result = derive_candidate_relation(
            {"topic": "密码", "password_type": "锁屏密码", "product_models": ["G10"]},
            claims("按设备端步骤重置"),
            {"topic": "密码", "password_type": "*", "product_categories": ["扫地机"]},
            claims("按设备端步骤重置"),
            self.catalog,
        )
        self.assertEqual(result["relation_type"], "SPECIALIZES")

    def test_explicit_condition_becomes_exception_not_conflict(self):
        result = derive_candidate_relation(
            {
                "topic": "密码",
                "password_type": "锁屏密码",
                "product_models": ["G10"],
                "connection_state": "离线",
            },
            claims("联系售后离线重置", exception_condition="G10 离线时不能在 App 重置"),
            {"topic": "密码", "password_type": "锁屏密码", "product_categories": ["扫地机"]},
            claims("在 App 的设备设置中重置"),
            self.catalog,
        )
        self.assertEqual(result["relation_type"], "EXCEPTION_TO")

    def test_incompatible_conclusions_in_same_scope_conflict(self):
        scope = {"topic": "密码", "password_type": "账号密码", "scenario": "找回", "product_models": ["G10"]}
        result = derive_candidate_relation(
            scope,
            claims("无需身份验证", claim_key="requires_identity_verification", claim_value="no", mutually_exclusive=True),
            scope,
            claims("必须完成身份验证", claim_key="requires_identity_verification", claim_value="yes", mutually_exclusive=True),
            self.catalog,
        )
        self.assertEqual(result["relation_type"], "CONFLICTS_WITH")

    def test_compatible_partial_scopes_overlap(self):
        result = derive_candidate_relation(
            {"topic": "密码", "product_models": ["G10", "G20"]},
            claims("在 App 中处理"),
            {"topic": "密码", "product_models": ["G20", "P20"]},
            claims("在 App 中处理"),
            self.catalog,
        )
        self.assertEqual(result["relation_type"], "OVERLAPS_WITH")

    def test_equal_scope_and_conclusion_is_duplicate_candidate(self):
        scope = {"topic": "密码", "password_type": "支付密码", "product_models": ["G10"]}
        result = derive_candidate_relation(scope, claims("通过 App 修改"), scope, claims("通过 App 修改"), self.catalog)
        self.assertEqual(result["relation_type"], "DUPLICATES")

    def test_navigation_is_not_treated_as_answer_coverage(self):
        result = derive_candidate_relation(
            {"topic": "密码"},
            {"navigation_only": True, "conclusion": "跳转到密码分类页"},
            {"topic": "密码", "password_type": "锁屏密码", "product_models": ["G10"]},
            claims("在设备端重置"),
        )
        self.assertEqual(result["relation_type"], "ROUTES_TO")
        no_coverage = derive_candidate_relation(
            {"topic": "密码", "password_type": "锁屏密码"},
            claims("在设备端重置"),
            {"topic": "密码", "password_type": "*", "product_categories": ["扫地机"]},
            claims("在设备端重置", coverage_evidence=""),
            self.catalog,
        )
        self.assertIsNone(no_coverage["relation_type"])

    def test_scope_direction_is_explicit(self):
        self.assertEqual(
            compare_scopes({"topic": "密码", "product_scope": "G10"}, {"topic": "密码", "product_scope": ["G10", "G20"]}),
            "subset",
        )

    def test_empty_product_scope_is_unknown_not_all_models(self):
        self.assertEqual(
            compare_scopes(
                {"topic": "密码"},
                {"topic": "密码", "product_categories": ["扫地机"]},
                self.catalog,
            ),
            "unknown",
        )

    def test_product_categories_do_not_cross(self):
        self.assertEqual(
            compare_scopes(
                {"topic": "WiFi", "product_categories": ["扫地机"]},
                {"topic": "WiFi", "product_categories": ["洗地机"]},
                self.catalog,
            ),
            "disjoint",
        )

    def test_all_models_scope_is_bound_to_catalog_snapshot(self):
        result = derive_candidate_relation(
            {"topic": "WiFi", "product_models": ["G10"]},
            claims("支持 2.4G"),
            {"topic": "WiFi", "all_models_explicit": True},
            claims("支持 2.4G"),
            self.catalog,
        )
        self.assertEqual(result["relation_type"], "SPECIALIZES")
        self.assertEqual(
            result["scope_basis"]["to_scope"]["product_catalog_snapshot"]["content_hash"],
            product_catalog_snapshot(self.catalog)["content_hash"],
        )

    def test_different_intents_do_not_become_conflict_without_explicit_assertion(self):
        scope = {"topic": "主刷", "product_models": ["P20"]}
        result = derive_candidate_relation(
            scope,
            claims("主刷可以拆卸", intent="部件拆卸", component="主刷"),
            scope,
            claims("错误5需清理主刷", intent="故障处理", component="主刷"),
            self.catalog,
        )
        self.assertIsNone(result["relation_type"])

    def test_subprocedure_and_prerequisite_are_directional(self):
        scope = {"topic": "主刷", "product_models": ["P20"]}
        subprocedure = derive_candidate_relations(
            scope,
            claims("拆卸并清理主刷", intent="部件拆卸", component="主刷", procedure_steps=["取下主刷", "清理毛发", "装回主刷"]),
            {"topic": "主刷", "product_categories": ["扫地机"]},
            claims("解决错误5", intent="故障处理", component="主刷", procedure_steps=["取下主刷", "清理毛发", "装回主刷", "检查安装方向", "重启设备"]),
            self.catalog,
        )
        self.assertEqual([item["relation_type"] for item in subprocedure], ["SUBPROCEDURE_OF"])

        prerequisite = derive_candidate_relations(
            {"topic": "WiFi", "product_models": ["G10"]},
            claims("密码格式检查完成", outcome_keys=["wifi_credentials_valid"]),
            {"topic": "WiFi", "product_categories": ["扫地机"]},
            claims("重新配网", precondition_keys=["wifi_credentials_valid"]),
            self.catalog,
        )
        self.assertEqual([item["relation_type"] for item in prerequisite], ["PREREQUISITE_FOR"])

    def test_same_pair_can_have_content_and_workflow_relations(self):
        scope = {"topic": "WiFi", "product_models": ["G10"]}
        relations = derive_candidate_relations(
            scope,
            claims("检查 WiFi 密码", outcome_keys=["wifi_credentials_valid"]),
            scope,
            claims("检查 WiFi 密码", precondition_keys=["wifi_credentials_valid"]),
            self.catalog,
        )
        self.assertEqual(
            {item["relation_type"] for item in relations},
            {"DUPLICATES", "PREREQUISITE_FOR"},
        )


class KnowledgeGraphStoreTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.database = Path(self.tempdir.name) / "graph.db"
        self.connection = sqlite3.connect(self.database)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE kb_retrieval_index (
                library_type TEXT NOT NULL,
                question_wiki_id TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                question TEXT,
                answer TEXT,
                product_category_name TEXT,
                product_names_json TEXT,
                source_update_time TEXT,
                index_status TEXT NOT NULL
            );
            CREATE TABLE product_matrix (
                id INTEGER PRIMARY KEY,
                question_wiki_id TEXT NOT NULL,
                product_name TEXT NOT NULL,
                is_configured BOOLEAN NOT NULL,
                manual_edit BOOLEAN DEFAULT 0,
                edit_source TEXT DEFAULT '',
                update_time TEXT,
                product_category TEXT
            );
            """
        )
        self.connection.executemany(
            """
            INSERT INTO kb_retrieval_index VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ready')
            """,
            [
                ("knowledge_base_v1", "KB-GENERAL", "hash-general", "密码通用处理", "通用答案", "扫地机", '["G10","G20"]', "v1"),
                ("knowledge_base_v1", "KB-LOCK", "hash-lock", "锁屏密码处理", "锁屏答案", "扫地机", '["G10"]', "v2"),
            ],
        )
        self.connection.execute(
            """
            INSERT INTO product_matrix (question_wiki_id, product_name, is_configured, update_time, product_category)
            VALUES ('KB-GENERAL', 'G10', 1, 'v1', '扫地机')
            """
        )
        self.connection.commit()
        apply_sqlite_schema(self.connection)
        self.catalog = {"扫地机": ["G10", "G20"], "洗地机": ["A10"]}
        self.store = GraphStore(self.connection, product_catalog=self.catalog)

    def tearDown(self):
        self.connection.close()
        self.tempdir.cleanup()

    def _create_candidate(self):
        return self.store.create_candidate(
            "KB-LOCK",
            "KB-GENERAL",
            {"topic": "密码", "password_type": "锁屏密码", "product_models": ["G10"]},
            claims("按设备端步骤重置"),
            {"topic": "密码", "password_type": "*", "product_categories": ["扫地机"]},
            claims("按设备端步骤重置"),
            actor="tester",
        )

    def _create_conflict_candidate(self):
        return self.store.create_candidate(
            "KB-LOCK",
            "KB-GENERAL",
            {"topic": "密码", "product_models": ["G10"]},
            claims(
                "旧处理方式",
                claim_key="reset_mode",
                claim_value="legacy",
                mutually_exclusive=True,
            ),
            {"topic": "密码", "product_models": ["G10"]},
            claims("统一处理方式", claim_key="reset_mode", claim_value="unified"),
            actor="tester",
        )

    def test_candidate_review_and_events_are_append_only(self):
        created = self._create_candidate()
        self.assertTrue(created["created"])
        edge_id = created["edge"]["edge_id"]
        reviewed = self.store.review_edge(edge_id, "confirmed", "人工确认范围包含", "reviewer")
        self.assertEqual(reviewed["review_status"], "confirmed")
        event_rows = self.connection.execute(
            "SELECT event_type, actor FROM kg_edge_events WHERE edge_id = ? ORDER BY created_at", (edge_id,)
        ).fetchall()
        self.assertEqual([row["event_type"] for row in event_rows], ["candidate_created", "review_confirmed"])
        self.assertEqual(event_rows[-1]["actor"], "reviewer")
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM kb_retrieval_index").fetchone()[0], 2)

    def test_source_hash_change_expires_old_candidate(self):
        edge_id = self._create_candidate()["edge"]["edge_id"]
        self.connection.execute(
            "UPDATE kb_retrieval_index SET content_hash = 'hash-lock-new' WHERE question_wiki_id = 'KB-LOCK'"
        )
        self.connection.commit()
        self.assertEqual(self.store.expire_stale_candidates("KB-LOCK", "tester"), 1)
        status = self.connection.execute("SELECT review_status FROM kg_edges WHERE edge_id = ?", (edge_id,)).fetchone()[0]
        self.assertEqual(status, "expired")
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM kg_edge_events WHERE edge_id = ?", (edge_id,)).fetchone()[0],
            2,
        )

    def test_human_revision_preserves_original_and_becomes_effective(self):
        original_edge_id = self._create_candidate()["edge"]["edge_id"]
        result = self.store.revise_edge(
            original_edge_id,
            "EXCEPTION_TO",
            {"topic": "密码", "password_type": "锁屏密码", "product_models": ["G10"]},
            claims("离线时联系售后", exception_condition="设备离线"),
            {"topic": "密码", "password_type": "*", "product_categories": ["扫地机"]},
            claims("在 App 中重置"),
            "确认这是离线条件例外，不是普通细化。",
            "reviewer",
        )
        revised = result["edge"]
        self.assertEqual(revised["review_status"], "confirmed")
        self.assertEqual(revised["relation_type"], "EXCEPTION_TO")
        self.assertEqual(revised["generated_by"], "human")
        self.assertEqual(revised["revision_kind"], "human_adjustment")
        self.assertEqual(revised["revision_no"], 2)
        self.assertEqual(revised["supersedes_edge_id"], original_edge_id)
        original = self.connection.execute(
            "SELECT review_status, valid_to FROM kg_edges WHERE edge_id=?", (original_edge_id,)
        ).fetchone()
        self.assertEqual(original["review_status"], "expired")
        self.assertTrue(original["valid_to"])
        effective = self.store.list_edges(wiki_id="KB-LOCK", effective_only=True)
        self.assertEqual(effective["total"], 1)
        self.assertEqual(effective["items"][0]["edge_id"], revised["edge_id"])

    def test_answer_change_expires_relation_without_copying_old_type(self):
        original_edge_id = self._create_candidate()["edge"]["edge_id"]
        self.store.review_edge(original_edge_id, "confirmed", "首次确认", "reviewer")
        self.connection.execute(
            "UPDATE kb_retrieval_index SET content_hash='hash-lock-v3', answer='更新后的锁屏答案' WHERE question_wiki_id='KB-LOCK'"
        )
        self.connection.commit()
        refreshed = self.store.refresh_stale_relationships("KB-LOCK", "reviewer")
        self.assertEqual(refreshed["expired_count"], 1)
        self.assertEqual(refreshed["revalidation_candidate_count"], 0)
        self.assertEqual(refreshed["revalidated_without_relation_count"], 1)
        self.assertIsNone(self.connection.execute(
            "SELECT * FROM kg_edges WHERE supersedes_edge_id=?", (original_edge_id,)
        ).fetchone())
        self.assertTrue(self.connection.execute(
            "SELECT review_note FROM kg_edges WHERE edge_id=?", (original_edge_id,)
        ).fetchone()[0].startswith("重判结果："))
        self.assertEqual(self.store.list_edges(wiki_id="KB-LOCK", effective_only=True)["total"], 0)

    def test_source_change_can_reclassify_conflict_as_duplicate(self):
        original_edge_id = self._create_conflict_candidate()["edge"]["edge_id"]
        refreshed = self.store.refresh_stale_relationships(
            "KB-LOCK",
            "reviewer",
            source_override={
                "question_wiki_id": "KB-LOCK",
                "content_hash": "hash-lock-unified",
                "question": "锁屏密码处理",
                "answer": "统一处理方式",
                "product_category_name": "扫地机",
                "product_names": ["G10"],
                "source_update_time": "v3",
                "changed_fields": ["answer"],
            },
        )
        self.assertEqual(refreshed["expired_count"], 1)
        self.assertEqual(refreshed["revalidation_candidate_count"], 1)
        self.assertEqual(refreshed["relation_changed_count"], 1)
        child = self.connection.execute(
            "SELECT * FROM kg_edges WHERE supersedes_edge_id=?", (original_edge_id,)
        ).fetchone()
        self.assertEqual(child["relation_type"], "DUPLICATES")
        self.assertEqual(child["review_status"], "candidate")
        self.assertNotIn("沿用上一版本关系", json.loads(child["evidence_json"])["rule_reason"])

    def test_product_scope_change_removes_conflict_when_scopes_become_disjoint(self):
        original_edge_id = self._create_conflict_candidate()["edge"]["edge_id"]
        refreshed = self.store.refresh_stale_relationships(
            "KB-LOCK",
            "reviewer",
            source_override={
                "question_wiki_id": "KB-LOCK",
                "content_hash": "hash-lock-a10",
                "question": "锁屏密码处理",
                "answer": "锁屏答案",
                "product_category_name": "洗地机",
                "product_names": ["A10"],
                "source_update_time": "v3",
                "changed_fields": ["products"],
            },
        )
        self.assertEqual(refreshed["expired_count"], 1)
        self.assertEqual(refreshed["revalidation_candidate_count"], 0)
        self.assertEqual(refreshed["revalidated_without_relation_count"], 1)
        self.assertIsNone(self.connection.execute(
            "SELECT * FROM kg_edges WHERE supersedes_edge_id=?", (original_edge_id,)
        ).fetchone())
        node_scope = json.loads(self.connection.execute(
            "SELECT scope_json FROM kg_nodes WHERE business_key='KB-LOCK'"
        ).fetchone()[0])
        self.assertEqual(node_scope["product_models"], ["A10"])

    def test_question_only_change_rechecks_and_keeps_duplicate_candidate(self):
        created = self.store.create_candidate(
            "KB-LOCK",
            "KB-GENERAL",
            {"topic": "密码", "product_models": ["G10"]},
            claims("同一处理方式"),
            {"topic": "密码", "product_models": ["G10"]},
            claims("同一处理方式"),
            actor="tester",
        )
        refreshed = self.store.refresh_stale_relationships(
            "KB-LOCK",
            "reviewer",
            source_override={
                "question_wiki_id": "KB-LOCK",
                "content_hash": "hash-lock-title",
                "question": "忘记锁屏密码后如何处理",
                "answer": "锁屏答案",
                "product_category_name": "扫地机",
                "product_names": ["G10"],
                "source_update_time": "v3",
                "changed_fields": ["question"],
            },
        )
        self.assertEqual(refreshed["revalidation_candidate_count"], 1)
        child = self.connection.execute(
            "SELECT * FROM kg_edges WHERE supersedes_edge_id=?", (created["edge"]["edge_id"],)
        ).fetchone()
        self.assertEqual(child["relation_type"], "DUPLICATES")

    def test_source_override_updates_node_without_active_relationships(self):
        self.store.upsert_knowledge_node(
            "KB-LOCK",
            {"topic": "密码", "product_models": ["G10"]},
            claims("旧答案"),
            "tester",
        )
        refreshed = self.store.refresh_stale_relationships(
            "KB-LOCK",
            "reviewer",
            source_override={
                "question_wiki_id": "KB-LOCK",
                "content_hash": "hash-lock-standalone",
                "question": "新的锁屏密码问题",
                "answer": "新的锁屏密码答案",
                "product_category_name": "洗地机",
                "product_names": ["A10"],
                "source_update_time": "v3",
                "changed_fields": ["question", "answer", "products"],
            },
        )
        self.assertEqual(refreshed["expired_count"], 0)
        node = self.connection.execute(
            "SELECT * FROM kg_nodes WHERE business_key='KB-LOCK'"
        ).fetchone()
        self.assertEqual(node["canonical_name"], "新的锁屏密码问题")
        self.assertEqual(node["content_hash"], "hash-lock-standalone")
        self.assertEqual(json.loads(node["scope_json"])["product_models"], ["A10"])
        self.assertEqual(json.loads(node["claims_json"])["conclusion"], "新的锁屏密码答案")

    def test_revision_rollback_refuses_to_drop_history(self):
        original_edge_id = self._create_candidate()["edge"]["edge_id"]
        self.store.revise_edge(
            original_edge_id,
            "SPECIALIZES",
            {"topic": "密码", "product_models": ["G10"]},
            claims("按设备端步骤重置"),
            {"topic": "密码", "product_categories": ["扫地机"]},
            claims("按设备端步骤重置"),
            "保留细化关系并形成修订版本。",
            "reviewer",
        )
        with self.assertRaises(ValueError):
            rollback_sqlite_revision_schema(self.connection)

    def test_backfill_preview_and_apply_only_write_sidecar_tables(self):
        preview = self.store.backfill_preview()
        self.assertEqual(preview["source_knowledge_count"], 2)
        self.assertEqual(preview["source_matrix_edge_count"], 1)
        applied = self.store.apply_backfill("migration-test", batch_size=1)
        self.assertGreaterEqual(applied["created_nodes"], 2)
        self.assertEqual(applied["created_applies_to_edges"], 1)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM kb_retrieval_index").fetchone()[0], 2)

    def test_schema_rolls_back_without_touching_source_tables(self):
        rollback_sqlite_schema(self.connection)
        status = graph_schema_status(self.connection)
        self.assertFalse(status["ready"])
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM kb_retrieval_index").fetchone()[0], 2)

    def test_relation_constraint_migration_and_rollback_preserve_edges_and_events(self):
        rollback_result = rollback_sqlite_relation_schema(self.connection)
        self.assertFalse(rollback_result["relation_schema_ready"])
        edge_id = self._create_candidate()["edge"]["edge_id"]
        before = (
            self.connection.execute("SELECT COUNT(*) FROM kg_edges").fetchone()[0],
            self.connection.execute("SELECT COUNT(*) FROM kg_edge_events").fetchone()[0],
        )
        migrated = migrate_sqlite_relation_schema(self.connection)
        self.assertTrue(migrated["relation_schema_ready"])
        self.assertEqual(
            before,
            (
                self.connection.execute("SELECT COUNT(*) FROM kg_edges").fetchone()[0],
                self.connection.execute("SELECT COUNT(*) FROM kg_edge_events").fetchone()[0],
            ),
        )
        self.assertEqual(self.connection.execute("SELECT review_status FROM kg_edges WHERE edge_id=?", (edge_id,)).fetchone()[0], "candidate")
        rolled_back = rollback_sqlite_relation_schema(self.connection)
        self.assertFalse(rolled_back["relation_schema_ready"])

    def test_revision_schema_empty_rollback_and_migration_preserve_edges(self):
        edge_id = self._create_candidate()["edge"]["edge_id"]
        before_events = self.connection.execute("SELECT COUNT(*) FROM kg_edge_events").fetchone()[0]
        rolled_back = rollback_sqlite_revision_schema(self.connection)
        self.assertTrue(rolled_back["changed"])
        self.assertFalse(rolled_back["revision_schema_ready"])
        migrated = migrate_sqlite_relation_schema(self.connection)
        self.assertTrue(migrated["revision_schema_ready"])
        self.assertEqual(
            self.connection.execute("SELECT review_status FROM kg_edges WHERE edge_id=?", (edge_id,)).fetchone()[0],
            "candidate",
        )
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM kg_edge_events").fetchone()[0],
            before_events,
        )

    def test_backup_uses_sqlite_snapshot_and_refuses_overwrite(self):
        backup_path = Path(self.tempdir.name) / "graph-backup.db"
        self.assertEqual(backup_sqlite_database(self.database, backup_path), backup_path.resolve())
        backup_connection = connect_sqlite(backup_path)
        try:
            self.assertEqual(backup_connection.execute("SELECT COUNT(*) FROM kb_retrieval_index").fetchone()[0], 2)
            self.assertTrue(graph_schema_status(backup_connection)["ready"])
        finally:
            backup_connection.close()
        with self.assertRaises(ValueError):
            backup_sqlite_database(self.database, backup_path)


class KnowledgeGraphApiTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.database = Path(self.tempdir.name) / "api.db"
        self.catalog_path = Path(self.tempdir.name) / "product_catalog.json"
        self.catalog_path.write_text('{"扫地机":["G10","G20"]}', encoding="utf-8")
        connection = connect_sqlite(self.database)
        connection.executescript(
            """
            CREATE TABLE kb_retrieval_index (
                library_type TEXT NOT NULL, question_wiki_id TEXT NOT NULL,
                content_hash TEXT NOT NULL, question TEXT, answer TEXT,
                product_category_name TEXT, product_names_json TEXT,
                source_update_time TEXT, index_status TEXT NOT NULL
            );
            CREATE TABLE product_matrix (
                id INTEGER PRIMARY KEY, question_wiki_id TEXT, product_name TEXT,
                is_configured BOOLEAN, manual_edit BOOLEAN DEFAULT 0,
                edit_source TEXT DEFAULT '', update_time TEXT, product_category TEXT
            );
            INSERT INTO kb_retrieval_index VALUES
                ('knowledge_base_v1','KB-UPSTREAM','hash-up','检查密码','密码符合要求','扫地机','["G10"]','v1','ready'),
                ('knowledge_base_v1','KB-DOWNSTREAM','hash-down','重新配网','重新配网','扫地机','["G10"]','v1','ready'),
                ('knowledge_base_v1','KB-UNKNOWN','hash-unknown','未登记范围知识','待补产品范围','','[]','v1','ready');
            INSERT INTO product_matrix (question_wiki_id, product_name, product_category, is_configured) VALUES
                ('KB-UPSTREAM','G10','扫地机',1),
                ('KB-DOWNSTREAM','G10','扫地机',1);
            """
        )
        connection.commit()
        apply_sqlite_schema(connection)
        connection.close()
        app = Flask(__name__)
        app.config.update(TESTING=True, SECRET_KEY="test")
        login_manager = LoginManager(app)

        @login_manager.user_loader
        def load_user(_user_id):
            return None

        register_knowledge_graph_routes(app, lambda function: function, self.database, self.catalog_path)
        self.client = app.test_client()

    def tearDown(self):
        self.tempdir.cleanup()

    def test_api_creates_and_lists_multiple_candidate_relations(self):
        payload = {
            "from_wiki_id": "KB-UPSTREAM",
            "to_wiki_id": "KB-DOWNSTREAM",
            "from_scope": {"topic": "WiFi", "product_models": ["G10"]},
            "to_scope": {"topic": "WiFi", "product_models": ["G10"]},
            "from_claims": {
                "conclusion": "密码符合要求",
                "outcome_keys": ["wifi_credentials_valid"],
            },
            "to_claims": {
                "conclusion": "密码符合要求",
                "precondition_keys": ["wifi_credentials_valid"],
            },
        }
        response = self.client.post("/api/kb/graph/candidates", json=payload)
        self.assertEqual(response.status_code, 200)
        result = response.get_json()
        self.assertEqual(result["created_count"], 2)
        self.assertEqual(
            {edge["relation_type"] for edge in result["edges"]},
            {"DUPLICATES", "PREREQUISITE_FOR"},
        )
        listed = self.client.get("/api/kb/graph/edges?review_status=candidate").get_json()
        self.assertEqual(listed["total"], 2)
        summary = self.client.get("/api/kb/graph/summary").get_json()
        self.assertEqual(summary["product_catalog_snapshot"]["model_count"], 2)

        revision = self.client.post(
            f"/api/kb/graph/edges/{result['edges'][0]['edge_id']}/revise",
            json={
                "relation_type": "PREREQUISITE_FOR",
                "from_scope": payload["from_scope"],
                "to_scope": payload["to_scope"],
                "from_claims": payload["from_claims"],
                "to_claims": payload["to_claims"],
                "review_note": "人工确认密码检查是重新配网前置条件。",
            },
        )
        self.assertEqual(revision.status_code, 200)
        revised_edge = revision.get_json()["edge"]
        self.assertEqual(revised_edge["generated_by"], "human")
        self.assertEqual(revised_edge["review_status"], "confirmed")
        effective = self.client.get("/api/kb/graph/edges?wiki_id=KB-UPSTREAM&effective_only=true").get_json()
        self.assertEqual(effective["total"], 1)
        self.assertEqual(effective["items"][0]["edge_id"], revised_edge["edge_id"])

    def test_catalog_overview_and_topics_are_read_only_and_keep_unknown_scope_visible(self):
        connection = connect_sqlite(self.database)
        try:
            connection.execute(
                "UPDATE product_matrix SET product_category='扫地机,洗地机' WHERE question_wiki_id='KB-DOWNSTREAM'"
            )
            connection.commit()
        finally:
            connection.close()
        before_connection = connect_sqlite(self.database)
        try:
            before_index_count = before_connection.execute(
                "SELECT COUNT(*) FROM kb_retrieval_index"
            ).fetchone()[0]
        finally:
            before_connection.close()
        overview = self.client.get("/api/kb/graph/catalog/overview")
        self.assertEqual(overview.status_code, 200)
        items = {item["category"]: item for item in overview.get_json()["items"]}
        self.assertEqual(items["扫地机"]["knowledge_count"], 2)
        self.assertEqual(items["扫地机"]["product_relation_count"], 2)
        self.assertEqual(items["洗地机"]["knowledge_count"], 1)
        self.assertNotIn("扫地机,洗地机", items)
        self.assertEqual(items["范围未知"]["knowledge_count"], 1)
        self.assertEqual(items["范围未知"]["scope_unknown_count"], 1)
        self.assertIn("不写入", overview.get_json()["source_contract"]["write_scope"])

        attention = self.client.get(
            "/api/kb/graph/catalog/attention?category=%E6%89%AB%E5%9C%B0%E6%9C%BA&reason=topic_missing&page=1&page_size=1"
        )
        self.assertEqual(attention.status_code, 200)
        attention_result = attention.get_json()
        self.assertEqual(attention_result["total"], 2)
        self.assertEqual(len(attention_result["items"]), 1)
        self.assertEqual(attention_result["items"][0]["attention_reasons"], ["待归类"])
        self.assertIn("不推断", attention_result["source_contract"]["write_scope"])
        unknown_attention = self.client.get(
            "/api/kb/graph/catalog/attention?category=%E8%8C%83%E5%9B%B4%E6%9C%AA%E7%9F%A5&reason=scope_unknown"
        ).get_json()
        self.assertEqual(unknown_attention["total"], 1)
        self.assertEqual(unknown_attention["items"][0]["wiki_id"], "KB-UNKNOWN")
        wiki_attention = self.client.get(
            "/api/kb/graph/catalog/attention?wiki_id=KB-DOWNSTREAM&reason=topic_missing"
        ).get_json()
        self.assertEqual(wiki_attention["total"], 1)
        self.assertEqual(wiki_attention["items"][0]["wiki_id"], "KB-DOWNSTREAM")
        self.assertEqual(wiki_attention["wiki_id"], "KB-DOWNSTREAM")

        rejected_assignment = self.client.post(
            "/api/kb/graph/catalog/topic-assignments",
            json={
                "wiki_id": "KB-UPSTREAM", "topic_id": "ROBOT_NAVIGATION", "review_note": "人工核对问题和答案。",
                "confirmation_phrase": "错误确认词",
            },
        )
        self.assertEqual(rejected_assignment.status_code, 422)
        assigned = self.client.post(
            "/api/kb/graph/catalog/topic-assignments",
            json={
                "wiki_id": "KB-UPSTREAM", "topic_id": "ROBOT_NAVIGATION", "review_note": "人工核对问题和答案。",
                "confirmation_phrase": "确认主题校对",
            },
        )
        self.assertEqual(assigned.status_code, 200)
        self.assertEqual(assigned.get_json()["assignment"]["topic_id"], "ROBOT_NAVIGATION")
        self.assertEqual(assigned.get_json()["assignment"]["topic"], "地图、定位与避障")
        self.assertIn("不修改知识", assigned.get_json()["write_scope"])
        attention_after_assignment = self.client.get(
            "/api/kb/graph/catalog/attention?category=%E6%89%AB%E5%9C%B0%E6%9C%BA&reason=topic_missing"
        ).get_json()
        self.assertEqual(attention_after_assignment["total"], 1)
        assignment_connection = connect_sqlite(self.database)
        try:
            self.assertEqual(assignment_connection.execute("SELECT COUNT(*) FROM kg_topic_assignments").fetchone()[0], 1)
            self.assertEqual(assignment_connection.execute("SELECT COUNT(*) FROM kg_topic_assignment_events").fetchone()[0], 1)
            self.assertEqual(assignment_connection.execute("SELECT COUNT(*) FROM kg_nodes").fetchone()[0], 0)
            self.assertEqual(assignment_connection.execute("SELECT COUNT(*) FROM kb_retrieval_index").fetchone()[0], before_index_count)
        finally:
            assignment_connection.close()

        payload = {
            "from_wiki_id": "KB-UPSTREAM",
            "to_wiki_id": "KB-DOWNSTREAM",
            "from_scope": {"topic": "WiFi", "product_models": ["G10"]},
            "to_scope": {"topic": "WiFi", "product_models": ["G10"]},
            "from_claims": {"conclusion": "密码符合要求"},
            "to_claims": {"conclusion": "密码符合要求"},
        }
        self.assertEqual(self.client.post("/api/kb/graph/candidates", json=payload).status_code, 200)
        topics = self.client.get("/api/kb/graph/catalog/%E6%89%AB%E5%9C%B0%E6%9C%BA/topics?topic=WiFi").get_json()
        self.assertEqual(topics["knowledge_total"], 1)
        self.assertEqual({item["wiki_id"] for item in topics["knowledge_items"]}, {"KB-DOWNSTREAM"})
        after_connection = connect_sqlite(self.database)
        try:
            self.assertEqual(after_connection.execute("SELECT COUNT(*) FROM kb_retrieval_index").fetchone()[0], before_index_count)
            self.assertEqual(after_connection.execute("SELECT COUNT(*) FROM product_matrix").fetchone()[0], 2)
        finally:
            after_connection.close()

    def test_catalog_candidate_preview_is_read_only_and_excludes_unknown_scope(self):
        connection = connect_sqlite(self.database)
        try:
            store = GraphStore(connection, product_catalog_path=self.catalog_path)
            store.upsert_knowledge_node(
                "KB-UPSTREAM",
                {"topic": "WiFi", "product_models": ["G10"]},
                {"conclusion": "密码符合要求", "outcome_keys": ["wifi_credentials_valid"]},
                "tester",
            )
            store.upsert_knowledge_node(
                "KB-DOWNSTREAM",
                {"topic": "WiFi", "product_models": ["G10"]},
                {"conclusion": "密码符合要求", "precondition_keys": ["wifi_credentials_valid"]},
                "tester",
            )
            connection.commit()
            before = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("kb_retrieval_index", "product_matrix", "kg_nodes", "kg_edges", "kg_edge_events")
            }
        finally:
            connection.close()

        response = self.client.post(
            "/api/kb/graph/catalog/candidates/preview",
            json={"category": "扫地机", "topics": ["WiFi"], "max_pairs_per_topic": 20},
        )
        self.assertEqual(response.status_code, 200)
        result = response.get_json()
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["source_knowledge_count"], 2)
        self.assertEqual(result["candidate_count"], 2)
        self.assertEqual(
            {item["relation_type"] for item in result["candidate_items"]},
            {"DUPLICATES", "PREREQUISITE_FOR"},
        )
        self.assertIn("不写入", result["source_contract"]["write_scope"])

        after_connection = connect_sqlite(self.database)
        try:
            after = {
                table: after_connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in before
            }
        finally:
            after_connection.close()
        self.assertEqual(after, before)

    def test_manual_topic_assignment_returns_to_attention_when_source_hash_changes(self):
        assigned = self.client.post(
            "/api/kb/graph/catalog/topic-assignments",
            json={
                "wiki_id": "KB-UPSTREAM", "topic_id": "ROBOT_NAVIGATION", "review_note": "人工核对来源内容。",
                "confirmation_phrase": "确认主题校对",
            },
        )
        self.assertEqual(assigned.status_code, 200)
        connection = connect_sqlite(self.database)
        try:
            connection.execute(
                "UPDATE kb_retrieval_index SET content_hash='hash-updated' WHERE question_wiki_id='KB-UPSTREAM'"
            )
            connection.commit()
        finally:
            connection.close()
        stale = self.client.get(
            "/api/kb/graph/catalog/attention?reason=topic_stale&category=%E6%89%AB%E5%9C%B0%E6%9C%BA"
        ).get_json()
        self.assertEqual(stale["total"], 1)
        self.assertEqual(stale["items"][0]["wiki_id"], "KB-UPSTREAM")
        self.assertEqual(stale["items"][0]["attention_reasons"], ["主题待复核"])

    def test_controlled_topic_vocabulary_rejects_free_text_and_mismatched_category(self):
        vocabulary = self.client.get(
            "/api/kb/graph/catalog/topic-vocabulary?category=%E6%89%AB%E5%9C%B0%E6%9C%BA"
        )
        self.assertEqual(vocabulary.status_code, 200)
        topic_ids = {item["topic_id"] for item in vocabulary.get_json()["items"]}
        self.assertEqual(topic_ids, {"ROBOT_BASE_STATION", "ROBOT_NAVIGATION"})

        free_text = self.client.post(
            "/api/kb/graph/catalog/topic-assignments",
            json={
                "wiki_id": "KB-UPSTREAM", "topic": "WiFi", "review_note": "不应允许自由主题。",
                "confirmation_phrase": "确认主题校对",
            },
        )
        self.assertEqual(free_text.status_code, 422)
        mismatched = self.client.post(
            "/api/kb/graph/catalog/topic-assignments",
            json={
                "wiki_id": "KB-UPSTREAM", "topic_id": "WASHER_WASH_DRY", "review_note": "品类不匹配。",
                "confirmation_phrase": "确认主题校对",
            },
        )
        self.assertEqual(mismatched.status_code, 422)

        before = connect_sqlite(self.database)
        try:
            source_counts = {
                table: before.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("kb_retrieval_index", "product_matrix", "kg_nodes", "kg_edges")
            }
        finally:
            before.close()
        assigned = self.client.post(
            "/api/kb/graph/catalog/topic-assignments",
            json={
                "wiki_id": "KB-UPSTREAM", "topic_id": "ROBOT_NAVIGATION", "review_note": "人工确认是地图定位问题。",
                "confirmation_phrase": "确认主题校对",
            },
        )
        self.assertEqual(assigned.status_code, 200)
        after = connect_sqlite(self.database)
        try:
            self.assertEqual(
                source_counts,
                {table: after.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in source_counts},
            )
            self.assertEqual(after.execute("SELECT COUNT(*) FROM kg_topic_definitions").fetchone()[0], 6)
            self.assertEqual(after.execute("SELECT COUNT(*) FROM kg_topic_definition_events").fetchone()[0], 6)
            self.assertEqual(after.execute("SELECT current_topic_id FROM kg_topic_assignment_events").fetchone()[0], "ROBOT_NAVIGATION")
            after.execute("UPDATE kg_topic_definitions SET lifecycle='deprecated' WHERE topic_id='ROBOT_NAVIGATION'")
            after.commit()
        finally:
            after.close()
        stale = self.client.get(
            "/api/kb/graph/catalog/attention?reason=topic_vocabulary_stale&category=%E6%89%AB%E5%9C%B0%E6%9C%BA"
        ).get_json()
        self.assertEqual(stale["total"], 1)
        self.assertEqual(stale["items"][0]["attention_reasons"], ["词表待复核"])

    def test_catalog_candidate_batch_requires_confirmation_and_rolls_back_candidates(self):
        connection = connect_sqlite(self.database)
        try:
            store = GraphStore(connection, product_catalog_path=self.catalog_path)
            store.upsert_knowledge_node(
                "KB-UPSTREAM",
                {"topic": "WiFi", "product_models": ["G10"]},
                {"conclusion": "密码符合要求", "outcome_keys": ["wifi_credentials_valid"]},
                "tester",
            )
            store.upsert_knowledge_node(
                "KB-DOWNSTREAM",
                {"topic": "WiFi", "product_models": ["G10"]},
                {"conclusion": "密码符合要求", "precondition_keys": ["wifi_credentials_valid"]},
                "tester",
            )
            connection.commit()
            before = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("kb_retrieval_index", "product_matrix", "kg_nodes", "kg_edges", "kg_edge_events")
            }
        finally:
            connection.close()

        payload = {
            "category": "扫地机",
            "topics": ["WiFi"],
            "max_pairs_per_topic": 20,
        }
        rejected = self.client.post(
            "/api/kb/graph/catalog/candidate-batches",
            json={**payload, "confirmation_phrase": "错误确认词"},
        )
        self.assertEqual(rejected.status_code, 422)

        created = self.client.post(
            "/api/kb/graph/catalog/candidate-batches",
            json={**payload, "confirmation_phrase": "写入候选"},
        )
        self.assertEqual(created.status_code, 200)
        result = created.get_json()
        self.assertEqual(result["created_count"], 2)
        self.assertEqual(result["status"], "active")
        batch_id = result["batch_id"]

        detail = self.client.get(f"/api/kb/graph/catalog/candidate-batches/{batch_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(len(detail.get_json()["edges"]), 2)
        self.assertEqual(detail.get_json()["batch"]["source_snapshot"]["writeable_candidate_count"], 2)

        listed = self.client.get("/api/kb/graph/catalog/candidate-batches")
        self.assertEqual(listed.status_code, 200)
        batch = listed.get_json()["items"][0]
        self.assertEqual(batch["batch_id"], batch_id)
        self.assertEqual(batch["edge_count"], 2)
        self.assertEqual(batch["candidate_count"], 2)
        self.assertEqual(batch["reviewed_count"], 0)
        self.assertEqual(batch["cluster_count"], 2)

        after_create = connect_sqlite(self.database)
        try:
            self.assertEqual(after_create.execute("SELECT COUNT(*) FROM kb_retrieval_index").fetchone()[0], before["kb_retrieval_index"])
            self.assertEqual(after_create.execute("SELECT COUNT(*) FROM product_matrix").fetchone()[0], before["product_matrix"])
            self.assertEqual(after_create.execute("SELECT COUNT(*) FROM kg_nodes").fetchone()[0], before["kg_nodes"])
            self.assertEqual(after_create.execute("SELECT COUNT(*) FROM kg_edges").fetchone()[0], before["kg_edges"] + 2)
            self.assertEqual(after_create.execute("SELECT COUNT(*) FROM kg_edge_events").fetchone()[0], before["kg_edge_events"] + 2)
            self.assertEqual(after_create.execute("SELECT COUNT(*) FROM kg_review_batches").fetchone()[0], 1)
            self.assertEqual(after_create.execute("SELECT COUNT(*) FROM kg_review_batch_edges").fetchone()[0], 2)
        finally:
            after_create.close()

        rollback = self.client.post(
            f"/api/kb/graph/catalog/candidate-batches/{batch_id}/rollback",
            json={"confirmation_phrase": "回退候选批次", "note": "测试回退"},
        )
        self.assertEqual(rollback.status_code, 200)
        self.assertEqual(rollback.get_json()["expired_count"], 2)
        self.assertEqual(rollback.get_json()["status"], "rolled_back")

        after_rollback = connect_sqlite(self.database)
        try:
            statuses = {
                row[0] for row in after_rollback.execute("SELECT review_status FROM kg_edges").fetchall()
            }
            self.assertEqual(statuses, {"expired"})
            self.assertEqual(after_rollback.execute("SELECT COUNT(*) FROM kg_edge_events").fetchone()[0], before["kg_edge_events"] + 4)
            self.assertEqual(after_rollback.execute("SELECT status FROM kg_review_batches WHERE batch_id=?", (batch_id,)).fetchone()[0], "rolled_back")
        finally:
            after_rollback.close()


if __name__ == "__main__":
    unittest.main()
