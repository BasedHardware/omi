"""Tests for cancelling/rescheduling the client reminder on action-item completion (#5085).

Completing (not deleting) an action item never cancelled its client-scheduled reminder, and the
update endpoint actively re-armed a completed item. The fix centralizes the decision in
utils.notifications.sync_action_item_reminder and calls it from every create/update/complete path.

utils.notifications pulls in firebase/database at import, so we import the REAL module under a stub
finder (so we exercise the real helper, not a copy), then patch the two send_* helpers. A second
group of source-inspection tests guards that every call site stays wired to the helper.
"""

import importlib.abc
import importlib.machinery
import os
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

# Keep these REAL (module under test + its package); stub the heavy leaves.
_REAL = {"utils", "utils.notifications"}
_PREF = ("firebase_admin", "database", "google", "utils.executors", "utils.llm")


class _AutoMock(types.ModuleType):
    __path__ = []

    def __getattr__(self, n):
        if n.startswith("__") and n.endswith("__"):
            raise AttributeError(n)
        m = MagicMock()
        setattr(self, n, m)
        return m


class _Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path=None, target=None):
        if name in _REAL:
            return None
        if any(name == p or name.startswith(p + ".") for p in _PREF):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
        return None

    def create_module(self, spec):
        return _AutoMock(spec.name)

    def exec_module(self, m):
        pass


def _load_real_notifications():
    sys.path.insert(0, str(BACKEND_DIR))
    finder = _Finder()
    sys.meta_path.insert(0, finder)
    try:
        import utils.notifications as notif

        return notif
    finally:
        sys.meta_path.remove(finder)
        for name in list(sys.modules.keys()):
            if name in _REAL:
                continue
            if any(name == p or name.startswith(p + ".") for p in _PREF):
                sys.modules.pop(name, None)


notif = _load_real_notifications()


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


def test_helper_cancels_on_completed_or_no_due():
    n = _src("utils/notifications.py")
    assert "def sync_action_item_reminder" in n
    assert "if completed or not due_at" in n  # cancel branch
    assert "send_action_item_deletion_message" in n and "send_action_item_update_message" in n


def test_router_wires_helper_and_no_longer_blindly_rearms():
    ai = _src("routers/action_items.py")
    # toggle-completion AND update both reconcile through the helper
    assert ai.count("sync_action_item_reminder(") >= 2
    # the old unconditional "re-arm whenever due_at present" block is gone
    assert "if 'due_at' in update_data and update_data['due_at']:" not in ai
    # creating an already-completed item must not arm a reminder
    assert "not request.completed" in ai


def test_agentic_and_developer_paths_wired():
    for rel in [
        "utils/retrieval/tools/action_item_tools.py",
        "utils/retrieval/tool_services/action_items.py",
        "routers/developer.py",
    ]:
        assert "sync_action_item_reminder(" in _src(rel), rel
