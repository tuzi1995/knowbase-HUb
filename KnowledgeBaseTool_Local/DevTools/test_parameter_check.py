import json
import unittest
import sys
from pathlib import Path
from unittest.mock import Mock, patch

from flask import Flask

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from parameter_check import (
    DEFAULT_CATALOG_BASE_URL,
    assess_ai_candidate_against_snapshot,
    _ai_numeric_parameter_prompt,
    _feature_scan_status,
    build_confirmed_model_scope,
    build_model_mapping_candidates,
    compare_proposed_numeric_claims,
    extract_ai_numeric_parameter_claims,
    extract_numeric_parameter_claims,
    get_parameter_check_overview,
    _knowledge_revision,
    _read_proposed_numeric_claims,
    normalize_model_name,
    register_parameter_check_routes,
    run_historical_ai_feature_scan_worker,
    select_ai_candidate_source_rows,
)


class ParameterCatalogEndpointTests(unittest.TestCase):
    def test_default_catalog_url_targets_the_backend_service(self):
        self.assertEqual(DEFAULT_CATALOG_BASE_URL, "http://127.0.0.1:18510")


class _OverviewCursor:
    def __init__(self):
        self.queries = []
        self._fetchall_results = [
            [{
                "run_id": "run-1",
                "run_type": "parameter_check",
                "snapshot_id": "snapshot-1",
                "scope_json": {"stage": "numeric_comparison"},
                "status": "completed",
                "result_counts_json": {},
                "created_by": "test",
                "created_at": None,
                "completed_at": None,
            }],
            [{"result_status": "consistent", "count": 1}],
            [{"resolution_status": "unreviewed", "count": 1}],
            [{"model_id": "model-1", "feature_id": "height"}],
            [],
        ]
        self._fetchone_results = [
            {
                "snapshot_id": "snapshot-1",
                "source_version": "v1",
                "content_hash": "hash",
                "synced_at": None,
                "content_json": {
                    "models": [],
                    "features": [
                        {"id": "suction", "name": "最大吸力"},
                        {"id": "height", "name": "机身高度"},
                        {"id": "obstacle", "name": "越障高度"},
                        {"id": "clean-water", "name": "清水箱容量"},
                        {"id": "dirty-water", "name": "污水箱容量"},
                        {"id": "battery", "name": "电池容量"},
                        {"id": "dust-box", "name": "尘盒容量"},
                        {"id": "dust-bag", "name": "尘袋容量"},
                        {"id": "solution-box", "name": "清洁液盒容量"},
                    ],
                },
            },
            {"count": 1},
        ]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, query, params=None):
        self.queries.append(" ".join(str(query).split()))

    def fetchall(self):
        return self._fetchall_results.pop(0)

    def fetchone(self):
        return self._fetchone_results.pop(0)


class _OverviewConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self, **_kwargs):
        return self._cursor


class _CurrentClaimCursor:
    def __init__(self):
        current_question = "最大吸力是多少？"
        current_answer = "最大吸力为5500Pa。"
        self.queries = []
        self._fetchall_results = [
            [
                {
                    "claim_id": "claim-current",
                    "question_wiki_id": "ICWIKI-CURRENT",
                    "feature_id": "suction",
                    "asserted_value": "5500Pa",
                    "normalized_value": "5500pa",
                    "evidence_text": current_answer,
                    "kb_revision": _knowledge_revision(current_question, current_answer),
                    "question": current_question,
                    "answer": current_answer,
                },
                {
                    "claim_id": "claim-stale",
                    "question_wiki_id": "ICWIKI-STALE",
                    "feature_id": "suction",
                    "asserted_value": "5400Pa",
                    "normalized_value": "5400pa",
                    "evidence_text": "最大吸力为5400Pa。",
                    "kb_revision": "sha256:stale",
                    "question": "最大吸力是多少？",
                    "answer": current_answer,
                },
            ],
            [{"model_id": "model-1"}],
        ]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, query, params=None):
        self.queries.append(" ".join(str(query).split()))

    def fetchall(self):
        return self._fetchall_results.pop(0)


class _CurrentClaimConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self, **_kwargs):
        return self._cursor


