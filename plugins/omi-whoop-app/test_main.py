"""Hermetic Whoop tool regressions for BasedHardware/omi#13927.

Import the production module with framework-only stubs, then exercise the real
tool handlers through the ``requests.get`` seam. No network, credentials, or
third-party runtime packages are required.
"""

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

    def Query(default=None, **kwargs):
        return default

    class HTTPException(Exception):
        def __init__(self, status_code=None, detail=None):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class _Response:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class ChatToolResponse:
        def __init__(self, result=None, error=None):
            self.result = result
            self.error = error

    requests = ModuleType("requests")
    requests.get = lambda *args, **kwargs: None
    requests.post = lambda *args, **kwargs: None

    dotenv = ModuleType("dotenv")
    dotenv.load_dotenv = lambda *args, **kwargs: None

    fastapi = ModuleType("fastapi")
    fastapi.FastAPI = FastAPI
    fastapi.Request = object
    fastapi.Query = Query
    fastapi.HTTPException = HTTPException

    responses = ModuleType("fastapi.responses")
    responses.HTMLResponse = _Response
    responses.RedirectResponse = _Response
    responses.JSONResponse = _Response

    db = ModuleType("db")
    for name in (
        "store_whoop_tokens",
        "update_whoop_tokens",
        "delete_whoop_tokens",
        "store_oauth_state",
        "delete_oauth_state",
        "store_user_setting",
    ):
        setattr(db, name, lambda *args, **kwargs: None)
    for name in ("get_whoop_tokens", "get_uid_from_oauth_state", "get_user_setting"):
        setattr(db, name, lambda *args, **kwargs: None)

    models = ModuleType("models")
    models.ChatToolResponse = ChatToolResponse

    spec = importlib.util.spec_from_file_location(
        "whoop_app", Path(__file__).with_name("main.py")
    )
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

MEASUREMENTS_URL = (
    "https://api.prod.whoop.com/developer/v1/user/measurement/body"
)


class FakeUpstreamResponse:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}
        self.text = text

    def json(self):
        return self._json_data


class FakeChatRequest:
    """Stand-in for fastapi.Request carrying a parsed JSON body."""

    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


class BodyMeasurementsTests(unittest.IsolatedAsyncioTestCase):
    async def test_requests_documented_body_measurements_path(self):
        """The tool must call GET /user/measurement/body, not the nonexistent
        /body_measurement route (#13927). A fake WHOOP that only answers on the
        documented path proves the URL, bearer header, and result formatting."""
        calls = []

        def fake_get(url, headers=None, params=None, **kwargs):
            calls.append({"url": url, "headers": headers, "params": params})
            if url == MEASUREMENTS_URL:
                return FakeUpstreamResponse(
                    200,
                    {
                        "height_meter": 1.8,
                        "weight_kilogram": 75.0,
                        "max_heart_rate": 190,
                    },
                )
            return FakeUpstreamResponse(404, text="")

        with patch.object(
            app, "get_valid_access_token", return_value="test-token"
        ), patch.object(app.requests, "get", side_effect=fake_get):
            response = await app.tool_get_body_measurements(
                FakeChatRequest({"uid": "u1"})
            )

        self.assertIsNone(response.error)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["url"], MEASUREMENTS_URL)
        self.assertEqual(
            calls[0]["headers"], {"Authorization": "Bearer test-token"}
        )
        self.assertIn("**Height:** 180 cm", response.result)
        self.assertIn("**Weight:** 75.0 kg", response.result)
        self.assertIn("**Max Heart Rate:** 190 bpm", response.result)

    async def test_empty_error_body_surfaces_http_status(self):
        """A 404 with an empty upstream body must surface 'HTTP 404', never a
        blank 'Failed to get measurements: ' reason."""
        def fake_get(url, headers=None, params=None, **kwargs):
            return FakeUpstreamResponse(404, text="")

        with patch.object(
            app, "get_valid_access_token", return_value="test-token"
        ), patch.object(app.requests, "get", side_effect=fake_get):
            response = await app.tool_get_body_measurements(
                FakeChatRequest({"uid": "u1"})
            )

        self.assertIsNotNone(response.error)
        self.assertIn("404", response.error)
        self.assertNotEqual(response.error.strip(), "Failed to get measurements:")


class WorkoutsNullParamTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_null_optional_params_fall_back_to_defaults(self):
        """JSON-null optional params must not crash min(); the request still
        goes out with the documented default window/limit."""
        calls = []

        def fake_get(url, headers=None, params=None, **kwargs):
            calls.append({"url": url, "params": params})
            return FakeUpstreamResponse(200, {"records": []})

        with patch.object(
            app, "get_valid_access_token", return_value="test-token"
        ), patch.object(app.requests, "get", side_effect=fake_get):
            response = await app.tool_get_workouts(
                FakeChatRequest(
                    {"uid": "u1", "days": None, "max_results": None}
                )
            )

        self.assertIsNone(response.error)
        self.assertIn("No workouts in the last 7 days.", response.result)
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0]["url"].endswith("/activity/workout"))
        self.assertEqual(calls[0]["params"]["limit"], 10)


if __name__ == "__main__":
    unittest.main()
