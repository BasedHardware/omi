"""Hermetic get_workouts input-coercion regressions (#13931).

Import the production module with framework-only stubs, then drive the real
async tool_get_workouts handler through the requests.get seam. The Omi backend
builds Optional[int] fields for non-required manifest params and forwards them
verbatim, so omitted days/max_results arrive as explicit JSON nulls rather than
absent keys; body.get("days", 7) therefore yields None and min(None, 30) used to
crash the handler. No network, credentials, or third-party runtime packages are
required.
"""

from datetime import datetime
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import patch


def load_app():
    class FastAPI:
        def __init__(self, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda handler: handler

        post = get

    class Request:
        pass

    class HTTPException(Exception):
        pass

    def Query(default=None, *args, **kwargs):
        return default

    class _StubResponse:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    fastapi = ModuleType("fastapi")
    fastapi.FastAPI = FastAPI
    fastapi.Request = Request
    fastapi.Query = Query
    fastapi.HTTPException = HTTPException
    responses = ModuleType("fastapi.responses")
    responses.HTMLResponse = _StubResponse
    responses.RedirectResponse = _StubResponse
    responses.JSONResponse = _StubResponse

    requests = ModuleType("requests")

    def _unpatched(*args, **kwargs):
        raise AssertionError("requests stub reached the network seam without a patch")

    requests.get = _unpatched
    requests.post = _unpatched

    dotenv = ModuleType("dotenv")
    dotenv.load_dotenv = lambda *args, **kwargs: None

    db = ModuleType("db")
    db.store_whoop_tokens = lambda *args, **kwargs: None
    db.get_whoop_tokens = lambda uid: {
        "access_token": "test-token",
        "refresh_token": "test-refresh",
        "expires_at": None,
    }
    db.update_whoop_tokens = lambda *args, **kwargs: None
    db.delete_whoop_tokens = lambda *args, **kwargs: None
    db.store_oauth_state = lambda *args, **kwargs: None
    db.get_uid_from_oauth_state = lambda *args, **kwargs: None
    db.delete_oauth_state = lambda *args, **kwargs: None
    db.store_user_setting = lambda *args, **kwargs: None
    db.get_user_setting = lambda *args, **kwargs: None

    class ChatToolResponse:
        def __init__(self, result=None, error=None):
            self.result = result
            self.error = error

    models = ModuleType("models")
    models.ChatToolResponse = ChatToolResponse

    spec = importlib.util.spec_from_file_location("whoop_app", Path(__file__).with_name("main.py"))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "requests": requests,
            "dotenv": dotenv,
            "fastapi": fastapi,
            "fastapi.responses": responses,
            "db": db,
            "models": models,
        },
    ):
        spec.loader.exec_module(module)
    return module


app = load_app()


class _FakeRequest:
    """Stands in for fastapi.Request: the handler awaits .json() once."""

    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


class _FakeWhoopResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = "" if status_code == 200 else "upstream failure"

    def json(self):
        return self._payload


WORKOUT = {
    "sport_id": 1,
    "start": "2026-01-01T10:00:00.000Z",
    "end": "2026-01-01T11:00:00.000Z",
    "score": {
        "strain": 12.3,
        "average_heart_rate": 140,
        "max_heart_rate": 175,
        "kilojoule": 800.0,
    },
}


def _window_days(params):
    """Calendar days between the start/end bounds the handler sent upstream."""
    start = datetime.strptime(params["start"][:10], "%Y-%m-%d")
    end = datetime.strptime(params["end"][:10], "%Y-%m-%d")
    return (end - start).days


