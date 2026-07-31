"""Regression checks for the login control before the large workbench bundle loads."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
VIEWER = ROOT / "link_viewer"


class LoginBootstrapTests(unittest.TestCase):
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
