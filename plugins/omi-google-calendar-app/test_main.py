"""Hermetic regression for BasedHardware/omi#13937.

The Omi backend builds optional manifest params as Optional[int] = None and
forwards them verbatim, so the plugin receives JSON null for arguments the
LLM omitted. dict.get(key, default) only applies its default when the key is
absent, so tool_list_events crashed on min(None, 30) with
"'<' not supported between instances of 'int' and 'NoneType'", and sibling
handlers trusted whatever type arrived for optional fields.

Stubs requests/dotenv/fastapi/db/models in sys.modules before loading
main.py; no FastAPI routing, network, or Google calls are made. The
production handlers are executed through the calendar_api_request seam.
"""
import asyncio
import importlib.util
from datetime import datetime
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


EVENT = {
    "id": "evt1234567890abcdefghij",
    "summary": "Team Sync",
    "start": {"dateTime": "2026-01-25T14:00:00Z"},
    "end": {"dateTime": "2026-01-25T15:00:00Z"},
}

CREATED_EVENT = {
    "id": "evt1",
    "htmlLink": "https://calendar.google.com/event?eid=evt1",
    "start": {"dateTime": "2026-01-25T14:00:00"},
    "end": {"dateTime": "2026-01-25T15:00:00"},
}


def request_with(body):
    request = Mock()
    request.json = AsyncMock(return_value=body)
    return request


def call_params(api_mock):
    """Extract the params dict the handler passed to calendar_api_request."""
    call = api_mock.call_args
    if call is None:
        return {}
    return call.kwargs.get("params") or call[1].get("params") or {}


def call_json(api_mock):
    call = api_mock.call_args
    if call is None:
        return {}
    return call.kwargs.get("json_data") or call[1].get("json_data") or {}


