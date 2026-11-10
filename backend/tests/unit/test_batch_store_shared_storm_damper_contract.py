"""Process-shared storm damper registry (the ``x1056/30m`` exhausted family).

The store storm damper spaces an exhausted operation's re-strikes by arming a
bounded, jittered per-label window. Its contract — the next entry of that
label waits the window out — used to be scoped to ONE ``FirestoreStore``
instance, and the process does not have one instance: serving, intake,
provider STT, voice evidence and cap-hold admission each construct their own
store for the same namespace, several per call, and a per-call store's window
died with the instance that armed it. The registry
(``shared_storm_damper``) gives every namespace one process-level damper, so
an exhaustion armed through any instance spaces the next entry on every
instance. This suite pins that contract end to end:

1. Identity and keying: same-namespace constructions share one damper;
   different namespaces stay independent; an injected ``storm_damper=`` is
   honored verbatim and never registered; the reset seam clears the registry;
   an invalid namespace registers nothing.
2. Sibling visibility through real ``run()``: an exhaustion through one
   instance spaces the next entry of the label on a sibling instance (logged
   at INFO as ``event=batch_store_backoff``), including the per-call
   construction shape the production bug lived in, and the exhaustion-stamped
   ``retry_after`` equals the residual the sibling waits.
3. Shared does not mean changed: ladder shape, cap, jitter, generation guard,
   wave-rung per-chain spacing, dormancy under the kill switches, and the
   untouched probe path all behave exactly as the per-instance damper did.

Failure-Class: FC-storm-damper-window-dies-with-its-store-instance
"""

import logging
import threading
from pathlib import Path
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import Aborted

from database import batch_pipeline_store as storage

BACKEND = Path(__file__).resolve().parents[2]

FC_TOKEN = 'FC-storm-damper-window-dies-with-its-store-instance'
BASE_SECONDS = storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS  # 0.25
CAP_SECONDS = storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS  # 4.0
LADDER_STEPS = storage.FirestoreStore.STORM_DAMPER_LADDER_STEPS  # 4


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


def shared_damper(namespace='batch_pipeline_dev', jitter=0.0, now=100.0):
    """The process-shared damper for ``namespace`` on a deterministic clock.

    The registry object is adopted onto an injected clock/seeder so the
    shared-window tests never sleep real time; the object identity stays
    exactly what the store constructor resolved. The namespace's fleet
    window is adopted onto the SAME clock: a broadcast window is a wall
    deadline, and a test that advances the damper's monotonic clock past it
    must advance the mirror's wall clock with it, or a real-time mirror
    would re-arm a label the damper has already expired.
    """
    clock = FakeClock(now=now, jitter=jitter)
    damper = storage.shared_storm_damper(namespace)
    damper._monotonic = clock.monotonic
    damper._sleeper = clock.sleep
    damper._random_value = clock.random_value
    storage.fleet_storm_window(namespace)._wall_now = clock.monotonic
    return damper, clock


def default_store(monkeypatch, namespace='batch_pipeline_dev', client=None):
    """A store on the process-shared damper (no ``storm_damper=`` injection)."""
    stage = 'prod' if namespace == 'batch_pipeline_prod' else 'dev'
    monkeypatch.setenv('OMI_ENV_STAGE', stage)
    return storage.FirestoreStore(namespace, firestore_client=client if client is not None else Mock())


def exhausting_client(abort_times=10**6):
    client = Mock()
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(abort_times)
    return client


def healthy_client():
    client = Mock()
    client.transaction.side_effect = lambda max_attempts=5: AbortThenCommitTx(0)
    return client


def aborting_chain_client(aborts):
    """The first ``aborts`` chain attempts abort at commit; the next succeeds."""
    client = Mock()
    remaining = {'value': aborts}

    def transaction_factory(max_attempts=5):
        if remaining['value'] > 0:
            remaining['value'] -= 1
            return AbortThenCommitTx(1)
        return AbortThenCommitTx(0)

    client.transaction.side_effect = transaction_factory
    return client


