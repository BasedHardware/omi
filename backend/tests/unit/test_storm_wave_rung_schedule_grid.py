"""Wave-rung schedule grid

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


def test_grid_wave_recover3_merge_commit_jitter_00(monkeypatch):
    """batch_merge_commit (jitter 0.0): recover on attempt 4 — sleeps [0.1, 0.2, 0.9]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=3)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_merge_commit_jitter_00(monkeypatch):
    """batch_merge_commit (jitter 0.0): recover on attempt 5 — sleeps [0.1, 0.2, 0.9, 1.8]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_merge_commit_jitter_00(monkeypatch):
    """batch_merge_commit (jitter 0.0): exhaustion walk — sleeps [0.1, 0.2, 0.9, 1.8], retry-after 0.125s."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_merge_commit', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_merge_commit')
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]
    assert caught.value.retry_after == pytest.approx(0.125)


def test_grid_wave_sibling2_merge_commit_jitter_00(monkeypatch):
    """batch_merge_commit (jitter 0.0): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.1, 0.325, 0.9, 1.8]


def test_grid_wave_sibling3_merge_commit_jitter_00(monkeypatch):
    """batch_merge_commit (jitter 0.0): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]


def test_grid_wave_doublearm_merge_commit_jitter_00(monkeypatch):
    """batch_merge_commit (jitter 0.0): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.1, 0.325, 0.9, 1.8]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_merge_commit')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_merge_commit_jitter_01(monkeypatch):
    """batch_merge_commit (jitter 0.1): recover on attempt 4 — sleeps [0.11, 0.22, 0.99]."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=3)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.11, 0.22, 0.99]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_merge_commit_jitter_01(monkeypatch):
    """batch_merge_commit (jitter 0.1): recover on attempt 5 — sleeps [0.11, 0.22, 0.99, 1.98]."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.11, 0.22, 0.99, 1.98]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_merge_commit_jitter_01(monkeypatch):
    """batch_merge_commit (jitter 0.1): exhaustion walk — sleeps [0.11, 0.22, 0.99, 1.98], retry-after 0.1375s."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_merge_commit', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_merge_commit')
    assert clock.sleeps == [0.11, 0.22, 0.99, 1.98]
    assert caught.value.retry_after == pytest.approx(0.1375)


def test_grid_wave_sibling2_merge_commit_jitter_01(monkeypatch):
    """batch_merge_commit (jitter 0.1): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.11, 0.3575, 0.99, 1.98]


def test_grid_wave_sibling3_merge_commit_jitter_01(monkeypatch):
    """batch_merge_commit (jitter 0.1): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.11, 0.22, 0.99, 1.98]


def test_grid_wave_doublearm_merge_commit_jitter_01(monkeypatch):
    """batch_merge_commit (jitter 0.1): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.11, 0.3575, 0.99, 1.98]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_merge_commit')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_merge_commit_jitter_02(monkeypatch):
    """batch_merge_commit (jitter 0.2): recover on attempt 4 — sleeps [0.12, 0.24, 1.08]."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=3)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.12, 0.24, 1.08]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_merge_commit_jitter_02(monkeypatch):
    """batch_merge_commit (jitter 0.2): recover on attempt 5 — sleeps [0.12, 0.24, 1.08, 2.16]."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.12, 0.24, 1.08, 2.16]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_merge_commit_jitter_02(monkeypatch):
    """batch_merge_commit (jitter 0.2): exhaustion walk — sleeps [0.12, 0.24, 1.08, 2.16], retry-after 0.15s."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_merge_commit', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_merge_commit')
    assert clock.sleeps == [0.12, 0.24, 1.08, 2.16]
    assert caught.value.retry_after == pytest.approx(0.15)


def test_grid_wave_sibling2_merge_commit_jitter_02(monkeypatch):
    """batch_merge_commit (jitter 0.2): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.12, 0.39, 1.08, 2.16]


def test_grid_wave_sibling3_merge_commit_jitter_02(monkeypatch):
    """batch_merge_commit (jitter 0.2): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.12, 0.24, 1.08, 2.16]


def test_grid_wave_doublearm_merge_commit_jitter_02(monkeypatch):
    """batch_merge_commit (jitter 0.2): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.12, 0.39, 1.08, 2.16]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_merge_commit')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_merge_commit_jitter_03(monkeypatch):
    """batch_merge_commit (jitter 0.3): recover on attempt 4 — sleeps [0.13, 0.26, 1.17]."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=3)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.13, 0.26, 1.17]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_merge_commit_jitter_03(monkeypatch):
    """batch_merge_commit (jitter 0.3): recover on attempt 5 — sleeps [0.13, 0.26, 1.17, 2.34]."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.13, 0.26, 1.17, 2.34]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_merge_commit_jitter_03(monkeypatch):
    """batch_merge_commit (jitter 0.3): exhaustion walk — sleeps [0.13, 0.26, 1.17, 2.34], retry-after 0.1625s."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_merge_commit', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_merge_commit')
    assert clock.sleeps == [0.13, 0.26, 1.17, 2.34]
    assert caught.value.retry_after == pytest.approx(0.1625)


def test_grid_wave_sibling2_merge_commit_jitter_03(monkeypatch):
    """batch_merge_commit (jitter 0.3): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.13, 0.4225, 1.17, 2.34]


def test_grid_wave_sibling3_merge_commit_jitter_03(monkeypatch):
    """batch_merge_commit (jitter 0.3): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.13, 0.26, 1.17, 2.34]


def test_grid_wave_doublearm_merge_commit_jitter_03(monkeypatch):
    """batch_merge_commit (jitter 0.3): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.13, 0.4225, 1.17, 2.34]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_merge_commit')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_merge_commit_jitter_04(monkeypatch):
    """batch_merge_commit (jitter 0.4): recover on attempt 4 — sleeps [0.14, 0.28, 1.26]."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=3)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.14, 0.28, 1.26]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_merge_commit_jitter_04(monkeypatch):
    """batch_merge_commit (jitter 0.4): recover on attempt 5 — sleeps [0.14, 0.28, 1.26, 2.52]."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.14, 0.28, 1.26, 2.52]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_merge_commit_jitter_04(monkeypatch):
    """batch_merge_commit (jitter 0.4): exhaustion walk — sleeps [0.14, 0.28, 1.26, 2.52], retry-after 0.175s."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_merge_commit', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_merge_commit')
    assert clock.sleeps == [0.14, 0.28, 1.26, 2.52]
    assert caught.value.retry_after == pytest.approx(0.175)


def test_grid_wave_sibling2_merge_commit_jitter_04(monkeypatch):
    """batch_merge_commit (jitter 0.4): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.14, 0.455, 1.26, 2.52]


def test_grid_wave_sibling3_merge_commit_jitter_04(monkeypatch):
    """batch_merge_commit (jitter 0.4): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.14, 0.28, 1.26, 2.52]


def test_grid_wave_doublearm_merge_commit_jitter_04(monkeypatch):
    """batch_merge_commit (jitter 0.4): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.14, 0.455, 1.26, 2.52]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_merge_commit')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_merge_commit_jitter_05(monkeypatch):
    """batch_merge_commit (jitter 0.5): recover on attempt 4 — sleeps [0.15, 0.3, 1.35]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=3)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_merge_commit_jitter_05(monkeypatch):
    """batch_merge_commit (jitter 0.5): recover on attempt 5 — sleeps [0.15, 0.3, 1.35, 2.7]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_merge_commit_jitter_05(monkeypatch):
    """batch_merge_commit (jitter 0.5): exhaustion walk — sleeps [0.15, 0.3, 1.35, 2.7], retry-after 0.1875s."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_merge_commit', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_merge_commit')
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]
    assert caught.value.retry_after == pytest.approx(0.1875)


def test_grid_wave_sibling2_merge_commit_jitter_05(monkeypatch):
    """batch_merge_commit (jitter 0.5): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.15, 0.4875, 1.35, 2.7]


def test_grid_wave_sibling3_merge_commit_jitter_05(monkeypatch):
    """batch_merge_commit (jitter 0.5): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]


def test_grid_wave_doublearm_merge_commit_jitter_05(monkeypatch):
    """batch_merge_commit (jitter 0.5): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.15, 0.4875, 1.35, 2.7]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_merge_commit')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_merge_commit_jitter_06(monkeypatch):
    """batch_merge_commit (jitter 0.6): recover on attempt 4 — sleeps [0.16, 0.32, 1.44]."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=3)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.16, 0.32, 1.44]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_merge_commit_jitter_06(monkeypatch):
    """batch_merge_commit (jitter 0.6): recover on attempt 5 — sleeps [0.16, 0.32, 1.44, 2.88]."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.16, 0.32, 1.44, 2.88]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_merge_commit_jitter_06(monkeypatch):
    """batch_merge_commit (jitter 0.6): exhaustion walk — sleeps [0.16, 0.32, 1.44, 2.88], retry-after 0.2s."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_merge_commit', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_merge_commit')
    assert clock.sleeps == [0.16, 0.32, 1.44, 2.88]
    assert caught.value.retry_after == pytest.approx(0.2)


def test_grid_wave_sibling2_merge_commit_jitter_06(monkeypatch):
    """batch_merge_commit (jitter 0.6): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.16, 0.52, 1.44, 2.88]


def test_grid_wave_sibling3_merge_commit_jitter_06(monkeypatch):
    """batch_merge_commit (jitter 0.6): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.16, 0.32, 1.44, 2.88]


def test_grid_wave_doublearm_merge_commit_jitter_06(monkeypatch):
    """batch_merge_commit (jitter 0.6): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.16, 0.52, 1.44, 2.88]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_merge_commit')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_merge_commit_jitter_07(monkeypatch):
    """batch_merge_commit (jitter 0.7): recover on attempt 4 — sleeps [0.17, 0.34, 1.53]."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=3)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.17, 0.34, 1.53]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_merge_commit_jitter_07(monkeypatch):
    """batch_merge_commit (jitter 0.7): recover on attempt 5 — sleeps [0.17, 0.34, 1.53, 3.06]."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.17, 0.34, 1.53, 3.06]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_merge_commit_jitter_07(monkeypatch):
    """batch_merge_commit (jitter 0.7): exhaustion walk — sleeps [0.17, 0.34, 1.53, 3.06], retry-after 0.2125s."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_merge_commit', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_merge_commit')
    assert clock.sleeps == [0.17, 0.34, 1.53, 3.06]
    assert caught.value.retry_after == pytest.approx(0.2125)


def test_grid_wave_sibling2_merge_commit_jitter_07(monkeypatch):
    """batch_merge_commit (jitter 0.7): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.17, 0.5525, 1.53, 3.06]


def test_grid_wave_sibling3_merge_commit_jitter_07(monkeypatch):
    """batch_merge_commit (jitter 0.7): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.17, 0.34, 1.53, 3.06]


def test_grid_wave_doublearm_merge_commit_jitter_07(monkeypatch):
    """batch_merge_commit (jitter 0.7): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.17, 0.5525, 1.53, 3.06]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_merge_commit')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_merge_commit_jitter_08(monkeypatch):
    """batch_merge_commit (jitter 0.8): recover on attempt 4 — sleeps [0.18, 0.36, 1.62]."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=3)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.18, 0.36, 1.62]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_merge_commit_jitter_08(monkeypatch):
    """batch_merge_commit (jitter 0.8): recover on attempt 5 — sleeps [0.18, 0.36, 1.62, 3.24]."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.18, 0.36, 1.62, 3.24]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_merge_commit_jitter_08(monkeypatch):
    """batch_merge_commit (jitter 0.8): exhaustion walk — sleeps [0.18, 0.36, 1.62, 3.24], retry-after 0.225s."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_merge_commit', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_merge_commit')
    assert clock.sleeps == [0.18, 0.36, 1.62, 3.24]
    assert caught.value.retry_after == pytest.approx(0.225)


def test_grid_wave_sibling2_merge_commit_jitter_08(monkeypatch):
    """batch_merge_commit (jitter 0.8): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.18, 0.585, 1.62, 3.24]


def test_grid_wave_sibling3_merge_commit_jitter_08(monkeypatch):
    """batch_merge_commit (jitter 0.8): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.18, 0.36, 1.62, 3.24]


def test_grid_wave_doublearm_merge_commit_jitter_08(monkeypatch):
    """batch_merge_commit (jitter 0.8): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.18, 0.585, 1.62, 3.24]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_merge_commit')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_merge_commit_jitter_09(monkeypatch):
    """batch_merge_commit (jitter 0.9): recover on attempt 4 — sleeps [0.19, 0.38, 1.71]."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=3)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.19, 0.38, 1.71]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_merge_commit_jitter_09(monkeypatch):
    """batch_merge_commit (jitter 0.9): recover on attempt 5 — sleeps [0.19, 0.38, 1.71, 3.42]."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.19, 0.38, 1.71, 3.42]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_merge_commit_jitter_09(monkeypatch):
    """batch_merge_commit (jitter 0.9): exhaustion walk — sleeps [0.19, 0.38, 1.71, 3.42], retry-after 0.2375s."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_merge_commit', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_merge_commit')
    assert clock.sleeps == [0.19, 0.38, 1.71, 3.42]
    assert caught.value.retry_after == pytest.approx(0.2375)


def test_grid_wave_sibling2_merge_commit_jitter_09(monkeypatch):
    """batch_merge_commit (jitter 0.9): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.19, 0.6175, 1.71, 3.42]


def test_grid_wave_sibling3_merge_commit_jitter_09(monkeypatch):
    """batch_merge_commit (jitter 0.9): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.19, 0.38, 1.71, 3.42]


def test_grid_wave_doublearm_merge_commit_jitter_09(monkeypatch):
    """batch_merge_commit (jitter 0.9): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.19, 0.6175, 1.71, 3.42]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_merge_commit')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_merge_commit_jitter_10(monkeypatch):
    """batch_merge_commit (jitter 1.0): recover on attempt 4 — sleeps [0.2, 0.4, 1.8]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=3)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_merge_commit_jitter_10(monkeypatch):
    """batch_merge_commit (jitter 1.0): recover on attempt 5 — sleeps [0.2, 0.4, 1.8, 3.6]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_merge_commit_jitter_10(monkeypatch):
    """batch_merge_commit (jitter 1.0): exhaustion walk — sleeps [0.2, 0.4, 1.8, 3.6], retry-after 0.25s."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_merge_commit', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_merge_commit')
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]
    assert caught.value.retry_after == pytest.approx(0.25)


def test_grid_wave_sibling2_merge_commit_jitter_10(monkeypatch):
    """batch_merge_commit (jitter 1.0): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.2, 0.65, 1.8, 3.6]


def test_grid_wave_sibling3_merge_commit_jitter_10(monkeypatch):
    """batch_merge_commit (jitter 1.0): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]


def test_grid_wave_doublearm_merge_commit_jitter_10(monkeypatch):
    """batch_merge_commit (jitter 1.0): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_merge_commit', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [0.2, 0.65, 1.8, 3.6]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_merge_commit')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_admit_jitter_00(monkeypatch):
    """batch_admit (jitter 0.0): recover on attempt 4 — sleeps [0.1, 0.2, 0.9]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=3)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_admit_jitter_00(monkeypatch):
    """batch_admit (jitter 0.0): recover on attempt 5 — sleeps [0.1, 0.2, 0.9, 1.8]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_admit_jitter_00(monkeypatch):
    """batch_admit (jitter 0.0): exhaustion walk — sleeps [0.1, 0.2, 0.9, 1.8], retry-after 0.125s."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_admit')
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]
    assert caught.value.retry_after == pytest.approx(0.125)


def test_grid_wave_sibling2_admit_jitter_00(monkeypatch):
    """batch_admit (jitter 0.0): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.1, 0.325, 0.9, 1.8]


def test_grid_wave_sibling3_admit_jitter_00(monkeypatch):
    """batch_admit (jitter 0.0): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]


def test_grid_wave_doublearm_admit_jitter_00(monkeypatch):
    """batch_admit (jitter 0.0): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.1, 0.325, 0.9, 1.8]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_admit')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_admit_jitter_01(monkeypatch):
    """batch_admit (jitter 0.1): recover on attempt 4 — sleeps [0.11, 0.22, 0.99]."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=3)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.11, 0.22, 0.99]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_admit_jitter_01(monkeypatch):
    """batch_admit (jitter 0.1): recover on attempt 5 — sleeps [0.11, 0.22, 0.99, 1.98]."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.11, 0.22, 0.99, 1.98]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_admit_jitter_01(monkeypatch):
    """batch_admit (jitter 0.1): exhaustion walk — sleeps [0.11, 0.22, 0.99, 1.98], retry-after 0.1375s."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_admit')
    assert clock.sleeps == [0.11, 0.22, 0.99, 1.98]
    assert caught.value.retry_after == pytest.approx(0.1375)


def test_grid_wave_sibling2_admit_jitter_01(monkeypatch):
    """batch_admit (jitter 0.1): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.11, 0.3575, 0.99, 1.98]


def test_grid_wave_sibling3_admit_jitter_01(monkeypatch):
    """batch_admit (jitter 0.1): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.11, 0.22, 0.99, 1.98]


def test_grid_wave_doublearm_admit_jitter_01(monkeypatch):
    """batch_admit (jitter 0.1): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.11, 0.3575, 0.99, 1.98]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_admit')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_admit_jitter_02(monkeypatch):
    """batch_admit (jitter 0.2): recover on attempt 4 — sleeps [0.12, 0.24, 1.08]."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=3)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.12, 0.24, 1.08]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_admit_jitter_02(monkeypatch):
    """batch_admit (jitter 0.2): recover on attempt 5 — sleeps [0.12, 0.24, 1.08, 2.16]."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.12, 0.24, 1.08, 2.16]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_admit_jitter_02(monkeypatch):
    """batch_admit (jitter 0.2): exhaustion walk — sleeps [0.12, 0.24, 1.08, 2.16], retry-after 0.15s."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_admit')
    assert clock.sleeps == [0.12, 0.24, 1.08, 2.16]
    assert caught.value.retry_after == pytest.approx(0.15)


def test_grid_wave_sibling2_admit_jitter_02(monkeypatch):
    """batch_admit (jitter 0.2): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.12, 0.39, 1.08, 2.16]


def test_grid_wave_sibling3_admit_jitter_02(monkeypatch):
    """batch_admit (jitter 0.2): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.12, 0.24, 1.08, 2.16]


def test_grid_wave_doublearm_admit_jitter_02(monkeypatch):
    """batch_admit (jitter 0.2): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.12, 0.39, 1.08, 2.16]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_admit')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_admit_jitter_03(monkeypatch):
    """batch_admit (jitter 0.3): recover on attempt 4 — sleeps [0.13, 0.26, 1.17]."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=3)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.13, 0.26, 1.17]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_admit_jitter_03(monkeypatch):
    """batch_admit (jitter 0.3): recover on attempt 5 — sleeps [0.13, 0.26, 1.17, 2.34]."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.13, 0.26, 1.17, 2.34]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_admit_jitter_03(monkeypatch):
    """batch_admit (jitter 0.3): exhaustion walk — sleeps [0.13, 0.26, 1.17, 2.34], retry-after 0.1625s."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_admit')
    assert clock.sleeps == [0.13, 0.26, 1.17, 2.34]
    assert caught.value.retry_after == pytest.approx(0.1625)


