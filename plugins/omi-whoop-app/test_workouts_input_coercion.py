"""Hermetic regression tests for Whoop workout input boundaries (#13931)."""
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


class _FastAPI:
    def __init__(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda function: function

    def post(self, *args, **kwargs):
        return lambda function: function


fastapi = types.ModuleType("fastapi")
fastapi.FastAPI = _FastAPI
fastapi.Request = object
fastapi.Query = lambda default=None, **kwargs: default
fastapi.HTTPException = type("HTTPException", (Exception,), {})
sys.modules["fastapi"] = fastapi

responses = types.ModuleType("fastapi.responses")
responses.HTMLResponse = responses.RedirectResponse = responses.JSONResponse = type("Response", (), {})
sys.modules["fastapi.responses"] = responses

requests = types.ModuleType("requests")
requests.get = requests.post = lambda *args, **kwargs: None
sys.modules["requests"] = requests

dotenv = types.ModuleType("dotenv")
dotenv.load_dotenv = lambda *args, **kwargs: None
sys.modules["dotenv"] = dotenv

db = types.ModuleType("db")
for name in (
    "store_whoop_tokens", "get_whoop_tokens", "update_whoop_tokens",
    "delete_whoop_tokens", "store_oauth_state", "get_uid_from_oauth_state",
    "delete_oauth_state", "store_user_setting", "get_user_setting",
):
    setattr(db, name, lambda *args, **kwargs: None)
sys.modules["db"] = db

models = types.ModuleType("models")

class ChatToolResponse:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

models.ChatToolResponse = ChatToolResponse
sys.modules["models"] = models

PLUGIN_DIR = Path(__file__).resolve().parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))
import main  # noqa: E402


class _Request:
    def __init__(self, body):
        self.body = body

    async def json(self):
        return self.body


WORKOUT = {
    "sport_id": 1,
    "start": "2026-09-15T10:00:00.000Z",
    "end": "2026-09-15T10:45:00.000Z",
    "score": {"strain": 8.5, "average_heart_rate": 140},
}


class CoerceIntTests(unittest.TestCase):
    def test_null_boolean_bad_and_non_integral_use_default(self):
        for value in (None, True, False, "", "oops", 3.5, object()):
            with self.subTest(value=repr(value)):
                self.assertEqual(main._coerce_int(value, 7, 1, 30), 7)

    def test_numeric_strings_and_bounds_are_normalized(self):
        self.assertEqual(main._coerce_int(" 3 ", 7, 1, 30), 3)
        self.assertEqual(main._coerce_int(0, 7, 1, 30), 1)
        self.assertEqual(main._coerce_int(-2, 7, 1, 30), 1)
        self.assertEqual(main._coerce_int(99, 7, 1, 30), 30)


class WorkoutHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def _call(self, body, payload=None):
        payload = payload if payload is not None else {"records": [WORKOUT]}
        with patch.object(main, "get_valid_access_token", return_value="token"), \
             patch.object(main, "whoop_api_request", return_value=payload) as request:
            response = await main.tool_get_workouts(_Request({"uid": "u", **body}))
        return response, request

    async def test_json_null_optionals_fall_back_to_documented_defaults(self):
        response, request = await self._call({"days": None, "max_results": None})
        self.assertIsNone(response.error)
        self.assertIn("Last 7 Days", response.result)
        params = request.call_args.kwargs["params"]
        self.assertEqual(params["limit"], 10)
        self.assertIn("T00:00:00.000Z", params["start"])

    async def test_numeric_strings_are_coerced_and_values_are_clamped(self):
        cases = [
            ({"days": "3", "max_results": "4"}, 3, 4),
            ({"days": 0, "max_results": -2}, 1, 1),
            ({"days": 99, "max_results": 100}, 30, 50),
            ({"days": "bad", "max_results": "bad"}, 7, 10),
        ]
        for body, expected_days, expected_limit in cases:
            with self.subTest(body=body):
                response, request = await self._call(body)
                self.assertIsNone(response.error)
                self.assertIn(f"Last {expected_days} Days", response.result)
                self.assertEqual(request.call_args.kwargs["params"]["limit"], expected_limit)

    async def test_upstream_error_is_returned_as_clean_tool_error(self):
        response, _ = await self._call({}, {"error": "HTTP 503", "status_code": 503})
        self.assertEqual(response.error, "Failed to get workouts: HTTP 503")

    async def test_missing_uid_is_rejected_before_api_access(self):
        with patch.object(main, "get_valid_access_token") as token:
            response = await main.tool_get_workouts(_Request({"days": None}))
        self.assertEqual(response.error, "User ID is required")
        token.assert_not_called()


if __name__ == "__main__":
    unittest.main()
