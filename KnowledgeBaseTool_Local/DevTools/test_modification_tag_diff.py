import unittest

from server import _compute_mod_changed_fields, _snapshot_mod_fields


class ModificationTagDiffTests(unittest.TestCase):
    def test_tag_only_edit_is_recorded(self):
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
