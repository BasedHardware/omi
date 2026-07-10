"""Tests for timezone-aware action-item timestamps in chat retrieval (issue #4643).

The agentic chat tool ``get_action_items_tool`` used to render action-item
timestamps with a bare ``strftime`` and no timezone, e.g. ``Due: 2026-06-26 22:00:00``.
The chat model then read that UTC wall-clock time as the user's local time and
mislabelled the time of day ("tonight" when it was actually mid-afternoon).

These tests assert the tool now renders ``created_at``/``due_at``/``completed_at``
in the user's local timezone with an explicit label, matching the pattern that
``conversations_to_string`` already uses for conversations.
"""

import importlib.util
import os
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Paths / env
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


# ---------------------------------------------------------------------------
# Stub helpers (same approach as test_action_item_date_validation.py)
# ---------------------------------------------------------------------------
def _stub_module(name):
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    if "." in name:
        parent_name, attr_name = name.rsplit(".", 1)
        parent = sys.modules.get(parent_name)
        if parent is not None:
            setattr(parent, attr_name, mod)
    return mod


def _stub_package(name):
    mod = _stub_module(name)
    mod.__path__ = []
    return mod


def _load_module_from_file(module_name, file_path):
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return mod


# ---------------------------------------------------------------------------
# Stub heavy dependencies
#
# Snapshot sys.modules first so the stubs installed below do not leak into other
# test files during bulk ``pytest tests/unit/`` collection (issue #8661). They are
# restored right after the module under test is imported.
# ---------------------------------------------------------------------------
_SYS_MODULES_SNAPSHOT = dict(sys.modules)

for mod_name in [
    "firebase_admin",
    "firebase_admin.firestore",
    "firebase_admin.auth",
    "firebase_admin.messaging",
    "firebase_admin.credentials",
    "google.cloud.firestore",
    "google.cloud.firestore_v1",
    "google.cloud.firestore_v1.base_query",
    "google.auth",
    "google.auth.transport",
    "google.auth.transport.requests",
    "google.cloud.storage",
    "opuslib",
    "sentry_sdk",
    "database._client",
    "database.redis_db",
    "database.auth",
]:
    if mod_name not in sys.modules:
        _stub_module(mod_name)
sys.modules["database.auth"].get_user_name = MagicMock(return_value="Test User")

# Stub database.action_items (get_action_items is patched per-test)
action_items_db = _stub_module("database.action_items")
action_items_db.get_action_items = MagicMock(return_value=[])
_stub_package("database")

# Stub database.notifications (source of the user's timezone, patched per-test)
notifications_db = _stub_module("database.notifications")
notifications_db.get_user_time_zone = MagicMock(return_value="UTC")

# Stub notifications senders pulled in by action_item_tools
notif_mod = _stub_module("utils.notifications")
notif_mod.send_action_item_completed_notification = MagicMock()
notif_mod.send_action_item_created_notification = MagicMock()
notif_mod.send_action_item_data_message = MagicMock()
notif_mod.sync_action_item_reminder = MagicMock()

# Stub langchain (passthrough @tool so the tool is directly callable)
langchain_core = _stub_package("langchain_core")
langchain_tools = _stub_module("langchain_core.tools")
langchain_runnables = _stub_module("langchain_core.runnables")


class FakeRunnableConfig(dict):
    pass


def fake_tool(func=None, **kwargs):
    if func is not None:
        return func
    return lambda f: f


langchain_tools.tool = fake_tool
langchain_runnables.RunnableConfig = FakeRunnableConfig

# Stub utils packages
_stub_package("utils")
_stub_package("utils.retrieval")
_stub_package("utils.retrieval.tools")
_stub_package("utils.conversations")

# Stub utils.conversations.render with the REAL tz-resolution behavior so the
# conversion under test is genuine (not a mock).
_render_stub = _stub_module("utils.conversations.render")


def _real_resolve_display_tz(tz):
    if tz:
        try:
            return ZoneInfo(tz), tz
        except Exception:
            pass
    return timezone.utc, "UTC"


_render_stub.resolve_display_tz = _real_resolve_display_tz

# Stub utils.retrieval.agentic (agent_config_context)
import contextvars

agentic_stub = _stub_module("utils.retrieval.agentic")
agentic_stub.agent_config_context = contextvars.ContextVar('agent_config', default=None)

# ---------------------------------------------------------------------------
# Load the module under test
# ---------------------------------------------------------------------------
action_item_tools = _load_module_from_file(
    "utils.retrieval.tools.action_item_tools",
    BACKEND_DIR / "utils" / "retrieval" / "tools" / "action_item_tools.py",
)
get_action_items_tool = action_item_tools.get_action_items_tool