def test_grid_wave_sibling2_admit_jitter_03(monkeypatch):
    """batch_admit (jitter 0.3): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.13, 0.4225, 1.17, 2.34]


def test_grid_wave_sibling3_admit_jitter_03(monkeypatch):
    """batch_admit (jitter 0.3): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.13, 0.26, 1.17, 2.34]


def test_grid_wave_doublearm_admit_jitter_03(monkeypatch):
    """batch_admit (jitter 0.3): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.13, 0.4225, 1.17, 2.34]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_admit')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_admit_jitter_04(monkeypatch):
    """batch_admit (jitter 0.4): recover on attempt 4 — sleeps [0.14, 0.28, 1.26]."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=3)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.14, 0.28, 1.26]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_admit_jitter_04(monkeypatch):
    """batch_admit (jitter 0.4): recover on attempt 5 — sleeps [0.14, 0.28, 1.26, 2.52]."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.14, 0.28, 1.26, 2.52]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_admit_jitter_04(monkeypatch):
    """batch_admit (jitter 0.4): exhaustion walk — sleeps [0.14, 0.28, 1.26, 2.52], retry-after 0.175s."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_admit')
    assert clock.sleeps == [0.14, 0.28, 1.26, 2.52]
    assert caught.value.retry_after == pytest.approx(0.175)


def test_grid_wave_sibling2_admit_jitter_04(monkeypatch):
    """batch_admit (jitter 0.4): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.14, 0.455, 1.26, 2.52]


def test_grid_wave_sibling3_admit_jitter_04(monkeypatch):
    """batch_admit (jitter 0.4): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.14, 0.28, 1.26, 2.52]


def test_grid_wave_doublearm_admit_jitter_04(monkeypatch):
    """batch_admit (jitter 0.4): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.14, 0.455, 1.26, 2.52]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_admit')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_admit_jitter_05(monkeypatch):
    """batch_admit (jitter 0.5): recover on attempt 4 — sleeps [0.15, 0.3, 1.35]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=3)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_admit_jitter_05(monkeypatch):
    """batch_admit (jitter 0.5): recover on attempt 5 — sleeps [0.15, 0.3, 1.35, 2.7]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_admit_jitter_05(monkeypatch):
    """batch_admit (jitter 0.5): exhaustion walk — sleeps [0.15, 0.3, 1.35, 2.7], retry-after 0.1875s."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_admit')
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]
    assert caught.value.retry_after == pytest.approx(0.1875)


def test_grid_wave_sibling2_admit_jitter_05(monkeypatch):
    """batch_admit (jitter 0.5): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.15, 0.4875, 1.35, 2.7]


def test_grid_wave_sibling3_admit_jitter_05(monkeypatch):
    """batch_admit (jitter 0.5): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]


def test_grid_wave_doublearm_admit_jitter_05(monkeypatch):
    """batch_admit (jitter 0.5): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.15, 0.4875, 1.35, 2.7]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_admit')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_admit_jitter_06(monkeypatch):
    """batch_admit (jitter 0.6): recover on attempt 4 — sleeps [0.16, 0.32, 1.44]."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=3)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.16, 0.32, 1.44]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_admit_jitter_06(monkeypatch):
    """batch_admit (jitter 0.6): recover on attempt 5 — sleeps [0.16, 0.32, 1.44, 2.88]."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.16, 0.32, 1.44, 2.88]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_admit_jitter_06(monkeypatch):
    """batch_admit (jitter 0.6): exhaustion walk — sleeps [0.16, 0.32, 1.44, 2.88], retry-after 0.2s."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_admit')
    assert clock.sleeps == [0.16, 0.32, 1.44, 2.88]
    assert caught.value.retry_after == pytest.approx(0.2)


def test_grid_wave_sibling2_admit_jitter_06(monkeypatch):
    """batch_admit (jitter 0.6): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.16, 0.52, 1.44, 2.88]


def test_grid_wave_sibling3_admit_jitter_06(monkeypatch):
    """batch_admit (jitter 0.6): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.16, 0.32, 1.44, 2.88]


def test_grid_wave_doublearm_admit_jitter_06(monkeypatch):
    """batch_admit (jitter 0.6): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.16, 0.52, 1.44, 2.88]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_admit')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_admit_jitter_07(monkeypatch):
    """batch_admit (jitter 0.7): recover on attempt 4 — sleeps [0.17, 0.34, 1.53]."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=3)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.17, 0.34, 1.53]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_admit_jitter_07(monkeypatch):
    """batch_admit (jitter 0.7): recover on attempt 5 — sleeps [0.17, 0.34, 1.53, 3.06]."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.17, 0.34, 1.53, 3.06]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_admit_jitter_07(monkeypatch):
    """batch_admit (jitter 0.7): exhaustion walk — sleeps [0.17, 0.34, 1.53, 3.06], retry-after 0.2125s."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_admit')
    assert clock.sleeps == [0.17, 0.34, 1.53, 3.06]
    assert caught.value.retry_after == pytest.approx(0.2125)


def test_grid_wave_sibling2_admit_jitter_07(monkeypatch):
    """batch_admit (jitter 0.7): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.17, 0.5525, 1.53, 3.06]


def test_grid_wave_sibling3_admit_jitter_07(monkeypatch):
    """batch_admit (jitter 0.7): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.17, 0.34, 1.53, 3.06]


def test_grid_wave_doublearm_admit_jitter_07(monkeypatch):
    """batch_admit (jitter 0.7): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.17, 0.5525, 1.53, 3.06]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_admit')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_admit_jitter_08(monkeypatch):
    """batch_admit (jitter 0.8): recover on attempt 4 — sleeps [0.18, 0.36, 1.62]."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=3)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.18, 0.36, 1.62]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_admit_jitter_08(monkeypatch):
    """batch_admit (jitter 0.8): recover on attempt 5 — sleeps [0.18, 0.36, 1.62, 3.24]."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.18, 0.36, 1.62, 3.24]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_admit_jitter_08(monkeypatch):
    """batch_admit (jitter 0.8): exhaustion walk — sleeps [0.18, 0.36, 1.62, 3.24], retry-after 0.225s."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_admit')
    assert clock.sleeps == [0.18, 0.36, 1.62, 3.24]
    assert caught.value.retry_after == pytest.approx(0.225)


def test_grid_wave_sibling2_admit_jitter_08(monkeypatch):
    """batch_admit (jitter 0.8): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.18, 0.585, 1.62, 3.24]


def test_grid_wave_sibling3_admit_jitter_08(monkeypatch):
    """batch_admit (jitter 0.8): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.18, 0.36, 1.62, 3.24]


def test_grid_wave_doublearm_admit_jitter_08(monkeypatch):
    """batch_admit (jitter 0.8): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.18, 0.585, 1.62, 3.24]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_admit')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_admit_jitter_09(monkeypatch):
    """batch_admit (jitter 0.9): recover on attempt 4 — sleeps [0.19, 0.38, 1.71]."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=3)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.19, 0.38, 1.71]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_admit_jitter_09(monkeypatch):
    """batch_admit (jitter 0.9): recover on attempt 5 — sleeps [0.19, 0.38, 1.71, 3.42]."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.19, 0.38, 1.71, 3.42]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_admit_jitter_09(monkeypatch):
    """batch_admit (jitter 0.9): exhaustion walk — sleeps [0.19, 0.38, 1.71, 3.42], retry-after 0.2375s."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_admit')
    assert clock.sleeps == [0.19, 0.38, 1.71, 3.42]
    assert caught.value.retry_after == pytest.approx(0.2375)


def test_grid_wave_sibling2_admit_jitter_09(monkeypatch):
    """batch_admit (jitter 0.9): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.19, 0.6175, 1.71, 3.42]


def test_grid_wave_sibling3_admit_jitter_09(monkeypatch):
    """batch_admit (jitter 0.9): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.19, 0.38, 1.71, 3.42]


def test_grid_wave_doublearm_admit_jitter_09(monkeypatch):
    """batch_admit (jitter 0.9): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.19, 0.6175, 1.71, 3.42]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_admit')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_admit_jitter_10(monkeypatch):
    """batch_admit (jitter 1.0): recover on attempt 4 — sleeps [0.2, 0.4, 1.8]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=3)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_admit_jitter_10(monkeypatch):
    """batch_admit (jitter 1.0): recover on attempt 5 — sleeps [0.2, 0.4, 1.8, 3.6]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_admit_jitter_10(monkeypatch):
    """batch_admit (jitter 1.0): exhaustion walk — sleeps [0.2, 0.4, 1.8, 3.6], retry-after 0.25s."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_admit')
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]
    assert caught.value.retry_after == pytest.approx(0.25)


def test_grid_wave_sibling2_admit_jitter_10(monkeypatch):
    """batch_admit (jitter 1.0): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.2, 0.65, 1.8, 3.6]


def test_grid_wave_sibling3_admit_jitter_10(monkeypatch):
    """batch_admit (jitter 1.0): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]


def test_grid_wave_doublearm_admit_jitter_10(monkeypatch):
    """batch_admit (jitter 1.0): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_admit', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_admit') == 'committed'
    assert clock.sleeps == [0.2, 0.65, 1.8, 3.6]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_admit')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_fail_jitter_00(monkeypatch):
    """batch_fail (jitter 0.0): recover on attempt 4 — sleeps [0.1, 0.2, 0.9]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=3)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_fail_jitter_00(monkeypatch):
    """batch_fail (jitter 0.0): recover on attempt 5 — sleeps [0.1, 0.2, 0.9, 1.8]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_fail_jitter_00(monkeypatch):
    """batch_fail (jitter 0.0): exhaustion walk — sleeps [0.1, 0.2, 0.9, 1.8], retry-after 0.125s."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_fail')
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]
    assert caught.value.retry_after == pytest.approx(0.125)


def test_grid_wave_sibling2_fail_jitter_00(monkeypatch):
    """batch_fail (jitter 0.0): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.1, 0.325, 0.9, 1.8]


def test_grid_wave_sibling3_fail_jitter_00(monkeypatch):
    """batch_fail (jitter 0.0): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]


def test_grid_wave_doublearm_fail_jitter_00(monkeypatch):
    """batch_fail (jitter 0.0): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.1, 0.325, 0.9, 1.8]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_fail')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_fail_jitter_01(monkeypatch):
    """batch_fail (jitter 0.1): recover on attempt 4 — sleeps [0.11, 0.22, 0.99]."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=3)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.11, 0.22, 0.99]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_fail_jitter_01(monkeypatch):
    """batch_fail (jitter 0.1): recover on attempt 5 — sleeps [0.11, 0.22, 0.99, 1.98]."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.11, 0.22, 0.99, 1.98]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_fail_jitter_01(monkeypatch):
    """batch_fail (jitter 0.1): exhaustion walk — sleeps [0.11, 0.22, 0.99, 1.98], retry-after 0.1375s."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_fail')
    assert clock.sleeps == [0.11, 0.22, 0.99, 1.98]
    assert caught.value.retry_after == pytest.approx(0.1375)


def test_grid_wave_sibling2_fail_jitter_01(monkeypatch):
    """batch_fail (jitter 0.1): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.11, 0.3575, 0.99, 1.98]


def test_grid_wave_sibling3_fail_jitter_01(monkeypatch):
    """batch_fail (jitter 0.1): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.11, 0.22, 0.99, 1.98]


def test_grid_wave_doublearm_fail_jitter_01(monkeypatch):
    """batch_fail (jitter 0.1): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.11, 0.3575, 0.99, 1.98]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_fail')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_fail_jitter_02(monkeypatch):
    """batch_fail (jitter 0.2): recover on attempt 4 — sleeps [0.12, 0.24, 1.08]."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=3)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.12, 0.24, 1.08]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_fail_jitter_02(monkeypatch):
    """batch_fail (jitter 0.2): recover on attempt 5 — sleeps [0.12, 0.24, 1.08, 2.16]."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.12, 0.24, 1.08, 2.16]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_fail_jitter_02(monkeypatch):
    """batch_fail (jitter 0.2): exhaustion walk — sleeps [0.12, 0.24, 1.08, 2.16], retry-after 0.15s."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_fail')
    assert clock.sleeps == [0.12, 0.24, 1.08, 2.16]
    assert caught.value.retry_after == pytest.approx(0.15)


def test_grid_wave_sibling2_fail_jitter_02(monkeypatch):
    """batch_fail (jitter 0.2): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.12, 0.39, 1.08, 2.16]


def test_grid_wave_sibling3_fail_jitter_02(monkeypatch):
    """batch_fail (jitter 0.2): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.12, 0.24, 1.08, 2.16]


def test_grid_wave_doublearm_fail_jitter_02(monkeypatch):
    """batch_fail (jitter 0.2): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.12, 0.39, 1.08, 2.16]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_fail')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_fail_jitter_03(monkeypatch):
    """batch_fail (jitter 0.3): recover on attempt 4 — sleeps [0.13, 0.26, 1.17]."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=3)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.13, 0.26, 1.17]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_fail_jitter_03(monkeypatch):
    """batch_fail (jitter 0.3): recover on attempt 5 — sleeps [0.13, 0.26, 1.17, 2.34]."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.13, 0.26, 1.17, 2.34]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_fail_jitter_03(monkeypatch):
    """batch_fail (jitter 0.3): exhaustion walk — sleeps [0.13, 0.26, 1.17, 2.34], retry-after 0.1625s."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_fail')
    assert clock.sleeps == [0.13, 0.26, 1.17, 2.34]
    assert caught.value.retry_after == pytest.approx(0.1625)


def test_grid_wave_sibling2_fail_jitter_03(monkeypatch):
    """batch_fail (jitter 0.3): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.13, 0.4225, 1.17, 2.34]


def test_grid_wave_sibling3_fail_jitter_03(monkeypatch):
    """batch_fail (jitter 0.3): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.13, 0.26, 1.17, 2.34]


def test_grid_wave_doublearm_fail_jitter_03(monkeypatch):
    """batch_fail (jitter 0.3): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.13, 0.4225, 1.17, 2.34]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_fail')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_fail_jitter_04(monkeypatch):
    """batch_fail (jitter 0.4): recover on attempt 4 — sleeps [0.14, 0.28, 1.26]."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=3)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.14, 0.28, 1.26]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_fail_jitter_04(monkeypatch):
    """batch_fail (jitter 0.4): recover on attempt 5 — sleeps [0.14, 0.28, 1.26, 2.52]."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.14, 0.28, 1.26, 2.52]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_fail_jitter_04(monkeypatch):
    """batch_fail (jitter 0.4): exhaustion walk — sleeps [0.14, 0.28, 1.26, 2.52], retry-after 0.175s."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_fail')
    assert clock.sleeps == [0.14, 0.28, 1.26, 2.52]
    assert caught.value.retry_after == pytest.approx(0.175)


def test_grid_wave_sibling2_fail_jitter_04(monkeypatch):
    """batch_fail (jitter 0.4): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.14, 0.455, 1.26, 2.52]


def test_grid_wave_sibling3_fail_jitter_04(monkeypatch):
    """batch_fail (jitter 0.4): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.14, 0.28, 1.26, 2.52]


def test_grid_wave_doublearm_fail_jitter_04(monkeypatch):
    """batch_fail (jitter 0.4): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.14, 0.455, 1.26, 2.52]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_fail')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_fail_jitter_05(monkeypatch):
    """batch_fail (jitter 0.5): recover on attempt 4 — sleeps [0.15, 0.3, 1.35]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=3)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_fail_jitter_05(monkeypatch):
    """batch_fail (jitter 0.5): recover on attempt 5 — sleeps [0.15, 0.3, 1.35, 2.7]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_fail_jitter_05(monkeypatch):
    """batch_fail (jitter 0.5): exhaustion walk — sleeps [0.15, 0.3, 1.35, 2.7], retry-after 0.1875s."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_fail')
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]
    assert caught.value.retry_after == pytest.approx(0.1875)


def test_grid_wave_sibling2_fail_jitter_05(monkeypatch):
    """batch_fail (jitter 0.5): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.15, 0.4875, 1.35, 2.7]


def test_grid_wave_sibling3_fail_jitter_05(monkeypatch):
    """batch_fail (jitter 0.5): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]


def test_grid_wave_doublearm_fail_jitter_05(monkeypatch):
    """batch_fail (jitter 0.5): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.15, 0.4875, 1.35, 2.7]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_fail')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_fail_jitter_06(monkeypatch):
    """batch_fail (jitter 0.6): recover on attempt 4 — sleeps [0.16, 0.32, 1.44]."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=3)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.16, 0.32, 1.44]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_fail_jitter_06(monkeypatch):
    """batch_fail (jitter 0.6): recover on attempt 5 — sleeps [0.16, 0.32, 1.44, 2.88]."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.16, 0.32, 1.44, 2.88]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_fail_jitter_06(monkeypatch):
    """batch_fail (jitter 0.6): exhaustion walk — sleeps [0.16, 0.32, 1.44, 2.88], retry-after 0.2s."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_fail')
    assert clock.sleeps == [0.16, 0.32, 1.44, 2.88]
    assert caught.value.retry_after == pytest.approx(0.2)


def test_grid_wave_sibling2_fail_jitter_06(monkeypatch):
    """batch_fail (jitter 0.6): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.16, 0.52, 1.44, 2.88]


def test_grid_wave_sibling3_fail_jitter_06(monkeypatch):
    """batch_fail (jitter 0.6): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.16, 0.32, 1.44, 2.88]


def test_grid_wave_doublearm_fail_jitter_06(monkeypatch):
    """batch_fail (jitter 0.6): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.16, 0.52, 1.44, 2.88]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_fail')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_fail_jitter_07(monkeypatch):
    """batch_fail (jitter 0.7): recover on attempt 4 — sleeps [0.17, 0.34, 1.53]."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=3)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.17, 0.34, 1.53]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_fail_jitter_07(monkeypatch):
    """batch_fail (jitter 0.7): recover on attempt 5 — sleeps [0.17, 0.34, 1.53, 3.06]."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.17, 0.34, 1.53, 3.06]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_fail_jitter_07(monkeypatch):
    """batch_fail (jitter 0.7): exhaustion walk — sleeps [0.17, 0.34, 1.53, 3.06], retry-after 0.2125s."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_fail')
    assert clock.sleeps == [0.17, 0.34, 1.53, 3.06]
    assert caught.value.retry_after == pytest.approx(0.2125)


def test_grid_wave_sibling2_fail_jitter_07(monkeypatch):
    """batch_fail (jitter 0.7): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.17, 0.5525, 1.53, 3.06]


def test_grid_wave_sibling3_fail_jitter_07(monkeypatch):
    """batch_fail (jitter 0.7): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.17, 0.34, 1.53, 3.06]


def test_grid_wave_doublearm_fail_jitter_07(monkeypatch):
    """batch_fail (jitter 0.7): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.17, 0.5525, 1.53, 3.06]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_fail')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_fail_jitter_08(monkeypatch):
    """batch_fail (jitter 0.8): recover on attempt 4 — sleeps [0.18, 0.36, 1.62]."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=3)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.18, 0.36, 1.62]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_fail_jitter_08(monkeypatch):
    """batch_fail (jitter 0.8): recover on attempt 5 — sleeps [0.18, 0.36, 1.62, 3.24]."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.18, 0.36, 1.62, 3.24]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_fail_jitter_08(monkeypatch):
    """batch_fail (jitter 0.8): exhaustion walk — sleeps [0.18, 0.36, 1.62, 3.24], retry-after 0.225s."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_fail')
    assert clock.sleeps == [0.18, 0.36, 1.62, 3.24]
    assert caught.value.retry_after == pytest.approx(0.225)


