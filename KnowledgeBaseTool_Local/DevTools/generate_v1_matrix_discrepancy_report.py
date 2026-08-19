#!/usr/bin/env python3
"""Read-only V1/product-matrix product_name reconciliation preview.

The script intentionally does not write to PostgreSQL. It emits CSV, JSON and
Markdown reports so the reconciliation can be reviewed before any backfill.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import psycopg2


def load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))["local_db"]


def normalize_name(value: object) -> str:
    text = str(value or "").replace("\u3000", " ")
    return re.sub(r"\s+", " ", text).strip().casefold()


def split_names(value: object) -> set[str]:
    return {name for item in re.split(r"[,，\n]+", str(value or "")) if (name := normalize_name(item))}


def display_names(names: dict[str, str] | set[str]) -> str:
    """Render names in source spelling while keeping deterministic ordering."""
    if isinstance(names, dict):
        values = names.values()
    else:
        values = names
    return ",".join(sorted(values, key=lambda value: (value.casefold(), value)))


def parse_dt(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso_dt(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def classify(v1_names: set[str], matrix_names: set[str], v1_time: datetime | None, matrix_time: datetime | None,
             button_time: datetime | None) -> tuple[str, str, str, bool]:
    if not v1_names:
        category = "matrix_only_missing_v1"
    elif not matrix_names:
        category = "v1_only_missing_matrix"
    elif v1_names < matrix_names:
        category = "matrix_superset"
    elif matrix_names < v1_names:
        category = "v1_superset"
    else:
        category = "both_different"

    if v1_time and matrix_time:
        delta_seconds = (matrix_time - v1_time).total_seconds()
        if delta_seconds > 60:
            temporal = "matrix_newer"
        elif delta_seconds < -60:
            temporal = "v1_newer"
        else:
            temporal = "same_or_close"
    elif matrix_time:
        temporal = "matrix_only_evidence"
    elif v1_time:
        temporal = "v1_only_evidence"
    else:
        temporal = "unknown"

    # A button submission is the strongest available evidence that the matrix
    # value was intentionally changed. A last_synced_at-only row may be a
    # migration or bulk refresh and is therefore not an automatic backfill.
    # Require the explicit submission itself to be newer than the V1 value.
    # A later sync timestamp with an older button event can represent a bulk
    # refresh and must not become an automatic backfill candidate.
    reliable = bool(
        v1_names
        and matrix_names
        and button_time
        and (not v1_time or (button_time - v1_time).total_seconds() > 60)
    )
    if reliable:
        recommendation = "可回填：矩阵有按钮提交审计且晚于V1；先人工抽样后批准"
        action = "backfill_candidate"
    elif category == "matrix_only_missing_v1":
        recommendation = "不可直接回填：V1不存在；先确认是否应创建/恢复V1条目"
        action = "investigate_missing_v1"
    elif temporal == "v1_newer":
        recommendation = "保留V1：V1更新时间较新；复核矩阵是否过期或误改"
        action = "keep_v1_review_matrix"
    elif temporal in {"matrix_newer", "matrix_only_evidence"}:
        recommendation = "矩阵较新但缺少明确按钮证据；人工核对后再决定"
        action = "manual_review_matrix_newer"
    elif temporal == "same_or_close":
        recommendation = "时间接近且值不同；无法仅凭时间判定，人工核对"
        action = "manual_review_conflict"
    else:
        recommendation = "缺少可比较时间证据；人工核对，不自动回填"
        action = "manual_review_no_time"
    return category, temporal, action, reliable, recommendation


def build_rows(conn) -> list[dict[str, object]]:
    with conn.cursor() as cur:
        cur.execute("SELECT question_wiki_id, product_name, update_time, content_version FROM knowledge_base_v1")
        v1 = {
            str(wiki_id): {"product_name": product_name or "", "update_time": update_time, "content_version": version}
            for wiki_id, product_name, update_time, version in cur.fetchall()
        }
        cur.execute(
            """SELECT question_wiki_id, product_name, is_configured, last_synced_at, update_time
               FROM product_matrix"""
        )
        matrix_rows: dict[str, list[tuple[object, bool, object, object]]] = defaultdict(list)
        for wiki_id, product_name, configured, synced_at, update_time in cur.fetchall():
            matrix_rows[str(wiki_id)].append((product_name, bool(configured), synced_at, update_time))
        cur.execute("SELECT question_wiki_id, max(submitted_at) FROM button GROUP BY question_wiki_id")
        button_times = {str(wiki_id): submitted_at for wiki_id, submitted_at in cur.fetchall()}

    rows: list[dict[str, object]] = []
    for wiki_id in sorted(set(v1) | set(matrix_rows)):
        v1_row = v1.get(wiki_id) or {}
        raw_matrix = matrix_rows.get(wiki_id) or []
        matrix_name_display: dict[str, str] = {}
        for product_name, configured, _, _ in raw_matrix:
            normalized = normalize_name(product_name)
            if configured and normalized and normalized not in matrix_name_display:
                matrix_name_display[normalized] = str(product_name).strip()
        matrix_names = set(matrix_name_display)
        v1_names = split_names(v1_row.get("product_name", ""))
        if v1_names == matrix_names:
            continue

        matrix_sync = max((parse_dt(synced_at) for _, _, synced_at, _ in raw_matrix if parse_dt(synced_at)), default=None)
        matrix_updates = max((parse_dt(update_time) for _, _, _, update_time in raw_matrix if parse_dt(update_time)), default=None)
        button_time = parse_dt(button_times.get(wiki_id))
        evidence_candidates = [("product_matrix.last_synced_at", matrix_sync), ("product_matrix.update_time", matrix_updates), ("button.submitted_at", button_time)]
        evidence_time = max((value for _, value in evidence_candidates if value), default=None)
        evidence_sources = ";".join(label for label, value in evidence_candidates if value and value == evidence_time)
        v1_time = parse_dt(v1_row.get("update_time"))
        category, temporal, action, reliable, recommendation = classify(v1_names, matrix_names, v1_time, evidence_time, button_time)
        added = sorted(matrix_names - v1_names)
        removed = sorted(v1_names - matrix_names)
        rows.append({
            "question_wiki_id": wiki_id,
            "v1_product_name": v1_row.get("product_name", ""),
            "matrix_product_name": display_names(matrix_name_display),
            "v1_product_set_normalized": display_names(v1_names),
            "matrix_product_set_normalized": display_names(matrix_names),
            "added_by_matrix": ",".join(added),
            "removed_by_matrix": ",".join(removed),
            "v1_update_time": iso_dt(v1_time),
            "matrix_last_synced_at": iso_dt(matrix_sync),
            "matrix_data_update_time": iso_dt(matrix_updates),
            "matrix_button_submitted_at": iso_dt(button_time),
            "matrix_evidence_at": iso_dt(evidence_time),
            "matrix_evidence_source": evidence_sources,
            "category": category,
            "temporal_relation": temporal,
            "recommended_action": action,
            "recommendation": recommendation,
            "reliable_backfill_candidate": "yes" if reliable else "no",
            "v1_content_version": v1_row.get("content_version", ""),
            "matrix_row_count": len(raw_matrix),
            "matrix_configured_count": len(matrix_names),
        })
    return rows


def write_reports(rows: list[dict[str, object]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = output_dir / "20260817_v1_matrix_product_name_discrepancy_preview"
    fieldnames = list(rows[0].keys()) if rows else ["question_wiki_id"]
    with (stem.with_suffix(".csv")).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    (stem.with_suffix(".json")).write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")

    counts = Counter(row["category"] for row in rows)
    temporal = Counter(row["temporal_relation"] for row in rows)
    actions = Counter(row["recommended_action"] for row in rows)
    reliable = [row for row in rows if row["reliable_backfill_candidate"] == "yes"]
    lines = [
        "# V1 vs 矩阵 product_name 差异预览（只读）",
        "",
        "> 生成时间：2026-08-17；数据源为本地 PostgreSQL `knowledgebase_local`。本报告未修改数据库，也未切换 `use_supabase_matrix`。",
        "",
        f"- 差异总数：**{len(rows)}**",
        f"- 分类统计：{json.dumps(dict(counts), ensure_ascii=False)}",
        f"- 时间关系：{json.dumps(dict(temporal), ensure_ascii=False)}",
        f"- 建议动作：{json.dumps(dict(actions), ensure_ascii=False)}",
        f"- 明确可回填候选：**{len(reliable)}**（仅指已有 V1 且有 `button.submitted_at` 且矩阵证据晚于 V1；仍需人工批准）",
        "",
        "## 字段说明",
        "",
        "`matrix_product_name` 仅聚合 `product_matrix.is_configured = true` 的型号。`matrix_evidence_at` 是 `last_synced_at`、`product_matrix.update_time`、`button.submitted_at` 中最新时间；只有按钮提交审计才被视为可自动回填的可靠意图证据。",
        "",
        "完整 787 条逐行清单见同名 CSV/JSON。下面列出所有明确可回填候选的 ID，供人工抽样：",
        "",
        "| question_wiki_id | V1 product_name | 矩阵 product_name | V1 更新时间 | 按钮提交时间 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in reliable:
        lines.append(f"| {row['question_wiki_id']} | {row['v1_product_name']} | {row['matrix_product_name']} | {row['v1_update_time']} | {row['matrix_button_submitted_at']} |")
    lines.extend(["", "## 后续边界", "", "- `matrix_only_missing_v1` 不可直接更新 V1，因为 V1 行不存在；应先确认是否为误导入、待恢复条目或合法矩阵孤儿。", "- `matrix_newer` 但无按钮审计的条目只做人工复核，不自动回填。", "- 在人工批准回填并重新对账前，不应把 `use_supabase_matrix` 切换为 `true`。", ""])
    stem.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parent.parent / "supabase_config_local.json")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent / "reports")
    args = parser.parse_args()
    cfg = load_config(args.config)
    conn = psycopg2.connect(host=cfg["host"], port=cfg["port"], dbname=cfg["database"], user=cfg["user"], password=cfg["password"], connect_timeout=5)
    try:
        rows = build_rows(conn)
    finally:
        conn.close()
    write_reports(rows, args.output_dir)
    print(json.dumps({"rows": len(rows), "categories": dict(Counter(row["category"] for row in rows)), "reliable_backfill_candidates": sum(row["reliable_backfill_candidate"] == "yes" for row in rows), "output_dir": str(args.output_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
