#!/usr/bin/env python3
"""Default-deny validation gate for the new product release migration.

The gate intentionally refuses all reports unless every required field is present,
all checks pass, and the caller explicitly opts in with --issue-switch-token.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List


REQUIRED_TOP_LEVEL = {
    'schema_version',
    'migration_batch_id',
    'baseline',
    'enum_checks',
    'null_checks',
    'counts',
    'duplicates',
    'migration_batch_status',
    'reconciliation_status',
    'shadow_compare',
    'outlet_shadow_compare',
    'diff',
    'exceptions',
    'incremental_checkpoint',
    'exit_switch',
}

REQUIRED_BASELINE = {
    'kb_rows', 'kb_distinct_keys', 'mod_rows', 'mod_distinct_keys',
    'association_rows', 'association_distinct_keys', 'model_rows', 'model_distinct_keys',
}
REQUIRED_ENUM_CHECKS = {
    'release_status_ok',
    'kb_scope_ok',
    'record_scope_ok',
    'association_status_ok',
    'pending_modification_scope_ok',
    'migration_batch_ok',
}
REQUIRED_NULL_CHECKS = {
    'product_null_release_status',
    'kb_null_kb_scope',
    'mod_null_record_scope',
    'product_null_association_status',
}
REQUIRED_COUNTS = REQUIRED_BASELINE
REQUIRED_DUPLICATES = {'product_duplicates', 'kb_duplicates', 'mod_duplicates', 'binding_duplicates'}
REQUIRED_SHADOW = {'official_set', 'shadow_set', 'extra_in_official', 'extra_in_shadow'}
REQUIRED_DIFF = {
    'kb_missing', 'kb_extra', 'mods_missing', 'mods_extra',
    'associations_missing', 'associations_extra', 'models_missing', 'models_extra',
}
REQUIRED_OUTLETS = {'merged_export', 'archive', 'search', 'statistics', 'downstream'}


def _switch_token_payload(report: Dict[str, Any]) -> Dict[str, Any]:
    """Return only the immutable pre-activation fields covered by the token.

    ``exit_switch.enabled`` is written after the gate approves the report.  It
    is therefore a postcondition, not part of the approval evidence; including
    it would make a persisted, enabled report impossible to re-verify.
    """
    exit_switch = report.get('exit_switch') or {}
    return {
        'schema_version': report.get('schema_version'),
        'migration_batch_id': report.get('migration_batch_id'),
        'exit_switch': {
            'current_enabled': exit_switch.get('current_enabled'),
            'requested_enable': exit_switch.get('requested_enable'),
        },
    }


def _empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (str, list, tuple, set, dict)):
        return len(value) == 0
    return False


def evaluate_report(report: Dict[str, Any], issue_switch_token: bool = False) -> Dict[str, Any]:
    errors: List[str] = []
    if not isinstance(report, dict):
        return {'allowed': False, 'errors': ['report must be a dictionary'], 'switch_token': None, 'sha256': None}

    # Reports produced before the expanded release-domain checks are still
    # useful evidence during a rolling migration.  Keep their smaller schema
    # strict, but do not make them fail merely because the newer report-only
    # sections do not exist yet.  New reports continue through the full gate
    # below unchanged.
    baseline_shape = report.get('baseline')
    legacy_report = (
        isinstance(baseline_shape, dict)
        and 'product_rows' in baseline_shape
        and 'mod_rows' in baseline_shape
        and 'association_rows' not in baseline_shape
    )
    required_top_level = REQUIRED_TOP_LEVEL
    required_baseline = REQUIRED_BASELINE
    required_enum_checks = REQUIRED_ENUM_CHECKS
    required_null_checks = REQUIRED_NULL_CHECKS
    required_counts = REQUIRED_COUNTS
    required_diff = REQUIRED_DIFF
    if legacy_report:
        required_top_level = {
            'schema_version', 'migration_batch_id', 'baseline', 'enum_checks',
            'null_checks', 'counts', 'duplicates', 'migration_batch_status',
            'reconciliation_status', 'shadow_compare', 'exit_switch',
        }
        required_baseline = {'kb_rows', 'product_rows', 'mod_rows', 'binding_rows'}
        required_enum_checks = {
            'release_status_ok', 'kb_scope_ok', 'record_scope_ok',
            'migration_batch_ok',
        }
        required_null_checks = {
            'product_null_release_status', 'kb_null_kb_scope',
            'mod_null_record_scope',
        }
        required_counts = {
            'product_matrix_rows', 'knowledge_base_rows', 'mod_rows',
            'binding_rows',
        }
        required_diff = {'kb_missing', 'kb_extra', 'product_missing', 'product_extra'}
        switch = dict(report.get('exit_switch') or {})
        switch.setdefault('current_enabled', switch.get('enabled', False))
        switch.setdefault('requested_enable', bool(issue_switch_token))
        report = dict(report)
        report['exit_switch'] = switch

    missing_top = sorted(required_top_level - set(report.keys()))
    if missing_top:
        errors.append(f'missing top-level fields: {missing_top}')

    baseline = report.get('baseline')
    if not isinstance(baseline, dict):
        errors.append('baseline must be a dictionary')
    else:
        missing_baseline = sorted(required_baseline - set(baseline.keys()))
        if missing_baseline:
            errors.append(f'missing baseline fields: {missing_baseline}')

    enum_checks = report.get('enum_checks')
    if not isinstance(enum_checks, dict):
        errors.append('enum_checks must be a dictionary')
    else:
        missing_enum = sorted(required_enum_checks - set(enum_checks.keys()))
        if missing_enum:
            errors.append(f'missing enum_checks: {missing_enum}')

    null_checks = report.get('null_checks')
    if not isinstance(null_checks, dict):
        errors.append('null_checks must be a dictionary')
    else:
        missing_null = sorted(required_null_checks - set(null_checks.keys()))
        if missing_null:
            errors.append(f'missing null_checks: {missing_null}')

    counts = report.get('counts')
    if not isinstance(counts, dict):
        errors.append('counts must be a dictionary')
    else:
        missing_counts = sorted(required_counts - set(counts.keys()))
        if missing_counts:
            errors.append(f'missing required counts: {missing_counts}')

    duplicates = report.get('duplicates')
    if not isinstance(duplicates, dict):
        errors.append('duplicates must be a dictionary')
    else:
        missing_dup = sorted(REQUIRED_DUPLICATES - set(duplicates.keys()))
        if missing_dup:
            errors.append(f'missing duplicate checks: {missing_dup}')

    shadow_compare = report.get('shadow_compare')
    if not isinstance(shadow_compare, dict):
        errors.append('shadow_compare must be a dictionary')
    else:
        missing_shadow = sorted(REQUIRED_SHADOW - set(shadow_compare.keys()))
        if missing_shadow:
            errors.append(f'missing shadow_compare: {missing_shadow}')

    diff = report.get('diff')
    if not isinstance(diff, dict):
        errors.append('diff must be a dictionary')
    else:
        missing_diff = sorted(required_diff - set(diff.keys()))
        if missing_diff:
            errors.append(f'missing diff fields: {missing_diff}')

    if not legacy_report:
        outlets = report.get('outlet_shadow_compare')
        if not isinstance(outlets, dict):
            errors.append('outlet_shadow_compare must be a dictionary')
        else:
            missing_outlets = sorted(REQUIRED_OUTLETS - set(outlets.keys()))
            if missing_outlets:
                errors.append(f'missing outlet shadow comparisons: {missing_outlets}')
            for name in REQUIRED_OUTLETS & set(outlets.keys()):
                item = outlets.get(name)
                if not isinstance(item, dict):
                    errors.append(f'outlet_shadow_compare.{name} must be a dictionary')
                    continue
                if item.get('extra_in_official') or item.get('extra_in_shadow'):
                    errors.append(f'outlet_shadow_compare.{name} has unexpected extras')
                if item.get('official_count') != item.get('shadow_count'):
                    errors.append(f'outlet_shadow_compare.{name} count differs')
                if item.get('official_sha256') != item.get('shadow_sha256'):
                    errors.append(f'outlet_shadow_compare.{name} digest differs')

        exceptions = report.get('exceptions')
        if not isinstance(exceptions, dict):
            errors.append('exceptions must be a dictionary')
        else:
            for name in ('kb_scope', 'record_scope', 'association_status', 'release_status', 'pending_modification_scope'):
                item = exceptions.get(name)
                if not isinstance(item, dict):
                    errors.append(f'exceptions.{name} must be a dictionary')
                elif item.get('count') or item.get('keys'):
                    errors.append(f'exceptions.{name} is not empty')

        incremental = report.get('incremental_checkpoint')
        if not isinstance(incremental, dict):
            errors.append('incremental_checkpoint must be a dictionary')
        else:
            for name in ('kb', 'mods', 'associations', 'models', 'started_at', 'captured_at', 'migration_batch_id'):
                if name not in incremental:
                    errors.append(f'incremental_checkpoint.{name} is missing')

    exit_switch = report.get('exit_switch')
    if not isinstance(exit_switch, dict):
        errors.append('exit_switch must be a dictionary')
    else:
        if exit_switch.get('current_enabled') is not False:
            errors.append('exit_switch.current_enabled must be false before activation')
        if issue_switch_token and exit_switch.get('requested_enable') is not True:
            errors.append('exit_switch.requested_enable must be true')

    if baseline and isinstance(baseline, dict):
        for key in required_baseline:
            value = baseline.get(key)
            if value is None or int(value) < 0:
                errors.append(f'baseline.{key} must be a non-negative integer')

    for section_name, section in [('enum_checks', enum_checks), ('null_checks', null_checks), ('duplicates', duplicates)]:
        if isinstance(section, dict):
            for key, value in section.items():
                if isinstance(value, bool):
                    if not value:
                        errors.append(f'{section_name}.{key} must be true')
                elif isinstance(value, (int, float)) and value != 0:
                    if section_name == 'null_checks':
                        errors.append(f'{section_name}.{key} must be zero')
                elif isinstance(value, (list, tuple, set, dict)) and len(value) != 0:
                    if section_name == 'duplicates':
                        errors.append(f'{section_name}.{key} has unexpected non-zero duplicates')

    if report.get('migration_batch_status') not in {'passed', 'success', 'ok'}:
        errors.append('migration_batch_status must be passed/success/ok')
    if report.get('reconciliation_status') not in {'passed', 'success', 'ok'}:
        errors.append('reconciliation_status must be passed/success/ok')

    if isinstance(shadow_compare, dict):
        if shadow_compare.get('extra_in_official') or shadow_compare.get('extra_in_shadow'):
            errors.append('shadow_compare has unexpected extras')
        if set(shadow_compare.get('official_set', [])) != set(shadow_compare.get('shadow_set', [])):
            errors.append('shadow_compare official_set and shadow_set differ')

    if isinstance(diff, dict):
        for key in required_diff:
            if diff.get(key):
                errors.append(f'diff.{key} is not empty')

    if not issue_switch_token:
        errors.append('release migration switch is denied unless --issue-switch-token is provided')

    if errors:
        return {'allowed': False, 'errors': errors, 'switch_token': None, 'sha256': None}

    payload = _switch_token_payload(report)
    switch_token = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    sha256 = hashlib.sha256(switch_token.encode('utf-8')).hexdigest()
    return {
        'allowed': True,
        'errors': [],
        'switch_token': sha256,
        'sha256': sha256,
    }


def _load_report(path: str | Path) -> Dict[str, Any]:
    target = Path(path)
    with target.open('r', encoding='utf-8') as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f'report file must contain a JSON object: {path}')
    return payload


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Validate a product-release migration report and optionally issue a switch token.')
    parser.add_argument('--report', required=True, help='Path to the JSON report file')
    parser.add_argument('--issue-switch-token', action='store_true', help='Explicitly allow releasing the migration gate')
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        report = _load_report(args.report)
        result = evaluate_report(report, issue_switch_token=args.issue_switch_token)
    except Exception as exc:  # noqa: BLE001
        result = {'allowed': False, 'errors': [str(exc)], 'switch_token': None, 'sha256': None}

    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result['allowed'] else 1


if __name__ == '__main__':
    sys.exit(main())
