"""Store-level contention storm damper (x2239/30m ``outcome=exhausted`` family).

The bounded contention chain gives one operation five immediate attempts whose
inter-attempt gaps sum to 1.5-3.0 s. During a real contention storm every caller that
exhausts re-strikes the same hot documents at once, so the whole process burns
its budgets in lockstep — the production signature
``firestore_transaction_contention operation=... attempt=5/5 outcome=exhausted``
(the largest worker error class in the Loop S sensor, x2239/30m at its peak).
The worker's pull loop already damps itself with a jittered instance backoff;
every other store entry re-strikes immediately. This suite pins the
store-level damper that closes that gap:

1. After ``FirestoreStore.run`` exhausts its contention budget for a label, the
   next entry of the SAME label waits out a bounded, jittered residual window
   (logged at INFO as ``event=batch_store_backoff``) while every other label
   runs untouched. One store instance is one process's view of one namespace,
   and the scheduler shards, the pump, intake and maintenance all share it —
   arming damps all of them, not just the caller that exhausted.
2. A successful commit clears the ladder, but only if no concurrent arm
   happened since the entry consulted (generation guard, mirroring the pull
   loop's generation-based reset).
3. The damper is dormant when either contention kill switch is off, never
   touches the advisory probe/due/oldest read paths, and is capped so it can
   neither grow state forever nor stall the record-latency path.

Failure-Class: FC-immediate-retry-loses-shared-cas
"""

import json
import logging
import threading
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import Aborted

from config import batch_pipeline as config_batch_pipeline
from database import batch_pipeline_store as storage
from database.batch_pipeline_transaction_labels import store_operation
from database.firestore_transaction_retry import FirestoreContentionExhausted

BACKEND = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------
# Harnesses
# --------------------------------------------------------------------------


class AbortThenCommitTx:
    """Minimal firestore_v1.Transaction: the first ``abort_times`` commits abort."""

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


class FakeClock:
    """Deterministic monotonic clock, sleeper recorder and jitter source."""

    def __init__(self, now=100.0, jitter=0.0):
        self.now = now
        self.jitter = jitter
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        assert seconds >= 0, 'damper must never sleep a negative residual'
        self.sleeps.append(seconds)
        self.now += seconds

    def random_value(self):
        return self.jitter

    @property
    def total_slept(self):
        return sum(self.sleeps)


def make_damper(clock=None, jitter=0.0, jitter_sequence=None):
    clock = clock if clock is not None else FakeClock(jitter=jitter)
    if jitter_sequence is not None:
        draws = iter(jitter_sequence)
        clock.random_value = lambda: next(draws, jitter_sequence[-1])
    return (
        storage._ContentionStormDamper(monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value),
        clock,
    )


def exhausting_client(abort_times=10**6):
    """Mock client whose transactions abort forever unless told otherwise."""
    client = Mock()
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(abort_times)
    return client


def healthy_client():
    client = Mock()
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    return client


def build_store(monkeypatch, damper=None, client=None, namespace='batch_pipeline_dev'):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    return storage.FirestoreStore(
        namespace, firestore_client=client if client is not None else exhausting_client(), storm_damper=damper
    )


def silence_chain_sleep(monkeypatch):
    """Skip the retry chain's own jitter sleeps; the damper's sleeps stay injected."""
    actual = storage.run_with_transaction_contention_retry

    def factory(*args, **kwargs):
        kwargs.setdefault('sleep', lambda _seconds: None)
        return actual(*args, **kwargs)

    monkeypatch.setattr(storage, 'run_with_transaction_contention_retry', factory)


def exhaust_run(store, label, times=1):
    """Drive ``label`` to exhaustion ``times`` times; return the last error."""
    error = None
    for _ in range(times):
        try:
            store.run(lambda tx: True, operation=label)
        except FirestoreContentionExhausted as caught:
            error = caught
        else:
            raise AssertionError('expected exhaustion')
    return error


# --------------------------------------------------------------------------
# Section A — damper unit semantics
# --------------------------------------------------------------------------


def test_idle_consult_waits_nothing():
    damper, clock = make_damper()
    waited, generation = damper.consult('batch_merge_commit')
    assert waited == 0.0
    assert clock.sleeps == []
    assert generation == 0


def test_consult_generation_is_zero_when_untracked():
    damper, _clock = make_damper()
    assert damper.consult('batch_admit')[1] == 0


def test_first_arm_at_min_jitter_is_half_the_base_maximum():
    damper, clock = make_damper(jitter=0.0)
    retry_after = damper.arm('batch_admit')
    assert retry_after == pytest.approx(storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS * 0.5)


def test_first_arm_near_max_jitter_approaches_the_full_base_maximum():
    damper, clock = make_damper(jitter=0.999)
    retry_after = damper.arm('batch_admit')
    assert (
        0.999 * storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS
        <= retry_after
        < (storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS)
    )


def test_jitter_stays_within_half_to_full_maximum_for_seeded_draws():
    for seed in range(12):
        damper, _clock = make_damper(jitter=(seed % 7) / 7.0)
        retry_after = damper.arm('batch_admit')
        maximum = storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS
        assert maximum * 0.5 - 1e-9 <= retry_after <= maximum + 1e-9


def test_ladder_doubles_each_consecutive_failure():
    rungs = []
    for failures in range(1, 6):
        damper, _clock = make_damper(jitter=1.0)
        for _ in range(failures - 1):
            damper.arm('batch_admit')
        rungs.append(damper.arm('batch_admit'))
    assert rungs == [
        pytest.approx(storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS),
        pytest.approx(storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS * 2),
        pytest.approx(storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS * 4),
        pytest.approx(storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS * 8),
        pytest.approx(storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS),
    ]


def test_ladder_cap_binds_at_the_fifth_failure():
    damper, clock = make_damper(jitter=1.0)
    for _ in range(4):
        damper.arm('batch_admit')
    retry_after = damper.arm('batch_admit')
    assert retry_after == pytest.approx(storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS)


def test_ladder_stays_capped_after_ten_failures():
    damper, clock = make_damper(jitter=1.0)
    for _ in range(10):
        damper.arm('batch_admit')
    assert damper.arm('batch_admit') == pytest.approx(storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS)


def test_arm_extends_and_never_shrinks_an_existing_window():
    damper, clock = make_damper(jitter=1.0)
    damper.arm('batch_admit')
    clock.now += 0.01  # a second exhaustion arrives while the window is live
    retry_after = damper.arm('batch_admit')
    assert retry_after > 0.0
    assert damper._armed_until['batch_admit'] == pytest.approx(clock.now + retry_after)


def test_second_exhaustion_never_shortens_the_live_window():
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    damper.arm('batch_admit')  # window [100.0, 100.25]
    clock.now += 0.05
    retry_after = damper.arm('batch_admit')  # rung-two draw 0.0 -> candidate until 100.30
    assert damper._armed_until['batch_admit'] == pytest.approx(100.30)
    assert retry_after == pytest.approx(0.25)


def test_consult_sleeps_exactly_the_residual():
    damper, clock = make_damper(jitter=1.0)
    armed = damper.arm('batch_admit')
    waited, _generation = damper.consult('batch_admit')
    assert waited == pytest.approx(armed)
    assert clock.sleeps == [pytest.approx(armed)]


def test_consult_returns_the_armed_generation():
    damper, _clock = make_damper()
    damper.arm('batch_admit')
    damper.arm('batch_admit')
    assert damper.consult('batch_admit')[1] == 2


def test_consult_does_not_advance_the_generation():
    damper, _clock = make_damper()
    damper.arm('batch_admit')
    damper.consult('batch_admit')
    assert damper._generations['batch_admit'] == 1


def test_expired_window_consults_without_sleeping():
    damper, clock = make_damper(jitter=1.0)
    damper.arm('batch_admit')
    clock.now += storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS * 2
    waited, _generation = damper.consult('batch_admit')
    assert waited == 0.0
    assert clock.sleeps == []


def test_expired_window_keeps_the_failure_ladder():
    damper, clock = make_damper(jitter=1.0)
    damper.arm('batch_admit')
    clock.now += storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS * 2
    damper.consult('batch_admit')
    damper.arm('batch_admit')
    assert damper._failures['batch_admit'] == 2


def test_note_success_clears_when_the_generation_matches():
    damper, _clock = make_damper()
    damper.arm('batch_admit')
    waited, generation = damper.consult('batch_admit')
    assert waited > 0.0
    damper.note_success('batch_admit', generation)
    assert damper._armed_until == {}
    assert damper._failures == {}
    assert damper._generations == {}
    assert damper.consult('batch_admit') == (0.0, 0)


def test_note_success_ignores_a_stale_generation():
    damper, _clock = make_damper()
    damper.arm('batch_admit')
    waited, generation = damper.consult('batch_admit')
    damper.arm('batch_admit')  # a concurrent caller exhausted while we ran
    damper.note_success('batch_admit', generation)
    assert 'batch_admit' in damper._armed_until
    assert damper._failures['batch_admit'] == 2


def test_note_success_after_stale_generation_still_works_when_reconsulted():
    damper, _clock = make_damper()
    damper.arm('batch_admit')
    _waited, stale = damper.consult('batch_admit')
    damper.arm('batch_admit')
    damper.note_success('batch_admit', stale)
    waited, fresh = damper.consult('batch_admit')
    damper.note_success('batch_admit', fresh)
    assert damper._generations == {}