class _QueueOverviewCursor:
    def __init__(self):
        self.queries = []
        self._fetchall_results = [
            [{
                "run_id": "run-feature-1",
                "run_type": "historical",
                "snapshot_id": "snapshot-feature-1",
                "scope_json": {
                    "stage": "ai_feature_extraction",
                    "category_name": "扫地机",
                    "feature_id": "height",
                    "feature_name": "机身高度",
                },
                "status": "running",
                "result_counts_json": {"processed_knowledge_count": 10, "total_eligible_knowledge_count": 20},
                "created_by": "test",
                "created_at": None,
                "completed_at": None,
            }],
            [{"model_id": "model-a", "feature_id": "height"}],
            [{"review_status": "unreviewed", "count": 1}],
            [{
                "claim_id": "00000000-0000-4000-8000-000000000001",
                "question_wiki_id": "ICWIKI-Q",
                "kb_revision": _knowledge_revision("机身高度是多少？", "机身高度为7.98cm。"),
                "feature_id": "height",
                "asserted_value": "7.98cm",
                "normalized_value": "79.8mm",
                "evidence_text": "机身高度为7.98cm。",
                "knowledge_question": "机身高度是多少？",
                "knowledge_answer": "机身高度为7.98cm。",
                "binding_status": "proposed",
                "created_at": None,
                "ai_verdict": "likely_consistent",
                "ai_reason_code": "value_match",
                "ai_reason": "数值一致",
                "comparison_verdict": "consistent",
                "comparison_reason": "快照一致",
                "comparison_values_json": [{"model_id": "model-a", "canonical_value": "79.8mm", "result_status": "consistent"}],
                "review_status": "unreviewed",
                "final_verdict": None,
                "review_reason": None,
                "reviewed_by": None,
                "reviewed_at": None,
                "source_run_id": "run-feature-1",
                "source_snapshot_id": "snapshot-feature-1",
                "source_scope_json": {"feature_name": "机身高度", "ai_model": "model-x"},
                "source_run_status": "running",
                "source_snapshot_content": {
                    "models": [{"id": "model-a", "model_name": "来源型号"}],
                    "features": [{"id": "height", "name": "机身高度"}],
                },
                "model_ids": ["model-a"],
            }],
        ]
        self._fetchone_results = [
            {
                "snapshot_id": "snapshot-current",
                "source_version": "v2",
                "content_hash": "hash-current",
                "synced_at": None,
                "content_json": {
                    "models": [{"id": "model-current", "model_name": "当前型号"}],
                    "features": [{"id": "height", "name": "机身高度"}],
                },
            },
            {"count": 1},
            {"count": 1},
            {"count": 1},
        ]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, query, params=None):
        self.queries.append(" ".join(str(query).split()))

    def fetchall(self):
        return self._fetchall_results.pop(0)

    def fetchone(self):
        return self._fetchone_results.pop(0)


