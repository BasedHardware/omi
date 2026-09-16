"""
Unit test suite for the Omi Wikipedia integration app.

Tests endpoint routing, query formatting, HTML snippet cleaning,
parameter sanitization, null safety, error handling, and mock API calls.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:
    TestClient = None

sys.path.insert(0, str(Path(__file__).resolve().parent))

_SPEC = importlib.util.spec_from_file_location(
    "omi_wikipedia_main", Path(__file__).with_name("main.py")
)
assert _SPEC is not None and _SPEC.loader is not None
main = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = main
_SPEC.loader.exec_module(main)


class WikipediaUnitHelperTests(unittest.TestCase):
    def test_safe_limit_defaults_and_bounds(self):
        self.assertEqual(main._safe_limit(None), 5)
        self.assertEqual(main._safe_limit(""), 5)
        self.assertEqual(main._safe_limit("invalid"), 5)
        self.assertEqual(main._safe_limit(0), 1)
        self.assertEqual(main._safe_limit(-10), 1)
        self.assertEqual(main._safe_limit(7), 7)
        self.assertEqual(main._safe_limit("7"), 7)
        self.assertEqual(main._safe_limit(15), 10)

    def test_safe_language_sanitization(self):
        self.assertEqual(main._safe_language(None), "en")
        self.assertEqual(main._safe_language(""), "en")
        self.assertEqual(main._safe_language("   "), "en")
        self.assertEqual(main._safe_language("fr"), "fr")
        self.assertEqual(main._safe_language("ES"), "es")
        self.assertEqual(main._safe_language("zh-cn"), "zh-cn")
        self.assertEqual(main._safe_language("invalid_lang!"), "en")
        self.assertEqual(main._safe_language("toolonglanguagecode"), "en")

    def test_clean_snippet_strips_html_and_unescapes(self):
        self.assertEqual(main._clean_snippet(None), "")
        self.assertEqual(main._clean_snippet(""), "")
        snippet = '<span class="searchmatch">Albert</span> Einstein &amp; Niels Bohr'
        self.assertEqual(main._clean_snippet(snippet), "Albert Einstein & Niels Bohr")

    def test_article_url_encoding(self):
        url = main._article_url("en", "Albert Einstein")
        self.assertEqual(url, "https://en.wikipedia.org/wiki/Albert_Einstein")
        url_special = main._article_url("fr", "Café & Thé")
        self.assertEqual(url_special, "https://fr.wikipedia.org/wiki/Caf%C3%A9_%26_Th%C3%A9")

    def test_format_summary_null_safety(self):
        # Full payload
        data_full = {
            "title": "Quantum mechanics",
            "description": "Branch of physics",
            "extract": "Quantum mechanics is a fundamental theory in physics.",
            "content_urls": {
                "desktop": {
                    "page": "https://en.wikipedia.org/wiki/Quantum_mechanics"
                }
            },
        }
        formatted = main._format_summary(data_full, "en")
        self.assertIn("Quantum mechanics", formatted)
        self.assertIn("Branch of physics", formatted)
        self.assertIn("https://en.wikipedia.org/wiki/Quantum_mechanics", formatted)

        # Regressions: None content_urls or None desktop must not raise AttributeError
        data_none_urls = {"title": "Null URLs", "content_urls": None}
        formatted_none = main._format_summary(data_none_urls, "en")
        self.assertIn("Null URLs", formatted_none)
        self.assertIn("https://en.wikipedia.org/wiki/Null_URLs", formatted_none)

        data_none_desktop = {"title": "Null Desktop", "content_urls": {"desktop": None}}
        formatted_desktop = main._format_summary(data_none_desktop, "en")
        self.assertIn("Null Desktop", formatted_desktop)
        self.assertIn("https://en.wikipedia.org/wiki/Null_Desktop", formatted_desktop)


@unittest.skipIf(TestClient is None, "fastapi/httpx test dependencies are not installed")
class WikipediaEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    def test_root_endpoint(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Wikipedia x Omi", res.text)

    def test_health_endpoint(self):
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "ok"})

    def test_tools_manifest(self):
        res = self.client.get("/.well-known/omi-tools.json")
        self.assertEqual(res.status_code, 200)
        tools = res.json()["tools"]
        tool_names = [t["name"] for t in tools]
        self.assertIn("search_articles", tool_names)
        self.assertIn("get_article_summary", tool_names)
        self.assertIn("get_random_article", tool_names)

        # Validate JSON schema structure
        for t in tools:
            self.assertEqual(t["parameters"]["type"], "object")
            self.assertIn("properties", t["parameters"])

    def test_search_articles_missing_query(self):
        res = self.client.post("/tools/search_articles", json={})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["error"], "Missing required field: query")

        res_empty = self.client.post("/tools/search_articles", json={"query": "   "})
        self.assertEqual(res_empty.status_code, 200)
        self.assertEqual(res_empty.json()["error"], "Missing required field: query")

    def test_search_articles_success(self):
        mock_data = {
            "query": {
                "search": [
                    {
                        "title": "Artificial intelligence",
                        "snippet": "Intelligence demonstrated by <span class=\"searchmatch\">machines</span>.",
                    }
                ]
            }
        }
        with mock.patch.object(main, "_request_json", return_value=mock_data) as mock_req:
            res = self.client.post("/tools/search_articles", json={"query": "AI", "limit": 3})
            self.assertEqual(res.status_code, 200)
            mock_req.assert_called_once()
            result = res.json()["result"]
            self.assertIn("Wikipedia search results for 'AI':", result)
            self.assertIn("1. Artificial intelligence", result)
            self.assertIn("Intelligence demonstrated by machines.", result)
            self.assertIn("https://en.wikipedia.org/wiki/Artificial_intelligence", result)

    def test_search_articles_no_results(self):
        mock_data = {"query": {"search": []}}
        with mock.patch.object(main, "_request_json", return_value=mock_data):
            res = self.client.post("/tools/search_articles", json={"query": "xyz123nonsense456"})
            self.assertEqual(res.status_code, 200)
            self.assertIn("No Wikipedia articles found", res.json()["result"])

    def test_search_articles_malformed_query_dict(self):
        # Query payload returning null query field or non-list search
        mock_data = {"query": None}
        with mock.patch.object(main, "_request_json", return_value=mock_data):
            res = self.client.post("/tools/search_articles", json={"query": "something"})
            self.assertEqual(res.status_code, 200)
            self.assertIn("No Wikipedia articles found", res.json()["result"])

    def test_get_article_summary_missing_title(self):
        res = self.client.post("/tools/get_article_summary", json={})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["error"], "Missing required field: title")

    def test_get_article_summary_success(self):
        mock_data = {
            "title": "Python (programming language)",
            "description": "High-level programming language",
            "extract": "Python is a high-level general-purpose programming language.",
            "content_urls": {
                "desktop": {
                    "page": "https://en.wikipedia.org/wiki/Python_(programming_language)"
                }
            },
        }
        with mock.patch.object(main, "_request_json", return_value=mock_data):
            res = self.client.post(
                "/tools/get_article_summary", json={"title": "Python (programming language)"}
            )
            self.assertEqual(res.status_code, 200)
            result = res.json()["result"]
            self.assertIn("Python (programming language)", result)
            self.assertIn("High-level programming language", result)

    def test_get_article_summary_disambiguation(self):
        mock_data = {
            "type": "disambiguation",
            "title": "Mercury",
            "extract": "Mercury most often refers to...",
        }
        with mock.patch.object(main, "_request_json", return_value=mock_data):
            res = self.client.post("/tools/get_article_summary", json={"title": "Mercury"})
            self.assertEqual(res.status_code, 200)
            result = res.json()["result"]
            self.assertIn("This is a disambiguation page", result)

    def test_get_random_article_success(self):
        mock_random = {
            "query": {
                "random": [
                    {"id": 999, "title": "Random Article Title"}
                ]
            }
        }
        mock_summary = {
            "title": "Random Article Title",
            "extract": "A fascinating random topic.",
        }
        with mock.patch.object(main, "_request_json", side_effect=[mock_random, mock_summary]):
            res = self.client.post("/tools/get_random_article", json={})
            self.assertEqual(res.status_code, 200)
            result = res.json()["result"]
            self.assertIn("Random Wikipedia article:", result)
            self.assertIn("Random Article Title", result)

    def test_get_random_article_empty_response(self):
        mock_random = {"query": {"random": []}}
        with mock.patch.object(main, "_request_json", return_value=mock_random):
            res = self.client.post("/tools/get_random_article", json={})
            self.assertEqual(res.status_code, 200)
            self.assertIn("No random Wikipedia article was returned", res.json()["result"])


if __name__ == "__main__":
    unittest.main()