class WorkoutsInputCoercionTests(unittest.IsolatedAsyncioTestCase):
    async def _call(self, body, payload=None, status_code=200):
        captured = {}

        def fake_get(url, headers=None, params=None, **kwargs):
            captured["url"] = url
            captured["params"] = dict(params or {})
            return _FakeWhoopResponse(
                {"records": [WORKOUT]} if payload is None else payload,
                status_code=status_code,
            )

        with patch.object(app.requests, "get", fake_get):
            response = await app.tool_get_workouts(_FakeRequest(body))
        return response, captured

    async def test_json_null_optionals_fall_back_to_defaults(self):
        # The backend's ordinary call: omitted Optional[int] manifest params are
        # forwarded as explicit JSON nulls. Regression: min(None, 30) raised
        # TypeError and the handler returned "Failed to get workouts: ...".
        response, captured = await self._call({"uid": "u1", "days": None, "max_results": None})
        self.assertIsNone(response.error)
        self.assertEqual(_window_days(captured["params"]), 7)
        self.assertEqual(captured["params"]["limit"], 10)
        self.assertIn("**Workouts (Last 7 Days)**", response.result)
        self.assertIn("**Running**", response.result)

    async def test_missing_keys_fall_back_to_defaults(self):
        response, captured = await self._call({"uid": "u1"})
        self.assertIsNone(response.error)
        self.assertEqual(_window_days(captured["params"]), 7)
        self.assertEqual(captured["params"]["limit"], 10)

    async def test_numeric_strings_are_coerced(self):
        response, captured = await self._call({"uid": "u1", "days": "3", "max_results": "5"})
        self.assertIsNone(response.error)
        self.assertEqual(_window_days(captured["params"]), 3)
        self.assertEqual(captured["params"]["limit"], 5)

    async def test_non_positive_values_are_clamped_to_one(self):
        # days=0 used to produce an empty window (start == end); non-positive
        # max_results was forwarded to WHOOP's limit, which rejects it.
        response, captured = await self._call({"uid": "u1", "days": 0, "max_results": 0})
        self.assertIsNone(response.error)
        self.assertEqual(_window_days(captured["params"]), 1)
        self.assertEqual(captured["params"]["limit"], 1)

    async def test_negative_values_are_clamped_to_one(self):
        response, captured = await self._call({"uid": "u1", "days": -5, "max_results": -2})
        self.assertIsNone(response.error)
        self.assertEqual(_window_days(captured["params"]), 1)
        self.assertEqual(captured["params"]["limit"], 1)

    async def test_oversized_days_capped_at_30(self):
        response, captured = await self._call({"uid": "u1", "days": 365})
        self.assertIsNone(response.error)
        self.assertEqual(_window_days(captured["params"]), 30)

    async def test_oversized_max_results_capped_at_50(self):
        response, captured = await self._call({"uid": "u1", "max_results": 999})
        self.assertIsNone(response.error)
        self.assertEqual(captured["params"]["limit"], 50)

    async def test_boundary_values_pass_through_unchanged(self):
        response, captured = await self._call({"uid": "u1", "days": 30, "max_results": 50})
        self.assertIsNone(response.error)
        self.assertEqual(_window_days(captured["params"]), 30)
        self.assertEqual(captured["params"]["limit"], 50)

    async def test_in_range_values_pass_through_unchanged(self):
        response, captured = await self._call({"uid": "u1", "days": 14, "max_results": 20})
        self.assertIsNone(response.error)
        self.assertEqual(_window_days(captured["params"]), 14)
        self.assertEqual(captured["params"]["limit"], 20)

    async def test_unparseable_days_falls_back_to_default(self):
        response, captured = await self._call({"uid": "u1", "days": "abc"})
        self.assertIsNone(response.error)
        self.assertEqual(_window_days(captured["params"]), 7)

    async def test_unparseable_max_results_falls_back_to_default(self):
        response, captured = await self._call({"uid": "u1", "max_results": "lots"})
        self.assertIsNone(response.error)
        self.assertEqual(captured["params"]["limit"], 10)

    async def test_booleans_fall_back_to_defaults(self):
        # bool is an int subclass; True/False must not silently become 1/0.
        response, captured = await self._call({"uid": "u1", "days": True, "max_results": False})
        self.assertIsNone(response.error)
        self.assertEqual(_window_days(captured["params"]), 7)
        self.assertEqual(captured["params"]["limit"], 10)

    async def test_list_value_falls_back_to_default(self):
        response, captured = await self._call({"uid": "u1", "days": [7]})
        self.assertIsNone(response.error)
        self.assertEqual(_window_days(captured["params"]), 7)

    async def test_missing_uid_returns_error_without_calling_whoop(self):
        response, captured = await self._call({"days": 3})
        self.assertEqual(response.error, "User ID is required")
        self.assertNotIn("params", captured)

    async def test_unauthenticated_user_gets_connect_prompt(self):
        with patch.object(app, "get_whoop_tokens", return_value=None):
            response, captured = await self._call({"uid": "u1", "days": None})
        self.assertIn("connect your Whoop", response.error)
        self.assertNotIn("params", captured)

    async def test_empty_records_reports_no_workouts_in_window(self):
        response, _ = await self._call({"uid": "u1", "days": None}, payload={"records": []})
        self.assertIsNone(response.error)
        self.assertEqual(response.result, "No workouts in the last 7 days.")

    async def test_upstream_error_surfaces_as_error_response(self):
        response, _ = await self._call({"uid": "u1"}, payload={"records": []}, status_code=500)
        self.assertIn("Failed to get workouts", response.error)


if __name__ == "__main__":
    unittest.main()
