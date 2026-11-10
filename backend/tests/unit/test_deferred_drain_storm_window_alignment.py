"""Deferred-drain re-strikes land after the store's armed storm window.

When a drained ordered-merge chain exhausts its contention budget,
``FirestoreStore.run`` arms the label's storm-damper window and now stamps
the window it actually applied onto the raised
``FirestoreContentionExhausted.retry_after``. The pump's deferred
publication-drain lane reads that measured signal and lands its re-drain
after the armed window instead of colliding inside it: without the signal
every lane attempt waited out the same window inside ``store.run``, burned
all five chain attempts against the same hot document, and repeated that
lockstep burn until the six-attempt budget died — the
``event=batch_merge outcome=retry exception_type=FirestoreContentionExhausted``
production signature. The signal never changes the lane's attempt budget or
its ceiling; a storm shifts when the next attempt lands.

Failure-Class: FC-deferred-drain-restrike-collides-inside-the-armed-storm-window
"""

import asyncio
import contextlib
import math
import types
from pathlib import Path
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import Aborted

from database import batch_pipeline_store as storage
from database.firestore_transaction_retry import FirestoreContentionExhausted
import utils.batch_pipeline.pump as pump_module
from utils.batch_pipeline.pump import Pump

try:
    # Parent revisions without the alignment collect fine and fail at
    # runtime below — that runtime failure is the RED half of the proof.
    from utils.batch_pipeline.pump import (
        DRAIN_RETRY_MAX_SECONDS,
        contention_retry_after,
        deferred_drain_delay,
    )
except ImportError:
    pass


BACKEND_CAP_SECONDS = storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS
BASE_SECONDS = storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS


# --------------------------------------------------------------------------
# Harnesses (mirroring the storm-damper and deferred-drain suites)
# --------------------------------------------------------------------------


class AbortThenCommitTx:
    """Minimal firestore_v1.Transaction: commits abort forever."""

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

    def __init__(self, now=100.0, jitter=1.0):
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

    def advance(self, seconds):
        self.now += seconds


def make_damper(clock=None):
    clock = clock or FakeClock()
    return (
        storage._ContentionStormDamper(monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value),
        clock,
    )


def exhausting_client():
    client = Mock()
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(10**6)
    return client


def build_store(monkeypatch, damper=None, client=None):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    return storage.FirestoreStore(
        'batch_pipeline_dev',
        firestore_client=client if client is not None else exhausting_client(),
        storm_damper=damper,
    )


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


@pytest.fixture(autouse=True)
def fast_chain(monkeypatch):
    """Skip the retry chain's own jitter sleeps; the damper's stay injected."""
    actual = storage.run_with_transaction_contention_retry

    def factory(*args, **kwargs):
        kwargs.setdefault('sleep', lambda _seconds: None)
        return actual(*args, **kwargs)

    monkeypatch.setattr(storage, 'run_with_transaction_contention_retry', factory)


class ScriptMerge:
    def __init__(self, script=None):
        self.held_owners = set()
        self.drained = []
        self.commits = 0
        self.script = list(script or [])

    def commit_next(self, owner_id, now):
        self.drained.append(owner_id)
        self.commits += 1
        if self.script:
            step = self.script.pop(0)
            if isinstance(step, BaseException):
                raise step
            return step
        return None


def make_pump(merge=None, clock=None):
    pump = Pump(
        types.SimpleNamespace(),
        types.SimpleNamespace(),
        merge=merge or ScriptMerge(),
        publish_concurrency=1,
    )
    pump._monotonic = clock.monotonic if clock is not None else (lambda: 100.0)
    return pump


async def drain_lane_hygiene(pump):
    pump._deferred_stopped = True
    lane = pump.__dict__.get('_deferred_lane')
    if lane is not None and not lane.done():
        lane.cancel()
        with contextlib.suppress(asyncio.CancelledError, RuntimeError):
            await lane


# --------------------------------------------------------------------------
# The store stamps the applied window on the exhausted chain
# --------------------------------------------------------------------------


def test_exhaustion_stamps_the_damper_window_on_the_exception(monkeypatch):
    damper, _clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_merge_commit')
    assert isinstance(error, FirestoreContentionExhausted)
    # Jitter pinned to 1.0: the applied window is exactly the ladder's first rung.
    assert error.retry_after == pytest.approx(BASE_SECONDS)
    assert 0 < error.retry_after <= BACKEND_CAP_SECONDS


def test_stamped_window_ladders_with_repeated_exhaustions(monkeypatch):
    damper, _clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    seen = []
    for _ in range(3):
        error = exhaust_run(store, 'batch_merge_commit')
        seen.append(error.retry_after)
    assert seen[0] == pytest.approx(BASE_SECONDS)
    assert seen[1] == pytest.approx(BASE_SECONDS * 2)
    assert seen[2] == pytest.approx(BASE_SECONDS * 4)
    assert max(seen) <= BACKEND_CAP_SECONDS


