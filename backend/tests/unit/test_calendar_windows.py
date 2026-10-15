"""Issue #21709 — a future start_date with no end_date must not collapse
the search window to 'the last six months up to now'.
"""

import asyncio
import importlib.util
import os
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _pkg(name):
    mod = sys.modules.get(name)
    if mod is None or not hasattr(mod, "__path__"):
        mod = types.ModuleType(name)
        mod.__path__ = []
        sys.modules[name] = mod
    return mod


def _mod(name):
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return mod


# langchain_core
_pkg("langchain_core")
_lc_tools = _mod("langchain_core.tools")


def _tool_decorator(fn=None, **kwargs):
    if fn is not None and callable(fn):
        fn.func = fn
        return fn

    def dec(func):
        func.func = func
        return func

    return dec


_lc_tools.tool = _tool_decorator
_mod("langchain_core.runnables").RunnableConfig = dict

# database + models + utils packages
_pkg("database")
_mod("database.notifications")
_pkg("models")
_cm = _mod("models.calendar_mutation")
_cm.CalendarMutationResult = MagicMock()
_cm.event_title = MagicMock(return_value="Event Title")
_cm.format_deleted_calendar_events = MagicMock(return_value="Deleted 1 event.")

for _p in [
    "utils",
    "utils.executors",
    "utils.http_client",
    "utils.retrieval",
    "utils.retrieval.tools",
    "utils.retrieval.tools.integration_base",
    "utils.retrieval.tools.google_utils",
    "utils.integration_telemetry",
    "utils.log_sanitizer",
]:
    _pkg(_p)


async def _run_blocking_stub(executor, fn, *args, **kwargs):
    res = fn(*args, **kwargs)
    if asyncio.iscoroutine(res):
        return await res
    return res


_mod("utils.executors").db_executor = MagicMock()
_mod("utils.executors").run_blocking = _run_blocking_stub
_mod("utils.http_client").get_auth_client = MagicMock()

_tel = _mod("utils.integration_telemetry")
_tel.GOOGLE_CALENDAR = "google_calendar"
_tel.IntegrationTelemetryContext = MagicMock
_tel.emit_sync_attempted = MagicMock()
_tel.emit_sync_failed = MagicMock()
_tel.emit_sync_succeeded = MagicMock()

_mod("utils.log_sanitizer").sanitize = lambda t: t
_mod("utils.log_sanitizer").sanitize_pii = lambda t: t


class GoogleAPIError(Exception):
    def __init__(self, message, is_auth_error=False, is_permission_error=False, status_code=400):
        super().__init__(message)
        self.message = message
        self.is_auth_error = is_auth_error
        self.is_permission_error = is_permission_error
        self.status_code = status_code


_gu = _mod("utils.retrieval.tools.google_utils")
_gu.google_api_request = AsyncMock()
_gu.GoogleAPIError = GoogleAPIError
_gu.refresh_google_token = MagicMock()

_ib = _mod("utils.retrieval.tools.integration_base")
_ib.ensure_capped = lambda val, cap, msg: min(val, cap)
def _real_parse(name, value, _hint):
    if value is None:
        return None, None
    try:
        return datetime.fromisoformat(value), None
    except Exception as e:
        return None, f"{name} bad: {e}"


_ib.parse_iso_with_tz = _real_parse
_ib.prepare_access = MagicMock()


def _load(module_name, rel_path):
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, str(BACKEND_DIR / rel_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


ct = _load(
    "utils.retrieval.tools._calendar_windows_test",
    "utils/retrieval/tools/calendar_tools.py",
)


def _event(day_offset, title="evt"):
    d = datetime.now(timezone.utc) + timedelta(days=day_offset)
    return {"id": f"e{day_offset}", "summary": title,
            "start": {"dateTime": d.isoformat()}}




class TestCalendarSearchFutureWindow(unittest.IsolatedAsyncioTestCase):
    """#21709 — a future start_date with no end_date must not collapse
    the search window to 'the last six months up to now'."""

    async def test_future_start_with_search_covers_the_future(self):
        captured = {}

        async def fake_fetch(**kw):
            captured["time_min"] = kw["time_min"]
            captured["time_max"] = kw["time_max"]
            return []

        now = datetime.now(timezone.utc)
        future_start = now + timedelta(days=3)
        with patch.object(ct, "prepare_access",
                          return_value=("u", {"a": 1}, "tok", None)), \
             patch.object(ct, "get_google_calendar_events", new=fake_fetch):
            await ct.get_calendar_events_tool.func(
                start_date=future_start.isoformat(),
                search_query="andy", max_results=10)

        self.assertGreater(captured["time_max"], future_start,
                           "search must look past the future start date")
