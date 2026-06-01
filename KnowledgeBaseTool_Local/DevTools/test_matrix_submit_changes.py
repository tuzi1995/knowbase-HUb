import time
import unittest
import requests


BASE_URL = "http://127.0.0.1:8080"


class TestMatrixSubmitChangesAPI(unittest.TestCase):
    def setUp(self):
        self.s = requests.Session()
        r = self.s.post(f"{BASE_URL}/login", json={"username": "admin", "password": "123456"}, timeout=10)
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertTrue(data.get("success"), data)

    def test_submit_changes_success_and_idempotent(self):
        wiki_id = f"test_submit_{int(time.time())}"
        product_name = "测试型号"

        r1 = self.s.post(
            f"{BASE_URL}/api/matrix/update",
            json={"question_wiki_id": wiki_id, "product_name": product_name, "is_configured": True},
            timeout=10,
        )
        self.assertEqual(r1.status_code, 200, r1.text)
        self.assertTrue(r1.json().get("success"), r1.json())

        operation_id = f"op_test_{int(time.time())}"
        payload = {
            "operation_id": operation_id,
            "attempt": 1,
            "changes": [
                {
                    "question_wiki_id": wiki_id,
                    "product_name": product_name,
                    "old_is_configured": False,
                    "new_is_configured": True,
                    "edit_source": "cell",
                }
            ],
        }

        r2 = self.s.post(f"{BASE_URL}/api/matrix/submit_changes", json=payload, timeout=20)
        self.assertEqual(r2.status_code, 200, r2.text)
        data2 = r2.json()
        self.assertTrue(data2.get("success"), data2)
        self.assertEqual(data2.get("operation_id"), operation_id)
        self.assertEqual(data2.get("written"), 1)

        r3 = self.s.post(f"{BASE_URL}/api/matrix/submit_changes", json=payload, timeout=20)
        self.assertEqual(r3.status_code, 200, r3.text)
        data3 = r3.json()
        self.assertTrue(data3.get("success"), data3)
        self.assertEqual(data3.get("operation_id"), operation_id)
        self.assertEqual(data3.get("written"), 1)

    def test_submit_changes_conflict(self):
        wiki_id = f"test_conflict_{int(time.time())}"
        product_name = "测试型号"

        r1 = self.s.post(
            f"{BASE_URL}/api/matrix/update",
            json={"question_wiki_id": wiki_id, "product_name": product_name, "is_configured": False},
            timeout=10,
        )
        self.assertEqual(r1.status_code, 200, r1.text)
        self.assertTrue(r1.json().get("success"), r1.json())

        operation_id = f"op_conflict_{int(time.time())}"
        payload = {
            "operation_id": operation_id,
            "attempt": 1,
            "changes": [
                {
                    "question_wiki_id": wiki_id,
                    "product_name": product_name,
                    "old_is_configured": True,
                    "new_is_configured": True,
                    "edit_source": "cell",
                }
            ],
        }

        r2 = self.s.post(f"{BASE_URL}/api/matrix/submit_changes", json=payload, timeout=20)
        self.assertIn(r2.status_code, [400, 500], r2.text)
        data2 = r2.json()
        self.assertFalse(data2.get("success"), data2)


if __name__ == "__main__":
    unittest.main()
