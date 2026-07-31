import base64
import os
import time
import unittest
from email.message import EmailMessage
from unittest.mock import patch

import server


def _message(subject, attachments=None, sent_at='Thu, 23 Jul 2026 09:30:00 +0800'):
    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = 'sender@example.com'
    message['Date'] = sent_at
    message['Message-ID'] = '<test-message@example.com>'
    message.set_content('test')
    for filename, content, content_type in attachments or []:
        maintype, subtype = content_type.split('/', 1)
        message.add_attachment(content, maintype=maintype, subtype=subtype, filename=filename)
    return message.as_bytes()


class FakeIMAP:
    messages = {}
    last_instance = None

    def __init__(self, host, port, timeout):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.fetched = []
        self.readonly = None
        self.logged_out = False
        type(self).last_instance = self

    def login(self, email_address, password):
        self.email_address = email_address
        self.password = password
        return 'OK', []

    def select(self, mailbox, readonly=False):
        self.readonly = readonly
        return 'OK', []

    def search(self, charset, *criteria):
        self.criteria = criteria
        return 'OK', [b' '.join(self.messages.keys())]

    def fetch(self, message_id, query):
        self.fetched.append(message_id)
        return 'OK', [(b'RFC822', self.messages[message_id])]

    def logout(self):
        self.logged_out = True


class KBMailImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.app.config.update(TESTING=True, LOGIN_DISABLED=True)

    def setUp(self):
        self.client = server.app.test_client()
        FakeIMAP.messages = {}
        FakeIMAP.last_instance = None
        server._clear_kb_mail_cache()

    def _config(self):
        return {
            'email': 'kb@example.com',
            'password': 'secret',
            'host': 'imap.feishu.cn',
            'port': 993,
            'keyword': '用户问题与反馈',
            'scan_days': 7,
        }

    def test_pull_uses_latest_matching_message_and_readonly_mailbox(self):
        FakeIMAP.messages = {
            b'1': _message(
                '用户问题与反馈 最新版',
                [('new.csv', b'new', 'text/csv')],
                'Thu, 23 Jul 2026 10:30:00 +0800',
            ),
            b'2': _message(
                '用户问题与反馈 旧版',
                [('old.csv', b'old', 'text/csv')],
                'Thu, 23 Jul 2026 09:30:00 +0800',
            ),
            b'3': _message('其他邮件', [('other.csv', b'other', 'text/csv')]),
        }

        result = server._pull_latest_kb_mail(self._config(), imap_factory=FakeIMAP)

        self.assertEqual(result['subject'], '用户问题与反馈 最新版')
        self.assertEqual(result['attachments'][0]['filename'], 'new.csv')
        self.assertEqual(base64.b64decode(result['attachments'][0]['content_base64']), b'new')
        self.assertEqual(result['sent_at_display'], '2026-07-23 10:30:00+08:00')
        self.assertEqual(FakeIMAP.last_instance.fetched, [b'1', b'2', b'3', b'1'])
        self.assertTrue(FakeIMAP.last_instance.readonly)
        self.assertTrue(FakeIMAP.last_instance.logged_out)

    def test_pull_reuses_only_latest_result_within_ten_minute_cache(self):
        FakeIMAP.messages = {
            b'1': _message('用户问题与反馈 最新版', [('new.csv', b'new', 'text/csv')]),
        }

        first = server._pull_latest_kb_mail(self._config(), imap_factory=FakeIMAP)
        first_fetches = list(FakeIMAP.last_instance.fetched)
        second = server._pull_latest_kb_mail(self._config(), imap_factory=FakeIMAP)
        second_fetches = list(FakeIMAP.last_instance.fetched)

        self.assertFalse(first['cache_hit'])
        self.assertTrue(first['cache_stored'])
        self.assertTrue(second['cache_hit'])
        self.assertEqual(first_fetches, [b'1', b'1'])
        self.assertEqual(second_fetches, [b'1'])

    def test_pull_replaces_cache_when_new_mail_arrives(self):
        FakeIMAP.messages = {
            b'1': _message('用户问题与反馈 旧版', [('old.csv', b'old', 'text/csv')]),
        }
        server._pull_latest_kb_mail(self._config(), imap_factory=FakeIMAP)
        FakeIMAP.messages[b'2'] = _message(
            '用户问题与反馈 新版',
            [('new.csv', b'new', 'text/csv')],
            'Thu, 23 Jul 2026 10:30:00 +0800',
        )

        result = server._pull_latest_kb_mail(self._config(), imap_factory=FakeIMAP)

        self.assertFalse(result['cache_hit'])
        self.assertEqual(result['subject'], '用户问题与反馈 新版')
        self.assertEqual(result['attachments'][0]['filename'], 'new.csv')
        self.assertEqual(FakeIMAP.last_instance.fetched, [b'1', b'2', b'2'])

    def test_pull_discards_expired_cache(self):
        FakeIMAP.messages = {
            b'1': _message('用户问题与反馈 最新版', [('new.csv', b'new', 'text/csv')]),
        }
        server._pull_latest_kb_mail(self._config(), imap_factory=FakeIMAP)
        with server._kb_mail_cache_lock:
            server._kb_mail_cache['expires_at'] = -1

        result = server._pull_latest_kb_mail(self._config(), imap_factory=FakeIMAP)

        self.assertFalse(result['cache_hit'])
        self.assertEqual(FakeIMAP.last_instance.fetched, [b'1', b'1'])

    def test_cache_is_automatically_released_after_ttl(self):
        FakeIMAP.messages = {
            b'1': _message('用户问题与反馈 最新版', [('new.csv', b'new', 'text/csv')]),
        }

        with patch.object(server, '_KB_MAIL_CACHE_TTL_SECONDS', 0.01):
            result = server._pull_latest_kb_mail(self._config(), imap_factory=FakeIMAP)
            time.sleep(0.03)

        self.assertTrue(result['cache_stored'])
        with server._kb_mail_cache_lock:
            self.assertIsNone(server._kb_mail_cache)
            self.assertIsNone(server._kb_mail_cache_timer)

    def test_pull_does_not_cache_attachment_over_memory_limit(self):
        FakeIMAP.messages = {
            b'1': _message('用户问题与反馈 最新版', [('new.csv', b'new', 'text/csv')]),
        }

        with patch.object(server, '_KB_MAIL_CACHE_MAX_BYTES', 2):
            first = server._pull_latest_kb_mail(self._config(), imap_factory=FakeIMAP)
            second = server._pull_latest_kb_mail(self._config(), imap_factory=FakeIMAP)

        self.assertFalse(first['cache_stored'])
        self.assertFalse(second['cache_hit'])
        self.assertEqual(FakeIMAP.last_instance.fetched, [b'1', b'1'])

    def test_pull_skips_newer_matching_message_without_supported_attachment(self):
        FakeIMAP.messages = {
            b'1': _message('用户问题与反馈 旧版', [('old.csv', b'old', 'text/csv')]),
            b'2': _message('用户问题与反馈 最新版', [('notes.txt', b'notes', 'text/plain')]),
        }

        result = server._pull_latest_kb_mail(self._config(), imap_factory=FakeIMAP)

        self.assertEqual(result['subject'], '用户问题与反馈 旧版')
        self.assertEqual(result['attachments'][0]['filename'], 'old.csv')
        self.assertEqual(result['skipped_matching_mails'], 1)

    def test_pull_returns_latest_match_when_no_matching_mail_has_supported_attachment(self):
        FakeIMAP.messages = {
            b'1': _message('用户问题与反馈 旧版', []),
            b'2': _message('用户问题与反馈 最新版', [('notes.txt', b'notes', 'text/plain')]),
        }

        result = server._pull_latest_kb_mail(self._config(), imap_factory=FakeIMAP)

        self.assertEqual(result['subject'], '用户问题与反馈 最新版')
        self.assertEqual(result['attachments'], [])
        self.assertEqual(result['ignored_attachments'][0]['filename'], 'notes.txt')
        self.assertEqual(result['skipped_matching_mails'], 2)

    def test_endpoint_reports_missing_server_configuration(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(
            server,
            '_read_kb_mail_keychain_value',
            return_value='',
        ):
            response = self.client.post('/api/kb/import/mail/latest')

        self.assertEqual(response.status_code, 503)
        self.assertIn('KMATRIX_IMAP_EMAIL', response.get_json()['message'])

    def test_config_uses_latest_kb_as_default_subject_keyword(self):
        with patch.dict(os.environ, {
            'KMATRIX_IMAP_EMAIL': 'kb@example.com',
            'KMATRIX_IMAP_PASSWORD': 'secret',
        }, clear=True):
            config = server._kb_mail_config()

        self.assertEqual(config['keyword'], '最新KB')

    def test_config_reads_credentials_from_macos_keychain(self):
        values = {
            server._KB_MAIL_KEYCHAIN_EMAIL_SERVICE: 'kb@example.com',
            server._KB_MAIL_KEYCHAIN_PASSWORD_SERVICE: 'keychain-secret',
        }
        with patch.dict(os.environ, {}, clear=True), patch.object(
            server,
            '_read_kb_mail_keychain_value',
            side_effect=lambda service: values.get(service, ''),
        ):
            config = server._kb_mail_config()

        self.assertEqual(config['email'], 'kb@example.com')
        self.assertEqual(config['password'], 'keychain-secret')

    @patch.object(server.imaplib, 'IMAP4_SSL', FakeIMAP)
    def test_endpoint_returns_attachment_without_importing_it(self):
        FakeIMAP.messages = {
            b'1': _message('用户问题与反馈 日报', [('daily.xlsx', b'xlsx-content', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')]),
        }
        env = {
            'KMATRIX_IMAP_EMAIL': 'kb@example.com',
            'KMATRIX_IMAP_PASSWORD': 'secret',
            'KMATRIX_IMAP_SUBJECT_KEYWORD': '用户问题与反馈',
        }

        with patch.dict(os.environ, env, clear=True):
            response = self.client.post('/api/kb/import/mail/latest')

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['mail']['sent_at_display'], '2026-07-23 09:30:00+08:00')
        self.assertEqual(data['mail']['attachments'][0]['filename'], 'daily.xlsx')
        self.assertEqual(base64.b64decode(data['mail']['attachments'][0]['content_base64']), b'xlsx-content')


if __name__ == '__main__':
    unittest.main()
