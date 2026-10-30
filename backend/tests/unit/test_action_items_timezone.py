"""Tests for timezone-aware action-item timestamps in chat retrieval (issue #4643).

The agentic chat tool ``get_action_items_tool`` used to render action-item
timestamps with a bare ``strftime`` and no timezone, e.g. ``Due: 2026-06-26 22:00``.
The chat model then read that UTC wall-clock time as the user's local time and
mislabelled the time of day ("tonight" when it was actually mid-afternoon).

These tests assert the tool now renders ``created_at``/``due_at``/``completed_at``
in the user's local timezone with an explicit label, matching the pattern that
``conversations_to_string`` already uses for conversations.
"""

from datetime import datetime, timezone
from unittest.mock import patch

from database import notifications as runtime_notifications_db
from utils import model_text as _model_text
from utils.retrieval.tools import action_item_tools

get_action_items_tool = action_item_tools.get_action_items_tool.func


def _make_config(uid="test-user-123", tz=None):
    values = {"user_id": uid}
    if tz is not None:
        values["user_timezone"] = tz
    return {"configurable": values}


# A fixed instant: 22:00 UTC == 15:00:00 in America/Los_Angeles (PDT, UTC-7 in June).
_UTC_INSTANT = datetime(2026, 6, 26, 22, 0, 0, tzinfo=timezone.utc)


def _item(**over):
    base = {
        'id': 'ai-1',
        'description': 'Submit the quarterly report',
        'completed': False,
        'created_at': _UTC_INSTANT,
        'due_at': _UTC_INSTANT,
        'completed_at': _UTC_INSTANT,
    }
    base.update(over)
    return base


def _run(items, tz):
    with patch.object(action_item_tools.action_items_db, 'get_action_items', return_value=items):
        return get_action_items_tool(config=_make_config(tz=tz))


# ===========================================================================
# Shared model-facing instant formatter
# ===========================================================================
class TestFormatLocalHelper:
    def test_aware_utc_converted_to_user_tz_with_label(self):
        out = _model_text.format_instant(_UTC_INSTANT, _model_text.DisplayClock.from_name("America/Los_Angeles"))
        assert out == "Fri 26 Jun 2026, 15:00 America/Los_Angeles (UTC-07:00)"

    def test_naive_value_treated_as_utc(self):
        naive = datetime(2026, 6, 26, 22, 0, 0)  # no tzinfo
        out = _model_text.format_instant(naive, _model_text.DisplayClock.from_name("America/Los_Angeles"))
        assert out == "Fri 26 Jun 2026, 15:00 America/Los_Angeles (UTC-07:00)"

    def test_utc_label_unchanged(self):
        out = _model_text.format_instant(_UTC_INSTANT, _model_text.DisplayClock.utc())
        assert out == "Fri 26 Jun 2026, 22:00 UTC"


# ===========================================================================
# get_action_items_tool rendering
# ===========================================================================
class TestActionItemsTimezoneRendering:
    def test_0718_utc_renders_as_1418_with_the_turn_zone_label(self):
        instant = datetime(2026, 9, 26, 7, 18, tzinfo=timezone.utc)
        result = _run([_item(created_at=instant, due_at=instant)], tz="Asia/Ho_Chi_Minh")
        assert result.startswith(
            "Action items (1 found, pending first, soonest due date first, newest created first (undated last)):"
        )
        assert "User Action Items" not in result
        assert "Created: Sat 26 Sep 2026, 14:18 Asia/Ho_Chi_Minh (UTC+07:00)" in result
        assert "Due: Sat 26 Sep 2026, 14:18 Asia/Ho_Chi_Minh (UTC+07:00)" in result

    def test_due_date_rendered_in_user_timezone(self):
        result = _run([_item()], tz="America/Los_Angeles")
        assert "Due: Fri 26 Jun 2026, 15:00 America/Los_Angeles (UTC-07:00)" in result
        # The raw UTC wall-clock time must not leak through unlabeled.
        assert "22:00" not in result

    def test_created_and_completed_rendered_in_user_timezone(self):
        result = _run([_item(completed=True)], tz="America/Los_Angeles")
        assert "Created: Fri 26 Jun 2026, 15:00 America/Los_Angeles (UTC-07:00)" in result
        assert "Completed: Fri 26 Jun 2026, 15:00 America/Los_Angeles (UTC-07:00)" in result

    def test_utc_when_timezone_is_utc(self):
        result = _run([_item()], tz="UTC")
        assert "Due: Fri 26 Jun 2026, 22:00 UTC" in result

    def test_empty_timezone_falls_back_to_utc(self):
        with patch.object(runtime_notifications_db, 'get_user_time_zone', return_value=None):
            result = _run([_item()], tz="")
        assert "Due: Fri 26 Jun 2026, 22:00 UTC" in result

    def test_invalid_timezone_falls_back_to_utc_without_crashing(self):
        result = _run([_item()], tz="Not/AZone")
        assert "Due: Fri 26 Jun 2026, 22:00 UTC" in result

    def test_naive_timestamp_is_converted_as_utc(self):
        naive_item = _item(due_at=datetime(2026, 6, 26, 22, 0, 0))  # naive
        result = _run([naive_item], tz="America/Los_Angeles")
        assert "Due: Fri 26 Jun 2026, 15:00 America/Los_Angeles (UTC-07:00)" in result

    def test_label_on_every_timestamp_line(self):
        result = _run([_item(completed=True)], tz="Asia/Tokyo")
        # Tokyo is UTC+9, so 22:00 UTC == 07:00 the next day.
        assert result.count("Asia/Tokyo") == 3
        assert "Sat 27 Jun 2026, 07:00 Asia/Tokyo (UTC+09:00)" in result

    def test_timezone_lookup_failure_falls_back_to_utc(self):
        # A Firestore failure in the timezone lookup must not abort retrieval; it
        # falls back to UTC formatting instead (cubic finding on #8483).
        with patch.object(action_item_tools.action_items_db, 'get_action_items', return_value=[_item()]), patch.object(
            runtime_notifications_db, 'get_user_time_zone', side_effect=RuntimeError("firestore down")
        ):
            result = get_action_items_tool(config=_make_config())
        assert "Due: Fri 26 Jun 2026, 22:00 UTC" in result
        assert "Error" not in result
