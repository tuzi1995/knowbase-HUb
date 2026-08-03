"""Phase-one, sidecar knowledge-graph support for KnowBase Hub.

The graph tables are deliberately independent from the knowledge and product
matrix source tables.  Candidates never change source knowledge, and every
state transition is recorded in ``kg_edge_events``.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


NODE_TYPES = {"knowledge", "product_model", "product_category", "topic"}
RELATION_TYPES = {
    "APPLIES_TO",
    "BELONGS_TO",
    "RELATED_TO",
    "OVERLAPS_WITH",
    "DUPLICATES",
    "SPECIALIZES",
    "EXCEPTION_TO",
    "CONFLICTS_WITH",
    "PARENT_TOPIC_OF",
    "ROUTES_TO",
    "PREREQUISITE_FOR",
    "SUBPROCEDURE_OF",
}
LEGACY_RELATION_TYPES = RELATION_TYPES - {"PREREQUISITE_FOR", "SUBPROCEDURE_OF"}
REVIEW_STATUSES = {"candidate", "confirmed", "rejected", "expired"}
GENERATED_BY = {"source_field", "rule", "ai", "human"}
REVISION_KINDS = {"original", "human_adjustment", "source_revalidation"}
KNOWLEDGE_RELATION_TYPES = RELATION_TYPES - {"APPLIES_TO", "BELONGS_TO"}
BATCH_CONFIRMATION_PHRASE = "写入候选"
BATCH_ROLLBACK_CONFIRMATION_PHRASE = "回退候选批次"
TOPIC_ASSIGNMENT_CONFIRMATION_PHRASE = "确认主题校对"
TOPIC_VOCABULARY_VERSION = "v1-pilot"
CONTROLLED_TOPIC_VOCABULARY_V1 = (
    {
        "topic_id": "ROBOT_BASE_STATION",
        "display_name": "基站、上下水与集尘",
        "allowed_categories": ("扫地机",),
        "description": "扫地机器人基站、上下水、集尘和洗布相关知识。",
        "include_rules": "纳入基站、上下水安装、集尘、洗布和基站兼容性。",
        "exclude_rules": "不纳入机器人本体充电、地图导航或单独的拖布材质问题。",
    },
    {
        "topic_id": "ROBOT_NAVIGATION",
        "display_name": "地图、定位与避障",
        "allowed_categories": ("扫地机",),
        "description": "扫地机器人建图、地图、定位、路径和避障相关知识。",
        "include_rules": "纳入建图、地图管理、定位、路径、避障和禁区。",
        "exclude_rules": "不纳入 App 账号、网络配网或基站维护。",
    },
    {
        "topic_id": "WASHER_WASH_DRY",
        "display_name": "洗涤、洗烘与烘干",
        "allowed_categories": ("洗衣机",),
        "description": "洗衣机洗涤、洗烘、烘干和衣物护理流程知识。",
        "include_rules": "纳入洗涤程序、洗烘逻辑、烘干方式、烘干时长和衣物护理。",
        "exclude_rules": "不纳入进排水故障、错误代码或 App 账号问题。",
    },
    {
        "topic_id": "FLOOR_SELF_CLEAN_DRY",
        "display_name": "自清洁与烘干",
        "allowed_categories": ("洗地机",),
        "description": "洗地机自清洁、烘干和清洁后维护知识。",
        "include_rules": "纳入自清洁、烘干、清洗流程和清洁后维护。",
        "exclude_rules": "不纳入洗衣机烘干、水箱水路或刷头规格问题。",
    },
    {
        "topic_id": "FLOOR_WATER_SYSTEM",
        "display_name": "清污水箱与水路",
        "allowed_categories": ("洗地机",),
        "description": "洗地机清水箱、污水箱、水路和供排水相关知识。",
        "include_rules": "纳入清污水箱、进排水、漏水和水位问题。",
        "exclude_rules": "不纳入洗衣机进排水、滚刷或自清洁流程。",
    },
    {
        "topic_id": "VACUUM_BRUSH_COLLECTION",
        "display_name": "刷头、集尘与尘袋",
        "allowed_categories": ("吸尘器",),
        "description": "吸尘器刷头、集尘、尘桶和尘袋相关知识。",
        "include_rules": "纳入地刷、床刷、刷头、集尘、尘桶和尘袋。",
        "exclude_rules": "不纳入洗地机滚刷、扫地机基站或电池续航问题。",
    },
)
SCOPE_DIMENSIONS = {
    "topic",
    "subtopic",
    "component",
    "password_type",
    "product_scope",
    "product_categories",
    "product_series",
    "product_models",
    "excluded_product_models",
    "all_models_explicit",
    "product_catalog_snapshot",
    "scenario",
    "user_role",
    "channel",
    "version_scope",
    "preconditions",
    "connection_state",
}
PRODUCT_SCOPE_DIMENSIONS = {
    "product_scope",
    "product_categories",
    "product_series",
    "product_models",
    "excluded_product_models",
    "all_models_explicit",
    "product_catalog_snapshot",
}
CLAIM_TEXT_FIELDS = {
    "conclusion",
    "coverage_evidence",
    "exception_condition",
    "intent",
    "component",
    "outcome",
    "claim_key",
    "claim_value",
}
CLAIM_LIST_FIELDS = {"preconditions", "procedure_steps", "outcome_keys", "precondition_keys"}
ANSWER_DERIVED_CLAIM_FIELDS = {
    "coverage_evidence",
    "exception_condition",
    "outcome",
    "claim_key",
    "claim_value",
    "mutually_exclusive",
    "preconditions",
    "procedure_steps",
    "outcome_keys",
    "precondition_keys",
    "navigation_only",
}


SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS kg_nodes (
    node_id TEXT PRIMARY KEY,
    node_type TEXT NOT NULL,
    business_key TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    aliases_json TEXT NOT NULL DEFAULT '[]',
    scope_json TEXT NOT NULL DEFAULT '{}',
    claims_json TEXT NOT NULL DEFAULT '{}',
    properties_json TEXT NOT NULL DEFAULT '{}',
    source_system TEXT NOT NULL,
    source_version TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(node_type, business_key),
    CHECK(node_type IN ('knowledge', 'product_model', 'product_category', 'topic')),
    CHECK(status IN ('active', 'inactive', 'deleted'))
);

CREATE INDEX IF NOT EXISTS idx_kg_nodes_business_key ON kg_nodes (business_key);
CREATE INDEX IF NOT EXISTS idx_kg_nodes_type_status ON kg_nodes (node_type, status);

CREATE TABLE IF NOT EXISTS kg_edges (
    edge_id TEXT PRIMARY KEY,
    from_node_id TEXT NOT NULL,
    to_node_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    scope_basis_json TEXT NOT NULL,
    confidence REAL NOT NULL,
    review_status TEXT NOT NULL DEFAULT 'candidate',
    generated_by TEXT NOT NULL,
    provenance_json TEXT NOT NULL,
    source_version TEXT NOT NULL DEFAULT '',
    source_content_hashes_json TEXT NOT NULL DEFAULT '{}',
    review_note TEXT NOT NULL DEFAULT '',
    reviewed_by TEXT NOT NULL DEFAULT '',
    reviewed_at TEXT,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    supersedes_edge_id TEXT,
    revision_no INTEGER NOT NULL DEFAULT 1,
    revision_kind TEXT NOT NULL DEFAULT 'original',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(from_node_id) REFERENCES kg_nodes(node_id),
    FOREIGN KEY(to_node_id) REFERENCES kg_nodes(node_id),
    CHECK(from_node_id <> to_node_id),
    CHECK(relation_type IN ('APPLIES_TO', 'BELONGS_TO', 'RELATED_TO', 'OVERLAPS_WITH', 'DUPLICATES', 'SPECIALIZES', 'EXCEPTION_TO', 'CONFLICTS_WITH', 'PARENT_TOPIC_OF', 'ROUTES_TO', 'PREREQUISITE_FOR', 'SUBPROCEDURE_OF')),
    CHECK(review_status IN ('candidate', 'confirmed', 'rejected', 'expired')),
    CHECK(generated_by IN ('source_field', 'rule', 'ai', 'human')),
    CHECK(revision_kind IN ('original', 'human_adjustment', 'source_revalidation')),
    CHECK(revision_no >= 1),
    CHECK(confidence >= 0 AND confidence <= 1)
);

CREATE INDEX IF NOT EXISTS idx_kg_edges_from ON kg_edges (from_node_id, review_status);
CREATE INDEX IF NOT EXISTS idx_kg_edges_to ON kg_edges (to_node_id, review_status);
CREATE INDEX IF NOT EXISTS idx_kg_edges_relation_review ON kg_edges (relation_type, review_status);

CREATE TABLE IF NOT EXISTS kg_review_batches (
    batch_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    topics_json TEXT NOT NULL,
    max_pairs_per_topic INTEGER NOT NULL,
    source_snapshot_json TEXT NOT NULL,
    confirmation_phrase TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    rolled_back_by TEXT NOT NULL DEFAULT '',
    rolled_back_at TEXT,
    rollback_note TEXT NOT NULL DEFAULT '',
    CHECK(status IN ('active', 'rolled_back')),
    CHECK(max_pairs_per_topic >= 1 AND max_pairs_per_topic <= 20)
);

CREATE INDEX IF NOT EXISTS idx_kg_review_batches_status_created ON kg_review_batches (status, created_at);

CREATE TABLE IF NOT EXISTS kg_review_batch_edges (
    batch_id TEXT NOT NULL,
    edge_id TEXT NOT NULL,
    cluster_key TEXT NOT NULL,
    rank INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(batch_id, edge_id),
    FOREIGN KEY(batch_id) REFERENCES kg_review_batches(batch_id),
    FOREIGN KEY(edge_id) REFERENCES kg_edges(edge_id),
    CHECK(rank >= 1)
);

CREATE INDEX IF NOT EXISTS idx_kg_review_batch_edges_edge ON kg_review_batch_edges (edge_id);

CREATE TABLE IF NOT EXISTS kg_topic_definitions (
    topic_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    allowed_categories_json TEXT NOT NULL,
    description TEXT NOT NULL,
    include_rules TEXT NOT NULL,
    exclude_rules TEXT NOT NULL,
    lifecycle TEXT NOT NULL DEFAULT 'draft',
    vocabulary_version TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK(lifecycle IN ('draft', 'active', 'deprecated'))
);

CREATE INDEX IF NOT EXISTS idx_kg_topic_definitions_lifecycle
    ON kg_topic_definitions (lifecycle, topic_id);

CREATE TABLE IF NOT EXISTS kg_topic_definition_events (
    event_id TEXT PRIMARY KEY,
    topic_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    before_json TEXT NOT NULL DEFAULT '{}',
    after_json TEXT NOT NULL DEFAULT '{}',
    review_note TEXT NOT NULL,
    actor TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(topic_id) REFERENCES kg_topic_definitions(topic_id),
    CHECK(event_type IN ('topic_seeded', 'topic_created', 'topic_updated', 'topic_deprecated'))
);

CREATE INDEX IF NOT EXISTS idx_kg_topic_definition_events_topic_created
    ON kg_topic_definition_events (topic_id, created_at);

CREATE TABLE IF NOT EXISTS kg_topic_assignments (
    assignment_id TEXT PRIMARY KEY,
    wiki_id TEXT NOT NULL UNIQUE,
    topic_id TEXT,
    topic TEXT NOT NULL,
    vocabulary_version TEXT NOT NULL DEFAULT '',
    review_note TEXT NOT NULL,
    source_content_hash TEXT NOT NULL,
    source_version TEXT NOT NULL DEFAULT '',
    assigned_by TEXT NOT NULL,
    assigned_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_kg_topic_assignments_topic ON kg_topic_assignments (topic);

CREATE TABLE IF NOT EXISTS kg_topic_assignment_events (
    event_id TEXT PRIMARY KEY,
    assignment_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    previous_topic_id TEXT NOT NULL DEFAULT '',
    current_topic_id TEXT NOT NULL DEFAULT '',
    vocabulary_version TEXT NOT NULL DEFAULT '',
    previous_topic TEXT NOT NULL DEFAULT '',
    current_topic TEXT NOT NULL,
    review_note TEXT NOT NULL,
    actor TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(assignment_id) REFERENCES kg_topic_assignments(assignment_id),
    CHECK(event_type IN ('topic_assigned', 'topic_reassigned'))
);

CREATE INDEX IF NOT EXISTS idx_kg_topic_assignment_events_assignment_created
    ON kg_topic_assignment_events (assignment_id, created_at);

CREATE TABLE IF NOT EXISTS kg_edge_events (
    event_id TEXT PRIMARY KEY,
    edge_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    from_review_status TEXT,
    to_review_status TEXT,
    event_data_json TEXT NOT NULL DEFAULT '{}',
    actor TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(edge_id) REFERENCES kg_edges(edge_id)
);

CREATE INDEX IF NOT EXISTS idx_kg_edge_events_edge_created ON kg_edge_events (edge_id, created_at);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _json_load(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value in (None, ""):
        return default
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError):
        return default
    return parsed


def _row_dict(row: sqlite3.Row | dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def _source_product_names(source: dict[str, Any]) -> list[str]:
    raw = source.get("product_names_json", source.get("product_names", []))
    parsed = _json_load(raw, raw)
    if isinstance(parsed, str):
        values = parsed.replace("，", ",").split(",")
    elif isinstance(parsed, (list, tuple, set)):
        values = parsed
    else:
        values = []
    return list(dict.fromkeys(str(item).strip() for item in values if str(item).strip()))


def _source_product_categories(value: Any) -> list[str]:
    """Keep multi-category matrix facts as separate workbench buckets."""
    return list(dict.fromkeys(
        item.strip()
        for item in str(value or "").replace("，", ",").replace("；", ",").split(",")
        if item.strip()
    ))


def _source_snapshot(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "question_wiki_id": str(source.get("question_wiki_id") or ""),
        "content_hash": str(source.get("content_hash") or ""),
        "question": str(source.get("question") or ""),
        "answer": str(source.get("answer") or ""),
        "product_category_name": str(source.get("product_category_name") or ""),
        "product_names": _source_product_names(source),
        "source_update_time": str(source.get("source_update_time") or ""),
        "authoritative_override": bool(source.get("authoritative_override")),
        "changed_fields": [
            str(item).strip()
            for item in source.get("changed_fields", [])
            if str(item).strip()
        ],
    }


def connect_sqlite(database_path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(database_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_knowledge_graph_schema(database_path: str | Path) -> None:
    connection = connect_sqlite(database_path)
    try:
        apply_sqlite_schema(connection)
        status = graph_schema_status(connection)
        if status["migration_required"]:
            raise RuntimeError("图谱关系结构待迁移，请先使用带备份的迁移脚本。")
    finally:
        connection.close()


def apply_sqlite_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SQLITE_SCHEMA)
    assignment_columns = {
        str(row[1]) for row in connection.execute("PRAGMA table_info(kg_topic_assignments)").fetchall()
    }
    if "topic_id" not in assignment_columns:
        connection.execute("ALTER TABLE kg_topic_assignments ADD COLUMN topic_id TEXT")
    if "vocabulary_version" not in assignment_columns:
        connection.execute(
            "ALTER TABLE kg_topic_assignments ADD COLUMN vocabulary_version TEXT NOT NULL DEFAULT ''"
        )
    assignment_event_columns = {
        str(row[1]) for row in connection.execute("PRAGMA table_info(kg_topic_assignment_events)").fetchall()
    }
    for column, definition in (
        ("previous_topic_id", "TEXT NOT NULL DEFAULT ''"),
        ("current_topic_id", "TEXT NOT NULL DEFAULT ''"),
        ("vocabulary_version", "TEXT NOT NULL DEFAULT ''"),
    ):
        if column not in assignment_event_columns:
            connection.execute(
                f"ALTER TABLE kg_topic_assignment_events ADD COLUMN {column} {definition}"
            )
    _seed_controlled_topic_vocabulary(connection)
    columns = {
        str(row[1]) for row in connection.execute("PRAGMA table_info(kg_edges)").fetchall()
    }
    if "supersedes_edge_id" in columns:
        connection.execute("CREATE INDEX IF NOT EXISTS idx_kg_edges_supersedes ON kg_edges (supersedes_edge_id)")
    connection.commit()


def _seed_controlled_topic_vocabulary(connection: sqlite3.Connection) -> None:
    """Seed the reviewed pilot vocabulary once without touching knowledge facts."""
    now = utc_now()
    for definition in CONTROLLED_TOPIC_VOCABULARY_V1:
        payload = {
            "topic_id": definition["topic_id"],
            "display_name": definition["display_name"],
            "allowed_categories": list(definition["allowed_categories"]),
            "description": definition["description"],
            "include_rules": definition["include_rules"],
            "exclude_rules": definition["exclude_rules"],
            "lifecycle": "active",
            "vocabulary_version": TOPIC_VOCABULARY_VERSION,
        }
        inserted = connection.execute(
            """
            INSERT OR IGNORE INTO kg_topic_definitions (
                topic_id, display_name, allowed_categories_json, description, include_rules,
                exclude_rules, lifecycle, vocabulary_version, created_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["topic_id"], payload["display_name"], _json_dump(payload["allowed_categories"]),
                payload["description"], payload["include_rules"], payload["exclude_rules"],
                payload["lifecycle"], payload["vocabulary_version"], "system_seed", now, now,
            ),
        )
        if inserted.rowcount:
            connection.execute(
                """
                INSERT INTO kg_topic_definition_events (
                    event_id, topic_id, event_type, before_json, after_json,
                    review_note, actor, created_at
                ) VALUES (?, ?, 'topic_seeded', '{}', ?, ?, 'system_seed', ?)
                """,
                (
                    str(uuid.uuid4()), payload["topic_id"], _json_dump(payload),
                    "基于 V1 全量只读分析启用受控主题词表试点。", now,
                ),
            )


