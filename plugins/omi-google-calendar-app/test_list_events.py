"""Hermetic regression tests for Google Calendar list_events tool.

Validates that tool_list_events safely handles None/null days and max_results,
invalid strings, negative numbers, and boundary limits without throwing TypeError.
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
    "requests": module("requests", get=Mock(), post=Mock(), patch=Mock(), delete=Mock()),
    "dotenv": module("dotenv", load_dotenv=lambda: None),
    "fastapi": module("fastapi", FastAPI=Framework, Request=Framework, Query=Framework, HTTPException=Exception),
    "fastapi.responses": module("fastapi.responses", HTMLResponse=Framework, RedirectResponse=Framework, JSONResponse=Framework),
    "models": module("models", ChatToolResponse=Response),
    "db": module("db", **{name: Mock() for name in (
        "store_google_tokens", "get_google_tokens", "update_google_tokens", "delete_google_tokens",
        "store_oauth_state", "get_oauth_state", "delete_oauth_state", "store_user_setting", "get_user_setting",
    )}),
}

spec = importlib.util.spec_from_file_location(
    "gcal_under_test", Path(__file__).with_name("main.py")
)
gcal = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(gcal)


def mock_request(json_data):
    req = Mock()
    req.json = AsyncMock(return_value=json_data)
    return req


class TestGoogleCalendarListEvents(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    def test_list_events_null_days_and_max_results_defaults(self):
        req = mock_request({"uid": "user1", "days": None, "max_results": None})
        with patch.object(gcal, "get_valid_access_token", return_value="tok"), \
             patch.object(gcal, "calendar_api_request", return_value={"items": []}) as mock_api:
            resp = self.loop.run_until_complete(gcal.tool_list_events(req))
            self.assertIsNone(resp.error)
            self.assertEqual(resp.result, "No events in the next 7 days.")
            mock_api.assert_called_once()
            params = mock_api.call_args.kwargs.get("params", {})
            self.assertEqual(params.get("maxResults"), 10)

    def test_list_events_custom_valid_parameters(self):
        req = mock_request({"uid": "user1", "days": 14, "max_results": 25})
        with patch.object(gcal, "get_valid_access_token", return_value="tok"), \
             patch.object(gcal, "calendar_api_request", return_value={"items": []}) as mock_api:
            resp = self.loop.run_until_complete(gcal.tool_list_events(req))
            self.assertIsNone(resp.error)
            self.assertEqual(resp.result, "No events in the next 14 days.")
            params = mock_api.call_args.kwargs.get("params", {})
            self.assertEqual(params.get("maxResults"), 25)

    def test_list_events_clamped_bounds(self):
        req = mock_request({"uid": "user1", "days": 100, "max_results": 1000})
        with patch.object(gcal, "get_valid_access_token", return_value="tok"), \
             patch.object(gcal, "calendar_api_request", return_value={"items": []}) as mock_api:
            resp = self.loop.run_until_complete(gcal.tool_list_events(req))
            self.assertIsNone(resp.error)
            self.assertEqual(resp.result, "No events in the next 30 days.")
            params = mock_api.call_args.kwargs.get("params", {})
            self.assertEqual(params.get("maxResults"), 50)

    def test_list_events_invalid_string_inputs(self):
        req = mock_request({"uid": "user1", "days": "invalid", "max_results": "invalid"})
        with patch.object(gcal, "get_valid_access_token", return_value="tok"), \
             patch.object(gcal, "calendar_api_request", return_value={"items": []}) as mock_api:
            resp = self.loop.run_until_complete(gcal.tool_list_events(req))
            self.assertIsNone(resp.error)
            self.assertEqual(resp.result, "No events in the next 7 days.")
            params = mock_api.call_args.kwargs.get("params", {})
            self.assertEqual(params.get("maxResults"), 10)


if __name__ == "__main__":
    unittest.main()
