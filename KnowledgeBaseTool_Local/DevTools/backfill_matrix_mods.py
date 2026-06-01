import os
import sqlite3
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

import server


IDS_TEXT = """
ICWIKI202509150002
ICWIKI202509150003
ICWIKI202509150006
ICWIKI202509150011
ICWIKI202509220001
ICWIKI202509220002
ICWIKI202509220003
ICWIKI202509220004
ICWIKI202509220006
ICWIKI202509220007
ICWIKI202509220008
ICWIKI202509220009
ICWIKI202509280002
ICWIKI202509280003
ICWIKI202509280005
ICWIKI202509280006
ICWIKI202509290010
ICWIKI202509290050
ICWIKI202509290059
ICWIKI202509290074
ICWIKI202509290092
ICWIKI202509290093
ICWIKI202509290094
ICWIKI202509290111
ICWIKI202510130001
ICWIKI202510130005
ICWIKI202510130015
ICWIKI202510210002
ICWIKI202510210023
ICWIKI202510210029
ICWIKI202510210030
ICWIKI202510270022
ICWIKI202511030006
ICWIKI202511100002
ICWIKI202511100006
ICWIKI202511100007
ICWIKI202511110001
ICWIKI202511170001
ICWIKI202511170005
ICWIKI202511210001
ICWIKI202511210002
ICWIKI202511210003
ICWIKI202511240004
ICWIKI202511240018
ICWIKI202512010001
ICWIKI202512080015
ICWIKI202512080018
ICWIKI202512080019
ICWIKI202512080020
ICWIKI202512080021
ICWIKI202512150002
ICWIKI202512150029
ICWIKI202512150031
ICWIKI202512150037
ICWIKI202512150039
ICWIKI202512150040
ICWIKI202512150053
ICWIKI202512150055
ICWIKI202512150061
ICWIKI202512150063
ICWIKI202512230003
ICWIKI202601140012
ICWIKI202601140013
ICWIKI202601220023
ICWIKI202601220025
ICWIKI202601280003
ICWIKI202601280005
ICWIKI202602020001
ICWIKI202602020002
ICWIKI202602020003
ICWIKI202602050004
ICWIKI202602090001
""".strip()


def _dedup(items: List[str]) -> List[str]:
    out: List[str] = []
    seen: Set[str] = set()
    for x in items:
        if x not in seen:
            out.append(x)
            seen.add(x)
    return out


def _parse_ids(text: str) -> List[str]:
    ids = [x.strip() for x in text.split() if x.strip()]
    return _dedup(ids)


def _is_archived(cur: sqlite3.Cursor, wid: str) -> bool:
    row = cur.execute(
        "SELECT 1 FROM archive_record WHERE record_json LIKE ? LIMIT 1",
        (f"%{wid}%",),
    ).fetchone()
    return bool(row)


def _get_latest_operation(cur: sqlite3.Cursor, wid: str) -> Optional[sqlite3.Row]:
    return cur.execute(
        "SELECT operation_id, submitted_at FROM button WHERE question_wiki_id=? ORDER BY submitted_at DESC LIMIT 1",
        (wid,),
    ).fetchone()


def _get_button_rows(cur: sqlite3.Cursor, wid: str, operation_id: str) -> List[sqlite3.Row]:
    return cur.execute(
        "SELECT product_name, old_is_configured, new_is_configured, edit_source FROM button WHERE question_wiki_id=? AND operation_id=?",
        (wid, operation_id),
    ).fetchall()


def _get_after_products_map(cur: sqlite3.Cursor, wiki_ids: List[str]) -> Dict[str, Set[str]]:
    if not wiki_ids:
        return {}
    qmarks = ",".join(["?"] * len(wiki_ids))
    rows = cur.execute(
        f"SELECT question_wiki_id, product_name FROM product_matrix WHERE is_configured=1 AND question_wiki_id IN ({qmarks})",
        wiki_ids,
    ).fetchall()
    out: Dict[str, Set[str]] = {}
    for r in rows:
        wid = str(r["question_wiki_id"] or "").strip()
        pn = str(r["product_name"] or "").strip()
        if wid and pn:
            out.setdefault(wid, set()).add(pn)
    return out


