"""Hermetic unit tests for Wikipedia Omi integration.

No third-party runtime dependencies required. Runs deterministically under
both standard library `python3 -S` and `pytest`.
"""

import asyncio
from contextlib import asynccontextmanager
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch
from urllib.parse import unquote


def load_app():
    class DummyFastAPI:
        def __init__(self, **kwargs):
            self.routes = []
            self.lifespan = kwargs.get("lifespan")

        def get(self, path, **kwargs):
            return self._route("GET", path, kwargs.get("response_model"))

        def post(self, path, **kwargs):
            return self._route("POST", path, kwargs.get("response_model"))

        def _route(self, method, path, response_model):
            def decorator(func):
                self.routes.append({
                    "method": method,
                    "path": path,
                    "func": func,
                    "response_model": response_model,
                })
                return func

            return decorator

    class DummyBaseModel:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

    class HTTPError(Exception):
        pass

    class HTTPStatusError(HTTPError):
        def __init__(self, message=None, response=None):
            super().__init__(message)
            self.response = response or types.SimpleNamespace(status_code=500)

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs):
            self.is_closed = False

        async def aclose(self):
            self.is_closed = True

        async def get(self, url, params=None):
            raise NotImplementedError

    fastapi = types.ModuleType("fastapi")
    fastapi.FastAPI = DummyFastAPI
    fastapi.Request = object
    fastapi_responses = types.ModuleType("fastapi.responses")
    fastapi_responses.HTMLResponse = str

    pydantic = types.ModuleType("pydantic")
    pydantic.BaseModel = DummyBaseModel

    httpx = types.ModuleType("httpx")
    httpx.HTTPError = HTTPError
    httpx.HTTPStatusError = HTTPStatusError
    httpx.AsyncClient = DummyAsyncClient

    spec = importlib.util.spec_from_file_location("wikipedia_app_hermetic", Path(__file__).with_name("main.py"))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "fastapi": fastapi,
            "fastapi.responses": fastapi_responses,
            "pydantic": pydantic,
            "httpx": httpx,
        },
    ):
        spec.loader.exec_module(module)
    return module


main = load_app()


class RouteWiringTests(unittest.TestCase):
    def test_routes_registered_with_correct_methods_and_paths(self):
        registered = {(r["method"], r["path"]): r for r in main.app.routes}
        expected_endpoints = {
            ("GET", "/"),
            ("GET", "/health"),
            ("GET", "/.well-known/omi-tools.json"),
            ("POST", "/tools/search_articles"),
            ("POST", "/tools/get_article_summary"),
            ("POST", "/tools/get_random_article"),
        }
        for endpoint in expected_endpoints:
            self.assertIn(endpoint, registered)

        self.assertIs(registered[("POST", "/tools/search_articles")]["response_model"], main.ChatToolResponse)
        self.assertIs(registered[("POST", "/tools/get_article_summary")]["response_model"], main.ChatToolResponse)
        self.assertIs(registered[("POST", "/tools/get_random_article")]["response_model"], main.ChatToolResponse)

    def test_tools_manifest_matches_registered_routes(self):
        manifest = asyncio.run(main.get_omi_tools_manifest())
        tools = manifest["tools"]
        self.assertEqual(len(tools), 3)
        tool_endpoints = {t["endpoint"]: t["method"] for t in tools}
        self.assertEqual(
            tool_endpoints,
            {
                "/tools/search_articles": "POST",
                "/tools/get_article_summary": "POST",
                "/tools/get_random_article": "POST",
            },
        )

    def test_root_and_health_endpoints(self):
        health_resp = asyncio.run(main.health())
        self.assertEqual(health_resp, {"status": "ok"})

        root_resp = asyncio.run(main.root())
        self.assertIn("Wikipedia x Omi", root_resp)


