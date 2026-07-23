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
            'answer': '在 App 的定时任务中新增清洁计划，设置后会每天到点自动打扫。',
            'similar_questions': [
                '如何设置定时清洁？',
                '定时清洁如何设置？',
                '每天到点自动打扫要在哪里开启？',
            ],
            'coverage_checks': [
                {
                    'question': '如何设置定时清洁？',
                    'answerable': True,
                    'evidence': '在 App 的定时任务中新增清洁计划',
                },
                {
                    'question': '每天到点自动打扫要在哪里开启？',
                    'answerable': True,
                    'evidence': '在 App 的定时任务中新增清洁计划',
                },
            ],
        }, ensure_ascii=False)

        response = self.client.post('/api/kb/compare/ai_merge', json={
            'base_id': 'ICWIKI001',
            'records': self.records,
        })

        self.assertEqual(response.status_code, 200)
        data = response.get_json()['data']
        self.assertTrue(data['recommend_merge'])
        self.assertEqual(data['question'], '如何设置定时清洁？')
        self.assertEqual(data['similar_questions'], ['每天到点自动打扫要在哪里开启？'])
        self.assertEqual(len(data['coverage_checks']), 2)
        self.assertEqual(data['source_ids'], ['ICWIKI001', 'ICWIKI002'])
        system_prompt = call_llm.call_args.args[1]
        self.assertIn('用于语义召回', system_prompt)
        self.assertIn('与 question 明显不同', system_prompt)
        self.assertIn('召回不要求文本完全一致', system_prompt)
        self.assertIn('不得添加或保留产品型号', system_prompt)
        self.assertIn('拆成多个单一问题', system_prompt)
        self.assertIn('coverage_checks', system_prompt)

    def test_similar_question_comparison_keeps_distinct_answer_applicable_phrasing(self):
        self.assertTrue(server._kb_compare_questions_too_similar('如何申请退款？', '退款如何申请？'))
        self.assertTrue(server._kb_compare_questions_too_similar('如何申请退款？', '怎么申请退款？'))
        self.assertFalse(server._kb_compare_questions_too_similar(
            '如何申请退款？',
            '购买后不想要了应该怎么处理？',
        ))

    def test_product_scope_is_removed_except_for_comparison_questions(self):
        records = [{
            'product_name': 'G10',
            'product_category_name': '扫地机器人',
        }]
        self.assertEqual(
            server._kb_compare_unneeded_product_terms('G10主机重量是多少？', records),
            ['G10'],
        )
        self.assertEqual(
            server._kb_compare_unneeded_product_terms('扫地机器人如何设置定时清洁？', records),
            ['扫地机器人'],
        )
        self.assertEqual(
            server._kb_compare_unneeded_product_terms('G10 和 G20 有什么区别？', records),
            [],
        )

    @patch.object(server, 'load_ai_config', return_value={'api_key': 'test', 'base_url': 'http://llm', 'model': 'test'})
    @patch.object(server, '_ai_call_llm')
    def test_rejects_coverage_evidence_not_found_in_answer(self, call_llm, _config):
        call_llm.return_value = json.dumps({
            'recommend_merge': True,
            'confidence': 0.86,
            'reason': '两条记录都是设置定时清洁。',
            'conflicts': [],
            'question': '如何设置定时清洁？',
            'answer': '在 App 的定时任务中新增清洁计划。',
            'similar_questions': ['每天到点自动打扫要在哪里开启？'],
            'coverage_checks': [
                {
                    'question': '如何设置定时清洁？',
                    'answerable': True,
                    'evidence': '在 App 的定时任务中新增清洁计划',
                },
                {
                    'question': '每天到点自动打扫要在哪里开启？',
                    'answerable': True,
                    'evidence': '每天到点自动执行',
                },
            ],
        }, ensure_ascii=False)

        response = self.client.post('/api/kb/compare/ai_merge', json={'records': self.records})

        self.assertEqual(response.status_code, 500)
        self.assertEqual(call_llm.call_count, 3)
        self.assertIn('未通过校验', response.get_json()['message'])

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
