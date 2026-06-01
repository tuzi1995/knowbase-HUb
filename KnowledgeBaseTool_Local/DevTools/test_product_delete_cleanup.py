import time
import unittest
import requests


BASE_URL = "http://127.0.0.1:8080"


class TestProductDeleteCleanup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = requests.Session()
        r = cls.s.post(f"{BASE_URL}/login", json={"username": "admin", "password": "123456"}, timeout=10)
        r.raise_for_status()
        if not r.json().get("success"):
            raise RuntimeError(r.text)

        cls.orig_catalog = cls.s.get(f"{BASE_URL}/api/kb/product_catalog", timeout=10).json()
        cls.orig_mappings = cls.s.get(f"{BASE_URL}/api/model_mappings", timeout=10).json()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.s.post(f"{BASE_URL}/api/kb/product_catalog", json=cls.orig_catalog, timeout=20)
            cls.s.post(f"{BASE_URL}/api/model_mappings", json=cls.orig_mappings, timeout=20)
        except Exception:
            pass

    def test_delete_model_cleans_products_and_mappings(self):
        model = f"测试型号_{int(time.time())}"
        cat = "临时分类"
        map_cat = f"临时映射_{int(time.time())}"
        wiki_id = f"tmp_wiki_{int(time.time())}"

        new_catalog = dict(self.orig_catalog)
        new_catalog.setdefault(cat, [])
        new_catalog[cat] = list(new_catalog[cat]) + [model]
        r1 = self.s.post(f"{BASE_URL}/api/kb/product_catalog", json=new_catalog, timeout=20)
        self.assertEqual(r1.status_code, 200, r1.text)
        self.assertTrue(r1.json().get("success"), r1.text)

        new_mappings = dict(self.orig_mappings)
        new_mappings[map_cat] = [model]
        r2 = self.s.post(f"{BASE_URL}/api/model_mappings", json=new_mappings, timeout=20)
        self.assertEqual(r2.status_code, 200, r2.text)
        self.assertTrue(r2.json().get("success"), r2.text)

        r3 = self.s.post(
            f"{BASE_URL}/api/matrix/update",
            json={"question_wiki_id": wiki_id, "product_name": model, "is_configured": True},
            timeout=10,
        )
        self.assertEqual(r3.status_code, 200, r3.text)
        self.assertTrue(r3.json().get("success"), r3.text)

        deleted_catalog = dict(new_catalog)
        deleted_catalog[cat] = [x for x in deleted_catalog.get(cat, []) if x != model]
        r4 = self.s.post(f"{BASE_URL}/api/kb/product_catalog", json=deleted_catalog, timeout=20)
        self.assertEqual(r4.status_code, 200, r4.text)
        self.assertTrue(r4.json().get("success"), r4.text)

        products = self.s.get(f"{BASE_URL}/api/matrix/products", timeout=10).json()
        all_products = set((products.get("data") or []))
        self.assertNotIn(model, all_products)

        mappings = self.s.get(f"{BASE_URL}/api/model_mappings", timeout=10).json()
        self.assertNotIn(map_cat, mappings)
        for k, v in (mappings or {}).items():
            self.assertNotIn(model, v)


if __name__ == "__main__":
    unittest.main()
