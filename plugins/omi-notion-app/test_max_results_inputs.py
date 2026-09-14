"""Regression tests for max_results handling in the Notion listing tools.

The Omi backend models every optional tool parameter as ``Optional[int]``
with a ``None`` default and forwards the model's arguments verbatim, so
``{"max_results": null}`` is what an ordinary "search my Notion" request
looks like on the wire. ``tool_search``, ``tool_list_pages``,
``tool_list_databases`` and ``tool_query_database`` used to do
``min(body.get("max_results", 10), N)`` on the raw value, which raises
``TypeError`` for ``None`` (and for numeric strings), so every one of them
answered ``... '<' not supported between instances of 'int' and 'NoneType'``.
Values of ``0`` or below were forwarded unchanged as ``page_size``, which the
Notion API rejects (it accepts 1..100).

Hermetic production-handler tests in the style of test_main.py: HTTP,
framework and token storage are doubles, so the suite runs on a stdlib-only
interpreter and never touches the network.
"""

import asyncio
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
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
    "fastapi": module("fastapi", FastAPI=Framework, Request=Framework, Query=Framework, HTTPException=Exception),
    "fastapi.responses": module("fastapi.responses", HTMLResponse=Framework, RedirectResponse=Framework, JSONResponse=Framework),
    "models": module("models", ChatToolResponse=Response),
    "db": module("db", **{name: Mock() for name in (
        "store_notion_tokens", "get_notion_tokens", "update_notion_tokens", "delete_notion_tokens",
        "store_oauth_state", "get_oauth_state", "delete_oauth_state", "store_user_setting", "get_user_setting",
    )}),
}
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # main.py imports notion_content as a sibling module
spec = importlib.util.spec_from_file_location("notion_under_test", HERE / "main.py")
notion = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(notion)

PAGE = {
    "object": "page",
    "id": "0123456789abcdef0123456789abcdef",
    "url": "https://www.notion.so/Weekly-plan-0123456789abcdef0123456789abcdef",
    "created_time": "2026-09-01T00:00:00.000Z",
    "last_edited_time": "2026-09-08T00:00:00.000Z",
    "properties": {"title": {"type": "title", "title": [{"plain_text": "Weekly plan"}]}},
}
DATABASE = {
    "object": "database",
    "id": "fedcba9876543210fedcba9876543210",
    "url": "https://www.notion.so/fedcba9876543210fedcba9876543210",
    "title": [{"plain_text": "Tasks"}],
    "properties": {"Name": {"type": "title"}},
}

# (handler, extra request fields, documented cap, upstream item to return)
TOOLS = [
    ("tool_search", {"query": "plan"}, 20, PAGE),
    ("tool_list_pages", {}, 20, PAGE),
    ("tool_list_databases", {}, 20, DATABASE),
    ("tool_query_database", {"database_id": DATABASE["id"]}, 50, PAGE),
]


class MaxResultsInputTests(unittest.TestCase):
    def call(self, handler, extra, max_results, item):
        response = Mock(status_code=200)
        response.json.return_value = {"results": [item]}
        request = Mock(json=AsyncMock(return_value={"uid": "test-user", "max_results": max_results, **extra}))
        with patch.object(notion, "get_valid_access_token", return_value="test-placeholder"), \
                patch.object(notion, "log"), \
                patch.object(notion.requests, "post", return_value=response) as post:
            result = asyncio.run(getattr(notion, handler)(request))
        self.assertEqual(post.call_count, 1, f"{handler}: {result.error}")
        sent = json.loads(post.call_args.kwargs["data"])
        return result, sent["page_size"]

    def assert_page_size(self, max_results, expected, label):
        for handler, extra, cap, item in TOOLS:
            with self.subTest(handler=handler, case=label):
                result, page_size = self.call(handler, extra, max_results, item)
                self.assertIsNone(result.error, result.error)
                self.assertIsNotNone(result.result)
                self.assertEqual(page_size, expected(cap))

    def test_json_null_falls_back_to_default(self):
        self.assert_page_size(None, lambda cap: 10, "null")

    def test_numeric_string_is_coerced(self):
        self.assert_page_size("5", lambda cap: 5, "string")

    def test_booleans_are_not_treated_as_counts(self):
        # bool is an int subclass; True must not become page_size=1 and False must not become 0.
        self.assert_page_size(True, lambda cap: 10, "true")
        self.assert_page_size(False, lambda cap: 10, "false")

    def test_non_positive_is_clamped_to_one(self):
        self.assert_page_size(0, lambda cap: 1, "zero")
        self.assert_page_size(-3, lambda cap: 1, "negative")

    def test_oversized_is_capped_at_the_documented_maximum(self):
        self.assert_page_size(500, lambda cap: cap, "oversized")

    def test_unparseable_and_overflowing_fall_back_to_default(self):
        self.assert_page_size("a few", lambda cap: 10, "text")
        # json.loads turns 1e309 into float('inf'); int(inf) raises OverflowError.
        self.assert_page_size(float("inf"), lambda cap: 10, "overflow")

    def test_results_are_rendered_for_the_default_request(self):
        result, _ = self.call("tool_search", {"query": "plan"}, None, PAGE)
        self.assertIn("Weekly plan", result.result)
        result, _ = self.call("tool_list_databases", {}, None, DATABASE)
        self.assertIn("Tasks", result.result)


if __name__ == "__main__":
    unittest.main()
