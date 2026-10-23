#!/usr/bin/env python3
"""Match an offline workbook by ID and update only image business tags."""

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from zipfile import ZipFile
import xml.etree.ElementTree as ET

import psycopg2
from psycopg2.extras import Json, RealDictCursor


NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def is_source_tag(tag):
    return tag.startswith(("来源:", "外链类型:"))


def parse_tags(value):
    """Split agreed separators outside parentheses, without rewriting names."""
    tags, current, stack = [], [], []
    pairs = {"）": "（", ")": "(", "】": "【", "]": "["}
    for char in value:
        if char in "（(【[":
            stack.append(char)
        elif char in pairs and stack and stack[-1] == pairs[char]:
            stack.pop()
        if char in "、,，\n\r" and not stack:
            tag = "".join(current).strip()
            if tag and tag not in tags:
                tags.append(tag)
            current = []
        else:
            current.append(char)
    tag = "".join(current).strip()
    if tag and tag not in tags:
        tags.append(tag)
    for tag in tags:
        if len(tag) > 100 or any(ord(c) < 32 for c in tag) or is_source_tag(tag):
            raise ValueError(f"Invalid business tag: {tag!r}")
    if len(tags) > 200:
        raise ValueError("Too many tags in one row")
    return tags


def read_rows(path):
    with ZipFile(path) as z:
        strings = []
        if "xl/sharedStrings.xml" in z.namelist():
            strings = ["".join(t.text or "" for t in si.findall(".//m:t", NS))
                       for si in ET.fromstring(z.read("xl/sharedStrings.xml"))]
        book = ET.fromstring(z.read("xl/workbook.xml"))
        sheet = next(s for s in book.findall("m:sheets/m:sheet", NS)
                     if s.get("name") == "图片清单")
        relationships = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        target = next(r.get("Target") for r in relationships if r.get("Id") == sheet.get(f"{{{REL}}}id"))
        sheet_path = target.lstrip("/") if target.startswith("/") else "xl/" + target
        data = []
        for row in ET.fromstring(z.read(sheet_path)).findall("m:sheetData/m:row", NS):
            cells = {}
            for cell in row.findall("m:c", NS):
                col = re.match(r"[A-Z]+", cell.get("r")).group()
                value = cell.find("m:v", NS)
                value = value.text or "" if value is not None else ""
                if cell.get("t") == "s" and value:
                    value = strings[int(value)]
                elif cell.get("t") == "inlineStr":
                    value = "".join(t.text or "" for t in cell.findall(".//m:t", NS))
                if col in ("B", "D", "F") and cell.find("m:f", NS) is not None:
                    raise ValueError(f"Unexpected formula in import field {cell.get('r')}")
                cells[col] = value
            row_num = int(row.get("r"))
            if row_num == 1:
                if cells.get("B") != "记录ID（请勿修改）" or cells.get("F") != "当前标签（可修改）":
                    raise ValueError("Unexpected workbook headers")
                continue
            if not any(cells.get(c) for c in ("B", "D", "F")):
                continue
            data.append({"row": row_num, "id": cells.get("B", "").strip(),
                         "url": cells.get("D", "").strip(),
                         "tags": parse_tags(cells.get("F", "")),
                         "source_tags": parse_tags_source(cells.get("G", ""))})
    ids = [row["id"] for row in data]
    if not ids or any(not ident for ident in ids):
        raise ValueError("Missing record IDs")
    return data


def parse_tags_source(value):
    return [t.strip() for t in re.split(r"[、,，\r\n]", value) if t.strip()]


def read_database(cursor, lock=False):
    cursor.execute("SELECT * FROM link_previews ORDER BY id" + (" FOR UPDATE" if lock else ""))
    return [dict(row) for row in cursor.fetchall()]