def test_grid_wave_sibling2_fail_jitter_08(monkeypatch):
    """batch_fail (jitter 0.8): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.18, 0.585, 1.62, 3.24]


def test_grid_wave_sibling3_fail_jitter_08(monkeypatch):
    """batch_fail (jitter 0.8): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.18, 0.36, 1.62, 3.24]


def test_grid_wave_doublearm_fail_jitter_08(monkeypatch):
    """batch_fail (jitter 0.8): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.18, 0.585, 1.62, 3.24]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_fail')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_fail_jitter_09(monkeypatch):
    """batch_fail (jitter 0.9): recover on attempt 4 — sleeps [0.19, 0.38, 1.71]."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=3)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.19, 0.38, 1.71]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_fail_jitter_09(monkeypatch):
    """batch_fail (jitter 0.9): recover on attempt 5 — sleeps [0.19, 0.38, 1.71, 3.42]."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.19, 0.38, 1.71, 3.42]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_fail_jitter_09(monkeypatch):
    """batch_fail (jitter 0.9): exhaustion walk — sleeps [0.19, 0.38, 1.71, 3.42], retry-after 0.2375s."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_fail')
    assert clock.sleeps == [0.19, 0.38, 1.71, 3.42]
    assert caught.value.retry_after == pytest.approx(0.2375)


def test_grid_wave_sibling2_fail_jitter_09(monkeypatch):
    """batch_fail (jitter 0.9): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.19, 0.6175, 1.71, 3.42]


def test_grid_wave_sibling3_fail_jitter_09(monkeypatch):
    """batch_fail (jitter 0.9): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.19, 0.38, 1.71, 3.42]


def test_grid_wave_doublearm_fail_jitter_09(monkeypatch):
    """batch_fail (jitter 0.9): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.19, 0.6175, 1.71, 3.42]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_fail')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_fail_jitter_10(monkeypatch):
    """batch_fail (jitter 1.0): recover on attempt 4 — sleeps [0.2, 0.4, 1.8]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=3)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_fail_jitter_10(monkeypatch):
    """batch_fail (jitter 1.0): recover on attempt 5 — sleeps [0.2, 0.4, 1.8, 3.6]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_fail_jitter_10(monkeypatch):
    """batch_fail (jitter 1.0): exhaustion walk — sleeps [0.2, 0.4, 1.8, 3.6], retry-after 0.25s."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_fail')
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]
    assert caught.value.retry_after == pytest.approx(0.25)


def test_grid_wave_sibling2_fail_jitter_10(monkeypatch):
    """batch_fail (jitter 1.0): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.2, 0.65, 1.8, 3.6]


def test_grid_wave_sibling3_fail_jitter_10(monkeypatch):
    """batch_fail (jitter 1.0): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]


def test_grid_wave_doublearm_fail_jitter_10(monkeypatch):
    """batch_fail (jitter 1.0): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_fail', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_fail') == 'committed'
    assert clock.sleeps == [0.2, 0.65, 1.8, 3.6]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_fail')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_complete_jitter_00(monkeypatch):
    """batch_complete (jitter 0.0): recover on attempt 4 — sleeps [0.1, 0.2, 0.9]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=3)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_complete_jitter_00(monkeypatch):
    """batch_complete (jitter 0.0): recover on attempt 5 — sleeps [0.1, 0.2, 0.9, 1.8]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_complete_jitter_00(monkeypatch):
    """batch_complete (jitter 0.0): exhaustion walk — sleeps [0.1, 0.2, 0.9, 1.8], retry-after 0.125s."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_complete')
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]
    assert caught.value.retry_after == pytest.approx(0.125)


def test_grid_wave_sibling2_complete_jitter_00(monkeypatch):
    """batch_complete (jitter 0.0): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.1, 0.325, 0.9, 1.8]


def test_grid_wave_sibling3_complete_jitter_00(monkeypatch):
    """batch_complete (jitter 0.0): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]


def test_grid_wave_doublearm_complete_jitter_00(monkeypatch):
    """batch_complete (jitter 0.0): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.1, 0.325, 0.9, 1.8]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_complete')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_complete_jitter_01(monkeypatch):
    """batch_complete (jitter 0.1): recover on attempt 4 — sleeps [0.11, 0.22, 0.99]."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=3)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.11, 0.22, 0.99]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_complete_jitter_01(monkeypatch):
    """batch_complete (jitter 0.1): recover on attempt 5 — sleeps [0.11, 0.22, 0.99, 1.98]."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.11, 0.22, 0.99, 1.98]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_complete_jitter_01(monkeypatch):
    """batch_complete (jitter 0.1): exhaustion walk — sleeps [0.11, 0.22, 0.99, 1.98], retry-after 0.1375s."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_complete')
    assert clock.sleeps == [0.11, 0.22, 0.99, 1.98]
    assert caught.value.retry_after == pytest.approx(0.1375)


def test_grid_wave_sibling2_complete_jitter_01(monkeypatch):
    """batch_complete (jitter 0.1): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.11, 0.3575, 0.99, 1.98]


def test_grid_wave_sibling3_complete_jitter_01(monkeypatch):
    """batch_complete (jitter 0.1): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.11, 0.22, 0.99, 1.98]


def test_grid_wave_doublearm_complete_jitter_01(monkeypatch):
    """batch_complete (jitter 0.1): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.11, 0.3575, 0.99, 1.98]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_complete')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_complete_jitter_02(monkeypatch):
    """batch_complete (jitter 0.2): recover on attempt 4 — sleeps [0.12, 0.24, 1.08]."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=3)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.12, 0.24, 1.08]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_complete_jitter_02(monkeypatch):
    """batch_complete (jitter 0.2): recover on attempt 5 — sleeps [0.12, 0.24, 1.08, 2.16]."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.12, 0.24, 1.08, 2.16]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_complete_jitter_02(monkeypatch):
    """batch_complete (jitter 0.2): exhaustion walk — sleeps [0.12, 0.24, 1.08, 2.16], retry-after 0.15s."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_complete')
    assert clock.sleeps == [0.12, 0.24, 1.08, 2.16]
    assert caught.value.retry_after == pytest.approx(0.15)


def test_grid_wave_sibling2_complete_jitter_02(monkeypatch):
    """batch_complete (jitter 0.2): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.12, 0.39, 1.08, 2.16]


def test_grid_wave_sibling3_complete_jitter_02(monkeypatch):
    """batch_complete (jitter 0.2): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.12, 0.24, 1.08, 2.16]


def test_grid_wave_doublearm_complete_jitter_02(monkeypatch):
    """batch_complete (jitter 0.2): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.12, 0.39, 1.08, 2.16]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_complete')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_complete_jitter_03(monkeypatch):
    """batch_complete (jitter 0.3): recover on attempt 4 — sleeps [0.13, 0.26, 1.17]."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=3)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.13, 0.26, 1.17]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_complete_jitter_03(monkeypatch):
    """batch_complete (jitter 0.3): recover on attempt 5 — sleeps [0.13, 0.26, 1.17, 2.34]."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.13, 0.26, 1.17, 2.34]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_complete_jitter_03(monkeypatch):
    """batch_complete (jitter 0.3): exhaustion walk — sleeps [0.13, 0.26, 1.17, 2.34], retry-after 0.1625s."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_complete')
    assert clock.sleeps == [0.13, 0.26, 1.17, 2.34]
    assert caught.value.retry_after == pytest.approx(0.1625)


def test_grid_wave_sibling2_complete_jitter_03(monkeypatch):
    """batch_complete (jitter 0.3): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.13, 0.4225, 1.17, 2.34]


def test_grid_wave_sibling3_complete_jitter_03(monkeypatch):
    """batch_complete (jitter 0.3): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.13, 0.26, 1.17, 2.34]


def test_grid_wave_doublearm_complete_jitter_03(monkeypatch):
    """batch_complete (jitter 0.3): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.13, 0.4225, 1.17, 2.34]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_complete')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_complete_jitter_04(monkeypatch):
    """batch_complete (jitter 0.4): recover on attempt 4 — sleeps [0.14, 0.28, 1.26]."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=3)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.14, 0.28, 1.26]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_complete_jitter_04(monkeypatch):
    """batch_complete (jitter 0.4): recover on attempt 5 — sleeps [0.14, 0.28, 1.26, 2.52]."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.14, 0.28, 1.26, 2.52]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_complete_jitter_04(monkeypatch):
    """batch_complete (jitter 0.4): exhaustion walk — sleeps [0.14, 0.28, 1.26, 2.52], retry-after 0.175s."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_complete')
    assert clock.sleeps == [0.14, 0.28, 1.26, 2.52]
    assert caught.value.retry_after == pytest.approx(0.175)


def test_grid_wave_sibling2_complete_jitter_04(monkeypatch):
    """batch_complete (jitter 0.4): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.14, 0.455, 1.26, 2.52]


def test_grid_wave_sibling3_complete_jitter_04(monkeypatch):
    """batch_complete (jitter 0.4): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.14, 0.28, 1.26, 2.52]


def test_grid_wave_doublearm_complete_jitter_04(monkeypatch):
    """batch_complete (jitter 0.4): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.14, 0.455, 1.26, 2.52]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_complete')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_complete_jitter_05(monkeypatch):
    """batch_complete (jitter 0.5): recover on attempt 4 — sleeps [0.15, 0.3, 1.35]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=3)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_complete_jitter_05(monkeypatch):
    """batch_complete (jitter 0.5): recover on attempt 5 — sleeps [0.15, 0.3, 1.35, 2.7]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_complete_jitter_05(monkeypatch):
    """batch_complete (jitter 0.5): exhaustion walk — sleeps [0.15, 0.3, 1.35, 2.7], retry-after 0.1875s."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_complete')
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]
    assert caught.value.retry_after == pytest.approx(0.1875)


def test_grid_wave_sibling2_complete_jitter_05(monkeypatch):
    """batch_complete (jitter 0.5): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.15, 0.4875, 1.35, 2.7]


def test_grid_wave_sibling3_complete_jitter_05(monkeypatch):
    """batch_complete (jitter 0.5): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]


def test_grid_wave_doublearm_complete_jitter_05(monkeypatch):
    """batch_complete (jitter 0.5): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.15, 0.4875, 1.35, 2.7]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_complete')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_complete_jitter_06(monkeypatch):
    """batch_complete (jitter 0.6): recover on attempt 4 — sleeps [0.16, 0.32, 1.44]."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=3)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.16, 0.32, 1.44]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_complete_jitter_06(monkeypatch):
    """batch_complete (jitter 0.6): recover on attempt 5 — sleeps [0.16, 0.32, 1.44, 2.88]."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.16, 0.32, 1.44, 2.88]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_complete_jitter_06(monkeypatch):
    """batch_complete (jitter 0.6): exhaustion walk — sleeps [0.16, 0.32, 1.44, 2.88], retry-after 0.2s."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_complete')
    assert clock.sleeps == [0.16, 0.32, 1.44, 2.88]
    assert caught.value.retry_after == pytest.approx(0.2)


def test_grid_wave_sibling2_complete_jitter_06(monkeypatch):
    """batch_complete (jitter 0.6): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.16, 0.52, 1.44, 2.88]


def test_grid_wave_sibling3_complete_jitter_06(monkeypatch):
    """batch_complete (jitter 0.6): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.16, 0.32, 1.44, 2.88]


def test_grid_wave_doublearm_complete_jitter_06(monkeypatch):
    """batch_complete (jitter 0.6): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.16, 0.52, 1.44, 2.88]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_complete')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_complete_jitter_07(monkeypatch):
    """batch_complete (jitter 0.7): recover on attempt 4 — sleeps [0.17, 0.34, 1.53]."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=3)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.17, 0.34, 1.53]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_complete_jitter_07(monkeypatch):
    """batch_complete (jitter 0.7): recover on attempt 5 — sleeps [0.17, 0.34, 1.53, 3.06]."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.17, 0.34, 1.53, 3.06]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_complete_jitter_07(monkeypatch):
    """batch_complete (jitter 0.7): exhaustion walk — sleeps [0.17, 0.34, 1.53, 3.06], retry-after 0.2125s."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_complete')
    assert clock.sleeps == [0.17, 0.34, 1.53, 3.06]
    assert caught.value.retry_after == pytest.approx(0.2125)


def test_grid_wave_sibling2_complete_jitter_07(monkeypatch):
    """batch_complete (jitter 0.7): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.17, 0.5525, 1.53, 3.06]


def test_grid_wave_sibling3_complete_jitter_07(monkeypatch):
    """batch_complete (jitter 0.7): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.17, 0.34, 1.53, 3.06]


def test_grid_wave_doublearm_complete_jitter_07(monkeypatch):
    """batch_complete (jitter 0.7): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.17, 0.5525, 1.53, 3.06]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_complete')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_complete_jitter_08(monkeypatch):
    """batch_complete (jitter 0.8): recover on attempt 4 — sleeps [0.18, 0.36, 1.62]."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=3)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.18, 0.36, 1.62]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_complete_jitter_08(monkeypatch):
    """batch_complete (jitter 0.8): recover on attempt 5 — sleeps [0.18, 0.36, 1.62, 3.24]."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.18, 0.36, 1.62, 3.24]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_complete_jitter_08(monkeypatch):
    """batch_complete (jitter 0.8): exhaustion walk — sleeps [0.18, 0.36, 1.62, 3.24], retry-after 0.225s."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_complete')
    assert clock.sleeps == [0.18, 0.36, 1.62, 3.24]
    assert caught.value.retry_after == pytest.approx(0.225)


def test_grid_wave_sibling2_complete_jitter_08(monkeypatch):
    """batch_complete (jitter 0.8): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.18, 0.585, 1.62, 3.24]


def test_grid_wave_sibling3_complete_jitter_08(monkeypatch):
    """batch_complete (jitter 0.8): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.18, 0.36, 1.62, 3.24]


def test_grid_wave_doublearm_complete_jitter_08(monkeypatch):
    """batch_complete (jitter 0.8): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.18, 0.585, 1.62, 3.24]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_complete')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_complete_jitter_09(monkeypatch):
    """batch_complete (jitter 0.9): recover on attempt 4 — sleeps [0.19, 0.38, 1.71]."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=3)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.19, 0.38, 1.71]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_complete_jitter_09(monkeypatch):
    """batch_complete (jitter 0.9): recover on attempt 5 — sleeps [0.19, 0.38, 1.71, 3.42]."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.19, 0.38, 1.71, 3.42]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_complete_jitter_09(monkeypatch):
    """batch_complete (jitter 0.9): exhaustion walk — sleeps [0.19, 0.38, 1.71, 3.42], retry-after 0.2375s."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_complete')
    assert clock.sleeps == [0.19, 0.38, 1.71, 3.42]
    assert caught.value.retry_after == pytest.approx(0.2375)


def test_grid_wave_sibling2_complete_jitter_09(monkeypatch):
    """batch_complete (jitter 0.9): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.19, 0.6175, 1.71, 3.42]


def test_grid_wave_sibling3_complete_jitter_09(monkeypatch):
    """batch_complete (jitter 0.9): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.19, 0.38, 1.71, 3.42]


def test_grid_wave_doublearm_complete_jitter_09(monkeypatch):
    """batch_complete (jitter 0.9): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.19, 0.6175, 1.71, 3.42]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_complete')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_complete_jitter_10(monkeypatch):
    """batch_complete (jitter 1.0): recover on attempt 4 — sleeps [0.2, 0.4, 1.8]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=3)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_complete_jitter_10(monkeypatch):
    """batch_complete (jitter 1.0): recover on attempt 5 — sleeps [0.2, 0.4, 1.8, 3.6]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_complete_jitter_10(monkeypatch):
    """batch_complete (jitter 1.0): exhaustion walk — sleeps [0.2, 0.4, 1.8, 3.6], retry-after 0.25s."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_complete')
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]
    assert caught.value.retry_after == pytest.approx(0.25)


def test_grid_wave_sibling2_complete_jitter_10(monkeypatch):
    """batch_complete (jitter 1.0): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.2, 0.65, 1.8, 3.6]


def test_grid_wave_sibling3_complete_jitter_10(monkeypatch):
    """batch_complete (jitter 1.0): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]


def test_grid_wave_doublearm_complete_jitter_10(monkeypatch):
    """batch_complete (jitter 1.0): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_complete', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_complete') == 'committed'
    assert clock.sleeps == [0.2, 0.65, 1.8, 3.6]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_complete')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_defer_jitter_00(monkeypatch):
    """batch_defer (jitter 0.0): recover on attempt 4 — sleeps [0.1, 0.2, 0.9]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=3)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_defer_jitter_00(monkeypatch):
    """batch_defer (jitter 0.0): recover on attempt 5 — sleeps [0.1, 0.2, 0.9, 1.8]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_defer_jitter_00(monkeypatch):
    """batch_defer (jitter 0.0): exhaustion walk — sleeps [0.1, 0.2, 0.9, 1.8], retry-after 0.125s."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_defer')
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]
    assert caught.value.retry_after == pytest.approx(0.125)


def test_grid_wave_sibling2_defer_jitter_00(monkeypatch):
    """batch_defer (jitter 0.0): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.1, 0.325, 0.9, 1.8]


def test_grid_wave_sibling3_defer_jitter_00(monkeypatch):
    """batch_defer (jitter 0.0): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]


def test_grid_wave_doublearm_defer_jitter_00(monkeypatch):
    """batch_defer (jitter 0.0): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.1, 0.325, 0.9, 1.8]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_defer')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_defer_jitter_01(monkeypatch):
    """batch_defer (jitter 0.1): recover on attempt 4 — sleeps [0.11, 0.22, 0.99]."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=3)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.11, 0.22, 0.99]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_defer_jitter_01(monkeypatch):
    """batch_defer (jitter 0.1): recover on attempt 5 — sleeps [0.11, 0.22, 0.99, 1.98]."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.11, 0.22, 0.99, 1.98]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_defer_jitter_01(monkeypatch):
    """batch_defer (jitter 0.1): exhaustion walk — sleeps [0.11, 0.22, 0.99, 1.98], retry-after 0.1375s."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_defer')
    assert clock.sleeps == [0.11, 0.22, 0.99, 1.98]
    assert caught.value.retry_after == pytest.approx(0.1375)


def test_grid_wave_sibling2_defer_jitter_01(monkeypatch):
    """batch_defer (jitter 0.1): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.11, 0.3575, 0.99, 1.98]


def test_grid_wave_sibling3_defer_jitter_01(monkeypatch):
    """batch_defer (jitter 0.1): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.11, 0.22, 0.99, 1.98]


