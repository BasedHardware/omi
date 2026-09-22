"""Hermetic unit tests verifying error sanitization in Notion plugin chat tools.
Ensures internal exception details, tracebacks, and sensitive paths are not leaked to users.
"""
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

spec = importlib.util.spec_from_file_location("notion_err_test", Path(__file__).with_name("main.py"))
notion = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(notion)


class NotionErrorSanitizationTests(unittest.TestCase):
    """Verify exception handlers return clean sanitized error strings without leaking internal state."""

    def test_tool_search_exception_sanitized(self):
        req = Mock(json=AsyncMock(return_value={"uid": "user1", "query": "test"}))
        with patch.object(notion, "get_valid_access_token", side_effect=RuntimeError("internal DB connection leak: postgres://sec")):
            res = asyncio.run(notion.tool_search(req))
            self.assertIsNone(res.result)
            self.assertEqual(res.error, "Search failed")
            self.assertNotIn("postgres", res.error)
            self.assertNotIn("internal", res.error)

    def test_tool_list_pages_exception_sanitized(self):
        req = Mock(json=AsyncMock(return_value={"uid": "user1"}))
        with patch.object(notion, "get_valid_access_token", side_effect=RuntimeError("sensitive token decryption failure")):
            res = asyncio.run(notion.tool_list_pages(req))
            self.assertIsNone(res.result)
            self.assertEqual(res.error, "Failed to list pages")
            self.assertNotIn("sensitive", res.error)

    def test_tool_get_page_exception_sanitized(self):
        req = Mock(json=AsyncMock(return_value={"uid": "user1", "page_id": "8a99478f-6b21-4f1b-857c-2b28cf9c9a29"}))
        with patch.object(notion, "get_valid_access_token", side_effect=RuntimeError("redis pool exhausted at 10.0.0.5")):
            res = asyncio.run(notion.tool_get_page(req))
            self.assertIsNone(res.result)
            self.assertEqual(res.error, "Failed to get page")
            self.assertNotIn("10.0.0.5", res.error)

    def test_tool_update_page_exception_sanitized(self):
        req = Mock(json=AsyncMock(return_value={"uid": "user1", "page_id": "8a99478f-6b21-4f1b-857c-2b28cf9c9a29", "title": "New"}))
        with patch.object(notion, "get_valid_access_token", side_effect=RuntimeError("cryptographic key error in vault")):
            res = asyncio.run(notion.tool_update_page(req))
            self.assertIsNone(res.result)
            self.assertEqual(res.error, "Failed to update page")
            self.assertNotIn("cryptographic", res.error)

    def test_tool_list_databases_exception_sanitized(self):
        req = Mock(json=AsyncMock(return_value={"uid": "user1"}))
        with patch.object(notion, "get_valid_access_token", side_effect=RuntimeError("SQLAlchemy unexpected failure")):
            res = asyncio.run(notion.tool_list_databases(req))
            self.assertIsNone(res.result)
            self.assertEqual(res.error, "Failed to list databases")
            self.assertNotIn("SQLAlchemy", res.error)

    def test_tool_query_database_exception_sanitized(self):
        req = Mock(json=AsyncMock(return_value={"uid": "user1", "database_id": "8a99478f-6b21-4f1b-857c-2b28cf9c9a29"}))
        with patch.object(notion, "get_valid_access_token", side_effect=RuntimeError("unhandled null pointer in schema")):
            res = asyncio.run(notion.tool_query_database(req))
            self.assertIsNone(res.result)
            self.assertEqual(res.error, "Failed to query database")
            self.assertNotIn("unhandled", res.error)


if __name__ == "__main__":
    unittest.main(verbosity=2)