def test_exhaustion_without_a_damper_keeps_retry_after_zero(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED', 'false')
    store = build_store(monkeypatch, damper=None)
    error = exhaust_run(store, 'batch_merge_commit')
    assert error.retry_after == 0.0


def test_foreign_label_exhaustion_does_not_stamp_the_drain_label(monkeypatch):
    damper, _clock = make_damper()
    store = build_store(monkeypatch, damper=damper)
    error = exhaust_run(store, 'batch_admit')
    assert error.retry_after > 0
    # The drain label itself stays unarmed: its own next re-drain consults nothing.
    assert 'batch_merge_commit' not in damper._armed_until


def test_exception_default_carries_no_window():
    error = FirestoreContentionExhausted('exhausted')
    assert error.retry_after == 0.0
    assert error.reason == 'attempts_exhausted'


# --------------------------------------------------------------------------
# The pump helper sanitizes the signal
# --------------------------------------------------------------------------


def test_helper_reads_only_a_positive_finite_stamped_window():
    assert contention_retry_after(None) == 0.0
    assert contention_retry_after(RuntimeError('not contention')) == 0.0
    assert contention_retry_after(FirestoreContentionExhausted('no damper')) == 0.0
    assert contention_retry_after(FirestoreContentionExhausted('stamped', retry_after=3.5)) == 3.5


def test_helper_rejects_hostile_and_malformed_values():
    class Weird:
        retry_after = '3.5'

    assert contention_retry_after(Weird()) == 0.0
    assert contention_retry_after(types.SimpleNamespace(retry_after=True)) == 0.0
    assert contention_retry_after(types.SimpleNamespace(retry_after=float('nan'))) == 0.0
    assert contention_retry_after(types.SimpleNamespace(retry_after=-1.0)) == 0.0
    assert contention_retry_after(types.SimpleNamespace(retry_after=float('inf'))) == 0.0


def test_helper_clamps_to_the_lane_max_step():
    assert contention_retry_after(FirestoreContentionExhausted('huge', retry_after=10_000.0)) == DRAIN_RETRY_MAX_SECONDS
    assert DRAIN_RETRY_MAX_SECONDS == 8.0


# --------------------------------------------------------------------------
# The lane arms its re-drain after the armed window
# --------------------------------------------------------------------------


async def test_contention_loss_arms_the_re_drain_after_the_storm_window():
    clock = FakeClock(now=1000.0, jitter=0.0)
    merge = ScriptMerge(script=[FirestoreContentionExhausted('storm', retry_after=3.5), None])
    pump = make_pump(merge, clock=clock)
    try:
        await pump._drain_after_publication('owner-a')
        armed = pump._deferred_drains['owner-a']
        assert armed['attempts'] == 1
        # The storm window (3.5s) outruns the documented first step (0.5s).
        assert armed['due_at'] == pytest.approx(clock.now + 3.5)
    finally:
        await drain_lane_hygiene(pump)


async def test_ladder_step_that_outruns_the_storm_wins():
    clock = FakeClock(now=1000.0, jitter=0.0)
    merge = ScriptMerge(script=[FirestoreContentionExhausted('storm', retry_after=0.25), None])
    pump = make_pump(merge, clock=clock)
    try:
        await pump._drain_after_publication('owner-a')
        armed = pump._deferred_drains['owner-a']
        # Attempt 1's documented step (0.5s) already clears the 0.25s window.
        assert armed['due_at'] == pytest.approx(clock.now + deferred_drain_delay(1))
    finally:
        await drain_lane_hygiene(pump)


async def test_storm_signal_is_clamped_to_the_lane_max_step():
    clock = FakeClock(now=1000.0, jitter=0.0)
    merge = ScriptMerge(script=[FirestoreContentionExhausted('huge', retry_after=9.0), None])
    pump = make_pump(merge, clock=clock)
    try:
        await pump._drain_after_publication('owner-a')
        assert pump._deferred_drains['owner-a']['due_at'] == pytest.approx(clock.now + DRAIN_RETRY_MAX_SECONDS)
    finally:
        await drain_lane_hygiene(pump)


async def test_non_contention_loss_keeps_the_legacy_schedule():
    clock = FakeClock(now=1000.0, jitter=0.0)
    merge = ScriptMerge(script=[RuntimeError('storage down'), None])
    pump = make_pump(merge, clock=clock)
    try:
        await pump._drain_after_publication('owner-a')
        armed = pump._deferred_drains['owner-a']
        assert armed['due_at'] == pytest.approx(clock.now + deferred_drain_delay(1))
    finally:
        await drain_lane_hygiene(pump)


async def test_exhaustion_without_a_stamped_window_keeps_the_legacy_schedule():
    clock = FakeClock(now=1000.0, jitter=0.0)
    merge = ScriptMerge(script=[FirestoreContentionExhausted('no damper in scope'), None])
    pump = make_pump(merge, clock=clock)
    try:
        await pump._drain_after_publication('owner-a')
        assert pump._deferred_drains['owner-a']['due_at'] == pytest.approx(clock.now + deferred_drain_delay(1))
    finally:
        await drain_lane_hygiene(pump)


async def test_storm_alignment_never_spends_extra_attempt_budget():
    clock = FakeClock(now=1000.0, jitter=0.0)
    pump = make_pump(ScriptMerge(), clock=clock)
    try:
        for attempt in range(1, 7):
            assert pump._defer_drain('owner-a', attempts=attempt - 1, retry_after=4.0) is True
            armed = pump._deferred_drains['owner-a']
            assert armed['attempts'] == attempt
            assert armed['due_at'] == pytest.approx(clock.now + max(deferred_drain_delay(attempt), 4.0))
        # The cap is the cap: alignment never buys a seventh attempt.
        assert pump._defer_drain('owner-a', attempts=6, retry_after=4.0) is False
        assert 'owner-a' not in pump._deferred_drains
    finally:
        await drain_lane_hygiene(pump)


async def test_continuation_reoffer_after_contention_loss_waits_out_the_storm():
    clock = FakeClock(now=1000.0, jitter=0.0)
    pump = make_pump(ScriptMerge(), clock=clock)
    try:
        assert pump._defer_drain('owner-a', continuation=True, retry_after=2.0) is True
        armed = pump._deferred_drains['owner-a']
        assert armed['continuation'] is True
        # A continuation re-offers at once only when the bound ended the
        # drain; a contention loss lands after the armed window.
        assert armed['due_at'] == pytest.approx(clock.now + 2.0)
        assert pump._defer_drain('owner-b', continuation=True) is True
        assert pump._deferred_drains['owner-b']['due_at'] == pytest.approx(clock.now)
    finally:
        await drain_lane_hygiene(pump)


# --------------------------------------------------------------------------
# End to end: the due lane drains after the window and converges
# --------------------------------------------------------------------------


async def test_lane_drains_after_the_armed_window_and_converges():
    clock = FakeClock(now=1000.0, jitter=0.0)
    merge = ScriptMerge(script=[FirestoreContentionExhausted('storm', retry_after=2.5), None])
    pump = make_pump(merge, clock=clock)
    try:
        await pump._drain_after_publication('owner-a')
        assert merge.drained == ['owner-a']
        # The lane must not re-drain inside the armed window.
        clock.advance(0.5)
        assert await pump._drain_deferred_due() == 0
        assert 'owner-a' in pump._deferred_drains
        clock.advance(2.0)  # now 1003.0: the window has elapsed
        drained = await pump._drain_deferred_due()
        assert drained == 1
        assert 'owner-a' not in pump._deferred_drains
        assert merge.drained == ['owner-a', 'owner-a']
    finally:
        await drain_lane_hygiene(pump)


async def test_lane_rearm_after_a_second_storm_loss_realigns_again():
    clock = FakeClock(now=1000.0, jitter=0.0)
    merge = ScriptMerge(
        script=[
            FirestoreContentionExhausted('storm-1', retry_after=2.0),
            FirestoreContentionExhausted('storm-2', retry_after=3.0),
            None,
        ]
    )
    pump = make_pump(merge, clock=clock)
    try:
        await pump._drain_after_publication('owner-a')
        clock.advance(2.5)
        drained = await pump._drain_deferred_due()
        assert drained == 0  # the re-drain lost to storm-2 and re-armed
        armed = pump._deferred_drains['owner-a']
        assert armed['attempts'] == 2
        # Attempt 2's documented step is 1.0s; the fresh 3.0s window wins.
        assert armed['due_at'] == pytest.approx(clock.now + 3.0)
        clock.advance(3.0)
        assert await pump._drain_deferred_due() == 1
        assert 'owner-a' not in pump._deferred_drains
    finally:
        await drain_lane_hygiene(pump)


# --------------------------------------------------------------------------
# Contract parity: the docs page names the alignment and its failure class
# --------------------------------------------------------------------------


def test_contract_doc_names_the_storm_alignment():
    doc = Path(__file__).resolve().parents[2] / 'docs' / 'batch-merge-deferred-drain-convergence.md'
    text = doc.read_text()
    assert 'Storm-window alignment' in text
    assert 'FirestoreContentionExhausted.retry_after' in text
    assert 'FC-deferred-drain-restrike-collides-inside-the-armed-storm-window' in text
    source = Path(pump_module.__file__).read_text()
    assert 'contention_retry_after' in source
    assert 'math.isfinite' in source
