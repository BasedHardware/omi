"""Legacy promotion preserves provenance and closes safely on budget failures."""

import hashlib

from unittest.mock import MagicMock
from concurrent.futures import ThreadPoolExecutor

import fakeredis

import pytest

from utils.sync import lanes, legacy_fresh


@pytest.fixture
def clock(monkeypatch):
    monkeypatch.setattr(lanes, 'parse_sync_filename_timestamp', lambda name: float(name))
    monkeypatch.setenv('SYNC_FRESH_MAX_AGE_SECONDS', '21600')
    monkeypatch.setenv('SYNC_BACKFILL_MAX_AGE_SECONDS', '2592000')
    monkeypatch.delenv('SYNC_CAPTURE_MAX_FUTURE_SKEW_SECONDS', raising=False)
    monkeypatch.delenv('SYNC_LEGACY_FRESH_ENABLED', raising=False)
    monkeypatch.delenv('SYNC_LEGACY_FRESH_UID_ALLOWLIST', raising=False)
    monkeypatch.setenv('SYNC_LEGACY_FRESH_PERCENT', '100')
    monkeypatch.delenv('SYNC_LEGACY_FRESH_HOURLY_TOKENS', raising=False)
    monkeypatch.delenv('SYNC_LEGACY_FRESH_BURST_TOKENS', raising=False)
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    return 2_000_000_000


def decide(clock, ages, enabled=True, device=None):
    return lanes.classify_sync_lane(
        [str(clock - age) for age in ages], client_device_id=device, now=clock, allow_legacy_fresh=enabled
    )


def test_default_off_and_explicit_flag(clock, monkeypatch):
    assert not legacy_fresh.enabled_for('synthetic')
    assert decide(clock, [60], enabled=False).reason == 'unbound_capture_time'
    monkeypatch.setenv('SYNC_LEGACY_FRESH_ENABLED', 'true')
    assert legacy_fresh.enabled_for('synthetic')
    promoted = decide(clock, [21600])
    assert promoted.lane == lanes.SyncLane.FRESH
    assert promoted.trust == lanes.CaptureTimeTrust.LEGACY
    assert promoted.reason == 'recent_legacy_capture'


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
def test_time_guards_survive_promotion(clock, ages, reason):
    decision = decide(clock, ages)
    assert decision.lane == lanes.SyncLane.BACKFILL
    assert decision.reason == reason
    if reason == 'lookback_exceeded':
        assert not decision.automatic_recovery_allowed


def test_within_tolerance_future_skew_is_not_punished(clock):
    """A phone clock ≤ SYNC_CAPTURE_MAX_FUTURE_SKEW_SECONDS ahead stays admissible."""
    decision = decide(clock, [-170])
    assert decision.lane is lanes.SyncLane.FRESH
    assert decision.reason == 'recent_legacy_capture'
    assert decision.newest_capture_at <= clock


def test_invalid_time_stays_untrusted(clock):
    decision = lanes.classify_sync_lane(['invalid'], client_device_id=None, now=clock, allow_legacy_fresh=True)
    assert decision.trust == lanes.CaptureTimeTrust.UNTRUSTED
    assert decision.reason == 'invalid_capture_time'


@pytest.mark.parametrize('sizes,cost', [([1], 1), ([0, 0], 1), ([legacy_fresh.MIB, 1], 2)])
def test_charge_uses_actual_total_bytes_with_minimum_one_upload(clock, monkeypatch, sizes, cost):
    redis = MagicMock()
    redis.eval.return_value = 1
    monkeypatch.setattr(legacy_fresh, 'redis_client', redis)
    decision = decide(clock, [60])
    assert legacy_fresh.admit('synthetic', decision, sizes) == decision
    assert redis.eval.call_args.args[2:] == ('sync_legacy_fresh:budget:synthetic', 10, 60, cost)


