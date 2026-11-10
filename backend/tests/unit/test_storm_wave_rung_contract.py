"""Wave-rung engagement contract

Every cell drives one real ``FirestoreStore.run`` entry on one real operation
label with an injected clock, and asserts the exact sleep vector (and, for
exhaustion walks, the stamped ``retry_after`` and the damper state) that the
mid-ladder wave wait produces. The wave wait engages from the third rung —
two measured collisions on one chain — and spaces that rung and deeper by the
same capped ladder the damper arms after an exhaustion, indexed by the failed
attempt and never recorded on the shared label state. Rung and window
expectations are computed at generation time from the documented formulas and
written as literals.

Failure-Class: FC-storm-window-arms-only-after-exhaustion
"""

import logging
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import Aborted

from database import batch_pipeline_store as storage

BASE_SECONDS = storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS  # 4.0 cap


def _aborting(tx):
    raise Aborted('synthetic storm')


class _Tx:
    """Minimal firestore_v1.Transaction: commits cleanly (the body aborts)."""

    _max_attempts = 1
    _read_only = False
    _id = None

    def __init__(self, abort_times=0):
        self.abort_times = abort_times
        self.commits = 0

    def _clean_up(self):
        self._id = None

    def _begin(self, retry_id=None):
        self._id = b'synthetic'

    def _commit(self):
        self.commits += 1
        if self.abort_times > 0:
            self.abort_times -= 1
            raise Aborted('synthetic commit contention')
        self._id = None

    def _rollback(self):
        self._id = None


class _Clock:
    """Deterministic monotonic clock, sleep recorder and jitter source."""

    def __init__(self, now=100.0, jitter=1.0):
        self.now = now
        self.jitter = jitter
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        assert seconds >= 0
        self.sleeps.append(round(seconds, 9))
        self.now += seconds

    def random_value(self):
        return self.jitter

    def advance(self, seconds):
        self.now += seconds


def _make_store(
    monkeypatch, clock, *, label, aborts=2, arm_at=None, exhausting=False, advance_per_attempt=0.0, dormant_env=None
):
    """A dev store on the injected clock whose body aborts ``aborts`` times."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    if dormant_env:
        monkeypatch.setenv(dormant_env, 'false')
    actual = storage.run_with_transaction_contention_retry

    def helper_factory(*args, **kwargs):
        kwargs.setdefault('sleep', clock.sleep)
        kwargs.setdefault('monotonic', clock.monotonic)
        kwargs.setdefault('random_value', clock.random_value)
        return actual(*args, **kwargs)

    monkeypatch.setattr(storage, 'run_with_transaction_contention_retry', helper_factory)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    client = Mock()
    client.transaction.side_effect = lambda max_attempts=5: _Tx(10**6 if exhausting else 0)
    store = storage.FirestoreStore('batch_pipeline_dev', firestore_client=client, storm_damper=damper)
    real_arm = damper.arm
    arm_points = [arm_at] if isinstance(arm_at, int) else list(arm_at or [])
    runs = {'n': 0}

    def body(tx):
        runs['n'] += 1
        if advance_per_attempt:
            clock.advance(advance_per_attempt)
        if runs['n'] in arm_points:
            real_arm(label)
        if exhausting or runs['n'] <= aborts:
            raise Aborted('synthetic mid-chain contention')
        return 'committed'

    return store, damper, client, body


def test_wave_boundary_below_batch_merge_commit_jitter_000(monkeypatch):
    """batch_merge_commit (jitter 0.0): two collisions never engage the wave wait — bare rungs [0.1, 0.2]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=2)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # bare rungs: the wave wait engages from the third rung


def test_wave_boundary_at_batch_merge_commit_jitter_000(monkeypatch):
    """batch_merge_commit (jitter 0.0): the third collision engages the wave wait — sleeps [0.1, 0.2, 0.9]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=3)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9]  # rung 3 adds its wave wait, rungs 1-2 stay bare


def test_wave_state_purity_batch_merge_commit_jitter_000(monkeypatch):
    """batch_merge_commit (jitter 0.0): wave rungs never write the shared label state."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    residual, generation = damper.peek('batch_merge_commit')
    assert residual == 0.0 and generation == 0  # no shared window was armed
    assert damper.tracked_labels() == 0 and not damper._failures


def test_wave_boundary_below_batch_merge_commit_jitter_050(monkeypatch):
    """batch_merge_commit (jitter 0.5): two collisions never engage the wave wait — bare rungs [0.15, 0.3]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=2)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.15, 0.3]  # bare rungs: the wave wait engages from the third rung


def test_wave_boundary_at_batch_merge_commit_jitter_050(monkeypatch):
    """batch_merge_commit (jitter 0.5): the third collision engages the wave wait — sleeps [0.15, 0.3, 1.35]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=3)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35]  # rung 3 adds its wave wait, rungs 1-2 stay bare


def test_wave_state_purity_batch_merge_commit_jitter_050(monkeypatch):
    """batch_merge_commit (jitter 0.5): wave rungs never write the shared label state."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    residual, generation = damper.peek('batch_merge_commit')
    assert residual == 0.0 and generation == 0  # no shared window was armed
    assert damper.tracked_labels() == 0 and not damper._failures


def test_wave_boundary_below_batch_merge_commit_jitter_100(monkeypatch):
    """batch_merge_commit (jitter 1.0): two collisions never engage the wave wait — bare rungs [0.2, 0.4]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=2)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # bare rungs: the wave wait engages from the third rung


def test_wave_boundary_at_batch_merge_commit_jitter_100(monkeypatch):
    """batch_merge_commit (jitter 1.0): the third collision engages the wave wait — sleeps [0.2, 0.4, 1.8]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=3)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8]  # rung 3 adds its wave wait, rungs 1-2 stay bare


def test_wave_state_purity_batch_merge_commit_jitter_100(monkeypatch):
    """batch_merge_commit (jitter 1.0): wave rungs never write the shared label state."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    residual, generation = damper.peek('batch_merge_commit')
    assert residual == 0.0 and generation == 0  # no shared window was armed
    assert damper.tracked_labels() == 0 and not damper._failures


def test_wave_boundary_below_batch_admit_jitter_000(monkeypatch):
    """batch_admit (jitter 0.0): two collisions never engage the wave wait — bare rungs [0.1, 0.2]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=2)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # bare rungs: the wave wait engages from the third rung


def test_wave_boundary_at_batch_admit_jitter_000(monkeypatch):
    """batch_admit (jitter 0.0): the third collision engages the wave wait — sleeps [0.1, 0.2, 0.9]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=3)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9]  # rung 3 adds its wave wait, rungs 1-2 stay bare


def test_wave_state_purity_batch_admit_jitter_000(monkeypatch):
    """batch_admit (jitter 0.0): wave rungs never write the shared label state."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4)
    assert store.run(body, operation='batch_admit') == 'committed'
    residual, generation = damper.peek('batch_admit')
    assert residual == 0.0 and generation == 0  # no shared window was armed
    assert damper.tracked_labels() == 0 and not damper._failures


def test_wave_boundary_below_batch_admit_jitter_050(monkeypatch):
    """batch_admit (jitter 0.5): two collisions never engage the wave wait — bare rungs [0.15, 0.3]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=2)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.15, 0.3]  # bare rungs: the wave wait engages from the third rung


