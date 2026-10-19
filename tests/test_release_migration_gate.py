import json
import subprocess
import sys
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / 'KnowledgeBaseTool_Local' / 'release_migration_gate.py'
SPEC = importlib.util.spec_from_file_location('release_migration_gate', MODULE_PATH)
release_migration_gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_migration_gate)


def make_report(**overrides):
    report = {
        'schema_version': '2026.09.21.new_product_release',
        'migration_batch_id': 'mb-20260921-001',
        'baseline': {
            'kb_rows': 2,
            'product_rows': 2,
            'mod_rows': 2,
            'binding_rows': 2,
        },
        'enum_checks': {
            'release_status_ok': True,
            'kb_scope_ok': True,
            'record_scope_ok': True,
            'migration_batch_ok': True,
        },
        'null_checks': {
            'product_null_release_status': 0,
            'kb_null_kb_scope': 0,
            'mod_null_record_scope': 0,
        },
        'counts': {
            'product_matrix_rows': 2,
            'knowledge_base_rows': 2,
            'mod_rows': 2,
            'binding_rows': 2,
        },
        'duplicates': {
            'product_duplicates': 0,
            'kb_duplicates': 0,
            'mod_duplicates': 0,
            'binding_duplicates': 0,
        },
        'migration_batch_status': 'passed',
        'reconciliation_status': 'passed',
        'shadow_compare': {
            'official_set': ['A', 'B'],
            'shadow_set': ['A', 'B'],
            'extra_in_official': [],
            'extra_in_shadow': [],
        },
        'diff': {
            'kb_missing': [],
            'kb_extra': [],
            'product_missing': [],
            'product_extra': [],
        },
        'exit_switch': {'enabled': False},
    }
    report.update(overrides)
    return report


def test_default_deny_blocks_untrusted_report():
    result = release_migration_gate.evaluate_report({})
    assert result['allowed'] is False
    assert result['errors']


def test_missing_required_baseline_blocks_report():
    report = make_report(baseline={'kb_rows': 2, 'product_rows': 2, 'mod_rows': 2})
    result = release_migration_gate.evaluate_report(report)
    assert result['allowed'] is False
    assert any('binding_rows' in str(error) for error in result['errors'])


def test_diff_and_shadow_mismatch_block_report():
    report = make_report(diff={'kb_missing': ['KB-9']}, shadow_compare={'official_set': ['A'], 'shadow_set': ['B'], 'extra_in_official': [], 'extra_in_shadow': []})
    result = release_migration_gate.evaluate_report(report)
    assert result['allowed'] is False
    assert any('diff' in str(error).lower() or 'shadow' in str(error).lower() for error in result['errors'])


def test_full_pass_issues_switch_token():
    report = make_report()
    result = release_migration_gate.evaluate_report(report, issue_switch_token=True)
    assert result['allowed'] is True
    assert 'switch_token' in result
    assert 'sha256' in result


def test_cli_accepts_report_file_and_issues_token(tmp_path):
    report_path = tmp_path / 'report.json'
    report_path.write_text(json.dumps(make_report()), encoding='utf-8')
    completed = subprocess.run(
        [
            sys.executable,
            str(MODULE_PATH),
            '--report',
            str(report_path),
            '--issue-switch-token',
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload['allowed'] is True
    assert 'switch_token' in payload
    assert 'sha256' in payload
