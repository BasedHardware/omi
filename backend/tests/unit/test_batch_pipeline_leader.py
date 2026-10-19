"""Advisory maintenance lease over the atomic snapshot store; no Firestore IO."""

from unittest.mock import Mock

import pytest

from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from utils.batch_pipeline.leader import PUMP_RECOVERY, SERVING_MAINTENANCE, TABLE, LeaderLease


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


def pair(store, clock, ttl=30):
    return [LeaderLease(store, PUMP_RECOVERY, ttl_seconds=ttl, clock=clock) for _ in range(2)]


def test_one_holder_per_role_and_roles_are_independent():
    store, clock = MemoryStore(), Clock()
    first, second = pair(store, clock)
    assert first.acquire() and not second.acquire()
    assert first.acquire() and not second.acquire()  # Renewal keeps it.
    assert LeaderLease(store, SERVING_MAINTENANCE, ttl_seconds=60, clock=clock).acquire()


def test_renewal_writes_only_past_half_ttl():
    store, clock = MemoryStore(), Clock()
    lease = LeaderLease(store, PUMP_RECOVERY, ttl_seconds=30, clock=clock)
    assert lease.acquire()
    row = store.rows[TABLE, PUMP_RECOVERY]
    clock.now += 10
    assert lease.acquire()
    assert store.rows[TABLE, PUMP_RECOVERY] == row  # Read-only renewal.
    clock.now += 10
    assert lease.acquire()
    renewed = store.rows[TABLE, PUMP_RECOVERY]
    assert renewed['expires_at'] == clock.now + 30 and renewed['token'] == row['token']


def test_lapsed_holder_hands_over_with_a_new_token_and_old_holder_follows():
    store, clock = MemoryStore(), Clock()
    first, second = pair(store, clock)
    assert first.acquire()
    old_token = first.token
    clock.now += 31  # First is stuck in a long GPU batch past its TTL.
    assert second.acquire()
    assert second.token != old_token
    assert not first.acquire() and first.token is None
    clock.now += 31
    assert first.acquire() and first.token not in {old_token, second.token}


def test_lease_store_errors_fail_open_and_kill_switch_bypasses_store(monkeypatch):
    broken = Mock()
    broken.run.side_effect = RuntimeError('unavailable')
    assert LeaderLease(broken, PUMP_RECOVERY, ttl_seconds=30).acquire()
    store, clock = MemoryStore(), Clock()
    first, second = pair(store, clock)
    assert first.acquire() and not second.acquire()
    monkeypatch.setenv('BATCH_PIPELINE_LEADER_LEASE_ENABLED', 'false')
    untouched = Mock()
    assert second.acquire()
    assert LeaderLease(untouched, PUMP_RECOVERY, ttl_seconds=30).acquire()
    untouched.run.assert_not_called()


@pytest.mark.parametrize('role,ttl', [('unbounded_role', 30), (PUMP_RECOVERY, 0), (PUMP_RECOVERY, 3600)])
def test_role_and_ttl_are_bounded(role, ttl):
    with pytest.raises(ValueError):
        LeaderLease(MemoryStore(), role, ttl_seconds=ttl)
