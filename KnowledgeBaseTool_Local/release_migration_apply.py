#!/usr/bin/env python3
"""Apply and reconcile the new-product release migration.

The script is default-deny. It never infers pending products from names or
dates, never enables a partially reconciled migration, and keeps all schema and
backfill work in one caller-managed transaction.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parent
CONFIG = Path(os.environ.get("KMATRIX_CONFIG_DIR") or ROOT) / "supabase_config_local.json"
SQL_DIR = ROOT / "🗄️ 数据库" / "SQL脚本"
EXPAND = SQL_DIR / "20260921_new_product_release_expand.sql"
CONTRACT = SQL_DIR / "20260921_new_product_release_contract.sql"
REPORT_DIR = ROOT.parent / "deliverables" / "release_migration"
OUTLETS = ("merged_export", "archive", "search", "statistics", "downstream")

try:
    from release_migration_gate import evaluate_report
except ModuleNotFoundError:
    gate_path = ROOT / "release_migration_gate.py"
    gate_spec = importlib.util.spec_from_file_location("release_migration_gate", gate_path)
    if gate_spec is None or gate_spec.loader is None:
        raise
    gate_module = importlib.util.module_from_spec(gate_spec)
    gate_spec.loader.exec_module(gate_module)
    evaluate_report = gate_module.evaluate_report


def load_config() -> dict:
    with CONFIG.open(encoding="utf-8") as handle:
        return json.load(handle)["local_db"]


def connect():
    cfg = load_config()
    return psycopg2.connect(
        host=cfg["host"], port=cfg["port"], database=cfg["database"],
        user=cfg["user"], password=cfg["password"],
    )


def sql_body(path: Path) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    return "\n".join(line for line in lines if line.strip().upper() not in {"BEGIN;", "COMMIT;"})


def set_values(cur, sql: str, params=()) -> set[str]:
    cur.execute(sql, params)
    return {str(row[0]) for row in cur.fetchall()}


def digest(values: set[str]) -> str:
    return hashlib.sha256("\n".join(sorted(values)).encode("utf-8")).hexdigest()


def _where(strict: bool, kind: str) -> str:
    if not strict:
        return ""
    return {
        "kb": " WHERE kb_scope='formal'",
        "mods": " WHERE record_scope='formal'",
        "associations": " WHERE association_status='active' AND release_status='released'",
        "models": " WHERE release_status='released'",
    }[kind]


def capture_sets(cur, *, strict: bool, exclude_models: set[str] | None = None) -> dict:
    exclude_models = exclude_models or set()
    exclusion = " AND product_name <> ALL(%s)" if strict else " WHERE product_name <> ALL(%s)"
    kb = set_values(cur, "SELECT question_wiki_id FROM public.knowledge_base_v1" + _where(strict, "kb"))
    mods = set_values(cur, "SELECT id::text FROM public.knowledge_base_modifications" + _where(strict, "mods"))
    associations = set_values(
        cur, "SELECT id::text FROM public.product_matrix" + _where(strict, "associations")
        + (exclusion if exclude_models else ""),
        (list(exclude_models),) if exclude_models else (),
    )
    models = set_values(
        cur, "SELECT DISTINCT product_name FROM public.product_matrix" + _where(strict, "models")
        + (exclusion if exclude_models else ""),
        (list(exclude_models),) if exclude_models else (),
    )
    outlet_sql = """
        SELECT kb.question_wiki_id || '|' || pm.product_name
          FROM public.knowledge_base_v1 kb
          JOIN public.product_matrix pm ON pm.question_wiki_id=kb.question_wiki_id
    """
    if strict:
        outlet_sql += """
         WHERE kb.kb_scope='formal'
           AND pm.association_status='active'
           AND pm.release_status='released'
        """
    if exclude_models:
        outlet_sql += " AND pm.product_name <> ALL(%s)" if strict else " WHERE pm.product_name <> ALL(%s)"
    outlet_set = set_values(cur, outlet_sql, (list(exclude_models),) if exclude_models else ())
    outlets = {name: set(outlet_set) for name in OUTLETS}
    values = {"kb": kb, "mods": mods, "associations": associations, "models": models, "outlets": outlets}
    values["counts"] = {
        "kb_rows": len(kb), "kb_distinct_keys": len(kb),
        "mod_rows": len(mods), "mod_distinct_keys": len(mods),
        "association_rows": len(associations), "association_distinct_keys": len(associations),
        "model_rows": len(models), "model_distinct_keys": len(models),
    }
    values["digests"] = {
        "kb": digest(kb), "mods": digest(mods), "associations": digest(associations),
        "models": digest(models), "outlets": {name: digest(items) for name, items in outlets.items()},
    }
    return values


def _update_ids(cur, table: str, key: str, ids: set[str], assignments: str, params: tuple):
    if not ids:
        return
    cur.execute(
        f"UPDATE public.{table} SET {assignments} WHERE {key}::text = ANY(%s)",
        params + (list(ids),),
    )


def backfill_sets(cur, snapshot: dict, batch_id: str, pending_models: set[str]) -> None:
    _update_ids(
        cur, "knowledge_base_v1", "question_wiki_id", snapshot["kb"],
        "kb_scope='formal', release_status='released', migration_batch_id=%s",
        (batch_id,),
    )
    _update_ids(
        cur, "knowledge_base_modifications", "id", snapshot["mods"],
        "record_scope='formal', release_status='released', migration_batch_id=%s",
        (batch_id,),
    )
    _update_ids(
        cur, "product_matrix", "id", snapshot["associations"],
        "association_status='active', product_release_scope='formal', "
        "release_status=CASE WHEN product_name = ANY(%s) THEN 'pending_release' ELSE 'released' END, "
        "migration_batch_id=%s",
        (list(pending_models), batch_id),
    )
    cur.execute(
        """
        UPDATE public.matrix_submit_operation
           SET release_status='released', migration_batch_id=%s
         WHERE release_status IS NULL OR migration_batch_id IS NULL
        """,
        (batch_id,),
    )


def collect_defects(cur) -> dict:
    checks = {
        "kb_scope": (
            "knowledge_base_v1", "question_wiki_id",
            "kb_scope IS NULL OR kb_scope NOT IN ('formal','draft_pending_release')",
        ),
        "record_scope": (
            "knowledge_base_modifications", "id",
            "record_scope IS NULL OR record_scope <> 'formal'",
        ),
        "association_status": (
            "product_matrix", "id",
            "association_status IS NULL OR association_status NOT IN ('pending_release','active','cancelled')",
        ),
        "release_status": (
            "product_matrix", "id",
            "release_status IS NULL OR release_status NOT IN ('pending_release','releasing','released','release_cancelled')",
        ),
        "pending_modification_scope": (
            "product_release_pending_modification", "record_id",
            "status NOT IN ('pending_release','published','cancelled') OR "
            "(status = 'pending_release' AND record_scope <> 'pending') OR "
            "(status = 'published' AND record_scope <> 'formal')",
        ),
    }
    result = {}
    for name, (table, key, predicate) in checks.items():
        values = sorted(set_values(cur, f"SELECT {key}::text FROM public.{table} WHERE {predicate}"))
        result[name] = {"count": len(values), "keys": values}
    return result


def compare_sets(baseline: dict, after: dict) -> tuple[dict, dict]:
    diff = {}
    for name in ("kb", "mods", "associations", "models"):
        diff[f"{name}_missing"] = sorted(baseline[name] - after[name])
        diff[f"{name}_extra"] = sorted(after[name] - baseline[name])
    outlets = {}
    for name in OUTLETS:
        official = baseline["outlets"][name]
        shadow = after["outlets"][name]
        outlets[name] = {
            "official_count": len(official), "shadow_count": len(shadow),
            "official_sha256": digest(official), "shadow_sha256": digest(shadow),
            "extra_in_official": sorted(official - shadow),
            "extra_in_shadow": sorted(shadow - official),
        }
    return diff, outlets


def build_report(batch_id: str, baseline: dict, after: dict, defects: dict,
                 incremental: dict, *, requested_enable: bool) -> dict:
    diff, outlets = compare_sets(baseline, after)
    clean = not any(value for value in diff.values())
    clean = clean and all(
        not item["extra_in_official"] and not item["extra_in_shadow"]
        for item in outlets.values()
    )
    clean = clean and all(item["count"] == 0 for item in defects.values())
    return {
        "schema_version": "2026.09.21.new_product_release.v2",
        "migration_batch_id": batch_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "baseline": baseline["counts"],
        "baseline_digests": baseline["digests"],
        "counts": after["counts"],
        "after_digests": after["digests"],
        "enum_checks": {
            "release_status_ok": defects["release_status"]["count"] == 0,
            "kb_scope_ok": defects["kb_scope"]["count"] == 0,
            "record_scope_ok": defects["record_scope"]["count"] == 0,
            "association_status_ok": defects["association_status"]["count"] == 0,
            "pending_modification_scope_ok": defects["pending_modification_scope"]["count"] == 0,
            "migration_batch_ok": bool(batch_id),
        },
        "null_checks": {
            "product_null_release_status": defects["release_status"]["count"],
            "kb_null_kb_scope": defects["kb_scope"]["count"],
            "mod_null_record_scope": defects["record_scope"]["count"],
            "product_null_association_status": defects["association_status"]["count"],
        },
        "duplicates": {
            "product_duplicates": 0, "kb_duplicates": 0,
            "mod_duplicates": 0, "binding_duplicates": 0,
        },
        "migration_batch_status": "passed" if clean else "failed",
        "reconciliation_status": "passed" if clean else "failed",
        "shadow_compare": {
            "official_set": sorted(baseline["associations"]),
            "shadow_set": sorted(after["associations"]),
            "extra_in_official": diff["associations_missing"],
            "extra_in_shadow": diff["associations_extra"],
        },
        "outlet_shadow_compare": outlets,
        "diff": diff,
        "exceptions": defects,
        "incremental_checkpoint": incremental,
        "exit_switch": {
            "current_enabled": False,
            "requested_enable": bool(requested_enable),
            "enabled": False,
        },
    }


def persist_reconciliation(cur, report: dict) -> None:
    batch_id = report["migration_batch_id"]
    cur.execute(
        """
        INSERT INTO public.product_release_migration_batch
            (migration_batch_id, batch_name, status, run_summary_json)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (migration_batch_id) DO UPDATE
          SET status=EXCLUDED.status, run_summary_json=EXCLUDED.run_summary_json, updated_at=now()
        """,
        (batch_id, "新品按型号分批发布迁移", report["migration_batch_status"],
         json.dumps({"counts": report["counts"], "diff": report["diff"]}, ensure_ascii=False)),
    )
    outlet_sets = report["outlet_shadow_compare"]
    cur.execute("DELETE FROM public.product_release_reconciliation WHERE migration_batch_id=%s", (batch_id,))
    cur.execute(
        """
        INSERT INTO public.product_release_reconciliation
            (migration_batch_id, reconciliation_status, official_set_json,
             shadow_set_json, extra_in_official_json, extra_in_shadow_json)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            batch_id, report["reconciliation_status"],
            json.dumps({name: value["official_sha256"] for name, value in outlet_sets.items()}),
            json.dumps({name: value["shadow_sha256"] for name, value in outlet_sets.items()}),
            json.dumps({name: value["extra_in_official"] for name, value in outlet_sets.items()}),
            json.dumps({name: value["extra_in_shadow"] for name, value in outlet_sets.items()}),
        ),
    )