class ParameterCheckMappingTests(unittest.TestCase):
    def test_current_comparison_excludes_claims_for_older_kb_revisions(self):
        cursor = _CurrentClaimCursor()

        claims = _read_proposed_numeric_claims(_CurrentClaimConnection(cursor), "扫地机")

        self.assertEqual([claim["claim_id"] for claim in claims], ["claim-current"])
        self.assertEqual(claims[0]["model_ids"], ["model-1"])
        self.assertIn("JOIN knowledge_base_v1 AS knowledge", cursor.queries[0])

    def test_normalize_model_name_only_applies_controlled_whitespace_normalization(self):
        self.assertEqual(normalize_model_name(" P20 净立方 "), "p20净立方")
        self.assertEqual(normalize_model_name("P20净立方"), "p20净立方")

    def test_exact_matches_are_confirmed_and_normalized_matches_remain_pending(self):
        candidates = build_model_mapping_candidates(
            [
                {"source_name": "P20", "source_wiki_count": 20},
                {"source_name": "P20 净立方", "source_wiki_count": 10},
                {"source_name": "不存在", "source_wiki_count": 0},
            ],
            [
                {"id": "model-p20", "model_code": "P20", "model_name": "P20"},
                {"id": "model-cube", "model_code": "P20净立方", "model_name": "P20净立方"},
            ],
        )
        self.assertEqual(candidates[0]["mapping_type"], "exact")
        self.assertEqual(candidates[0]["status"], "confirmed")
        self.assertEqual(candidates[1]["mapping_type"], "normalized")
        self.assertEqual(candidates[1]["status"], "pending")
        self.assertEqual(candidates[2]["mapping_type"], "manual")
        self.assertEqual(candidates[2]["model_id"], "")

    def test_confirmed_scope_resolves_the_user_confirmed_whitespace_alias(self):
        scopes, summary = build_confirmed_model_scope(
            [
                {"question_wiki_id": "ICWIKI1", "product_name": "P20净立方"},
                {"question_wiki_id": "ICWIKI2", "product_name": "G10"},
                {"question_wiki_id": "ICWIKI3", "product_name": "未映射型号"},
            ],
            [
                {"source_name": "P20 净立方", "model_id": "cube", "status": "confirmed"},
                {"source_name": "G10", "model_id": "g10", "status": "confirmed"},
            ],
        )

        self.assertEqual(scopes["ICWIKI1"], {"cube"})
        self.assertEqual(scopes["ICWIKI2"], {"g10"})
        self.assertNotIn("ICWIKI3", scopes)
        self.assertEqual(summary["matched_matrix_row_count"], 2)

    def test_numeric_claim_extraction_requires_an_explicit_feature_and_one_value(self):
        snapshot = {
            "features": [
                {"id": "suction", "name": "最大吸力"},
                {"id": "height", "name": "机身高度"},
                {"id": "water", "name": "清水箱容量"},
            ]
        }
        claims = extract_numeric_parameter_claims(
            [
                {
                    "question_wiki_id": "ICWIKI1",
                    "question": "最大吸力是多少？",
                    "answer": "最大吸力可达5100帕。机身高度为7.98cm。",
                },
                {
                    "question_wiki_id": "ICWIKI2",
                    "question": "P20对比",
                    "answer": "最大吸力为22000Pa，P20 Pro最大吸力为18500Pa。",
                },
                {
                    "question_wiki_id": "ICWIKI3",
                    "question": "加水",
                    "answer": "清水箱容量4L。",
                },
                {
                    "question_wiki_id": "ICWIKI4",
                    "question": "能不能进入家具底部",
                    "answer": "如果家具高度低于机身高度可能无法进入，宽度低于38cm也可能无法进入。",
                },
            ],
            {"ICWIKI1": {"g10"}, "ICWIKI2": {"p20", "p20-pro"}, "ICWIKI3": {"p10"}, "ICWIKI4": {"g20"}},
            snapshot,
        )

        self.assertEqual(
            [(claim["question_wiki_id"], claim["feature_id"], claim["normalized_value"]) for claim in claims],
            [
                ("ICWIKI1", "suction", "5100pa"),
                ("ICWIKI1", "height", "79.8mm"),
                ("ICWIKI3", "water", "4000ml"),
            ],
        )
        self.assertTrue(all(claim["model_ids"] for claim in claims))

    def test_two_distinct_features_can_share_one_sentence_without_becoming_ambiguous(self):
        claims = extract_numeric_parameter_claims(
            [{"question_wiki_id": "ICWIKI4", "question": "水箱", "answer": "清水箱容量4L，污水箱容量3.5L。"}],
            {"ICWIKI4": {"g20s"}},
            {
                "features": [
                    {"id": "clean", "name": "清水箱容量"},
                    {"id": "dirty", "name": "污水箱容量"},
                ]
            },
        )

        self.assertEqual(
            [(claim["feature_id"], claim["normalized_value"]) for claim in claims],
            [("clean", "4000ml"), ("dirty", "3500ml")],
        )

    def test_expanded_numeric_rules_extract_only_explicit_parameter_values(self):
        claims = extract_numeric_parameter_claims(
            [{
                "question_wiki_id": "ICWIKI-EXPANDED",
                "question": "容量参数",
                "answer": "电池容量5200mAh，尘盒容量350ml，尘袋容量2.7L，清洁液盒容量580毫升。",
            }],
            {"ICWIKI-EXPANDED": {"model-a"}},
            {
                "features": [
                    {"id": "battery", "name": "电池容量"},
                    {"id": "dust-box", "name": "尘盒容量"},
                    {"id": "dust-bag", "name": "尘袋容量"},
                    {"id": "solution-box", "name": "清洁液盒容量"},
                ]
            },
        )

        self.assertEqual(
            [(claim["feature_id"], claim["normalized_value"]) for claim in claims],
            [
                ("battery", "5200mah"),
                ("dust-box", "350ml"),
                ("dust-bag", "2700ml"),
                ("solution-box", "580ml"),
            ],
        )

    def test_cleaning_solution_usage_amount_is_not_treated_as_box_capacity(self):
        claims = extract_numeric_parameter_claims(
            [{
                "question_wiki_id": "ICWIKI-SOLUTION-USAGE",
                "question": "添加多少清洁液",
                "answer": "建议向清洁液盒加入500ml清洁液。",
            }],
            {"ICWIKI-SOLUTION-USAGE": {"model-a"}},
            {"features": [{"id": "solution-box", "name": "清洁液盒容量"}]},
        )

        self.assertEqual(claims, [])

    def test_ai_candidates_require_source_evidence_and_keep_confirmed_model_scope(self):
        claims = extract_ai_numeric_parameter_claims(
            json.dumps({
                "candidates": [
                    {
                        "feature_id": "height",
                        "asserted_value": "7.98cm",
                        "evidence_text": "机身仅7.98cm，可以进入低矮空间。",
                    },
                    {
                        "feature_id": "water",
                        "asserted_value": "4L",
                        "evidence_text": "原文不存在的证据",
                    },
                    {
                        "feature_id": "outside-scope",
                        "asserted_value": "5500Pa",
                        "evidence_text": "最大吸力5500Pa。",
                    },
                ],
            }),
            {
                "question_wiki_id": "ICWIKI-AI-1",
                "question": "能否进入低矮空间？",
                "answer": "机身仅7.98cm，可以进入低矮空间。最大吸力5500Pa。",
            },
            {"g20s"},
            {
                "features": [
                    {"id": "height", "name": "机身高度"},
                    {"id": "water", "name": "清水箱容量"},
                ],
            },
        )

        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]["feature_id"], "height")
        self.assertEqual(claims[0]["normalized_value"], "79.8mm")
        self.assertEqual(claims[0]["model_ids"], ["g20s"])

    def test_ai_candidates_keep_a_supported_initial_judgment_and_fall_back_when_missing(self):
        claims = extract_ai_numeric_parameter_claims(
            json.dumps({
                "candidates": [
                    {
                        "feature_id": "height",
                        "asserted_value": "7.98cm",
                        "evidence_text": "机身仅7.98cm，可以进入低矮空间。",
                        "initial_verdict": "likely_consistent",
                        "reason_code": "value_match",
                        "reason": "与参数快照值一致。",
                    },
                    {
                        "feature_id": "height",
                        "asserted_value": "7.98cm",
                        "evidence_text": "机身仅7.98cm，可以进入低矮空间。",
                        "initial_verdict": "unsupported",
                        "reason_code": "unsupported",
                    },
                ],
            }),
            {
                "question_wiki_id": "ICWIKI-AI-2",
                "question": "能否进入低矮空间？",
                "answer": "机身仅7.98cm，可以进入低矮空间。",
            },
            {"g20s"},
            {"features": [{"id": "height", "name": "机身高度"}]},
        )

        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]["ai_verdict"], "likely_consistent")
        self.assertEqual(claims[0]["ai_reason_code"], "value_match")

    def test_snapshot_assessment_keeps_the_value_basis_separate_from_the_ai_judgment(self):
        assessment = assess_ai_candidate_against_snapshot(
            {
                "question_wiki_id": "ICWIKI-AI-3",
                "feature_id": "height",
                "asserted_value": "7.98cm",
                "normalized_value": "79.8mm",
                "evidence_text": "G20S Ultra 机身仅7.98cm。",
                "model_ids": ["g20s-ultra"],
            },
            {
                "models": [{"id": "g20s-ultra", "model_name": "G20S Ultra"}],
                "features": [{"id": "height", "name": "机身高度"}],
                "feature_values": [
                    {"model_id": "g20s-ultra", "feature_id": "height", "value_text": "79.8mm", "quality_status": "confirmed", "version": 4}
                ],
            },
        )

        self.assertEqual(assessment["comparison_verdict"], "consistent")
        self.assertEqual(assessment["comparison_values"][0]["model_name"], "G20S Ultra")
        self.assertEqual(assessment["comparison_values"][0]["canonical_value"], "79.8mm")

    def test_ai_source_selection_prefilters_and_prioritizes_numeric_parameter_text(self):
        rows, eligible_count, candidate_source_count, already_compared_count = select_ai_candidate_source_rows(
            [
                {"question_wiki_id": "ICWIKI-GENERIC", "question": "如何清洁？", "answer": "请定期维护设备。"},
                {"question_wiki_id": "ICWIKI-SEMANTIC", "question": "能进入低矮空间吗？", "answer": "机身仅 7.98cm，可以进入低矮空间。"},
                {"question_wiki_id": "ICWIKI-EXACT", "question": "最大吸力是多少？", "answer": "最大吸力为 5500Pa。"},
            ],
            set(),
            {
                "suction": {"id": "suction", "name": "最大吸力", "normalization": "pressure"},
                "height": {"id": "height", "name": "机身高度", "normalization": "length"},
            },
            batch_size=1,
        )

        self.assertEqual(candidate_source_count, 3)
        self.assertEqual(already_compared_count, 0)
        self.assertEqual(eligible_count, 2)
        self.assertEqual([row["question_wiki_id"] for row in rows], ["ICWIKI-EXACT"])

    def test_ai_source_selection_excludes_the_same_knowledge_revision_already_compared_by_rules(self):
        exact_row = {"question_wiki_id": "ICWIKI-EXACT", "question": "最大吸力是多少？", "answer": "最大吸力为 5500Pa。"}
        rows, eligible_count, candidate_source_count, already_compared_count = select_ai_candidate_source_rows(
            [
                {"question_wiki_id": "ICWIKI-GENERIC", "question": "如何清洁？", "answer": "请定期维护设备。"},
                {"question_wiki_id": "ICWIKI-SEMANTIC", "question": "能进入低矮空间吗？", "answer": "机身仅 7.98cm，可以进入低矮空间。"},
                exact_row,
            ],
            set(),
            {
                "suction": {"id": "suction", "name": "最大吸力", "normalization": "pressure"},
                "height": {"id": "height", "name": "机身高度", "normalization": "length"},
            },
            batch_size=10,
            compared_revisions={
                (exact_row["question_wiki_id"], _knowledge_revision(exact_row["question"], exact_row["answer"]))
            },
        )

        self.assertEqual(candidate_source_count, 2)
        self.assertEqual(already_compared_count, 1)
        self.assertEqual(eligible_count, 1)
        self.assertEqual([row["question_wiki_id"] for row in rows], ["ICWIKI-SEMANTIC"])

    def test_feature_scan_keeps_prompt_and_validation_inside_the_selected_function(self):
        snapshot = {
            "features": [
                {"id": "suction", "name": "最大吸力"},
                {"id": "height", "name": "机身高度"},
            ]
        }
        feature_rules = {"height": {"id": "height", "name": "机身高度", "normalization": "length"}}
        _system, user_prompt = _ai_numeric_parameter_prompt(
            {"question_wiki_id": "ICWIKI-F", "question": "高度", "answer": "机身高度为7.98cm，最大吸力为5500Pa。"},
            feature_rules,
            {"model-a"},
            snapshot,
        )
        self.assertEqual(json.loads(user_prompt)["allowed_features"], [{"feature_id": "height", "feature_name": "机身高度", "normalized_unit": "length"}])
        claims = extract_ai_numeric_parameter_claims(
            json.dumps({"candidates": [
                {"feature_id": "height", "asserted_value": "7.98cm", "evidence_text": "机身高度为7.98cm"},
                {"feature_id": "suction", "asserted_value": "5500Pa", "evidence_text": "最大吸力为5500Pa"},
            ]}),
            {"question_wiki_id": "ICWIKI-F", "question": "高度", "answer": "机身高度为7.98cm，最大吸力为5500Pa。"},
            {"model-a"},
            snapshot,
            allowed_feature_ids={"height"},
        )
        self.assertEqual([(claim["feature_id"], claim["normalized_value"]) for claim in claims], [("height", "79.8mm")])

    def test_feature_scan_allows_another_function_to_scan_the_same_knowledge_revision(self):
        row = {"question_wiki_id": "ICWIKI-SAME", "question": "参数", "answer": "最大吸力为5500Pa，机身高度为7.98cm。"}
        feature_rules = {
            "suction": {"id": "suction", "name": "最大吸力", "normalization": "pressure"},
            "height": {"id": "height", "name": "机身高度", "normalization": "length"},
        }
        revision = _knowledge_revision(row["question"], row["answer"])
        already_scanned_rows, *_ = select_ai_candidate_source_rows([row], {(row["question_wiki_id"], revision)}, {"suction": feature_rules["suction"]}, batch_size=10)
        other_feature_rows, *_ = select_ai_candidate_source_rows([row], set(), {"height": feature_rules["height"]}, batch_size=10)
        self.assertEqual(already_scanned_rows, [])
        self.assertEqual([item["question_wiki_id"] for item in other_feature_rows], ["ICWIKI-SAME"])

    def test_feature_scan_status_marks_partial_only_after_some_progress(self):
        self.assertEqual(_feature_scan_status(20, 0), "completed")
        self.assertEqual(_feature_scan_status(10, 1), "partial")
        self.assertEqual(_feature_scan_status(0, 1), "failed")

    def test_feature_scan_worker_accumulates_progress_and_marks_a_failed_segment_partial(self):
        job = {
            "run_id": "00000000-0000-4000-8000-000000000002",
            "category_name": "扫地机",
            "feature_id": "height",
            "chunk_size": 1,
            "snapshot": {"features": [{"id": "height", "name": "机身高度"}]},
            "feature_rules": {"height": {"id": "height", "name": "机身高度", "normalization": "length"}},
            "config": {"api_key": "key", "base_url": "http://example.test", "model": "test-model"},
            "scope_by_wiki": {"ICWIKI-1": {"model-a"}, "ICWIKI-2": {"model-a"}},
            "pending_rows": [
                {"question_wiki_id": "ICWIKI-1", "question": "高度", "answer": "机身高度为7.98cm。"},
                {"question_wiki_id": "ICWIKI-2", "question": "高度", "answer": "机身高度为7.98cm。"},
            ],
            "result_counts": {
                "total_eligible_knowledge_count": 2,
                "processed_knowledge_count": 0,
                "scanned_knowledge_count": 0,
                "candidate_count": 0,
                "proposed_claim_count": 0,
                "existing_proposed_claim_count": 0,
                "remaining_knowledge_count": 2,
                "failed_knowledge_count": 0,
                "failed_chunk_count": 0,
                "scan_status_counts": {},
            },
        }
        connections = [Mock() for _ in range(4)]
        with patch("parameter_check._call_ai_numeric_parameter_extraction", side_effect=['{"candidates": []}', RuntimeError("AI 暂不可用")]), patch(
            "parameter_check._write_ai_candidate_scan_rows",
            return_value={"scanned_knowledge_count": 1, "candidate_count": 0, "proposed_claim_count": 0, "existing_proposed_claim_count": 0, "scan_status_counts": {"no_candidate": 1}},
        ), patch("parameter_check.connect_main_database", side_effect=connections), patch(
            "parameter_check._update_feature_ai_scan_progress"
        ) as update_progress:
            run_historical_ai_feature_scan_worker(job)

        self.assertEqual(update_progress.call_count, 3)
        final = update_progress.call_args.kwargs
        self.assertEqual(final["status"], "partial")
        self.assertTrue(final["completed"])
        self.assertEqual(final["result_counts"]["processed_knowledge_count"], 1)
        self.assertEqual(final["result_counts"]["failed_chunk_count"], 1)

    def test_historical_run_routes_are_registered(self):
        app = Flask(__name__)
        register_parameter_check_routes(app, lambda view: view, lambda: {"扫地机": []})
        routes = {rule.rule for rule in app.url_map.iter_rules()}

        self.assertIn("/api/kb/parameter-check/runs", routes)
        self.assertIn("/api/kb/parameter-check/runs/<run_id>", routes)
        self.assertIn("/api/kb/parameter-check/overview", routes)
        self.assertIn("/api/kb/parameter-check/candidates/<claim_id>/review", routes)

    def test_ai_extract_route_uses_the_parameter_check_runner(self):
        app = Flask(__name__)
        register_parameter_check_routes(app, lambda view: view, lambda: {"扫地机": []})
        connection = Mock()
        expected = {"run_id": "run-ai", "snapshot_id": "snapshot-1", "result_counts": {"candidate_count": 1}}
        with patch("flask_login.utils._get_user", return_value=Mock(is_authenticated=False)), patch(
            "parameter_check.connect_main_database", return_value=connection
        ), patch("parameter_check.run_historical_ai_candidate_scan", return_value=expected) as run_ai:
            response = app.test_client().post(
                "/api/kb/parameter-check/runs",
                json={"mode": "ai_extract", "batch_size": 10},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])
        self.assertEqual(response.get_json()["run_id"], "run-ai")
        run_ai.assert_called_once_with(connection, category_name="扫地机", actor="system", batch_size=10)
        connection.close.assert_called_once()

    def test_refresh_compare_route_rebuilds_current_kb_claims_before_comparison(self):
        app = Flask(__name__)
        register_parameter_check_routes(app, lambda view: view, lambda: {"扫地机": []})
        connection = Mock()
        expected = {
            "run_id": "run-comparison",
            "snapshot_id": "snapshot-1",
            "result_counts": {"finding_count": 3},
            "scan_result": {"run_id": "run-extraction"},
        }
        with patch("flask_login.utils._get_user", return_value=Mock(is_authenticated=False)), patch(
            "parameter_check.connect_main_database", return_value=connection
        ), patch(
            "parameter_check.run_current_knowledge_parameter_comparison", return_value=expected
        ) as run_current:
            response = app.test_client().post(
                "/api/kb/parameter-check/runs",
                json={"mode": "refresh_compare"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["run_id"], "run-comparison")
        run_current.assert_called_once_with(connection, category_name="扫地机", actor="system")
        connection.close.assert_called_once()

    def test_feature_scan_route_returns_before_the_background_worker_runs(self):
        app = Flask(__name__)
        register_parameter_check_routes(app, lambda view: view, lambda: {"扫地机": []})
        connection = Mock()
        result = {
            "run_id": "run-feature",
            "snapshot_id": "snapshot-1",
            "feature_id": "height",
            "feature_name": "机身高度",
            "result_counts": {"total_eligible_knowledge_count": 120},
        }
        job = {"run_id": "run-feature", "feature_id": "height"}
        with patch("flask_login.utils._get_user", return_value=Mock(is_authenticated=False)), patch(
            "parameter_check.connect_main_database", return_value=connection
        ), patch("parameter_check.create_historical_ai_feature_scan", return_value=(result, job)) as create_scan, patch(
            "parameter_check.threading.Thread"
        ) as thread:
            response = app.test_client().post(
                "/api/kb/parameter-check/runs",
                json={"mode": "ai_feature_extract", "feature_id": "height"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["run_id"], "run-feature")
        create_scan.assert_called_once_with(connection, category_name="扫地机", feature_id="height", actor="system")
        thread.return_value.start.assert_called_once()
        connection.close.assert_called_once()

    def test_feature_scan_route_marks_run_failed_if_background_thread_cannot_start(self):
        app = Flask(__name__)
        register_parameter_check_routes(app, lambda view: view, lambda: {"扫地机": []})
        connection = Mock()
        recovery_connection = Mock()
        result = {
            "run_id": "run-feature",
            "snapshot_id": "snapshot-1",
            "feature_id": "height",
            "feature_name": "机身高度",
            "result_counts": {"total_eligible_knowledge_count": 120},
        }
        job = {"run_id": "run-feature", "feature_id": "height"}
        with patch("flask_login.utils._get_user", return_value=Mock(is_authenticated=False)), patch(
            "parameter_check.connect_main_database", side_effect=[connection, recovery_connection]
        ), patch("parameter_check.create_historical_ai_feature_scan", return_value=(result, job)), patch(
            "parameter_check.threading.Thread"
        ) as thread, patch("parameter_check._update_feature_ai_scan_progress") as update_progress:
            thread.return_value.start.side_effect = RuntimeError("thread unavailable")
            response = app.test_client().post(
                "/api/kb/parameter-check/runs",
                json={"mode": "ai_feature_extract", "feature_id": "height"},
            )

        self.assertEqual(response.status_code, 422)
        self.assertIn("已标记为失败", response.get_json()["message"])
        update_progress.assert_called_once()
        self.assertEqual(update_progress.call_args.kwargs["status"], "failed")
        self.assertTrue(update_progress.call_args.kwargs["completed"])
        self.assertIn("thread unavailable", update_progress.call_args.kwargs["result_counts"]["last_error"])
        recovery_connection.close.assert_called_once()

    def test_ai_candidate_review_route_delegates_to_the_review_service(self):
        app = Flask(__name__)
        register_parameter_check_routes(app, lambda view: view, lambda: {"扫地机": []})
        connection = Mock()
        claim_id = "00000000-0000-4000-8000-000000000001"
        expected = {"claim_id": claim_id, "review_status": "corrected", "final_verdict": "conflict"}
        with patch("flask_login.utils._get_user", return_value=Mock(is_authenticated=False)), patch(
            "parameter_check.connect_main_database", return_value=connection
        ), patch("parameter_check.decide_ai_candidate_review", return_value=expected) as decide:
            response = app.test_client().post(
                f"/api/kb/parameter-check/candidates/{claim_id}/review",
                json={"decision": "corrected", "final_verdict": "conflict", "review_reason": "人工复核后确认数值不同。"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["review"]["final_verdict"], "conflict")
        decide.assert_called_once_with(
            connection,
            claim_id=claim_id,
            decision="corrected",
            final_verdict="conflict",
            review_reason="人工复核后确认数值不同。",
            actor="system",
        )
        connection.close.assert_called_once()

    def test_overview_route_returns_read_only_dashboard_payload(self):
        app = Flask(__name__)
        register_parameter_check_routes(app, lambda view: view, lambda: {"扫地机": []})
        connection = Mock()
        overview = {
            "category_name": "扫地机",
            "snapshot": {"snapshot_id": "snapshot-1"},
            "runs": [{"run_id": "run-1"}],
            "selected_run": {"run_id": "run-1"},
            "summary": {"finding_count": 1},
            "filter_options": {"models": [], "features": []},
            "findings": [],
            "pagination": {"page": 1, "page_size": 50, "total": 0},
        }
        with patch("parameter_check.connect_main_database", return_value=connection), patch(
            "parameter_check.get_parameter_check_overview", return_value=overview
        ) as get_overview:
            response = app.test_client().get("/api/kb/parameter-check/overview?page=1&page_size=50")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])
        self.assertEqual(response.get_json()["selected_run"]["run_id"], "run-1")
        get_overview.assert_called_once_with(
            connection,
            category_name="扫地机",
            run_id=None,
            result_status=None,
            resolution_status=None,
            model_id=None,
            feature_id=None,
            wiki_id=None,
            ai_view="comparison",
            page=1,
            page_size=50,
        )
        connection.close.assert_called_once()

    def test_overview_route_rejects_invalid_result_status_without_querying_database(self):
        app = Flask(__name__)
        register_parameter_check_routes(app, lambda view: view, lambda: {"扫地机": []})
        with patch("parameter_check.connect_main_database") as connect:
            response = app.test_client().get("/api/kb/parameter-check/overview?result_status=unknown")

        self.assertEqual(response.status_code, 422)
        self.assertIn("比较状态不合法", response.get_json()["message"])
        connect.assert_not_called()

    def test_overview_feature_filter_qualifies_finding_columns_after_claim_join(self):
        cursor = _OverviewCursor()
        overview = get_parameter_check_overview(
            _OverviewConnection(cursor),
            category_name="扫地机",
            feature_id="height",
            ai_view="candidates",
        )

        queries = "\n".join(cursor.queries)
        self.assertEqual(overview["pagination"]["total"], 1)
        self.assertEqual(len(overview["scan_feature_options"]), 9)
        self.assertEqual(
            {item["name"] for item in overview["scan_feature_options"]},
            {"最大吸力", "机身高度", "越障高度", "清水箱容量", "污水箱容量", "电池容量", "尘盒容量", "尘袋容量", "清洁液盒容量"},
        )
        self.assertIn(
            "FROM parameter_check_finding AS finding WHERE finding.run_id = %s AND finding.feature_id = %s",
            queries,
        )
        self.assertIn(
            "LEFT JOIN kb_parameter_claim AS claim ON claim.claim_id = finding.claim_id LEFT JOIN knowledge_base_v1 AS knowledge ON knowledge.question_wiki_id = finding.question_wiki_id WHERE finding.run_id = %s AND finding.feature_id = %s",
            queries,
        )
        self.assertNotIn("WHERE finding.finding.", queries)

    def test_full_review_queue_aggregates_ai_runs_and_uses_each_source_snapshot(self):
        cursor = _QueueOverviewCursor()
        overview = get_parameter_check_overview(
            _OverviewConnection(cursor),
            category_name="扫地机",
            ai_view="queue",
        )

        self.assertEqual(overview["view_mode"], "ai_candidate_queue")
        self.assertIsNone(overview["selected_run"])
        self.assertEqual(overview["summary"]["running_scan_count"], 1)
        self.assertEqual(overview["summary"]["ai_snapshot_agree_count"], 1)
        self.assertEqual(overview["candidates"][0]["model_names"], ["来源型号"])
        self.assertEqual(overview["candidates"][0]["source_feature_name"], "机身高度")
        self.assertEqual(overview["candidates"][0]["knowledge_content"]["answer"], "机身高度为7.98cm。")
        self.assertTrue(overview["candidates"][0]["knowledge_content"]["revision_matches_claim"])
        queries = "\n".join(cursor.queries)
        self.assertIn("source_run.scope_json ->> 'stage' IN ('ai_candidate_extraction', 'ai_feature_extraction')", queries)
        self.assertIn("LEFT JOIN knowledge_base_v1 AS knowledge ON knowledge.question_wiki_id = claim.question_wiki_id", queries)

    def test_numeric_comparison_records_consistent_conflict_and_missing_data_separately(self):
        findings = compare_proposed_numeric_claims(
            [
                {
                    "claim_id": "claim-1",
                    "question_wiki_id": "ICWIKI1",
                    "feature_id": "suction",
                    "asserted_value": "5100帕",
                    "normalized_value": "5100pa",
                    "model_ids": ["model-a"],
                },
                {
                    "claim_id": "claim-2",
                    "question_wiki_id": "ICWIKI2",
                    "feature_id": "water",
                    "asserted_value": "3.5L",
                    "normalized_value": "3500ml",
                    "model_ids": ["model-b"],
                },
                {
                    "claim_id": "claim-3",
                    "question_wiki_id": "ICWIKI3",
                    "feature_id": "obstacle",
                    "asserted_value": "2cm",
                    "normalized_value": "20mm",
                    "model_ids": ["model-c"],
                },
            ],
            {
                "features": [
                    {"id": "suction", "name": "最大吸力"},
                    {"id": "water", "name": "清水箱容量"},
                    {"id": "obstacle", "name": "越障高度"},
                ],
                "feature_values": [
                    {"model_id": "model-a", "feature_id": "suction", "value_text": "5100Pa", "quality_status": "confirmed", "version": 2},
                    {"model_id": "model-b", "feature_id": "water", "value_text": "3L", "quality_status": "confirmed", "version": 3},
                    {"model_id": "model-c", "feature_id": "obstacle", "value_text": "双层门槛4cm，日常越障3cm", "quality_status": "confirmed", "version": 1},
                ],
            },
        )

        self.assertEqual([finding["result_status"] for finding in findings], ["consistent", "conflict", "needs_parameter_data"])
        self.assertEqual([finding["severity"] for finding in findings], ["info", "error", "warning"])
        self.assertEqual(findings[0]["feature_value_version"], 2)

    def test_numeric_comparison_uses_a_unique_nearby_model_name_to_narrow_matrix_scope(self):
        findings = compare_proposed_numeric_claims(
            [{
                "claim_id": "claim-height",
                "question_wiki_id": "ICWIKI4",
                "feature_id": "height",
                "asserted_value": "7.98cm",
                "normalized_value": "79.8mm",
                "evidence_text": "机身高度G20S Ultra更轻薄，仅7.98cm，也是市面主流扫地机最薄的。",
                "model_ids": ["g20s", "g20s-ultra"],
            }],
            {
                "models": [
                    {"id": "g20s", "model_name": "G20S"},
                    {"id": "g20s-ultra", "model_name": "G20S Ultra"},
                ],
                "features": [{"id": "height", "name": "机身高度"}],
                "feature_values": [
                    {"model_id": "g20s", "feature_id": "height", "value_text": "机身高度为103mm", "quality_status": "confirmed", "version": 1},
                    {"model_id": "g20s-ultra", "feature_id": "height", "value_text": "机身高度为79.8mm", "quality_status": "confirmed", "version": 1},
                ],
            },
        )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["model_id"], "g20s-ultra")
        self.assertEqual(findings[0]["result_status"], "consistent")
        self.assertIn("缩小本次比较范围", findings[0]["reason"])


if __name__ == "__main__":
    unittest.main()