@pytest.mark.parametrize('sizes', [[None], [], [-1], [11 * legacy_fresh.MIB]])
def test_unmeasured_or_large_upload_demotes_without_redis(clock, monkeypatch, sizes):
    redis = MagicMock()
    monkeypatch.setattr(legacy_fresh, 'redis_client', redis)
    assert legacy_fresh.admit('synthetic', decide(clock, [60]), sizes).lane == lanes.SyncLane.BACKFILL
    redis.eval.assert_not_called()


@pytest.mark.parametrize(
    'reply,reason', [(0, 'legacy_fresh_budget_exceeded'), (None, 'legacy_fresh_budget_unavailable')]
)
def test_rejection_or_malformed_store_reply_demotes(clock, monkeypatch, reply, reason):
    redis = MagicMock()
    redis.eval.return_value = reply
    monkeypatch.setattr(legacy_fresh, 'redis_client', redis)
    decision = legacy_fresh.admit('synthetic', decide(clock, [60]), [100])
    assert decision.lane == lanes.SyncLane.BACKFILL
    assert decision.trust == lanes.CaptureTimeTrust.LEGACY
    assert decision.reason == reason


def test_store_outage_demotes_and_does_not_log_identity(clock, monkeypatch, caplog):
    redis = MagicMock()
    redis.eval.side_effect = ConnectionError('private details')
    monkeypatch.setattr(legacy_fresh, 'redis_client', redis)
    decision = legacy_fresh.admit('synthetic-private-user', decide(clock, [60]), [1])
    assert decision.reason == 'legacy_fresh_budget_unavailable'
    assert 'synthetic-private-user' not in caplog.text
    assert 'private details' not in caplog.text


@pytest.mark.parametrize('hourly,burst', [('0', '10'), ('60', '0'), ('121', '10'), ('60', '61'), ('invalid', '10')])
def test_bad_configuration_closes_promotion(clock, monkeypatch, hourly, burst):
    monkeypatch.setenv('SYNC_LEGACY_FRESH_HOURLY_TOKENS', hourly)
    monkeypatch.setenv('SYNC_LEGACY_FRESH_BURST_TOKENS', burst)
    redis = MagicMock()
    monkeypatch.setattr(legacy_fresh, 'redis_client', redis)
    assert legacy_fresh.admit('synthetic', decide(clock, [60]), [1]).lane == lanes.SyncLane.BACKFILL
    redis.eval.assert_not_called()


def test_device_bound_and_historical_decisions_do_not_consume_legacy_budget(clock, monkeypatch):
    redis = MagicMock()
    monkeypatch.setattr(legacy_fresh, 'redis_client', redis)
    for decision in (decide(clock, [60], device='ios_12345678'), decide(clock, [21601])):
        assert legacy_fresh.admit('synthetic', decision, [1]) == decision
    redis.eval.assert_not_called()


def test_budget_keys_are_stage_isolated(clock, monkeypatch):
    redis = MagicMock()
    redis.eval.return_value = 1
    monkeypatch.setattr(legacy_fresh, 'redis_client', redis)
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    legacy_fresh.admit('synthetic', decide(clock, [60]), [1])
    assert redis.eval.call_args.args[2] != 'sync_legacy_fresh:budget:synthetic'


def test_atomic_lua_parallel_reservations_and_uid_isolation(clock, monkeypatch):
    redis = fakeredis.FakeRedis()
    monkeypatch.setattr(legacy_fresh, 'redis_client', redis)
    decision = decide(clock, [60])
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda _: legacy_fresh.admit('synthetic', decision, [1]), range(40)))
    assert sum(d.lane == lanes.SyncLane.FRESH for d in results) == 10
    assert legacy_fresh.admit('other-synthetic', decision, [1]).lane == lanes.SyncLane.FRESH
    assert redis.ttl('sync_legacy_fresh:budget:synthetic') > 0


