"""Projection lane storm gate (x1167/30m ``outcome=exhausted`` contention family).

``ProjectionStore.run`` opts into the same bounded contention retry engine as
the batch-store lane, but it passes no ``inter_attempt_gate``: no entry
consult, no mid-ladder storm peek, no wave rungs, and an exhaustion that
carries ``retry_after=0.0``. The projection lane writes the same hot
``jobs``/``results`` rows the batch-store labels contend over, so a storm
window the store lane (or a sibling pod) armed for those rows is invisible to
the projection chain — it re-fires every rung into the window's interior and
re-derives the storm the fleet already measured. This suite pins the
projection lane's storm gate:

1. Entry consult: the projection run waits out a window armed for
   ``batch_projection`` before opening its chain (logged at INFO as
   ``event=batch_projection_backoff``), and a success clears the ladder only
   when no concurrent arm bumped the generation.
2. Mid-ladder gate: each rung after a measured collision adopts the peeked
   residual, and from the third failed rung also the wave rung — the same
   shape the batch-store lane spaces its deep rungs by.
3. Exhaustion stamps the damper's applied window onto ``retry_after`` so a
   caller scheduling its own re-offer lands after the window.
4. The gate is dormant with the storm-damper kill switch off and completely
   absent from the non-retry paths; the policy-off and env-fallback shapes
   keep their exact legacy behavior otherwise.

Failure-Class: FC-projection-contention-chain-collides-inside-armed-storm-window
"""

import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import Aborted

from database import batch_pipeline_projection as projection_module
from database import batch_pipeline_store as storage
from database.firestore_transaction_retry import FirestoreContentionExhausted

PROJECTION_LABEL = 'batch_projection'


# --------------------------------------------------------------------------
# Harnesses (mirrors of the store damper suite's deterministic fakes)
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


class RecordingDamper(storage._ContentionStormDamper):
    """The real damper with call-order recording; arithmetic stays real."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.events = []
        self.last_arm_applied = None

    def consult(self, label, *, client=None):
        self.events.append(('consult', label))
        return super().consult(label, client=client)

    def peek(self, label, *, client=None):
        self.events.append(('peek', label))
        return super().peek(label, client=client)

    def arm(self, label, *, client=None):
        self.events.append(('arm', label))
        applied = super().arm(label, client=client)
        self.last_arm_applied = applied
        return applied

    def note_success(self, label, generation):
        self.events.append(('note_success', label, generation))
        return super().note_success(label, generation)

    def calls_of(self, kind):
        return [event for event in self.events if event[0] == kind]


def make_damper(jitter=0.0):
    clock = FakeClock(jitter=jitter)
    damper = RecordingDamper(monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value)
    return damper, clock


def retrying_client(abort_times=10**6):
    client = Mock()
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(abort_times)
    return client


def healthy_client():
    client = Mock()
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    return client


def build_projection_store(monkeypatch, damper=None, client=None):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    store = storage.FirestoreStore(
        'batch_pipeline_dev', firestore_client=client if client is not None else healthy_client(), storm_damper=damper
    )
    return projection_module.ProjectionStore(store)


class ChainSleepRecorder:
    """Records the per-rung sleeps the retry engine asks for."""

    def __init__(self):
        self.sleeps = []

    def __call__(self, seconds):
        self.sleeps.append(round(seconds, 6))


def silence_chain_sleep(monkeypatch, recorder=None):
    """Skip the retry chain's own jitter sleeps; damper sleeps stay injected."""
    from database import firestore_transaction_retry as engine

    actual = engine.run_with_transaction_contention_retry

    def factory(*args, **kwargs):
        kwargs.setdefault('sleep', recorder if recorder is not None else (lambda _seconds: None))
        return actual(*args, **kwargs)

    monkeypatch.setattr(engine, 'run_with_transaction_contention_retry', factory)


def contended_body(calls, abort_before_success=0, mid_flight=None):
    """A projection body that aborts ``abort_before_success`` times, then commits."""

    def body(transaction):
        calls.append(len(calls) + 1)
        if mid_flight is not None and len(calls) in mid_flight:
            mid_flight[len(calls)]()
        if len(calls) <= abort_before_success:
            raise Aborted('synthetic read contention')
        return 'projected'

    return body


def enable_damper(monkeypatch):
    monkeypatch.setattr(storage, 'contention_retry_enabled', lambda: True)
    monkeypatch.setattr(storage, 'contention_storm_damper_enabled', lambda: True)


# --------------------------------------------------------------------------
# 1. Entry consult
# --------------------------------------------------------------------------