def test_wave_boundary_at_batch_admit_jitter_050(monkeypatch):
    """batch_admit (jitter 0.5): the third collision engages the wave wait — sleeps [0.15, 0.3, 1.35]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=3)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35]  # rung 3 adds its wave wait, rungs 1-2 stay bare


def test_wave_state_purity_batch_admit_jitter_050(monkeypatch):
    """batch_admit (jitter 0.5): wave rungs never write the shared label state."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4)
    assert store.run(body, operation='batch_admit') == 'committed'
    residual, generation = damper.peek('batch_admit')
    assert residual == 0.0 and generation == 0  # no shared window was armed
    assert damper.tracked_labels() == 0 and not damper._failures


def test_wave_boundary_below_batch_admit_jitter_100(monkeypatch):
    """batch_admit (jitter 1.0): two collisions never engage the wave wait — bare rungs [0.2, 0.4]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=2)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # bare rungs: the wave wait engages from the third rung


def test_wave_boundary_at_batch_admit_jitter_100(monkeypatch):
    """batch_admit (jitter 1.0): the third collision engages the wave wait — sleeps [0.2, 0.4, 1.8]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=3)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8]  # rung 3 adds its wave wait, rungs 1-2 stay bare


def test_wave_state_purity_batch_admit_jitter_100(monkeypatch):
    """batch_admit (jitter 1.0): wave rungs never write the shared label state."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4)
    assert store.run(body, operation='batch_admit') == 'committed'
    residual, generation = damper.peek('batch_admit')
    assert residual == 0.0 and generation == 0  # no shared window was armed
    assert damper.tracked_labels() == 0 and not damper._failures


def test_wave_boundary_below_batch_fail_jitter_000(monkeypatch):
    """batch_fail (jitter 0.0): two collisions never engage the wave wait — bare rungs [0.1, 0.2]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=2)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # bare rungs: the wave wait engages from the third rung


def test_wave_boundary_at_batch_fail_jitter_000(monkeypatch):
    """batch_fail (jitter 0.0): the third collision engages the wave wait — sleeps [0.1, 0.2, 0.9]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=3)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9]  # rung 3 adds its wave wait, rungs 1-2 stay bare


def test_wave_state_purity_batch_fail_jitter_000(monkeypatch):
    """batch_fail (jitter 0.0): wave rungs never write the shared label state."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4)
    assert store.run(body, operation='batch_fail') == 'committed'
    residual, generation = damper.peek('batch_fail')
    assert residual == 0.0 and generation == 0  # no shared window was armed
    assert damper.tracked_labels() == 0 and not damper._failures


def test_wave_boundary_below_batch_fail_jitter_050(monkeypatch):
    """batch_fail (jitter 0.5): two collisions never engage the wave wait — bare rungs [0.15, 0.3]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=2)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.15, 0.3]  # bare rungs: the wave wait engages from the third rung


def test_wave_boundary_at_batch_fail_jitter_050(monkeypatch):
    """batch_fail (jitter 0.5): the third collision engages the wave wait — sleeps [0.15, 0.3, 1.35]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=3)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35]  # rung 3 adds its wave wait, rungs 1-2 stay bare


def test_wave_state_purity_batch_fail_jitter_050(monkeypatch):
    """batch_fail (jitter 0.5): wave rungs never write the shared label state."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4)
    assert store.run(body, operation='batch_fail') == 'committed'
    residual, generation = damper.peek('batch_fail')
    assert residual == 0.0 and generation == 0  # no shared window was armed
    assert damper.tracked_labels() == 0 and not damper._failures


def test_wave_boundary_below_batch_fail_jitter_100(monkeypatch):
    """batch_fail (jitter 1.0): two collisions never engage the wave wait — bare rungs [0.2, 0.4]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=2)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # bare rungs: the wave wait engages from the third rung


def test_wave_boundary_at_batch_fail_jitter_100(monkeypatch):
    """batch_fail (jitter 1.0): the third collision engages the wave wait — sleeps [0.2, 0.4, 1.8]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=3)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8]  # rung 3 adds its wave wait, rungs 1-2 stay bare


def test_wave_state_purity_batch_fail_jitter_100(monkeypatch):
    """batch_fail (jitter 1.0): wave rungs never write the shared label state."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4)
    assert store.run(body, operation='batch_fail') == 'committed'
    residual, generation = damper.peek('batch_fail')
    assert residual == 0.0 and generation == 0  # no shared window was armed
    assert damper.tracked_labels() == 0 and not damper._failures


def test_wave_boundary_below_batch_complete_jitter_000(monkeypatch):
    """batch_complete (jitter 0.0): two collisions never engage the wave wait — bare rungs [0.1, 0.2]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=2)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # bare rungs: the wave wait engages from the third rung


def test_wave_boundary_at_batch_complete_jitter_000(monkeypatch):
    """batch_complete (jitter 0.0): the third collision engages the wave wait — sleeps [0.1, 0.2, 0.9]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=3)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9]  # rung 3 adds its wave wait, rungs 1-2 stay bare


def test_wave_state_purity_batch_complete_jitter_000(monkeypatch):
    """batch_complete (jitter 0.0): wave rungs never write the shared label state."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4)
    assert store.run(body, operation='batch_complete') == 'committed'
    residual, generation = damper.peek('batch_complete')
    assert residual == 0.0 and generation == 0  # no shared window was armed
    assert damper.tracked_labels() == 0 and not damper._failures


def test_wave_boundary_below_batch_complete_jitter_050(monkeypatch):
    """batch_complete (jitter 0.5): two collisions never engage the wave wait — bare rungs [0.15, 0.3]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=2)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.15, 0.3]  # bare rungs: the wave wait engages from the third rung


def test_wave_boundary_at_batch_complete_jitter_050(monkeypatch):
    """batch_complete (jitter 0.5): the third collision engages the wave wait — sleeps [0.15, 0.3, 1.35]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=3)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35]  # rung 3 adds its wave wait, rungs 1-2 stay bare


def test_wave_state_purity_batch_complete_jitter_050(monkeypatch):
    """batch_complete (jitter 0.5): wave rungs never write the shared label state."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4)
    assert store.run(body, operation='batch_complete') == 'committed'
    residual, generation = damper.peek('batch_complete')
    assert residual == 0.0 and generation == 0  # no shared window was armed
    assert damper.tracked_labels() == 0 and not damper._failures


def test_wave_boundary_below_batch_complete_jitter_100(monkeypatch):
    """batch_complete (jitter 1.0): two collisions never engage the wave wait — bare rungs [0.2, 0.4]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=2)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # bare rungs: the wave wait engages from the third rung


def test_wave_boundary_at_batch_complete_jitter_100(monkeypatch):
    """batch_complete (jitter 1.0): the third collision engages the wave wait — sleeps [0.2, 0.4, 1.8]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=3)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8]  # rung 3 adds its wave wait, rungs 1-2 stay bare


