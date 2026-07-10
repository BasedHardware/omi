"""search_screen_activity_tool must render match timestamps in the user's timezone (#4643).

The screen-activity search result formatted each match's epoch timestamp with a naive
datetime.fromtimestamp(ts), which uses the host's local timezone. It now renders in the user's
timezone via notification_db.get_user_time_zone(uid), matching how conversation_tools renders chat
timestamps, so screen-activity and conversation matches in the same chat answer use the same
timezone. It falls back to UTC when the user has no timezone set or it is not a valid IANA name.

The _resolve_display_tz helper is exercised behaviorally (the tool has a heavy import graph, so the
module is loaded with its heavy leaves stubbed); the wiring into the render is checked at source level.
"""

import importlib.util
import os
import sys
import types
from datetime import timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
SOURCE = BACKEND_DIR / "utils" / "retrieval" / "tools" / "screen_activity_tools.py"

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


def _mod(name, **attrs):
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    sys.modules[name] = mod
    return mod


# Stub the heavy leaves screen_activity_tools.py imports (all absolute imports, no relative ones, so
# the module can load under a plain name). The utils.retrieval.agentic import is left to fail so the
# module's own ImportError fallback runs.
for _p in ["langchain_core", "database", "utils", "utils.llm"]:
    _pkg(_p)
_mod("langchain_core.tools", tool=lambda fn: fn)
_mod("langchain_core.runnables", RunnableConfig=object)
_mod("database.screen_activity")
_mod("database.vector_db", search_screen_activity_vectors=MagicMock())
_mod("database.notifications", get_user_time_zone=lambda uid: None)
_mod("database._client", db=MagicMock())
_mod("utils.llm.clients", gemini_embed_query=MagicMock())


def _load():
    spec = importlib.util.spec_from_file_location("screen_activity_tools_under_test", str(SOURCE))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sat = _load()


def _with_tz(tz_name):
    return patch.object(sat.notification_db, "get_user_time_zone", lambda uid: tz_name)


def test_resolve_display_tz_uses_user_timezone():
    with _with_tz("America/New_York"):
        tz = sat._resolve_display_tz("u1")
    assert str(tz) == "America/New_York"


def test_resolve_display_tz_falls_back_to_utc_when_unset():
    with _with_tz(None):
        assert sat._resolve_display_tz("u1") is timezone.utc


def test_resolve_display_tz_falls_back_to_utc_on_invalid():
    with _with_tz("Not/AValidZone"):
        assert sat._resolve_display_tz("u1") is timezone.utc


def test_resolve_display_tz_falls_back_to_utc_when_lookup_raises():
    # A transient Firestore/network error reading the user's timezone must not crash the search.
    def _boom(uid):
        raise RuntimeError("firestore unavailable")

    with patch.object(sat.notification_db, "get_user_time_zone", _boom):
        assert sat._resolve_display_tz("u1") is timezone.utc


def test_search_tool_renders_in_resolved_timezone():
    source = SOURCE.read_text(encoding="utf-8")
    func = source[source.index("def search_screen_activity_tool") :]
    assert "_resolve_display_tz(uid)" in func
    assert "datetime.fromtimestamp(ts, tz=display_tz)" in func
    # The naive form (no tzinfo) must be gone.
    assert "datetime.fromtimestamp(ts).strftime" not in func