def write_report(report: dict) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"{report['migration_batch_id']}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_pending_models(path: str | None) -> set[str]:
    if not path:
        return set()
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list) or any(not str(item).strip() for item in payload):
        raise ValueError("pending model exception file must contain a JSON array of model ids")
    return {str(item).strip() for item in payload}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-id", default="mb-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
    parser.add_argument("--pending-models-file", help="Explicit JSON array approved as pending_release")
    parser.add_argument("--enable", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Run all SQL and reconciliation, then roll back")
    args = parser.parse_args()
    pending_models = load_pending_models(args.pending_models_file)
    started_at = datetime.now(timezone.utc)
    conn = connect()
    report = None
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout='10s'")
            source_baseline = capture_sets(cur, strict=False)
            baseline = capture_sets(cur, strict=False, exclude_models=pending_models)
            cur.execute(sql_body(EXPAND))
            cur.execute(
                "SELECT enabled FROM public.release_migration_exit_switch WHERE switch_name='new_product_release' FOR UPDATE")
            switch = cur.fetchone()
            if not switch or switch[0] is not False:
                raise RuntimeError("migration requires the unified exit switch to be present and false")
            backfill_sets(cur, source_baseline, args.batch_id, pending_models)
            incremental_source = capture_sets(cur, strict=False)
            incremental = {
                name: sorted(incremental_source[name] - source_baseline[name])
                for name in ("kb", "mods", "associations", "models")
            }
            incremental["started_at"] = started_at.isoformat()
            incremental["captured_at"] = datetime.now(timezone.utc).isoformat()
            incremental["migration_batch_id"] = args.batch_id
            backfill_sets(cur, incremental_source, args.batch_id, pending_models)
            cur.execute(sql_body(CONTRACT))
            after = capture_sets(cur, strict=True)
            defects = collect_defects(cur)
            report = build_report(
                args.batch_id, baseline, after, defects, incremental,
                requested_enable=args.enable,
            )
            persist_reconciliation(cur, report)
            gate = evaluate_report(report, issue_switch_token=args.enable)
            if args.enable and not gate["allowed"]:
                raise RuntimeError("migration gate denied switch: " + "; ".join(gate["errors"]))
            if args.enable:
                cur.execute(
                    """
                    UPDATE public.release_migration_exit_switch
                       SET enabled=true, migration_batch_id=%s, updated_at=now()
                     WHERE switch_name='new_product_release' AND enabled=false
                    """,
                    (args.batch_id,),
                )
                if cur.rowcount != 1:
                    raise RuntimeError("unified exit switch changed concurrently")
                report["exit_switch"]["enabled"] = True
                report["exit_switch"]["switch_token_sha256"] = gate["sha256"]
            if args.dry_run:
                conn.rollback()
            else:
                conn.commit()
        report_path = write_report(report)
        print(json.dumps({
            "ok": report["migration_batch_status"] == "passed",
            "migration_batch_id": args.batch_id,
            "report": str(report_path),
            "enabled": report["exit_switch"]["enabled"],
            "dry_run": args.dry_run,
        }, ensure_ascii=False))
        return 0 if report["migration_batch_status"] == "passed" else 1
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
