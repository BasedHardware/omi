"""Hermetic error-handling regression suite for omi-notion-app.

Verifies that internal exceptions, unhandled errors, and sensitive system traces
never leak into client HTTP responses or chat-tool errors across all Notion app endpoints.
Uses Python standard library unittest only.

Run: python3 plugins/omi-notion-app/test_error_handling.py
"""

import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

SENTINEL_ERROR = "INTERNAL_DB_DISCONNECTED_AT_10.240.0.1_PASSWORD_LEAK"


class FakeRequest:
    def __init__(self, data):
        self._data = data

    async def json(self):
        return self._data


def load_notion_app():
    """Load plugins/omi-notion-app/main.py hermetically without external dependencies."""
    class Framework:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda fn: fn

        post = get

    class Response:
        result = None
        error = None

        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    def make_module(name, **attributes):
        val = types.ModuleType(name)
        val.__dict__.update(attributes)
        return val

    stubs = {
        "requests": make_module("requests", get=Mock(), post=Mock(), patch=Mock()),
        "dotenv": make_module("dotenv", load_dotenv=lambda: None),
        "fastapi": make_module("fastapi", FastAPI=Framework, Request=Framework, Query=Framework, HTTPException=Exception),
        "fastapi.responses": make_module("fastapi.responses", HTMLResponse=Framework, RedirectResponse=Framework, JSONResponse=Framework),
        "models": make_module("models", ChatToolResponse=Response),
        "db": make_module("db", **{name: Mock() for name in (
            "store_notion_tokens", "get_notion_tokens", "update_notion_tokens", "delete_notion_tokens",
            "store_oauth_state", "get_oauth_state", "delete_oauth_state", "store_user_setting", "get_user_setting",
        )}),
        "notion_content": make_module("notion_content", encode_payload=lambda *a, **k: None, plan_content_requests=lambda *a, **k: [{}], title_items=lambda *a, **k: []),
    }

    main_py_path = Path(__file__).parent / "notion_main_hardened.py"
    if not main_py_path.exists():
        main_py_path = Path(__file__).with_name("main.py")

    spec = importlib.util.spec_from_file_location("notion_app", main_py_path)
    notion = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(notion)
    return notion


class TestNotionErrorHandling(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = load_notion_app()

    def setUp(self):
        self.app.get_valid_access_token = lambda uid: "valid_token"
        self.app.get_notion_tokens = lambda uid: {"access_token": "valid_token"}

    def test_notion_api_request_does_not_leak_exception(self):
        """notion_api_request masks raw Exception from callers."""
        with patch.object(self.app.requests, "post", side_effect=Exception(SENTINEL_ERROR)):
            res = self.app.notion_api_request("uid123", "POST", "/search")
            self.assertIn("error", res)
            self.assertNotIn(SENTINEL_ERROR, res["error"])
            self.assertEqual(res["error"], "Notion API request failed")

    def test_tool_search_does_not_leak_exception(self):
        """tool_search masks unexpected exceptions in ChatToolResponse."""
        req = FakeRequest({"uid": "uid123", "query": "test"})
        with patch.object(self.app, "notion_api_request", side_effect=Exception(SENTINEL_ERROR)):
            res = asyncio.run(self.app.tool_search(req))
            self.assertIsNotNone(res.error)
            self.assertNotIn(SENTINEL_ERROR, res.error)
            self.assertEqual(res.error, "Search failed")

    def test_tool_list_pages_does_not_leak_exception(self):
        """tool_list_pages masks unexpected exceptions in ChatToolResponse."""
        req = FakeRequest({"uid": "uid123"})
        with patch.object(self.app, "notion_api_request", side_effect=Exception(SENTINEL_ERROR)):
            res = asyncio.run(self.app.tool_list_pages(req))
            self.assertIsNotNone(res.error)
            self.assertNotIn(SENTINEL_ERROR, res.error)
            self.assertEqual(res.error, "Failed to list pages")

    def test_tool_get_page_does_not_leak_exception(self):
        """tool_get_page masks unexpected exceptions in ChatToolResponse."""
        req = FakeRequest({"uid": "uid123", "page_id": "00000000-0000-0000-0000-000000000001"})
        with patch.object(self.app, "notion_api_request", side_effect=Exception(SENTINEL_ERROR)):
            res = asyncio.run(self.app.tool_get_page(req))
            self.assertIsNotNone(res.error)
            self.assertNotIn(SENTINEL_ERROR, res.error)
            self.assertEqual(res.error, "Failed to get page")

    def test_tool_update_page_does_not_leak_exception(self):
        """tool_update_page masks unexpected exceptions in ChatToolResponse."""
        req = FakeRequest({"uid": "uid123", "page_id": "00000000-0000-0000-0000-000000000001", "title": "New"})
        with patch.object(self.app, "notion_api_request", side_effect=Exception(SENTINEL_ERROR)):
            res = asyncio.run(self.app.tool_update_page(req))
            self.assertIsNotNone(res.error)
            self.assertNotIn(SENTINEL_ERROR, res.error)
            self.assertEqual(res.error, "Failed to update page")

    def test_tool_list_databases_does_not_leak_exception(self):
        """tool_list_databases masks unexpected exceptions in ChatToolResponse."""
        req = FakeRequest({"uid": "uid123"})
        with patch.object(self.app, "notion_api_request", side_effect=Exception(SENTINEL_ERROR)):
            res = asyncio.run(self.app.tool_list_databases(req))
            self.assertIsNotNone(res.error)
            self.assertNotIn(SENTINEL_ERROR, res.error)
            self.assertEqual(res.error, "Failed to list databases")

    def test_tool_query_database_does_not_leak_exception(self):
        """tool_query_database masks unexpected exceptions in ChatToolResponse."""
        req = FakeRequest({"uid": "uid123", "database_id": "00000000-0000-0000-0000-000000000001"})
        with patch.object(self.app, "notion_api_request", side_effect=Exception(SENTINEL_ERROR)):
            res = asyncio.run(self.app.tool_query_database(req))
            self.assertIsNotNone(res.error)
            self.assertNotIn(SENTINEL_ERROR, res.error)
            self.assertEqual(res.error, "Failed to query database")


if __name__ == "__main__":
    unittest.main()
