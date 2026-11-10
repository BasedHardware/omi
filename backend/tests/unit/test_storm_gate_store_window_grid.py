"""Store storm-window grid for the mid-ladder gate.

Every cell drives one real ``FirestoreStore.run`` entry on one real
operation label with an injected clock, and asserts the full sleep vector,
the mid-ladder log taxonomy, the retry-after stamp and the damper state the
gate leaves behind. The damper constants (``STORM_DAMPER_BASE_SECONDS`` etc.)
are read from the real module; rung and window expectations are computed at
generation time from the documented formulas and written as literals.

Failure-Class: FC-mid-ladder-retry-collides-inside-the-concurrently-armed-storm-window
"""

import logging
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import Aborted

from database import batch_pipeline_store as storage
from database.batch_pipeline_transaction_labels import require_operation_label
from database.firestore_transaction_retry import FirestoreContentionExhausted

BASE_SECONDS = storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS
CAP_SECONDS = storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS


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


def _make_store(monkeypatch, clock, *, label, aborts=2, arm_at=None, exhausting=False, dormant_env=None):
    """A dev store on the injected clock whose body aborts ``aborts`` times.

    ``arm_at`` (an attempt number or a list of them) makes the body arm the
    label's storm window mid-flight, exactly like a sibling's exhaustion
    would. ``dormant_env`` names a kill switch to turn off before the run.
    """
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
        if runs['n'] in arm_points:
            real_arm(label)
        if exhausting or runs['n'] <= aborts:
            raise Aborted('synthetic mid-chain contention')
        return 'committed'

    return store, damper, client, body


def test_grid_quiet_batch_provider_stt_jitter_000(monkeypatch):
    """batch_provider_stt (jitter 0.0): quiet chain rides bare rungs [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=2)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # bare rungs, no window anywhere


def test_grid_quiet_batch_provider_stt_jitter_025(monkeypatch):
    """batch_provider_stt (jitter 0.25): quiet chain rides bare rungs [0.125, 0.25]."""
    clock = _Clock(jitter=0.25)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=2)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.125, 0.25]  # bare rungs, no window anywhere


def test_grid_quiet_batch_provider_stt_jitter_050(monkeypatch):
    """batch_provider_stt (jitter 0.5): quiet chain rides bare rungs [0.15, 0.3]."""
    clock = _Clock(jitter=0.5)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=2)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.15, 0.3]  # bare rungs, no window anywhere


def test_grid_quiet_batch_provider_stt_jitter_075(monkeypatch):
    """batch_provider_stt (jitter 0.75): quiet chain rides bare rungs [0.175, 0.35]."""
    clock = _Clock(jitter=0.75)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=2)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.175, 0.35]  # bare rungs, no window anywhere


def test_grid_quiet_batch_provider_stt_jitter_100(monkeypatch):
    """batch_provider_stt (jitter 1.0): quiet chain rides bare rungs [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=2)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # bare rungs, no window anywhere


def test_grid_quiet_batch_merge_commit_jitter_000(monkeypatch):
    """batch_merge_commit (jitter 0.0): quiet chain rides bare rungs [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=2)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # bare rungs, no window anywhere


def test_grid_quiet_batch_merge_commit_jitter_025(monkeypatch):
    """batch_merge_commit (jitter 0.25): quiet chain rides bare rungs [0.125, 0.25]."""
    clock = _Clock(jitter=0.25)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=2)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.125, 0.25]  # bare rungs, no window anywhere


def test_grid_quiet_batch_merge_commit_jitter_050(monkeypatch):
    """batch_merge_commit (jitter 0.5): quiet chain rides bare rungs [0.15, 0.3]."""
    clock = _Clock(jitter=0.5)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=2)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.15, 0.3]  # bare rungs, no window anywhere


def test_grid_quiet_batch_merge_commit_jitter_075(monkeypatch):
    """batch_merge_commit (jitter 0.75): quiet chain rides bare rungs [0.175, 0.35]."""
    clock = _Clock(jitter=0.75)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=2)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.175, 0.35]  # bare rungs, no window anywhere


def test_grid_quiet_batch_merge_commit_jitter_100(monkeypatch):
    """batch_merge_commit (jitter 1.0): quiet chain rides bare rungs [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=2)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # bare rungs, no window anywhere


def test_grid_quiet_batch_recover_jitter_000(monkeypatch):
    """batch_recover (jitter 0.0): quiet chain rides bare rungs [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=2)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # bare rungs, no window anywhere


def test_grid_quiet_batch_recover_jitter_025(monkeypatch):
    """batch_recover (jitter 0.25): quiet chain rides bare rungs [0.125, 0.25]."""
    clock = _Clock(jitter=0.25)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=2)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.125, 0.25]  # bare rungs, no window anywhere


def test_grid_quiet_batch_recover_jitter_050(monkeypatch):
    """batch_recover (jitter 0.5): quiet chain rides bare rungs [0.15, 0.3]."""
    clock = _Clock(jitter=0.5)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=2)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.15, 0.3]  # bare rungs, no window anywhere


def test_grid_quiet_batch_recover_jitter_075(monkeypatch):
    """batch_recover (jitter 0.75): quiet chain rides bare rungs [0.175, 0.35]."""
    clock = _Clock(jitter=0.75)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=2)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.175, 0.35]  # bare rungs, no window anywhere


def test_grid_quiet_batch_recover_jitter_100(monkeypatch):
    """batch_recover (jitter 1.0): quiet chain rides bare rungs [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=2)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # bare rungs, no window anywhere


def test_grid_quiet_batch_fail_jitter_000(monkeypatch):
    """batch_fail (jitter 0.0): quiet chain rides bare rungs [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=2)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # bare rungs, no window anywhere


def test_grid_quiet_batch_fail_jitter_025(monkeypatch):
    """batch_fail (jitter 0.25): quiet chain rides bare rungs [0.125, 0.25]."""
    clock = _Clock(jitter=0.25)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=2)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.125, 0.25]  # bare rungs, no window anywhere


def test_grid_quiet_batch_fail_jitter_050(monkeypatch):
    """batch_fail (jitter 0.5): quiet chain rides bare rungs [0.15, 0.3]."""
    clock = _Clock(jitter=0.5)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=2)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.15, 0.3]  # bare rungs, no window anywhere


def test_grid_quiet_batch_fail_jitter_075(monkeypatch):
    """batch_fail (jitter 0.75): quiet chain rides bare rungs [0.175, 0.35]."""
    clock = _Clock(jitter=0.75)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=2)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.175, 0.35]  # bare rungs, no window anywhere


def test_grid_quiet_batch_fail_jitter_100(monkeypatch):
    """batch_fail (jitter 1.0): quiet chain rides bare rungs [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=2)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # bare rungs, no window anywhere


def test_grid_quiet_batch_complete_jitter_000(monkeypatch):
    """batch_complete (jitter 0.0): quiet chain rides bare rungs [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=2)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # bare rungs, no window anywhere


def test_grid_quiet_batch_complete_jitter_025(monkeypatch):
    """batch_complete (jitter 0.25): quiet chain rides bare rungs [0.125, 0.25]."""
    clock = _Clock(jitter=0.25)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=2)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.125, 0.25]  # bare rungs, no window anywhere


def test_grid_quiet_batch_complete_jitter_050(monkeypatch):
    """batch_complete (jitter 0.5): quiet chain rides bare rungs [0.15, 0.3]."""
    clock = _Clock(jitter=0.5)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=2)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.15, 0.3]  # bare rungs, no window anywhere


def test_grid_quiet_batch_complete_jitter_075(monkeypatch):
    """batch_complete (jitter 0.75): quiet chain rides bare rungs [0.175, 0.35]."""
    clock = _Clock(jitter=0.75)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=2)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.175, 0.35]  # bare rungs, no window anywhere


def test_grid_quiet_batch_complete_jitter_100(monkeypatch):
    """batch_complete (jitter 1.0): quiet chain rides bare rungs [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=2)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # bare rungs, no window anywhere


def test_grid_quiet_batch_defer_jitter_000(monkeypatch):
    """batch_defer (jitter 0.0): quiet chain rides bare rungs [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=2)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # bare rungs, no window anywhere


def test_grid_quiet_batch_defer_jitter_025(monkeypatch):
    """batch_defer (jitter 0.25): quiet chain rides bare rungs [0.125, 0.25]."""
    clock = _Clock(jitter=0.25)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=2)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.125, 0.25]  # bare rungs, no window anywhere


def test_grid_quiet_batch_defer_jitter_050(monkeypatch):
    """batch_defer (jitter 0.5): quiet chain rides bare rungs [0.15, 0.3]."""
    clock = _Clock(jitter=0.5)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=2)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.15, 0.3]  # bare rungs, no window anywhere


def test_grid_quiet_batch_defer_jitter_075(monkeypatch):
    """batch_defer (jitter 0.75): quiet chain rides bare rungs [0.175, 0.35]."""
    clock = _Clock(jitter=0.75)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=2)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.175, 0.35]  # bare rungs, no window anywhere


def test_grid_quiet_batch_defer_jitter_100(monkeypatch):
    """batch_defer (jitter 1.0): quiet chain rides bare rungs [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=2)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # bare rungs, no window anywhere


def test_grid_quiet_batch_heartbeat_jitter_000(monkeypatch):
    """batch_heartbeat (jitter 0.0): quiet chain rides bare rungs [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_heartbeat', aborts=2)
    assert store.run(body, operation='batch_heartbeat') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # bare rungs, no window anywhere


def test_grid_quiet_batch_heartbeat_jitter_025(monkeypatch):
    """batch_heartbeat (jitter 0.25): quiet chain rides bare rungs [0.125, 0.25]."""
    clock = _Clock(jitter=0.25)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_heartbeat', aborts=2)
    assert store.run(body, operation='batch_heartbeat') == 'committed'
    assert clock.sleeps == [0.125, 0.25]  # bare rungs, no window anywhere


def test_grid_quiet_batch_heartbeat_jitter_050(monkeypatch):
    """batch_heartbeat (jitter 0.5): quiet chain rides bare rungs [0.15, 0.3]."""
    clock = _Clock(jitter=0.5)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_heartbeat', aborts=2)
    assert store.run(body, operation='batch_heartbeat') == 'committed'
    assert clock.sleeps == [0.15, 0.3]  # bare rungs, no window anywhere


def test_grid_quiet_batch_heartbeat_jitter_075(monkeypatch):
    """batch_heartbeat (jitter 0.75): quiet chain rides bare rungs [0.175, 0.35]."""
    clock = _Clock(jitter=0.75)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_heartbeat', aborts=2)
    assert store.run(body, operation='batch_heartbeat') == 'committed'
    assert clock.sleeps == [0.175, 0.35]  # bare rungs, no window anywhere


def test_grid_quiet_batch_heartbeat_jitter_100(monkeypatch):
    """batch_heartbeat (jitter 1.0): quiet chain rides bare rungs [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_heartbeat', aborts=2)
    assert store.run(body, operation='batch_heartbeat') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # bare rungs, no window anywhere


def test_grid_quiet_batch_admit_jitter_000(monkeypatch):
    """batch_admit (jitter 0.0): quiet chain rides bare rungs [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=2)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # bare rungs, no window anywhere


def test_grid_quiet_batch_admit_jitter_025(monkeypatch):
    """batch_admit (jitter 0.25): quiet chain rides bare rungs [0.125, 0.25]."""
    clock = _Clock(jitter=0.25)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=2)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.125, 0.25]  # bare rungs, no window anywhere


def test_grid_quiet_batch_admit_jitter_050(monkeypatch):
    """batch_admit (jitter 0.5): quiet chain rides bare rungs [0.15, 0.3]."""
    clock = _Clock(jitter=0.5)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=2)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.15, 0.3]  # bare rungs, no window anywhere


def test_grid_quiet_batch_admit_jitter_075(monkeypatch):
    """batch_admit (jitter 0.75): quiet chain rides bare rungs [0.175, 0.35]."""
    clock = _Clock(jitter=0.75)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=2)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.175, 0.35]  # bare rungs, no window anywhere


def test_grid_quiet_batch_admit_jitter_100(monkeypatch):
    """batch_admit (jitter 1.0): quiet chain rides bare rungs [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=2)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # bare rungs, no window anywhere


def test_grid_quiet_batch_enqueue_jitter_000(monkeypatch):
    """batch_enqueue (jitter 0.0): quiet chain rides bare rungs [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_enqueue', aborts=2)
    assert store.run(body, operation='batch_enqueue') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # bare rungs, no window anywhere


def test_grid_quiet_batch_enqueue_jitter_025(monkeypatch):
    """batch_enqueue (jitter 0.25): quiet chain rides bare rungs [0.125, 0.25]."""
    clock = _Clock(jitter=0.25)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_enqueue', aborts=2)
    assert store.run(body, operation='batch_enqueue') == 'committed'
    assert clock.sleeps == [0.125, 0.25]  # bare rungs, no window anywhere


def test_grid_quiet_batch_enqueue_jitter_050(monkeypatch):
    """batch_enqueue (jitter 0.5): quiet chain rides bare rungs [0.15, 0.3]."""
    clock = _Clock(jitter=0.5)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_enqueue', aborts=2)
    assert store.run(body, operation='batch_enqueue') == 'committed'
    assert clock.sleeps == [0.15, 0.3]  # bare rungs, no window anywhere


def test_grid_quiet_batch_enqueue_jitter_075(monkeypatch):
    """batch_enqueue (jitter 0.75): quiet chain rides bare rungs [0.175, 0.35]."""
    clock = _Clock(jitter=0.75)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_enqueue', aborts=2)
    assert store.run(body, operation='batch_enqueue') == 'committed'
    assert clock.sleeps == [0.175, 0.35]  # bare rungs, no window anywhere


def test_grid_quiet_batch_enqueue_jitter_100(monkeypatch):
    """batch_enqueue (jitter 1.0): quiet chain rides bare rungs [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_enqueue', aborts=2)
    assert store.run(body, operation='batch_enqueue') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # bare rungs, no window anywhere


def test_grid_quiet_batch_intake_status_jitter_000(monkeypatch):
    """batch_intake_status (jitter 0.0): quiet chain rides bare rungs [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=2)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # bare rungs, no window anywhere


def test_grid_quiet_batch_intake_status_jitter_025(monkeypatch):
    """batch_intake_status (jitter 0.25): quiet chain rides bare rungs [0.125, 0.25]."""
    clock = _Clock(jitter=0.25)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=2)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.125, 0.25]  # bare rungs, no window anywhere


def test_grid_quiet_batch_intake_status_jitter_050(monkeypatch):
    """batch_intake_status (jitter 0.5): quiet chain rides bare rungs [0.15, 0.3]."""
    clock = _Clock(jitter=0.5)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=2)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.15, 0.3]  # bare rungs, no window anywhere


def test_grid_quiet_batch_intake_status_jitter_075(monkeypatch):
    """batch_intake_status (jitter 0.75): quiet chain rides bare rungs [0.175, 0.35]."""
    clock = _Clock(jitter=0.75)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=2)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.175, 0.35]  # bare rungs, no window anywhere


def test_grid_quiet_batch_intake_status_jitter_100(monkeypatch):
    """batch_intake_status (jitter 1.0): quiet chain rides bare rungs [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=2)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # bare rungs, no window anywhere


def test_grid_quiet_batch_seal_register_jitter_000(monkeypatch):
    """batch_seal_register (jitter 0.0): quiet chain rides bare rungs [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=2)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # bare rungs, no window anywhere


def test_grid_quiet_batch_seal_register_jitter_025(monkeypatch):
    """batch_seal_register (jitter 0.25): quiet chain rides bare rungs [0.125, 0.25]."""
    clock = _Clock(jitter=0.25)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=2)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.125, 0.25]  # bare rungs, no window anywhere


def test_grid_quiet_batch_seal_register_jitter_050(monkeypatch):
    """batch_seal_register (jitter 0.5): quiet chain rides bare rungs [0.15, 0.3]."""
    clock = _Clock(jitter=0.5)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=2)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.15, 0.3]  # bare rungs, no window anywhere


def test_grid_quiet_batch_seal_register_jitter_075(monkeypatch):
    """batch_seal_register (jitter 0.75): quiet chain rides bare rungs [0.175, 0.35]."""
    clock = _Clock(jitter=0.75)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=2)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.175, 0.35]  # bare rungs, no window anywhere


def test_grid_quiet_batch_seal_register_jitter_100(monkeypatch):
    """batch_seal_register (jitter 1.0): quiet chain rides bare rungs [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=2)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # bare rungs, no window anywhere


def test_grid_quiet_batch_release_jitter_000(monkeypatch):
    """batch_release (jitter 0.0): quiet chain rides bare rungs [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=2)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # bare rungs, no window anywhere


def test_grid_quiet_batch_release_jitter_025(monkeypatch):
    """batch_release (jitter 0.25): quiet chain rides bare rungs [0.125, 0.25]."""
    clock = _Clock(jitter=0.25)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=2)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.125, 0.25]  # bare rungs, no window anywhere


def test_grid_quiet_batch_release_jitter_050(monkeypatch):
    """batch_release (jitter 0.5): quiet chain rides bare rungs [0.15, 0.3]."""
    clock = _Clock(jitter=0.5)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=2)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.15, 0.3]  # bare rungs, no window anywhere


def test_grid_quiet_batch_release_jitter_075(monkeypatch):
    """batch_release (jitter 0.75): quiet chain rides bare rungs [0.175, 0.35]."""
    clock = _Clock(jitter=0.75)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=2)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.175, 0.35]  # bare rungs, no window anywhere


def test_grid_quiet_batch_release_jitter_100(monkeypatch):
    """batch_release (jitter 1.0): quiet chain rides bare rungs [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=2)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # bare rungs, no window anywhere


def test_grid_quiet_batch_redrive_jitter_000(monkeypatch):
    """batch_redrive (jitter 0.0): quiet chain rides bare rungs [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=2)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # bare rungs, no window anywhere


def test_grid_quiet_batch_redrive_jitter_025(monkeypatch):
    """batch_redrive (jitter 0.25): quiet chain rides bare rungs [0.125, 0.25]."""
    clock = _Clock(jitter=0.25)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=2)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.125, 0.25]  # bare rungs, no window anywhere


def test_grid_quiet_batch_redrive_jitter_050(monkeypatch):
    """batch_redrive (jitter 0.5): quiet chain rides bare rungs [0.15, 0.3]."""
    clock = _Clock(jitter=0.5)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=2)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.15, 0.3]  # bare rungs, no window anywhere


def test_grid_quiet_batch_redrive_jitter_075(monkeypatch):
    """batch_redrive (jitter 0.75): quiet chain rides bare rungs [0.175, 0.35]."""
    clock = _Clock(jitter=0.75)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=2)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.175, 0.35]  # bare rungs, no window anywhere


def test_grid_quiet_batch_redrive_jitter_100(monkeypatch):
    """batch_redrive (jitter 1.0): quiet chain rides bare rungs [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=2)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # bare rungs, no window anywhere


def test_grid_quiet_batch_pull_shard_scheduler_00_jitter_000(monkeypatch):
    """batch_pull shard=scheduler_00 (jitter 0.0): quiet chain rides bare rungs [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_pull shard=scheduler_00', aborts=2)
    assert store.run(body, operation='batch_pull shard=scheduler_00') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # bare rungs, no window anywhere


def test_grid_quiet_batch_pull_shard_scheduler_00_jitter_025(monkeypatch):
    """batch_pull shard=scheduler_00 (jitter 0.25): quiet chain rides bare rungs [0.125, 0.25]."""
    clock = _Clock(jitter=0.25)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_pull shard=scheduler_00', aborts=2)
    assert store.run(body, operation='batch_pull shard=scheduler_00') == 'committed'
    assert clock.sleeps == [0.125, 0.25]  # bare rungs, no window anywhere


def test_grid_quiet_batch_pull_shard_scheduler_00_jitter_050(monkeypatch):
    """batch_pull shard=scheduler_00 (jitter 0.5): quiet chain rides bare rungs [0.15, 0.3]."""
    clock = _Clock(jitter=0.5)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_pull shard=scheduler_00', aborts=2)
    assert store.run(body, operation='batch_pull shard=scheduler_00') == 'committed'
    assert clock.sleeps == [0.15, 0.3]  # bare rungs, no window anywhere


def test_grid_quiet_batch_pull_shard_scheduler_00_jitter_075(monkeypatch):
    """batch_pull shard=scheduler_00 (jitter 0.75): quiet chain rides bare rungs [0.175, 0.35]."""
    clock = _Clock(jitter=0.75)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_pull shard=scheduler_00', aborts=2)
    assert store.run(body, operation='batch_pull shard=scheduler_00') == 'committed'
    assert clock.sleeps == [0.175, 0.35]  # bare rungs, no window anywhere


def test_grid_quiet_batch_pull_shard_scheduler_00_jitter_100(monkeypatch):
    """batch_pull shard=scheduler_00 (jitter 1.0): quiet chain rides bare rungs [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_pull shard=scheduler_00', aborts=2)
    assert store.run(body, operation='batch_pull shard=scheduler_00') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # bare rungs, no window anywhere


def test_grid_sibling_arm2_batch_provider_stt_jitter_000(monkeypatch):
    """batch_provider_stt (jitter 0.0): sibling arms during attempt 2; rung 2 waits 0.125s out of the window."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.1, 0.325]  # rung 2 carries the sibling window 0.125


def test_grid_sibling_arm2_batch_provider_stt_jitter_100(monkeypatch):
    """batch_provider_stt (jitter 1.0): sibling arms during attempt 2; rung 2 waits 0.25s out of the window."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.2, 0.65]  # rung 2 carries the sibling window 0.25


def test_grid_sibling_arm2_batch_merge_commit_jitter_000(monkeypatch):
    """batch_merge_commit (jitter 0.0): sibling arms during attempt 2; rung 2 waits 0.125s out of the window."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.1, 0.325]  # rung 2 carries the sibling window 0.125


def test_grid_sibling_arm2_batch_merge_commit_jitter_100(monkeypatch):
    """batch_merge_commit (jitter 1.0): sibling arms during attempt 2; rung 2 waits 0.25s out of the window."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.2, 0.65]  # rung 2 carries the sibling window 0.25


def test_grid_sibling_arm2_batch_recover_jitter_000(monkeypatch):
    """batch_recover (jitter 0.0): sibling arms during attempt 2; rung 2 waits 0.125s out of the window."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.1, 0.325]  # rung 2 carries the sibling window 0.125


def test_grid_sibling_arm2_batch_recover_jitter_100(monkeypatch):
    """batch_recover (jitter 1.0): sibling arms during attempt 2; rung 2 waits 0.25s out of the window."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.2, 0.65]  # rung 2 carries the sibling window 0.25


def test_grid_sibling_arm2_batch_fail_jitter_000(monkeypatch):
    """batch_fail (jitter 0.0): sibling arms during attempt 2; rung 2 waits 0.125s out of the window."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.1, 0.325]  # rung 2 carries the sibling window 0.125


def test_grid_sibling_arm2_batch_fail_jitter_100(monkeypatch):
    """batch_fail (jitter 1.0): sibling arms during attempt 2; rung 2 waits 0.25s out of the window."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.2, 0.65]  # rung 2 carries the sibling window 0.25


def test_grid_sibling_arm2_batch_complete_jitter_000(monkeypatch):
    """batch_complete (jitter 0.0): sibling arms during attempt 2; rung 2 waits 0.125s out of the window."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.1, 0.325]  # rung 2 carries the sibling window 0.125


def test_grid_sibling_arm2_batch_complete_jitter_100(monkeypatch):
    """batch_complete (jitter 1.0): sibling arms during attempt 2; rung 2 waits 0.25s out of the window."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.2, 0.65]  # rung 2 carries the sibling window 0.25


def test_grid_sibling_arm2_batch_defer_jitter_000(monkeypatch):
    """batch_defer (jitter 0.0): sibling arms during attempt 2; rung 2 waits 0.125s out of the window."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.1, 0.325]  # rung 2 carries the sibling window 0.125


def test_grid_sibling_arm2_batch_defer_jitter_100(monkeypatch):
    """batch_defer (jitter 1.0): sibling arms during attempt 2; rung 2 waits 0.25s out of the window."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.2, 0.65]  # rung 2 carries the sibling window 0.25


def test_grid_sibling_arm2_batch_heartbeat_jitter_000(monkeypatch):
    """batch_heartbeat (jitter 0.0): sibling arms during attempt 2; rung 2 waits 0.125s out of the window."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_heartbeat', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_heartbeat') == 'committed'
    assert clock.sleeps == [0.1, 0.325]  # rung 2 carries the sibling window 0.125


def test_grid_sibling_arm2_batch_heartbeat_jitter_100(monkeypatch):
    """batch_heartbeat (jitter 1.0): sibling arms during attempt 2; rung 2 waits 0.25s out of the window."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_heartbeat', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_heartbeat') == 'committed'
    assert clock.sleeps == [0.2, 0.65]  # rung 2 carries the sibling window 0.25


def test_grid_sibling_arm2_batch_admit_jitter_000(monkeypatch):
    """batch_admit (jitter 0.0): sibling arms during attempt 2; rung 2 waits 0.125s out of the window."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.1, 0.325]  # rung 2 carries the sibling window 0.125


def test_grid_sibling_arm2_batch_admit_jitter_100(monkeypatch):
    """batch_admit (jitter 1.0): sibling arms during attempt 2; rung 2 waits 0.25s out of the window."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.2, 0.65]  # rung 2 carries the sibling window 0.25


def test_grid_sibling_arm2_batch_enqueue_jitter_000(monkeypatch):
    """batch_enqueue (jitter 0.0): sibling arms during attempt 2; rung 2 waits 0.125s out of the window."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_enqueue', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_enqueue') == 'committed'
    assert clock.sleeps == [0.1, 0.325]  # rung 2 carries the sibling window 0.125


def test_grid_sibling_arm2_batch_enqueue_jitter_100(monkeypatch):
    """batch_enqueue (jitter 1.0): sibling arms during attempt 2; rung 2 waits 0.25s out of the window."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_enqueue', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_enqueue') == 'committed'
    assert clock.sleeps == [0.2, 0.65]  # rung 2 carries the sibling window 0.25


def test_grid_sibling_arm2_batch_intake_status_jitter_000(monkeypatch):
    """batch_intake_status (jitter 0.0): sibling arms during attempt 2; rung 2 waits 0.125s out of the window."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.1, 0.325]  # rung 2 carries the sibling window 0.125


def test_grid_sibling_arm2_batch_intake_status_jitter_100(monkeypatch):
    """batch_intake_status (jitter 1.0): sibling arms during attempt 2; rung 2 waits 0.25s out of the window."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.2, 0.65]  # rung 2 carries the sibling window 0.25


def test_grid_sibling_arm2_batch_seal_register_jitter_000(monkeypatch):
    """batch_seal_register (jitter 0.0): sibling arms during attempt 2; rung 2 waits 0.125s out of the window."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.1, 0.325]  # rung 2 carries the sibling window 0.125


def test_grid_sibling_arm2_batch_seal_register_jitter_100(monkeypatch):
    """batch_seal_register (jitter 1.0): sibling arms during attempt 2; rung 2 waits 0.25s out of the window."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.2, 0.65]  # rung 2 carries the sibling window 0.25


def test_grid_sibling_arm2_batch_release_jitter_000(monkeypatch):
    """batch_release (jitter 0.0): sibling arms during attempt 2; rung 2 waits 0.125s out of the window."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.1, 0.325]  # rung 2 carries the sibling window 0.125


def test_grid_sibling_arm2_batch_release_jitter_100(monkeypatch):
    """batch_release (jitter 1.0): sibling arms during attempt 2; rung 2 waits 0.25s out of the window."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.2, 0.65]  # rung 2 carries the sibling window 0.25


def test_grid_sibling_arm2_batch_redrive_jitter_000(monkeypatch):
    """batch_redrive (jitter 0.0): sibling arms during attempt 2; rung 2 waits 0.125s out of the window."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.1, 0.325]  # rung 2 carries the sibling window 0.125


def test_grid_sibling_arm2_batch_redrive_jitter_100(monkeypatch):
    """batch_redrive (jitter 1.0): sibling arms during attempt 2; rung 2 waits 0.25s out of the window."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.2, 0.65]  # rung 2 carries the sibling window 0.25


def test_grid_sibling_arm2_batch_pull_shard_scheduler_00_jitter_000(monkeypatch):
    """batch_pull shard=scheduler_00 (jitter 0.0): sibling arms during attempt 2; rung 2 waits 0.125s out of the window."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_pull shard=scheduler_00', aborts=2, arm_at=2
    )
    assert store.run(body, operation='batch_pull shard=scheduler_00') == 'committed'
    assert clock.sleeps == [0.1, 0.325]  # rung 2 carries the sibling window 0.125


def test_grid_sibling_arm2_batch_pull_shard_scheduler_00_jitter_100(monkeypatch):
    """batch_pull shard=scheduler_00 (jitter 1.0): sibling arms during attempt 2; rung 2 waits 0.25s out of the window."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_pull shard=scheduler_00', aborts=2, arm_at=2
    )
    assert store.run(body, operation='batch_pull shard=scheduler_00') == 'committed'
    assert clock.sleeps == [0.2, 0.65]  # rung 2 carries the sibling window 0.25


def test_grid_sibling_arm3_batch_provider_stt_jitter_000(monkeypatch):
    """batch_provider_stt (jitter 0.0): sibling arms during attempt 3; rungs 1-2 stay bare."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=3, arm_at=3)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9]  # rung 3 rides the max of the sibling window and its own wave wait


def test_grid_sibling_arm3_batch_provider_stt_jitter_100(monkeypatch):
    """batch_provider_stt (jitter 1.0): sibling arms during attempt 3; rungs 1-2 stay bare."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=3, arm_at=3)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8]  # rung 3 rides the max of the sibling window and its own wave wait


def test_grid_sibling_arm3_batch_merge_commit_jitter_000(monkeypatch):
    """batch_merge_commit (jitter 0.0): sibling arms during attempt 3; rungs 1-2 stay bare."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=3, arm_at=3)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9]  # rung 3 rides the max of the sibling window and its own wave wait


def test_grid_sibling_arm3_batch_merge_commit_jitter_100(monkeypatch):
    """batch_merge_commit (jitter 1.0): sibling arms during attempt 3; rungs 1-2 stay bare."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=3, arm_at=3)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8]  # rung 3 rides the max of the sibling window and its own wave wait


def test_grid_sibling_arm3_batch_recover_jitter_000(monkeypatch):
    """batch_recover (jitter 0.0): sibling arms during attempt 3; rungs 1-2 stay bare."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=3, arm_at=3)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9]  # rung 3 rides the max of the sibling window and its own wave wait


def test_grid_sibling_arm3_batch_recover_jitter_100(monkeypatch):
    """batch_recover (jitter 1.0): sibling arms during attempt 3; rungs 1-2 stay bare."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=3, arm_at=3)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8]  # rung 3 rides the max of the sibling window and its own wave wait


def test_grid_sibling_arm3_batch_fail_jitter_000(monkeypatch):
    """batch_fail (jitter 0.0): sibling arms during attempt 3; rungs 1-2 stay bare."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=3, arm_at=3)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9]  # rung 3 rides the max of the sibling window and its own wave wait


def test_grid_sibling_arm3_batch_fail_jitter_100(monkeypatch):
    """batch_fail (jitter 1.0): sibling arms during attempt 3; rungs 1-2 stay bare."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=3, arm_at=3)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8]  # rung 3 rides the max of the sibling window and its own wave wait


def test_grid_sibling_arm3_batch_complete_jitter_000(monkeypatch):
    """batch_complete (jitter 0.0): sibling arms during attempt 3; rungs 1-2 stay bare."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=3, arm_at=3)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9]  # rung 3 rides the max of the sibling window and its own wave wait


def test_grid_sibling_arm3_batch_complete_jitter_100(monkeypatch):
    """batch_complete (jitter 1.0): sibling arms during attempt 3; rungs 1-2 stay bare."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=3, arm_at=3)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8]  # rung 3 rides the max of the sibling window and its own wave wait


def test_grid_sibling_arm3_batch_defer_jitter_000(monkeypatch):
    """batch_defer (jitter 0.0): sibling arms during attempt 3; rungs 1-2 stay bare."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=3, arm_at=3)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9]  # rung 3 rides the max of the sibling window and its own wave wait


def test_grid_sibling_arm3_batch_defer_jitter_100(monkeypatch):
    """batch_defer (jitter 1.0): sibling arms during attempt 3; rungs 1-2 stay bare."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=3, arm_at=3)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8]  # rung 3 rides the max of the sibling window and its own wave wait


def test_grid_sibling_arm3_batch_heartbeat_jitter_000(monkeypatch):
    """batch_heartbeat (jitter 0.0): sibling arms during attempt 3; rungs 1-2 stay bare."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_heartbeat', aborts=3, arm_at=3)
    assert store.run(body, operation='batch_heartbeat') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9]  # rung 3 rides the max of the sibling window and its own wave wait


def test_grid_sibling_arm3_batch_heartbeat_jitter_100(monkeypatch):
    """batch_heartbeat (jitter 1.0): sibling arms during attempt 3; rungs 1-2 stay bare."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_heartbeat', aborts=3, arm_at=3)
    assert store.run(body, operation='batch_heartbeat') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8]  # rung 3 rides the max of the sibling window and its own wave wait


def test_grid_sibling_arm3_batch_admit_jitter_000(monkeypatch):
    """batch_admit (jitter 0.0): sibling arms during attempt 3; rungs 1-2 stay bare."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=3, arm_at=3)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9]  # rung 3 rides the max of the sibling window and its own wave wait


def test_grid_sibling_arm3_batch_admit_jitter_100(monkeypatch):
    """batch_admit (jitter 1.0): sibling arms during attempt 3; rungs 1-2 stay bare."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=3, arm_at=3)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8]  # rung 3 rides the max of the sibling window and its own wave wait


def test_grid_sibling_arm3_batch_enqueue_jitter_000(monkeypatch):
    """batch_enqueue (jitter 0.0): sibling arms during attempt 3; rungs 1-2 stay bare."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_enqueue', aborts=3, arm_at=3)
    assert store.run(body, operation='batch_enqueue') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9]  # rung 3 rides the max of the sibling window and its own wave wait


def test_grid_sibling_arm3_batch_enqueue_jitter_100(monkeypatch):
    """batch_enqueue (jitter 1.0): sibling arms during attempt 3; rungs 1-2 stay bare."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_enqueue', aborts=3, arm_at=3)
    assert store.run(body, operation='batch_enqueue') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8]  # rung 3 rides the max of the sibling window and its own wave wait


