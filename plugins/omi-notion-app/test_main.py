"""Hermetic production-handler tests; HTTP, framework and token storage are doubles."""
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
    "requests": module("requests", get=Mock()),
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

class PageReadTests(unittest.TestCase):
    def read(self, content_response, archived=False):
        metadata = Mock(status_code=200)
        metadata.json.return_value = {
            "properties": {"title": {"type": "title", "title": [{"plain_text": "Known title"}]}},
            "id": "test-page", "archived": archived,
            "url": "https://www.notion.so/test-page",
            "created_time": "2026-09-01T00:00:00.000Z",
            "last_edited_time": "2026-09-08T00:00:00.000Z",
        }
        request = Mock(json=AsyncMock(return_value={"uid": "test-user", "page_id": "test-page"}))
        with patch.object(notion, "get_valid_access_token", return_value="test-placeholder"), patch.object(notion, "log"), patch.object(notion.requests, "get", side_effect=[metadata, content_response]) as get:
            result = asyncio.run(notion.tool_get_page(request))
        self.assertEqual(get.call_count, 2)
        self.assertTrue(get.call_args.args[0].endswith("/blocks/test-page/children"))
        return result

    def test_failed_content_is_not_an_empty_success(self):
        for status in (403, 429, 500):
            for body in ("", "private upstream response"):
                with self.subTest(status=status, body=body):
                    result = self.read(Mock(status_code=status, text=body))
                    self.assertIsNone(result.result)
                    self.assertTrue(result.error.startswith(f"Failed to retrieve page content (HTTP {status}). Please try again."))
                    self.assertNotIn("private upstream response", result.error)

    def test_transport_failure_is_not_success(self):
        result = self.read(RuntimeError("private transport detail"))
        self.assertIsNone(result.result)
        self.assertTrue(result.error.startswith("Failed to retrieve page content. Please try again."))

    def test_content_errors_retain_known_metadata_without_success(self):
        # Separate metadata/content endpoints: errors must not erase a successful
        # metadata read, or claim that unavailable content is an empty page.
        for archived in (False, True):
            for status in (404, 403, 429, 500, None):
                with self.subTest(archived=archived, status=status):
                    response = (Mock(status_code=status, text="private upstream response")
                                if status else RuntimeError("private transport detail"))
                    result = self.read(response, archived=archived)
                    self.assertIsNone(result.result)
                    self.assertIn("Failed to retrieve page content", result.error)
                    if status:
                        self.assertIn(f"HTTP {status}", result.error)
                    self.assertIn("**Known title**", result.error)
                    self.assertIn("**Status:** Archived" if archived else "**Status:** Active", result.error)
                    self.assertIn("**URL:** https://www.notion.so/test-page", result.error)
                    self.assertIn("**Created:** 2026-09-01", result.error)
                    self.assertIn("**Last Edited:** 2026-09-08", result.error)
                    self.assertIn("**Page ID:** `test-page`", result.error)
                    self.assertNotIn("**Content:**", result.error)
                    self.assertNotIn("private", result.error)

    def test_successful_empty_and_nonempty_content(self):
        for text in ("", "Useful page content"):
            with self.subTest(text=text):
                response = Mock(status_code=200)
                response.json.return_value = {"results": [] if not text else [{"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": text}]}}]}
                result = self.read(response)
                self.assertIsNone(result.error)
                self.assertIn("**Known title**", result.result)
                self.assertEqual("**Content:**" in result.result, bool(text))
                if text:
                    self.assertIn(text, result.result)

if __name__ == "__main__":
    unittest.main(verbosity=2)