def test_projection_run_consults_armed_window_before_first_attempt(monkeypatch):
    damper, clock = make_damper()
    enable_damper(monkeypatch)
    damper.arm(PROJECTION_LABEL)
    residual = damper.peek(PROJECTION_LABEL)[0]
    assert residual > 0
    store = build_projection_store(monkeypatch, damper=damper, client=healthy_client())
    calls = []
    silence_chain_sleep(monkeypatch)
    result = store.run(contended_body(calls), policy=SimpleNamespace(projection_contention=True))
    assert result == 'projected'
    assert calls == [1]
    assert clock.sleeps == [pytest.approx(residual)]
    assert damper.calls_of('consult') == [('consult', PROJECTION_LABEL)]
    assert damper.calls_of('note_success'), 'a projected commit must clear the label ladder'


def test_projection_entry_consult_precedes_the_transaction_body(monkeypatch):
    damper, clock = make_damper()
    enable_damper(monkeypatch)
    damper.arm(PROJECTION_LABEL)
    store = build_projection_store(monkeypatch, damper=damper, client=healthy_client())
    calls = []
    silence_chain_sleep(monkeypatch)
    store.run(contended_body(calls), policy=SimpleNamespace(projection_contention=True))
    consult_index = damper.events.index(('consult', PROJECTION_LABEL))
    body_events = [event for event in damper.events[consult_index + 1 :] if event[0] == 'peek']
    assert clock.sleeps, 'the armed window must be slept at entry, before any body call'
    assert body_events == [], 'a first-attempt success never consults the mid-ladder peek'


def test_projection_run_without_armed_window_consults_cold_and_runs_untouched(monkeypatch):
    damper, clock = make_damper()
    enable_damper(monkeypatch)
    store = build_projection_store(monkeypatch, damper=damper, client=healthy_client())
    calls = []
    silence_chain_sleep(monkeypatch)
    result = store.run(contended_body(calls), policy=SimpleNamespace(projection_contention=True))
    assert result == 'projected'
    assert clock.sleeps == []
    assert [event[0] for event in damper.events] == ['consult', 'note_success']


def test_projection_success_notes_the_entry_generation(monkeypatch):
    damper, clock = make_damper()
    enable_damper(monkeypatch)
    store = build_projection_store(monkeypatch, damper=damper, client=healthy_client())
    calls = []
    silence_chain_sleep(monkeypatch)
    store.run(contended_body(calls), policy=SimpleNamespace(projection_contention=True))
    notes = damper.calls_of('note_success')
    assert len(notes) == 1
    label, generation = notes[0][1], notes[0][2]
    assert label == PROJECTION_LABEL
    assert isinstance(generation, int)


# --------------------------------------------------------------------------
# 2. Mid-ladder gate
# --------------------------------------------------------------------------


def test_second_rung_adopts_window_a_sibling_armed_mid_flight(monkeypatch):
    damper, clock = make_damper()
    enable_damper(monkeypatch)
    store = build_projection_store(monkeypatch, damper=damper, client=retrying_client(abort_times=1))
    calls = []
    recorder = ChainSleepRecorder()

    def sibling_arms_mid_flight():
        damper.arm(PROJECTION_LABEL)

    silence_chain_sleep(monkeypatch, recorder)
    result = store.run(
        contended_body(calls, abort_before_success=1, mid_flight={1: sibling_arms_mid_flight}),
        policy=SimpleNamespace(projection_contention=True),
    )
    assert result == 'projected'
    residual = damper.last_arm_applied
    assert residual > 0
    # Rung 2's wait is the equal-jitter step (0.1-0.2 s) plus the peeked
    # residual; the parent lane's bare ladder keeps only the step, so any
    # wait below residual + 0.1 means the gate never ran.
    assert 0.1 + residual - 1e-9 <= recorder.sleeps[0] < 0.2 + residual + 1e-9
    assert damper.calls_of('peek') == [('peek', PROJECTION_LABEL)]


def test_third_rung_engages_the_wave_ladder(monkeypatch):
    damper, clock = make_damper()
    enable_damper(monkeypatch)
    store = build_projection_store(monkeypatch, damper=damper, client=retrying_client(abort_times=3))
    calls = []
    recorder = ChainSleepRecorder()

    def sibling_arms_mid_flight():
        damper.arm(PROJECTION_LABEL)

    silence_chain_sleep(monkeypatch, recorder)
    result = store.run(
        contended_body(calls, abort_before_success=3, mid_flight={1: sibling_arms_mid_flight}),
        policy=SimpleNamespace(projection_contention=True),
    )
    assert result == 'projected'
    residual = damper.last_arm_applied
    wave_rung_three = min(storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS, 0.25 * 2**2) * 0.5
    # Rung 2 and 3 adopt the peeked residual; rung 4 — the first rung after
    # the third failed attempt, sustained-wave evidence — waits the deeper
    # of the residual and the attempt-3 wave rung (0.5 s at damper jitter 0).
    assert 0.1 + residual - 1e-9 <= recorder.sleeps[0] < 0.2 + residual + 1e-9
    assert 0.2 + residual - 1e-9 <= recorder.sleeps[1] < 0.4 + residual + 1e-9
    assert 0.4 + wave_rung_three - 1e-9 <= recorder.sleeps[2] < 0.8 + wave_rung_three + 1e-9
    assert len(damper.calls_of('peek')) == 3