def test_wave_state_purity_batch_complete_jitter_100(monkeypatch):
    """batch_complete (jitter 1.0): wave rungs never write the shared label state."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4)
    assert store.run(body, operation='batch_complete') == 'committed'
    residual, generation = damper.peek('batch_complete')
    assert residual == 0.0 and generation == 0  # no shared window was armed
    assert damper.tracked_labels() == 0 and not damper._failures


def test_wave_boundary_below_batch_defer_jitter_000(monkeypatch):
    """batch_defer (jitter 0.0): two collisions never engage the wave wait — bare rungs [0.1, 0.2]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=2)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # bare rungs: the wave wait engages from the third rung


def test_wave_boundary_at_batch_defer_jitter_000(monkeypatch):
    """batch_defer (jitter 0.0): the third collision engages the wave wait — sleeps [0.1, 0.2, 0.9]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=3)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9]  # rung 3 adds its wave wait, rungs 1-2 stay bare


def test_wave_state_purity_batch_defer_jitter_000(monkeypatch):
    """batch_defer (jitter 0.0): wave rungs never write the shared label state."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4)
    assert store.run(body, operation='batch_defer') == 'committed'
    residual, generation = damper.peek('batch_defer')
    assert residual == 0.0 and generation == 0  # no shared window was armed
    assert damper.tracked_labels() == 0 and not damper._failures


def test_wave_boundary_below_batch_defer_jitter_050(monkeypatch):
    """batch_defer (jitter 0.5): two collisions never engage the wave wait — bare rungs [0.15, 0.3]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=2)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.15, 0.3]  # bare rungs: the wave wait engages from the third rung


def test_wave_boundary_at_batch_defer_jitter_050(monkeypatch):
    """batch_defer (jitter 0.5): the third collision engages the wave wait — sleeps [0.15, 0.3, 1.35]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=3)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35]  # rung 3 adds its wave wait, rungs 1-2 stay bare


def test_wave_state_purity_batch_defer_jitter_050(monkeypatch):
    """batch_defer (jitter 0.5): wave rungs never write the shared label state."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4)
    assert store.run(body, operation='batch_defer') == 'committed'
    residual, generation = damper.peek('batch_defer')
    assert residual == 0.0 and generation == 0  # no shared window was armed
    assert damper.tracked_labels() == 0 and not damper._failures


def test_wave_boundary_below_batch_defer_jitter_100(monkeypatch):
    """batch_defer (jitter 1.0): two collisions never engage the wave wait — bare rungs [0.2, 0.4]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=2)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # bare rungs: the wave wait engages from the third rung


def test_wave_boundary_at_batch_defer_jitter_100(monkeypatch):
    """batch_defer (jitter 1.0): the third collision engages the wave wait — sleeps [0.2, 0.4, 1.8]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=3)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8]  # rung 3 adds its wave wait, rungs 1-2 stay bare


def test_wave_state_purity_batch_defer_jitter_100(monkeypatch):
    """batch_defer (jitter 1.0): wave rungs never write the shared label state."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4)
    assert store.run(body, operation='batch_defer') == 'committed'
    residual, generation = damper.peek('batch_defer')
    assert residual == 0.0 and generation == 0  # no shared window was armed
    assert damper.tracked_labels() == 0 and not damper._failures


def test_wave_boundary_below_batch_intake_status_jitter_000(monkeypatch):
    """batch_intake_status (jitter 0.0): two collisions never engage the wave wait — bare rungs [0.1, 0.2]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=2)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # bare rungs: the wave wait engages from the third rung


def test_wave_boundary_at_batch_intake_status_jitter_000(monkeypatch):
    """batch_intake_status (jitter 0.0): the third collision engages the wave wait — sleeps [0.1, 0.2, 0.9]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=3)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9]  # rung 3 adds its wave wait, rungs 1-2 stay bare


def test_wave_state_purity_batch_intake_status_jitter_000(monkeypatch):
    """batch_intake_status (jitter 0.0): wave rungs never write the shared label state."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    residual, generation = damper.peek('batch_intake_status')
    assert residual == 0.0 and generation == 0  # no shared window was armed
    assert damper.tracked_labels() == 0 and not damper._failures


def test_wave_boundary_below_batch_intake_status_jitter_050(monkeypatch):
    """batch_intake_status (jitter 0.5): two collisions never engage the wave wait — bare rungs [0.15, 0.3]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=2)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.15, 0.3]  # bare rungs: the wave wait engages from the third rung


def test_wave_boundary_at_batch_intake_status_jitter_050(monkeypatch):
    """batch_intake_status (jitter 0.5): the third collision engages the wave wait — sleeps [0.15, 0.3, 1.35]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=3)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35]  # rung 3 adds its wave wait, rungs 1-2 stay bare


def test_wave_state_purity_batch_intake_status_jitter_050(monkeypatch):
    """batch_intake_status (jitter 0.5): wave rungs never write the shared label state."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    residual, generation = damper.peek('batch_intake_status')
    assert residual == 0.0 and generation == 0  # no shared window was armed
    assert damper.tracked_labels() == 0 and not damper._failures


def test_wave_boundary_below_batch_intake_status_jitter_100(monkeypatch):
    """batch_intake_status (jitter 1.0): two collisions never engage the wave wait — bare rungs [0.2, 0.4]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=2)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # bare rungs: the wave wait engages from the third rung


def test_wave_boundary_at_batch_intake_status_jitter_100(monkeypatch):
    """batch_intake_status (jitter 1.0): the third collision engages the wave wait — sleeps [0.2, 0.4, 1.8]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=3)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8]  # rung 3 adds its wave wait, rungs 1-2 stay bare


def test_wave_state_purity_batch_intake_status_jitter_100(monkeypatch):
    """batch_intake_status (jitter 1.0): wave rungs never write the shared label state."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    residual, generation = damper.peek('batch_intake_status')
    assert residual == 0.0 and generation == 0  # no shared window was armed
    assert damper.tracked_labels() == 0 and not damper._failures


def test_wave_boundary_below_batch_seal_register_jitter_000(monkeypatch):
    """batch_seal_register (jitter 0.0): two collisions never engage the wave wait — bare rungs [0.1, 0.2]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=2)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # bare rungs: the wave wait engages from the third rung


def test_wave_boundary_at_batch_seal_register_jitter_000(monkeypatch):
    """batch_seal_register (jitter 0.0): the third collision engages the wave wait — sleeps [0.1, 0.2, 0.9]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=3)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9]  # rung 3 adds its wave wait, rungs 1-2 stay bare


def test_wave_state_purity_batch_seal_register_jitter_000(monkeypatch):
    """batch_seal_register (jitter 0.0): wave rungs never write the shared label state."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    residual, generation = damper.peek('batch_seal_register')
    assert residual == 0.0 and generation == 0  # no shared window was armed
    assert damper.tracked_labels() == 0 and not damper._failures


def test_wave_boundary_below_batch_seal_register_jitter_050(monkeypatch):
    """batch_seal_register (jitter 0.5): two collisions never engage the wave wait — bare rungs [0.15, 0.3]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=2)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.15, 0.3]  # bare rungs: the wave wait engages from the third rung


def test_wave_boundary_at_batch_seal_register_jitter_050(monkeypatch):
    """batch_seal_register (jitter 0.5): the third collision engages the wave wait — sleeps [0.15, 0.3, 1.35]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=3)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35]  # rung 3 adds its wave wait, rungs 1-2 stay bare


