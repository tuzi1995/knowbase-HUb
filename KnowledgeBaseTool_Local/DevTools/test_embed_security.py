import os
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import server


class TestEmbedSecurity(unittest.TestCase):
    APP_ROOT = Path(__file__).resolve().parents[1]

    @classmethod
    def setUpClass(cls):
        server.app.config.update(TESTING=True)

    def setUp(self):
        self.client = server.app.test_client()

    def test_allowed_origin_is_normalized_and_accepted(self):
        with patch.dict(os.environ, {
            'KMATRIX_EMBED_ALLOWED_ORIGINS': 'http://127.0.0.1:5175,https://example.test',
        }):
            response = self.client.get('/api/embed/validate?host_origin=http://127.0.0.1:5175/path')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['host_origin'], 'http://127.0.0.1:5175')

    def test_untrusted_and_missing_origins_are_rejected(self):
        with patch.dict(os.environ, {
            'KMATRIX_EMBED_ALLOWED_ORIGINS': 'http://127.0.0.1:5175',
        }):
            untrusted = self.client.get('/api/embed/validate?host_origin=http://evil.test')
            missing = self.client.get('/api/embed/validate')
        self.assertEqual(untrusted.status_code, 403)
        self.assertFalse(untrusted.get_json()['allowed'])
        self.assertEqual(missing.status_code, 400)

    def test_root_response_limits_frame_ancestors(self):
        with patch.dict(os.environ, {
            'KMATRIX_EMBED_ALLOWED_ORIGINS': 'http://127.0.0.1:5175,https://example.test',
        }):
            response = self.client.get('/')
        try:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.headers.get('Content-Security-Policy'),
                "frame-ancestors 'self' http://127.0.0.1:5175 https://example.test",
            )
            self.assertIsNone(response.headers.get('X-Frame-Options'))
        finally:
            response.close()

    def test_change_source_is_written_to_modification_metadata(self):
        source = server._resolve_kb_change_source({'change_source': '知识库内容检测工具'})
        record = {}
        server._attach_change_meta(record, {'source': source, 'changed_fields': ['answer']})
        self.assertEqual(source, '知识库内容检测工具')
        self.assertEqual(record['source_module'], '知识库内容检测工具')
        self.assertEqual(json.loads(record['change_meta'])['source'], '知识库内容检测工具')
        self.assertTrue(server._mod_source_match(record['source_module'], source))
        self.assertFalse(server._mod_source_match(record['source_module'], '知识库管理'))

    def test_modification_source_filter_contains_detection_tool(self):
        html = (self.APP_ROOT / 'link_viewer' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('<option value="知识库内容检测工具">知识库内容检测工具</option>', html)

    def test_compare_embed_forces_workbench_to_single_column(self):
        css = (self.APP_ROOT / 'link_viewer' / 'extra_styles.css').read_text(encoding='utf-8')
        selector = 'body.kb-action-embed-mode #mainContent .workbench-layout {'
        block = css.split(selector, 1)[1].split('}', 1)[0]
        self.assertIn('grid-template-columns: minmax(0, 1fr) !important;', block)
        self.assertIn('width: 100% !important;', block)
        self.assertIn('min-width: 0 !important;', block)

    def test_compare_embed_uses_inner_scroll_container(self):
        js = (self.APP_ROOT / 'link_viewer' / 'app_v8.js').read_text(encoding='utf-8')
        css = (self.APP_ROOT / 'link_viewer' / 'extra_styles.css').read_text(encoding='utf-8')
        html_selector = 'html.kb-action-embed-mode {'
        html_block = css.split(html_selector, 1)[1].split('}', 1)[0]
        body_selector = 'body.kb-action-embed-mode {'
        body_block = css.split(body_selector, 1)[1].split('}', 1)[0]
        self.assertIn("document.documentElement.classList.add('kb-action-embed-mode');", js)
        self.assertIn('overflow: hidden;', html_block)
        self.assertIn('height: 100vh;', body_block)
        views_selector = 'body.kb-action-embed-mode #mainContent .workbench-views {'
        views_block = css.split(views_selector, 1)[1].split('}', 1)[0]
        self.assertIn('overflow-y: auto !important;', views_block)
        self.assertIn('min-height: 0 !important;', views_block)
        self.assertIn("document.querySelector('#mainContent .workbench-views')", js)

    def test_compare_embed_keeps_panels_in_the_same_scroll_flow(self):
        js = (self.APP_ROOT / 'link_viewer' / 'app_v8.js').read_text(encoding='utf-8')
        css = (self.APP_ROOT / 'link_viewer' / 'extra_styles.css').read_text(encoding='utf-8')
        self.assertIn('class="kb-compare-draft-footer"', js)
        header_actions_selector = 'body.kb-action-embed-mode .kb-compare-draft-action-stack {'
        header_actions_block = css.split(header_actions_selector, 1)[1].split('}', 1)[0]
        self.assertIn('display: none !important;', header_actions_block)
        import_selector = 'body.kb-action-embed-mode .kb-compare-import-panel {'
        import_block = css.split(import_selector, 1)[1].split('}', 1)[0]
        self.assertIn('position: static;', import_block)
        self.assertIn('max-height: none;', import_block)
        footer_selector = 'body.kb-action-embed-mode .kb-compare-draft-footer {'
        footer_block = css.split(footer_selector, 1)[1].split('}', 1)[0]
        self.assertIn('position: static;', footer_block)
        self.assertNotIn('position: fixed;', footer_block)
        self.assertNotIn('bottom:', footer_block)


if __name__ == '__main__':
    unittest.main()