def test_wave_ladder_never_engages_below_the_sustained_wave_threshold(monkeypatch):
    damper, clock = make_damper()
    enable_damper(monkeypatch)
    store = build_projection_store(monkeypatch, damper=damper, client=retrying_client(abort_times=1))
    calls = []
    recorder = ChainSleepRecorder()
    silence_chain_sleep(monkeypatch, recorder)
    store.run(contended_body(calls, abort_before_success=1), policy=SimpleNamespace(projection_contention=True))
    # One measured collision is transient evidence and the window is cold:
    # rung 2 keeps the bare equal-jitter step, no gate wait at all.
    assert 0.1 - 1e-9 <= recorder.sleeps[0] < 0.2 + 1e-9
    assert damper.calls_of('peek') == [('peek', PROJECTION_LABEL)]


def test_fifth_rung_caps_the_wave_ladder_at_the_damper_ceiling(monkeypatch):
    damper, clock = make_damper()
    enable_damper(monkeypatch)
    store = build_projection_store(monkeypatch, damper=damper, client=retrying_client(abort_times=4))
    calls = []
    recorder = ChainSleepRecorder()

    def sibling_arms_mid_flight():
        damper.arm(PROJECTION_LABEL)

    silence_chain_sleep(monkeypatch, recorder)
    result = store.run(
        contended_body(calls, abort_before_success=4, mid_flight={1: sibling_arms_mid_flight}),
        policy=SimpleNamespace(projection_contention=True),
    )
    assert result == 'projected'
    residual = damper.last_arm_applied
    # Failed attempt 4: the wave ladder step is min(cap, 0.25 * 2^3) halved
    # by the jitter draw -> 1.0 s, deeper than the fixture's residual, and
    # still far under the 4.0 s damper ceiling.
    wave_rung_four = min(storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS, 0.25 * 2**3) * 0.5
    assert 0.8 + wave_rung_four - 1e-9 <= recorder.sleeps[3] < 1.6 + wave_rung_four + 1e-9
    assert wave_rung_four < storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS
    assert residual <= storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS


def test_gate_never_gates_the_first_attempt(monkeypatch):
    damper, clock = make_damper()
    enable_damper(monkeypatch)
    store = build_projection_store(monkeypatch, damper=damper, client=healthy_client())
    calls = []
    recorder = ChainSleepRecorder()
    silence_chain_sleep(monkeypatch, recorder)
    store.run(contended_body(calls), policy=SimpleNamespace(projection_contention=True))
    assert recorder.sleeps == []
    assert damper.calls_of('peek') == []


# --------------------------------------------------------------------------
# 3. Exhaustion stamps the measured window
# --------------------------------------------------------------------------


def test_projection_exhaustion_stamps_damper_window_onto_retry_after(monkeypatch):
    damper, clock = make_damper()
    enable_damper(monkeypatch)
    store = build_projection_store(monkeypatch, damper=damper, client=retrying_client())
    calls = []
    silence_chain_sleep(monkeypatch)
    with pytest.raises(FirestoreContentionExhausted) as excinfo:
        store.run(contended_body(calls, abort_before_success=10**6), policy=SimpleNamespace(projection_contention=True))
    assert calls == [1, 2, 3, 4, 5]
    assert excinfo.value.reason == 'attempts_exhausted'
    assert excinfo.value.retry_after == pytest.approx(damper.last_arm_applied)
    assert excinfo.value.retry_after > 0
    assert damper.calls_of('arm') == [('arm', PROJECTION_LABEL)]


def test_projection_exhaustion_without_damper_keeps_zero_retry_after(monkeypatch):
    monkeypatch.setattr(storage, 'contention_retry_enabled', lambda: True)
    monkeypatch.setattr(storage, 'contention_storm_damper_enabled', lambda: False)
    store = build_projection_store(monkeypatch, damper=None, client=retrying_client())
    calls = []
    silence_chain_sleep(monkeypatch)
    with pytest.raises(FirestoreContentionExhausted) as excinfo:
        store.run(contended_body(calls, abort_before_success=10**6), policy=SimpleNamespace(projection_contention=True))
    assert calls == [1, 2, 3, 4, 5]
    assert excinfo.value.retry_after == 0.0


