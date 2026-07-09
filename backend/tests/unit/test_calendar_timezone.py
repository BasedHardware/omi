"""Tests for timezone-aware calendar event times in chat (issue #4643).

``get_calendar_events_tool`` rendered Google Calendar event times in raw UTC / the
event's own zone, so the chat model mislabeled the time of day ("tonight" vs
"this afternoon"). It now renders Start/End in the user's timezone via two pure
helpers, which these tests cover directly (no Google API or async needed).
"""

import asyncio
import importlib.util
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


class _AutoMockModule(ModuleType):
    """Module stub that returns a MagicMock for any missing attribute."""

    def __init__(self, name):
        super().__init__(name)
        self.__path__ = []

    def __getattr__(self, name):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


def _register(name):
    mod = sys.modules.get(name)
    if not isinstance(mod, _AutoMockModule):
        mod = _AutoMockModule(name)
        sys.modules[name] = mod
        if "." in name:
            parent_name, attr = name.rsplit(".", 1)
            setattr(_register(parent_name), attr, mod)
    return mod


# Stub the heavy imports calendar_tools pulls at module load.
for _name in [
    "httpx",
    "langchain_core",
    "langchain_core.tools",
    "langchain_core.runnables",
    "database",
    "database.users",
    "database.notifications",
    "models",
    "models.calendar_mutation",
    "utils",
    "utils.executors",
    "utils.http_client",
    "utils.integration_telemetry",
    "utils.log_sanitizer",
    "utils.retrieval",
    "utils.retrieval.tools",
    "utils.retrieval.tools.integration_base",
    "utils.retrieval.tools.google_utils",
]:
    _register(_name)

# Passthrough @tool decorator so the tool stays a plain callable.
sys.modules["langchain_core.tools"].tool = lambda func=None, **kw: (func if func is not None else (lambda f: f))


def _load_module_from_file(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


calendar_tools = _load_module_from_file(
    "utils.retrieval.tools.calendar_tools",
    BACKEND_DIR / "utils" / "retrieval" / "tools" / "calendar_tools.py",
)

# 22:00 UTC == 15:00 in America/Los_Angeles (PDT, UTC-7 in June).
_UTC_INSTANT = datetime(2026, 6, 30, 22, 0, 0, tzinfo=timezone.utc)
_LA = ZoneInfo("America/Los_Angeles")


class TestResolveDisplayTz:
    def test_valid_zone(self):
        tzinfo, label = calendar_tools._resolve_display_tz("America/Los_Angeles")
        assert tzinfo == _LA and label == "America/Los_Angeles"

    def test_missing_or_invalid_falls_back_to_utc(self):
        for bad in (None, "", "Not/AZone"):
            tzinfo, label = calendar_tools._resolve_display_tz(bad)
            assert tzinfo == timezone.utc and label == "UTC"


class TestFormatEventDt:
    def test_aware_utc_converted_to_user_tz_with_label(self):
        assert calendar_tools._format_event_dt(_UTC_INSTANT, _LA, "America/Los_Angeles") == (
            "2026-06-30 15:00:00 America/Los_Angeles"
        )

    def test_naive_value_treated_as_utc(self):
        naive = datetime(2026, 6, 30, 22, 0, 0)
        assert calendar_tools._format_event_dt(naive, _LA, "America/Los_Angeles") == (
            "2026-06-30 15:00:00 America/Los_Angeles"
        )

    def test_utc_label_unchanged(self):
        assert calendar_tools._format_event_dt(_UTC_INSTANT, timezone.utc, "UTC") == "2026-06-30 22:00:00 UTC"

    def test_crosses_day_boundary_in_user_tz(self):
        # Tokyo is UTC+9, so 22:00 UTC is 07:00 the next day.
        out = calendar_tools._format_event_dt(_UTC_INSTANT, ZoneInfo("Asia/Tokyo"), "Asia/Tokyo")
        assert out == "2026-07-01 07:00:00 Asia/Tokyo"


class TestUserDisplayTz:
    def test_lookup_success(self):
        with patch.object(calendar_tools, "run_blocking", new=AsyncMock(return_value="America/Los_Angeles")):
            tzinfo, label = asyncio.run(calendar_tools._get_user_display_tz("uid"))
        assert tzinfo == _LA and label == "America/Los_Angeles"

    def test_lookup_failure_falls_back_to_utc(self):
        # A Firestore failure in the timezone lookup must not abort the tool; it
        # falls back to UTC so the calendar events still render (cubic on #8495).
        with patch.object(calendar_tools, "run_blocking", new=AsyncMock(side_effect=RuntimeError("firestore down"))):
            tzinfo, label = asyncio.run(calendar_tools._get_user_display_tz("uid"))
        assert tzinfo == timezone.utc and label == "UTC"
