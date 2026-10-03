"""Hermetic unit test suite for Google Calendar app error handling.

Verifies that internal exceptions, system paths, network addresses, and raw
tracebacks never leak into chat tool responses or OAuth callback HTML responses.
Standard library only (unittest, isolated asyncio).
"""

import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch


class Framework:
    def __init__(self, content="", status_code=200, **kwargs):
        self.content = content
        self.status_code = status_code
        self.kwargs = kwargs

    def get(self, *args, **kwargs):
        return lambda function: function

    post = get


class HTTPExceptionStub(Exception):
    def __init__(self, status_code=None, detail=None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class ChatToolResponseStub:
    def __init__(self, result=None, error=None, **kwargs):
        self.result = result
        self.error = error


def make_module(name, **attributes):
    value = types.ModuleType(name)
    value.__dict__.update(attributes)
    return value


def load_calendar_module():
    stubs = {
        "requests": make_module(
            "requests",
            get=lambda *args, **kwargs: None,
            post=lambda *args, **kwargs: None,
            request=lambda *args, **kwargs: None,
            RequestException=OSError,
        ),
        "dotenv": make_module("dotenv", load_dotenv=lambda *args, **kwargs: None),
        "fastapi": make_module(
            "fastapi",
            FastAPI=Framework,
            Request=Framework,
            Query=lambda *args, **kwargs: None,
            HTTPException=HTTPExceptionStub,
        ),
        "fastapi.responses": make_module(
            "fastapi.responses",
            HTMLResponse=Framework,
            RedirectResponse=Framework,
            JSONResponse=Framework,
        ),
        "db": make_module(
            "db",
            **{name: Mock() for name in (
                "store_google_tokens", "get_google_tokens", "update_google_tokens",
                "delete_google_tokens", "store_oauth_state", "get_oauth_state",
                "delete_oauth_state", "store_user_setting", "get_user_setting"
            )}
        ),
        "models": make_module("models", ChatToolResponse=ChatToolResponseStub),
    }

    for k, v in stubs.items():
        sys.modules.setdefault(k, v)

    spec = importlib.util.spec_from_file_location(
        "google_calendar_app", Path(__file__).with_name("main.py")
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module


app = load_calendar_module()


class FakeChatRequest:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


class GoogleCalendarErrorHandlingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.sensitive_leak = "FATAL: /var/secrets/gcal_key.json: database connection failed at 192.168.1.100:5432"

    def test_calendar_api_request_sanitizes_raw_exception(self):
        """calendar_api_request must not return raw exception string."""
        with patch.object(app, "get_valid_access_token", return_value="fake-token"):
            with patch.object(app.requests, "request", side_effect=RuntimeError(self.sensitive_leak)):
                result = app.calendar_api_request("user123", "GET", "/users/me/calendarList")
                self.assertIsNotNone(result)
                self.assertIn("error", result)
                self.assertEqual(result["error"], "Google Calendar API request failed")
                self.assertNotIn(self.sensitive_leak, str(result))
                self.assertNotIn("192.168.1.100", str(result))

    async def test_tool_list_events_sanitizes_exception(self):
        req = FakeChatRequest({"uid": "user123"})
        with patch.object(app, "get_valid_access_token", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.tool_list_events(req)
            self.assertEqual(resp.error, "Failed to list events due to an internal error.")
            self.assertNotIn(self.sensitive_leak, resp.error)
            self.assertNotIn("gcal_key", resp.error)

    async def test_tool_create_event_sanitizes_exception(self):
        req = FakeChatRequest({"uid": "user123", "title": "Meeting", "start": "2026-09-25T10:00:00Z"})
        with patch.object(app, "get_valid_access_token", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.tool_create_event(req)
            self.assertEqual(resp.error, "Failed to create event due to an internal error.")
            self.assertNotIn(self.sensitive_leak, resp.error)
            self.assertNotIn("gcal_key", resp.error)

    async def test_tool_get_event_sanitizes_exception(self):
        req = FakeChatRequest({"uid": "user123", "event_id": "event_abc123"})
        with patch.object(app, "get_valid_access_token", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.tool_get_event(req)
            self.assertEqual(resp.error, "Failed to get event due to an internal error.")
            self.assertNotIn(self.sensitive_leak, resp.error)
            self.assertNotIn("gcal_key", resp.error)

    async def test_tool_update_event_sanitizes_exception(self):
        req = FakeChatRequest({"uid": "user123", "event_id": "event_abc123", "title": "New Title"})
        with patch.object(app, "get_valid_access_token", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.tool_update_event(req)
            self.assertEqual(resp.error, "Failed to update event due to an internal error.")
            self.assertNotIn(self.sensitive_leak, resp.error)
            self.assertNotIn("gcal_key", resp.error)

    async def test_tool_delete_event_sanitizes_exception(self):
        req = FakeChatRequest({"uid": "user123", "event_id": "event_abc123"})
        with patch.object(app, "get_valid_access_token", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.tool_delete_event(req)
            self.assertEqual(resp.error, "Failed to delete event due to an internal error.")
            self.assertNotIn(self.sensitive_leak, resp.error)
            self.assertNotIn("gcal_key", resp.error)

    async def test_tool_list_calendars_sanitizes_exception(self):
        req = FakeChatRequest({"uid": "user123"})
        with patch.object(app, "get_valid_access_token", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.tool_list_calendars(req)
            self.assertEqual(resp.error, "Failed to list calendars due to an internal error.")
            self.assertNotIn(self.sensitive_leak, resp.error)
            self.assertNotIn("gcal_key", resp.error)

    async def test_google_auth_sanitizes_exception(self):
        with patch.object(app, "GOOGLE_CLIENT_ID", "fake-client-id"):
            with patch.object(app, "GOOGLE_CLIENT_SECRET", "fake-client-secret"):
                with patch.object(app, "store_oauth_state", side_effect=RuntimeError(self.sensitive_leak)):
                    with self.assertRaises(app.HTTPException) as ctx:
                        await app.google_auth(uid="user123")
                    self.assertEqual(ctx.exception.status_code, 500)
                    self.assertEqual(ctx.exception.detail, "OAuth initialization failed")
                    self.assertNotIn(self.sensitive_leak, ctx.exception.detail)

    async def test_google_callback_sanitizes_exception(self):
        with patch.object(app, "get_oauth_state", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.google_callback(code="auth-code", state="user123:random_token")
            self.assertEqual(resp.status_code, 500)
            self.assertIn("Authentication Error", resp.content)
            self.assertNotIn(self.sensitive_leak, resp.content)
            self.assertNotIn("192.168.1.100", resp.content)

    async def test_tool_create_event_masks_invalid_datetime_format(self):
        with patch.object(app, "get_valid_access_token", return_value="fake-token"):
            req_start = FakeChatRequest({"uid": "user123", "title": "Meeting", "start": "not-a-valid-date"})
            resp_start = await app.tool_create_event(req_start)
            self.assertEqual(resp_start.error, "Invalid start time. Could not parse datetime.")

            req_end = FakeChatRequest({"uid": "user123", "title": "Meeting", "start": "2026-09-25T10:00:00Z", "end": "bad-end-date"})
            resp_end = await app.tool_create_event(req_end)
            self.assertEqual(resp_end.error, "Invalid end time. Could not parse datetime.")

    async def test_tool_update_event_masks_invalid_datetime_format(self):
        with patch.object(app, "get_valid_access_token", return_value="fake-token"):
            with patch.object(app, "get_default_calendar", return_value="primary"):
                with patch.object(app, "calendar_api_request", return_value={"id": "evt1", "summary": "Meeting"}):
                    req_start = FakeChatRequest({"uid": "user123", "event_id": "evt1", "start": "bad-start-date"})
                    resp_start = await app.tool_update_event(req_start)
                    self.assertEqual(resp_start.error, "Invalid start time. Could not parse datetime.")

                    req_end = FakeChatRequest({"uid": "user123", "event_id": "evt1", "end": "bad-end-date"})
                    resp_end = await app.tool_update_event(req_end)
                    self.assertEqual(resp_end.error, "Invalid end time. Could not parse datetime.")


if __name__ == "__main__":
    unittest.main()
