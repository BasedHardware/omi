"""Hermetic regressions for BasedHardware/omi#13922.

create_task crashed or silently dropped fields when optional parameters arrived
wrong-typed: non-numeric assignee tokens raised inside the int() comprehension
and aborted task creation, millisecond due-date timestamps failed ISO parsing,
and priority was forwarded to ClickUp without coercion or 1-4 validation.
The same defect class lived in two sibling spots: task_detector emitted the
"None" sentinel string for members without an id, and process_segments called
seg.get() on non-dict transcript segments.

The suite loads the production modules with stub-only dependencies (requests,
dotenv, fastapi, openai, storage, notifications) — no network, credentials, or
third-party packages — and drives both the client boundary and the real
process_segments handler path.
"""

import asyncio
import importlib.util
import sys
import types
import unittest
from datetime import datetime, timezone as dt_timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

HERE = Path(__file__).resolve().parent


def _module(name, **attributes):
    value = types.ModuleType(name)
    value.__dict__.update(attributes)
    return value


# clickup_client.py imports requests + dotenv at load time; stub both during
# the import (same pattern as test_clickup_client.py) so the suite runs on a
# stdlib-only interpreter. The stub stays bound inside the loaded module, so
# patching clickup_client.requests.post still intercepts the HTTP call.
_requests = _module("requests", get=None, post=None)
_dotenv = _module("dotenv", load_dotenv=lambda *args, **kwargs: None)

_spec = importlib.util.spec_from_file_location("clickup_client", HERE / "clickup_client.py")
clickup_client = importlib.util.module_from_spec(_spec)
with patch.dict(sys.modules, {"requests": _requests, "dotenv": _dotenv}):
    _spec.loader.exec_module(clickup_client)

# task_detector.py builds a module-level AsyncOpenAI client; a Mock stands in
# and its chat completion is replaced per test.
_spec = importlib.util.spec_from_file_location("task_detector", HERE / "task_detector.py")
task_detector = importlib.util.module_from_spec(_spec)
with patch.dict(sys.modules, {"openai": _module("openai", AsyncOpenAI=Mock), "dotenv": _dotenv}):
    _spec.loader.exec_module(task_detector)


