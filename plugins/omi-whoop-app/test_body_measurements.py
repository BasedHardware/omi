"""Hermetic regression tests for the Whoop get_body_measurements chat tool.

Validates that:
1. The tool requests the documented ``/user/measurement/body`` endpoint (not the non-existent ``/body_measurement``).
2. Upstream HTTP 404 (returned when a new/fresh user has no measurements recorded) is gracefully mapped to
   a friendly empty state ("No body measurements available.") rather than hard-failing the chat tool.
3. Other upstream errors (e.g. HTTP 500) surface meaningful status codes in the error envelope.
4. Non-numeric dirty data fields in upstream responses are guarded against TypeError crashes.
5. Missing uid and disconnected accounts are safely rejected.
6. OAuth callback error query parameters are strictly HTML-escaped to prevent reflected XSS.

The suite executes the production handlers through the requests seam and runs on a stdlib-only
interpreter (zero network, runnable under python3 -S).
"""

import asyncio
import html
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).resolve().parent


def _stub_requests():
    mod = types.ModuleType("requests")
    mod.get = mod.post = mod.patch = mod.delete = None
    return mod


def _stub_dotenv():
    mod = types.ModuleType("dotenv")
    mod.load_dotenv = lambda *args, **kwargs: None
    return mod


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
        def __init__(self, content="", status_code=200, *args, **kwargs):
            self.content = content
            self.status_code = status_code

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
    stubs = {
        "requests": _stub_requests(),
        "dotenv": _stub_dotenv(),
        "db": types.ModuleType("db"),
    }
    for name in (
        "store_whoop_tokens", "get_whoop_tokens", "update_whoop_tokens", "delete_whoop_tokens",
        "store_oauth_state", "get_uid_from_oauth_state", "delete_oauth_state",
        "store_user_setting", "get_user_setting",
    ):
        setattr(stubs["db"], name, Mock())

    if importlib.util.find_spec("fastapi") is None:
        fastapi, responses = _stub_fastapi()
        stubs["fastapi"] = fastapi
        stubs["fastapi.responses"] = responses
    if importlib.util.find_spec("pydantic") is None:
        stubs["pydantic"] = _stub_pydantic()

    spec = importlib.util.spec_from_file_location("whoop_main_under_test", HERE / "main.py")
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
    def __init__(self, status_code=200, payload=None, text=""):
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


DOCUMENTED_BODY_MEASUREMENT_URL = "https://api.prod.whoop.com/developer/v1/user/measurement/body"


class BodyMeasurementEndpointTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(main, "get_valid_access_token", return_value="test-token")
        self.addCleanup(patcher.stop)
        patcher.start()

    def _run(self, fake_get, body=None):
        if body is None:
            body = {"uid": "u1"}
        with patch.object(main.requests, "get", side_effect=fake_get) as get:
            response = asyncio.run(main.tool_get_body_measurements(FakeRequest(body)))
        return response, get

    def test_requests_documented_body_measurement_path_and_formats_measurements(self):
        payload = {"height_meter": 1.8288, "weight_kilogram": 90.7185, "max_heart_rate": 200}

        def fake_get(url, headers=None, params=None, timeout=None):
            if url == DOCUMENTED_BODY_MEASUREMENT_URL:
                return FakeResponse(200, payload)
            return FakeResponse(404, text="")

        response, get = self._run(fake_get)

        self.assertEqual(get.call_count, 1)
        self.assertEqual(get.call_args.args[0], DOCUMENTED_BODY_MEASUREMENT_URL)
        self.assertEqual(get.call_args.kwargs["headers"], {"Authorization": "Bearer test-token"})
        self.assertIsNone(response.error)
        self.assertIn("Height:", response.result)
        self.assertIn("183 cm", response.result)
        self.assertIn("Weight:", response.result)
        self.assertIn("90.7 kg", response.result)
        self.assertIn("Max Heart Rate:", response.result)
        self.assertIn("200 bpm", response.result)

    def test_upstream_404_handled_gracefully_as_empty_state(self):
        """When WHOOP returns 404 because user has no measurements yet, tool returns friendly empty state."""
        def fake_get(url, headers=None, params=None, timeout=None):
            return FakeResponse(404, text="Not Found")

        response, _ = self._run(fake_get)

        self.assertIsNone(response.error)
        self.assertEqual(response.result, "No body measurements available.")

    def test_upstream_500_error_reported_with_status(self):
        def fake_get(url, headers=None, params=None, timeout=None):
            return FakeResponse(500, text="Internal Server Error")

        response, _ = self._run(fake_get)

        self.assertIsNone(response.result)
        self.assertIn("500", response.error)
        self.assertIn("Failed to get measurements", response.error)

    def test_missing_uid_returns_error(self):
        response = asyncio.run(main.tool_get_body_measurements(FakeRequest({})))
        self.assertEqual(response.error, "User ID is required")

    def test_unconnected_whoop_returns_error(self):
        with patch.object(main, "get_valid_access_token", return_value=None):
            response = asyncio.run(main.tool_get_body_measurements(FakeRequest({"uid": "u_unauthed"})))
            self.assertEqual(response.error, "Please connect your Whoop first in the app settings.")

    def test_dirty_or_missing_fields_in_payload_guarded(self):
        # Payload with non-numeric fields and None values
        payload = {"height_meter": "not_a_number", "weight_kilogram": None, "max_heart_rate": []}

        def fake_get(url, headers=None, params=None, timeout=None):
            return FakeResponse(200, payload)

        response, _ = self._run(fake_get)
        self.assertIsNone(response.error)
        self.assertEqual(response.result, "No body measurements available.")

    def test_oauth_callback_escapes_html_error(self):
        xss_payload = '<script>alert("xss")</script>'
        res = asyncio.run(main.whoop_callback(error=xss_payload))
        self.assertEqual(res.status_code, 400)
        self.assertNotIn("<script>", res.content)
        self.assertIn("&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;", res.content)


if __name__ == "__main__":
    unittest.main()
