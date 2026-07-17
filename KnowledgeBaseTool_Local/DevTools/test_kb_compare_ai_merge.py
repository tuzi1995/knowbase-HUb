import json
import unittest
from unittest.mock import patch

import server


class TestKBCompareAIMerge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.app.config.update(TESTING=True, LOGIN_DISABLED=True)

    def setUp(self):
        self.client = server.app.test_client()
        self.records = [
            {
                'question_wiki_id': 'ICWIKI001',
                'question': '怎么设置定时清洁？',
                'answer': '打开 App 后进入定时任务。',
                'similar_questions': '如何预约清扫？',
                'product_name': 'G20S',
            },
            {
                'question_wiki_id': 'ICWIKI002',
                'question': '如何预约定时清扫？',
                'answer': '在 App 的定时任务中新增计划。',
                'similar_questions': ['每天定时清洁怎么开？'],
                'product_name': 'G20S',
            },
        ]

    @patch.object(server, 'load_ai_config', return_value={'api_key': 'test', 'base_url': 'http://llm', 'model': 'test'})
    @patch.object(server, '_ai_call_llm')
    def test_recommended_merge_returns_only_ai_content_fields(self, call_llm, _config):
        call_llm.return_value = json.dumps({
            'recommend_merge': True,
            'confidence': 0.86,
            'reason': '两条记录都是设置定时清洁。',
            'conflicts': [],
            'question': '如何设置定时清洁？',
            'answer': '在 App 的定时任务中新增清洁计划。',
            'similar_questions': ['怎么预约清扫？'],
        }, ensure_ascii=False)

        response = self.client.post('/api/kb/compare/ai_merge', json={
            'base_id': 'ICWIKI001',
            'records': self.records,
        })

        self.assertEqual(response.status_code, 200)
        data = response.get_json()['data']
        self.assertTrue(data['recommend_merge'])
        self.assertEqual(data['question'], '如何设置定时清洁？')
        self.assertEqual(data['similar_questions'], ['怎么预约清扫？'])
        self.assertEqual(data['source_ids'], ['ICWIKI001', 'ICWIKI002'])

    @patch.object(server, 'load_ai_config', return_value={'api_key': 'test', 'base_url': 'http://llm', 'model': 'test'})
    @patch.object(server, '_ai_call_llm')
    def test_not_recommended_does_not_return_generated_content(self, call_llm, _config):
        call_llm.return_value = json.dumps({
            'recommend_merge': False,
            'confidence': 0.91,
            'reason': '两条记录的操作目标不同。',
            'conflicts': ['一个是定时清洁，一个是清洁顺序'],
            'question': '不应写入',
            'answer': '不应写入',
            'similar_questions': ['不应写入'],
        }, ensure_ascii=False)

        response = self.client.post('/api/kb/compare/ai_merge', json={'records': self.records})

        self.assertEqual(response.status_code, 200)
        data = response.get_json()['data']
        self.assertFalse(data['recommend_merge'])
        self.assertEqual(data['question'], '')
        self.assertEqual(data['answer'], '')
        self.assertEqual(data['similar_questions'], [])
        self.assertEqual(data['conflicts'], ['一个是定时清洁，一个是清洁顺序'])

    def test_requires_two_valid_records(self):
        response = self.client.post('/api/kb/compare/ai_merge', json={'records': self.records[:1]})
        self.assertEqual(response.status_code, 400)
        self.assertIn('至少需要 2 条', response.get_json()['message'])


if __name__ == '__main__':
    unittest.main()
