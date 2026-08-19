import json
import unittest
import uuid
from unittest.mock import patch

import server


class FakeResponse:
    def __init__(self, status_code=200, data=None, text=''):
        self.status_code = status_code
        self._data = data if data is not None else []
        self.text = text
        self.headers = {}

    def json(self):
        return self._data


class InMemoryKnowledgeClient:
    def __init__(self):
        self.tables = {
            'knowledge_base_v1': [{
                'question_wiki_id': 'ACT-001',
                'question': '活动优惠什么时候结束？',
                'answer': '活动于本周日 24:00 结束。',
                'product_name': 'S8 Pro',
                'product_category_name': '扫地机',
                'question_type': '活动',
                'answer_type': '规则',
                'similar_questions': ['优惠结束时间'],
                'keyword_list': ['活动', '优惠'],
                'image_urls': ['https://example.test/activity.png'],
                'review_status': 'unadjusted',
                'update_time': '2026-07-29T10:00:00+08:00',
            }],
            'kb_tags': [{'id': 1, 'name': '活动'}],
            'kb_item_tags': [{
                'library_type': 'current',
                'question_wiki_id': 'ACT-001',
                'tag_id': 1,
            }],
            'kb_scores': [{'kb_id': 'ACT-001'}],
            'link_previews': [],
            'knowledge_base_modifications': [],
        }

    @staticmethod
    def _in_values(value):
        raw = str(value or '')
        if not raw.startswith('in.(') or not raw.endswith(')'):
            return []
        body = raw[4:-1]
        return [piece.strip().strip('"') for piece in body.split(',') if piece.strip()]

    @staticmethod
    def _matches(row, filters):
        for key, value in (filters or {}).items():
            text = str(value)
            if text.startswith('in.('):
                if str(row.get(key, '')) not in InMemoryKnowledgeClient._in_values(text):
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

    def select(self, table, page=1, page_size=20, filters=None, order_by=None, order_dir='asc', columns='*', count='exact'):
        rows = self.select_all(table, filters, order_by, order_dir, columns, page_size)
        start = (page - 1) * page_size
        response = FakeResponse(200, rows[start:start + page_size])
        response.headers['Content-Range'] = f'{start}-{max(start, start + len(rows[start:start + page_size]) - 1)}/{len(rows)}'
        return response

    def delete(self, table, filters):
        rows = self.tables.setdefault(table, [])
        self.tables[table] = [row for row in rows if not self._matches(row, filters)]
        return FakeResponse(200)

    def insert(self, table, data, ignore_duplicates=False):
        rows = data if isinstance(data, list) else [data]
        target = self.tables.setdefault(table, [])
        for row in rows:
            copied = dict(row)
            if table == 'knowledge_base_v1':
                if any(item.get('question_wiki_id') == copied.get('question_wiki_id') for item in target):
                    return FakeResponse(409, text='duplicate question_wiki_id')
            if table == 'kb_tags' and 'id' not in copied:
                copied['id'] = max([item.get('id', 0) for item in target] or [0]) + 1
            target.append(copied)
        return FakeResponse(201)

    def upsert(self, table, data, on_conflict=None):
        rows = data if isinstance(data, list) else [data]
        if table == 'kb_tags':
            for row in rows:
                if not any(str(item.get('name')).lower() == str(row.get('name')).lower() for item in self.tables[table]):
                    self.insert(table, row)
            return FakeResponse(200)
        return self.insert(table, rows)


class ActivityArchiveApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.app.config.update(TESTING=True, LOGIN_DISABLED=True)
        with server.app.app_context():
            server.db.create_all()

    def setUp(self):
        self.client = server.app.test_client()
        self.remote = InMemoryKnowledgeClient()
        self.batch_name = f'活动暂存测试-{uuid.uuid4()}'
        self.client_patch = patch.object(server, 'get_supabase_client', return_value=self.remote)
        self.client_patch.start()

    def tearDown(self):
        self.client_patch.stop()
        with server.app.app_context():
            batch_ids = [row.id for row in server.ActivityArchiveBatch.query.filter_by(batch_name=self.batch_name).all()]
            if batch_ids:
                server.ActivityArchiveRecord.query.filter(server.ActivityArchiveRecord.batch_id.in_(batch_ids)).delete(synchronize_session=False)
                server.ActivityArchiveBatch.query.filter(server.ActivityArchiveBatch.id.in_(batch_ids)).delete(synchronize_session=False)
                server.db.session.commit()

    def test_archive_then_restore_preserves_content_and_tags(self):
        archived = self.client.post('/api/kb/activity-archives', json={
            'batch_name': self.batch_name,
            'ids': ['ACT-001'],
            'expected_count': 1,
            'confirm_archive': True,
        })
        self.assertEqual(archived.status_code, 200, archived.get_data(as_text=True))
        payload = archived.get_json()
        self.assertTrue(payload['success'])
        self.assertEqual(self.remote.tables['knowledge_base_v1'], [])
        self.assertEqual(self.remote.tables['kb_item_tags'], [])
        archive_modification = self.remote.tables['knowledge_base_modifications'][0]
        self.assertEqual(archive_modification['change_type'], 'delete')
        self.assertEqual(archive_modification['source_module'], '活动暂存')
        self.assertEqual(json.loads(archive_modification['change_meta'])['before']['question'], '活动优惠什么时候结束？')

        with server.app.app_context():
            batch = server.db.session.get(server.ActivityArchiveBatch, payload['batch_id'])
            record = server.ActivityArchiveRecord.query.filter_by(batch_id=batch.id, question_wiki_id='ACT-001').one()
            snapshot = json.loads(record.record_json)
            self.assertEqual(batch.status, 'archived')
            self.assertEqual(snapshot['answer'], '活动于本周日 24:00 结束。')
            self.assertEqual(json.loads(record.tag_names_json), ['活动'])

        restored = self.client.post(f"/api/kb/activity-archives/{payload['batch_id']}/restore", json={
            'confirm_restore': True,
        })
        self.assertEqual(restored.status_code, 200, restored.get_data(as_text=True))
        self.assertTrue(restored.get_json()['success'])
        self.assertEqual(self.remote.tables['knowledge_base_v1'][0]['question_wiki_id'], 'ACT-001')
        self.assertEqual(self.remote.tables['knowledge_base_v1'][0]['review_status'], 'modifying')
        self.assertEqual(self.remote.tables['knowledge_base_v1'][0]['answer'], '活动于本周日 24:00 结束。')
        self.assertEqual(self.remote.tables['kb_item_tags'][0]['question_wiki_id'], 'ACT-001')

        second_restore = self.client.post(f"/api/kb/activity-archives/{payload['batch_id']}/restore", json={
            'confirm_restore': True,
        })
        self.assertEqual(second_restore.status_code, 409)

    def test_archive_requires_confirmation_and_blocks_duplicate_active_snapshot(self):
        needs_confirmation = self.client.post('/api/kb/activity-archives', json={
            'batch_name': self.batch_name,
            'ids': ['ACT-001'],
        })
        self.assertEqual(needs_confirmation.status_code, 409)
        self.assertTrue(needs_confirmation.get_json()['requires_confirmation'])

        first = self.client.post('/api/kb/activity-archives', json={
            'batch_name': self.batch_name,
            'ids': ['ACT-001'],
            'expected_count': 1,
            'confirm_archive': True,
        })
        self.assertEqual(first.status_code, 200, first.get_data(as_text=True))

        duplicate = self.client.post('/api/kb/activity-archives', json={
            'batch_name': self.batch_name + '-重复',
            'ids': ['ACT-001'],
            'expected_count': 1,
            'confirm_archive': True,
        })
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.get_json()['conflict_ids'], ['ACT-001'])


class ArchiveDeletionApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.app.config.update(TESTING=True, LOGIN_DISABLED=True)
        with server.app.app_context():
            server.db.create_all()

    def setUp(self):
        self.client = server.app.test_client()
        self.remote = InMemoryKnowledgeClient()
        self.batch_name = f'归档删除测试-{uuid.uuid4()}'
        self.client_patch = patch.object(server, 'get_supabase_client', return_value=self.remote)
        self.client_patch.start()
        with server.app.app_context():
            batch = server.ArchiveBatch(
                batch_name=self.batch_name,
                record_count=2,
                created_by='test',
            )
            server.db.session.add(batch)
            server.db.session.flush()
            self.batch_id = batch.id
            server.db.session.add_all([
                server.ArchiveRecord(
                    batch_id=batch.id,
                    record_json=json.dumps({'question_wiki_id': 'KB-001'}),
                ),
                server.ArchiveRecord(
                    batch_id=batch.id,
                    record_json=json.dumps({'question_wiki_id': 'KB-002'}),
                ),
            ])
            server.db.session.commit()
        self.remote.tables.update({
            'archive_batch': [{'id': self.batch_id, 'batch_name': self.batch_name}],
            'archive_record': [
                {'id': 1, 'batch_id': self.batch_id, 'record_json': '{}'},
                {'id': 2, 'batch_id': self.batch_id, 'record_json': '{}'},
            ],
            'knowledge_base_modifications': [
                {'id': 11, 'archive_batch_id': str(self.batch_id)},
                {'id': 12, 'archive_batch_id': str(self.batch_id)},
                {'id': 99, 'archive_batch_id': 'another-batch'},
            ],
        })

    def tearDown(self):
        self.client_patch.stop()
        with server.app.app_context():
            server.ArchiveRecord.query.filter_by(batch_id=self.batch_id).delete(synchronize_session=False)
            server.ArchiveBatch.query.filter_by(id=self.batch_id).delete(synchronize_session=False)
            server.db.session.commit()

    def test_delete_archive_batch_removes_batch_records_and_archived_modifications(self):
        needs_confirmation = self.client.delete(f'/api/archives/{self.batch_id}', json={})
        self.assertEqual(needs_confirmation.status_code, 409)
        self.assertTrue(needs_confirmation.get_json()['requires_confirmation'])

        with patch.object(server, 'is_supabase_archives_enabled', return_value=True), \
                patch.object(server, '_supabase_table_exists', return_value=True):
            deleted = self.client.delete(
                f'/api/archives/{self.batch_id}',
                json={'confirm_delete': True},
            )
        self.assertEqual(deleted.status_code, 200, deleted.get_data(as_text=True))
        payload = deleted.get_json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['deleted_record_count'], 2)
        self.assertEqual(payload['deleted_modification_count'], 2)
        self.assertEqual(self.remote.tables['archive_batch'], [])
        self.assertEqual(self.remote.tables['archive_record'], [])
        self.assertEqual(
            self.remote.tables['knowledge_base_modifications'],
            [{'id': 99, 'archive_batch_id': 'another-batch'}],
        )
        with server.app.app_context():
            self.assertIsNone(server.db.session.get(server.ArchiveBatch, self.batch_id))
            self.assertEqual(
                server.ArchiveRecord.query.filter_by(batch_id=self.batch_id).count(),
                0,
            )


if __name__ == '__main__':
    unittest.main()