def test_grid_wave_doublearm_defer_jitter_01(monkeypatch):
    """batch_defer (jitter 0.1): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.11, 0.3575, 0.99, 1.98]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_defer')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_defer_jitter_02(monkeypatch):
    """batch_defer (jitter 0.2): recover on attempt 4 — sleeps [0.12, 0.24, 1.08]."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=3)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.12, 0.24, 1.08]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_defer_jitter_02(monkeypatch):
    """batch_defer (jitter 0.2): recover on attempt 5 — sleeps [0.12, 0.24, 1.08, 2.16]."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.12, 0.24, 1.08, 2.16]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_defer_jitter_02(monkeypatch):
    """batch_defer (jitter 0.2): exhaustion walk — sleeps [0.12, 0.24, 1.08, 2.16], retry-after 0.15s."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_defer')
    assert clock.sleeps == [0.12, 0.24, 1.08, 2.16]
    assert caught.value.retry_after == pytest.approx(0.15)


def test_grid_wave_sibling2_defer_jitter_02(monkeypatch):
    """batch_defer (jitter 0.2): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.12, 0.39, 1.08, 2.16]


def test_grid_wave_sibling3_defer_jitter_02(monkeypatch):
    """batch_defer (jitter 0.2): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.12, 0.24, 1.08, 2.16]


def test_grid_wave_doublearm_defer_jitter_02(monkeypatch):
    """batch_defer (jitter 0.2): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.12, 0.39, 1.08, 2.16]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_defer')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_defer_jitter_03(monkeypatch):
    """batch_defer (jitter 0.3): recover on attempt 4 — sleeps [0.13, 0.26, 1.17]."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=3)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.13, 0.26, 1.17]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_defer_jitter_03(monkeypatch):
    """batch_defer (jitter 0.3): recover on attempt 5 — sleeps [0.13, 0.26, 1.17, 2.34]."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.13, 0.26, 1.17, 2.34]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_defer_jitter_03(monkeypatch):
    """batch_defer (jitter 0.3): exhaustion walk — sleeps [0.13, 0.26, 1.17, 2.34], retry-after 0.1625s."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_defer')
    assert clock.sleeps == [0.13, 0.26, 1.17, 2.34]
    assert caught.value.retry_after == pytest.approx(0.1625)


def test_grid_wave_sibling2_defer_jitter_03(monkeypatch):
    """batch_defer (jitter 0.3): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.13, 0.4225, 1.17, 2.34]


def test_grid_wave_sibling3_defer_jitter_03(monkeypatch):
    """batch_defer (jitter 0.3): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.13, 0.26, 1.17, 2.34]


def test_grid_wave_doublearm_defer_jitter_03(monkeypatch):
    """batch_defer (jitter 0.3): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.13, 0.4225, 1.17, 2.34]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_defer')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_defer_jitter_04(monkeypatch):
    """batch_defer (jitter 0.4): recover on attempt 4 — sleeps [0.14, 0.28, 1.26]."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=3)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.14, 0.28, 1.26]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_defer_jitter_04(monkeypatch):
    """batch_defer (jitter 0.4): recover on attempt 5 — sleeps [0.14, 0.28, 1.26, 2.52]."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.14, 0.28, 1.26, 2.52]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_defer_jitter_04(monkeypatch):
    """batch_defer (jitter 0.4): exhaustion walk — sleeps [0.14, 0.28, 1.26, 2.52], retry-after 0.175s."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_defer')
    assert clock.sleeps == [0.14, 0.28, 1.26, 2.52]
    assert caught.value.retry_after == pytest.approx(0.175)


def test_grid_wave_sibling2_defer_jitter_04(monkeypatch):
    """batch_defer (jitter 0.4): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.14, 0.455, 1.26, 2.52]


def test_grid_wave_sibling3_defer_jitter_04(monkeypatch):
    """batch_defer (jitter 0.4): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.14, 0.28, 1.26, 2.52]


def test_grid_wave_doublearm_defer_jitter_04(monkeypatch):
    """batch_defer (jitter 0.4): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.14, 0.455, 1.26, 2.52]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_defer')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_defer_jitter_05(monkeypatch):
    """batch_defer (jitter 0.5): recover on attempt 4 — sleeps [0.15, 0.3, 1.35]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=3)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_defer_jitter_05(monkeypatch):
    """batch_defer (jitter 0.5): recover on attempt 5 — sleeps [0.15, 0.3, 1.35, 2.7]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_defer_jitter_05(monkeypatch):
    """batch_defer (jitter 0.5): exhaustion walk — sleeps [0.15, 0.3, 1.35, 2.7], retry-after 0.1875s."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_defer')
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]
    assert caught.value.retry_after == pytest.approx(0.1875)


def test_grid_wave_sibling2_defer_jitter_05(monkeypatch):
    """batch_defer (jitter 0.5): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.15, 0.4875, 1.35, 2.7]


def test_grid_wave_sibling3_defer_jitter_05(monkeypatch):
    """batch_defer (jitter 0.5): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]


def test_grid_wave_doublearm_defer_jitter_05(monkeypatch):
    """batch_defer (jitter 0.5): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.15, 0.4875, 1.35, 2.7]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_defer')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_defer_jitter_06(monkeypatch):
    """batch_defer (jitter 0.6): recover on attempt 4 — sleeps [0.16, 0.32, 1.44]."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=3)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.16, 0.32, 1.44]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_defer_jitter_06(monkeypatch):
    """batch_defer (jitter 0.6): recover on attempt 5 — sleeps [0.16, 0.32, 1.44, 2.88]."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.16, 0.32, 1.44, 2.88]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_defer_jitter_06(monkeypatch):
    """batch_defer (jitter 0.6): exhaustion walk — sleeps [0.16, 0.32, 1.44, 2.88], retry-after 0.2s."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_defer')
    assert clock.sleeps == [0.16, 0.32, 1.44, 2.88]
    assert caught.value.retry_after == pytest.approx(0.2)


def test_grid_wave_sibling2_defer_jitter_06(monkeypatch):
    """batch_defer (jitter 0.6): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.16, 0.52, 1.44, 2.88]


def test_grid_wave_sibling3_defer_jitter_06(monkeypatch):
    """batch_defer (jitter 0.6): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.16, 0.32, 1.44, 2.88]


def test_grid_wave_doublearm_defer_jitter_06(monkeypatch):
    """batch_defer (jitter 0.6): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.16, 0.52, 1.44, 2.88]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_defer')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_defer_jitter_07(monkeypatch):
    """batch_defer (jitter 0.7): recover on attempt 4 — sleeps [0.17, 0.34, 1.53]."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=3)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.17, 0.34, 1.53]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_defer_jitter_07(monkeypatch):
    """batch_defer (jitter 0.7): recover on attempt 5 — sleeps [0.17, 0.34, 1.53, 3.06]."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.17, 0.34, 1.53, 3.06]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_defer_jitter_07(monkeypatch):
    """batch_defer (jitter 0.7): exhaustion walk — sleeps [0.17, 0.34, 1.53, 3.06], retry-after 0.2125s."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_defer')
    assert clock.sleeps == [0.17, 0.34, 1.53, 3.06]
    assert caught.value.retry_after == pytest.approx(0.2125)


def test_grid_wave_sibling2_defer_jitter_07(monkeypatch):
    """batch_defer (jitter 0.7): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.17, 0.5525, 1.53, 3.06]


def test_grid_wave_sibling3_defer_jitter_07(monkeypatch):
    """batch_defer (jitter 0.7): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.17, 0.34, 1.53, 3.06]


def test_grid_wave_doublearm_defer_jitter_07(monkeypatch):
    """batch_defer (jitter 0.7): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.17, 0.5525, 1.53, 3.06]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_defer')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_defer_jitter_08(monkeypatch):
    """batch_defer (jitter 0.8): recover on attempt 4 — sleeps [0.18, 0.36, 1.62]."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=3)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.18, 0.36, 1.62]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_defer_jitter_08(monkeypatch):
    """batch_defer (jitter 0.8): recover on attempt 5 — sleeps [0.18, 0.36, 1.62, 3.24]."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.18, 0.36, 1.62, 3.24]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_defer_jitter_08(monkeypatch):
    """batch_defer (jitter 0.8): exhaustion walk — sleeps [0.18, 0.36, 1.62, 3.24], retry-after 0.225s."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_defer')
    assert clock.sleeps == [0.18, 0.36, 1.62, 3.24]
    assert caught.value.retry_after == pytest.approx(0.225)


def test_grid_wave_sibling2_defer_jitter_08(monkeypatch):
    """batch_defer (jitter 0.8): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.18, 0.585, 1.62, 3.24]


def test_grid_wave_sibling3_defer_jitter_08(monkeypatch):
    """batch_defer (jitter 0.8): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.18, 0.36, 1.62, 3.24]


def test_grid_wave_doublearm_defer_jitter_08(monkeypatch):
    """batch_defer (jitter 0.8): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.18, 0.585, 1.62, 3.24]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_defer')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_defer_jitter_09(monkeypatch):
    """batch_defer (jitter 0.9): recover on attempt 4 — sleeps [0.19, 0.38, 1.71]."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=3)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.19, 0.38, 1.71]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_defer_jitter_09(monkeypatch):
    """batch_defer (jitter 0.9): recover on attempt 5 — sleeps [0.19, 0.38, 1.71, 3.42]."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.19, 0.38, 1.71, 3.42]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_defer_jitter_09(monkeypatch):
    """batch_defer (jitter 0.9): exhaustion walk — sleeps [0.19, 0.38, 1.71, 3.42], retry-after 0.2375s."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_defer')
    assert clock.sleeps == [0.19, 0.38, 1.71, 3.42]
    assert caught.value.retry_after == pytest.approx(0.2375)


def test_grid_wave_sibling2_defer_jitter_09(monkeypatch):
    """batch_defer (jitter 0.9): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.19, 0.6175, 1.71, 3.42]


def test_grid_wave_sibling3_defer_jitter_09(monkeypatch):
    """batch_defer (jitter 0.9): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.19, 0.38, 1.71, 3.42]


def test_grid_wave_doublearm_defer_jitter_09(monkeypatch):
    """batch_defer (jitter 0.9): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.19, 0.6175, 1.71, 3.42]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_defer')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_defer_jitter_10(monkeypatch):
    """batch_defer (jitter 1.0): recover on attempt 4 — sleeps [0.2, 0.4, 1.8]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=3)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_defer_jitter_10(monkeypatch):
    """batch_defer (jitter 1.0): recover on attempt 5 — sleeps [0.2, 0.4, 1.8, 3.6]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_defer_jitter_10(monkeypatch):
    """batch_defer (jitter 1.0): exhaustion walk — sleeps [0.2, 0.4, 1.8, 3.6], retry-after 0.25s."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_defer')
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]
    assert caught.value.retry_after == pytest.approx(0.25)


def test_grid_wave_sibling2_defer_jitter_10(monkeypatch):
    """batch_defer (jitter 1.0): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.2, 0.65, 1.8, 3.6]


def test_grid_wave_sibling3_defer_jitter_10(monkeypatch):
    """batch_defer (jitter 1.0): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]


def test_grid_wave_doublearm_defer_jitter_10(monkeypatch):
    """batch_defer (jitter 1.0): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_defer', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_defer') == 'committed'
    assert clock.sleeps == [0.2, 0.65, 1.8, 3.6]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_defer')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_intake_status_jitter_00(monkeypatch):
    """batch_intake_status (jitter 0.0): recover on attempt 4 — sleeps [0.1, 0.2, 0.9]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=3)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_intake_status_jitter_00(monkeypatch):
    """batch_intake_status (jitter 0.0): recover on attempt 5 — sleeps [0.1, 0.2, 0.9, 1.8]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_intake_status_jitter_00(monkeypatch):
    """batch_intake_status (jitter 0.0): exhaustion walk — sleeps [0.1, 0.2, 0.9, 1.8], retry-after 0.125s."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_intake_status', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_intake_status')
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]
    assert caught.value.retry_after == pytest.approx(0.125)


def test_grid_wave_sibling2_intake_status_jitter_00(monkeypatch):
    """batch_intake_status (jitter 0.0): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.1, 0.325, 0.9, 1.8]


def test_grid_wave_sibling3_intake_status_jitter_00(monkeypatch):
    """batch_intake_status (jitter 0.0): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]


def test_grid_wave_doublearm_intake_status_jitter_00(monkeypatch):
    """batch_intake_status (jitter 0.0): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.1, 0.325, 0.9, 1.8]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_intake_status')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_intake_status_jitter_01(monkeypatch):
    """batch_intake_status (jitter 0.1): recover on attempt 4 — sleeps [0.11, 0.22, 0.99]."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=3)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.11, 0.22, 0.99]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_intake_status_jitter_01(monkeypatch):
    """batch_intake_status (jitter 0.1): recover on attempt 5 — sleeps [0.11, 0.22, 0.99, 1.98]."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.11, 0.22, 0.99, 1.98]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_intake_status_jitter_01(monkeypatch):
    """batch_intake_status (jitter 0.1): exhaustion walk — sleeps [0.11, 0.22, 0.99, 1.98], retry-after 0.1375s."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_intake_status', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_intake_status')
    assert clock.sleeps == [0.11, 0.22, 0.99, 1.98]
    assert caught.value.retry_after == pytest.approx(0.1375)


def test_grid_wave_sibling2_intake_status_jitter_01(monkeypatch):
    """batch_intake_status (jitter 0.1): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.11, 0.3575, 0.99, 1.98]


def test_grid_wave_sibling3_intake_status_jitter_01(monkeypatch):
    """batch_intake_status (jitter 0.1): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.11, 0.22, 0.99, 1.98]


def test_grid_wave_doublearm_intake_status_jitter_01(monkeypatch):
    """batch_intake_status (jitter 0.1): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.11, 0.3575, 0.99, 1.98]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_intake_status')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_intake_status_jitter_02(monkeypatch):
    """batch_intake_status (jitter 0.2): recover on attempt 4 — sleeps [0.12, 0.24, 1.08]."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=3)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.12, 0.24, 1.08]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_intake_status_jitter_02(monkeypatch):
    """batch_intake_status (jitter 0.2): recover on attempt 5 — sleeps [0.12, 0.24, 1.08, 2.16]."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.12, 0.24, 1.08, 2.16]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_intake_status_jitter_02(monkeypatch):
    """batch_intake_status (jitter 0.2): exhaustion walk — sleeps [0.12, 0.24, 1.08, 2.16], retry-after 0.15s."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_intake_status', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_intake_status')
    assert clock.sleeps == [0.12, 0.24, 1.08, 2.16]
    assert caught.value.retry_after == pytest.approx(0.15)


def test_grid_wave_sibling2_intake_status_jitter_02(monkeypatch):
    """batch_intake_status (jitter 0.2): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.12, 0.39, 1.08, 2.16]


def test_grid_wave_sibling3_intake_status_jitter_02(monkeypatch):
    """batch_intake_status (jitter 0.2): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.12, 0.24, 1.08, 2.16]


def test_grid_wave_doublearm_intake_status_jitter_02(monkeypatch):
    """batch_intake_status (jitter 0.2): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.12, 0.39, 1.08, 2.16]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_intake_status')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_intake_status_jitter_03(monkeypatch):
    """batch_intake_status (jitter 0.3): recover on attempt 4 — sleeps [0.13, 0.26, 1.17]."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=3)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.13, 0.26, 1.17]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_intake_status_jitter_03(monkeypatch):
    """batch_intake_status (jitter 0.3): recover on attempt 5 — sleeps [0.13, 0.26, 1.17, 2.34]."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.13, 0.26, 1.17, 2.34]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_intake_status_jitter_03(monkeypatch):
    """batch_intake_status (jitter 0.3): exhaustion walk — sleeps [0.13, 0.26, 1.17, 2.34], retry-after 0.1625s."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_intake_status', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_intake_status')
    assert clock.sleeps == [0.13, 0.26, 1.17, 2.34]
    assert caught.value.retry_after == pytest.approx(0.1625)


def test_grid_wave_sibling2_intake_status_jitter_03(monkeypatch):
    """batch_intake_status (jitter 0.3): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.13, 0.4225, 1.17, 2.34]


def test_grid_wave_sibling3_intake_status_jitter_03(monkeypatch):
    """batch_intake_status (jitter 0.3): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.13, 0.26, 1.17, 2.34]


def test_grid_wave_doublearm_intake_status_jitter_03(monkeypatch):
    """batch_intake_status (jitter 0.3): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.13, 0.4225, 1.17, 2.34]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_intake_status')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_intake_status_jitter_04(monkeypatch):
    """batch_intake_status (jitter 0.4): recover on attempt 4 — sleeps [0.14, 0.28, 1.26]."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=3)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.14, 0.28, 1.26]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_intake_status_jitter_04(monkeypatch):
    """batch_intake_status (jitter 0.4): recover on attempt 5 — sleeps [0.14, 0.28, 1.26, 2.52]."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.14, 0.28, 1.26, 2.52]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_intake_status_jitter_04(monkeypatch):
    """batch_intake_status (jitter 0.4): exhaustion walk — sleeps [0.14, 0.28, 1.26, 2.52], retry-after 0.175s."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_intake_status', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_intake_status')
    assert clock.sleeps == [0.14, 0.28, 1.26, 2.52]
    assert caught.value.retry_after == pytest.approx(0.175)


def test_grid_wave_sibling2_intake_status_jitter_04(monkeypatch):
    """batch_intake_status (jitter 0.4): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.14, 0.455, 1.26, 2.52]


def test_grid_wave_sibling3_intake_status_jitter_04(monkeypatch):
    """batch_intake_status (jitter 0.4): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.14, 0.28, 1.26, 2.52]


def test_grid_wave_doublearm_intake_status_jitter_04(monkeypatch):
    """batch_intake_status (jitter 0.4): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.14, 0.455, 1.26, 2.52]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_intake_status')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_intake_status_jitter_05(monkeypatch):
    """batch_intake_status (jitter 0.5): recover on attempt 4 — sleeps [0.15, 0.3, 1.35]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=3)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_intake_status_jitter_05(monkeypatch):
    """batch_intake_status (jitter 0.5): recover on attempt 5 — sleeps [0.15, 0.3, 1.35, 2.7]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_intake_status_jitter_05(monkeypatch):
    """batch_intake_status (jitter 0.5): exhaustion walk — sleeps [0.15, 0.3, 1.35, 2.7], retry-after 0.1875s."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_intake_status', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_intake_status')
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]
    assert caught.value.retry_after == pytest.approx(0.1875)


def test_grid_wave_sibling2_intake_status_jitter_05(monkeypatch):
    """batch_intake_status (jitter 0.5): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.15, 0.4875, 1.35, 2.7]


def test_grid_wave_sibling3_intake_status_jitter_05(monkeypatch):
    """batch_intake_status (jitter 0.5): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]


def test_grid_wave_doublearm_intake_status_jitter_05(monkeypatch):
    """batch_intake_status (jitter 0.5): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.15, 0.4875, 1.35, 2.7]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_intake_status')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_intake_status_jitter_06(monkeypatch):
    """batch_intake_status (jitter 0.6): recover on attempt 4 — sleeps [0.16, 0.32, 1.44]."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=3)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.16, 0.32, 1.44]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_intake_status_jitter_06(monkeypatch):
    """batch_intake_status (jitter 0.6): recover on attempt 5 — sleeps [0.16, 0.32, 1.44, 2.88]."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.16, 0.32, 1.44, 2.88]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_intake_status_jitter_06(monkeypatch):
    """batch_intake_status (jitter 0.6): exhaustion walk — sleeps [0.16, 0.32, 1.44, 2.88], retry-after 0.2s."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_intake_status', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_intake_status')
    assert clock.sleeps == [0.16, 0.32, 1.44, 2.88]
    assert caught.value.retry_after == pytest.approx(0.2)


