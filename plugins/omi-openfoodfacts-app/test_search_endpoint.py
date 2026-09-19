"""Full-text search endpoint contract (#13190).

Hermetic stdlib-only regression runnable via
``python3 test_search_endpoint.py``; broader coverage lives in test_main.py.
"""

import unittest
from unittest.mock import patch

from test_main import load_app

app = load_app()


class SearchEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_foods_uses_cgi_fulltext_endpoint(self):
        captured = {}

        async def fake_get_async(path, params=None):
            captured["path"] = path
            captured["params"] = params or {}
            return {
                "products": [{"code": "1", "product_name": "Oat milk"}],
                "count": 1,
            }

        with patch.object(app, "_openfoodfacts_get_async", fake_get_async):
            result = await app._search_foods("oat milk", 5)

        self.assertEqual(captured["path"], "/cgi/search.pl")
        self.assertEqual(captured["params"]["search_terms"], "oat milk")
        self.assertEqual(captured["params"]["json"], 1)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["products"][0]["name"], "Oat milk")


if __name__ == "__main__":
    unittest.main()
