#!/usr/bin/env python3
"""
Apply required PostgreSQL fixes for K-Matrix cloud deployment.

Run from the deployed project directory:
    python3 DevTools/apply_required_sql_fixes.py
or:
    venv/bin/python DevTools/apply_required_sql_fixes.py
"""

import json
import sys
from pathlib import Path

try:
    import psycopg2
except Exception as exc:
    print("缺少 psycopg2-binary。请先执行: pip3 install psycopg2-binary")
    print(f"导入失败: {exc}")
    sys.exit(1)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = PROJECT_ROOT / "supabase_config_local.json"

SQL_STEPS = [
    (
        "1/3 修复增量导入 ON CONFLICT 约束",
        r"""
DO $$
DECLARE
    v_table text;
    v_null_count integer;
    v_dup_count integer;
    v_has_constraint boolean;
BEGIN
    FOREACH v_table IN ARRAY ARRAY['knowledge_base_v1', 'knowledge_base_v1_t1']
    LOOP
        EXECUTE format(
            'SELECT COUNT(*) FROM public.%I WHERE question_wiki_id IS NULL OR btrim(question_wiki_id) = ''''',
            v_table
        )
        INTO v_null_count;

        IF v_null_count > 0 THEN
            RAISE EXCEPTION '% has % rows with empty question_wiki_id. Fix those rows before adding a unique constraint.',
                v_table, v_null_count;
        END IF;

        EXECUTE format(
            'SELECT COUNT(*) FROM (
                SELECT question_wiki_id
                FROM public.%I
                GROUP BY question_wiki_id
                HAVING COUNT(*) > 1
            ) d',
            v_table
        )
        INTO v_dup_count;

        IF v_dup_count > 0 THEN
            RAISE EXCEPTION '% has % duplicate question_wiki_id values. Deduplicate before adding a unique constraint.',
                v_table, v_dup_count;
        END IF;

        SELECT EXISTS (
            SELECT 1
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = 'public'
              AND t.relname = v_table
              AND c.contype IN ('p', 'u')
              AND c.conkey = ARRAY[
                  (
                      SELECT a.attnum
                      FROM pg_attribute a
                      WHERE a.attrelid = t.oid
                        AND a.attname = 'question_wiki_id'
                        AND NOT a.attisdropped
                  )
              ]::smallint[]
        )
        INTO v_has_constraint;

        IF NOT v_has_constraint THEN
            EXECUTE format(
                'ALTER TABLE public.%I ADD CONSTRAINT %I UNIQUE (question_wiki_id)',
                v_table,
                v_table || '_question_wiki_id_unique'
            );
            RAISE NOTICE 'Added unique constraint on %.question_wiki_id', v_table;
        ELSE
            RAISE NOTICE '%.question_wiki_id already has a primary/unique constraint', v_table;
        END IF;

        EXECUTE format('ALTER TABLE public.%I ALTER COLUMN question_wiki_id SET NOT NULL', v_table);
    END LOOP;
END $$;

NOTIFY pgrst, 'reload schema';
""",
    ),
    (
        "2/3 修复评分页产品/型号回填",
        r"""
ALTER TABLE IF EXISTS public.kb_scores
    ADD COLUMN IF NOT EXISTS product_name TEXT;

UPDATE public.kb_scores s
SET product_name = COALESCE(k.product_name, '')
FROM public.knowledge_base_v1 k
WHERE s.kb_id = k.question_wiki_id
  AND COALESCE(s.product_name, '') <> COALESCE(k.product_name, '');

CREATE INDEX IF NOT EXISTS idx_kb_scores_product_name
    ON public.kb_scores(product_name);

NOTIFY pgrst, 'reload schema';
""",
    ),
    (
        "3/3 添加云端列表加载索引",
        r"""
DO $$
BEGIN
    IF to_regclass('public.kb_scores') IS NOT NULL THEN
        CREATE INDEX IF NOT EXISTS idx_kb_scores_kb_id ON public.kb_scores(kb_id);
        CREATE INDEX IF NOT EXISTS idx_kb_scores_status ON public.kb_scores(status);
        CREATE INDEX IF NOT EXISTS idx_kb_scores_updated_at ON public.kb_scores(updated_at);
        CREATE INDEX IF NOT EXISTS idx_kb_scores_total_score ON public.kb_scores(total_score);
        CREATE INDEX IF NOT EXISTS idx_kb_scores_product_name ON public.kb_scores(product_name);
        ANALYZE public.kb_scores;
    END IF;

    IF to_regclass('public.link_previews') IS NOT NULL THEN
        CREATE INDEX IF NOT EXISTS idx_link_previews_created_at ON public.link_previews(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_link_previews_kb_id ON public.link_previews(kb_id);
        CREATE INDEX IF NOT EXISTS idx_link_previews_type ON public.link_previews(type);
        ANALYZE public.link_previews;
    END IF;

    IF to_regclass('public.kb_recall') IS NOT NULL THEN
        CREATE INDEX IF NOT EXISTS idx_kb_recall_month ON public.kb_recall(month);
        CREATE INDEX IF NOT EXISTS idx_kb_recall_kb_id ON public.kb_recall(kb_id);
        CREATE INDEX IF NOT EXISTS idx_kb_recall_month_kb_id ON public.kb_recall(month, kb_id);
        ANALYZE public.kb_recall;
    END IF;

    IF to_regclass('public.product_matrix') IS NOT NULL THEN
        CREATE INDEX IF NOT EXISTS idx_product_matrix_question_wiki_id ON public.product_matrix(question_wiki_id);
        CREATE INDEX IF NOT EXISTS idx_product_matrix_product_name ON public.product_matrix(product_name);
        CREATE INDEX IF NOT EXISTS idx_product_matrix_question_product ON public.product_matrix(question_wiki_id, product_name);
        CREATE INDEX IF NOT EXISTS idx_product_matrix_product_question ON public.product_matrix(product_name, question_wiki_id);
        CREATE INDEX IF NOT EXISTS idx_product_matrix_product_category ON public.product_matrix(product_category);
        CREATE INDEX IF NOT EXISTS idx_product_matrix_is_configured ON public.product_matrix(is_configured);
        CREATE INDEX IF NOT EXISTS idx_product_matrix_manual_edit ON public.product_matrix(manual_edit);
        CREATE INDEX IF NOT EXISTS idx_product_matrix_edit_source ON public.product_matrix(edit_source);
        ANALYZE public.product_matrix;
    END IF;

    IF to_regclass('public.matrix_column') IS NOT NULL THEN
        CREATE INDEX IF NOT EXISTS idx_matrix_column_product_name ON public.matrix_column(product_name);
        CREATE INDEX IF NOT EXISTS idx_matrix_column_sort_order ON public.matrix_column(sort_order);
        ANALYZE public.matrix_column;
    END IF;

    IF to_regclass('public.kb_item_tags') IS NOT NULL THEN
        CREATE INDEX IF NOT EXISTS idx_kb_item_tags_library_wiki ON public.kb_item_tags(library_type, question_wiki_id);
        CREATE INDEX IF NOT EXISTS idx_kb_item_tags_library_tag ON public.kb_item_tags(library_type, tag_id);
        CREATE INDEX IF NOT EXISTS idx_kb_item_tags_question_wiki_id ON public.kb_item_tags(question_wiki_id);
        CREATE INDEX IF NOT EXISTS idx_kb_item_tags_tag_id ON public.kb_item_tags(tag_id);
        ANALYZE public.kb_item_tags;
    END IF;

    IF to_regclass('public.kb_tags') IS NOT NULL THEN
        CREATE INDEX IF NOT EXISTS idx_kb_tags_name ON public.kb_tags(name);
        ANALYZE public.kb_tags;
    END IF;
END $$;

NOTIFY pgrst, 'reload schema';
""",
    ),
]


