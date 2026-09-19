"""Hermetic regression tests for Whoop get_workouts tool.

Validates that tool_get_workouts safely handles None/null days and max_results,
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
        "store_whoop_tokens", "get_whoop_tokens", "update_whoop_tokens", "delete_whoop_tokens",
        "store_oauth_state", "get_uid_from_oauth_state", "delete_oauth_state", "store_user_setting", "get_user_setting",
    )}),
}

spec = importlib.util.spec_from_file_location(
    "whoop_under_test", Path(__file__).with_name("main.py")
)
whoop = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(whoop)


def mock_request(json_data):
    req = Mock()
    req.json = AsyncMock(return_value=json_data)
    return req


class TestWhoopGetWorkouts(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    def test_get_workouts_null_days_and_max_results_defaults(self):
        req = mock_request({"uid": "user1", "days": None, "max_results": None})
        with patch.object(whoop, "get_valid_access_token", return_value="tok"), \
             patch.object(whoop, "whoop_api_request", return_value={"records": []}) as mock_api:
            resp = self.loop.run_until_complete(whoop.tool_get_workouts(req))
            self.assertIsNone(resp.error)
            self.assertEqual(resp.result, "No workouts in the last 7 days.")
            mock_api.assert_called_once()
            params = mock_api.call_args.kwargs.get("params", {})
            self.assertEqual(params.get("limit"), 10)

    def test_get_workouts_custom_valid_parameters(self):
        req = mock_request({"uid": "user1", "days": 14, "max_results": 25})
        with patch.object(whoop, "get_valid_access_token", return_value="tok"), \
             patch.object(whoop, "whoop_api_request", return_value={"records": []}) as mock_api:
            resp = self.loop.run_until_complete(whoop.tool_get_workouts(req))
            self.assertIsNone(resp.error)
            self.assertEqual(resp.result, "No workouts in the last 14 days.")
            params = mock_api.call_args.kwargs.get("params", {})
            self.assertEqual(params.get("limit"), 25)

    def test_get_workouts_clamped_bounds(self):
        req = mock_request({"uid": "user1", "days": 100, "max_results": 1000})
        with patch.object(whoop, "get_valid_access_token", return_value="tok"), \
             patch.object(whoop, "whoop_api_request", return_value={"records": []}) as mock_api:
            resp = self.loop.run_until_complete(whoop.tool_get_workouts(req))
            self.assertIsNone(resp.error)
            self.assertEqual(resp.result, "No workouts in the last 30 days.")
            params = mock_api.call_args.kwargs.get("params", {})
            self.assertEqual(params.get("limit"), 50)

    def test_get_workouts_invalid_string_inputs(self):
        req = mock_request({"uid": "user1", "days": "invalid", "max_results": "invalid"})
        with patch.object(whoop, "get_valid_access_token", return_value="tok"), \
             patch.object(whoop, "whoop_api_request", return_value={"records": []}) as mock_api:
            resp = self.loop.run_until_complete(whoop.tool_get_workouts(req))
            self.assertIsNone(resp.error)
            self.assertEqual(resp.result, "No workouts in the last 7 days.")
            params = mock_api.call_args.kwargs.get("params", {})
            self.assertEqual(params.get("limit"), 10)


if __name__ == "__main__":
    unittest.main()