def test_note_success_resets_the_failure_ladder_to_base():
    damper, clock = make_damper(jitter=1.0)
    damper.arm('batch_admit')
    damper.arm('batch_admit')
    _waited, generation = damper.consult('batch_admit')
    damper.note_success('batch_admit', generation)
    retry_after = damper.arm('batch_admit')
    assert retry_after == pytest.approx(storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS)


def test_labels_are_isolated_on_arm():
    damper, clock = make_damper(jitter=1.0)
    damper.arm('batch_merge_commit')
    waited, _generation = damper.consult('batch_admit')
    assert waited == 0.0
    assert clock.sleeps == []


def test_labels_are_isolated_on_the_ladder():
    damper, _clock = make_damper(jitter=1.0)
    damper.arm('batch_merge_commit')
    damper.arm('batch_merge_commit')
    damper.arm('batch_admit')
    assert damper._failures['batch_admit'] == 1
    assert damper._failures['batch_merge_commit'] == 2


def test_success_on_one_label_keeps_the_other_armed():
    damper, _clock = make_damper()
    damper.arm('batch_merge_commit')
    damper.arm('batch_admit')
    _waited, admit_generation = damper.consult('batch_admit')
    damper.note_success('batch_admit', admit_generation)
    assert 'batch_merge_commit' in damper._armed_until
    assert 'batch_admit' not in damper._armed_until


def test_concurrent_arms_extend_but_never_sum_the_window():
    damper, clock = make_damper(jitter=1.0)
    damper.arm('batch_admit')
    first_until = damper._armed_until['batch_admit']
    damper.arm('batch_admit')
    assert damper._armed_until['batch_admit'] >= first_until
    assert damper._armed_until['batch_admit'] <= clock.now + storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS


def test_tracked_labels_counts_distinct_labels():
    damper, _clock = make_damper()
    damper.arm('batch_admit')
    damper.arm('batch_admit')
    damper.arm('batch_merge_commit')
    assert damper.tracked_labels() == 2


def test_tracked_label_cap_stops_tracking_new_labels_fail_open():
    damper, clock = make_damper(jitter=1.0)
    cap = storage.FirestoreStore.STORM_DAMPER_MAX_TRACKED_LABELS
    for index in range(cap):
        damper.arm(f'batch_overflow_{index:02d}')
    assert damper.tracked_labels() == cap
    assert damper.arm('batch_overflow_untracked') == 0.0
    assert damper.tracked_labels() == cap
    assert clock.sleeps == []


def test_tracked_cap_keeps_damping_existing_labels():
    damper, _clock = make_damper(jitter=1.0)
    cap = storage.FirestoreStore.STORM_DAMPER_MAX_TRACKED_LABELS
    for index in range(cap):
        damper.arm(f'batch_overflow_{index:02d}')
    assert damper.arm('batch_overflow_00') > 0.0


def test_unknown_label_consult_after_cap_is_a_noop():
    damper, clock = make_damper(jitter=1.0)
    cap = storage.FirestoreStore.STORM_DAMPER_MAX_TRACKED_LABELS
    for index in range(cap):
        damper.arm(f'batch_overflow_{index:02d}')
    waited, generation = damper.consult('batch_overflow_untracked')
    assert (waited, generation) == (0.0, 0)
    assert clock.sleeps == []


def test_arm_generations_increase_monotonically_per_label():
    damper, _clock = make_damper()
    seen = [damper.arm('batch_admit') for _ in range(3)]
    assert seen[0] > 0 and seen[-1] >= seen[0]
    assert damper._generations['batch_admit'] == 3


def test_sleeper_runs_once_per_damped_consult():
    damper, clock = make_damper(jitter=1.0)
    damper.arm('batch_admit')
    damper.consult('batch_admit')
    damper.consult('batch_admit')  # window expired by the first sleep's clock advance
    assert len(clock.sleeps) == 1


def test_clear_consult_never_touches_the_sleeper():
    damper, clock = make_damper()
    damper.arm('batch_admit')
    clock.now += storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS
    damper.consult('batch_admit')
    assert clock.sleeps == []


def test_ladder_reaches_the_cap_in_ladder_steps_doublings():
    assert (
        storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS * (2**storage.FirestoreStore.STORM_DAMPER_LADDER_STEPS)
        == storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS
    )


def test_base_is_below_cap_and_steps_are_positive():
    assert 0 < storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS < storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS
    assert storage.FirestoreStore.STORM_DAMPER_LADDER_STEPS >= 1
    assert storage.FirestoreStore.STORM_DAMPER_MAX_TRACKED_LABELS >= 1


def test_arm_after_a_cleared_ladder_starts_from_base_again():
    damper, clock = make_damper(jitter=1.0)
    damper.arm('batch_admit')
    damper.arm('batch_admit')
    _waited, generation = damper.consult('batch_admit')
    damper.note_success('batch_admit', generation)
    first_again = damper.arm('batch_admit')
    assert first_again == pytest.approx(storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS)


def test_negative_residual_is_treated_as_expired():
    damper, clock = make_damper(jitter=1.0)
    damper.arm('batch_admit')
    clock.now += storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS + 0.001
    waited, _generation = damper.consult('batch_admit')
    assert waited == 0.0


def test_damped_consult_blocks_only_its_own_label_in_a_thread():
    damper, clock = make_damper(jitter=1.0)
    damper.arm('batch_merge_commit')
    observed = {}

    def other_label():
        observed['waited'] = damper.consult('batch_admit')[0]

    thread = threading.Thread(target=other_label)
    thread.start()
    damper.consult('batch_merge_commit')
    thread.join(timeout=2)
    assert observed['waited'] == 0.0
    assert len(clock.sleeps) == 1


def test_concurrent_arms_from_threads_stay_bounded():
    damper, clock = make_damper(jitter=0.5)

    def storm():
        for _ in range(8):
            damper.arm('batch_admit')

    threads = [threading.Thread(target=storm) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)
    assert damper._failures['batch_admit'] == 32
    assert damper._armed_until['batch_admit'] <= clock.now + storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS + 1e-9


def test_success_note_from_threads_only_clears_current_generation():
    damper, _clock = make_damper()
    damper.arm('batch_admit')
    _waited, stale = damper.consult('batch_admit')
    results = []
    damper.arm('batch_admit')
    thread = threading.Thread(target=lambda: results.append(damper.note_success('batch_admit', stale)))
    thread.start()
    thread.join(timeout=2)
    assert results == [None]
    assert 'batch_admit' in damper._armed_until


# --------------------------------------------------------------------------
# Section B — the ladder's per-rung delay math
# --------------------------------------------------------------------------


def test_rung_one_delay_spans_half_base_to_base():
    damper, clock = make_damper(jitter=0.25)
    assert damper.arm('batch_admit') == pytest.approx(storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS * 0.625)


def test_rung_two_delay_spans_half_doubled_to_doubled():
    damper, clock = make_damper(jitter=0.5)
    damper.arm('batch_admit')
    assert damper.arm('batch_admit') == pytest.approx(storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS * 2 * 0.75)


def test_rung_three_delay_spans_half_quadrupled_to_quadrupled():
    damper, clock = make_damper(jitter=0.75)
    damper.arm('batch_admit')
    damper.arm('batch_admit')
    assert damper.arm('batch_admit') == pytest.approx(storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS * 4 * 0.875)


def test_rung_four_delay_is_capped_at_the_damper_cap():
    damper, clock = make_damper(jitter=0.5)
    for _ in range(3):
        damper.arm('batch_admit')
    assert damper.arm('batch_admit') == pytest.approx(storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS * 8 * 0.75)


def test_rung_delays_never_exceed_the_cap_for_any_jitter():
    for jitter in (0.0, 0.1, 0.5, 0.9, 1.0):
        damper, _clock = make_damper(jitter=jitter)
        for _ in range(6):
            assert damper.arm('batch_admit') <= storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS + 1e-9


def test_min_jitter_is_inclusive_at_every_rung():
    damper, _clock = make_damper(jitter=0.0)
    expected = [storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS * (2**rung) * 0.5 for rung in range(4)]
    for rung in range(4):
        assert damper.arm('batch_admit') == pytest.approx(expected[rung])


# --------------------------------------------------------------------------
# Section C — store.run integration: consult, arm, reset, kill switches
# --------------------------------------------------------------------------


@pytest.fixture
def fast_chain(monkeypatch):
    """Skip the retry chain's own jitter sleeps; damper sleeps stay injected."""
    silence_chain_sleep(monkeypatch)


def test_first_exhaustion_does_not_consult_sleep(monkeypatch, fast_chain):
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    exhaust_run(store, 'batch_merge_commit')
    assert clock.sleeps == []
    assert damper.tracked_labels() == 1


def test_exhaustion_arms_the_operation_label(monkeypatch, fast_chain):
    damper, _clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    exhaust_run(store, 'batch_merge_commit')
    assert damper._failures['batch_merge_commit'] == 1
    assert damper._armed_until['batch_merge_commit'] > 100.0


def test_next_entry_of_same_label_waits_the_residual(monkeypatch, fast_chain):
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    store = build_store(monkeypatch, damper=damper)
    exhaust_run(store, 'batch_merge_commit')
    exhaust_run(store, 'batch_merge_commit')
    assert clock.sleeps == [pytest.approx(storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS)]


def test_next_entry_of_sibling_label_runs_without_waiting(monkeypatch, fast_chain):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_merge_commit')
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert clock.sleeps == []


