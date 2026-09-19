"""
Hermetic regression tests for Omi Wikipedia App.
"""

import unittest
from unittest.mock import AsyncMock, patch
import httpx
from fastapi.testclient import TestClient

# 引入被测应用
import main


class TestOmiWikipediaApp(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    def test_health_check(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_tools_manifest(self):
        response = self.client.get("/.well-known/omi-tools.json")
        self.assertEqual(response.status_code, 200)
        manifest = response.json()
        self.assertIn("tools", manifest)
        self.assertEqual(len(manifest["tools"]), 3)
        tool_names = [t["name"] for t in manifest["tools"]]
        self.assertIn("search_articles", tool_names)
        self.assertIn("get_article_summary", tool_names)
        self.assertIn("get_random_article", tool_names)

    @patch("main_wiki._request_json", new_callable=AsyncMock)
    def test_search_articles_success(self, mock_request):
        mock_request.return_value = {
            "query": {
                "search": [
                    {"title": "Artificial intelligence", "snippet": "<span>AI</span> is smart."}
                ]
            }
        }
        response = self.client.post("/tools/search_articles", json={"query": "AI"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("Artificial intelligence", data["result"])
        self.assertIn("AI is smart.", data["result"])
        self.assertIsNone(data["error"])

    def test_search_articles_missing_query(self):
        response = self.client.post("/tools/search_articles", json={"query": ""})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("Missing required field: query", data["error"])

    def test_search_articles_null_payload(self):
        response = self.client.post("/tools/search_articles", json=None)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("Missing required field: query", data["error"])

    @patch("main_wiki._request_json", new_callable=AsyncMock)
    def test_get_article_summary_success(self, mock_request):
        mock_request.return_value = {
            "title": "Python",
            "description": "Programming language",
            "extract": "Python is high-level.",
            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Python"}}
        }
        response = self.client.post("/tools/get_article_summary", json={"title": "Python"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("Python", data["result"])
        self.assertIn("Programming language", data["result"])
        self.assertIn("Python is high-level.", data["result"])
        self.assertIsNone(data["error"])

    @patch("main_wiki._request_json", new_callable=AsyncMock)
    def test_get_article_summary_404(self, mock_request):
        mock_response = httpx.Response(404, request=httpx.Request("GET", "https://en.wikipedia.org"))
        mock_request.side_effect = httpx.HTTPStatusError("Not Found", request=mock_response.request, response=mock_response)

        response = self.client.post("/tools/get_article_summary", json={"title": "NonExistentThing123"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("No Wikipedia article found", data["error"])

    @patch("main_wiki._request_json", new_callable=AsyncMock)
    def test_get_random_article_success_and_empty_payload(self, mock_request):
        mock_request.side_effect = [
            {"query": {"random": [{"title": "Serendipity"}]}},
            {
                "title": "Serendipity",
                "extract": "An unplanned fortunate discovery.",
                "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Serendipity"}}
            }
        ]
        # 测试空载荷以及空请求体均不报错
        response = self.client.post("/tools/get_random_article", json=None)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("Random Wikipedia article:", data["result"])
        self.assertIn("Serendipity", data["result"])
        self.assertIsNone(data["error"])

    def test_safe_helpers(self):
        self.assertEqual(main._safe_limit(None), 5)
        self.assertEqual(main._safe_limit(""), 5)
        self.assertEqual(main._safe_limit("invalid"), 5)
        self.assertEqual(main._safe_limit(100), 10) # 限制在 MAX_LIMIT
        self.assertEqual(main._safe_limit(-5), 1)

        self.assertEqual(main._safe_language(None), "en")
        self.assertEqual(main._safe_language(""), "en")
        self.assertEqual(main._safe_language("  FR  "), "fr")
        self.assertEqual(main._safe_language("invalid_long_string_1234567"), "en")


if __name__ == "__main__":
    unittest.main()
