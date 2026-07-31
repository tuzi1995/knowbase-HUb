#!/usr/bin/env python3
"""Preview or explicitly backfill the phase-one graph sidecar from local sources."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DEFAULT_PRODUCT_CATALOG = ROOT.parent / "⚙️ 配置文件" / "product_catalog.json"

from knowledge_graph import GraphStore, backup_sqlite_database, connect_sqlite  # noqa: E402


CONFIRMATION = "APPLY_KG_SIDECAR_BACKFILL"


def main() -> int:
    parser = argparse.ArgumentParser(description="8085 知识图谱一期旁路回填工具")
    parser.add_argument("--database", default=str(ROOT / "instance" / "data.db"), help="SQLite 数据库路径")
    parser.add_argument("--product-catalog", default=str(DEFAULT_PRODUCT_CATALOG), help="8085 型号库 JSON 路径")
    parser.add_argument("--limit", type=int, help="仅预览或回填前 N 条有效知识，范围 1 到 10000")
    parser.add_argument("--batch-size", type=int, default=25, help="每批提交的知识数，范围 1 到 1000，默认 25")
    parser.add_argument("--apply", action="store_true", help="写入 kg_* 旁路表；默认仅输出 dry-run 差异")
    parser.add_argument("--backup", help="执行回填前保存的数据库备份路径")
    parser.add_argument("--confirm", help=f"执行回填所需确认词：{CONFIRMATION}")
    args = parser.parse_args()
    if args.limit is not None and not 1 <= args.limit <= 10000:
        parser.error("--limit 范围为 1 到 10000")
    if not 1 <= args.batch_size <= 1000:
        parser.error("--batch-size 范围为 1 到 1000")

    if args.apply and (not args.backup or args.confirm != CONFIRMATION):
        parser.error(f"执行回填必须同时提供 --backup 和 --confirm {CONFIRMATION}")

    connection = connect_sqlite(args.database)
    try:
        store = GraphStore(connection, product_catalog_path=args.product_catalog)
        preview = store.backfill_preview(limit=args.limit)
    finally:
        connection.close()

    if not args.apply:
        print(json.dumps({"success": True, "dry_run": True, **preview}, ensure_ascii=False, indent=2))
        return 0

    backup_path = backup_sqlite_database(args.database, args.backup)
    connection = connect_sqlite(args.database)
    try:
        store = GraphStore(connection, product_catalog_path=args.product_catalog)
        result = store.apply_backfill(actor="knowledge_graph_backfill", limit=args.limit, batch_size=args.batch_size)
    finally:
        connection.close()
    print(json.dumps({"success": True, "dry_run": False, "backup": str(backup_path), **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
