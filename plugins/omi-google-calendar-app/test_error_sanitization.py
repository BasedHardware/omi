"""Hermetic tests ensuring error sanitization across google-calendar-app.

Tests verify that internal exceptions and tracebacks are never leaked to users
or API callers.
"""

import asyncio
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

APP_ROOT = Path(__file__).resolve().parent


class _Captured:
    def __init__(self, content=None, status_code=200, url=None, **kwargs):
        self.body = content if content is not None else (url or "")
        self.status_code = status_code
        self.url = url


def _load_main():
    saved = {
        name: sys.modules.get(name)
        for name in ("requests", "dotenv", "fastapi", "fastapi.responses", "db", "models", "main")
    }

    requests_mod = types.ModuleType("requests")
    requests_mod.get = MagicMock()
    requests_mod.post = MagicMock()
    requests_mod.patch = MagicMock()
    requests_mod.delete = MagicMock()
    sys.modules["requests"] = requests_mod

    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *a, **k: None
    sys.modules["dotenv"] = dotenv

    fastapi = types.ModuleType("fastapi")

    class _App:
        def __init__(self, *a, **k):
            pass

        def _decorator(self, *a, **k):
            def wrap(fn):
                return fn
            return wrap

        get = post = put = delete = on_event = middleware = _decorator

    fastapi.FastAPI = _App
    fastapi.Request = object
    fastapi.Query = lambda default=None, **k: default
    fastapi.HTTPException = Exception
    sys.modules["fastapi"] = fastapi

    responses = types.ModuleType("fastapi.responses")
    responses.HTMLResponse = _Captured
    responses.RedirectResponse = _Captured
    responses.JSONResponse = _Captured
    sys.modules["fastapi.responses"] = responses

    db = types.ModuleType("db")
    db.store_google_tokens = MagicMock()
    db.get_google_tokens = MagicMock()
    db.update_google_tokens = MagicMock()
    db.delete_google_tokens = MagicMock()
    db.store_oauth_state = MagicMock()
    db.get_oauth_state = MagicMock()
    db.delete_oauth_state = MagicMock()
    db.store_user_setting = MagicMock()
    db.get_user_setting = MagicMock()
    sys.modules["db"] = db

    models = types.ModuleType("models")

    class ChatToolResponse:
        def __init__(self, result=None, error=None):
            self.result = result
            self.error = error

    models.ChatToolResponse = ChatToolResponse
    sys.modules["models"] = models

    main_path = APP_ROOT / "main.py"
    with open(main_path, "r", encoding="utf-8") as f:
        code = compile(f.read(), str(main_path), "exec")

    mod = types.ModuleType("main")
    mod.__file__ = str(main_path)
    sys.modules["main"] = mod
    exec(code, mod.__dict__)

    return mod, saved


class TestGoogleCalendarErrorSanitization(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main_mod, cls.saved_modules = _load_main()

    @classmethod
    def tearDownClass(cls):
        for name, mod in cls.saved_modules.items():
            if mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = mod

    def test_calendar_api_request_sanitizes_exception(self):
        with patch.object(self.main_mod, "get_valid_access_token", return_value="test_token"), \
             patch.object(self.main_mod.requests, "get", side_effect=Exception("Sensitive DB connection failed: host=10.0.0.5")):
            result = self.main_mod.calendar_api_request("test_uid", "GET", "/test")
            self.assertEqual(result, {"error": "API request failed"})

    def test_tool_list_events_sanitizes_exception(self):
        req = MagicMock()
        req.json = MagicMock(side_effect=Exception("Internal parse failure"))
        result = asyncio.run(self.main_mod.tool_list_events(req))
        self.assertEqual(result.error, "Failed to list events")
        self.assertNotIn("Internal parse failure", result.error)

    def test_tool_create_event_sanitizes_exception(self):
        req = MagicMock()
        req.json = MagicMock(side_effect=Exception("Internal create failure"))
        result = asyncio.run(self.main_mod.tool_create_event(req))
        self.assertEqual(result.error, "Failed to create event")
        self.assertNotIn("Internal create failure", result.error)

    def test_tool_get_event_sanitizes_exception(self):
        req = MagicMock()
        req.json = MagicMock(side_effect=Exception("Internal get failure"))
        result = asyncio.run(self.main_mod.tool_get_event(req))
        self.assertEqual(result.error, "Failed to get event")
        self.assertNotIn("Internal get failure", result.error)

    def test_tool_update_event_sanitizes_exception(self):
        req = MagicMock()
        req.json = MagicMock(side_effect=Exception("Internal update failure"))
        result = asyncio.run(self.main_mod.tool_update_event(req))
        self.assertEqual(result.error, "Failed to update event")
        self.assertNotIn("Internal update failure", result.error)

    def test_tool_delete_event_sanitizes_exception(self):
        req = MagicMock()
        req.json = MagicMock(side_effect=Exception("Internal delete failure"))
        result = asyncio.run(self.main_mod.tool_delete_event(req))
        self.assertEqual(result.error, "Failed to delete event")
        self.assertNotIn("Internal delete failure", result.error)

    def test_tool_list_calendars_sanitizes_exception(self):
        req = MagicMock()
        req.json = MagicMock(side_effect=Exception("Internal list failure"))
        result = asyncio.run(self.main_mod.tool_list_calendars(req))
        self.assertEqual(result.error, "Failed to list calendars")
        self.assertNotIn("Internal list failure", result.error)

    def test_oauth_callback_sanitizes_exception(self):
        with patch.object(self.main_mod, "get_oauth_state", return_value="auth_code:test_uid"), \
             patch.object(self.main_mod.requests, "post", side_effect=Exception("SQL leak password=xyz")):
            resp = asyncio.run(self.main_mod.google_callback(code="auth_code", state="auth_code:test_uid"))
            self.assertEqual(resp.status_code, 500)
            self.assertIn("Authentication error: Failed to complete authentication", resp.body)
            self.assertNotIn("SQL leak", resp.body)


if __name__ == "__main__":
    unittest.main()
