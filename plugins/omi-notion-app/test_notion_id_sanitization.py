"""
Hermetic unit tests for Notion identifier sanitization and normalization.
Tests that page and database identifiers (URLs, 32-hex strings, UUIDs, prefixes)
are cleanly normalized to standard 36-character hyphenated UUIDs across all tool endpoints.
"""
import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch


# Lightweight stubs for hermetic test execution without network or external services
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
    val = types.ModuleType(name)
    val.__dict__.update(attributes)
    return val


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

spec = importlib.util.spec_from_file_location("notion_app", Path(__file__).with_name("main.py"))
notion = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(notion)


class NotionIdSanitizationTests(unittest.TestCase):
    """Verify sanitize_notion_id correctly normalizes various ID formats and rejects invalid inputs."""

    EXPECTED_UUID = "8a99478f-6b21-4f1b-857c-2b28cf9c9a29"

    def test_32_hex_string_normalization(self):
        # Unhyphenated lowercase
        self.assertEqual(
            notion.sanitize_notion_id("8a99478f6b214f1b857c2b28cf9c9a29"),
            self.EXPECTED_UUID,
        )
        # Unhyphenated uppercase
        self.assertEqual(
            notion.sanitize_notion_id("8A99478F6B214F1B857C2B28CF9C9A29"),
            self.EXPECTED_UUID,
        )

    def test_standard_36_uuid_preservation(self):
        # Standard lowercase
        self.assertEqual(
            notion.sanitize_notion_id("8a99478f-6b21-4f1b-857c-2b28cf9c9a29"),
            self.EXPECTED_UUID,
        )
        # Standard uppercase converted to lowercase
        self.assertEqual(
            notion.sanitize_notion_id("8A99478F-6B21-4F1B-857C-2B28CF9C9A29"),
            self.EXPECTED_UUID,
        )

    def test_notion_urls(self):
        # Full URL with slug and query param
        url1 = "https://www.notion.so/workspace/Team-Sync-Notes-8a99478f6b214f1b857c2b28cf9c9a29?pvs=4"
        self.assertEqual(notion.sanitize_notion_id(url1), self.EXPECTED_UUID)

        # URL without slug
        url2 = "https://notion.so/8a99478f6b214f1b857c2b28cf9c9a29"
        self.assertEqual(notion.sanitize_notion_id(url2), self.EXPECTED_UUID)

        # Notion site URL
        url3 = "https://myworkspace.notion.site/Page-8a99478f6b214f1b857c2b28cf9c9a29"
        self.assertEqual(notion.sanitize_notion_id(url3), self.EXPECTED_UUID)

    def test_notion_peek_modal_urls(self):
        # Modal peek URL with 32-hex ?p= parameter
        peek1 = "https://www.notion.so/workspace/Tasks-board?p=8a99478f6b214f1b857c2b28cf9c9a29&pm=s"
        self.assertEqual(notion.sanitize_notion_id(peek1), self.EXPECTED_UUID)

        # Modal peek URL with hyphenated ?p= parameter
        peek2 = "https://www.notion.so/workspace/board?p=8a99478f-6b21-4f1b-857c-2b28cf9c9a29"
        self.assertEqual(notion.sanitize_notion_id(peek2), self.EXPECTED_UUID)

    def test_prefixes_and_delimiters(self):
        cases = [
            "page:8a99478f6b214f1b857c2b28cf9c9a29",
            "page/8a99478f-6b21-4f1b-857c-2b28cf9c9a29",
            "p: 8a99478f6b214f1b857c2b28cf9c9a29",
            "database: 8a99478f6b214f1b857c2b28cf9c9a29",
            "db: 8a99478f6b214f1b857c2b28cf9c9a29",
            "block: 8a99478f6b214f1b857c2b28cf9c9a29",
            "#8a99478f6b214f1b857c2b28cf9c9a29",
            "`8a99478f6b214f1b857c2b28cf9c9a29`",
            "<8a99478f-6b21-4f1b-857c-2b28cf9c9a29>",
            "[8a99478f6b214f1b857c2b28cf9c9a29]",
            "  8a99478f-6b21-4f1b-857c-2b28cf9c9a29  ",
        ]
        for c in cases:
            self.assertEqual(notion.sanitize_notion_id(c), self.EXPECTED_UUID, msg=f"Failed for case: {c}")

    def test_invalid_and_dirty_inputs(self):
        self.assertIsNone(notion.sanitize_notion_id(None))
        self.assertIsNone(notion.sanitize_notion_id(True))
        self.assertIsNone(notion.sanitize_notion_id(False))
        self.assertIsNone(notion.sanitize_notion_id({}))
        self.assertIsNone(notion.sanitize_notion_id([]))
        self.assertIsNone(notion.sanitize_notion_id(""))
        self.assertIsNone(notion.sanitize_notion_id("   "))
        self.assertIsNone(notion.sanitize_notion_id("Meeting Notes"))
        self.assertIsNone(notion.sanitize_notion_id("not-a-valid-hex-or-uuid"))
        self.assertIsNone(notion.sanitize_notion_id("https://notion.so/workspace/"))


