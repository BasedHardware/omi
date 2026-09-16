"""
Hermetic test suite for the Google Calendar integration app.

Exercises manifest schemas, parameter validation, datetime parsing,
event formatting, and tool endpoints without external services.
Runs cleanly under standard library Python (including under python3 -S).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch


def load_app():
    class FastAPI:
        def __init__(self, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda handler: handler

        post = get

    class BaseModel:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class HTTPException(Exception):
        def __init__(self, status_code=400, detail=""):
            self.status_code = status_code
            self.detail = detail

    class Request:
        def __init__(self, json_data=None):
            self._json = json_data or {}

        async def json(self):
            return self._json

    fastapi = ModuleType("fastapi")
    fastapi.FastAPI = FastAPI
    fastapi.Request = Request
    fastapi.HTTPException = HTTPException
    fastapi.Query = lambda default=None, **kwargs: default

    responses = ModuleType("fastapi.responses")
    responses.HTMLResponse = str
    responses.RedirectResponse = str
    responses.JSONResponse = dict

    pydantic = ModuleType("pydantic")
    pydantic.BaseModel = BaseModel

    requests = ModuleType("requests")
    requests.get = Mock()
    requests.post = Mock()
    requests.patch = Mock()
    requests.delete = Mock()

    dotenv = ModuleType("dotenv")
    dotenv.load_dotenv = lambda *args, **kwargs: None

    db = ModuleType("db")
    db.store_google_tokens = Mock()
    db.get_google_tokens = Mock(return_value=None)
    db.update_google_tokens = Mock()
    db.delete_google_tokens = Mock()
    db.store_oauth_state = Mock()
    db.get_oauth_state = Mock()
    db.delete_oauth_state = Mock()
    db.store_user_setting = Mock()
    db.get_user_setting = Mock(return_value=None)

    models = ModuleType("models")

    class ChatToolResponse(BaseModel):
        def __init__(self, result=None, error=None):
            self.result = result
            self.error = error

    models.ChatToolResponse = ChatToolResponse
    models.CalendarEvent = BaseModel
    models.Calendar = BaseModel
    models.GoogleUserInfo = BaseModel

    stubs = {
        "fastapi": fastapi,
        "fastapi.responses": responses,
        "pydantic": pydantic,
        "requests": requests,
        "dotenv": dotenv,
        "db": db,
        "models": models,
    }

    app_path = Path(__file__).resolve().parent / "main.py"
    spec = importlib.util.spec_from_file_location("google_calendar_main", app_path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module, stubs


app_module, stubs = load_app()


class GoogleCalendarAppTests(unittest.TestCase):
    def test_manifest_schema_compliance(self):
        coro = app_module.get_omi_tools_manifest()
        manifest = asyncio.run(coro)
        self.assertIn("tools", manifest)
        self.assertGreaterEqual(len(manifest["tools"]), 5)

        for tool in manifest["tools"]:
            self.assertIn("name", tool)
            self.assertIn("description", tool)
            self.assertIn("parameters", tool)
            params = tool["parameters"]
            self.assertEqual(
                params.get("type"),
                "object",
                f"Tool {tool['name']} parameters missing 'type': 'object'",
            )
            self.assertIn("properties", params)
            self.assertIn("required", params)

    def test_parse_datetime_natural_language(self):
        dt, is_all_day = app_module.parse_datetime("today")
        self.assertFalse(is_all_day)
        self.assertIsInstance(dt, datetime)

        dt_tomorrow, is_all_day_tomorrow = app_module.parse_datetime("tomorrow")
        self.assertTrue(is_all_day_tomorrow)
        self.assertIsInstance(dt_tomorrow, datetime)

        dt_time, is_all_day_time = app_module.parse_datetime("14:30")
        self.assertFalse(is_all_day_time)
        self.assertEqual(dt_time.hour, 14)
        self.assertEqual(dt_time.minute, 30)

    def test_parse_datetime_iso(self):
        dt, is_all_day = app_module.parse_datetime("2026-05-15T10:00:00")
        self.assertFalse(is_all_day)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 5)
        self.assertEqual(dt.day, 15)
        self.assertEqual(dt.hour, 10)

    def test_parse_datetime_invalid(self):
        with self.assertRaises(ValueError):
            app_module.parse_datetime("invalid_date_format_xyz")

    def test_list_events_requires_uid(self):
        req = stubs["fastapi"].Request({"days": 5})
        resp = asyncio.run(app_module.tool_list_events(req))
        self.assertIn("User ID is required", resp.error)

    def test_list_events_requires_auth(self):
        req = stubs["fastapi"].Request({"uid": "user123"})
        stubs["db"].get_google_tokens.return_value = None
        resp = asyncio.run(app_module.tool_list_events(req))
        self.assertIn("connect your Google Calendar first", resp.error)

    def test_list_events_success_empty(self):
        req = stubs["fastapi"].Request({"uid": "user123", "days": 7})
        with patch.object(app_module, "get_valid_access_token", return_value="token123"):
            with patch.object(app_module, "calendar_api_request", return_value={"items": []}):
                resp = asyncio.run(app_module.tool_list_events(req))
                self.assertIn("No events in the next 7 days", resp.result)

    def test_list_events_success_with_items(self):
        req = stubs["fastapi"].Request({"uid": "user123", "days": 7})
        items = [
            {
                "id": "event_12345",
                "summary": "Team Sync",
                "start": {"dateTime": "2026-05-15T10:00:00Z"},
                "end": {"dateTime": "2026-05-15T11:00:00Z"},
                "location": "Google Meet",
            }
        ]
        with patch.object(app_module, "get_valid_access_token", return_value="token123"):
            with patch.object(app_module, "calendar_api_request", return_value={"items": items}):
                resp = asyncio.run(app_module.tool_list_events(req))
                self.assertIn("Team Sync", resp.result)
                self.assertIn("Google Meet", resp.result)

    def test_create_event_validation(self):
        req = stubs["fastapi"].Request({"uid": "user123"})
        resp = asyncio.run(app_module.tool_create_event(req))
        self.assertIn("title is required", resp.error)

        req2 = stubs["fastapi"].Request({"uid": "user123", "title": "Coffee"})
        resp2 = asyncio.run(app_module.tool_create_event(req2))
        self.assertIn("start time is required", resp2.error)

    def test_create_event_success(self):
        req = stubs["fastapi"].Request({
            "uid": "user123",
            "title": "Meeting with Client",
            "start": "2026-05-15T14:00:00",
            "end": "2026-05-15T15:00:00",
            "location": "Office 402",
        })
        with patch.object(app_module, "get_valid_access_token", return_value="token123"):
            with patch.object(app_module, "calendar_api_request", return_value={
                "id": "new_event_id",
                "htmlLink": "https://calendar.google.com/event?id=new_event_id",
                "start": {"dateTime": "2026-05-15T14:00:00Z"},
                "end": {"dateTime": "2026-05-15T15:00:00Z"},
            }):
                resp = asyncio.run(app_module.tool_create_event(req))
                self.assertIn("Event Created!", resp.result)
                self.assertIn("Meeting with Client", resp.result)
                self.assertIn("Office 402", resp.result)

    def test_get_event_missing_id(self):
        req = stubs["fastapi"].Request({"uid": "user123"})
        resp = asyncio.run(app_module.tool_get_event(req))
        self.assertIn("Event ID is required", resp.error)

    def test_delete_event_success(self):
        req = stubs["fastapi"].Request({"uid": "user123", "event_id": "ev_456"})
        with patch.object(app_module, "get_valid_access_token", return_value="token123"):
            with patch.object(app_module, "calendar_api_request", side_effect=[
                {"summary": "Old Standup"},  # GET
                {"success": True},           # DELETE
            ]):
                resp = asyncio.run(app_module.tool_delete_event(req))
                self.assertIn("Event Deleted", resp.result)
                self.assertIn("Old Standup", resp.result)


if __name__ == "__main__":
    unittest.main()