def test_grid_sibling_arm3_batch_intake_status_jitter_000(monkeypatch):
    """batch_intake_status (jitter 0.0): sibling arms during attempt 3; rungs 1-2 stay bare."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=3, arm_at=3)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9]  # rung 3 rides the max of the sibling window and its own wave wait


def test_grid_sibling_arm3_batch_intake_status_jitter_100(monkeypatch):
    """batch_intake_status (jitter 1.0): sibling arms during attempt 3; rungs 1-2 stay bare."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=3, arm_at=3)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8]  # rung 3 rides the max of the sibling window and its own wave wait


def test_grid_sibling_arm3_batch_seal_register_jitter_000(monkeypatch):
    """batch_seal_register (jitter 0.0): sibling arms during attempt 3; rungs 1-2 stay bare."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=3, arm_at=3)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9]  # rung 3 rides the max of the sibling window and its own wave wait


def test_grid_sibling_arm3_batch_seal_register_jitter_100(monkeypatch):
    """batch_seal_register (jitter 1.0): sibling arms during attempt 3; rungs 1-2 stay bare."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=3, arm_at=3)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8]  # rung 3 rides the max of the sibling window and its own wave wait


def test_grid_sibling_arm3_batch_release_jitter_000(monkeypatch):
    """batch_release (jitter 0.0): sibling arms during attempt 3; rungs 1-2 stay bare."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=3, arm_at=3)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9]  # rung 3 rides the max of the sibling window and its own wave wait


def test_grid_sibling_arm3_batch_release_jitter_100(monkeypatch):
    """batch_release (jitter 1.0): sibling arms during attempt 3; rungs 1-2 stay bare."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=3, arm_at=3)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8]  # rung 3 rides the max of the sibling window and its own wave wait


def test_grid_sibling_arm3_batch_redrive_jitter_000(monkeypatch):
    """batch_redrive (jitter 0.0): sibling arms during attempt 3; rungs 1-2 stay bare."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=3, arm_at=3)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9]  # rung 3 rides the max of the sibling window and its own wave wait


def test_grid_sibling_arm3_batch_redrive_jitter_100(monkeypatch):
    """batch_redrive (jitter 1.0): sibling arms during attempt 3; rungs 1-2 stay bare."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=3, arm_at=3)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8]  # rung 3 rides the max of the sibling window and its own wave wait


def test_grid_sibling_arm3_batch_pull_shard_scheduler_00_jitter_000(monkeypatch):
    """batch_pull shard=scheduler_00 (jitter 0.0): sibling arms during attempt 3; rungs 1-2 stay bare."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_pull shard=scheduler_00', aborts=3, arm_at=3
    )
    assert store.run(body, operation='batch_pull shard=scheduler_00') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9]  # rung 3 rides the max of the sibling window and its own wave wait


def test_grid_sibling_arm3_batch_pull_shard_scheduler_00_jitter_100(monkeypatch):
    """batch_pull shard=scheduler_00 (jitter 1.0): sibling arms during attempt 3; rungs 1-2 stay bare."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_pull shard=scheduler_00', aborts=3, arm_at=3
    )
    assert store.run(body, operation='batch_pull shard=scheduler_00') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8]  # rung 3 rides the max of the sibling window and its own wave wait


def test_grid_sibling_arm4_lands_batch_provider_stt_jitter_000(monkeypatch):
    """batch_provider_stt (jitter 0.0): sibling arms during the committing attempt 4 - no rung follows, so no gate wait."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=3, arm_at=4)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    # arm at attempt 4: rungs 1-2 bare, rung 3 rides its wave wait, the
    # chain lands on the ungated committing attempt
    assert clock.sleeps == [0.1, 0.2, 0.9]


def test_grid_sibling_arm4_lands_batch_provider_stt_jitter_100(monkeypatch):
    """batch_provider_stt (jitter 1.0): sibling arms during the committing attempt 4 - no rung follows, so no gate wait."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=3, arm_at=4)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    # arm at attempt 4: rungs 1-2 bare, rung 3 rides its wave wait, the
    # chain lands on the ungated committing attempt
    assert clock.sleeps == [0.2, 0.4, 1.8]


def test_grid_sibling_arm4_lands_batch_merge_commit_jitter_000(monkeypatch):
    """batch_merge_commit (jitter 0.0): sibling arms during the committing attempt 4 - no rung follows, so no gate wait."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=3, arm_at=4)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    # arm at attempt 4: rungs 1-2 bare, rung 3 rides its wave wait, the
    # chain lands on the ungated committing attempt
    assert clock.sleeps == [0.1, 0.2, 0.9]


def test_grid_sibling_arm4_lands_batch_merge_commit_jitter_100(monkeypatch):
    """batch_merge_commit (jitter 1.0): sibling arms during the committing attempt 4 - no rung follows, so no gate wait."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=3, arm_at=4)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    # arm at attempt 4: rungs 1-2 bare, rung 3 rides its wave wait, the
    # chain lands on the ungated committing attempt
    assert clock.sleeps == [0.2, 0.4, 1.8]


def test_grid_sibling_arm4_lands_batch_recover_jitter_000(monkeypatch):
    """batch_recover (jitter 0.0): sibling arms during the committing attempt 4 - no rung follows, so no gate wait."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=3, arm_at=4)
    assert store.run(body, operation='batch_recover') == 'committed'
    # arm at attempt 4: rungs 1-2 bare, rung 3 rides its wave wait, the
    # chain lands on the ungated committing attempt
    assert clock.sleeps == [0.1, 0.2, 0.9]


def test_grid_sibling_arm4_lands_batch_recover_jitter_100(monkeypatch):
    """batch_recover (jitter 1.0): sibling arms during the committing attempt 4 - no rung follows, so no gate wait."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=3, arm_at=4)
    assert store.run(body, operation='batch_recover') == 'committed'
    # arm at attempt 4: rungs 1-2 bare, rung 3 rides its wave wait, the
    # chain lands on the ungated committing attempt
    assert clock.sleeps == [0.2, 0.4, 1.8]


def test_grid_sibling_arm4_lands_batch_fail_jitter_000(monkeypatch):
    """batch_fail (jitter 0.0): sibling arms during the committing attempt 4 - no rung follows, so no gate wait."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=3, arm_at=4)
    assert store.run(body, operation='batch_fail') == 'committed'
    # arm at attempt 4: rungs 1-2 bare, rung 3 rides its wave wait, the
    # chain lands on the ungated committing attempt
    assert clock.sleeps == [0.1, 0.2, 0.9]


def test_grid_sibling_arm4_lands_batch_fail_jitter_100(monkeypatch):
    """batch_fail (jitter 1.0): sibling arms during the committing attempt 4 - no rung follows, so no gate wait."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=3, arm_at=4)
    assert store.run(body, operation='batch_fail') == 'committed'
    # arm at attempt 4: rungs 1-2 bare, rung 3 rides its wave wait, the
    # chain lands on the ungated committing attempt
    assert clock.sleeps == [0.2, 0.4, 1.8]


def test_grid_sibling_arm4_lands_batch_complete_jitter_000(monkeypatch):
    """batch_complete (jitter 0.0): sibling arms during the committing attempt 4 - no rung follows, so no gate wait."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=3, arm_at=4)
    assert store.run(body, operation='batch_complete') == 'committed'
    # arm at attempt 4: rungs 1-2 bare, rung 3 rides its wave wait, the
    # chain lands on the ungated committing attempt
    assert clock.sleeps == [0.1, 0.2, 0.9]


def test_grid_sibling_arm4_lands_batch_complete_jitter_100(monkeypatch):
    """batch_complete (jitter 1.0): sibling arms during the committing attempt 4 - no rung follows, so no gate wait."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=3, arm_at=4)
    assert store.run(body, operation='batch_complete') == 'committed'
    # arm at attempt 4: rungs 1-2 bare, rung 3 rides its wave wait, the
    # chain lands on the ungated committing attempt
    assert clock.sleeps == [0.2, 0.4, 1.8]


def test_grid_sibling_arm4_lands_batch_defer_jitter_000(monkeypatch):
    """batch_defer (jitter 0.0): sibling arms during the committing attempt 4 - no rung follows, so no gate wait."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=3, arm_at=4)
    assert store.run(body, operation='batch_defer') == 'committed'
    # arm at attempt 4: rungs 1-2 bare, rung 3 rides its wave wait, the
    # chain lands on the ungated committing attempt
    assert clock.sleeps == [0.1, 0.2, 0.9]


def test_grid_sibling_arm4_lands_batch_defer_jitter_100(monkeypatch):
    """batch_defer (jitter 1.0): sibling arms during the committing attempt 4 - no rung follows, so no gate wait."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=3, arm_at=4)
    assert store.run(body, operation='batch_defer') == 'committed'
    # arm at attempt 4: rungs 1-2 bare, rung 3 rides its wave wait, the
    # chain lands on the ungated committing attempt
    assert clock.sleeps == [0.2, 0.4, 1.8]


def test_grid_sibling_arm4_lands_batch_heartbeat_jitter_000(monkeypatch):
    """batch_heartbeat (jitter 0.0): sibling arms during the committing attempt 4 - no rung follows, so no gate wait."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_heartbeat', aborts=3, arm_at=4)
    assert store.run(body, operation='batch_heartbeat') == 'committed'
    # arm at attempt 4: rungs 1-2 bare, rung 3 rides its wave wait, the
    # chain lands on the ungated committing attempt
    assert clock.sleeps == [0.1, 0.2, 0.9]


def test_grid_sibling_arm4_lands_batch_heartbeat_jitter_100(monkeypatch):
    """batch_heartbeat (jitter 1.0): sibling arms during the committing attempt 4 - no rung follows, so no gate wait."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_heartbeat', aborts=3, arm_at=4)
    assert store.run(body, operation='batch_heartbeat') == 'committed'
    # arm at attempt 4: rungs 1-2 bare, rung 3 rides its wave wait, the
    # chain lands on the ungated committing attempt
    assert clock.sleeps == [0.2, 0.4, 1.8]


def test_grid_sibling_arm4_lands_batch_admit_jitter_000(monkeypatch):
    """batch_admit (jitter 0.0): sibling arms during the committing attempt 4 - no rung follows, so no gate wait."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=3, arm_at=4)
    assert store.run(body, operation='batch_admit') == 'committed'
    # arm at attempt 4: rungs 1-2 bare, rung 3 rides its wave wait, the
    # chain lands on the ungated committing attempt
    assert clock.sleeps == [0.1, 0.2, 0.9]


def test_grid_sibling_arm4_lands_batch_admit_jitter_100(monkeypatch):
    """batch_admit (jitter 1.0): sibling arms during the committing attempt 4 - no rung follows, so no gate wait."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=3, arm_at=4)
    assert store.run(body, operation='batch_admit') == 'committed'
    # arm at attempt 4: rungs 1-2 bare, rung 3 rides its wave wait, the
    # chain lands on the ungated committing attempt
    assert clock.sleeps == [0.2, 0.4, 1.8]


def test_grid_sibling_arm4_lands_batch_enqueue_jitter_000(monkeypatch):
    """batch_enqueue (jitter 0.0): sibling arms during the committing attempt 4 - no rung follows, so no gate wait."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_enqueue', aborts=3, arm_at=4)
    assert store.run(body, operation='batch_enqueue') == 'committed'
    # arm at attempt 4: rungs 1-2 bare, rung 3 rides its wave wait, the
    # chain lands on the ungated committing attempt
    assert clock.sleeps == [0.1, 0.2, 0.9]


def test_grid_sibling_arm4_lands_batch_enqueue_jitter_100(monkeypatch):
    """batch_enqueue (jitter 1.0): sibling arms during the committing attempt 4 - no rung follows, so no gate wait."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_enqueue', aborts=3, arm_at=4)
    assert store.run(body, operation='batch_enqueue') == 'committed'
    # arm at attempt 4: rungs 1-2 bare, rung 3 rides its wave wait, the
    # chain lands on the ungated committing attempt
    assert clock.sleeps == [0.2, 0.4, 1.8]


def test_grid_sibling_arm4_lands_batch_intake_status_jitter_000(monkeypatch):
    """batch_intake_status (jitter 0.0): sibling arms during the committing attempt 4 - no rung follows, so no gate wait."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=3, arm_at=4)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    # arm at attempt 4: rungs 1-2 bare, rung 3 rides its wave wait, the
    # chain lands on the ungated committing attempt
    assert clock.sleeps == [0.1, 0.2, 0.9]


def test_grid_sibling_arm4_lands_batch_intake_status_jitter_100(monkeypatch):
    """batch_intake_status (jitter 1.0): sibling arms during the committing attempt 4 - no rung follows, so no gate wait."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=3, arm_at=4)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    # arm at attempt 4: rungs 1-2 bare, rung 3 rides its wave wait, the
    # chain lands on the ungated committing attempt
    assert clock.sleeps == [0.2, 0.4, 1.8]


def test_grid_sibling_arm4_lands_batch_seal_register_jitter_000(monkeypatch):
    """batch_seal_register (jitter 0.0): sibling arms during the committing attempt 4 - no rung follows, so no gate wait."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=3, arm_at=4)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    # arm at attempt 4: rungs 1-2 bare, rung 3 rides its wave wait, the
    # chain lands on the ungated committing attempt
    assert clock.sleeps == [0.1, 0.2, 0.9]


def test_grid_sibling_arm4_lands_batch_seal_register_jitter_100(monkeypatch):
    """batch_seal_register (jitter 1.0): sibling arms during the committing attempt 4 - no rung follows, so no gate wait."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=3, arm_at=4)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    # arm at attempt 4: rungs 1-2 bare, rung 3 rides its wave wait, the
    # chain lands on the ungated committing attempt
    assert clock.sleeps == [0.2, 0.4, 1.8]