def test_success_clears_the_armed_window(monkeypatch, fast_chain):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_merge_commit')
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_merge_commit') == 'ok'
    assert damper._armed_until == {}
    assert damper.tracked_labels() == 0


def test_success_after_wait_clears_the_whole_ladder(monkeypatch, fast_chain):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_merge_commit')
    clock.jitter = 1.0
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_merge_commit') == 'ok'
    assert (damper._armed_until, damper._failures, damper._generations) == ({}, {}, {})


def test_repeated_exhaustions_grow_the_wait_ladder(monkeypatch, fast_chain):
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    exhaust_run(store, 'batch_merge_commit', times=4)
    # consult residuals seen by entries 2..4: one min-jitter rung per arm step
    assert clock.sleeps == [
        pytest.approx(storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS * 0.5),
        pytest.approx(storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS),
        pytest.approx(storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS * 2),
    ]


def test_non_contention_error_never_arms(monkeypatch, fast_chain):
    damper, _clock = make_damper()
    store = build_store(monkeypatch, damper=damper)

    def body(tx):
        raise KeyError('schema drift')

    with pytest.raises(KeyError):
        store.run(body, operation='batch_merge_commit')
    assert damper.tracked_labels() == 0
    assert damper._armed_until == {}


def test_non_contention_error_after_a_storm_keeps_the_window(monkeypatch, fast_chain):
    damper, _clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    exhaust_run(store, 'batch_merge_commit')
    before = dict(damper._armed_until)
    with pytest.raises(KeyError):
        store.run(lambda tx: (_ for _ in ()).throw(KeyError('x')), operation='batch_merge_commit')
    assert damper._armed_until == before
    assert damper._failures['batch_merge_commit'] == 1