class EndpointIdSanitizationTests(unittest.TestCase):
    """Verify tool endpoints sanitize IDs before invoking downstream Notion API."""

    CLEAN_UUID = "8a99478f-6b21-4f1b-857c-2b28cf9c9a29"
    RAW_URL = "https://www.notion.so/workspace/Project-8a99478f6b214f1b857c2b28cf9c9a29?pvs=4"

    def test_tool_get_page_sanitizes_page_id(self):
        request = Mock(json=AsyncMock(return_value={
            "uid": "test-uid",
            "page_id": self.RAW_URL,
        }))
        with patch.object(notion, "get_valid_access_token", return_value="token"), \
             patch.object(notion, "notion_api_request") as mock_req, \
             patch.object(notion, "fetch_page_blocks", return_value={"results": []}):
            mock_req.return_value = {
                "id": self.CLEAN_UUID,
                "properties": {"title": {"type": "title", "title": [{"plain_text": "Test"}]}},
                "created_time": "2026-09-01T00:00:00.000Z",
                "last_edited_time": "2026-09-08T00:00:00.000Z",
            }
            res = asyncio.run(notion.tool_get_page(request))
            self.assertIsNone(res.error)
            mock_req.assert_any_call("test-uid", "GET", f"/pages/{self.CLEAN_UUID}")

    def test_tool_update_page_sanitizes_page_id(self):
        request = Mock(json=AsyncMock(return_value={
            "uid": "test-uid",
            "page_id": f"page:{self.CLEAN_UUID}",
            "archived": True,
        }))
        with patch.object(notion, "get_valid_access_token", return_value="token"), \
             patch.object(notion, "notion_api_request") as mock_req:
            mock_req.return_value = {"id": self.CLEAN_UUID}
            res = asyncio.run(notion.tool_update_page(request))
            self.assertIsNone(res.error)
            mock_req.assert_called_with("test-uid", "PATCH", f"/pages/{self.CLEAN_UUID}", json_data={"archived": True})

    def test_tool_append_content_sanitizes_page_id(self):
        request = Mock(json=AsyncMock(return_value={
            "uid": "test-uid",
            "page_id": "8a99478f6b214f1b857c2b28cf9c9a29",
            "content": "Hello World",
        }))
        with patch.object(notion, "get_valid_access_token", return_value="token"), \
             patch.object(notion, "append_content_batches", return_value=None) as mock_append:
            res = asyncio.run(notion.tool_append_content(request))
            self.assertIsNone(res.error)
            self.assertEqual(mock_append.call_args.args[1], self.CLEAN_UUID)

    def test_tool_create_page_sanitizes_parent_and_database_id(self):
        # Case 1: database_id URL
        request_db = Mock(json=AsyncMock(return_value={
            "uid": "test-uid",
            "title": "New Item",
            "database_id": self.RAW_URL,
        }))
        with patch.object(notion, "get_valid_access_token", return_value="token"), \
             patch.object(notion, "notion_api_request", return_value={"id": "new-page-id"}) as mock_req, \
             patch.object(notion, "append_content_batches", return_value=None):
            res = asyncio.run(notion.tool_create_page(request_db))
            self.assertIsNone(res.error)
            call_json = mock_req.call_args.kwargs.get("json_data", {})
            self.assertEqual(call_json.get("parent"), {"database_id": self.CLEAN_UUID})

        # Case 2: parent_page_id 32-hex
        request_parent = Mock(json=AsyncMock(return_value={
            "uid": "test-uid",
            "title": "Sub Page",
            "parent_page_id": "8a99478f6b214f1b857c2b28cf9c9a29",
        }))
        with patch.object(notion, "get_valid_access_token", return_value="token"), \
             patch.object(notion, "notion_api_request", return_value={"id": "sub-page-id"}) as mock_req, \
             patch.object(notion, "append_content_batches", return_value=None):
            res = asyncio.run(notion.tool_create_page(request_parent))
            self.assertIsNone(res.error)
            call_json = mock_req.call_args.kwargs.get("json_data", {})
            self.assertEqual(call_json.get("parent"), {"page_id": self.CLEAN_UUID})

    def test_tool_query_database_sanitizes_database_id(self):
        request = Mock(json=AsyncMock(return_value={
            "uid": "test-uid",
            "database_id": f"database: {self.CLEAN_UUID}",
        }))
        with patch.object(notion, "get_valid_access_token", return_value="token"), \
             patch.object(notion, "notion_api_request") as mock_req:
            mock_req.return_value = {"results": []}
            res = asyncio.run(notion.tool_query_database(request))
            self.assertIsNone(res.error)
            mock_req.assert_called_with("test-uid", "POST", f"/databases/{self.CLEAN_UUID}/query", json_data={"page_size": 10})

    def test_missing_page_id_returns_error(self):
        # Empty string
        req_empty = Mock(json=AsyncMock(return_value={"uid": "test-uid", "page_id": ""}))
        res_empty = asyncio.run(notion.tool_get_page(req_empty))
        self.assertIn("Page ID is required", res_empty.error)

        # Boolean value
        req_bool = Mock(json=AsyncMock(return_value={"uid": "test-uid", "page_id": True}))
        res_bool = asyncio.run(notion.tool_get_page(req_bool))
        self.assertIn("Page ID is required", res_bool.error)


if __name__ == "__main__":
    unittest.main(verbosity=2)
