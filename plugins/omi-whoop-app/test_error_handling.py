"""Hermetic tests for Whoop app tool error sanitization.

Ensures that internal exceptions or sensitive runtime details do not leak into
user-facing ChatToolResponse error messages.
"""

import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch


def load_whoop_app():
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
            self.content = kwargs.get("content", args[0] if args else "")
            self.status_code = kwargs.get("status_code", 200)

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

    spec = importlib.util.spec_from_file_location("whoop_app_error_sanitization", Path(__file__).with_name("main.py"))
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


app = load_whoop_app()


class FakeChatRequest:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


class TestWhoopErrorSanitization(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(app, "get_valid_access_token", return_value="test-token")
        self.addCleanup(patcher.stop)
        patcher.start()

    def test_tool_get_recovery_sanitizes_errors(self):
        sensitive_msg = "DatabaseConnectionError: sql://secret_pw@10.0.0.5:5432"
        with patch.object(app, "whoop_api_request", side_effect=RuntimeError(sensitive_msg)):
            req = FakeChatRequest({"uid": "user123"})
            res = asyncio.run(app.tool_get_recovery(req))
            self.assertIsNotNone(res.error)
            self.assertNotIn("DatabaseConnectionError", res.error)
            self.assertNotIn("secret_pw", res.error)
            self.assertNotIn("10.0.0.5", res.error)
            self.assertEqual(res.error, "Failed to get recovery. Please try again.")

    def test_tool_get_strain_sanitizes_errors(self):
        sensitive_msg = "TimeoutError: connection to https://api.prod.whoop.internal timed out"
        with patch.object(app, "whoop_api_request", side_effect=Exception(sensitive_msg)):
            req = FakeChatRequest({"uid": "user123"})
            res = asyncio.run(app.tool_get_strain(req))
            self.assertIsNotNone(res.error)
            self.assertNotIn("TimeoutError", res.error)
            self.assertNotIn("api.prod.whoop.internal", res.error)
            self.assertEqual(res.error, "Failed to get strain. Please try again.")

    def test_tool_get_sleep_sanitizes_errors(self):
        sensitive_msg = "OAuthTokenExpiredError: secret_refresh_token_leak"
        with patch.object(app, "whoop_api_request", side_effect=Exception(sensitive_msg)):
            req = FakeChatRequest({"uid": "user123"})
            res = asyncio.run(app.tool_get_sleep(req))
            self.assertIsNotNone(res.error)
            self.assertNotIn("secret_refresh_token_leak", res.error)
            self.assertEqual(res.error, "Failed to get sleep. Please try again.")

    def test_tool_get_workouts_sanitizes_errors(self):
        sensitive_msg = "ConnectionRefused: raw socket closed at /var/run/socket"
        with patch.object(app, "whoop_api_request", side_effect=Exception(sensitive_msg)):
            req = FakeChatRequest({"uid": "user123"})
            res = asyncio.run(app.tool_get_workouts(req))
            self.assertIsNotNone(res.error)
            self.assertNotIn("raw socket closed", res.error)
            self.assertEqual(res.error, "Failed to get workouts. Please try again.")

    def test_tool_get_weekly_summary_sanitizes_errors(self):
        sensitive_msg = "ZeroDivisionError: integer division by zero in /opt/app/calculations.py"
        with patch.object(app, "whoop_api_request", side_effect=Exception(sensitive_msg)):
            req = FakeChatRequest({"uid": "user123"})
            res = asyncio.run(app.tool_get_weekly_summary(req))
            self.assertIsNotNone(res.error)
            self.assertNotIn("ZeroDivisionError", res.error)
            self.assertNotIn("/opt/app/calculations.py", res.error)
            self.assertEqual(res.error, "Failed to get weekly summary. Please try again.")

    def test_tool_get_body_measurements_sanitizes_errors(self):
        sensitive_msg = "KeyError: 'height_meter' at line 428 in main.py"
        with patch.object(app, "whoop_api_request", side_effect=Exception(sensitive_msg)):
            req = FakeChatRequest({"uid": "user123"})
            res = asyncio.run(app.tool_get_body_measurements(req))
            self.assertIsNotNone(res.error)
            self.assertNotIn("KeyError", res.error)
            self.assertNotIn("line 428", res.error)
            self.assertEqual(res.error, "Failed to get measurements. Please try again.")

    def test_tool_get_profile_sanitizes_errors(self):
        sensitive_msg = "SSLError: certificate verify failed for user profile endpoint"
        with patch.object(app, "whoop_api_request", side_effect=Exception(sensitive_msg)):
            req = FakeChatRequest({"uid": "user123"})
            res = asyncio.run(app.tool_get_profile(req))
            self.assertIsNotNone(res.error)
            self.assertNotIn("SSLError", res.error)
            self.assertEqual(res.error, "Failed to get profile. Please try again.")

    def test_whoop_callback_exception_sanitized(self):
        sensitive_msg = "ConnectionRefusedError: failed to connect to oauth.whoop.com:443"
        with patch.object(app, "get_uid_from_oauth_state", return_value="uid123"), patch.object(
            app.requests, "post", side_effect=RuntimeError(sensitive_msg)
        ):
            res = asyncio.run(app.whoop_callback(code="auth_code_123", state="state_xyz", error=None))
            self.assertEqual(res.status_code, 500)
            self.assertNotIn("ConnectionRefusedError", res.content)
            self.assertNotIn("oauth.whoop.com:443", res.content)
            self.assertIn("Authentication error: An unexpected error occurred during authentication.", res.content)

    def test_whoop_api_request_network_exception_sanitized(self):
        sensitive_msg = "HTTPSConnectionPool(host='api.prod.whoop.internal', port=443): Max retries exceeded"
        with patch.object(app.requests, "get", side_effect=Exception(sensitive_msg)):
            result = app.whoop_api_request("user123", "GET", "/recovery")
            self.assertIsInstance(result, dict)
            self.assertIn("error", result)
            self.assertNotIn("api.prod.whoop.internal", result["error"])
            self.assertNotIn("HTTPSConnectionPool", result["error"])
            self.assertEqual(result["error"], "Whoop API request failed")

    def test_tool_handlers_network_failure_sanitized(self):
        sensitive_msg = "HTTPSConnectionPool(host='api.prod.whoop.internal', port=443): Max retries exceeded"
        with patch.object(app.requests, "get", side_effect=Exception(sensitive_msg)):
            req = FakeChatRequest({"uid": "user123"})

            # Recovery
            res_rec = asyncio.run(app.tool_get_recovery(req))
            self.assertIsNotNone(res_rec.error)
            self.assertNotIn("api.prod.whoop.internal", res_rec.error)
            self.assertNotIn("HTTPSConnectionPool", res_rec.error)
            self.assertEqual(res_rec.error, "Failed to get recovery. Please try again.")

            # Strain
            res_str = asyncio.run(app.tool_get_strain(req))
            self.assertIsNotNone(res_str.error)
            self.assertNotIn("api.prod.whoop.internal", res_str.error)
            self.assertNotIn("HTTPSConnectionPool", res_str.error)
            self.assertEqual(res_str.error, "Failed to get strain. Please try again.")

            # Sleep
            res_slp = asyncio.run(app.tool_get_sleep(req))
            self.assertIsNotNone(res_slp.error)
            self.assertNotIn("api.prod.whoop.internal", res_slp.error)
            self.assertNotIn("HTTPSConnectionPool", res_slp.error)
            self.assertEqual(res_slp.error, "Failed to get sleep. Please try again.")

            # Workouts
            res_wkt = asyncio.run(app.tool_get_workouts(req))
            self.assertIsNotNone(res_wkt.error)
            self.assertNotIn("api.prod.whoop.internal", res_wkt.error)
            self.assertNotIn("HTTPSConnectionPool", res_wkt.error)
            self.assertEqual(res_wkt.error, "Failed to get workouts. Please try again.")

            # Measurements
            res_msr = asyncio.run(app.tool_get_body_measurements(req))
            self.assertIsNotNone(res_msr.error)
            self.assertNotIn("api.prod.whoop.internal", res_msr.error)
            self.assertNotIn("HTTPSConnectionPool", res_msr.error)
            self.assertEqual(res_msr.error, "Failed to get measurements. Please try again.")

    def test_tool_handlers_http_error_code_surfaced(self):
        class FakeHTTPResponse:
            def __init__(self, status_code):
                self.status_code = status_code

            def json(self):
                return {}

        with patch.object(app.requests, "get", return_value=FakeHTTPResponse(404)):
            req = FakeChatRequest({"uid": "user123"})
            res = asyncio.run(app.tool_get_body_measurements(req))
            self.assertIsNotNone(res.error)
            self.assertIn("404", res.error)
            self.assertEqual(res.error, "Failed to get measurements: HTTP 404")


if __name__ == "__main__":
    unittest.main()
