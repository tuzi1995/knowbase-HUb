#!/usr/bin/env python3
"""Permanently retire the unused V1T-1 knowledge-base table."""

import argparse
import json
from pathlib import Path

import psycopg2


def load_database_config(path):
    config = json.loads(Path(path).read_text(encoding='utf-8'))
    database = config.get('local_db') if isinstance(config.get('local_db'), dict) else config
    required = ('host', 'port', 'database', 'user')
    missing = [key for key in required if not database.get(key)]
    if missing:
        raise RuntimeError(f"database config missing: {', '.join(missing)}")
    return database


def retire(config_path):
    database = load_database_config(config_path)
    connection = psycopg2.connect(
        host=database['host'],
        port=database['port'],
        database=database['database'],
        user=database['user'],
        password=database.get('password', ''),
        connect_timeout=10,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('public.knowledge_base_v1_t1')")
            table_existed = cursor.fetchone()[0] is not None
            retired_rows = 0
            if table_existed:
                cursor.execute('SELECT COUNT(*) FROM public.knowledge_base_v1_t1')
                retired_rows = int(cursor.fetchone()[0])

            cursor.execute("SELECT to_regclass('public.kb_item_tags')")
            tag_table_exists = cursor.fetchone()[0] is not None
            deleted_tag_mappings = 0
            if tag_table_exists:
                cursor.execute("DELETE FROM public.kb_item_tags WHERE library_type IS DISTINCT FROM 'current'")
                deleted_tag_mappings = int(cursor.rowcount or 0)
                cursor.execute(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_constraint
                            WHERE conname = 'kb_item_tags_current_only'
                              AND conrelid = 'public.kb_item_tags'::regclass
                        ) THEN
                            ALTER TABLE public.kb_item_tags
                            ADD CONSTRAINT kb_item_tags_current_only
                            CHECK (library_type = 'current' AND library_type IS NOT NULL);
                        END IF;
                    END $$
                    """
                )

            cursor.execute('DROP FUNCTION IF EXISTS public.sync_v1_to_v1_t1()')
            cursor.execute('DROP FUNCTION IF EXISTS public.sync_knowledge_base()')
            cursor.execute('DROP TABLE IF EXISTS public.knowledge_base_v1_t1 CASCADE')
        connection.commit()
        return {
            'ok': True,
            'table_existed': table_existed,
            'retired_rows': retired_rows,
            'deleted_previous_tag_mappings': deleted_tag_mappings,
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description='Retire knowledge_base_v1_t1 and previous-library metadata')
    parser.add_argument('--config', default='supabase_config_local.json')
    args = parser.parse_args()
    print(json.dumps(retire(Path(args.config).resolve()), ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
