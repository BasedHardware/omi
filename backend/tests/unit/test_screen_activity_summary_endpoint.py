"""GET /v1/screen-activity/summary returns the user's aggregated per-app screen-activity.

The desktop app captures screen-activity rows but they were only ever read back internally
(MCP); this exposes the aggregated summary (per-app counts, first/last seen) to the user's own
first-party client, converting an optional YYYY-MM-DD date into a single-day range and rejecting
a bad date with 422.

Test isolation: routers.focus_sessions imports cleanly, so the test imports it normally,
patches the import-cheap screen_activity_db helper with monkeypatch.setattr, and calls the
handler directly.
"""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from datetime import datetime  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import pytest  # noqa: E402
from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from routers import focus_sessions as fs_mod  # noqa: E402


def test_summary_no_date_passes_none(monkeypatch):
    captured = {}

    def fake(uid, start_date=None, end_date=None):
        captured.update(uid=uid, start=start_date, end=end_date)
        return {'apps': {'Code': {'count': 3}}, 'total_screenshots': 3}

    monkeypatch.setattr(fs_mod.screen_activity_db, 'get_screen_activity_summary', fake)
    result = fs_mod.screen_activity_summary(date=None, uid='u1')
    assert result == {'apps': {'Code': {'count': 3}}, 'total_screenshots': 3}
    assert captured == {'uid': 'u1', 'start': None, 'end': None}


def test_summary_date_becomes_single_day_range(monkeypatch):
    captured = {}

    def fake(uid, start_date=None, end_date=None):
        captured.update(start=start_date, end=end_date)
        return {'apps': {}, 'total_screenshots': 0}

    monkeypatch.setattr(fs_mod.screen_activity_db, 'get_screen_activity_summary', fake)
    fs_mod.screen_activity_summary(date='2026-07-03', uid='u1')
    assert captured['start'] == datetime(2026, 7, 3)
    # inclusive same-day end (23:59:59), not next-day midnight
    assert captured['end'] == datetime(2026, 7, 3, 23, 59, 59)


def test_summary_bad_date_returns_422(monkeypatch):
    monkeypatch.setattr(fs_mod.screen_activity_db, 'get_screen_activity_summary', lambda *a, **k: {})
    with pytest.raises(HTTPException) as ei:
        fs_mod.screen_activity_summary(date='2026-02-30', uid='u1')
    assert ei.value.status_code == 422


class _RecordingFirestore:
    """Minimal Firestore stand-in that records the range filters a query applies."""

    def __init__(self, filters, rows=()):
        self._filters = filters
        self.rows = rows
        self.requested_limit = None
        self.collection_names = []

    def collection(self, *a, **k):
        self.collection_names.append(a[0])
        return self

    def document(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def where(self, filter=None, **k):
        self._filters.append((filter.field_path, filter.op_string, filter.value))
        return self

    def limit(self, count):
        self.requested_limit = count
        return self

    def stream(self):
        return iter(
            SimpleNamespace(id=str(index), to_dict=lambda row=row: dict(row))
            for index, row in enumerate(self.rows[: self.requested_limit])
        )


def test_summary_single_day_applies_exact_day_firestore_boundaries(monkeypatch):
    # Exercise the real get_screen_activity_summary so this covers the actual Firestore
    # boundary strings, not just the router's end datetime.
    filters = []
    monkeypatch.setattr(fs_mod.screen_activity_db, 'db', _RecordingFirestore(filters))
    fs_mod.screen_activity_summary(date='2026-07-03', uid='u1')

    ts_bounds = {op: val for (field, op, val) in filters if field == 'timestamp'}
    assert ts_bounds['>='] == '2026-07-03 00:00:00.000'
    # inclusive same-day end; must not reach 2026-07-04
    assert ts_bounds['<='] == '2026-07-03 23:59:59.999'


@pytest.mark.parametrize('row_count', [0, 2, 5000, 5001])
def test_summary_http_preserves_sample_coverage_and_excludes_lookahead(monkeypatch, row_count):
    # Synthetic uneven observations: neither row counts nor first/last bounds measure usage.
    rows = [
        {'appName': 'Editor', 'timestamp': '2026-07-03 01:00:00.000', 'windowTitle': 'Example'}
        for _ in range(min(row_count, 5000))
    ]
    if rows:
        rows[-1]['timestamp'] = '2026-07-03 12:00:00.000'
    if row_count > 5000:
        rows.append({'appName': 'Later app', 'timestamp': '2026-07-03 23:00:00.000'})
    client_db = _RecordingFirestore([], rows)
    monkeypatch.setattr(fs_mod.screen_activity_db, 'db', client_db)
    app = FastAPI()
    app.include_router(fs_mod.router)
    app.dependency_overrides[fs_mod.auth.get_current_user_uid] = lambda: 'synthetic-user'
    with TestClient(app) as client:
        response = client.get('/v1/screen-activity/summary?date=2026-07-03')
    assert response.status_code == 200
    result = response.json()
    assert result['total_screenshots'] == min(row_count, 5000)
    assert result['coverage'] == {
        'source': 'synced_screen_activity',
        'row_limit': 5000,
        'truncated': row_count > 5000,
        'first_observed_at': '2026-07-03 01:00:00.000' if rows else None,
        'last_observed_at': '2026-07-03 12:00:00.000' if rows else None,
        'capture_completeness': 'unknown',
    }
    assert client_db.requested_limit == 5001
    assert client_db.collection_names == ['users', 'screen_activity']
    assert 'Later app' not in result['apps']
    assert sum(app['count'] for app in result['apps'].values()) == min(row_count, 5000)
