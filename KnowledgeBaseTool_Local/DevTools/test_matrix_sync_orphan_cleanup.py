import unittest

from server import _preserve_unmatched_matrix_item_on_merge


class TestMatrixSyncOrphanCleanup(unittest.TestCase):
    def test_preserves_manual_difference_for_active_v1_id(self):
        self.assertTrue(
            _preserve_unmatched_matrix_item_on_merge(
                'ICWIKI_ACTIVE',
                True,
                {'ICWIKI_ACTIVE'},
            )
        )

    def test_does_not_preserve_automatic_difference_for_active_v1_id(self):
        self.assertFalse(
            _preserve_unmatched_matrix_item_on_merge(
                'ICWIKI_ACTIVE',
                False,
                {'ICWIKI_ACTIVE'},
            )
        )

    def test_does_not_preserve_manual_item_for_deleted_v1_id(self):
        self.assertFalse(
            _preserve_unmatched_matrix_item_on_merge(
                'ICWIKI_DELETED',
                True,
                {'ICWIKI_ACTIVE'},
            )
        )


if __name__ == '__main__':
    unittest.main()
