"""Regression test: a midnight (hour 0) daily-summary time must not be reported as 10 PM.

utils.retrieval.tools.notification_settings_tools.manage_daily_summary_tool built the current
hour with `get_daily_summary_hour_local(uid) or 22`. Hour 0 (midnight) is a valid setting
(set_daily_summary_hour_local accepts 0 <= h <= 23), but `0 or 22` evaluates to 22, so a user who
set midnight was told 10:00 PM on both enable and get_settings. The hour is now taken as-is unless
the getter returns None (unset).
"""

import utils.retrieval.tools.notification_settings_tools as mod


def _call(monkeypatch, action, stored_hour, enabled=True):
    monkeypatch.setattr(mod.notification_db, 'get_daily_summary_hour_local', lambda uid: stored_hour)
    monkeypatch.setattr(mod.notification_db, 'get_daily_summary_enabled', lambda uid: enabled)
    monkeypatch.setattr(mod.notification_db, 'set_daily_summary_enabled', lambda uid, v: None)
    return mod.manage_daily_summary_tool.func(action=action, config={'configurable': {'user_id': 'u1'}})


def test_get_settings_reports_midnight(monkeypatch):
    result = _call(monkeypatch, 'get_settings', 0)
    assert 'midnight' in result
    assert '10:00 PM' not in result


def test_enable_reports_midnight(monkeypatch):
    result = _call(monkeypatch, 'enable', 0)
    assert 'midnight' in result


def test_unset_hour_defaults_to_22(monkeypatch):
    result = _call(monkeypatch, 'get_settings', None)
    assert '10:00 PM' in result  # None -> unset -> default 22 -> "10:00 PM"