def window_days(params):
    start = datetime.fromisoformat(params["timeMin"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(params["timeMax"].replace("Z", "+00:00"))
    return (end - start).days


class ListEventsInputTests(unittest.TestCase):
    def invoke(self, body, api_return=None):
        api_return = {"items": [EVENT]} if api_return is None else api_return
        with patch.object(gcal, "get_valid_access_token", return_value="tok"), \
             patch.object(gcal, "get_default_calendar", return_value="primary"), \
             patch.object(gcal, "calendar_api_request", return_value=api_return) as api, \
             patch.object(gcal, "log"):
            result = asyncio.run(gcal.tool_list_events(request_with(body)))
        return result, api

    def assert_window(self, api, days, max_results):
        params = call_params(api)
        self.assertTrue(
            api.call_args[0][2].endswith("/calendars/primary/events"),
            f"unexpected endpoint {api.call_args[0][2]}",
        )
        self.assertEqual(window_days(params), days)
        self.assertEqual(params["maxResults"], max_results)

    def test_json_null_optionals_fall_back_to_defaults(self):
        # The exact payload the backend sends when the LLM omits both params.
        result, api = self.invoke(
            {"uid": "u", "days": None, "max_results": None}
        )
        self.assertIsNone(result.error)
        self.assert_window(api, 7, 10)
        self.assertIn("Team Sync", result.result)

    def test_absent_optionals_fall_back_to_defaults(self):
        result, api = self.invoke({"uid": "u"})
        self.assertIsNone(result.error)
        self.assert_window(api, 7, 10)

    def test_valid_values_pass_through(self):
        result, api = self.invoke({"uid": "u", "days": 3, "max_results": 5})
        self.assertIsNone(result.error)
        self.assert_window(api, 3, 5)

    def test_numeric_strings_are_coerced(self):
        result, api = self.invoke({"uid": "u", "days": "4", "max_results": "12"})
        self.assertIsNone(result.error)
        self.assert_window(api, 4, 12)

    def test_over_cap_values_are_capped(self):
        result, api = self.invoke({"uid": "u", "days": 999, "max_results": 500})
        self.assertIsNone(result.error)
        self.assert_window(api, 30, 50)

    def test_non_positive_values_clamp_to_one(self):
        for body in (
            {"uid": "u", "days": 0, "max_results": 0},
            {"uid": "u", "days": -2, "max_results": -5},
            {"uid": "u", "days": "-3", "max_results": "-1"},
        ):
            with self.subTest(body=body):
                result, api = self.invoke(body)
                self.assertIsNone(result.error)
                self.assert_window(api, 1, 1)

    def test_wrong_types_fall_back_to_defaults(self):
        for days, max_results in (
            ("next week", "many"),      # unparseable strings
            (True, False),              # bools are ints in Python; reject
            (3.5, 2.5),                 # floats are not manifest ints
            (["3"], {"n": 5}),          # containers
            ("3.5", "ten"),             # non-integer numeric string
        ):
            body = {"uid": "u", "days": days, "max_results": max_results}
            with self.subTest(body=body):
                result, api = self.invoke(body)
                self.assertIsNone(result.error)
                self.assert_window(api, 7, 10)

    def test_no_events_message_uses_coerced_days(self):
        result, _api = self.invoke(
            {"uid": "u", "days": None, "max_results": None},
            api_return={"items": []},
        )
        self.assertIsNone(result.error)
        self.assertEqual(result.result, "No events in the next 7 days.")

    def test_event_list_is_formatted(self):
        result, _api = self.invoke({"uid": "u", "days": 2, "max_results": 1})
        self.assertIsNone(result.error)
        self.assertIn("**Upcoming Events (1)**", result.result)
        self.assertIn("Team Sync", result.result)


class CreateEventInputTests(unittest.TestCase):
    BASE_BODY = {"uid": "u", "title": "Meet", "start": "2026-01-25T14:00:00"}

    def invoke(self, body, api_return=None):
        api_return = CREATED_EVENT if api_return is None else api_return
        with patch.object(gcal, "get_valid_access_token", return_value="tok"), \
             patch.object(gcal, "get_default_calendar", return_value="primary"), \
             patch.object(gcal, "calendar_api_request", return_value=api_return) as api, \
             patch.object(gcal, "log"):
            result = asyncio.run(gcal.tool_create_event(request_with(body)))
        return result, api

    def test_null_optionals_behave_like_absent(self):
        body = dict(self.BASE_BODY, description=None, location=None,
                    attendees=None, all_day=None, end=None, calendar_id=None)
        result, api = self.invoke(body)
        self.assertIsNone(result.error)
        sent = call_json(api)
        self.assertNotIn("attendees", sent)
        self.assertNotIn("description", sent)
        self.assertNotIn("location", sent)
        # all_day None must not become an all-day event.
        self.assertIn("dateTime", sent["start"])

    def test_attendees_string_is_wrapped_not_iterated(self):
        result, api = self.invoke(dict(self.BASE_BODY, attendees="a@b.com"))
        self.assertIsNone(result.error)
        self.assertEqual(call_json(api)["attendees"], [{"email": "a@b.com"}])
        self.assertIn("a@b.com", result.result)

    def test_attendees_wrong_types_are_dropped(self):
        for attendees, expected in (
            (123, []),                                   # non-list, non-str
            ({"email": "a@b.com"}, []),                  # dict
            (["a@b.com", 5, None, {"x": 1}, " b@c.com "],
             [{"email": "a@b.com"}, {"email": "b@c.com"}]),
            ([], []),
        ):
            body = dict(self.BASE_BODY, attendees=attendees)
            with self.subTest(attendees=attendees):
                result, api = self.invoke(body)
                self.assertIsNone(result.error)
                sent = call_json(api)
                if expected:
                    self.assertEqual(sent["attendees"], expected)
                else:
                    self.assertNotIn("attendees", sent)

    def test_all_day_string_does_not_create_all_day_event(self):
        # "false" is truthy; only a real JSON boolean enables all-day.
        result, api = self.invoke(dict(self.BASE_BODY, all_day="false"))
        self.assertIsNone(result.error)
        self.assertIn("dateTime", call_json(api)["start"])

    def test_all_day_true_creates_all_day_event(self):
        result, api = self.invoke(dict(self.BASE_BODY, all_day=True))
        self.assertIsNone(result.error)
        self.assertIn("date", call_json(api)["start"])
        self.assertNotIn("dateTime", call_json(api)["start"])

    def test_non_string_optional_end_returns_clean_error(self):
        result, _api = self.invoke(dict(self.BASE_BODY, end=5))
        self.assertIsNotNone(result.error)
        self.assertIn("Invalid end time", result.error)
        self.assertIn("Could not parse datetime", result.error)

    def test_null_end_defaults_to_one_hour(self):
        result, api = self.invoke(dict(self.BASE_BODY, end=None))
        self.assertIsNone(result.error)
        sent = call_json(api)
        start = datetime.fromisoformat(sent["start"]["dateTime"])
        end = datetime.fromisoformat(sent["end"]["dateTime"])
        self.assertEqual((end - start).total_seconds(), 3600)


class UpdateEventInputTests(unittest.TestCase):
    def test_non_string_optional_end_returns_clean_error(self):
        body = {"uid": "u", "event_id": "evt1", "end": 5}
        with patch.object(gcal, "get_valid_access_token", return_value="tok"), \
             patch.object(gcal, "get_default_calendar", return_value="primary"), \
             patch.object(
                 gcal, "calendar_api_request",
                 return_value={"id": "evt1", "summary": "Meet"}), \
             patch.object(gcal, "log"):
            result = asyncio.run(gcal.tool_update_event(request_with(body)))
        self.assertIsNotNone(result.error)
        self.assertIn("Invalid end time", result.error)


if __name__ == "__main__":
    unittest.main(verbosity=2)