# Restore sys.modules now that the module under test is imported and bound to its
# (stubbed) dependencies. This stops the empty-package stubs above from leaking into
# other test files during bulk collection (issue #8661). The tests below patch
# ``action_item_tools.action_items_db`` directly, so the restore does not affect them.
for _name in list(sys.modules):
    if _name in _SYS_MODULES_SNAPSHOT:
        if sys.modules[_name] is not _SYS_MODULES_SNAPSHOT[_name]:
            sys.modules[_name] = _SYS_MODULES_SNAPSHOT[_name]
    else:
        del sys.modules[_name]
del _SYS_MODULES_SNAPSHOT


def _make_config(uid="test-user-123"):
    return {"configurable": {"user_id": uid}}


# A fixed instant: 22:00:00 UTC == 15:00:00 in America/Los_Angeles (PDT, UTC-7 in June).
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
    with patch.object(action_item_tools.action_items_db, 'get_action_items', return_value=items), patch.object(
        action_item_tools.notification_db, 'get_user_time_zone', return_value=tz
    ):
        return get_action_items_tool(config=_make_config())


# ===========================================================================
# _format_local helper
# ===========================================================================
class TestFormatLocalHelper:
    def test_aware_utc_converted_to_user_tz_with_label(self):
        out = action_item_tools._format_local(_UTC_INSTANT, ZoneInfo("America/Los_Angeles"), "America/Los_Angeles")
        assert out == "2026-06-26 15:00:00 America/Los_Angeles"

    def test_naive_value_treated_as_utc(self):
        naive = datetime(2026, 6, 26, 22, 0, 0)  # no tzinfo
        out = action_item_tools._format_local(naive, ZoneInfo("America/Los_Angeles"), "America/Los_Angeles")
        assert out == "2026-06-26 15:00:00 America/Los_Angeles"

    def test_utc_label_unchanged(self):
        out = action_item_tools._format_local(_UTC_INSTANT, timezone.utc, "UTC")
        assert out == "2026-06-26 22:00:00 UTC"


# ===========================================================================
# get_action_items_tool rendering
# ===========================================================================
class TestActionItemsTimezoneRendering:
    def test_due_date_rendered_in_user_timezone(self):
        result = _run([_item()], tz="America/Los_Angeles")
        assert "Due: 2026-06-26 15:00:00 America/Los_Angeles" in result
        # The raw UTC wall-clock time must not leak through unlabeled.
        assert "22:00:00" not in result

    def test_created_and_completed_rendered_in_user_timezone(self):
        result = _run([_item(completed=True)], tz="America/Los_Angeles")
        assert "Created: 2026-06-26 15:00:00 America/Los_Angeles" in result
        assert "Completed: 2026-06-26 15:00:00 America/Los_Angeles" in result

    def test_utc_when_timezone_is_utc(self):
        result = _run([_item()], tz="UTC")
        assert "Due: 2026-06-26 22:00:00 UTC" in result

    def test_empty_timezone_falls_back_to_utc(self):
        result = _run([_item()], tz="")
        assert "Due: 2026-06-26 22:00:00 UTC" in result

    def test_invalid_timezone_falls_back_to_utc_without_crashing(self):
        result = _run([_item()], tz="Not/AZone")
        assert "Due: 2026-06-26 22:00:00 UTC" in result

    def test_naive_timestamp_is_converted_as_utc(self):
        naive_item = _item(due_at=datetime(2026, 6, 26, 22, 0, 0))  # naive
        result = _run([naive_item], tz="America/Los_Angeles")
        assert "Due: 2026-06-26 15:00:00 America/Los_Angeles" in result

    def test_label_on_every_timestamp_line(self):
        result = _run([_item(completed=True)], tz="Asia/Tokyo")
        # Tokyo is UTC+9, so 22:00 UTC == 07:00 the next day.
        assert result.count("Asia/Tokyo") == 3
        assert "2026-06-27 07:00:00 Asia/Tokyo" in result

    def test_timezone_lookup_failure_falls_back_to_utc(self):
        # A Firestore failure in the timezone lookup must not abort retrieval; it
        # falls back to UTC formatting instead (cubic finding on #8483).
        with patch.object(action_item_tools.action_items_db, 'get_action_items', return_value=[_item()]), patch.object(
            action_item_tools.notification_db, 'get_user_time_zone', side_effect=RuntimeError("firestore down")
        ):
            result = get_action_items_tool(config=_make_config())
        assert "Due: 2026-06-26 22:00:00 UTC" in result
        assert "Error" not in result
