import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import os
# Add parent directory to path to allow importing modules from root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


import unittest
from unittest.mock import MagicMock, patch
import json
import sys
import os

# Add current directory to path
sys.path.append(os.getcwd())

# Import app from server
from server import app

class TestScoringCache(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['LOGIN_DISABLED'] = True
        self.client = app.test_client()
        
    @patch('server.get_supabase_client')
    def test_clear_cache(self, mock_get_client):
        # Setup mock
        mock_supabase = MagicMock()
        mock_get_client.return_value = mock_supabase
        
        # Mock delete response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_supabase.delete.return_value = mock_response
        
        # Call endpoint
        response = self.client.post('/api/scoring/clear_cache')
        
        # Assertions
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {'success': True})
        
        # Verify delete was called with correct args
        # delete('kb_scores', {'id': 'gt.0'})
        mock_supabase.delete.assert_called_once_with('kb_scores', {'id': 'gt.0'})
        print("Clear Cache Test Passed")

    @patch('server.get_supabase_client')
    @patch('server.load_scoring_config')
    @patch('server.LLMScorer') # Mock LLMScorer to avoid API calls
    def test_evaluate_use_cache(self, mock_llm_scorer, mock_load_config, mock_get_client):
        # Setup mocks
        mock_supabase = MagicMock()
        mock_get_client.return_value = mock_supabase
        
        mock_load_config.return_value = {
            'api_key': 'test_key',
            'base_url': 'http://test',
            'model': 'test_model'
        }
        
        # Mock LLMScorer instance
        mock_scorer_instance = MagicMock()
        mock_llm_scorer.return_value = mock_scorer_instance
        
        # Define test data
        test_kb_id = "KB001"
        cached_score_data = {
            "总分": 95,
            "analysis": "Test Analysis"
        }
        cached_score_record = {
            "kb_id": test_kb_id,
            "status": "scored",
            "score_data": json.dumps(cached_score_data),
            "total_score": 95
        }
        
        # Mock fetch existing scores (cache hit)
        # The code does: client.select('kb_scores', ..., filters={'kb_id': ...})
        # It returns a list of dicts
        mock_supabase.select.side_effect = [
            [cached_score_record], # First call: fetch cached scores
            [{'question_wiki_id': test_kb_id, 'question': 'q', 'answer': 'a'}] # Second call: fetch KB items
        ]
        
        # Mock fetch all KB for overlap (lightweight)
        mock_supabase.select_all.return_value = [] 
        
        # Call endpoint with use_cache=True
        response = self.client.post('/api/scoring/evaluate', json={
            'ids': [test_kb_id],
            'use_cache': True
        })
        
        # Assertions
        self.assertEqual(response.status_code, 200)
        data = response.json
        self.assertTrue(data['success'])
        self.assertEqual(len(data['results']), 1)
        result = data['results'][0]
        
        self.assertEqual(result['kb_id'], test_kb_id)
        self.assertEqual(result['总分'], 95)
        
        # Verify LLMScorer.evaluate_one was NOT called
        mock_scorer_instance.evaluate_one.assert_not_called()
        print("Use Cache Test Passed")

    @patch('server.get_supabase_client')
    @patch('server.load_scoring_config')
    @patch('server.LLMScorer')
    def test_evaluate_no_cache(self, mock_llm_scorer, mock_load_config, mock_get_client):
        # Setup mocks
        mock_supabase = MagicMock()
        mock_get_client.return_value = mock_supabase
        
        mock_load_config.return_value = {
            'api_key': 'test_key',
            'base_url': 'http://test',
            'model': 'test_model'
        }
        
        mock_scorer_instance = MagicMock()
        mock_llm_scorer.return_value = mock_scorer_instance
        
        # Mock LLM result
        llm_result = {
            "总分": 80,
            "质量得分": 80,
            "合规得分": 0,
            "时效得分": 0,
            "实用得分": 0,
            "冗余扣分": 0,
            "多媒体得分": 0,
            "修改建议": "None",
            "扣分分析": "None"
        }
        mock_scorer_instance.evaluate_one.return_value = llm_result
        
        test_kb_id = "KB002"
        
        # Mock fetch KB items (Cache fetch is skipped when use_cache=False)
        mock_supabase.select.side_effect = [
            [{'question_wiki_id': test_kb_id, 'question': 'q', 'answer': 'a'}] # KB item found
        ]
        mock_supabase.select_all.return_value = []
        
        # Call endpoint with use_cache=False
        response = self.client.post('/api/scoring/evaluate', json={
            'ids': [test_kb_id],
            'use_cache': False
        })
        
        # Assertions
        self.assertEqual(response.status_code, 200)
        data = response.json
        self.assertTrue(data['success'])
        result = data['results'][0]
        self.assertEqual(result['kb_id'], test_kb_id)
        self.assertEqual(result['总分'], 80)
        
        # Verify LLMScorer.evaluate_one WAS called
        mock_scorer_instance.evaluate_one.assert_called_once()
        print("No Cache Test Passed")

if __name__ == '__main__':
    unittest.main()
