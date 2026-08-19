"""Focused regression tests for the local service security boundaries.

The repository-level conftest forces an isolated temporary SQLite database;
these tests never contact a remote service.
"""

import os
from pathlib import Path

import pytest

os.environ.setdefault('KMATRIX_ADMIN_PASSWORD', 'security-test-password')

import server  # noqa: E402


def _logged_in_client():
    server.app.config.update(TESTING=True)
    server.init_db()
    client = server.app.test_client()
    response = client.post('/login', json={
        'username': 'admin',
        'password': os.environ['KMATRIX_ADMIN_PASSWORD'],
    })
    assert response.status_code == 200
    return client


def test_proxy_requires_login_before_fetching_target():
    server.app.config.update(TESTING=True, LOGIN_DISABLED=False)
    response = server.app.test_client().get('/api/proxy_image?url=http://127.0.0.1:8085/private')
    assert response.status_code == 401


def test_proxy_rejects_loopback_after_login():
    client = _logged_in_client()
    response = client.get('/api/proxy_image?url=http://127.0.0.1:8085/private')
    assert response.status_code == 400
    assert '禁止' in response.get_json()['message']


def test_proxy_rejects_non_global_shared_address(monkeypatch):
    monkeypatch.setattr(server.socket, 'getaddrinfo', lambda *args, **kwargs: [
        (server.socket.AF_INET, server.socket.SOCK_STREAM, 6, '', ('100.64.0.1', 80)),
    ])
    url, addresses, error = server._resolve_proxy_target('http://shared.example/image.png')
    assert url is None
    assert addresses == []
    assert '禁止' in error


def test_proxy_https_connection_is_pinned_to_validated_ip(monkeypatch):
    captured = {}

    class FakeRaw:
        status = 200
        headers = {'Content-Type': 'image/png'}

        def close(self):
            pass

    class FakePool:
        def __init__(self, **kwargs):
            captured['pool'] = kwargs

        def urlopen(self, method, path, **kwargs):
            captured['method'] = method
            captured['path'] = path
            captured['request'] = kwargs
            return FakeRaw()

        def close(self):
            captured['closed'] = True

    monkeypatch.setattr(server.urllib3, 'HTTPSConnectionPool', FakePool)
    response = server._open_pinned_proxy_response(
        'https://media.example.com:8443/image.png?size=large',
        ['203.0.113.10'],
        {'Range': 'bytes=0-99'},
    )
    assert response.status_code == 200
    assert captured['pool']['host'] == '203.0.113.10'
    assert captured['pool']['server_hostname'] == 'media.example.com'
    assert captured['pool']['assert_hostname'] == 'media.example.com'
    assert captured['request']['headers']['Host'] == 'media.example.com:8443'
    assert captured['request']['headers']['Range'] == 'bytes=0-99'
    assert captured['path'] == '/image.png?size=large'
    server._close_pinned_proxy_response(response)
    assert captured['closed'] is True


def test_llm_config_metadata_does_not_contain_key_fragments():
    payload = server._llm_config_meta('sk-super-secret-value', 'https://example.invalid', 'model')
    assert 'api_key' not in payload
    assert 'prefix' not in payload
    assert 'suffix' not in payload
    assert payload['api_key_configured'] is True


def test_llm_config_get_redacts_api_key(monkeypatch):
    client = _logged_in_client()
    monkeypatch.setattr(server, 'load_scoring_config', lambda: {
        'api_key': 'sk-super-secret-value',
        'base_url': 'https://example.invalid',
        'model': 'model',
    })
    response = client.get('/api/scoring/config')
    assert response.status_code == 200
    body = response.get_json()
    assert 'api_key' not in body
    assert 'sk-super-secret-value' not in response.get_data(as_text=True)
    assert body['api_key_configured'] is True


def test_empty_key_from_legacy_client_preserves_stored_secret(monkeypatch):
    client = _logged_in_client()
    state = {
        'api_key': 'sk-super-secret-value',
        'base_url': 'https://example.invalid',
        'model': 'old-model',
    }

    monkeypatch.setattr(server, 'load_scoring_config', lambda: dict(state))

    def save_config(value):
        state.clear()
        state.update(value)
        return True

    monkeypatch.setattr(server, 'save_scoring_config', save_config)
    response = client.post('/api/scoring/config', json={
        'api_key': '',
        'model': 'new-model',
    })
    assert response.status_code == 200
    assert state['api_key'] == 'sk-super-secret-value'
    assert state['model'] == 'new-model'
    assert 'sk-super-secret-value' not in response.get_data(as_text=True)


def test_connection_test_uses_stored_key_when_browser_omits_it(monkeypatch):
    client = _logged_in_client()
    captured = {}

    class FakeScorer:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def _chat_completions(self, **kwargs):
            return 'OK'

    monkeypatch.setattr(server, 'load_scoring_config', lambda: {
        'api_key': 'sk-stored-secret',
        'base_url': 'https://example.invalid',
        'model': 'stored-model',
    })
    monkeypatch.setattr(server, 'LLMScorer', FakeScorer)
    response = client.post('/api/scoring/test_config', json={
        'base_url': 'https://example.invalid',
        'model': 'stored-model',
    })
    assert response.status_code == 200
    assert response.get_json()['success'] is True
    assert captured['api_key'] == 'sk-stored-secret'
    assert 'sk-stored-secret' not in response.get_data(as_text=True)


def test_secret_key_is_not_historical_default():
    assert server.app.config['SECRET_KEY'] != 'dev-only-change-me'
    assert len(str(server.app.config['SECRET_KEY'])) >= 32


def test_link_payload_rejects_script_protocol_and_normalizes_tags():
    with pytest.raises(ValueError, match='HTTP/HTTPS'):
        server._normalize_link_preview_payload({
            'id': 'link-1',
            'url': 'javascript:alert(1)',
            'tags': [],
            'createdAt': '2026-08-14T00:00:00',
        })

    payload = server._normalize_link_preview_payload({
        'id': 'link-1',
        'kb_id': "KB-'quoted'",
        'url': 'https://example.com/image.png',
        'tags': ['manual', 'manual', '<b>tag</b>'],
        'createdAt': '2026-08-14T00:00:00',
    })
    assert payload['type'] == 'image'
    assert payload['tags'] == ['manual', '<b>tag</b>']


def test_frontend_does_not_interpolate_persisted_link_fields_into_event_html():
    source = (Path(server._BASE_DIR) / 'link_viewer' / 'app_v8.js').read_text(encoding='utf-8')
    assert "el.innerHTML = `${t}" not in source
    assert "onclick=\"searchKBById('${oneId}')\"" not in source
    assert 'href="${item.url}"' not in source


def test_frontend_connection_test_omits_blank_key_and_explains_stored_key():
    source = (Path(server._BASE_DIR) / 'link_viewer' / 'app_v8.js').read_text(encoding='utf-8')
    assert "if (apiKey) payload.api_key = apiKey;" in source
    assert "apiKeyInput.dataset.storedKeyConfigured" in source
    assert "使用已保存密钥" in source
