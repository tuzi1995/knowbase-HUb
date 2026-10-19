from types import SimpleNamespace

import pytest

import server
from product_categories import ProductCategoryResolver, category_is_blank


CATALOG = {'扫地机': ['G20S', 'P10S Pro 系列'], '洗地机': ['A30'], '洗衣机': ['Q1']}


@pytest.mark.parametrize('products,expected', [
    (' g 20s ', '扫地机'),
    ('p10s pro', '扫地机'),
    ('P10S PRO series', '扫地机'),
    ('Q1，A30\nG20S', '扫地机,洗地机,洗衣机'),
    ('["Q1", "A30"]', '洗地机,洗衣机'),
    (['Q1', 'A30'], '洗地机,洗衣机'),
    ('G20S Ultra', ''),
    (None, ''),
])
def test_resolver_uses_catalog_not_prefixes(products, expected):
    assert ProductCategoryResolver(CATALOG).resolve(products) == expected


@pytest.mark.parametrize('value', [None, '', ' ', 'nan', 'NULL', 'None', float('nan')])
def test_blank_values(value):
    assert category_is_blank(value)
    assert ProductCategoryResolver(CATALOG).resolve('Q1', value) == '洗衣机'


def test_existing_category_is_preserved():
    assert ProductCategoryResolver(CATALOG).resolve('Q1', '手动分类') == '手动分类'


def test_sync_backfill_is_versioned_and_refreshes_full_row(monkeypatch):
    monkeypatch.setattr(server, 'parse_product_catalog', lambda: CATALOG)
    row = {'question_wiki_id': 'KB-1', 'product_name': 'Q1',
           'product_category_name': None, 'content_version': 7, 'answer': 'old'}
    writes = []

    class Client:
        def update(self, table, payload, filters):
            writes.append((table, payload, filters))
            return SimpleNamespace(status_code=200)

        def select_all(self, table, **kwargs):
            assert kwargs['use_formal'] is False
            assert kwargs['columns'] == '*'
            return [dict(row, product_category_name='洗衣机', content_version=8, answer='latest')]

    assert server._backfill_kb_categories_for_sync(Client(), [row]) == 1
    assert writes[0][1] == {'product_category_name': '洗衣机', 'content_version': 8}
    assert writes[0][2]['content_version'] == 'eq.7'
    assert writes[0][2]['product_category_name'] == 'is.null'
    assert row['answer'] == 'latest'
    assert server._backfill_kb_categories_for_sync(Client(), [row]) == 0


def test_sync_backfill_detects_concurrent_empty_category(monkeypatch):
    monkeypatch.setattr(server, 'parse_product_catalog', lambda: CATALOG)
    row = {'question_wiki_id': 'KB-1', 'product_name': 'Q1', 'product_category_name': ''}
    client = SimpleNamespace(update=lambda *args: SimpleNamespace(status_code=200),
                             select_all=lambda *args, **kwargs: [dict(row)])
    with pytest.raises(RuntimeError, match='并发修改'):
        server._backfill_kb_categories_for_sync(client, [row])


def test_local_matrix_projection_fills_blank_category(monkeypatch):
    monkeypatch.setattr(server, 'parse_product_catalog', lambda: CATALOG)
    with server.app.app_context():
        server.init_db()
        rows = [{'question_wiki_id': 'KB-CAT', 'product_name': 'Q1,A30', 'product_category_name': ''}]
        assert server._rebuild_local_matrix_from_v1(rows) == 2
        assert {r.product_category for r in server.ProductMatrix.query.all()} == {'洗地机,洗衣机'}
        server.ProductMatrix.query.delete()
        server.db.session.commit()


def test_atomic_edit_fills_category_without_overwriting_existing(monkeypatch):
    monkeypatch.setattr(server, 'parse_product_catalog', lambda: CATALOG)
    row = {'question_wiki_id': 'KB-1', 'product_name': 'Q1', 'product_category_name': '', 'content_version': 2}

    class Client:
        def select_all(self, *args, **kwargs):
            return [dict(row)]

        def update(self, table, payload, filters):
            row.update(payload)
            return SimpleNamespace(status_code=200)

    assert server._atomic_update_kb_current(Client(), 'KB-1', {'answer': 'new'})['ok']
    assert row['product_category_name'] == '洗衣机'
    row['product_category_name'] = '手动分类'
    assert server._atomic_update_kb_current(Client(), 'KB-1', {'answer': 'next'})['ok']
    assert row['product_category_name'] == '手动分类'