class _FastAPI:
    def __init__(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda handler: handler

    post = get

    def on_event(self, *args, **kwargs):
        return lambda handler: handler


class _Resp:
    def __init__(self, *args, **kwargs):
        pass


# main.py wires FastAPI, storage, the client, the detector, and notifications
# at import. The real clickup_client module is registered so the production
# create_task runs inside the handler path under test.
_main_stubs = {
    "fastapi": _module(
        "fastapi",
        FastAPI=_FastAPI,
        Request=_Resp,
        HTTPException=Exception,
        Query=lambda *args, **kwargs: None,
    ),
    "fastapi.responses": _module(
        "fastapi.responses", HTMLResponse=_Resp, RedirectResponse=_Resp, JSONResponse=_Resp
    ),
    "dotenv": _dotenv,
    "simple_storage": _module(
        "simple_storage",
        SimpleUserStorage=Mock(),
        SimpleSessionStorage=Mock(),
        sessions={},
        users={},
        save_users=Mock(),
        save_sessions=Mock(),
    ),
    "clickup_client": clickup_client,
    "task_detector": _module("task_detector", TaskDetector=Mock),
    "omi_notifications": _module(
        "omi_notifications", notify_task_created=AsyncMock(), notify_task_failed=AsyncMock()
    ),
}

_spec = importlib.util.spec_from_file_location("clickup_app_main", HERE / "main.py")
app_main = importlib.util.module_from_spec(_spec)
with patch.dict(sys.modules, _main_stubs):
    _spec.loader.exec_module(app_main)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self._payload


def run_create_task(client, **kwargs):
    """Run the real create_task with a stubbed POST; returns (result, task_data)."""
    sent = {}

    def post(url, headers=None, json=None):
        sent["json"] = json
        return FakeResponse(
            {
                "id": "task-1",
                "name": json.get("name"),
                "url": "https://app.clickup.com/t/task-1",
                "status": {"status": "open"},
            }
        )

    with patch.object(clickup_client.requests, "post", post):
        result = asyncio.run(
            client.create_task(access_token="token", list_id="list-1", name="Test task", **kwargs)
        )
    return result, sent.get("json") or {}


class _UtcZone:
    """pytz-zone stand-in: pytz's localize() is replace(tzinfo=utc) for UTC."""

    def localize(self, dt):
        return dt.replace(tzinfo=dt_timezone.utc)


# pytz is not installed in the stdlib-only test environment; a fake zone pins
# ISO parsing to UTC so expected millisecond values are deterministic.
FAKE_PYTZ = _module("pytz", timezone=lambda name: _UtcZone())


def iso_ms(year, month, day, hour=0, minute=0, second=0):
    return int(datetime(year, month, day, hour, minute, second, tzinfo=dt_timezone.utc).timestamp() * 1000)


class AssigneeCoercionTests(unittest.TestCase):
    def setUp(self):
        self.client = clickup_client.ClickUpClient()

    def test_absent_null_and_empty_send_no_assignees(self):
        for kwargs in ({}, {"assignees": None}, {"assignees": []}):
            with self.subTest(kwargs=kwargs):
                result, sent = run_create_task(self.client, **kwargs)
                self.assertTrue(result["success"])
                self.assertNotIn("assignees", sent)

    def test_numeric_strings_ints_and_integral_floats_become_ids(self):
        result, sent = run_create_task(self.client, assignees=["123", " 456 ", 789, 42.0])
        self.assertTrue(result["success"])
        self.assertEqual(sent["assignees"], [123, 456, 789, 42])

    def test_invalid_tokens_are_dropped_not_fatal(self):
        # The failure from #13922: names, JSON nulls, "None" sentinel strings,
        # blanks, zero/negatives, and booleans each made int() raise and the
        # whole task creation returned success=False.
        result, sent = run_create_task(
            self.client, assignees=["sarah", "None", "null", None, "  ", "-7", 0, -3, True, 2.5]
        )
        self.assertTrue(result["success"], "task creation must continue when no assignee resolves")
        self.assertNotIn("assignees", sent)

    def test_mixed_tokens_keep_valid_ids_deduped(self):
        result, sent = run_create_task(self.client, assignees=["42", "sarah", "42", 42, "None"])
        self.assertTrue(result["success"])
        self.assertEqual(sent["assignees"], [42])

    def test_non_list_assignee_value_is_coerced(self):
        for raw, expected in (("123", [123]), (456, [456]), ("sarah", None), (None, None)):
            with self.subTest(raw=raw):
                result, sent = run_create_task(self.client, assignees=raw)
                self.assertTrue(result["success"])
                if expected is None:
                    self.assertNotIn("assignees", sent)
                else:
                    self.assertEqual(sent["assignees"], expected)


class DueDateCoercionTests(unittest.TestCase):
    def setUp(self):
        self.client = clickup_client.ClickUpClient()

    def test_absent_and_null_send_no_due_date(self):
        for kwargs in ({}, {"due_date": None}):
            with self.subTest(kwargs=kwargs):
                result, sent = run_create_task(self.client, **kwargs)
                self.assertTrue(result["success"])
                self.assertNotIn("due_date", sent)

    def test_epoch_milliseconds_int_passes_through(self):
        # #13922: 'T' in due_date raised TypeError on ints and the due date was
        # silently dropped (a traceback was printed, task created without it).
        result, sent = run_create_task(self.client, due_date=1726358400000)
        self.assertTrue(result["success"])
        self.assertEqual(sent["due_date"], 1726358400000)
        self.assertIs(sent["due_date_time"], True)

    def test_epoch_milliseconds_float_and_digit_string(self):
        for raw in (1726358400000.0, "1726358400000", " 1726358400000 "):
            with self.subTest(raw=raw):
                result, sent = run_create_task(self.client, due_date=raw)
                self.assertTrue(result["success"])
                self.assertEqual(sent["due_date"], 1726358400000)
                self.assertIs(sent["due_date_time"], True)

    def test_iso_date_without_time_uses_end_of_day(self):
        with patch.dict(sys.modules, {"pytz": FAKE_PYTZ}):
            result, sent = run_create_task(self.client, due_date="2025-09-15", timezone="UTC")
        self.assertTrue(result["success"])
        self.assertEqual(sent["due_date"], iso_ms(2025, 9, 15, 23, 59, 59))
        self.assertIs(sent["due_date_time"], False)

    def test_iso_datetime_with_time_is_preserved(self):
        with patch.dict(sys.modules, {"pytz": FAKE_PYTZ}):
            result, sent = run_create_task(self.client, due_date="2025-09-15T17:30:00", timezone="UTC")
        self.assertTrue(result["success"])
        self.assertEqual(sent["due_date"], iso_ms(2025, 9, 15, 17, 30, 0))
        self.assertIs(sent["due_date_time"], True)

    def test_unparseable_or_wrong_typed_due_date_is_dropped_not_fatal(self):
        for raw in ("garbage", "2025-13-45", True, -1, 0, {"date": "x"}, ["2025-09-15"]):
            with self.subTest(raw=raw):
                result, sent = run_create_task(self.client, due_date=raw)
                self.assertTrue(result["success"], "a bad due date must not fail task creation")
                self.assertNotIn("due_date", sent)


class PriorityCoercionTests(unittest.TestCase):
    def setUp(self):
        self.client = clickup_client.ClickUpClient()

    def test_absent_and_null_send_no_priority(self):
        for kwargs in ({}, {"priority": None}):
            with self.subTest(kwargs=kwargs):
                result, sent = run_create_task(self.client, **kwargs)
                self.assertTrue(result["success"])
                self.assertNotIn("priority", sent)

    def test_valid_priorities_and_boundaries(self):
        for raw in (1, 2, 3, 4):
            with self.subTest(raw=raw):
                result, sent = run_create_task(self.client, priority=raw)
                self.assertTrue(result["success"])
                self.assertEqual(sent["priority"], raw)

    def test_numeric_string_and_integral_float_are_coerced(self):
        for raw, expected in (("2", 2), (" 4 ", 4), (3.0, 3)):
            with self.subTest(raw=raw):
                result, sent = run_create_task(self.client, priority=raw)
                self.assertTrue(result["success"])
                self.assertEqual(sent["priority"], expected)

    def test_out_of_range_priority_is_dropped_not_sent(self):
        # ClickUp only accepts 1-4; passing 0/5/99 through invited a 400 from
        # the API or an invisible priority.
        for raw in (0, 5, 99, -1):
            with self.subTest(raw=raw):
                result, sent = run_create_task(self.client, priority=raw)
                self.assertTrue(result["success"])
                self.assertNotIn("priority", sent)

    def test_wrong_typed_priority_is_dropped_not_sent(self):
        for raw in ("urgent", True, [2], {"p": 1}, 2.5):
            with self.subTest(raw=raw):
                result, sent = run_create_task(self.client, priority=raw)
                self.assertTrue(result["success"])
                self.assertNotIn("priority", sent)


class ProcessSegmentsTests(unittest.TestCase):
    """Drive the production test-mode handler: the same coercion boundary all
    three create_task call sites share."""

    def _user(self):
        return {
            "uid": "user-1",
            "access_token": "token",
            "timezone": "UTC",
            "available_lists": [{"id": "list-1", "name": "Inbox"}],
            "available_members": [],
            "selected_list": "list-1",
        }

    def _session(self, session_id="test_session_1", task_mode="idle"):
        return {
            "session_id": session_id,
            "task_mode": task_mode,
            "segments_count": 0,
            "accumulated_text": "",
        }

    def test_handler_survives_wrong_typed_extracted_fields(self):
        detector = Mock()
        detector.detect_trigger.return_value = True
        detector.extract_task_content.return_value = "fix the login bug"
        detector.ai_extract_task_details = AsyncMock(
            return_value=(
                "list-1",
                "Inbox",
                "Fix login bug",
                None,
                99,  # out of ClickUp's 1-4 range
                1726358400000,  # millisecond timestamp, not ISO
                ["sarah", "None", "123"],  # names and sentinels mixed with an id
            )
        )
        sent = {}

        def post(url, headers=None, json=None):
            sent["json"] = json
            return FakeResponse(
                {"id": "task-9", "name": "Fix login bug", "url": "u", "status": {"status": "open"}}
            )

        with patch.object(app_main, "task_detector", detector), patch.object(
            clickup_client.requests, "post", post
        ):
            message = asyncio.run(
                app_main.process_segments(
                    self._session(), [{"text": "create clickup task fix login bug"}], self._user()
                )
            )

        self.assertTrue(message.startswith("✅ Task created"), message)
        self.assertEqual(sent["json"]["assignees"], [123])
        self.assertEqual(sent["json"]["due_date"], 1726358400000)
        self.assertNotIn("priority", sent["json"])

    def test_handler_survives_all_invalid_assignees(self):
        # The exact #13922 abort: every token invalid must not fail the task.
        detector = Mock()
        detector.detect_trigger.return_value = True
        detector.extract_task_content.return_value = "fix the login bug"
        detector.ai_extract_task_details = AsyncMock(
            return_value=("list-1", "Inbox", "Fix login bug", None, 2, None, ["sarah", "None", None])
        )
        sent = {}

        def post(url, headers=None, json=None):
            sent["json"] = json
            return FakeResponse({"id": "task-9", "name": "x", "url": "u", "status": {"status": "open"}})

        with patch.object(app_main, "task_detector", detector), patch.object(
            clickup_client.requests, "post", post
        ):
            message = asyncio.run(
                app_main.process_segments(
                    self._session(), [{"text": "create clickup task fix login bug"}], self._user()
                )
            )

        self.assertTrue(message.startswith("✅ Task created"), message)
        self.assertNotIn("assignees", sent["json"])
        self.assertEqual(sent["json"]["priority"], 2)

    def test_non_dict_segments_do_not_crash_the_handler(self):
        # Same defect class: seg.get() on a wrong-typed JSON element raised
        # AttributeError and failed the webhook.
        detector = Mock()
        detector.detect_trigger.return_value = False
        with patch.object(app_main, "task_detector", detector):
            message = asyncio.run(
                app_main.process_segments(
                    self._session(), [{"text": "hello"}, "raw text", 42, None], self._user()
                )
            )
        self.assertEqual(message, "listening")


class TaskDetectorAssigneeTests(unittest.TestCase):
    def _extract(self, ai_content, members):
        response = Mock()
        message = Mock()
        message.content = ai_content
        choice = Mock()
        choice.message = message
        response.choices = [choice]
        client = Mock()
        client.chat.completions.create = AsyncMock(return_value=response)
        with patch.object(
            task_detector, "get_openai_client", return_value=client
        ):
            return asyncio.run(
                task_detector.TaskDetector.ai_extract_task_details(
                    "fix bug assign to sarah", [], members, "UTC"
                )
            )

    def test_fuzzy_match_without_member_id_emits_no_none_sentinel(self):
        # The "None" token #13922 names is produced here: str(member.get("id"))
        # on a member whose id is None. create_task now filters it, but the
        # producer must not emit it either.
        result = self._extract(
            "LIST: UNKNOWN\nTASK: Fix bug\nDESCRIPTION: NONE\nPRIORITY: 3\nDUE_DATE: NONE\nASSIGNEES: Sarah",
            [{"id": None, "username": "sarah", "email": "sarah@example.com"}],
        )
        self.assertEqual(result[6], [])

    def test_fuzzy_match_with_member_id_returns_id_string(self):
        result = self._extract(
            "LIST: UNKNOWN\nTASK: Fix bug\nDESCRIPTION: NONE\nPRIORITY: 3\nDUE_DATE: NONE\nASSIGNEES: Sarah",
            [{"id": 777, "username": "sarah", "email": "sarah@example.com"}],
        )
        self.assertEqual(result[6], ["777"])


if __name__ == "__main__":
    unittest.main()
