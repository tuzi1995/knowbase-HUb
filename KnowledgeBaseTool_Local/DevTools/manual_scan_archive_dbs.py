import os
import sqlite3
from datetime import datetime
from typing import List, Tuple


def _looks_like_db(name: str) -> bool:
    n = name.lower()
    return n.endswith(".db") or n.endswith(".sqlite") or n.endswith(".sqlite3")


def _table_exists(cur: sqlite3.Cursor, table: str) -> bool:
    row = cur.execute(
        "select name from sqlite_master where type='table' and name=?",
        (table,),
    ).fetchone()
    return bool(row)


def _count(cur: sqlite3.Cursor, table: str) -> int:
    row = cur.execute(f"select count(*) from {table}").fetchone()
    return int((row or [0])[0] or 0)


def _scan_root(root: str, max_depth: int = 8) -> List[Tuple[str, int, int, float]]:
    out: List[Tuple[str, int, int, float]] = []
    root = os.path.abspath(root)
    root_depth = root.count(os.sep)
    for base, dirs, files in os.walk(root):
        depth = base.count(os.sep) - root_depth
        if depth > max_depth:
            dirs[:] = []
            continue
        for f in files:
            if not _looks_like_db(f):
                continue
            p = os.path.join(base, f)
            try:
                conn = sqlite3.connect(p)
                cur = conn.cursor()
                if _table_exists(cur, "archive_batch") and _table_exists(cur, "archive_record"):
                    b = _count(cur, "archive_batch")
                    r = _count(cur, "archive_record")
                    mtime = 0.0
                    try:
                        mtime = float(os.path.getmtime(p))
                    except Exception:
                        pass
                    out.append((p, b, r, mtime))
                conn.close()
            except Exception:
                continue
    return out


def main() -> int:
    roots = [
        os.path.expanduser("~"),
        "/Users",
        "/root",
        "/home",
        "/opt",
        "/data",
        "/srv",
        "/var/www",
        "/var/lib",
        "/www",
    ]
    all_hits: List[Tuple[str, int, int, float]] = []
    for root in roots:
        if not os.path.exists(root):
            continue
        hits = _scan_root(root, max_depth=8)
        all_hits.extend(hits)

    if not all_hits:
        print("NO_ARCHIVE_DB_FOUND")
        return 0

    all_hits.sort(key=lambda x: (x[1], x[2], x[3]), reverse=True)
    print("FOUND_ARCHIVE_DBS")
    for p, b, r, m in all_hits:
        mtxt = ""
        if m > 0:
            mtxt = datetime.fromtimestamp(m).isoformat(sep=" ", timespec="seconds")
        print(f"{p} | archive_batch={b} | archive_record={r} | mtime={mtxt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
