import unittest
from unittest.mock import patch

import server


class KBDuplicateCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.app.config.update(TESTING=True, LOGIN_DISABLED=True)
        server.init_db()

    def tearDown(self):
        with server.app.app_context():
            server.KBDuplicateCheckTask.query.filter(
                server.KBDuplicateCheckTask.task_id.like('test-duplicate-%')
            ).delete(synchronize_session=False)
            server.KBDuplicateIndexJob.query.filter(
                server.KBDuplicateIndexJob.job_id.like('test-index-%')
            ).delete(synchronize_session=False)
            server.db.session.commit()

    def _create_task(self, suffix='worker'):
        task = server.KBDuplicateCheckTask(
            task_id=f'test-duplicate-{suffix}',
            username='',
            library='knowledge_base_v1',
            status='running',
            stage='preparing_index',
            question='扫地机吐头发怎么办？',
            answer='清理主刷并检查风道。',
            product_category_name='扫地机',
            product_names_json='["G30"]',
            source_note='test',
            candidates_json='[]',
            analysis_json='{}',
            completed_channels_json='[]',
            failed_stages_json='[]',
        )
        server.db.session.merge(task)
        server.db.session.commit()
        return task

    def test_topic_terms_keep_domain_terms_and_model_codes(self):
        terms = server._kd_topic_terms('G30 主刷吐头发', '请检查风道并清理毛发')

        self.assertIn('G30', terms)
        self.assertIn('主刷', terms)
        self.assertIn('风道', terms)
        self.assertIn('毛发', terms)

    def test_ai_contract_rejects_unknown_relationship(self):
        candidates = [{'question_wiki_id': 'ICWIKI001'}]

        with self.assertRaisesRegex(ValueError, '覆盖关系'):
            server._kd_normalize_ai_analysis({
                'relationship': 'maybe_related',
                'recommended_action': 'manual_review',
                'reason': '无法确认',
            }, candidates)

    @patch.object(server, '_kd_run_ai_coverage', side_effect=RuntimeError('AI offline'))
    @patch.object(server, '_kd_retrieve_candidates')
    @patch.object(server, '_kd_sync_index', return_value={'embedding_error': ''})
    def test_worker_keeps_candidates_when_ai_fails(self, _sync, retrieve, _ai):
        candidate = {
            'question_wiki_id': 'ICWIKI001',
            'question': '清扫时毛发吸不进去怎么办？',
            'answer': '清理主刷和风道。',
            'product_category_name': '扫地机',
            'product_names': ['G30'],
            'channels': ['structured'],
            'question_similarity': 0.72,
            'answer_similarity': 0.68,
            'keyword_hits': ['主刷', '风道'],
            'relationship': 'partially_covered',
            'confidence': 0.72,
            'covered_points': ['主刷', '风道'],
            'missing_points': [],
            'conflicts': [],
            'recommended_action': 'manual_review',
            'reason': '等待 AI 覆盖判断',
            'analysis_source': 'heuristic',
        }
        retrieve.return_value = ([candidate], {'embedding_error': '', 'channels': ['structured']})

        with server.app.app_context():
            self._create_task()
            server._kd_run_task('test-duplicate-worker')
            task = server.KBDuplicateCheckTask.query.get('test-duplicate-worker')
            candidates = server._kd_json_load(task.candidates_json, [])
            failed = server._kd_json_load(task.failed_stages_json, [])

        self.assertEqual(task.status, 'partial_failed')
        self.assertEqual(candidates[0]['question_wiki_id'], 'ICWIKI001')
        self.assertIn('ai', failed)

    @patch.object(server, '_kd_spawn_task', return_value=True)
    def test_start_api_persists_valid_input(self, _spawn):
        client = server.app.test_client()
        response = client.post('/api/kb/duplicate-check/start', json={
            'library': 'knowledge_base_v1',
            'question': '扫地机吐头发怎么办？',
            'answer': '请清理主刷。',
            'product_category_name': '扫地机',
            'product_names': ['G30'],
        })

        self.assertEqual(response.status_code, 200)
        task_id = response.get_json()['task_id']
        with server.app.app_context():
            task = server.KBDuplicateCheckTask.query.get(task_id)
            task.task_id = 'test-duplicate-start'
            server.db.session.commit()
            self.assertEqual(task.question, '扫地机吐头发怎么办？')
            self.assertEqual(server._kd_json_load(task.product_names_json, []), ['G30'])

    @patch.object(server, '_sm_load_embedding_config', return_value={
        'api_url': 'https://example.test/v1/embeddings',
        'api_key': '',
        'model': 'test-embedding',
        'dimensions': 3,
    })
    def test_index_rebuild_requires_api_key(self, _config):
        client = server.app.test_client()

        response = client.post('/api/kb/duplicate-check/index/rebuild', json={
            'library': 'knowledge_base_v1',
            'mode': 'full',
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn('API Key', response.get_json()['message'])

    @patch.object(server, '_kd_spawn_index_job', return_value=True)
    @patch.object(server, '_sm_load_embedding_config', return_value={
        'api_url': 'https://example.test/v1/embeddings',
        'api_key': 'test-key',
        'model': 'test-embedding',
        'dimensions': 3,
    })
    def test_index_rebuild_creates_independent_job(self, _config, _spawn):
        client = server.app.test_client()
        response = client.post('/api/kb/duplicate-check/index/rebuild', json={
            'library': 'knowledge_base_v1',
            'mode': 'full',
        })

        self.assertEqual(response.status_code, 200)
        job_id = response.get_json()['job_id']
        with server.app.app_context():
            job = server.KBDuplicateIndexJob.query.get(job_id)
            job.job_id = 'test-index-created'
            server.db.session.commit()
            self.assertEqual(job.mode, 'full')
            self.assertEqual(job.status, 'running')

    @patch.object(server, '_kd_sync_index', return_value={
        'embedding_error': '',
        'total': 6003,
        'done': 6003,
        'cache_hits': 120,
        'failed_count': 0,
        'updated_count': 6003,
        'cancelled': False,
    })
    def test_index_worker_persists_completion(self, _sync):
        with server.app.app_context():
            server.db.session.add(server.KBDuplicateIndexJob(
                job_id='test-index-worker',
                username='',
                library='knowledge_base_v1',
                mode='full',
                status='running',
            ))
            server.db.session.commit()
            server._kd_run_index_job('test-index-worker')
            job = server.KBDuplicateIndexJob.query.get('test-index-worker')

        self.assertEqual(job.status, 'done')
        self.assertEqual(job.done, 6003)
        self.assertEqual(job.cache_hits, 120)


if __name__ == '__main__':
    unittest.main()
