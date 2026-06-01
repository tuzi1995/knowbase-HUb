import unittest

from matrix_submit_validation import validate_submit_changes


class TestValidateSubmitChanges(unittest.TestCase):
    def test_empty(self):
        normalized, errors = validate_submit_changes([])
        self.assertEqual(normalized, [])
        self.assertTrue(errors)

    def test_valid(self):
        normalized, errors = validate_submit_changes([
            {
                "question_wiki_id": "1",
                "product_name": "A",
                "old_is_configured": False,
                "new_is_configured": True,
                "edit_source": "cell",
            }
        ])
        self.assertEqual(errors, [])
        self.assertEqual(len(normalized), 1)

    def test_duplicate(self):
        normalized, errors = validate_submit_changes([
            {
                "question_wiki_id": "1",
                "product_name": "A",
                "old_is_configured": False,
                "new_is_configured": True,
            },
            {
                "question_wiki_id": "1",
                "product_name": "A",
                "old_is_configured": True,
                "new_is_configured": False,
            },
        ])
        self.assertTrue(any("重复" in e for e in errors))

    def test_no_diff(self):
        normalized, errors = validate_submit_changes([
            {
                "question_wiki_id": "1",
                "product_name": "A",
                "old_is_configured": True,
                "new_is_configured": True,
            }
        ])
        self.assertTrue(any("无差异" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
