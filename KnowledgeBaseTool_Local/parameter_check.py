"""Read-only ParamAggregator snapshots and auditable 8085 model bindings."""

from __future__ import annotations

import json
import os
import re
import threading
import unicodedata
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
from pathlib import Path
from typing import Any

import psycopg2
import requests
from psycopg2.extras import Json, RealDictCursor
from scoring_logic import LLMScorer, load_ai_config


PARAMETER_CHECK_SCHEMA_VERSION = "20260724_02"
DEFAULT_CATALOG_BASE_URL = "http://127.0.0.1:18511"
HISTORICAL_NUMERIC_RULE_VERSION = "sweeper-numeric-v2"
HISTORICAL_COMPARE_RULE_VERSION = "sweeper-compare-v2"
HISTORICAL_AI_CANDIDATE_RULE_VERSION = "sweeper-ai-candidate-v2"
AI_CANDIDATE_BATCH_SIZE = 10
AI_CANDIDATE_BATCH_MAX = 20
AI_FEATURE_SCAN_CHUNK_SIZE = 10
MODEL_SCOPE_LOOKBACK_CHARS = 20
MODEL_SCOPE_LOOKAHEAD_CHARS = 48
AI_CANDIDATE_PREFILTER_VERSION = "ai-numeric-prefilter-v2"


# These rules deliberately require both an explicit feature name and a matching
# numeric unit. The ParamAggregator legacy import has not yet assigned units to
# its feature definitions, so the units live here for the initial read-only run.
NUMERIC_CLAIM_RULES = (
    {
        "feature_name": "最大吸力",
        "aliases": ("最大吸力",),
        "unit_pattern": r"(?:pa|帕)",
        "normalization": "pressure",
    },
    {
        "feature_name": "机身高度",
        "aliases": ("机身高度", "机器高度"),
        "unit_pattern": r"(?:mm|毫米|cm|厘米)",
        "normalization": "length",
        "relation_pattern": r"(?:为|约为|仅|是|[:：])",
    },
    {
        "feature_name": "越障高度",
        "aliases": ("越障高度", "最大越障高度"),
        "unit_pattern": r"(?:mm|毫米|cm|厘米)",
        "normalization": "length",
        "relation_pattern": r"(?:为|约为|仅|是|[:：])",
    },
    {
        "feature_name": "清水箱容量",
        "aliases": ("清水箱容量",),
        "unit_pattern": r"(?:ml|毫升|l|升)",
        "normalization": "capacity",
    },
    {
        "feature_name": "污水箱容量",
        "aliases": ("污水箱容量",),
        "unit_pattern": r"(?:ml|毫升|l|升)",
        "normalization": "capacity",
    },
    {
        "feature_name": "电池容量",
        "aliases": ("电池容量",),
        "unit_pattern": r"(?:mah|毫安时|毫安)",
        "normalization": "battery_capacity",
    },
    {
        "feature_name": "尘盒容量",
        "aliases": ("尘盒容量",),
        "unit_pattern": r"(?:ml|毫升|l|升)",
        "normalization": "capacity",
    },
    {
        "feature_name": "尘袋容量",
        "aliases": ("尘袋容量",),
        "unit_pattern": r"(?:ml|毫升|l|升)",
        "normalization": "capacity",
    },
    {
        "feature_name": "清洁液盒容量",
        "aliases": ("清洁液盒容量",),
        "unit_pattern": r"(?:ml|毫升|l|升)",
        "normalization": "capacity",
    },
)
AI_CANDIDATE_SEMANTIC_TERMS = {
    "最大吸力": ("吸力",),
    "机身高度": ("机身", "机器", "超薄"),
    "越障高度": ("越障", "门槛", "跨越"),
    "清水箱容量": ("清水箱", "净水箱"),
    "污水箱容量": ("污水箱",),
    "电池容量": ("电池", "续航"),
    "尘盒容量": ("尘盒",),
    "尘袋容量": ("尘袋", "集尘袋"),
    "清洁液盒容量": ("清洁液盒容量",),
}
NUMERIC_UNIT_PATTERNS = {
    "pressure": r"(?:pa|帕)",
    "length": r"(?:mm|毫米|cm|厘米)",
    "capacity": r"(?:ml|毫升|l|升)",
    "battery_capacity": r"(?:mah|毫安时|毫安)",
}

PARAMETER_CHECK_RESULT_STATUSES = {
    "consistent",
    "conflict",
    "scope_mismatch",
    "needs_parameter_data",
    "ambiguous_model",
    "ambiguous_feature",
    "not_parameter_claim",
    "check_unavailable",
}
PARAMETER_CHECK_RESOLUTION_STATUSES = {
    "unreviewed",
    "confirmed_issue",
    "false_positive",
    "resolved",
}
AI_INITIAL_VERDICTS = {
    "likely_consistent",
    "likely_inconsistent",
    "needs_human_review",
}
AI_INITIAL_REASON_CODES = {
    "value_match",
    "value_conflict",
    "model_scope_uncertain",
    "parameter_unavailable",
    "ambiguous_claim",
}
PARAMETER_CANDIDATE_REVIEW_STATUSES = {
    "unreviewed",
    "accepted",
    "corrected",
    "false_positive",
}
PARAMETER_AI_SCAN_STATUSES = {
    "candidate",
    "no_candidate",
    "validator_rejected",
}


