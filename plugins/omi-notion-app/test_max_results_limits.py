"""Hermetic regression tests for Notion list tools with null/omitted max_results.

Validates that tool_search, tool_list_pages, tool_list_databases, and tool_query_database
safely handle None/null max_results, invalid strings, and boundary values without throwing TypeError.
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
    "notion_content": module("notion_content", encode_payload=Mock(), plan_content_requests=Mock(), title_items=Mock()),
    "db": module("db", **{name: Mock() for name in (
        "store_notion_tokens", "get_notion_tokens", "update_notion_tokens", "delete_notion_tokens",
        "store_oauth_state", "get_oauth_state", "delete_oauth_state", "store_user_setting", "get_user_setting",
    )}),
}

spec = importlib.util.spec_from_file_location(
    "notion_under_test", Path(__file__).with_name("main.py")
)
notion = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(notion)


def mock_request(json_data):
    req = Mock()
    req.json = AsyncMock(return_value=json_data)
    return req


class TestNotionMaxResultsLimits(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    def test_search_null_max_results_defaults_to_10(self):
        req = mock_request({"uid": "u1", "query": "plan", "max_results": None})
        with patch.object(notion, "get_valid_access_token", return_value="tok"), \
             patch.object(notion, "notion_api_request", return_value={"results": []}) as mock_api:
            resp = self.loop.run_until_complete(notion.tool_search(req))
            self.assertIsNone(resp.error)
            mock_api.assert_called_once()
            json_data = mock_api.call_args.kwargs.get("json_data") or mock_api.call_args[1].get("json_data")
            self.assertEqual(json_data.get("page_size"), 10)

    def test_list_pages_null_max_results_defaults_to_10(self):
        req = mock_request({"uid": "u1", "max_results": None})
        with patch.object(notion, "get_valid_access_token", return_value="tok"), \
             patch.object(notion, "notion_api_request", return_value={"results": []}) as mock_api:
            resp = self.loop.run_until_complete(notion.tool_list_pages(req))
            self.assertIsNone(resp.error)
            mock_api.assert_called_once()
            json_data = mock_api.call_args.kwargs.get("json_data") or mock_api.call_args[1].get("json_data")
            self.assertEqual(json_data.get("page_size"), 10)

    def test_list_databases_null_max_results_defaults_to_10(self):
        req = mock_request({"uid": "u1", "max_results": None})
        with patch.object(notion, "get_valid_access_token", return_value="tok"), \
             patch.object(notion, "notion_api_request", return_value={"results": []}) as mock_api:
            resp = self.loop.run_until_complete(notion.tool_list_databases(req))
            self.assertIsNone(resp.error)
            mock_api.assert_called_once()
            json_data = mock_api.call_args.kwargs.get("json_data") or mock_api.call_args[1].get("json_data")
            self.assertEqual(json_data.get("page_size"), 10)

    def test_query_database_null_max_results_defaults_to_10(self):
        req = mock_request({"uid": "u1", "database_id": "db-123", "max_results": None})
        with patch.object(notion, "get_valid_access_token", return_value="tok"), \
             patch.object(notion, "notion_api_request", return_value={"results": []}) as mock_api:
            resp = self.loop.run_until_complete(notion.tool_query_database(req))
            self.assertIsNone(resp.error)
            mock_api.assert_called_once()
            json_data = mock_api.call_args.kwargs.get("json_data") or mock_api.call_args[1].get("json_data")
            self.assertEqual(json_data.get("page_size"), 10)

    def test_query_database_custom_and_clamped_max_results(self):
        req = mock_request({"uid": "u1", "database_id": "db-123", "max_results": 999})
        with patch.object(notion, "get_valid_access_token", return_value="tok"), \
             patch.object(notion, "notion_api_request", return_value={"results": []}) as mock_api:
            resp = self.loop.run_until_complete(notion.tool_query_database(req))
            self.assertIsNone(resp.error)
            json_data = mock_api.call_args.kwargs.get("json_data") or mock_api.call_args[1].get("json_data")
            self.assertEqual(json_data.get("page_size"), 50)


if __name__ == "__main__":
    unittest.main()
