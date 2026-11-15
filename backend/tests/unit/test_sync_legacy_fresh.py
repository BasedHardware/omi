"""Capture provenance still gates fresh capacity after optional promotion retires.

Keep this canonical guard path used by the failure-class registry. Recent
unbound uploads stay in backfill; server-bound captures retain fresh routing.
"""

import pytest

from utils.sync import lanes


@pytest.fixture
def clock(monkeypatch):
    monkeypatch.setattr(lanes, 'parse_sync_filename_timestamp', lambda name: float(name))
    monkeypatch.setenv('SYNC_FRESH_MAX_AGE_SECONDS', '21600')
    monkeypatch.setenv('SYNC_BACKFILL_MAX_AGE_SECONDS', '2592000')
    monkeypatch.delenv('SYNC_CAPTURE_MAX_FUTURE_SKEW_SECONDS', raising=False)
    return 2_000_000_000


def decide(clock, ages, device=None):
    return lanes.classify_sync_lane([str(clock - age) for age in ages], client_device_id=device, now=clock)


@pytest.mark.parametrize('age', [60, 21600])
def test_recent_unbound_capture_stays_in_backfill(clock, age):
    decision = decide(clock, [age])
    assert decision.lane is lanes.SyncLane.BACKFILL
    assert decision.trust is lanes.CaptureTimeTrust.LEGACY
    assert decision.reason == 'unbound_capture_time'


@pytest.mark.parametrize(
    'ages,reason',
    [
        ([21600.01], 'unbound_capture_time'),
        ([60, 21601], 'unbound_capture_time'),
        ([-601], 'future_capture_time'),
        ([31 * 86400], 'lookback_exceeded'),
        ([], 'missing_capture_time'),
    ],
)
def test_time_guards_survive_retirement(clock, ages, reason):
    decision = decide(clock, ages)
    assert decision.lane is lanes.SyncLane.BACKFILL
    assert decision.reason == reason
    if reason == 'lookback_exceeded':
        assert not decision.automatic_recovery_allowed


@pytest.mark.parametrize('age', [60, 21600, -170])
def test_device_bound_fresh_capture_preserves_provenance(clock, age):
    decision = decide(clock, [age], device='ios_12345678')
    assert decision.lane is lanes.SyncLane.FRESH
    assert decision.trust is lanes.CaptureTimeTrust.DEVICE_BOUND
    assert decision.reason == 'recent_capture'
    assert decision.newest_capture_at <= clock


def test_invalid_time_stays_untrusted(clock):
    decision = lanes.classify_sync_lane(['invalid'], client_device_id=None, now=clock)
    assert decision.trust is lanes.CaptureTimeTrust.UNTRUSTED
    assert decision.reason == 'invalid_capture_time'
