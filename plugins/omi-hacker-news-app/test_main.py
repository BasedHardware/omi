"""Hermetic unit tests for Omi Hacker News app."""

import asyncio
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

# Provide lightweight stubs for third-party runtime dependencies so test_main.py
# runs hermetically on any clean standard library Python environment without
# requiring FastAPI, httpx, or Pydantic to be installed.
if "httpx" not in sys.modules:
    try:
        import httpx  # type: ignore
    except ImportError:
        httpx = types.ModuleType("httpx")

        class HTTPError(Exception):
            pass

        class HTTPStatusError(HTTPError):
            def __init__(self, message=None, request=None, response=None):
                super().__init__(message)
                self.request = request
                self.response = response or types.SimpleNamespace(status_code=500)

        class AsyncClient:
            def __init__(self, *args, **kwargs):
                self.is_closed = False

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                self.is_closed = True

            async def get(self, *args, **kwargs):
                pass

        httpx.HTTPError = HTTPError
        httpx.HTTPStatusError = HTTPStatusError
        httpx.AsyncClient = AsyncClient
        sys.modules["httpx"] = httpx

if "fastapi" not in sys.modules:
    try:
        import fastapi  # type: ignore
        import fastapi.exceptions  # type: ignore
        import fastapi.responses  # type: ignore
    except ImportError:
        fastapi = types.ModuleType("fastapi")

        class FastAPI:
            def __init__(self, *args, **kwargs):
                self.state = types.SimpleNamespace()
                self.routes = []

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

            def exception_handler(self, exc_class):
                return lambda f: f

        class Request:
            pass

        class RequestValidationError(Exception):
            def __init__(self, errors=None):
                super().__init__("Validation error")
                self._errors = errors or []

            def errors(self):
                return self._errors

        fastapi.FastAPI = FastAPI
        fastapi.Request = Request
        sys.modules["fastapi"] = fastapi

        exceptions = types.ModuleType("fastapi.exceptions")
        exceptions.RequestValidationError = RequestValidationError
        sys.modules["fastapi.exceptions"] = exceptions
        fastapi.exceptions = exceptions

        responses = types.ModuleType("fastapi.responses")

        class HTMLResponse:
            def __init__(self, content="", status_code=200):
                self.content = content
                self.status_code = status_code

        class JSONResponse:
            def __init__(self, content=None, status_code=200):
                self.content = content
                self.status_code = status_code

        responses.HTMLResponse = HTMLResponse
        responses.JSONResponse = JSONResponse
        sys.modules["fastapi.responses"] = responses
        fastapi.responses = responses

if "pydantic" not in sys.modules:
    try:
        import pydantic  # type: ignore
    except ImportError:
        pydantic = types.ModuleType("pydantic")

        def Field(default=None, **kwargs):
            return default

        class BaseModel:
            def __init__(self, **kwargs):
                for cls in reversed(self.__class__.__mro__):
                    for k, v in getattr(cls, "__dict__", {}).items():
                        if not k.startswith("_") and not callable(v):
                            setattr(self, k, None if v is ... else v)
                for k, v in kwargs.items():
                    setattr(self, k, v)

            def model_dump(self):
                return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

        pydantic.BaseModel = BaseModel
        pydantic.Field = Field
        sys.modules["pydantic"] = pydantic

# Add plugin directory to path so models and main can be loaded hermetically
PLUGIN_DIR = Path(__file__).resolve().parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

import main
import models


