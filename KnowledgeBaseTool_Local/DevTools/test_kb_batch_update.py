import json
import unittest
from unittest.mock import patch

import server


class FakeResponse:
    def __init__(self, status_code=200, data=None, text=''):
        self.status_code = status_code
        self._data = data if data is not None else []
        self.text = text

    def json(self):
        return self._data


class InMemoryKnowledgeClient:
    def __init__(self):
        self.tables = {
            'knowledge_base_v1': [
                {
                    'question_wiki_id': 'KB-001',
                    'question': '如何清洁？',
                    'answer': '请按说明书清洁。',
                    'product_name': 'S8 Pro',
                    'product_category_name': '扫地机',
                    'question_type': '维护',
                    'answer_type': '文字',
                    'if_bm25': False,
                    'similar_questions': ['怎么清洗'],
                    'keyword_list': ['清洁'],
                    'image_urls': ['https://example.test/old.png'],
                    'link_type': '手册',
                    'link_url': 'https://example.test/manual',
                    'review_status': 'unadjusted',
                    'update_time': '2026-07-31T10:00:00+08:00',
                },
                {
                    'question_wiki_id': 'KB-002',
                    'question': '如何保养？',
                    'answer': '请定期维护。',
                    'product_name': 'T7 Pro',
                    'product_category_name': '扫地机',
                    'question_type': '维护',
                    'answer_type': '文字',
                    'if_bm25': False,
                    'similar_questions': ['怎么维护'],
                    'keyword_list': ['维护'],
                    'image_urls': [],
                    'link_type': '手册',
                    'link_url': '',
                    'review_status': 'unadjusted',
                    'update_time': '2026-07-31T10:00:00+08:00',
                },
            ],
            'kb_tags': [
                {'id': 1, 'name': '维护'},
                {'id': 2, 'name': '原有'},
            ],
            'kb_item_tags': [
                {'library_type': 'current', 'question_wiki_id': 'KB-001', 'tag_id': 1},
                {'library_type': 'current', 'question_wiki_id': 'KB-002', 'tag_id': 2},
            ],
            'knowledge_base_modifications': [],
        }

    @staticmethod
    def _in_values(value):
        raw = str(value or '')
        if not raw.startswith('in.(') or not raw.endswith(')'):
            return []
        body = raw[4:-1]
        return [piece.strip().strip('"') for piece in body.split(',') if piece.strip()]

    @classmethod
    def _matches(cls, row, filters):
        for key, value in (filters or {}).items():
            text = str(value or '')
            if text.startswith('in.('):
                if str(row.get(key, '')) not in cls._in_values(text):
                    return False
            elif text.startswith('eq.'):
                if str(row.get(key, '')) != text[3:]:
                    return False
        return True

    def select_all(self, table, filters=None, order_by=None, order_dir='asc', columns='*', page_size=1000):
        rows = [dict(row) for row in self.tables.get(table, []) if self._matches(row, filters)]
        if order_by:
            rows.sort(key=lambda row: str(row.get(order_by) or ''), reverse=order_dir == 'desc')
        return rows

    def update(self, table, data, filters):
        matched = False
        for row in self.tables.get(table, []):
            if self._matches(row, filters):
                row.update(dict(data))
                matched = True
        return FakeResponse(200 if matched else 404, text='' if matched else 'not found')

    def delete(self, table, filters):
        rows = self.tables.setdefault(table, [])
        self.tables[table] = [row for row in rows if not self._matches(row, filters)]
        return FakeResponse(200)

    def insert(self, table, data, ignore_duplicates=False):
        rows = data if isinstance(data, list) else [data]
        target = self.tables.setdefault(table, [])
        for row in rows:
            copied = dict(row)
            if table == 'kb_item_tags' and any(item == copied for item in target):
                continue
            target.append(copied)
        return FakeResponse(201)

    def upsert(self, table, data, on_conflict=None):
        rows = data if isinstance(data, list) else [data]
        if table == 'kb_tags':
            for row in rows:
                if any(str(item.get('name')).lower() == str(row.get('name')).lower() for item in self.tables[table]):
                    continue
                next_id = max([item.get('id', 0) for item in self.tables[table]] or [0]) + 1
                self.tables[table].append({'id': next_id, 'name': row['name']})
            return FakeResponse(200)
        return self.insert(table, rows)


class KBBatchUpdateApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.app.config.update(TESTING=True, LOGIN_DISABLED=True)

    def setUp(self):
        self.client = server.app.test_client()
        self.remote = InMemoryKnowledgeClient()
        self.client_patch = patch.object(server, 'get_supabase_client', return_value=self.remote)
        self.models_patch = patch.object(
            server,
            'get_all_valid_models',
            return_value=({'s8pro': 'S8 Pro', 't7pro': 'T7 Pro'}, {'S8 Pro', 'T7 Pro'}),
        )
        self.client_patch.start()
        self.models_patch.start()

    def tearDown(self):
        self.models_patch.stop()
        self.client_patch.stop()

    def test_applies_list_set_and_tag_rules_with_per_item_audit(self):
        response = self.client.post('/api/kb/batch-update', json={
            'table': 'knowledge_base_v1',
            'ids': ['KB-001', 'KB-002'],
            'expected_count': 2,
            'operations': [
                {'field': 'product_name', 'mode': 'add', 'values': ['S8 Pro']},
                {'field': 'similar_questions', 'mode': 'remove', 'values': ['怎么清洗']},
                {'field': 'image_urls', 'mode': 'add', 'values': ['https://example.test/new.png']},
                {'field': 'kb_tags', 'mode': 'add', 'values': ['批量修改']},
                {'field': 'question_type', 'value': '售后'},
                {'field': 'answer_type', 'value': '图文'},
                {'field': 'if_bm25', 'value': True},
                {'field': 'link_type', 'value': 'FAQ'},
            ],
        })

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['count'], 2)
        self.assertTrue(payload['mod_log_ok'])

        first, second = self.remote.tables['knowledge_base_v1']
        self.assertEqual(first['product_name'], 'S8 Pro')
        self.assertEqual(second['product_name'], 'T7 Pro,S8 Pro')
        self.assertIsNone(first['similar_questions'])
        self.assertEqual(json.loads(first['image_urls']), ['https://example.test/old.png', 'https://example.test/new.png'])
        self.assertEqual(json.loads(second['image_urls']), ['https://example.test/new.png'])
        self.assertEqual(first['question_type'], '售后')
        self.assertEqual(second['answer_type'], '图文')
        self.assertTrue(first['if_bm25'])
        self.assertEqual(second['link_type'], 'FAQ')
        self.assertEqual(first['review_status'], 'modifying')

        tag_names = {row['id']: row['name'] for row in self.remote.tables['kb_tags']}
        tags_by_item = {}
        for mapping in self.remote.tables['kb_item_tags']:
            tags_by_item.setdefault(mapping['question_wiki_id'], set()).add(tag_names[mapping['tag_id']])
        self.assertEqual(tags_by_item['KB-001'], {'维护', '批量修改'})
        self.assertEqual(tags_by_item['KB-002'], {'原有', '批量修改'})

        modifications = self.remote.tables['knowledge_base_modifications']
        self.assertEqual(len(modifications), 2)
        operation_ids = {json.loads(item['change_meta'])['operation_id'] for item in modifications}
        self.assertEqual(len(operation_ids), 1)
        changed_fields = json.loads(modifications[0]['change_meta'])['changed_fields']
        self.assertIn('kb_tags', changed_fields)
        self.assertIn('question_type', changed_fields)

    def test_skips_noop_and_rejects_unsupported_or_previous_library_writes(self):
        no_change = self.client.post('/api/kb/batch-update', json={
            'ids': ['KB-001'],
            'operations': [{'field': 'keyword_list', 'mode': 'add', 'values': ['清洁']}],
        })
        self.assertEqual(no_change.status_code, 200, no_change.get_data(as_text=True))
        self.assertEqual(no_change.get_json()['count'], 0)
        self.assertEqual(no_change.get_json()['skipped_ids'], ['KB-001'])
        self.assertEqual(self.remote.tables['knowledge_base_modifications'], [])

        answer_rejected = self.client.post('/api/kb/batch-update', json={
            'ids': ['KB-001'],
            'operations': [{'field': 'answer', 'value': '不允许'}],
        })
        self.assertEqual(answer_rejected.status_code, 400)
        self.assertIn('不支持批量编辑字段', answer_rejected.get_json()['message'])

        previous_rejected = self.client.post('/api/kb/batch-update', json={
            'table': 'knowledge_base_v1_t1',
            'ids': ['KB-001'],
            'operations': [{'field': 'question_type', 'value': '售后'}],
        })
        self.assertEqual(previous_rejected.status_code, 400)
        self.assertIn('前刻库仅用于对比', previous_rejected.get_json()['message'])


if __name__ == '__main__':
    unittest.main()
