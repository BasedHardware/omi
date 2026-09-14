"""Hermetic regression: event ids emitted by chat tools must be usable as
`event_id` input to get_event, update_event and delete_event.

`list_events` used to print `event_id[:20] + "..."`. Google-generated event
ids are 26 base32hex characters and recurring-instance ids append
`_YYYYMMDDTHHMMSSZ`, so every id the tool handed back was truncated and the
follow-up tools (which send the id verbatim to the Calendar API) could not
find the event. `create_event` printed no id at all.

Import the production module with framework-only stubs, then exercise the
real handlers. No network, credentials, or third-party packages required.

Run: python3 plugins/omi-google-calendar-app/test_event_ids.py
"""

import asyncio
import importlib.util
import re
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

MAIN_PATH = Path(__file__).resolve().parent / "main.py"

# Shapes taken from real Calendar API responses: a single event id (26
# base32hex chars) and a recurring-instance id (base id + "_" + UTC start).
SINGLE_EVENT_ID = "0v8c8q9j2mrq3b6m1u5s0n8p4a"
RECURRING_INSTANCE_ID = "0v8c8q9j2mrq3b6m1u5s0n8p4a_20260914T100000Z"


def load_app():
    class FastAPI:
        def __init__(self, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda handler: handler

        post = get

    class ChatToolResponse:
        def __init__(self, result=None, error=None):
            self.result = result
            self.error = error

    fastapi = ModuleType("fastapi")
    fastapi.FastAPI = FastAPI
    fastapi.Request = object
    fastapi.Query = lambda default=None, **kwargs: default
    fastapi.HTTPException = Exception
    responses = ModuleType("fastapi.responses")
    responses.HTMLResponse = str
    responses.RedirectResponse = str
    responses.JSONResponse = dict
    dotenv = ModuleType("dotenv")
    dotenv.load_dotenv = lambda *args, **kwargs: None
    db = ModuleType("db")
    for name in (
        "store_google_tokens",
        "get_google_tokens",
        "update_google_tokens",
        "delete_google_tokens",
        "store_oauth_state",
        "get_oauth_state",
        "delete_oauth_state",
        "store_user_setting",
        "get_user_setting",
    ):
        setattr(db, name, lambda *args, **kwargs: None)
    models = ModuleType("models")
    models.ChatToolResponse = ChatToolResponse
    requests = ModuleType("requests")

    spec = importlib.util.spec_from_file_location("google_calendar_app", MAIN_PATH)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "fastapi": fastapi,
            "fastapi.responses": responses,
            "dotenv": dotenv,
            "db": db,
            "models": models,
            "requests": requests,
        },
    ):
        spec.loader.exec_module(module)
    return module


app = load_app()


def _request(body):
    class _Request:
        async def json(self):
            return body

    return _Request()


def _run(coro):
    return asyncio.run(coro)


def _event(event_id, summary="Standup"):
    return {
        "id": event_id,
        "summary": summary,
        "start": {"dateTime": "2026-09-14T10:00:00Z"},
        "end": {"dateTime": "2026-09-14T10:30:00Z"},
    }


def _ids_in(text):
    """Every backtick-quoted id the tool printed, in order."""
    return re.findall(r"ID:\*{0,2} `([^`]*)`", text)


class _FakeCalendarApi:
    """Stands in for calendar_api_request and records what it was asked."""

    def __init__(self, events_by_id):
        self.events_by_id = events_by_id
        self.calls = []

    def __call__(self, uid, method, endpoint, params=None, json_data=None):
        self.calls.append((method, endpoint))
        if method == "GET" and endpoint.endswith("/events"):
            return {"items": list(self.events_by_id.values())}
        if method == "POST" and endpoint.endswith("/events"):
            created = dict(json_data, id=SINGLE_EVENT_ID)
            self.events_by_id[SINGLE_EVENT_ID] = created
            return created
        event_id = endpoint.rsplit("/", 1)[-1]
        event = self.events_by_id.get(event_id)
        if event is None:
            return {"error": "Not Found", "status_code": 404}
        if method == "DELETE":
            return {"success": True}
        return event