BASE_EDGE_COLUMNS = (
    "edge_id, from_node_id, to_node_id, relation_type, evidence_json, scope_basis_json, "
    "confidence, review_status, generated_by, provenance_json, source_version, "
    "source_content_hashes_json, review_note, reviewed_by, reviewed_at, valid_from, "
    "valid_to, created_at, updated_at"
)
REVISION_EDGE_COLUMNS = "supersedes_edge_id, revision_no, revision_kind"
EDGE_COLUMNS = f"{BASE_EDGE_COLUMNS}, {REVISION_EDGE_COLUMNS}"


def _edge_table_sql(
    table_name: str,
    relation_types: set[str],
    include_revision_columns: bool = True,
) -> str:
    allowed = ", ".join(f"'{item}'" for item in sorted(relation_types))
    revision_columns = """
            supersedes_edge_id TEXT,
            revision_no INTEGER NOT NULL DEFAULT 1,
            revision_kind TEXT NOT NULL DEFAULT 'original',
    """ if include_revision_columns else ""
    revision_checks = """
            CHECK(revision_kind IN ('original', 'human_adjustment', 'source_revalidation')),
            CHECK(revision_no >= 1),
    """ if include_revision_columns else ""
    return f"""
        CREATE TABLE {table_name} (
            edge_id TEXT PRIMARY KEY,
            from_node_id TEXT NOT NULL,
            to_node_id TEXT NOT NULL,
            relation_type TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            scope_basis_json TEXT NOT NULL,
            confidence REAL NOT NULL,
            review_status TEXT NOT NULL DEFAULT 'candidate',
            generated_by TEXT NOT NULL,
            provenance_json TEXT NOT NULL,
            source_version TEXT NOT NULL DEFAULT '',
            source_content_hashes_json TEXT NOT NULL DEFAULT '{{}}',
            review_note TEXT NOT NULL DEFAULT '',
            reviewed_by TEXT NOT NULL DEFAULT '',
            reviewed_at TEXT,
            valid_from TEXT NOT NULL,
            valid_to TEXT,
            {revision_columns}
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(from_node_id) REFERENCES kg_nodes(node_id),
            FOREIGN KEY(to_node_id) REFERENCES kg_nodes(node_id),
            CHECK(from_node_id <> to_node_id),
            CHECK(relation_type IN ({allowed})),
            CHECK(review_status IN ('candidate', 'confirmed', 'rejected', 'expired')),
            CHECK(generated_by IN ('source_field', 'rule', 'ai', 'human')),
            {revision_checks}
            CHECK(confidence >= 0 AND confidence <= 1)
        )
    """


def _rebuild_sqlite_edge_table(
    connection: sqlite3.Connection,
    relation_types: set[str],
    include_revision_columns: bool = True,
) -> dict[str, int]:
    before_edges = int(connection.execute("SELECT COUNT(*) FROM kg_edges").fetchone()[0])
    before_events = int(connection.execute("SELECT COUNT(*) FROM kg_edge_events").fetchone()[0])
    current_columns = {
        str(row[1]) for row in connection.execute("PRAGMA table_info(kg_edges)").fetchall()
    }
    source_has_revisions = {"supersedes_edge_id", "revision_no", "revision_kind"}.issubset(current_columns)
    copy_columns = EDGE_COLUMNS if include_revision_columns and source_has_revisions else BASE_EDGE_COLUMNS
    connection.commit()
    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DROP TABLE IF EXISTS kg_edges_relation_migration")
        connection.execute(
            _edge_table_sql(
                "kg_edges_relation_migration",
                relation_types,
                include_revision_columns=include_revision_columns,
            )
        )
        connection.execute(
            f"INSERT INTO kg_edges_relation_migration ({copy_columns}) SELECT {copy_columns} FROM kg_edges"
        )
        connection.execute("DROP TABLE kg_edges")
        connection.execute("ALTER TABLE kg_edges_relation_migration RENAME TO kg_edges")
        connection.execute("CREATE INDEX idx_kg_edges_from ON kg_edges (from_node_id, review_status)")
        connection.execute("CREATE INDEX idx_kg_edges_to ON kg_edges (to_node_id, review_status)")
        connection.execute("CREATE INDEX idx_kg_edges_relation_review ON kg_edges (relation_type, review_status)")
        if include_revision_columns:
            connection.execute("CREATE INDEX idx_kg_edges_supersedes ON kg_edges (supersedes_edge_id)")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.execute("PRAGMA foreign_keys = ON")
    violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise RuntimeError("图谱关系表迁移后外键校验失败。")
    after_edges = int(connection.execute("SELECT COUNT(*) FROM kg_edges").fetchone()[0])
    after_events = int(connection.execute("SELECT COUNT(*) FROM kg_edge_events").fetchone()[0])
    if (before_edges, before_events) != (after_edges, after_events):
        raise RuntimeError("图谱关系表迁移前后边或事件数量不一致。")
    return {"edge_count": after_edges, "event_count": after_events}


def migrate_sqlite_revision_schema(connection: sqlite3.Connection) -> dict[str, Any]:
    """Add append-only revision metadata without rebuilding existing edge rows."""
    current_columns = {
        str(row[1]) for row in connection.execute("PRAGMA table_info(kg_edges)").fetchall()
    }
    additions = {
        "supersedes_edge_id": "TEXT",
        "revision_no": "INTEGER NOT NULL DEFAULT 1",
        "revision_kind": "TEXT NOT NULL DEFAULT 'original'",
    }
    changed = False
    for column, definition in additions.items():
        if column in current_columns:
            continue
        connection.execute(f"ALTER TABLE kg_edges ADD COLUMN {column} {definition}")
        changed = True
    connection.execute("CREATE INDEX IF NOT EXISTS idx_kg_edges_supersedes ON kg_edges (supersedes_edge_id)")
    connection.commit()
    return {"changed": changed, **graph_schema_status(connection)}


def rollback_sqlite_revision_schema(connection: sqlite3.Connection) -> dict[str, Any]:
    """Remove revision columns only when no revision history would be lost."""
    columns = {
        str(row[1]) for row in connection.execute("PRAGMA table_info(kg_edges)").fetchall()
    }
    if not {"supersedes_edge_id", "revision_no", "revision_kind"}.issubset(columns):
        return {"changed": False, **graph_schema_status(connection)}
    revision_count = int(
        connection.execute(
            """
            SELECT COUNT(*) FROM kg_edges
            WHERE supersedes_edge_id IS NOT NULL OR revision_no <> 1 OR revision_kind <> 'original'
            """
        ).fetchone()[0]
    )
    if revision_count:
        raise ValueError("回退前仍存在人工修订或重新复核版本，请使用迁移前备份恢复，避免丢失审计记录。")
    counts = _rebuild_sqlite_edge_table(
        connection,
        RELATION_TYPES,
        include_revision_columns=False,
    )
    return {"changed": True, **counts, **graph_schema_status(connection)}


def migrate_sqlite_relation_schema(connection: sqlite3.Connection) -> dict[str, Any]:
    """Upgrade relation types and append-only revision metadata while preserving graph data."""
    apply_sqlite_schema(connection)
    status = graph_schema_status(connection)
    changed = False
    counts: dict[str, int] = {}
    if not status["relation_schema_ready"]:
        counts = _rebuild_sqlite_edge_table(connection, RELATION_TYPES)
        changed = True
    revision_result = migrate_sqlite_revision_schema(connection)
    return {"changed": changed or revision_result["changed"], **counts, **graph_schema_status(connection)}


def rollback_sqlite_relation_schema(connection: sqlite3.Connection) -> dict[str, Any]:
    """Return to the phase-one constraint when no v2 workflow edges exist."""
    new_edge_count = int(
        connection.execute(
            "SELECT COUNT(*) FROM kg_edges WHERE relation_type IN ('PREREQUISITE_FOR', 'SUBPROCEDURE_OF')"
        ).fetchone()[0]
    )
    if new_edge_count:
        raise ValueError("回退前仍存在新流程关系，请使用迁移前备份恢复，避免丢失审计记录。")
    counts = _rebuild_sqlite_edge_table(connection, LEGACY_RELATION_TYPES)
    return {"changed": True, **counts, **graph_schema_status(connection)}


def rollback_sqlite_schema(connection: sqlite3.Connection) -> None:
    """Drop only the phase-one sidecar tables, in dependency order."""
    connection.executescript(
        """
        DROP TABLE IF EXISTS kg_review_batch_edges;
        DROP TABLE IF EXISTS kg_review_batches;
        DROP TABLE IF EXISTS kg_topic_assignment_events;
        DROP TABLE IF EXISTS kg_topic_assignments;
        DROP TABLE IF EXISTS kg_topic_definition_events;
        DROP TABLE IF EXISTS kg_topic_definitions;
        DROP TABLE IF EXISTS kg_edge_events;
        DROP TABLE IF EXISTS kg_edges;
        DROP TABLE IF EXISTS kg_nodes;
        """
    )
    connection.commit()


def graph_schema_status(connection: sqlite3.Connection) -> dict[str, Any]:
    expected = {
        "kg_nodes", "kg_edges", "kg_edge_events", "kg_topic_definitions", "kg_topic_definition_events",
        "kg_topic_assignments", "kg_topic_assignment_events",
    }
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'kg_%'"
    ).fetchall()
    present = {str(row[0]) for row in rows}
    edge_schema_row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='kg_edges'"
    ).fetchone()
    edge_schema = str(edge_schema_row[0] or "") if edge_schema_row else ""
    relation_schema_ready = all(relation in edge_schema for relation in ("PREREQUISITE_FOR", "SUBPROCEDURE_OF"))
    edge_columns = {
        str(row[1]) for row in connection.execute("PRAGMA table_info(kg_edges)").fetchall()
    } if edge_schema_row else set()
    revision_schema_ready = {"supersedes_edge_id", "revision_no", "revision_kind"}.issubset(edge_columns)
    tables_ready = expected.issubset(present)
    return {
        "expected_tables": sorted(expected),
        "present_tables": sorted(present),
        "ready": tables_ready and relation_schema_ready and revision_schema_ready,
        "tables_ready": tables_ready,
        "relation_schema_ready": relation_schema_ready,
        "revision_schema_ready": revision_schema_ready,
        "migration_required": tables_ready and not (relation_schema_ready and revision_schema_ready),
        "missing_tables": sorted(expected - present),
    }


def load_product_catalog(catalog_path: str | Path) -> dict[str, list[str]]:
    path = Path(catalog_path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"未找到 8085 型号库：{path}") from exc
    except (OSError, ValueError) as exc:
        raise ValueError(f"8085 型号库无法读取：{path}") from exc
    if not isinstance(raw, dict):
        raise ValueError("8085 型号库必须是分类到型号列表的 JSON 对象。")
    catalog: dict[str, list[str]] = {}
    seen_models: dict[str, str] = {}
    for raw_category, raw_models in raw.items():
        category = str(raw_category or "").strip()
        if not category or not isinstance(raw_models, list):
            continue
        models: list[str] = []
        for raw_model in raw_models:
            model = str(raw_model or "").strip()
            if not model or model in models:
                continue
            if model in seen_models and seen_models[model] != category:
                raise ValueError(f"型号 {model} 同时归属多个产品类型。")
            seen_models[model] = category
            models.append(model)
        if models:
            catalog[category] = models
    if not catalog:
        raise ValueError("8085 型号库中没有可用型号。")
    return catalog


def product_catalog_snapshot(catalog: dict[str, list[str]], source: str = "8085_product_catalog") -> dict[str, Any]:
    normalized = {category: list(models) for category, models in sorted(catalog.items())}
    canonical = _json_dump(normalized)
    all_models = sorted({model for models in normalized.values() for model in models})
    return {
        "source": source,
        "content_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "category_count": len(normalized),
        "model_count": len(all_models),
        "category_counts": {category: len(models) for category, models in normalized.items()},
    }


