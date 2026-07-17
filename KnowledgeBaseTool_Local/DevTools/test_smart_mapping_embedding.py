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
