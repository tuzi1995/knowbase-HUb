"""Regression checks for the login control before the large workbench bundle loads."""

from pathlib import Path
import unittest
from unittest.mock import patch

import server
from werkzeug.security import generate_password_hash


ROOT = Path(__file__).resolve().parents[1]
VIEWER = ROOT / "link_viewer"


class LoginBootstrapTests(unittest.TestCase):
    def test_existing_scrypt_hash_requires_compatible_runtime(self):
        self.assertTrue(server._password_hash_requires_scrypt('scrypt:32768:8:1:salt:hash'))
        self.assertFalse(server._password_hash_requires_scrypt('pbkdf2:sha256:100000$salt$hash'))

    def test_incompatible_runtime_fails_when_database_contains_scrypt_hash(self):
        with server.app.app_context(), patch.object(server.hashlib, 'scrypt', None, create=True):
            server.db.create_all()
            with server.db.session.no_autoflush:
                server.db.session.add(server.User(username='runtime-check', password_hash='scrypt:32768:8:1:salt:hash'))
                server.db.session.flush()
            with self.assertRaisesRegex(RuntimeError, '缺少 hashlib.scrypt'):
                server._ensure_password_hash_runtime()
            server.db.session.rollback()

    def test_scrypt_user_can_log_in_and_create_session(self):
        with server.app.app_context():
            server.db.create_all()
            server.db.session.query(server.User).delete()
            server.db.session.add(server.User(
                username='login-regression',
                password_hash=generate_password_hash('isolated-test-password'),
            ))
            server.db.session.commit()

        client = server.app.test_client()
        response = client.post('/login', json={
            'username': 'login-regression',
            'password': 'isolated-test-password',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {'success': True, 'username': 'login-regression'})
        self.assertEqual(client.get('/api/status').get_json(), {
            'logged_in': True,
            'username': 'login-regression',
        })

    def test_login_bootstrap_loads_before_the_main_bundle(self):
        for page_name, bundle_name in (("index.html", "app_v8.js"), ("index.prod.html", "app_v8.min.js")):
            page = (VIEWER / page_name).read_text(encoding="utf-8")
            self.assertIn('id="loginStatus"', page)
            self.assertIn('src="login_bootstrap.js?v=1"', page)
            self.assertLess(page.index('src="login_bootstrap.js?v=1"'), page.index(bundle_name))

    def test_bootstrap_prevents_duplicate_main_bundle_submission(self):
        script = (VIEWER / "login_bootstrap.js").read_text(encoding="utf-8")
        self.assertIn("event.stopImmediatePropagation()", script)
        self.assertIn("credentials: 'same-origin'", script)
        self.assertIn("window.location.reload()", script)


if __name__ == "__main__":
    unittest.main()
