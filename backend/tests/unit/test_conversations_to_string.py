import os
import sys
import time
import types
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _ensure_stub(name):
    existing = sys.modules.get(name)
    if existing is not None and getattr(existing, "__file__", None):
        return existing
    if existing is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return sys.modules[name]


# Stub database chain so render.py can import at module level without Firestore
_ensure_stub("database")
sys.modules["database"].__path__ = getattr(sys.modules["database"], "__path__", [])
for _sub in ["_client", "redis_db", "users", "folders", "auth"]:
    _ensure_stub(f"database.{_sub}")
sys.modules["database._client"].db = MagicMock()
sys.modules["database.auth"].get_user_name = MagicMock(return_value="TestUser")
sys.modules["database.users"].get_people_by_ids = MagicMock(return_value=[])
sys.modules["database.folders"].get_folders = MagicMock(return_value=[])

# When run via `pytest tests/unit/`, earlier test files may have stubbed these
# packages with empty ModuleType objects. Force-reimport the real ones.
for _mod in [
    "models",
    "models.conversation",
    "models.conversation_enums",
    "models.structured",
    "utils",
    "utils.conversations",
    "utils.conversations.render",
]:
    _existing = sys.modules.get(_mod)
    if _existing is not None and not getattr(_existing, "__file__", None):
        del sys.modules[_mod]

from models.conversation import AppResult, Conversation
from models.conversation_enums import CategoryEnum
from models.structured import Structured
from utils.conversations.render import conversations_to_string
from models.transcript_segment import TranscriptSegment
from utils.model_text import DisplayClock, ELAPSED_LEGEND, truncation_note


def _make_conversation(overview="Test overview", apps_results=None, title="Test Title"):
    """Create a minimal Conversation for testing."""
    return Conversation(
        id="test-id",
        created_at=datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc),
        started_at=datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 1, 15, 10, 30, tzinfo=timezone.utc),
        structured=Structured(
            title=title,
            overview=overview,
            category=CategoryEnum.personal,
        ),
        apps_results=apps_results or [],
    )


class TestConversationsToStringDedup:
    """Test that conversations_to_string avoids double-summarization."""

    def test_no_apps_results_uses_overview(self):
        conv = _make_conversation(overview="My overview")
        result = conversations_to_string([conv])
        assert "My overview" in result

    def test_apps_results_uses_app_content(self):
        conv = _make_conversation(
            overview="My overview",
            apps_results=[AppResult(app_id="summarizer", content="App summary here")],
        )
        result = conversations_to_string([conv])
        assert "App summary here" in result

    def test_apps_results_excludes_overview(self):
        conv = _make_conversation(
            overview="My overview",
            apps_results=[AppResult(app_id="summarizer", content="App summary here")],
        )
        result = conversations_to_string([conv])
        assert "My overview" not in result

    def test_empty_apps_results_uses_overview(self):
        conv = _make_conversation(overview="Fallback overview", apps_results=[])
        result = conversations_to_string([conv])
        assert "Fallback overview" in result

    def test_empty_app_content_falls_back_to_overview(self):
        conv = _make_conversation(
            overview="Fallback overview",
            apps_results=[AppResult(app_id="summarizer", content="")],
        )
        result = conversations_to_string([conv])
        assert "Fallback overview" in result

    def test_whitespace_app_content_falls_back_to_overview(self):
        conv = _make_conversation(
            overview="Fallback overview",
            apps_results=[AppResult(app_id="summarizer", content="   ")],
        )
        result = conversations_to_string([conv])
        assert "Fallback overview" in result

    def test_first_nonblank_app_result_wins_even_after_blank_result(self):
        conv = _make_conversation(
            overview="Fallback overview",
            apps_results=[
                AppResult(app_id="blank", content="  "),
                AppResult(app_id="selected", content="Selected app output"),
            ],
        )
        result = conversations_to_string([conv])
        assert "Selected app output" in result
        assert "Fallback overview" not in result

    def test_projected_sections_are_emitted_once(self):
        conv = _make_conversation(
            overview="## Decisions\n\n- Ship the design.",
        )
        conv.structured.sections = [
            {'heading': 'Decisions', 'body_markdown': '- Ship the design.'},
        ]
        result = conversations_to_string([conv])
        assert result.count('Ship the design.') == 1

    def test_no_duplicate_summarization_label(self):
        conv = _make_conversation(
            apps_results=[AppResult(app_id="summarizer", content="App summary")],
        )
        result = conversations_to_string([conv])
        assert "Summarization:" not in result