def test_wave_state_purity_batch_seal_register_jitter_050(monkeypatch):
    """batch_seal_register (jitter 0.5): wave rungs never write the shared label state."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    residual, generation = damper.peek('batch_seal_register')
    assert residual == 0.0 and generation == 0  # no shared window was armed
    assert damper.tracked_labels() == 0 and not damper._failures


def test_wave_boundary_below_batch_seal_register_jitter_100(monkeypatch):
    """batch_seal_register (jitter 1.0): two collisions never engage the wave wait — bare rungs [0.2, 0.4]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=2)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # bare rungs: the wave wait engages from the third rung


def test_wave_boundary_at_batch_seal_register_jitter_100(monkeypatch):
    """batch_seal_register (jitter 1.0): the third collision engages the wave wait — sleeps [0.2, 0.4, 1.8]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=3)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8]  # rung 3 adds its wave wait, rungs 1-2 stay bare


def test_wave_state_purity_batch_seal_register_jitter_100(monkeypatch):
    """batch_seal_register (jitter 1.0): wave rungs never write the shared label state."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    residual, generation = damper.peek('batch_seal_register')
    assert residual == 0.0 and generation == 0  # no shared window was armed
    assert damper.tracked_labels() == 0 and not damper._failures


def test_wave_exhaustion_stamp_batch_merge_commit_jitter_000(monkeypatch):
    """batch_merge_commit (jitter 0.0): four wave rungs do not escalate the exhaustion stamp (0.125s, failures still 1)."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_merge_commit', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_merge_commit')
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]  # rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.125)
    assert damper._failures['batch_merge_commit'] == 1  # wave rungs never arm


def test_wave_exhaustion_stamp_batch_merge_commit_jitter_050(monkeypatch):
    """batch_merge_commit (jitter 0.5): four wave rungs do not escalate the exhaustion stamp (0.1875s, failures still 1)."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_merge_commit', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_merge_commit')
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]  # rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.1875)
    assert damper._failures['batch_merge_commit'] == 1  # wave rungs never arm


def test_wave_exhaustion_stamp_batch_merge_commit_jitter_100(monkeypatch):
    """batch_merge_commit (jitter 1.0): four wave rungs do not escalate the exhaustion stamp (0.25s, failures still 1)."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_merge_commit', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_merge_commit')
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]  # rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.25)
    assert damper._failures['batch_merge_commit'] == 1  # wave rungs never arm


def test_wave_exhaustion_stamp_batch_admit_jitter_000(monkeypatch):
    """batch_admit (jitter 0.0): four wave rungs do not escalate the exhaustion stamp (0.125s, failures still 1)."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_admit')
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]  # rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.125)
    assert damper._failures['batch_admit'] == 1  # wave rungs never arm


def test_wave_exhaustion_stamp_batch_admit_jitter_050(monkeypatch):
    """batch_admit (jitter 0.5): four wave rungs do not escalate the exhaustion stamp (0.1875s, failures still 1)."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_admit')
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]  # rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.1875)
    assert damper._failures['batch_admit'] == 1  # wave rungs never arm


def test_wave_exhaustion_stamp_batch_admit_jitter_100(monkeypatch):
    """batch_admit (jitter 1.0): four wave rungs do not escalate the exhaustion stamp (0.25s, failures still 1)."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_admit')
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]  # rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.25)
    assert damper._failures['batch_admit'] == 1  # wave rungs never arm


def test_wave_exhaustion_stamp_batch_fail_jitter_000(monkeypatch):
    """batch_fail (jitter 0.0): four wave rungs do not escalate the exhaustion stamp (0.125s, failures still 1)."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_fail')
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]  # rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.125)
    assert damper._failures['batch_fail'] == 1  # wave rungs never arm


def test_wave_exhaustion_stamp_batch_fail_jitter_050(monkeypatch):
    """batch_fail (jitter 0.5): four wave rungs do not escalate the exhaustion stamp (0.1875s, failures still 1)."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_fail')
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]  # rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.1875)
    assert damper._failures['batch_fail'] == 1  # wave rungs never arm


def test_wave_exhaustion_stamp_batch_fail_jitter_100(monkeypatch):
    """batch_fail (jitter 1.0): four wave rungs do not escalate the exhaustion stamp (0.25s, failures still 1)."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_fail')
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]  # rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.25)
    assert damper._failures['batch_fail'] == 1  # wave rungs never arm


def test_wave_exhaustion_stamp_batch_complete_jitter_000(monkeypatch):
    """batch_complete (jitter 0.0): four wave rungs do not escalate the exhaustion stamp (0.125s, failures still 1)."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_complete')
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]  # rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.125)
    assert damper._failures['batch_complete'] == 1  # wave rungs never arm


def test_wave_exhaustion_stamp_batch_complete_jitter_050(monkeypatch):
    """batch_complete (jitter 0.5): four wave rungs do not escalate the exhaustion stamp (0.1875s, failures still 1)."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_complete')
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]  # rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.1875)
    assert damper._failures['batch_complete'] == 1  # wave rungs never arm


def test_wave_exhaustion_stamp_batch_complete_jitter_100(monkeypatch):
    """batch_complete (jitter 1.0): four wave rungs do not escalate the exhaustion stamp (0.25s, failures still 1)."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_complete')
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]  # rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.25)
    assert damper._failures['batch_complete'] == 1  # wave rungs never arm


def test_wave_exhaustion_stamp_batch_defer_jitter_000(monkeypatch):
    """batch_defer (jitter 0.0): four wave rungs do not escalate the exhaustion stamp (0.125s, failures still 1)."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_defer')
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]  # rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.125)
    assert damper._failures['batch_defer'] == 1  # wave rungs never arm


def test_wave_exhaustion_stamp_batch_defer_jitter_050(monkeypatch):
    """batch_defer (jitter 0.5): four wave rungs do not escalate the exhaustion stamp (0.1875s, failures still 1)."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_defer')
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]  # rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.1875)
    assert damper._failures['batch_defer'] == 1  # wave rungs never arm


def test_wave_exhaustion_stamp_batch_defer_jitter_100(monkeypatch):
    """batch_defer (jitter 1.0): four wave rungs do not escalate the exhaustion stamp (0.25s, failures still 1)."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_defer')
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]  # rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.25)
    assert damper._failures['batch_defer'] == 1  # wave rungs never arm


def test_wave_exhaustion_stamp_batch_intake_status_jitter_000(monkeypatch):
    """batch_intake_status (jitter 0.0): four wave rungs do not escalate the exhaustion stamp (0.125s, failures still 1)."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_intake_status', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_intake_status')
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]  # rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.125)
    assert damper._failures['batch_intake_status'] == 1  # wave rungs never arm


def test_wave_exhaustion_stamp_batch_intake_status_jitter_050(monkeypatch):
    """batch_intake_status (jitter 0.5): four wave rungs do not escalate the exhaustion stamp (0.1875s, failures still 1)."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_intake_status', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_intake_status')
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]  # rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.1875)
    assert damper._failures['batch_intake_status'] == 1  # wave rungs never arm


def test_wave_exhaustion_stamp_batch_intake_status_jitter_100(monkeypatch):
    """batch_intake_status (jitter 1.0): four wave rungs do not escalate the exhaustion stamp (0.25s, failures still 1)."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_intake_status', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_intake_status')
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]  # rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.25)
    assert damper._failures['batch_intake_status'] == 1  # wave rungs never arm


