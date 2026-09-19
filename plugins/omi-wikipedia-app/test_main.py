"""
Hermetic test suite for the Omi Wikipedia integration app.

Exercises endpoint handlers, string sanitization, null safety, HTML stripping,
and tools manifest without requiring third-party libraries (httpx, fastapi, pydantic).
Can run cleanly in isolated python3 environments (e.g., under python3 -S).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import AsyncMock, patch


def load_app():
    class FastAPI:
        def __init__(self, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda handler: handler

        post = get

    class BaseModel:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class HTTPError(Exception):
        pass

    class HTTPStatusError(HTTPError):
        def __init__(self, message="", *, request=None, response=None):
            super().__init__(message)
            self.response = response

    httpx = ModuleType("httpx")
    httpx.AsyncClient = object
    httpx.HTTPError = HTTPError
    httpx.HTTPStatusError = HTTPStatusError

    fastapi = ModuleType("fastapi")
    fastapi.FastAPI = FastAPI
    responses = ModuleType("fastapi.responses")
    responses.HTMLResponse = str
    pydantic = ModuleType("pydantic")
    pydantic.BaseModel = BaseModel

    spec = importlib.util.spec_from_file_location(
        "omi_wikipedia_main", Path(__file__).with_name("main.py")
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "httpx": httpx,
            "fastapi": fastapi,
            "fastapi.responses": responses,
            "pydantic": pydantic,
        },
    ):
        spec.loader.exec_module(module)
    return module


app = load_app()


class WikipediaUnitHelperTests(unittest.TestCase):
    def test_safe_limit_defaults_and_bounds(self):
        self.assertEqual(app._safe_limit(None), 5)
        self.assertEqual(app._safe_limit(""), 5)
        self.assertEqual(app._safe_limit("invalid"), 5)
        self.assertEqual(app._safe_limit(0), 1)
        self.assertEqual(app._safe_limit(-10), 1)
        self.assertEqual(app._safe_limit(7), 7)
        self.assertEqual(app._safe_limit("7"), 7)
        self.assertEqual(app._safe_limit(15), 10)

    def test_safe_language_sanitization(self):
        self.assertEqual(app._safe_language(None), "en")
        self.assertEqual(app._safe_language(""), "en")
        self.assertEqual(app._safe_language("   "), "en")
        self.assertEqual(app._safe_language("fr"), "fr")
        self.assertEqual(app._safe_language("ES"), "es")
        self.assertEqual(app._safe_language("zh-cn"), "zh-cn")
        self.assertEqual(app._safe_language("invalid_lang!"), "en")
        self.assertEqual(app._safe_language("toolonglanguagecode"), "en")

    def test_clean_snippet_strips_html_and_unescapes(self):
        self.assertEqual(app._clean_snippet(None), "")
        self.assertEqual(app._clean_snippet(""), "")
        snippet = '<span class="searchmatch">Albert</span> Einstein &amp; Niels Bohr'
        self.assertEqual(app._clean_snippet(snippet), "Albert Einstein & Niels Bohr")

    def test_article_url_encoding(self):
        url = app._article_url("en", "Albert Einstein")
        self.assertEqual(url, "https://en.wikipedia.org/wiki/Albert_Einstein")
        url_special = app._article_url("fr", "Café & Thé")
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
        formatted = app._format_summary(data_full, "en")
        self.assertIn("Quantum mechanics", formatted)
        self.assertIn("Branch of physics", formatted)
        self.assertIn("https://en.wikipedia.org/wiki/Quantum_mechanics", formatted)

        # Regressions: None content_urls or None desktop must not raise AttributeError
        data_none_urls = {"title": "Null URLs", "content_urls": None}
        formatted_none = app._format_summary(data_none_urls, "en")
        self.assertIn("Null URLs", formatted_none)
        self.assertIn("https://en.wikipedia.org/wiki/Null_URLs", formatted_none)

        data_none_desktop = {"title": "Null Desktop", "content_urls": {"desktop": None}}
        formatted_desktop = app._format_summary(data_none_desktop, "en")
        self.assertIn("Null Desktop", formatted_desktop)
        self.assertIn("https://en.wikipedia.org/wiki/Null_Desktop", formatted_desktop)


class WikipediaEndpointAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_root_endpoint(self):
        res = await app.root()
        self.assertIn("Wikipedia x Omi", res)

    async def test_health_endpoint(self):
        res = await app.health()
        self.assertEqual(res, {"status": "ok"})

    async def test_tools_manifest(self):
        res = await app.get_omi_tools_manifest()
        self.assertIn("tools", res)
        tool_names = [t["name"] for t in res["tools"]]
        self.assertIn("search_articles", tool_names)
        self.assertIn("get_article_summary", tool_names)
        self.assertIn("get_random_article", tool_names)

        for t in res["tools"]:
            self.assertEqual(t["parameters"]["type"], "object")
            self.assertIn("properties", t["parameters"])

    async def test_search_articles_missing_query(self):
        res = await app.search_articles({})
        self.assertEqual(res.error, "Missing required field: query")

        res_empty = await app.search_articles({"query": "   "})
        self.assertEqual(res_empty.error, "Missing required field: query")

    async def test_search_articles_success(self):
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
        with patch.object(app, "_request_json", AsyncMock(return_value=mock_data)) as mock_req:
            res = await app.search_articles({"query": "AI", "limit": 3})
            self.assertIsNone(res.error)
            mock_req.assert_awaited_once()
            self.assertIn("Wikipedia search results for 'AI':", res.result)
            self.assertIn("1. Artificial intelligence", res.result)
            self.assertIn("Intelligence demonstrated by machines.", res.result)
            self.assertIn("https://en.wikipedia.org/wiki/Artificial_intelligence", res.result)

    async def test_search_articles_no_results(self):
        mock_data = {"query": {"search": []}}
        with patch.object(app, "_request_json", AsyncMock(return_value=mock_data)):
            res = await app.search_articles({"query": "xyz123nonsense456"})
            self.assertIsNone(res.error)
            self.assertIn("No Wikipedia articles found", res.result)

    async def test_search_articles_malformed_query_dict(self):
        mock_data = {"query": None}
        with patch.object(app, "_request_json", AsyncMock(return_value=mock_data)):
            res = await app.search_articles({"query": "something"})
            self.assertIsNone(res.error)
            self.assertIn("No Wikipedia articles found", res.result)

    async def test_get_article_summary_missing_title(self):
        res = await app.get_article_summary({})
        self.assertEqual(res.error, "Missing required field: title")

    async def test_get_article_summary_success(self):
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
        with patch.object(app, "_request_json", AsyncMock(return_value=mock_data)):
            res = await app.get_article_summary({"title": "Python (programming language)"})
            self.assertIsNone(res.error)
            self.assertIn("Python (programming language)", res.result)
            self.assertIn("High-level programming language", res.result)

    async def test_get_article_summary_disambiguation(self):
        mock_data = {
            "type": "disambiguation",
            "title": "Mercury",
            "extract": "Mercury most often refers to...",
        }
        with patch.object(app, "_request_json", AsyncMock(return_value=mock_data)):
            res = await app.get_article_summary({"title": "Mercury"})
            self.assertIsNone(res.error)
            self.assertIn("This is a disambiguation page", res.result)

    async def test_get_random_article_success(self):
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
        with patch.object(app, "_request_json", AsyncMock(side_effect=[mock_random, mock_summary])):
            res = await app.get_random_article({})
            self.assertIsNone(res.error)
            self.assertIn("Random Wikipedia article:", res.result)
            self.assertIn("Random Article Title", res.result)

    async def test_get_random_article_empty_response(self):
        mock_random = {"query": {"random": []}}
        with patch.object(app, "_request_json", AsyncMock(return_value=mock_random)):
            res = await app.get_random_article({})
            self.assertIsNone(res.error)
            self.assertIn("No random Wikipedia article was returned", res.result)

    async def test_search_articles_non_dict_items(self):
        mock_data = {
            "query": {
                "search": [
                    None,
                    "malformed_item",
                    {"title": "Valid Article", "snippet": "A good snippet"},
                    123,
                ]
            }
        }
        with patch.object(app, "_request_json", AsyncMock(return_value=mock_data)):
            res = await app.search_articles({"query": "valid test"})
            self.assertIsNone(res.error)
            self.assertIn("Valid Article", res.result)
            self.assertIn("A good snippet", res.result)

    async def test_get_random_article_non_dict_items(self):
        mock_random = {
            "query": {
                "random": [
                    None,
                    "invalid",
                    {"id": 1234, "title": "Recovered Random Title"},
                ]
            }
        }
        mock_summary = {
            "title": "Recovered Random Title",
            "extract": "Summary for recovered random article.",
        }
        with patch.object(app, "_request_json", AsyncMock(side_effect=[mock_random, mock_summary])):
            res = await app.get_random_article({})
            self.assertIsNone(res.error)
            self.assertIn("Random Wikipedia article:", res.result)
            self.assertIn("Recovered Random Title", res.result)


if __name__ == "__main__":
    unittest.main()