class TestConversationsToStringTimezone:
    """Timestamps must render in the user's timezone when tz is provided (issue #6214)."""

    def test_default_is_utc(self):
        # created_at is 10:00 UTC
        conv = _make_conversation()
        result = conversations_to_string([conv])
        assert "Thu 15 Jan 2026 (Personal)" in result
        assert "When: Thu 15 Jan 2026, 10:00–10:30 UTC, 30m" in result

    def test_missing_start_uses_created_at_for_when_line_in_user_zone(self):
        conv = _make_conversation()
        conv.started_at = None
        result = conversations_to_string([conv], clock=DisplayClock.from_name('Asia/Ho_Chi_Minh'))
        assert 'When: Thu 15 Jan 2026, 17:00–17:30 Asia/Ho_Chi_Minh (UTC+07:00), 30m' in result

    def test_elapsed_legend_once_and_only_when_timestamps_show(self):
        first = _make_conversation()
        second = _make_conversation()
        first.transcript_segments = [TranscriptSegment(text='hello', is_user=True, start=12, end=15)]
        second.transcript_segments = [TranscriptSegment(text='again', is_user=True, start=20, end=23)]
        rendered = conversations_to_string([first, second], use_transcript=True, include_timestamps=True)
        assert rendered.count(ELAPSED_LEGEND) == 1
        without_timestamps = conversations_to_string([first], use_transcript=True, include_timestamps=False)
        assert ELAPSED_LEGEND not in without_timestamps

    def test_truncation_note_is_rendered_only_when_supplied(self):
        conv = _make_conversation()
        note = truncation_note(
            shown=1,
            total=2,
            unit='transcript segments',
            how_to_get_more='Increase max_transcript_segments or set it to -1.',
        )
        shown = conversations_to_string([conv], use_transcript=True, truncation_notes={conv.id: note})
        complete = conversations_to_string([conv], use_transcript=True, truncation_notes={})
        assert 'omitted, not absent' in shown
        assert 'omitted, not absent' not in complete

    def test_converts_to_user_timezone(self):
        # 10:00 UTC -> 07:00 in America/Sao_Paulo (UTC-3), matching the issue's "off by 3 hours" report
        conv = _make_conversation()
        result = conversations_to_string([conv], tz="America/Sao_Paulo")
        assert "When: Thu 15 Jan 2026, 07:00–07:30 America/Sao_Paulo (UTC-03:00), 30m" in result
        assert "America/Sao_Paulo (UTC-03:00)" in result

    def test_kolkata_half_hour_offset(self):
        # 10:00 UTC -> 15:30 IST (UTC+5:30)
        conv = _make_conversation()
        result = conversations_to_string([conv], tz="Asia/Kolkata")
        assert "15:30–16:00 Asia/Kolkata (UTC+05:30), 30m" in result

    def test_invalid_timezone_falls_back_to_utc(self):
        conv = _make_conversation()
        result = conversations_to_string([conv], tz="Not/AZone")
        assert "10:00–10:30 UTC, 30m" in result