def test_grid_sibling_arm4_lands_batch_release_jitter_000(monkeypatch):
    """batch_release (jitter 0.0): sibling arms during the committing attempt 4 - no rung follows, so no gate wait."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=3, arm_at=4)
    assert store.run(body, operation='batch_release') == 'committed'
    # arm at attempt 4: rungs 1-2 bare, rung 3 rides its wave wait, the
    # chain lands on the ungated committing attempt
    assert clock.sleeps == [0.1, 0.2, 0.9]


def test_grid_sibling_arm4_lands_batch_release_jitter_100(monkeypatch):
    """batch_release (jitter 1.0): sibling arms during the committing attempt 4 - no rung follows, so no gate wait."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=3, arm_at=4)
    assert store.run(body, operation='batch_release') == 'committed'
    # arm at attempt 4: rungs 1-2 bare, rung 3 rides its wave wait, the
    # chain lands on the ungated committing attempt
    assert clock.sleeps == [0.2, 0.4, 1.8]


def test_grid_sibling_arm4_lands_batch_redrive_jitter_000(monkeypatch):
    """batch_redrive (jitter 0.0): sibling arms during the committing attempt 4 - no rung follows, so no gate wait."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=3, arm_at=4)
    assert store.run(body, operation='batch_redrive') == 'committed'
    # arm at attempt 4: rungs 1-2 bare, rung 3 rides its wave wait, the
    # chain lands on the ungated committing attempt
    assert clock.sleeps == [0.1, 0.2, 0.9]


def test_grid_sibling_arm4_lands_batch_redrive_jitter_100(monkeypatch):
    """batch_redrive (jitter 1.0): sibling arms during the committing attempt 4 - no rung follows, so no gate wait."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=3, arm_at=4)
    assert store.run(body, operation='batch_redrive') == 'committed'
    # arm at attempt 4: rungs 1-2 bare, rung 3 rides its wave wait, the
    # chain lands on the ungated committing attempt
    assert clock.sleeps == [0.2, 0.4, 1.8]


def test_grid_sibling_arm4_lands_batch_pull_shard_scheduler_00_jitter_000(monkeypatch):
    """batch_pull shard=scheduler_00 (jitter 0.0): sibling arms during the committing attempt 4 - no rung follows, so no gate wait."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_pull shard=scheduler_00', aborts=3, arm_at=4
    )
    assert store.run(body, operation='batch_pull shard=scheduler_00') == 'committed'
    # arm at attempt 4: rungs 1-2 bare, rung 3 rides its wave wait, the
    # chain lands on the ungated committing attempt
    assert clock.sleeps == [0.1, 0.2, 0.9]


def test_grid_sibling_arm4_lands_batch_pull_shard_scheduler_00_jitter_100(monkeypatch):
    """batch_pull shard=scheduler_00 (jitter 1.0): sibling arms during the committing attempt 4 - no rung follows, so no gate wait."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_pull shard=scheduler_00', aborts=3, arm_at=4
    )
    assert store.run(body, operation='batch_pull shard=scheduler_00') == 'committed'
    # arm at attempt 4: rungs 1-2 bare, rung 3 rides its wave wait, the
    # chain lands on the ungated committing attempt
    assert clock.sleeps == [0.2, 0.4, 1.8]


def test_grid_neighbor_isolation_batch_provider_stt_jitter_000(monkeypatch):
    """batch_provider_stt (jitter 0.0): a neighbor label armed hot leaves this label bare [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=2)
    damper.arm('batch_neighbor_hot')
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # a hot neighbor label never gates this one


def test_grid_neighbor_isolation_batch_provider_stt_jitter_100(monkeypatch):
    """batch_provider_stt (jitter 1.0): a neighbor label armed hot leaves this label bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=2)
    damper.arm('batch_neighbor_hot')
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # a hot neighbor label never gates this one


def test_grid_neighbor_isolation_batch_merge_commit_jitter_000(monkeypatch):
    """batch_merge_commit (jitter 0.0): a neighbor label armed hot leaves this label bare [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=2)
    damper.arm('batch_neighbor_hot')
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # a hot neighbor label never gates this one


def test_grid_neighbor_isolation_batch_merge_commit_jitter_100(monkeypatch):
    """batch_merge_commit (jitter 1.0): a neighbor label armed hot leaves this label bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=2)
    damper.arm('batch_neighbor_hot')
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # a hot neighbor label never gates this one


def test_grid_neighbor_isolation_batch_recover_jitter_000(monkeypatch):
    """batch_recover (jitter 0.0): a neighbor label armed hot leaves this label bare [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=2)
    damper.arm('batch_neighbor_hot')
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # a hot neighbor label never gates this one


def test_grid_neighbor_isolation_batch_recover_jitter_100(monkeypatch):
    """batch_recover (jitter 1.0): a neighbor label armed hot leaves this label bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=2)
    damper.arm('batch_neighbor_hot')
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # a hot neighbor label never gates this one


def test_grid_neighbor_isolation_batch_fail_jitter_000(monkeypatch):
    """batch_fail (jitter 0.0): a neighbor label armed hot leaves this label bare [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=2)
    damper.arm('batch_neighbor_hot')
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # a hot neighbor label never gates this one


def test_grid_neighbor_isolation_batch_fail_jitter_100(monkeypatch):
    """batch_fail (jitter 1.0): a neighbor label armed hot leaves this label bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=2)
    damper.arm('batch_neighbor_hot')
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # a hot neighbor label never gates this one


def test_grid_neighbor_isolation_batch_complete_jitter_000(monkeypatch):
    """batch_complete (jitter 0.0): a neighbor label armed hot leaves this label bare [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=2)
    damper.arm('batch_neighbor_hot')
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # a hot neighbor label never gates this one


def test_grid_neighbor_isolation_batch_complete_jitter_100(monkeypatch):
    """batch_complete (jitter 1.0): a neighbor label armed hot leaves this label bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=2)
    damper.arm('batch_neighbor_hot')
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # a hot neighbor label never gates this one


def test_grid_neighbor_isolation_batch_defer_jitter_000(monkeypatch):
    """batch_defer (jitter 0.0): a neighbor label armed hot leaves this label bare [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=2)
    damper.arm('batch_neighbor_hot')
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # a hot neighbor label never gates this one


def test_grid_neighbor_isolation_batch_defer_jitter_100(monkeypatch):
    """batch_defer (jitter 1.0): a neighbor label armed hot leaves this label bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=2)
    damper.arm('batch_neighbor_hot')
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # a hot neighbor label never gates this one


def test_grid_neighbor_isolation_batch_heartbeat_jitter_000(monkeypatch):
    """batch_heartbeat (jitter 0.0): a neighbor label armed hot leaves this label bare [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_heartbeat', aborts=2)
    damper.arm('batch_neighbor_hot')
    assert store.run(body, operation='batch_heartbeat') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # a hot neighbor label never gates this one


def test_grid_neighbor_isolation_batch_heartbeat_jitter_100(monkeypatch):
    """batch_heartbeat (jitter 1.0): a neighbor label armed hot leaves this label bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_heartbeat', aborts=2)
    damper.arm('batch_neighbor_hot')
    assert store.run(body, operation='batch_heartbeat') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # a hot neighbor label never gates this one


def test_grid_neighbor_isolation_batch_admit_jitter_000(monkeypatch):
    """batch_admit (jitter 0.0): a neighbor label armed hot leaves this label bare [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=2)
    damper.arm('batch_neighbor_hot')
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # a hot neighbor label never gates this one


def test_grid_neighbor_isolation_batch_admit_jitter_100(monkeypatch):
    """batch_admit (jitter 1.0): a neighbor label armed hot leaves this label bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=2)
    damper.arm('batch_neighbor_hot')
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # a hot neighbor label never gates this one


def test_grid_neighbor_isolation_batch_enqueue_jitter_000(monkeypatch):
    """batch_enqueue (jitter 0.0): a neighbor label armed hot leaves this label bare [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_enqueue', aborts=2)
    damper.arm('batch_neighbor_hot')
    assert store.run(body, operation='batch_enqueue') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # a hot neighbor label never gates this one


def test_grid_neighbor_isolation_batch_enqueue_jitter_100(monkeypatch):
    """batch_enqueue (jitter 1.0): a neighbor label armed hot leaves this label bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_enqueue', aborts=2)
    damper.arm('batch_neighbor_hot')
    assert store.run(body, operation='batch_enqueue') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # a hot neighbor label never gates this one


def test_grid_neighbor_isolation_batch_intake_status_jitter_000(monkeypatch):
    """batch_intake_status (jitter 0.0): a neighbor label armed hot leaves this label bare [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=2)
    damper.arm('batch_neighbor_hot')
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # a hot neighbor label never gates this one


def test_grid_neighbor_isolation_batch_intake_status_jitter_100(monkeypatch):
    """batch_intake_status (jitter 1.0): a neighbor label armed hot leaves this label bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=2)
    damper.arm('batch_neighbor_hot')
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # a hot neighbor label never gates this one


def test_grid_neighbor_isolation_batch_seal_register_jitter_000(monkeypatch):
    """batch_seal_register (jitter 0.0): a neighbor label armed hot leaves this label bare [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=2)
    damper.arm('batch_neighbor_hot')
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # a hot neighbor label never gates this one


def test_grid_neighbor_isolation_batch_seal_register_jitter_100(monkeypatch):
    """batch_seal_register (jitter 1.0): a neighbor label armed hot leaves this label bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=2)
    damper.arm('batch_neighbor_hot')
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # a hot neighbor label never gates this one


def test_grid_neighbor_isolation_batch_release_jitter_000(monkeypatch):
    """batch_release (jitter 0.0): a neighbor label armed hot leaves this label bare [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=2)
    damper.arm('batch_neighbor_hot')
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # a hot neighbor label never gates this one


def test_grid_neighbor_isolation_batch_release_jitter_100(monkeypatch):
    """batch_release (jitter 1.0): a neighbor label armed hot leaves this label bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=2)
    damper.arm('batch_neighbor_hot')
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # a hot neighbor label never gates this one


def test_grid_neighbor_isolation_batch_redrive_jitter_000(monkeypatch):
    """batch_redrive (jitter 0.0): a neighbor label armed hot leaves this label bare [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=2)
    damper.arm('batch_neighbor_hot')
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # a hot neighbor label never gates this one


def test_grid_neighbor_isolation_batch_redrive_jitter_100(monkeypatch):
    """batch_redrive (jitter 1.0): a neighbor label armed hot leaves this label bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=2)
    damper.arm('batch_neighbor_hot')
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # a hot neighbor label never gates this one


def test_grid_neighbor_isolation_batch_pull_shard_scheduler_00_jitter_000(monkeypatch):
    """batch_pull shard=scheduler_00 (jitter 0.0): a neighbor label armed hot leaves this label bare [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_pull shard=scheduler_00', aborts=2)
    damper.arm('batch_neighbor_hot')
    assert store.run(body, operation='batch_pull shard=scheduler_00') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # a hot neighbor label never gates this one


def test_grid_neighbor_isolation_batch_pull_shard_scheduler_00_jitter_100(monkeypatch):
    """batch_pull shard=scheduler_00 (jitter 1.0): a neighbor label armed hot leaves this label bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_pull shard=scheduler_00', aborts=2)
    damper.arm('batch_neighbor_hot')
    assert store.run(body, operation='batch_pull shard=scheduler_00') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # a hot neighbor label never gates this one


def test_grid_dormant_damper_batch_provider_stt(monkeypatch):
    """batch_provider_stt with BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED=false: the armed window is ignored, rungs stay bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(
        monkeypatch,
        clock,
        label='batch_provider_stt',
        aborts=2,
        dormant_env='BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED',
    )
    damper.arm('batch_provider_stt')  # window armed on the damper object, but the switch is off
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # dormant damper: bare rungs, the armed window ignored


def test_grid_dormant_damper_batch_merge_commit(monkeypatch):
    """batch_merge_commit with BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED=false: the armed window is ignored, rungs stay bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(
        monkeypatch,
        clock,
        label='batch_merge_commit',
        aborts=2,
        dormant_env='BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED',
    )
    damper.arm('batch_merge_commit')  # window armed on the damper object, but the switch is off
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # dormant damper: bare rungs, the armed window ignored


def test_grid_dormant_damper_batch_recover(monkeypatch):
    """batch_recover with BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED=false: the armed window is ignored, rungs stay bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(
        monkeypatch,
        clock,
        label='batch_recover',
        aborts=2,
        dormant_env='BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED',
    )
    damper.arm('batch_recover')  # window armed on the damper object, but the switch is off
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # dormant damper: bare rungs, the armed window ignored


def test_grid_dormant_damper_batch_fail(monkeypatch):
    """batch_fail with BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED=false: the armed window is ignored, rungs stay bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_fail', aborts=2, dormant_env='BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED'
    )
    damper.arm('batch_fail')  # window armed on the damper object, but the switch is off
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # dormant damper: bare rungs, the armed window ignored


def test_grid_dormant_damper_batch_complete(monkeypatch):
    """batch_complete with BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED=false: the armed window is ignored, rungs stay bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(
        monkeypatch,
        clock,
        label='batch_complete',
        aborts=2,
        dormant_env='BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED',
    )
    damper.arm('batch_complete')  # window armed on the damper object, but the switch is off
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # dormant damper: bare rungs, the armed window ignored


def test_grid_dormant_damper_batch_defer(monkeypatch):
    """batch_defer with BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED=false: the armed window is ignored, rungs stay bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_defer', aborts=2, dormant_env='BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED'
    )
    damper.arm('batch_defer')  # window armed on the damper object, but the switch is off
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # dormant damper: bare rungs, the armed window ignored


def test_grid_dormant_damper_batch_heartbeat(monkeypatch):
    """batch_heartbeat with BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED=false: the armed window is ignored, rungs stay bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(
        monkeypatch,
        clock,
        label='batch_heartbeat',
        aborts=2,
        dormant_env='BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED',
    )
    damper.arm('batch_heartbeat')  # window armed on the damper object, but the switch is off
    assert store.run(body, operation='batch_heartbeat') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # dormant damper: bare rungs, the armed window ignored


def test_grid_dormant_damper_batch_admit(monkeypatch):
    """batch_admit with BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED=false: the armed window is ignored, rungs stay bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_admit', aborts=2, dormant_env='BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED'
    )
    damper.arm('batch_admit')  # window armed on the damper object, but the switch is off
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # dormant damper: bare rungs, the armed window ignored


def test_grid_dormant_damper_batch_enqueue(monkeypatch):
    """batch_enqueue with BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED=false: the armed window is ignored, rungs stay bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(
        monkeypatch,
        clock,
        label='batch_enqueue',
        aborts=2,
        dormant_env='BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED',
    )
    damper.arm('batch_enqueue')  # window armed on the damper object, but the switch is off
    assert store.run(body, operation='batch_enqueue') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # dormant damper: bare rungs, the armed window ignored


def test_grid_dormant_damper_batch_intake_status(monkeypatch):
    """batch_intake_status with BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED=false: the armed window is ignored, rungs stay bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(
        monkeypatch,
        clock,
        label='batch_intake_status',
        aborts=2,
        dormant_env='BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED',
    )
    damper.arm('batch_intake_status')  # window armed on the damper object, but the switch is off
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # dormant damper: bare rungs, the armed window ignored


def test_grid_dormant_damper_batch_seal_register(monkeypatch):
    """batch_seal_register with BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED=false: the armed window is ignored, rungs stay bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(
        monkeypatch,
        clock,
        label='batch_seal_register',
        aborts=2,
        dormant_env='BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED',
    )
    damper.arm('batch_seal_register')  # window armed on the damper object, but the switch is off
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # dormant damper: bare rungs, the armed window ignored


def test_grid_dormant_damper_batch_release(monkeypatch):
    """batch_release with BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED=false: the armed window is ignored, rungs stay bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(
        monkeypatch,
        clock,
        label='batch_release',
        aborts=2,
        dormant_env='BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED',
    )
    damper.arm('batch_release')  # window armed on the damper object, but the switch is off
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # dormant damper: bare rungs, the armed window ignored


def test_grid_dormant_damper_batch_redrive(monkeypatch):
    """batch_redrive with BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED=false: the armed window is ignored, rungs stay bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(
        monkeypatch,
        clock,
        label='batch_redrive',
        aborts=2,
        dormant_env='BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED',
    )
    damper.arm('batch_redrive')  # window armed on the damper object, but the switch is off
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # dormant damper: bare rungs, the armed window ignored


def test_grid_dormant_damper_batch_pull_shard_scheduler_00(monkeypatch):
    """batch_pull shard=scheduler_00 with BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED=false: the armed window is ignored, rungs stay bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(
        monkeypatch,
        clock,
        label='batch_pull shard=scheduler_00',
        aborts=2,
        dormant_env='BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED',
    )
    damper.arm('batch_pull shard=scheduler_00')  # window armed on the damper object, but the switch is off
    assert store.run(body, operation='batch_pull shard=scheduler_00') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # dormant damper: bare rungs, the armed window ignored


def test_grid_dormant_retry_batch_provider_stt(monkeypatch):
    """batch_provider_stt with BATCH_PIPELINE_CONTENTION_RETRY_ENABLED=false: no retry budget, no gate, no damper consumption."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_provider_stt', aborts=0, dormant_env='BATCH_PIPELINE_CONTENTION_RETRY_ENABLED'
    )
    damper.arm('batch_provider_stt')
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == []  # no outer budget at all: the single SDK attempt never sleeps on this clock
    residual, generation = damper.peek('batch_provider_stt')
    assert residual > 0.0 and generation == 1  # and the armed window survives untouched


def test_grid_dormant_retry_batch_merge_commit(monkeypatch):
    """batch_merge_commit with BATCH_PIPELINE_CONTENTION_RETRY_ENABLED=false: no retry budget, no gate, no damper consumption."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_merge_commit', aborts=0, dormant_env='BATCH_PIPELINE_CONTENTION_RETRY_ENABLED'
    )
    damper.arm('batch_merge_commit')
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == []  # no outer budget at all: the single SDK attempt never sleeps on this clock
    residual, generation = damper.peek('batch_merge_commit')
    assert residual > 0.0 and generation == 1  # and the armed window survives untouched


def test_grid_dormant_retry_batch_recover(monkeypatch):
    """batch_recover with BATCH_PIPELINE_CONTENTION_RETRY_ENABLED=false: no retry budget, no gate, no damper consumption."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_recover', aborts=0, dormant_env='BATCH_PIPELINE_CONTENTION_RETRY_ENABLED'
    )
    damper.arm('batch_recover')
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == []  # no outer budget at all: the single SDK attempt never sleeps on this clock
    residual, generation = damper.peek('batch_recover')
    assert residual > 0.0 and generation == 1  # and the armed window survives untouched


def test_grid_dormant_retry_batch_fail(monkeypatch):
    """batch_fail with BATCH_PIPELINE_CONTENTION_RETRY_ENABLED=false: no retry budget, no gate, no damper consumption."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_fail', aborts=0, dormant_env='BATCH_PIPELINE_CONTENTION_RETRY_ENABLED'
    )
    damper.arm('batch_fail')
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == []  # no outer budget at all: the single SDK attempt never sleeps on this clock
    residual, generation = damper.peek('batch_fail')
    assert residual > 0.0 and generation == 1  # and the armed window survives untouched


def test_grid_dormant_retry_batch_complete(monkeypatch):
    """batch_complete with BATCH_PIPELINE_CONTENTION_RETRY_ENABLED=false: no retry budget, no gate, no damper consumption."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_complete', aborts=0, dormant_env='BATCH_PIPELINE_CONTENTION_RETRY_ENABLED'
    )
    damper.arm('batch_complete')
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == []  # no outer budget at all: the single SDK attempt never sleeps on this clock
    residual, generation = damper.peek('batch_complete')
    assert residual > 0.0 and generation == 1  # and the armed window survives untouched


def test_grid_dormant_retry_batch_defer(monkeypatch):
    """batch_defer with BATCH_PIPELINE_CONTENTION_RETRY_ENABLED=false: no retry budget, no gate, no damper consumption."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_defer', aborts=0, dormant_env='BATCH_PIPELINE_CONTENTION_RETRY_ENABLED'
    )
    damper.arm('batch_defer')
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == []  # no outer budget at all: the single SDK attempt never sleeps on this clock
    residual, generation = damper.peek('batch_defer')
    assert residual > 0.0 and generation == 1  # and the armed window survives untouched


def test_grid_dormant_retry_batch_heartbeat(monkeypatch):
    """batch_heartbeat with BATCH_PIPELINE_CONTENTION_RETRY_ENABLED=false: no retry budget, no gate, no damper consumption."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_heartbeat', aborts=0, dormant_env='BATCH_PIPELINE_CONTENTION_RETRY_ENABLED'
    )
    damper.arm('batch_heartbeat')
    assert store.run(body, operation='batch_heartbeat') == 'committed'
    assert clock.sleeps == []  # no outer budget at all: the single SDK attempt never sleeps on this clock
    residual, generation = damper.peek('batch_heartbeat')
    assert residual > 0.0 and generation == 1  # and the armed window survives untouched


def test_grid_dormant_retry_batch_admit(monkeypatch):
    """batch_admit with BATCH_PIPELINE_CONTENTION_RETRY_ENABLED=false: no retry budget, no gate, no damper consumption."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_admit', aborts=0, dormant_env='BATCH_PIPELINE_CONTENTION_RETRY_ENABLED'
    )
    damper.arm('batch_admit')
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == []  # no outer budget at all: the single SDK attempt never sleeps on this clock
    residual, generation = damper.peek('batch_admit')
    assert residual > 0.0 and generation == 1  # and the armed window survives untouched


def test_grid_dormant_retry_batch_enqueue(monkeypatch):
    """batch_enqueue with BATCH_PIPELINE_CONTENTION_RETRY_ENABLED=false: no retry budget, no gate, no damper consumption."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_enqueue', aborts=0, dormant_env='BATCH_PIPELINE_CONTENTION_RETRY_ENABLED'
    )
    damper.arm('batch_enqueue')
    assert store.run(body, operation='batch_enqueue') == 'committed'
    assert clock.sleeps == []  # no outer budget at all: the single SDK attempt never sleeps on this clock
    residual, generation = damper.peek('batch_enqueue')
    assert residual > 0.0 and generation == 1  # and the armed window survives untouched


def test_grid_dormant_retry_batch_intake_status(monkeypatch):
    """batch_intake_status with BATCH_PIPELINE_CONTENTION_RETRY_ENABLED=false: no retry budget, no gate, no damper consumption."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_intake_status', aborts=0, dormant_env='BATCH_PIPELINE_CONTENTION_RETRY_ENABLED'
    )
    damper.arm('batch_intake_status')
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == []  # no outer budget at all: the single SDK attempt never sleeps on this clock
    residual, generation = damper.peek('batch_intake_status')
    assert residual > 0.0 and generation == 1  # and the armed window survives untouched


def test_grid_dormant_retry_batch_seal_register(monkeypatch):
    """batch_seal_register with BATCH_PIPELINE_CONTENTION_RETRY_ENABLED=false: no retry budget, no gate, no damper consumption."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_seal_register', aborts=0, dormant_env='BATCH_PIPELINE_CONTENTION_RETRY_ENABLED'
    )
    damper.arm('batch_seal_register')
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == []  # no outer budget at all: the single SDK attempt never sleeps on this clock
    residual, generation = damper.peek('batch_seal_register')
    assert residual > 0.0 and generation == 1  # and the armed window survives untouched


def test_grid_dormant_retry_batch_release(monkeypatch):
    """batch_release with BATCH_PIPELINE_CONTENTION_RETRY_ENABLED=false: no retry budget, no gate, no damper consumption."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_release', aborts=0, dormant_env='BATCH_PIPELINE_CONTENTION_RETRY_ENABLED'
    )
    damper.arm('batch_release')
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == []  # no outer budget at all: the single SDK attempt never sleeps on this clock
    residual, generation = damper.peek('batch_release')
    assert residual > 0.0 and generation == 1  # and the armed window survives untouched


