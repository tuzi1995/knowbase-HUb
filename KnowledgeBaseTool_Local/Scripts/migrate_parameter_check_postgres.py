from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from parameter_check import (
    PARAMETER_CHECK_SCHEMA_VERSION,
    apply_schema,
    backfill_historical_ai_candidate_assessments,
    connect_main_database,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the 8085 parameter-check audit schema in PostgreSQL.")
    parser.add_argument("--config", help="Path to supabase_config_local.json")
    args = parser.parse_args()

    connection = connect_main_database(args.config)
    try:
        apply_schema(connection)
        historical_assessment_count = backfill_historical_ai_candidate_assessments(connection)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN (
                    'parameter_snapshot',
                    'parameter_model_alias_binding',
                    'kb_parameter_claim',
                    'kb_parameter_claim_model',
                    'parameter_check_run',
                    'parameter_check_finding',
                    'parameter_ai_scan_receipt',
                    'parameter_ai_scan_item',
                    'parameter_ai_candidate_assessment'
                  )
                ORDER BY table_name
                """
            )
            tables = [row[0] for row in cursor.fetchall()]
        print(json.dumps({
            "ok": len(tables) == 9,
            "version": PARAMETER_CHECK_SCHEMA_VERSION,
            "tables": tables,
            "historical_assessment_count": historical_assessment_count,
        }, ensure_ascii=False))
        return 0 if len(tables) == 9 else 1
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
