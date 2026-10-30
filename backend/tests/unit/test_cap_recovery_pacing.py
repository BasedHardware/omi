"""Run the production Lua on one hermetic Redis server shared by many pods."""

from concurrent.futures import ThreadPoolExecutor
import time
from unittest.mock import Mock

import fakeredis
import pytest

from config import cap_recovery_pacing as config
from database import cap_recovery_pacing as bucket


@pytest.fixture
def fleet(monkeypatch):
    monkeypatch.delenv('CAP_HOLD_RECOVERY_AUDIO_HOURS_PER_HOUR', raising=False)
    monkeypatch.delenv('CAP_HOLD_RECOVERY_HOLDS_PER_HOUR', raising=False)
    clock = [1000.0]
    monkeypatch.setattr(time, 'time', lambda: clock[0])
    server = fakeredis.FakeServer()
    pods = [fakeredis.FakeRedis(server=server) for _ in range(4)]
    # No free startup burst, even on missing/evicted state.
    assert bucket.reserve(600, redis_client=pods[0]) == bucket.Decision('deferred', 10)
    clock[0] += 60
    return clock, server, pods


def test_aggregate_audio_limit_across_pods_with_real_atomic_lua(fleet):
    clock, _, pods = fleet
    with ThreadPoolExecutor(max_workers=4) as executor:
        decisions = list(executor.map(lambda n: bucket.reserve(600, redis_client=pods[n % 4]), range(40)))
    assert sum(d.outcome == 'granted' for d in decisions) == 6  # 3600 audio seconds, fleet-wide
    assert all(d.retry_after == 10 for d in decisions if d.outcome != 'granted')
    clock[0] += 10
    assert bucket.reserve(600, redis_client=pods[3]).outcome == 'granted'
    assert bucket.reserve(600, redis_client=pods[0]).outcome == 'deferred'


def test_intent_ceiling_is_independent_and_denials_do_not_spend(fleet):
    clock, _, pods = fleet
    decisions = [bucket.reserve(0.1, redis_client=pods[n % 4]) for n in range(240)]
    assert sum(d.outcome == 'granted' for d in decisions) == 200
    # The 40 denials did not spend future intent credits.
    clock[0] += 0.301
    assert bucket.reserve(0.1, redis_client=pods[1]).outcome == 'granted'
    assert bucket.reserve(0.1, redis_client=pods[2]).outcome == 'deferred'


def test_redis_clock_controls_refill_and_idle_credit_is_bounded(fleet):
    clock, _, pods = fleet
    clock[0] += 86400
    assert bucket.reserve(3600, redis_client=pods[0]).outcome == 'granted'
    clock[0] -= 10  # A clock rollback cannot create credits.
    assert bucket.reserve(60, redis_client=pods[1]).outcome == 'deferred'
    clock[0] += 11
    assert bucket.reserve(60, redis_client=pods[2]).outcome == 'granted'


def test_evicted_state_starts_empty_instead_of_minting_another_burst(fleet):
    _, _, pods = fleet
    assert bucket.reserve(3600, redis_client=pods[0]).outcome == 'granted'
    pods[1].delete(bucket.KEY)
    assert bucket.reserve(3600, redis_client=pods[2]) == bucket.Decision('deferred', 60)


@pytest.mark.parametrize('fault', ['disconnected', 'ambiguous', 'malformed'])
def test_shared_state_errors_fail_closed(fleet, fault):
    _, server, pods = fleet
    client = pods[0]
    if fault == 'disconnected':
        server.connected = False
    else:
        client = Mock()
        if fault == 'ambiguous':
            client.eval.side_effect = TimeoutError('reply lost after possible debit')
        else:
            client.eval.return_value = [1, 100]
    assert bucket.reserve(60, redis_client=client) == bucket.Decision('refused', 60, 'unavailable')


@pytest.mark.parametrize('value', ['0', '-1', 'nan', 'inf', 'oops'])
@pytest.mark.parametrize('key', ['CAP_HOLD_RECOVERY_AUDIO_HOURS_PER_HOUR', 'CAP_HOLD_RECOVERY_HOLDS_PER_HOUR'])
def test_bad_config_refuses_without_io(monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    client = Mock()
    assert bucket.reserve(60, redis_client=client) == bucket.Decision('refused', 60, 'invalid')
    client.eval.assert_not_called()


@pytest.mark.parametrize('cost', [0, -1, float('nan'), float('inf'), True, None])
def test_invalid_cost_never_becomes_free_dispatch(cost):
    client = Mock()
    assert bucket.reserve(cost, redis_client=client).outcome == 'refused'
    client.eval.assert_not_called()


def test_live_config_reduction_clamps_stored_credits(fleet, monkeypatch):
    _, _, pods = fleet
    assert bucket.reserve(1, redis_client=pods[0]).outcome == 'granted'
    monkeypatch.setenv('CAP_HOLD_RECOVERY_AUDIO_HOURS_PER_HOUR', '10')
    assert bucket.reserve(600, redis_client=pods[1]).outcome == 'granted'
    assert bucket.reserve(1, redis_client=pods[2]).outcome == 'deferred'
    assert bucket.reserve(601, redis_client=pods[3]) == bucket.Decision('refused', 60, 'oversized')
    assert config.limits().audio_per_second == 10