_AI_FEATURE_SCAN_LOCK = threading.Lock()
_AI_FEATURE_SCAN_ACTIVE_SCOPES: set[tuple[str, str]] = set()


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS parameter_check_schema_migration (
        version TEXT PRIMARY KEY,
        applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS parameter_snapshot (
        snapshot_id TEXT PRIMARY KEY,
        source_system TEXT NOT NULL CHECK (source_system = 'param_aggregator'),
        source_version TEXT NOT NULL,
        category_ids_json JSONB NOT NULL,
        content_hash TEXT NOT NULL,
        content_json JSONB NOT NULL,
        sync_status TEXT NOT NULL CHECK (sync_status IN ('ready', 'partial', 'failed')),
        error_message TEXT,
        synced_at TIMESTAMPTZ NOT NULL,
        created_by TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS parameter_model_alias_binding (
        binding_id UUID PRIMARY KEY,
        source_name TEXT NOT NULL,
        source_category_name TEXT NOT NULL,
        category_id TEXT NOT NULL,
        model_id TEXT NOT NULL DEFAULT '',
        mapping_type TEXT NOT NULL CHECK (mapping_type IN ('exact', 'normalized', 'alias', 'series', 'manual')),
        status TEXT NOT NULL CHECK (status IN ('confirmed', 'pending', 'rejected')),
        rule_version TEXT NOT NULL,
        source_snapshot_id TEXT NOT NULL REFERENCES parameter_snapshot(snapshot_id),
        source_wiki_count INTEGER NOT NULL DEFAULT 0,
        evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        confirmed_by TEXT,
        confirmed_at TIMESTAMPTZ,
        resolution_note TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (source_name, category_id, model_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS kb_parameter_claim (
        claim_id UUID PRIMARY KEY,
        library_type TEXT NOT NULL,
        question_wiki_id TEXT NOT NULL,
        kb_revision TEXT NOT NULL,
        feature_id TEXT NOT NULL,
        asserted_value TEXT,
        normalized_value TEXT,
        evidence_text TEXT NOT NULL,
        extraction_method TEXT NOT NULL CHECK (extraction_method IN ('rule', 'ai_candidate', 'manual')),
        binding_status TEXT NOT NULL CHECK (binding_status IN ('proposed', 'confirmed', 'rejected')),
        confirmed_by TEXT,
        confirmed_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS kb_parameter_claim_model (
        claim_id UUID NOT NULL REFERENCES kb_parameter_claim(claim_id),
        model_id TEXT NOT NULL,
        scope_source TEXT NOT NULL CHECK (scope_source IN ('product_matrix', 'knowledge_text', 'manual')),
        scope_status TEXT NOT NULL CHECK (scope_status IN ('confirmed', 'pending', 'excluded')),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (claim_id, model_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS parameter_check_run (
        run_id UUID PRIMARY KEY,
        run_type TEXT NOT NULL CHECK (run_type IN ('historical', 'create_preview', 'edit_preview', 'import', 'change_impact')),
        snapshot_id TEXT REFERENCES parameter_snapshot(snapshot_id),
        scope_json JSONB NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'partial', 'failed', 'cancelled')),
        result_counts_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_by TEXT NOT NULL DEFAULT '',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        completed_at TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS parameter_check_finding (
        finding_id UUID PRIMARY KEY,
        run_id UUID NOT NULL REFERENCES parameter_check_run(run_id),
        question_wiki_id TEXT NOT NULL,
        claim_id UUID REFERENCES kb_parameter_claim(claim_id),
        model_id TEXT NOT NULL,
        feature_id TEXT NOT NULL,
        asserted_value TEXT,
        canonical_value TEXT,
        feature_value_version INTEGER,
        result_status TEXT NOT NULL CHECK (result_status IN ('consistent', 'conflict', 'scope_mismatch', 'needs_parameter_data', 'ambiguous_model', 'ambiguous_feature', 'not_parameter_claim', 'check_unavailable')),
        severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'error')),
        reason TEXT NOT NULL,
        resolution_status TEXT NOT NULL CHECK (resolution_status IN ('unreviewed', 'confirmed_issue', 'false_positive', 'resolved')),
        resolution_note TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS parameter_ai_scan_receipt (
        library_type TEXT NOT NULL,
        question_wiki_id TEXT NOT NULL,
        kb_revision TEXT NOT NULL,
        category_name TEXT NOT NULL,
        source_run_id UUID NOT NULL REFERENCES parameter_check_run(run_id),
        candidate_count INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (library_type, question_wiki_id, kb_revision, category_name)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_parameter_snapshot_synced_at ON parameter_snapshot (synced_at DESC)",
    "CREATE INDEX IF NOT EXISTS ix_parameter_model_binding_source ON parameter_model_alias_binding (source_category_name, source_name)",
    "CREATE INDEX IF NOT EXISTS ix_parameter_model_binding_status ON parameter_model_alias_binding (source_category_name, status)",
    "CREATE INDEX IF NOT EXISTS ix_kb_parameter_claim_wiki ON kb_parameter_claim (library_type, question_wiki_id)",
    "CREATE INDEX IF NOT EXISTS ix_parameter_check_run_status ON parameter_check_run (status, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS ix_parameter_check_finding_run ON parameter_check_finding (run_id, result_status, severity)",
    "ALTER TABLE kb_parameter_claim ADD COLUMN IF NOT EXISTS source_run_id UUID REFERENCES parameter_check_run(run_id)",
    "CREATE INDEX IF NOT EXISTS ix_kb_parameter_claim_source_run ON kb_parameter_claim (source_run_id)",
    "CREATE INDEX IF NOT EXISTS ix_parameter_ai_scan_receipt_category ON parameter_ai_scan_receipt (category_name, created_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS parameter_ai_scan_item (
        run_id UUID NOT NULL REFERENCES parameter_check_run(run_id),
        question_wiki_id TEXT NOT NULL,
        kb_revision TEXT NOT NULL,
        scan_status TEXT NOT NULL CHECK (scan_status IN ('candidate', 'no_candidate', 'validator_rejected')),
        raw_candidate_count INTEGER NOT NULL DEFAULT 0,
        valid_candidate_count INTEGER NOT NULL DEFAULT 0,
        validation_reason TEXT NOT NULL DEFAULT '',
        response_hash TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (run_id, question_wiki_id, kb_revision)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS parameter_ai_candidate_assessment (
        claim_id UUID PRIMARY KEY REFERENCES kb_parameter_claim(claim_id),
        ai_verdict TEXT NOT NULL CHECK (ai_verdict IN ('likely_consistent', 'likely_inconsistent', 'needs_human_review')),
        ai_reason_code TEXT NOT NULL CHECK (ai_reason_code IN ('value_match', 'value_conflict', 'model_scope_uncertain', 'parameter_unavailable', 'ambiguous_claim')),
        ai_reason TEXT NOT NULL DEFAULT '',
        comparison_verdict TEXT NOT NULL CHECK (comparison_verdict IN ('consistent', 'conflict', 'scope_mismatch', 'needs_parameter_data', 'ambiguous_model', 'ambiguous_feature', 'not_parameter_claim', 'check_unavailable')),
        comparison_reason TEXT NOT NULL DEFAULT '',
        comparison_values_json JSONB NOT NULL DEFAULT '[]'::jsonb,
        review_status TEXT NOT NULL DEFAULT 'unreviewed' CHECK (review_status IN ('unreviewed', 'accepted', 'corrected', 'false_positive')),
        final_verdict TEXT CHECK (final_verdict IN ('consistent', 'conflict', 'scope_mismatch', 'needs_parameter_data', 'ambiguous_model', 'ambiguous_feature', 'not_parameter_claim', 'check_unavailable')),
        review_reason TEXT,
        reviewed_by TEXT,
        reviewed_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_parameter_ai_scan_item_run ON parameter_ai_scan_item (run_id, scan_status, question_wiki_id)",
    "CREATE INDEX IF NOT EXISTS ix_parameter_ai_candidate_review_status ON parameter_ai_candidate_assessment (review_status, updated_at DESC)",
)


def normalize_model_name(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    return re.sub(r"\s+", "", text).casefold()


def build_model_mapping_candidates(
    source_models: list[dict[str, Any]],
    parameter_models: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_exact: dict[str, list[dict[str, Any]]] = {}
    by_normalized: dict[str, list[dict[str, Any]]] = {}
    for model in parameter_models:
        for value in (model.get("model_code"), model.get("model_name")):
            text = str(value or "").strip()
            if not text:
                continue
            by_exact.setdefault(text, []).append(model)
            by_normalized.setdefault(normalize_model_name(text), []).append(model)

    candidates: list[dict[str, Any]] = []
    for source in source_models:
        source_name = str(source.get("source_name") or "").strip()
        if not source_name:
            continue
        exact_matches = {item["id"]: item for item in by_exact.get(source_name, [])}
        normalized_matches = {item["id"]: item for item in by_normalized.get(normalize_model_name(source_name), [])}
        matches = exact_matches or normalized_matches
        if len(matches) == 1:
            target = next(iter(matches.values()))
            mapping_type = "exact" if exact_matches else "normalized"
            candidates.append({
                **source,
                "model_id": target["id"],
                "model_name": target["model_name"],
                "mapping_type": mapping_type,
                "status": "confirmed" if mapping_type == "exact" else "pending",
                "candidate_count": 1,
            })
            continue

        candidates.append({
            **source,
            "model_id": "",
            "model_name": "",
            "mapping_type": "manual",
            "status": "pending",
            "candidate_count": len(matches),
        })
    return candidates


def _config_path(value: str | None = None) -> Path:
    if value:
        return Path(value)
    base_dir = Path(__file__).resolve().parent
    external_path = base_dir.parent / "⚙️ 配置文件" / "supabase_config_local.json"
    local_path = base_dir / "supabase_config_local.json"
    return external_path if external_path.exists() else local_path


def _load_local_database_config(config_path: str | None = None) -> dict[str, Any]:
    config = json.loads(_config_path(config_path).read_text(encoding="utf-8"))
    local_db = config.get("local_db")
    if not isinstance(local_db, dict):
        raise RuntimeError("参数校对需要配置 8085 本地主库 PostgreSQL。")
    required = ("host", "port", "database", "user", "password")
    if any(not local_db.get(name) for name in required):
        raise RuntimeError("8085 本地主库配置不完整。")
    return local_db


def connect_main_database(config_path: str | None = None):
    config = _load_local_database_config(config_path)
    return psycopg2.connect(
        host=config["host"],
        port=config["port"],
        dbname=config["database"],
        user=config["user"],
        password=config["password"],
        connect_timeout=5,
    )


def apply_schema(connection) -> None:
    with connection.cursor() as cursor:
        for statement in SCHEMA_STATEMENTS:
            cursor.execute(statement)
        cursor.execute(
            "INSERT INTO parameter_check_schema_migration (version) VALUES (%s) ON CONFLICT (version) DO NOTHING",
            (PARAMETER_CHECK_SCHEMA_VERSION,),
        )
    connection.commit()


def fetch_catalog_snapshot(category_name: str, base_url: str | None = None) -> dict[str, Any]:
    root = (base_url or os.environ.get("PARAMETER_CATALOG_BASE_URL") or DEFAULT_CATALOG_BASE_URL).rstrip("/")
    categories_response = requests.get(f"{root}/api/v1/categories", timeout=10)
    categories_response.raise_for_status()
    categories = categories_response.json().get("categories") or []
    category = next((item for item in categories if item.get("name") == category_name), None)
    if not category:
        raise ValueError(f"参数清单中不存在品类：{category_name}")
    snapshot_response = requests.get(
        f"{root}/api/v1/catalog/snapshot",
        params={"category_id": category["id"]},
        timeout=20,
    )
    snapshot_response.raise_for_status()
    snapshot = snapshot_response.json()
    required = ("snapshot_id", "source_version", "content_hash", "categories", "models", "features", "feature_values")
    if any(name not in snapshot for name in required):
        raise ValueError("参数清单快照响应不完整。")
    if snapshot.get("source_system") != "param_aggregator":
        raise ValueError("参数清单快照来源不正确。")
    return snapshot


def store_snapshot(connection, snapshot: dict[str, Any], actor: str) -> None:
    categories = snapshot.get("categories") or []
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO parameter_snapshot (
                snapshot_id, source_system, source_version, category_ids_json,
                content_hash, content_json, sync_status, synced_at, created_by
            ) VALUES (%s, %s, %s, %s, %s, %s, 'ready', %s, %s)
            ON CONFLICT (snapshot_id) DO NOTHING
            """,
            (
                snapshot["snapshot_id"],
                snapshot["source_system"],
                snapshot["source_version"],
                Json([item.get("id") for item in categories]),
                snapshot["content_hash"],
                Json(snapshot),
                datetime.now(timezone.utc),
                actor,
            ),
        )
    connection.commit()


def _latest_snapshot(connection, category_name: str) -> dict[str, Any] | None:
    with connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT snapshot_id, content_json
            FROM parameter_snapshot
            WHERE sync_status = 'ready'
              AND content_json @> %s::jsonb
            ORDER BY synced_at DESC
            LIMIT 1
            """,
            (Json({"categories": [{"name": category_name}]}),),
        )
        return cursor.fetchone()


def _source_models(connection, category_name: str, catalog_models: list[str]) -> list[dict[str, Any]]:
    if not catalog_models:
        return []
    with connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT product_name AS source_name, COUNT(DISTINCT question_wiki_id) AS source_wiki_count
            FROM product_matrix
            WHERE product_name = ANY(%s)
            GROUP BY product_name
            """,
            (catalog_models,),
        )
        existing = {row["source_name"]: int(row["source_wiki_count"]) for row in cursor.fetchall()}
    return [
        {"source_name": model_name, "source_wiki_count": existing.get(model_name, 0)}
        for model_name in catalog_models
    ]


def refresh_model_bindings(
    connection,
    *,
    category_name: str,
    catalog_models: list[str],
    actor: str,
) -> dict[str, int]:
    snapshot_row = _latest_snapshot(connection, category_name)
    if not snapshot_row:
        raise ValueError(f"没有可用的 {category_name} 参数快照，请先同步快照。")
    snapshot = snapshot_row["content_json"]
    category = next(item for item in snapshot["categories"] if item.get("name") == category_name)
    candidates = build_model_mapping_candidates(
        _source_models(connection, category_name, catalog_models),
        snapshot["models"],
    )
    with connection.cursor() as cursor:
        for candidate in candidates:
            status = candidate["status"]
            cursor.execute(
                """
                INSERT INTO parameter_model_alias_binding (
                    binding_id, source_name, source_category_name, category_id, model_id,
                    mapping_type, status, rule_version, source_snapshot_id, source_wiki_count,
                    evidence_json, confirmed_by, confirmed_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_name, category_id, model_id) DO UPDATE SET
                    source_snapshot_id = EXCLUDED.source_snapshot_id,
                    source_wiki_count = EXCLUDED.source_wiki_count,
                    evidence_json = EXCLUDED.evidence_json,
                    updated_at = NOW()
                WHERE parameter_model_alias_binding.status = 'pending'
                """,
                (
                    str(uuid.uuid4()),
                    candidate["source_name"],
                    category_name,
                    category["id"],
                    candidate["model_id"],
                    candidate["mapping_type"],
                    status,
                    "model-mapping-v1",
                    snapshot_row["snapshot_id"],
                    candidate["source_wiki_count"],
                    Json({
                        "target_model_name": candidate["model_name"],
                        "candidate_count": candidate["candidate_count"],
                        "normalization": normalize_model_name(candidate["source_name"]),
                    }),
                    "system:exact-match" if status == "confirmed" else None,
                    datetime.now(timezone.utc) if status == "confirmed" else None,
                ),
            )
    connection.commit()
    return {
        "source_count": len(candidates),
        "exact_confirmed": sum(item["mapping_type"] == "exact" for item in candidates),
        "pending_normalized": sum(item["mapping_type"] == "normalized" for item in candidates),
        "pending_manual": sum(item["mapping_type"] == "manual" for item in candidates),
    }


def list_model_bindings(connection, category_name: str, status: str | None = None) -> list[dict[str, Any]]:
    clauses = ["source_category_name = %s"]
    params: list[Any] = [category_name]
    if status:
        clauses.append("status = %s")
        params.append(status)
    with connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            f"""
            SELECT binding_id, source_name, source_category_name, category_id, model_id,
                   mapping_type, status, rule_version, source_snapshot_id, source_wiki_count,
                   evidence_json, confirmed_by, confirmed_at, resolution_note, created_at, updated_at
            FROM parameter_model_alias_binding
            WHERE {' AND '.join(clauses)}
            ORDER BY source_name, model_id
            """,
            params,
        )
        return [dict(row) for row in cursor.fetchall()]


def decide_model_binding(connection, binding_id: str, status: str, actor: str, note: str) -> dict[str, Any] | None:
    if status not in {"confirmed", "rejected"}:
        raise ValueError("型号映射结论只能是 confirmed 或 rejected。")
    with connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
            UPDATE parameter_model_alias_binding
            SET status = %s, confirmed_by = %s, confirmed_at = NOW(),
                resolution_note = %s, updated_at = NOW()
            WHERE binding_id = %s
            RETURNING binding_id, source_name, model_id, mapping_type, status,
                      confirmed_by, confirmed_at, resolution_note
            """,
            (status, actor, note, binding_id),
        )
        row = cursor.fetchone()
    connection.commit()
    return dict(row) if row else None


def build_confirmed_model_scope(
    matrix_rows: list[dict[str, Any]],
    bindings: list[dict[str, Any]],
) -> tuple[dict[str, set[str]], dict[str, int]]:
    """Resolve matrix rows through confirmed bindings, including controlled aliases."""
    targets_by_name: dict[str, set[str]] = {}
    for binding in bindings:
        if binding.get("status") != "confirmed":
            continue
        source_name = normalize_model_name(str(binding.get("source_name") or ""))
        model_id = str(binding.get("model_id") or "").strip()
        if source_name and model_id:
            targets_by_name.setdefault(source_name, set()).add(model_id)

    scope_by_wiki: dict[str, set[str]] = {}
    matched_matrix_rows = 0
    for row in matrix_rows:
        wiki_id = str(row.get("question_wiki_id") or "").strip()
        source_name = normalize_model_name(str(row.get("product_name") or ""))
        targets = targets_by_name.get(source_name)
        if not wiki_id or not targets:
            continue
        scope_by_wiki.setdefault(wiki_id, set()).update(targets)
        matched_matrix_rows += 1
    return scope_by_wiki, {
        "confirmed_source_name_count": len(targets_by_name),
        "matched_matrix_row_count": matched_matrix_rows,
        "scoped_wiki_count": len(scope_by_wiki),
    }


def resolve_confirmed_model_scope(connection, category_name: str) -> tuple[dict[str, set[str]], dict[str, int]]:
    with connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT source_name, model_id, status
            FROM parameter_model_alias_binding
            WHERE source_category_name = %s AND status = 'confirmed'
            """,
            (category_name,),
        )
        bindings = [dict(row) for row in cursor.fetchall()]
        cursor.execute("SELECT DISTINCT question_wiki_id, product_name FROM product_matrix")
        matrix_rows = [dict(row) for row in cursor.fetchall()]
    return build_confirmed_model_scope(matrix_rows, bindings)


def _knowledge_revision(question: str, answer: str) -> str:
    content = json.dumps(
        {"question": question, "answer": answer},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def _parameter_check_knowledge_content(
    question: object,
    answer: object,
    claim_revision: object,
) -> dict[str, Any] | None:
    """Return the current KB source separately from the immutable candidate evidence."""
    question_text = str(question or "")
    answer_text = str(answer or "")
    if not question_text and not answer_text:
        return None
    revision = str(claim_revision or "")
    return {
        "question": question_text,
        "answer": answer_text,
        "revision_matches_claim": (
            _knowledge_revision(question_text, answer_text) == revision if revision else None
        ),
    }


def _normalize_numeric_value(raw_value: str, normalization: str) -> str | None:
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([^\d\s]+)\s*", raw_value, re.IGNORECASE)
    if not match:
        return None
    try:
        number = Decimal(match.group(1))
    except InvalidOperation:
        return None
    unit = match.group(2).casefold()
    if normalization == "pressure" and unit in {"pa", "帕"}:
        canonical_unit = "pa"
    elif normalization == "length" and unit in {"mm", "毫米"}:
        canonical_unit = "mm"
    elif normalization == "length" and unit in {"cm", "厘米"}:
        number *= 10
        canonical_unit = "mm"
    elif normalization == "capacity" and unit in {"ml", "毫升"}:
        canonical_unit = "ml"
    elif normalization == "capacity" and unit in {"l", "升"}:
        number *= 1000
        canonical_unit = "ml"
    elif normalization == "battery_capacity" and unit in {"mah", "毫安时", "毫安"}:
        canonical_unit = "mah"
    else:
        return None
    number_text = format(number.normalize(), "f")
    if "." in number_text:
        number_text = number_text.rstrip("0").rstrip(".")
    return f"{number_text}{canonical_unit}"


def _evidence_fragment(text: str, start: int, end: int) -> str:
    left = max(0, start - 80)
    right = min(len(text), end + 160)
    return re.sub(r"\s+", " ", text[left:right]).strip()


def _numeric_claim_matches(
    text: str,
    rule: dict[str, Any],
    other_feature_aliases: tuple[str, ...],
) -> list[tuple[str, str, str]]:
    feature_starts = sorted({
        match.start()
        for alias in rule["aliases"]
        for match in re.finditer(re.escape(alias), text, re.IGNORECASE)
    })
    if not feature_starts:
        return []
    feature_start = feature_starts[0]
    following_boundaries = [
        match.start()
        for alias in other_feature_aliases
        for match in re.finditer(re.escape(alias), text, re.IGNORECASE)
        if match.start() > feature_start
    ]
    feature_end = min(following_boundaries, default=len(text))
    feature_text = text[feature_start:feature_end]

    direct_matches: dict[tuple[str, str], tuple[str, int, int]] = {}
    number = r"\d+(?:\.\d+)?"
    for alias in rule["aliases"]:
        relation = str(rule.get("relation_pattern") or "")
        between = rf"[^。！？；;\n]{{0,32}}?{relation}\s*" if relation else r"[^。！？；;\n]{0,80}?"
        pattern = re.compile(
            rf"{re.escape(alias)}{between}(?P<value>{number}\s*{rule['unit_pattern']})",
            re.IGNORECASE,
        )
        for match in pattern.finditer(feature_text):
            asserted_value = match.group("value")
            normalized_value = _normalize_numeric_value(asserted_value, rule["normalization"])
            if normalized_value is None:
                continue
            direct_matches.setdefault(
                (asserted_value, normalized_value),
                (asserted_value, match.start(), match.end()),
            )
    if not direct_matches:
        return []

    all_values = {
        normalized_value
        for match in re.finditer(rf"(?P<value>{number}\s*{rule['unit_pattern']})", feature_text, re.IGNORECASE)
        if (normalized_value := _normalize_numeric_value(match.group("value"), rule["normalization"])) is not None
    }
    if len(all_values) != 1:
        return []
    asserted_value, normalized_value = next(iter(direct_matches))
    _, start, end = direct_matches[(asserted_value, normalized_value)]
    return [(
        asserted_value,
        normalized_value,
        _evidence_fragment(text, feature_start + start, feature_start + end),
    )]


def extract_numeric_parameter_claims(
    kb_rows: list[dict[str, Any]],
    scope_by_wiki: dict[str, set[str]],
    snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return only unambiguous numeric candidates; no comparison is performed here."""
    features_by_name: dict[str, list[dict[str, Any]]] = {}
    for feature in snapshot.get("features") or []:
        features_by_name.setdefault(str(feature.get("name") or ""), []).append(feature)

    active_rules = []
    for rule in NUMERIC_CLAIM_RULES:
        features = features_by_name.get(rule["feature_name"], [])
        if len(features) == 1:
            active_rules.append((rule, features[0]))

    claims: list[dict[str, Any]] = []
    for row in kb_rows:
        wiki_id = str(row.get("question_wiki_id") or "").strip()
        model_ids = sorted(scope_by_wiki.get(wiki_id) or [])
        if not wiki_id or not model_ids:
            continue
        question = str(row.get("question") or "")
        answer = str(row.get("answer") or "")
        kb_revision = _knowledge_revision(question, answer)
        for text in (question, answer):
            for rule, feature in active_rules:
                other_feature_aliases = tuple(
                    alias
                    for other_rule, _other_feature in active_rules
                    if other_rule["feature_name"] != rule["feature_name"]
                    for alias in other_rule["aliases"]
                )
                matches = _numeric_claim_matches(text, rule, other_feature_aliases)
                if len(matches) != 1:
                    continue
                asserted_value, normalized_value, evidence_text = matches[0]
                claims.append({
                    "library_type": "current",
                    "question_wiki_id": wiki_id,
                    "kb_revision": kb_revision,
                    "feature_id": feature["id"],
                    "feature_name": rule["feature_name"],
                    "asserted_value": asserted_value,
                    "normalized_value": normalized_value,
                    "evidence_text": evidence_text,
                    "model_ids": model_ids,
                })
    return claims


def _unique_normalized_numeric_value(value_text: str, normalization: str) -> str | None:
    unit_pattern = NUMERIC_UNIT_PATTERNS.get(normalization)
    if not unit_pattern:
        return None
    values = {
        normalized_value
        for match in re.finditer(rf"\d+(?:\.\d+)?\s*{unit_pattern}", value_text, re.IGNORECASE)
        if (normalized_value := _normalize_numeric_value(match.group(0), normalization)) is not None
    }
    return next(iter(values)) if len(values) == 1 else None


def _comparison_model_scope(claim: dict[str, Any], model_names: dict[str, str]) -> tuple[list[str], bool]:
    model_ids = sorted({str(model_id) for model_id in claim.get("model_ids") or [] if str(model_id)})
    if len(model_ids) < 2:
        return model_ids, False
    evidence_text = str(claim.get("evidence_text") or "")
    asserted_value = str(claim.get("asserted_value") or "")
    value_position = evidence_text.casefold().find(asserted_value.casefold())
    if value_position < 0:
        return model_ids, False
    nearby_text = evidence_text[
        max(0, value_position - MODEL_SCOPE_LOOKBACK_CHARS):value_position + len(asserted_value) + MODEL_SCOPE_LOOKAHEAD_CHARS
    ]
    matched_ids: list[str] = []
    occupied_spans: list[tuple[int, int]] = []
    for model_id in sorted(model_ids, key=lambda item: len(model_names.get(item, "")), reverse=True):
        model_name = model_names.get(model_id, "")
        if not model_name:
            continue
        for match in re.finditer(re.escape(model_name), nearby_text, re.IGNORECASE):
            span = match.span()
            if any(span[0] < end and start < span[1] for start, end in occupied_spans):
                continue
            occupied_spans.append(span)
            matched_ids.append(model_id)
            break
    return (matched_ids, True) if len(matched_ids) == 1 else (model_ids, False)


def compare_proposed_numeric_claims(
    claims: list[dict[str, Any]],
    snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    """Compare proposed numeric claims to one snapshot without changing claims or knowledge."""
    feature_names = {str(feature.get("id") or ""): str(feature.get("name") or "") for feature in snapshot.get("features") or []}
    model_names = {str(model.get("id") or ""): str(model.get("model_name") or "") for model in snapshot.get("models") or []}
    normalization_by_feature = {rule["feature_name"]: rule["normalization"] for rule in NUMERIC_CLAIM_RULES}
    values_by_model_feature = {
        (str(value.get("model_id") or ""), str(value.get("feature_id") or "")): value
        for value in snapshot.get("feature_values") or []
    }
    findings: list[dict[str, Any]] = []
    for claim in claims:
        feature_id = str(claim.get("feature_id") or "")
        feature_name = feature_names.get(feature_id, "")
        normalization = normalization_by_feature.get(feature_name)
        model_ids, narrowed_by_evidence = _comparison_model_scope(claim, model_names)
        scope_reason = "原文数值附近唯一识别到适用型号，已按该型号缩小本次比较范围。" if narrowed_by_evidence else ""
        for model_id in model_ids:
            parameter_value = values_by_model_feature.get((model_id, feature_id))
            canonical_value = str((parameter_value or {}).get("value_text") or "")
            canonical_normalized = (
                _unique_normalized_numeric_value(canonical_value, normalization)
                if normalization and parameter_value and parameter_value.get("quality_status") == "confirmed"
                else None
            )
            if canonical_normalized is None:
                status = "needs_parameter_data"
                severity = "warning"
                reason = "参数清单值不是可唯一归一化的已确认数值，不能判定知识错误。"
            elif canonical_normalized == claim["normalized_value"]:
                status = "consistent"
                severity = "info"
                reason = "知识声明值与参数清单已确认值一致。"
            else:
                status = "conflict"
                severity = "error"
                reason = "知识声明值与参数清单已确认值不同，需人工复核型号范围和原文。"
            findings.append({
                "question_wiki_id": claim["question_wiki_id"],
                "claim_id": claim["claim_id"],
                "model_id": model_id,
                "feature_id": feature_id,
                "asserted_value": claim["asserted_value"],
                "canonical_value": canonical_value or None,
                "feature_value_version": (parameter_value or {}).get("version"),
                "result_status": status,
                "severity": severity,
                "reason": f"{reason}{scope_reason}",
            })
    return findings


def _read_proposed_numeric_claims(connection, category_name: str) -> list[dict[str, Any]]:
    with connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT claim.claim_id, claim.question_wiki_id, claim.feature_id,
                   claim.asserted_value, claim.normalized_value, claim.evidence_text
            FROM kb_parameter_claim AS claim
            JOIN parameter_check_run AS source_run ON source_run.run_id = claim.source_run_id
            WHERE claim.library_type = 'current'
              AND claim.extraction_method = 'rule'
              AND claim.binding_status = 'proposed'
              AND source_run.scope_json ->> 'category_name' = %s
            ORDER BY claim.question_wiki_id, claim.feature_id, claim.claim_id
            """,
            (category_name,),
        )
        claims = [dict(row) for row in cursor.fetchall()]
        for claim in claims:
            cursor.execute(
                "SELECT model_id FROM kb_parameter_claim_model WHERE claim_id = %s ORDER BY model_id",
                (claim["claim_id"],),
            )
            claim["model_ids"] = [str(row["model_id"]) for row in cursor.fetchall()]
    return claims


def run_historical_numeric_comparison(connection, *, category_name: str, actor: str) -> dict[str, Any]:
    snapshot_row = _latest_snapshot(connection, category_name)
    if not snapshot_row:
        raise ValueError(f"没有可用的 {category_name} 参数快照，请先同步快照。")
    claims = _read_proposed_numeric_claims(connection, category_name)
    run_id = str(uuid.uuid4())
    scope_json = {
        "category_name": category_name,
        "library_type": "current",
        "stage": "numeric_comparison",
        "rule_version": HISTORICAL_COMPARE_RULE_VERSION,
        "proposed_claim_count": len(claims),
    }
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO parameter_check_run (run_id, run_type, snapshot_id, scope_json, status, created_by)
            VALUES (%s, 'historical', %s, %s, 'running', %s)
            """,
            (run_id, snapshot_row["snapshot_id"], Json(scope_json), actor),
        )
    connection.commit()

    try:
        findings = compare_proposed_numeric_claims(claims, snapshot_row["content_json"])
        status_counts: dict[str, int] = {}
        with connection.cursor() as cursor:
            for finding in findings:
                cursor.execute(
                    """
                    INSERT INTO parameter_check_finding (
                        finding_id, run_id, question_wiki_id, claim_id, model_id, feature_id,
                        asserted_value, canonical_value, feature_value_version, result_status,
                        severity, reason, resolution_status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'unreviewed')
                    """,
                    (
                        str(uuid.uuid4()),
                        run_id,
                        finding["question_wiki_id"],
                        finding["claim_id"],
                        finding["model_id"],
                        finding["feature_id"],
                        finding["asserted_value"],
                        finding["canonical_value"],
                        finding["feature_value_version"],
                        finding["result_status"],
                        finding["severity"],
                        finding["reason"],
                    ),
                )
                status_counts[finding["result_status"]] = status_counts.get(finding["result_status"], 0) + 1
        result_counts = {
            "proposed_claim_count": len(claims),
            "finding_count": len(findings),
            **status_counts,
        }
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE parameter_check_run
                SET status = 'completed', result_counts_json = %s, completed_at = NOW()
                WHERE run_id = %s
                """,
                (Json(result_counts), run_id),
            )
        connection.commit()
        return {"run_id": run_id, "snapshot_id": snapshot_row["snapshot_id"], "result_counts": result_counts}
    except Exception:
        connection.rollback()
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE parameter_check_run SET status = 'failed', completed_at = NOW() WHERE run_id = %s",
                (run_id,),
            )
        connection.commit()
        raise


def _read_scoped_knowledge_rows(connection, wiki_ids: list[str]) -> list[dict[str, Any]]:
    if not wiki_ids:
        return []
    with connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT question_wiki_id, question, answer
            FROM knowledge_base_v1
            WHERE question_wiki_id = ANY(%s)
            ORDER BY question_wiki_id
            """,
            (wiki_ids,),
        )
        return [dict(row) for row in cursor.fetchall()]


def _parameter_candidate_feature_rules(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rule_by_name = {str(rule["feature_name"]): rule for rule in NUMERIC_CLAIM_RULES}
    return {
        str(feature.get("id")): {
            "id": str(feature.get("id")),
            "name": str(feature.get("name") or ""),
            "normalization": rule_by_name[str(feature.get("name") or "")]["normalization"],
        }
        for feature in snapshot.get("features") or []
        if str(feature.get("id") or "") and str(feature.get("name") or "") in rule_by_name
    }


def _parse_ai_json_object(value: str) -> dict[str, Any] | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def _ai_response_candidate_count(value: str) -> int:
    parsed = _parse_ai_json_object(value)
    candidates = parsed.get("candidates") if parsed else None
    return len(candidates) if isinstance(candidates, list) else 0


def assess_ai_candidate_against_snapshot(
    candidate: dict[str, Any],
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Keep the AI suggestion visible while deriving a reproducible value comparison."""
    model_names = {
        str(model.get("id") or ""): str(model.get("model_name") or model.get("model_code") or model.get("id") or "")
        for model in snapshot.get("models") or []
    }
    findings = compare_proposed_numeric_claims([{**candidate, "claim_id": ""}], snapshot)
    if not findings:
        return {
            "comparison_verdict": "check_unavailable",
            "comparison_reason": "未找到可用于该候选的已确认型号范围，不能自动比对。",
            "comparison_values": [],
        }

    statuses = {str(finding["result_status"]) for finding in findings}
    comparison_values = [
        {
            "model_id": str(finding["model_id"]),
            "model_name": model_names.get(str(finding["model_id"]), str(finding["model_id"])),
            "canonical_value": finding.get("canonical_value"),
            "feature_value_version": finding.get("feature_value_version"),
            "result_status": finding["result_status"],
            "reason": finding["reason"],
        }
        for finding in findings
    ]
    if len(statuses) == 1:
        verdict = next(iter(statuses))
        return {
            "comparison_verdict": verdict,
            "comparison_reason": "；".join(dict.fromkeys(str(finding["reason"]) for finding in findings)),
            "comparison_values": comparison_values,
        }
    return {
        "comparison_verdict": "ambiguous_model",
        "comparison_reason": "同一知识候选覆盖的型号得出不同参数比对结果，需人工确认适用范围。",
        "comparison_values": comparison_values,
    }


def extract_ai_numeric_parameter_claims(
    raw_response: str,
    kb_row: dict[str, Any],
    model_ids: set[str],
    snapshot: dict[str, Any],
    allowed_feature_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Validate AI output into review-only claims anchored to the source text."""
    parsed = _parse_ai_json_object(raw_response)
    candidates = parsed.get("candidates") if parsed else None
    if not isinstance(candidates, list):
        return []
    feature_rules = _parameter_candidate_feature_rules(snapshot)
    if allowed_feature_ids is not None:
        feature_rules = {
            feature_id: rule
            for feature_id, rule in feature_rules.items()
            if feature_id in allowed_feature_ids
        }
    question = str(kb_row.get("question") or "")
    answer = str(kb_row.get("answer") or "")
    source_text = f"{question}\n{answer}"
    claims: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for raw in candidates[:10]:
        if not isinstance(raw, dict):
            continue
        feature_id = str(raw.get("feature_id") or "").strip()
        asserted_value = str(raw.get("asserted_value") or "").strip()
        evidence_text = str(raw.get("evidence_text") or "").strip()
        feature_rule = feature_rules.get(feature_id)
        if not feature_rule or not asserted_value or not evidence_text:
            continue
        if evidence_text not in source_text or asserted_value not in evidence_text:
            continue
        normalized_value = _normalize_numeric_value(asserted_value, feature_rule["normalization"])
        if normalized_value is None:
            continue
        key = (feature_id, asserted_value, evidence_text)
        if key in seen:
            continue
        seen.add(key)
        claims.append({
            "library_type": "current",
            "question_wiki_id": str(kb_row.get("question_wiki_id") or ""),
            "kb_revision": _knowledge_revision(question, answer),
            "feature_id": feature_id,
            "asserted_value": asserted_value,
            "normalized_value": normalized_value,
            "evidence_text": evidence_text,
            "model_ids": sorted(str(model_id) for model_id in model_ids if str(model_id)),
            "ai_verdict": str(raw.get("initial_verdict") or "needs_human_review").strip(),
            "ai_reason_code": str(raw.get("reason_code") or "ambiguous_claim").strip(),
            "ai_reason": str(raw.get("reason") or "").strip()[:500],
        })
        if claims[-1]["ai_verdict"] not in AI_INITIAL_VERDICTS:
            claims[-1]["ai_verdict"] = "needs_human_review"
        if claims[-1]["ai_reason_code"] not in AI_INITIAL_REASON_CODES:
            claims[-1]["ai_reason_code"] = "ambiguous_claim"
    return claims


def _ai_parameter_reference_context(
    snapshot: dict[str, Any],
    model_ids: set[str],
    feature_rules: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    model_names = {
        str(model.get("id") or ""): str(model.get("model_name") or model.get("model_code") or model.get("id") or "")
        for model in snapshot.get("models") or []
    }
    feature_ids = set(feature_rules)
    values_by_model: dict[str, list[dict[str, Any]]] = {str(model_id): [] for model_id in model_ids}
    for value in snapshot.get("feature_values") or []:
        model_id = str(value.get("model_id") or "")
        if model_id not in values_by_model or str(value.get("feature_id") or "") not in feature_ids:
            continue
        values_by_model[model_id].append({
            "feature_id": str(value.get("feature_id") or ""),
            "value_text": str(value.get("value_text") or ""),
            "quality_status": str(value.get("quality_status") or ""),
            "version": value.get("version"),
        })
    return [
        {
            "model_id": model_id,
            "model_name": model_names.get(model_id, model_id),
            "parameter_values": values_by_model.get(model_id, []),
        }
        for model_id in sorted(values_by_model)
    ]


def _ai_numeric_parameter_prompt(
    kb_row: dict[str, Any],
    feature_rules: dict[str, dict[str, Any]],
    model_ids: set[str],
    snapshot: dict[str, Any],
) -> tuple[str, str]:
    feature_list = [
        {"feature_id": item["id"], "feature_name": item["name"], "normalized_unit": item["normalization"]}
        for item in feature_rules.values()
    ]
    system_prompt = (
        "你是知识库参数候选提取助手，只提取明确写在输入知识原文中的数值型参数候选。"
        "这不是参数事实判定，也不能补充、改写、推断任何原文没有的事实。"
        "只能选择提供的 feature_id；evidence_text 必须逐字摘自输入原文，且 asserted_value 必须出现在 evidence_text 中。"
        "只保留带数字和单位、能对应单一数值的直接参数描述。比较句、条件句、多个场景数值或含义不明确时不要输出。"
        "对于每个候选，结合给定参数快照给出 initial_verdict：likely_consistent、likely_inconsistent 或 needs_human_review；"
        "reason_code 只能是 value_match、value_conflict、model_scope_uncertain、parameter_unavailable、ambiguous_claim。"
        "初判只是建议，参数快照没有已确认唯一值或适用型号不明确时必须输出 needs_human_review。"
        "只输出严格 JSON：{\"candidates\":[{\"feature_id\":string,\"asserted_value\":string,\"evidence_text\":string,\"initial_verdict\":string,\"reason_code\":string,\"reason\":string}]}。"
    )
    user_prompt = json.dumps({
        "allowed_features": feature_list,
        "knowledge": {
            "question_wiki_id": str(kb_row.get("question_wiki_id") or ""),
            "question": str(kb_row.get("question") or "")[:6000],
            "answer": str(kb_row.get("answer") or "")[:12000],
        },
        "parameter_snapshot_context": _ai_parameter_reference_context(snapshot, model_ids, feature_rules),
    }, ensure_ascii=False)
    return system_prompt, user_prompt


def _call_ai_numeric_parameter_extraction(
    config: dict[str, Any],
    kb_row: dict[str, Any],
    feature_rules: dict[str, dict[str, Any]],
    model_ids: set[str],
    snapshot: dict[str, Any],
) -> str:
    api_key = str(config.get("api_key") or "").strip()
    base_url = str(config.get("base_url") or "").strip()
    model = str(config.get("model") or "").strip()
    if not api_key or not base_url or not model:
        raise ValueError("知识库 AI 配置不完整，请先在 AI 配置中设置 API Key、Base URL 和模型。")
    system_prompt, user_prompt = _ai_numeric_parameter_prompt(kb_row, feature_rules, model_ids, snapshot)
    scorer = LLMScorer(api_key=api_key, base_url=base_url, model=model, system_prompt=system_prompt)
    return scorer._chat_completions(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
        response_format=None,
        timeout=90,
    )


def _read_ai_scanned_revisions(connection, category_name: str, wiki_ids: list[str]) -> set[tuple[str, str]]:
    if not wiki_ids:
        return set()
    with connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT question_wiki_id, kb_revision
            FROM parameter_ai_scan_receipt
            WHERE library_type = 'current'
              AND category_name = %s
              AND question_wiki_id = ANY(%s)
            """,
            (category_name, wiki_ids),
        )
        return {(str(row["question_wiki_id"]), str(row["kb_revision"])) for row in cursor.fetchall()}


def _read_feature_ai_scanned_revisions(
    connection,
    category_name: str,
    feature_id: str,
    wiki_ids: list[str],
) -> set[tuple[str, str]]:
    """Only exclude a revision after this exact parameter function scanned it."""
    if not wiki_ids:
        return set()
    with connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT scan.question_wiki_id, scan.kb_revision
            FROM parameter_ai_scan_item AS scan
            JOIN parameter_check_run AS source_run ON source_run.run_id = scan.run_id
            WHERE source_run.scope_json ->> 'stage' = 'ai_feature_extraction'
              AND source_run.scope_json ->> 'category_name' = %s
              AND source_run.scope_json ->> 'feature_id' = %s
              AND scan.question_wiki_id = ANY(%s)
            """,
            (category_name, feature_id, wiki_ids),
        )
        return {(str(row["question_wiki_id"]), str(row["kb_revision"])) for row in cursor.fetchall()}


def _read_rule_compared_revisions(
    connection,
    category_name: str,
    wiki_ids: list[str],
) -> set[tuple[str, str]]:
    """Return current rule claims that already have a completed model comparison."""
    if not wiki_ids:
        return set()
    with connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT DISTINCT claim.question_wiki_id, claim.kb_revision
            FROM parameter_check_finding AS finding
            JOIN parameter_check_run AS comparison_run ON comparison_run.run_id = finding.run_id
            JOIN kb_parameter_claim AS claim ON claim.claim_id = finding.claim_id
            WHERE comparison_run.status = 'completed'
              AND comparison_run.scope_json ->> 'category_name' = %s
              AND comparison_run.scope_json ->> 'stage' = 'numeric_comparison'
              AND claim.library_type = 'current'
              AND claim.extraction_method = 'rule'
              AND claim.question_wiki_id = ANY(%s)
            """,
            (category_name, wiki_ids),
        )
        return {(str(row["question_wiki_id"]), str(row["kb_revision"])) for row in cursor.fetchall()}


def _ai_candidate_prefilter_score(kb_row: dict[str, Any], feature_rules: dict[str, dict[str, Any]]) -> int:
    """Rank likely numeric-parameter knowledge locally before an AI request."""
    source_text = f"{str(kb_row.get('question') or '')}\n{str(kb_row.get('answer') or '')}"
    if not source_text.strip():
        return 0
    source_folded = source_text.casefold()
    enabled_feature_names = {str(feature.get("name") or "") for feature in feature_rules.values()}
    score = 0
    for rule in NUMERIC_CLAIM_RULES:
        feature_name = str(rule["feature_name"])
        if feature_name not in enabled_feature_names:
            continue
        if not re.search(rf"\d+(?:\.\d+)?\s*{rule['unit_pattern']}", source_text, re.IGNORECASE):
            continue
        if any(alias.casefold() in source_folded for alias in rule["aliases"]):
            score += 2
            continue
        if any(term.casefold() in source_folded for term in AI_CANDIDATE_SEMANTIC_TERMS[feature_name]):
            score += 1
    return score


def select_ai_candidate_source_rows(
    kb_rows: list[dict[str, Any]],
    scanned_revisions: set[tuple[str, str]],
    feature_rules: dict[str, dict[str, Any]],
    batch_size: int,
    compared_revisions: set[tuple[str, str]] | None = None,
) -> tuple[list[dict[str, Any]], int, int, int]:
    """Return the next AI batch after scan and completed-rule-comparison exclusions."""
    unscanned_rows = [
        row
        for row in kb_rows
        if (
            str(row.get("question_wiki_id") or ""),
            _knowledge_revision(str(row.get("question") or ""), str(row.get("answer") or "")),
        ) not in scanned_revisions
    ]
    compared_revisions = compared_revisions or set()
    candidate_source_rows = [
        row
        for row in unscanned_rows
        if (
            str(row.get("question_wiki_id") or ""),
            _knowledge_revision(str(row.get("question") or ""), str(row.get("answer") or "")),
        ) not in compared_revisions
    ]
    ranked_rows = [
        (score, str(row.get("question_wiki_id") or ""), row)
        for row in candidate_source_rows
        if (score := _ai_candidate_prefilter_score(row, feature_rules)) > 0
    ]
    ranked_rows.sort(key=lambda item: (-item[0], item[1]))
    eligible_count = len(ranked_rows)
    return (
        [row for _score, _wiki_id, row in ranked_rows[:batch_size]],
        eligible_count,
        len(candidate_source_rows),
        len(unscanned_rows) - len(candidate_source_rows),
    )


def _feature_scan_status(processed_count: int, failed_chunk_count: int) -> str:
    if failed_chunk_count == 0:
        return "completed"
    return "partial" if processed_count else "failed"


def _write_ai_candidate_scan_rows(
    connection,
    *,
    run_id: str,
    category_name: str,
    snapshot: dict[str, Any],
    candidates_by_row: list[tuple[dict[str, Any], list[dict[str, Any]], str, int, str, str]],
) -> dict[str, Any]:
    """Persist one completed internal segment before the next AI request starts."""
    candidate_count = sum(len(candidates) for _row, candidates, *_rest in candidates_by_row)
    inserted_count = 0
    existing_count = 0
    scan_status_counts: dict[str, int] = {}
    with connection.cursor() as cursor:
        for row, candidates, scan_status, raw_candidate_count, validation_reason, response_hash in candidates_by_row:
            scan_status_counts[scan_status] = scan_status_counts.get(scan_status, 0) + 1
            for candidate in candidates:
                cursor.execute(
                    """
                    SELECT claim_id
                    FROM kb_parameter_claim
                    WHERE library_type = %s
                      AND question_wiki_id = %s
                      AND kb_revision = %s
                      AND feature_id = %s
                      AND asserted_value IS NOT DISTINCT FROM %s
                      AND normalized_value IS NOT DISTINCT FROM %s
                      AND evidence_text = %s
                      AND extraction_method = 'ai_candidate'
                      AND binding_status = 'proposed'
                    LIMIT 1
                    """,
                    (
                        candidate["library_type"],
                        candidate["question_wiki_id"],
                        candidate["kb_revision"],
                        candidate["feature_id"],
                        candidate["asserted_value"],
                        candidate["normalized_value"],
                        candidate["evidence_text"],
                    ),
                )
                if cursor.fetchone():
                    existing_count += 1
                    continue
                claim_id = str(uuid.uuid4())
                cursor.execute(
                    """
                    INSERT INTO kb_parameter_claim (
                        claim_id, library_type, question_wiki_id, kb_revision, feature_id,
                        asserted_value, normalized_value, evidence_text, extraction_method,
                        binding_status, source_run_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'ai_candidate', 'proposed', %s)
                    """,
                    (
                        claim_id,
                        candidate["library_type"],
                        candidate["question_wiki_id"],
                        candidate["kb_revision"],
                        candidate["feature_id"],
                        candidate["asserted_value"],
                        candidate["normalized_value"],
                        candidate["evidence_text"],
                        run_id,
                    ),
                )
                for model_id in candidate["model_ids"]:
                    cursor.execute(
                        """
                        INSERT INTO kb_parameter_claim_model (claim_id, model_id, scope_source, scope_status)
                        VALUES (%s, %s, 'product_matrix', 'confirmed')
                        ON CONFLICT (claim_id, model_id) DO NOTHING
                        """,
                        (claim_id, model_id),
                    )
                assessment = assess_ai_candidate_against_snapshot(candidate, snapshot)
                cursor.execute(
                    """
                    INSERT INTO parameter_ai_candidate_assessment (
                        claim_id, ai_verdict, ai_reason_code, ai_reason,
                        comparison_verdict, comparison_reason, comparison_values_json
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (claim_id) DO NOTHING
                    """,
                    (
                        claim_id,
                        candidate["ai_verdict"],
                        candidate["ai_reason_code"],
                        candidate["ai_reason"],
                        assessment["comparison_verdict"],
                        assessment["comparison_reason"],
                        Json(assessment["comparison_values"]),
                    ),
                )
                inserted_count += 1
            revision = _knowledge_revision(str(row.get("question") or ""), str(row.get("answer") or ""))
            cursor.execute(
                """
                INSERT INTO parameter_ai_scan_item (
                    run_id, question_wiki_id, kb_revision, scan_status,
                    raw_candidate_count, valid_candidate_count, validation_reason, response_hash
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id, question_wiki_id, kb_revision) DO NOTHING
                """,
                (
                    run_id,
                    str(row["question_wiki_id"]),
                    revision,
                    scan_status,
                    raw_candidate_count,
                    len(candidates),
                    validation_reason,
                    response_hash,
                ),
            )
    connection.commit()
    return {
        "scanned_knowledge_count": len(candidates_by_row),
        "candidate_count": candidate_count,
        "proposed_claim_count": inserted_count,
        "existing_proposed_claim_count": existing_count,
        "scan_status_counts": scan_status_counts,
    }


def _update_feature_ai_scan_progress(
    connection,
    *,
    run_id: str,
    result_counts: dict[str, Any],
    status: str = "running",
    completed: bool = False,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE parameter_check_run
            SET status = %s,
                result_counts_json = %s,
                completed_at = CASE WHEN %s THEN NOW() ELSE completed_at END
            WHERE run_id = %s
            """,
            (status, Json(result_counts), completed, run_id),
        )
    connection.commit()


def _release_feature_scan_scope(category_name: str, feature_id: str) -> None:
    with _AI_FEATURE_SCAN_LOCK:
        _AI_FEATURE_SCAN_ACTIVE_SCOPES.discard((category_name, feature_id))


def _mark_feature_ai_scan_launch_failed(
    *,
    run_id: str,
    category_name: str,
    feature_id: str,
    result_counts: dict[str, Any],
    error: Exception,
) -> None:
    """Close a persisted run when its background thread could not start."""
    failed_counts = dict(result_counts)
    failed_counts["last_error"] = f"后台扫描线程未启动：{str(error)[:420]}"
    try:
        connection = connect_main_database()
        try:
            _update_feature_ai_scan_progress(
                connection,
                run_id=run_id,
                result_counts=failed_counts,
                status="failed",
                completed=True,
            )
        finally:
            connection.close()
    finally:
        _release_feature_scan_scope(category_name, feature_id)


def create_historical_ai_feature_scan(
    connection,
    *,
    category_name: str,
    feature_id: str,
    actor: str,
    chunk_size: int = AI_FEATURE_SCAN_CHUNK_SIZE,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create a feature-level scan and return a self-contained background job."""
    if chunk_size < 1 or chunk_size > AI_CANDIDATE_BATCH_MAX:
        raise ValueError(f"AI 参数功能扫描的内部片段范围为 1 到 {AI_CANDIDATE_BATCH_MAX} 条知识。")
    snapshot_row = _latest_snapshot(connection, category_name)
    if not snapshot_row:
        raise ValueError(f"没有可用的 {category_name} 参数快照，请先同步快照。")
    feature_rules = _parameter_candidate_feature_rules(snapshot_row["content_json"])
    feature_rule = feature_rules.get(feature_id)
    if not feature_rule:
        raise ValueError("该参数功能不在当前可扫描的数值型功能范围内。")
    config = load_ai_config() or {}
    ai_model = str(config.get("model") or "").strip()
    if not str(config.get("api_key") or "").strip() or not str(config.get("base_url") or "").strip() or not ai_model:
        raise ValueError("知识库 AI 配置不完整，请先在 AI 配置中设置 API Key、Base URL 和模型。")

    scope_by_wiki, scope_counts = resolve_confirmed_model_scope(connection, category_name)
    wiki_ids = sorted(scope_by_wiki)
    kb_rows = _read_scoped_knowledge_rows(connection, wiki_ids)
    scanned_revisions = _read_feature_ai_scanned_revisions(connection, category_name, feature_id, wiki_ids)
    pending_rows, eligible_count, candidate_source_count, _already_compared_count = select_ai_candidate_source_rows(
        kb_rows,
        scanned_revisions,
        {feature_id: feature_rule},
        batch_size=max(1, len(kb_rows)),
    )
    scope_key = (category_name, feature_id)
    with _AI_FEATURE_SCAN_LOCK:
        if scope_key in _AI_FEATURE_SCAN_ACTIVE_SCOPES:
            raise ValueError(f"{feature_rule['name']} 已有一项全量扫描正在后台执行。")
        run_id = str(uuid.uuid4())
        scope_json = {
            "category_name": category_name,
            "library_type": "current",
            "scope_source": "confirmed_model_bindings_v1",
            "stage": "ai_feature_extraction",
            "feature_id": feature_id,
            "feature_name": feature_rule["name"],
            "rule_version": HISTORICAL_AI_CANDIDATE_RULE_VERSION,
            "ai_config_source": "knowledge_base_ai_config",
            "ai_model": ai_model,
            "internal_chunk_size": chunk_size,
            "prefilter_version": AI_CANDIDATE_PREFILTER_VERSION,
            "prefilter_eligible_knowledge_count": eligible_count,
            "prefilter_excluded_knowledge_count": candidate_source_count - eligible_count,
            **scope_counts,
        }
        result_counts = {
            "total_eligible_knowledge_count": eligible_count,
            "processed_knowledge_count": 0,
            "scanned_knowledge_count": 0,
            "candidate_count": 0,
            "proposed_claim_count": 0,
            "existing_proposed_claim_count": 0,
            "remaining_knowledge_count": eligible_count,
            "failed_knowledge_count": 0,
            "failed_chunk_count": 0,
            "scan_status_counts": {},
        }
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO parameter_check_run (run_id, run_type, snapshot_id, scope_json, status, result_counts_json, created_by)
                    VALUES (%s, 'historical', %s, %s, 'running', %s, %s)
                    """,
                    (run_id, snapshot_row["snapshot_id"], Json(scope_json), Json(result_counts), actor),
                )
            connection.commit()
            _AI_FEATURE_SCAN_ACTIVE_SCOPES.add(scope_key)
        except Exception:
            connection.rollback()
            raise

    job = {
        "run_id": run_id,
        "category_name": category_name,
        "feature_id": feature_id,
        "feature_name": feature_rule["name"],
        "chunk_size": chunk_size,
        "snapshot": snapshot_row["content_json"],
        "feature_rules": {feature_id: feature_rule},
        "config": config,
        "scope_by_wiki": scope_by_wiki,
        "pending_rows": pending_rows,
        "result_counts": result_counts,
    }
    return {
        "run_id": run_id,
        "snapshot_id": snapshot_row["snapshot_id"],
        "result_counts": result_counts,
        "feature_id": feature_id,
        "feature_name": feature_rule["name"],
    }, job


def run_historical_ai_feature_scan_worker(job: dict[str, Any]) -> None:
    """Run all internal segments without holding request or Flask context resources."""
    run_id = str(job["run_id"])
    category_name = str(job["category_name"])
    feature_id = str(job["feature_id"])
    pending_rows = list(job.get("pending_rows") or [])
    result_counts = dict(job.get("result_counts") or {})
    scan_status_counts = dict(result_counts.get("scan_status_counts") or {})
    try:
        for start in range(0, len(pending_rows), int(job["chunk_size"])):
            rows = pending_rows[start:start + int(job["chunk_size"])]
            try:
                candidates_by_row = []
                for row in rows:
                    model_ids = (job.get("scope_by_wiki") or {}).get(str(row["question_wiki_id"]), set())
                    raw_response = _call_ai_numeric_parameter_extraction(
                        job["config"],
                        row,
                        job["feature_rules"],
                        model_ids,
                        job["snapshot"],
                    )
                    candidates = extract_ai_numeric_parameter_claims(
                        raw_response,
                        row,
                        model_ids,
                        job["snapshot"],
                        allowed_feature_ids={feature_id},
                    )
                    raw_candidate_count = _ai_response_candidate_count(raw_response)
                    if candidates:
                        scan_status = "candidate"
                        validation_reason = "AI 候选已通过原文证据、单位归一化和功能项校验。"
                    elif raw_candidate_count:
                        scan_status = "validator_rejected"
                        validation_reason = "AI 返回了候选，但未通过原文证据、单位归一化或功能项校验。"
                    else:
                        scan_status = "no_candidate"
                        validation_reason = "AI 未返回可用于参数校对的明确数值候选。"
                    candidates_by_row.append((
                        row,
                        candidates,
                        scan_status,
                        raw_candidate_count,
                        validation_reason,
                        hashlib.sha256(raw_response.encode("utf-8")).hexdigest(),
                    ))

                connection = connect_main_database()
                try:
                    batch_counts = _write_ai_candidate_scan_rows(
                        connection,
                        run_id=run_id,
                        category_name=category_name,
                        snapshot=job["snapshot"],
                        candidates_by_row=candidates_by_row,
                    )
                finally:
                    connection.close()
                result_counts["processed_knowledge_count"] = int(result_counts.get("processed_knowledge_count") or 0) + len(rows)
                for key in ("scanned_knowledge_count", "candidate_count", "proposed_claim_count", "existing_proposed_claim_count"):
                    result_counts[key] = int(result_counts.get(key) or 0) + int(batch_counts.get(key) or 0)
                for status, count in (batch_counts.get("scan_status_counts") or {}).items():
                    scan_status_counts[status] = int(scan_status_counts.get(status) or 0) + int(count)
                result_counts["scan_status_counts"] = scan_status_counts
                result_counts["remaining_knowledge_count"] = max(
                    0,
                    int(result_counts.get("total_eligible_knowledge_count") or 0) - int(result_counts.get("processed_knowledge_count") or 0),
                )
            except Exception as exc:
                result_counts["failed_chunk_count"] = int(result_counts.get("failed_chunk_count") or 0) + 1
                result_counts["failed_knowledge_count"] = int(result_counts.get("failed_knowledge_count") or 0) + len(rows)
                result_counts["last_error"] = str(exc)[:500]

            connection = connect_main_database()
            try:
                _update_feature_ai_scan_progress(connection, run_id=run_id, result_counts=result_counts)
            finally:
                connection.close()

        final_status = _feature_scan_status(
            int(result_counts.get("processed_knowledge_count") or 0),
            int(result_counts.get("failed_chunk_count") or 0),
        )
        connection = connect_main_database()
        try:
            _update_feature_ai_scan_progress(
                connection,
                run_id=run_id,
                result_counts=result_counts,
                status=final_status,
                completed=True,
            )
        finally:
            connection.close()
    finally:
        _release_feature_scan_scope(category_name, feature_id)


def run_historical_ai_candidate_scan(
    connection,
    *,
    category_name: str,
    actor: str,
    batch_size: int = AI_CANDIDATE_BATCH_SIZE,
) -> dict[str, Any]:
    if batch_size < 1 or batch_size > AI_CANDIDATE_BATCH_MAX:
        raise ValueError(f"AI 候选提取每批范围为 1 到 {AI_CANDIDATE_BATCH_MAX} 条知识。")
    snapshot_row = _latest_snapshot(connection, category_name)
    if not snapshot_row:
        raise ValueError(f"没有可用的 {category_name} 参数快照，请先同步快照。")
    feature_rules = _parameter_candidate_feature_rules(snapshot_row["content_json"])
    if not feature_rules:
        raise ValueError("参数快照中没有可用于 AI 候选提取的首批功能项。")
    config = load_ai_config() or {}
    ai_model = str(config.get("model") or "").strip()
    if not str(config.get("api_key") or "").strip() or not str(config.get("base_url") or "").strip() or not ai_model:
        raise ValueError("知识库 AI 配置不完整，请先在 AI 配置中设置 API Key、Base URL 和模型。")
    scope_by_wiki, scope_counts = resolve_confirmed_model_scope(connection, category_name)
    kb_rows = _read_scoped_knowledge_rows(connection, sorted(scope_by_wiki))
    scanned_revisions = _read_ai_scanned_revisions(connection, category_name, sorted(scope_by_wiki))
    compared_revisions = _read_rule_compared_revisions(connection, category_name, sorted(scope_by_wiki))
    pending_rows, eligible_count, candidate_source_count, already_compared_count = select_ai_candidate_source_rows(
        kb_rows,
        scanned_revisions,
        feature_rules,
        batch_size,
        compared_revisions,
    )
    run_id = str(uuid.uuid4())
    scope_json = {
        "category_name": category_name,
        "library_type": "current",
        "scope_source": "confirmed_model_bindings_v1",
        "stage": "ai_candidate_extraction",
        "rule_version": HISTORICAL_AI_CANDIDATE_RULE_VERSION,
        "ai_config_source": "knowledge_base_ai_config",
        "ai_model": ai_model,
        "batch_size": batch_size,
        "prefilter_version": AI_CANDIDATE_PREFILTER_VERSION,
        "prefilter_eligible_knowledge_count": eligible_count,
        "prefilter_excluded_knowledge_count": candidate_source_count - eligible_count,
        "already_compared_knowledge_count": already_compared_count,
        **scope_counts,
    }
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO parameter_check_run (run_id, run_type, snapshot_id, scope_json, status, created_by)
            VALUES (%s, 'historical', %s, %s, 'running', %s)
            """,
            (run_id, snapshot_row["snapshot_id"], Json(scope_json), actor),
        )
    connection.commit()

    try:
        candidates_by_row = []
        for row in pending_rows:
            model_ids = scope_by_wiki.get(str(row["question_wiki_id"]), set())
            raw_response = _call_ai_numeric_parameter_extraction(
                config,
                row,
                feature_rules,
                model_ids,
                snapshot_row["content_json"],
            )
            candidates = extract_ai_numeric_parameter_claims(
                raw_response,
                row,
                model_ids,
                snapshot_row["content_json"],
            )
            raw_candidate_count = _ai_response_candidate_count(raw_response)
            if candidates:
                scan_status = "candidate"
                validation_reason = "AI 候选已通过原文证据、单位归一化和功能项校验。"
            elif raw_candidate_count:
                scan_status = "validator_rejected"
                validation_reason = "AI 返回了候选，但未通过原文证据、单位归一化或功能项校验。"
            else:
                scan_status = "no_candidate"
                validation_reason = "AI 未返回可用于参数校对的明确数值候选。"
            candidates_by_row.append((
                row,
                candidates,
                scan_status,
                raw_candidate_count,
                validation_reason,
                hashlib.sha256(raw_response.encode("utf-8")).hexdigest(),
            ))

        candidate_count = sum(len(candidates) for _, candidates, *_rest in candidates_by_row)
        inserted_count = 0
        existing_count = 0
        scan_status_counts: dict[str, int] = {}
        with connection.cursor() as cursor:
            for row, candidates, scan_status, raw_candidate_count, validation_reason, response_hash in candidates_by_row:
                scan_status_counts[scan_status] = scan_status_counts.get(scan_status, 0) + 1
                for candidate in candidates:
                    cursor.execute(
                        """
                        SELECT claim_id
                        FROM kb_parameter_claim
                        WHERE library_type = %s
                          AND question_wiki_id = %s
                          AND kb_revision = %s
                          AND feature_id = %s
                          AND asserted_value IS NOT DISTINCT FROM %s
                          AND normalized_value IS NOT DISTINCT FROM %s
                          AND evidence_text = %s
                          AND extraction_method = 'ai_candidate'
                          AND binding_status = 'proposed'
                        LIMIT 1
                        """,
                        (
                            candidate["library_type"],
                            candidate["question_wiki_id"],
                            candidate["kb_revision"],
                            candidate["feature_id"],
                            candidate["asserted_value"],
                            candidate["normalized_value"],
                            candidate["evidence_text"],
                        ),
                    )
                    if cursor.fetchone():
                        existing_count += 1
                        continue
                    claim_id = str(uuid.uuid4())
                    cursor.execute(
                        """
                        INSERT INTO kb_parameter_claim (
                            claim_id, library_type, question_wiki_id, kb_revision, feature_id,
                            asserted_value, normalized_value, evidence_text, extraction_method,
                            binding_status, source_run_id
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'ai_candidate', 'proposed', %s)
                        """,
                        (
                            claim_id,
                            candidate["library_type"],
                            candidate["question_wiki_id"],
                            candidate["kb_revision"],
                            candidate["feature_id"],
                            candidate["asserted_value"],
                            candidate["normalized_value"],
                            candidate["evidence_text"],
                            run_id,
                        ),
                    )
                    for model_id in candidate["model_ids"]:
                        cursor.execute(
                            """
                            INSERT INTO kb_parameter_claim_model (claim_id, model_id, scope_source, scope_status)
                            VALUES (%s, %s, 'product_matrix', 'confirmed')
                            ON CONFLICT (claim_id, model_id) DO NOTHING
                            """,
                            (claim_id, model_id),
                        )
                    assessment = assess_ai_candidate_against_snapshot(candidate, snapshot_row["content_json"])
                    cursor.execute(
                        """
                        INSERT INTO parameter_ai_candidate_assessment (
                            claim_id, ai_verdict, ai_reason_code, ai_reason,
                            comparison_verdict, comparison_reason, comparison_values_json
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (claim_id) DO NOTHING
                        """,
                        (
                            claim_id,
                            candidate["ai_verdict"],
                            candidate["ai_reason_code"],
                            candidate["ai_reason"],
                            assessment["comparison_verdict"],
                            assessment["comparison_reason"],
                            Json(assessment["comparison_values"]),
                        ),
                    )
                    inserted_count += 1
                revision = _knowledge_revision(str(row.get("question") or ""), str(row.get("answer") or ""))
                cursor.execute(
                    """
                    INSERT INTO parameter_ai_scan_item (
                        run_id, question_wiki_id, kb_revision, scan_status,
                        raw_candidate_count, valid_candidate_count, validation_reason, response_hash
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (run_id, question_wiki_id, kb_revision) DO NOTHING
                    """,
                    (
                        run_id,
                        str(row["question_wiki_id"]),
                        revision,
                        scan_status,
                        raw_candidate_count,
                        len(candidates),
                        validation_reason,
                        response_hash,
                    ),
                )
                cursor.execute(
                    """
                    INSERT INTO parameter_ai_scan_receipt (
                        library_type, question_wiki_id, kb_revision, category_name, source_run_id, candidate_count
                    ) VALUES ('current', %s, %s, %s, %s, %s)
                    ON CONFLICT (library_type, question_wiki_id, kb_revision, category_name) DO NOTHING
                    """,
                    (str(row["question_wiki_id"]), revision, category_name, run_id, len(candidates)),
                )
        result_counts = {
            "scanned_knowledge_count": len(pending_rows),
            "candidate_count": candidate_count,
            "proposed_claim_count": inserted_count,
            "existing_proposed_claim_count": existing_count,
            "remaining_knowledge_count": max(0, eligible_count - len(pending_rows)),
            "prefilter_excluded_knowledge_count": candidate_source_count - eligible_count,
            "already_compared_knowledge_count": already_compared_count,
            "scan_status_counts": scan_status_counts,
            "finding_count": 0,
        }
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE parameter_check_run
                SET status = 'completed', result_counts_json = %s, completed_at = NOW()
                WHERE run_id = %s
                """,
                (Json(result_counts), run_id),
            )
        connection.commit()
        return {"run_id": run_id, "snapshot_id": snapshot_row["snapshot_id"], "result_counts": result_counts}
    except Exception:
        connection.rollback()
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE parameter_check_run SET status = 'failed', completed_at = NOW() WHERE run_id = %s",
                (run_id,),
            )
        connection.commit()
        raise


def run_historical_numeric_claim_scan(connection, *, category_name: str, actor: str) -> dict[str, Any]:
    snapshot_row = _latest_snapshot(connection, category_name)
    if not snapshot_row:
        raise ValueError(f"没有可用的 {category_name} 参数快照，请先同步快照。")
    scope_by_wiki, scope_counts = resolve_confirmed_model_scope(connection, category_name)
    wiki_ids = sorted(scope_by_wiki)
    run_id = str(uuid.uuid4())
    scope_json = {
        "category_name": category_name,
        "library_type": "current",
        "scope_source": "confirmed_model_bindings_v1",
        "rule_version": HISTORICAL_NUMERIC_RULE_VERSION,
        **scope_counts,
    }
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO parameter_check_run (run_id, run_type, snapshot_id, scope_json, status, created_by)
            VALUES (%s, 'historical', %s, %s, 'running', %s)
            """,
            (run_id, snapshot_row["snapshot_id"], Json(scope_json), actor),
        )
    connection.commit()

    try:
        kb_rows = _read_scoped_knowledge_rows(connection, wiki_ids)
        candidates = extract_numeric_parameter_claims(kb_rows, scope_by_wiki, snapshot_row["content_json"])
        inserted_count = 0
        existing_count = 0
        with connection.cursor() as cursor:
            for candidate in candidates:
                cursor.execute(
                    """
                    SELECT claim_id
                    FROM kb_parameter_claim
                    WHERE library_type = %s
                      AND question_wiki_id = %s
                      AND kb_revision = %s
                      AND feature_id = %s
                      AND asserted_value IS NOT DISTINCT FROM %s
                      AND normalized_value IS NOT DISTINCT FROM %s
                      AND evidence_text = %s
                      AND extraction_method = 'rule'
                      AND binding_status = 'proposed'
                    LIMIT 1
                    """,
                    (
                        candidate["library_type"],
                        candidate["question_wiki_id"],
                        candidate["kb_revision"],
                        candidate["feature_id"],
                        candidate["asserted_value"],
                        candidate["normalized_value"],
                        candidate["evidence_text"],
                    ),
                )
                row = cursor.fetchone()
                if row:
                    existing_count += 1
                    continue
                claim_id = str(uuid.uuid4())
                cursor.execute(
                    """
                    INSERT INTO kb_parameter_claim (
                        claim_id, library_type, question_wiki_id, kb_revision, feature_id,
                        asserted_value, normalized_value, evidence_text, extraction_method,
                        binding_status, source_run_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'rule', 'proposed', %s)
                    """,
                    (
                        claim_id,
                        candidate["library_type"],
                        candidate["question_wiki_id"],
                        candidate["kb_revision"],
                        candidate["feature_id"],
                        candidate["asserted_value"],
                        candidate["normalized_value"],
                        candidate["evidence_text"],
                        run_id,
                    ),
                )
                for model_id in candidate["model_ids"]:
                    cursor.execute(
                        """
                        INSERT INTO kb_parameter_claim_model (claim_id, model_id, scope_source, scope_status)
                        VALUES (%s, %s, 'product_matrix', 'confirmed')
                        ON CONFLICT (claim_id, model_id) DO NOTHING
                        """,
                        (claim_id, model_id),
                    )
                inserted_count += 1
        result_counts = {
            "scoped_wiki_count": len(kb_rows),
            "candidate_count": len(candidates),
            "proposed_claim_count": inserted_count,
            "existing_proposed_claim_count": existing_count,
            "finding_count": 0,
        }
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE parameter_check_run
                SET status = 'completed', result_counts_json = %s, completed_at = NOW()
                WHERE run_id = %s
                """,
                (Json(result_counts), run_id),
            )
        connection.commit()
        return {"run_id": run_id, "snapshot_id": snapshot_row["snapshot_id"], "result_counts": result_counts}
    except Exception:
        connection.rollback()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE parameter_check_run
                SET status = 'failed', completed_at = NOW()
                WHERE run_id = %s
                """,
                (run_id,),
            )
        connection.commit()
        raise


def get_parameter_check_run(connection, run_id: str) -> dict[str, Any] | None:
    with connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT run_id, run_type, snapshot_id, scope_json, status, result_counts_json,
                   created_by, created_at, completed_at
            FROM parameter_check_run
            WHERE run_id = %s
            """,
            (run_id,),
        )
        row = cursor.fetchone()
    return dict(row) if row else None


def _parameter_check_snapshot_metadata(snapshot_row: dict[str, Any] | None) -> tuple[dict[str, Any] | None, dict[str, str], dict[str, str]]:
    if not snapshot_row:
        return None, {}, {}
    content = snapshot_row.get("content_json") or {}
    models = content.get("models") or []
    features = content.get("features") or []
    model_names = {
        str(item.get("id")): str(item.get("model_name") or item.get("model_code") or item.get("id"))
        for item in models
        if item.get("id")
    }
    feature_names = {
        str(item.get("id")): str(item.get("name") or item.get("feature_code") or item.get("id"))
        for item in features
        if item.get("id")
    }
    return {
        "snapshot_id": snapshot_row.get("snapshot_id"),
        "source_version": snapshot_row.get("source_version"),
        "content_hash": snapshot_row.get("content_hash"),
        "synced_at": snapshot_row.get("synced_at"),
        "model_count": len(models),
        "feature_count": len(features),
        "feature_value_count": len(content.get("feature_values") or []),
    }, model_names, feature_names


def _parameter_scan_feature_options(feature_names: dict[str, str]) -> list[dict[str, str]]:
    numeric_feature_names = {str(rule["feature_name"]) for rule in NUMERIC_CLAIM_RULES}
    options = [
        {"id": feature_id, "name": feature_name}
        for feature_id, feature_name in feature_names.items()
        if feature_name in numeric_feature_names
    ]
    return sorted(options, key=lambda item: item["name"])


def _parameter_check_run_payload(row: dict[str, Any]) -> dict[str, Any]:
    scope = row.get("scope_json") or {}
    return {
        "run_id": str(row.get("run_id") or ""),
        "run_type": row.get("run_type"),
        "snapshot_id": row.get("snapshot_id"),
        "stage": scope.get("stage"),
        "feature_id": scope.get("feature_id"),
        "feature_name": scope.get("feature_name"),
        "internal_chunk_size": scope.get("internal_chunk_size"),
        "ai_config_source": scope.get("ai_config_source"),
        "ai_model": scope.get("ai_model"),
        "status": row.get("status"),
        "result_counts": row.get("result_counts_json") or {},
        "created_by": row.get("created_by"),
        "created_at": row.get("created_at"),
        "completed_at": row.get("completed_at"),
    }


def _ai_verdict_to_final_verdict(value: str) -> str | None:
    return {
        "likely_consistent": "consistent",
        "likely_inconsistent": "conflict",
    }.get(value)


def decide_ai_candidate_review(
    connection,
    *,
    claim_id: str,
    decision: str,
    final_verdict: str | None,
    review_reason: str,
    actor: str,
) -> dict[str, Any]:
    if decision not in PARAMETER_CANDIDATE_REVIEW_STATUSES - {"unreviewed"}:
        raise ValueError("人工复核动作不合法。")
    try:
        uuid.UUID(claim_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("AI 候选标识格式不正确。") from exc

    normalized_reason = review_reason.strip()[:1000]
    with connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT assessment.ai_verdict, assessment.comparison_verdict
            FROM parameter_ai_candidate_assessment AS assessment
            JOIN kb_parameter_claim AS claim ON claim.claim_id = assessment.claim_id
            WHERE assessment.claim_id = %s
              AND claim.extraction_method = 'ai_candidate'
            """,
            (claim_id,),
        )
        existing = cursor.fetchone()
        if not existing:
            raise ValueError("未找到可人工复核的 AI 候选。")

        if decision == "false_positive":
            final_verdict = "not_parameter_claim"
        elif final_verdict not in PARAMETER_CHECK_RESULT_STATUSES:
            raise ValueError("人工最终结论不合法。")

        expected_verdict = _ai_verdict_to_final_verdict(str(existing["ai_verdict"]))
        if decision == "accepted":
            if not expected_verdict or final_verdict != expected_verdict:
                raise ValueError("AI 初判为待人工判断时，请使用“修正结论”提交最终判断。")
            if final_verdict != str(existing["comparison_verdict"]):
                raise ValueError("AI 初判与参数快照比对不一致时，请使用“修正结论”并说明原因。")
        elif not normalized_reason:
            raise ValueError("修正 AI 初判或标记误报时必须填写人工复核理由。")

        cursor.execute(
            """
            UPDATE parameter_ai_candidate_assessment
            SET review_status = %s,
                final_verdict = %s,
                review_reason = %s,
                reviewed_by = %s,
                reviewed_at = NOW(),
                updated_at = NOW()
            WHERE claim_id = %s
            RETURNING review_status, final_verdict, review_reason, reviewed_by, reviewed_at, updated_at
            """,
            (decision, final_verdict, normalized_reason or None, actor, claim_id),
        )
        review = dict(cursor.fetchone())
        cursor.execute(
            """
            UPDATE kb_parameter_claim
            SET binding_status = %s,
                confirmed_by = %s,
                confirmed_at = NOW(),
                updated_at = NOW()
            WHERE claim_id = %s
            """,
            ("rejected" if decision == "false_positive" else "confirmed", actor, claim_id),
        )
    connection.commit()
    return {"claim_id": claim_id, **review}


def backfill_historical_ai_candidate_assessments(connection) -> int:
    """Append safe review bases for AI candidates created before initial judgments existed."""
    with connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT claim.claim_id::text, claim.question_wiki_id, claim.feature_id,
                   claim.asserted_value, claim.normalized_value, claim.evidence_text,
                   snapshot.content_json
            FROM kb_parameter_claim AS claim
            JOIN parameter_check_run AS source_run ON source_run.run_id = claim.source_run_id
            LEFT JOIN parameter_snapshot AS snapshot ON snapshot.snapshot_id = source_run.snapshot_id
            LEFT JOIN parameter_ai_candidate_assessment AS assessment ON assessment.claim_id = claim.claim_id
            WHERE claim.extraction_method = 'ai_candidate'
              AND assessment.claim_id IS NULL
            ORDER BY claim.created_at, claim.claim_id
            """
        )
        claims = [dict(row) for row in cursor.fetchall()]
        created_count = 0
        for claim in claims:
            cursor.execute(
                "SELECT model_id FROM kb_parameter_claim_model WHERE claim_id = %s ORDER BY model_id",
                (claim["claim_id"],),
            )
            claim["model_ids"] = [str(row["model_id"]) for row in cursor.fetchall()]
            snapshot = claim.pop("content_json", None)
            if isinstance(snapshot, dict):
                assessment = assess_ai_candidate_against_snapshot(claim, snapshot)
            else:
                assessment = {
                    "comparison_verdict": "check_unavailable",
                    "comparison_reason": "历史候选对应的参数快照已不可用，需人工补充依据。",
                    "comparison_values": [],
                }
            cursor.execute(
                """
                INSERT INTO parameter_ai_candidate_assessment (
                    claim_id, ai_verdict, ai_reason_code, ai_reason,
                    comparison_verdict, comparison_reason, comparison_values_json
                ) VALUES (%s, 'needs_human_review', 'ambiguous_claim', %s, %s, %s, %s)
                ON CONFLICT (claim_id) DO NOTHING
                """,
                (
                    claim["claim_id"],
                    "历史扫描未保留 AI 初判；请结合原文与参数快照作出人工结论。",
                    assessment["comparison_verdict"],
                    assessment["comparison_reason"],
                    Json(assessment["comparison_values"]),
                ),
            )
            created_count += int(cursor.rowcount or 0)
    connection.commit()
    return created_count


def _get_ai_scan_audit_overview(
    cursor,
    *,
    category_name: str,
    snapshot: dict[str, Any] | None,
    run_rows: list[dict[str, Any]],
    selected_run: dict[str, Any],
    wiki_id: str | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    base = ["scan.run_id = %s"]
    params: list[Any] = [selected_run["run_id"]]
    if wiki_id:
        base.append("scan.question_wiki_id ILIKE %s")
        params.append(f"%{wiki_id}%")
    where_clause = " AND ".join(base)
    cursor.execute(
        "SELECT scan_status, COUNT(*) AS count FROM parameter_ai_scan_item WHERE run_id = %s GROUP BY scan_status",
        (selected_run["run_id"],),
    )
    status_counts = {str(row["scan_status"]): int(row["count"]) for row in cursor.fetchall()}
    cursor.execute(f"SELECT COUNT(*) AS count FROM parameter_ai_scan_item AS scan WHERE {where_clause}", params)
    total = int(cursor.fetchone()["count"])
    if total:
        cursor.execute(
            f"""
            SELECT scan.question_wiki_id, scan.kb_revision, scan.scan_status,
                   scan.raw_candidate_count, scan.valid_candidate_count,
                   scan.validation_reason, scan.response_hash, scan.created_at,
                   FALSE AS historical_summary
            FROM parameter_ai_scan_item AS scan
            WHERE {where_clause}
            ORDER BY CASE scan.scan_status WHEN 'candidate' THEN 0 WHEN 'validator_rejected' THEN 1 ELSE 2 END,
                     scan.question_wiki_id
            LIMIT %s OFFSET %s
            """,
            [*params, page_size, (page - 1) * page_size],
        )
        rows = [dict(row) for row in cursor.fetchall()]
    else:
        receipt_where = ["receipt.source_run_id = %s"]
        receipt_params: list[Any] = [selected_run["run_id"]]
        if wiki_id:
            receipt_where.append("receipt.question_wiki_id ILIKE %s")
            receipt_params.append(f"%{wiki_id}%")
        receipt_clause = " AND ".join(receipt_where)
        cursor.execute(
            f"SELECT COUNT(*) AS count FROM parameter_ai_scan_receipt AS receipt WHERE {receipt_clause}",
            receipt_params,
        )
        total = int(cursor.fetchone()["count"])
        cursor.execute(
            f"""
            SELECT receipt.question_wiki_id, receipt.kb_revision,
                   CASE WHEN receipt.candidate_count > 0 THEN 'candidate' ELSE 'no_candidate' END AS scan_status,
                   NULL::INTEGER AS raw_candidate_count,
                   receipt.candidate_count AS valid_candidate_count,
                   '历史运行仅保留最终候选数量，未保留 AI 原始响应和校验明细。' AS validation_reason,
                   NULL::TEXT AS response_hash,
                   receipt.created_at,
                   TRUE AS historical_summary
            FROM parameter_ai_scan_receipt AS receipt
            WHERE {receipt_clause}
            ORDER BY receipt.question_wiki_id
            LIMIT %s OFFSET %s
            """,
            [*receipt_params, page_size, (page - 1) * page_size],
        )
        rows = [dict(row) for row in cursor.fetchall()]
        status_counts = {}
        for row in rows:
            status = str(row["scan_status"])
            status_counts[status] = status_counts.get(status, 0) + 1
    items = []
    for item in rows:
        item["audit_key"] = f"{item['question_wiki_id']}:{item['kb_revision']}"
        items.append(item)
    result_counts = selected_run.get("result_counts_json") or {}
    return {
        "category_name": category_name,
        "snapshot": snapshot,
        "runs": [_parameter_check_run_payload(row) for row in run_rows],
        "selected_run": _parameter_check_run_payload(selected_run),
        "view_mode": "ai_scan_audit",
        "summary": {
            "scanned_knowledge_count": int(result_counts.get("scanned_knowledge_count") or 0),
            "candidate_count": int(result_counts.get("candidate_count") or 0),
            "scan_status_counts": status_counts,
        },
        "filter_options": {"models": [], "features": []},
        "findings": [],
        "audit_items": items,
        "pagination": {"page": page, "page_size": page_size, "total": total},
    }


def _get_ai_candidate_overview(
    cursor,
    *,
    category_name: str,
    snapshot: dict[str, Any] | None,
    model_names: dict[str, str],
    feature_names: dict[str, str],
    run_rows: list[dict[str, Any]],
    selected_run: dict[str, Any] | None,
    queue: bool,
    model_id: str | None,
    feature_id: str | None,
    wiki_id: str | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    base = ["claim.extraction_method = 'ai_candidate'"]
    base_params: list[Any] = []
    if queue:
        base.extend([
            "source_run.scope_json ->> 'category_name' = %s",
            "source_run.scope_json ->> 'stage' IN ('ai_candidate_extraction', 'ai_feature_extraction')",
        ])
        base_params.append(category_name)
    elif selected_run:
        base.append("claim.source_run_id = %s")
        base_params.append(selected_run["run_id"])
    if model_id:
        base.append(
            "EXISTS (SELECT 1 FROM kb_parameter_claim_model AS model_filter "
            "WHERE model_filter.claim_id = claim.claim_id AND model_filter.model_id = %s)"
        )
        base_params.append(model_id)
    if feature_id:
        base.append("claim.feature_id = %s")
        base_params.append(feature_id)
    if wiki_id:
        base.append("claim.question_wiki_id ILIKE %s")
        base_params.append(f"%{wiki_id}%")
    where_clause = " AND ".join(base)
    cursor.execute(
        f"""
        SELECT DISTINCT model.model_id, claim.feature_id
        FROM kb_parameter_claim AS claim
        JOIN parameter_check_run AS source_run ON source_run.run_id = claim.source_run_id
        JOIN kb_parameter_claim_model AS model ON model.claim_id = claim.claim_id
        WHERE {where_clause}
        ORDER BY model.model_id, claim.feature_id
        """,
        base_params,
    )
    filter_rows = [dict(row) for row in cursor.fetchall()]
    cursor.execute(
        f"""
        SELECT COALESCE(assessment.review_status, 'unreviewed') AS review_status, COUNT(*) AS count
        FROM kb_parameter_claim AS claim
        JOIN parameter_check_run AS source_run ON source_run.run_id = claim.source_run_id
        LEFT JOIN parameter_ai_candidate_assessment AS assessment ON assessment.claim_id = claim.claim_id
        WHERE {where_clause}
        GROUP BY COALESCE(assessment.review_status, 'unreviewed')
        """,
        base_params,
    )
    review_status_counts = {str(row["review_status"]): int(row["count"]) for row in cursor.fetchall()}
    cursor.execute(
        f"""
        SELECT COUNT(*) AS count
        FROM kb_parameter_claim AS claim
        JOIN parameter_check_run AS source_run ON source_run.run_id = claim.source_run_id
        LEFT JOIN parameter_ai_candidate_assessment AS assessment ON assessment.claim_id = claim.claim_id
        WHERE {where_clause}
          AND (
              (assessment.ai_verdict = 'likely_consistent' AND assessment.comparison_verdict = 'consistent')
              OR (assessment.ai_verdict = 'likely_inconsistent' AND assessment.comparison_verdict = 'conflict')
          )
        """,
        base_params,
    )
    ai_snapshot_agree_count = int(cursor.fetchone()["count"])
    cursor.execute(
        f"""
        SELECT COUNT(*) AS count
        FROM kb_parameter_claim AS claim
        JOIN parameter_check_run AS source_run ON source_run.run_id = claim.source_run_id
        WHERE {where_clause}
        """,
        base_params,
    )
    total = int(cursor.fetchone()["count"])
    cursor.execute(
        f"""
        SELECT claim.claim_id::text, claim.question_wiki_id, claim.kb_revision, claim.feature_id,
               claim.asserted_value, claim.normalized_value, claim.evidence_text,
               claim.binding_status, claim.created_at,
               assessment.ai_verdict, assessment.ai_reason_code, assessment.ai_reason,
               assessment.comparison_verdict, assessment.comparison_reason, assessment.comparison_values_json,
               assessment.review_status, assessment.final_verdict, assessment.review_reason,
               assessment.reviewed_by, assessment.reviewed_at,
               source_run.run_id::text AS source_run_id, source_run.snapshot_id AS source_snapshot_id,
               source_run.scope_json AS source_scope_json, source_run.status AS source_run_status,
               source_snapshot.content_json AS source_snapshot_content,
               knowledge.question AS knowledge_question, knowledge.answer AS knowledge_answer,
               ARRAY_AGG(model.model_id ORDER BY model.model_id) AS model_ids
        FROM kb_parameter_claim AS claim
        JOIN parameter_check_run AS source_run ON source_run.run_id = claim.source_run_id
        LEFT JOIN parameter_snapshot AS source_snapshot ON source_snapshot.snapshot_id = source_run.snapshot_id
        LEFT JOIN knowledge_base_v1 AS knowledge ON knowledge.question_wiki_id = claim.question_wiki_id
        JOIN kb_parameter_claim_model AS model ON model.claim_id = claim.claim_id
        LEFT JOIN parameter_ai_candidate_assessment AS assessment ON assessment.claim_id = claim.claim_id
        WHERE {where_clause}
        GROUP BY claim.claim_id, claim.question_wiki_id, claim.kb_revision, claim.feature_id,
               claim.asserted_value, claim.normalized_value, claim.evidence_text,
               claim.binding_status, claim.created_at,
               assessment.ai_verdict, assessment.ai_reason_code, assessment.ai_reason,
               assessment.comparison_verdict, assessment.comparison_reason, assessment.comparison_values_json,
               assessment.review_status, assessment.final_verdict, assessment.review_reason,
               assessment.reviewed_by, assessment.reviewed_at,
               source_run.run_id, source_run.snapshot_id, source_run.scope_json, source_run.status,
               source_snapshot.content_json, knowledge.question, knowledge.answer
        ORDER BY claim.question_wiki_id, claim.feature_id, claim.created_at
        LIMIT %s OFFSET %s
        """,
        [*base_params, page_size, (page - 1) * page_size],
    )
    candidates = []
    for row in cursor.fetchall():
        candidate = dict(row)
        source_content = candidate.pop("source_snapshot_content", None) or {}
        candidate["knowledge_content"] = _parameter_check_knowledge_content(
            candidate.pop("knowledge_question", ""),
            candidate.pop("knowledge_answer", ""),
            candidate.get("kb_revision"),
        )
        source_models = {
            str(model.get("id") or ""): str(model.get("model_name") or model.get("model_code") or model.get("id") or "")
            for model in source_content.get("models") or []
        }
        source_features = {
            str(feature.get("id") or ""): str(feature.get("name") or feature.get("id") or "")
            for feature in source_content.get("features") or []
        }
        source_scope = candidate.get("source_scope_json") or {}
        candidate["model_ids"] = [str(item) for item in candidate.get("model_ids") or []]
        candidate["model_names"] = [source_models.get(item) or model_names.get(item, item) for item in candidate["model_ids"]]
        candidate["feature_name"] = source_features.get(str(candidate["feature_id"])) or feature_names.get(str(candidate["feature_id"]), str(candidate["feature_id"]))
        candidate["source_feature_name"] = source_scope.get("feature_name") or candidate["feature_name"]
        candidate["review_status"] = candidate.get("review_status") or "unreviewed"
        candidate["comparison_values"] = [
            {
                **value,
                "model_name": value.get("model_name") or source_models.get(str(value.get("model_id") or "")) or model_names.get(str(value.get("model_id") or ""), str(value.get("model_id") or "")),
            }
            for value in (candidate.pop("comparison_values_json", None) or [])
            if isinstance(value, dict)
        ]
        candidates.append(candidate)
    result_counts = selected_run.get("result_counts_json") if selected_run else {}
    running_feature_runs = [
        _parameter_check_run_payload(row)
        for row in run_rows
        if (row.get("scope_json") or {}).get("stage") == "ai_feature_extraction" and row.get("status") == "running"
    ]
    model_ids = sorted({str(row["model_id"]) for row in filter_rows})
    feature_ids = sorted({str(row["feature_id"]) for row in filter_rows})
    return {
        "category_name": category_name,
        "snapshot": snapshot,
        "runs": [_parameter_check_run_payload(row) for row in run_rows],
        "selected_run": _parameter_check_run_payload(selected_run) if selected_run else None,
        "view_mode": "ai_candidate_queue" if queue else "ai_candidates",
        "summary": {
            "candidate_count": total if queue else int(result_counts.get("candidate_count") or 0),
            "proposed_claim_count": total if queue else int(result_counts.get("proposed_claim_count") or 0),
            "existing_proposed_claim_count": int(result_counts.get("existing_proposed_claim_count") or 0),
            "remaining_knowledge_count": int(result_counts.get("remaining_knowledge_count") or 0),
            "review_status_counts": review_status_counts,
            "ai_snapshot_agree_count": ai_snapshot_agree_count,
            "running_scan_count": len(running_feature_runs),
            "running_scans": running_feature_runs,
        },
        "filter_options": {
            "models": [{"id": item, "name": model_names.get(item, item)} for item in model_ids],
            "features": [{"id": item, "name": feature_names.get(item, item)} for item in feature_ids],
        },
        "scan_feature_options": _parameter_scan_feature_options(feature_names),
        "findings": [],
        "candidates": candidates,
        "pagination": {"page": page, "page_size": page_size, "total": total},
    }


def get_parameter_check_overview(
    connection,
    *,
    category_name: str,
    run_id: str | None = None,
    result_status: str | None = None,
    resolution_status: str | None = None,
    model_id: str | None = None,
    feature_id: str | None = None,
    wiki_id: str | None = None,
    ai_view: str = "queue",
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    with connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT run_id, run_type, snapshot_id, scope_json, status, result_counts_json,
                   created_by, created_at, completed_at
            FROM parameter_check_run
            WHERE scope_json ->> 'category_name' = %s
            ORDER BY created_at DESC
            LIMIT 20
            """,
            (category_name,),
        )
        run_rows = [dict(row) for row in cursor.fetchall()]

        selected_run = None
        if run_id:
            try:
                uuid.UUID(run_id)
            except (TypeError, ValueError) as exc:
                raise ValueError("校对运行标识格式不正确。") from exc
            selected_run = next((row for row in run_rows if str(row["run_id"]) == run_id), None)
            if selected_run is None:
                cursor.execute(
                    """
                    SELECT run_id, run_type, snapshot_id, scope_json, status, result_counts_json,
                           created_by, created_at, completed_at
                    FROM parameter_check_run
                    WHERE run_id = %s AND scope_json ->> 'category_name' = %s
                    """,
                    (run_id, category_name),
                )
                row = cursor.fetchone()
                selected_run = dict(row) if row else None
            if selected_run is None:
                raise ValueError("未找到该品类的参数校对运行。")
        else:
            selected_run = next(
                (
                    row
                    for row in run_rows
                    if row.get("status") == "completed"
                    and (row.get("scope_json") or {}).get("stage") == "numeric_comparison"
                ),
                run_rows[0] if run_rows else None,
            )

        snapshot_id = selected_run.get("snapshot_id") if selected_run else None
        if snapshot_id:
            cursor.execute(
                """
                SELECT snapshot_id, source_version, content_hash, synced_at, content_json
                FROM parameter_snapshot
                WHERE snapshot_id = %s
                """,
                (snapshot_id,),
            )
        else:
            cursor.execute(
                """
                SELECT snapshot_id, source_version, content_hash, synced_at, content_json
                FROM parameter_snapshot
                WHERE sync_status = 'ready'
                  AND content_json @> %s::jsonb
                ORDER BY synced_at DESC
                LIMIT 1
                """,
                (Json({"categories": [{"name": category_name}]}),),
            )
        snapshot_row = cursor.fetchone()
        snapshot, model_names, feature_names = _parameter_check_snapshot_metadata(
            dict(snapshot_row) if snapshot_row else None
        )
        scan_feature_options = _parameter_scan_feature_options(feature_names)

        if ai_view == "queue":
            return _get_ai_candidate_overview(
                cursor,
                category_name=category_name,
                snapshot=snapshot,
                model_names=model_names,
                feature_names=feature_names,
                run_rows=run_rows,
                selected_run=None,
                queue=True,
                model_id=model_id,
                feature_id=feature_id,
                wiki_id=wiki_id,
                page=page,
                page_size=page_size,
            )

        if selected_run and (selected_run.get("scope_json") or {}).get("stage") in {"ai_candidate_extraction", "ai_feature_extraction"}:
            if ai_view == "audit":
                return _get_ai_scan_audit_overview(
                    cursor,
                    category_name=category_name,
                    snapshot=snapshot,
                    run_rows=run_rows,
                    selected_run=selected_run,
                    wiki_id=wiki_id,
                    page=page,
                    page_size=page_size,
                )
            return _get_ai_candidate_overview(
                cursor,
                category_name=category_name,
                snapshot=snapshot,
                model_names=model_names,
                feature_names=feature_names,
                run_rows=run_rows,
                selected_run=selected_run,
                queue=False,
                model_id=model_id,
                feature_id=feature_id,
                wiki_id=wiki_id,
                page=page,
                page_size=page_size,
            )

        base = ["finding.run_id = %s"]
        base_params: list[Any] = [selected_run["run_id"]] if selected_run else []
        if selected_run and result_status:
            base.append("finding.result_status = %s")
            base_params.append(result_status)
        if selected_run and resolution_status:
            base.append("finding.resolution_status = %s")
            base_params.append(resolution_status)
        if selected_run and model_id:
            base.append("finding.model_id = %s")
            base_params.append(model_id)
        if selected_run and feature_id:
            base.append("finding.feature_id = %s")
            base_params.append(feature_id)
        if selected_run and wiki_id:
            base.append("finding.question_wiki_id ILIKE %s")
            base_params.append(f"%{wiki_id}%")

        if not selected_run:
            return {
                "category_name": category_name,
                "snapshot": snapshot,
                "runs": [_parameter_check_run_payload(row) for row in run_rows],
                "selected_run": None,
                "summary": {
                    "finding_count": 0,
                    "result_status_counts": {},
                    "resolution_status_counts": {},
                },
                "filter_options": {"models": [], "features": []},
                "scan_feature_options": scan_feature_options,
                "findings": [],
                "pagination": {"page": page, "page_size": page_size, "total": 0},
            }

        cursor.execute(
            """
            SELECT result_status, COUNT(*) AS count
            FROM parameter_check_finding
            WHERE run_id = %s
            GROUP BY result_status
            """,
            (selected_run["run_id"],),
        )
        result_status_counts = {str(row["result_status"]): int(row["count"]) for row in cursor.fetchall()}
        cursor.execute(
            """
            SELECT resolution_status, COUNT(*) AS count
            FROM parameter_check_finding
            WHERE run_id = %s
            GROUP BY resolution_status
            """,
            (selected_run["run_id"],),
        )
        resolution_status_counts = {str(row["resolution_status"]): int(row["count"]) for row in cursor.fetchall()}
        cursor.execute(
            """
            SELECT DISTINCT model_id, feature_id
            FROM parameter_check_finding
            WHERE run_id = %s
            ORDER BY model_id, feature_id
            """,
            (selected_run["run_id"],),
        )
        filter_rows = [dict(row) for row in cursor.fetchall()]

        where_clause = " AND ".join(base)
        cursor.execute(
            f"SELECT COUNT(*) AS count FROM parameter_check_finding AS finding WHERE {where_clause}",
            base_params,
        )
        total = int(cursor.fetchone()["count"])
        cursor.execute(
            f"""
            SELECT finding.finding_id::text, finding.question_wiki_id, finding.model_id,
                   finding.feature_id, finding.asserted_value, finding.canonical_value,
                   finding.feature_value_version, finding.result_status, finding.severity,
                   finding.reason, finding.resolution_status, finding.resolution_note,
                   finding.created_at, finding.updated_at, claim.evidence_text, claim.kb_revision,
                   knowledge.question AS knowledge_question, knowledge.answer AS knowledge_answer
            FROM parameter_check_finding AS finding
            LEFT JOIN kb_parameter_claim AS claim ON claim.claim_id = finding.claim_id
            LEFT JOIN knowledge_base_v1 AS knowledge ON knowledge.question_wiki_id = finding.question_wiki_id
            WHERE {where_clause}
            ORDER BY CASE finding.severity WHEN 'error' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END,
                     finding.question_wiki_id, finding.feature_id, finding.model_id
            LIMIT %s OFFSET %s
            """,
            [*base_params, page_size, (page - 1) * page_size],
        )
        findings = []
        for row in cursor.fetchall():
            finding = dict(row)
            finding["knowledge_content"] = _parameter_check_knowledge_content(
                finding.pop("knowledge_question", ""),
                finding.pop("knowledge_answer", ""),
                finding.get("kb_revision"),
            )
            finding["model_name"] = model_names.get(str(finding["model_id"]), str(finding["model_id"]))
            finding["feature_name"] = feature_names.get(str(finding["feature_id"]), str(finding["feature_id"]))
            findings.append(finding)

    model_ids = sorted({str(row["model_id"]) for row in filter_rows})
    feature_ids = sorted({str(row["feature_id"]) for row in filter_rows})
    return {
        "category_name": category_name,
        "snapshot": snapshot,
        "runs": [_parameter_check_run_payload(row) for row in run_rows],
        "selected_run": _parameter_check_run_payload(selected_run),
        "summary": {
            "finding_count": sum(result_status_counts.values()),
            "result_status_counts": result_status_counts,
            "resolution_status_counts": resolution_status_counts,
        },
        "filter_options": {
            "models": [{"id": item, "name": model_names.get(item, item)} for item in model_ids],
            "features": [{"id": item, "name": feature_names.get(item, item)} for item in feature_ids],
        },
        "scan_feature_options": scan_feature_options,
        "findings": findings,
        "pagination": {"page": page, "page_size": page_size, "total": total},
    }


def register_parameter_check_routes(app, login_required, product_catalog_loader) -> None:
    from flask import jsonify, request
    from flask_login import current_user

    def actor() -> str:
        return current_user.username if current_user.is_authenticated else "system"

    def category_models(category_name: str) -> list[str]:
        catalog = product_catalog_loader()
        models = catalog.get(category_name) if isinstance(catalog, dict) else None
        if not isinstance(models, list):
            raise ValueError(f"8085 型号目录中不存在品类：{category_name}")
        return [str(model).strip() for model in models if str(model).strip()]

    @app.route("/api/kb/parameter-check/snapshots/sync", methods=["POST"])
    @login_required
    def sync_parameter_snapshot():
        payload = request.get_json(silent=True) or {}
        category_name = str(payload.get("category_name") or "扫地机").strip()
        try:
            snapshot = fetch_catalog_snapshot(category_name)
            connection = connect_main_database()
            try:
                store_snapshot(connection, snapshot, actor())
            finally:
                connection.close()
            return jsonify({
                "success": True,
                "snapshot_id": snapshot["snapshot_id"],
                "source_version": snapshot["source_version"],
                "counts": {name: len(snapshot.get(name) or []) for name in ("models", "features", "feature_values")},
            })
        except requests.RequestException as exc:
            return jsonify({"success": False, "message": f"参数清单快照不可用：{exc}"}), 503
        except (RuntimeError, ValueError) as exc:
            return jsonify({"success": False, "message": str(exc)}), 422

    @app.route("/api/kb/parameter-check/model-alias-bindings/refresh", methods=["POST"])
    @login_required
    def refresh_parameter_model_bindings():
        payload = request.get_json(silent=True) or {}
        category_name = str(payload.get("category_name") or "扫地机").strip()
        try:
            connection = connect_main_database()
            try:
                summary = refresh_model_bindings(
                    connection,
                    category_name=category_name,
                    catalog_models=category_models(category_name),
                    actor=actor(),
                )
            finally:
                connection.close()
            return jsonify({"success": True, "category_name": category_name, "summary": summary})
        except (RuntimeError, ValueError) as exc:
            return jsonify({"success": False, "message": str(exc)}), 422

    @app.route("/api/kb/parameter-check/model-alias-bindings", methods=["GET"])
    @login_required
    def get_parameter_model_bindings():
        category_name = str(request.args.get("category_name") or "扫地机").strip()
        status = str(request.args.get("status") or "").strip() or None
        if status not in {None, "confirmed", "pending", "rejected"}:
            return jsonify({"success": False, "message": "status 不合法。"}), 422
        try:
            connection = connect_main_database()
            try:
                bindings = list_model_bindings(connection, category_name, status)
            finally:
                connection.close()
            return jsonify({"success": True, "bindings": bindings})
        except RuntimeError as exc:
            return jsonify({"success": False, "message": str(exc)}), 422

    @app.route("/api/kb/parameter-check/model-alias-bindings/<binding_id>/decision", methods=["POST"])
    @login_required
    def decide_parameter_model_binding(binding_id: str):
        payload = request.get_json(silent=True) or {}
        status = str(payload.get("status") or "").strip()
        note = str(payload.get("note") or "").strip()
        try:
            connection = connect_main_database()
            try:
                binding = decide_model_binding(connection, binding_id, status, actor(), note)
            finally:
                connection.close()
            if binding is None:
                return jsonify({"success": False, "message": "型号映射不存在。"}), 404
            return jsonify({"success": True, "binding": binding})
        except ValueError as exc:
            return jsonify({"success": False, "message": str(exc)}), 422

    @app.route("/api/kb/parameter-check/runs", methods=["POST"])
    @login_required
    def create_parameter_check_run():
        payload = request.get_json(silent=True) or {}
        category_name = str(payload.get("category_name") or "扫地机").strip()
        mode = str(payload.get("mode") or "extract").strip()
        try:
            connection = connect_main_database()
            try:
                if mode == "extract":
                    result = run_historical_numeric_claim_scan(
                        connection,
                        category_name=category_name,
                        actor=actor(),
                    )
                elif mode == "compare":
                    result = run_historical_numeric_comparison(
                        connection,
                        category_name=category_name,
                        actor=actor(),
                    )
                elif mode == "ai_extract":
                    try:
                        batch_size = int(payload.get("batch_size") or AI_CANDIDATE_BATCH_SIZE)
                    except (TypeError, ValueError) as exc:
                        raise ValueError("AI 候选提取批次必须是整数。") from exc
                    result = run_historical_ai_candidate_scan(
                        connection,
                        category_name=category_name,
                        actor=actor(),
                        batch_size=batch_size,
                    )
                elif mode == "ai_feature_extract":
                    feature_id = str(payload.get("feature_id") or "").strip()
                    if not feature_id:
                        raise ValueError("请选择要扫描的参数功能。")
                    result, job = create_historical_ai_feature_scan(
                        connection,
                        category_name=category_name,
                        feature_id=feature_id,
                        actor=actor(),
                    )
                else:
                    raise ValueError("mode 只能是 extract、compare、ai_extract 或 ai_feature_extract。")
            finally:
                connection.close()
            if mode == "ai_feature_extract":
                try:
                    threading.Thread(
                        target=run_historical_ai_feature_scan_worker,
                        args=(job,),
                        daemon=True,
                        name=f"parameter-ai-{result['feature_id']}",
                    ).start()
                except Exception as exc:
                    _mark_feature_ai_scan_launch_failed(
                        run_id=str(result["run_id"]),
                        category_name=category_name,
                        feature_id=str(result["feature_id"]),
                        result_counts=dict(result.get("result_counts") or {}),
                        error=exc,
                    )
                    raise RuntimeError("后台参数功能扫描未能启动，本次运行已标记为失败。") from exc
            return jsonify({"success": True, "mode": mode, **result})
        except (RuntimeError, ValueError) as exc:
            return jsonify({"success": False, "message": str(exc)}), 422

    @app.route("/api/kb/parameter-check/runs/<run_id>", methods=["GET"])
    @login_required
    def get_parameter_check_run_route(run_id: str):
        try:
            connection = connect_main_database()
            try:
                run = get_parameter_check_run(connection, run_id)
            finally:
                connection.close()
            if run is None:
                return jsonify({"success": False, "message": "参数校对任务不存在。"}), 404
            return jsonify({"success": True, "run": run})
        except RuntimeError as exc:
            return jsonify({"success": False, "message": str(exc)}), 422

    @app.route("/api/kb/parameter-check/candidates/<claim_id>/review", methods=["POST"])
    @login_required
    def review_parameter_ai_candidate(claim_id: str):
        payload = request.get_json(silent=True) or {}
        decision = str(payload.get("decision") or "").strip()
        final_verdict = str(payload.get("final_verdict") or "").strip() or None
        review_reason = str(payload.get("review_reason") or "")
        try:
            connection = connect_main_database()
            try:
                review = decide_ai_candidate_review(
                    connection,
                    claim_id=claim_id,
                    decision=decision,
                    final_verdict=final_verdict,
                    review_reason=review_reason,
                    actor=actor(),
                )
            finally:
                connection.close()
            return jsonify({"success": True, "review": review})
        except (RuntimeError, ValueError) as exc:
            return jsonify({"success": False, "message": str(exc)}), 422

    @app.route("/api/kb/parameter-check/overview", methods=["GET"])
    @login_required
    def get_parameter_check_overview_route():
        category_name = str(request.args.get("category_name") or "扫地机").strip()
        run_id = str(request.args.get("run_id") or "").strip() or None
        result_status = str(request.args.get("result_status") or "").strip() or None
        resolution_status = str(request.args.get("resolution_status") or "").strip() or None
        model_id = str(request.args.get("model_id") or "").strip() or None
        feature_id = str(request.args.get("feature_id") or "").strip() or None
        wiki_id = str(request.args.get("wiki_id") or "").strip() or None
        ai_view = str(request.args.get("ai_view") or "queue").strip() or "queue"
        try:
            page = int(request.args.get("page") or 1)
            page_size = int(request.args.get("page_size") or 50)
        except ValueError:
            return jsonify({"success": False, "message": "页码和每页条数必须是整数。"}), 422
        if page < 1 or page_size < 1 or page_size > 100:
            return jsonify({"success": False, "message": "页码必须大于 0，每页条数范围为 1 到 100。"}), 422
        if result_status and result_status not in PARAMETER_CHECK_RESULT_STATUSES:
            return jsonify({"success": False, "message": "比较状态不合法。"}), 422
        if resolution_status and resolution_status not in PARAMETER_CHECK_RESOLUTION_STATUSES:
            return jsonify({"success": False, "message": "人工处理状态不合法。"}), 422
        if ai_view not in {"queue", "candidates", "audit"}:
            return jsonify({"success": False, "message": "AI 视图类型不合法。"}), 422
        try:
            connection = connect_main_database()
            try:
                overview = get_parameter_check_overview(
                    connection,
                    category_name=category_name,
                    run_id=run_id,
                    result_status=result_status,
                    resolution_status=resolution_status,
                    model_id=model_id,
                    feature_id=feature_id,
                    wiki_id=wiki_id,
                    ai_view=ai_view,
                    page=page,
                    page_size=page_size,
                )
            finally:
                connection.close()
            return jsonify({"success": True, **overview})
        except (RuntimeError, ValueError) as exc:
            return jsonify({"success": False, "message": str(exc)}), 422
