import unittest
from unittest.mock import patch

import server
from server import _compute_mod_changed_fields, _snapshot_mod_fields


class _Response:
    status_code = 200
    text = ''


class _TagClient:
    def __init__(self):
        self.tags = [{'id': 1, 'name': '旧标签'}, {'id': 2, 'name': '新标签'}]
        self.item_tags = [
            {'library_type': 'current', 'question_wiki_id': 'KB-TAG-ONLY', 'tag_id': 1},
        ]
        self.inserted_tables = []

    def select_all(self, table, filters=None, **kwargs):
        if table == 'kb_item_tags':
            return [dict(row) for row in self.item_tags]
        if table == 'kb_tags':
            return [dict(row) for row in self.tags]
        raise AssertionError(table)

    def delete(self, table, filters):
        assert table == 'kb_item_tags'
        self.item_tags = []
        return _Response()

    def upsert(self, table, data, on_conflict=None):
        assert table == 'kb_tags'
        return _Response()

    def insert(self, table, data):
        self.inserted_tables.append(table)
        assert table == 'kb_item_tags'
        self.item_tags.extend(dict(row) for row in data)
        return _Response()


class ModificationTagDiffTests(unittest.TestCase):
    def test_tag_change_is_detected_for_tag_storage(self):
        before = _snapshot_mod_fields({
            'question': '问题',
            'answer': '答案',
            'kb_tags': ['旧标签'],
        })
        after = _snapshot_mod_fields({
            'question': '问题',
            'answer': '答案',
            'kb_tags': ['旧标签', '新标签'],
        })

        self.assertEqual(_compute_mod_changed_fields(before, after), ['kb_tags'])

    def test_product_separator_formatting_is_not_a_change(self):
        before = _snapshot_mod_fields({
            'product_name': (
                'A20 Air,A30,A30 2.0,A30 CE,A30 CE 增强版,A30 CE 性能版,'
                'A30 CE 畅享版,A30 Combo,A30 Pro CE 悦享版,A30 Pro Steam 智享版,'
                'A30 Pro Turbo,A30 ProCE,A30 超能版,拓界 Aura,拓界 Pro,拓界 Tech,'
                '拓界Airy,拓界Noble,智净'
            ),
        })
        after = _snapshot_mod_fields({
            'product_name': (
                'A20 Air, A30, A30 2.0, A30 CE, A30 CE 增强版, A30 CE 性能版, '
                'A30 CE 畅享版, A30 Combo, A30 Pro CE 悦享版, A30 Pro Steam 智享版, '
                'A30 Pro Turbo, A30 ProCE, A30 超能版, 拓界 Aura, 拓界 Pro, 拓界 Tech, '
                '拓界Airy, 拓界Noble, 智净'
            ),
        })

        self.assertEqual(_compute_mod_changed_fields(before, after), [])

    def test_real_product_scope_change_is_recorded(self):
        before = _snapshot_mod_fields({'product_name': 'A20 Air,A30'})
        after = _snapshot_mod_fields({'product_name': 'A20 Air'})

        self.assertEqual(_compute_mod_changed_fields(before, after), ['products'])

    def test_tag_endpoint_saves_tags_without_modification_record(self):
        client = _TagClient()
        server.app.config.update(TESTING=True, LOGIN_DISABLED=True)

        with patch.object(server, 'get_supabase_client', return_value=client):
            response = server.app.test_client().put('/api/kb/item/tags', json={
                'libraryType': 'current',
                'question_wiki_id': 'KB-TAG-ONLY',
                'tagNames': ['旧标签', '新标签'],
            })

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertTrue(response.get_json()['changed'])
        self.assertEqual(client.inserted_tables, ['kb_item_tags'])

    def test_json_list_string_and_list_are_equal(self):
        before = _snapshot_mod_fields({
            'image_urls': '["https://example.com/a.jpg"]',
            'link_type': None,
        })
        after = _snapshot_mod_fields({
            'image_urls': ['https://example.com/a.jpg'],
            'link_type': '',
        })

        self.assertEqual(_compute_mod_changed_fields(before, after), [])

    def test_double_encoded_json_list_and_list_are_equal(self):
        before = _snapshot_mod_fields({
            'image_urls': '"[\\"https://example.com/a.jpg\\"]"',
        })
        after = _snapshot_mod_fields({
            'image_urls': ['https://example.com/a.jpg'],
        })

        self.assertEqual(_compute_mod_changed_fields(before, after), [])

    def test_tag_order_does_not_create_false_change(self):
        before = _snapshot_mod_fields({'kb_tags': ['标签B', '标签A']})
        after = _snapshot_mod_fields({'kb_tags': ['标签A', '标签B']})

        self.assertEqual(_compute_mod_changed_fields(before, after), [])


if __name__ == '__main__':
    unittest.main()