# --------------------------------------------------------------------------
# 4. Dormancy and legacy shapes
# --------------------------------------------------------------------------


def test_projection_storm_gate_dormant_when_storm_damper_switch_is_off(monkeypatch):
    damper, clock = make_damper()
    monkeypatch.setattr(storage, 'contention_retry_enabled', lambda: True)
    monkeypatch.setattr(storage, 'contention_storm_damper_enabled', lambda: False)
    store = build_projection_store(monkeypatch, damper=damper, client=retrying_client(abort_times=1))
    calls = []
    silence_chain_sleep(monkeypatch)
    result = store.run(contended_body(calls), policy=SimpleNamespace(projection_contention=True))
    assert result == 'projected'
    assert damper.events == [], 'a dormant damper is never consulted, peeked, armed or noted'
    assert clock.sleeps == []


def test_projection_policy_off_keeps_the_direct_transactional_path(monkeypatch):
    damper, clock = make_damper()
    enable_damper(monkeypatch)
    store = build_projection_store(monkeypatch, damper=damper, client=healthy_client())
    calls = []
    silence_chain_sleep(monkeypatch)
    result = store.run(contended_body(calls), policy=SimpleNamespace(projection_contention=False))
    assert result == 'projected'
    assert damper.events == []
    assert clock.sleeps == []


def test_projection_env_fallback_retry_gains_the_gate(monkeypatch):
    damper, clock = make_damper()
    enable_damper(monkeypatch)
    monkeypatch.setenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', 'true')
    store = build_projection_store(monkeypatch, damper=damper, client=retrying_client())
    calls = []
    silence_chain_sleep(monkeypatch)
    with pytest.raises(FirestoreContentionExhausted):
        store.run(
            contended_body(calls, abort_before_success=10**6), policy=SimpleNamespace(projection_contention=False)
        )
    assert calls == [1, 2, 3, 4, 5]
    assert damper.calls_of('consult') == [('consult', PROJECTION_LABEL)]
    assert damper.last_arm_applied is not None and damper.last_arm_applied > 0


def test_projection_policy_off_env_fallback_chain_stays_bare_without_switches(monkeypatch):
    monkeypatch.setattr(storage, 'contention_retry_enabled', lambda: True)
    monkeypatch.setattr(storage, 'contention_storm_damper_enabled', lambda: False)
    monkeypatch.setenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', 'true')
    store = build_projection_store(monkeypatch, damper=None, client=retrying_client(abort_times=1))
    calls = []
    silence_chain_sleep(monkeypatch)
    result = store.run(
        contended_body(calls, abort_before_success=1), policy=SimpleNamespace(projection_contention=False)
    )
    assert result == 'projected'
    assert calls == [1, 2]


# --------------------------------------------------------------------------
# 5. Concurrency and isolation
# --------------------------------------------------------------------------


def test_projection_gate_shares_one_process_damper_across_stores(monkeypatch):
    enable_damper(monkeypatch)
    damper, clock = make_damper()
    client = healthy_client()
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    inner = storage.FirestoreStore('batch_pipeline_dev', firestore_client=client, storm_damper=damper)
    lane_a = projection_module.ProjectionStore(inner)
    lane_b = projection_module.ProjectionStore(inner)
    damper.arm(PROJECTION_LABEL)
    silence_chain_sleep(monkeypatch)
    calls_a, calls_b = [], []
    result_b = lane_b.run(contended_body(calls_b), policy=SimpleNamespace(projection_contention=True))
    result_a = lane_a.run(contended_body(calls_a), policy=SimpleNamespace(projection_contention=True))
    assert (result_a, result_b) == ('projected', 'projected')
    # Both lanes consulted the SAME damper: only the damped entry slept.
    assert len(damper.calls_of('consult')) == 2
    assert len(clock.sleeps) == 1


def test_projection_gate_is_thread_safe_under_concurrent_runs(monkeypatch):
    damper, clock = make_damper()
    enable_damper(monkeypatch)
    store = build_projection_store(monkeypatch, damper=damper, client=healthy_client())
    silence_chain_sleep(monkeypatch)
    results = []
    errors = []

    def worker():
        try:
            calls = []
            results.append(store.run(contended_body(calls), policy=SimpleNamespace(projection_contention=True)))
        except Exception as error:  # pragma: no cover - surfaced by the assert
            errors.append(error)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert results == ['projected'] * 8
    assert len(damper.calls_of('consult')) == 8
