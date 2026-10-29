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
    # Two prior hours at ~5/h; the mean divides by the hour span since the
    # class first appeared, not by the number of observed buckets.
    for offset, ts in ((2, '2026-10-29T09:10:00Z'), (1, '2026-10-29T10:10:00Z')):
        evaluate_window(
            [entry('ERROR routers.x: boom for 42', ts=ts) for _ in range(5)],
            now_epoch=now - offset * hour,
            client=client,
        )
    result = evaluate_window(error_entries(60), now_epoch=now, client=client)
    assert len(result['fired']) == 1
    assert result['fired'][0]['disposition'] == 'surge'
    assert result['fired'][0]['baseline_mean'] == 5.0  # 5 in the one elapsed hour before the window


def test_new_class_below_threshold_alerts_when_it_crosses(client):
    now = int(datetime(2026, 10, 29, 4, 0, tzinfo=timezone.utc).timestamp())
    below = evaluate_window(error_entries(19), now_epoch=now, client=client)
    assert below['fired'] == []
    # The record exists now, but there is still no baseline before the new
    # window, so crossing the new-class threshold on a later sweep fires.
    crossed = evaluate_window(error_entries(22, ts='2026-10-29T04:30:00Z'), now_epoch=now + 1800, client=client)
    assert len(crossed['fired']) == 1
    assert crossed['fired'][0]['disposition'] == 'new'


def test_once_active_class_decays_to_a_span_baseline(client):
    hour = 3600
    now = int(datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc).timestamp())
    # One quiet hour (19/h, below the new threshold so no dedupe key is set) a
    # hundred hours ago, silent since: the span mean is ~0.2/h, so 50/h is a 5x
    # surge rather than a comparison against the one observed bucket.
    evaluate_window(
        [entry('ERROR routers.x: boom for 42', ts='2026-10-28T02:10:00Z') for _ in range(19)],
        now_epoch=now - 100 * hour,
        client=client,
    )
    result = evaluate_window(error_entries(50), now_epoch=now, client=client)
    assert len(result['fired']) == 1
    assert result['fired'][0]['disposition'] == 'surge'
    assert result['fired'][0]['baseline_mean'] < 1.0


def test_idle_class_returns_as_new_after_a_week(client):
    hour = 3600
    now = int(datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc).timestamp())
    evaluate_window(
        [entry('ERROR routers.x: boom for 42', ts='2026-10-21T02:10:00Z') for _ in range(19)],
        now_epoch=now - 200 * hour,
        client=client,
    )
    # Buckets older than the 7-day window age out, leaving no baseline.
    result = evaluate_window(error_entries(30), now_epoch=now, client=client)
    assert len(result['fired']) == 1
    assert result['fired'][0]['disposition'] == 'new'


def test_warning_exception_uses_doubled_thresholds(client):
    text = 'WARNING routers.y: bad thing\nValueError: nope'
    now = int(datetime(2026, 10, 29, 4, 0, tzinfo=timezone.utc).timestamp())
    below = evaluate_window([entry(text) for _ in range(30)], now_epoch=now, client=client)
    assert below['fired'] == []
    fires = evaluate_window([entry(text) for _ in range(45)], now_epoch=now, client=client)
    assert len(fires['fired']) == 1


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


def test_baseline_drops_buckets_older_than_seven_days(client):
    import json as _json

    now = 1_800_000_000
    # A stored record carrying a 200h-old bucket (from a long-ago window).
    client.hset(
        baseline_db.BASELINE_KEY,
        'f',
        _json.dumps({'first_seen': now - 200 * 3600, 'buckets': {str(now // 3600 - 200): 9}}),
    )
    recent = baseline_db.record_window(
        client,
        fingerprint='f',
        label='l',
        level='ERROR',
        window_buckets={now // 3600 - 5: 3},
        now_epoch=now,
    )
    # The 200h-old bucket ages out; only the in-window bucket survives.
    assert recent['buckets'] == {str(now // 3600 - 5): 3}


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


def test_logging_read_uses_dedicated_impersonated_sa(monkeypatch):
    # backend-runtime must not hold logging.read itself (David, 2026-10-29):
    # the default-session path has to impersonate omi-errclass-sentinel.
    captured = {}

    class _Creds:
        def __init__(self, source_credentials, target_principal, target_scopes):
            captured['principal'] = target_principal
            captured['scopes'] = target_scopes
            captured['source'] = source_credentials

    import google.auth as _gauth

    monkeypatch.setattr(_gauth, 'default', lambda *a, **k: (_Creds('src', 'x', ['y']), None))
    monkeypatch.setattr('google.auth.impersonated_credentials.Credentials', _Creds)
    session = sentinel.logging_session()
    assert captured['principal'] == sentinel.LOGGING_SA
    assert sentinel.LOGGING_SA == 'omi-errclass-sentinel@based-hardware.iam.gserviceaccount.com'
    assert captured['scopes'] == [sentinel.LOGGING_READ_SCOPE]
    assert session is not None


def test_read_log_entries_fails_closed_when_impersonation_unavailable(monkeypatch):
    def _boom():
        raise RuntimeError('no adc')

    monkeypatch.setattr(sentinel, 'logging_session', _boom)
    out = sentinel.read_log_entries(
        start=datetime(2026, 10, 29, 3, 0, tzinfo=timezone.utc),
        end=datetime(2026, 10, 29, 4, 0, tzinfo=timezone.utc),
    )
    assert out == {'entries': [], 'truncated': False, 'errors': 1, 'status': 403}


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
