import tempfile
import unittest
from pathlib import Path

from kb_v1_sync import create_import_snapshot, get_snapshot


class TestKbV1Sync(unittest.TestCase):
    def create_snapshot(self, before, after):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        base = Path(root.name)
        return create_import_snapshot(str(base / 'data.db'), str(base / 'snapshots'), before, after, 'upsert', 'tester'), base

    def test_added_updated_deleted_are_hash_based(self):
        event, _ = self.create_snapshot(
            [{'question_wiki_id': 'ICWIKI001', 'question': 'Q', 'answer': 'old'}, {'question_wiki_id': 'ICWIKI002', 'question': 'keep', 'answer': 'same'}],
            [{'question_wiki_id': 'ICWIKI001', 'question': 'Q', 'answer': 'new'}, {'question_wiki_id': 'ICWIKI003', 'question': 'add', 'answer': 'new'}],
        )
        self.assertEqual(event['added_ids'], ['ICWIKI003'])
        self.assertEqual(event['updated_ids'], ['ICWIKI001'])
        self.assertEqual(event['deleted_ids'], ['ICWIKI002'])

    def test_reimporting_same_business_content_is_not_updated(self):
        event, _ = self.create_snapshot(
            [{'question_wiki_id': 'ICWIKI001', 'question': ' Q ', 'answer': 'A', 'update_time': 'old'}],
            [{'question_wiki_id': 'ICWIKI001', 'question': 'Q', 'answer': 'A', 'update_time': 'new'}],
        )
        self.assertEqual(event['updated_ids'], [])

    def test_snapshot_artifact_is_immutable_and_readable(self):
        event, base = self.create_snapshot([], [{'question_wiki_id': 'ICWIKI001', 'question': 'Q', 'answer': 'A'}])
        snapshot = get_snapshot(str(base / 'data.db'), event['snapshot_id'])
        self.assertEqual(snapshot['snapshot_hash'], event['snapshot_hash'])
        self.assertTrue(Path(snapshot['artifact_path']).is_file())
        self.assertIn('ICWIKI001', Path(snapshot['artifact_path']).read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
