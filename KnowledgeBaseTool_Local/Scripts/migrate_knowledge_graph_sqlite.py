#!/usr/bin/env python3
"""Safely inspect, apply, or roll back the local knowledge-graph sidecar schema."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from knowledge_graph import (  # noqa: E402
    backup_sqlite_database,
    connect_sqlite,
    graph_schema_status,
    migrate_sqlite_relation_schema,
    rollback_sqlite_relation_schema,
    rollback_sqlite_revision_schema,
    rollback_sqlite_schema,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="8085 知识图谱一期 SQLite 迁移工具")
    parser.add_argument("--database", default=str(ROOT / "instance" / "data.db"), help="SQLite 数据库路径")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--apply", action="store_true", help="创建旁路表或保留数据升级关系类型约束")
    actions.add_argument("--rollback-relations", action="store_true", help="回退新关系类型约束，保留所有旧边和事件")
    actions.add_argument("--rollback-revisions", action="store_true", help="无修订历史时回退关系版本字段")
    actions.add_argument("--rollback", action="store_true", help="删除全部 kg_* 旁路表")
    parser.add_argument("--backup", help="执行 apply/rollback 前写入的数据库备份路径")
    args = parser.parse_args()

    if not args.apply and not args.rollback and not args.rollback_relations and not args.rollback_revisions:
        connection = connect_sqlite(args.database)
        try:
            print(json.dumps({"dry_run": True, **graph_schema_status(connection)}, ensure_ascii=False, indent=2))
        finally:
            connection.close()
        return 0
    if not args.backup:
        parser.error("执行迁移或回退必须提供 --backup，避免覆盖现有旁路审计数据")

    backup_path = backup_sqlite_database(args.database, args.backup)
    connection = connect_sqlite(args.database)
    try:
        if args.apply:
            result = migrate_sqlite_relation_schema(connection)
            action = "relation_schema_applied"
        elif args.rollback_revisions:
            result = rollback_sqlite_revision_schema(connection)
            action = "revision_schema_rolled_back"
        elif args.rollback_relations:
            result = rollback_sqlite_relation_schema(connection)
            action = "relation_schema_rolled_back"
        else:
            rollback_sqlite_schema(connection)
            action = "rolled_back"
            result = graph_schema_status(connection)
        print(json.dumps({"success": True, "action": action, "backup": str(backup_path), **result}, ensure_ascii=False, indent=2))
    except ValueError as exc:
        print(json.dumps({"success": False, "backup": str(backup_path), "message": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