class HelperFunctionTests(unittest.TestCase):
    def test_safe_limit(self):
        self.assertEqual(main._safe_limit(None), 5)
        self.assertEqual(main._safe_limit(""), 5)
        self.assertEqual(main._safe_limit("invalid"), 5)
        self.assertEqual(main._safe_limit(0), 1)
        self.assertEqual(main._safe_limit(-10), 1)
        self.assertEqual(main._safe_limit(7), 7)
        self.assertEqual(main._safe_limit("8"), 8)
        self.assertEqual(main._safe_limit(100), 10)

    def test_safe_language(self):
        self.assertEqual(main._safe_language(None), "en")
        self.assertEqual(main._safe_language(""), "en")
        self.assertEqual(main._safe_language("   "), "en")
        self.assertEqual(main._safe_language("FR"), "fr")
        self.assertEqual(main._safe_language("zh-cn"), "zh-cn")
        self.assertEqual(main._safe_language("../../etc/passwd"), "en")
        self.assertEqual(main._safe_language("very-long-language-tag-exceeding-limit"), "en")

    def test_article_url(self):
        url = main._article_url("en", "Albert Einstein")
        self.assertEqual(url, "https://en.wikipedia.org/wiki/Albert_Einstein")

        url_special = main._article_url("ja", "初音ミク")
        self.assertIn("https://ja.wikipedia.org/wiki/", url_special)

    def test_clean_snippet(self):
        self.assertEqual(main._clean_snippet(None), "")
        self.assertEqual(main._clean_snippet(123), "")
        raw = '<span>Albert</span> Einstein was a <b>physicist</b> &amp; mathematician.'
        cleaned = main._clean_snippet(raw)
        self.assertEqual(cleaned, "Albert Einstein was a physicist & mathematician.")

    def test_format_summary_valid(self):
        data = {
            "title": "Quantum computing",
            "description": "Subfield of computer science",
            "extract": "Quantum computing is a rapidly-emerging technology.",
            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Quantum_computing"}},
        }
        res = main._format_summary(data, "en")
        self.assertIn("Quantum computing", res)
        self.assertIn("Subfield of computer science", res)
        self.assertIn("Quantum computing is a rapidly-emerging technology.", res)
        self.assertIn("https://en.wikipedia.org/wiki/Quantum_computing", res)

    def test_format_summary_non_dict_payload(self):
        self.assertEqual(main._format_summary(None, "en"), "No summary was returned for this article.")
        self.assertEqual(main._format_summary("error string", "en"), "No summary was returned for this article.")

    def test_format_summary_malformed_urls(self):
        data = {
            "title": "Black hole",
            "extract": "A region of spacetime where gravity is so strong that nothing can escape.",
            "content_urls": None,
        }
        res = main._format_summary(data, "en")
        self.assertIn("Black hole", res)
        self.assertIn("https://en.wikipedia.org/wiki/Black_hole", res)


class WikipediaToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_articles_success(self):
        mock_data = {
            "query": {
                "search": [
                    {"title": "Python (programming language)", "snippet": "A high-level <b>language</b>."},
                    {"title": "Python (genus)", "snippet": "A genus of nonvenomous snakes."},
                ]
            }
        }
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_data
            resp = await main.search_articles({"query": "python", "limit": 2})
            self.assertIsNone(resp.error)
            self.assertIn("Wikipedia search results for 'python':", resp.result)
            self.assertIn("1. Python (programming language)", resp.result)
            self.assertIn("2. Python (genus)", resp.result)

    async def test_search_articles_empty_query(self):
        resp = await main.search_articles({"query": "   "})
        self.assertEqual(resp.error, "Missing required field: query")

        resp_none = await main.search_articles({"query": None})
        self.assertEqual(resp_none.error, "Missing required field: query")

        resp_non_dict = await main.search_articles("not-a-dict")
        self.assertEqual(resp_non_dict.error, "Missing required field: query")

    async def test_search_articles_empty_results(self):
        mock_data = {"query": {"search": []}}
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_data
            resp = await main.search_articles({"query": "nonexistentquery12345"})
            self.assertIsNone(resp.error)
            self.assertIn("No Wikipedia articles found for 'nonexistentquery12345'.", resp.result)

    async def test_search_articles_non_dict_api_payload(self):
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = "<html>Gateway Timeout</html>"
            resp = await main.search_articles({"query": "test"})
            self.assertIsNone(resp.error)
            self.assertIn("No Wikipedia articles found for 'test'.", resp.result)

    async def test_search_articles_null_query_in_response(self):
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"query": None}
            resp = await main.search_articles({"query": "test"})
            self.assertIsNone(resp.error)
            self.assertIn("No Wikipedia articles found for 'test'.", resp.result)

    async def test_search_articles_malformed_search_items(self):
        mock_data = {
            "query": {
                "search": [
                    "invalid-scalar-item",
                    {"title": "Valid Article", "snippet": "A valid snippet"},
                ]
            }
        }
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_data
            resp = await main.search_articles({"query": "valid"})
            self.assertIsNone(resp.error)
            self.assertIn("1. Valid Article", resp.result)

    async def test_search_articles_http_error(self):
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            response = types.SimpleNamespace(status_code=503)
            mock_req.side_effect = main.httpx.HTTPStatusError("Service Unavailable", response=response)
            resp = await main.search_articles({"query": "fail"})
            self.assertIn("Wikipedia search failed with status 503.", resp.error)

    async def test_get_article_summary_success(self):
        mock_data = {
            "type": "standard",
            "title": "NixOS",
            "description": "Linux distribution based on the Nix package manager",
            "extract": "NixOS is a free and open-source Linux distribution.",
            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/NixOS"}},
        }
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_data
            resp = await main.get_article_summary({"title": "NixOS"})
            self.assertIsNone(resp.error)
            self.assertIn("NixOS", resp.result)
            self.assertIn("Linux distribution based on the Nix package manager", resp.result)
            self.assertIn("https://en.wikipedia.org/wiki/NixOS", resp.result)

    async def test_get_article_summary_disambiguation(self):
        mock_data = {
            "type": "disambiguation",
            "title": "Mercury",
            "description": "Topics referred to by the same term",
            "extract": "Mercury most commonly refers to the chemical element or the planet.",
            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Mercury"}},
        }
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_data
            resp = await main.get_article_summary({"title": "Mercury"})
            self.assertIsNone(resp.error)
            self.assertIn("This is a disambiguation page. Use search_articles for more specific matches.", resp.result)

    async def test_get_article_summary_missing_title(self):
        resp = await main.get_article_summary({"title": ""})
        self.assertEqual(resp.error, "Missing required field: title")

        resp_non_dict = await main.get_article_summary(None)
        self.assertEqual(resp_non_dict.error, "Missing required field: title")

    async def test_get_article_summary_404(self):
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            response = types.SimpleNamespace(status_code=404)
            mock_req.side_effect = main.httpx.HTTPStatusError("Not Found", response=response)
            resp = await main.get_article_summary({"title": "Unknown Article 9999"})
            self.assertIn("No Wikipedia article found for 'Unknown Article 9999'.", resp.error)

    async def test_get_article_summary_non_dict_response(self):
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = None
            resp = await main.get_article_summary({"title": "Test"})
            self.assertIn("No Wikipedia article found for 'Test'. Try search_articles first.", resp.error)

    async def test_get_random_article_success(self):
        query_mock = {"query": {"random": [{"title": "Voyager 1"}]}}
        summary_mock = {
            "title": "Voyager 1",
            "description": "Space probe launched by NASA",
            "extract": "Voyager 1 is a space probe launched by NASA on September 5, 1977.",
            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Voyager_1"}},
        }
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = [query_mock, summary_mock]
            resp = await main.get_random_article({})
            self.assertIsNone(resp.error)
            self.assertIn("Random Wikipedia article:", resp.result)
            self.assertIn("Voyager 1", resp.result)
            self.assertIn("Space probe launched by NASA", resp.result)

    async def test_get_random_article_empty_random(self):
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"query": {"random": []}}
            resp = await main.get_random_article({})
            self.assertEqual(resp.result, "No random Wikipedia article was returned.")

    async def test_get_random_article_missing_title(self):
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"query": {"random": [{"title": ""}]}}
            resp = await main.get_random_article({})
            self.assertEqual(resp.result, "Wikipedia returned a random article without a title.")

    async def test_get_random_article_non_dict_query(self):
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = "<html>Service Down</html>"
            resp = await main.get_random_article({})
            self.assertEqual(resp.result, "No random Wikipedia article was returned.")


class LifespanTests(unittest.IsolatedAsyncioTestCase):
    async def test_lifespan_initializes_and_closes_client(self):
        async with main.lifespan(main.app):
            client = await main._get_wikipedia_client()
            self.assertIsNotNone(client)
            self.assertFalse(getattr(client, "is_closed", False))
        self.assertTrue(getattr(main._wikipedia_client, "is_closed", False))


if __name__ == "__main__":
    unittest.main()