class ListedEventIdsAreUsable(unittest.TestCase):
    def setUp(self):
        self.api = _FakeCalendarApi(
            {
                SINGLE_EVENT_ID: _event(SINGLE_EVENT_ID, "Standup"),
                RECURRING_INSTANCE_ID: _event(RECURRING_INSTANCE_ID, "Weekly sync"),
            }
        )
        patches = [
            patch.object(app, "calendar_api_request", self.api),
            patch.object(app, "get_valid_access_token", lambda uid: "token"),
            patch.object(app, "get_default_calendar", lambda uid: "primary"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def _list_ids(self):
        response = _run(app.tool_list_events(_request({"uid": "u1"})))
        self.assertIsNone(response.error, response.error)
        ids = _ids_in(response.result)
        self.assertEqual(len(ids), 2, response.result)
        return ids

    def test_list_events_prints_complete_ids(self):
        ids = self._list_ids()
        self.assertEqual(ids, [SINGLE_EVENT_ID, RECURRING_INSTANCE_ID])
        self.assertNotIn("...", ids[0])

    def test_listed_id_round_trips_through_get_event(self):
        for event_id in self._list_ids():
            with self.subTest(event_id=event_id):
                response = _run(app.tool_get_event(_request({"uid": "u1", "event_id": event_id})))
                self.assertIsNone(response.error, response.error)
                self.assertEqual(_ids_in(response.result), [event_id])

    def test_listed_id_round_trips_through_update_event(self):
        for event_id in self._list_ids():
            with self.subTest(event_id=event_id):
                response = _run(
                    app.tool_update_event(_request({"uid": "u1", "event_id": event_id, "title": "Renamed"}))
                )
                self.assertIsNone(response.error, response.error)
                self.assertEqual(self.api.calls[-1], ("PATCH", f"/calendars/primary/events/{event_id}"))

    def test_listed_id_round_trips_through_delete_event(self):
        for event_id in self._list_ids():
            with self.subTest(event_id=event_id):
                response = _run(app.tool_delete_event(_request({"uid": "u1", "event_id": event_id})))
                self.assertIsNone(response.error, response.error)
                self.assertEqual(self.api.calls[-1], ("DELETE", f"/calendars/primary/events/{event_id}"))

    def test_truncated_id_is_rejected_by_the_api_seam(self):
        # Documents why the full id matters: the prefix the old output produced
        # is not an event the Calendar API knows about.
        truncated = SINGLE_EVENT_ID[:20]
        response = _run(app.tool_get_event(_request({"uid": "u1", "event_id": truncated})))
        self.assertIsNotNone(response.error)


class CreatedEventIdIsReported(unittest.TestCase):
    def test_create_event_prints_id_that_get_update_and_delete_accept(self):
        api = _FakeCalendarApi({})
        with patch.object(app, "calendar_api_request", api), patch.object(
            app, "get_valid_access_token", lambda uid: "token"
        ), patch.object(app, "get_default_calendar", lambda uid: "primary"):
            created = _run(
                app.tool_create_event(
                    _request(
                        {
                            "uid": "u1",
                            "title": "Dentist",
                            "start": "2026-09-15T09:00:00Z",
                            "end": "2026-09-15T09:30:00Z",
                        }
                    )
                )
            )
            self.assertIsNone(created.error, created.error)
            ids = _ids_in(created.result)
            self.assertEqual(ids, [SINGLE_EVENT_ID], created.result)

            fetched = _run(app.tool_get_event(_request({"uid": "u1", "event_id": ids[0]})))
            self.assertIsNone(fetched.error, fetched.error)

            updated = _run(app.tool_update_event(_request({"uid": "u1", "event_id": ids[0], "title": "Dentist (moved)"})))
            self.assertIsNone(updated.error, updated.error)
            self.assertEqual(api.calls[-1], ("PATCH", f"/calendars/primary/events/{ids[0]}"))

            deleted = _run(app.tool_delete_event(_request({"uid": "u1", "event_id": ids[0]})))
            self.assertIsNone(deleted.error, deleted.error)
            self.assertEqual(api.calls[-1], ("DELETE", f"/calendars/primary/events/{ids[0]}"))


if __name__ == "__main__":
    unittest.main()
