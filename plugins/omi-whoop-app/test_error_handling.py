"""Hermetic unit test suite for Whoop app error handling.

Verifies that internal exceptions, system paths, network addresses, and raw
tracebacks never leak into chat tool responses or OAuth callback HTML responses.
Standard library only (unittest, isolated asyncio).
"""

import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import patch, MagicMock


def load_whoop_module():
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
        def __init__(self, content="", status_code=200, **kwargs):
            self.content = content
            self.status_code = status_code
            self.kwargs = kwargs

    class ChatToolResponse:
        def __init__(self, result=None, error=None):
            self.result = result
            self.error = error

    requests = ModuleType("requests")
    requests.get = lambda *args, **kwargs: None
    requests.post = lambda *args, **kwargs: None
    requests.request = lambda *args, **kwargs: None

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

    stubs = {
        "requests": requests,
        "dotenv": dotenv,
        "fastapi": fastapi,
        "fastapi.responses": responses,
        "db": db,
        "models": models,
    }
    for k, v in stubs.items():
        sys.modules.setdefault(k, v)

    spec = importlib.util.spec_from_file_location(
        "whoop_app", Path(__file__).with_name("main.py")
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module


app = load_whoop_module()


class FakeChatRequest:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


class WhoopErrorHandlingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.sensitive_leak = "FATAL: /var/secrets/whoop_privkey.pem: leaked credentials at 10.0.0.1:8080"

    def test_whoop_api_request_sanitizes_raw_exception(self):
        """whoop_api_request must not return raw exception string."""
        with patch.object(app, "get_valid_access_token", return_value="fake-token"):
            with patch.object(app.requests, "request", side_effect=RuntimeError(self.sensitive_leak)):
                result = app.whoop_api_request("user123", "GET", "/activity/recovery")
                self.assertIsNotNone(result)
                self.assertIn("error", result)
                self.assertEqual(result["error"], "Whoop API request failed")
                self.assertNotIn(self.sensitive_leak, str(result))
                self.assertNotIn("/var/secrets", str(result))

    async def test_tool_get_recovery_sanitizes_exception(self):
        req = FakeChatRequest({"uid": "user123"})
        with patch.object(app, "get_valid_access_token", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.tool_get_recovery(req)
            self.assertEqual(resp.error, "Failed to get recovery due to an internal error.")
            self.assertNotIn(self.sensitive_leak, resp.error)
            self.assertNotIn("whoop_privkey", resp.error)

    async def test_tool_get_strain_sanitizes_exception(self):
        req = FakeChatRequest({"uid": "user123"})
        with patch.object(app, "get_valid_access_token", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.tool_get_strain(req)
            self.assertEqual(resp.error, "Failed to get strain due to an internal error.")
            self.assertNotIn(self.sensitive_leak, resp.error)
            self.assertNotIn("whoop_privkey", resp.error)

    async def test_tool_get_sleep_sanitizes_exception(self):
        req = FakeChatRequest({"uid": "user123"})
        with patch.object(app, "get_valid_access_token", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.tool_get_sleep(req)
            self.assertEqual(resp.error, "Failed to get sleep due to an internal error.")
            self.assertNotIn(self.sensitive_leak, resp.error)
            self.assertNotIn("whoop_privkey", resp.error)

    async def test_tool_get_workouts_sanitizes_exception(self):
        req = FakeChatRequest({"uid": "user123"})
        with patch.object(app, "get_valid_access_token", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.tool_get_workouts(req)
            self.assertEqual(resp.error, "Failed to get workouts due to an internal error.")
            self.assertNotIn(self.sensitive_leak, resp.error)
            self.assertNotIn("whoop_privkey", resp.error)

    async def test_tool_get_weekly_summary_sanitizes_exception(self):
        req = FakeChatRequest({"uid": "user123"})
        with patch.object(app, "get_valid_access_token", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.tool_get_weekly_summary(req)
            self.assertEqual(resp.error, "Failed to get weekly summary due to an internal error.")
            self.assertNotIn(self.sensitive_leak, resp.error)
            self.assertNotIn("whoop_privkey", resp.error)

    async def test_tool_get_body_measurements_sanitizes_exception(self):
        req = FakeChatRequest({"uid": "user123"})
        with patch.object(app, "get_valid_access_token", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.tool_get_body_measurements(req)
            self.assertEqual(resp.error, "Failed to get measurements due to an internal error.")
            self.assertNotIn(self.sensitive_leak, resp.error)
            self.assertNotIn("whoop_privkey", resp.error)

    async def test_tool_get_profile_sanitizes_exception(self):
        req = FakeChatRequest({"uid": "user123"})
        with patch.object(app, "get_valid_access_token", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.tool_get_profile(req)
            self.assertEqual(resp.error, "Failed to get profile due to an internal error.")
            self.assertNotIn(self.sensitive_leak, resp.error)
            self.assertNotIn("whoop_privkey", resp.error)

    async def test_whoop_callback_sanitizes_oauth_exception(self):
        with patch.object(app, "get_uid_from_oauth_state", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.whoop_callback(code="auth-code", state="state123")
            self.assertEqual(resp.status_code, 500)
            self.assertIn("Authentication Error", resp.content)
            self.assertNotIn(self.sensitive_leak, resp.content)
            self.assertNotIn("whoop_privkey", resp.content)
            self.assertNotIn("10.0.0.1", resp.content)

    async def test_whoop_auth_sanitizes_oauth_exception(self):
        with patch.object(app, "WHOOP_CLIENT_ID", "fake-id"):
            with patch.object(app, "WHOOP_CLIENT_SECRET", "fake-secret"):
                with patch.object(app, "store_oauth_state", side_effect=RuntimeError(self.sensitive_leak)):
                    with self.assertRaises(app.HTTPException) as ctx:
                        await app.whoop_auth(uid="user123")
                    self.assertEqual(ctx.exception.status_code, 500)
                    self.assertEqual(ctx.exception.detail, "OAuth initialization failed")
                    self.assertNotIn(self.sensitive_leak, ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
