"""
Hermetic test suite for Omi Wikipedia Integration App.
Tests all chat tool endpoints, input coercion, null guards, and error paths.
Uses zero external dependencies (stubs FastAPI/Pydantic if absent).
"""

import asyncio
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

# --- Hermetic stubs for environments without FastAPI/Pydantic installed ---
if "fastapi" not in sys.modules:
    fastapi_mod = ModuleType("fastapi")

    class DummyFastAPI:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda f: f

        def post(self, *args, **kwargs):
            return lambda f: f

    fastapi_mod.FastAPI = DummyFastAPI
    fastapi_responses = ModuleType("fastapi.responses")
    fastapi_responses.HTMLResponse = lambda content, *args, **kwargs: content
    fastapi_mod.responses = fastapi_responses
    sys.modules["fastapi"] = fastapi_mod
    sys.modules["fastapi.responses"] = fastapi_responses

if "pydantic" not in sys.modules:
    pydantic_mod = ModuleType("pydantic")

    class DummyBaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    pydantic_mod.BaseModel = DummyBaseModel
    sys.modules["pydantic"] = pydantic_mod

if "httpx" not in sys.modules:
    httpx_mod = ModuleType("httpx")
    httpx_mod.HTTPError = Exception

    class DummyHTTPStatusError(Exception):
        def __init__(self, message, request=None, response=None):
            super().__init__(message)
            self.request = request
            self.response = response

    httpx_mod.HTTPStatusError = DummyHTTPStatusError
    httpx_mod.TimeoutException = Exception

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs):
            self.is_closed = False

        async def aclose(self):
            self.is_closed = True

        async def get(self, *args, **kwargs):
            raise NotImplementedError

    httpx_mod.AsyncClient = DummyAsyncClient
    sys.modules["httpx"] = httpx_mod

import httpx
import main


def _run(coro):
    return asyncio.run(coro)


class TestInputSanitizationAndHelpers(unittest.TestCase):
    def test_safe_limit_defaults_and_bounds(self):
        self.assertEqual(main._safe_limit(None), 5)
        self.assertEqual(main._safe_limit(""), 5)
        self.assertEqual(main._safe_limit(True), 5)
        self.assertEqual(main._safe_limit(False), 5)
        self.assertEqual(main._safe_limit("invalid"), 5)
        self.assertEqual(main._safe_limit(3), 3)
        self.assertEqual(main._safe_limit("8"), 8)
        self.assertEqual(main._safe_limit(0), 1)
        self.assertEqual(main._safe_limit(50), 10)

    def test_safe_language_validation(self):
        self.assertEqual(main._safe_language(None), "en")
        self.assertEqual(main._safe_language(""), "en")
        self.assertEqual(main._safe_language("pt"), "pt")
        self.assertEqual(main._safe_language("zh-cn"), "zh-cn")
        self.assertEqual(main._safe_language("invalid$lang!"), "en")
        self.assertEqual(main._safe_language("a" * 20), "en")

    def test_clean_snippet(self):
        self.assertEqual(main._clean_snippet(None), "")
        self.assertEqual(main._clean_snippet(""), "")
        snippet = 'The <span class="searchmatch">Python</span> programming language &amp; ecosystem.'
        cleaned = main._clean_snippet(snippet)
        self.assertEqual(cleaned, "The Python programming language & ecosystem.")

    def test_format_summary_with_null_content_urls(self):
        # Regression test: Wikipedia API may return None for content_urls or desktop
        data_null_urls = {
            "title": "Test Article",
            "extract": "This is a summary.",
            "content_urls": None,
        }
        res = main._format_summary(data_null_urls, "en")
        self.assertIn("Test Article", res)
        self.assertIn("This is a summary.", res)
        self.assertIn("https://en.wikipedia.org/wiki/Test_Article", res)

        data_null_desktop = {
            "title": "Test Article 2",
            "extract": "Summary 2.",
            "content_urls": {"desktop": None},
        }
        res2 = main._format_summary(data_null_desktop, "en")
        self.assertIn("Test Article 2", res2)
        self.assertIn("https://en.wikipedia.org/wiki/Test_Article_2", res2)