def plan_changes(rows, before):
    by_id = {row["id"]: row for row in before}
    by_url = {}
    for live in before:
        by_url.setdefault(live["url"], []).append(live)
    resolved_ids, corrections = set(), []
    changes, unchanged, source_differences = [], 0, []
    for row in rows:
        live = by_id.get(row["id"])
        if live is None or row["url"] != live["url"]:
            matches = by_url.get(row["url"], [])
            if len(matches) != 1:
                raise ValueError(f"Cannot uniquely match URL: row {row['row']}")
            live = matches[0]
            corrections.append({"row": row["row"], "workbook_id": row["id"], "database_id": live["id"],
                                "reason": "exact_unique_image_url"})
        if live is None or str(live.get("type", "")).lower() != "image":
            raise ValueError(f"Record missing or no longer an image: row {row['row']}")
        if row["url"] != live["url"]:
            raise ValueError(f"URL mismatch: row {row['row']}")
        if live["id"] in resolved_ids:
            raise ValueError(f"Multiple workbook rows target one database record: row {row['row']}")
        resolved_ids.add(live["id"])
        old = live.get("tags") or []
        if not isinstance(old, list) or any(not isinstance(t, str) for t in old):
            raise ValueError(f"Invalid stored tags: row {row['row']}")
        source = [tag for tag in old if is_source_tag(tag)]
        if source != row["source_tags"]:
            source_differences.append(row["row"])
        new = source + row["tags"]
        if set(old) == set(new):
            unchanged += 1
            continue
        changes.append({"row": row["row"], "id": live["id"], "old_tags": old, "new_tags": new})
    return changes, unchanged, source_differences, corrections


def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, default=str)
        stream.flush()
        import os
        os.fsync(stream.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--audit-dir", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    rows = read_rows(args.workbook)
    config = json.loads(args.config.read_text())["local_db"]
    connection = psycopg2.connect(**config)
    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SET LOCAL lock_timeout = '10s'")
            cursor.execute("SET LOCAL statement_timeout = '60s'")
            before = read_database(cursor, lock=args.apply)
            changes, unchanged, source_differences, corrections = plan_changes(rows, before)
            summary = {"mode": "apply" if args.apply else "dry_run", "workbook_rows": len(rows),
                       "matched": len(rows), "changed": len(changes), "unchanged": unchanged,
                       "blank_business_tags": sum(not r["tags"] for r in rows),
                       "distinct_business_tags": len({t for r in rows for t in r["tags"]}),
                       "source_differences_preserved_from_database": source_differences,
                       "id_corrections_matched_by_unique_url": corrections,
                       "table_records": len(before),
                       "top_labels": Counter(t for r in rows for t in r["tags"]).most_common(8)}
            args.audit_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            plan_path = args.audit_dir / f"{stamp}_{summary['mode']}.json"
            write_json(plan_path, {"summary": summary, "source_workbook": str(args.workbook.resolve()),
                                  "workbook_sha256": hashlib.sha256(args.workbook.read_bytes()).hexdigest(),
                                  "active_config": str(args.config.resolve()), "changes": changes})
            if args.apply:
                backup_path = args.audit_dir / f"{stamp}_before.json"
                write_json(backup_path, before)
                for change in changes:
                    cursor.execute("UPDATE link_previews SET tags=%s WHERE id=%s", (Json(change["new_tags"]), change["id"]))
                    if cursor.rowcount != 1:
                        raise RuntimeError("Update did not affect exactly one record")
                after = read_database(cursor)
                wanted = {change["id"]: change["new_tags"] for change in changes}
                expected = [{**row, **({"tags": wanted[row["id"]]} if row["id"] in wanted else {})} for row in before]
                if expected != after:
                    raise RuntimeError("Post-update verification failed; rolling back")
                connection.commit()
                if read_database(cursor) != after:
                    raise RuntimeError("Readback after commit differed")
                summary.update({"backup": str(backup_path.resolve()), "verified": True})
                write_json(args.audit_dir / f"{stamp}_receipt.json", summary)
            else:
                connection.rollback()
            summary["audit"] = str(plan_path.resolve())
            print(json.dumps(summary, ensure_ascii=False))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