def test_grid_wave_sibling2_intake_status_jitter_06(monkeypatch):
    """batch_intake_status (jitter 0.6): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.16, 0.52, 1.44, 2.88]


def test_grid_wave_sibling3_intake_status_jitter_06(monkeypatch):
    """batch_intake_status (jitter 0.6): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.16, 0.32, 1.44, 2.88]


def test_grid_wave_doublearm_intake_status_jitter_06(monkeypatch):
    """batch_intake_status (jitter 0.6): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.16, 0.52, 1.44, 2.88]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_intake_status')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_intake_status_jitter_07(monkeypatch):
    """batch_intake_status (jitter 0.7): recover on attempt 4 — sleeps [0.17, 0.34, 1.53]."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=3)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.17, 0.34, 1.53]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_intake_status_jitter_07(monkeypatch):
    """batch_intake_status (jitter 0.7): recover on attempt 5 — sleeps [0.17, 0.34, 1.53, 3.06]."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.17, 0.34, 1.53, 3.06]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_intake_status_jitter_07(monkeypatch):
    """batch_intake_status (jitter 0.7): exhaustion walk — sleeps [0.17, 0.34, 1.53, 3.06], retry-after 0.2125s."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_intake_status', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_intake_status')
    assert clock.sleeps == [0.17, 0.34, 1.53, 3.06]
    assert caught.value.retry_after == pytest.approx(0.2125)


def test_grid_wave_sibling2_intake_status_jitter_07(monkeypatch):
    """batch_intake_status (jitter 0.7): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.17, 0.5525, 1.53, 3.06]


def test_grid_wave_sibling3_intake_status_jitter_07(monkeypatch):
    """batch_intake_status (jitter 0.7): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.17, 0.34, 1.53, 3.06]


def test_grid_wave_doublearm_intake_status_jitter_07(monkeypatch):
    """batch_intake_status (jitter 0.7): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.17, 0.5525, 1.53, 3.06]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_intake_status')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_intake_status_jitter_08(monkeypatch):
    """batch_intake_status (jitter 0.8): recover on attempt 4 — sleeps [0.18, 0.36, 1.62]."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=3)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.18, 0.36, 1.62]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_intake_status_jitter_08(monkeypatch):
    """batch_intake_status (jitter 0.8): recover on attempt 5 — sleeps [0.18, 0.36, 1.62, 3.24]."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.18, 0.36, 1.62, 3.24]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_intake_status_jitter_08(monkeypatch):
    """batch_intake_status (jitter 0.8): exhaustion walk — sleeps [0.18, 0.36, 1.62, 3.24], retry-after 0.225s."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_intake_status', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_intake_status')
    assert clock.sleeps == [0.18, 0.36, 1.62, 3.24]
    assert caught.value.retry_after == pytest.approx(0.225)


def test_grid_wave_sibling2_intake_status_jitter_08(monkeypatch):
    """batch_intake_status (jitter 0.8): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.18, 0.585, 1.62, 3.24]


def test_grid_wave_sibling3_intake_status_jitter_08(monkeypatch):
    """batch_intake_status (jitter 0.8): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.18, 0.36, 1.62, 3.24]


def test_grid_wave_doublearm_intake_status_jitter_08(monkeypatch):
    """batch_intake_status (jitter 0.8): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.18, 0.585, 1.62, 3.24]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_intake_status')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_intake_status_jitter_09(monkeypatch):
    """batch_intake_status (jitter 0.9): recover on attempt 4 — sleeps [0.19, 0.38, 1.71]."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=3)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.19, 0.38, 1.71]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_intake_status_jitter_09(monkeypatch):
    """batch_intake_status (jitter 0.9): recover on attempt 5 — sleeps [0.19, 0.38, 1.71, 3.42]."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.19, 0.38, 1.71, 3.42]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_intake_status_jitter_09(monkeypatch):
    """batch_intake_status (jitter 0.9): exhaustion walk — sleeps [0.19, 0.38, 1.71, 3.42], retry-after 0.2375s."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_intake_status', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_intake_status')
    assert clock.sleeps == [0.19, 0.38, 1.71, 3.42]
    assert caught.value.retry_after == pytest.approx(0.2375)


def test_grid_wave_sibling2_intake_status_jitter_09(monkeypatch):
    """batch_intake_status (jitter 0.9): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.19, 0.6175, 1.71, 3.42]


def test_grid_wave_sibling3_intake_status_jitter_09(monkeypatch):
    """batch_intake_status (jitter 0.9): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.19, 0.38, 1.71, 3.42]


def test_grid_wave_doublearm_intake_status_jitter_09(monkeypatch):
    """batch_intake_status (jitter 0.9): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.19, 0.6175, 1.71, 3.42]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_intake_status')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_intake_status_jitter_10(monkeypatch):
    """batch_intake_status (jitter 1.0): recover on attempt 4 — sleeps [0.2, 0.4, 1.8]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=3)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_intake_status_jitter_10(monkeypatch):
    """batch_intake_status (jitter 1.0): recover on attempt 5 — sleeps [0.2, 0.4, 1.8, 3.6]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_intake_status_jitter_10(monkeypatch):
    """batch_intake_status (jitter 1.0): exhaustion walk — sleeps [0.2, 0.4, 1.8, 3.6], retry-after 0.25s."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_intake_status', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_intake_status')
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]
    assert caught.value.retry_after == pytest.approx(0.25)


def test_grid_wave_sibling2_intake_status_jitter_10(monkeypatch):
    """batch_intake_status (jitter 1.0): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.2, 0.65, 1.8, 3.6]


def test_grid_wave_sibling3_intake_status_jitter_10(monkeypatch):
    """batch_intake_status (jitter 1.0): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]


def test_grid_wave_doublearm_intake_status_jitter_10(monkeypatch):
    """batch_intake_status (jitter 1.0): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_intake_status', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_intake_status') == 'committed'
    assert clock.sleeps == [0.2, 0.65, 1.8, 3.6]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_intake_status')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_seal_register_jitter_00(monkeypatch):
    """batch_seal_register (jitter 0.0): recover on attempt 4 — sleeps [0.1, 0.2, 0.9]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=3)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_seal_register_jitter_00(monkeypatch):
    """batch_seal_register (jitter 0.0): recover on attempt 5 — sleeps [0.1, 0.2, 0.9, 1.8]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_seal_register_jitter_00(monkeypatch):
    """batch_seal_register (jitter 0.0): exhaustion walk — sleeps [0.1, 0.2, 0.9, 1.8], retry-after 0.125s."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_seal_register', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_seal_register')
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]
    assert caught.value.retry_after == pytest.approx(0.125)


def test_grid_wave_sibling2_seal_register_jitter_00(monkeypatch):
    """batch_seal_register (jitter 0.0): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.1, 0.325, 0.9, 1.8]


def test_grid_wave_sibling3_seal_register_jitter_00(monkeypatch):
    """batch_seal_register (jitter 0.0): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]


def test_grid_wave_doublearm_seal_register_jitter_00(monkeypatch):
    """batch_seal_register (jitter 0.0): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.1, 0.325, 0.9, 1.8]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_seal_register')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_seal_register_jitter_01(monkeypatch):
    """batch_seal_register (jitter 0.1): recover on attempt 4 — sleeps [0.11, 0.22, 0.99]."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=3)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.11, 0.22, 0.99]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_seal_register_jitter_01(monkeypatch):
    """batch_seal_register (jitter 0.1): recover on attempt 5 — sleeps [0.11, 0.22, 0.99, 1.98]."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.11, 0.22, 0.99, 1.98]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_seal_register_jitter_01(monkeypatch):
    """batch_seal_register (jitter 0.1): exhaustion walk — sleeps [0.11, 0.22, 0.99, 1.98], retry-after 0.1375s."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_seal_register', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_seal_register')
    assert clock.sleeps == [0.11, 0.22, 0.99, 1.98]
    assert caught.value.retry_after == pytest.approx(0.1375)


def test_grid_wave_sibling2_seal_register_jitter_01(monkeypatch):
    """batch_seal_register (jitter 0.1): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.11, 0.3575, 0.99, 1.98]


def test_grid_wave_sibling3_seal_register_jitter_01(monkeypatch):
    """batch_seal_register (jitter 0.1): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.11, 0.22, 0.99, 1.98]


def test_grid_wave_doublearm_seal_register_jitter_01(monkeypatch):
    """batch_seal_register (jitter 0.1): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.11, 0.3575, 0.99, 1.98]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_seal_register')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_seal_register_jitter_02(monkeypatch):
    """batch_seal_register (jitter 0.2): recover on attempt 4 — sleeps [0.12, 0.24, 1.08]."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=3)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.12, 0.24, 1.08]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_seal_register_jitter_02(monkeypatch):
    """batch_seal_register (jitter 0.2): recover on attempt 5 — sleeps [0.12, 0.24, 1.08, 2.16]."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.12, 0.24, 1.08, 2.16]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_seal_register_jitter_02(monkeypatch):
    """batch_seal_register (jitter 0.2): exhaustion walk — sleeps [0.12, 0.24, 1.08, 2.16], retry-after 0.15s."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_seal_register', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_seal_register')
    assert clock.sleeps == [0.12, 0.24, 1.08, 2.16]
    assert caught.value.retry_after == pytest.approx(0.15)


def test_grid_wave_sibling2_seal_register_jitter_02(monkeypatch):
    """batch_seal_register (jitter 0.2): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.12, 0.39, 1.08, 2.16]


def test_grid_wave_sibling3_seal_register_jitter_02(monkeypatch):
    """batch_seal_register (jitter 0.2): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.12, 0.24, 1.08, 2.16]


def test_grid_wave_doublearm_seal_register_jitter_02(monkeypatch):
    """batch_seal_register (jitter 0.2): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.12, 0.39, 1.08, 2.16]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_seal_register')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_seal_register_jitter_03(monkeypatch):
    """batch_seal_register (jitter 0.3): recover on attempt 4 — sleeps [0.13, 0.26, 1.17]."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=3)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.13, 0.26, 1.17]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_seal_register_jitter_03(monkeypatch):
    """batch_seal_register (jitter 0.3): recover on attempt 5 — sleeps [0.13, 0.26, 1.17, 2.34]."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.13, 0.26, 1.17, 2.34]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_seal_register_jitter_03(monkeypatch):
    """batch_seal_register (jitter 0.3): exhaustion walk — sleeps [0.13, 0.26, 1.17, 2.34], retry-after 0.1625s."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_seal_register', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_seal_register')
    assert clock.sleeps == [0.13, 0.26, 1.17, 2.34]
    assert caught.value.retry_after == pytest.approx(0.1625)


def test_grid_wave_sibling2_seal_register_jitter_03(monkeypatch):
    """batch_seal_register (jitter 0.3): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.13, 0.4225, 1.17, 2.34]


def test_grid_wave_sibling3_seal_register_jitter_03(monkeypatch):
    """batch_seal_register (jitter 0.3): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.13, 0.26, 1.17, 2.34]


def test_grid_wave_doublearm_seal_register_jitter_03(monkeypatch):
    """batch_seal_register (jitter 0.3): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.13, 0.4225, 1.17, 2.34]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_seal_register')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_seal_register_jitter_04(monkeypatch):
    """batch_seal_register (jitter 0.4): recover on attempt 4 — sleeps [0.14, 0.28, 1.26]."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=3)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.14, 0.28, 1.26]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_seal_register_jitter_04(monkeypatch):
    """batch_seal_register (jitter 0.4): recover on attempt 5 — sleeps [0.14, 0.28, 1.26, 2.52]."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.14, 0.28, 1.26, 2.52]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_seal_register_jitter_04(monkeypatch):
    """batch_seal_register (jitter 0.4): exhaustion walk — sleeps [0.14, 0.28, 1.26, 2.52], retry-after 0.175s."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_seal_register', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_seal_register')
    assert clock.sleeps == [0.14, 0.28, 1.26, 2.52]
    assert caught.value.retry_after == pytest.approx(0.175)


def test_grid_wave_sibling2_seal_register_jitter_04(monkeypatch):
    """batch_seal_register (jitter 0.4): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.14, 0.455, 1.26, 2.52]


def test_grid_wave_sibling3_seal_register_jitter_04(monkeypatch):
    """batch_seal_register (jitter 0.4): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.14, 0.28, 1.26, 2.52]


def test_grid_wave_doublearm_seal_register_jitter_04(monkeypatch):
    """batch_seal_register (jitter 0.4): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.14, 0.455, 1.26, 2.52]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_seal_register')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_seal_register_jitter_05(monkeypatch):
    """batch_seal_register (jitter 0.5): recover on attempt 4 — sleeps [0.15, 0.3, 1.35]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=3)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_seal_register_jitter_05(monkeypatch):
    """batch_seal_register (jitter 0.5): recover on attempt 5 — sleeps [0.15, 0.3, 1.35, 2.7]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_seal_register_jitter_05(monkeypatch):
    """batch_seal_register (jitter 0.5): exhaustion walk — sleeps [0.15, 0.3, 1.35, 2.7], retry-after 0.1875s."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_seal_register', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_seal_register')
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]
    assert caught.value.retry_after == pytest.approx(0.1875)


def test_grid_wave_sibling2_seal_register_jitter_05(monkeypatch):
    """batch_seal_register (jitter 0.5): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.15, 0.4875, 1.35, 2.7]


def test_grid_wave_sibling3_seal_register_jitter_05(monkeypatch):
    """batch_seal_register (jitter 0.5): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]


def test_grid_wave_doublearm_seal_register_jitter_05(monkeypatch):
    """batch_seal_register (jitter 0.5): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.15, 0.4875, 1.35, 2.7]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_seal_register')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_seal_register_jitter_06(monkeypatch):
    """batch_seal_register (jitter 0.6): recover on attempt 4 — sleeps [0.16, 0.32, 1.44]."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=3)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.16, 0.32, 1.44]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_seal_register_jitter_06(monkeypatch):
    """batch_seal_register (jitter 0.6): recover on attempt 5 — sleeps [0.16, 0.32, 1.44, 2.88]."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.16, 0.32, 1.44, 2.88]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_seal_register_jitter_06(monkeypatch):
    """batch_seal_register (jitter 0.6): exhaustion walk — sleeps [0.16, 0.32, 1.44, 2.88], retry-after 0.2s."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_seal_register', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_seal_register')
    assert clock.sleeps == [0.16, 0.32, 1.44, 2.88]
    assert caught.value.retry_after == pytest.approx(0.2)


def test_grid_wave_sibling2_seal_register_jitter_06(monkeypatch):
    """batch_seal_register (jitter 0.6): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.16, 0.52, 1.44, 2.88]


def test_grid_wave_sibling3_seal_register_jitter_06(monkeypatch):
    """batch_seal_register (jitter 0.6): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.16, 0.32, 1.44, 2.88]


def test_grid_wave_doublearm_seal_register_jitter_06(monkeypatch):
    """batch_seal_register (jitter 0.6): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.16, 0.52, 1.44, 2.88]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_seal_register')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_seal_register_jitter_07(monkeypatch):
    """batch_seal_register (jitter 0.7): recover on attempt 4 — sleeps [0.17, 0.34, 1.53]."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=3)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.17, 0.34, 1.53]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_seal_register_jitter_07(monkeypatch):
    """batch_seal_register (jitter 0.7): recover on attempt 5 — sleeps [0.17, 0.34, 1.53, 3.06]."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.17, 0.34, 1.53, 3.06]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_seal_register_jitter_07(monkeypatch):
    """batch_seal_register (jitter 0.7): exhaustion walk — sleeps [0.17, 0.34, 1.53, 3.06], retry-after 0.2125s."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_seal_register', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_seal_register')
    assert clock.sleeps == [0.17, 0.34, 1.53, 3.06]
    assert caught.value.retry_after == pytest.approx(0.2125)


def test_grid_wave_sibling2_seal_register_jitter_07(monkeypatch):
    """batch_seal_register (jitter 0.7): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.17, 0.5525, 1.53, 3.06]


def test_grid_wave_sibling3_seal_register_jitter_07(monkeypatch):
    """batch_seal_register (jitter 0.7): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.17, 0.34, 1.53, 3.06]


def test_grid_wave_doublearm_seal_register_jitter_07(monkeypatch):
    """batch_seal_register (jitter 0.7): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.17, 0.5525, 1.53, 3.06]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_seal_register')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_seal_register_jitter_08(monkeypatch):
    """batch_seal_register (jitter 0.8): recover on attempt 4 — sleeps [0.18, 0.36, 1.62]."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=3)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.18, 0.36, 1.62]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_seal_register_jitter_08(monkeypatch):
    """batch_seal_register (jitter 0.8): recover on attempt 5 — sleeps [0.18, 0.36, 1.62, 3.24]."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.18, 0.36, 1.62, 3.24]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_seal_register_jitter_08(monkeypatch):
    """batch_seal_register (jitter 0.8): exhaustion walk — sleeps [0.18, 0.36, 1.62, 3.24], retry-after 0.225s."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_seal_register', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_seal_register')
    assert clock.sleeps == [0.18, 0.36, 1.62, 3.24]
    assert caught.value.retry_after == pytest.approx(0.225)


def test_grid_wave_sibling2_seal_register_jitter_08(monkeypatch):
    """batch_seal_register (jitter 0.8): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.18, 0.585, 1.62, 3.24]


def test_grid_wave_sibling3_seal_register_jitter_08(monkeypatch):
    """batch_seal_register (jitter 0.8): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.18, 0.36, 1.62, 3.24]


def test_grid_wave_doublearm_seal_register_jitter_08(monkeypatch):
    """batch_seal_register (jitter 0.8): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.18, 0.585, 1.62, 3.24]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_seal_register')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_seal_register_jitter_09(monkeypatch):
    """batch_seal_register (jitter 0.9): recover on attempt 4 — sleeps [0.19, 0.38, 1.71]."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=3)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.19, 0.38, 1.71]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_seal_register_jitter_09(monkeypatch):
    """batch_seal_register (jitter 0.9): recover on attempt 5 — sleeps [0.19, 0.38, 1.71, 3.42]."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.19, 0.38, 1.71, 3.42]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_seal_register_jitter_09(monkeypatch):
    """batch_seal_register (jitter 0.9): exhaustion walk — sleeps [0.19, 0.38, 1.71, 3.42], retry-after 0.2375s."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_seal_register', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_seal_register')
    assert clock.sleeps == [0.19, 0.38, 1.71, 3.42]
    assert caught.value.retry_after == pytest.approx(0.2375)


def test_grid_wave_sibling2_seal_register_jitter_09(monkeypatch):
    """batch_seal_register (jitter 0.9): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.19, 0.6175, 1.71, 3.42]


def test_grid_wave_sibling3_seal_register_jitter_09(monkeypatch):
    """batch_seal_register (jitter 0.9): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.19, 0.38, 1.71, 3.42]


