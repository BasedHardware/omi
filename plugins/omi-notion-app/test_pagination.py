"""Hermetic regression tests for #13915: get_page must follow Notion's
has_more/next_cursor block-children pagination instead of stopping at the
first response. HTTP, framework and token storage are doubles; the
production handler runs through the requests seam."""
import asyncio
import importlib.util
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
    "requests": module("requests", get=Mock(), post=Mock(), patch=Mock()),
    "dotenv": module("dotenv", load_dotenv=lambda: None),
    "fastapi": module("fastapi", FastAPI=Framework, Request=Framework, Query=Framework, HTTPException=Exception),
    "fastapi.responses": module("fastapi.responses", HTMLResponse=Framework, RedirectResponse=Framework, JSONResponse=Framework),
    "models": module("models", ChatToolResponse=Response),
    "db": module("db", **{name: Mock() for name in (
        "store_notion_tokens", "get_notion_tokens", "update_notion_tokens", "delete_notion_tokens",
        "store_oauth_state", "get_oauth_state", "delete_oauth_state", "store_user_setting", "get_user_setting",
    )}),
}
spec = importlib.util.spec_from_file_location("notion_under_test", Path(__file__).with_name("main.py"))
notion = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(notion)


def page_metadata():
    response = Mock(status_code=200)
    response.json.return_value = {
        "properties": {"title": {"type": "title", "title": [{"plain_text": "Known title"}]}},
        "id": "test-page", "archived": False,
        "url": "https://www.notion.so/test-page",
        "created_time": "2026-09-01T00:00:00.000Z",
        "last_edited_time": "2026-09-08T00:00:00.000Z",
    }
    return response


def children_page(blocks, has_more=False, next_cursor=None):
    response = Mock(status_code=200)
    response.json.return_value = {
        "object": "list",
        "results": blocks,
        "has_more": has_more,
        "next_cursor": next_cursor,
    }
    return response


def paragraph(text):
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"plain_text": text}]}}


