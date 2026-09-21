"""
Hermetic regression tests for sensitive exception leak prevention in Notion app.
Verifies that low-level network errors and runtime exceptions never leak internal credentials,
hostnames, IPs, or exception tracebacks into chat tool responses.
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
    val = types.ModuleType(name)
    val.__dict__.update(attributes)
    return val


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

spec = importlib.util.spec_from_file_location("notion_app", Path(__file__).with_name("main.py"))
notion = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(notion)


class NotionErrorSanitizationTests(unittest.TestCase):
    def test_notion_api_request_exception_sanitization(self):
        sensitive_msg = "ConnectTimeout to https://api.notion.com/v1/pages?token=secret_notion_api_key_xyz"
        err = Exception(sensitive_msg)

        with patch.object(notion, "get_valid_access_token", return_value="valid-token"), \
             patch.object(notion.requests, "get", side_effect=err):
            result = notion.notion_api_request("user1", "GET", "/pages/123")

        self.assertIn("error", result)
        self.assertEqual(result["error"], "Request failed")
        self.assertNotIn("secret_notion_api_key_xyz", result["error"])
        self.assertNotIn("https://api.notion.com", result["error"])

    def test_tool_search_unexpected_exception_sanitization(self):
        sensitive_msg = "RuntimeError: Database pool exhausted at postgres://user:pass@10.0.1.99:5432"
        req = Mock(json=AsyncMock(return_value={"uid": "user1", "query": "meeting notes"}))

        with patch.object(notion, "get_valid_access_token", side_effect=RuntimeError(sensitive_msg)):
            resp = asyncio.run(notion.tool_search(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Search failed")
        self.assertNotIn("10.0.1.99", resp.error)
        self.assertNotIn("pass", resp.error)

    def test_tool_list_pages_unexpected_exception_sanitization(self):
        sensitive_msg = "KeyError: /var/secrets/notion_token.json: 'private_key'"
        req = Mock(json=AsyncMock(return_value={"uid": "user1"}))

        with patch.object(notion, "get_valid_access_token", side_effect=KeyError(sensitive_msg)):
            resp = asyncio.run(notion.tool_list_pages(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Failed to list pages")
        self.assertNotIn("/var/secrets", resp.error)

    def test_tool_get_page_unexpected_exception_sanitization(self):
        sensitive_msg = "Timeout accessing proxy http://gateway.corp:3128 with auth=secret_notion"
        req = Mock(json=AsyncMock(return_value={"uid": "user1", "page_id": "8a99478f6b214f1b857c2b28cf9c9a29"}))

        with patch.object(notion, "get_valid_access_token", side_effect=TimeoutError(sensitive_msg)):
            resp = asyncio.run(notion.tool_get_page(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Failed to get page")
        self.assertNotIn("gateway.corp", resp.error)
        self.assertNotIn("secret_notion", resp.error)

    def test_tool_update_page_unexpected_exception_sanitization(self):
        sensitive_msg = "ConnectionResetError: peer closed socket at 192.168.1.100"
        req = Mock(json=AsyncMock(return_value={
            "uid": "user1",
            "page_id": "8a99478f6b214f1b857c2b28cf9c9a29",
            "title": "Updated Title",
        }))

        with patch.object(notion, "get_valid_access_token", side_effect=ConnectionResetError(sensitive_msg)):
            resp = asyncio.run(notion.tool_update_page(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Failed to update page")
        self.assertNotIn("192.168.1.100", resp.error)

    def test_tool_list_databases_unexpected_exception_sanitization(self):
        sensitive_msg = "MemoryError: worker thread pool exhausted at 0x7fffbeef"
        req = Mock(json=AsyncMock(return_value={"uid": "user1"}))

        with patch.object(notion, "get_valid_access_token", side_effect=MemoryError(sensitive_msg)):
            resp = asyncio.run(notion.tool_list_databases(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Failed to list databases")
        self.assertNotIn("0x7fffbeef", resp.error)

    def test_tool_query_database_unexpected_exception_sanitization(self):
        sensitive_msg = "ValueError: Bad internal state at /etc/ssl/certs/internal.crt"
        req = Mock(json=AsyncMock(return_value={
            "uid": "user1",
            "database_id": "8a99478f6b214f1b857c2b28cf9c9a29",
        }))

        with patch.object(notion, "get_valid_access_token", side_effect=ValueError(sensitive_msg)):
            resp = asyncio.run(notion.tool_query_database(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Failed to query database")
        self.assertNotIn("/etc/ssl", resp.error)


if __name__ == "__main__":
    unittest.main()
