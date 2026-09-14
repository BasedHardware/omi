"""Regression tests for list_events optional-integer handling.

The Omi backend models every optional tool parameter as ``Optional[int]``
with a ``None`` default and forwards the model's arguments verbatim, so
``{"days": null, "max_results": null}`` is what an ordinary "what's on my
calendar?" request looks like on the wire. ``tool_list_events`` used to do
``min(body.get("days", 7), 30)`` on the raw value, which raises ``TypeError``
for ``None`` (and for numeric strings), so the tool answered
``Failed to list events: '<' not supported ...``. Values of ``0`` or below
were forwarded unchanged as an empty time window or a ``maxResults`` Google
rejects.

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
    module.get = module.post = module.put = module.patch = module.delete = None
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

    spec = importlib.util.spec_from_file_location("gcal_main", HERE / "main.py")
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


EVENT = {
    "id": "abc123def456ghi789jkl012",
    "summary": "Team standup",
    "location": "Room 4",
    "start": {"dateTime": "2026-09-15T09:00:00Z"},
    "end": {"dateTime": "2026-09-15T09:30:00Z"},
}


def _window_days(params):
    start = datetime.fromisoformat(params["timeMin"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(params["timeMax"].replace("Z", "+00:00"))
    return (end - start).days


class ListEventsInputCoercionTests(unittest.TestCase):
    def setUp(self):
        for name, value in (("get_valid_access_token", "test-token"), ("get_default_calendar", "primary")):
            patcher = patch.object(main, name, return_value=value)
            self.addCleanup(patcher.stop)
            patcher.start()

    def _run(self, body, items=(EVENT,)):
        calls = []

        def fake_get(url, headers=None, params=None):
            calls.append((url, dict(params or {})))
            return FakeResponse(200, {"items": list(items)})

        with patch.object(main.requests, "get", side_effect=fake_get):
            response = asyncio.run(main.tool_list_events(FakeRequest({"uid": "u1", **body})))
        return response, calls

    def test_json_null_optionals_fall_back_to_defaults(self):
        response, calls = self._run({"days": None, "max_results": None})

        self.assertIsNone(response.error, response.error)
        self.assertEqual(len(calls), 1)
        url, params = calls[0]
        self.assertTrue(url.endswith("/calendars/primary/events"), url)
        self.assertEqual(params["maxResults"], 10)
        self.assertEqual(_window_days(params), 7)
        self.assertIn("**Upcoming Events (1)**", response.result)
        self.assertIn("**Team standup**", response.result)

    def test_json_null_optionals_with_no_events_reports_default_window(self):
        response, _ = self._run({"days": None, "max_results": None}, items=())

        self.assertIsNone(response.error, response.error)
        self.assertEqual(response.result, "No events in the next 7 days.")

    def test_numeric_strings_are_coerced(self):
        response, calls = self._run({"days": "3", "max_results": "5"})

        self.assertIsNone(response.error, response.error)
        _, params = calls[0]
        self.assertEqual(params["maxResults"], 5)
        self.assertEqual(_window_days(params), 3)

    def test_non_positive_values_are_clamped_to_one(self):
        response, calls = self._run({"days": 0, "max_results": -2})

        self.assertIsNone(response.error, response.error)
        _, params = calls[0]
        self.assertEqual(params["maxResults"], 1)
        self.assertEqual(_window_days(params), 1)

    def test_oversized_values_are_capped(self):
        response, calls = self._run({"days": 90, "max_results": 500})

        self.assertIsNone(response.error, response.error)
        _, params = calls[0]
        self.assertEqual(params["maxResults"], 50)
        self.assertEqual(_window_days(params), 30)

    def test_unparseable_values_fall_back_to_defaults(self):
        response, calls = self._run({"days": "next week", "max_results": [10]})

        self.assertIsNone(response.error, response.error)
        _, params = calls[0]
        self.assertEqual(params["maxResults"], 10)
        self.assertEqual(_window_days(params), 7)


if __name__ == "__main__":
    unittest.main()