def test_grid_dormant_retry_batch_redrive(monkeypatch):
    """batch_redrive with BATCH_PIPELINE_CONTENTION_RETRY_ENABLED=false: no retry budget, no gate, no damper consumption."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_redrive', aborts=0, dormant_env='BATCH_PIPELINE_CONTENTION_RETRY_ENABLED'
    )
    damper.arm('batch_redrive')
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == []  # no outer budget at all: the single SDK attempt never sleeps on this clock
    residual, generation = damper.peek('batch_redrive')
    assert residual > 0.0 and generation == 1  # and the armed window survives untouched


def test_grid_dormant_retry_batch_pull_shard_scheduler_00(monkeypatch):
    """batch_pull shard=scheduler_00 with BATCH_PIPELINE_CONTENTION_RETRY_ENABLED=false: no retry budget, no gate, no damper consumption."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(
        monkeypatch,
        clock,
        label='batch_pull shard=scheduler_00',
        aborts=0,
        dormant_env='BATCH_PIPELINE_CONTENTION_RETRY_ENABLED',
    )
    damper.arm('batch_pull shard=scheduler_00')
    assert store.run(body, operation='batch_pull shard=scheduler_00') == 'committed'
    assert clock.sleeps == []  # no outer budget at all: the single SDK attempt never sleeps on this clock
    residual, generation = damper.peek('batch_pull shard=scheduler_00')
    assert residual > 0.0 and generation == 1  # and the armed window survives untouched


def test_grid_expired_window_batch_provider_stt_jitter_000(monkeypatch):
    """batch_provider_stt (jitter 0.0): a long-expired window costs nothing; rungs stay bare [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=2)
    damper.arm('batch_provider_stt')
    clock.advance(999.0)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # an expired window is no window at all


def test_grid_expired_window_batch_provider_stt_jitter_100(monkeypatch):
    """batch_provider_stt (jitter 1.0): a long-expired window costs nothing; rungs stay bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=2)
    damper.arm('batch_provider_stt')
    clock.advance(999.0)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # an expired window is no window at all


def test_grid_expired_window_batch_merge_commit_jitter_000(monkeypatch):
    """batch_merge_commit (jitter 0.0): a long-expired window costs nothing; rungs stay bare [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=2)
    damper.arm('batch_merge_commit')
    clock.advance(999.0)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # an expired window is no window at all


def test_grid_expired_window_batch_merge_commit_jitter_100(monkeypatch):
    """batch_merge_commit (jitter 1.0): a long-expired window costs nothing; rungs stay bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=2)
    damper.arm('batch_merge_commit')
    clock.advance(999.0)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # an expired window is no window at all


def test_grid_expired_window_batch_recover_jitter_000(monkeypatch):
    """batch_recover (jitter 0.0): a long-expired window costs nothing; rungs stay bare [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=2)
    damper.arm('batch_recover')
    clock.advance(999.0)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # an expired window is no window at all


def test_grid_expired_window_batch_recover_jitter_100(monkeypatch):
    """batch_recover (jitter 1.0): a long-expired window costs nothing; rungs stay bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=2)
    damper.arm('batch_recover')
    clock.advance(999.0)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # an expired window is no window at all


def test_grid_expired_window_batch_fail_jitter_000(monkeypatch):
    """batch_fail (jitter 0.0): a long-expired window costs nothing; rungs stay bare [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=2)
    damper.arm('batch_fail')
    clock.advance(999.0)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # an expired window is no window at all


def test_grid_expired_window_batch_fail_jitter_100(monkeypatch):
    """batch_fail (jitter 1.0): a long-expired window costs nothing; rungs stay bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=2)
    damper.arm('batch_fail')
    clock.advance(999.0)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # an expired window is no window at all


def test_grid_expired_window_batch_complete_jitter_000(monkeypatch):
    """batch_complete (jitter 0.0): a long-expired window costs nothing; rungs stay bare [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=2)
    damper.arm('batch_complete')
    clock.advance(999.0)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # an expired window is no window at all


def test_grid_expired_window_batch_complete_jitter_100(monkeypatch):
    """batch_complete (jitter 1.0): a long-expired window costs nothing; rungs stay bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=2)
    damper.arm('batch_complete')
    clock.advance(999.0)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # an expired window is no window at all


def test_grid_expired_window_batch_defer_jitter_000(monkeypatch):
    """batch_defer (jitter 0.0): a long-expired window costs nothing; rungs stay bare [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=2)
    damper.arm('batch_defer')
    clock.advance(999.0)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # an expired window is no window at all


def test_grid_expired_window_batch_defer_jitter_100(monkeypatch):
    """batch_defer (jitter 1.0): a long-expired window costs nothing; rungs stay bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=2)
    damper.arm('batch_defer')
    clock.advance(999.0)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # an expired window is no window at all


def test_grid_expired_window_batch_heartbeat_jitter_000(monkeypatch):
    """batch_heartbeat (jitter 0.0): a long-expired window costs nothing; rungs stay bare [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_heartbeat', aborts=2)
    damper.arm('batch_heartbeat')
    clock.advance(999.0)
    assert store.run(body, operation='batch_heartbeat') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # an expired window is no window at all


def test_grid_expired_window_batch_heartbeat_jitter_100(monkeypatch):
    """batch_heartbeat (jitter 1.0): a long-expired window costs nothing; rungs stay bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_heartbeat', aborts=2)
    damper.arm('batch_heartbeat')
    clock.advance(999.0)
    assert store.run(body, operation='batch_heartbeat') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # an expired window is no window at all


def test_grid_expired_window_batch_admit_jitter_000(monkeypatch):
    """batch_admit (jitter 0.0): a long-expired window costs nothing; rungs stay bare [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=2)
    damper.arm('batch_admit')
    clock.advance(999.0)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # an expired window is no window at all


def test_grid_expired_window_batch_admit_jitter_100(monkeypatch):
    """batch_admit (jitter 1.0): a long-expired window costs nothing; rungs stay bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=2)
    damper.arm('batch_admit')
    clock.advance(999.0)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # an expired window is no window at all


def test_grid_expired_window_batch_enqueue_jitter_000(monkeypatch):
    """batch_enqueue (jitter 0.0): a long-expired window costs nothing; rungs stay bare [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_enqueue', aborts=2)
    damper.arm('batch_enqueue')
    clock.advance(999.0)
    assert store.run(body, operation='batch_enqueue') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # an expired window is no window at all


def test_grid_expired_window_batch_enqueue_jitter_100(monkeypatch):
    """batch_enqueue (jitter 1.0): a long-expired window costs nothing; rungs stay bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_enqueue', aborts=2)
    damper.arm('batch_enqueue')
    clock.advance(999.0)
    assert store.run(body, operation='batch_enqueue') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # an expired window is no window at all


def test_grid_expired_window_batch_intake_status_jitter_000(monkeypatch):
    """batch_intake_status (jitter 0.0): a long-expired window costs nothing; rungs stay bare [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=2)
    damper.arm('batch_intake_status')
    clock.advance(999.0)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # an expired window is no window at all


def test_grid_expired_window_batch_intake_status_jitter_100(monkeypatch):
    """batch_intake_status (jitter 1.0): a long-expired window costs nothing; rungs stay bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=2)
    damper.arm('batch_intake_status')
    clock.advance(999.0)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # an expired window is no window at all


def test_grid_expired_window_batch_seal_register_jitter_000(monkeypatch):
    """batch_seal_register (jitter 0.0): a long-expired window costs nothing; rungs stay bare [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=2)
    damper.arm('batch_seal_register')
    clock.advance(999.0)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # an expired window is no window at all


def test_grid_expired_window_batch_seal_register_jitter_100(monkeypatch):
    """batch_seal_register (jitter 1.0): a long-expired window costs nothing; rungs stay bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=2)
    damper.arm('batch_seal_register')
    clock.advance(999.0)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # an expired window is no window at all


def test_grid_expired_window_batch_release_jitter_000(monkeypatch):
    """batch_release (jitter 0.0): a long-expired window costs nothing; rungs stay bare [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=2)
    damper.arm('batch_release')
    clock.advance(999.0)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # an expired window is no window at all


def test_grid_expired_window_batch_release_jitter_100(monkeypatch):
    """batch_release (jitter 1.0): a long-expired window costs nothing; rungs stay bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=2)
    damper.arm('batch_release')
    clock.advance(999.0)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # an expired window is no window at all


def test_grid_expired_window_batch_redrive_jitter_000(monkeypatch):
    """batch_redrive (jitter 0.0): a long-expired window costs nothing; rungs stay bare [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=2)
    damper.arm('batch_redrive')
    clock.advance(999.0)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # an expired window is no window at all


def test_grid_expired_window_batch_redrive_jitter_100(monkeypatch):
    """batch_redrive (jitter 1.0): a long-expired window costs nothing; rungs stay bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=2)
    damper.arm('batch_redrive')
    clock.advance(999.0)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # an expired window is no window at all


def test_grid_expired_window_batch_pull_shard_scheduler_00_jitter_000(monkeypatch):
    """batch_pull shard=scheduler_00 (jitter 0.0): a long-expired window costs nothing; rungs stay bare [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_pull shard=scheduler_00', aborts=2)
    damper.arm('batch_pull shard=scheduler_00')
    clock.advance(999.0)
    assert store.run(body, operation='batch_pull shard=scheduler_00') == 'committed'
    assert clock.sleeps == [0.1, 0.2]  # an expired window is no window at all


def test_grid_expired_window_batch_pull_shard_scheduler_00_jitter_100(monkeypatch):
    """batch_pull shard=scheduler_00 (jitter 1.0): a long-expired window costs nothing; rungs stay bare [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_pull shard=scheduler_00', aborts=2)
    damper.arm('batch_pull shard=scheduler_00')
    clock.advance(999.0)
    assert store.run(body, operation='batch_pull shard=scheduler_00') == 'committed'
    assert clock.sleeps == [0.2, 0.4]  # an expired window is no window at all


def test_grid_prearmed_live_batch_provider_stt_jitter_000(monkeypatch):
    """batch_provider_stt (jitter 0.0): pre-armed window waited once at entry (0.125s); rung 1 never gated twice."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=2)
    damper.arm('batch_provider_stt')
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.125, 0.1, 0.2]  # entry consult waits 0.125; rung 1 is NOT gated a second time


def test_grid_prearmed_live_batch_provider_stt_jitter_100(monkeypatch):
    """batch_provider_stt (jitter 1.0): pre-armed window waited once at entry (0.25s); rung 1 never gated twice."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=2)
    damper.arm('batch_provider_stt')
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.25, 0.2, 0.4]  # entry consult waits 0.25; rung 1 is NOT gated a second time


def test_grid_prearmed_live_batch_merge_commit_jitter_000(monkeypatch):
    """batch_merge_commit (jitter 0.0): pre-armed window waited once at entry (0.125s); rung 1 never gated twice."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=2)
    damper.arm('batch_merge_commit')
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.125, 0.1, 0.2]  # entry consult waits 0.125; rung 1 is NOT gated a second time


def test_grid_prearmed_live_batch_merge_commit_jitter_100(monkeypatch):
    """batch_merge_commit (jitter 1.0): pre-armed window waited once at entry (0.25s); rung 1 never gated twice."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=2)
    damper.arm('batch_merge_commit')
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.25, 0.2, 0.4]  # entry consult waits 0.25; rung 1 is NOT gated a second time


def test_grid_prearmed_live_batch_recover_jitter_000(monkeypatch):
    """batch_recover (jitter 0.0): pre-armed window waited once at entry (0.125s); rung 1 never gated twice."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=2)
    damper.arm('batch_recover')
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.125, 0.1, 0.2]  # entry consult waits 0.125; rung 1 is NOT gated a second time


def test_grid_prearmed_live_batch_recover_jitter_100(monkeypatch):
    """batch_recover (jitter 1.0): pre-armed window waited once at entry (0.25s); rung 1 never gated twice."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=2)
    damper.arm('batch_recover')
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.25, 0.2, 0.4]  # entry consult waits 0.25; rung 1 is NOT gated a second time


def test_grid_prearmed_live_batch_fail_jitter_000(monkeypatch):
    """batch_fail (jitter 0.0): pre-armed window waited once at entry (0.125s); rung 1 never gated twice."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=2)
    damper.arm('batch_fail')
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.125, 0.1, 0.2]  # entry consult waits 0.125; rung 1 is NOT gated a second time


def test_grid_prearmed_live_batch_fail_jitter_100(monkeypatch):
    """batch_fail (jitter 1.0): pre-armed window waited once at entry (0.25s); rung 1 never gated twice."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=2)
    damper.arm('batch_fail')
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.25, 0.2, 0.4]  # entry consult waits 0.25; rung 1 is NOT gated a second time


def test_grid_prearmed_live_batch_complete_jitter_000(monkeypatch):
    """batch_complete (jitter 0.0): pre-armed window waited once at entry (0.125s); rung 1 never gated twice."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=2)
    damper.arm('batch_complete')
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.125, 0.1, 0.2]  # entry consult waits 0.125; rung 1 is NOT gated a second time


def test_grid_prearmed_live_batch_complete_jitter_100(monkeypatch):
    """batch_complete (jitter 1.0): pre-armed window waited once at entry (0.25s); rung 1 never gated twice."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=2)
    damper.arm('batch_complete')
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.25, 0.2, 0.4]  # entry consult waits 0.25; rung 1 is NOT gated a second time


def test_grid_prearmed_live_batch_defer_jitter_000(monkeypatch):
    """batch_defer (jitter 0.0): pre-armed window waited once at entry (0.125s); rung 1 never gated twice."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=2)
    damper.arm('batch_defer')
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.125, 0.1, 0.2]  # entry consult waits 0.125; rung 1 is NOT gated a second time


def test_grid_prearmed_live_batch_defer_jitter_100(monkeypatch):
    """batch_defer (jitter 1.0): pre-armed window waited once at entry (0.25s); rung 1 never gated twice."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=2)
    damper.arm('batch_defer')
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.25, 0.2, 0.4]  # entry consult waits 0.25; rung 1 is NOT gated a second time


def test_grid_prearmed_live_batch_heartbeat_jitter_000(monkeypatch):
    """batch_heartbeat (jitter 0.0): pre-armed window waited once at entry (0.125s); rung 1 never gated twice."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_heartbeat', aborts=2)
    damper.arm('batch_heartbeat')
    assert store.run(body, operation='batch_heartbeat') == 'committed'
    assert clock.sleeps == [0.125, 0.1, 0.2]  # entry consult waits 0.125; rung 1 is NOT gated a second time


def test_grid_prearmed_live_batch_heartbeat_jitter_100(monkeypatch):
    """batch_heartbeat (jitter 1.0): pre-armed window waited once at entry (0.25s); rung 1 never gated twice."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_heartbeat', aborts=2)
    damper.arm('batch_heartbeat')
    assert store.run(body, operation='batch_heartbeat') == 'committed'
    assert clock.sleeps == [0.25, 0.2, 0.4]  # entry consult waits 0.25; rung 1 is NOT gated a second time


def test_grid_prearmed_live_batch_admit_jitter_000(monkeypatch):
    """batch_admit (jitter 0.0): pre-armed window waited once at entry (0.125s); rung 1 never gated twice."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=2)
    damper.arm('batch_admit')
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.125, 0.1, 0.2]  # entry consult waits 0.125; rung 1 is NOT gated a second time


def test_grid_prearmed_live_batch_admit_jitter_100(monkeypatch):
    """batch_admit (jitter 1.0): pre-armed window waited once at entry (0.25s); rung 1 never gated twice."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=2)
    damper.arm('batch_admit')
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.25, 0.2, 0.4]  # entry consult waits 0.25; rung 1 is NOT gated a second time


def test_grid_prearmed_live_batch_enqueue_jitter_000(monkeypatch):
    """batch_enqueue (jitter 0.0): pre-armed window waited once at entry (0.125s); rung 1 never gated twice."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_enqueue', aborts=2)
    damper.arm('batch_enqueue')
    assert store.run(body, operation='batch_enqueue') == 'committed'
    assert clock.sleeps == [0.125, 0.1, 0.2]  # entry consult waits 0.125; rung 1 is NOT gated a second time


def test_grid_prearmed_live_batch_enqueue_jitter_100(monkeypatch):
    """batch_enqueue (jitter 1.0): pre-armed window waited once at entry (0.25s); rung 1 never gated twice."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_enqueue', aborts=2)
    damper.arm('batch_enqueue')
    assert store.run(body, operation='batch_enqueue') == 'committed'
    assert clock.sleeps == [0.25, 0.2, 0.4]  # entry consult waits 0.25; rung 1 is NOT gated a second time


def test_grid_prearmed_live_batch_intake_status_jitter_000(monkeypatch):
    """batch_intake_status (jitter 0.0): pre-armed window waited once at entry (0.125s); rung 1 never gated twice."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=2)
    damper.arm('batch_intake_status')
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.125, 0.1, 0.2]  # entry consult waits 0.125; rung 1 is NOT gated a second time


def test_grid_prearmed_live_batch_intake_status_jitter_100(monkeypatch):
    """batch_intake_status (jitter 1.0): pre-armed window waited once at entry (0.25s); rung 1 never gated twice."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=2)
    damper.arm('batch_intake_status')
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.25, 0.2, 0.4]  # entry consult waits 0.25; rung 1 is NOT gated a second time


def test_grid_prearmed_live_batch_seal_register_jitter_000(monkeypatch):
    """batch_seal_register (jitter 0.0): pre-armed window waited once at entry (0.125s); rung 1 never gated twice."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=2)
    damper.arm('batch_seal_register')
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.125, 0.1, 0.2]  # entry consult waits 0.125; rung 1 is NOT gated a second time


def test_grid_prearmed_live_batch_seal_register_jitter_100(monkeypatch):
    """batch_seal_register (jitter 1.0): pre-armed window waited once at entry (0.25s); rung 1 never gated twice."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=2)
    damper.arm('batch_seal_register')
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.25, 0.2, 0.4]  # entry consult waits 0.25; rung 1 is NOT gated a second time


def test_grid_prearmed_live_batch_release_jitter_000(monkeypatch):
    """batch_release (jitter 0.0): pre-armed window waited once at entry (0.125s); rung 1 never gated twice."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=2)
    damper.arm('batch_release')
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.125, 0.1, 0.2]  # entry consult waits 0.125; rung 1 is NOT gated a second time


def test_grid_prearmed_live_batch_release_jitter_100(monkeypatch):
    """batch_release (jitter 1.0): pre-armed window waited once at entry (0.25s); rung 1 never gated twice."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=2)
    damper.arm('batch_release')
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.25, 0.2, 0.4]  # entry consult waits 0.25; rung 1 is NOT gated a second time


def test_grid_prearmed_live_batch_redrive_jitter_000(monkeypatch):
    """batch_redrive (jitter 0.0): pre-armed window waited once at entry (0.125s); rung 1 never gated twice."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=2)
    damper.arm('batch_redrive')
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.125, 0.1, 0.2]  # entry consult waits 0.125; rung 1 is NOT gated a second time


def test_grid_prearmed_live_batch_redrive_jitter_100(monkeypatch):
    """batch_redrive (jitter 1.0): pre-armed window waited once at entry (0.25s); rung 1 never gated twice."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=2)
    damper.arm('batch_redrive')
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.25, 0.2, 0.4]  # entry consult waits 0.25; rung 1 is NOT gated a second time


def test_grid_prearmed_live_batch_pull_shard_scheduler_00_jitter_000(monkeypatch):
    """batch_pull shard=scheduler_00 (jitter 0.0): pre-armed window waited once at entry (0.125s); rung 1 never gated twice."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_pull shard=scheduler_00', aborts=2)
    damper.arm('batch_pull shard=scheduler_00')
    assert store.run(body, operation='batch_pull shard=scheduler_00') == 'committed'
    assert clock.sleeps == [0.125, 0.1, 0.2]  # entry consult waits 0.125; rung 1 is NOT gated a second time


def test_grid_prearmed_live_batch_pull_shard_scheduler_00_jitter_100(monkeypatch):
    """batch_pull shard=scheduler_00 (jitter 1.0): pre-armed window waited once at entry (0.25s); rung 1 never gated twice."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_pull shard=scheduler_00', aborts=2)
    damper.arm('batch_pull shard=scheduler_00')
    assert store.run(body, operation='batch_pull shard=scheduler_00') == 'committed'
    assert clock.sleeps == [0.25, 0.2, 0.4]  # entry consult waits 0.25; rung 1 is NOT gated a second time


def test_grid_exhaust_walk_batch_provider_stt_jitter_000(monkeypatch):
    """batch_provider_stt (jitter 0.0): exhaustion walk with a sibling arm at attempt 2 - rung 2 gated, retry-after stamped 0.25s."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_provider_stt', exhausting=True, arm_at=2
    )
    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_provider_stt')
    assert clock.sleeps == [0.1, 0.325, 0.9, 1.8]  # gated rung 2, then rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.25)  # the exhaustion re-arms the label


def test_grid_exhaust_walk_batch_provider_stt_jitter_100(monkeypatch):
    """batch_provider_stt (jitter 1.0): exhaustion walk with a sibling arm at attempt 2 - rung 2 gated, retry-after stamped 0.5s."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_provider_stt', exhausting=True, arm_at=2
    )
    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_provider_stt')
    assert clock.sleeps == [0.2, 0.65, 1.8, 3.6]  # gated rung 2, then rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.5)  # the exhaustion re-arms the label


def test_grid_exhaust_walk_batch_merge_commit_jitter_000(monkeypatch):
    """batch_merge_commit (jitter 0.0): exhaustion walk with a sibling arm at attempt 2 - rung 2 gated, retry-after stamped 0.25s."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_merge_commit', exhausting=True, arm_at=2
    )
    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_merge_commit')
    assert clock.sleeps == [0.1, 0.325, 0.9, 1.8]  # gated rung 2, then rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.25)  # the exhaustion re-arms the label


def test_grid_exhaust_walk_batch_merge_commit_jitter_100(monkeypatch):
    """batch_merge_commit (jitter 1.0): exhaustion walk with a sibling arm at attempt 2 - rung 2 gated, retry-after stamped 0.5s."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_merge_commit', exhausting=True, arm_at=2
    )
    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_merge_commit')
    assert clock.sleeps == [0.2, 0.65, 1.8, 3.6]  # gated rung 2, then rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.5)  # the exhaustion re-arms the label


def test_grid_exhaust_walk_batch_recover_jitter_000(monkeypatch):
    """batch_recover (jitter 0.0): exhaustion walk with a sibling arm at attempt 2 - rung 2 gated, retry-after stamped 0.25s."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', exhausting=True, arm_at=2)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_recover')
    assert clock.sleeps == [0.1, 0.325, 0.9, 1.8]  # gated rung 2, then rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.25)  # the exhaustion re-arms the label


def test_grid_exhaust_walk_batch_recover_jitter_100(monkeypatch):
    """batch_recover (jitter 1.0): exhaustion walk with a sibling arm at attempt 2 - rung 2 gated, retry-after stamped 0.5s."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', exhausting=True, arm_at=2)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_recover')
    assert clock.sleeps == [0.2, 0.65, 1.8, 3.6]  # gated rung 2, then rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.5)  # the exhaustion re-arms the label


def test_grid_exhaust_walk_batch_fail_jitter_000(monkeypatch):
    """batch_fail (jitter 0.0): exhaustion walk with a sibling arm at attempt 2 - rung 2 gated, retry-after stamped 0.25s."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', exhausting=True, arm_at=2)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_fail')
    assert clock.sleeps == [0.1, 0.325, 0.9, 1.8]  # gated rung 2, then rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.25)  # the exhaustion re-arms the label


def test_grid_exhaust_walk_batch_fail_jitter_100(monkeypatch):
    """batch_fail (jitter 1.0): exhaustion walk with a sibling arm at attempt 2 - rung 2 gated, retry-after stamped 0.5s."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', exhausting=True, arm_at=2)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_fail')
    assert clock.sleeps == [0.2, 0.65, 1.8, 3.6]  # gated rung 2, then rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.5)  # the exhaustion re-arms the label


