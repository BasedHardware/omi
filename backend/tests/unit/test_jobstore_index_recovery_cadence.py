"""Actual IndexStore + Scheduler recovery under a dropped/saturated mirror.

The synthetic primary isolates the leased population: retry has a separate
test suite. No SQL, emulator, customer data or runtime admission is involved.
"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from database.jobstore.index_store import IndexStore
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from utils.batch_pipeline.scheduler import Scheduler
from database.batch_pipeline_recovery_discovery import RecoveryCaller


class LeasedPrimary(MemoryStore):
    namespace = 'batch_pipeline_dev'

    def due(self, state, now, limit):
        if state != 'leased':
            return []
        return [
            key
            for clock, key in sorted(
                (job['lease_until'], key)
                for (table, key), job in self.rows.items()
                if table == 'jobs' and job['state'] == 'leased' and job['lease_until'] <= now
            )
        ][: max(1, min(limit, 100))]


class SyntheticMirror:
    def __init__(self, primary):
        self.primary = primary
        self.shadow = SimpleNamespace(namespace=primary.namespace, pool=Mock())

    def __getattr__(self, name):
        return getattr(self.primary, name)


def recovery(monkeypatch, count=0):
    monkeypatch.setenv('CAPTURE_RETRY_CAP_ENFORCED', 'false')
    primary = LeasedPrimary()
    primary.rows = {
        ('jobs', f'synthetic-{n:05}'): {
            'state': 'leased',
            'lease_until': 120,
            'attempt': 1,
            'owner_id': 'synthetic',
            'duration_seconds': 1,
        }
        for n in range(count)
    }
    clock = [0.0]
    mirror = SyntheticMirror(primary)
    store = IndexStore(
        mirror, enabled_queries={'due_leased'}, clock=lambda: clock[0], recovery_policy=lambda: 'role_minute_v1:10000'
    )
    store._index.due = Mock(return_value=['deleted-copy-id'])
    return primary, store, Scheduler(store, recovery_caller=RecoveryCaller.PUMP), clock


@pytest.mark.parametrize('stop', [100, 900])
def test_full_primary_prefix_keeps_recovery_on_primary_until_caught_up(monkeypatch, stop):
    primary, store, queue, clock = recovery(monkeypatch, count=40)
    hint_times = []

    def hint(*args):
        hint_times.append(clock[0])
        assert not any(job['state'] == 'leased' for job in primary.rows.values())
        return ['deleted-copy-id']

    store._index.due.side_effect = hint
    # Scale the executable2000/100 witness to40/2 for the fast CPU lane.
    # Bare60s cadence leaves8 by900s; per-call recovery clears40 by95s.
    for elapsed in range(0, stop + 1, 5):
        clock[0] = elapsed
        queue.recover(121 + elapsed, limit=2)
    assert not any(job['state'] == 'leased' for job in primary.rows.values())
    assert not hint_times or min(hint_times) >= 105


def test_empty_or_saturated_hint_uses_canonical_primary(monkeypatch):
    primary, store, _queue, _clock = recovery(monkeypatch)
    assert store.due('leased', 121) == []
    primary.rows['jobs', 'inserted-behind-copy-cursor'] = {
        'state': 'leased',
        'lease_until': 1,
        'attempt': 1,
        'owner_id': 'synthetic',
        'duration_seconds': 1,
    }
    for hints in ([], ['old-a', 'old-b']):
        store._index.due.return_value = hints
        assert store.due('leased', 122, 2) == ['inserted-behind-copy-cursor']


def test_idle_to_active_must_sweep_before_nonempty_hint(monkeypatch):
    primary, store, _queue, clock = recovery(monkeypatch)
    store.due('leased', 121)
    clock[0] = 3600
    assert store.due('leased', 3721) == []
    store._index.due.assert_not_called()


@pytest.mark.parametrize('state', ['leased', 'result_ready', 'retry'])
def test_actual_scheduler_rechecks_heartbeat_aba_and_deleted_hints(monkeypatch, state):
    primary, store, queue, _clock = recovery(monkeypatch)
    queue.recover(121)  # Mandatory primary first.
    queue.enqueue(item('new-token', owner='synthetic'), 0)
    lease = queue.pull(1)[0]
    if state == 'leased':
        assert queue.heartbeat('new-token', lease.token, 100)
    elif state == 'retry':
        assert queue.defer('new-token', lease.token, 2, retry_after=30)
    else:
        primary.rows['jobs', 'new-token']['state'] = state
    before = dict(primary.rows['jobs', 'new-token'])
    # One missing key and one renewed/changed-state key from an old copy.
    store._index.due.return_value = ['deleted', 'new-token']
    assert queue.recover(122) == 0
    assert primary.rows['jobs', 'new-token'] == before


def test_empty_leased_discovery_does_not_skip_retry_discovery(monkeypatch):
    primary, store, queue, _clock = recovery(monkeypatch)
    original = primary.due
    primary.due = Mock(side_effect=original)
    assert queue.recover(121) == 0
    assert [call.args[0] for call in primary.due.call_args_list] == ['leased', 'retry']


def test_sql_crossing_sweep_deadline_cannot_return_hint(monkeypatch):
    primary, store, _queue, clock = recovery(monkeypatch)
    assert store.due('leased', 121) == []
    clock[0] = 59.9

    def slow_hint(*args):
        clock[0] = 60.1
        return ['stale']

    store._index.due.side_effect = slow_hint
    assert store.due('leased', 122) == []


def test_slow_successful_primary_does_not_buy_another_full_interval(monkeypatch):
    primary, store, _queue, clock = recovery(monkeypatch)
    original = primary.due

    def slow_primary(*args):
        clock[0] += 61
        return original(*args)

    primary.due = slow_primary
    assert store.due('leased', 121) == []
    assert store.due('leased', 182) == []
    store._index.due.assert_not_called()


def test_failed_fallback_invalidates_previous_sweep(monkeypatch):
    primary, store, _queue, clock = recovery(monkeypatch)
    store.due('leased', 121)
    store._index.due.side_effect = RuntimeError('copy failed')
    original = primary.due
    primary.due = Mock(side_effect=RuntimeError('primary failed'))
    with pytest.raises(RuntimeError, match='primary failed'):
        store.due('leased', 122)
    store._index.due.side_effect = None
    primary.due = original
    assert store.due('leased', 123) == []


def test_sweep_interval_cannot_exceed_existing_sixty_second_bound(monkeypatch):
    _primary, store, _queue, _clock = recovery(monkeypatch)
    with pytest.raises(ValueError):
        IndexStore(store.mirror, enabled_queries={'due_leased'}, sweep_interval_s=60.01)