def test_wave_exhaustion_stamp_batch_seal_register_jitter_000(monkeypatch):
    """batch_seal_register (jitter 0.0): four wave rungs do not escalate the exhaustion stamp (0.125s, failures still 1)."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_seal_register', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_seal_register')
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]  # rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.125)
    assert damper._failures['batch_seal_register'] == 1  # wave rungs never arm


def test_wave_exhaustion_stamp_batch_seal_register_jitter_050(monkeypatch):
    """batch_seal_register (jitter 0.5): four wave rungs do not escalate the exhaustion stamp (0.1875s, failures still 1)."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_seal_register', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_seal_register')
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]  # rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.1875)
    assert damper._failures['batch_seal_register'] == 1  # wave rungs never arm


def test_wave_exhaustion_stamp_batch_seal_register_jitter_100(monkeypatch):
    """batch_seal_register (jitter 1.0): four wave rungs do not escalate the exhaustion stamp (0.25s, failures still 1)."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_seal_register', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_seal_register')
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]  # rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.25)
    assert damper._failures['batch_seal_register'] == 1  # wave rungs never arm


def test_wave_sibling_ladder_wins_batch_merge_jitter_000(monkeypatch):
    """three sibling arms before rung 3 stack a window longer than the wave wait (jitter 0.0) — the sibling wins."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_merge_commit', aborts=3, arm_at=(2, 2, 2)
    )
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.1, 0.325, 0.9]  # rung 3 waits out the stacked sibling window


def test_wave_sibling_ladder_wins_batch_merge_jitter_050(monkeypatch):
    """three sibling arms before rung 3 stack a window longer than the wave wait (jitter 0.5) — the sibling wins."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_merge_commit', aborts=3, arm_at=(2, 2, 2)
    )
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.15, 0.4875, 1.35]  # rung 3 waits out the stacked sibling window


def test_wave_sibling_ladder_wins_batch_merge_jitter_100(monkeypatch):
    """three sibling arms before rung 3 stack a window longer than the wave wait (jitter 1.0) — the sibling wins."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_merge_commit', aborts=3, arm_at=(2, 2, 2)
    )
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.2, 0.65, 1.8]  # rung 3 waits out the stacked sibling window


def test_wave_dormant_batch_fail_jitter_000(monkeypatch):
    """damper kill switch off (jitter 0.0): deep aborts still ride the bare ladder [0.1, 0.2, 0.4, 0.8]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_fail', aborts=4, dormant_env='BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED'
    )
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.4, 0.8]  # no gate, no wave, no wait


def test_wave_dormant_batch_fail_jitter_050(monkeypatch):
    """damper kill switch off (jitter 0.5): deep aborts still ride the bare ladder [0.15, 0.3, 0.6, 1.2]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_fail', aborts=4, dormant_env='BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED'
    )
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 0.6, 1.2]  # no gate, no wave, no wait


def test_wave_dormant_batch_fail_jitter_100(monkeypatch):
    """damper kill switch off (jitter 1.0): deep aborts still ride the bare ladder [0.2, 0.4, 0.8, 1.6]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_fail', aborts=4, dormant_env='BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED'
    )
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 0.8, 1.6]  # no gate, no wave, no wait


def test_wave_deadline_budget_31_advance_145_jitter_000(monkeypatch):
    """budget 31s with 14.5s attempts (jitter 0.0): outcome deadline_exhausted, sleeps [0.1]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_merge_commit', aborts=4, advance_per_attempt=14.5
    )
    from database.firestore_transaction_retry import (
        FirestoreContentionExhausted,
        transaction_retry_deadline_scope,
    )

    with transaction_retry_deadline_scope(clock.monotonic() + 31):
        with pytest.raises(FirestoreContentionExhausted) as caught:
            store.run(body, operation='batch_merge_commit')
    assert 'deadline' in str(caught.value)
    assert clock.sleeps == [0.1]  # every recorded sleep fits inside the budget


def test_wave_deadline_budget_31_advance_145_jitter_050(monkeypatch):
    """budget 31s with 14.5s attempts (jitter 0.5): outcome deadline_exhausted, sleeps [0.15]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_merge_commit', aborts=4, advance_per_attempt=14.5
    )
    from database.firestore_transaction_retry import (
        FirestoreContentionExhausted,
        transaction_retry_deadline_scope,
    )

    with transaction_retry_deadline_scope(clock.monotonic() + 31):
        with pytest.raises(FirestoreContentionExhausted) as caught:
            store.run(body, operation='batch_merge_commit')
    assert 'deadline' in str(caught.value)
    assert clock.sleeps == [0.15]  # every recorded sleep fits inside the budget


def test_wave_deadline_budget_31_advance_145_jitter_100(monkeypatch):
    """budget 31s with 14.5s attempts (jitter 1.0): outcome deadline_exhausted, sleeps [0.2]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_merge_commit', aborts=4, advance_per_attempt=14.5
    )
    from database.firestore_transaction_retry import (
        FirestoreContentionExhausted,
        transaction_retry_deadline_scope,
    )

    with transaction_retry_deadline_scope(clock.monotonic() + 31):
        with pytest.raises(FirestoreContentionExhausted) as caught:
            store.run(body, operation='batch_merge_commit')
    assert 'deadline' in str(caught.value)
    assert clock.sleeps == [0.2]  # every recorded sleep fits inside the budget


def test_wave_deadline_budget_60_advance_145_jitter_000(monkeypatch):
    """budget 60s with 14.5s attempts (jitter 0.0): outcome deadline_exhausted, sleeps [0.1, 0.2, 0.9]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_merge_commit', aborts=4, advance_per_attempt=14.5
    )
    from database.firestore_transaction_retry import (
        FirestoreContentionExhausted,
        transaction_retry_deadline_scope,
    )

    with transaction_retry_deadline_scope(clock.monotonic() + 60):
        with pytest.raises(FirestoreContentionExhausted) as caught:
            store.run(body, operation='batch_merge_commit')
    assert 'deadline' in str(caught.value)
    assert clock.sleeps == [0.1, 0.2, 0.9]  # every recorded sleep fits inside the budget


def test_wave_deadline_budget_60_advance_145_jitter_050(monkeypatch):
    """budget 60s with 14.5s attempts (jitter 0.5): outcome deadline_exhausted, sleeps [0.15, 0.3, 1.35]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_merge_commit', aborts=4, advance_per_attempt=14.5
    )
    from database.firestore_transaction_retry import (
        FirestoreContentionExhausted,
        transaction_retry_deadline_scope,
    )

    with transaction_retry_deadline_scope(clock.monotonic() + 60):
        with pytest.raises(FirestoreContentionExhausted) as caught:
            store.run(body, operation='batch_merge_commit')
    assert 'deadline' in str(caught.value)
    assert clock.sleeps == [0.15, 0.3, 1.35]  # every recorded sleep fits inside the budget