def test_grid_exhaust_walk_batch_complete_jitter_000(monkeypatch):
    """batch_complete (jitter 0.0): exhaustion walk with a sibling arm at attempt 2 - rung 2 gated, retry-after stamped 0.25s."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', exhausting=True, arm_at=2)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_complete')
    assert clock.sleeps == [0.1, 0.325, 0.9, 1.8]  # gated rung 2, then rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.25)  # the exhaustion re-arms the label


def test_grid_exhaust_walk_batch_complete_jitter_100(monkeypatch):
    """batch_complete (jitter 1.0): exhaustion walk with a sibling arm at attempt 2 - rung 2 gated, retry-after stamped 0.5s."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', exhausting=True, arm_at=2)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_complete')
    assert clock.sleeps == [0.2, 0.65, 1.8, 3.6]  # gated rung 2, then rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.5)  # the exhaustion re-arms the label


def test_grid_exhaust_walk_batch_defer_jitter_000(monkeypatch):
    """batch_defer (jitter 0.0): exhaustion walk with a sibling arm at attempt 2 - rung 2 gated, retry-after stamped 0.25s."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', exhausting=True, arm_at=2)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_defer')
    assert clock.sleeps == [0.1, 0.325, 0.9, 1.8]  # gated rung 2, then rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.25)  # the exhaustion re-arms the label


def test_grid_exhaust_walk_batch_defer_jitter_100(monkeypatch):
    """batch_defer (jitter 1.0): exhaustion walk with a sibling arm at attempt 2 - rung 2 gated, retry-after stamped 0.5s."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', exhausting=True, arm_at=2)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_defer')
    assert clock.sleeps == [0.2, 0.65, 1.8, 3.6]  # gated rung 2, then rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.5)  # the exhaustion re-arms the label


def test_grid_exhaust_walk_batch_heartbeat_jitter_000(monkeypatch):
    """batch_heartbeat (jitter 0.0): exhaustion walk with a sibling arm at attempt 2 - rung 2 gated, retry-after stamped 0.25s."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_heartbeat', exhausting=True, arm_at=2)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_heartbeat')
    assert clock.sleeps == [0.1, 0.325, 0.9, 1.8]  # gated rung 2, then rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.25)  # the exhaustion re-arms the label


def test_grid_exhaust_walk_batch_heartbeat_jitter_100(monkeypatch):
    """batch_heartbeat (jitter 1.0): exhaustion walk with a sibling arm at attempt 2 - rung 2 gated, retry-after stamped 0.5s."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_heartbeat', exhausting=True, arm_at=2)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_heartbeat')
    assert clock.sleeps == [0.2, 0.65, 1.8, 3.6]  # gated rung 2, then rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.5)  # the exhaustion re-arms the label


def test_grid_exhaust_walk_batch_admit_jitter_000(monkeypatch):
    """batch_admit (jitter 0.0): exhaustion walk with a sibling arm at attempt 2 - rung 2 gated, retry-after stamped 0.25s."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', exhausting=True, arm_at=2)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_admit')
    assert clock.sleeps == [0.1, 0.325, 0.9, 1.8]  # gated rung 2, then rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.25)  # the exhaustion re-arms the label


def test_grid_exhaust_walk_batch_admit_jitter_100(monkeypatch):
    """batch_admit (jitter 1.0): exhaustion walk with a sibling arm at attempt 2 - rung 2 gated, retry-after stamped 0.5s."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', exhausting=True, arm_at=2)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_admit')
    assert clock.sleeps == [0.2, 0.65, 1.8, 3.6]  # gated rung 2, then rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.5)  # the exhaustion re-arms the label


def test_grid_exhaust_walk_batch_enqueue_jitter_000(monkeypatch):
    """batch_enqueue (jitter 0.0): exhaustion walk with a sibling arm at attempt 2 - rung 2 gated, retry-after stamped 0.25s."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_enqueue', exhausting=True, arm_at=2)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_enqueue')
    assert clock.sleeps == [0.1, 0.325, 0.9, 1.8]  # gated rung 2, then rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.25)  # the exhaustion re-arms the label


def test_grid_exhaust_walk_batch_enqueue_jitter_100(monkeypatch):
    """batch_enqueue (jitter 1.0): exhaustion walk with a sibling arm at attempt 2 - rung 2 gated, retry-after stamped 0.5s."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_enqueue', exhausting=True, arm_at=2)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_enqueue')
    assert clock.sleeps == [0.2, 0.65, 1.8, 3.6]  # gated rung 2, then rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.5)  # the exhaustion re-arms the label


def test_grid_exhaust_walk_batch_intake_status_jitter_000(monkeypatch):
    """batch_intake_status (jitter 0.0): exhaustion walk with a sibling arm at attempt 2 - rung 2 gated, retry-after stamped 0.25s."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_intake_status', exhausting=True, arm_at=2
    )
    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_intake_status')
    assert clock.sleeps == [0.1, 0.325, 0.9, 1.8]  # gated rung 2, then rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.25)  # the exhaustion re-arms the label


def test_grid_exhaust_walk_batch_intake_status_jitter_100(monkeypatch):
    """batch_intake_status (jitter 1.0): exhaustion walk with a sibling arm at attempt 2 - rung 2 gated, retry-after stamped 0.5s."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_intake_status', exhausting=True, arm_at=2
    )
    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_intake_status')
    assert clock.sleeps == [0.2, 0.65, 1.8, 3.6]  # gated rung 2, then rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.5)  # the exhaustion re-arms the label


def test_grid_exhaust_walk_batch_seal_register_jitter_000(monkeypatch):
    """batch_seal_register (jitter 0.0): exhaustion walk with a sibling arm at attempt 2 - rung 2 gated, retry-after stamped 0.25s."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_seal_register', exhausting=True, arm_at=2
    )
    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_seal_register')
    assert clock.sleeps == [0.1, 0.325, 0.9, 1.8]  # gated rung 2, then rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.25)  # the exhaustion re-arms the label


def test_grid_exhaust_walk_batch_seal_register_jitter_100(monkeypatch):
    """batch_seal_register (jitter 1.0): exhaustion walk with a sibling arm at attempt 2 - rung 2 gated, retry-after stamped 0.5s."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_seal_register', exhausting=True, arm_at=2
    )
    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_seal_register')
    assert clock.sleeps == [0.2, 0.65, 1.8, 3.6]  # gated rung 2, then rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.5)  # the exhaustion re-arms the label


def test_grid_exhaust_walk_batch_release_jitter_000(monkeypatch):
    """batch_release (jitter 0.0): exhaustion walk with a sibling arm at attempt 2 - rung 2 gated, retry-after stamped 0.25s."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', exhausting=True, arm_at=2)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_release')
    assert clock.sleeps == [0.1, 0.325, 0.9, 1.8]  # gated rung 2, then rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.25)  # the exhaustion re-arms the label


def test_grid_exhaust_walk_batch_release_jitter_100(monkeypatch):
    """batch_release (jitter 1.0): exhaustion walk with a sibling arm at attempt 2 - rung 2 gated, retry-after stamped 0.5s."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', exhausting=True, arm_at=2)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_release')
    assert clock.sleeps == [0.2, 0.65, 1.8, 3.6]  # gated rung 2, then rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.5)  # the exhaustion re-arms the label


def test_grid_exhaust_walk_batch_redrive_jitter_000(monkeypatch):
    """batch_redrive (jitter 0.0): exhaustion walk with a sibling arm at attempt 2 - rung 2 gated, retry-after stamped 0.25s."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', exhausting=True, arm_at=2)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_redrive')
    assert clock.sleeps == [0.1, 0.325, 0.9, 1.8]  # gated rung 2, then rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.25)  # the exhaustion re-arms the label


def test_grid_exhaust_walk_batch_redrive_jitter_100(monkeypatch):
    """batch_redrive (jitter 1.0): exhaustion walk with a sibling arm at attempt 2 - rung 2 gated, retry-after stamped 0.5s."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', exhausting=True, arm_at=2)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_redrive')
    assert clock.sleeps == [0.2, 0.65, 1.8, 3.6]  # gated rung 2, then rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.5)  # the exhaustion re-arms the label


def test_grid_exhaust_walk_batch_pull_shard_scheduler_00_jitter_000(monkeypatch):
    """batch_pull shard=scheduler_00 (jitter 0.0): exhaustion walk with a sibling arm at attempt 2 - rung 2 gated, retry-after stamped 0.25s."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_pull shard=scheduler_00', exhausting=True, arm_at=2
    )
    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_pull shard=scheduler_00')
    assert clock.sleeps == [0.1, 0.325, 0.9, 1.8]  # gated rung 2, then rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.25)  # the exhaustion re-arms the label


def test_grid_exhaust_walk_batch_pull_shard_scheduler_00_jitter_100(monkeypatch):
    """batch_pull shard=scheduler_00 (jitter 1.0): exhaustion walk with a sibling arm at attempt 2 - rung 2 gated, retry-after stamped 0.5s."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_pull shard=scheduler_00', exhausting=True, arm_at=2
    )
    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_pull shard=scheduler_00')
    assert clock.sleeps == [0.2, 0.65, 1.8, 3.6]  # gated rung 2, then rungs 3-4 ride their wave waits
    assert caught.value.retry_after == pytest.approx(0.5)  # the exhaustion re-arms the label


def test_grid_success_clears_batch_provider_stt_jitter_000(monkeypatch):
    """batch_provider_stt (jitter 0.0): success after a mid-chain arm clears the ladder (latest-generation guard)."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    residual, generation = damper.peek('batch_provider_stt')
    assert residual == 0.0 and generation == 0  # success cleared the mid-chain arm


def test_grid_success_clears_batch_provider_stt_jitter_100(monkeypatch):
    """batch_provider_stt (jitter 1.0): success after a mid-chain arm clears the ladder (latest-generation guard)."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    residual, generation = damper.peek('batch_provider_stt')
    assert residual == 0.0 and generation == 0  # success cleared the mid-chain arm


def test_grid_success_clears_batch_merge_commit_jitter_000(monkeypatch):
    """batch_merge_commit (jitter 0.0): success after a mid-chain arm clears the ladder (latest-generation guard)."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    residual, generation = damper.peek('batch_merge_commit')
    assert residual == 0.0 and generation == 0  # success cleared the mid-chain arm


def test_grid_success_clears_batch_merge_commit_jitter_100(monkeypatch):
    """batch_merge_commit (jitter 1.0): success after a mid-chain arm clears the ladder (latest-generation guard)."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    residual, generation = damper.peek('batch_merge_commit')
    assert residual == 0.0 and generation == 0  # success cleared the mid-chain arm


def test_grid_success_clears_batch_recover_jitter_000(monkeypatch):
    """batch_recover (jitter 0.0): success after a mid-chain arm clears the ladder (latest-generation guard)."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_recover') == 'committed'
    residual, generation = damper.peek('batch_recover')
    assert residual == 0.0 and generation == 0  # success cleared the mid-chain arm


def test_grid_success_clears_batch_recover_jitter_100(monkeypatch):
    """batch_recover (jitter 1.0): success after a mid-chain arm clears the ladder (latest-generation guard)."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_recover') == 'committed'
    residual, generation = damper.peek('batch_recover')
    assert residual == 0.0 and generation == 0  # success cleared the mid-chain arm


def test_grid_success_clears_batch_fail_jitter_000(monkeypatch):
    """batch_fail (jitter 0.0): success after a mid-chain arm clears the ladder (latest-generation guard)."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_fail') == 'committed'
    residual, generation = damper.peek('batch_fail')
    assert residual == 0.0 and generation == 0  # success cleared the mid-chain arm


def test_grid_success_clears_batch_fail_jitter_100(monkeypatch):
    """batch_fail (jitter 1.0): success after a mid-chain arm clears the ladder (latest-generation guard)."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_fail') == 'committed'
    residual, generation = damper.peek('batch_fail')
    assert residual == 0.0 and generation == 0  # success cleared the mid-chain arm


def test_grid_success_clears_batch_complete_jitter_000(monkeypatch):
    """batch_complete (jitter 0.0): success after a mid-chain arm clears the ladder (latest-generation guard)."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_complete') == 'committed'
    residual, generation = damper.peek('batch_complete')
    assert residual == 0.0 and generation == 0  # success cleared the mid-chain arm


def test_grid_success_clears_batch_complete_jitter_100(monkeypatch):
    """batch_complete (jitter 1.0): success after a mid-chain arm clears the ladder (latest-generation guard)."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_complete') == 'committed'
    residual, generation = damper.peek('batch_complete')
    assert residual == 0.0 and generation == 0  # success cleared the mid-chain arm


def test_grid_success_clears_batch_defer_jitter_000(monkeypatch):
    """batch_defer (jitter 0.0): success after a mid-chain arm clears the ladder (latest-generation guard)."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_defer') == 'committed'
    residual, generation = damper.peek('batch_defer')
    assert residual == 0.0 and generation == 0  # success cleared the mid-chain arm


def test_grid_success_clears_batch_defer_jitter_100(monkeypatch):
    """batch_defer (jitter 1.0): success after a mid-chain arm clears the ladder (latest-generation guard)."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_defer') == 'committed'
    residual, generation = damper.peek('batch_defer')
    assert residual == 0.0 and generation == 0  # success cleared the mid-chain arm


def test_grid_success_clears_batch_heartbeat_jitter_000(monkeypatch):
    """batch_heartbeat (jitter 0.0): success after a mid-chain arm clears the ladder (latest-generation guard)."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_heartbeat', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_heartbeat') == 'committed'
    residual, generation = damper.peek('batch_heartbeat')
    assert residual == 0.0 and generation == 0  # success cleared the mid-chain arm


def test_grid_success_clears_batch_heartbeat_jitter_100(monkeypatch):
    """batch_heartbeat (jitter 1.0): success after a mid-chain arm clears the ladder (latest-generation guard)."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_heartbeat', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_heartbeat') == 'committed'
    residual, generation = damper.peek('batch_heartbeat')
    assert residual == 0.0 and generation == 0  # success cleared the mid-chain arm


def test_grid_success_clears_batch_admit_jitter_000(monkeypatch):
    """batch_admit (jitter 0.0): success after a mid-chain arm clears the ladder (latest-generation guard)."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_admit') == 'committed'
    residual, generation = damper.peek('batch_admit')
    assert residual == 0.0 and generation == 0  # success cleared the mid-chain arm


def test_grid_success_clears_batch_admit_jitter_100(monkeypatch):
    """batch_admit (jitter 1.0): success after a mid-chain arm clears the ladder (latest-generation guard)."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_admit') == 'committed'
    residual, generation = damper.peek('batch_admit')
    assert residual == 0.0 and generation == 0  # success cleared the mid-chain arm


def test_grid_success_clears_batch_enqueue_jitter_000(monkeypatch):
    """batch_enqueue (jitter 0.0): success after a mid-chain arm clears the ladder (latest-generation guard)."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_enqueue', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_enqueue') == 'committed'
    residual, generation = damper.peek('batch_enqueue')
    assert residual == 0.0 and generation == 0  # success cleared the mid-chain arm


def test_grid_success_clears_batch_enqueue_jitter_100(monkeypatch):
    """batch_enqueue (jitter 1.0): success after a mid-chain arm clears the ladder (latest-generation guard)."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_enqueue', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_enqueue') == 'committed'
    residual, generation = damper.peek('batch_enqueue')
    assert residual == 0.0 and generation == 0  # success cleared the mid-chain arm


def test_grid_success_clears_batch_intake_status_jitter_000(monkeypatch):
    """batch_intake_status (jitter 0.0): success after a mid-chain arm clears the ladder (latest-generation guard)."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    residual, generation = damper.peek('batch_intake_status')
    assert residual == 0.0 and generation == 0  # success cleared the mid-chain arm


def test_grid_success_clears_batch_intake_status_jitter_100(monkeypatch):
    """batch_intake_status (jitter 1.0): success after a mid-chain arm clears the ladder (latest-generation guard)."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    residual, generation = damper.peek('batch_intake_status')
    assert residual == 0.0 and generation == 0  # success cleared the mid-chain arm


def test_grid_success_clears_batch_seal_register_jitter_000(monkeypatch):
    """batch_seal_register (jitter 0.0): success after a mid-chain arm clears the ladder (latest-generation guard)."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    residual, generation = damper.peek('batch_seal_register')
    assert residual == 0.0 and generation == 0  # success cleared the mid-chain arm


def test_grid_success_clears_batch_seal_register_jitter_100(monkeypatch):
    """batch_seal_register (jitter 1.0): success after a mid-chain arm clears the ladder (latest-generation guard)."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    residual, generation = damper.peek('batch_seal_register')
    assert residual == 0.0 and generation == 0  # success cleared the mid-chain arm


def test_grid_success_clears_batch_release_jitter_000(monkeypatch):
    """batch_release (jitter 0.0): success after a mid-chain arm clears the ladder (latest-generation guard)."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_release') == 'committed'
    residual, generation = damper.peek('batch_release')
    assert residual == 0.0 and generation == 0  # success cleared the mid-chain arm


def test_grid_success_clears_batch_release_jitter_100(monkeypatch):
    """batch_release (jitter 1.0): success after a mid-chain arm clears the ladder (latest-generation guard)."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_release') == 'committed'
    residual, generation = damper.peek('batch_release')
    assert residual == 0.0 and generation == 0  # success cleared the mid-chain arm


def test_grid_success_clears_batch_redrive_jitter_000(monkeypatch):
    """batch_redrive (jitter 0.0): success after a mid-chain arm clears the ladder (latest-generation guard)."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_redrive') == 'committed'
    residual, generation = damper.peek('batch_redrive')
    assert residual == 0.0 and generation == 0  # success cleared the mid-chain arm


def test_grid_success_clears_batch_redrive_jitter_100(monkeypatch):
    """batch_redrive (jitter 1.0): success after a mid-chain arm clears the ladder (latest-generation guard)."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=2, arm_at=2)
    assert store.run(body, operation='batch_redrive') == 'committed'
    residual, generation = damper.peek('batch_redrive')
    assert residual == 0.0 and generation == 0  # success cleared the mid-chain arm


def test_grid_success_clears_batch_pull_shard_scheduler_00_jitter_000(monkeypatch):
    """batch_pull shard=scheduler_00 (jitter 0.0): success after a mid-chain arm clears the ladder (latest-generation guard)."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_pull shard=scheduler_00', aborts=2, arm_at=2
    )
    assert store.run(body, operation='batch_pull shard=scheduler_00') == 'committed'
    residual, generation = damper.peek('batch_pull shard=scheduler_00')
    assert residual == 0.0 and generation == 0  # success cleared the mid-chain arm


def test_grid_success_clears_batch_pull_shard_scheduler_00_jitter_100(monkeypatch):
    """batch_pull shard=scheduler_00 (jitter 1.0): success after a mid-chain arm clears the ladder (latest-generation guard)."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_pull shard=scheduler_00', aborts=2, arm_at=2
    )
    assert store.run(body, operation='batch_pull shard=scheduler_00') == 'committed'
    residual, generation = damper.peek('batch_pull shard=scheduler_00')
    assert residual == 0.0 and generation == 0  # success cleared the mid-chain arm


def test_grid_arm_on_last_attempt_kept_batch_provider_stt_jitter_000(monkeypatch):
    """batch_provider_stt (jitter 0.0): an arm fired on the committing attempt survives the success guard (0.125s left)."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=2, arm_at=3)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    residual, generation = damper.peek('batch_provider_stt')
    assert residual == pytest.approx(0.125)
    assert generation == 1  # armed on the LAST peeked generation: the guard keeps the window


def test_grid_arm_on_last_attempt_kept_batch_provider_stt_jitter_100(monkeypatch):
    """batch_provider_stt (jitter 1.0): an arm fired on the committing attempt survives the success guard (0.25s left)."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=2, arm_at=3)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    residual, generation = damper.peek('batch_provider_stt')
    assert residual == pytest.approx(0.25)
    assert generation == 1  # armed on the LAST peeked generation: the guard keeps the window


def test_grid_arm_on_last_attempt_kept_batch_merge_commit_jitter_000(monkeypatch):
    """batch_merge_commit (jitter 0.0): an arm fired on the committing attempt survives the success guard (0.125s left)."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=2, arm_at=3)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    residual, generation = damper.peek('batch_merge_commit')
    assert residual == pytest.approx(0.125)
    assert generation == 1  # armed on the LAST peeked generation: the guard keeps the window


def test_grid_arm_on_last_attempt_kept_batch_merge_commit_jitter_100(monkeypatch):
    """batch_merge_commit (jitter 1.0): an arm fired on the committing attempt survives the success guard (0.25s left)."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=2, arm_at=3)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    residual, generation = damper.peek('batch_merge_commit')
    assert residual == pytest.approx(0.25)
    assert generation == 1  # armed on the LAST peeked generation: the guard keeps the window


def test_grid_arm_on_last_attempt_kept_batch_recover_jitter_000(monkeypatch):
    """batch_recover (jitter 0.0): an arm fired on the committing attempt survives the success guard (0.125s left)."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=2, arm_at=3)
    assert store.run(body, operation='batch_recover') == 'committed'
    residual, generation = damper.peek('batch_recover')
    assert residual == pytest.approx(0.125)
    assert generation == 1  # armed on the LAST peeked generation: the guard keeps the window


def test_grid_arm_on_last_attempt_kept_batch_recover_jitter_100(monkeypatch):
    """batch_recover (jitter 1.0): an arm fired on the committing attempt survives the success guard (0.25s left)."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=2, arm_at=3)
    assert store.run(body, operation='batch_recover') == 'committed'
    residual, generation = damper.peek('batch_recover')
    assert residual == pytest.approx(0.25)
    assert generation == 1  # armed on the LAST peeked generation: the guard keeps the window


def test_grid_arm_on_last_attempt_kept_batch_fail_jitter_000(monkeypatch):
    """batch_fail (jitter 0.0): an arm fired on the committing attempt survives the success guard (0.125s left)."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=2, arm_at=3)
    assert store.run(body, operation='batch_fail') == 'committed'
    residual, generation = damper.peek('batch_fail')
    assert residual == pytest.approx(0.125)
    assert generation == 1  # armed on the LAST peeked generation: the guard keeps the window


def test_grid_arm_on_last_attempt_kept_batch_fail_jitter_100(monkeypatch):
    """batch_fail (jitter 1.0): an arm fired on the committing attempt survives the success guard (0.25s left)."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=2, arm_at=3)
    assert store.run(body, operation='batch_fail') == 'committed'
    residual, generation = damper.peek('batch_fail')
    assert residual == pytest.approx(0.25)
    assert generation == 1  # armed on the LAST peeked generation: the guard keeps the window


def test_grid_arm_on_last_attempt_kept_batch_complete_jitter_000(monkeypatch):
    """batch_complete (jitter 0.0): an arm fired on the committing attempt survives the success guard (0.125s left)."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=2, arm_at=3)
    assert store.run(body, operation='batch_complete') == 'committed'
    residual, generation = damper.peek('batch_complete')
    assert residual == pytest.approx(0.125)
    assert generation == 1  # armed on the LAST peeked generation: the guard keeps the window


def test_grid_arm_on_last_attempt_kept_batch_complete_jitter_100(monkeypatch):
    """batch_complete (jitter 1.0): an arm fired on the committing attempt survives the success guard (0.25s left)."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=2, arm_at=3)
    assert store.run(body, operation='batch_complete') == 'committed'
    residual, generation = damper.peek('batch_complete')
    assert residual == pytest.approx(0.25)
    assert generation == 1  # armed on the LAST peeked generation: the guard keeps the window


def test_grid_arm_on_last_attempt_kept_batch_defer_jitter_000(monkeypatch):
    """batch_defer (jitter 0.0): an arm fired on the committing attempt survives the success guard (0.125s left)."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=2, arm_at=3)
    assert store.run(body, operation='batch_defer') == 'committed'
    residual, generation = damper.peek('batch_defer')
    assert residual == pytest.approx(0.125)
    assert generation == 1  # armed on the LAST peeked generation: the guard keeps the window


def test_grid_arm_on_last_attempt_kept_batch_defer_jitter_100(monkeypatch):
    """batch_defer (jitter 1.0): an arm fired on the committing attempt survives the success guard (0.25s left)."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=2, arm_at=3)
    assert store.run(body, operation='batch_defer') == 'committed'
    residual, generation = damper.peek('batch_defer')
    assert residual == pytest.approx(0.25)
    assert generation == 1  # armed on the LAST peeked generation: the guard keeps the window


