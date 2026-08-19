import unittest
from unittest.mock import patch

import server


class ReferenceClient:
    def __init__(self, rows):
        self.rows = [dict(row) for row in rows]

    def select_all(self, _table, filters=None, **_kwargs):
        if not filters:
            return [dict(row) for row in self.rows]
        raw = str(filters.get('question_wiki_id') or '')
        ids = {part.strip().strip('"') for part in raw[4:-1].split(',')} if raw.startswith('in.(') else set()
        return [dict(row) for row in self.rows if row.get('question_wiki_id') in ids]


class KBReferenceCandidatesTests(unittest.TestCase):
    def setUp(self):
        server.app.config.update(TESTING=True, LOGIN_DISABLED=True)
        self.rows = [
            {
                'question_wiki_id': 'KB-LIGHT',
                'question': '充电完成后状态指示灯是什么状态？',
                'answer': '设备充满电后，状态指示灯会显示充电完成状态。',
                'product_name': 'S8 Pro',
                'product_category_name': '扫地机',
                'update_time': '2026-08-05T10:00:00+08:00',
            },
            {
                'question_wiki_id': 'KB-OTHER',
                'question': '如何清洗尘盒？',
                'answer': '请取出尘盒后清洁。',
                'product_name': 'S8 Pro',
                'product_category_name': '扫地机',
                'update_time': '2026-08-05T10:00:00+08:00',
            },
        ]

    def test_candidate_prefers_matching_content_and_product(self):
        candidate = server._kb_reference_candidate(
            {'question': '充满电没有语音提示，怎么判断？', 'answer': '请查看状态指示灯。'},
            self.rows[0],
            {'S8 Pro'},
            {'扫地机'},
        )

        self.assertIsNotNone(candidate)
        self.assertGreater(candidate['score'], 8)
        self.assertIn('适用型号一致', candidate['reason'])

    @patch.object(server, 'get_supabase_client')
    def test_api_returns_candidates_without_rendering_source_id_as_display_text(self, get_client):
        get_client.return_value = ReferenceClient(self.rows)

        response = server.app.test_client().post('/api/kb/reference-candidates', json={
            'question': '充满电没有语音提示，怎么判断？',
            'answer': '请查看状态指示灯。',
            'product_name': 'S8 Pro',
            'product_category_name': '扫地机',
        })

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['candidates'][0]['wiki_id'], 'KB-LIGHT')
        self.assertEqual(payload['candidates'][0]['question'], '充电完成后状态指示灯是什么状态？')

    def test_confirmed_references_are_rebuilt_from_database_snapshots(self):
        references = server._kb_confirmed_references(
            ReferenceClient(self.rows),
            [{'wiki_id': 'KB-LIGHT'}],
        )

        self.assertEqual(len(references), 1)
        self.assertEqual(references[0]['wiki_id'], 'KB-LIGHT')
        self.assertTrue(references[0]['source_content_hash'])
        self.assertIn('状态指示灯', references[0]['answer_excerpt'])


if __name__ == '__main__':
    unittest.main()