def test_grid_wave_doublearm_seal_register_jitter_09(monkeypatch):
    """batch_seal_register (jitter 0.9): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.19, 0.6175, 1.71, 3.42]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_seal_register')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_seal_register_jitter_10(monkeypatch):
    """batch_seal_register (jitter 1.0): recover on attempt 4 — sleeps [0.2, 0.4, 1.8]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=3)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_seal_register_jitter_10(monkeypatch):
    """batch_seal_register (jitter 1.0): recover on attempt 5 — sleeps [0.2, 0.4, 1.8, 3.6]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_seal_register_jitter_10(monkeypatch):
    """batch_seal_register (jitter 1.0): exhaustion walk — sleeps [0.2, 0.4, 1.8, 3.6], retry-after 0.25s."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_seal_register', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_seal_register')
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]
    assert caught.value.retry_after == pytest.approx(0.25)


def test_grid_wave_sibling2_seal_register_jitter_10(monkeypatch):
    """batch_seal_register (jitter 1.0): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.2, 0.65, 1.8, 3.6]


def test_grid_wave_sibling3_seal_register_jitter_10(monkeypatch):
    """batch_seal_register (jitter 1.0): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]


def test_grid_wave_doublearm_seal_register_jitter_10(monkeypatch):
    """batch_seal_register (jitter 1.0): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_seal_register', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_seal_register') == 'committed'
    assert clock.sleeps == [0.2, 0.65, 1.8, 3.6]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_seal_register')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_release_jitter_00(monkeypatch):
    """batch_release (jitter 0.0): recover on attempt 4 — sleeps [0.1, 0.2, 0.9]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=3)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_release_jitter_00(monkeypatch):
    """batch_release (jitter 0.0): recover on attempt 5 — sleeps [0.1, 0.2, 0.9, 1.8]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_release_jitter_00(monkeypatch):
    """batch_release (jitter 0.0): exhaustion walk — sleeps [0.1, 0.2, 0.9, 1.8], retry-after 0.125s."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_release')
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]
    assert caught.value.retry_after == pytest.approx(0.125)


def test_grid_wave_sibling2_release_jitter_00(monkeypatch):
    """batch_release (jitter 0.0): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.1, 0.325, 0.9, 1.8]


def test_grid_wave_sibling3_release_jitter_00(monkeypatch):
    """batch_release (jitter 0.0): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]


def test_grid_wave_doublearm_release_jitter_00(monkeypatch):
    """batch_release (jitter 0.0): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.1, 0.325, 0.9, 1.8]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_release')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_release_jitter_01(monkeypatch):
    """batch_release (jitter 0.1): recover on attempt 4 — sleeps [0.11, 0.22, 0.99]."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=3)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.11, 0.22, 0.99]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_release_jitter_01(monkeypatch):
    """batch_release (jitter 0.1): recover on attempt 5 — sleeps [0.11, 0.22, 0.99, 1.98]."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.11, 0.22, 0.99, 1.98]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_release_jitter_01(monkeypatch):
    """batch_release (jitter 0.1): exhaustion walk — sleeps [0.11, 0.22, 0.99, 1.98], retry-after 0.1375s."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_release')
    assert clock.sleeps == [0.11, 0.22, 0.99, 1.98]
    assert caught.value.retry_after == pytest.approx(0.1375)


def test_grid_wave_sibling2_release_jitter_01(monkeypatch):
    """batch_release (jitter 0.1): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.11, 0.3575, 0.99, 1.98]


def test_grid_wave_sibling3_release_jitter_01(monkeypatch):
    """batch_release (jitter 0.1): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.11, 0.22, 0.99, 1.98]


def test_grid_wave_doublearm_release_jitter_01(monkeypatch):
    """batch_release (jitter 0.1): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.11, 0.3575, 0.99, 1.98]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_release')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_release_jitter_02(monkeypatch):
    """batch_release (jitter 0.2): recover on attempt 4 — sleeps [0.12, 0.24, 1.08]."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=3)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.12, 0.24, 1.08]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_release_jitter_02(monkeypatch):
    """batch_release (jitter 0.2): recover on attempt 5 — sleeps [0.12, 0.24, 1.08, 2.16]."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.12, 0.24, 1.08, 2.16]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_release_jitter_02(monkeypatch):
    """batch_release (jitter 0.2): exhaustion walk — sleeps [0.12, 0.24, 1.08, 2.16], retry-after 0.15s."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_release')
    assert clock.sleeps == [0.12, 0.24, 1.08, 2.16]
    assert caught.value.retry_after == pytest.approx(0.15)


def test_grid_wave_sibling2_release_jitter_02(monkeypatch):
    """batch_release (jitter 0.2): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.12, 0.39, 1.08, 2.16]


def test_grid_wave_sibling3_release_jitter_02(monkeypatch):
    """batch_release (jitter 0.2): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.12, 0.24, 1.08, 2.16]


def test_grid_wave_doublearm_release_jitter_02(monkeypatch):
    """batch_release (jitter 0.2): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.12, 0.39, 1.08, 2.16]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_release')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_release_jitter_03(monkeypatch):
    """batch_release (jitter 0.3): recover on attempt 4 — sleeps [0.13, 0.26, 1.17]."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=3)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.13, 0.26, 1.17]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_release_jitter_03(monkeypatch):
    """batch_release (jitter 0.3): recover on attempt 5 — sleeps [0.13, 0.26, 1.17, 2.34]."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.13, 0.26, 1.17, 2.34]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_release_jitter_03(monkeypatch):
    """batch_release (jitter 0.3): exhaustion walk — sleeps [0.13, 0.26, 1.17, 2.34], retry-after 0.1625s."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_release')
    assert clock.sleeps == [0.13, 0.26, 1.17, 2.34]
    assert caught.value.retry_after == pytest.approx(0.1625)


def test_grid_wave_sibling2_release_jitter_03(monkeypatch):
    """batch_release (jitter 0.3): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.13, 0.4225, 1.17, 2.34]


def test_grid_wave_sibling3_release_jitter_03(monkeypatch):
    """batch_release (jitter 0.3): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.13, 0.26, 1.17, 2.34]


def test_grid_wave_doublearm_release_jitter_03(monkeypatch):
    """batch_release (jitter 0.3): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.13, 0.4225, 1.17, 2.34]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_release')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_release_jitter_04(monkeypatch):
    """batch_release (jitter 0.4): recover on attempt 4 — sleeps [0.14, 0.28, 1.26]."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=3)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.14, 0.28, 1.26]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_release_jitter_04(monkeypatch):
    """batch_release (jitter 0.4): recover on attempt 5 — sleeps [0.14, 0.28, 1.26, 2.52]."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.14, 0.28, 1.26, 2.52]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_release_jitter_04(monkeypatch):
    """batch_release (jitter 0.4): exhaustion walk — sleeps [0.14, 0.28, 1.26, 2.52], retry-after 0.175s."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_release')
    assert clock.sleeps == [0.14, 0.28, 1.26, 2.52]
    assert caught.value.retry_after == pytest.approx(0.175)


def test_grid_wave_sibling2_release_jitter_04(monkeypatch):
    """batch_release (jitter 0.4): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.14, 0.455, 1.26, 2.52]


def test_grid_wave_sibling3_release_jitter_04(monkeypatch):
    """batch_release (jitter 0.4): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.14, 0.28, 1.26, 2.52]


def test_grid_wave_doublearm_release_jitter_04(monkeypatch):
    """batch_release (jitter 0.4): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.14, 0.455, 1.26, 2.52]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_release')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_release_jitter_05(monkeypatch):
    """batch_release (jitter 0.5): recover on attempt 4 — sleeps [0.15, 0.3, 1.35]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=3)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_release_jitter_05(monkeypatch):
    """batch_release (jitter 0.5): recover on attempt 5 — sleeps [0.15, 0.3, 1.35, 2.7]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_release_jitter_05(monkeypatch):
    """batch_release (jitter 0.5): exhaustion walk — sleeps [0.15, 0.3, 1.35, 2.7], retry-after 0.1875s."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_release')
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]
    assert caught.value.retry_after == pytest.approx(0.1875)


def test_grid_wave_sibling2_release_jitter_05(monkeypatch):
    """batch_release (jitter 0.5): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.15, 0.4875, 1.35, 2.7]


def test_grid_wave_sibling3_release_jitter_05(monkeypatch):
    """batch_release (jitter 0.5): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]


def test_grid_wave_doublearm_release_jitter_05(monkeypatch):
    """batch_release (jitter 0.5): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.15, 0.4875, 1.35, 2.7]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_release')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_release_jitter_06(monkeypatch):
    """batch_release (jitter 0.6): recover on attempt 4 — sleeps [0.16, 0.32, 1.44]."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=3)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.16, 0.32, 1.44]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_release_jitter_06(monkeypatch):
    """batch_release (jitter 0.6): recover on attempt 5 — sleeps [0.16, 0.32, 1.44, 2.88]."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.16, 0.32, 1.44, 2.88]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_release_jitter_06(monkeypatch):
    """batch_release (jitter 0.6): exhaustion walk — sleeps [0.16, 0.32, 1.44, 2.88], retry-after 0.2s."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_release')
    assert clock.sleeps == [0.16, 0.32, 1.44, 2.88]
    assert caught.value.retry_after == pytest.approx(0.2)


def test_grid_wave_sibling2_release_jitter_06(monkeypatch):
    """batch_release (jitter 0.6): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.16, 0.52, 1.44, 2.88]


def test_grid_wave_sibling3_release_jitter_06(monkeypatch):
    """batch_release (jitter 0.6): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.16, 0.32, 1.44, 2.88]


def test_grid_wave_doublearm_release_jitter_06(monkeypatch):
    """batch_release (jitter 0.6): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.16, 0.52, 1.44, 2.88]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_release')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_release_jitter_07(monkeypatch):
    """batch_release (jitter 0.7): recover on attempt 4 — sleeps [0.17, 0.34, 1.53]."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=3)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.17, 0.34, 1.53]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_release_jitter_07(monkeypatch):
    """batch_release (jitter 0.7): recover on attempt 5 — sleeps [0.17, 0.34, 1.53, 3.06]."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.17, 0.34, 1.53, 3.06]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_release_jitter_07(monkeypatch):
    """batch_release (jitter 0.7): exhaustion walk — sleeps [0.17, 0.34, 1.53, 3.06], retry-after 0.2125s."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_release')
    assert clock.sleeps == [0.17, 0.34, 1.53, 3.06]
    assert caught.value.retry_after == pytest.approx(0.2125)


def test_grid_wave_sibling2_release_jitter_07(monkeypatch):
    """batch_release (jitter 0.7): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.17, 0.5525, 1.53, 3.06]


def test_grid_wave_sibling3_release_jitter_07(monkeypatch):
    """batch_release (jitter 0.7): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.17, 0.34, 1.53, 3.06]


def test_grid_wave_doublearm_release_jitter_07(monkeypatch):
    """batch_release (jitter 0.7): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.17, 0.5525, 1.53, 3.06]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_release')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_release_jitter_08(monkeypatch):
    """batch_release (jitter 0.8): recover on attempt 4 — sleeps [0.18, 0.36, 1.62]."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=3)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.18, 0.36, 1.62]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_release_jitter_08(monkeypatch):
    """batch_release (jitter 0.8): recover on attempt 5 — sleeps [0.18, 0.36, 1.62, 3.24]."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.18, 0.36, 1.62, 3.24]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_release_jitter_08(monkeypatch):
    """batch_release (jitter 0.8): exhaustion walk — sleeps [0.18, 0.36, 1.62, 3.24], retry-after 0.225s."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_release')
    assert clock.sleeps == [0.18, 0.36, 1.62, 3.24]
    assert caught.value.retry_after == pytest.approx(0.225)


def test_grid_wave_sibling2_release_jitter_08(monkeypatch):
    """batch_release (jitter 0.8): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.18, 0.585, 1.62, 3.24]


def test_grid_wave_sibling3_release_jitter_08(monkeypatch):
    """batch_release (jitter 0.8): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.18, 0.36, 1.62, 3.24]


def test_grid_wave_doublearm_release_jitter_08(monkeypatch):
    """batch_release (jitter 0.8): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.18, 0.585, 1.62, 3.24]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_release')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_release_jitter_09(monkeypatch):
    """batch_release (jitter 0.9): recover on attempt 4 — sleeps [0.19, 0.38, 1.71]."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=3)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.19, 0.38, 1.71]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_release_jitter_09(monkeypatch):
    """batch_release (jitter 0.9): recover on attempt 5 — sleeps [0.19, 0.38, 1.71, 3.42]."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.19, 0.38, 1.71, 3.42]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_release_jitter_09(monkeypatch):
    """batch_release (jitter 0.9): exhaustion walk — sleeps [0.19, 0.38, 1.71, 3.42], retry-after 0.2375s."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_release')
    assert clock.sleeps == [0.19, 0.38, 1.71, 3.42]
    assert caught.value.retry_after == pytest.approx(0.2375)


def test_grid_wave_sibling2_release_jitter_09(monkeypatch):
    """batch_release (jitter 0.9): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.19, 0.6175, 1.71, 3.42]


def test_grid_wave_sibling3_release_jitter_09(monkeypatch):
    """batch_release (jitter 0.9): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.19, 0.38, 1.71, 3.42]


def test_grid_wave_doublearm_release_jitter_09(monkeypatch):
    """batch_release (jitter 0.9): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.19, 0.6175, 1.71, 3.42]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_release')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_release_jitter_10(monkeypatch):
    """batch_release (jitter 1.0): recover on attempt 4 — sleeps [0.2, 0.4, 1.8]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=3)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_release_jitter_10(monkeypatch):
    """batch_release (jitter 1.0): recover on attempt 5 — sleeps [0.2, 0.4, 1.8, 3.6]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_release_jitter_10(monkeypatch):
    """batch_release (jitter 1.0): exhaustion walk — sleeps [0.2, 0.4, 1.8, 3.6], retry-after 0.25s."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_release')
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]
    assert caught.value.retry_after == pytest.approx(0.25)


def test_grid_wave_sibling2_release_jitter_10(monkeypatch):
    """batch_release (jitter 1.0): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.2, 0.65, 1.8, 3.6]


def test_grid_wave_sibling3_release_jitter_10(monkeypatch):
    """batch_release (jitter 1.0): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]


def test_grid_wave_doublearm_release_jitter_10(monkeypatch):
    """batch_release (jitter 1.0): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_release', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_release') == 'committed'
    assert clock.sleeps == [0.2, 0.65, 1.8, 3.6]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_release')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_redrive_jitter_00(monkeypatch):
    """batch_redrive (jitter 0.0): recover on attempt 4 — sleeps [0.1, 0.2, 0.9]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=3)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_redrive_jitter_00(monkeypatch):
    """batch_redrive (jitter 0.0): recover on attempt 5 — sleeps [0.1, 0.2, 0.9, 1.8]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_redrive_jitter_00(monkeypatch):
    """batch_redrive (jitter 0.0): exhaustion walk — sleeps [0.1, 0.2, 0.9, 1.8], retry-after 0.125s."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_redrive')
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]
    assert caught.value.retry_after == pytest.approx(0.125)


def test_grid_wave_sibling2_redrive_jitter_00(monkeypatch):
    """batch_redrive (jitter 0.0): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.1, 0.325, 0.9, 1.8]


def test_grid_wave_sibling3_redrive_jitter_00(monkeypatch):
    """batch_redrive (jitter 0.0): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]


def test_grid_wave_doublearm_redrive_jitter_00(monkeypatch):
    """batch_redrive (jitter 0.0): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.1, 0.325, 0.9, 1.8]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_redrive')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_redrive_jitter_01(monkeypatch):
    """batch_redrive (jitter 0.1): recover on attempt 4 — sleeps [0.11, 0.22, 0.99]."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=3)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.11, 0.22, 0.99]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_redrive_jitter_01(monkeypatch):
    """batch_redrive (jitter 0.1): recover on attempt 5 — sleeps [0.11, 0.22, 0.99, 1.98]."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.11, 0.22, 0.99, 1.98]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_redrive_jitter_01(monkeypatch):
    """batch_redrive (jitter 0.1): exhaustion walk — sleeps [0.11, 0.22, 0.99, 1.98], retry-after 0.1375s."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_redrive')
    assert clock.sleeps == [0.11, 0.22, 0.99, 1.98]
    assert caught.value.retry_after == pytest.approx(0.1375)


def test_grid_wave_sibling2_redrive_jitter_01(monkeypatch):
    """batch_redrive (jitter 0.1): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.11, 0.3575, 0.99, 1.98]


def test_grid_wave_sibling3_redrive_jitter_01(monkeypatch):
    """batch_redrive (jitter 0.1): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.11, 0.22, 0.99, 1.98]


def test_grid_wave_doublearm_redrive_jitter_01(monkeypatch):
    """batch_redrive (jitter 0.1): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.11, 0.3575, 0.99, 1.98]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_redrive')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_redrive_jitter_02(monkeypatch):
    """batch_redrive (jitter 0.2): recover on attempt 4 — sleeps [0.12, 0.24, 1.08]."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=3)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.12, 0.24, 1.08]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_redrive_jitter_02(monkeypatch):
    """batch_redrive (jitter 0.2): recover on attempt 5 — sleeps [0.12, 0.24, 1.08, 2.16]."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.12, 0.24, 1.08, 2.16]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_redrive_jitter_02(monkeypatch):
    """batch_redrive (jitter 0.2): exhaustion walk — sleeps [0.12, 0.24, 1.08, 2.16], retry-after 0.15s."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_redrive')
    assert clock.sleeps == [0.12, 0.24, 1.08, 2.16]
    assert caught.value.retry_after == pytest.approx(0.15)


def test_grid_wave_sibling2_redrive_jitter_02(monkeypatch):
    """batch_redrive (jitter 0.2): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.12, 0.39, 1.08, 2.16]


def test_grid_wave_sibling3_redrive_jitter_02(monkeypatch):
    """batch_redrive (jitter 0.2): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.12, 0.24, 1.08, 2.16]


def test_grid_wave_doublearm_redrive_jitter_02(monkeypatch):
    """batch_redrive (jitter 0.2): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.12, 0.39, 1.08, 2.16]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_redrive')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_redrive_jitter_03(monkeypatch):
    """batch_redrive (jitter 0.3): recover on attempt 4 — sleeps [0.13, 0.26, 1.17]."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=3)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.13, 0.26, 1.17]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_redrive_jitter_03(monkeypatch):
    """batch_redrive (jitter 0.3): recover on attempt 5 — sleeps [0.13, 0.26, 1.17, 2.34]."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.13, 0.26, 1.17, 2.34]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_redrive_jitter_03(monkeypatch):
    """batch_redrive (jitter 0.3): exhaustion walk — sleeps [0.13, 0.26, 1.17, 2.34], retry-after 0.1625s."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_redrive')
    assert clock.sleeps == [0.13, 0.26, 1.17, 2.34]
    assert caught.value.retry_after == pytest.approx(0.1625)


def test_grid_wave_sibling2_redrive_jitter_03(monkeypatch):
    """batch_redrive (jitter 0.3): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.13, 0.4225, 1.17, 2.34]


def test_grid_wave_sibling3_redrive_jitter_03(monkeypatch):
    """batch_redrive (jitter 0.3): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.13, 0.26, 1.17, 2.34]


