"""Hermetic regression tests for optional Notion result limits.

The Omi retrieval layer serializes omitted optional integer arguments as JSON
``null``.  These tests exercise all four affected production handlers through
the HTTP request seam and verify the resulting Notion ``page_size`` values.
"""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch


class Framework:
    def __init__(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda function: function

    post = get


class Response:
    result = None
    error = None

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def module(name, **attributes):
    value = types.ModuleType(name)
    value.__dict__.update(attributes)
    return value


stubs = {
    "requests": module("requests", get=Mock(), post=Mock(), patch=Mock(), delete=Mock()),
    "dotenv": module("dotenv", load_dotenv=lambda: None),
    "fastapi": module("fastapi", FastAPI=Framework, Request=Framework, Query=Framework,
                       HTTPException=Exception),
    "fastapi.responses": module("fastapi.responses", HTMLResponse=Framework,
                                  RedirectResponse=Framework, JSONResponse=Framework),
    "models": module("models", ChatToolResponse=Response),
    "db": module("db", **{name: Mock() for name in (
        "store_notion_tokens", "get_notion_tokens", "update_notion_tokens", "delete_notion_tokens",
        "store_oauth_state", "get_oauth_state", "delete_oauth_state", "store_user_setting", "get_user_setting",
    )}),
}
spec = importlib.util.spec_from_file_location(
    "notion_limit_under_test", Path(__file__).with_name("main.py")
)
notion = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(notion)


class LimitInputTests(unittest.TestCase):
    def response_for(self, url):
        response = Mock(status_code=200, content=b"{}")
        if url.endswith("/databases/demo/query"):
            response.json.return_value = {"results": [{
                "id": "entry-id", "url": "https://notion.so/entry-id", "properties": {},
            }]}
        elif url.endswith("/search"):
            response.json.return_value = {"results": [{
                "object": "page", "id": "page-id", "url": "https://notion.so/page-id",
                "properties": {"title": {"type": "title", "title": [{"plain_text": "Demo"}]}},
                "created_time": "2026-09-14T00:00:00.000Z",
                "last_edited_time": "2026-09-14T00:00:00.000Z",
            }]}
        return response

    def invoke(self, tool, max_results, **extra):
        body = {"uid": "test-user", "max_results": max_results}
        body.update(extra)
        request = Mock(json=AsyncMock(return_value=body))

        def post(url, **kwargs):
            return self.response_for(url)

        with patch.object(notion, "get_valid_access_token", return_value="test-token"), \
             patch.object(notion.requests, "post", side_effect=post) as api:
            result = asyncio.run(tool(request))
        self.assertIsNone(result.error)
        self.assertTrue(result.result)
        self.assertEqual(api.call_count, 1)
        return json.loads(api.call_args.kwargs["data"])

    def test_coerce_int_contract(self):
        cases = (
            (None, 10),
            (True, 10),
            (False, 10),
            ("", 10),
            (" 5 ", 5),
            (5, 5),
            (0, 1),
            (-3, 1),
            (999, 50),
            ("not-a-number", 10),
            (float("inf"), 10),
            (float("nan"), 10),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(notion._coerce_int(value, 10, 1, 50), expected)

    def test_search_normalizes_max_results(self):
        for value, expected in ((None, 10), ("5", 5), (0, 1), (-3, 1), (500, 20),
                                 ("1e309", 10), (float("inf"), 10)):
            with self.subTest(value=value):
                payload = self.invoke(notion.tool_search, value, query="weekly plan")
                self.assertEqual(payload["page_size"], expected)

    def test_list_pages_normalizes_max_results(self):
        for value, expected in ((None, 10), ("5", 5), (0, 1), (-3, 1), (500, 20),
                                 ("1e309", 10), (float("inf"), 10)):
            with self.subTest(value=value):
                payload = self.invoke(notion.tool_list_pages, value)
                self.assertEqual(payload["page_size"], expected)

    def test_list_databases_normalizes_max_results(self):
        for value, expected in ((None, 10), ("5", 5), (0, 1), (-3, 1), (500, 20),
                                 ("1e309", 10), (float("inf"), 10)):
            with self.subTest(value=value):
                payload = self.invoke(notion.tool_list_databases, value)
                self.assertEqual(payload["page_size"], expected)

    def test_query_database_normalizes_max_results(self):
        for value, expected in ((None, 10), ("5", 5), (0, 1), (-3, 1), (500, 50),
                                 ("1e309", 10), (float("inf"), 10)):
            with self.subTest(value=value):
                payload = self.invoke(notion.tool_query_database, value, database_id="demo")
                self.assertEqual(payload["page_size"], expected)


if __name__ == "__main__":
    unittest.main()
