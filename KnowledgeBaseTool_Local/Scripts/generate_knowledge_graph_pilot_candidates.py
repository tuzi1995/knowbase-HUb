#!/usr/bin/env python3
"""Preview or explicitly create governed pilot knowledge-to-knowledge candidates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DEFAULT_PRODUCT_CATALOG = ROOT.parent / "⚙️ 配置文件" / "product_catalog.json"
DEFAULT_MANIFEST = ROOT / "knowledge_graph_pilot_candidates.json"

from knowledge_graph import GraphStore, backup_sqlite_database, connect_sqlite  # noqa: E402


CONFIRMATION = "APPLY_KG_PILOT_CANDIDATES"


def load_manifest(path: str | Path) -> list[dict]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"试点清单无法读取：{path}") from exc
    if not isinstance(payload, list) or not payload:
        raise ValueError("试点清单必须是非空 JSON 数组。")
    return payload


def preview_manifest(store: GraphStore, manifest: list[dict]) -> dict:
    items = []
    relation_counts: dict[str, int] = {}
    new_relation_count = 0
    for entry in manifest:
        result = store.preview_candidates(
            entry.get("from_wiki_id"),
            entry.get("to_wiki_id"),
            entry.get("from_scope"),
            entry.get("from_claims"),
            entry.get("to_scope"),
            entry.get("to_claims"),
        )
        relations = result["relations"]
        if not relations:
            raise ValueError(
                f"{entry.get('from_wiki_id')} -> {entry.get('to_wiki_id')} 没有足够证据生成候选。"
            )
        for relation in relations:
            relation_type = relation["relation_type"]
            relation_counts[relation_type] = relation_counts.get(relation_type, 0) + 1
            if not relation["existing"]:
                new_relation_count += 1
        items.append(
            {
                "pilot": str(entry.get("pilot") or ""),
                "from_wiki_id": result["from_wiki_id"],
                "to_wiki_id": result["to_wiki_id"],
                "relations": [
                    {
                        "relation_type": relation["relation_type"],
                        "confidence": relation["confidence"],
                        "reason": relation["reason"],
                        "existing": relation["existing"],
                    }
                    for relation in relations
                ],
            }
        )
    return {
        "pair_count": len(items),
        "relation_counts": relation_counts,
        "new_relation_count": new_relation_count,
        "items": items,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="8085 知识图谱首批试点候选工具")
    parser.add_argument("--database", default=str(ROOT / "instance" / "data.db"), help="SQLite 数据库路径")
    parser.add_argument("--product-catalog", default=str(DEFAULT_PRODUCT_CATALOG), help="8085 型号库 JSON 路径")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="结构化试点清单")
    parser.add_argument("--apply", action="store_true", help="写入 candidate 边；默认只输出 dry-run")
    parser.add_argument("--backup", help="执行前保存的 SQLite 备份路径")
    parser.add_argument("--confirm", help=f"执行所需确认词：{CONFIRMATION}")
    args = parser.parse_args()
    if args.apply and (not args.backup or args.confirm != CONFIRMATION):
        parser.error(f"正式生成必须同时提供 --backup 和 --confirm {CONFIRMATION}")

    manifest = load_manifest(args.manifest)
    connection = connect_sqlite(args.database)
    try:
        store = GraphStore(connection, product_catalog_path=args.product_catalog)
        preview = preview_manifest(store, manifest)
    finally:
        connection.close()
    if not args.apply:
        print(json.dumps({"success": True, "dry_run": True, **preview}, ensure_ascii=False, indent=2))
        return 0

    backup_path = backup_sqlite_database(args.database, args.backup)
    connection = connect_sqlite(args.database)
    try:
        store = GraphStore(connection, product_catalog_path=args.product_catalog)
        results = []
        for entry in manifest:
            result = store.create_candidates(
                from_wiki_id=entry.get("from_wiki_id"),
                to_wiki_id=entry.get("to_wiki_id"),
                from_scope=entry.get("from_scope"),
                from_claims=entry.get("from_claims"),
                to_scope=entry.get("to_scope"),
                to_claims=entry.get("to_claims"),
                actor="knowledge_graph_pilot_20260727",
                generated_by="rule",
                evidence={"pilot": entry.get("pilot"), "note": entry.get("evidence")},
            )
            results.append(
                {
                    "pilot": entry.get("pilot"),
                    "created_count": result["created_count"],
                    "edges": [
                        {
                            "edge_id": edge["edge_id"],
                            "relation_type": edge["relation_type"],
                            "review_status": edge["review_status"],
                            "created": edge["created"],
                        }
                        for edge in result["edges"]
                    ],
                }
            )
    finally:
        connection.close()
    print(
        json.dumps(
            {
                "success": True,
                "dry_run": False,
                "backup": str(backup_path),
                "preview": preview,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