class HelperFunctionTests(unittest.TestCase):
    def test_clean_text_normal_and_entities(self):
        self.assertEqual(main._clean_text("Hello &amp; world"), "Hello & world")
        self.assertEqual(main._clean_text("Test&#39;s &quot;quotes&quot;"), "Test's \"quotes\"")
        self.assertEqual(main._clean_text("<p>Line 1</p><p>Line 2</p>"), "Line 1\n\nLine 2")
        self.assertEqual(main._clean_text("<code>let x = 1;</code>"), "`let x = 1;`")

    def test_clean_text_none_and_non_string(self):
        self.assertEqual(main._clean_text(None), "")
        self.assertEqual(main._clean_text(""), "")
        self.assertEqual(main._clean_text(123), "")
        self.assertEqual(main._clean_text([]), "")

    def test_safe_limit_bounds_and_fallbacks(self):
        self.assertEqual(main._safe_limit(None, 10), 10)
        self.assertEqual(main._safe_limit("", 5), 5)
        self.assertEqual(main._safe_limit("invalid", 10), 10)
        self.assertEqual(main._safe_limit(5), 5)
        self.assertEqual(main._safe_limit("15"), 15)
        self.assertEqual(main._safe_limit(-10), 1)
        self.assertEqual(main._safe_limit(100), main.MAX_LIMIT)
        self.assertEqual(main._safe_limit(float("nan"), 10), 10)
        self.assertEqual(main._safe_limit(float("inf"), 10), 10)

    def test_format_story_normal(self):
        hit = {
            "title": "Show HN: A cool project",
            "author": "dev",
            "points": 42,
            "num_comments": 15,
            "objectID": "12345",
            "url": "https://example.com",
        }
        res = main._format_story(hit, 1)
        self.assertIn("1. Show HN: A cool project", res)
        self.assertIn("by dev | 42 points | 15 comments", res)
        self.assertIn("https://example.com", res)
        self.assertIn("https://news.ycombinator.com/item?id=12345", res)

    def test_format_story_missing_fields_and_non_dict(self):
        hit = {"story_title": "Alternative Title", "story_id": "999"}
        res = main._format_story(hit, 2)
        self.assertIn("2. Alternative Title", res)
        self.assertIn("by unknown | 0 points | 0 comments", res)
        self.assertIn("https://news.ycombinator.com/item?id=999", res)

        non_dict_res = main._format_story("not a dict", 3)
        self.assertIn("3. (untitled)", non_dict_res)


class RouteWiringTests(unittest.TestCase):
    def test_manifest_structure_and_no_auth(self):
        manifest = asyncio.run(main.get_omi_tools_manifest())
        tools = manifest.get("tools", [])
        tool_names = {t["name"] for t in tools}
        self.assertEqual(tool_names, {"get_front_page", "search_stories", "get_discussion"})
        for t in tools:
            self.assertFalse(t["auth_required"])

    def test_health_endpoint(self):
        res = asyncio.run(main.health())
        self.assertEqual(res, {"status": "ok"})

    def test_root_endpoint(self):
        res = asyncio.run(main.root())
        self.assertIn("Hacker News x Omi", res.content)


class ToolFrontPageTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_front_page_success(self):
        mock_data = {
            "hits": [
                {
                    "title": "Front page story",
                    "author": "alice",
                    "points": 100,
                    "num_comments": 20,
                    "objectID": "101",
                    "url": "https://story1.com",
                }
            ]
        }
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_data
            resp = await main.get_front_page({"limit": 5})
            self.assertIsNone(resp.error)
            self.assertIn("Front page story", resp.result)
            self.assertIn("alice", resp.result)

    async def test_get_front_page_empty_and_null_hits(self):
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"hits": []}
            resp = await main.get_front_page({})
            self.assertEqual(resp.result, "No Hacker News front page stories were returned.")

            mock_req.return_value = {"hits": None}
            resp = await main.get_front_page({})
            self.assertEqual(resp.result, "No Hacker News front page stories were returned.")

    async def test_get_front_page_non_dict_payload_and_response(self):
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = "<html>502 Bad Gateway</html>"
            resp = await main.get_front_page(None)
            self.assertIsNone(resp.error)
            self.assertEqual(resp.result, "No Hacker News front page stories were returned.")

    async def test_get_front_page_http_error(self):
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = main.httpx.HTTPError("Network down")
            resp = await main.get_front_page({"limit": 10})
            self.assertIn("Hacker News request failed: Network down", resp.error)


class ToolSearchStoriesTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_stories_success_relevance(self):
        mock_data = {
            "hits": [
                {
                    "title": "Python 3.13 Released",
                    "author": "guido",
                    "points": 500,
                    "num_comments": 150,
                    "objectID": "202",
                    "url": "https://python.org",
                }
            ]
        }
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_data
            resp = await main.search_stories({"query": "python", "limit": 5})
            self.assertIsNone(resp.error)
            self.assertIn("Python 3.13 Released", resp.result)
            mock_req.assert_called_once_with("/search", {"query": "python", "tags": "story", "hitsPerPage": 5})

    async def test_search_stories_success_date(self):
        mock_data = {"hits": [{"title": "Latest News", "objectID": "203"}]}
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_data
            resp = await main.search_stories({"query": "ai", "sort_by": "date"})
            self.assertIsNone(resp.error)
            mock_req.assert_called_once_with("/search_by_date", {"query": "ai", "tags": "story", "hitsPerPage": 10})

    async def test_search_stories_missing_query(self):
        resp = await main.search_stories({})
        self.assertEqual(resp.error, "Missing required field: query")

        resp = await main.search_stories({"query": "   "})
        self.assertEqual(resp.error, "Missing required field: query")

        resp = await main.search_stories(None)
        self.assertEqual(resp.error, "Missing required field: query")

    async def test_search_stories_empty_hits(self):
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"hits": []}
            resp = await main.search_stories({"query": "unknownterm123"})
            self.assertEqual(resp.result, "No Hacker News stories found for 'unknownterm123'.")

    async def test_search_stories_http_error(self):
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = main.httpx.HTTPError("Timeout")
            resp = await main.search_stories({"query": "crash"})
            self.assertIn("Hacker News search failed: Timeout", resp.error)


class ToolGetDiscussionTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_discussion_success_with_comments(self):
        mock_item = {
            "title": "Ask HN: Favorite tools?",
            "author": "asker",
            "points": 35,
            "url": None,
            "text": "<p>Use &lt;vector&gt; here.</p>",
            "children": [
                {"author": "bob", "text": "if a &lt; b and c &gt; d"},
                {"author": "charlie", "text": "<p>I prefer emacs.</p>"},
            ],
        }
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_item
            resp = await main.get_discussion({"item_id": 303, "comment_limit": 5})
            self.assertIsNone(resp.error)
            self.assertIn("Ask HN: Favorite tools?", resp.result)
            self.assertIn("Post text:\nUse <vector> here.", resp.result)
            self.assertIn("Top 2 comments:", resp.result)
            self.assertIn("bob: if a < b and c > d", resp.result)
            self.assertIn("charlie: I prefer emacs.", resp.result)

    async def test_get_discussion_null_children_and_deleted_comments(self):
        mock_item = {
            "title": "Item With Deleted Comments",
            "author": "author1",
            "points": 10,
            "children": [None, {"author": "user", "text": None}, "not a dict"],
        }
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_item
            resp = await main.get_discussion({"item_id": 404})
            self.assertIsNone(resp.error)
            self.assertIn("No top-level comments returned.", resp.result)

            mock_item["children"] = None
            resp = await main.get_discussion({"item_id": 404})
            self.assertIsNone(resp.error)
            self.assertIn("No top-level comments returned.", resp.result)

    async def test_get_discussion_missing_and_invalid_item_id(self):
        resp = await main.get_discussion({})
        self.assertEqual(resp.error, "Missing required field: item_id")

        resp = await main.get_discussion({"item_id": -5})
        self.assertEqual(resp.error, "item_id must be a positive integer")

        resp = await main.get_discussion({"item_id": 0})
        self.assertEqual(resp.error, "item_id must be a positive integer")

        resp = await main.get_discussion(None)
        self.assertEqual(resp.error, "Missing required field: item_id")

    async def test_get_discussion_404_not_found(self):
        resp_404 = types.SimpleNamespace(status_code=404)
        exc = main.httpx.HTTPStatusError("Not Found", response=resp_404)
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = exc
            resp = await main.get_discussion({"item_id": 999999})
            self.assertEqual(resp.error, "Hacker News item 999999 not found.")

    async def test_get_discussion_non_dict_payload(self):
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = "<html>404</html>"
            resp = await main.get_discussion({"item_id": 123})
            self.assertEqual(resp.result, "No Hacker News discussion found for item 123.")


class ClientPoolingAndLifespanTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_json_uses_pooled_client(self):
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_response = unittest.mock.MagicMock()
        mock_response.json.return_value = {"status": "ok"}
        mock_response.raise_for_status.return_value = None
        mock_client.get = AsyncMock(return_value=mock_response)

        main.app.state.client = mock_client
        try:
            res = await main._request_json("/test")
            self.assertEqual(res, {"status": "ok"})
            mock_client.get.assert_called_once()
        finally:
            main.app.state.client = None

    async def test_request_json_fallback_when_no_client(self):
        main.app.state.client = None
        mock_response = unittest.mock.MagicMock()
        mock_response.json.return_value = {"status": "fallback_ok"}
        mock_response.raise_for_status.return_value = None

        with patch.object(main.httpx, "AsyncClient") as mock_client_cls:
            instance = AsyncMock()
            instance.get = AsyncMock(return_value=mock_response)
            instance.__aenter__.return_value = instance
            mock_client_cls.return_value = instance

            res = await main._request_json("/fallback_test")
            self.assertEqual(res, {"status": "fallback_ok"})

    async def test_validation_exception_handler(self):
        exc = main.RequestValidationError([{"loc": ["body", "item_id"], "msg": "value is not a valid integer"}])
        res = await main.validation_exception_handler(main.Request(), exc)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.content, {"result": None, "error": "invalid tool request: item_id: value is not a valid integer"})

        empty_exc = main.RequestValidationError([])
        res2 = await main.validation_exception_handler(main.Request(), empty_exc)
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.content, {"result": None, "error": "invalid tool request: invalid request payload"})


if __name__ == "__main__":
    unittest.main()
