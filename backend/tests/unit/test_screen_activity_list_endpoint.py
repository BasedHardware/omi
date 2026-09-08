"""GET /v1/screen-activity lists the user's captured screen-activity rows.

The desktop app writes these rows but they were only ever read back internally (MCP). This
exposes them to the user's own first-party client, converting an optional YYYY-MM-DD date into
a single-day range and rejecting a bad date with 422.

Test isolation: routers.focus_sessions imports cleanly, so the test imports it normally,
patches the import-cheap screen_activity_db helper with monkeypatch.setattr, and calls the
handler directly.
"""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from datetime import datetime  # noqa: E402

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from routers import focus_sessions as fs_mod  # noqa: E402


def test_list_screen_activity_no_date_passes_none(monkeypatch):
    captured = {}

    def fake(uid, start_date=None, end_date=None, app_filter=None, limit=500):
        captured.update(uid=uid, start=start_date, end=end_date, app=app_filter, limit=limit)
        return [{'id': 'a', 'appName': 'Code'}]

    monkeypatch.setattr(fs_mod.screen_activity_db, 'get_screen_activity', fake)
    result = fs_mod.list_screen_activity(date=None, app_filter=None, limit=500, uid='u1')
    assert result == [{'id': 'a', 'appName': 'Code'}]
    assert captured == {'uid': 'u1', 'start': None, 'end': None, 'app': None, 'limit': 500}


def test_list_screen_activity_date_becomes_single_day_range(monkeypatch):
    captured = {}

    def fake(uid, start_date=None, end_date=None, app_filter=None, limit=500):
        captured.update(start=start_date, end=end_date, app=app_filter, limit=limit)
        return []

    monkeypatch.setattr(fs_mod.screen_activity_db, 'get_screen_activity', fake)
    fs_mod.list_screen_activity(date='2026-07-03', app_filter='Code', limit=100, uid='u1')
    assert captured['start'] == datetime(2026, 7, 3)
    # inclusive same-day end (23:59:59), not next-day midnight
    assert captured['end'] == datetime(2026, 7, 3, 23, 59, 59)
    assert captured['app'] == 'Code'
    assert captured['limit'] == 100


class _RecordingFirestore:
    """Minimal Firestore stand-in that records the range filters a query applies."""

    def __init__(self, filters):
        self._filters = filters

    def collection(self, *a, **k):
        return self

    def document(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def where(self, filter=None, **k):
        self._filters.append((filter.field_path, filter.op_string, filter.value))
        return self

    def limit(self, *a, **k):
        return self

    def stream(self):
        return iter(())


def test_single_day_query_applies_exact_day_firestore_boundaries(monkeypatch):
    # Exercise the real get_screen_activity so this covers the actual Firestore boundary
    # strings, not just the router's end datetime.
    filters = []
    monkeypatch.setattr(fs_mod.screen_activity_db, 'db', _RecordingFirestore(filters))
    fs_mod.list_screen_activity(date='2026-07-03', app_filter=None, limit=500, uid='u1')

    ts_bounds = {op: val for (field, op, val) in filters if field == 'timestamp'}
    assert ts_bounds['>='] == '2026-07-03 00:00:00.000'
    # inclusive same-day end; must not reach 2026-07-04
    assert ts_bounds['<='] == '2026-07-03 23:59:59.999'


def test_list_screen_activity_bad_date_returns_422(monkeypatch):
    monkeypatch.setattr(fs_mod.screen_activity_db, 'get_screen_activity', lambda *a, **k: [])
    with pytest.raises(HTTPException) as ei:
        fs_mod.list_screen_activity(date='2026-13-99', app_filter=None, limit=500, uid='u1')
    assert ei.value.status_code == 422
