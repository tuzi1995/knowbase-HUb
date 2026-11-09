"""Mapping order round trips use temporary config files, never live mappings."""
import io
import json

import pandas as pd
import pytest

import server


@pytest.fixture
def mapping_api(tmp_path, monkeypatch):
    path = tmp_path / 'model_mappings.json'
    path.write_text(json.dumps({'A系列': ['A10'], 'Z系列': ['A20']}), encoding='utf-8')
    monkeypatch.setattr(server, 'MODEL_MAPPINGS_FILE', str(path))
    monkeypatch.setattr(server, 'MODEL_MAPPINGS_BACKUP_DIR', str(tmp_path / 'history'))
    monkeypatch.setattr(server, 'parse_product_catalog', lambda: {'产品': ['A10', 'A20']})
    monkeypatch.setitem(server.app.config, 'LOGIN_DISABLED', True)
    with server.app.test_client() as client:
        yield client, path


def save_mappings(client, mappings, category_order=None, expected_revision=None):
    current = client.get('/api/model_mappings?include_order=1').get_json()
    if expected_revision is None:
        expected_revision = current['revision']
    if category_order is None:
        category_order = current['category_order']
    return client.post('/api/model_mappings', json={
        'mappings': mappings,
        'category_order': category_order or list(mappings),
        'expected_revision': expected_revision,
    })


def test_manual_order_survives_reload_and_subsequent_save(mapping_api):
    client, path = mapping_api
    response = save_mappings(client, {'A系列': ['A10'], 'Z系列': ['A20']}, ['Z系列', 'A系列'])
    assert response.status_code == 200
    assert response.get_json()['backup_created']
    assert response.get_json()['category_order'] == ['Z系列', 'A系列']
    assert json.loads(path.with_name(path.name + '.order.json').read_text()) == ['Z系列', 'A系列']
    assert list(json.loads(path.read_text(encoding='utf-8'))) == ['Z系列', 'A系列']
    loaded = client.get('/api/model_mappings?include_order=1').get_json()
    assert loaded['category_order'] == ['Z系列', 'A系列']
    assert loaded['mappings'] == client.get('/api/model_mappings').get_json()
    assert list(server.get_model_mappings()) == ['Z系列', 'A系列']
    assert save_mappings(client, {'A系列': ['A10'], 'Z系列': ['A20']}).status_code == 200
    assert client.get('/api/model_mappings?include_order=1').get_json()['category_order'] == ['Z系列', 'A系列']


def test_order_defaults_deduplicates_and_ignores_deleted_categories(mapping_api):
    client, path = mapping_api
    assert client.get('/api/model_mappings?include_order=1').get_json()['category_order'] == ['A系列', 'Z系列']
    order_path = path.with_name(path.name + '.order.json')
    order_path.write_text(json.dumps(['Z系列', '已删除', 'Z系列', 123]))
    assert server.get_model_mapping_category_order({'A系列': [], 'Z系列': [], 'B系列': []}) == ['Z系列', 'A系列', 'B系列']
    order_path.write_text('invalid json')
    assert server.get_model_mapping_category_order({'Z系列': [], 'A系列': []}) == ['Z系列', 'A系列']


def test_mapping_file_key_order_survives_without_sidecar(mapping_api):
    client, path = mapping_api
    payload = {'mappings': {'A系列': ['A10'], 'Z系列': ['A20']}, 'category_order': ['Z系列', 'A系列']}
    assert save_mappings(client, payload['mappings'], payload['category_order']).status_code == 200
    path.with_name(path.name + '.order.json').unlink()
    assert server.get_model_mapping_category_order(server.get_model_mappings()) == ['Z系列', 'A系列']