def normalize_scope(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("scope_json 必须是对象。")
    normalized: dict[str, Any] = {}
    for key, raw in value.items():
        name = str(key or "").strip()
        if not name:
            continue
        if name not in SCOPE_DIMENSIONS:
            raise ValueError(f"scope_json 不支持范围维度：{name}")
        if name == "all_models_explicit":
            if raw is True:
                normalized[name] = True
            elif raw not in (False, None, ""):
                raise ValueError("all_models_explicit 只能填 true，空范围不代表全部型号。")
        elif name == "product_catalog_snapshot":
            if not isinstance(raw, dict):
                raise ValueError("product_catalog_snapshot 必须是对象。")
            normalized[name] = dict(raw)
        elif isinstance(raw, (list, tuple, set)):
            values = [str(item).strip() for item in raw if str(item).strip()]
            if values:
                normalized[name] = list(dict.fromkeys(values))
        elif raw is not None and str(raw).strip():
            normalized[name] = str(raw).strip()
    if not normalized:
        raise ValueError("scope_json 至少需要一个明确范围维度。")
    return normalized


def normalize_claims(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("claims_json 必须是对象。")
    normalized: dict[str, Any] = dict(value)
    for key in CLAIM_TEXT_FIELDS:
        if key in normalized and normalized[key] is not None:
            normalized[key] = str(normalized[key]).strip()
    for key in CLAIM_LIST_FIELDS:
        if key not in normalized:
            continue
        raw_values = normalized[key] if isinstance(normalized[key], (list, tuple, set)) else [normalized[key]]
        normalized[key] = list(dict.fromkeys(str(item).strip() for item in raw_values if str(item).strip()))
    for key in ("navigation_only", "mutually_exclusive"):
        if key in normalized:
            normalized[key] = bool(normalized[key])
    if not any(
        (
            normalized.get("conclusion"),
            normalized.get("navigation_only"),
            normalized.get("procedure_steps"),
            normalized.get("outcome"),
            normalized.get("outcome_keys"),
            normalized.get("preconditions"),
            normalized.get("precondition_keys"),
        )
    ):
        raise ValueError("claims_json 至少需要结论、流程步骤、前置条件或导航标记之一。")
    return normalized


def bind_scope_to_product_catalog(
    scope: dict[str, Any], catalog: dict[str, list[str]] | None
) -> dict[str, Any]:
    normalized = normalize_scope(scope)
    if catalog is None:
        return normalized
    snapshot = product_catalog_snapshot(catalog)
    categories = set(catalog)
    models = {model for values in catalog.values() for model in values}
    requested_categories = _scope_value_set(normalized.get("product_categories")) or set()
    invalid_categories = sorted(value for value in requested_categories if value not in {item.casefold() for item in categories})
    if invalid_categories:
        raise ValueError(f"8085 型号库中不存在产品类型：{', '.join(invalid_categories)}")
    model_lookup = {model.casefold(): model for model in models}
    category_lookup = {category.casefold(): category for category in categories}
    for key in ("product_models", "excluded_product_models"):
        values = _scope_value_set(normalized.get(key)) or set()
        invalid = sorted(value for value in values if value not in model_lookup)
        if invalid:
            raise ValueError(f"8085 型号库中不存在型号：{', '.join(invalid)}")
    legacy_values = _scope_value_set(normalized.get("product_scope")) or set()
    invalid_legacy = sorted(value for value in legacy_values if value not in model_lookup and value not in category_lookup)
    if invalid_legacy:
        raise ValueError(f"product_scope 含型号库之外的值：{', '.join(invalid_legacy)}")
    has_base = bool(
        normalized.get("all_models_explicit")
        or requested_categories
        or _scope_value_set(normalized.get("product_models"))
        or legacy_values
    )
    if normalized.get("excluded_product_models") and not has_base:
        raise ValueError("排除型号必须与全量、产品类型或具体型号范围一起使用。")
    if normalized.get("all_models_explicit"):
        supplied = normalized.get("product_catalog_snapshot") or {}
        if supplied and supplied.get("content_hash") not in (None, "", snapshot["content_hash"]):
            raise ValueError("scope_json 绑定的型号库快照已过期，请重新生成候选。")
        normalized["product_catalog_snapshot"] = snapshot
    return normalized


def _scope_value_set(value: Any) -> set[str] | None:
    if value is None:
        return None
    values = value if isinstance(value, (list, tuple, set)) else [value]
    normalized = {str(item).strip().casefold() for item in values if str(item).strip()}
    if not normalized or normalized.intersection({"*", "all", "全部", "不限"}):
        return None
    return normalized


def _set_relation(left: set[str], right: set[str]) -> str:
    if left == right:
        return "equal"
    if left.isdisjoint(right):
        return "disjoint"
    if left.issubset(right):
        return "subset"
    if right.issubset(left):
        return "superset"
    return "overlap"


def _resolved_product_models(
    scope: dict[str, Any], catalog: dict[str, list[str]] | None
) -> tuple[set[str] | None, dict[str, Any]]:
    if catalog is None:
        legacy = _scope_value_set(scope.get("product_models") or scope.get("product_scope"))
        return legacy, {"resolution": "literal" if legacy else "unknown"}
    model_lookup = {model.casefold(): model for values in catalog.values() for model in values}
    category_lookup = {category.casefold(): category for category in catalog}
    resolved: set[str] | None = None
    basis: list[str] = []
    if scope.get("all_models_explicit"):
        resolved = set(model_lookup.values())
        basis.append("all_models_explicit")
    category_values = _scope_value_set(scope.get("product_categories")) or set()
    legacy_values = _scope_value_set(scope.get("product_scope")) or set()
    category_values.update(value for value in legacy_values if value in category_lookup)
    if category_values:
        category_models = {
            model for value in category_values for model in catalog[category_lookup[value]]
        }
        resolved = category_models if resolved is None else resolved.intersection(category_models)
        basis.append("product_categories")
    model_values = _scope_value_set(scope.get("product_models")) or set()
    model_values.update(value for value in legacy_values if value in model_lookup)
    if model_values:
        explicit_models = {model_lookup[value] for value in model_values}
        resolved = explicit_models if resolved is None else resolved.intersection(explicit_models)
        basis.append("product_models")
    excluded = _scope_value_set(scope.get("excluded_product_models")) or set()
    if resolved is not None and excluded:
        resolved.difference_update(model_lookup[value] for value in excluded)
        basis.append("excluded_product_models")
    return resolved, {
        "resolution": "resolved" if resolved is not None else "unknown",
        "basis": basis,
        "model_count": len(resolved) if resolved is not None else None,
        "models": sorted(resolved) if resolved is not None else [],
        "catalog_snapshot": product_catalog_snapshot(catalog),
    }


def compare_scopes(
    left: dict[str, Any], right: dict[str, Any], product_catalog: dict[str, list[str]] | None = None
) -> str:
    """Return left's range relative to right: equal/subset/superset/overlap/disjoint."""
    left = bind_scope_to_product_catalog(left, product_catalog)
    right = bind_scope_to_product_catalog(right, product_catalog)
    left_products, _ = _resolved_product_models(left, product_catalog)
    right_products, _ = _resolved_product_models(right, product_catalog)
    if left_products is None or right_products is None:
        return "unknown"
    dimension_relations = [_set_relation(left_products, right_products)]
    for key in set(left).union(right) - PRODUCT_SCOPE_DIMENSIONS:
        left_values = _scope_value_set(left.get(key))
        right_values = _scope_value_set(right.get(key))
        if left_values is None and right_values is None:
            continue
        if left_values is None:
            dimension_relations.append("superset")
            continue
        if right_values is None:
            dimension_relations.append("subset")
            continue
        dimension_relations.append(_set_relation(left_values, right_values))
    if "disjoint" in dimension_relations:
        return "disjoint"
    has_subset = "subset" in dimension_relations
    has_superset = "superset" in dimension_relations
    if "overlap" in dimension_relations or (has_subset and has_superset):
        return "overlap"
    if has_subset:
        return "subset"
    if has_superset:
        return "superset"
    return "equal"


def _claim_conclusion(claims: dict[str, Any]) -> str:
    return str(claims.get("conclusion") or "").strip().casefold()


def _normalized_claim_values(value: Any) -> list[str]:
    values = value if isinstance(value, (list, tuple, set)) else [value]
    return [str(item).strip().casefold() for item in values if str(item).strip()]


def _is_ordered_subset(left: list[str], right: list[str]) -> bool:
    if not left or len(left) >= len(right):
        return False
    iterator = iter(right)
    return all(any(candidate == item for candidate in iterator) for item in left)


def derive_candidate_relations(
    from_scope: dict[str, Any],
    from_claims: dict[str, Any],
    to_scope: dict[str, Any],
    to_claims: dict[str, Any],
    product_catalog: dict[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
    """Classify zero or more independent content and workflow relationships."""
    from_scope = bind_scope_to_product_catalog(from_scope, product_catalog)
    to_scope = bind_scope_to_product_catalog(to_scope, product_catalog)
    from_claims = normalize_claims(from_claims)
    to_claims = normalize_claims(to_claims)
    from_products, from_product_basis = _resolved_product_models(from_scope, product_catalog)
    to_products, to_product_basis = _resolved_product_models(to_scope, product_catalog)
    basis = {
        "scope_relation": compare_scopes(from_scope, to_scope, product_catalog),
        "from_scope": from_scope,
        "to_scope": to_scope,
        "from_product_resolution": from_product_basis,
        "to_product_resolution": to_product_basis,
        "from_conclusion": from_claims.get("conclusion", ""),
        "to_conclusion": to_claims.get("conclusion", ""),
    }
    candidates: list[dict[str, Any]] = []

    if from_claims.get("navigation_only"):
        return [{
            "relation_type": "ROUTES_TO",
            "confidence": 0.72,
            "scope_basis": basis,
            "reason": "来源条目被明确标记为主题导航，未将导航当作答案覆盖。",
        }]

    relation = basis["scope_relation"]
    from_conclusion = _claim_conclusion(from_claims)
    to_conclusion = _claim_conclusion(to_claims)
    same_conclusion = bool(from_conclusion and from_conclusion == to_conclusion)
    explicit_exception = bool(from_claims.get("exception_condition"))
    general_has_coverage = bool(str(to_claims.get("coverage_evidence") or "").strip())
    same_intent = not from_claims.get("intent") or not to_claims.get("intent") or from_claims.get("intent") == to_claims.get("intent")
    same_component = not from_claims.get("component") or not to_claims.get("component") or from_claims.get("component") == to_claims.get("component")
    compatible_context = same_intent and same_component
    claim_key_matches = bool(
        from_claims.get("claim_key")
        and from_claims.get("claim_key") == to_claims.get("claim_key")
    )
    claim_values_differ = bool(
        from_claims.get("claim_value")
        and to_claims.get("claim_value")
        and from_claims.get("claim_value") != to_claims.get("claim_value")
    )
    explicit_conflict = bool(
        claim_key_matches
        and claim_values_differ
        and (from_claims.get("mutually_exclusive") or to_claims.get("mutually_exclusive"))
    )

    if relation == "equal" and same_conclusion and compatible_context:
        candidates.append({
            "relation_type": "DUPLICATES",
            "confidence": 0.92,
            "scope_basis": basis,
            "reason": "范围相同且关键结论一致。",
        })
    elif relation == "subset" and same_conclusion and general_has_coverage and compatible_context:
        candidates.append({
            "relation_type": "SPECIALIZES",
            "confidence": 0.88,
            "scope_basis": basis,
            "reason": "来源范围是目标范围的子集，且目标答案有明确覆盖证据。",
        })
    elif relation == "subset" and not same_conclusion and explicit_exception:
        candidates.append({
            "relation_type": "EXCEPTION_TO",
            "confidence": 0.84,
            "scope_basis": basis,
            "reason": "来源范围更具体，且存在明确条件说明其结论是例外。",
        })
    elif relation in {"equal", "subset", "overlap"} and not same_conclusion and explicit_conflict:
        candidates.append({
            "relation_type": "CONFLICTS_WITH",
            "confidence": 0.78,
            "scope_basis": basis,
            "reason": "范围相同或交叉，且同一结论键的值被明确标记为不能同时成立。",
        })
    elif relation == "overlap" and same_conclusion and compatible_context:
        candidates.append({
            "relation_type": "OVERLAPS_WITH",
            "confidence": 0.76,
            "scope_basis": basis,
            "reason": "范围部分重叠，结论可同时成立。",
        })

    scopes_can_interact = relation not in {"unknown", "disjoint"} and from_products is not None and to_products is not None
    from_steps = _normalized_claim_values(from_claims.get("procedure_steps") or [])
    to_steps = _normalized_claim_values(to_claims.get("procedure_steps") or [])
    if scopes_can_interact and _is_ordered_subset(from_steps, to_steps):
        candidates.append({
            "relation_type": "SUBPROCEDURE_OF",
            "confidence": 0.86,
            "scope_basis": {**basis, "matched_steps": from_claims.get("procedure_steps", [])},
            "reason": "起点知识的步骤按顺序完整出现在目标知识的更大流程中。",
        })
    from_outcomes = set(_normalized_claim_values(from_claims.get("outcome_keys") or from_claims.get("outcome") or []))
    to_preconditions = set(_normalized_claim_values(to_claims.get("precondition_keys") or to_claims.get("preconditions") or []))
    matched_conditions = sorted(from_outcomes.intersection(to_preconditions))
    if scopes_can_interact and matched_conditions:
        candidates.append({
            "relation_type": "PREREQUISITE_FOR",
            "confidence": 0.84,
            "scope_basis": {**basis, "matched_conditions": matched_conditions},
            "reason": "起点知识的输出结果满足目标知识的明确前置条件。",
        })
    return candidates


def derive_candidate_relation(
    from_scope: dict[str, Any],
    from_claims: dict[str, Any],
    to_scope: dict[str, Any],
    to_claims: dict[str, Any],
    product_catalog: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Backward-compatible single-result wrapper used by older callers."""
    results = derive_candidate_relations(from_scope, from_claims, to_scope, to_claims, product_catalog)
    if results:
        return results[0]
    normalized_from = bind_scope_to_product_catalog(from_scope, product_catalog)
    normalized_to = bind_scope_to_product_catalog(to_scope, product_catalog)
    return {
        "relation_type": None,
        "confidence": 0.0,
        "scope_basis": {
            "scope_relation": compare_scopes(normalized_from, normalized_to, product_catalog),
            "from_scope": normalized_from,
            "to_scope": normalized_to,
        },
        "reason": "证据不足以建立知识间候选关系。",
    }


def _record_event(
    connection: sqlite3.Connection,
    edge_id: str,
    event_type: str,
    actor: str,
    from_status: str | None = None,
    to_status: str | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO kg_edge_events (
            event_id, edge_id, event_type, from_review_status, to_review_status,
            event_data_json, actor, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            edge_id,
            event_type,
            from_status,
            to_status,
            _json_dump(data or {}),
            actor,
            utc_now(),
        ),
    )


def _edge_payload(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    for key in ("evidence_json", "scope_basis_json", "provenance_json", "source_content_hashes_json"):
        data[key.removesuffix("_json")] = _json_load(data.pop(key, ""), {})
    return data


class GraphStore:
    """Small SQLite repository used by both Flask routes and offline tools."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        product_catalog: dict[str, list[str]] | None = None,
        product_catalog_path: str | Path | None = None,
    ):
        self.connection = connection
        self.product_catalog = product_catalog or (
            load_product_catalog(product_catalog_path) if product_catalog_path else None
        )
        self.catalog_snapshot = (
            product_catalog_snapshot(self.product_catalog) if self.product_catalog else None
        )

    def _source_knowledge(self, wiki_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            """
            SELECT question_wiki_id, content_hash, question, answer, product_category_name,
                   product_names_json, source_update_time
            FROM kb_retrieval_index
            WHERE library_type = 'knowledge_base_v1'
              AND index_status = 'ready'
              AND question_wiki_id = ?
            """,
            (wiki_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"未在可用知识索引中找到 Wiki ID：{wiki_id}")
        return dict(row)

    def _node_by_business_key(self, node_type: str, business_key: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM kg_nodes WHERE node_type = ? AND business_key = ?",
            (node_type, business_key),
        ).fetchone()
        return _row_dict(row)

    def _expire_stale_candidates_for_source(self, wiki_id: str, content_hash: str, actor: str) -> int:
        result = self.refresh_stale_relationships(wiki_id, actor)
        return int(result["expired_count"])

    def _edge_with_business_keys(self, edge_id: str) -> sqlite3.Row | None:
        return self.connection.execute(
            """
            SELECT e.*, f.business_key AS from_business_key, f.canonical_name AS from_name,
                   t.business_key AS to_business_key, t.canonical_name AS to_name,
                   f.node_type AS from_node_type, t.node_type AS to_node_type
            FROM kg_edges e
            JOIN kg_nodes f ON f.node_id = e.from_node_id
            JOIN kg_nodes t ON t.node_id = e.to_node_id
            WHERE e.edge_id = ?
            """,
            (edge_id,),
        ).fetchone()

    def _revision_source(
        self,
        wiki_id: str,
        source_override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if source_override and str(source_override.get("question_wiki_id") or "").strip() == wiki_id:
            snapshot = _source_snapshot(source_override)
            snapshot["authoritative_override"] = True
            content_hash = snapshot["content_hash"].strip()
            if not content_hash:
                raise ValueError("知识变更快照缺少 content_hash。")
            return snapshot
        indexed = _source_snapshot(self._source_knowledge(wiki_id))
        node = self._node_by_business_key("knowledge", wiki_id)
        if node:
            properties = _json_load(node.get("properties_json"), {})
            latest = properties.get("latest_source_snapshot")
            if isinstance(latest, dict):
                latest = _source_snapshot(latest)
                if (
                    latest.get("authoritative_override")
                    and latest.get("content_hash")
                    and latest.get("content_hash") == str(node.get("content_hash") or "")
                    and latest.get("content_hash") != indexed.get("content_hash")
                ):
                    return latest
        return indexed

    def _structured_revalidation_side(
        self,
        wiki_id: str,
        source: dict[str, Any],
        fallback_scope: dict[str, Any],
        fallback_claims: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
        node = self._node_by_business_key("knowledge", wiki_id)
        scope = _json_load((node or {}).get("scope_json"), fallback_scope)
        claims = _json_load((node or {}).get("claims_json"), fallback_claims)
        properties = _json_load((node or {}).get("properties_json"), {})
        previous_source = properties.get("latest_source_snapshot")
        previous = _source_snapshot(previous_source) if isinstance(previous_source, dict) else None
        current = _source_snapshot(source)
        changed_fields = set(current.get("changed_fields") or [])
        if previous:
            if previous.get("question") != current.get("question"):
                changed_fields.add("question")
            if previous.get("answer") != current.get("answer"):
                changed_fields.add("answer")
            if previous.get("product_names") != current.get("product_names"):
                changed_fields.add("products")
            if previous.get("product_category_name") != current.get("product_category_name"):
                changed_fields.add("product_category_name")

        scope = dict(scope or fallback_scope or {})
        claims = dict(claims or fallback_claims or {})
        if "products" in changed_fields or "product_category_name" in changed_fields:
            for key in PRODUCT_SCOPE_DIMENSIONS:
                scope.pop(key, None)
            product_names = current.get("product_names") or []
            if product_names:
                scope["product_models"] = product_names
        if "answer" in changed_fields:
            for key in ANSWER_DERIVED_CLAIM_FIELDS:
                claims.pop(key, None)
            claims["conclusion"] = current.get("answer") or ""

        return (
            bind_scope_to_product_catalog(scope, self.product_catalog),
            normalize_claims(claims),
            sorted(changed_fields),
        )

    def _persist_source_state(
        self,
        wiki_id: str,
        source: dict[str, Any],
        scope: dict[str, Any],
        claims: dict[str, Any],
        now: str,
    ) -> None:
        node = self._node_by_business_key("knowledge", wiki_id)
        if not node:
            return
        properties = _json_load(node.get("properties_json"), {})
        snapshot = _source_snapshot(source)
        snapshot["changed_fields"] = []
        properties["latest_source_snapshot"] = snapshot
        properties["source_products"] = snapshot["product_names"]
        properties["product_category_name"] = snapshot["product_category_name"]
        self.connection.execute(
            """
            UPDATE kg_nodes
            SET canonical_name=?, scope_json=?, claims_json=?, properties_json=?,
                source_version=?, content_hash=?, updated_at=?
            WHERE node_id=?
            """,
            (
                snapshot["question"] or node["canonical_name"],
                _json_dump(scope),
                _json_dump(claims),
                _json_dump(properties),
                snapshot["source_update_time"],
                snapshot["content_hash"],
                now,
                node["node_id"],
            ),
        )

    def _manual_scope_basis(
        self,
        from_scope: dict[str, Any],
        from_claims: dict[str, Any],
        to_scope: dict[str, Any],
        to_claims: dict[str, Any],
        original_basis: dict[str, Any],
        relation_type: str,
        original_relation_type: str,
        swap_direction: bool,
    ) -> dict[str, Any]:
        prepared_from_scope = bind_scope_to_product_catalog(from_scope, self.product_catalog)
        prepared_to_scope = bind_scope_to_product_catalog(to_scope, self.product_catalog)
        prepared_from_claims = normalize_claims(from_claims)
        prepared_to_claims = normalize_claims(to_claims)
        _, from_resolution = _resolved_product_models(prepared_from_scope, self.product_catalog)
        _, to_resolution = _resolved_product_models(prepared_to_scope, self.product_catalog)
        basis = {
            "scope_relation": compare_scopes(
                prepared_from_scope,
                prepared_to_scope,
                self.product_catalog,
            ),
            "from_scope": prepared_from_scope,
            "to_scope": prepared_to_scope,
            "from_product_resolution": from_resolution,
            "to_product_resolution": to_resolution,
            "from_claims": prepared_from_claims,
            "to_claims": prepared_to_claims,
            "from_conclusion": str(prepared_from_claims.get("conclusion") or ""),
            "to_conclusion": str(prepared_to_claims.get("conclusion") or ""),
            "human_adjustment": {
                "previous_relation_type": original_relation_type,
                "relation_type": relation_type,
                "direction_swapped": swap_direction,
            },
        }
        for key in ("matched_conditions", "matched_steps"):
            if original_basis.get(key):
                basis[key] = original_basis[key]
        return basis

    def revise_edge(
        self,
        edge_id: str,
        relation_type: str,
        from_scope: dict[str, Any],
        from_claims: dict[str, Any],
        to_scope: dict[str, Any],
        to_claims: dict[str, Any],
        note: str,
        actor: str,
        swap_direction: bool = False,
    ) -> dict[str, Any]:
        relation_type = str(relation_type or "").strip()
        if relation_type not in KNOWLEDGE_RELATION_TYPES:
            raise ValueError("人工修订的知识关系类型不合法。")
        note = str(note or "").strip()
        if not note:
            raise ValueError("调整关系时必须填写复核备注。")
        original = self._edge_with_business_keys(edge_id)
        if original is None:
            raise ValueError("未找到图谱关系。")
        if original["review_status"] not in {"candidate", "confirmed"}:
            raise ValueError("只有待复核或当前已确认关系可以创建人工修订版。")
        if original["from_node_type"] != "knowledge" or original["to_node_type"] != "knowledge":
            raise ValueError("只有知识到知识的关系可以人工修订。")

        original_basis = _json_load(original["scope_basis_json"], {})
        if swap_direction:
            from_scope, to_scope = to_scope, from_scope
            from_claims, to_claims = to_claims, from_claims
            from_node_id, to_node_id = original["to_node_id"], original["from_node_id"]
            from_wiki_id, to_wiki_id = original["to_business_key"], original["from_business_key"]
        else:
            from_node_id, to_node_id = original["from_node_id"], original["to_node_id"]
            from_wiki_id, to_wiki_id = original["from_business_key"], original["to_business_key"]
        scope_basis = self._manual_scope_basis(
            from_scope,
            from_claims,
            to_scope,
            to_claims,
            original_basis,
            relation_type,
            str(original["relation_type"]),
            bool(swap_direction),
        )
        from_source = self._revision_source(str(from_wiki_id))
        to_source = self._revision_source(str(to_wiki_id))
        source_hashes = {
            str(from_wiki_id): str(from_source.get("content_hash") or ""),
            str(to_wiki_id): str(to_source.get("content_hash") or ""),
        }
        original_evidence = _json_load(original["evidence_json"], {})
        evidence = {
            **original_evidence,
            "rule_reason": f"人工复核修订：{note}",
            "from_question": str(from_source.get("question") or "")[:500],
            "to_question": str(to_source.get("question") or "")[:500],
            "from_answer_excerpt": str(from_source.get("answer") or "")[:1200],
            "to_answer_excerpt": str(to_source.get("answer") or "")[:1200],
            "human_revision": {
                "note": note,
                "reviewed_by": actor,
                "previous_relation_type": str(original["relation_type"]),
                "direction_swapped": bool(swap_direction),
            },
        }
        provenance = {
            **_json_load(original["provenance_json"], {}),
            "generated_by": "human",
            "revision_kind": "human_adjustment",
            "supersedes_edge_id": edge_id,
            "reviewed_by": actor,
        }
        now = utc_now()
        revised_edge_id = str(uuid.uuid4())
        revision_no = int(original["revision_no"] or 1) + 1
        try:
            self.connection.execute(
                """
                UPDATE kg_edges
                SET review_status='expired', valid_to=?, updated_at=?
                WHERE edge_id=?
                """,
                (now, now, edge_id),
            )
            self.connection.execute(
                """
                INSERT INTO kg_edges (
                    edge_id, from_node_id, to_node_id, relation_type, evidence_json,
                    scope_basis_json, confidence, review_status, generated_by, provenance_json,
                    source_version, source_content_hashes_json, review_note, reviewed_by,
                    reviewed_at, valid_from, valid_to, created_at, updated_at,
                    supersedes_edge_id, revision_no, revision_kind
                ) VALUES (?, ?, ?, ?, ?, ?, 1, 'confirmed', 'human', ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, 'human_adjustment')
                """,
                (
                    revised_edge_id,
                    from_node_id,
                    to_node_id,
                    relation_type,
                    _json_dump(evidence),
                    _json_dump(scope_basis),
                    _json_dump(provenance),
                    f"{from_source.get('source_update_time') or ''}|{to_source.get('source_update_time') or ''}",
                    _json_dump(source_hashes),
                    note[:2000],
                    actor,
                    now,
                    now,
                    now,
                    now,
                    edge_id,
                    revision_no,
                ),
            )
            _record_event(
                self.connection,
                edge_id,
                "superseded_by_human_revision",
                actor,
                str(original["review_status"]),
                "expired",
                {"revised_edge_id": revised_edge_id, "review_note": note[:2000]},
            )
            _record_event(
                self.connection,
                revised_edge_id,
                "human_revision_confirmed",
                actor,
                None,
                "confirmed",
                {"supersedes_edge_id": edge_id, "revision_no": revision_no, "review_note": note[:2000]},
            )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        revised = self._edge_with_business_keys(revised_edge_id)
        assert revised is not None
        return {
            "edge": _edge_payload(revised),
            "superseded_edge_id": edge_id,
        }

    def refresh_stale_relationships(
        self,
        wiki_id: str | None,
        actor: str,
        source_override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        wiki_id = str(wiki_id or "").strip() or None
        values: list[Any] = []
        wiki_filter = ""
        if wiki_id:
            wiki_filter = " AND (f.business_key=? OR t.business_key=?)"
            values.extend([wiki_id, wiki_id])
        rows = self.connection.execute(
            f"""
            SELECT e.*, f.business_key AS from_business_key, t.business_key AS to_business_key
            FROM kg_edges e
            JOIN kg_nodes f ON f.node_id=e.from_node_id AND f.node_type='knowledge'
            JOIN kg_nodes t ON t.node_id=e.to_node_id AND t.node_type='knowledge'
            WHERE e.review_status IN ('candidate', 'confirmed')
              {wiki_filter}
            ORDER BY e.created_at
            """,
            values,
        ).fetchall()
        grouped_rows: dict[tuple[str, str], list[sqlite3.Row]] = {}
        for row in rows:
            grouped_rows.setdefault((str(row["from_node_id"]), str(row["to_node_id"])), []).append(row)

        expired_count = 0
        revalidation_count = 0
        revalidated_without_relation_count = 0
        relation_changed_count = 0
        source_missing_count = 0
        created_edge_ids: list[str] = []
        now = utc_now()
        try:
            for pair_rows in grouped_rows.values():
                representative = pair_rows[-1]
                from_wiki_id = str(representative["from_business_key"])
                to_wiki_id = str(representative["to_business_key"])
                try:
                    from_source = self._revision_source(from_wiki_id, source_override)
                    to_source = self._revision_source(to_wiki_id, source_override)
                except ValueError:
                    from_source = None
                    to_source = None
                current_hashes = {
                    from_wiki_id: str((from_source or {}).get("content_hash") or ""),
                    to_wiki_id: str((to_source or {}).get("content_hash") or ""),
                }
                stale_rows = [
                    row for row in pair_rows
                    if not from_source
                    or not to_source
                    or any(
                        str(_json_load(row["source_content_hashes_json"], {}).get(key) or "") != value
                        for key, value in current_hashes.items()
                    )
                ]
                if not stale_rows:
                    continue

                for row in stale_rows:
                    stored_hashes = _json_load(row["source_content_hashes_json"], {})
                    self.connection.execute(
                        "UPDATE kg_edges SET review_status='expired', valid_to=?, updated_at=? WHERE edge_id=?",
                        (now, now, row["edge_id"]),
                    )
                    _record_event(
                        self.connection,
                        str(row["edge_id"]),
                        "expired_source_changed",
                        actor,
                        str(row["review_status"]),
                        "expired",
                        {
                            "wiki_id": wiki_id,
                            "previous_content_hashes": stored_hashes,
                            "current_content_hashes": current_hashes,
                        },
                    )
                    expired_count += 1

                if not from_source or not to_source:
                    source_missing_count += 1
                    continue

                original_basis = _json_load(representative["scope_basis_json"], {})
                try:
                    from_scope, from_claims, from_changed = self._structured_revalidation_side(
                        from_wiki_id,
                        from_source,
                        original_basis.get("from_scope") or {},
                        original_basis.get("from_claims") or {
                            "conclusion": original_basis.get("from_conclusion") or ""
                        },
                    )
                    to_scope, to_claims, to_changed = self._structured_revalidation_side(
                        to_wiki_id,
                        to_source,
                        original_basis.get("to_scope") or {},
                        original_basis.get("to_claims") or {
                            "conclusion": original_basis.get("to_conclusion") or ""
                        },
                    )
                    results = derive_candidate_relations(
                        from_scope,
                        from_claims,
                        to_scope,
                        to_claims,
                        self.product_catalog,
                    )
                    revalidation_error = ""
                except ValueError as exc:
                    from_changed = list((from_source or {}).get("changed_fields") or [])
                    to_changed = list((to_source or {}).get("changed_fields") or [])
                    results = []
                    revalidation_error = str(exc)

                if not revalidation_error:
                    self._persist_source_state(from_wiki_id, from_source, from_scope, from_claims, now)
                    self._persist_source_state(to_wiki_id, to_source, to_scope, to_claims, now)

                previous_types = {str(row["relation_type"]) for row in stale_rows}
                if not results:
                    revalidated_without_relation_count += 1
                    no_relation_reason = revalidation_error or "最新范围和结论不足以继续建立知识关系。"
                    for row in stale_rows:
                        self.connection.execute(
                            "UPDATE kg_edges SET review_note=?, updated_at=? WHERE edge_id=?",
                            (f"重判结果：{no_relation_reason}", now, row["edge_id"]),
                        )
                        _record_event(
                            self.connection,
                            str(row["edge_id"]),
                            "source_revalidation_no_relation",
                            actor,
                            "expired",
                            "expired",
                            {
                                "reason": no_relation_reason,
                                "from_changed_fields": from_changed,
                                "to_changed_fields": to_changed,
                            },
                        )
                    continue

                revision_no = max(int(row["revision_no"] or 1) for row in stale_rows) + 1
                for result in results:
                    relation_type = str(result["relation_type"])
                    duplicate = self.connection.execute(
                        """
                        SELECT edge_id FROM kg_edges
                        WHERE from_node_id=? AND to_node_id=? AND relation_type=?
                          AND review_status IN ('candidate', 'confirmed')
                          AND source_content_hashes_json=?
                        LIMIT 1
                        """,
                        (
                            representative["from_node_id"],
                            representative["to_node_id"],
                            relation_type,
                            _json_dump(current_hashes),
                        ),
                    ).fetchone()
                    if duplicate:
                        continue
                    superseded = next(
                        (row for row in stale_rows if str(row["relation_type"]) == relation_type),
                        representative,
                    )
                    new_edge_id = str(uuid.uuid4())
                    original_evidence = _json_load(superseded["evidence_json"], {})
                    evidence = {
                        **original_evidence,
                        "rule_reason": f"来源知识已变化，按最新范围和结论重新判定：{result['reason']}",
                        "from_question": str(from_source.get("question") or "")[:500],
                        "to_question": str(to_source.get("question") or "")[:500],
                        "from_answer_excerpt": str(from_source.get("answer") or "")[:1200],
                        "to_answer_excerpt": str(to_source.get("answer") or "")[:1200],
                        "source_revalidation": {
                            "previous_edge_ids": [str(row["edge_id"]) for row in stale_rows],
                            "previous_relation_types": sorted(previous_types),
                            "from_changed_fields": from_changed,
                            "to_changed_fields": to_changed,
                        },
                    }
                    provenance = {
                        **_json_load(superseded["provenance_json"], {}),
                        "generated_by": "rule",
                        "revision_kind": "source_revalidation",
                        "supersedes_edge_id": str(superseded["edge_id"]),
                        "revalidation_requested_by": actor,
                    }
                    self.connection.execute(
                        """
                        INSERT INTO kg_edges (
                            edge_id, from_node_id, to_node_id, relation_type, evidence_json,
                            scope_basis_json, confidence, review_status, generated_by, provenance_json,
                            source_version, source_content_hashes_json, review_note, reviewed_by,
                            reviewed_at, valid_from, valid_to, created_at, updated_at,
                            supersedes_edge_id, revision_no, revision_kind
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'candidate', 'rule', ?, ?, ?, '', '', NULL, ?, NULL, ?, ?, ?, ?, 'source_revalidation')
                        """,
                        (
                            new_edge_id,
                            representative["from_node_id"],
                            representative["to_node_id"],
                            relation_type,
                            _json_dump(evidence),
                            _json_dump(result["scope_basis"]),
                            float(result["confidence"]),
                            _json_dump(provenance),
                            f"{from_source.get('source_update_time') or ''}|{to_source.get('source_update_time') or ''}",
                            _json_dump(current_hashes),
                            now,
                            now,
                            now,
                            str(superseded["edge_id"]),
                            revision_no,
                        ),
                    )
                    _record_event(
                        self.connection,
                        new_edge_id,
                        "source_revalidation_created",
                        actor,
                        None,
                        "candidate",
                        {
                            "supersedes_edge_id": str(superseded["edge_id"]),
                            "revision_no": revision_no,
                            "previous_relation_types": sorted(previous_types),
                            "relation_type": relation_type,
                        },
                    )
                    if relation_type not in previous_types:
                        relation_changed_count += 1
                    revalidation_count += 1
                    created_edge_ids.append(new_edge_id)
            if source_override and wiki_id:
                node = self._node_by_business_key("knowledge", wiki_id)
                if node:
                    source = self._revision_source(wiki_id, source_override)
                    try:
                        scope, claims, _ = self._structured_revalidation_side(
                            wiki_id,
                            source,
                            _json_load(node.get("scope_json"), {}),
                            _json_load(node.get("claims_json"), {}) or {
                                "conclusion": str(source.get("answer") or "")
                            },
                        )
                        self._persist_source_state(wiki_id, source, scope, claims, now)
                    except ValueError:
                        properties = _json_load(node.get("properties_json"), {})
                        snapshot = _source_snapshot(source)
                        snapshot["changed_fields"] = []
                        properties["latest_source_snapshot"] = snapshot
                        self.connection.execute(
                            """
                            UPDATE kg_nodes
                            SET canonical_name=?, properties_json=?, source_version=?,
                                content_hash=?, updated_at=?
                            WHERE node_id=?
                            """,
                            (
                                snapshot["question"] or node["canonical_name"],
                                _json_dump(properties),
                                snapshot["source_update_time"],
                                snapshot["content_hash"],
                                now,
                                node["node_id"],
                            ),
                        )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        return {
            "expired_count": expired_count,
            "revalidation_candidate_count": revalidation_count,
            "revalidated_without_relation_count": revalidated_without_relation_count,
            "relation_changed_count": relation_changed_count,
            "source_missing_count": source_missing_count,
            "created_edge_ids": created_edge_ids,
        }

    def upsert_knowledge_node(
        self,
        wiki_id: str,
        scope: dict[str, Any],
        claims: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        scope = bind_scope_to_product_catalog(scope, self.product_catalog)
        claims = normalize_claims(claims)
        source = self._revision_source(wiki_id)
        self._expire_stale_candidates_for_source(wiki_id, str(source["content_hash"] or ""), actor)
        now = utc_now()
        existing = self._node_by_business_key("knowledge", wiki_id)
        products = _source_product_names(source)
        source_snapshot = _source_snapshot(source)
        source_snapshot["changed_fields"] = []
        properties = {
            "scope_review_status": "candidate",
            "claims_review_status": "candidate",
            "product_category_name": str(source.get("product_category_name") or ""),
            "source_products": products,
            "latest_source_snapshot": source_snapshot,
        }
        values = (
            wiki_id,
            str(source.get("question") or wiki_id),
            _json_dump(scope),
            _json_dump(claims),
            _json_dump(properties),
            str(source.get("source_update_time") or ""),
            str(source.get("content_hash") or ""),
            now,
        )
        if existing:
            self.connection.execute(
                """
                UPDATE kg_nodes
                SET canonical_name = ?, scope_json = ?, claims_json = ?, properties_json = ?,
                    source_version = ?, content_hash = ?, status = 'active', updated_at = ?
                WHERE node_id = ?
                """,
                (*values[1:], existing["node_id"]),
            )
        else:
            node_id = str(uuid.uuid4())
            self.connection.execute(
                """
                INSERT INTO kg_nodes (
                    node_id, node_type, business_key, canonical_name, aliases_json,
                    scope_json, claims_json, properties_json, source_system,
                    source_version, content_hash, status, created_at, updated_at
                ) VALUES (?, 'knowledge', ?, ?, '[]', ?, ?, ?, 'kb_retrieval_index', ?, ?, 'active', ?, ?)
                """,
                (node_id, *values, now),
            )
        node = self._node_by_business_key("knowledge", wiki_id)
        assert node is not None
        return node

    def _upsert_product_node(self, product_name: str, category: str = "") -> dict[str, Any]:
        if self.product_catalog:
            model_categories = {
                model: catalog_category
                for catalog_category, models in self.product_catalog.items()
                for model in models
            }
            if product_name not in model_categories:
                raise ValueError(f"产品矩阵型号不在 8085 型号库中：{product_name}")
            category = model_categories[product_name]
        existing = self._node_by_business_key("product_model", product_name)
        now = utc_now()
        if existing:
            return existing
        node_id = str(uuid.uuid4())
        self.connection.execute(
            """
            INSERT INTO kg_nodes (
                node_id, node_type, business_key, canonical_name, aliases_json,
                scope_json, claims_json, properties_json, source_system,
                source_version, content_hash, status, created_at, updated_at
            ) VALUES (?, 'product_model', ?, ?, '[]', '{}', '{}', ?, ?, ?, ?, 'active', ?, ?)
            """,
            (
                node_id,
                product_name,
                product_name,
                _json_dump({"product_category": category, "catalog_snapshot": self.catalog_snapshot or {}}),
                "8085_product_catalog" if self.product_catalog else "product_matrix",
                str((self.catalog_snapshot or {}).get("content_hash") or ""),
                str((self.catalog_snapshot or {}).get("content_hash") or ""),
                now,
                now,
            ),
        )
        return self._node_by_business_key("product_model", product_name) or {}

    def preview_candidates(
        self,
        from_wiki_id: str,
        to_wiki_id: str,
        from_scope: dict[str, Any],
        from_claims: dict[str, Any],
        to_scope: dict[str, Any],
        to_claims: dict[str, Any],
    ) -> dict[str, Any]:
        from_wiki_id = str(from_wiki_id or "").strip()
        to_wiki_id = str(to_wiki_id or "").strip()
        if not from_wiki_id or not to_wiki_id or from_wiki_id == to_wiki_id:
            raise ValueError("需要两条不同的知识 Wiki ID。")
        from_source = self._revision_source(from_wiki_id)
        to_source = self._revision_source(to_wiki_id)
        prepared_from_scope = bind_scope_to_product_catalog(from_scope, self.product_catalog)
        prepared_to_scope = bind_scope_to_product_catalog(to_scope, self.product_catalog)
        prepared_from_claims = normalize_claims(from_claims)
        prepared_to_claims = normalize_claims(to_claims)
        results = derive_candidate_relations(
            prepared_from_scope,
            prepared_from_claims,
            prepared_to_scope,
            prepared_to_claims,
            self.product_catalog,
        )
        source_hashes = {
            from_wiki_id: str(from_source.get("content_hash") or ""),
            to_wiki_id: str(to_source.get("content_hash") or ""),
        }
        existing_types: set[str] = set()
        from_node = self._node_by_business_key("knowledge", from_wiki_id)
        to_node = self._node_by_business_key("knowledge", to_wiki_id)
        if from_node and to_node:
            rows = self.connection.execute(
                """
                SELECT relation_type FROM kg_edges
                WHERE from_node_id=? AND to_node_id=?
                  AND review_status IN ('candidate', 'confirmed')
                  AND source_content_hashes_json=?
                """,
                (from_node["node_id"], to_node["node_id"], _json_dump(source_hashes)),
            ).fetchall()
            existing_types = {str(row[0]) for row in rows}
        return {
            "from_wiki_id": from_wiki_id,
            "to_wiki_id": to_wiki_id,
            "from_scope": prepared_from_scope,
            "to_scope": prepared_to_scope,
            "from_claims": prepared_from_claims,
            "to_claims": prepared_to_claims,
            "source_hashes": source_hashes,
            "relations": [
                {**result, "existing": result["relation_type"] in existing_types}
                for result in results
            ],
        }

    def create_candidates(
        self,
        from_wiki_id: str,
        to_wiki_id: str,
        from_scope: dict[str, Any],
        from_claims: dict[str, Any],
        to_scope: dict[str, Any],
        to_claims: dict[str, Any],
        actor: str,
        generated_by: str = "rule",
        confidence: Any = None,
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        from_wiki_id = str(from_wiki_id or "").strip()
        to_wiki_id = str(to_wiki_id or "").strip()
        if not from_wiki_id or not to_wiki_id or from_wiki_id == to_wiki_id:
            raise ValueError("需要两条不同的知识 Wiki ID。")
        if generated_by not in {"rule", "ai"}:
            raise ValueError("候选生成方式只能是 rule 或 ai。")
        preview = self.preview_candidates(
            from_wiki_id, to_wiki_id, from_scope, from_claims, to_scope, to_claims
        )
        results = preview["relations"]
        if not results:
            raise ValueError("证据不足以建立知识间候选关系。")
        from_node = self.upsert_knowledge_node(
            from_wiki_id, preview["from_scope"], preview["from_claims"], actor
        )
        to_node = self.upsert_knowledge_node(
            to_wiki_id, preview["to_scope"], preview["to_claims"], actor
        )
        from_source = self._revision_source(from_wiki_id)
        to_source = self._revision_source(to_wiki_id)
        source_hashes = preview["source_hashes"]
        response_edges: list[dict[str, Any]] = []
        created_count = 0
        for result in results:
            relation_type = result["relation_type"]
            duplicate = self.connection.execute(
                """
                SELECT * FROM kg_edges
                WHERE from_node_id = ? AND to_node_id = ? AND relation_type = ?
                  AND review_status IN ('candidate', 'confirmed')
                  AND source_content_hashes_json = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (from_node["node_id"], to_node["node_id"], relation_type, _json_dump(source_hashes)),
            ).fetchone()
            if duplicate:
                response_edges.append({**_edge_payload(duplicate), "created": False, "candidate_reason": "同版本候选已存在。"})
                continue
            try:
                final_confidence = float(result["confidence"] if confidence is None else confidence)
            except (TypeError, ValueError) as exc:
                raise ValueError("confidence 必须是 0 到 1 之间的数值。") from exc
            if not 0 <= final_confidence <= 1:
                raise ValueError("confidence 必须是 0 到 1 之间的数值。")
            now = utc_now()
            edge_id = str(uuid.uuid4())
            automatic_evidence = {
                "rule_reason": result["reason"],
                "from_question": str(from_source.get("question") or "")[:500],
                "to_question": str(to_source.get("question") or "")[:500],
                "from_answer_excerpt": str(from_source.get("answer") or "")[:800],
                "to_answer_excerpt": str(to_source.get("answer") or "")[:800],
                "provided_evidence": evidence or {},
            }
            provenance = {
                "generated_by": generated_by,
                "source_system": "kb_retrieval_index",
                "source_wiki_ids": [from_wiki_id, to_wiki_id],
                "requested_by": actor,
                "product_catalog_snapshot": self.catalog_snapshot or {},
            }
            self.connection.execute(
                """
                INSERT INTO kg_edges (
                    edge_id, from_node_id, to_node_id, relation_type, evidence_json,
                    scope_basis_json, confidence, review_status, generated_by, provenance_json,
                    source_version, source_content_hashes_json, review_note, reviewed_by,
                    reviewed_at, valid_from, valid_to, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'candidate', ?, ?, ?, ?, '', '', NULL, ?, NULL, ?, ?)
                """,
                (
                    edge_id,
                    from_node["node_id"],
                    to_node["node_id"],
                    relation_type,
                    _json_dump(automatic_evidence),
                    _json_dump(result["scope_basis"]),
                    final_confidence,
                    generated_by,
                    _json_dump(provenance),
                    f"{from_source.get('source_update_time') or ''}|{to_source.get('source_update_time') or ''}",
                    _json_dump(source_hashes),
                    now,
                    now,
                    now,
                ),
            )
            _record_event(
                self.connection,
                edge_id,
                "candidate_created",
                actor,
                None,
                "candidate",
                {"relation_type": relation_type, "generated_by": generated_by},
            )
            created_count += 1
            edge = self.connection.execute("SELECT * FROM kg_edges WHERE edge_id = ?", (edge_id,)).fetchone()
            assert edge is not None
            response_edges.append({**_edge_payload(edge), "created": True, "candidate_reason": result["reason"]})
        self.connection.commit()
        return {
            "edges": response_edges,
            "edge": response_edges[0],
            "created_count": created_count,
            "created": created_count > 0,
            "reason": "; ".join(str(item.get("candidate_reason") or "") for item in response_edges),
        }

    def create_candidate(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Compatibility alias; one pair can now create multiple candidate edges."""
        return self.create_candidates(*args, **kwargs)

    def review_edge(self, edge_id: str, decision: str, note: str, actor: str) -> dict[str, Any]:
        decision = str(decision or "").strip()
        if decision not in {"confirmed", "rejected"}:
            raise ValueError("审核结论只能是 confirmed 或 rejected。")
        row = self.connection.execute("SELECT * FROM kg_edges WHERE edge_id = ?", (edge_id,)).fetchone()
        if row is None:
            raise ValueError("未找到图谱关系。")
        if row["review_status"] != "candidate":
            raise ValueError("只有 candidate 状态的关系可以审核。")
        now = utc_now()
        self.connection.execute(
            """
            UPDATE kg_edges
            SET review_status = ?, review_note = ?, reviewed_by = ?, reviewed_at = ?, updated_at = ?
            WHERE edge_id = ?
            """,
            (decision, str(note or "").strip()[:2000], actor, now, now, edge_id),
        )
        _record_event(
            self.connection,
            edge_id,
            f"review_{decision}",
            actor,
            "candidate",
            decision,
            {"review_note": str(note or "").strip()[:2000]},
        )
        self.connection.commit()
        updated = self.connection.execute("SELECT * FROM kg_edges WHERE edge_id = ?", (edge_id,)).fetchone()
        assert updated is not None
        return _edge_payload(updated)

    def expire_stale_candidates(self, wiki_id: str | None, actor: str) -> int:
        return int(self.refresh_stale_relationships(wiki_id, actor)["expired_count"])

    def list_edges(
        self,
        wiki_id: str | None = None,
        review_status: str | None = None,
        relation_type: str | None = None,
        effective_only: bool = False,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        filters: list[str] = []
        values: list[Any] = []
        joins = """
            FROM kg_edges e
            JOIN kg_nodes f ON f.node_id = e.from_node_id
            JOIN kg_nodes t ON t.node_id = e.to_node_id
        """
        if wiki_id:
            filters.append("(f.business_key = ? OR t.business_key = ?)")
            values.extend([wiki_id, wiki_id])
        if review_status:
            if review_status not in REVIEW_STATUSES:
                raise ValueError("review_status 不合法。")
            filters.append("e.review_status = ?")
            values.append(review_status)
        if relation_type:
            if relation_type not in RELATION_TYPES:
                raise ValueError("relation_type 不合法。")
            filters.append("e.relation_type = ?")
            values.append(relation_type)
        if effective_only:
            filters.extend([
                "e.review_status = 'confirmed'",
                "e.valid_to IS NULL",
                "NOT EXISTS (SELECT 1 FROM kg_edges child WHERE child.supersedes_edge_id = e.edge_id)",
            ])
        where = f" WHERE {' AND '.join(filters)}" if filters else ""
        total = int(self.connection.execute(f"SELECT COUNT(*) {joins}{where}", values).fetchone()[0])
        rows = self.connection.execute(
            f"""
            SELECT e.*, f.business_key AS from_business_key, f.canonical_name AS from_name,
                   t.business_key AS to_business_key, t.canonical_name AS to_name,
                   EXISTS(SELECT 1 FROM kg_edges child WHERE child.supersedes_edge_id=e.edge_id) AS has_newer_revision
            {joins}{where}
            ORDER BY CASE e.review_status WHEN 'candidate' THEN 0 WHEN 'confirmed' THEN 1 ELSE 2 END,
                     CASE e.revision_kind WHEN 'human_adjustment' THEN 0 WHEN 'source_revalidation' THEN 1 ELSE 2 END,
                     e.updated_at DESC
            LIMIT ? OFFSET ?
            """,
            [*values, page_size, (page - 1) * page_size],
        ).fetchall()
        items = []
        for row in rows:
            payload = _edge_payload(row)
            payload["is_current_revision"] = not bool(payload.pop("has_newer_revision", 0))
            payload["is_effective"] = bool(
                payload["review_status"] == "confirmed"
                and payload["is_current_revision"]
                and not payload.get("valid_to")
            )
            items.append(payload)
        return {"items": items, "total": total, "page": page, "page_size": page_size, "effective_only": effective_only}

    def knowledge_detail(self, wiki_id: str) -> dict[str, Any]:
        source = self._revision_source(wiki_id)
        node = self._node_by_business_key("knowledge", wiki_id)
        edge_result = self.list_edges(wiki_id=wiki_id, page_size=100)
        effective_edge_result = self.list_edges(wiki_id=wiki_id, effective_only=True, page_size=100)
        products = self.connection.execute(
            """
            SELECT product_name, product_category, manual_edit, edit_source, update_time
            FROM product_matrix
            WHERE question_wiki_id = ? AND is_configured = 1
            ORDER BY product_name
            """,
            (wiki_id,),
        ).fetchall()
        node_payload = None
        if node:
            node_payload = dict(node)
            for key in ("aliases_json", "scope_json", "claims_json", "properties_json"):
                node_payload[key.removesuffix("_json")] = _json_load(node_payload.pop(key, ""), {})
        return {
            "source": {
                "question_wiki_id": wiki_id,
                "question": str(source.get("question") or ""),
                "source_version": str(source.get("source_update_time") or ""),
                "content_hash": str(source.get("content_hash") or ""),
            },
            "node": node_payload,
            "products": [dict(product) for product in products],
            "edges": edge_result["items"],
            "effective_edges": effective_edge_result["items"],
        }

    def summary(self) -> dict[str, Any]:
        counts = {row[0]: int(row[1]) for row in self.connection.execute("SELECT review_status, COUNT(*) FROM kg_edges GROUP BY review_status")}
        node_count = int(self.connection.execute("SELECT COUNT(*) FROM kg_nodes").fetchone()[0])
        event_count = int(self.connection.execute("SELECT COUNT(*) FROM kg_edge_events").fetchone()[0])
        effective_edge_count = int(self.connection.execute(
            """
            SELECT COUNT(*) FROM kg_edges e
            WHERE e.review_status='confirmed' AND e.valid_to IS NULL
              AND NOT EXISTS (SELECT 1 FROM kg_edges child WHERE child.supersedes_edge_id=e.edge_id)
            """
        ).fetchone()[0])
        human_revision_count = int(self.connection.execute(
            "SELECT COUNT(*) FROM kg_edges WHERE revision_kind='human_adjustment'"
        ).fetchone()[0])
        return {
            "node_count": node_count,
            "edge_counts": counts,
            "effective_edge_count": effective_edge_count,
            "human_revision_count": human_revision_count,
            "event_count": event_count,
            "product_catalog_snapshot": self.catalog_snapshot or {},
        }

    def _topic_definition(self, topic_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT topic_id, display_name, allowed_categories_json, description, include_rules,
                   exclude_rules, lifecycle, vocabulary_version, created_by, created_at, updated_at
            FROM kg_topic_definitions WHERE topic_id=?
            """,
            (str(topic_id or "").strip(),),
        ).fetchone()
        if row is None:
            return None
        definition = dict(row)
        definition["allowed_categories"] = _source_product_categories(
            ",".join(_json_load(definition.pop("allowed_categories_json"), []))
        )
        return definition

    def _configured_categories_for_wiki(self, wiki_id: str) -> list[str]:
        rows = self.connection.execute(
            """
            SELECT product_category FROM product_matrix
            WHERE question_wiki_id=? AND is_configured=1
            """,
            (wiki_id,),
        ).fetchall()
        return sorted({
            category
            for row in rows
            for category in _source_product_categories(row["product_category"])
        })

    @staticmethod
    def _topic_definition_applies(definition: dict[str, Any] | None, categories: list[str]) -> bool:
        allowed = set((definition or {}).get("allowed_categories") or [])
        return bool(categories) and bool(allowed) and set(categories).issubset(allowed)

    def catalog_topic_vocabulary(self, category: str | None = None) -> dict[str, Any]:
        categories = _source_product_categories(category)
        rows = self.connection.execute(
            """
            SELECT topic_id, display_name, allowed_categories_json, description, include_rules,
                   exclude_rules, lifecycle, vocabulary_version
            FROM kg_topic_definitions
            WHERE lifecycle='active'
            ORDER BY display_name, topic_id
            """
        ).fetchall()
        items = []
        for row in rows:
            definition = dict(row)
            definition["allowed_categories"] = _source_product_categories(
                ",".join(_json_load(definition.pop("allowed_categories_json"), []))
            )
            if not categories or self._topic_definition_applies(definition, categories):
                items.append(definition)
        return {
            "category": str(category or "").strip(),
            "categories": categories,
            "items": items,
            "source_contract": {
                "ownership": "主题词表是图谱侧车治理定义，不修改 knowledge_base_v1 或 product_matrix。",
                "selection_rule": "只返回当前品类全部适用的 active 主题；多品类知识不会被放入单品类主题。",
            },
        }

    def _catalog_records(self) -> list[dict[str, Any]]:
        """Build a read-only category/topic projection from existing fact tables."""
        source_rows = self.connection.execute(
            """
            SELECT question_wiki_id, question, content_hash
            FROM kb_retrieval_index
            WHERE library_type='knowledge_base_v1' AND index_status='ready'
            ORDER BY question_wiki_id
            """
        ).fetchall()
        matrix_rows = self.connection.execute(
            """
            SELECT question_wiki_id, product_name, product_category
            FROM product_matrix
            WHERE is_configured=1
            """
        ).fetchall()
        node_rows = self.connection.execute(
            """
            SELECT business_key, scope_json
            FROM kg_nodes
            WHERE node_type='knowledge' AND status='active'
            """
        ).fetchall()
        assignment_rows = self.connection.execute(
            """
            SELECT assignment_id, wiki_id, topic_id, topic, vocabulary_version, review_note, source_content_hash,
                   source_version, assigned_by, assigned_at, updated_at
            FROM kg_topic_assignments
            """
        ).fetchall()
        definition_rows = self.connection.execute(
            """
            SELECT topic_id, display_name, allowed_categories_json, lifecycle, vocabulary_version
            FROM kg_topic_definitions
            """
        ).fetchall()
        edge_rows = self.connection.execute(
            """
            SELECT e.edge_id, e.relation_type, e.review_status, e.valid_to,
                   f.business_key AS from_wiki_id, t.business_key AS to_wiki_id,
                   EXISTS(SELECT 1 FROM kg_edges child WHERE child.supersedes_edge_id=e.edge_id) AS has_newer_revision
            FROM kg_edges e
            JOIN kg_nodes f ON f.node_id=e.from_node_id AND f.node_type='knowledge'
            JOIN kg_nodes t ON t.node_id=e.to_node_id AND t.node_type='knowledge'
            """
        ).fetchall()

        matrix_by_wiki: dict[str, list[dict[str, str]]] = {}
        for row in matrix_rows:
            wiki_id = str(row["question_wiki_id"] or "").strip()
            product_name = str(row["product_name"] or "").strip()
            if wiki_id and product_name:
                matrix_by_wiki.setdefault(wiki_id, []).append({
                    "product_name": product_name,
                    "product_categories": _source_product_categories(row["product_category"]),
                })
        topics_by_wiki = {
            str(row["business_key"]): str(_json_load(row["scope_json"], {}).get("topic") or "").strip()
            for row in node_rows
        }
        assignments_by_wiki = {str(row["wiki_id"]): dict(row) for row in assignment_rows}
        definitions_by_id = {}
        for row in definition_rows:
            definition = dict(row)
            definition["allowed_categories"] = _source_product_categories(
                ",".join(_json_load(definition.pop("allowed_categories_json"), []))
            )
            definitions_by_id[str(definition["topic_id"])] = definition
        edges_by_wiki: dict[str, dict[str, dict[str, Any]]] = {}
        for row in edge_rows:
            edge = dict(row)
            for wiki_id in {str(edge["from_wiki_id"]), str(edge["to_wiki_id"])}:
                edges_by_wiki.setdefault(wiki_id, {})[str(edge["edge_id"])] = edge

        records = []
        for row in source_rows:
            wiki_id = str(row["question_wiki_id"])
            product_links = matrix_by_wiki.get(wiki_id, [])
            categories = sorted({
                category for link in product_links for category in link["product_categories"]
            })
            assignment = assignments_by_wiki.get(wiki_id)
            source_content_hash = str(row["content_hash"] or "")
            assignment_is_current = bool(
                assignment and assignment["source_content_hash"] == source_content_hash
            )
            assignment_definition = definitions_by_id.get(str((assignment or {}).get("topic_id") or ""))
            assignment_vocabulary_is_current = bool(
                assignment_definition
                and assignment_definition["lifecycle"] == "active"
                and self._topic_definition_applies(assignment_definition, categories)
            )
            if assignment_is_current and assignment_vocabulary_is_current:
                topic = str(assignment["topic"])
                topic_status = "人工已校对"
            elif assignment:
                topic = "待归类"
                topic_status = "主题待复核" if not assignment_is_current else "词表待复核"
            elif topics_by_wiki.get(wiki_id):
                topic = topics_by_wiki[wiki_id]
                topic_status = "既有图谱主题"
            else:
                topic = "待归类"
                topic_status = "待归类"
            records.append({
                "wiki_id": wiki_id,
                "question": str(row["question"] or ""),
                "categories": categories or ["范围未知"],
                "topic": topic,
                "topic_status": topic_status,
                "product_relation_count": len(product_links),
                "scope_unknown": not bool(categories),
                "edges": list(edges_by_wiki.get(wiki_id, {}).values()),
            })
        return records

    @staticmethod
    def _catalog_edge_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
        edges = {
            str(edge["edge_id"]): edge
            for record in records
            for edge in record["edges"]
        }
        active_edges = [
            edge for edge in edges.values()
            if edge["review_status"] == "candidate"
            or (edge["review_status"] == "confirmed" and not edge["valid_to"] and not edge["has_newer_revision"])
        ]
        relation_type_counts: dict[str, int] = {}
        for edge in active_edges:
            relation_type = str(edge["relation_type"])
            relation_type_counts[relation_type] = relation_type_counts.get(relation_type, 0) + 1
        return {
            "candidate_edge_count": sum(edge["review_status"] == "candidate" for edge in active_edges),
            "effective_edge_count": sum(edge["review_status"] == "confirmed" for edge in active_edges),
            "governance_issue_count": sum(
                edge["relation_type"] in {"DUPLICATES", "CONFLICTS_WITH"}
                for edge in active_edges
            ),
            "relation_type_counts": relation_type_counts,
        }

    def catalog_overview(self) -> dict[str, Any]:
        records = self._catalog_records()
        catalog_categories = list((self.product_catalog or {}).keys())
        observed_categories = sorted({
            category for record in records for category in record["categories"] if category != "范围未知"
        })
        categories = list(dict.fromkeys([*catalog_categories, *observed_categories, "范围未知"]))
        items = []
        for category in categories:
            grouped = [record for record in records if category in record["categories"]]
            metrics = self._catalog_edge_metrics(grouped)
            items.append({
                "category": category,
                "knowledge_count": len(grouped),
                "product_relation_count": sum(record["product_relation_count"] for record in grouped),
                "scope_unknown_count": sum(record["scope_unknown"] for record in grouped),
                "topic_count": len({record["topic"] for record in grouped}),
                **metrics,
            })
        return {
            "items": items,
            "source_knowledge_count": len(records),
            "overall_metrics": {
                "knowledge_count": len(records),
                "product_relation_count": sum(record["product_relation_count"] for record in records),
                "scope_unknown_count": sum(record["scope_unknown"] for record in records),
                **self._catalog_edge_metrics(records),
            },
            "source_contract": {
                "knowledge": "knowledge_base_v1 的本地只读索引 kb_retrieval_index",
                "product_relations": "product_matrix（is_configured=1）",
                "topics": "kg_nodes.scope_json.topic 的现有侧车字段；缺失即待归类",
                "write_scope": "本接口不写入 knowledge_base_v1、product_matrix、kg_nodes、kg_edges 或 kg_edge_events。",
            },
        }

    def catalog_topics(self, category: str, topic: str | None = None) -> dict[str, Any]:
        category = str(category or "").strip()
        if not category:
            raise ValueError("category 不能为空。")
        records = [record for record in self._catalog_records() if category in record["categories"]]
        by_topic: dict[str, list[dict[str, Any]]] = {}
        for record in records:
            by_topic.setdefault(record["topic"], []).append(record)
        topic_items = []
        for topic_name, grouped in sorted(by_topic.items(), key=lambda item: (item[0] == "待归类", item[0])):
            topic_items.append({
                "topic": topic_name,
                "knowledge_count": len(grouped),
                "product_relation_count": sum(record["product_relation_count"] for record in grouped),
                "scope_unknown_count": sum(record["scope_unknown"] for record in grouped),
                **self._catalog_edge_metrics(grouped),
            })
        selected_topic = str(topic or "").strip()
        selected_records = by_topic.get(selected_topic, []) if selected_topic else []
        return {
            "category": category,
            "items": topic_items,
            "selected_topic": selected_topic,
            "knowledge_items": [
                {
                    "wiki_id": record["wiki_id"],
                    "question": record["question"],
                    "product_relation_count": record["product_relation_count"],
                    "scope_status": "范围未知" if record["scope_unknown"] else "已登记产品范围",
                }
                for record in selected_records[:100]
            ],
            "knowledge_total": len(selected_records),
        }

    def catalog_attention_queue(
        self,
        category: str | None = None,
        reason: str | None = None,
        wiki_id: str | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        """List knowledge that lacks a usable topic or product scope without inferring either."""
        selected_category = str(category or "").strip()
        selected_reason = str(reason or "all").strip() or "all"
        selected_wiki_id = str(wiki_id or "").strip()
        if selected_reason not in {"all", "topic_missing", "topic_stale", "topic_vocabulary_stale", "scope_unknown"}:
            raise ValueError("reason 仅支持 all、topic_missing、topic_stale、topic_vocabulary_stale 或 scope_unknown。")
        if page < 1 or page_size < 1 or page_size > 200:
            raise ValueError("page 必须大于 0，page_size 必须在 1 到 200 之间。")

        records = self._catalog_records()
        categories = sorted({category for record in records for category in record["categories"]})

        def reasons(record: dict[str, Any]) -> list[str]:
            result = []
            if record["topic"] == "待归类":
                if record["topic_status"] == "主题待复核":
                    result.append("主题待复核")
                elif record["topic_status"] == "词表待复核":
                    result.append("词表待复核")
                else:
                    result.append("待归类")
            if record["scope_unknown"]:
                result.append("范围未知")
            return result

        attention_records = [record for record in records if reasons(record)]
        filtered = [
            record for record in attention_records
            if (not selected_category or selected_category in record["categories"])
            and (not selected_wiki_id or record["wiki_id"] == selected_wiki_id)
            and (
                selected_reason == "all"
                or (selected_reason == "topic_missing" and record["topic_status"] == "待归类")
                or (selected_reason == "topic_stale" and record["topic_status"] == "主题待复核")
                or (selected_reason == "topic_vocabulary_stale" and record["topic_status"] == "词表待复核")
                or (selected_reason == "scope_unknown" and record["scope_unknown"])
            )
        ]
        filtered.sort(key=lambda record: record["wiki_id"])
        total = len(filtered)
        start = (page - 1) * page_size
        visible = filtered[start:start + page_size]
        return {
            "category": selected_category,
            "reason": selected_reason,
            "wiki_id": selected_wiki_id,
            "page": page,
            "page_size": page_size,
            "total": total,
            "items": [
                {
                    "wiki_id": record["wiki_id"],
                    "question": record["question"],
                    "categories": record["categories"],
                    "topic": record["topic"],
                    "topic_status": record["topic_status"],
                    "product_relation_count": record["product_relation_count"],
                    "attention_reasons": reasons(record),
                }
                for record in visible
            ],
            "summary": {
                "attention_count": len(attention_records),
                "topic_missing_count": sum(record["topic_status"] == "待归类" for record in records),
                "topic_stale_count": sum(record["topic_status"] == "主题待复核" for record in records),
                "topic_vocabulary_stale_count": sum(record["topic_status"] == "词表待复核" for record in records),
                "scope_unknown_count": sum(record["scope_unknown"] for record in records),
            },
            "available_categories": categories,
            "available_topics": sorted({
                record["topic"] for record in records if record["topic"] != "待归类"
            }),
            "source_contract": {
                "knowledge": "knowledge_base_v1 的本地只读索引 kb_retrieval_index",
                "product_relations": "product_matrix（is_configured=1）",
                "topics": "既有图谱主题或内容哈希与词表状态均有效的人工主题侧车投影；缺失即待归类",
                "write_scope": "本接口只读，不推断主题或全量产品范围，也不写入任何表或审计事件。",
            },
        }

    def assign_catalog_topic(
        self,
        wiki_id: str,
        topic_id: str,
        review_note: str,
        confirmation_phrase: str,
        actor: str,
    ) -> dict[str, Any]:
        if str(confirmation_phrase or "").strip() != TOPIC_ASSIGNMENT_CONFIRMATION_PHRASE:
            raise ValueError(f"确认词必须为“{TOPIC_ASSIGNMENT_CONFIRMATION_PHRASE}”。")
        wiki_id = str(wiki_id or "").strip()
        topic_id = str(topic_id or "").strip()
        review_note = str(review_note or "").strip()
        if not wiki_id:
            raise ValueError("wiki_id 不能为空。")
        if not topic_id:
            raise ValueError("必须从受控主题词表中选择主题。")
        if not review_note:
            raise ValueError("人工主题校对必须填写依据。")
        source = self._source_knowledge(wiki_id)
        categories = self._configured_categories_for_wiki(wiki_id)
        definition = self._topic_definition(topic_id)
        if definition is None:
            raise ValueError("主题不在受控主题词表中。")
        if definition["lifecycle"] != "active":
            raise ValueError("当前主题未启用，不能用于人工校对。")
        if not self._topic_definition_applies(definition, categories):
            raise ValueError("当前知识的已登记产品品类不适用于该主题，未写入主题。")
        topic = str(definition["display_name"])
        current = self.connection.execute(
            "SELECT * FROM kg_topic_assignments WHERE wiki_id=?", (wiki_id,)
        ).fetchone()
        now = utc_now()
        assignment_id = str(current["assignment_id"]) if current else str(uuid.uuid4())
        previous_topic_id = str(current["topic_id"] or "") if current else ""
        previous_topic = str(current["topic"] or "") if current else ""
        event_type = "topic_reassigned" if current else "topic_assigned"
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            if current:
                self.connection.execute(
                    """
                    UPDATE kg_topic_assignments
                    SET topic_id=?, topic=?, vocabulary_version=?, review_note=?, source_content_hash=?, source_version=?,
                        assigned_by=?, updated_at=?
                    WHERE assignment_id=?
                    """,
                    (
                        topic_id, topic, str(definition["vocabulary_version"]), review_note[:2000],
                        str(source["content_hash"] or ""),
                        str(source["source_update_time"] or ""), actor, now, assignment_id,
                    ),
                )
            else:
                self.connection.execute(
                    """
                    INSERT INTO kg_topic_assignments (
                        assignment_id, wiki_id, topic_id, topic, vocabulary_version, review_note, source_content_hash,
                        source_version, assigned_by, assigned_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        assignment_id, wiki_id, topic_id, topic, str(definition["vocabulary_version"]), review_note[:2000],
                        str(source["content_hash"] or ""), str(source["source_update_time"] or ""),
                        actor, now, now,
                    ),
                )
            self.connection.execute(
                """
                INSERT INTO kg_topic_assignment_events (
                    event_id, assignment_id, event_type, previous_topic_id, current_topic_id,
                    vocabulary_version, previous_topic, current_topic, review_note, actor, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()), assignment_id, event_type, previous_topic_id, topic_id,
                    str(definition["vocabulary_version"]), previous_topic, topic, review_note[:2000], actor, now,
                ),
            )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        assignment = self.connection.execute(
            "SELECT * FROM kg_topic_assignments WHERE assignment_id=?", (assignment_id,)
        ).fetchone()
        return {
            "assignment": dict(assignment or {}),
            "topic_definition": definition,
            "event_type": event_type,
            "write_scope": "仅写入 kg_topic_assignments 和 kg_topic_assignment_events；不修改知识、产品矩阵、kg_nodes、关系或关系事件。",
        }

    def catalog_candidate_preview(
        self,
        category: str,
        topics: Iterable[str],
        max_pairs_per_topic: int = 20,
    ) -> dict[str, Any]:
        """Preview rule candidates for explicit, already-classified catalog buckets."""
        category = str(category or "").strip()
        selected_topics = list(dict.fromkeys(
            str(topic or "").strip() for topic in topics if str(topic or "").strip()
        ))
        if not category or category == "范围未知":
            raise ValueError("候选预览必须选择一个已登记产品品类。")
        if not 1 <= len(selected_topics) <= 5:
            raise ValueError("候选预览需要选择 1 到 5 个已归类主题。")
        if "待归类" in selected_topics:
            raise ValueError("待归类知识不能进入候选预览。")
        if not 1 <= max_pairs_per_topic <= 20:
            raise ValueError("每个主题最多预览 20 个知识对。")

        records = [
            record for record in self._catalog_records()
            if category in record["categories"] and record["topic"] in selected_topics
        ]
        wiki_ids = [record["wiki_id"] for record in records]
        if not wiki_ids:
            return {
                "category": category,
                "topics": selected_topics,
                "topic_items": [],
                "candidate_items": [],
                "candidate_count": 0,
                "source_knowledge_count": 0,
                "skipped": {},
                "source_contract": {
                    "write_scope": "本接口只读取事实来源和图谱侧车，不写入任何表或审计事件。",
                },
            }

        placeholders = ",".join("?" for _ in wiki_ids)
        node_rows = self.connection.execute(
            f"""
            SELECT business_key, scope_json, claims_json
            FROM kg_nodes
            WHERE node_type='knowledge' AND status='active' AND business_key IN ({placeholders})
            """,
            wiki_ids,
        ).fetchall()
        source_rows = self.connection.execute(
            f"""
            SELECT question_wiki_id, content_hash, question, answer, source_update_time
            FROM kb_retrieval_index
            WHERE library_type='knowledge_base_v1' AND index_status='ready'
              AND question_wiki_id IN ({placeholders})
            """,
            wiki_ids,
        ).fetchall()
        nodes_by_wiki = {str(row["business_key"]): dict(row) for row in node_rows}
        sources_by_wiki = {str(row["question_wiki_id"]): dict(row) for row in source_rows}
        active_edges = {
            (
                str(edge["from_wiki_id"]),
                str(edge["to_wiki_id"]),
                str(edge["relation_type"]),
            )
            for record in records
            for edge in record["edges"]
            if edge["review_status"] == "candidate"
            or (edge["review_status"] == "confirmed" and not edge["valid_to"] and not edge["has_newer_revision"])
        }

        prepared_by_topic: dict[str, list[dict[str, Any]]] = {topic: [] for topic in selected_topics}
        skipped: dict[str, int] = {}
        for record in records:
            node = nodes_by_wiki.get(record["wiki_id"])
            source = sources_by_wiki.get(record["wiki_id"])
            if not node or not source:
                skipped["missing_graph_node"] = skipped.get("missing_graph_node", 0) + 1
                continue
            try:
                scope = bind_scope_to_product_catalog(_json_load(node["scope_json"], {}), self.product_catalog)
                claims = normalize_claims(_json_load(node["claims_json"], {}))
                resolved_models, _ = _resolved_product_models(scope, self.product_catalog)
            except ValueError:
                skipped["invalid_scope_or_claims"] = skipped.get("invalid_scope_or_claims", 0) + 1
                continue
            if resolved_models is None:
                skipped["scope_unknown"] = skipped.get("scope_unknown", 0) + 1
                continue
            prepared_by_topic[record["topic"]].append({
                "wiki_id": record["wiki_id"],
                "question": str(source.get("question") or ""),
                "answer_excerpt": str(source.get("answer") or "")[:800],
                "content_hash": str(source.get("content_hash") or ""),
                "source_version": str(source.get("source_update_time") or ""),
                "scope": scope,
                "claims": claims,
            })

        symmetric_types = {"DUPLICATES", "CONFLICTS_WITH", "OVERLAPS_WITH"}
        seen: set[tuple[str, str, str]] = set()
        candidate_items: list[dict[str, Any]] = []
        topic_items = []
        for topic in selected_topics:
            prepared = prepared_by_topic[topic]
            scanned_pairs = 0
            topic_candidate_count = 0
            for index, left in enumerate(prepared):
                for right in prepared[index + 1:]:
                    if scanned_pairs >= max_pairs_per_topic:
                        break
                    scanned_pairs += 1
                    for from_item, to_item in ((left, right), (right, left)):
                        for relation in derive_candidate_relations(
                            from_item["scope"], from_item["claims"],
                            to_item["scope"], to_item["claims"], self.product_catalog,
                        ):
                            relation_type = str(relation["relation_type"])
                            if relation_type in symmetric_types:
                                key = (*sorted((from_item["wiki_id"], to_item["wiki_id"])), relation_type)
                            else:
                                key = (from_item["wiki_id"], to_item["wiki_id"], relation_type)
                            if key in seen:
                                continue
                            seen.add(key)
                            candidate_items.append({
                                "topic": topic,
                                "from_wiki_id": from_item["wiki_id"],
                                "from_question": from_item["question"],
                                "from_answer_excerpt": from_item["answer_excerpt"],
                                "to_wiki_id": to_item["wiki_id"],
                                "to_question": to_item["question"],
                                "to_answer_excerpt": to_item["answer_excerpt"],
                                "relation_type": relation_type,
                                "confidence": relation["confidence"],
                                "reason": relation["reason"],
                                "scope_basis": relation["scope_basis"],
                                "source_hashes": {
                                    from_item["wiki_id"]: from_item["content_hash"],
                                    to_item["wiki_id"]: to_item["content_hash"],
                                },
                                "source_versions": {
                                    from_item["wiki_id"]: from_item["source_version"],
                                    to_item["wiki_id"]: to_item["source_version"],
                                },
                                "existing_active_relation": (
                                    (from_item["wiki_id"], to_item["wiki_id"], relation_type) in active_edges
                                    or (
                                        relation_type in symmetric_types
                                        and (to_item["wiki_id"], from_item["wiki_id"], relation_type) in active_edges
                                    )
                                ),
                            })
                            topic_candidate_count += 1
                if scanned_pairs >= max_pairs_per_topic:
                    break
            topic_items.append({
                "topic": topic,
                "eligible_knowledge_count": len(prepared),
                "scanned_pair_count": scanned_pairs,
                "candidate_count": topic_candidate_count,
            })
        return {
            "category": category,
            "topics": selected_topics,
            "max_pairs_per_topic": max_pairs_per_topic,
            "source_knowledge_count": len(records),
            "topic_items": topic_items,
            "candidate_items": candidate_items,
            "candidate_count": len(candidate_items),
            "skipped": skipped,
            "source_contract": {
                "knowledge": "knowledge_base_v1 的本地只读索引 kb_retrieval_index",
                "product_relations": "product_matrix（is_configured=1）",
                "topics_and_claims": "kg_nodes 的既有主题、范围和关键结论字段",
                "write_scope": "本接口只读取事实来源和图谱侧车，不写入任何表或审计事件。",
            },
        }

    def create_catalog_candidate_batch(
        self,
        category: str,
        topics: Iterable[str],
        max_pairs_per_topic: int,
        confirmation_phrase: str,
        actor: str,
    ) -> dict[str, Any]:
        if str(confirmation_phrase or "").strip() != BATCH_CONFIRMATION_PHRASE:
            raise ValueError(f"确认词必须为“{BATCH_CONFIRMATION_PHRASE}”。")
        preview = self.catalog_candidate_preview(category, topics, max_pairs_per_topic)
        proposed = [item for item in preview["candidate_items"] if not item["existing_active_relation"]]
        if not proposed:
            raise ValueError("当前预览没有可写入的新候选关系。")

        now = utc_now()
        batch_id = str(uuid.uuid4())
        snapshot = {
            "source_knowledge_count": preview["source_knowledge_count"],
            "topic_items": preview["topic_items"],
            "skipped": preview["skipped"],
            "proposed_candidate_count": preview["candidate_count"],
            "writeable_candidate_count": len(proposed),
            "product_catalog_snapshot": self.catalog_snapshot or {},
        }
        created_edge_ids: list[str] = []
        existing_count = 0
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self.connection.execute(
                """
                INSERT INTO kg_review_batches (
                    batch_id, category, topics_json, max_pairs_per_topic, source_snapshot_json,
                    confirmation_phrase, status, created_by, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)
                """,
                (
                    batch_id,
                    preview["category"],
                    _json_dump(preview["topics"]),
                    preview["max_pairs_per_topic"],
                    _json_dump(snapshot),
                    BATCH_CONFIRMATION_PHRASE,
                    actor,
                    now,
                ),
            )
            for rank, item in enumerate(proposed, start=1):
                from_node = self._node_by_business_key("knowledge", item["from_wiki_id"])
                to_node = self._node_by_business_key("knowledge", item["to_wiki_id"])
                if not from_node or not to_node:
                    raise ValueError("候选预览来源节点已变化，请重新预览。")
                duplicate = self.connection.execute(
                    """
                    SELECT edge_id FROM kg_edges
                    WHERE from_node_id=? AND to_node_id=? AND relation_type=?
                      AND review_status IN ('candidate', 'confirmed')
                      AND source_content_hashes_json=?
                    LIMIT 1
                    """,
                    (
                        from_node["node_id"],
                        to_node["node_id"],
                        item["relation_type"],
                        _json_dump(item["source_hashes"]),
                    ),
                ).fetchone()
                if duplicate:
                    existing_count += 1
                    continue
                edge_id = str(uuid.uuid4())
                evidence = {
                    "rule_reason": item["reason"],
                    "from_question": item["from_question"][:500],
                    "to_question": item["to_question"][:500],
                    "from_answer_excerpt": item["from_answer_excerpt"],
                    "to_answer_excerpt": item["to_answer_excerpt"],
                    "batch_id": batch_id,
                }
                provenance = {
                    "generated_by": "rule",
                    "source_system": "kb_retrieval_index",
                    "source_wiki_ids": [item["from_wiki_id"], item["to_wiki_id"]],
                    "requested_by": actor,
                    "batch_id": batch_id,
                    "product_catalog_snapshot": self.catalog_snapshot or {},
                }
                self.connection.execute(
                    """
                    INSERT INTO kg_edges (
                        edge_id, from_node_id, to_node_id, relation_type, evidence_json,
                        scope_basis_json, confidence, review_status, generated_by, provenance_json,
                        source_version, source_content_hashes_json, review_note, reviewed_by,
                        reviewed_at, valid_from, valid_to, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'candidate', 'rule', ?, ?, ?, '', '', NULL, ?, NULL, ?, ?)
                    """,
                    (
                        edge_id,
                        from_node["node_id"],
                        to_node["node_id"],
                        item["relation_type"],
                        _json_dump(evidence),
                        _json_dump(item["scope_basis"]),
                        float(item["confidence"]),
                        _json_dump(provenance),
                        f"{item['source_versions'].get(item['from_wiki_id'], '')}|{item['source_versions'].get(item['to_wiki_id'], '')}",
                        _json_dump(item["source_hashes"]),
                        now,
                        now,
                        now,
                    ),
                )
                self.connection.execute(
                    """
                    INSERT INTO kg_review_batch_edges (batch_id, edge_id, cluster_key, rank, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (batch_id, edge_id, f"{item['topic']}:{item['relation_type']}", rank, now),
                )
                _record_event(
                    self.connection,
                    edge_id,
                    "candidate_created",
                    actor,
                    None,
                    "candidate",
                    {"relation_type": item["relation_type"], "generated_by": "rule", "batch_id": batch_id},
                )
                created_edge_ids.append(edge_id)
            if not created_edge_ids:
                raise ValueError("候选在写入前已存在，请重新预览。")
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        return {
            "batch_id": batch_id,
            "status": "active",
            "created_count": len(created_edge_ids),
            "existing_count": existing_count,
            "edge_ids": created_edge_ids,
            "source_snapshot": snapshot,
            "write_scope": "仅写入 kg_review_batches、kg_review_batch_edges、kg_edges（candidate）和 kg_edge_events；不写入业务事实。",
        }

    def candidate_batch_detail(self, batch_id: str) -> dict[str, Any]:
        batch = self.connection.execute(
            "SELECT * FROM kg_review_batches WHERE batch_id=?", (str(batch_id or "").strip(),)
        ).fetchone()
        if batch is None:
            raise ValueError("未找到候选批次。")
        edges = self.connection.execute(
            """
            SELECT b.cluster_key, b.rank, e.*, f.business_key AS from_wiki_id, t.business_key AS to_wiki_id
            FROM kg_review_batch_edges b
            JOIN kg_edges e ON e.edge_id=b.edge_id
            JOIN kg_nodes f ON f.node_id=e.from_node_id
            JOIN kg_nodes t ON t.node_id=e.to_node_id
            WHERE b.batch_id=?
            ORDER BY b.rank, e.created_at
            """,
            (batch["batch_id"],),
        ).fetchall()
        payload = dict(batch)
        payload["topics"] = _json_load(payload.pop("topics_json"), [])
        payload["source_snapshot"] = _json_load(payload.pop("source_snapshot_json"), {})
        return {
            "batch": payload,
            "edges": [
                {**_edge_payload(edge), "cluster_key": edge["cluster_key"], "rank": edge["rank"],
                 "from_wiki_id": edge["from_wiki_id"], "to_wiki_id": edge["to_wiki_id"]}
                for edge in edges
            ],
        }

    def list_candidate_batches(self) -> dict[str, Any]:
        """Return auditable batch progress without touching graph or source facts."""
        rows = self.connection.execute(
            """
            SELECT b.*, COUNT(be.edge_id) AS edge_count,
                   COUNT(DISTINCT be.cluster_key) AS cluster_count,
                   SUM(CASE WHEN e.review_status='candidate' THEN 1 ELSE 0 END) AS candidate_count,
                   SUM(CASE WHEN e.review_status='confirmed' THEN 1 ELSE 0 END) AS confirmed_count,
                   SUM(CASE WHEN e.review_status='rejected' THEN 1 ELSE 0 END) AS rejected_count,
                   SUM(CASE WHEN e.review_status='expired' THEN 1 ELSE 0 END) AS expired_count
            FROM kg_review_batches b
            LEFT JOIN kg_review_batch_edges be ON be.batch_id=b.batch_id
            LEFT JOIN kg_edges e ON e.edge_id=be.edge_id
            GROUP BY b.batch_id
            ORDER BY b.created_at DESC, b.batch_id DESC
            """
        ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["topics"] = _json_load(item.pop("topics_json"), [])
            item.pop("source_snapshot_json", None)
            for key in (
                "edge_count", "cluster_count", "candidate_count", "confirmed_count",
                "rejected_count", "expired_count",
            ):
                item[key] = int(item.get(key) or 0)
            item["reviewed_count"] = (
                item["confirmed_count"] + item["rejected_count"] + item["expired_count"]
            )
            items.append(item)
        return {
            "items": items,
            "source_contract": {
                "batches": "kg_review_batches 与 kg_review_batch_edges 的只读批次投影",
                "edge_status": "kg_edges 的当前 review_status，供批次进度汇总使用",
                "write_scope": "本接口只读，不写入知识、产品矩阵、关系或审计事件。",
            },
        }

    def rollback_catalog_candidate_batch(
        self,
        batch_id: str,
        confirmation_phrase: str,
        note: str,
        actor: str,
    ) -> dict[str, Any]:
        if str(confirmation_phrase or "").strip() != BATCH_ROLLBACK_CONFIRMATION_PHRASE:
            raise ValueError(f"确认词必须为“{BATCH_ROLLBACK_CONFIRMATION_PHRASE}”。")
        note = str(note or "").strip()
        if not note:
            raise ValueError("回退必须填写原因。")
        batch = self.connection.execute(
            "SELECT * FROM kg_review_batches WHERE batch_id=?", (str(batch_id or "").strip(),)
        ).fetchone()
        if batch is None:
            raise ValueError("未找到候选批次。")
        if batch["status"] != "active":
            raise ValueError("该候选批次已经回退。")
        rows = self.connection.execute(
            """
            SELECT e.edge_id, e.review_status FROM kg_review_batch_edges b
            JOIN kg_edges e ON e.edge_id=b.edge_id WHERE b.batch_id=?
            """,
            (batch["batch_id"],),
        ).fetchall()
        now = utc_now()
        expired_count = 0
        preserved_count = 0
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            for row in rows:
                if row["review_status"] != "candidate":
                    preserved_count += 1
                    continue
                self.connection.execute(
                    """
                    UPDATE kg_edges SET review_status='expired', valid_to=?, updated_at=?
                    WHERE edge_id=? AND review_status='candidate'
                    """,
                    (now, now, row["edge_id"]),
                )
                _record_event(
                    self.connection,
                    row["edge_id"],
                    "candidate_batch_rolled_back",
                    actor,
                    "candidate",
                    "expired",
                    {"batch_id": batch["batch_id"], "note": note},
                )
                expired_count += 1
            self.connection.execute(
                """
                UPDATE kg_review_batches
                SET status='rolled_back', rolled_back_by=?, rolled_back_at=?, rollback_note=?
                WHERE batch_id=?
                """,
                (actor, now, note, batch["batch_id"]),
            )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        return {
            "batch_id": batch["batch_id"],
            "status": "rolled_back",
            "expired_count": expired_count,
            "preserved_non_candidate_count": preserved_count,
            "write_scope": "仅将本批仍为 candidate 的 kg_edges 标记为 expired，并追加 kg_edge_events；不删除历史或修改业务事实。",
        }

    def backfill_preview(self, limit: int | None = None) -> dict[str, Any]:
        params: list[Any] = []
        limit_sql = ""
        if limit is not None:
            limit_sql = " LIMIT ?"
            params.append(limit)
        source_rows = self.connection.execute(
            """
            SELECT question_wiki_id FROM kb_retrieval_index
            WHERE library_type='knowledge_base_v1' AND index_status='ready'
            ORDER BY question_wiki_id
            """ + limit_sql,
            params,
        ).fetchall()
        wiki_ids = [str(row[0]) for row in source_rows]
        if not wiki_ids:
            return {"source_knowledge_count": 0, "source_matrix_edge_count": 0, "missing_nodes": 0, "missing_applies_to_edges": 0, "sample_wiki_ids": []}
        placeholders = ",".join("?" for _ in wiki_ids)
        schema_status = graph_schema_status(self.connection)
        tables_ready = schema_status["tables_ready"]
        existing_nodes = 0
        existing_applies = 0
        if tables_ready:
            existing_nodes = int(self.connection.execute(
                f"SELECT COUNT(*) FROM kg_nodes WHERE node_type='knowledge' AND business_key IN ({placeholders})", wiki_ids
            ).fetchone()[0])
        matrix_count = int(self.connection.execute(
            f"SELECT COUNT(*) FROM product_matrix WHERE is_configured=1 AND question_wiki_id IN ({placeholders})", wiki_ids
        ).fetchone()[0])
        if tables_ready:
            existing_applies = int(self.connection.execute(
                f"""
                SELECT COUNT(*) FROM kg_edges e
                JOIN kg_nodes n ON n.node_id=e.from_node_id
                WHERE e.relation_type='APPLIES_TO' AND e.review_status='confirmed'
                  AND n.business_key IN ({placeholders})
                """, wiki_ids
            ).fetchone()[0])
        graph_product_models = {
            str(row[0])
            for row in self.connection.execute(
                "SELECT business_key FROM kg_nodes WHERE node_type='product_model' AND status='active'"
            ).fetchall()
        } if tables_ready else set()
        catalog_models = {
            model for models in (self.product_catalog or {}).values() for model in models
        }
        matrix_models = {
            str(row[0])
            for row in self.connection.execute(
                f"SELECT DISTINCT product_name FROM product_matrix WHERE is_configured=1 AND question_wiki_id IN ({placeholders})",
                wiki_ids,
            ).fetchall()
            if str(row[0] or "").strip()
        }
        return {
            "source_knowledge_count": len(wiki_ids),
            "source_matrix_edge_count": matrix_count,
            "existing_knowledge_nodes": existing_nodes,
            "existing_applies_to_edges": existing_applies,
            "missing_nodes": max(0, len(wiki_ids) - existing_nodes),
            "missing_applies_to_edges": max(0, matrix_count - existing_applies),
            "sample_wiki_ids": wiki_ids[:20],
            "schema_ready": schema_status["ready"],
            "relation_schema_migration_required": schema_status["migration_required"],
            "product_catalog_snapshot": self.catalog_snapshot or {},
            "catalog_missing_graph_models": sorted(catalog_models - graph_product_models),
            "graph_models_outside_catalog": sorted(graph_product_models - catalog_models) if self.product_catalog else [],
            "matrix_models_outside_catalog": sorted(matrix_models - catalog_models) if self.product_catalog else [],
            "write_scope": "仅 kg_nodes、kg_edges、kg_edge_events；不会写入 kb_retrieval_index 或 product_matrix。",
        }

    def apply_backfill(self, actor: str, limit: int | None = None, batch_size: int = 25) -> dict[str, Any]:
        if not 1 <= batch_size <= 1000:
            raise ValueError("batch_size 范围为 1 到 1000。")
        apply_sqlite_schema(self.connection)
        preview = self.backfill_preview(limit=limit)
        source_rows = self.connection.execute(
            """
            SELECT question_wiki_id, content_hash, question, product_category_name,
                   product_names_json, source_update_time
            FROM kb_retrieval_index
            WHERE library_type='knowledge_base_v1' AND index_status='ready'
            ORDER BY question_wiki_id
            """ + (" LIMIT ?" if limit is not None else ""),
            ([limit] if limit is not None else []),
        ).fetchall()
        created_nodes = 0
        created_edges = 0
        for source_index, source_row in enumerate(source_rows, start=1):
            source = dict(source_row)
            wiki_id = str(source["question_wiki_id"])
            existing = self._node_by_business_key("knowledge", wiki_id)
            if existing is None:
                now = utc_now()
                product_names = _json_load(source.get("product_names_json"), [])
                self.connection.execute(
                    """
                    INSERT INTO kg_nodes (
                        node_id, node_type, business_key, canonical_name, aliases_json,
                        scope_json, claims_json, properties_json, source_system,
                        source_version, content_hash, status, created_at, updated_at
                    ) VALUES (?, 'knowledge', ?, ?, '[]', ?, '{}', ?, 'kb_retrieval_index', ?, ?, 'active', ?, ?)
                    """,
                    (
                        str(uuid.uuid4()), wiki_id, str(source.get("question") or wiki_id),
                        _json_dump({"product_scope": product_names} if isinstance(product_names, list) and product_names else {"topic": str(source.get("product_category_name") or "未知")}),
                        _json_dump({"scope_review_status": "source_field", "claims_review_status": "not_extracted"}),
                        str(source.get("source_update_time") or ""), str(source.get("content_hash") or ""), now, now,
                    ),
                )
                created_nodes += 1
            knowledge_node = self._node_by_business_key("knowledge", wiki_id)
            assert knowledge_node is not None
            matrix_rows = self.connection.execute(
                """
                SELECT id, product_name, product_category, update_time
                FROM product_matrix WHERE question_wiki_id=? AND is_configured=1
                """, (wiki_id,)
            ).fetchall()
            for matrix_row in matrix_rows:
                product_name = str(matrix_row["product_name"] or "").strip()
                if not product_name:
                    continue
                product_node = self._upsert_product_node(product_name, str(matrix_row["product_category"] or ""))
                duplicate = self.connection.execute(
                    """
                    SELECT edge_id FROM kg_edges
                    WHERE from_node_id=? AND to_node_id=? AND relation_type='APPLIES_TO'
                      AND review_status='confirmed'
                    LIMIT 1
                    """, (knowledge_node["node_id"], product_node["node_id"])
                ).fetchone()
                if duplicate:
                    continue
                now = utc_now()
                edge_id = str(uuid.uuid4())
                self.connection.execute(
                    """
                    INSERT INTO kg_edges (
                        edge_id, from_node_id, to_node_id, relation_type, evidence_json,
                        scope_basis_json, confidence, review_status, generated_by, provenance_json,
                        source_version, source_content_hashes_json, review_note, reviewed_by,
                        reviewed_at, valid_from, valid_to, created_at, updated_at
                    ) VALUES (?, ?, ?, 'APPLIES_TO', ?, ?, 1, 'confirmed', 'source_field', ?, ?, ?, '', ?, ?, ?, NULL, ?, ?)
                    """,
                    (
                        edge_id, knowledge_node["node_id"], product_node["node_id"],
                        _json_dump({"matrix_row_id": matrix_row["id"], "product_name": product_name, "is_configured": True}),
                        _json_dump({"basis": "product_matrix.is_configured=true"}),
                        _json_dump({"source_system": "product_matrix", "matrix_row_id": matrix_row["id"]}),
                        str(matrix_row["update_time"] or source.get("source_update_time") or ""),
                        _json_dump({wiki_id: str(source.get("content_hash") or "")}),
                        actor, now, now, now, now,
                    ),
                )
                _record_event(edge_id=edge_id, connection=self.connection, event_type="source_field_backfilled", actor=actor, to_status="confirmed")
                created_edges += 1
            # Keep the live SQLite service responsive during large historical backfills.
            if source_index % batch_size == 0:
                self.connection.commit()
        self.connection.commit()
        return {**preview, "created_nodes": created_nodes, "created_applies_to_edges": created_edges}


def backup_sqlite_database(database_path: str | Path, backup_path: str | Path) -> Path:
    source = Path(database_path).resolve()
    target = Path(backup_path).resolve()
    if not source.is_file():
        raise ValueError(f"数据库不存在：{source}")
    if source == target:
        raise ValueError("备份文件不能覆盖当前数据库。")
    if target.exists():
        raise ValueError(f"备份文件已存在，拒绝覆盖：{target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    source_connection = sqlite3.connect(str(source))
    target_connection = sqlite3.connect(str(target))
    try:
        # SQLite backup creates a consistent snapshot while the service remains online.
        source_connection.backup(target_connection, pages=256, sleep=0.1)
    finally:
        target_connection.close()
        source_connection.close()
    return target


def invalidate_relationships_for_source_change(
    database_path: str | Path,
    product_catalog_path: str | Path | None,
    wiki_id: str,
    source_snapshot: dict[str, Any],
    actor: str,
) -> dict[str, Any]:
    """Invalidate only graph sidecar relations after a successful source knowledge update."""
    connection = connect_sqlite(database_path)
    try:
        status = graph_schema_status(connection)
        if not status["ready"]:
            raise ValueError("知识图谱修订迁移尚未完成，未执行关系失效处理。")
        store = GraphStore(connection, product_catalog_path=product_catalog_path)
        return store.refresh_stale_relationships(
            wiki_id=str(wiki_id or "").strip(),
            actor=str(actor or "system"),
            source_override=source_snapshot,
        )
    finally:
        connection.close()


def register_knowledge_graph_routes(
    app: Any,
    login_required: Any,
    database_path: str | Path,
    product_catalog_path: str | Path | None = None,
) -> None:
    """Attach authenticated graph routes without importing the Flask app globally."""
    from flask import jsonify, request
    from flask_login import current_user

    def actor() -> str:
        return str(current_user.username) if current_user.is_authenticated else "system"

    def open_store() -> tuple[sqlite3.Connection, GraphStore]:
        connection = connect_sqlite(database_path)
        return connection, GraphStore(connection, product_catalog_path=product_catalog_path)

    def error_response(exc: Exception):
        return jsonify({"success": False, "message": str(exc)}), 422

    @app.route("/api/kb/graph/summary", methods=["GET"])
    @login_required
    def knowledge_graph_summary():
        connection, store = open_store()
        try:
            return jsonify({"success": True, **store.summary()})
        finally:
            connection.close()

    @app.route("/api/kb/graph/catalog/overview", methods=["GET"])
    @login_required
    def knowledge_graph_catalog_overview():
        connection, store = open_store()
        try:
            return jsonify({"success": True, **store.catalog_overview()})
        finally:
            connection.close()

    @app.route("/api/kb/graph/catalog/attention", methods=["GET"])
    @login_required
    def knowledge_graph_catalog_attention_queue():
        try:
            page = int(request.args.get("page") or 1)
            page_size = int(request.args.get("page_size") or 100)
        except (TypeError, ValueError):
            return error_response(ValueError("page 和 page_size 必须是整数。"))
        connection, store = open_store()
        try:
            return jsonify({
                "success": True,
                **store.catalog_attention_queue(
                    category=request.args.get("category"),
                    reason=request.args.get("reason"),
                    wiki_id=request.args.get("wiki_id"),
                    page=page,
                    page_size=page_size,
                ),
            })
        except ValueError as exc:
            return error_response(exc)
        finally:
            connection.close()

    @app.route("/api/kb/graph/catalog/topic-vocabulary", methods=["GET"])
    @login_required
    def knowledge_graph_catalog_topic_vocabulary():
        connection, store = open_store()
        try:
            return jsonify({
                "success": True,
                **store.catalog_topic_vocabulary(request.args.get("category")),
            })
        finally:
            connection.close()

    @app.route("/api/kb/graph/catalog/topic-assignments", methods=["POST"])
    @login_required
    def assign_knowledge_graph_catalog_topic():
        payload = request.get_json(silent=True) or {}
        connection, store = open_store()
        try:
            return jsonify({
                "success": True,
                **store.assign_catalog_topic(
                    wiki_id=payload.get("wiki_id"),
                    topic_id=payload.get("topic_id"),
                    review_note=payload.get("review_note"),
                    confirmation_phrase=payload.get("confirmation_phrase"),
                    actor=actor(),
                ),
            })
        except ValueError as exc:
            return error_response(exc)
        finally:
            connection.close()

    @app.route("/api/kb/graph/catalog/<path:category>/topics", methods=["GET"])
    @login_required
    def knowledge_graph_catalog_topics(category: str):
        connection, store = open_store()
        try:
            return jsonify({
                "success": True,
                **store.catalog_topics(category, request.args.get("topic")),
            })
        except ValueError as exc:
            return error_response(exc)
        finally:
            connection.close()

    @app.route("/api/kb/graph/catalog/candidates/preview", methods=["POST"])
    @login_required
    def knowledge_graph_catalog_candidates_preview():
        payload = request.get_json(silent=True) or {}
        topics = payload.get("topics")
        if not isinstance(topics, list):
            return error_response(ValueError("topics 必须是主题数组。"))
        try:
            max_pairs_per_topic = int(payload.get("max_pairs_per_topic") or 20)
        except (TypeError, ValueError):
            return error_response(ValueError("每个主题最多预览 20 个知识对。"))
        connection, store = open_store()
        try:
            return jsonify({
                "success": True,
                "dry_run": True,
                **store.catalog_candidate_preview(
                    category=payload.get("category"),
                    topics=topics,
                    max_pairs_per_topic=max_pairs_per_topic,
                ),
            })
        except ValueError as exc:
            return error_response(exc)
        finally:
            connection.close()

    @app.route("/api/kb/graph/catalog/candidate-batches", methods=["POST"])
    @login_required
    def create_knowledge_graph_catalog_candidate_batch():
        payload = request.get_json(silent=True) or {}
        topics = payload.get("topics")
        if not isinstance(topics, list):
            return error_response(ValueError("topics 必须是主题数组。"))
        try:
            max_pairs_per_topic = int(payload.get("max_pairs_per_topic") or 20)
        except (TypeError, ValueError):
            return error_response(ValueError("每个主题最多写入 20 个知识对。"))
        connection, store = open_store()
        try:
            return jsonify({
                "success": True,
                **store.create_catalog_candidate_batch(
                    category=payload.get("category"),
                    topics=topics,
                    max_pairs_per_topic=max_pairs_per_topic,
                    confirmation_phrase=payload.get("confirmation_phrase"),
                    actor=actor(),
                ),
            })
        except ValueError as exc:
            return error_response(exc)
        finally:
            connection.close()

    @app.route("/api/kb/graph/catalog/candidate-batches", methods=["GET"])
    @login_required
    def list_knowledge_graph_catalog_candidate_batches():
        connection, store = open_store()
        try:
            return jsonify({"success": True, **store.list_candidate_batches()})
        finally:
            connection.close()

    @app.route("/api/kb/graph/catalog/candidate-batches/<batch_id>", methods=["GET"])
    @login_required
    def knowledge_graph_catalog_candidate_batch_detail(batch_id: str):
        connection, store = open_store()
        try:
            return jsonify({"success": True, **store.candidate_batch_detail(batch_id)})
        except ValueError as exc:
            return error_response(exc)
        finally:
            connection.close()

    @app.route("/api/kb/graph/catalog/candidate-batches/<batch_id>/rollback", methods=["POST"])
    @login_required
    def rollback_knowledge_graph_catalog_candidate_batch(batch_id: str):
        payload = request.get_json(silent=True) or {}
        connection, store = open_store()
        try:
            return jsonify({
                "success": True,
                **store.rollback_catalog_candidate_batch(
                    batch_id=batch_id,
                    confirmation_phrase=payload.get("confirmation_phrase"),
                    note=payload.get("note"),
                    actor=actor(),
                ),
            })
        except ValueError as exc:
            return error_response(exc)
        finally:
            connection.close()

    @app.route("/api/kb/graph/knowledge/<wiki_id>", methods=["GET"])
    @login_required
    def knowledge_graph_knowledge(wiki_id: str):
        connection, store = open_store()
        try:
            return jsonify({"success": True, **store.knowledge_detail(str(wiki_id).strip())})
        except ValueError as exc:
            return error_response(exc)
        finally:
            connection.close()

    @app.route("/api/kb/graph/edges", methods=["GET"])
    @login_required
    def knowledge_graph_edges():
        try:
            page = max(1, int(request.args.get("page") or 1))
            page_size = min(100, max(1, int(request.args.get("page_size") or 50)))
        except ValueError:
            return jsonify({"success": False, "message": "页码必须是整数。"}), 422
        connection, store = open_store()
        try:
            result = store.list_edges(
                wiki_id=str(request.args.get("wiki_id") or "").strip() or None,
                review_status=str(request.args.get("review_status") or "").strip() or None,
                relation_type=str(request.args.get("relation_type") or "").strip() or None,
                effective_only=str(request.args.get("effective_only") or "").strip().lower() in {"1", "true", "yes"},
                page=page,
                page_size=page_size,
            )
            return jsonify({"success": True, **result})
        except ValueError as exc:
            return error_response(exc)
        finally:
            connection.close()

    @app.route("/api/kb/graph/candidates", methods=["POST"])
    @login_required
    def create_knowledge_graph_candidate():
        payload = request.get_json(silent=True) or {}
        connection, store = open_store()
        try:
            result = store.create_candidates(
                from_wiki_id=payload.get("from_wiki_id"),
                to_wiki_id=payload.get("to_wiki_id"),
                from_scope=payload.get("from_scope"),
                from_claims=payload.get("from_claims"),
                to_scope=payload.get("to_scope"),
                to_claims=payload.get("to_claims"),
                actor=actor(),
                generated_by=str(payload.get("generated_by") or "rule").strip(),
                confidence=payload.get("confidence"),
                evidence=payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {},
            )
            return jsonify({"success": True, **result})
        except ValueError as exc:
            return error_response(exc)
        finally:
            connection.close()

    @app.route("/api/kb/graph/edges/<edge_id>/review", methods=["POST"])
    @login_required
    def review_knowledge_graph_edge(edge_id: str):
        payload = request.get_json(silent=True) or {}
        connection, store = open_store()
        try:
            edge = store.review_edge(edge_id, payload.get("decision"), payload.get("review_note"), actor())
            return jsonify({"success": True, "edge": edge})
        except ValueError as exc:
            return error_response(exc)
        finally:
            connection.close()

    @app.route("/api/kb/graph/edges/<edge_id>/revise", methods=["POST"])
    @login_required
    def revise_knowledge_graph_edge(edge_id: str):
        payload = request.get_json(silent=True) or {}
        connection, store = open_store()
        try:
            result = store.revise_edge(
                edge_id=edge_id,
                relation_type=payload.get("relation_type"),
                from_scope=payload.get("from_scope"),
                from_claims=payload.get("from_claims"),
                to_scope=payload.get("to_scope"),
                to_claims=payload.get("to_claims"),
                note=payload.get("review_note"),
                actor=actor(),
                swap_direction=bool(payload.get("swap_direction")),
            )
            return jsonify({"success": True, **result})
        except ValueError as exc:
            return error_response(exc)
        finally:
            connection.close()

    @app.route("/api/kb/graph/candidates/expire-stale", methods=["POST"])
    @login_required
    def expire_stale_knowledge_graph_candidates():
        payload = request.get_json(silent=True) or {}
        connection, store = open_store()
        try:
            wiki_id = str(payload.get("wiki_id") or "").strip() or None
            return jsonify({"success": True, **store.refresh_stale_relationships(wiki_id, actor())})
        except ValueError as exc:
            return error_response(exc)
        finally:
            connection.close()

    @app.route("/api/kb/graph/backfill/preview", methods=["POST"])
    @login_required
    def knowledge_graph_backfill_preview():
        payload = request.get_json(silent=True) or {}
        try:
            limit = payload.get("limit")
            limit = int(limit) if limit not in (None, "") else None
            if limit is not None and not 1 <= limit <= 10000:
                raise ValueError("limit 范围为 1 到 10000。")
        except (TypeError, ValueError) as exc:
            return error_response(ValueError("limit 范围为 1 到 10000。"))
        connection, store = open_store()
        try:
            return jsonify({"success": True, "dry_run": True, **store.backfill_preview(limit)})
        finally:
            connection.close()
