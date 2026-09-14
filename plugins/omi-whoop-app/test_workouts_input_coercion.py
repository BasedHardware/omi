"""Regression tests for get_workouts optional-integer handling.

The Omi backend models every optional tool parameter as ``Optional[int]``
with a ``None`` default and forwards the model's arguments verbatim, so
``{"days": null}`` is a legal request body. ``tool_get_workouts`` used to do
``min(body.get("days", 7), 30)`` on the raw value, which raises ``TypeError``
for ``None`` (and for numeric strings), turning an ordinary "show my
workouts" into ``Failed to get workouts: '<' not supported ...``. Values of
``0`` or below were forwarded to WHOOP unchanged as a zero/negative
``limit`` or an empty date window.

The suite executes the production handler through the ``requests.get`` seam
and runs on a stdlib-only interpreter: ``requests``/``dotenv`` are always
stubbed (no network is ever attempted) and ``fastapi``/``pydantic`` are only
stubbed when they are not installed, matching the sibling plugin suites.
"""

import asyncio
import importlib.util
import sys
import types
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def _stub_requests():
    module = types.ModuleType("requests")
    module.get = module.post = None
    return module


def _stub_dotenv():
    module = types.ModuleType("dotenv")
    module.load_dotenv = lambda *args, **kwargs: None
    return module


def _stub_fastapi():
    fastapi = types.ModuleType("fastapi")

    class FastAPI:
        def __init__(self, *args, **kwargs):
            pass

        def _route(self, *args, **kwargs):
            return lambda fn: fn

        get = post = _route

    class Request:
        pass

    class HTTPException(Exception):
        def __init__(self, status_code=500, detail=""):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    def Query(default=None, *args, **kwargs):
        return default

    fastapi.FastAPI = FastAPI
    fastapi.Request = Request
    fastapi.HTTPException = HTTPException
    fastapi.Query = Query

    responses = types.ModuleType("fastapi.responses")

    class _Response:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    responses.HTMLResponse = responses.RedirectResponse = responses.JSONResponse = _Response
    fastapi.responses = responses
    return fastapi, responses


def _stub_pydantic():
    pydantic = types.ModuleType("pydantic")

    class BaseModel:
        def __init__(self, **kwargs):
            for name in ("result", "error"):
                setattr(self, name, kwargs.get(name))

    pydantic.BaseModel = BaseModel
    return pydantic


def _load_main():
    stubs = {"requests": _stub_requests(), "dotenv": _stub_dotenv()}
    if importlib.util.find_spec("fastapi") is None:
        fastapi, responses = _stub_fastapi()
        stubs["fastapi"] = fastapi
        stubs["fastapi.responses"] = responses
    if importlib.util.find_spec("pydantic") is None:
        stubs["pydantic"] = _stub_pydantic()

    spec = importlib.util.spec_from_file_location("whoop_main", HERE / "main.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(HERE))
    try:
        with patch.dict(sys.modules, stubs):
            spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(HERE))
    return module


main = _load_main()


class FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


class FakeRequest:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


WORKOUT = {
    "sport_id": 1,
    "start": "2026-09-13T07:00:00.000Z",
    "end": "2026-09-13T07:30:00.000Z",
    "score": {"strain": 8.2, "average_heart_rate": 140, "max_heart_rate": 170, "kilojoule": 1200.0},
}


def _window_days(params):
    start = datetime.strptime(params["start"], "%Y-%m-%dT%H:%M:%S.%fZ")
    end = datetime.strptime(params["end"], "%Y-%m-%dT%H:%M:%S.%fZ")
    return (end.date() - start.date()).days


class WorkoutsInputCoercionTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(main, "get_valid_access_token", return_value="test-token")
        self.addCleanup(patcher.stop)
        patcher.start()

    def _run(self, body):
        calls = []

        def fake_get(url, headers=None, params=None):
            calls.append((url, dict(params or {})))
            return FakeResponse(200, {"records": [WORKOUT]})

        with patch.object(main.requests, "get", side_effect=fake_get):
            response = asyncio.run(main.tool_get_workouts(FakeRequest({"uid": "u1", **body})))
        return response, calls

    def test_json_null_optionals_fall_back_to_defaults(self):
        response, calls = self._run({"days": None, "max_results": None})

        self.assertIsNone(response.error, response.error)
        self.assertEqual(len(calls), 1)
        url, params = calls[0]
        self.assertTrue(url.endswith("/activity/workout"))
        self.assertEqual(params["limit"], 10)
        self.assertEqual(_window_days(params), 7)
        self.assertIn("**Workouts (Last 7 Days)**", response.result)
        self.assertIn("**Running** (30 min)", response.result)

    def test_numeric_strings_are_coerced(self):
        response, calls = self._run({"days": "3", "max_results": "5"})

        self.assertIsNone(response.error, response.error)
        _, params = calls[0]
        self.assertEqual(params["limit"], 5)
        self.assertEqual(_window_days(params), 3)
        self.assertIn("**Workouts (Last 3 Days)**", response.result)

    def test_non_positive_values_are_clamped_to_one(self):
        response, calls = self._run({"days": 0, "max_results": -2})

        self.assertIsNone(response.error, response.error)
        _, params = calls[0]
        self.assertEqual(params["limit"], 1)
        self.assertEqual(_window_days(params), 1)

    def test_oversized_values_are_capped(self):
        response, calls = self._run({"days": 90, "max_results": 500})

        self.assertIsNone(response.error, response.error)
        _, params = calls[0]
        self.assertEqual(params["limit"], 50)
        self.assertEqual(_window_days(params), 30)
        self.assertIn("**Workouts (Last 30 Days)**", response.result)

    def test_unparseable_values_fall_back_to_defaults(self):
        response, calls = self._run({"days": "last week", "max_results": [10]})

        self.assertIsNone(response.error, response.error)
        _, params = calls[0]
        self.assertEqual(params["limit"], 10)
        self.assertEqual(_window_days(params), 7)

    def test_overflowing_json_numbers_fall_back_to_defaults(self):
        # json.loads turns 1e309 into float('inf'); int(inf) raises OverflowError.
        response, calls = self._run({"days": float("inf"), "max_results": float("-inf")})

        self.assertIsNone(response.error, response.error)
        _, params = calls[0]
        self.assertEqual(params["limit"], 10)
        self.assertEqual(_window_days(params), 7)


if __name__ == "__main__":
    unittest.main()