class TestSearchArticlesEndpoint(unittest.TestCase):
    def test_search_missing_or_empty_query(self):
        res1 = _run(main.search_articles({}))
        self.assertIn("Missing required field: query", res1.error)

        res2 = _run(main.search_articles({"query": "   "}))
        self.assertIn("Missing required field: query", res2.error)

        res3 = _run(main.search_articles(None))
        self.assertIn("Missing required field: query", res3.error)

    def test_search_articles_success(self):
        sample_search_response = {
            "query": {
                "search": [
                    {
                        "title": "Artificial Intelligence",
                        "snippet": 'Research on <span class="searchmatch">AI</span> and machine learning.',
                    }
                ]
            }
        }
        with patch.object(main, "_request_json", new=AsyncMock(return_value=sample_search_response)):
            res = _run(main.search_articles({"query": "AI"}))

        self.assertIsNone(getattr(res, "error", None))
        self.assertIn("Artificial Intelligence", res.result)
        self.assertIn("Research on AI and machine learning.", res.result)
        self.assertIn("https://en.wikipedia.org/wiki/Artificial_Intelligence", res.result)

    def test_search_articles_no_results(self):
        sample_empty = {"query": {"search": []}}
        with patch.object(main, "_request_json", new=AsyncMock(return_value=sample_empty)):
            res = _run(main.search_articles({"query": "nonexistentterm999"}))

        self.assertIsNone(getattr(res, "error", None))
        self.assertEqual(res.result, "No Wikipedia articles found for 'nonexistentterm999'.")

    def test_search_articles_http_error(self):
        mock_resp = SimpleNamespace(status_code=500)
        exc = httpx.HTTPStatusError("500 Internal Server Error", request=None, response=mock_resp)
        with patch.object(main, "_request_json", new=AsyncMock(side_effect=exc)):
            res = _run(main.search_articles({"query": "test"}))

        self.assertIsNone(getattr(res, "result", None))
        self.assertIn("Wikipedia search failed with status 500", res.error)


class TestGetArticleSummaryEndpoint(unittest.TestCase):
    def test_summary_missing_title(self):
        res = _run(main.get_article_summary({}))
        self.assertIn("Missing required field: title", res.error)

        res_none = _run(main.get_article_summary(None))
        self.assertIn("Missing required field: title", res_none.error)

    def test_summary_success(self):
        sample_summary = {
            "title": "Ada Lovelace",
            "description": "English mathematician and writer",
            "extract": "Augusta Ada King, Countess of Lovelace was an English mathematician.",
            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Ada_Lovelace"}},
        }
        with patch.object(main, "_request_json", new=AsyncMock(return_value=sample_summary)):
            res = _run(main.get_article_summary({"title": "Ada Lovelace"}))

        self.assertIsNone(getattr(res, "error", None))
        self.assertIn("Ada Lovelace", res.result)
        self.assertIn("English mathematician and writer", res.result)
        self.assertIn("https://en.wikipedia.org/wiki/Ada_Lovelace", res.result)

    def test_summary_disambiguation(self):
        sample_disambig = {
            "type": "disambiguation",
            "title": "Mercury",
            "extract": "Mercury most often refers to...",
        }
        with patch.object(main, "_request_json", new=AsyncMock(return_value=sample_disambig)):
            res = _run(main.get_article_summary({"title": "Mercury"}))

        self.assertIsNone(getattr(res, "error", None))
        self.assertIn("disambiguation page", res.result)

    def test_summary_not_found_404(self):
        mock_resp = SimpleNamespace(status_code=404)
        exc = httpx.HTTPStatusError("404 Not Found", request=None, response=mock_resp)
        with patch.object(main, "_request_json", new=AsyncMock(side_effect=exc)):
            res = _run(main.get_article_summary({"title": "NonExistentArticle999"}))

        self.assertIsNone(getattr(res, "result", None))
        self.assertIn("No Wikipedia article found for 'NonExistentArticle999'", res.error)


class TestGetRandomArticleEndpoint(unittest.TestCase):
    def test_random_article_success(self):
        sample_random = {"query": {"random": [{"title": "Cosmic Ray"}]}}
        sample_summary = {
            "title": "Cosmic Ray",
            "extract": "Cosmic rays are high-energy particles.",
            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Cosmic_Ray"}},
        }

        async def mock_req(url, params=None):
            if "w/api.php" in url:
                return sample_random
            return sample_summary

        with patch.object(main, "_request_json", new=AsyncMock(side_effect=mock_req)):
            res = _run(main.get_random_article({}))

        self.assertIsNone(getattr(res, "error", None))
        self.assertIn("Random Wikipedia article:", res.result)
        self.assertIn("Cosmic Ray", res.result)

    def test_random_article_empty_response(self):
        sample_empty = {"query": {"random": []}}
        with patch.object(main, "_request_json", new=AsyncMock(return_value=sample_empty)):
            res = _run(main.get_random_article(None))

        self.assertIsNone(getattr(res, "error", None))
        self.assertIn("No random Wikipedia article was returned.", res.result)


class TestHealthAndManifest(unittest.TestCase):
    def test_health_endpoint(self):
        res = _run(main.health())
        self.assertEqual(res, {"status": "ok"})

    def test_manifest_endpoint(self):
        manifest = _run(main.get_omi_tools_manifest())
        self.assertIn("tools", manifest)
        tool_names = [t["name"] for t in manifest["tools"]]
        self.assertIn("search_articles", tool_names)
        self.assertIn("get_article_summary", tool_names)
        self.assertIn("get_random_article", tool_names)


if __name__ == "__main__":
    unittest.main()
