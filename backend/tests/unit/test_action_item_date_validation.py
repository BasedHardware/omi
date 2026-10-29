"""Tests for action item due date validation (issue #4841).

Covers:
1. create_action_item_tool rejects due dates more than 1 day in the past
2. update_action_item_tool rejects due dates more than 1 day in the past
3. Dates within 1-day grace window are accepted
4. Future dates are accepted unchanged
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from database import action_items as action_items_db, chat_edits
from utils.retrieval.tools import action_item_tools

create_action_item_tool = action_item_tools.create_action_item_tool.func
update_action_item_tool = action_item_tools.update_action_item_tool.func


@pytest.fixture(autouse=True)
def storage_and_delivery(monkeypatch):
    monkeypatch.setattr(action_items_db, 'create_action_item', MagicMock(return_value='test-item-id'))
    monkeypatch.setattr(
        action_items_db,
        'get_action_item',
        MagicMock(
            return_value={
                'id': 'test-item-id',
                'description': 'Test task',
                'completed': False,
                'due_at': datetime.now(timezone.utc) + timedelta(hours=24),
            }
        ),
    )
    monkeypatch.setattr(
        action_items_db,
        'update_action_item',
        MagicMock(side_effect=lambda *args, **kwargs: kwargs.get('expected_chat_state', {}).update(after={}) or True),
    )
    monkeypatch.setattr(chat_edits, 'snapshot', MagicMock(return_value={}))
    monkeypatch.setattr(chat_edits, 'envelope', MagicMock(return_value={}))
    monkeypatch.setattr(action_item_tools, 'record_write', MagicMock(return_value=''))
    for name in (
        'send_action_item_completed_notification',
        'send_action_item_created_notification',
        'send_action_item_data_message',
        'sync_action_item_reminder',
    ):
        monkeypatch.setattr(action_item_tools, name, MagicMock())


def _make_config(uid="test-user-123"):
    # Chat turns always carry the resolved zone; without it DisplayClock would import the real
    # database.notifications after the stubs above are restored.
    return {"configurable": {"user_id": uid, "user_timezone": "UTC"}}


# ===========================================================================
# create_action_item_tool tests
# ===========================================================================


class TestCreateActionItemDateValidation:
    def test_rejects_date_months_in_past(self):
        """Due date from September 2025 should be rejected."""
        result = create_action_item_tool(
            description="Call venue",
            due_at="2025-09-15T10:00:00+00:00",
            config=_make_config(),
        )
        assert "Error" in result
        assert "in the past" in result

    def test_rejects_date_one_year_in_past(self):
        """Due date from a year ago should be rejected."""
        one_year_ago = (datetime.now(timezone.utc) - timedelta(days=365)).strftime('%Y-%m-%dT%H:%M:%S+00:00')
        result = create_action_item_tool(
            description="Old task",
            due_at=one_year_ago,
            config=_make_config(),
        )
        assert "Error" in result
        assert "in the past" in result

    def test_accepts_future_date(self):
        """Due date in the future should be accepted."""
        future_date = (datetime.now(timezone.utc) + timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%S+00:00')
        result = create_action_item_tool(
            description="Future task",
            due_at=future_date,
            config=_make_config(),
        )
        assert "Error" not in result
        assert "Added" in result or "✅" in result

    def test_accepts_date_within_grace_window(self):
        """Due date 12 hours ago should be accepted (within 1-day grace)."""
        twelve_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=12)).strftime('%Y-%m-%dT%H:%M:%S+00:00')
        result = create_action_item_tool(
            description="Recent task",
            due_at=twelve_hours_ago,
            config=_make_config(),
        )
        assert "Error" not in result
        assert "Added" in result or "✅" in result

    def test_rejects_date_two_days_in_past(self):
        """Due date 2 days ago should be rejected (beyond 1-day grace)."""
        two_days_ago = (datetime.now(timezone.utc) - timedelta(days=2)).strftime('%Y-%m-%dT%H:%M:%S+00:00')
        result = create_action_item_tool(
            description="Past task",
            due_at=two_days_ago,
            config=_make_config(),
        )
        assert "Error" in result
        assert "in the past" in result

    def test_error_includes_current_time(self):
        """Error message should include current time so LLM can correct."""
        result = create_action_item_tool(
            description="Past task",
            due_at="2025-06-01T10:00:00+00:00",
            config=_make_config(),
        )
        assert "current time is" in result

    def test_format_validation_still_works(self):
        """Format validation should still reject invalid formats."""
        result = create_action_item_tool(
            description="Bad format",
            due_at="not-a-date",
            config=_make_config(),
        )
        assert "Error" in result
        assert "Invalid due_at format" in result

    def test_no_due_date_stays_undated(self):
        """A task the user never dated must be written with no due date.

        Inventing ``now + 24h`` put it in neither the overdue nor the due-today
        bucket any reader uses, so "remind me to X" followed by "what's on my
        list" deterministically answered that there was nothing.
        """
        action_items_db.create_action_item.reset_mock()
        result = create_action_item_tool(
            description="No due date task",
            due_at=None,
            config=_make_config(),
        )
        assert "in the past" not in result
        action_items_db.create_action_item.assert_called_once()
        written = action_items_db.create_action_item.call_args.args[1]
        assert written.get("due_at") is None, f"expected no invented due date, got {written.get('due_at')!r}"

    def test_boundary_23h_ago_accepted(self):
        """Due date 23h ago should be accepted (within 1-day grace)."""
        twenty_three_h = (datetime.now(timezone.utc) - timedelta(hours=23)).strftime('%Y-%m-%dT%H:%M:%S+00:00')
        result = create_action_item_tool(
            description="Boundary task",
            due_at=twenty_three_h,
            config=_make_config(),
        )
        assert "in the past" not in result

    def test_boundary_25h_ago_rejected(self):
        """Due date 25h ago should be rejected (beyond 1-day grace)."""
        twenty_five_h = (datetime.now(timezone.utc) - timedelta(hours=25)).strftime('%Y-%m-%dT%H:%M:%S+00:00')
        result = create_action_item_tool(
            description="Just beyond boundary",
            due_at=twenty_five_h,
            config=_make_config(),
        )
        assert "Error" in result
        assert "in the past" in result

    def test_accepts_non_utc_timezone_offset(self):
        """Due date with -08:00 offset in the future should be accepted."""
        future_pst = (datetime.now(timezone.utc) + timedelta(days=2)).strftime('%Y-%m-%dT%H:%M:%S-08:00')
        result = create_action_item_tool(
            description="PST task",
            due_at=future_pst,
            config=_make_config(),
        )
        assert "Error" not in result
        assert "Added" in result or "✅" in result


# ===========================================================================
# update_action_item_tool tests
# ===========================================================================


class TestUpdateActionItemDateValidation:
    def test_rejects_past_date_on_update(self):
        """Updating due date to a past date should be rejected."""
        result = update_action_item_tool(
            action_item_id="test-item-id",
            due_at="2025-09-15T10:00:00+00:00",
            config=_make_config(),
        )
        assert "Error" in result
        assert "in the past" in result

    def test_accepts_future_date_on_update(self):
        """Updating due date to a future date should work."""
        future_date = (datetime.now(timezone.utc) + timedelta(days=3)).strftime('%Y-%m-%dT%H:%M:%S+00:00')
        action_items_db.update_action_item.side_effect = (
            lambda *args, **kwargs: kwargs['expected_chat_state'].update(after={}) or True
        )
        result = update_action_item_tool(
            action_item_id="test-item-id",
            due_at=future_date,
            config=_make_config(),
        )
        assert "Error" not in result or "in the past" not in result
        assert "updated" in result.lower() or "Successfully" in result

    def test_accepts_date_within_grace_window_on_update(self):
        """Due date 12 hours ago on update should be accepted."""
        twelve_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=12)).strftime('%Y-%m-%dT%H:%M:%S+00:00')
        result = update_action_item_tool(
            action_item_id="test-item-id",
            due_at=twelve_hours_ago,
            config=_make_config(),
        )
        assert "in the past" not in result

    def test_rejects_invalid_format_on_update(self):
        """Invalid date format on update should be rejected."""
        result = update_action_item_tool(
            action_item_id="test-item-id",
            due_at="not-a-date",
            config=_make_config(),
        )
        assert "Error" in result
        assert "Invalid due_at format" in result

    def test_boundary_25h_ago_rejected_on_update(self):
        """Due date 25h ago on update should be rejected."""
        just_beyond = (datetime.now(timezone.utc) - timedelta(hours=25)).strftime('%Y-%m-%dT%H:%M:%S+00:00')
        result = update_action_item_tool(
            action_item_id="test-item-id",
            due_at=just_beyond,
            config=_make_config(),
        )
        assert "Error" in result
        assert "in the past" in result


# ===========================================================================
# ===========================================================================
