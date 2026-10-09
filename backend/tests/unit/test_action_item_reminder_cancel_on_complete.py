"""Tests for cancelling/rescheduling the client reminder on action-item completion (#5085).

Completing (not deleting) an action item never cancelled its client-scheduled reminder, and the
update endpoint actively re-armed a completed item. The fix centralizes the decision in
utils.notifications.sync_action_item_reminder and calls it from every create/update/complete path.

The real helper runs with its delivery functions patched. A second group of
source-inspection tests supplements behavior with narrow call-site wiring guards.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from utils import notifications as notif

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def _call(completed, due_at):
    with patch.object(notif, "send_action_item_deletion_message") as cancel, patch.object(
        notif, "send_action_item_update_message"
    ) as reschedule:
        notif.sync_action_item_reminder("u1", "a1", "desc", completed, due_at)
        return cancel, reschedule


# ---------------------------------------------------------------------------
# Real helper behavior
# ---------------------------------------------------------------------------
def test_completed_cancels_reminder():
    cancel, reschedule = _call(True, datetime.now(timezone.utc) + timedelta(days=1))
    cancel.assert_called_once()
    reschedule.assert_not_called()


def test_open_with_due_reschedules():
    due = datetime.now(timezone.utc) + timedelta(days=1)
    cancel, reschedule = _call(False, due)
    reschedule.assert_called_once()
    cancel.assert_not_called()
    assert reschedule.call_args.kwargs.get("due_at") == due.isoformat()  # datetime -> iso string


def test_open_without_due_cancels():
    cancel, reschedule = _call(False, None)
    cancel.assert_called_once()  # due date cleared -> cancel any stale reminder
    reschedule.assert_not_called()


def test_completed_without_due_cancels():
    cancel, reschedule = _call(True, None)
    cancel.assert_called_once()
    reschedule.assert_not_called()


# ---------------------------------------------------------------------------
# Source-inspection: every create/update/complete path stays wired to the helper
# ---------------------------------------------------------------------------
def _src(rel):
    return (BACKEND_DIR / rel).read_text(encoding="utf-8")


_HELPER = "sync_action_item_reminder"


def _live_call_lines(rel):
    """Lines that actually call the helper, excluding comments — so a commented-out or dead-text
    occurrence can't satisfy the wire guard."""
    return [ln for ln in _src(rel).splitlines() if f"{_HELPER}(" in ln and not ln.lstrip().startswith("#")]


def _is_imported(rel):
    """True if the helper is imported (single-line `from x import a, helper` or a parenthesized
    multi-line member line `    helper,`)."""
    for ln in _src(rel).splitlines():
        s = ln.strip()
        if s in (f"{_HELPER},", _HELPER):  # member of a parenthesized import block
            return True
        if s.startswith(("from ", "import ")) and _HELPER in s:  # single-line import
            return True
    return False


def test_helper_cancels_on_completed_or_no_due():
    for completed, due_at in [(True, datetime(2027, 1, 15, tzinfo=timezone.utc)), (False, None)]:
        cancel, reschedule = _call(completed, due_at)
        cancel.assert_called_once_with(user_id="u1", action_item_id="a1")
        reschedule.assert_not_called()


def test_router_wires_helper_and_no_longer_blindly_rearms():
    ai = _src("routers/action_items.py")
    assert _is_imported("routers/action_items.py")
    # toggle-completion, update AND the reminders sync batch all reconcile through the helper
    # (real calls, not comments)
    assert len(_live_call_lines("routers/action_items.py")) >= 3
    # the old unconditional "re-arm whenever due_at present" block is gone
    assert "if 'due_at' in update_data and update_data['due_at']:" not in ai
    # A create replay uses the saved state, which may now be completed.
    # Behavioral coverage is in test_action_item_idempotency.py.
    assert "not response.completed" in ai


def test_agentic_and_developer_paths_wired():
    for rel in [
        "utils/retrieval/tools/action_item_tools.py",
        "utils/retrieval/tool_services/action_items.py",
        "routers/developer.py",
    ]:
        assert _is_imported(rel), f"{rel} does not import {_HELPER}"
        assert _live_call_lines(rel), f"{rel} has no live (non-comment) {_HELPER} call"