def test_grid_arm_on_last_attempt_kept_batch_heartbeat_jitter_000(monkeypatch):
    """batch_heartbeat (jitter 0.0): an arm fired on the committing attempt survives the success guard (0.125s left)."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_heartbeat', aborts=2, arm_at=3)
    assert store.run(body, operation='batch_heartbeat') == 'committed'
    residual, generation = damper.peek('batch_heartbeat')
    assert residual == pytest.approx(0.125)
    assert generation == 1  # armed on the LAST peeked generation: the guard keeps the window


def test_grid_arm_on_last_attempt_kept_batch_heartbeat_jitter_100(monkeypatch):
    """batch_heartbeat (jitter 1.0): an arm fired on the committing attempt survives the success guard (0.25s left)."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_heartbeat', aborts=2, arm_at=3)
    assert store.run(body, operation='batch_heartbeat') == 'committed'
    residual, generation = damper.peek('batch_heartbeat')
    assert residual == pytest.approx(0.25)
    assert generation == 1  # armed on the LAST peeked generation: the guard keeps the window


def test_grid_arm_on_last_attempt_kept_batch_admit_jitter_000(monkeypatch):
    """batch_admit (jitter 0.0): an arm fired on the committing attempt survives the success guard (0.125s left)."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=2, arm_at=3)
    assert store.run(body, operation='batch_admit') == 'committed'
    residual, generation = damper.peek('batch_admit')
    assert residual == pytest.approx(0.125)
    assert generation == 1  # armed on the LAST peeked generation: the guard keeps the window


def test_grid_arm_on_last_attempt_kept_batch_admit_jitter_100(monkeypatch):
    """batch_admit (jitter 1.0): an arm fired on the committing attempt survives the success guard (0.25s left)."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=2, arm_at=3)
    assert store.run(body, operation='batch_admit') == 'committed'
    residual, generation = damper.peek('batch_admit')
    assert residual == pytest.approx(0.25)
    assert generation == 1  # armed on the LAST peeked generation: the guard keeps the window


def test_grid_arm_on_last_attempt_kept_batch_enqueue_jitter_000(monkeypatch):
    """batch_enqueue (jitter 0.0): an arm fired on the committing attempt survives the success guard (0.125s left)."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_enqueue', aborts=2, arm_at=3)
    assert store.run(body, operation='batch_enqueue') == 'committed'
    residual, generation = damper.peek('batch_enqueue')
    assert residual == pytest.approx(0.125)
    assert generation == 1  # armed on the LAST peeked generation: the guard keeps the window


def test_grid_arm_on_last_attempt_kept_batch_enqueue_jitter_100(monkeypatch):
    """batch_enqueue (jitter 1.0): an arm fired on the committing attempt survives the success guard (0.25s left)."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_enqueue', aborts=2, arm_at=3)
    assert store.run(body, operation='batch_enqueue') == 'committed'
    residual, generation = damper.peek('batch_enqueue')
    assert residual == pytest.approx(0.25)
    assert generation == 1  # armed on the LAST peeked generation: the guard keeps the window


def test_grid_arm_on_last_attempt_kept_batch_intake_status_jitter_000(monkeypatch):
    """batch_intake_status (jitter 0.0): an arm fired on the committing attempt survives the success guard (0.125s left)."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=2, arm_at=3)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    residual, generation = damper.peek('batch_intake_status')
    assert residual == pytest.approx(0.125)
    assert generation == 1  # armed on the LAST peeked generation: the guard keeps the window


def test_grid_arm_on_last_attempt_kept_batch_intake_status_jitter_100(monkeypatch):
    """batch_intake_status (jitter 1.0): an arm fired on the committing attempt survives the success guard (0.25s left)."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=2, arm_at=3)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    residual, generation = damper.peek('batch_intake_status')
    assert residual == pytest.approx(0.25)
    assert generation == 1  # armed on the LAST peeked generation: the guard keeps the window


def test_grid_arm_on_last_attempt_kept_batch_seal_register_jitter_000(monkeypatch):
    """batch_seal_register (jitter 0.0): an arm fired on the committing attempt survives the success guard (0.125s left)."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=2, arm_at=3)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    residual, generation = damper.peek('batch_seal_register')
    assert residual == pytest.approx(0.125)
    assert generation == 1  # armed on the LAST peeked generation: the guard keeps the window


def test_grid_arm_on_last_attempt_kept_batch_seal_register_jitter_100(monkeypatch):
    """batch_seal_register (jitter 1.0): an arm fired on the committing attempt survives the success guard (0.25s left)."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=2, arm_at=3)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    residual, generation = damper.peek('batch_seal_register')
    assert residual == pytest.approx(0.25)
    assert generation == 1  # armed on the LAST peeked generation: the guard keeps the window


def test_grid_arm_on_last_attempt_kept_batch_release_jitter_000(monkeypatch):
    """batch_release (jitter 0.0): an arm fired on the committing attempt survives the success guard (0.125s left)."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=2, arm_at=3)
    assert store.run(body, operation='batch_release') == 'committed'
    residual, generation = damper.peek('batch_release')
    assert residual == pytest.approx(0.125)
    assert generation == 1  # armed on the LAST peeked generation: the guard keeps the window


def test_grid_arm_on_last_attempt_kept_batch_release_jitter_100(monkeypatch):
    """batch_release (jitter 1.0): an arm fired on the committing attempt survives the success guard (0.25s left)."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=2, arm_at=3)
    assert store.run(body, operation='batch_release') == 'committed'
    residual, generation = damper.peek('batch_release')
    assert residual == pytest.approx(0.25)
    assert generation == 1  # armed on the LAST peeked generation: the guard keeps the window


def test_grid_arm_on_last_attempt_kept_batch_redrive_jitter_000(monkeypatch):
    """batch_redrive (jitter 0.0): an arm fired on the committing attempt survives the success guard (0.125s left)."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=2, arm_at=3)
    assert store.run(body, operation='batch_redrive') == 'committed'
    residual, generation = damper.peek('batch_redrive')
    assert residual == pytest.approx(0.125)
    assert generation == 1  # armed on the LAST peeked generation: the guard keeps the window


def test_grid_arm_on_last_attempt_kept_batch_redrive_jitter_100(monkeypatch):
    """batch_redrive (jitter 1.0): an arm fired on the committing attempt survives the success guard (0.25s left)."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=2, arm_at=3)
    assert store.run(body, operation='batch_redrive') == 'committed'
    residual, generation = damper.peek('batch_redrive')
    assert residual == pytest.approx(0.25)
    assert generation == 1  # armed on the LAST peeked generation: the guard keeps the window


def test_grid_arm_on_last_attempt_kept_batch_pull_shard_scheduler_00_jitter_000(monkeypatch):
    """batch_pull shard=scheduler_00 (jitter 0.0): an arm fired on the committing attempt survives the success guard (0.125s left)."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_pull shard=scheduler_00', aborts=2, arm_at=3
    )
    assert store.run(body, operation='batch_pull shard=scheduler_00') == 'committed'
    residual, generation = damper.peek('batch_pull shard=scheduler_00')
    assert residual == pytest.approx(0.125)
    assert generation == 1  # armed on the LAST peeked generation: the guard keeps the window


def test_grid_arm_on_last_attempt_kept_batch_pull_shard_scheduler_00_jitter_100(monkeypatch):
    """batch_pull shard=scheduler_00 (jitter 1.0): an arm fired on the committing attempt survives the success guard (0.25s left)."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_pull shard=scheduler_00', aborts=2, arm_at=3
    )
    assert store.run(body, operation='batch_pull shard=scheduler_00') == 'committed'
    residual, generation = damper.peek('batch_pull shard=scheduler_00')
    assert residual == pytest.approx(0.25)
    assert generation == 1  # armed on the LAST peeked generation: the guard keeps the window


def test_grid_double_arm_batch_provider_stt_jitter_000(monkeypatch):
    """batch_provider_stt (jitter 0.0): two mid-flight arms stack (0.125s then 0.5s) and clear on success."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=3, arm_at=(2, 3))
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.1, 0.325, 0.9]  # rung 2 waits the sibling window 0.125, rung 3 rides its 0.5 wave wait
    residual, generation = damper.peek('batch_provider_stt')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_double_arm_batch_provider_stt_jitter_100(monkeypatch):
    """batch_provider_stt (jitter 1.0): two mid-flight arms stack (0.25s then 1.0s) and clear on success."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=3, arm_at=(2, 3))
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.2, 0.65, 1.8]  # rung 2 waits the sibling window 0.25, rung 3 rides its 1.0 wave wait
    residual, generation = damper.peek('batch_provider_stt')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_double_arm_batch_merge_commit_jitter_000(monkeypatch):
    """batch_merge_commit (jitter 0.0): two mid-flight arms stack (0.125s then 0.5s) and clear on success."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=3, arm_at=(2, 3))
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.1, 0.325, 0.9]  # rung 2 waits the sibling window 0.125, rung 3 rides its 0.5 wave wait
    residual, generation = damper.peek('batch_merge_commit')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_double_arm_batch_merge_commit_jitter_100(monkeypatch):
    """batch_merge_commit (jitter 1.0): two mid-flight arms stack (0.25s then 1.0s) and clear on success."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=3, arm_at=(2, 3))
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.2, 0.65, 1.8]  # rung 2 waits the sibling window 0.25, rung 3 rides its 1.0 wave wait
    residual, generation = damper.peek('batch_merge_commit')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_double_arm_batch_recover_jitter_000(monkeypatch):
    """batch_recover (jitter 0.0): two mid-flight arms stack (0.125s then 0.5s) and clear on success."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=3, arm_at=(2, 3))
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.1, 0.325, 0.9]  # rung 2 waits the sibling window 0.125, rung 3 rides its 0.5 wave wait
    residual, generation = damper.peek('batch_recover')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_double_arm_batch_recover_jitter_100(monkeypatch):
    """batch_recover (jitter 1.0): two mid-flight arms stack (0.25s then 1.0s) and clear on success."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=3, arm_at=(2, 3))
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.2, 0.65, 1.8]  # rung 2 waits the sibling window 0.25, rung 3 rides its 1.0 wave wait
    residual, generation = damper.peek('batch_recover')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_double_arm_batch_fail_jitter_000(monkeypatch):
    """batch_fail (jitter 0.0): two mid-flight arms stack (0.125s then 0.5s) and clear on success."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=3, arm_at=(2, 3))
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.1, 0.325, 0.9]  # rung 2 waits the sibling window 0.125, rung 3 rides its 0.5 wave wait
    residual, generation = damper.peek('batch_fail')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_double_arm_batch_fail_jitter_100(monkeypatch):
    """batch_fail (jitter 1.0): two mid-flight arms stack (0.25s then 1.0s) and clear on success."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=3, arm_at=(2, 3))
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.2, 0.65, 1.8]  # rung 2 waits the sibling window 0.25, rung 3 rides its 1.0 wave wait
    residual, generation = damper.peek('batch_fail')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_double_arm_batch_complete_jitter_000(monkeypatch):
    """batch_complete (jitter 0.0): two mid-flight arms stack (0.125s then 0.5s) and clear on success."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=3, arm_at=(2, 3))
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.1, 0.325, 0.9]  # rung 2 waits the sibling window 0.125, rung 3 rides its 0.5 wave wait
    residual, generation = damper.peek('batch_complete')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_double_arm_batch_complete_jitter_100(monkeypatch):
    """batch_complete (jitter 1.0): two mid-flight arms stack (0.25s then 1.0s) and clear on success."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=3, arm_at=(2, 3))
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.2, 0.65, 1.8]  # rung 2 waits the sibling window 0.25, rung 3 rides its 1.0 wave wait
    residual, generation = damper.peek('batch_complete')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_double_arm_batch_defer_jitter_000(monkeypatch):
    """batch_defer (jitter 0.0): two mid-flight arms stack (0.125s then 0.5s) and clear on success."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=3, arm_at=(2, 3))
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.1, 0.325, 0.9]  # rung 2 waits the sibling window 0.125, rung 3 rides its 0.5 wave wait
    residual, generation = damper.peek('batch_defer')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_double_arm_batch_defer_jitter_100(monkeypatch):
    """batch_defer (jitter 1.0): two mid-flight arms stack (0.25s then 1.0s) and clear on success."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=3, arm_at=(2, 3))
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.2, 0.65, 1.8]  # rung 2 waits the sibling window 0.25, rung 3 rides its 1.0 wave wait
    residual, generation = damper.peek('batch_defer')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_double_arm_batch_heartbeat_jitter_000(monkeypatch):
    """batch_heartbeat (jitter 0.0): two mid-flight arms stack (0.125s then 0.5s) and clear on success."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_heartbeat', aborts=3, arm_at=(2, 3))
    assert store.run(body, operation='batch_heartbeat') == 'committed'
    assert clock.sleeps == [0.1, 0.325, 0.9]  # rung 2 waits the sibling window 0.125, rung 3 rides its 0.5 wave wait
    residual, generation = damper.peek('batch_heartbeat')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_double_arm_batch_heartbeat_jitter_100(monkeypatch):
    """batch_heartbeat (jitter 1.0): two mid-flight arms stack (0.25s then 1.0s) and clear on success."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_heartbeat', aborts=3, arm_at=(2, 3))
    assert store.run(body, operation='batch_heartbeat') == 'committed'
    assert clock.sleeps == [0.2, 0.65, 1.8]  # rung 2 waits the sibling window 0.25, rung 3 rides its 1.0 wave wait
    residual, generation = damper.peek('batch_heartbeat')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_double_arm_batch_admit_jitter_000(monkeypatch):
    """batch_admit (jitter 0.0): two mid-flight arms stack (0.125s then 0.5s) and clear on success."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=3, arm_at=(2, 3))
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.1, 0.325, 0.9]  # rung 2 waits the sibling window 0.125, rung 3 rides its 0.5 wave wait
    residual, generation = damper.peek('batch_admit')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_double_arm_batch_admit_jitter_100(monkeypatch):
    """batch_admit (jitter 1.0): two mid-flight arms stack (0.25s then 1.0s) and clear on success."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=3, arm_at=(2, 3))
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.2, 0.65, 1.8]  # rung 2 waits the sibling window 0.25, rung 3 rides its 1.0 wave wait
    residual, generation = damper.peek('batch_admit')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_double_arm_batch_enqueue_jitter_000(monkeypatch):
    """batch_enqueue (jitter 0.0): two mid-flight arms stack (0.125s then 0.5s) and clear on success."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_enqueue', aborts=3, arm_at=(2, 3))
    assert store.run(body, operation='batch_enqueue') == 'committed'
    assert clock.sleeps == [0.1, 0.325, 0.9]  # rung 2 waits the sibling window 0.125, rung 3 rides its 0.5 wave wait
    residual, generation = damper.peek('batch_enqueue')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_double_arm_batch_enqueue_jitter_100(monkeypatch):
    """batch_enqueue (jitter 1.0): two mid-flight arms stack (0.25s then 1.0s) and clear on success."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_enqueue', aborts=3, arm_at=(2, 3))
    assert store.run(body, operation='batch_enqueue') == 'committed'
    assert clock.sleeps == [0.2, 0.65, 1.8]  # rung 2 waits the sibling window 0.25, rung 3 rides its 1.0 wave wait
    residual, generation = damper.peek('batch_enqueue')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_double_arm_batch_intake_status_jitter_000(monkeypatch):
    """batch_intake_status (jitter 0.0): two mid-flight arms stack (0.125s then 0.5s) and clear on success."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=3, arm_at=(2, 3))
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.1, 0.325, 0.9]  # rung 2 waits the sibling window 0.125, rung 3 rides its 0.5 wave wait
    residual, generation = damper.peek('batch_intake_status')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_double_arm_batch_intake_status_jitter_100(monkeypatch):
    """batch_intake_status (jitter 1.0): two mid-flight arms stack (0.25s then 1.0s) and clear on success."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=3, arm_at=(2, 3))
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.2, 0.65, 1.8]  # rung 2 waits the sibling window 0.25, rung 3 rides its 1.0 wave wait
    residual, generation = damper.peek('batch_intake_status')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_double_arm_batch_seal_register_jitter_000(monkeypatch):
    """batch_seal_register (jitter 0.0): two mid-flight arms stack (0.125s then 0.5s) and clear on success."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=3, arm_at=(2, 3))
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.1, 0.325, 0.9]  # rung 2 waits the sibling window 0.125, rung 3 rides its 0.5 wave wait
    residual, generation = damper.peek('batch_seal_register')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_double_arm_batch_seal_register_jitter_100(monkeypatch):
    """batch_seal_register (jitter 1.0): two mid-flight arms stack (0.25s then 1.0s) and clear on success."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=3, arm_at=(2, 3))
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.2, 0.65, 1.8]  # rung 2 waits the sibling window 0.25, rung 3 rides its 1.0 wave wait
    residual, generation = damper.peek('batch_seal_register')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_double_arm_batch_release_jitter_000(monkeypatch):
    """batch_release (jitter 0.0): two mid-flight arms stack (0.125s then 0.5s) and clear on success."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=3, arm_at=(2, 3))
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.1, 0.325, 0.9]  # rung 2 waits the sibling window 0.125, rung 3 rides its 0.5 wave wait
    residual, generation = damper.peek('batch_release')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_double_arm_batch_release_jitter_100(monkeypatch):
    """batch_release (jitter 1.0): two mid-flight arms stack (0.25s then 1.0s) and clear on success."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=3, arm_at=(2, 3))
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.2, 0.65, 1.8]  # rung 2 waits the sibling window 0.25, rung 3 rides its 1.0 wave wait
    residual, generation = damper.peek('batch_release')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_double_arm_batch_redrive_jitter_000(monkeypatch):
    """batch_redrive (jitter 0.0): two mid-flight arms stack (0.125s then 0.5s) and clear on success."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=3, arm_at=(2, 3))
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.1, 0.325, 0.9]  # rung 2 waits the sibling window 0.125, rung 3 rides its 0.5 wave wait
    residual, generation = damper.peek('batch_redrive')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_double_arm_batch_redrive_jitter_100(monkeypatch):
    """batch_redrive (jitter 1.0): two mid-flight arms stack (0.25s then 1.0s) and clear on success."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=3, arm_at=(2, 3))
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.2, 0.65, 1.8]  # rung 2 waits the sibling window 0.25, rung 3 rides its 1.0 wave wait
    residual, generation = damper.peek('batch_redrive')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_double_arm_batch_pull_shard_scheduler_00_jitter_000(monkeypatch):
    """batch_pull shard=scheduler_00 (jitter 0.0): two mid-flight arms stack (0.125s then 0.5s) and clear on success."""
    clock = _Clock(jitter=0.0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_pull shard=scheduler_00', aborts=3, arm_at=(2, 3)
    )
    assert store.run(body, operation='batch_pull shard=scheduler_00') == 'committed'
    assert clock.sleeps == [0.1, 0.325, 0.9]  # rung 2 waits the sibling window 0.125, rung 3 rides its 0.5 wave wait
    residual, generation = damper.peek('batch_pull shard=scheduler_00')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_double_arm_batch_pull_shard_scheduler_00_jitter_100(monkeypatch):
    """batch_pull shard=scheduler_00 (jitter 1.0): two mid-flight arms stack (0.25s then 1.0s) and clear on success."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_pull shard=scheduler_00', aborts=3, arm_at=(2, 3)
    )
    assert store.run(body, operation='batch_pull shard=scheduler_00') == 'committed'
    assert clock.sleeps == [0.2, 0.65, 1.8]  # rung 2 waits the sibling window 0.25, rung 3 rides its 1.0 wave wait
    residual, generation = damper.peek('batch_pull shard=scheduler_00')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_log_taxonomy_batch_provider_stt(monkeypatch, caplog):
    """batch_provider_stt: exactly one mid_ladder INFO line naming the label, the failed attempt and the waited ms."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=2, arm_at=2)
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        assert store.run(body, operation='batch_provider_stt') == 'committed'
    lines = [record.getMessage() for record in caplog.records if 'scope=mid_ladder' in record.getMessage()]
    assert len(lines) == 1
    assert 'operation=batch_provider_stt' in lines[0]
    assert 'attempt=2' in lines[0]
    assert 'waited_ms=250' in lines[0]


def test_grid_log_taxonomy_batch_merge_commit(monkeypatch, caplog):
    """batch_merge_commit: exactly one mid_ladder INFO line naming the label, the failed attempt and the waited ms."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=2, arm_at=2)
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        assert store.run(body, operation='batch_merge_commit') == 'committed'
    lines = [record.getMessage() for record in caplog.records if 'scope=mid_ladder' in record.getMessage()]
    assert len(lines) == 1
    assert 'operation=batch_merge_commit' in lines[0]
    assert 'attempt=2' in lines[0]
    assert 'waited_ms=250' in lines[0]


def test_grid_log_taxonomy_batch_recover(monkeypatch, caplog):
    """batch_recover: exactly one mid_ladder INFO line naming the label, the failed attempt and the waited ms."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=2, arm_at=2)
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        assert store.run(body, operation='batch_recover') == 'committed'
    lines = [record.getMessage() for record in caplog.records if 'scope=mid_ladder' in record.getMessage()]
    assert len(lines) == 1
    assert 'operation=batch_recover' in lines[0]
    assert 'attempt=2' in lines[0]
    assert 'waited_ms=250' in lines[0]


def test_grid_log_taxonomy_batch_fail(monkeypatch, caplog):
    """batch_fail: exactly one mid_ladder INFO line naming the label, the failed attempt and the waited ms."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=2, arm_at=2)
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        assert store.run(body, operation='batch_fail') == 'committed'
    lines = [record.getMessage() for record in caplog.records if 'scope=mid_ladder' in record.getMessage()]
    assert len(lines) == 1
    assert 'operation=batch_fail' in lines[0]
    assert 'attempt=2' in lines[0]
    assert 'waited_ms=250' in lines[0]


def test_grid_log_taxonomy_batch_complete(monkeypatch, caplog):
    """batch_complete: exactly one mid_ladder INFO line naming the label, the failed attempt and the waited ms."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=2, arm_at=2)
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        assert store.run(body, operation='batch_complete') == 'committed'
    lines = [record.getMessage() for record in caplog.records if 'scope=mid_ladder' in record.getMessage()]
    assert len(lines) == 1
    assert 'operation=batch_complete' in lines[0]
    assert 'attempt=2' in lines[0]
    assert 'waited_ms=250' in lines[0]


def test_grid_log_taxonomy_batch_defer(monkeypatch, caplog):
    """batch_defer: exactly one mid_ladder INFO line naming the label, the failed attempt and the waited ms."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=2, arm_at=2)
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        assert store.run(body, operation='batch_defer') == 'committed'
    lines = [record.getMessage() for record in caplog.records if 'scope=mid_ladder' in record.getMessage()]
    assert len(lines) == 1
    assert 'operation=batch_defer' in lines[0]
    assert 'attempt=2' in lines[0]
    assert 'waited_ms=250' in lines[0]


def test_grid_log_taxonomy_batch_heartbeat(monkeypatch, caplog):
    """batch_heartbeat: exactly one mid_ladder INFO line naming the label, the failed attempt and the waited ms."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_heartbeat', aborts=2, arm_at=2)
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        assert store.run(body, operation='batch_heartbeat') == 'committed'
    lines = [record.getMessage() for record in caplog.records if 'scope=mid_ladder' in record.getMessage()]
    assert len(lines) == 1
    assert 'operation=batch_heartbeat' in lines[0]
    assert 'attempt=2' in lines[0]
    assert 'waited_ms=250' in lines[0]


def test_grid_log_taxonomy_batch_admit(monkeypatch, caplog):
    """batch_admit: exactly one mid_ladder INFO line naming the label, the failed attempt and the waited ms."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=2, arm_at=2)
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        assert store.run(body, operation='batch_admit') == 'committed'
    lines = [record.getMessage() for record in caplog.records if 'scope=mid_ladder' in record.getMessage()]
    assert len(lines) == 1
    assert 'operation=batch_admit' in lines[0]
    assert 'attempt=2' in lines[0]
    assert 'waited_ms=250' in lines[0]


def test_grid_log_taxonomy_batch_enqueue(monkeypatch, caplog):
    """batch_enqueue: exactly one mid_ladder INFO line naming the label, the failed attempt and the waited ms."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_enqueue', aborts=2, arm_at=2)
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        assert store.run(body, operation='batch_enqueue') == 'committed'
    lines = [record.getMessage() for record in caplog.records if 'scope=mid_ladder' in record.getMessage()]
    assert len(lines) == 1
    assert 'operation=batch_enqueue' in lines[0]
    assert 'attempt=2' in lines[0]
    assert 'waited_ms=250' in lines[0]


