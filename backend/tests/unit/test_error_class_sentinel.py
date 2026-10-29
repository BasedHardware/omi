"""Error-class sentinel: detection math, baseline merge, and fail-closed ticks."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import fakeredis
import pytest

import services.error_class_sentinel as sentinel
from database import error_class_baseline as baseline_db
from services.error_class_sentinel import evaluate_window, window_bounds


def entry(text, *, service='backend-sync', ts='2026-10-29T03:00:00Z'):
    return {
        'textPayload': text,
        'timestamp': ts,
        'resource': {'type': 'cloud_run_revision', 'labels': {'service_name': service}},
        'logName': 'projects/based-hardware/logs/stderr',
    }


def error_entries(count, text='ERROR routers.x: boom for 42', service='backend-sync', ts='2026-10-29T11:00:00Z'):
    return [entry(text, service=service, ts=ts) for _ in range(count)]


@pytest.fixture()
def client():
    return fakeredis.FakeRedis()


def test_new_error_class_fires_at_threshold(client):
    now = int(datetime(2026, 10, 29, 4, 0, tzinfo=timezone.utc).timestamp())
    result = evaluate_window(error_entries(25), now_epoch=now, client=client)
    assert result['classes'] == 1
    assert len(result['fired']) == 1
    fired = result['fired'][0]
    assert fired['disposition'] == 'new' and fired['count'] == 25


def test_below_new_threshold_does_not_fire(client):
    now = int(datetime(2026, 10, 29, 4, 0, tzinfo=timezone.utc).timestamp())
    result = evaluate_window(error_entries(19), now_epoch=now, client=client)
    assert result['fired'] == []


def test_surging_class_fires_against_baseline(client):
    hour = 3600
    now = int(datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc).timestamp())
    # Two prior hours at ~5/h establish the baseline mean.
    for offset, ts in ((2, '2026-10-29T09:10:00Z'), (1, '2026-10-29T10:10:00Z')):
        evaluate_window(
            [entry('ERROR routers.x: boom for 42', ts=ts) for _ in range(5)],
            now_epoch=now - offset * hour,
            client=client,
        )
    result = evaluate_window(error_entries(60), now_epoch=now, client=client)
    assert len(result['fired']) == 1
    assert result['fired'][0]['disposition'] == 'surge'
    assert result['fired'][0]['baseline_mean'] == 5.0


def test_warning_level_needs_doubled_thresholds(client):
    now = int(datetime(2026, 10, 29, 4, 0, tzinfo=timezone.utc).timestamp())
    result = evaluate_window(
        [entry('WARNING routers.x: storm line 7') for _ in range(30)], now_epoch=now, client=client
    )
    assert result['fired'] == []
    result = evaluate_window(
        [entry('WARNING routers.x: storm line 7') for _ in range(45)], now_epoch=now, client=client
    )
    assert len(result['fired']) == 1


def test_info_level_never_fires(client):
    now = int(datetime(2026, 10, 29, 4, 0, tzinfo=timezone.utc).timestamp())
    result = evaluate_window(
        [entry('INFO config.policy: event=tick') for _ in range(500)], now_epoch=now, client=client
    )
    assert result['fired'] == []


def test_alert_dedupe_suppresses_refire_within_ttl(client):
    now = int(datetime(2026, 10, 29, 4, 0, tzinfo=timezone.utc).timestamp())
    first = evaluate_window(error_entries(30), now_epoch=now, client=client)
    assert len(first['fired']) == 1
    # 200/h is a valid surge against the 30/h baseline; only the 6h dedupe
    # entry keeps it from firing again fifteen minutes later.
    again = evaluate_window(error_entries(200), now_epoch=now + 900, client=client)
    assert again['fired'] == []


def test_baseline_keeps_only_seven_days_of_buckets(client):
    now = 1_800_000_000
    for step in range(170):
        baseline_db.record_window(
            client,
            fingerprint='f',
            label='l',
            level='ERROR',
            window_buckets={now // 3600 - step: 3},
            now_epoch=now - step * 3600,
        )
    record = baseline_db.record_window(
        client, fingerprint='f', label='l', level='ERROR', window_buckets={now // 3600: 1}, now_epoch=now
    )
    assert len(record['buckets']) == baseline_db.KEEP_BUCKETS


def test_window_bounds_skip_the_view_lag():
    now = datetime(2026, 10, 29, 4, 0, tzinfo=timezone.utc)
    start, end = window_bounds(now)
    assert end == now - timedelta(minutes=20)
    assert start == end - timedelta(hours=1)


class _FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code

    def json(self):
        return {}


class _FailingSession:
    def __init__(self, status):
        self.status = status
        self.calls = 0

    def post(self, *_args, **_kwargs):
        self.calls += 1
        return _FakeResponse(self.status)


def test_tick_fails_closed_on_permission_denied(client):
    summary = sentinel._tick(
        client_factory=lambda: client,
        session_factory=lambda: _FailingSession(403),
        now=datetime(2026, 10, 29, 4, 0, tzinfo=timezone.utc),
    )
    assert summary['outcome'] == 'permission_denied'
    assert 'fired' not in summary


def test_tick_fails_closed_on_truncation(monkeypatch, client):
    def truncated_read(**_kwargs):
        return {'entries': error_entries(3), 'truncated': True, 'errors': 0, 'status': 200}

    monkeypatch.setattr(sentinel, 'read_log_entries', lambda **kwargs: truncated_read())
    summary = sentinel._tick(
        client_factory=lambda: client,
        session_factory=lambda: None,
        now=datetime(2026, 10, 29, 4, 0, tzinfo=timezone.utc),
    )
    assert summary['outcome'] == 'truncated'
    assert 'fired' not in summary


def test_tick_ok_path_reports_classes_and_fires(monkeypatch, client):
    def ok_read(**_kwargs):
        return {'entries': error_entries(22), 'truncated': False, 'errors': 0, 'status': 200}

    monkeypatch.setattr(sentinel, 'read_log_entries', lambda **kwargs: ok_read())
    summary = sentinel._tick(
        client_factory=lambda: client,
        session_factory=lambda: None,
        now=datetime(2026, 10, 29, 4, 0, tzinfo=timezone.utc),
    )
    assert summary['outcome'] == 'ok'
    assert summary['fired'] == 1 and summary['classes'] == 1


def test_log_filter_scopes_fleet_and_splits_warning_pass():
    now = datetime(2026, 10, 29, 4, 0, tzinfo=timezone.utc)
    start, end = window_bounds(now)
    base = sentinel.log_filter(start, end)
    assert 'severity>=ERROR' in base and 'prod-omi-gke' in base
    assert 'backend-sync-backfill' in base and 'backend-listen' in base
    warning = sentinel.log_filter(start, end, sentinel.ONLY_WARNING)
    quiet = sentinel.log_filter(start, end, sentinel.EXCL_CHATTY)
    assert 'textPayload=~"^WARNING"' in warning
    assert 'NOT textPayload=~"^(WARNING|INFO|DEBUG)"' in quiet
