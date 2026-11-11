"""Tests for attendee normalization, input safety, and time bounds validation."""
import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch


class Framework:
    def __init__(self, *args, **kwargs):
        pass

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


def module(name, **attributes):
    value = types.ModuleType(name)
    value.__dict__.update(attributes)
    return value


stubs = {
    "requests": module("requests", RequestException=OSError),
    "dotenv": module("dotenv", load_dotenv=lambda *args, **kwargs: None),
    "fastapi": module(
        "fastapi",
        FastAPI=Framework,
        Request=Framework,
        Query=Framework,
        HTTPException=HTTPExceptionStub,
    ),
    "fastapi.responses": module(
        "fastapi.responses",
        **{name: Framework for name in
           ("HTMLResponse", "RedirectResponse", "JSONResponse")}
    ),
    "db": module("db", **{name: Mock() for name in (
        "store_google_tokens", "get_google_tokens", "update_google_tokens",
        "delete_google_tokens", "store_oauth_state", "get_oauth_state",
        "delete_oauth_state", "store_user_setting", "get_user_setting")}),
    "models": module("models", ChatToolResponse=ChatToolResponseStub),
}

spec = importlib.util.spec_from_file_location(
    "gcal_under_test", Path(__file__).with_name("main.py")
)
gcal = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(gcal)


def request_with(body):
    req = Mock()
    req.json = AsyncMock(return_value=body)
    return req


class TestAttendeeNormalization(unittest.TestCase):
    def test_normalize_attendees_string(self):
        res = gcal._normalize_attendees("alice@example.com")
        self.assertEqual(res, ["alice@example.com"])

    def test_normalize_attendees_comma_separated(self):
        res = gcal._normalize_attendees("alice@example.com, bob@example.com, carol@example.com")
        self.assertEqual(res, ["alice@example.com", "bob@example.com", "carol@example.com"])

    def test_normalize_attendees_semicolon_and_whitespace(self):
        res = gcal._normalize_attendees("alice@example.com;bob@example.com ;  carol@example.com")
        self.assertEqual(res, ["alice@example.com", "bob@example.com", "carol@example.com"])

    def test_normalize_attendees_deduplication(self):
        res = gcal._normalize_attendees(["alice@example.com", "bob@example.com, alice@example.com"])
        self.assertEqual(res, ["alice@example.com", "bob@example.com"])

    def test_normalize_attendees_non_string_elements(self):
        res = gcal._normalize_attendees([None, 123, "alice@example.com", {"email": "bad"}])
        self.assertEqual(res, ["alice@example.com"])

    def test_normalize_attendees_invalid_types(self):
        self.assertEqual(gcal._normalize_attendees(None), [])
        self.assertEqual(gcal._normalize_attendees(12345), [])
        self.assertEqual(gcal._normalize_attendees({"email": "alice@example.com"}), [])


class TestFormatEventTimeDefensive(unittest.TestCase):
    def test_format_event_time_non_dict(self):
        self.assertEqual(gcal.format_event_time(None), "")
        self.assertEqual(gcal.format_event_time("not a dict"), "")
        self.assertEqual(gcal.format_event_time([]), "")

    def test_format_event_time_missing_or_invalid_start_end(self):
        self.assertEqual(gcal.format_event_time({}), " - ")
        self.assertEqual(gcal.format_event_time({"start": None, "end": None}), " - ")
        self.assertEqual(gcal.format_event_time({"start": "invalid", "end": 123}), " - ")