def test_wave_deadline_budget_60_advance_145_jitter_100(monkeypatch):
    """budget 60s with 14.5s attempts (jitter 1.0): outcome deadline_exhausted, sleeps [0.2, 0.4, 1.8]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_merge_commit', aborts=4, advance_per_attempt=14.5
    )
    from database.firestore_transaction_retry import (
        FirestoreContentionExhausted,
        transaction_retry_deadline_scope,
    )

    with transaction_retry_deadline_scope(clock.monotonic() + 60):
        with pytest.raises(FirestoreContentionExhausted) as caught:
            store.run(body, operation='batch_merge_commit')
    assert 'deadline' in str(caught.value)
    assert clock.sleeps == [0.2, 0.4, 1.8]  # every recorded sleep fits inside the budget


def test_wave_deadline_budget_45_advance_80_jitter_000(monkeypatch):
    """budget 45s with 8s attempts (jitter 0.0): outcome deadline_exhausted, sleeps [0.1, 0.2]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_merge_commit', aborts=4, advance_per_attempt=8
    )
    from database.firestore_transaction_retry import (
        FirestoreContentionExhausted,
        transaction_retry_deadline_scope,
    )

    with transaction_retry_deadline_scope(clock.monotonic() + 45):
        with pytest.raises(FirestoreContentionExhausted) as caught:
            store.run(body, operation='batch_merge_commit')
    assert 'deadline' in str(caught.value)
    assert clock.sleeps == [0.1, 0.2]  # every recorded sleep fits inside the budget


def test_wave_deadline_budget_45_advance_80_jitter_050(monkeypatch):
    """budget 45s with 8s attempts (jitter 0.5): outcome deadline_exhausted, sleeps [0.15, 0.3]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_merge_commit', aborts=4, advance_per_attempt=8
    )
    from database.firestore_transaction_retry import (
        FirestoreContentionExhausted,
        transaction_retry_deadline_scope,
    )

    with transaction_retry_deadline_scope(clock.monotonic() + 45):
        with pytest.raises(FirestoreContentionExhausted) as caught:
            store.run(body, operation='batch_merge_commit')
    assert 'deadline' in str(caught.value)
    assert clock.sleeps == [0.15, 0.3]  # every recorded sleep fits inside the budget


def test_wave_deadline_budget_45_advance_80_jitter_100(monkeypatch):
    """budget 45s with 8s attempts (jitter 1.0): outcome deadline_exhausted, sleeps [0.2, 0.4]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_merge_commit', aborts=4, advance_per_attempt=8
    )
    from database.firestore_transaction_retry import (
        FirestoreContentionExhausted,
        transaction_retry_deadline_scope,
    )

    with transaction_retry_deadline_scope(clock.monotonic() + 45):
        with pytest.raises(FirestoreContentionExhausted) as caught:
            store.run(body, operation='batch_merge_commit')
    assert 'deadline' in str(caught.value)
    assert clock.sleeps == [0.2, 0.4]  # every recorded sleep fits inside the budget


def test_wave_log_taxonomy_batch_merge_commit_rungs3_jitter_000(caplog, monkeypatch):
    """batch_merge_commit (jitter 0.0): exactly one mid-ladder line, on rung 3."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=3)
    import logging as _logging

    with caplog.at_level(_logging.INFO, logger='database.batch_pipeline_store'):
        store.run(body, operation='batch_merge_commit')
    lines = [r.getMessage() for r in caplog.records if 'scope=mid_ladder' in r.getMessage()]
    assert len(lines) == 1
    assert 'attempt=3' in lines[0]
    assert f'waited_ms={round(0.5 * 1000)}' in lines[0]


def test_wave_log_taxonomy_batch_merge_commit_rungs34_jitter_000(caplog, monkeypatch):
    """batch_merge_commit (jitter 0.0): two mid-ladder lines, rungs 3 and 4."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4)
    import logging as _logging

    with caplog.at_level(_logging.INFO, logger='database.batch_pipeline_store'):
        store.run(body, operation='batch_merge_commit')
    lines = [r.getMessage() for r in caplog.records if 'scope=mid_ladder' in r.getMessage()]
    assert len(lines) == 2
    assert 'attempt=3' in lines[0] and 'attempt=4' in lines[1]


def test_wave_log_taxonomy_batch_merge_commit_rungs3_jitter_050(caplog, monkeypatch):
    """batch_merge_commit (jitter 0.5): exactly one mid-ladder line, on rung 3."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=3)
    import logging as _logging

    with caplog.at_level(_logging.INFO, logger='database.batch_pipeline_store'):
        store.run(body, operation='batch_merge_commit')
    lines = [r.getMessage() for r in caplog.records if 'scope=mid_ladder' in r.getMessage()]
    assert len(lines) == 1
    assert 'attempt=3' in lines[0]
    assert f'waited_ms={round(0.75 * 1000)}' in lines[0]


def test_wave_log_taxonomy_batch_merge_commit_rungs34_jitter_050(caplog, monkeypatch):
    """batch_merge_commit (jitter 0.5): two mid-ladder lines, rungs 3 and 4."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4)
    import logging as _logging

    with caplog.at_level(_logging.INFO, logger='database.batch_pipeline_store'):
        store.run(body, operation='batch_merge_commit')
    lines = [r.getMessage() for r in caplog.records if 'scope=mid_ladder' in r.getMessage()]
    assert len(lines) == 2
    assert 'attempt=3' in lines[0] and 'attempt=4' in lines[1]


def test_wave_log_taxonomy_batch_merge_commit_rungs3_jitter_100(caplog, monkeypatch):
    """batch_merge_commit (jitter 1.0): exactly one mid-ladder line, on rung 3."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=3)
    import logging as _logging

    with caplog.at_level(_logging.INFO, logger='database.batch_pipeline_store'):
        store.run(body, operation='batch_merge_commit')
    lines = [r.getMessage() for r in caplog.records if 'scope=mid_ladder' in r.getMessage()]
    assert len(lines) == 1
    assert 'attempt=3' in lines[0]
    assert f'waited_ms={round(1 * 1000)}' in lines[0]


def test_wave_log_taxonomy_batch_merge_commit_rungs34_jitter_100(caplog, monkeypatch):
    """batch_merge_commit (jitter 1.0): two mid-ladder lines, rungs 3 and 4."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4)
    import logging as _logging

    with caplog.at_level(_logging.INFO, logger='database.batch_pipeline_store'):
        store.run(body, operation='batch_merge_commit')
    lines = [r.getMessage() for r in caplog.records if 'scope=mid_ladder' in r.getMessage()]
    assert len(lines) == 2
    assert 'attempt=3' in lines[0] and 'attempt=4' in lines[1]


