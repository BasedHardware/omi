import unittest
from unittest.mock import AsyncMock, patch
import sys
from pathlib import Path

# Add current dir to path to import main
sys.path.insert(0, str(Path(__file__).parent))
import main

class WikipediaPluginTests(unittest.IsolatedAsyncioTestCase):
    def test_safe_language_valid(self):
        self.assertEqual(main._safe_language("en"), "en")
        self.assertEqual(main._safe_language("es"), "es")
        self.assertEqual(main._safe_language("zh-cn"), "zh-cn")
        self.assertEqual(main._safe_language("pt-br"), "pt-br")

    def test_safe_language_invalid_or_non_string(self):
        self.assertEqual(main._safe_language(None), "en")
        self.assertEqual(main._safe_language(""), "en")
        self.assertEqual(main._safe_language(123), "en")
        self.assertEqual(main._safe_language(["en"]), "en")
        self.assertEqual(main._safe_language("-en"), "en")
        self.assertEqual(main._safe_language("en-"), "en")
        self.assertEqual(main._safe_language("ß"), "en")
        self.assertEqual(main._safe_language("мо"), "en")
        self.assertEqual(main._safe_language("a" * 20), "en")

    def test_article_url_escapes_slashes(self):
        url = main._article_url("en", "../../../../w/api.php")
        self.assertNotIn("/../../../../", url)
        self.assertIn("%2F", url)

    async def test_search_articles_non_string_query(self):
        cases = [2026, 3.5, ["ai"], {"q": "ai"}, True, False, None, "", "   "]
        for bad_query in cases:
            with self.subTest(query=bad_query):
                res = await main.search_articles({"query": bad_query})
                self.assertEqual(res.error, "Missing required field: query")
                self.assertIsNone(res.result)

    async def test_get_article_summary_non_string_title(self):
        cases = [2026, 3.5, ["ai"], {"q": "ai"}, True, False, None, "", "   "]
        for bad_title in cases:
            with self.subTest(title=bad_title):
                res = await main.get_article_summary({"title": bad_title})
                self.assertEqual(res.error, "Missing required field: title")
                self.assertIsNone(res.result)

if __name__ == "__main__":
    unittest.main()