def test_grid_log_taxonomy_batch_intake_status(monkeypatch, caplog):
    """batch_intake_status: exactly one mid_ladder INFO line naming the label, the failed attempt and the waited ms."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=2, arm_at=2)
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        assert store.run(body, operation='batch_intake_status') == 'committed'
    lines = [record.getMessage() for record in caplog.records if 'scope=mid_ladder' in record.getMessage()]
    assert len(lines) == 1
    assert 'operation=batch_intake_status' in lines[0]
    assert 'attempt=2' in lines[0]
    assert 'waited_ms=250' in lines[0]


def test_grid_log_taxonomy_batch_seal_register(monkeypatch, caplog):
    """batch_seal_register: exactly one mid_ladder INFO line naming the label, the failed attempt and the waited ms."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=2, arm_at=2)
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        assert store.run(body, operation='batch_seal_register') == 'committed'
    lines = [record.getMessage() for record in caplog.records if 'scope=mid_ladder' in record.getMessage()]
    assert len(lines) == 1
    assert 'operation=batch_seal_register' in lines[0]
    assert 'attempt=2' in lines[0]
    assert 'waited_ms=250' in lines[0]


def test_grid_log_taxonomy_batch_release(monkeypatch, caplog):
    """batch_release: exactly one mid_ladder INFO line naming the label, the failed attempt and the waited ms."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=2, arm_at=2)
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        assert store.run(body, operation='batch_release') == 'committed'
    lines = [record.getMessage() for record in caplog.records if 'scope=mid_ladder' in record.getMessage()]
    assert len(lines) == 1
    assert 'operation=batch_release' in lines[0]
    assert 'attempt=2' in lines[0]
    assert 'waited_ms=250' in lines[0]


def test_grid_log_taxonomy_batch_redrive(monkeypatch, caplog):
    """batch_redrive: exactly one mid_ladder INFO line naming the label, the failed attempt and the waited ms."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=2, arm_at=2)
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        assert store.run(body, operation='batch_redrive') == 'committed'
    lines = [record.getMessage() for record in caplog.records if 'scope=mid_ladder' in record.getMessage()]
    assert len(lines) == 1
    assert 'operation=batch_redrive' in lines[0]
    assert 'attempt=2' in lines[0]
    assert 'waited_ms=250' in lines[0]


def test_grid_log_taxonomy_batch_pull_shard_scheduler_00(monkeypatch, caplog):
    """batch_pull shard=scheduler_00: exactly one mid_ladder INFO line naming the label, the failed attempt and the waited ms."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_pull shard=scheduler_00', aborts=2, arm_at=2
    )
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        assert store.run(body, operation='batch_pull shard=scheduler_00') == 'committed'
    lines = [record.getMessage() for record in caplog.records if 'scope=mid_ladder' in record.getMessage()]
    assert len(lines) == 1
    assert 'operation=batch_pull shard=scheduler_00' in lines[0]
    assert 'attempt=2' in lines[0]
    assert 'waited_ms=250' in lines[0]


def test_grid_composite_valid_batch_pull_shard_scheduler_00(monkeypatch):
    """batch_pull shard=scheduler_00: valid composite label walks the gated chain like any plain label."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_pull shard=scheduler_00', aborts=1)
    assert require_operation_label('batch_pull shard=scheduler_00') == 'batch_pull shard=scheduler_00'
    assert store.run(body, operation='batch_pull shard=scheduler_00') == 'committed'
    assert clock.sleeps == [0.1]  # one bare rung: composed shard labels gate like any other


def test_grid_composite_valid_batch_pull_shard_scheduler_63(monkeypatch):
    """batch_pull shard=scheduler_63: valid composite label walks the gated chain like any plain label."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_pull shard=scheduler_63', aborts=1)
    assert require_operation_label('batch_pull shard=scheduler_63') == 'batch_pull shard=scheduler_63'
    assert store.run(body, operation='batch_pull shard=scheduler_63') == 'committed'
    assert clock.sleeps == [0.1]  # one bare rung: composed shard labels gate like any other


def test_grid_composite_valid_batch_claim_shard_scheduler_31(monkeypatch):
    """batch_claim shard=scheduler_31: valid composite label walks the gated chain like any plain label."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_claim shard=scheduler_31', aborts=1)
    assert require_operation_label('batch_claim shard=scheduler_31') == 'batch_claim shard=scheduler_31'
    assert store.run(body, operation='batch_claim shard=scheduler_31') == 'committed'
    assert clock.sleeps == [0.1]  # one bare rung: composed shard labels gate like any other


def test_grid_composite_valid_batch_claim_shard_scheduler_05(monkeypatch):
    """batch_claim shard=scheduler_05: valid composite label walks the gated chain like any plain label."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_claim shard=scheduler_05', aborts=1)
    assert require_operation_label('batch_claim shard=scheduler_05') == 'batch_claim shard=scheduler_05'
    assert store.run(body, operation='batch_claim shard=scheduler_05') == 'committed'
    assert clock.sleeps == [0.1]  # one bare rung: composed shard labels gate like any other


def test_grid_label_refused_anonymous(monkeypatch):
    """Label anonymous: refused before any transaction opens; the gate never prices an unnamed storm."""
    clock = _Clock(jitter=1.0)
    store, _damper, client, _body = _make_store(monkeypatch, clock, label='batch_admit', aborts=1)
    with pytest.raises(ValueError):
        store.run(lambda tx: True, operation=None)
    client.transaction.assert_not_called()  # refused before any client touch
    assert clock.sleeps == []


def test_grid_label_refused_empty(monkeypatch):
    """Label empty: refused before any transaction opens; the gate never prices an unnamed storm."""
    clock = _Clock(jitter=1.0)
    store, _damper, client, _body = _make_store(monkeypatch, clock, label='batch_admit', aborts=1)
    with pytest.raises(ValueError):
        store.run(lambda tx: True, operation='')
    client.transaction.assert_not_called()  # refused before any client touch
    assert clock.sleeps == []


def test_grid_label_refused_uppercase(monkeypatch):
    """Label uppercase: refused before any transaction opens; the gate never prices an unnamed storm."""
    clock = _Clock(jitter=1.0)
    store, _damper, client, _body = _make_store(monkeypatch, clock, label='batch_admit', aborts=1)
    with pytest.raises(ValueError):
        store.run(lambda tx: True, operation='BATCH_PULL')
    client.transaction.assert_not_called()  # refused before any client touch
    assert clock.sleeps == []


def test_grid_label_refused_unknown_verb(monkeypatch):
    """Label unknown_verb: refused before any transaction opens; the gate never prices an unnamed storm."""
    clock = _Clock(jitter=1.0)
    store, _damper, client, _body = _make_store(monkeypatch, clock, label='batch_admit', aborts=1)
    with pytest.raises(ValueError):
        store.run(lambda tx: True, operation='batch_pul shard=scheduler_00')
    client.transaction.assert_not_called()  # refused before any client touch
    assert clock.sleeps == []


def test_grid_label_refused_bad_shard(monkeypatch):
    """Label bad_shard: refused before any transaction opens; the gate never prices an unnamed storm."""
    clock = _Clock(jitter=1.0)
    store, _damper, client, _body = _make_store(monkeypatch, clock, label='batch_admit', aborts=1)
    with pytest.raises(ValueError):
        store.run(lambda tx: True, operation='batch_pull shard=scheduler_99')
    client.transaction.assert_not_called()  # refused before any client touch
    assert clock.sleeps == []


def test_grid_label_refused_missing_digits(monkeypatch):
    """Label missing_digits: refused before any transaction opens; the gate never prices an unnamed storm."""
    clock = _Clock(jitter=1.0)
    store, _damper, client, _body = _make_store(monkeypatch, clock, label='batch_admit', aborts=1)
    with pytest.raises(ValueError):
        store.run(lambda tx: True, operation='batch_pull shard=scheduler_')
    client.transaction.assert_not_called()  # refused before any client touch
    assert clock.sleeps == []


def test_grid_label_refused_glued(monkeypatch):
    """Label glued: refused before any transaction opens; the gate never prices an unnamed storm."""
    clock = _Clock(jitter=1.0)
    store, _damper, client, _body = _make_store(monkeypatch, clock, label='batch_admit', aborts=1)
    with pytest.raises(ValueError):
        store.run(lambda tx: True, operation='batch_pullshard=scheduler_00')
    client.transaction.assert_not_called()  # refused before any client touch
    assert clock.sleeps == []


def test_grid_label_refused_spaced(monkeypatch):
    """Label spaced: refused before any transaction opens; the gate never prices an unnamed storm."""
    clock = _Clock(jitter=1.0)
    store, _damper, client, _body = _make_store(monkeypatch, clock, label='batch_admit', aborts=1)
    with pytest.raises(ValueError):
        store.run(lambda tx: True, operation='batch_pull shard = scheduler_00')
    client.transaction.assert_not_called()  # refused before any client touch
    assert clock.sleeps == []


def test_grid_label_refused_trailing(monkeypatch):
    """Label trailing: refused before any transaction opens; the gate never prices an unnamed storm."""
    clock = _Clock(jitter=1.0)
    store, _damper, client, _body = _make_store(monkeypatch, clock, label='batch_admit', aborts=1)
    with pytest.raises(ValueError):
        store.run(lambda tx: True, operation='batch_pull shard=scheduler_00 extra')
    client.transaction.assert_not_called()  # refused before any client touch
    assert clock.sleeps == []


def test_grid_label_refused_too_long(monkeypatch):
    """Label too_long: refused before any transaction opens; the gate never prices an unnamed storm."""
    clock = _Clock(jitter=1.0)
    store, _damper, client, _body = _make_store(monkeypatch, clock, label='batch_admit', aborts=1)
    with pytest.raises(ValueError):
        store.run(lambda tx: True, operation='bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb')
    client.transaction.assert_not_called()  # refused before any client touch
    assert clock.sleeps == []


def test_grid_label_refused_interpolated(monkeypatch):
    """Label interpolated: refused before any transaction opens; the gate never prices an unnamed storm."""
    clock = _Clock(jitter=1.0)
    store, _damper, client, _body = _make_store(monkeypatch, clock, label='batch_admit', aborts=1)
    with pytest.raises(ValueError):
        store.run(lambda tx: True, operation="batch_x'; drop table jobs")
    client.transaction.assert_not_called()  # refused before any client touch
    assert clock.sleeps == []


def test_grid_label_refused_numeric_start(monkeypatch):
    """Label numeric_start: refused before any transaction opens; the gate never prices an unnamed storm."""
    clock = _Clock(jitter=1.0)
    store, _damper, client, _body = _make_store(monkeypatch, clock, label='batch_admit', aborts=1)
    with pytest.raises(ValueError):
        store.run(lambda tx: True, operation='1batch_pull')
    client.transaction.assert_not_called()  # refused before any client touch
    assert clock.sleeps == []


def test_grid_parity_quiet_batch_provider_stt(monkeypatch):
    """batch_provider_stt: damper active vs dormant on a quiet label - byte-identical bare schedule [0.15, 0.3]."""
    clock_active = _Clock(jitter=0.5)
    store_active, _d1, _c1, body_a = _make_store(monkeypatch, clock_active, label='batch_provider_stt', aborts=2)
    assert store_active.run(body_a, operation='batch_provider_stt') == 'committed'
    assert clock_active.sleeps == [0.15, 0.3]
    clock_dormant = _Clock(jitter=0.5)
    store_dormant, _d2, _c2, body_d = _make_store(
        monkeypatch,
        clock_dormant,
        label='batch_provider_stt',
        aborts=2,
        dormant_env='BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED',
    )
    assert store_dormant.run(body_d, operation='batch_provider_stt') == 'committed'
    assert clock_dormant.sleeps == [0.15, 0.3]  # identical: a quiet label never feels the gate


def test_grid_parity_quiet_batch_merge_commit(monkeypatch):
    """batch_merge_commit: damper active vs dormant on a quiet label - byte-identical bare schedule [0.15, 0.3]."""
    clock_active = _Clock(jitter=0.5)
    store_active, _d1, _c1, body_a = _make_store(monkeypatch, clock_active, label='batch_merge_commit', aborts=2)
    assert store_active.run(body_a, operation='batch_merge_commit') == 'committed'
    assert clock_active.sleeps == [0.15, 0.3]
    clock_dormant = _Clock(jitter=0.5)
    store_dormant, _d2, _c2, body_d = _make_store(
        monkeypatch,
        clock_dormant,
        label='batch_merge_commit',
        aborts=2,
        dormant_env='BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED',
    )
    assert store_dormant.run(body_d, operation='batch_merge_commit') == 'committed'
    assert clock_dormant.sleeps == [0.15, 0.3]  # identical: a quiet label never feels the gate


def test_grid_parity_quiet_batch_recover(monkeypatch):
    """batch_recover: damper active vs dormant on a quiet label - byte-identical bare schedule [0.15, 0.3]."""
    clock_active = _Clock(jitter=0.5)
    store_active, _d1, _c1, body_a = _make_store(monkeypatch, clock_active, label='batch_recover', aborts=2)
    assert store_active.run(body_a, operation='batch_recover') == 'committed'
    assert clock_active.sleeps == [0.15, 0.3]
    clock_dormant = _Clock(jitter=0.5)
    store_dormant, _d2, _c2, body_d = _make_store(
        monkeypatch,
        clock_dormant,
        label='batch_recover',
        aborts=2,
        dormant_env='BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED',
    )
    assert store_dormant.run(body_d, operation='batch_recover') == 'committed'
    assert clock_dormant.sleeps == [0.15, 0.3]  # identical: a quiet label never feels the gate


def test_grid_parity_quiet_batch_fail(monkeypatch):
    """batch_fail: damper active vs dormant on a quiet label - byte-identical bare schedule [0.15, 0.3]."""
    clock_active = _Clock(jitter=0.5)
    store_active, _d1, _c1, body_a = _make_store(monkeypatch, clock_active, label='batch_fail', aborts=2)
    assert store_active.run(body_a, operation='batch_fail') == 'committed'
    assert clock_active.sleeps == [0.15, 0.3]
    clock_dormant = _Clock(jitter=0.5)
    store_dormant, _d2, _c2, body_d = _make_store(
        monkeypatch,
        clock_dormant,
        label='batch_fail',
        aborts=2,
        dormant_env='BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED',
    )
    assert store_dormant.run(body_d, operation='batch_fail') == 'committed'
    assert clock_dormant.sleeps == [0.15, 0.3]  # identical: a quiet label never feels the gate


def test_grid_parity_quiet_batch_complete(monkeypatch):
    """batch_complete: damper active vs dormant on a quiet label - byte-identical bare schedule [0.15, 0.3]."""
    clock_active = _Clock(jitter=0.5)
    store_active, _d1, _c1, body_a = _make_store(monkeypatch, clock_active, label='batch_complete', aborts=2)
    assert store_active.run(body_a, operation='batch_complete') == 'committed'
    assert clock_active.sleeps == [0.15, 0.3]
    clock_dormant = _Clock(jitter=0.5)
    store_dormant, _d2, _c2, body_d = _make_store(
        monkeypatch,
        clock_dormant,
        label='batch_complete',
        aborts=2,
        dormant_env='BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED',
    )
    assert store_dormant.run(body_d, operation='batch_complete') == 'committed'
    assert clock_dormant.sleeps == [0.15, 0.3]  # identical: a quiet label never feels the gate


def test_grid_parity_quiet_batch_defer(monkeypatch):
    """batch_defer: damper active vs dormant on a quiet label - byte-identical bare schedule [0.15, 0.3]."""
    clock_active = _Clock(jitter=0.5)
    store_active, _d1, _c1, body_a = _make_store(monkeypatch, clock_active, label='batch_defer', aborts=2)
    assert store_active.run(body_a, operation='batch_defer') == 'committed'
    assert clock_active.sleeps == [0.15, 0.3]
    clock_dormant = _Clock(jitter=0.5)
    store_dormant, _d2, _c2, body_d = _make_store(
        monkeypatch,
        clock_dormant,
        label='batch_defer',
        aborts=2,
        dormant_env='BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED',
    )
    assert store_dormant.run(body_d, operation='batch_defer') == 'committed'
    assert clock_dormant.sleeps == [0.15, 0.3]  # identical: a quiet label never feels the gate


def test_grid_parity_quiet_batch_heartbeat(monkeypatch):
    """batch_heartbeat: damper active vs dormant on a quiet label - byte-identical bare schedule [0.15, 0.3]."""
    clock_active = _Clock(jitter=0.5)
    store_active, _d1, _c1, body_a = _make_store(monkeypatch, clock_active, label='batch_heartbeat', aborts=2)
    assert store_active.run(body_a, operation='batch_heartbeat') == 'committed'
    assert clock_active.sleeps == [0.15, 0.3]
    clock_dormant = _Clock(jitter=0.5)
    store_dormant, _d2, _c2, body_d = _make_store(
        monkeypatch,
        clock_dormant,
        label='batch_heartbeat',
        aborts=2,
        dormant_env='BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED',
    )
    assert store_dormant.run(body_d, operation='batch_heartbeat') == 'committed'
    assert clock_dormant.sleeps == [0.15, 0.3]  # identical: a quiet label never feels the gate


def test_grid_parity_quiet_batch_admit(monkeypatch):
    """batch_admit: damper active vs dormant on a quiet label - byte-identical bare schedule [0.15, 0.3]."""
    clock_active = _Clock(jitter=0.5)
    store_active, _d1, _c1, body_a = _make_store(monkeypatch, clock_active, label='batch_admit', aborts=2)
    assert store_active.run(body_a, operation='batch_admit') == 'committed'
    assert clock_active.sleeps == [0.15, 0.3]
    clock_dormant = _Clock(jitter=0.5)
    store_dormant, _d2, _c2, body_d = _make_store(
        monkeypatch,
        clock_dormant,
        label='batch_admit',
        aborts=2,
        dormant_env='BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED',
    )
    assert store_dormant.run(body_d, operation='batch_admit') == 'committed'
    assert clock_dormant.sleeps == [0.15, 0.3]  # identical: a quiet label never feels the gate


def test_grid_parity_quiet_batch_enqueue(monkeypatch):
    """batch_enqueue: damper active vs dormant on a quiet label - byte-identical bare schedule [0.15, 0.3]."""
    clock_active = _Clock(jitter=0.5)
    store_active, _d1, _c1, body_a = _make_store(monkeypatch, clock_active, label='batch_enqueue', aborts=2)
    assert store_active.run(body_a, operation='batch_enqueue') == 'committed'
    assert clock_active.sleeps == [0.15, 0.3]
    clock_dormant = _Clock(jitter=0.5)
    store_dormant, _d2, _c2, body_d = _make_store(
        monkeypatch,
        clock_dormant,
        label='batch_enqueue',
        aborts=2,
        dormant_env='BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED',
    )
    assert store_dormant.run(body_d, operation='batch_enqueue') == 'committed'
    assert clock_dormant.sleeps == [0.15, 0.3]  # identical: a quiet label never feels the gate


def test_grid_parity_quiet_batch_intake_status(monkeypatch):
    """batch_intake_status: damper active vs dormant on a quiet label - byte-identical bare schedule [0.15, 0.3]."""
    clock_active = _Clock(jitter=0.5)
    store_active, _d1, _c1, body_a = _make_store(monkeypatch, clock_active, label='batch_intake_status', aborts=2)
    assert store_active.run(body_a, operation='batch_intake_status') == 'committed'
    assert clock_active.sleeps == [0.15, 0.3]
    clock_dormant = _Clock(jitter=0.5)
    store_dormant, _d2, _c2, body_d = _make_store(
        monkeypatch,
        clock_dormant,
        label='batch_intake_status',
        aborts=2,
        dormant_env='BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED',
    )
    assert store_dormant.run(body_d, operation='batch_intake_status') == 'committed'
    assert clock_dormant.sleeps == [0.15, 0.3]  # identical: a quiet label never feels the gate


def test_grid_parity_quiet_batch_seal_register(monkeypatch):
    """batch_seal_register: damper active vs dormant on a quiet label - byte-identical bare schedule [0.15, 0.3]."""
    clock_active = _Clock(jitter=0.5)
    store_active, _d1, _c1, body_a = _make_store(monkeypatch, clock_active, label='batch_seal_register', aborts=2)
    assert store_active.run(body_a, operation='batch_seal_register') == 'committed'
    assert clock_active.sleeps == [0.15, 0.3]
    clock_dormant = _Clock(jitter=0.5)
    store_dormant, _d2, _c2, body_d = _make_store(
        monkeypatch,
        clock_dormant,
        label='batch_seal_register',
        aborts=2,
        dormant_env='BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED',
    )
    assert store_dormant.run(body_d, operation='batch_seal_register') == 'committed'
    assert clock_dormant.sleeps == [0.15, 0.3]  # identical: a quiet label never feels the gate


def test_grid_parity_quiet_batch_release(monkeypatch):
    """batch_release: damper active vs dormant on a quiet label - byte-identical bare schedule [0.15, 0.3]."""
    clock_active = _Clock(jitter=0.5)
    store_active, _d1, _c1, body_a = _make_store(monkeypatch, clock_active, label='batch_release', aborts=2)
    assert store_active.run(body_a, operation='batch_release') == 'committed'
    assert clock_active.sleeps == [0.15, 0.3]
    clock_dormant = _Clock(jitter=0.5)
    store_dormant, _d2, _c2, body_d = _make_store(
        monkeypatch,
        clock_dormant,
        label='batch_release',
        aborts=2,
        dormant_env='BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED',
    )
    assert store_dormant.run(body_d, operation='batch_release') == 'committed'
    assert clock_dormant.sleeps == [0.15, 0.3]  # identical: a quiet label never feels the gate


def test_grid_parity_quiet_batch_redrive(monkeypatch):
    """batch_redrive: damper active vs dormant on a quiet label - byte-identical bare schedule [0.15, 0.3]."""
    clock_active = _Clock(jitter=0.5)
    store_active, _d1, _c1, body_a = _make_store(monkeypatch, clock_active, label='batch_redrive', aborts=2)
    assert store_active.run(body_a, operation='batch_redrive') == 'committed'
    assert clock_active.sleeps == [0.15, 0.3]
    clock_dormant = _Clock(jitter=0.5)
    store_dormant, _d2, _c2, body_d = _make_store(
        monkeypatch,
        clock_dormant,
        label='batch_redrive',
        aborts=2,
        dormant_env='BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED',
    )
    assert store_dormant.run(body_d, operation='batch_redrive') == 'committed'
    assert clock_dormant.sleeps == [0.15, 0.3]  # identical: a quiet label never feels the gate


def test_grid_parity_quiet_batch_pull_shard_scheduler_00(monkeypatch):
    """batch_pull shard=scheduler_00: damper active vs dormant on a quiet label - byte-identical bare schedule [0.15, 0.3]."""
    clock_active = _Clock(jitter=0.5)
    store_active, _d1, _c1, body_a = _make_store(
        monkeypatch, clock_active, label='batch_pull shard=scheduler_00', aborts=2
    )
    assert store_active.run(body_a, operation='batch_pull shard=scheduler_00') == 'committed'
    assert clock_active.sleeps == [0.15, 0.3]
    clock_dormant = _Clock(jitter=0.5)
    store_dormant, _d2, _c2, body_d = _make_store(
        monkeypatch,
        clock_dormant,
        label='batch_pull shard=scheduler_00',
        aborts=2,
        dormant_env='BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED',
    )
    assert store_dormant.run(body_d, operation='batch_pull shard=scheduler_00') == 'committed'
    assert clock_dormant.sleeps == [0.15, 0.3]  # identical: a quiet label never feels the gate


def test_grid_cap_batch_provider_stt(monkeypatch):
    """batch_provider_stt: six stacked arms cap the window at 4.0s; the gate never waits beyond the damper cap."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=1)
    for _ in range(6):
        damper.arm('batch_provider_stt')  # walk the ladder to its cap
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [4.0, 0.2]  # entry consult waits the capped 4.0; rung 1 is spent, not gated again
    assert 4.0 <= CAP_SECONDS