def test_wave_log_taxonomy_batch_admit_rungs3_jitter_000(caplog, monkeypatch):
    """batch_admit (jitter 0.0): exactly one mid-ladder line, on rung 3."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=3)
    import logging as _logging

    with caplog.at_level(_logging.INFO, logger='database.batch_pipeline_store'):
        store.run(body, operation='batch_admit')
    lines = [r.getMessage() for r in caplog.records if 'scope=mid_ladder' in r.getMessage()]
    assert len(lines) == 1
    assert 'attempt=3' in lines[0]
    assert f'waited_ms={round(0.5 * 1000)}' in lines[0]


def test_wave_log_taxonomy_batch_admit_rungs34_jitter_000(caplog, monkeypatch):
    """batch_admit (jitter 0.0): two mid-ladder lines, rungs 3 and 4."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4)
    import logging as _logging

    with caplog.at_level(_logging.INFO, logger='database.batch_pipeline_store'):
        store.run(body, operation='batch_admit')
    lines = [r.getMessage() for r in caplog.records if 'scope=mid_ladder' in r.getMessage()]
    assert len(lines) == 2
    assert 'attempt=3' in lines[0] and 'attempt=4' in lines[1]


def test_wave_log_taxonomy_batch_admit_rungs3_jitter_050(caplog, monkeypatch):
    """batch_admit (jitter 0.5): exactly one mid-ladder line, on rung 3."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=3)
    import logging as _logging

    with caplog.at_level(_logging.INFO, logger='database.batch_pipeline_store'):
        store.run(body, operation='batch_admit')
    lines = [r.getMessage() for r in caplog.records if 'scope=mid_ladder' in r.getMessage()]
    assert len(lines) == 1
    assert 'attempt=3' in lines[0]
    assert f'waited_ms={round(0.75 * 1000)}' in lines[0]


def test_wave_log_taxonomy_batch_admit_rungs34_jitter_050(caplog, monkeypatch):
    """batch_admit (jitter 0.5): two mid-ladder lines, rungs 3 and 4."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4)
    import logging as _logging

    with caplog.at_level(_logging.INFO, logger='database.batch_pipeline_store'):
        store.run(body, operation='batch_admit')
    lines = [r.getMessage() for r in caplog.records if 'scope=mid_ladder' in r.getMessage()]
    assert len(lines) == 2
    assert 'attempt=3' in lines[0] and 'attempt=4' in lines[1]


def test_wave_log_taxonomy_batch_admit_rungs3_jitter_100(caplog, monkeypatch):
    """batch_admit (jitter 1.0): exactly one mid-ladder line, on rung 3."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=3)
    import logging as _logging

    with caplog.at_level(_logging.INFO, logger='database.batch_pipeline_store'):
        store.run(body, operation='batch_admit')
    lines = [r.getMessage() for r in caplog.records if 'scope=mid_ladder' in r.getMessage()]
    assert len(lines) == 1
    assert 'attempt=3' in lines[0]
    assert f'waited_ms={round(1 * 1000)}' in lines[0]


def test_wave_log_taxonomy_batch_admit_rungs34_jitter_100(caplog, monkeypatch):
    """batch_admit (jitter 1.0): two mid-ladder lines, rungs 3 and 4."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4)
    import logging as _logging

    with caplog.at_level(_logging.INFO, logger='database.batch_pipeline_store'):
        store.run(body, operation='batch_admit')
    lines = [r.getMessage() for r in caplog.records if 'scope=mid_ladder' in r.getMessage()]
    assert len(lines) == 2
    assert 'attempt=3' in lines[0] and 'attempt=4' in lines[1]