def silence_chain_sleep(monkeypatch, sleeps=None, chain_jitter=0.0):
    """Record (or drop) the retry chain's own sleeps; seed its jitter deterministically."""
    actual = storage.run_with_transaction_contention_retry

    def factory(*args, **kwargs):
        kwargs.setdefault('sleep', sleeps if sleeps is not None else (lambda _seconds: None))
        kwargs.setdefault('random_value', lambda: chain_jitter)
        return actual(*args, **kwargs)

    monkeypatch.setattr(storage, 'run_with_transaction_contention_retry', factory)


def exhaust_run(store, label, times=1):
    """Drive ``label`` to exhaustion ``times`` times; return the last error."""
    error = None
    for _ in range(times):
        try:
            store.run(lambda tx: True, operation=label)
        except storage.FirestoreContentionExhausted as caught:
            error = caught
        else:
            raise AssertionError('expected exhaustion')
    return error


def arm_delay_seconds(exhaustions, jitter):
    """The documented damper ladder: min(cap, base * 2**min(k-1, steps)) * (0.5 + 0.5*j)."""
    maximum = min(CAP_SECONDS, BASE_SECONDS * (2 ** min(exhaustions - 1, LADDER_STEPS)))
    return maximum * (0.5 + 0.5 * jitter)


def wave_rung_seconds(failed_attempt, jitter):
    """The documented wave rung: the same ladder indexed by the failed attempt."""
    return arm_delay_seconds(failed_attempt, jitter)


def equal_jitter_floor(attempt, chain_jitter=0.0):
    """The chain's own equal-jitter wait at ``chain_jitter=0`` (the recorded floor)."""
    high = min(0.2 * (2 ** (attempt - 1)), 4.0)
    return high / 2 + (high / 2) * chain_jitter


@pytest.fixture
def fast_chain(monkeypatch):
    silence_chain_sleep(monkeypatch)


# --------------------------------------------------------------------------
# Section A — registry identity and keying
# --------------------------------------------------------------------------


def test_same_namespace_constructions_share_one_damper(monkeypatch):
    first = default_store(monkeypatch)
    second = default_store(monkeypatch)
    assert first._storm_damper is second._storm_damper


def test_three_same_namespace_stores_share_one_damper(monkeypatch):
    stores = [default_store(monkeypatch) for _ in range(3)]
    assert stores[0]._storm_damper is stores[1]._storm_damper is stores[2]._storm_damper


def test_shared_accessor_is_idempotent():
    assert storage.shared_storm_damper('batch_pipeline_dev') is storage.shared_storm_damper('batch_pipeline_dev')


def test_shared_damper_is_the_store_damper_class():
    assert isinstance(storage.shared_storm_damper('batch_pipeline_dev'), storage._ContentionStormDamper)


def test_different_namespaces_get_different_dampers(monkeypatch):
    dev = default_store(monkeypatch, namespace='batch_pipeline_dev')
    prod = default_store(monkeypatch, namespace='batch_pipeline_prod')
    assert dev._storm_damper is not prod._storm_damper


def test_adjacent_test_namespaces_get_different_dampers(monkeypatch):
    monkeypatch.setenv('FIRESTORE_EMULATOR_HOST', '127.0.0.1:8080')
    left = storage.FirestoreStore('batch_pipeline_test_unit', firestore_client=None)
    right = storage.FirestoreStore('batch_pipeline_test_unit2', firestore_client=None)
    assert left._storm_damper is not right._storm_damper


def test_prod_and_dev_windows_stay_independent(monkeypatch, fast_chain):
    damper_prod, clock_prod = shared_damper('batch_pipeline_prod', jitter=0.0)
    damper_dev, clock_dev = shared_damper('batch_pipeline_dev', jitter=0.0)
    store_prod = default_store(monkeypatch, namespace='batch_pipeline_prod', client=exhausting_client())
    exhaust_run(store_prod, 'batch_merge_commit')
    assert clock_prod.sleeps == []
    assert damper_dev._generations == {}
    assert clock_dev.sleeps == []


def test_registry_holds_exactly_one_entry_per_namespace(monkeypatch):
    for _ in range(5):
        default_store(monkeypatch, namespace='batch_pipeline_dev')
    assert len(storage._SHARED_STORM_DAMPERS) == 1