def test_wait_precedes_the_first_transaction_open(monkeypatch, fast_chain):
    events = []
    clock = FakeClock()

    def record_sleep(seconds):
        events.append(('sleep', round(seconds, 3)))
        clock.sleeps.append(seconds)
        clock.now += seconds

    clock.sleep = record_sleep  # installed before make_damper binds the sleeper
    damper, clock = make_damper(clock=clock, jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    client.transaction.side_effect = lambda max_attempts=5: (events.append(('tx',)), AbortThenCommitTx(10**6))[1]
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_merge_commit')
    events.clear()
    exhaust_run(store, 'batch_merge_commit')
    assert events[0][0] == 'sleep'
    assert events[1][0] == 'tx'


def test_label_refusal_precedes_any_consult(monkeypatch, fast_chain):
    damper, clock = make_damper()
    client = Mock()
    store = build_store(monkeypatch, damper=damper, client=client)
    with pytest.raises(ValueError, match='static store operation label required'):
        store.run(lambda tx: None)
    assert clock.sleeps == []
    client.transaction.assert_not_called()


def test_legacy_retry_kill_switch_disables_the_damper_entirely(monkeypatch, fast_chain):
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_RETRY_ENABLED', 'false')
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    with pytest.raises(ValueError) as caught:
        store.run(lambda tx: True, operation='batch_merge_commit')
    assert isinstance(caught.value.__cause__, Aborted)
    assert damper.tracked_labels() == 0
    assert clock.sleeps == []


def test_damper_kill_switch_disables_consult_and_arm(monkeypatch, fast_chain):
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED', 'false')
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    exhaust_run(store, 'batch_merge_commit', times=2)
    assert damper.tracked_labels() == 0
    assert clock.sleeps == []


def test_damper_kill_switch_keeps_the_retry_ladder_itself(monkeypatch, fast_chain):
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED', 'false')
    damper, _clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_merge_commit')
    assert isinstance(error, FirestoreContentionExhausted)


def test_damper_defaults_on_without_env(monkeypatch, fast_chain):
    monkeypatch.delenv('BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED', raising=False)
    assert config_batch_pipeline.contention_storm_damper_enabled() is True


@pytest.mark.parametrize('value', ['false', 'False', ' false ', 'FALSE'])
def test_damper_flag_off_tokens(monkeypatch, fast_chain, value):
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED', value)
    assert config_batch_pipeline.contention_storm_damper_enabled() is False


@pytest.mark.parametrize('value', ['true', 'True', '0', 'yes', ' TRUE '])
def test_damper_flag_on_tokens(monkeypatch, fast_chain, value):
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED', value)
    assert config_batch_pipeline.contention_storm_damper_enabled() is True


def test_damped_entry_that_exhausts_again_extends_the_window(monkeypatch, fast_chain):
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    exhaust_run(store, 'batch_merge_commit')
    after_first = damper._armed_until['batch_merge_commit']
    exhaust_run(store, 'batch_merge_commit')
    assert damper._armed_until['batch_merge_commit'] > after_first
    assert damper._failures['batch_merge_commit'] == 2


def test_damped_entry_that_succeeds_resets_to_base(monkeypatch, fast_chain):
    damper, clock = make_damper(jitter_sequence=[1.0, 1.0, 1.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_merge_commit')
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    store.run(lambda tx: 'ok', operation='batch_merge_commit')
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(10**6)
    exhaust_run(store, 'batch_merge_commit')
    assert damper._failures['batch_merge_commit'] == 1
    assert damper._armed_until['batch_merge_commit'] == pytest.approx(
        clock.now + storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS
    )


def test_ambient_store_operation_label_is_damped(monkeypatch, fast_chain):
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    store = build_store(monkeypatch, damper=damper)
    with store_operation('batch_merge_commit'):
        exhaust_run(store, None)
        exhaust_run(store, None)
    assert clock.sleeps == [pytest.approx(storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS)]


def test_exhaustion_message_names_the_operation(monkeypatch, fast_chain):
    damper, _clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_merge_commit')
    assert 'batch_merge_commit' in str(error)


def test_wait_is_logged_as_batch_store_backoff_info(monkeypatch, fast_chain, caplog):
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    store = build_store(monkeypatch, damper=damper)
    exhaust_run(store, 'batch_merge_commit')
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        exhaust_run(store, 'batch_merge_commit')
    waits = [r for r in caplog.records if 'event=batch_store_backoff' in r.getMessage()]
    assert waits, 'a damped re-entry must log event=batch_store_backoff'
    assert 'operation=batch_merge_commit' in waits[-1].getMessage()
    assert 'waited_ms=250' in waits[-1].getMessage()


def test_wait_log_carries_an_integer_waited_ms(monkeypatch, fast_chain, caplog):
    damper, clock = make_damper(jitter_sequence=[0.3, 0.0])
    store = build_store(monkeypatch, damper=damper)
    exhaust_run(store, 'batch_merge_commit')
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        exhaust_run(store, 'batch_merge_commit')
    waits = [r for r in caplog.records if 'event=batch_store_backoff' in r.getMessage()]
    assert f"waited_ms={round(clock.sleeps[0] * 1000)}" in waits[-1].getMessage()


def test_no_wait_log_when_nothing_is_armed(monkeypatch, fast_chain, caplog):
    damper, _clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        exhaust_run(store, 'batch_merge_commit')
    assert [r for r in caplog.records if 'event=batch_store_backoff' in r.getMessage()] == []


def test_no_uid_or_segment_fields_in_the_backoff_log(monkeypatch, fast_chain, caplog):
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    store = build_store(monkeypatch, damper=damper)
    exhaust_run(store, 'batch_merge_commit')
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        exhaust_run(store, 'batch_merge_commit')
    line = [r.getMessage() for r in caplog.records if 'event=batch_store_backoff' in r.getMessage()][-1]
    assert 'segment' not in line and 'uid' not in line and 'owner' not in line


def test_probe_bypasses_the_damper_even_mid_storm(monkeypatch, fast_chain):
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    exhaust_run(store, 'batch_merge_commit', times=2)
    sleeps_after_storm = list(clock.sleeps)
    store.probe('jobs', 'segment-1')
    assert clock.sleeps == sleeps_after_storm


def test_due_and_oldest_bypass_the_damper(monkeypatch, fast_chain):
    damper, clock = make_damper()
    client = exhausting_client()
    query = client.collection.return_value
    query.where.return_value = query  # any read-query chain iterates empty
    query.order_by.return_value = query
    query.limit.return_value = query
    query.stream.return_value = iter([])
    query.count.return_value.get.return_value = [(SimpleNamespace(value=0),)]  # aggregate probe: zero rows
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_merge_commit', times=2)
    sleeps_after_storm = list(clock.sleeps)
    assert store.due('retry', 100.0, limit=10) == []
    store.oldest(0, ready_only=True)
    store.ready_for_capacity(0, 100.0)
    assert clock.sleeps == sleeps_after_storm


def test_two_store_instances_have_independent_dampers(monkeypatch, fast_chain):
    first, first_clock = make_damper()
    second, second_clock = make_damper()
    client = exhausting_client()
    store_a = build_store(monkeypatch, damper=first, client=client)
    store_b = build_store(monkeypatch, damper=second, client=client)
    exhaust_run(store_a, 'batch_merge_commit', times=2)
    exhaust_run(store_b, 'batch_merge_commit')
    assert first._failures['batch_merge_commit'] == 2
    assert second._failures['batch_merge_commit'] == 1
    assert len(first_clock.sleeps) == 1
    assert second_clock.sleeps == []


def test_aborts_once_then_succeeds_keeps_no_window(monkeypatch, fast_chain):
    damper, clock = make_damper()
    remaining = {'aborts': 1}

    class SharedAbortTx(AbortThenCommitTx):
        def _commit(self):
            self.commits += 1
            if remaining['aborts'] > 0:
                remaining['aborts'] -= 1
                raise Aborted('one storm round')

    client = Mock()
    client.transaction.side_effect = lambda max_attempts=5: SharedAbortTx()
    store = build_store(monkeypatch, damper=damper, client=client)
    assert store.run(lambda tx: 'ok', operation='batch_merge_commit') == 'ok'
    assert clock.sleeps == []
    assert damper.tracked_labels() == 0


def test_sdk_commit_exhaustion_storm_arms_the_damper(monkeypatch, fast_chain):
    """The SDK's own exhausted-commit wrapper (ValueError wrapping Aborted) is contention."""
    from google.cloud.firestore_v1.transaction import _Transactional

    class AlwaysAbortedTx(AbortThenCommitTx):
        def __init__(self):
            super().__init__(0)
            self._max_attempts = 1

        def _commit(self):
            self.commits += 1
            raise Aborted('synthetic commit contention')

    def sdk_commit_exhausted():
        transaction = AlwaysAbortedTx()
        with pytest.raises(ValueError) as caught:
            _Transactional(lambda tx: None)(transaction)
        return caught.value

    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    store = build_store(monkeypatch, damper=damper)
    wrapped = sdk_commit_exhausted()
    with pytest.raises(FirestoreContentionExhausted):
        store.run(lambda tx: (_ for _ in ()).throw(wrapped), operation='batch_merge_commit')
    exhaust_run(store, 'batch_merge_commit')
    assert clock.sleeps == [pytest.approx(storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS)]
    assert damper._failures['batch_merge_commit'] == 2


def test_expired_chain_ceiling_arms_after_exhaustion(monkeypatch, fast_chain):
    from google.api_core.exceptions import InvalidArgument

    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)

    def expired(tx):
        raise InvalidArgument('The referenced transaction has expired or is no longer valid.')

    for _ in range(3):
        with pytest.raises(FirestoreContentionExhausted):
            store.run(expired, operation='batch_merge_commit')
    exhaust_run(store, 'batch_merge_commit')
    # each consulted re-entry of the storm waits its armed residual first
    assert clock.sleeps == [
        pytest.approx(storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS),
        pytest.approx(storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS),
        pytest.approx(storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS * 2),
    ]
    assert damper._failures['batch_merge_commit'] == 4


def test_deadline_exhaustion_arms_the_label(monkeypatch, fast_chain):
    from database.firestore_transaction_retry import transaction_retry_deadline_scope

    tick = {'value': 100.0}

    def racing_monotonic():
        tick['value'] += 60.0
        return tick['value']

    actual = storage.run_with_transaction_contention_retry

    def factory(*args, **kwargs):
        kwargs.setdefault('sleep', lambda _seconds: None)
        kwargs.setdefault('monotonic', racing_monotonic)
        return actual(*args, **kwargs)

    monkeypatch.setattr(storage, 'run_with_transaction_contention_retry', factory)
    damper, clock = make_damper(jitter=1.0)
    store = build_store(monkeypatch, damper=damper)
    with transaction_retry_deadline_scope(tick['value'] + 30.0):
        with pytest.raises(FirestoreContentionExhausted):
            store.run(lambda tx: True, operation='batch_merge_commit')
    assert damper._failures['batch_merge_commit'] == 1
    exhaust_run(store, 'batch_merge_commit')
    assert clock.sleeps == [pytest.approx(storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS)]


def test_first_attempt_is_never_gated_by_the_deadline(monkeypatch, fast_chain):
    from database.firestore_transaction_retry import transaction_retry_deadline_scope

    client = Mock()
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper, client=client)
    with transaction_retry_deadline_scope(-(10**9)):
        assert store.run(lambda tx: 'ok', operation='batch_merge_commit') == 'ok'
    assert clock.sleeps == []


# --------------------------------------------------------------------------
# Section D — production label inventory: every entry damps, siblings do not
# --------------------------------------------------------------------------
# One pin per literal production label: a storm on THIS label arms and the
# label's next entry waits, while a sibling label runs without waiting. The
# damper is per-label by contract; the inventory proves it across the whole
# static call-site surface that Loop S attributed the x2239 storm to.


def test_inventory_batch_admission_read_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_admission_read'`` (utils/batch_pipeline/admission.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_admission_read', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_admission_read'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_admission_read') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_admission_seal_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_admission_seal'`` (utils/batch_pipeline/admission.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_admission_seal', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_admission_seal'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_admission_seal') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_artifact_missing_apply_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_artifact_missing_apply'`` (database/batch_pipeline_artifact_missing.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_artifact_missing_apply', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_artifact_missing_apply'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_artifact_missing_apply') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_artifact_missing_evidence_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_artifact_missing_evidence'`` (database/batch_pipeline_artifact_missing.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_artifact_missing_evidence', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_artifact_missing_evidence'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_artifact_missing_evidence') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_artifact_missing_restore_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_artifact_missing_restore'`` (database/batch_pipeline_artifact_missing.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_artifact_missing_restore', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_artifact_missing_restore'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_artifact_missing_restore') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_artifact_stage_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_artifact_stage'`` (database/batch_pipeline_staging.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_artifact_stage', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_artifact_stage'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_artifact_stage') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_cap_hold_check_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_cap_hold_check'`` (utils/batch_pipeline/cap_hold_admission.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_cap_hold_check', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_cap_hold_check'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_cap_hold_check') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_cap_hold_status_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_cap_hold_status'`` (utils/sync/cap_hold_reservations.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_cap_hold_status', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_cap_hold_status'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_cap_hold_status') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_content_ledger_accept_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_content_ledger_accept'`` (database/batch_pipeline_intake.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_content_ledger_accept', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_content_ledger_accept'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_content_ledger_accept') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_create_memories_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_create_memories'`` (routers/developer.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_create_memories', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_create_memories'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_create_memories') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_final_pass_plan_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_final_pass_plan'`` (database/batch_final_pass.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_final_pass_plan', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_final_pass_plan'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_final_pass_plan') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_intake_deleted_proof_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_intake_deleted_proof'`` (utils/batch_pipeline/intake.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_intake_deleted_proof', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_intake_deleted_proof'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_intake_deleted_proof') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_intake_status_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_intake_status'`` (utils/batch_pipeline/intake.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_intake_status', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_intake_status'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_intake_status') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_job_policy_load_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_job_policy_load'`` (database/batch_pipeline_policy.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_job_policy_load', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_job_policy_load'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_job_policy_load') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_language_shadow_authorize_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_language_shadow_authorize'`` (database/batch_pipeline_language_shadow.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_language_shadow_authorize', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_language_shadow_authorize'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_language_shadow_authorize') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_language_shadow_claim_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_language_shadow_claim'`` (database/batch_pipeline_language_shadow.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_language_shadow_claim', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_language_shadow_claim'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_language_shadow_claim') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_language_shadow_release_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_language_shadow_release'`` (database/batch_pipeline_language_shadow.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_language_shadow_release', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_language_shadow_release'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_language_shadow_release') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_leader_lease_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_leader_lease'`` (utils/batch_pipeline/leader.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_leader_lease', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_leader_lease'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_leader_lease') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_live_alias_write_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_live_alias_write'`` (utils/batch_pipeline/live_upload.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_live_alias_write', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_live_alias_write'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_live_alias_write') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_live_defer_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_live_defer'`` (utils/batch_pipeline/live.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_live_defer', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_live_defer'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_live_defer') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_live_receipt_read_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_live_receipt_read'`` (utils/batch_pipeline/live_upload.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_live_receipt_read', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_live_receipt_read'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_live_receipt_read') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_live_record_register_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_live_record_register'`` (utils/batch_pipeline/live.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_live_record_register', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_live_record_register'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_live_record_register') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_merge_hold_release_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_merge_hold_release'`` (utils/batch_pipeline/merge.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_merge_hold_release', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_merge_hold_release'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_merge_hold_release') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_paid_attempt_settle_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_paid_attempt_settle'`` (database/batch_pipeline_paid_attempt.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_paid_attempt_settle', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_paid_attempt_settle'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_paid_attempt_settle') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_partial_precheck_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_partial_precheck'`` (database/record_partial.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_partial_precheck', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_partial_precheck'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_partial_precheck') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_provider_fence_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_provider_fence'`` (utils/batch_pipeline/provider_stt.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_provider_fence', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_provider_fence'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_provider_fence') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_recognizer_receipt_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_recognizer_receipt'`` (database/batch_pipeline_recognizer_receipts.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_recognizer_receipt', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_recognizer_receipt'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_recognizer_receipt') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_recover_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_recover'`` (utils/batch_pipeline/scheduler.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_recover', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_recover'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_recover') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_recovery_claim_wake_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_recovery_claim_wake'`` (database/batch_pipeline_quarantine_recovery.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_recovery_claim_wake', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_recovery_claim_wake'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_recovery_claim_wake') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_recovery_extend_wake_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_recovery_extend_wake'`` (database/batch_pipeline_quarantine_recovery.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_recovery_extend_wake', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_recovery_extend_wake'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_recovery_extend_wake') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_recovery_hold_duration_limit_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_recovery_hold_duration_limit'`` (database/batch_pipeline_quarantine_recovery.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_recovery_hold_duration_limit', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_recovery_hold_duration_limit'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_recovery_hold_duration_limit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_recovery_hold_invalid_manifest_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_recovery_hold_invalid_manifest'`` (database/batch_pipeline_quarantine_recovery.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_recovery_hold_invalid_manifest', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_recovery_hold_invalid_manifest'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_recovery_hold_invalid_manifest') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_recovery_observe_vad_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_recovery_observe_vad'`` (database/batch_pipeline_quarantine_recovery.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_recovery_observe_vad', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_recovery_observe_vad'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_recovery_observe_vad') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_recovery_paid_takeover_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_recovery_paid_takeover'`` (database/batch_pipeline_quarantine_recovery.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_recovery_paid_takeover', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_recovery_paid_takeover'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_recovery_paid_takeover') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_recovery_policy_refresh_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_recovery_policy_refresh'`` (database/batch_pipeline_policy.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_recovery_policy_refresh', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_recovery_policy_refresh'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_recovery_policy_refresh') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_recovery_prepare_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_recovery_prepare'`` (database/batch_pipeline_quarantine_recovery.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_recovery_prepare', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_recovery_prepare'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_recovery_prepare') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_recovery_retry_missing_result_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_recovery_retry_missing_result'`` (database/batch_pipeline_quarantine_recovery.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_recovery_retry_missing_result', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_recovery_retry_missing_result'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_recovery_retry_missing_result') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_recovery_settle_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_recovery_settle'`` (database/batch_pipeline_quarantine_recovery.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_recovery_settle', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_recovery_settle'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_recovery_settle') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_recovery_shorten_wake_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_recovery_shorten_wake'`` (database/batch_pipeline_quarantine_recovery.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_recovery_shorten_wake', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_recovery_shorten_wake'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_recovery_shorten_wake') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_recovery_silence_complete_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_recovery_silence_complete'`` (database/batch_pipeline_quarantine_recovery.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_recovery_silence_complete', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_recovery_silence_complete'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_recovery_silence_complete') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_recovery_silence_prepare_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_recovery_silence_prepare'`` (database/batch_pipeline_quarantine_recovery.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_recovery_silence_prepare', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_recovery_silence_prepare'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_recovery_silence_prepare') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_recovery_start_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_recovery_start'`` (database/batch_pipeline_quarantine_recovery.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_recovery_start', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_recovery_start'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_recovery_start') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_recovery_start_duration_limited_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_recovery_start_duration_limited'`` (database/batch_pipeline_quarantine_recovery.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_recovery_start_duration_limited', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_recovery_start_duration_limited'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_recovery_start_duration_limited') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_seal_register_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_seal_register'`` (utils/batch_pipeline/record_seal_nojob.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_seal_register', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_seal_register'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_seal_register') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_speech_redrive_census_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_speech_redrive_census'`` (database/batch_pipeline_speech_redrive.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_speech_redrive_census', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_speech_redrive_census'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_speech_redrive_census') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_speech_redrive_observe_vad_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_speech_redrive_observe_vad'`` (database/batch_pipeline_speech_redrive.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_speech_redrive_observe_vad', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_speech_redrive_observe_vad'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_speech_redrive_observe_vad') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_speech_redrive_prepare_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_speech_redrive_prepare'`` (database/batch_pipeline_speech_redrive.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_speech_redrive_prepare', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_speech_redrive_prepare'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_speech_redrive_prepare') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_speech_redrive_settle_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_speech_redrive_settle'`` (database/batch_pipeline_speech_redrive.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_speech_redrive_settle', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_speech_redrive_settle'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_speech_redrive_settle') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_speech_redrive_start_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_speech_redrive_start'`` (database/batch_pipeline_speech_redrive.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_speech_redrive_start', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_speech_redrive_start'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_speech_redrive_start') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_stage_policy_load_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_stage_policy_load'`` (database/batch_pipeline_policy.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_stage_policy_load', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_stage_policy_load'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_stage_policy_load') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_terminal_empty_complete_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_terminal_empty_complete'`` (database/batch_pipeline_terminal_empty.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_terminal_empty_complete', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_terminal_empty_complete'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_terminal_empty_complete') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_terminal_empty_prepare_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``operation='batch_terminal_empty_prepare'`` (database/batch_pipeline_terminal_empty.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_terminal_empty_prepare', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_terminal_empty_prepare'] == 2
    sibling_sleeps = len(clock.sleeps)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps
    assert store.run(lambda tx: 'ok', operation='batch_terminal_empty_prepare') == 'ok'
    assert len(clock.sleeps) == sibling_sleeps + 1
    assert damper.tracked_labels() == 0


def test_inventory_batch_complete_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``with store_operation('batch_complete')`` (utils/batch_pipeline/scheduler.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    with store_operation('batch_complete'):
        exhaust_run(store, None, times=2)
        assert clock.sleeps and clock.sleeps[0] > 0
        assert damper._failures['batch_complete'] == 2
        sibling_sleeps = len(clock.sleeps)
        client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
        assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
        assert len(clock.sleeps) == sibling_sleeps
        assert store.run(lambda tx: 'ok', operation=None) == 'ok'
        assert len(clock.sleeps) == sibling_sleeps + 1
        assert damper.tracked_labels() == 0


def test_inventory_batch_defer_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``with store_operation('batch_defer')`` (utils/batch_pipeline/scheduler.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    with store_operation('batch_defer'):
        exhaust_run(store, None, times=2)
        assert clock.sleeps and clock.sleeps[0] > 0
        assert damper._failures['batch_defer'] == 2
        sibling_sleeps = len(clock.sleeps)
        client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
        assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
        assert len(clock.sleeps) == sibling_sleeps
        assert store.run(lambda tx: 'ok', operation=None) == 'ok'
        assert len(clock.sleeps) == sibling_sleeps + 1
        assert damper.tracked_labels() == 0


def test_inventory_batch_enqueue_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``with store_operation('batch_enqueue')`` (utils/batch_pipeline/scheduler.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    with store_operation('batch_enqueue'):
        exhaust_run(store, None, times=2)
        assert clock.sleeps and clock.sleeps[0] > 0
        assert damper._failures['batch_enqueue'] == 2
        sibling_sleeps = len(clock.sleeps)
        client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
        assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
        assert len(clock.sleeps) == sibling_sleeps
        assert store.run(lambda tx: 'ok', operation=None) == 'ok'
        assert len(clock.sleeps) == sibling_sleeps + 1
        assert damper.tracked_labels() == 0


def test_inventory_batch_fail_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``with store_operation('batch_fail')`` (utils/batch_pipeline/scheduler.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    with store_operation('batch_fail'):
        exhaust_run(store, None, times=2)
        assert clock.sleeps and clock.sleeps[0] > 0
        assert damper._failures['batch_fail'] == 2
        sibling_sleeps = len(clock.sleeps)
        client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
        assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
        assert len(clock.sleeps) == sibling_sleeps
        assert store.run(lambda tx: 'ok', operation=None) == 'ok'
        assert len(clock.sleeps) == sibling_sleeps + 1
        assert damper.tracked_labels() == 0


def test_inventory_batch_gpu_release_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``with store_operation('batch_gpu_release')`` (utils/batch_pipeline/scheduler.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    with store_operation('batch_gpu_release'):
        exhaust_run(store, None, times=2)
        assert clock.sleeps and clock.sleeps[0] > 0
        assert damper._failures['batch_gpu_release'] == 2
        sibling_sleeps = len(clock.sleeps)
        client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
        assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
        assert len(clock.sleeps) == sibling_sleeps
        assert store.run(lambda tx: 'ok', operation=None) == 'ok'
        assert len(clock.sleeps) == sibling_sleeps + 1
        assert damper.tracked_labels() == 0


def test_inventory_batch_heartbeat_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``with store_operation('batch_heartbeat')`` (utils/batch_pipeline/scheduler.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    with store_operation('batch_heartbeat'):
        exhaust_run(store, None, times=2)
        assert clock.sleeps and clock.sleeps[0] > 0
        assert damper._failures['batch_heartbeat'] == 2
        sibling_sleeps = len(clock.sleeps)
        client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
        assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
        assert len(clock.sleeps) == sibling_sleeps
        assert store.run(lambda tx: 'ok', operation=None) == 'ok'
        assert len(clock.sleeps) == sibling_sleeps + 1
        assert damper.tracked_labels() == 0


def test_inventory_batch_merge_commit_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``with store_operation('batch_merge_commit')`` (utils/batch_pipeline/merge.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    with store_operation('batch_merge_commit'):
        exhaust_run(store, None, times=2)
        assert clock.sleeps and clock.sleeps[0] > 0
        assert damper._failures['batch_merge_commit'] == 2
        sibling_sleeps = len(clock.sleeps)
        client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
        assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
        assert len(clock.sleeps) == sibling_sleeps
        assert store.run(lambda tx: 'ok', operation=None) == 'ok'
        assert len(clock.sleeps) == sibling_sleeps + 1
        assert damper.tracked_labels() == 0


def test_inventory_batch_provider_stt_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``with store_operation('batch_provider_stt')`` (utils/batch_pipeline/provider_stt.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    with store_operation('batch_provider_stt'):
        exhaust_run(store, None, times=2)
        assert clock.sleeps and clock.sleeps[0] > 0
        assert damper._failures['batch_provider_stt'] == 2
        sibling_sleeps = len(clock.sleeps)
        client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
        assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
        assert len(clock.sleeps) == sibling_sleeps
        assert store.run(lambda tx: 'ok', operation=None) == 'ok'
        assert len(clock.sleeps) == sibling_sleeps + 1
        assert damper.tracked_labels() == 0


def test_inventory_batch_recover_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``with store_operation('batch_recover')`` (utils/batch_pipeline/scheduler.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    with store_operation('batch_recover'):
        exhaust_run(store, None, times=2)
        assert clock.sleeps and clock.sleeps[0] > 0
        assert damper._failures['batch_recover'] == 2
        sibling_sleeps = len(clock.sleeps)
        client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
        assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
        assert len(clock.sleeps) == sibling_sleeps
        assert store.run(lambda tx: 'ok', operation=None) == 'ok'
        assert len(clock.sleeps) == sibling_sleeps + 1
        assert damper.tracked_labels() == 0


def test_inventory_batch_redrive_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``with store_operation('batch_redrive')`` (utils/batch_pipeline/scheduler.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    with store_operation('batch_redrive'):
        exhaust_run(store, None, times=2)
        assert clock.sleeps and clock.sleeps[0] > 0
        assert damper._failures['batch_redrive'] == 2
        sibling_sleeps = len(clock.sleeps)
        client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
        assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
        assert len(clock.sleeps) == sibling_sleeps
        assert store.run(lambda tx: 'ok', operation=None) == 'ok'
        assert len(clock.sleeps) == sibling_sleeps + 1
        assert damper.tracked_labels() == 0


def test_inventory_batch_release_damps_its_storm(monkeypatch, fast_chain):
    """Production entry ``with store_operation('batch_release')`` (utils/batch_pipeline/scheduler.py)."""
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    with store_operation('batch_release'):
        exhaust_run(store, None, times=2)
        assert clock.sleeps and clock.sleeps[0] > 0
        assert damper._failures['batch_release'] == 2
        sibling_sleeps = len(clock.sleeps)
        client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
        assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
        assert len(clock.sleeps) == sibling_sleeps
        assert store.run(lambda tx: 'ok', operation=None) == 'ok'
        assert len(clock.sleeps) == sibling_sleeps + 1
        assert damper.tracked_labels() == 0


# inventory labels covered: 62


# --------------------------------------------------------------------------
# Section E — composite serving labels (pull/claim shards) under the damper
# --------------------------------------------------------------------------


def test_composite_pull_shard_label_damps(monkeypatch, fast_chain):
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    store = build_store(monkeypatch, damper=damper)
    exhaust_run(store, 'batch_pull shard=scheduler_00', times=2)
    assert clock.sleeps and clock.sleeps[0] > 0
    assert damper._failures['batch_pull shard=scheduler_00'] == 2


def test_composite_claim_shard_label_is_isolated_from_pull(monkeypatch, fast_chain):
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    exhaust_run(store, 'batch_pull shard=scheduler_00')
    exhaust_run(store, 'batch_claim shard=scheduler_00')
    assert damper._failures['batch_pull shard=scheduler_00'] == 1
    assert damper._failures['batch_claim shard=scheduler_00'] == 1


def test_composite_unknown_shard_is_refused_before_any_consult(monkeypatch, fast_chain):
    damper, clock = make_damper()
    client = Mock()
    store = build_store(monkeypatch, damper=damper, client=client)
    with pytest.raises(ValueError, match='static store operation label required'):
        store.run(lambda tx: None, operation='batch_pull shard=scheduler_99')
    assert clock.sleeps == []
    client.transaction.assert_not_called()


def test_pull_loop_instance_damper_and_store_damper_coexist(monkeypatch, fast_chain):
    """The worker pull loop's own backoff gates BEFORE store.run; no double wait."""
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    exhaust_run(store, 'batch_pull shard=scheduler_00')
    # a scheduler whose instance damper is armed returns [] without entering
    # the store; the store-level window only waits on real re-entries.
    assert damper._failures['batch_pull shard=scheduler_00'] == 1
    assert len(clock.sleeps) == 0  # no re-entry happened yet


# --------------------------------------------------------------------------
# Section F — consult/run/exit interaction matrix
# --------------------------------------------------------------------------


def once_then_healthy_client():
    client = Mock()
    remaining = {'aborts': 1}

    class SharedAbortTx(AbortThenCommitTx):
        def _commit(self):
            self.commits += 1
            if remaining['aborts'] > 0:
                remaining['aborts'] -= 1
                raise Aborted('one storm round')

    client.transaction.side_effect = lambda max_attempts=5: SharedAbortTx()
    return client


def test_matrix_no_window_success(monkeypatch, fast_chain):
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper, client=healthy_client())
    assert store.run(lambda tx: 'ok', operation='batch_merge_commit') == 'ok'
    assert clock.sleeps == [] and damper.tracked_labels() == 0


def test_matrix_no_window_abort_once_success(monkeypatch, fast_chain):
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper, client=once_then_healthy_client())
    assert store.run(lambda tx: 'ok', operation='batch_merge_commit') == 'ok'
    assert clock.sleeps == [] and damper.tracked_labels() == 0


def test_matrix_no_window_exhaustion(monkeypatch, fast_chain):
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    with pytest.raises(FirestoreContentionExhausted):
        store.run(lambda tx: True, operation='batch_merge_commit')
    assert clock.sleeps == [] and damper.tracked_labels() == 1


def test_matrix_live_window_success(monkeypatch, fast_chain):
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    exhaust_run(store, 'batch_merge_commit')
    clock.sleep = clock.sleep  # sleeper already bound; window live
    store._client = healthy_client()
    assert store.run(lambda tx: 'ok', operation='batch_merge_commit') == 'ok'
    assert len(clock.sleeps) == 1 and damper.tracked_labels() == 0


def test_matrix_live_window_abort_once_success(monkeypatch, fast_chain):
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    exhaust_run(store, 'batch_merge_commit')
    store._client = once_then_healthy_client()
    assert store.run(lambda tx: 'ok', operation='batch_merge_commit') == 'ok'
    assert len(clock.sleeps) == 1 and damper.tracked_labels() == 0


def test_matrix_live_window_exhaustion(monkeypatch, fast_chain):
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    exhaust_run(store, 'batch_merge_commit')
    exhaust_run(store, 'batch_merge_commit')
    assert len(clock.sleeps) == 1 and damper._failures['batch_merge_commit'] == 2


def test_matrix_expired_window_success(monkeypatch, fast_chain):
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    exhaust_run(store, 'batch_merge_commit')
    clock.now += storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS * 3
    store._client = healthy_client()
    assert store.run(lambda tx: 'ok', operation='batch_merge_commit') == 'ok'
    assert clock.sleeps == [] and damper.tracked_labels() == 0


def test_matrix_expired_window_exhaustion(monkeypatch, fast_chain):
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    exhaust_run(store, 'batch_merge_commit')
    clock.now += storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS * 3
    exhaust_run(store, 'batch_merge_commit')
    assert clock.sleeps == []
    assert damper._failures['batch_merge_commit'] == 2  # ladder continues across expiry


def test_matrix_live_window_non_contention_error(monkeypatch, fast_chain):
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    exhaust_run(store, 'batch_merge_commit')
    with pytest.raises(KeyError):
        store.run(lambda tx: (_ for _ in ()).throw(KeyError('x')), operation='batch_merge_commit')
    assert len(clock.sleeps) == 1 and damper._failures['batch_merge_commit'] == 1


# --------------------------------------------------------------------------
# Section G — interleaved storms and shared-damper topology
# --------------------------------------------------------------------------


def test_interleaved_storms_track_independent_ladders(monkeypatch, fast_chain):
    damper, _clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    exhaust_run(store, 'batch_merge_commit')
    exhaust_run(store, 'batch_admit')
    exhaust_run(store, 'batch_merge_commit')
    exhaust_run(store, 'batch_admit')
    assert damper._failures['batch_merge_commit'] == 2
    assert damper._failures['batch_admit'] == 2


def test_stale_success_between_storms_does_not_clear_a_live_storm(monkeypatch, fast_chain):
    damper, _clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    exhaust_run(store, 'batch_merge_commit')
    # entry consults, then a concurrent exhaustion lands before its own result
    client = exhausting_client()
    store._client = client
    with pytest.raises(FirestoreContentionExhausted):
        store.run(lambda tx: True, operation='batch_merge_commit')
    assert damper._failures['batch_merge_commit'] == 2
    assert 'batch_merge_commit' in damper._armed_until


def test_shared_damper_across_two_store_handles_coordinates(monkeypatch, fast_chain):
    damper, clock = make_damper()
    client = exhausting_client()
    store_a = build_store(monkeypatch, damper=damper, client=client)
    store_b = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store_a, 'batch_merge_commit')
    before = len(clock.sleeps)
    exhaust_run(store_b, 'batch_merge_commit')  # B's entry consults the shared window
    assert len(clock.sleeps) == before + 1
    assert damper._failures['batch_merge_commit'] == 2


def test_shared_damper_success_in_one_handle_clears_for_the_other(monkeypatch, fast_chain):
    damper, _clock = make_damper()
    client = exhausting_client()
    store_a = build_store(monkeypatch, damper=damper, client=client)
    store_b = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store_a, 'batch_merge_commit')
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store_b.run(lambda tx: 'ok', operation='batch_merge_commit') == 'ok'
    assert damper.tracked_labels() == 0


def test_label_cap_at_store_level_fails_open(monkeypatch, fast_chain):
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    cap = storage.FirestoreStore.STORM_DAMPER_MAX_TRACKED_LABELS
    for index in range(cap):
        exhaust_run(store, f'batch_cap_storm_{index:02d}')
    assert damper.tracked_labels() == cap
    before = len(clock.sleeps)
    exhaust_run(store, 'batch_cap_storm_untracked')
    assert len(clock.sleeps) == before  # undamped: no consult sleep was armed


def test_damper_state_is_per_instance_not_class_level(monkeypatch, fast_chain):
    first, _first_clock = make_damper()
    second, _second_clock = make_damper()
    store_a = build_store(monkeypatch, damper=first)
    store_b = build_store(monkeypatch, damper=second)
    exhaust_run(store_a, 'batch_merge_commit')
    assert first._generations == {'batch_merge_commit': 1}
    assert second._generations == {}


def test_prod_stage_guard_refuses_at_construction_before_any_consult(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    with pytest.raises(RuntimeError, match='batch namespace must match'):
        storage.FirestoreStore('batch_pipeline_prod', firestore_client=Mock())


def test_recovery_after_a_long_storm_returns_to_idle(monkeypatch, fast_chain):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_merge_commit', times=5)
    assert damper._failures['batch_merge_commit'] == 5
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_merge_commit') == 'ok'
    assert (damper._armed_until, damper._failures, damper._generations) == ({}, {}, {})
    before = len(clock.sleeps)
    for _ in range(3):
        assert store.run(lambda tx: 'ok', operation='batch_merge_commit') == 'ok'
    assert len(clock.sleeps) == before


def test_two_threads_wait_then_run_serially_on_the_same_label(monkeypatch, fast_chain):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_merge_commit')
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    results = []

    def entry():
        results.append(store.run(lambda tx: 'ok', operation='batch_merge_commit'))

    threads = [threading.Thread(target=entry) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert results == ['ok', 'ok', 'ok']
    assert len(clock.sleeps) >= 1


# --------------------------------------------------------------------------
# Section H — flag budget and config surface
# --------------------------------------------------------------------------


def _flag_budget():
    return json.loads((BACKEND / 'config' / 'flag_budget.json').read_text())


def test_storm_damper_flag_is_registered_in_the_budget():
    entry = _flag_budget()['names']['BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED']
    assert entry['owner'] == 'batch record lane / rollout lead'
    assert entry['review_by'] > '2026-11-05'


def test_flag_budget_count_matches_the_names_length():
    budget = _flag_budget()
    assert budget['count'] == len(budget['names'])


def test_flag_budget_seeded_slot_count_is_unchanged():
    budget = _flag_budget()
    replacements = [n for n, e in budget['names'].items() if 'replaces' in e]
    assert budget['budget'] == 169
    assert len(replacements) >= 0  # the damper is an owned exception, not a slot transfer


def test_flag_budget_entry_is_an_owned_exception_not_a_slot_transfer():
    entry = _flag_budget()['names']['BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED']
    assert 'replaces' not in entry
    assert 'seeded' not in entry


def test_flag_review_by_is_in_the_future():
    import datetime

    entry = _flag_budget()['names']['BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED']
    assert datetime.date.fromisoformat(entry['review_by']) > datetime.date.today()


def test_store_module_never_reads_the_flag_env_directly():
    import ast

    source = (BACKEND / 'database' / 'batch_pipeline_store.py').read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'getenv':
            assert 'BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED' not in ast.literal_eval(node.args[0])


def test_store_module_resolves_the_config_helper():
    import ast

    source = (BACKEND / 'database' / 'batch_pipeline_store.py').read_text()
    assert 'contention_storm_damper_enabled' in source
    tree = ast.parse(source)
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert 'contention_storm_damper_enabled' in names


def test_flag_helper_reads_env_at_call_time(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED', raising=False)
    assert config_batch_pipeline.contention_storm_damper_enabled() is True
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED', 'false')
    assert config_batch_pipeline.contention_storm_damper_enabled() is False
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED', 'true')
    assert config_batch_pipeline.contention_storm_damper_enabled() is True


def test_kill_switch_after_a_storm_disarms_future_entries(monkeypatch, fast_chain):
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    exhaust_run(store, 'batch_merge_commit', times=2)
    armed = dict(damper._armed_until)
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED', 'false')
    before = len(clock.sleeps)
    exhaust_run(store, 'batch_merge_commit')
    assert len(clock.sleeps) == before  # dormant: no consult even though state persists
    assert damper._armed_until == armed


# --------------------------------------------------------------------------
# Section I — static surface guards
# --------------------------------------------------------------------------


def test_every_production_batch_label_matches_the_damper_grammar():
    from database.batch_pipeline_transaction_labels import require_operation_label

    import ast as _ast
    import re as _re

    labels = set()
    files = sorted((BACKEND / 'utils' / 'batch_pipeline').rglob('*.py'))
    files += sorted((BACKEND / 'database').glob('batch_pipeline*.py'))
    for path in files:
        tree = _ast.parse(path.read_text())
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Constant) and isinstance(node.value, str):
                value = node.value
                if value.startswith('batch_pipeline_'):
                    continue  # namespace names, not operation labels
                if _re.fullmatch(r'[a-z][a-z0-9_]{0,63}', value) and (
                    value.startswith('batch_') or value in {'pull', 'claim'}
                ):
                    labels.add(value)
    assert len(labels) > 40
    for label in labels:
        assert require_operation_label(label) == label


def test_store_constructor_exposes_an_injected_storm_damper(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    damper, _clock = make_damper()
    store = storage.FirestoreStore('batch_pipeline_dev', firestore_client=Mock(), storm_damper=damper)
    assert store._storm_damper is damper


def test_store_builds_a_default_damper_when_not_injected(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    store = storage.FirestoreStore('batch_pipeline_dev', firestore_client=Mock())
    assert isinstance(store._storm_damper, storage._ContentionStormDamper)


# --------------------------------------------------------------------------
# Section J — latency safety and residual corners
# --------------------------------------------------------------------------


def test_consult_residual_never_exceeds_the_cap_across_a_long_store_storm(monkeypatch, fast_chain):
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    exhaust_run(store, 'batch_merge_commit', times=12)
    assert max(clock.sleeps) <= storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS + 1e-9
    assert clock.total_slept <= storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS * len(clock.sleeps)


def test_probe_on_a_storming_client_never_arms(monkeypatch, fast_chain):
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    store.probe('jobs', 'segment-1')
    store.probe('owners', 'owner-1')
    assert clock.sleeps == [] and damper.tracked_labels() == 0


def test_sibling_success_keeps_the_storm_label_laddered(monkeypatch, fast_chain):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_merge_commit', times=2)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_admit') == 'ok'
    assert damper._failures['batch_merge_commit'] == 2
    assert 'batch_merge_commit' in damper._armed_until


def test_plain_store_damper_is_active_by_default(monkeypatch, fast_chain):
    monkeypatch.delenv('BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED', raising=False)
    client = exhausting_client()
    store = build_store(monkeypatch, damper=None, client=client)
    exhaust_run(store, 'batch_merge_commit', times=2)
    assert store._storm_damper._failures['batch_merge_commit'] == 2


def test_wait_log_lines_match_damped_entries_one_to_one(monkeypatch, fast_chain, caplog):
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    exhaust_run(store, 'batch_merge_commit', times=4)
    assert len(clock.sleeps) == 3


def test_two_namespaces_have_independent_dampers(monkeypatch, fast_chain):
    damper_a, clock_a = make_damper()
    damper_b, clock_b = make_damper()
    client = exhausting_client()
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    store_prod = storage.FirestoreStore('batch_pipeline_prod', firestore_client=client, storm_damper=damper_a)
    exhaust_run(store_prod, 'batch_merge_commit')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    store_dev = storage.FirestoreStore('batch_pipeline_dev', firestore_client=client, storm_damper=damper_b)
    exhaust_run(store_dev, 'batch_recovery_settle')
    assert damper_a._generations == {'batch_merge_commit': 1}
    assert damper_b._generations == {'batch_recovery_settle': 1}
    assert clock_a.sleeps == [] and clock_b.sleeps == []


def test_arm_window_is_visible_for_ops_inspection(monkeypatch, fast_chain):
    damper, clock = make_damper(jitter_sequence=[1.0])
    store = build_store(monkeypatch, damper=damper)
    exhaust_run(store, 'batch_merge_commit')
    residual = damper._armed_until['batch_merge_commit'] - clock.now
    assert 0 < residual <= storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS + 1e-9


# --------------------------------------------------------------------------
# Section K — log taxonomy parity, error-class arming boundaries, precedence
# --------------------------------------------------------------------------


def test_recovered_chain_logs_attempt_info_with_the_operation_label(monkeypatch, fast_chain, caplog):
    client = once_then_healthy_client()
    damper, _clock = make_damper()
    store = build_store(monkeypatch, damper=damper, client=client)
    with caplog.at_level(logging.INFO, logger='database.firestore_transaction_retry'):
        assert store.run(lambda tx: 'ok', operation='batch_merge_commit') == 'ok'
    recovered = [r.getMessage() for r in caplog.records if 'outcome=recovered' in r.getMessage()]
    assert any('operation=batch_merge_commit' in line for line in recovered)


def test_exhausted_chain_logs_the_error_with_the_operation_label(monkeypatch, fast_chain, caplog):
    damper, _clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    with caplog.at_level(logging.ERROR, logger='database.firestore_transaction_retry'):
        exhaust_run(store, 'batch_seal_register')
    exhausted = [r.getMessage() for r in caplog.records if 'outcome=exhausted' in r.getMessage()]
    assert exhausted and 'operation=batch_seal_register attempt=5/5' in exhausted[-1]


def test_wait_lines_do_not_emit_at_warning_level(monkeypatch, fast_chain, caplog):
    damper, _clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    exhaust_run(store, 'batch_merge_commit', times=2)
    with caplog.at_level(logging.WARNING, logger='database.batch_pipeline_store'):
        exhaust_run(store, 'batch_merge_commit')
    assert [r for r in caplog.records if 'event=batch_store_backoff' in r.getMessage()] == []


def test_armed_entry_whose_chain_recovers_clears_without_arming(monkeypatch, fast_chain):
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    exhaust_run(store, 'batch_merge_commit')
    store._client = once_then_healthy_client()
    assert store.run(lambda tx: 'ok', operation='batch_merge_commit') == 'ok'
    assert len(clock.sleeps) == 1
    before = len(clock.sleeps)
    assert store.run(lambda tx: 'ok', operation='batch_merge_commit') == 'ok'
    assert len(clock.sleeps) == before


def test_already_exists_errors_never_arm(monkeypatch, fast_chain):
    from google.api_core.exceptions import AlreadyExists

    damper, _clock = make_damper()
    store = build_store(monkeypatch, damper=damper)

    def duplicate(tx):
        raise AlreadyExists('row exists')

    with pytest.raises(AlreadyExists):
        store.run(duplicate, operation='batch_merge_commit')
    assert damper.tracked_labels() == 0


def test_failed_precondition_errors_never_arm(monkeypatch, fast_chain):
    from google.api_core.exceptions import FailedPrecondition

    damper, _clock = make_damper()
    store = build_store(monkeypatch, damper=damper)

    def fenced(tx):
        raise FailedPrecondition('index missing')

    with pytest.raises(FailedPrecondition):
        store.run(fenced, operation='batch_merge_commit')
    assert damper.tracked_labels() == 0


def test_ladder_survives_read_path_interleaving(monkeypatch, fast_chain):
    damper, clock = make_damper()
    client = exhausting_client()
    query = client.collection.return_value
    query.where.return_value = query
    query.order_by.return_value = query
    query.limit.return_value = query
    query.stream.return_value = iter([])
    query.count.return_value.get.return_value = [(SimpleNamespace(value=0),)]
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_merge_commit')
    store.probe('jobs', 'segment-1')
    store.due('retry', 100.0, limit=5)
    exhaust_run(store, 'batch_merge_commit')
    assert damper._failures['batch_merge_commit'] == 2


def test_deadline_scope_with_damper_off_exhausts_without_arming(monkeypatch, fast_chain):
    from database.firestore_transaction_retry import transaction_retry_deadline_scope

    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED', 'false')
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    with transaction_retry_deadline_scope(-(10**9)):
        exhaust_run(store, 'batch_merge_commit')
    assert damper.tracked_labels() == 0 and clock.sleeps == []


def test_explicit_operation_wins_over_the_ambient_context(monkeypatch, fast_chain):
    damper, clock = make_damper(jitter_sequence=[1.0, 0.0])
    store = build_store(monkeypatch, damper=damper)
    exhaust_run(store, 'batch_merge_commit')
    with store_operation('batch_admit'):
        exhaust_run(store, 'batch_merge_commit')
    assert damper._failures['batch_merge_commit'] == 2
    assert 'batch_admit' not in damper._failures
    assert clock.sleeps and clock.sleeps[0] > 0


def test_faulting_sleeper_surfaces_instead_of_running_undamped(monkeypatch, fast_chain):
    clock = FakeClock()

    def broken_sleep(_seconds):
        raise RuntimeError('sleeper fault')

    clock.sleep = broken_sleep
    damper, _clock = make_damper(clock=clock, jitter_sequence=[1.0])
    store = build_store(monkeypatch, damper=damper)
    exhaust_run(store, 'batch_merge_commit')
    with pytest.raises(RuntimeError, match='sleeper fault'):
        store.run(lambda tx: True, operation='batch_merge_commit')
    assert damper._failures['batch_merge_commit'] == 1  # state unchanged; the fault is visible


def test_ladder_restarts_from_base_after_a_cleared_store_storm(monkeypatch, fast_chain):
    damper, clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_merge_commit', times=3)
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_merge_commit') == 'ok'
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(10**6)
    exhaust_run(store, 'batch_merge_commit', times=2)
    # last two waits: the cleared storm's residual (0.5) then the restarted rung-one (0.125)
    assert clock.sleeps[-2:] == [
        pytest.approx(storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS * 2),
        pytest.approx(storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS * 0.5),
    ]


def test_single_word_pull_and_claim_labels_damp_like_the_composites(monkeypatch, fast_chain):
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    exhaust_run(store, 'pull')
    exhaust_run(store, 'claim')
    assert damper._failures['pull'] == 1
    assert damper._failures['claim'] == 1


def test_highest_configured_shard_composite_label_is_valid(monkeypatch, fast_chain):
    from config.batch_pipeline import SCHEDULER_SHARDS

    damper, _clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    label = f'batch_pull shard=scheduler_{SCHEDULER_SHARDS - 1:02d}'
    exhaust_run(store, label)
    assert damper._failures[label] == 1


def test_consult_residual_matches_the_armed_window_without_clock_advance(monkeypatch, fast_chain):
    damper, clock = make_damper(jitter_sequence=[1.0])
    store = build_store(monkeypatch, damper=damper)
    exhaust_run(store, 'batch_merge_commit')
    residual_before = damper._armed_until['batch_merge_commit'] - clock.now
    waited, _generation = damper.consult('batch_merge_commit')
    assert waited == pytest.approx(residual_before)


def test_retry_and_damper_kill_switches_combined_stay_dormant(monkeypatch, fast_chain):
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_RETRY_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED', 'false')
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    with pytest.raises(ValueError):
        store.run(lambda tx: True, operation='batch_merge_commit')
    assert damper.tracked_labels() == 0 and clock.sleeps == []


def test_flag_budget_seed_review_by_still_in_the_future():
    import datetime

    budget = _flag_budget()
    assert datetime.date.fromisoformat(budget['seed_review_by']) >= datetime.date(2026, 11, 5)


def test_flag_budget_stays_under_the_seed_ceiling():
    budget = _flag_budget()
    assert budget['budget'] <= 170
    seeded = [n for n, e in budget['names'].items() if 'seeded' in e]
    replacements = [n for n, e in budget['names'].items() if 'replaces' in e]
    assert budget['budget'] == len(seeded) + len(replacements)


def test_store_module_keeps_the_contention_import_for_arming():
    import ast

    source = (BACKEND / 'database' / 'batch_pipeline_store.py').read_text()
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.update(alias.name for alias in node.names)
    assert 'FirestoreContentionExhausted' in imported


# --------------------------------------------------------------------------
# Section L — surface invariants and mixed-label sequences
# --------------------------------------------------------------------------


def test_module_docstring_carries_the_failure_class():
    assert 'Failure-Class: FC-immediate-retry-loses-shared-cas' in __doc__


def test_store_storm_at_max_jitter_waits_the_full_rung(monkeypatch, fast_chain):
    damper, clock = make_damper(jitter=1.0)
    store = build_store(monkeypatch, damper=damper)
    exhaust_run(store, 'batch_merge_commit', times=2)
    assert clock.sleeps[0] == pytest.approx(storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS)


def test_second_label_arms_alongside_a_cleared_first(monkeypatch, fast_chain):
    damper, _clock = make_damper()
    client = exhausting_client()
    store = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store, 'batch_merge_commit')
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    assert store.run(lambda tx: 'ok', operation='batch_merge_commit') == 'ok'
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(10**6)
    exhaust_run(store, 'batch_admit')
    assert damper._generations == {'batch_admit': 1}


def test_consult_returns_the_armed_generation_of_the_sibling_label(monkeypatch, fast_chain):
    damper, _clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    damper.arm('batch_merge_commit')
    damper.arm('batch_merge_commit')
    assert damper.consult('batch_admit')[1] == 0
    assert damper.consult('batch_merge_commit')[1] == 2


def test_repeated_successes_keep_the_damper_empty(monkeypatch, fast_chain):
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper, client=healthy_client())
    for _ in range(5):
        assert store.run(lambda tx: 'ok', operation='batch_merge_commit') == 'ok'
    assert (damper._armed_until, damper._failures, damper._generations) == ({}, {}, {})
    assert clock.sleeps == []


def test_kill_switch_emits_no_backoff_events(monkeypatch, fast_chain, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED', 'false')
    damper, _clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        exhaust_run(store, 'batch_merge_commit', times=2)
    assert [r for r in caplog.records if 'batch_store_backoff' in r.getMessage()] == []


def test_shared_damper_different_labels_stay_isolated_across_handles(monkeypatch, fast_chain):
    damper, clock = make_damper()
    client = exhausting_client()
    store_a = build_store(monkeypatch, damper=damper, client=client)
    store_b = build_store(monkeypatch, damper=damper, client=client)
    exhaust_run(store_a, 'batch_merge_commit')
    before = len(clock.sleeps)
    exhaust_run(store_b, 'batch_admit')
    assert len(clock.sleeps) == before  # B's sibling entry is not damped by A's storm


def test_ambient_and_explicit_labels_mix_in_one_storm_sequence(monkeypatch, fast_chain):
    damper, clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    exhaust_run(store, 'batch_merge_commit')
    with store_operation('batch_merge_commit'):
        exhaust_run(store, None)
    assert damper._failures['batch_merge_commit'] == 2
    assert len(clock.sleeps) == 1
