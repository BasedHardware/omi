"""Hermetic regression tests verifying error sanitization in plugins/omi-whoop-app.
Ensures internal exception details, network errors, and sensitive tokens are not leaked to users.
"""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import AsyncMock, Mock, patch


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
        def __init__(self, content=None, status_code=200, **kwargs):
            self.content = content
            self.status_code = status_code

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
        "whoop_app_err_test", Path(__file__).with_name("main.py")
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


class FakeChatRequest:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


class WhoopErrorSanitizationTests(unittest.IsolatedAsyncioTestCase):
    """Verify that network exceptions and unexpected tool errors return sanitized messages."""

    def test_whoop_api_request_exception_sanitized(self):
        with patch.object(app, "get_valid_access_token", return_value="secret-tok"):
            with patch.object(app.requests, "get", side_effect=RuntimeError("connection refused: 192.168.1.1:443")):
                res = app.whoop_api_request("user1", "GET", "/recovery")
                self.assertEqual(res, {"error": "API request failed"})
                self.assertNotIn("192.168.1.1", str(res))

    async def test_tool_get_recovery_exception_sanitized(self):
        req = Mock()
        req.json = AsyncMock(side_effect=RuntimeError("internal crash in recovery JSON"))
        res = await app.tool_get_recovery(req)
        self.assertIsNone(res.result)
        self.assertEqual(res.error, "Failed to get recovery")
        self.assertNotIn("internal crash", res.error)

    async def test_tool_get_strain_exception_sanitized(self):
        req = Mock()
        req.json = AsyncMock(side_effect=RuntimeError("internal crash in strain JSON"))
        res = await app.tool_get_strain(req)
        self.assertIsNone(res.result)
        self.assertEqual(res.error, "Failed to get strain")
        self.assertNotIn("internal crash", res.error)

    async def test_tool_get_sleep_exception_sanitized(self):
        req = Mock()
        req.json = AsyncMock(side_effect=RuntimeError("internal crash in sleep JSON"))
        res = await app.tool_get_sleep(req)
        self.assertIsNone(res.result)
        self.assertEqual(res.error, "Failed to get sleep")
        self.assertNotIn("internal crash", res.error)

    async def test_tool_get_workouts_exception_sanitized(self):
        req = Mock()
        req.json = AsyncMock(side_effect=RuntimeError("internal crash in workouts JSON"))
        res = await app.tool_get_workouts(req)
        self.assertIsNone(res.result)
        self.assertEqual(res.error, "Failed to get workouts")
        self.assertNotIn("internal crash", res.error)

    async def test_tool_get_weekly_summary_exception_sanitized(self):
        req = Mock()
        req.json = AsyncMock(side_effect=RuntimeError("internal crash in weekly summary JSON"))
        res = await app.tool_get_weekly_summary(req)
        self.assertIsNone(res.result)
        self.assertEqual(res.error, "Failed to get weekly summary")
        self.assertNotIn("internal crash", res.error)

    async def test_tool_get_body_measurements_exception_sanitized(self):
        req = Mock()
        req.json = AsyncMock(side_effect=RuntimeError("internal crash in measurements JSON"))
        res = await app.tool_get_body_measurements(req)
        self.assertIsNone(res.result)
        self.assertEqual(res.error, "Failed to get measurements")
        self.assertNotIn("internal crash", res.error)

    async def test_tool_get_profile_exception_sanitized(self):
        req = Mock()
        req.json = AsyncMock(side_effect=RuntimeError("internal crash in profile JSON"))
        res = await app.tool_get_profile(req)
        self.assertIsNone(res.result)
        self.assertEqual(res.error, "Failed to get profile")
        self.assertNotIn("internal crash", res.error)

    async def test_whoop_callback_exception_sanitized(self):
        with patch.object(app, "get_uid_from_oauth_state", return_value="user123"):
            with patch.object(app.requests, "post", side_effect=RuntimeError("db connection failed: postgresql://secret")):
                res = await app.whoop_callback(code="auth_code", state="state123")
                self.assertEqual(res.status_code, 500)
                self.assertEqual(res.content, "Authentication error")
                self.assertNotIn("postgresql", str(res.content))


if __name__ == "__main__":
    unittest.main(verbosity=2)