class TestConversationsToStringEventTimes:
    """structured.events[].start must render in the user's tz with a label.

    The Events line used to str() the raw stored datetime ('2026-09-26 07:18:00+00:00'),
    an unlabelled UTC wall clock on an otherwise tz-labelled card. The chat model read it
    as the local a.m. time and stated the wrong time of day for the event (reported as
    'event was in the morning, actually in the afternoon', UTC+7). Same contract as the
    Started/Finished lines: user-local wall clock + tz label, with duration stated as a
    bare number so a clock pair can never be misread as start-to-end times.
    """

    def _make_event_conversation(self):
        from models.structured import Event

        conv = _make_conversation()
        conv.structured.events = [
            Event(
                title="Grokbot demo",
                description="",
                start=datetime(2026, 9, 26, 7, 18, tzinfo=timezone.utc),
                duration=130,
            )
        ]
        return conv

    def test_event_start_converts_to_user_tz_with_label(self):
        conv = self._make_event_conversation()
        result = conversations_to_string([conv], tz="Asia/Ho_Chi_Minh")
        assert "14:18 Asia/Ho_Chi_Minh" in result
        assert "07:18" not in result
        # Duration is a bare value (format_duration), not a second clock pair.
        assert "2h 10m" in result

    def test_event_start_defaults_to_utc_label(self):
        conv = self._make_event_conversation()
        result = conversations_to_string([conv])
        assert "07:18 UTC" in result
        assert "+00:00" not in result


def _make_naive_conversation(created, started, finished):
    """A Conversation whose timestamps are timezone-naive (as stored for many rows)."""
    return Conversation(
        id="naive-id",
        created_at=created,
        started_at=started,
        finished_at=finished,
        structured=Structured(title="T", overview="O", category=CategoryEnum.personal),
        apps_results=[],
    )


class TestConversationsToStringNaiveTimestamps:
    """Naive stored timestamps must be read as UTC, never as the server's local time.

    ``conversation.created_at`` / ``started_at`` / ``finished_at`` are plain ``datetime``
    and are frequently naive (stored as naive UTC). Calling ``.astimezone(display_tz)`` on a
    naive datetime makes Python assume it is in the *server's* local timezone, so the text
    handed to the chat LLM shows a wrong wall clock whenever the backend host is not on UTC —
    exactly the "incorrect event time mentions" class of bug the module's ``_as_utc`` guard
    exists to prevent (issues #4643, #6214). This test forces a non-UTC process timezone so
    the naive-as-local defect is deterministic regardless of where the suite runs.
    """

    def setup_method(self):
        self._old_tz = os.environ.get("TZ")
        os.environ["TZ"] = "America/Los_Angeles"  # UTC-8 / -7, well away from UTC
        if hasattr(time, "tzset"):
            time.tzset()

    def teardown_method(self):
        if self._old_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = self._old_tz
        if hasattr(time, "tzset"):
            time.tzset()

    def test_naive_timestamps_render_as_utc(self):
        if not hasattr(time, "tzset"):
            pytest.skip("time.tzset() unavailable on this platform")
        # Naive 20:00 must be read as 20:00 UTC. The buggy path would treat it as
        # 20:00 America/Los_Angeles and render 16 Jan ~04:00 UTC instead.
        conv = _make_naive_conversation(
            created=datetime(2026, 1, 15, 20, 0),
            started=datetime(2026, 1, 15, 20, 0),
            finished=datetime(2026, 1, 15, 20, 30),
        )
        result = conversations_to_string([conv])
        assert "When: Thu 15 Jan 2026, 20:00–20:30 UTC, 30m" in result
        assert "16 Jan" not in result

    def test_naive_timestamps_convert_to_user_tz(self):
        if not hasattr(time, "tzset"):
            pytest.skip("time.tzset() unavailable on this platform")
        # Naive 20:00 (UTC) -> 17:00 in America/Sao_Paulo (UTC-3), independent of server tz.
        conv = _make_naive_conversation(
            created=datetime(2026, 1, 15, 20, 0),
            started=datetime(2026, 1, 15, 20, 0),
            finished=datetime(2026, 1, 15, 20, 30),
        )
        result = conversations_to_string([conv], tz="America/Sao_Paulo")
        assert "17:00–17:30 America/Sao_Paulo (UTC-03:00), 30m" in result