def load_config():
    if not CONFIG_FILE.exists():
        raise RuntimeError(f"找不到配置文件: {CONFIG_FILE}")
    with CONFIG_FILE.open("r", encoding="utf-8") as f:
        cfg = json.load(f) or {}
    db_cfg = cfg.get("local_db") if isinstance(cfg.get("local_db"), dict) else cfg
    if not db_cfg.get("database") or not db_cfg.get("user"):
        raise RuntimeError("配置文件里缺少 local_db.database 或 local_db.user")
    return db_cfg


def connect(db_cfg):
    return psycopg2.connect(
        host=db_cfg.get("host", "localhost"),
        port=int(db_cfg.get("port", 5432)),
        dbname=db_cfg.get("database"),
        user=db_cfg.get("user"),
        password=db_cfg.get("password") or None,
    )


def main():
    print("=" * 60)
    print("K-Matrix 云端 SQL 修复")
    print("=" * 60)
    db_cfg = load_config()
    print(
        "数据库: "
        f"{db_cfg.get('host', 'localhost')}:{db_cfg.get('port', 5432)}/"
        f"{db_cfg.get('database')} user={db_cfg.get('user')}"
    )

    conn = connect(db_cfg)
    try:
        for title, sql in SQL_STEPS:
            print("")
            print(title)
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
            for notice in conn.notices:
                print(notice.strip())
            conn.notices.clear()
            print("完成")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print("")
    print("=" * 60)
    print("全部完成。接下来请重启应用服务，并刷新浏览器。")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("")
        print("执行失败。请把下面错误发给维护人员：")
        print(exc)
        sys.exit(1)
