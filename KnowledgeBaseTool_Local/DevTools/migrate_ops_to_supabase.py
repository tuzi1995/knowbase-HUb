import json
import os
import sqlite3
from typing import List, Dict, Any

import requests


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQLITE_PATH = os.path.join(BASE_DIR, "instance", "data.db")
CONFIG_PATH = os.path.join(BASE_DIR, "supabase_config.json")


def _load_config() -> Dict[str, Any]:
    if not os.path.exists(CONFIG_PATH):
        raise RuntimeError(f"Missing config: {CONFIG_PATH}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    if not isinstance(cfg, dict):
        raise RuntimeError("supabase_config.json format invalid")
    return cfg


def _load_ops_from_sqlite() -> List[Dict[str, Any]]:
    if not os.path.exists(SQLITE_PATH):
        raise RuntimeError(f"Missing sqlite db: {SQLITE_PATH}")
    con = sqlite3.connect(SQLITE_PATH)
    con.row_factory = sqlite3.Row
    try:
        cur = con.cursor()
        cur.execute(
            """
            SELECT id, kind, name, steps, compatible_models, sort_order, created_at, updated_at
            FROM ops_library_item
            ORDER BY kind ASC, sort_order ASC, id ASC
            """
        )
        rows = cur.fetchall()
        out = []
        for r in rows:
            out.append({
                "id": int(r["id"]),
                "kind": str(r["kind"] or "").strip(),
                "name": str(r["name"] or "").strip(),
                "steps": str(r["steps"] or ""),
                "compatible_models": str(r["compatible_models"] or ""),
                "sort_order": int(r["sort_order"] or 0),
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            })
        return out
    finally:
        con.close()


def _upsert_chunks(url: str, key: str, rows: List[Dict[str, Any]], chunk_size: int = 500) -> None:
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates, return=minimal",
    }
    endpoint = f"{url}/rest/v1/ops_library_item?on_conflict=id"
    total = len(rows)
    done = 0
    for i in range(0, total, chunk_size):
        batch = rows[i:i + chunk_size]
        resp = requests.post(endpoint, headers=headers, json=batch, timeout=120)
        if resp.status_code >= 400:
            raise RuntimeError(f"Supabase upsert failed: {resp.status_code} {resp.text}")
        done += len(batch)
        print(f"Upserted {done}/{total}")


def main() -> None:
    cfg = _load_config()
    url = str(cfg.get("url") or "").strip()
    key = str(cfg.get("service_role_key") or cfg.get("key") or "").strip()
    if not url or not key:
        raise RuntimeError("supabase_config.json missing url/key")

    rows = _load_ops_from_sqlite()
    if not rows:
        print("No ops_library_item rows found in local sqlite; nothing to migrate.")
        return

    print(f"Loaded {len(rows)} rows from sqlite")
    _upsert_chunks(url, key, rows)
    print("Migration done.")


if __name__ == "__main__":
    main()
