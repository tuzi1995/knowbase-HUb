import unittest
from unittest.mock import Mock, patch

import server


class SmartMappingEmbeddingTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            'api_url': 'https://example.test/v1/embeddings',
            'api_key': 'test-key',
            'api_key_source': 'custom',
            'model': 'test-embedding',
            'dimensions': 3,
            'threshold': 0.75,
            'batch_size': 64,
            'timeout': 10,
            'fallback_to_ngram': True,
        }

    @patch.object(server.requests, 'post')
    def test_embedding_request_orders_and_validates_vectors(self, post):
        response = Mock(status_code=200)
        response.json.return_value = {
            'data': [
                {'index': 1, 'embedding': [0.0, 1.0, 0.0]},
                {'index': 0, 'embedding': [1.0, 0.0, 0.0]},
            ]
        }
        post.return_value = response

        vectors = server._sm_embedding_request(['问题', '答案'], self.config)

        self.assertEqual(vectors, [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        payload = post.call_args.kwargs['json']
        self.assertEqual(payload['model'], 'test-embedding')
        self.assertEqual(payload['input'], ['问题', '答案'])

    @patch.object(server.requests, 'post')
    def test_embedding_request_rejects_dimension_mismatch(self, post):
        response = Mock(status_code=200)
        response.json.return_value = {
            'data': [{'index': 0, 'embedding': [1.0, 0.0]}]
        }
        post.return_value = response

        with self.assertRaisesRegex(RuntimeError, '维度'):
            server._sm_embedding_request(['问题'], self.config)

    def test_binary_cache_round_trip(self):
        vector = [0.125, -0.5, 0.75]
        blob = server.array('f', vector).tobytes()
        restored = server._sm_unpack_embedding(blob, 3)
        self.assertEqual(len(restored), 3)
        for actual, expected in zip(restored, vector):
            self.assertAlmostEqual(actual, expected, places=6)

    def _ai_review_config(self):
        return {
            **self.config,
            'ai_review_enabled': True,
            'ai_review_match_types': ['问题+答案均一致', '仅问题一致', '仅答案一致'],
            'ai_review_batch_size': 8,
            'ai_review_resolved_base_url': 'https://example.test/v1',
            'ai_review_resolved_model': 'test-chat',
            'ai_review_resolved_api_key': 'test-key',
            'ai_review_fail_closed': True,
        }

    def _ai_review_row(self):
        return {
            'faq': {'question': '设备尺寸是多少？', 'answer': '尺寸为 400×415×500 mm。'},
            'match': {
                'type': '问题+答案均一致',
                'kb_id': 'KB-DIMENSION',
                'kb_question': '设备尺寸是多少？',
                'kb_answer': '尺寸为 350×456×456 mm。',
            },
            'reason': 'Embedding问题、答案均达到阈值',
        }

    @patch.object(server, '_sm_ai_review_batch')
    def test_ai_review_conflict_turns_dimension_mismatch_into_no_match(self, review_batch):
        review_batch.return_value = {
            0: {
                'decision': 'conflict',
                'confidence': 0.99,
                'conflicts': ['尺寸 400×415×500 mm 与 350×456×456 mm 不一致'],
                'reason': '关键尺寸不同',
            }
        }
        row = self._ai_review_row()

        summary = server._sm_apply_ai_reviews([row], self._ai_review_config())

        self.assertEqual(summary['reviewed'], 1)
        self.assertEqual(row['match']['type'], '无匹配')
        self.assertEqual(row['match']['ai_original_type'], '问题+答案均一致')
        self.assertEqual(row['match']['kb_id'], 'KB-DIMENSION')
        self.assertEqual(row['match']['ai_review_status'], 'conflict')
        self.assertFalse(row['match']['ai_review_blocking'])
        self.assertIn('尺寸', row['reason'])

    @patch.object(server, '_sm_ai_review_batch')
    def test_ai_review_consistent_keeps_embedding_match(self, review_batch):
        review_batch.return_value = {
            0: {'decision': 'consistent', 'confidence': 0.98, 'conflicts': [], 'reason': '关键事实一致'}
        }
        row = self._ai_review_row()

        server._sm_apply_ai_reviews([row], self._ai_review_config())

        self.assertEqual(row['match']['type'], '问题+答案均一致')
        self.assertEqual(row['match']['ai_review_status'], 'pass')
        self.assertFalse(row['match']['ai_review_blocking'])

    @patch.object(server, '_sm_ai_review_batch')
    def test_ai_review_uncertain_blocks_submission(self, review_batch):
        review_batch.return_value = {
            0: {'decision': 'uncertain', 'confidence': 0.4, 'conflicts': [], 'reason': '信息不足'}
        }
        row = self._ai_review_row()

        server._sm_apply_ai_reviews([row], self._ai_review_config())

        self.assertEqual(row['match']['ai_review_status'], 'uncertain')
        self.assertTrue(row['match']['ai_review_blocking'])
        self.assertIn('AI事实复核未完成', server._sm_ai_submission_block_reason(row))

    @patch.object(server, '_sm_ai_review_batch', side_effect=RuntimeError('provider unavailable'))
    def test_ai_review_error_blocks_submission(self, _review_batch):
        row = self._ai_review_row()

        server._sm_apply_ai_reviews([row], self._ai_review_config())

        self.assertEqual(row['match']['ai_review_status'], 'error')
        self.assertTrue(row['match']['ai_review_blocking'])
        self.assertIn('provider unavailable', row['match']['ai_review_reason'])

    def test_manual_override_allows_blocked_ai_result_to_submit(self):
        row = self._ai_review_row()
        row['match'].update({
            'ai_review_status': 'manual_override',
            'ai_review_blocking': True,
            'ai_review_manual_override': True,
        })

        self.assertEqual(server._sm_ai_submission_block_reason(row), '')

    @patch.object(server, '_sm_ai_review_batch')
    @patch.object(server, '_sm_db_update_job')
    @patch.object(server, '_sm_load_embedding_config')
    @patch.object(server, '_sm_get_embeddings')
    def test_compare_job_publishes_partial_results_during_ai_review(
        self, get_embeddings, load_config, _update_job, review_batch
    ):
        load_config.return_value = self._ai_review_config()
        get_embeddings.side_effect = lambda texts, _config: [[1.0, 0.0, 0.0] for _ in texts]
        review_batch.return_value = {
            0: {'decision': 'consistent', 'confidence': 0.95, 'conflicts': [], 'reason': '事实一致'}
        }
        job_id = 'streaming-job'
        server._SM_JOBS[job_id] = {'ts': 0, 'status': 'running', 'done': 0, 'results': []}

        server._sm_run_compare_job(
            job_id,
            'tester',
            'knowledge_base_v1',
            [],
            [{'row_number': 1, 'question': '待查问题', 'answer': '待查答案'}],
            [{'question_wiki_id': 'KB1', 'question': '候选问题', 'answer': '候选答案'}],
            0.75,
        )

        partial_updates = [
            call for call in _update_job.call_args_list
            if call.kwargs.get('status') == 'running' and call.kwargs.get('results_json')
        ]
        self.assertTrue(partial_updates)
        self.assertTrue(any(
            'AI 事实复核：1/1' in call.kwargs.get('message', '')
            for call in _update_job.call_args_list
        ))
        self.assertEqual(server._SM_JOBS[job_id]['status'], 'done')
        self.assertEqual(server._SM_JOBS[job_id]['results'][0]['match']['ai_review_status'], 'pass')

    @patch.object(server, '_sm_db_update_job')
    @patch.object(server, '_sm_load_embedding_config')
    @patch.object(server, '_sm_get_embeddings')
    def test_compare_job_uses_embedding_scores(self, get_embeddings, load_config, _update_job):
        load_config.return_value = dict(self.config)
        vectors_by_text = {
            '候选问题一': [1.0, 0.0, 0.0],
            '候选答案一': [1.0, 0.0, 0.0],
            '候选问题二': [0.0, 1.0, 0.0],
            '候选答案二': [0.0, 1.0, 0.0],
            '待查问题': [0.0, 1.0, 0.0],
            '待查答案': [0.0, 1.0, 0.0],
        }
        get_embeddings.side_effect = lambda texts, _config: [vectors_by_text[text] for text in texts]
        job_id = 'embedding-job'
        server._SM_JOBS[job_id] = {'ts': 0, 'status': 'running', 'done': 0, 'results': []}

        server._sm_run_compare_job(
            job_id,
            'tester',
            'knowledge_base_v1',
            [],
            [{'row_number': 1, 'question': '待查问题', 'answer': '待查答案'}],
            [
                {'question_wiki_id': 'KB1', 'question': '候选问题一', 'answer': '候选答案一'},
                {'question_wiki_id': 'KB2', 'question': '候选问题二', 'answer': '候选答案二'},
            ],
            0.75,
        )

        result = server._SM_JOBS[job_id]['results'][0]
        self.assertEqual(result['match']['kb_id'], 'KB2')
        self.assertEqual(result['match']['type'], '问题+答案均一致')
        self.assertEqual(result['match']['algorithm'], 'embedding')
        self.assertIn('Embedding', result['reason'])

    @patch.object(server, '_sm_db_update_job')
    @patch.object(server, '_sm_load_embedding_config')
    @patch.object(server, '_sm_get_embeddings', side_effect=RuntimeError('service unavailable'))
    def test_compare_job_falls_back_to_ngram(self, _get_embeddings, load_config, _update_job):
        load_config.return_value = dict(self.config)
        job_id = 'fallback-job'
        server._SM_JOBS[job_id] = {'ts': 0, 'status': 'running', 'done': 0, 'results': []}

        server._sm_run_compare_job(
            job_id,
            'tester',
            'knowledge_base_v1',
            [],
            [{'row_number': 1, 'question': '清扫不干净', 'answer': '请清理主刷'}],
            [{'question_wiki_id': 'KB1', 'question': '清扫不干净', 'answer': '请清理主刷'}],
            0.75,
        )

        result = server._SM_JOBS[job_id]['results'][0]
        self.assertEqual(result['match']['kb_id'], 'KB1')
        self.assertEqual(result['match']['algorithm'], 'ngram_fallback')
        self.assertIn('service unavailable', result['match']['fallback_reason'])


if __name__ == '__main__':
    unittest.main()