class TestChatToolsRobustness(unittest.TestCase):
    def setUp(self):
        self.uid = "test-user-123"

    def test_non_dict_body_across_all_tools(self):
        tools = [
            gcal.tool_list_events,
            gcal.tool_create_event,
            gcal.tool_get_event,
            gcal.tool_update_event,
            gcal.tool_delete_event,
            gcal.tool_list_calendars,
        ]
        for tool in tools:
            for bad_body in (None, "string", [1, 2, 3], 42):
                resp = asyncio.run(tool(request_with(bad_body)))
                self.assertIsNotNone(resp.error)
                self.assertIn("required", resp.error.lower())

    @patch.object(gcal, "calendar_api_request")
    @patch.object(gcal, "get_valid_access_token", return_value="token123")
    def test_create_event_with_comma_separated_attendees(self, mock_auth, mock_api):
        mock_api.return_value = {
            "id": "evt100",
            "summary": "Team Sync",
            "start": {"dateTime": "2026-10-01T10:00:00Z"},
            "end": {"dateTime": "2026-10-01T11:00:00Z"},
        }
        req = request_with({
            "uid": self.uid,
            "title": "Team Sync",
            "start": "2026-10-01T10:00:00Z",
            "end": "2026-10-01T11:00:00Z",
            "attendees": "alice@example.com, bob@example.com; charlie@example.com",
        })
        resp = asyncio.run(gcal.tool_create_event(req))
        self.assertIsNone(resp.error)
        self.assertIn("alice@example.com", resp.result)
        self.assertIn("bob@example.com", resp.result)
        self.assertIn("charlie@example.com", resp.result)

        # Verify payload sent to calendar API
        call_kwargs = mock_api.call_args[1]
        json_data = call_kwargs.get("json_data", {})
        self.assertEqual(
            json_data.get("attendees"),
            [
                {"email": "alice@example.com"},
                {"email": "bob@example.com"},
                {"email": "charlie@example.com"},
            ],
        )

    @patch.object(gcal, "get_valid_access_token", return_value="token123")
    def test_create_event_end_time_before_or_equal_start_time(self, mock_auth):
        # End before start
        req = request_with({
            "uid": self.uid,
            "title": "Bad Meeting",
            "start": "2026-10-01T14:00:00Z",
            "end": "2026-10-01T13:00:00Z",
        })
        resp = asyncio.run(gcal.tool_create_event(req))
        self.assertIsNotNone(resp.error)
        self.assertIn("End time must be after start time", resp.error)

        # End equal to start
        req = request_with({
            "uid": self.uid,
            "title": "Instant Meeting",
            "start": "2026-10-01T14:00:00Z",
            "end": "2026-10-01T14:00:00Z",
        })
        resp = asyncio.run(gcal.tool_create_event(req))
        self.assertIsNotNone(resp.error)
        self.assertIn("End time must be after start time", resp.error)

    @patch.object(gcal, "calendar_api_request")
    @patch.object(gcal, "get_valid_access_token", return_value="token123")
    def test_update_event_end_time_before_or_equal_start_time(self, mock_auth, mock_api):
        mock_api.return_value = {"id": "evt100", "summary": "Existing"}
        req = request_with({
            "uid": self.uid,
            "event_id": "evt100",
            "start": "2026-10-01T15:00:00Z",
            "end": "2026-10-01T14:00:00Z",
        })
        resp = asyncio.run(gcal.tool_update_event(req))
        self.assertIsNotNone(resp.error)
        self.assertIn("End time must be after start time", resp.error)

    @patch.object(gcal, "calendar_api_request")
    @patch.object(gcal, "get_valid_access_token", return_value="token123")
    def test_update_event_with_normalized_attendees(self, mock_auth, mock_api):
        mock_api.side_effect = [
            {"id": "evt100", "summary": "Existing"},  # GET existing
            {"id": "evt100", "summary": "Existing"},  # PATCH update
        ]
        req = request_with({
            "uid": self.uid,
            "event_id": "evt100",
            "attendees": "dev1@example.com, dev2@example.com",
        })
        resp = asyncio.run(gcal.tool_update_event(req))
        self.assertIsNone(resp.error)
        self.assertIn("dev1@example.com", resp.result)

        # Check PATCH payload
        patch_call = mock_api.call_args_list[1]
        json_data = patch_call[1].get("json_data", {})
        self.assertEqual(
            json_data.get("attendees"),
            [{"email": "dev1@example.com"}, {"email": "dev2@example.com"}],
        )

    @patch.object(gcal, "calendar_api_request")
    @patch.object(gcal, "get_valid_access_token", return_value="token123")
    def test_get_event_non_dict_attendees(self, mock_auth, mock_api):
        mock_api.return_value = {
            "id": "evt100",
            "summary": "Team Sync",
            "status": "confirmed",
            "start": {"dateTime": "2026-10-01T10:00:00Z"},
            "end": {"dateTime": "2026-10-01T11:00:00Z"},
            "attendees": [None, "invalid_attendee", {"email": "valid@example.com"}, {"not_email": 123}],
        }
        req = request_with({"uid": self.uid, "event_id": "evt100"})
        resp = asyncio.run(gcal.tool_get_event(req))
        self.assertIsNone(resp.error)
        self.assertIn("valid@example.com", resp.result)

    @patch.object(gcal, "calendar_api_request")
    @patch.object(gcal, "get_valid_access_token", return_value="token123")
    def test_list_events_non_dict_items(self, mock_auth, mock_api):
        mock_api.return_value = {
            "items": [None, 123, {"id": "evt1", "summary": "Valid Event", "start": {}, "end": {}}],
        }
        req = request_with({"uid": self.uid})
        resp = asyncio.run(gcal.tool_list_events(req))
        self.assertIsNone(resp.error)
        self.assertIn("Valid Event", resp.result)


if __name__ == "__main__":
    unittest.main()
