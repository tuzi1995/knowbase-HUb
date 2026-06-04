#!/usr/bin/env python3
"""
Apply required SQL fixes for the deployed K-Matrix PostgreSQL database.

This script reads the existing supabase_config_local.json local_db config and
executes the required SQL files in the safe order.
"""

import json
import sys
from pathlib import Path

try:
    import psycopg2
except Exception as exc:
    print("缺少 psycopg2-binary，请先安装依赖: pip3 install psycopg2-binary")
    print(f"导入失败: {exc}")
    sys.exit(1)


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent

CONFIG_CANDIDATES = [
    PROJECT_ROOT / "KnowledgeBaseTool_Local" / "supabase_config_local.json",
    PROJECT_ROOT / "⚙️ 配置文件" / "supabase_config_local.json",
]

SQL_FILES = [
    PROJECT_ROOT / "🗄️ 数据库" / "修复脚本" / "fix_kb_v1_question_wiki_unique.sql",
    PROJECT_ROOT / "🗄️ 数据库" / "修复脚本" / "fix_kb_scores_product_name.sql",
    PROJECT_ROOT / "🗄️ 数据库" / "索引优化" / "cloud_module_load_indexes.sql",
]


def load_db_config():
    for path in CONFIG_CANDIDATES:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as f:
            cfg = json.load(f) or {}
        db_cfg = cfg.get("local_db") if isinstance(cfg.get("local_db"), dict) else cfg
        if db_cfg.get("database") and db_cfg.get("user"):
            print(f"已读取数据库配置: {path}")
            return db_cfg
    raise RuntimeError("未找到可用的 supabase_config_local.json 数据库配置")


def connect(db_cfg):
    return psycopg2.connect(
        host=db_cfg.get("host", "localhost"),
        port=int(db_cfg.get("port", 5432)),
        dbname=db_cfg.get("database"),
        user=db_cfg.get("user"),
        password=db_cfg.get("password") or None,
    )


def execute_sql_file(conn, path):
    if not path.exists():
        raise RuntimeError(f"SQL 文件不存在: {path}")
    print("")
    print(f"开始执行: {path.name}")
    sql = path.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    for notice in conn.notices:
        print(notice.strip())
    conn.notices.clear()
    print(f"执行成功: {path.name}")


def main():
    print("=" * 60)
    print("K-Matrix 必需 SQL 修复脚本")
    print("=" * 60)
    db_cfg = load_db_config()
    print(
        "连接数据库: "
        f"{db_cfg.get('host', 'localhost')}:{db_cfg.get('port', 5432)}/"
        f"{db_cfg.get('database')} user={db_cfg.get('user')}"
    )

    conn = connect(db_cfg)
    try:
        for path in SQL_FILES:
            execute_sql_file(conn, path)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print("")
    print("=" * 60)
    print("全部 SQL 已执行完成。请重启应用服务，然后刷新浏览器。")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("")
        print("执行失败，请把下面这段错误发给维护人员：")
        print(exc)
        sys.exit(1)