def test_grid_wave_doublearm_redrive_jitter_03(monkeypatch):
    """batch_redrive (jitter 0.3): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.13, 0.4225, 1.17, 2.34]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_redrive')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_redrive_jitter_04(monkeypatch):
    """batch_redrive (jitter 0.4): recover on attempt 4 — sleeps [0.14, 0.28, 1.26]."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=3)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.14, 0.28, 1.26]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_redrive_jitter_04(monkeypatch):
    """batch_redrive (jitter 0.4): recover on attempt 5 — sleeps [0.14, 0.28, 1.26, 2.52]."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.14, 0.28, 1.26, 2.52]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_redrive_jitter_04(monkeypatch):
    """batch_redrive (jitter 0.4): exhaustion walk — sleeps [0.14, 0.28, 1.26, 2.52], retry-after 0.175s."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_redrive')
    assert clock.sleeps == [0.14, 0.28, 1.26, 2.52]
    assert caught.value.retry_after == pytest.approx(0.175)


def test_grid_wave_sibling2_redrive_jitter_04(monkeypatch):
    """batch_redrive (jitter 0.4): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.14, 0.455, 1.26, 2.52]


def test_grid_wave_sibling3_redrive_jitter_04(monkeypatch):
    """batch_redrive (jitter 0.4): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.14, 0.28, 1.26, 2.52]


def test_grid_wave_doublearm_redrive_jitter_04(monkeypatch):
    """batch_redrive (jitter 0.4): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.14, 0.455, 1.26, 2.52]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_redrive')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_redrive_jitter_05(monkeypatch):
    """batch_redrive (jitter 0.5): recover on attempt 4 — sleeps [0.15, 0.3, 1.35]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=3)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_redrive_jitter_05(monkeypatch):
    """batch_redrive (jitter 0.5): recover on attempt 5 — sleeps [0.15, 0.3, 1.35, 2.7]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_redrive_jitter_05(monkeypatch):
    """batch_redrive (jitter 0.5): exhaustion walk — sleeps [0.15, 0.3, 1.35, 2.7], retry-after 0.1875s."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_redrive')
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]
    assert caught.value.retry_after == pytest.approx(0.1875)


def test_grid_wave_sibling2_redrive_jitter_05(monkeypatch):
    """batch_redrive (jitter 0.5): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.15, 0.4875, 1.35, 2.7]


def test_grid_wave_sibling3_redrive_jitter_05(monkeypatch):
    """batch_redrive (jitter 0.5): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]


def test_grid_wave_doublearm_redrive_jitter_05(monkeypatch):
    """batch_redrive (jitter 0.5): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.15, 0.4875, 1.35, 2.7]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_redrive')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_redrive_jitter_06(monkeypatch):
    """batch_redrive (jitter 0.6): recover on attempt 4 — sleeps [0.16, 0.32, 1.44]."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=3)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.16, 0.32, 1.44]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_redrive_jitter_06(monkeypatch):
    """batch_redrive (jitter 0.6): recover on attempt 5 — sleeps [0.16, 0.32, 1.44, 2.88]."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.16, 0.32, 1.44, 2.88]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_redrive_jitter_06(monkeypatch):
    """batch_redrive (jitter 0.6): exhaustion walk — sleeps [0.16, 0.32, 1.44, 2.88], retry-after 0.2s."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_redrive')
    assert clock.sleeps == [0.16, 0.32, 1.44, 2.88]
    assert caught.value.retry_after == pytest.approx(0.2)


def test_grid_wave_sibling2_redrive_jitter_06(monkeypatch):
    """batch_redrive (jitter 0.6): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.16, 0.52, 1.44, 2.88]


def test_grid_wave_sibling3_redrive_jitter_06(monkeypatch):
    """batch_redrive (jitter 0.6): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.16, 0.32, 1.44, 2.88]


def test_grid_wave_doublearm_redrive_jitter_06(monkeypatch):
    """batch_redrive (jitter 0.6): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.16, 0.52, 1.44, 2.88]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_redrive')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_redrive_jitter_07(monkeypatch):
    """batch_redrive (jitter 0.7): recover on attempt 4 — sleeps [0.17, 0.34, 1.53]."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=3)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.17, 0.34, 1.53]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_redrive_jitter_07(monkeypatch):
    """batch_redrive (jitter 0.7): recover on attempt 5 — sleeps [0.17, 0.34, 1.53, 3.06]."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.17, 0.34, 1.53, 3.06]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_redrive_jitter_07(monkeypatch):
    """batch_redrive (jitter 0.7): exhaustion walk — sleeps [0.17, 0.34, 1.53, 3.06], retry-after 0.2125s."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_redrive')
    assert clock.sleeps == [0.17, 0.34, 1.53, 3.06]
    assert caught.value.retry_after == pytest.approx(0.2125)


def test_grid_wave_sibling2_redrive_jitter_07(monkeypatch):
    """batch_redrive (jitter 0.7): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.17, 0.5525, 1.53, 3.06]


def test_grid_wave_sibling3_redrive_jitter_07(monkeypatch):
    """batch_redrive (jitter 0.7): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.17, 0.34, 1.53, 3.06]


def test_grid_wave_doublearm_redrive_jitter_07(monkeypatch):
    """batch_redrive (jitter 0.7): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.17, 0.5525, 1.53, 3.06]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_redrive')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_redrive_jitter_08(monkeypatch):
    """batch_redrive (jitter 0.8): recover on attempt 4 — sleeps [0.18, 0.36, 1.62]."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=3)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.18, 0.36, 1.62]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_redrive_jitter_08(monkeypatch):
    """batch_redrive (jitter 0.8): recover on attempt 5 — sleeps [0.18, 0.36, 1.62, 3.24]."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.18, 0.36, 1.62, 3.24]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_redrive_jitter_08(monkeypatch):
    """batch_redrive (jitter 0.8): exhaustion walk — sleeps [0.18, 0.36, 1.62, 3.24], retry-after 0.225s."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_redrive')
    assert clock.sleeps == [0.18, 0.36, 1.62, 3.24]
    assert caught.value.retry_after == pytest.approx(0.225)


def test_grid_wave_sibling2_redrive_jitter_08(monkeypatch):
    """batch_redrive (jitter 0.8): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.18, 0.585, 1.62, 3.24]


def test_grid_wave_sibling3_redrive_jitter_08(monkeypatch):
    """batch_redrive (jitter 0.8): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.18, 0.36, 1.62, 3.24]


def test_grid_wave_doublearm_redrive_jitter_08(monkeypatch):
    """batch_redrive (jitter 0.8): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.18, 0.585, 1.62, 3.24]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_redrive')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_redrive_jitter_09(monkeypatch):
    """batch_redrive (jitter 0.9): recover on attempt 4 — sleeps [0.19, 0.38, 1.71]."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=3)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.19, 0.38, 1.71]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_redrive_jitter_09(monkeypatch):
    """batch_redrive (jitter 0.9): recover on attempt 5 — sleeps [0.19, 0.38, 1.71, 3.42]."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.19, 0.38, 1.71, 3.42]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_redrive_jitter_09(monkeypatch):
    """batch_redrive (jitter 0.9): exhaustion walk — sleeps [0.19, 0.38, 1.71, 3.42], retry-after 0.2375s."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_redrive')
    assert clock.sleeps == [0.19, 0.38, 1.71, 3.42]
    assert caught.value.retry_after == pytest.approx(0.2375)


def test_grid_wave_sibling2_redrive_jitter_09(monkeypatch):
    """batch_redrive (jitter 0.9): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.19, 0.6175, 1.71, 3.42]


def test_grid_wave_sibling3_redrive_jitter_09(monkeypatch):
    """batch_redrive (jitter 0.9): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.19, 0.38, 1.71, 3.42]


def test_grid_wave_doublearm_redrive_jitter_09(monkeypatch):
    """batch_redrive (jitter 0.9): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.19, 0.6175, 1.71, 3.42]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_redrive')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_redrive_jitter_10(monkeypatch):
    """batch_redrive (jitter 1.0): recover on attempt 4 — sleeps [0.2, 0.4, 1.8]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=3)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_redrive_jitter_10(monkeypatch):
    """batch_redrive (jitter 1.0): recover on attempt 5 — sleeps [0.2, 0.4, 1.8, 3.6]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_redrive_jitter_10(monkeypatch):
    """batch_redrive (jitter 1.0): exhaustion walk — sleeps [0.2, 0.4, 1.8, 3.6], retry-after 0.25s."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_redrive')
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]
    assert caught.value.retry_after == pytest.approx(0.25)


def test_grid_wave_sibling2_redrive_jitter_10(monkeypatch):
    """batch_redrive (jitter 1.0): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.2, 0.65, 1.8, 3.6]


def test_grid_wave_sibling3_redrive_jitter_10(monkeypatch):
    """batch_redrive (jitter 1.0): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]


def test_grid_wave_doublearm_redrive_jitter_10(monkeypatch):
    """batch_redrive (jitter 1.0): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_redrive', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_redrive') == 'committed'
    assert clock.sleeps == [0.2, 0.65, 1.8, 3.6]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_redrive')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_recover_jitter_00(monkeypatch):
    """batch_recover (jitter 0.0): recover on attempt 4 — sleeps [0.1, 0.2, 0.9]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=3)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_recover_jitter_00(monkeypatch):
    """batch_recover (jitter 0.0): recover on attempt 5 — sleeps [0.1, 0.2, 0.9, 1.8]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_recover_jitter_00(monkeypatch):
    """batch_recover (jitter 0.0): exhaustion walk — sleeps [0.1, 0.2, 0.9, 1.8], retry-after 0.125s."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_recover')
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]
    assert caught.value.retry_after == pytest.approx(0.125)


def test_grid_wave_sibling2_recover_jitter_00(monkeypatch):
    """batch_recover (jitter 0.0): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.1, 0.325, 0.9, 1.8]


def test_grid_wave_sibling3_recover_jitter_00(monkeypatch):
    """batch_recover (jitter 0.0): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]


def test_grid_wave_doublearm_recover_jitter_00(monkeypatch):
    """batch_recover (jitter 0.0): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.1, 0.325, 0.9, 1.8]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_recover')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_recover_jitter_01(monkeypatch):
    """batch_recover (jitter 0.1): recover on attempt 4 — sleeps [0.11, 0.22, 0.99]."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=3)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.11, 0.22, 0.99]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_recover_jitter_01(monkeypatch):
    """batch_recover (jitter 0.1): recover on attempt 5 — sleeps [0.11, 0.22, 0.99, 1.98]."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.11, 0.22, 0.99, 1.98]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_recover_jitter_01(monkeypatch):
    """batch_recover (jitter 0.1): exhaustion walk — sleeps [0.11, 0.22, 0.99, 1.98], retry-after 0.1375s."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_recover')
    assert clock.sleeps == [0.11, 0.22, 0.99, 1.98]
    assert caught.value.retry_after == pytest.approx(0.1375)


def test_grid_wave_sibling2_recover_jitter_01(monkeypatch):
    """batch_recover (jitter 0.1): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.11, 0.3575, 0.99, 1.98]


def test_grid_wave_sibling3_recover_jitter_01(monkeypatch):
    """batch_recover (jitter 0.1): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.11, 0.22, 0.99, 1.98]


def test_grid_wave_doublearm_recover_jitter_01(monkeypatch):
    """batch_recover (jitter 0.1): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.11, 0.3575, 0.99, 1.98]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_recover')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_recover_jitter_02(monkeypatch):
    """batch_recover (jitter 0.2): recover on attempt 4 — sleeps [0.12, 0.24, 1.08]."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=3)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.12, 0.24, 1.08]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_recover_jitter_02(monkeypatch):
    """batch_recover (jitter 0.2): recover on attempt 5 — sleeps [0.12, 0.24, 1.08, 2.16]."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.12, 0.24, 1.08, 2.16]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_recover_jitter_02(monkeypatch):
    """batch_recover (jitter 0.2): exhaustion walk — sleeps [0.12, 0.24, 1.08, 2.16], retry-after 0.15s."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_recover')
    assert clock.sleeps == [0.12, 0.24, 1.08, 2.16]
    assert caught.value.retry_after == pytest.approx(0.15)


def test_grid_wave_sibling2_recover_jitter_02(monkeypatch):
    """batch_recover (jitter 0.2): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.12, 0.39, 1.08, 2.16]


def test_grid_wave_sibling3_recover_jitter_02(monkeypatch):
    """batch_recover (jitter 0.2): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.12, 0.24, 1.08, 2.16]


def test_grid_wave_doublearm_recover_jitter_02(monkeypatch):
    """batch_recover (jitter 0.2): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.12, 0.39, 1.08, 2.16]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_recover')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_recover_jitter_03(monkeypatch):
    """batch_recover (jitter 0.3): recover on attempt 4 — sleeps [0.13, 0.26, 1.17]."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=3)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.13, 0.26, 1.17]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_recover_jitter_03(monkeypatch):
    """batch_recover (jitter 0.3): recover on attempt 5 — sleeps [0.13, 0.26, 1.17, 2.34]."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.13, 0.26, 1.17, 2.34]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_recover_jitter_03(monkeypatch):
    """batch_recover (jitter 0.3): exhaustion walk — sleeps [0.13, 0.26, 1.17, 2.34], retry-after 0.1625s."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_recover')
    assert clock.sleeps == [0.13, 0.26, 1.17, 2.34]
    assert caught.value.retry_after == pytest.approx(0.1625)


def test_grid_wave_sibling2_recover_jitter_03(monkeypatch):
    """batch_recover (jitter 0.3): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.13, 0.4225, 1.17, 2.34]


def test_grid_wave_sibling3_recover_jitter_03(monkeypatch):
    """batch_recover (jitter 0.3): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.13, 0.26, 1.17, 2.34]


def test_grid_wave_doublearm_recover_jitter_03(monkeypatch):
    """batch_recover (jitter 0.3): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.13, 0.4225, 1.17, 2.34]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_recover')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_recover_jitter_04(monkeypatch):
    """batch_recover (jitter 0.4): recover on attempt 4 — sleeps [0.14, 0.28, 1.26]."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=3)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.14, 0.28, 1.26]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_recover_jitter_04(monkeypatch):
    """batch_recover (jitter 0.4): recover on attempt 5 — sleeps [0.14, 0.28, 1.26, 2.52]."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.14, 0.28, 1.26, 2.52]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_recover_jitter_04(monkeypatch):
    """batch_recover (jitter 0.4): exhaustion walk — sleeps [0.14, 0.28, 1.26, 2.52], retry-after 0.175s."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_recover')
    assert clock.sleeps == [0.14, 0.28, 1.26, 2.52]
    assert caught.value.retry_after == pytest.approx(0.175)


def test_grid_wave_sibling2_recover_jitter_04(monkeypatch):
    """batch_recover (jitter 0.4): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.14, 0.455, 1.26, 2.52]


def test_grid_wave_sibling3_recover_jitter_04(monkeypatch):
    """batch_recover (jitter 0.4): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.14, 0.28, 1.26, 2.52]


def test_grid_wave_doublearm_recover_jitter_04(monkeypatch):
    """batch_recover (jitter 0.4): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.14, 0.455, 1.26, 2.52]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_recover')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_recover_jitter_05(monkeypatch):
    """batch_recover (jitter 0.5): recover on attempt 4 — sleeps [0.15, 0.3, 1.35]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=3)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_recover_jitter_05(monkeypatch):
    """batch_recover (jitter 0.5): recover on attempt 5 — sleeps [0.15, 0.3, 1.35, 2.7]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_recover_jitter_05(monkeypatch):
    """batch_recover (jitter 0.5): exhaustion walk — sleeps [0.15, 0.3, 1.35, 2.7], retry-after 0.1875s."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_recover')
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]
    assert caught.value.retry_after == pytest.approx(0.1875)


def test_grid_wave_sibling2_recover_jitter_05(monkeypatch):
    """batch_recover (jitter 0.5): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.15, 0.4875, 1.35, 2.7]


def test_grid_wave_sibling3_recover_jitter_05(monkeypatch):
    """batch_recover (jitter 0.5): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]


def test_grid_wave_doublearm_recover_jitter_05(monkeypatch):
    """batch_recover (jitter 0.5): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.15, 0.4875, 1.35, 2.7]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_recover')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_recover_jitter_06(monkeypatch):
    """batch_recover (jitter 0.6): recover on attempt 4 — sleeps [0.16, 0.32, 1.44]."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=3)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.16, 0.32, 1.44]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_recover_jitter_06(monkeypatch):
    """batch_recover (jitter 0.6): recover on attempt 5 — sleeps [0.16, 0.32, 1.44, 2.88]."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.16, 0.32, 1.44, 2.88]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_recover_jitter_06(monkeypatch):
    """batch_recover (jitter 0.6): exhaustion walk — sleeps [0.16, 0.32, 1.44, 2.88], retry-after 0.2s."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_recover')
    assert clock.sleeps == [0.16, 0.32, 1.44, 2.88]
    assert caught.value.retry_after == pytest.approx(0.2)


def test_grid_wave_sibling2_recover_jitter_06(monkeypatch):
    """batch_recover (jitter 0.6): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.16, 0.52, 1.44, 2.88]


def test_grid_wave_sibling3_recover_jitter_06(monkeypatch):
    """batch_recover (jitter 0.6): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.16, 0.32, 1.44, 2.88]


def test_grid_wave_doublearm_recover_jitter_06(monkeypatch):
    """batch_recover (jitter 0.6): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.16, 0.52, 1.44, 2.88]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_recover')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_recover_jitter_07(monkeypatch):
    """batch_recover (jitter 0.7): recover on attempt 4 — sleeps [0.17, 0.34, 1.53]."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=3)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.17, 0.34, 1.53]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_recover_jitter_07(monkeypatch):
    """batch_recover (jitter 0.7): recover on attempt 5 — sleeps [0.17, 0.34, 1.53, 3.06]."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.17, 0.34, 1.53, 3.06]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_recover_jitter_07(monkeypatch):
    """batch_recover (jitter 0.7): exhaustion walk — sleeps [0.17, 0.34, 1.53, 3.06], retry-after 0.2125s."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_recover')
    assert clock.sleeps == [0.17, 0.34, 1.53, 3.06]
    assert caught.value.retry_after == pytest.approx(0.2125)


def test_grid_wave_sibling2_recover_jitter_07(monkeypatch):
    """batch_recover (jitter 0.7): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.17, 0.5525, 1.53, 3.06]


def test_grid_wave_sibling3_recover_jitter_07(monkeypatch):
    """batch_recover (jitter 0.7): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.17, 0.34, 1.53, 3.06]


def test_grid_wave_doublearm_recover_jitter_07(monkeypatch):
    """batch_recover (jitter 0.7): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.17, 0.5525, 1.53, 3.06]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_recover')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_recover_jitter_08(monkeypatch):
    """batch_recover (jitter 0.8): recover on attempt 4 — sleeps [0.18, 0.36, 1.62]."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=3)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.18, 0.36, 1.62]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_recover_jitter_08(monkeypatch):
    """batch_recover (jitter 0.8): recover on attempt 5 — sleeps [0.18, 0.36, 1.62, 3.24]."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.18, 0.36, 1.62, 3.24]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_recover_jitter_08(monkeypatch):
    """batch_recover (jitter 0.8): exhaustion walk — sleeps [0.18, 0.36, 1.62, 3.24], retry-after 0.225s."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_recover')
    assert clock.sleeps == [0.18, 0.36, 1.62, 3.24]
    assert caught.value.retry_after == pytest.approx(0.225)