def test_wave_unit_arithmetic_rung1_jitter_00(monkeypatch):
    """wave_rung_wait(1) at jitter 0.0 is exactly 0.125s (capped ladder rung 0.25)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(1) == pytest.approx(0.125)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung1_jitter_01(monkeypatch):
    """wave_rung_wait(1) at jitter 0.1 is exactly 0.1375s (capped ladder rung 0.25)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.1)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(1) == pytest.approx(0.1375)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung1_jitter_02(monkeypatch):
    """wave_rung_wait(1) at jitter 0.2 is exactly 0.15s (capped ladder rung 0.25)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.2)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(1) == pytest.approx(0.15)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung1_jitter_03(monkeypatch):
    """wave_rung_wait(1) at jitter 0.3 is exactly 0.1625s (capped ladder rung 0.25)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.3)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(1) == pytest.approx(0.1625)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung1_jitter_04(monkeypatch):
    """wave_rung_wait(1) at jitter 0.4 is exactly 0.175s (capped ladder rung 0.25)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.4)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(1) == pytest.approx(0.175)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung1_jitter_05(monkeypatch):
    """wave_rung_wait(1) at jitter 0.5 is exactly 0.1875s (capped ladder rung 0.25)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.5)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(1) == pytest.approx(0.1875)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung1_jitter_06(monkeypatch):
    """wave_rung_wait(1) at jitter 0.6 is exactly 0.2s (capped ladder rung 0.25)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.6)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(1) == pytest.approx(0.2)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung1_jitter_07(monkeypatch):
    """wave_rung_wait(1) at jitter 0.7 is exactly 0.2125s (capped ladder rung 0.25)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.7)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(1) == pytest.approx(0.2125)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung1_jitter_08(monkeypatch):
    """wave_rung_wait(1) at jitter 0.8 is exactly 0.225s (capped ladder rung 0.25)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.8)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(1) == pytest.approx(0.225)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung1_jitter_09(monkeypatch):
    """wave_rung_wait(1) at jitter 0.9 is exactly 0.2375s (capped ladder rung 0.25)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.9)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(1) == pytest.approx(0.2375)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung1_jitter_10(monkeypatch):
    """wave_rung_wait(1) at jitter 1.0 is exactly 0.25s (capped ladder rung 0.25)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=1)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(1) == pytest.approx(0.25)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung2_jitter_00(monkeypatch):
    """wave_rung_wait(2) at jitter 0.0 is exactly 0.25s (capped ladder rung 0.5)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(2) == pytest.approx(0.25)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung2_jitter_01(monkeypatch):
    """wave_rung_wait(2) at jitter 0.1 is exactly 0.275s (capped ladder rung 0.5)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.1)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(2) == pytest.approx(0.275)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung2_jitter_02(monkeypatch):
    """wave_rung_wait(2) at jitter 0.2 is exactly 0.3s (capped ladder rung 0.5)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.2)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(2) == pytest.approx(0.3)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung2_jitter_03(monkeypatch):
    """wave_rung_wait(2) at jitter 0.3 is exactly 0.325s (capped ladder rung 0.5)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.3)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(2) == pytest.approx(0.325)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung2_jitter_04(monkeypatch):
    """wave_rung_wait(2) at jitter 0.4 is exactly 0.35s (capped ladder rung 0.5)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.4)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(2) == pytest.approx(0.35)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung2_jitter_05(monkeypatch):
    """wave_rung_wait(2) at jitter 0.5 is exactly 0.375s (capped ladder rung 0.5)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.5)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(2) == pytest.approx(0.375)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung2_jitter_06(monkeypatch):
    """wave_rung_wait(2) at jitter 0.6 is exactly 0.4s (capped ladder rung 0.5)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.6)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(2) == pytest.approx(0.4)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung2_jitter_07(monkeypatch):
    """wave_rung_wait(2) at jitter 0.7 is exactly 0.425s (capped ladder rung 0.5)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.7)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(2) == pytest.approx(0.425)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung2_jitter_08(monkeypatch):
    """wave_rung_wait(2) at jitter 0.8 is exactly 0.45s (capped ladder rung 0.5)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.8)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(2) == pytest.approx(0.45)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung2_jitter_09(monkeypatch):
    """wave_rung_wait(2) at jitter 0.9 is exactly 0.475s (capped ladder rung 0.5)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.9)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(2) == pytest.approx(0.475)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung2_jitter_10(monkeypatch):
    """wave_rung_wait(2) at jitter 1.0 is exactly 0.5s (capped ladder rung 0.5)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=1)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(2) == pytest.approx(0.5)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung3_jitter_00(monkeypatch):
    """wave_rung_wait(3) at jitter 0.0 is exactly 0.5s (capped ladder rung 1)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(3) == pytest.approx(0.5)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung3_jitter_01(monkeypatch):
    """wave_rung_wait(3) at jitter 0.1 is exactly 0.55s (capped ladder rung 1)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.1)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(3) == pytest.approx(0.55)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung3_jitter_02(monkeypatch):
    """wave_rung_wait(3) at jitter 0.2 is exactly 0.6s (capped ladder rung 1)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.2)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(3) == pytest.approx(0.6)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung3_jitter_03(monkeypatch):
    """wave_rung_wait(3) at jitter 0.3 is exactly 0.65s (capped ladder rung 1)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.3)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(3) == pytest.approx(0.65)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung3_jitter_04(monkeypatch):
    """wave_rung_wait(3) at jitter 0.4 is exactly 0.7s (capped ladder rung 1)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.4)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(3) == pytest.approx(0.7)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung3_jitter_05(monkeypatch):
    """wave_rung_wait(3) at jitter 0.5 is exactly 0.75s (capped ladder rung 1)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.5)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(3) == pytest.approx(0.75)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung3_jitter_06(monkeypatch):
    """wave_rung_wait(3) at jitter 0.6 is exactly 0.8s (capped ladder rung 1)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.6)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(3) == pytest.approx(0.8)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung3_jitter_07(monkeypatch):
    """wave_rung_wait(3) at jitter 0.7 is exactly 0.85s (capped ladder rung 1)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.7)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(3) == pytest.approx(0.85)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung3_jitter_08(monkeypatch):
    """wave_rung_wait(3) at jitter 0.8 is exactly 0.9s (capped ladder rung 1)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.8)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(3) == pytest.approx(0.9)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung3_jitter_09(monkeypatch):
    """wave_rung_wait(3) at jitter 0.9 is exactly 0.95s (capped ladder rung 1)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.9)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(3) == pytest.approx(0.95)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung3_jitter_10(monkeypatch):
    """wave_rung_wait(3) at jitter 1.0 is exactly 1s (capped ladder rung 1)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=1)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(3) == pytest.approx(1)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung4_jitter_00(monkeypatch):
    """wave_rung_wait(4) at jitter 0.0 is exactly 1s (capped ladder rung 2)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(4) == pytest.approx(1)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung4_jitter_01(monkeypatch):
    """wave_rung_wait(4) at jitter 0.1 is exactly 1.1s (capped ladder rung 2)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.1)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(4) == pytest.approx(1.1)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung4_jitter_02(monkeypatch):
    """wave_rung_wait(4) at jitter 0.2 is exactly 1.2s (capped ladder rung 2)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.2)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(4) == pytest.approx(1.2)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung4_jitter_03(monkeypatch):
    """wave_rung_wait(4) at jitter 0.3 is exactly 1.3s (capped ladder rung 2)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.3)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(4) == pytest.approx(1.3)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung4_jitter_04(monkeypatch):
    """wave_rung_wait(4) at jitter 0.4 is exactly 1.4s (capped ladder rung 2)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.4)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(4) == pytest.approx(1.4)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung4_jitter_05(monkeypatch):
    """wave_rung_wait(4) at jitter 0.5 is exactly 1.5s (capped ladder rung 2)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.5)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(4) == pytest.approx(1.5)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung4_jitter_06(monkeypatch):
    """wave_rung_wait(4) at jitter 0.6 is exactly 1.6s (capped ladder rung 2)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.6)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(4) == pytest.approx(1.6)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung4_jitter_07(monkeypatch):
    """wave_rung_wait(4) at jitter 0.7 is exactly 1.7s (capped ladder rung 2)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.7)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(4) == pytest.approx(1.7)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung4_jitter_08(monkeypatch):
    """wave_rung_wait(4) at jitter 0.8 is exactly 1.8s (capped ladder rung 2)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.8)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(4) == pytest.approx(1.8)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung4_jitter_09(monkeypatch):
    """wave_rung_wait(4) at jitter 0.9 is exactly 1.9s (capped ladder rung 2)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.9)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(4) == pytest.approx(1.9)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung4_jitter_10(monkeypatch):
    """wave_rung_wait(4) at jitter 1.0 is exactly 2s (capped ladder rung 2)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=1)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(4) == pytest.approx(2)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung5_jitter_00(monkeypatch):
    """wave_rung_wait(5) at jitter 0.0 is exactly 2s (capped ladder rung 4)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(5) == pytest.approx(2)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung5_jitter_01(monkeypatch):
    """wave_rung_wait(5) at jitter 0.1 is exactly 2.2s (capped ladder rung 4)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.1)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(5) == pytest.approx(2.2)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung5_jitter_02(monkeypatch):
    """wave_rung_wait(5) at jitter 0.2 is exactly 2.4s (capped ladder rung 4)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.2)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(5) == pytest.approx(2.4)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung5_jitter_03(monkeypatch):
    """wave_rung_wait(5) at jitter 0.3 is exactly 2.6s (capped ladder rung 4)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.3)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(5) == pytest.approx(2.6)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung5_jitter_04(monkeypatch):
    """wave_rung_wait(5) at jitter 0.4 is exactly 2.8s (capped ladder rung 4)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.4)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(5) == pytest.approx(2.8)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung5_jitter_05(monkeypatch):
    """wave_rung_wait(5) at jitter 0.5 is exactly 3s (capped ladder rung 4)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.5)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(5) == pytest.approx(3)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung5_jitter_06(monkeypatch):
    """wave_rung_wait(5) at jitter 0.6 is exactly 3.2s (capped ladder rung 4)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.6)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(5) == pytest.approx(3.2)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung5_jitter_07(monkeypatch):
    """wave_rung_wait(5) at jitter 0.7 is exactly 3.4s (capped ladder rung 4)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.7)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(5) == pytest.approx(3.4)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung5_jitter_08(monkeypatch):
    """wave_rung_wait(5) at jitter 0.8 is exactly 3.6s (capped ladder rung 4)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.8)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(5) == pytest.approx(3.6)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung5_jitter_09(monkeypatch):
    """wave_rung_wait(5) at jitter 0.9 is exactly 3.8s (capped ladder rung 4)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=0.9)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(5) == pytest.approx(3.8)
    assert clock.sleeps == []  # the wave wait never sleeps on its own


def test_wave_unit_arithmetic_rung5_jitter_10(monkeypatch):
    """wave_rung_wait(5) at jitter 1.0 is exactly 4s (capped ladder rung 4)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = _Clock(jitter=1)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    assert damper.wave_rung_wait(5) == pytest.approx(4)
    assert clock.sleeps == []  # the wave wait never sleeps on its own