def _parse_dt(value: object) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    s = str(value).strip()
    if not s:
        return datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _build_mod_record(
    *,
    wid: str,
    kb_row: Dict,
    after_products: Set[str],
    button_rows: List[sqlite3.Row],
    operation_id: str,
    submitted_at: object,
) -> Dict:
    after_set = set(after_products)
    before_set = set(after_set)
    changed_products: List[str] = []
    edit_sources: List[str] = []

    for br in button_rows:
        pn = str(br["product_name"] or "").strip()
        if pn:
            changed_products.append(pn)
        es = str(br["edit_source"] or "").strip()
        if es:
            edit_sources.append(es)
        old_v = bool(br["old_is_configured"])
        new_v = bool(br["new_is_configured"])
        if new_v and (not old_v):
            before_set.discard(pn)
        elif (not new_v) and old_v:
            before_set.add(pn)

    changed_products = _dedup([x for x in changed_products if x])
    edit_sources = _dedup([x for x in edit_sources if x])

    before_products = ", ".join(sorted(before_set))
    after_products_str = ", ".join(sorted(after_set))

    rec = dict(kb_row or {})
    rec.pop("id", None)
    rec["kb_id"] = wid
    rec["question_wiki_id"] = wid
    rec["change_type"] = "edit"
    rec["modifier"] = "admin"
    rec["modification_time"] = _parse_dt(submitted_at).isoformat()
    rec["product_name"] = after_products_str

    before_obj = server._snapshot_mod_fields(rec)
    before_obj["products"] = before_products
    after_obj = server._snapshot_mod_fields(rec)
    after_obj["products"] = after_products_str
    changed_fields = server._compute_mod_changed_fields(before_obj, after_obj)

    server._attach_change_meta(
        rec,
        {
            "source": "机型矩阵管理",
            "operation_id": operation_id,
            "edit_source": edit_sources[0] if len(edit_sources) == 1 else ",".join(edit_sources),
            "changed_products": changed_products,
            "before": before_obj,
            "after": after_obj,
            "changed_fields": changed_fields,
        },
    )
    return rec


def main() -> int:
    base = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base, "instance", "data.db")
    ids = _parse_ids(IDS_TEXT)

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    archived = [wid for wid in ids if _is_archived(cur, wid)]
    archived_set = set(archived)
    candidates = [wid for wid in ids if wid not in archived_set]

    client = server.get_supabase_client()
    if not client:
        raise RuntimeError("Supabase client not available")

    existing_set: Set[str] = set()
    in_str = server._postgrest_in_str(candidates)
    if in_str:
        existing = (
            client.select_all(
                "knowledge_base_modifications",
                filters={"kb_id": in_str},
                order_by="modification_time",
                order_dir="desc",
                columns="kb_id",
                page_size=1000,
            )
            or []
        )
        for r in existing:
            k = str(r.get("kb_id") or "").strip()
            if k:
                existing_set.add(k)

    missing = [wid for wid in candidates if wid not in existing_set]

    print(
        "ids_total",
        len(ids),
        "archived_local",
        len(archived),
        "candidate_not_archived",
        len(candidates),
        "already_in_supabase_mods",
        len(existing_set),
        "need_backfill",
        len(missing),
    )

    if not missing:
        con.close()
        return 0

    kb_map: Dict[str, Dict] = {}
    kb_in = server._postgrest_in_str(missing)
    if kb_in:
        kb_rows = (
            client.select_all(
                "knowledge_base_v1",
                filters={"question_wiki_id": kb_in},
                order_by="question_wiki_id",
                order_dir="asc",
                columns="question_wiki_id,question,answer,question_type,answer_type,if_bm25,similar_questions,error_list,keyword_list,image_urls,video_urls,file_urls,link_type,link_url,update_time,product_name,product_category_name",
                page_size=1000,
            )
            or []
        )
        for r in kb_rows:
            wid = str(r.get("question_wiki_id") or "").strip()
            if wid:
                kb_map[wid] = r

    after_map = _get_after_products_map(cur, missing)

    mod_records: List[Dict] = []
    for wid in missing:
        latest = _get_latest_operation(cur, wid)
        if not latest:
            continue
        operation_id = str(latest["operation_id"] or "").strip()
        btn_rows = _get_button_rows(cur, wid, operation_id)
        rec = _build_mod_record(
            wid=wid,
            kb_row=kb_map.get(wid, {}),
            after_products=after_map.get(wid, set()),
            button_rows=btn_rows,
            operation_id=operation_id,
            submitted_at=latest["submitted_at"],
        )
        mod_records.append(rec)

    con.close()

    print("prepared_mod_records", len(mod_records))
    if not mod_records:
        return 0

    resp = client.insert("knowledge_base_modifications", mod_records)
    ok = bool(resp) and resp.status_code in (200, 201)
    print("insert_status", getattr(resp, "status_code", None), "ok", ok)
    if not ok:
        raise RuntimeError(getattr(resp, "text", "") or "unknown insert error")

    probe = missing[:5]
    for wid in probe:
        r = client.select(
            "knowledge_base_modifications",
            page=1,
            page_size=1,
            order_by="modification_time",
            order_dir="desc",
            filters={"kb_id": f"eq.{wid}"},
        )
        if r.status_code >= 400:
            print("probe", wid, "ERR", r.status_code, (r.text or "")[:160])
        else:
            print("probe", wid, "OK", len(r.json() or []))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