def test_lua_refill_and_weighted_exhaustion(clock, monkeypatch):
    redis = fakeredis.FakeRedis()
    monkeypatch.setattr(legacy_fresh, 'redis_client', redis)
    decision = decide(clock, [60])
    assert legacy_fresh.admit('synthetic', decision, [9 * legacy_fresh.MIB]).lane == lanes.SyncLane.FRESH
    assert legacy_fresh.admit('synthetic', decision, [2 * legacy_fresh.MIB]).reason == 'legacy_fresh_budget_exceeded'
    # Advance the stored server clock by one refill minute; no wall-clock wait.
    key = 'sync_legacy_fresh:budget:synthetic'
    redis.hset(key, 'updated', float(redis.hget(key, 'updated')) - 60)
    assert legacy_fresh.admit('synthetic', decision, [2 * legacy_fresh.MIB]).lane == lanes.SyncLane.FRESH


def test_slow_refill_expiry_cannot_reset_budget_early(clock, monkeypatch):
    redis = fakeredis.FakeRedis()
    monkeypatch.setattr(legacy_fresh, 'redis_client', redis)
    monkeypatch.setenv('SYNC_LEGACY_FRESH_HOURLY_TOKENS', '1')
    monkeypatch.setenv('SYNC_LEGACY_FRESH_BURST_TOKENS', '60')
    legacy_fresh.admit('synthetic', decide(clock, [60]), [1])
    assert redis.ttl('sync_legacy_fresh:budget:synthetic') >= 60 * 3600


def test_budget_client_is_lazy_and_uses_bounded_socket_io(monkeypatch):
    redis = MagicMock()
    create = MagicMock(return_value=redis)
    monkeypatch.setattr(legacy_fresh, 'redis_client', None)
    monkeypatch.setattr(legacy_fresh, 'create_bounded_redis_client', create)
    create.assert_not_called()
    assert legacy_fresh._get_redis_client() is redis
    assert legacy_fresh._get_redis_client() is redis
    create.assert_called_once_with(1.0)


@pytest.mark.parametrize('percent', ['0', '', 'invalid', 'nan', 'inf', '-1'])
def test_cohort_closed_or_invalid_percent(clock, monkeypatch, percent):
    monkeypatch.setenv('SYNC_LEGACY_FRESH_ENABLED', 'true')
    monkeypatch.setenv('SYNC_LEGACY_FRESH_PERCENT', percent)
    assert not legacy_fresh.enabled_for('synthetic-outsider')


def test_allowlist_is_exact_and_master_switch_wins(clock, monkeypatch):
    monkeypatch.setenv('SYNC_LEGACY_FRESH_UID_ALLOWLIST', ' synthetic-one, synthetic-two ,,')
    monkeypatch.setenv('SYNC_LEGACY_FRESH_PERCENT', '0')
    assert not legacy_fresh.enabled_for('synthetic-one')
    monkeypatch.setenv('SYNC_LEGACY_FRESH_ENABLED', 'true')
    assert legacy_fresh.enabled_for('synthetic-one')
    assert legacy_fresh.enabled_for('synthetic-two')
    assert not legacy_fresh.enabled_for('synthetic-on')
    assert not legacy_fresh.enabled_for('synthetic-outsider')
    assert not legacy_fresh.enabled_for('')


def test_cohort_default_is_closed_and_matches_final_pass_hash(clock, monkeypatch):
    monkeypatch.setenv('SYNC_LEGACY_FRESH_ENABLED', 'true')
    monkeypatch.delenv('SYNC_LEGACY_FRESH_PERCENT')
    assert not legacy_fresh.enabled_for('synthetic')
    monkeypatch.setenv('SYNC_LEGACY_FRESH_PERCENT', '5')
    admitted = []
    for index in range(1000):
        uid = f'synthetic-{index}'
        bucket = int.from_bytes(hashlib.sha256(uid.encode()).digest()[:4], 'big') / 2**32 * 100
        assert legacy_fresh.enabled_for(uid) == (bucket < 5)
        if legacy_fresh.enabled_for(uid):
            admitted.append(uid)
    assert 20 < len(admitted) < 80
    monkeypatch.setenv('SYNC_LEGACY_FRESH_PERCENT', '100')
    assert all(legacy_fresh.enabled_for(uid) for uid in admitted)
    assert legacy_fresh.enabled_for('synthetic-outsider')
    assert not legacy_fresh.enabled_for('')