def test_grid_cap_batch_merge_commit(monkeypatch):
    """batch_merge_commit: six stacked arms cap the window at 4.0s; the gate never waits beyond the damper cap."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=1)
    for _ in range(6):
        damper.arm('batch_merge_commit')  # walk the ladder to its cap
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [4.0, 0.2]  # entry consult waits the capped 4.0; rung 1 is spent, not gated again
    assert 4.0 <= CAP_SECONDS


def test_grid_cap_batch_recover(monkeypatch):
    """batch_recover: six stacked arms cap the window at 4.0s; the gate never waits beyond the damper cap."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=1)
    for _ in range(6):
        damper.arm('batch_recover')  # walk the ladder to its cap
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [4.0, 0.2]  # entry consult waits the capped 4.0; rung 1 is spent, not gated again
    assert 4.0 <= CAP_SECONDS


def test_grid_cap_batch_fail(monkeypatch):
    """batch_fail: six stacked arms cap the window at 4.0s; the gate never waits beyond the damper cap."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=1)
    for _ in range(6):
        damper.arm('batch_fail')  # walk the ladder to its cap
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [4.0, 0.2]  # entry consult waits the capped 4.0; rung 1 is spent, not gated again
    assert 4.0 <= CAP_SECONDS


def test_grid_cap_batch_complete(monkeypatch):
    """batch_complete: six stacked arms cap the window at 4.0s; the gate never waits beyond the damper cap."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=1)
    for _ in range(6):
        damper.arm('batch_complete')  # walk the ladder to its cap
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [4.0, 0.2]  # entry consult waits the capped 4.0; rung 1 is spent, not gated again
    assert 4.0 <= CAP_SECONDS


def test_grid_cap_batch_defer(monkeypatch):
    """batch_defer: six stacked arms cap the window at 4.0s; the gate never waits beyond the damper cap."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=1)
    for _ in range(6):
        damper.arm('batch_defer')  # walk the ladder to its cap
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [4.0, 0.2]  # entry consult waits the capped 4.0; rung 1 is spent, not gated again
    assert 4.0 <= CAP_SECONDS


def test_grid_cap_batch_heartbeat(monkeypatch):
    """batch_heartbeat: six stacked arms cap the window at 4.0s; the gate never waits beyond the damper cap."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_heartbeat', aborts=1)
    for _ in range(6):
        damper.arm('batch_heartbeat')  # walk the ladder to its cap
    assert store.run(body, operation='batch_heartbeat') == 'committed'
    assert clock.sleeps == [4.0, 0.2]  # entry consult waits the capped 4.0; rung 1 is spent, not gated again
    assert 4.0 <= CAP_SECONDS


def test_grid_cap_batch_admit(monkeypatch):
    """batch_admit: six stacked arms cap the window at 4.0s; the gate never waits beyond the damper cap."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=1)
    for _ in range(6):
        damper.arm('batch_admit')  # walk the ladder to its cap
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [4.0, 0.2]  # entry consult waits the capped 4.0; rung 1 is spent, not gated again
    assert 4.0 <= CAP_SECONDS


def test_grid_cap_batch_enqueue(monkeypatch):
    """batch_enqueue: six stacked arms cap the window at 4.0s; the gate never waits beyond the damper cap."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_enqueue', aborts=1)
    for _ in range(6):
        damper.arm('batch_enqueue')  # walk the ladder to its cap
    assert store.run(body, operation='batch_enqueue') == 'committed'
    assert clock.sleeps == [4.0, 0.2]  # entry consult waits the capped 4.0; rung 1 is spent, not gated again
    assert 4.0 <= CAP_SECONDS


def test_grid_cap_batch_intake_status(monkeypatch):
    """batch_intake_status: six stacked arms cap the window at 4.0s; the gate never waits beyond the damper cap."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=1)
    for _ in range(6):
        damper.arm('batch_intake_status')  # walk the ladder to its cap
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [4.0, 0.2]  # entry consult waits the capped 4.0; rung 1 is spent, not gated again
    assert 4.0 <= CAP_SECONDS


def test_grid_cap_batch_seal_register(monkeypatch):
    """batch_seal_register: six stacked arms cap the window at 4.0s; the gate never waits beyond the damper cap."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=1)
    for _ in range(6):
        damper.arm('batch_seal_register')  # walk the ladder to its cap
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [4.0, 0.2]  # entry consult waits the capped 4.0; rung 1 is spent, not gated again
    assert 4.0 <= CAP_SECONDS


def test_grid_cap_batch_release(monkeypatch):
    """batch_release: six stacked arms cap the window at 4.0s; the gate never waits beyond the damper cap."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=1)
    for _ in range(6):
        damper.arm('batch_release')  # walk the ladder to its cap
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [4.0, 0.2]  # entry consult waits the capped 4.0; rung 1 is spent, not gated again
    assert 4.0 <= CAP_SECONDS


def test_grid_cap_batch_redrive(monkeypatch):
    """batch_redrive: six stacked arms cap the window at 4.0s; the gate never waits beyond the damper cap."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=1)
    for _ in range(6):
        damper.arm('batch_redrive')  # walk the ladder to its cap
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [4.0, 0.2]  # entry consult waits the capped 4.0; rung 1 is spent, not gated again
    assert 4.0 <= CAP_SECONDS


def test_grid_cap_batch_pull_shard_scheduler_00(monkeypatch):
    """batch_pull shard=scheduler_00: six stacked arms cap the window at 4.0s; the gate never waits beyond the damper cap."""
    clock = _Clock(jitter=1.0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_pull shard=scheduler_00', aborts=1)
    for _ in range(6):
        damper.arm('batch_pull shard=scheduler_00')  # walk the ladder to its cap
    assert store.run(body, operation='batch_pull shard=scheduler_00') == 'committed'
    assert clock.sleeps == [4.0, 0.2]  # entry consult waits the capped 4.0; rung 1 is spent, not gated again
    assert 4.0 <= CAP_SECONDS


def test_grid_storm_then_recovery_batch_provider_stt_jitter_000(monkeypatch):
    """batch_provider_stt (jitter 0.0): after a storm, the next entry waits 0.125s at entry and rung 1 stays ungated."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=1)
    with pytest.raises(FirestoreContentionExhausted):
        store.run(_aborting, operation='batch_provider_stt')
    clock.sleeps.clear()
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.125, 0.1]  # the re-run waits out the storm window at entry, then rides bare rung 1


def test_grid_storm_then_recovery_batch_provider_stt_jitter_100(monkeypatch):
    """batch_provider_stt (jitter 1.0): after a storm, the next entry waits 0.25s at entry and rung 1 stays ungated."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=1)
    with pytest.raises(FirestoreContentionExhausted):
        store.run(_aborting, operation='batch_provider_stt')
    clock.sleeps.clear()
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.25, 0.2]  # the re-run waits out the storm window at entry, then rides bare rung 1


def test_grid_storm_then_recovery_batch_merge_commit_jitter_000(monkeypatch):
    """batch_merge_commit (jitter 0.0): after a storm, the next entry waits 0.125s at entry and rung 1 stays ungated."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=1)
    with pytest.raises(FirestoreContentionExhausted):
        store.run(_aborting, operation='batch_merge_commit')
    clock.sleeps.clear()
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.125, 0.1]  # the re-run waits out the storm window at entry, then rides bare rung 1


def test_grid_storm_then_recovery_batch_merge_commit_jitter_100(monkeypatch):
    """batch_merge_commit (jitter 1.0): after a storm, the next entry waits 0.25s at entry and rung 1 stays ungated."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=1)
    with pytest.raises(FirestoreContentionExhausted):
        store.run(_aborting, operation='batch_merge_commit')
    clock.sleeps.clear()
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.25, 0.2]  # the re-run waits out the storm window at entry, then rides bare rung 1


def test_grid_storm_then_recovery_batch_recover_jitter_000(monkeypatch):
    """batch_recover (jitter 0.0): after a storm, the next entry waits 0.125s at entry and rung 1 stays ungated."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=1)
    with pytest.raises(FirestoreContentionExhausted):
        store.run(_aborting, operation='batch_recover')
    clock.sleeps.clear()
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.125, 0.1]  # the re-run waits out the storm window at entry, then rides bare rung 1


def test_grid_storm_then_recovery_batch_recover_jitter_100(monkeypatch):
    """batch_recover (jitter 1.0): after a storm, the next entry waits 0.25s at entry and rung 1 stays ungated."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=1)
    with pytest.raises(FirestoreContentionExhausted):
        store.run(_aborting, operation='batch_recover')
    clock.sleeps.clear()
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.25, 0.2]  # the re-run waits out the storm window at entry, then rides bare rung 1


def test_grid_storm_then_recovery_batch_fail_jitter_000(monkeypatch):
    """batch_fail (jitter 0.0): after a storm, the next entry waits 0.125s at entry and rung 1 stays ungated."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=1)
    with pytest.raises(FirestoreContentionExhausted):
        store.run(_aborting, operation='batch_fail')
    clock.sleeps.clear()
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.125, 0.1]  # the re-run waits out the storm window at entry, then rides bare rung 1


def test_grid_storm_then_recovery_batch_fail_jitter_100(monkeypatch):
    """batch_fail (jitter 1.0): after a storm, the next entry waits 0.25s at entry and rung 1 stays ungated."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=1)
    with pytest.raises(FirestoreContentionExhausted):
        store.run(_aborting, operation='batch_fail')
    clock.sleeps.clear()
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.25, 0.2]  # the re-run waits out the storm window at entry, then rides bare rung 1


def test_grid_storm_then_recovery_batch_complete_jitter_000(monkeypatch):
    """batch_complete (jitter 0.0): after a storm, the next entry waits 0.125s at entry and rung 1 stays ungated."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=1)
    with pytest.raises(FirestoreContentionExhausted):
        store.run(_aborting, operation='batch_complete')
    clock.sleeps.clear()
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.125, 0.1]  # the re-run waits out the storm window at entry, then rides bare rung 1


def test_grid_storm_then_recovery_batch_complete_jitter_100(monkeypatch):
    """batch_complete (jitter 1.0): after a storm, the next entry waits 0.25s at entry and rung 1 stays ungated."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=1)
    with pytest.raises(FirestoreContentionExhausted):
        store.run(_aborting, operation='batch_complete')
    clock.sleeps.clear()
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.25, 0.2]  # the re-run waits out the storm window at entry, then rides bare rung 1


def test_grid_storm_then_recovery_batch_defer_jitter_000(monkeypatch):
    """batch_defer (jitter 0.0): after a storm, the next entry waits 0.125s at entry and rung 1 stays ungated."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=1)
    with pytest.raises(FirestoreContentionExhausted):
        store.run(_aborting, operation='batch_defer')
    clock.sleeps.clear()
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.125, 0.1]  # the re-run waits out the storm window at entry, then rides bare rung 1


def test_grid_storm_then_recovery_batch_defer_jitter_100(monkeypatch):
    """batch_defer (jitter 1.0): after a storm, the next entry waits 0.25s at entry and rung 1 stays ungated."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=1)
    with pytest.raises(FirestoreContentionExhausted):
        store.run(_aborting, operation='batch_defer')
    clock.sleeps.clear()
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.25, 0.2]  # the re-run waits out the storm window at entry, then rides bare rung 1


def test_grid_storm_then_recovery_batch_heartbeat_jitter_000(monkeypatch):
    """batch_heartbeat (jitter 0.0): after a storm, the next entry waits 0.125s at entry and rung 1 stays ungated."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_heartbeat', aborts=1)
    with pytest.raises(FirestoreContentionExhausted):
        store.run(_aborting, operation='batch_heartbeat')
    clock.sleeps.clear()
    assert store.run(body, operation='batch_heartbeat') == 'committed'
    assert clock.sleeps == [0.125, 0.1]  # the re-run waits out the storm window at entry, then rides bare rung 1


def test_grid_storm_then_recovery_batch_heartbeat_jitter_100(monkeypatch):
    """batch_heartbeat (jitter 1.0): after a storm, the next entry waits 0.25s at entry and rung 1 stays ungated."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_heartbeat', aborts=1)
    with pytest.raises(FirestoreContentionExhausted):
        store.run(_aborting, operation='batch_heartbeat')
    clock.sleeps.clear()
    assert store.run(body, operation='batch_heartbeat') == 'committed'
    assert clock.sleeps == [0.25, 0.2]  # the re-run waits out the storm window at entry, then rides bare rung 1


def test_grid_storm_then_recovery_batch_admit_jitter_000(monkeypatch):
    """batch_admit (jitter 0.0): after a storm, the next entry waits 0.125s at entry and rung 1 stays ungated."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=1)
    with pytest.raises(FirestoreContentionExhausted):
        store.run(_aborting, operation='batch_admit')
    clock.sleeps.clear()
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.125, 0.1]  # the re-run waits out the storm window at entry, then rides bare rung 1


def test_grid_storm_then_recovery_batch_admit_jitter_100(monkeypatch):
    """batch_admit (jitter 1.0): after a storm, the next entry waits 0.25s at entry and rung 1 stays ungated."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=1)
    with pytest.raises(FirestoreContentionExhausted):
        store.run(_aborting, operation='batch_admit')
    clock.sleeps.clear()
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.25, 0.2]  # the re-run waits out the storm window at entry, then rides bare rung 1


def test_grid_storm_then_recovery_batch_enqueue_jitter_000(monkeypatch):
    """batch_enqueue (jitter 0.0): after a storm, the next entry waits 0.125s at entry and rung 1 stays ungated."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_enqueue', aborts=1)
    with pytest.raises(FirestoreContentionExhausted):
        store.run(_aborting, operation='batch_enqueue')
    clock.sleeps.clear()
    assert store.run(body, operation='batch_enqueue') == 'committed'
    assert clock.sleeps == [0.125, 0.1]  # the re-run waits out the storm window at entry, then rides bare rung 1


def test_grid_storm_then_recovery_batch_enqueue_jitter_100(monkeypatch):
    """batch_enqueue (jitter 1.0): after a storm, the next entry waits 0.25s at entry and rung 1 stays ungated."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_enqueue', aborts=1)
    with pytest.raises(FirestoreContentionExhausted):
        store.run(_aborting, operation='batch_enqueue')
    clock.sleeps.clear()
    assert store.run(body, operation='batch_enqueue') == 'committed'
    assert clock.sleeps == [0.25, 0.2]  # the re-run waits out the storm window at entry, then rides bare rung 1


def test_grid_storm_then_recovery_batch_intake_status_jitter_000(monkeypatch):
    """batch_intake_status (jitter 0.0): after a storm, the next entry waits 0.125s at entry and rung 1 stays ungated."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=1)
    with pytest.raises(FirestoreContentionExhausted):
        store.run(_aborting, operation='batch_intake_status')
    clock.sleeps.clear()
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.125, 0.1]  # the re-run waits out the storm window at entry, then rides bare rung 1


def test_grid_storm_then_recovery_batch_intake_status_jitter_100(monkeypatch):
    """batch_intake_status (jitter 1.0): after a storm, the next entry waits 0.25s at entry and rung 1 stays ungated."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=1)
    with pytest.raises(FirestoreContentionExhausted):
        store.run(_aborting, operation='batch_intake_status')
    clock.sleeps.clear()
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.25, 0.2]  # the re-run waits out the storm window at entry, then rides bare rung 1


def test_grid_storm_then_recovery_batch_seal_register_jitter_000(monkeypatch):
    """batch_seal_register (jitter 0.0): after a storm, the next entry waits 0.125s at entry and rung 1 stays ungated."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=1)
    with pytest.raises(FirestoreContentionExhausted):
        store.run(_aborting, operation='batch_seal_register')
    clock.sleeps.clear()
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.125, 0.1]  # the re-run waits out the storm window at entry, then rides bare rung 1


def test_grid_storm_then_recovery_batch_seal_register_jitter_100(monkeypatch):
    """batch_seal_register (jitter 1.0): after a storm, the next entry waits 0.25s at entry and rung 1 stays ungated."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=1)
    with pytest.raises(FirestoreContentionExhausted):
        store.run(_aborting, operation='batch_seal_register')
    clock.sleeps.clear()
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.25, 0.2]  # the re-run waits out the storm window at entry, then rides bare rung 1


def test_grid_storm_then_recovery_batch_release_jitter_000(monkeypatch):
    """batch_release (jitter 0.0): after a storm, the next entry waits 0.125s at entry and rung 1 stays ungated."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=1)
    with pytest.raises(FirestoreContentionExhausted):
        store.run(_aborting, operation='batch_release')
    clock.sleeps.clear()
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.125, 0.1]  # the re-run waits out the storm window at entry, then rides bare rung 1


def test_grid_storm_then_recovery_batch_release_jitter_100(monkeypatch):
    """batch_release (jitter 1.0): after a storm, the next entry waits 0.25s at entry and rung 1 stays ungated."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=1)
    with pytest.raises(FirestoreContentionExhausted):
        store.run(_aborting, operation='batch_release')
    clock.sleeps.clear()
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.25, 0.2]  # the re-run waits out the storm window at entry, then rides bare rung 1


def test_grid_storm_then_recovery_batch_redrive_jitter_000(monkeypatch):
    """batch_redrive (jitter 0.0): after a storm, the next entry waits 0.125s at entry and rung 1 stays ungated."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=1)
    with pytest.raises(FirestoreContentionExhausted):
        store.run(_aborting, operation='batch_redrive')
    clock.sleeps.clear()
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.125, 0.1]  # the re-run waits out the storm window at entry, then rides bare rung 1


def test_grid_storm_then_recovery_batch_redrive_jitter_100(monkeypatch):
    """batch_redrive (jitter 1.0): after a storm, the next entry waits 0.25s at entry and rung 1 stays ungated."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=1)
    with pytest.raises(FirestoreContentionExhausted):
        store.run(_aborting, operation='batch_redrive')
    clock.sleeps.clear()
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.25, 0.2]  # the re-run waits out the storm window at entry, then rides bare rung 1


def test_grid_storm_then_recovery_batch_pull_shard_scheduler_00_jitter_000(monkeypatch):
    """batch_pull shard=scheduler_00 (jitter 0.0): after a storm, the next entry waits 0.125s at entry and rung 1 stays ungated."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_pull shard=scheduler_00', aborts=1)
    with pytest.raises(FirestoreContentionExhausted):
        store.run(_aborting, operation='batch_pull shard=scheduler_00')
    clock.sleeps.clear()
    assert store.run(body, operation='batch_pull shard=scheduler_00') == 'committed'
    assert clock.sleeps == [0.125, 0.1]  # the re-run waits out the storm window at entry, then rides bare rung 1


def test_grid_storm_then_recovery_batch_pull_shard_scheduler_00_jitter_100(monkeypatch):
    """batch_pull shard=scheduler_00 (jitter 1.0): after a storm, the next entry waits 0.25s at entry and rung 1 stays ungated."""
    clock = _Clock(jitter=1.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_pull shard=scheduler_00', aborts=1)
    with pytest.raises(FirestoreContentionExhausted):
        store.run(_aborting, operation='batch_pull shard=scheduler_00')
    clock.sleeps.clear()
    assert store.run(body, operation='batch_pull shard=scheduler_00') == 'committed'
    assert clock.sleeps == [0.25, 0.2]  # the re-run waits out the storm window at entry, then rides bare rung 1


def test_grid_quiet_no_log_batch_provider_stt(monkeypatch, caplog):
    """batch_provider_stt: a quiet chain never emits the mid_ladder line."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=2)
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert not [record for record in caplog.records if 'scope=mid_ladder' in record.getMessage()]


def test_grid_quiet_no_log_batch_merge_commit(monkeypatch, caplog):
    """batch_merge_commit: a quiet chain never emits the mid_ladder line."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=2)
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert not [record for record in caplog.records if 'scope=mid_ladder' in record.getMessage()]


def test_grid_quiet_no_log_batch_recover(monkeypatch, caplog):
    """batch_recover: a quiet chain never emits the mid_ladder line."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=2)
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        assert store.run(body, operation='batch_recover') == 'committed'
    assert not [record for record in caplog.records if 'scope=mid_ladder' in record.getMessage()]


def test_grid_quiet_no_log_batch_fail(monkeypatch, caplog):
    """batch_fail: a quiet chain never emits the mid_ladder line."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=2)
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        assert store.run(body, operation='batch_fail') == 'committed'
    assert not [record for record in caplog.records if 'scope=mid_ladder' in record.getMessage()]


def test_grid_quiet_no_log_batch_complete(monkeypatch, caplog):
    """batch_complete: a quiet chain never emits the mid_ladder line."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=2)
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        assert store.run(body, operation='batch_complete') == 'committed'
    assert not [record for record in caplog.records if 'scope=mid_ladder' in record.getMessage()]


def test_grid_quiet_no_log_batch_defer(monkeypatch, caplog):
    """batch_defer: a quiet chain never emits the mid_ladder line."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=2)
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        assert store.run(body, operation='batch_defer') == 'committed'
    assert not [record for record in caplog.records if 'scope=mid_ladder' in record.getMessage()]


def test_grid_quiet_no_log_batch_heartbeat(monkeypatch, caplog):
    """batch_heartbeat: a quiet chain never emits the mid_ladder line."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_heartbeat', aborts=2)
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        assert store.run(body, operation='batch_heartbeat') == 'committed'
    assert not [record for record in caplog.records if 'scope=mid_ladder' in record.getMessage()]


def test_grid_quiet_no_log_batch_admit(monkeypatch, caplog):
    """batch_admit: a quiet chain never emits the mid_ladder line."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=2)
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        assert store.run(body, operation='batch_admit') == 'committed'
    assert not [record for record in caplog.records if 'scope=mid_ladder' in record.getMessage()]


def test_grid_quiet_no_log_batch_enqueue(monkeypatch, caplog):
    """batch_enqueue: a quiet chain never emits the mid_ladder line."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_enqueue', aborts=2)
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        assert store.run(body, operation='batch_enqueue') == 'committed'
    assert not [record for record in caplog.records if 'scope=mid_ladder' in record.getMessage()]


def test_grid_quiet_no_log_batch_intake_status(monkeypatch, caplog):
    """batch_intake_status: a quiet chain never emits the mid_ladder line."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=2)
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        assert store.run(body, operation='batch_intake_status') == 'committed'
    assert not [record for record in caplog.records if 'scope=mid_ladder' in record.getMessage()]


def test_grid_quiet_no_log_batch_seal_register(monkeypatch, caplog):
    """batch_seal_register: a quiet chain never emits the mid_ladder line."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=2)
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        assert store.run(body, operation='batch_seal_register') == 'committed'
    assert not [record for record in caplog.records if 'scope=mid_ladder' in record.getMessage()]


def test_grid_quiet_no_log_batch_release(monkeypatch, caplog):
    """batch_release: a quiet chain never emits the mid_ladder line."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=2)
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        assert store.run(body, operation='batch_release') == 'committed'
    assert not [record for record in caplog.records if 'scope=mid_ladder' in record.getMessage()]


def test_grid_quiet_no_log_batch_redrive(monkeypatch, caplog):
    """batch_redrive: a quiet chain never emits the mid_ladder line."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=2)
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        assert store.run(body, operation='batch_redrive') == 'committed'
    assert not [record for record in caplog.records if 'scope=mid_ladder' in record.getMessage()]


def test_grid_quiet_no_log_batch_pull_shard_scheduler_00(monkeypatch, caplog):
    """batch_pull shard=scheduler_00: a quiet chain never emits the mid_ladder line."""
    clock = _Clock(jitter=0.0)
    store, _damper, _client, body = _make_store(monkeypatch, clock, label='batch_pull shard=scheduler_00', aborts=2)
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        assert store.run(body, operation='batch_pull shard=scheduler_00') == 'committed'
    assert not [record for record in caplog.records if 'scope=mid_ladder' in record.getMessage()]