class GetPagePaginationTests(unittest.TestCase):
    def read(self, *responses):
        request = Mock(json=AsyncMock(return_value={"uid": "test-user", "page_id": "test-page"}))
        with patch.object(notion, "get_valid_access_token", return_value="test-placeholder"), patch.object(notion, "log"), \
             patch.object(notion.requests, "get", side_effect=[page_metadata(), *responses]) as get:
            result = asyncio.run(notion.tool_get_page(request))
        return result, get

    def children_params(self, get):
        """params kwarg of each /blocks/.../children call, in order."""
        return [call.kwargs["params"] for call in get.call_args_list
                if call.args[0].endswith("/blocks/test-page/children")]

    def test_single_page_page_is_fetched_once_at_max_page_size(self):
        result, get = self.read(children_page([paragraph("only block")]))
        self.assertIsNone(result.error)
        self.assertIn("only block", result.result)
        params = self.children_params(get)
        self.assertEqual(len(params), 1)
        # Notion's maximum block-children page size is 100.
        self.assertEqual(params[0]["page_size"], 100)
        self.assertNotIn("start_cursor", params[0])

    def test_multi_page_fetches_every_block(self):
        first = children_page([paragraph(f"block {index}") for index in range(50)],
                              has_more=True, next_cursor="cursor-2")
        second = children_page([paragraph("block 51")], has_more=False, next_cursor=None)
        result, get = self.read(first, second)
        self.assertIsNone(result.error)
        self.assertIn("block 0", result.result)
        self.assertIn("block 51", result.result)
        params = self.children_params(get)
        self.assertEqual(len(params), 2)
        self.assertEqual(params[1]["start_cursor"], "cursor-2")

    def test_blocks_past_first_response_render(self):
        # Dividers and other non-text blocks produce no characters but still
        # count against the page window; the tail text must survive.
        first = children_page([{"object": "block", "type": "divider", "divider": {}}
                               for _ in range(100)], has_more=True, next_cursor="cursor-2")
        second = children_page([paragraph("tail text")])
        result, get = self.read(first, second)
        self.assertIsNone(result.error)
        self.assertIn("tail text", result.result)
        self.assertEqual(len(self.children_params(get)), 2)

    def test_content_budget_stops_pagination(self):
        # Once the rendered output fills the 1,000-character budget, no
        # further page is fetched even when has_more is still true.
        for text_len in (1000, 1500):
            with self.subTest(text_len=text_len):
                first = children_page([paragraph("x" * text_len)], has_more=True, next_cursor="cursor-2")
                second = children_page([paragraph("should-not-be-fetched")])
                result, get = self.read(first, second)
                self.assertIsNone(result.error)
                self.assertEqual(len(self.children_params(get)), 1)
                self.assertNotIn("should-not-be-fetched", result.result)

        # One character under the budget still follows the cursor.
        first = children_page([paragraph("x" * 999)],
                              has_more=True, next_cursor="cursor-2")
        second = children_page([paragraph("tail")])
        result, get = self.read(first, second)
        self.assertIsNone(result.error)
        self.assertEqual(len(self.children_params(get)), 2)

    def test_later_page_failure_is_an_error_not_a_short_page(self):
        for failure in (Mock(status_code=429, text="private upstream response"),
                        RuntimeError("private transport detail")):
            with self.subTest(failure=type(failure).__name__):
                first = children_page([paragraph("block 1")], has_more=True, next_cursor="cursor-2")
                result, get = self.read(first, failure)
                self.assertIsNone(result.result)
                self.assertIn("Failed to retrieve page content", result.error)
                if isinstance(failure, Mock):
                    self.assertIn("HTTP 429", result.error)
                self.assertIn("**Known title**", result.error)
                self.assertNotIn("private", result.error)

    def test_repeated_cursor_stops_instead_of_looping(self):
        # A malformed upstream returning the same cursor forever must not
        # re-request it: second identical cursor is not followed.
        first = children_page([paragraph("page one")], has_more=True, next_cursor="stuck")
        second = children_page([paragraph("page two")], has_more=True, next_cursor="stuck")
        result, get = self.read(first, second)
        self.assertIsNone(result.error)
        self.assertIn("page two", result.result)
        params = self.children_params(get)
        self.assertEqual(len(params), 2)
        self.assertEqual(params[1]["start_cursor"], "stuck")

    def test_missing_or_nonstring_cursor_stops(self):
        for cursor in (None, "", 123, {"opaque": "cursor"}):
            with self.subTest(cursor=cursor):
                first = children_page([paragraph("done")], has_more=True, next_cursor=cursor)
                result, get = self.read(first)
                self.assertIsNone(result.error)
                self.assertIn("done", result.result)
                self.assertEqual(len(self.children_params(get)), 1)

    def test_page_ceiling_bounds_distinct_cursors(self):
        # Even an endless supply of fresh cursors stops at the 10-page
        # ceiling (1,000 blocks) that bounds a malformed cursor.
        pages = [children_page([paragraph(f"p{index}")], has_more=True, next_cursor=f"cursor-{index}")
                 for index in range(15)]
        result, get = self.read(*pages)
        self.assertIsNone(result.error)
        self.assertEqual(len(self.children_params(get)), 10)

    def test_malformed_results_shape_is_not_silent_success(self):
        first = children_page([paragraph("block 1")], has_more=True, next_cursor="cursor-2")
        malformed = Mock(status_code=200)
        malformed.json.return_value = {"object": "list", "results": "private malformed results",
                                       "has_more": True, "next_cursor": "cursor-3"}
        result, get = self.read(first, malformed)
        self.assertIsNone(result.result)
        self.assertIn("Failed to retrieve page content", result.error)
        self.assertNotIn("private", result.error)


if __name__ == "__main__":
    unittest.main(verbosity=2)
