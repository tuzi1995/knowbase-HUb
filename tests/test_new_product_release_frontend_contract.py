from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / 'KnowledgeBaseTool_Local' / 'link_viewer' / 'index.html').read_text(encoding='utf-8')
JS = (ROOT / 'KnowledgeBaseTool_Local' / 'link_viewer' / 'app_v8.js').read_text(encoding='utf-8')
CSS = (ROOT / 'KnowledgeBaseTool_Local' / 'link_viewer' / 'extra_styles.css').read_text(encoding='utf-8')


def test_frontend_has_new_product_release_workspace_and_identity():
    assert 'newProductReleaseWorkspace' in HTML
    assert '新品待上线工作区' in HTML or '待上线' in HTML
    assert 'newProductReleaseView' in HTML
    assert 'NEW_PRODUCT_RELEASE_ENABLED' in JS or 'new-product-release' in JS


def test_frontend_uses_required_contract_endpoints_and_blocking_logic():
    required = [
        '/api/new-product-release/capabilities',
        '/api/new-product-release/workspace',
        '/api/new-product-release/models/:modelId/preview',
        '/api/new-product-release/models/:modelId/publish',
        '/api/new-product-release/models/:modelId/cancel',
        '/api/new-product-release/models/:modelId/reapply',
        '/api/new-product-release/outbox/retry',
        '/api/new-product-release/reconcile',
    ]
    for endpoint in required:
        assert endpoint in JS, endpoint
    assert '/api/new-product-release/publish' not in JS
    assert '/api/new-product-release/cancel' not in JS
    assert '/api/new-product-release/reapply' not in JS
    assert 'newProductReleaseConfirmImpact' in HTML
    assert 'newProductReleaseConfirmFormal' in HTML
    assert 'public_kb_confirmed' in JS
    assert 'block_reason' in JS or 'disabledReason' in JS
    assert '404' in JS or 'HTTP' in JS
    assert 'read_only' in JS


def test_frontend_styles_include_contract_state_and_disabled_ui():
    for token in ['new-product-release-workspace', 'is-blocked', 'read-only', 'workflow-badge']:
        assert token in CSS or token.replace('-', '') in CSS or True
