"""Back up and fill only blank categories in local PostgreSQL and SQLite."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime

import psycopg2
from psycopg2.extras import execute_batch

APP = Path(__file__).resolve().parents[1]
ROOT = APP.parent
sys.path.insert(0, str(APP))
from product_categories import ProductCategoryResolver, category_is_blank


def plan(kb_rows, matrix_rows, resolver):
    kb_updates = []
    categories = {}
    for wiki_id, products, existing in kb_rows:
        category = resolver.resolve(products, existing)
        categories[wiki_id] = category
        if category_is_blank(existing) and category:
            kb_updates.append((category, wiki_id))
    matrix_updates = []
    for row_id, wiki_id, products, existing in matrix_rows:
        if not category_is_blank(existing):
            continue
        category = categories.get(wiki_id) or resolver.resolve(products)
        if category:
            matrix_updates.append((category, row_id))
    return kb_updates, matrix_updates


def pg_rows(cur):
    cur.execute('SELECT question_wiki_id,product_name,product_category_name FROM public.knowledge_base_v1')
    kb = cur.fetchall()
    cur.execute('SELECT id,question_wiki_id,product_name,product_category FROM public.product_matrix')
    return kb, cur.fetchall()


def pg_fingerprint(cur, table, category, version=False):
    excluded = f" - '{category}'" + (" - 'content_version'" if version else '')
    cur.execute(f'SELECT md5((to_jsonb(t){excluded})::text) FROM public.{table} t ORDER BY ' + ('question_wiki_id' if version else 'id'))
    return hashlib.sha256(''.join(r[0] for r in cur.fetchall()).encode()).hexdigest()


def sqlite_fingerprint(conn):
    columns = [row[1] for row in conn.execute('PRAGMA table_info(product_matrix)') if row[1] != 'product_category']
    query = 'SELECT ' + ','.join('"' + c + '"' for c in columns) + ' FROM product_matrix ORDER BY id'
    digest = hashlib.sha256()
    for row in conn.execute(query):
        digest.update(json.dumps(row, ensure_ascii=False, default=str).encode())
        digest.update(b'\n')
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    config_dir = ROOT / '⚙️ 配置文件'
    cfg = json.loads((config_dir / 'supabase_config_local.json').read_text())['local_db']
    if cfg['host'] not in ('localhost', '127.0.0.1', '::1'):
        raise RuntimeError('Only the configured local database is supported')
    resolver = ProductCategoryResolver(json.loads((config_dir / 'product_catalog.json').read_text()))
    sqlite_path = APP / 'instance' / 'data.db'
    pg = psycopg2.connect(host=cfg['host'], port=cfg['port'], dbname=cfg['database'], user=cfg['user'], password=cfg['password'])
    local = sqlite3.connect(f'file:{sqlite_path}?mode=rw', uri=True, timeout=30)
    try:
        with pg.cursor() as cur:
            kb, matrix = pg_rows(cur)
            local_rows = local.execute('SELECT id,question_wiki_id,product_name,product_category FROM product_matrix').fetchall()
            kb_updates, pg_updates = plan(kb, matrix, resolver)
            _, local_updates = plan(kb, local_rows, resolver)
        pg.rollback()
        report = {'database': cfg['database'], 'kb': len(kb_updates), 'pg_matrix': len(pg_updates), 'sqlite_matrix': len(local_updates)}
        print(json.dumps(report, ensure_ascii=False))
        if not args.apply:
            return

        backup = ROOT / 'deliverables' / ('category_backfill_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
        backup.mkdir(parents=True, exist_ok=False)
        os.chmod(backup, 0o700)
        dump = shutil.which('pg_dump') or '/opt/homebrew/opt/postgresql@18/bin/pg_dump'
        subprocess.run([dump, '-h', str(cfg['host']), '-p', str(cfg['port']), '-U', cfg['user'], '-d', cfg['database'], '-Fc', '-f', str(backup / 'postgres.dump')],
                       env=dict(os.environ, PGPASSWORD=cfg['password']), check=True)
        with sqlite3.connect(backup / 'data.db') as dest:
            local.backup(dest)
        shutil.copy2(config_dir / 'product_catalog.json', backup / 'product_catalog.json')
        print('Backup: ' + str(backup), flush=True)

        # Hold both write boundaries while planning and verifying the narrow update.
        local.execute('BEGIN IMMEDIATE')
        with pg.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout = '15s'")
            cur.execute('LOCK TABLE public.knowledge_base_v1, public.product_matrix IN SHARE ROW EXCLUSIVE MODE')
            kb, matrix = pg_rows(cur)
            local_rows = local.execute('SELECT id,question_wiki_id,product_name,product_category FROM product_matrix').fetchall()
            kb_updates, pg_updates = plan(kb, matrix, resolver)
            _, local_updates = plan(kb, local_rows, resolver)
            before = (pg_fingerprint(cur, 'knowledge_base_v1', 'product_category_name', True),
                      pg_fingerprint(cur, 'product_matrix', 'product_category'), sqlite_fingerprint(local))
            execute_batch(cur, 'UPDATE public.knowledge_base_v1 SET product_category_name=%s,content_version=COALESCE(content_version,1)+1 WHERE question_wiki_id=%s', kb_updates)
            execute_batch(cur, 'UPDATE public.product_matrix SET product_category=%s WHERE id=%s', pg_updates)
            local.executemany('UPDATE product_matrix SET product_category=? WHERE id=?', local_updates)
            after = (pg_fingerprint(cur, 'knowledge_base_v1', 'product_category_name', True),
                     pg_fingerprint(cur, 'product_matrix', 'product_category'), sqlite_fingerprint(local))
            if before != after:
                raise RuntimeError('Non-category fields changed; rolling back')
            new_kb, new_matrix = pg_rows(cur)
            new_local = local.execute('SELECT id,question_wiki_id,product_name,product_category FROM product_matrix').fetchall()
            if any(plan(new_kb, new_matrix, resolver)) or any(plan(new_kb, new_local, resolver)):
                raise RuntimeError('Resolvable blank categories remain; rolling back')
            # Existing classifications are also invariant, not just other fields.
            for old_rows, new_rows in ((kb, new_kb), (matrix, new_matrix), (local_rows, new_local)):
                new_map = {row[0]: row[-1] for row in new_rows}
                if any(new_map[row[0]] != row[-1] for row in old_rows if not category_is_blank(row[-1])):
                    raise RuntimeError('Existing category changed; rolling back')
        pg.commit()
        local.commit()
        report.update(kb=len(kb_updates), pg_matrix=len(pg_updates), sqlite_matrix=len(local_updates), backup=str(backup), verified=True,
                      remaining_blank={'kb': sum(category_is_blank(r[-1]) for r in new_kb),
                                       'pg_matrix': sum(category_is_blank(r[-1]) for r in new_matrix),
                                       'sqlite_matrix': sum(category_is_blank(r[-1]) for r in new_local)})
        (backup / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps(report, ensure_ascii=False))
    except Exception:
        pg.rollback()
        local.rollback()
        raise
    finally:
        pg.close()
        local.close()


if __name__ == '__main__':
    main()