def test_grid_wave_sibling2_recover_jitter_08(monkeypatch):
    """batch_recover (jitter 0.8): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.18, 0.585, 1.62, 3.24]


def test_grid_wave_sibling3_recover_jitter_08(monkeypatch):
    """batch_recover (jitter 0.8): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.18, 0.36, 1.62, 3.24]


def test_grid_wave_doublearm_recover_jitter_08(monkeypatch):
    """batch_recover (jitter 0.8): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.18, 0.585, 1.62, 3.24]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_recover')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_recover_jitter_09(monkeypatch):
    """batch_recover (jitter 0.9): recover on attempt 4 — sleeps [0.19, 0.38, 1.71]."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=3)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.19, 0.38, 1.71]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_recover_jitter_09(monkeypatch):
    """batch_recover (jitter 0.9): recover on attempt 5 — sleeps [0.19, 0.38, 1.71, 3.42]."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.19, 0.38, 1.71, 3.42]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_recover_jitter_09(monkeypatch):
    """batch_recover (jitter 0.9): exhaustion walk — sleeps [0.19, 0.38, 1.71, 3.42], retry-after 0.2375s."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_recover')
    assert clock.sleeps == [0.19, 0.38, 1.71, 3.42]
    assert caught.value.retry_after == pytest.approx(0.2375)


def test_grid_wave_sibling2_recover_jitter_09(monkeypatch):
    """batch_recover (jitter 0.9): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.19, 0.6175, 1.71, 3.42]


def test_grid_wave_sibling3_recover_jitter_09(monkeypatch):
    """batch_recover (jitter 0.9): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.19, 0.38, 1.71, 3.42]


def test_grid_wave_doublearm_recover_jitter_09(monkeypatch):
    """batch_recover (jitter 0.9): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.19, 0.6175, 1.71, 3.42]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_recover')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_recover_jitter_10(monkeypatch):
    """batch_recover (jitter 1.0): recover on attempt 4 — sleeps [0.2, 0.4, 1.8]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=3)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_recover_jitter_10(monkeypatch):
    """batch_recover (jitter 1.0): recover on attempt 5 — sleeps [0.2, 0.4, 1.8, 3.6]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_recover_jitter_10(monkeypatch):
    """batch_recover (jitter 1.0): exhaustion walk — sleeps [0.2, 0.4, 1.8, 3.6], retry-after 0.25s."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=0, exhausting=True)
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_recover')
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]
    assert caught.value.retry_after == pytest.approx(0.25)


def test_grid_wave_sibling2_recover_jitter_10(monkeypatch):
    """batch_recover (jitter 1.0): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.2, 0.65, 1.8, 3.6]


def test_grid_wave_sibling3_recover_jitter_10(monkeypatch):
    """batch_recover (jitter 1.0): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]


def test_grid_wave_doublearm_recover_jitter_10(monkeypatch):
    """batch_recover (jitter 1.0): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_recover', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_recover') == 'committed'
    assert clock.sleeps == [0.2, 0.65, 1.8, 3.6]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_recover')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_provider_stt_jitter_00(monkeypatch):
    """batch_provider_stt (jitter 0.0): recover on attempt 4 — sleeps [0.1, 0.2, 0.9]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=3)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_provider_stt_jitter_00(monkeypatch):
    """batch_provider_stt (jitter 0.0): recover on attempt 5 — sleeps [0.1, 0.2, 0.9, 1.8]."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_provider_stt_jitter_00(monkeypatch):
    """batch_provider_stt (jitter 0.0): exhaustion walk — sleeps [0.1, 0.2, 0.9, 1.8], retry-after 0.125s."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_provider_stt', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_provider_stt')
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]
    assert caught.value.retry_after == pytest.approx(0.125)


def test_grid_wave_sibling2_provider_stt_jitter_00(monkeypatch):
    """batch_provider_stt (jitter 0.0): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.1, 0.325, 0.9, 1.8]


def test_grid_wave_sibling3_provider_stt_jitter_00(monkeypatch):
    """batch_provider_stt (jitter 0.0): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.1, 0.2, 0.9, 1.8]


def test_grid_wave_doublearm_provider_stt_jitter_00(monkeypatch):
    """batch_provider_stt (jitter 0.0): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.1, 0.325, 0.9, 1.8]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_provider_stt')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_provider_stt_jitter_01(monkeypatch):
    """batch_provider_stt (jitter 0.1): recover on attempt 4 — sleeps [0.11, 0.22, 0.99]."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=3)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.11, 0.22, 0.99]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_provider_stt_jitter_01(monkeypatch):
    """batch_provider_stt (jitter 0.1): recover on attempt 5 — sleeps [0.11, 0.22, 0.99, 1.98]."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.11, 0.22, 0.99, 1.98]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_provider_stt_jitter_01(monkeypatch):
    """batch_provider_stt (jitter 0.1): exhaustion walk — sleeps [0.11, 0.22, 0.99, 1.98], retry-after 0.1375s."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_provider_stt', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_provider_stt')
    assert clock.sleeps == [0.11, 0.22, 0.99, 1.98]
    assert caught.value.retry_after == pytest.approx(0.1375)


def test_grid_wave_sibling2_provider_stt_jitter_01(monkeypatch):
    """batch_provider_stt (jitter 0.1): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.11, 0.3575, 0.99, 1.98]


def test_grid_wave_sibling3_provider_stt_jitter_01(monkeypatch):
    """batch_provider_stt (jitter 0.1): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.11, 0.22, 0.99, 1.98]


def test_grid_wave_doublearm_provider_stt_jitter_01(monkeypatch):
    """batch_provider_stt (jitter 0.1): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.11, 0.3575, 0.99, 1.98]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_provider_stt')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_provider_stt_jitter_02(monkeypatch):
    """batch_provider_stt (jitter 0.2): recover on attempt 4 — sleeps [0.12, 0.24, 1.08]."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=3)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.12, 0.24, 1.08]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_provider_stt_jitter_02(monkeypatch):
    """batch_provider_stt (jitter 0.2): recover on attempt 5 — sleeps [0.12, 0.24, 1.08, 2.16]."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.12, 0.24, 1.08, 2.16]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_provider_stt_jitter_02(monkeypatch):
    """batch_provider_stt (jitter 0.2): exhaustion walk — sleeps [0.12, 0.24, 1.08, 2.16], retry-after 0.15s."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_provider_stt', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_provider_stt')
    assert clock.sleeps == [0.12, 0.24, 1.08, 2.16]
    assert caught.value.retry_after == pytest.approx(0.15)


def test_grid_wave_sibling2_provider_stt_jitter_02(monkeypatch):
    """batch_provider_stt (jitter 0.2): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.12, 0.39, 1.08, 2.16]


def test_grid_wave_sibling3_provider_stt_jitter_02(monkeypatch):
    """batch_provider_stt (jitter 0.2): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.12, 0.24, 1.08, 2.16]


def test_grid_wave_doublearm_provider_stt_jitter_02(monkeypatch):
    """batch_provider_stt (jitter 0.2): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.2)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.12, 0.39, 1.08, 2.16]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_provider_stt')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_provider_stt_jitter_03(monkeypatch):
    """batch_provider_stt (jitter 0.3): recover on attempt 4 — sleeps [0.13, 0.26, 1.17]."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=3)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.13, 0.26, 1.17]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_provider_stt_jitter_03(monkeypatch):
    """batch_provider_stt (jitter 0.3): recover on attempt 5 — sleeps [0.13, 0.26, 1.17, 2.34]."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.13, 0.26, 1.17, 2.34]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_provider_stt_jitter_03(monkeypatch):
    """batch_provider_stt (jitter 0.3): exhaustion walk — sleeps [0.13, 0.26, 1.17, 2.34], retry-after 0.1625s."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_provider_stt', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_provider_stt')
    assert clock.sleeps == [0.13, 0.26, 1.17, 2.34]
    assert caught.value.retry_after == pytest.approx(0.1625)


def test_grid_wave_sibling2_provider_stt_jitter_03(monkeypatch):
    """batch_provider_stt (jitter 0.3): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.13, 0.4225, 1.17, 2.34]


def test_grid_wave_sibling3_provider_stt_jitter_03(monkeypatch):
    """batch_provider_stt (jitter 0.3): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.13, 0.26, 1.17, 2.34]


def test_grid_wave_doublearm_provider_stt_jitter_03(monkeypatch):
    """batch_provider_stt (jitter 0.3): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.3)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.13, 0.4225, 1.17, 2.34]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_provider_stt')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_provider_stt_jitter_04(monkeypatch):
    """batch_provider_stt (jitter 0.4): recover on attempt 4 — sleeps [0.14, 0.28, 1.26]."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=3)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.14, 0.28, 1.26]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_provider_stt_jitter_04(monkeypatch):
    """batch_provider_stt (jitter 0.4): recover on attempt 5 — sleeps [0.14, 0.28, 1.26, 2.52]."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.14, 0.28, 1.26, 2.52]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_provider_stt_jitter_04(monkeypatch):
    """batch_provider_stt (jitter 0.4): exhaustion walk — sleeps [0.14, 0.28, 1.26, 2.52], retry-after 0.175s."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_provider_stt', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_provider_stt')
    assert clock.sleeps == [0.14, 0.28, 1.26, 2.52]
    assert caught.value.retry_after == pytest.approx(0.175)


def test_grid_wave_sibling2_provider_stt_jitter_04(monkeypatch):
    """batch_provider_stt (jitter 0.4): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.14, 0.455, 1.26, 2.52]


def test_grid_wave_sibling3_provider_stt_jitter_04(monkeypatch):
    """batch_provider_stt (jitter 0.4): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.14, 0.28, 1.26, 2.52]


def test_grid_wave_doublearm_provider_stt_jitter_04(monkeypatch):
    """batch_provider_stt (jitter 0.4): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.4)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.14, 0.455, 1.26, 2.52]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_provider_stt')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_provider_stt_jitter_05(monkeypatch):
    """batch_provider_stt (jitter 0.5): recover on attempt 4 — sleeps [0.15, 0.3, 1.35]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=3)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_provider_stt_jitter_05(monkeypatch):
    """batch_provider_stt (jitter 0.5): recover on attempt 5 — sleeps [0.15, 0.3, 1.35, 2.7]."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_provider_stt_jitter_05(monkeypatch):
    """batch_provider_stt (jitter 0.5): exhaustion walk — sleeps [0.15, 0.3, 1.35, 2.7], retry-after 0.1875s."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_provider_stt', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_provider_stt')
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]
    assert caught.value.retry_after == pytest.approx(0.1875)


def test_grid_wave_sibling2_provider_stt_jitter_05(monkeypatch):
    """batch_provider_stt (jitter 0.5): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.15, 0.4875, 1.35, 2.7]


def test_grid_wave_sibling3_provider_stt_jitter_05(monkeypatch):
    """batch_provider_stt (jitter 0.5): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.15, 0.3, 1.35, 2.7]


def test_grid_wave_doublearm_provider_stt_jitter_05(monkeypatch):
    """batch_provider_stt (jitter 0.5): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.5)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.15, 0.4875, 1.35, 2.7]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_provider_stt')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_provider_stt_jitter_06(monkeypatch):
    """batch_provider_stt (jitter 0.6): recover on attempt 4 — sleeps [0.16, 0.32, 1.44]."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=3)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.16, 0.32, 1.44]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_provider_stt_jitter_06(monkeypatch):
    """batch_provider_stt (jitter 0.6): recover on attempt 5 — sleeps [0.16, 0.32, 1.44, 2.88]."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.16, 0.32, 1.44, 2.88]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_provider_stt_jitter_06(monkeypatch):
    """batch_provider_stt (jitter 0.6): exhaustion walk — sleeps [0.16, 0.32, 1.44, 2.88], retry-after 0.2s."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_provider_stt', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_provider_stt')
    assert clock.sleeps == [0.16, 0.32, 1.44, 2.88]
    assert caught.value.retry_after == pytest.approx(0.2)


def test_grid_wave_sibling2_provider_stt_jitter_06(monkeypatch):
    """batch_provider_stt (jitter 0.6): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.16, 0.52, 1.44, 2.88]


def test_grid_wave_sibling3_provider_stt_jitter_06(monkeypatch):
    """batch_provider_stt (jitter 0.6): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.16, 0.32, 1.44, 2.88]


def test_grid_wave_doublearm_provider_stt_jitter_06(monkeypatch):
    """batch_provider_stt (jitter 0.6): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.6)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.16, 0.52, 1.44, 2.88]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_provider_stt')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_provider_stt_jitter_07(monkeypatch):
    """batch_provider_stt (jitter 0.7): recover on attempt 4 — sleeps [0.17, 0.34, 1.53]."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=3)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.17, 0.34, 1.53]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_provider_stt_jitter_07(monkeypatch):
    """batch_provider_stt (jitter 0.7): recover on attempt 5 — sleeps [0.17, 0.34, 1.53, 3.06]."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.17, 0.34, 1.53, 3.06]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_provider_stt_jitter_07(monkeypatch):
    """batch_provider_stt (jitter 0.7): exhaustion walk — sleeps [0.17, 0.34, 1.53, 3.06], retry-after 0.2125s."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_provider_stt', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_provider_stt')
    assert clock.sleeps == [0.17, 0.34, 1.53, 3.06]
    assert caught.value.retry_after == pytest.approx(0.2125)


def test_grid_wave_sibling2_provider_stt_jitter_07(monkeypatch):
    """batch_provider_stt (jitter 0.7): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.17, 0.5525, 1.53, 3.06]


def test_grid_wave_sibling3_provider_stt_jitter_07(monkeypatch):
    """batch_provider_stt (jitter 0.7): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.17, 0.34, 1.53, 3.06]


def test_grid_wave_doublearm_provider_stt_jitter_07(monkeypatch):
    """batch_provider_stt (jitter 0.7): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.7)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.17, 0.5525, 1.53, 3.06]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_provider_stt')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_provider_stt_jitter_08(monkeypatch):
    """batch_provider_stt (jitter 0.8): recover on attempt 4 — sleeps [0.18, 0.36, 1.62]."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=3)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.18, 0.36, 1.62]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_provider_stt_jitter_08(monkeypatch):
    """batch_provider_stt (jitter 0.8): recover on attempt 5 — sleeps [0.18, 0.36, 1.62, 3.24]."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.18, 0.36, 1.62, 3.24]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_provider_stt_jitter_08(monkeypatch):
    """batch_provider_stt (jitter 0.8): exhaustion walk — sleeps [0.18, 0.36, 1.62, 3.24], retry-after 0.225s."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_provider_stt', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_provider_stt')
    assert clock.sleeps == [0.18, 0.36, 1.62, 3.24]
    assert caught.value.retry_after == pytest.approx(0.225)


def test_grid_wave_sibling2_provider_stt_jitter_08(monkeypatch):
    """batch_provider_stt (jitter 0.8): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.18, 0.585, 1.62, 3.24]


def test_grid_wave_sibling3_provider_stt_jitter_08(monkeypatch):
    """batch_provider_stt (jitter 0.8): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.18, 0.36, 1.62, 3.24]


def test_grid_wave_doublearm_provider_stt_jitter_08(monkeypatch):
    """batch_provider_stt (jitter 0.8): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.8)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.18, 0.585, 1.62, 3.24]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_provider_stt')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_provider_stt_jitter_09(monkeypatch):
    """batch_provider_stt (jitter 0.9): recover on attempt 4 — sleeps [0.19, 0.38, 1.71]."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=3)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.19, 0.38, 1.71]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_provider_stt_jitter_09(monkeypatch):
    """batch_provider_stt (jitter 0.9): recover on attempt 5 — sleeps [0.19, 0.38, 1.71, 3.42]."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.19, 0.38, 1.71, 3.42]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_provider_stt_jitter_09(monkeypatch):
    """batch_provider_stt (jitter 0.9): exhaustion walk — sleeps [0.19, 0.38, 1.71, 3.42], retry-after 0.2375s."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_provider_stt', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_provider_stt')
    assert clock.sleeps == [0.19, 0.38, 1.71, 3.42]
    assert caught.value.retry_after == pytest.approx(0.2375)


def test_grid_wave_sibling2_provider_stt_jitter_09(monkeypatch):
    """batch_provider_stt (jitter 0.9): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.19, 0.6175, 1.71, 3.42]


def test_grid_wave_sibling3_provider_stt_jitter_09(monkeypatch):
    """batch_provider_stt (jitter 0.9): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.19, 0.38, 1.71, 3.42]


def test_grid_wave_doublearm_provider_stt_jitter_09(monkeypatch):
    """batch_provider_stt (jitter 0.9): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=0.9)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.19, 0.6175, 1.71, 3.42]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_provider_stt')
    assert residual == 0.0 and generation == 0  # success cleared both arms


def test_grid_wave_recover3_provider_stt_jitter_10(monkeypatch):
    """batch_provider_stt (jitter 1.0): recover on attempt 4 — sleeps [0.2, 0.4, 1.8]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=3)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_recover4_provider_stt_jitter_10(monkeypatch):
    """batch_provider_stt (jitter 1.0): recover on attempt 5 — sleeps [0.2, 0.4, 1.8, 3.6]."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]  # rungs 1-2 bare, rungs 3+ add their wave waits


def test_grid_wave_exhaust_provider_stt_jitter_10(monkeypatch):
    """batch_provider_stt (jitter 1.0): exhaustion walk — sleeps [0.2, 0.4, 1.8, 3.6], retry-after 0.25s."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(
        monkeypatch, clock, label='batch_provider_stt', aborts=0, exhausting=True
    )
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted) as caught:
        store.run(body, operation='batch_provider_stt')
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]
    assert caught.value.retry_after == pytest.approx(0.25)


def test_grid_wave_sibling2_provider_stt_jitter_10(monkeypatch):
    """batch_provider_stt (jitter 1.0): sibling arm during attempt 2; deep rungs take the max."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4, arm_at=2)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.2, 0.65, 1.8, 3.6]


def test_grid_wave_sibling3_provider_stt_jitter_10(monkeypatch):
    """batch_provider_stt (jitter 1.0): sibling arm during attempt 3; deep rungs take the max."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4, arm_at=3)
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.2, 0.4, 1.8, 3.6]


def test_grid_wave_doublearm_provider_stt_jitter_10(monkeypatch):
    """batch_provider_stt (jitter 1.0): stacked sibling arms at attempts 2 and 3 vs the wave wait on rung 3."""
    clock = _Clock(jitter=1)
    store, damper, _client, body = _make_store(monkeypatch, clock, label='batch_provider_stt', aborts=4, arm_at=(2, 3))
    assert store.run(body, operation='batch_provider_stt') == 'committed'
    assert clock.sleeps == [0.2, 0.65, 1.8, 3.6]  # rung 3 takes the longer of sibling and wave
    residual, generation = damper.peek('batch_provider_stt')
    assert residual == 0.0 and generation == 0  # success cleared both arms
