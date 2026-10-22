"""Tests verifying parameter guards, coercion, and config handling in notification_settings_tools.py.

Ensures that:
1. Non-string or None actions return clean user-facing error messages instead of raising AttributeError.
2. String hour values (e.g. "22", "9") from LLM tool arguments are safely coerced to int without raising TypeError.
3. Out-of-bounds or invalid hour formats return clear errors.
4. Top-level config fallbacks for user_id/uid resolve properly when 'configurable' wrapper is absent.
"""

import importlib.util
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def _pkg(name: str):
    mod = sys.modules.get(name)
    if mod is None or not hasattr(mod, "__path__"):
        mod = types.ModuleType(name)
        mod.__path__ = []
        sys.modules[name] = mod
    return mod


def _mod(name: str):
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return mod


def _load(module_name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(module_name, str(BACKEND_DIR / rel_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _tool_decorator(fn=None, **kwargs):
    if fn is not None and callable(fn):
        fn.func = fn
        return fn

    def dec(func):
        func.func = func
        return func

    return dec


# Ensure dependencies are stubbed for isolated unit execution
_pkg("langchain_core")
_lc_tools = _mod("langchain_core.tools")
if not hasattr(_lc_tools, "tool"):
    _lc_tools.tool = _tool_decorator

_lc_runnables = _mod("langchain_core.runnables")
if not hasattr(_lc_runnables, "RunnableConfig"):
    _lc_runnables.RunnableConfig = dict

_pkg("database")
_mock_notif_db = _mod("database.notifications")
_mock_notif_db.get_daily_summary_enabled = MagicMock(return_value=True)
_mock_notif_db.get_daily_summary_hour_local = MagicMock(return_value=22)
_mock_notif_db.set_daily_summary_enabled = MagicMock()
_mock_notif_db.set_daily_summary_hour_local = MagicMock()

nst = _load(
    "utils.retrieval.tools._notification_settings_tools_test",
    "utils/retrieval/tools/notification_settings_tools.py",
)


def test_safe_int_coercion():
    assert nst._safe_int(10) == 10
    assert nst._safe_int("22") == 22
    assert nst._safe_int("  8  ") == 8
    assert nst._safe_int(None) is None
    assert nst._safe_int(True) is None
    assert nst._safe_int(False) is None
    assert nst._safe_int("invalid") is None
    assert nst._safe_int([]) is None
    assert nst._safe_int({}) is None


def test_format_hour():
    assert nst._format_hour(0) == "12:00 AM (midnight)"
    assert nst._format_hour(12) == "12:00 PM (noon)"
    assert nst._format_hour(8) == "8:00 AM"
    assert nst._format_hour(21) == "9:00 PM"


def test_action_none_or_invalid_returns_clean_error():
    # None or non-string actions must return a clean error without raising AttributeError
    res_none = nst.manage_daily_summary_tool.func(action=None, config={"configurable": {"user_id": "u1"}})
    assert "Unknown action: None" in res_none

    res_int = nst.manage_daily_summary_tool.func(action=123, config={"configurable": {"user_id": "u1"}})
    assert "Unknown action: 123" in res_int

    res_unknown = nst.manage_daily_summary_tool.func(action="not_real", config={"configurable": {"user_id": "u1"}})
    assert "Unknown action: not_real" in res_unknown


def test_string_hour_coercion_and_bounds():
    _mock_notif_db.get_daily_summary_enabled.return_value = True

    # Numeric string "21" must coerce cleanly to 21 without raising TypeError
    res_str = nst.manage_daily_summary_tool.func(
        action="set_time", hour="21", config={"configurable": {"user_id": "u1"}}
    )
    assert "9:00 PM" in res_str
    _mock_notif_db.set_daily_summary_hour_local.assert_called_with("u1", 21)

    # Invalid hour string must return helpful error
    res_invalid = nst.manage_daily_summary_tool.func(
        action="set_time", hour="noon", config={"configurable": {"user_id": "u1"}}
    )
    assert "Hour must be a valid integer between 0 and 23" in res_invalid

    # Out of bounds hour
    res_oob = nst.manage_daily_summary_tool.func(
        action="set_time", hour=25, config={"configurable": {"user_id": "u1"}}
    )
    assert "Hour must be between 0 and 23. You provided 25." in res_oob


def test_top_level_config_uid_resolution():
    _mock_notif_db.get_daily_summary_enabled.return_value = True
    _mock_notif_db.get_daily_summary_hour_local.return_value = 22

    # user_id placed at top-level of config instead of nested in configurable
    res_top_uid = nst.manage_daily_summary_tool.func(action="get_settings", config={"user_id": "u123"})
    assert "Daily summary is enabled" in res_top_uid

    # uid placed at top-level
    res_top_uid2 = nst.manage_daily_summary_tool.func(action="get_settings", config={"uid": "u456"})
    assert "Daily summary is enabled" in res_top_uid2

    # Missing config entirely
    res_no_cfg = nst.manage_daily_summary_tool.func(action="get_settings", config={})
    assert res_no_cfg == "Error: User ID not found"