def test_injected_damper_is_not_registered(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    injected = storage._ContentionStormDamper()
    storage.FirestoreStore('batch_pipeline_dev', firestore_client=Mock(), storm_damper=injected)
    assert 'batch_pipeline_dev' not in storage._SHARED_STORM_DAMPERS


def test_injected_damper_stays_distinct_from_the_shared_one(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    injected = storage._ContentionStormDamper()
    store = storage.FirestoreStore('batch_pipeline_dev', firestore_client=Mock(), storm_damper=injected)
    shared = storage.shared_storm_damper('batch_pipeline_dev')
    assert store._storm_damper is injected
    assert store._storm_damper is not shared


def test_reset_clears_the_registry():
    storage.shared_storm_damper('batch_pipeline_dev')
    storage.shared_storm_damper('batch_pipeline_prod')
    assert len(storage._SHARED_STORM_DAMPERS) == 2
    storage.reset_shared_storm_dampers()
    assert storage._SHARED_STORM_DAMPERS == {}


def test_post_reset_construction_gets_a_fresh_damper(monkeypatch, fast_chain):
    first = default_store(monkeypatch, client=exhausting_client())
    exhaust_run(first, 'batch_merge_commit')
    assert first._storm_damper._generations == {'batch_merge_commit': 1}
    storage.reset_shared_storm_dampers()
    second = default_store(monkeypatch)
    assert second._storm_damper is not first._storm_damper
    assert second._storm_damper._generations == {}


def test_pre_reset_store_keeps_functioning_after_reset(monkeypatch, fast_chain):
    store = default_store(monkeypatch, client=exhausting_client())
    old_damper = store._storm_damper
    storage.reset_shared_storm_dampers()
    assert store._storm_damper is old_damper
    exhaust_run(store, 'batch_merge_commit')
    assert old_damper._generations == {'batch_merge_commit': 1}


def test_reset_is_safe_on_an_empty_registry():
    storage.reset_shared_storm_dampers()
    storage.reset_shared_storm_dampers()
    assert storage._SHARED_STORM_DAMPERS == {}


def test_invalid_namespace_registers_nothing():
    with pytest.raises(ValueError):
        storage.FirestoreStore('batch_pipeline_unknown', firestore_client=Mock())
    assert storage._SHARED_STORM_DAMPERS == {}


def test_test_namespace_without_a_loopback_emulator_registers_nothing(monkeypatch):
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    with pytest.raises(RuntimeError):
        storage.FirestoreStore('batch_pipeline_test_unit', firestore_client=Mock())
    assert storage._SHARED_STORM_DAMPERS == {}


def test_threads_concurrently_converge_on_one_damper(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    barrier = threading.Barrier(8)
    seen = []
    lock = threading.Lock()

    def build():
        barrier.wait()
        store = storage.FirestoreStore('batch_pipeline_dev', firestore_client=Mock())
        with lock:
            seen.append(store._storm_damper)

    threads = [threading.Thread(target=build) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len({id(damper) for damper in seen}) == 1
    assert len(storage._SHARED_STORM_DAMPERS) == 1


def test_concurrent_distinct_namespaces_each_register_once(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('FIRESTORE_EMULATOR_HOST', '127.0.0.1:8080')
    namespaces = [f'batch_pipeline_test_conv_{n}' for n in range(4)]
    barrier = threading.Barrier(8)
    errors = []

    def build(index):
        barrier.wait()
        try:
            storage.FirestoreStore(namespaces[index % len(namespaces)], firestore_client=None)
        except Exception as error:  # pragma: no cover - recorded, never raised
            errors.append(error)

    threads = [threading.Thread(target=build, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert len(storage._SHARED_STORM_DAMPERS) == len(namespaces)


def test_registry_never_grows_past_one_entry_per_namespace(monkeypatch):
    for _ in range(4):
        default_store(monkeypatch, namespace='batch_pipeline_dev')
        storage.shared_storm_damper('batch_pipeline_dev')
    assert len(storage._SHARED_STORM_DAMPERS) == 1


# --------------------------------------------------------------------------
# Section B — sibling visibility through real run()
# --------------------------------------------------------------------------


def test_sibling_store_entry_waits_out_the_window_an_exhaustion_armed(monkeypatch, fast_chain):
    _damper, clock = shared_damper('batch_pipeline_dev', jitter=0.0)
    store_a = default_store(monkeypatch, client=exhausting_client())
    exhaust_run(store_a, 'batch_merge_commit')
    store_b = default_store(monkeypatch, client=healthy_client())
    assert store_b.run(lambda tx: 'ok', operation='batch_merge_commit') == 'ok'
    assert clock.sleeps == [arm_delay_seconds(1, 0.0)]


def test_sibling_wait_logs_label_and_waited_ms(monkeypatch, fast_chain, caplog):
    _damper, _clock = shared_damper('batch_pipeline_dev', jitter=0.0)
    store_a = default_store(monkeypatch, client=exhausting_client())
    exhaust_run(store_a, 'batch_merge_commit')
    store_b = default_store(monkeypatch, client=healthy_client())
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        store_b.run(lambda tx: 'ok', operation='batch_merge_commit')
    lines = [record.getMessage() for record in caplog.records if 'event=batch_store_backoff' in record.getMessage()]
    assert lines == ['event=batch_store_backoff operation=batch_merge_commit waited_ms=125']


def test_sibling_wait_never_logs_at_warning_level(monkeypatch, fast_chain, caplog):
    _damper, _clock = shared_damper('batch_pipeline_dev', jitter=0.0)
    store_a = default_store(monkeypatch, client=exhausting_client())
    exhaust_run(store_a, 'batch_merge_commit')
    store_b = default_store(monkeypatch, client=healthy_client())
    with caplog.at_level(logging.WARNING, logger='database.batch_pipeline_store'):
        store_b.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert [record for record in caplog.records if 'event=batch_store_backoff' in record.getMessage()] == []


def test_per_call_construction_sites_damp_each_other(monkeypatch, fast_chain):
    """The production shape: each call built its own store, and the window died."""
    _damper, clock = shared_damper('batch_pipeline_dev', jitter=0.0)
    first = default_store(monkeypatch, client=exhausting_client())
    exhaust_run(first, 'batch_provider_stt')
    del first
    second = default_store(monkeypatch, client=healthy_client())
    second.run(lambda tx: 'ok', operation='batch_provider_stt')
    assert clock.sleeps == [arm_delay_seconds(1, 0.0)]


def test_third_instance_sees_the_laddered_residual(monkeypatch, fast_chain):
    _damper, clock = shared_damper('batch_pipeline_dev', jitter=0.0)
    store_a = default_store(monkeypatch, client=exhausting_client())
    exhaust_run(store_a, 'batch_intake_status', times=2)
    # A's own second entry consults its first window (0.125) before exhausting
    # again; the third instance then waits the laddered residual (0.25).
    store_c = default_store(monkeypatch, client=healthy_client())
    store_c.run(lambda tx: 'ok', operation='batch_intake_status')
    assert clock.sleeps == [arm_delay_seconds(1, 0.0), arm_delay_seconds(2, 0.0)]


def test_window_expiry_returns_sibling_entry_to_zero_wait(monkeypatch, fast_chain):
    damper, clock = shared_damper('batch_pipeline_dev', jitter=0.0)
    store_a = default_store(monkeypatch, client=exhausting_client())
    exhaust_run(store_a, 'batch_merge_commit')
    clock.now = clock.now + arm_delay_seconds(1, 0.0) + 0.001
    assert damper.peek('batch_merge_commit')[0] == 0.0
    store_c = default_store(monkeypatch, client=healthy_client())
    store_c.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == []


def test_sibling_success_clears_the_shared_ladder(monkeypatch, fast_chain):
    damper, clock = shared_damper('batch_pipeline_dev', jitter=0.0)
    store_a = default_store(monkeypatch, client=exhausting_client())
    exhaust_run(store_a, 'batch_merge_commit')
    store_b = default_store(monkeypatch, client=healthy_client())
    store_b.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert damper._generations == {}
    store_c = default_store(monkeypatch, client=healthy_client())
    store_c.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert len(clock.sleeps) == 1


def test_sibling_success_does_not_clear_a_window_armed_mid_chain(monkeypatch, fast_chain):
    """Generation guard across instances: an arm during B's chain holds the window."""
    damper, clock = shared_damper('batch_pipeline_dev', jitter=0.0)
    store_a = default_store(monkeypatch, client=exhausting_client())
    exhaust_run(store_a, 'batch_merge_commit')

    def arming_body(_tx):
        damper.arm('batch_merge_commit')  # a sibling exhaustion lands mid-chain
        return 'ok'

    store_b = default_store(monkeypatch, client=healthy_client())
    assert store_b.run(arming_body, operation='batch_merge_commit') == 'ok'
    assert damper._generations == {'batch_merge_commit': 2}
    store_c = default_store(monkeypatch, client=healthy_client())
    store_c.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert len(clock.sleeps) == 2


def test_retry_after_stamp_equals_the_residual_the_sibling_waits(monkeypatch, fast_chain):
    damper, clock = shared_damper('batch_pipeline_dev', jitter=1.0)
    store_a = default_store(monkeypatch, client=exhausting_client())
    error = exhaust_run(store_a, 'batch_merge_commit')
    assert error.retry_after == pytest.approx(arm_delay_seconds(1, 1.0))
    store_b = default_store(monkeypatch, client=healthy_client())
    store_b.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [pytest.approx(error.retry_after)]
    assert 'batch_merge_commit' not in damper._armed_until


def test_kill_switch_dormant_sibling_waits_nothing(monkeypatch, fast_chain):
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED', 'false')
    damper, clock = shared_damper('batch_pipeline_dev', jitter=0.0)
    store_a = default_store(monkeypatch, client=exhausting_client())
    exhaust_run(store_a, 'batch_merge_commit')
    store_b = default_store(monkeypatch, client=healthy_client())
    assert store_b.run(lambda tx: 'ok', operation='batch_merge_commit') == 'ok'
    assert clock.sleeps == []
    assert damper_state_empty(damper)


def damper_state_empty(damper):
    return damper._generations == {} and damper._armed_until == {} and damper._failures == {}


def test_retry_switch_off_propagates_without_arming(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_RETRY_ENABLED', 'false')
    damper, clock = shared_damper('batch_pipeline_dev', jitter=0.0)
    store = default_store(monkeypatch, client=aborting_chain_client(1))
    # The SDK's own transactional wrapper raises once its one allowed commit aborts;
    # our bounded helper (and the damper behind it) never enters the path.
    with pytest.raises(ValueError):
        store.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == []
    assert damper_state_empty(damper)


def test_probe_on_a_storming_sibling_never_waits(monkeypatch, fast_chain):
    _damper, clock = shared_damper('batch_pipeline_dev', jitter=0.0)
    store_a = default_store(monkeypatch, client=exhausting_client())
    exhaust_run(store_a, 'batch_merge_commit')
    store_b = default_store(monkeypatch, client=healthy_client())
    store_b.probe('jobs', 'segment-1')
    assert clock.sleeps == []


def test_sibling_wait_stays_bounded_by_the_cap(monkeypatch, fast_chain):
    _damper, clock = shared_damper('batch_pipeline_dev', jitter=1.0)
    store_a = default_store(monkeypatch, client=exhausting_client())
    exhaust_run(store_a, 'batch_merge_commit', times=12)
    store_b = default_store(monkeypatch, client=healthy_client())
    store_b.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert max(clock.sleeps) <= CAP_SECONDS + 1e-9
    assert clock.sleeps[-1] == pytest.approx(arm_delay_seconds(12, 1.0))


def test_composed_shard_label_is_damped_across_instances(monkeypatch, fast_chain):
    _damper, clock = shared_damper('batch_pipeline_dev', jitter=0.0)
    store_a = default_store(monkeypatch, client=exhausting_client())
    exhaust_run(store_a, 'batch_pull shard=scheduler_03')
    store_b = default_store(monkeypatch, client=healthy_client())
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_03')
    assert clock.sleeps == [arm_delay_seconds(1, 0.0)]


def test_shard_labels_damp_independently_of_each_other(monkeypatch, fast_chain):
    damper, clock = shared_damper('batch_pipeline_dev', jitter=0.0)
    store_a = default_store(monkeypatch, client=exhausting_client())
    exhaust_run(store_a, 'batch_pull shard=scheduler_03')
    store_b = default_store(monkeypatch, client=healthy_client())
    store_b.run(lambda tx: 'ok', operation='batch_pull shard=scheduler_04')
    assert clock.sleeps == []
    assert 'batch_pull shard=scheduler_04' not in damper._armed_until


# --------------------------------------------------------------------------
# Section C — the mid-ladder gate reads the sibling's window
# --------------------------------------------------------------------------


def mid_chain_arming_body(damper, label, arm_on_body_call):
    """A transaction body that simulates a sibling exhausting mid-chain."""
    state = {'calls': 0}

    def body(_tx):
        state['calls'] += 1
        if state['calls'] == arm_on_body_call:
            damper.arm(label)
        return 'ok'

    return body


def test_gate_rung_waits_out_a_sibling_armed_window(monkeypatch, fast_chain):
    damper, _clock = shared_damper('batch_pipeline_dev', jitter=0.0)
    store_a = default_store(monkeypatch, client=exhausting_client())
    exhaust_run(store_a, 'batch_merge_commit')
    rung_sleeps = []
    monkeypatch.setattr(storage, 'run_with_transaction_contention_retry', silence_chain_sleep_for(rung_sleeps))
    store_b = default_store(monkeypatch, client=aborting_chain_client(1))
    assert (
        store_b.run(
            mid_chain_arming_body(damper, 'batch_merge_commit', arm_on_body_call=1), operation='batch_merge_commit'
        )
        == 'ok'
    )
    # The mid-chain arm is the SECOND failure on the shared damper (A's storm
    # already counted one), so the gate waits the second rung's residual.
    assert rung_sleeps[0] == pytest.approx(equal_jitter_floor(1) + arm_delay_seconds(2, 0.0))


def silence_chain_sleep_for(record):
    actual = storage.run_with_transaction_contention_retry

    def factory(*args, **kwargs):
        kwargs.setdefault('sleep', record.append)
        kwargs.setdefault('random_value', lambda: 0.0)
        return actual(*args, **kwargs)

    return factory


def test_wave_rung_from_rung_three_stays_per_chain(monkeypatch):
    damper, _clock = shared_damper('batch_pipeline_dev', jitter=0.0)
    rung_sleeps = []
    monkeypatch.setattr(storage, 'run_with_transaction_contention_retry', silence_chain_sleep_for(rung_sleeps))
    store = default_store(monkeypatch, client=aborting_chain_client(3))
    assert store.run(lambda tx: 'ok', operation='batch_merge_commit') == 'ok'
    assert rung_sleeps[2] == pytest.approx(equal_jitter_floor(3) + wave_rung_seconds(3, 0.0))
    assert damper._generations == {}


def test_wave_rung_loses_to_a_longer_sibling_window(monkeypatch, fast_chain):
    damper, _clock = shared_damper('batch_pipeline_dev', jitter=0.0)
    store_a = default_store(monkeypatch, client=exhausting_client())
    exhaust_run(store_a, 'batch_merge_commit', times=4)
    rung_sleeps = []
    monkeypatch.setattr(storage, 'run_with_transaction_contention_retry', silence_chain_sleep_for(rung_sleeps))
    store_b = default_store(monkeypatch, client=aborting_chain_client(3))
    body = mid_chain_arming_body(damper, 'batch_merge_commit', arm_on_body_call=2)
    assert store_b.run(body, operation='batch_merge_commit') == 'ok'
    residual = arm_delay_seconds(5, 0.0)  # 2.0: A counted four failures, the mid-chain arm is the fifth
    wave = wave_rung_seconds(3, 0.0)  # 0.5: the per-chain wave wait at rung three
    assert rung_sleeps[1] == pytest.approx(equal_jitter_floor(2) + residual)
    assert rung_sleeps[2] == pytest.approx(equal_jitter_floor(3) + max(residual, wave))
    # B's chain recovered, and its mid-ladder peeks kept the generation guard
    # honest: the success cleared the shared window outright.
    assert 'batch_merge_commit' not in damper._generations


def test_gate_never_gates_the_first_attempt(monkeypatch):
    damper, _clock = shared_damper('batch_pipeline_dev', jitter=0.0)
    store_a = default_store(monkeypatch, client=exhausting_client())
    exhaust_run(store_a, 'batch_merge_commit')
    rung_sleeps = []
    monkeypatch.setattr(storage, 'run_with_transaction_contention_retry', silence_chain_sleep_for(rung_sleeps))
    store_b = default_store(monkeypatch, client=aborting_chain_client(0))
    assert store_b.run(lambda tx: 'ok', operation='batch_merge_commit') == 'ok'
    assert rung_sleeps == []
    assert damper._generations == {}


# --------------------------------------------------------------------------
# Section D — the shared damper keeps its unit semantics
# --------------------------------------------------------------------------


def test_first_arm_at_zero_jitter_is_half_the_base_maximum():
    damper, _clock = shared_damper('batch_pipeline_dev', jitter=0.0)
    assert damper.arm('batch_admit') == pytest.approx(arm_delay_seconds(1, 0.0))


def test_first_arm_at_full_jitter_is_the_base_maximum():
    damper, _clock = shared_damper('batch_pipeline_dev', jitter=1.0)
    assert damper.arm('batch_admit') == pytest.approx(arm_delay_seconds(1, 1.0))


def test_ladder_doubles_to_the_cap_through_the_shared_damper():
    rungs = []
    for failures in range(1, 7):
        storage.reset_shared_storm_dampers()
        damper, _clock = shared_damper('batch_pipeline_dev', jitter=1.0)
        for _ in range(failures - 1):
            damper.arm('batch_admit')
        rungs.append(damper.arm('batch_admit'))
    assert rungs == [pytest.approx(arm_delay_seconds(k, 1.0)) for k in range(1, 7)]


def test_consult_generation_increments_across_arms():
    damper, _clock = shared_damper('batch_pipeline_dev')
    assert damper.consult('batch_admit')[1] == 0
    damper.arm('batch_admit')
    assert damper.consult('batch_admit')[1] == 1
    damper.arm('batch_admit')
    assert damper.consult('batch_admit')[1] == 2


def test_note_success_clears_only_the_matching_generation():
    damper, _clock = shared_damper('batch_pipeline_dev')
    _waited, generation = damper.consult('batch_admit')
    damper.arm('batch_admit')
    damper.note_success('batch_admit', generation)
    assert damper._generations == {'batch_admit': 1}


def test_peek_residual_is_zero_when_expired():
    damper, clock = shared_damper('batch_pipeline_dev', jitter=0.0)
    damper.arm('batch_admit')
    clock.now += arm_delay_seconds(1, 0.0)
    assert damper.peek('batch_admit')[0] == 0.0


def test_wave_rung_wait_draw_is_never_recorded_on_the_shared_state():
    damper, _clock = shared_damper('batch_pipeline_dev', jitter=1.0)
    wait = damper.wave_rung_wait(3)
    assert wait == pytest.approx(wave_rung_seconds(3, 1.0))
    assert damper._generations == {} and damper._armed_until == {}


def test_label_cap_fails_open_through_the_shared_damper():
    damper, _clock = shared_damper('batch_pipeline_dev')
    for index in range(storage.FirestoreStore.STORM_DAMPER_MAX_TRACKED_LABELS):
        damper.arm(f'batch_cap_fill_{index:02d}')
    assert damper.arm('batch_cap_overflow') == 0.0
    assert damper.tracked_labels() == storage.FirestoreStore.STORM_DAMPER_MAX_TRACKED_LABELS


# --------------------------------------------------------------------------
# Section E — doc and source parity
# --------------------------------------------------------------------------


def test_doc_names_the_failure_class():
    doc = (BACKEND / 'docs' / 'batch-store-shared-storm-damper.md').read_text(encoding='utf-8')
    assert FC_TOKEN in doc


def test_doc_names_the_registry_functions():
    doc = (BACKEND / 'docs' / 'batch-store-shared-storm-damper.md').read_text(encoding='utf-8')
    assert 'shared_storm_damper' in doc
    assert 'reset_shared_storm_dampers' in doc


def test_doc_states_what_did_not_change():
    doc = (BACKEND / 'docs' / 'batch-store-shared-storm-damper.md').read_text(encoding='utf-8')
    assert '## What did not change' in doc
    assert 'honored verbatim' in doc


def test_store_module_carries_the_failure_class():
    source = (BACKEND / 'database' / 'batch_pipeline_store.py').read_text(encoding='utf-8')
    assert FC_TOKEN in source


def test_registry_helper_exists_with_a_reset_seam():
    assert callable(storage.shared_storm_damper)
    assert callable(storage.reset_shared_storm_dampers)