def test_rename_delete_and_append_persist(mapping_api):
    client, _ = mapping_api
    payload = {'mappings': {'新名称': ['A20'], '新增': ['A10']}, 'category_order': ['新名称', '新增']}
    assert save_mappings(client, payload['mappings'], payload['category_order']).status_code == 200
    loaded = client.get('/api/model_mappings?include_order=1').get_json()
    assert loaded['mappings'] == payload['mappings']
    assert loaded['category_order'] == payload['category_order']


def test_invalid_order_and_empty_write_do_not_overwrite(mapping_api):
    client, path = mapping_api
    original = path.read_bytes()
    revision = client.get('/api/model_mappings?include_order=1').get_json()['revision']
    for order in [None, 'A系列', [123]]:
        response = client.post('/api/model_mappings', json={
            'mappings': {'A系列': ['A10']}, 'category_order': order, 'expected_revision': revision,
        })
        assert response.status_code == 400
    assert client.post('/api/model_mappings', json={
        'mappings': {}, 'category_order': [], 'expected_revision': revision,
    }).status_code == 409
    assert path.read_bytes() == original


def test_stale_revision_cannot_replace_full_mapping_with_four_categories(mapping_api):
    client, path = mapping_api
    stale_revision = client.get('/api/model_mappings?include_order=1').get_json()['revision']
    assert save_mappings(client, {'A系列': ['A10'], 'Z系列': ['A20']}).status_code == 200
    current_bytes = path.read_bytes()

    response = save_mappings(client, {
        '所有型号': ['T7 Pro'],
        '所有联网设备': ['T7 Pro'],
        '所有扫地机': ['T7 Pro'],
        '震动系列': ['T7 Pro'],
    }, expected_revision=stale_revision)

    assert response.status_code == 409
    assert response.get_json()['code'] == 'mapping_revision_conflict'
    assert path.read_bytes() == current_bytes


def test_large_mapping_reduction_requires_explicit_confirmation(mapping_api):
    client, path = mapping_api
    path.write_text(json.dumps({f'分类{i}': ['A10', 'A20'] for i in range(10)}), encoding='utf-8')
    revision = client.get('/api/model_mappings?include_order=1').get_json()['revision']
    original = path.read_bytes()

    payload = {
        'mappings': {'A系列': ['A10']},
        'category_order': ['A系列'],
        'expected_revision': revision,
    }
    response = client.post('/api/model_mappings', json=payload)
    assert response.status_code == 409
    assert response.get_json()['code'] == 'mapping_large_change_confirmation_required'
    assert response.get_json()['before'] == {'categories': 10, 'associations': 20}
    assert path.read_bytes() == original

    payload['confirm_large_change'] = True
    response = client.post('/api/model_mappings', json=payload)
    assert response.status_code == 200
    assert json.loads(path.read_text()) == {'A系列': ['A10']}


def test_mapping_write_requires_revision(mapping_api):
    client, path = mapping_api
    original = path.read_bytes()
    response = client.post('/api/model_mappings', json={
        'mappings': {'A系列': ['A10']},
        'category_order': ['A系列'],
    })
    assert response.status_code == 428
    assert response.get_json()['code'] == 'mapping_revision_required'
    assert path.read_bytes() == original


def test_export_uses_unsaved_order_and_tags_use_saved_order(mapping_api):
    client, _ = mapping_api
    mappings = {'A系列': ['A10'], 'Z系列': ['A10']}
    payload = {'mappings': mappings, 'category_order': ['Z系列', 'A系列']}
    exported = client.post('/api/model_mappings/export_excel', json=payload)
    assert exported.status_code == 200
    assert pd.read_excel(io.BytesIO(exported.data))['分类'].tolist() == ['Z系列', 'A系列']
    assert save_mappings(client, payload['mappings'], payload['category_order']).status_code == 200
    assert server._mapping_categories_for_product_value('A10') == ['Z系列', 'A系列']
    exported = client.post('/api/model_mappings/export_excel', json=mappings)
    assert pd.read_excel(io.BytesIO(exported.data))['分类'].tolist() == ['Z系列', 'A系列']
