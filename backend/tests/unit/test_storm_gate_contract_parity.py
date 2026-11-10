"""Contract parity for the mid-ladder storm gate.


The docs page is the contract of record for the gate; these pins fail when
code and contract drift apart in either direction. Literal extraction reads
the real module sources and the real page - nothing is hard-coded twice.


Failure-Class: FC-mid-ladder-retry-collides-inside-the-concurrently-armed-storm-window

"""

import inspect
import math
import re
from pathlib import Path
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import Aborted

from database import batch_pipeline_store as storage
from database import firestore_transaction_retry as retry_module
from database.firestore_transaction_retry import (
    FirestoreContentionExhausted,
    normalized_gate_seconds,
    run_with_transaction_contention_retry,
)

DOCS = Path(__file__).resolve().parents[2] / 'docs' / 'batch-store-mid-ladder-storm-gate.md'

RETRY_SOURCE = inspect.getsource(retry_module)
STORE_SOURCE = inspect.getsource(storage)
FC = 'FC-mid-ladder-retry-collides-inside-the-concurrently-armed-storm-window'


def docs_text():
    """The docs page, whitespace-normalized so pins never hinge on line wraps."""
    return ' '.join(DOCS.read_text().split())


# ---------------------------------------------------------------- docs pins


def test_parity_doc_mid_ladder_storm_gating():
    assert 'Mid-ladder storm gating' in docs_text()


def test_parity_doc_inter_attempt_gate():
    assert 'inter_attempt_gate' in docs_text()


def test_parity_doc_failed_attempt_number():
    assert 'the 1-based number of the attempt that just failed' in docs_text()


def test_parity_doc_first_attempt_rule():
    assert 'The gate never gates the first attempt' in docs_text()


def test_parity_doc_advisory_only():
    assert 'advisory only' in docs_text()


def test_parity_doc_collapses_to_zero():
    assert 'all collapse to `0.0`' in docs_text()


def test_parity_doc_deadline_bound():
    assert 'deadline + one in-flight attempt' in docs_text()


def test_parity_doc_damper_cap_bound():
    assert '(the damper cap, 4.0 s)' in docs_text()


def test_parity_doc_non_sleeping_peek():
    assert 'non-sleeping damper' in docs_text() and 'peek' in docs_text()


def test_parity_doc_scope_mid_ladder_log():
    assert 'event=batch_store_backoff scope=mid_ladder' in docs_text()


def test_parity_doc_gate_ms_taxonomy():
    assert 'outcome=retry delay_ms=<jitter> gate_ms=<gate>' in docs_text()
    assert 'gate_ms=0' in docs_text()


def test_parity_doc_generation_guard():
    assert 'refreshed by every mid-ladder peek' in docs_text()
    assert 'note_success' in docs_text()


def test_parity_doc_byte_for_byte_bare_ladder():
    assert 'byte-for-byte the bare ladder' in docs_text()


def test_parity_doc_exhaustion_skips_gate():
    assert 'the final failed attempt raises without consulting the gate' in docs_text()


def test_parity_doc_raising_gate_fails_open():
    assert 'A raising gate fails open' in docs_text()


def test_parity_doc_what_did_not_change_section():
    assert '## What did not change' in docs_text()


def test_parity_doc_fc_trailer():
    assert FC in docs_text()


# ------------------------------------------------------------- source pins


def test_source_helper_accepts_inter_attempt_gate():
    signature = inspect.signature(run_with_transaction_contention_retry)
    assert 'inter_attempt_gate' in signature.parameters
    parameter = signature.parameters['inter_attempt_gate']
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is None


def test_source_store_passes_mid_ladder_gate():
    assert 'inter_attempt_gate=mid_ladder_gate' in STORE_SOURCE


def test_source_store_defines_mid_ladder_gate_closure():
    assert 'def mid_ladder_gate(failed_attempt: int) -> float:' in STORE_SOURCE


def test_source_damper_defines_peek():
    assert 'def peek(self, label: str) -> tuple[float, int]:' in STORE_SOURCE


def test_source_peek_does_not_sleep():
    peek_source = inspect.getsource(storage._ContentionStormDamper.peek)
    assert 'self._sleeper' not in peek_source
    assert 'sleep(' not in peek_source


def test_source_peek_clamps_negative_residual():
    assert 'max(residual, 0.0)' in inspect.getsource(storage._ContentionStormDamper.peek)


def test_source_gate_defends_against_hostile_answers():
    assert 'normalized_gate_seconds(inter_attempt_gate(attempt))' in RETRY_SOURCE


def test_source_gate_failure_is_fail_open():
    assert 'advisory spacing fails open to the bare jitter schedule' in RETRY_SOURCE


def test_source_gate_joins_deadline_check():
    assert 'deadline - monotonic() < delay + gate_seconds' in RETRY_SOURCE


def test_source_retry_line_carries_gate_ms():
    assert 'outcome=retry delay_ms=%d gate_ms=%d' in RETRY_SOURCE


def test_source_deadline_line_carries_gate_ms():
    assert 'remaining_ms=%d delay_ms=%d gate_ms=%d' in RETRY_SOURCE


def test_source_sleeps_delay_plus_gate():
    assert 'sleep(delay + gate_seconds)' in RETRY_SOURCE


def test_source_note_success_uses_latest_generation():
    assert 'damper.note_success(label, latest_generation)' in STORE_SOURCE


def test_source_latest_generation_refreshed_by_gate():
    assert 'latest_generation = gate_generation' in STORE_SOURCE


def test_source_scope_mid_ladder_log_in_store():
    assert "'event=batch_store_backoff scope=mid_ladder operation=%s attempt=%d waited_ms=%d'" in STORE_SOURCE


def test_source_module_docstring_names_the_failure_class():
    assert FC in RETRY_SOURCE
    assert FC in STORE_SOURCE


# ------------------------------------------------ hostile-answer normalization


@pytest.mark.parametrize('value', [True, False])
def test_normalized_gate_bools_are_zero(value):
    assert normalized_gate_seconds(value) == 0.0


@pytest.mark.parametrize('value', ['1.0', '0', None, object(), [1.0], ('1.0',)])
def test_normalized_gate_non_numbers_are_zero(value):
    assert normalized_gate_seconds(value) == 0.0


@pytest.mark.parametrize('value', [float('nan'), float('inf'), float('-inf')])
def test_normalized_gate_non_finite_is_zero(value):
    assert normalized_gate_seconds(value) == 0.0


@pytest.mark.parametrize('value', [0.0, -0.0, -1.0, -0.001, -1e9])
def test_normalized_gate_non_positive_is_zero(value):
    assert normalized_gate_seconds(value) == 0.0


def test_normalized_gate_positive_float_passes():
    assert normalized_gate_seconds(0.125) == pytest.approx(0.125)


def test_normalized_gate_positive_int_passes():
    assert normalized_gate_seconds(2) == pytest.approx(2.0)


def test_normalized_gate_tiny_positive_passes():
    assert normalized_gate_seconds(1e-6) == pytest.approx(1e-6)


def test_normalized_gate_huge_positive_passes():
    assert normalized_gate_seconds(1e9) == pytest.approx(1e9)


def test_normalized_gate_never_raises():
    for hostile in (True, 'x', None, float('nan'), -5):
        assert normalized_gate_seconds(hostile) == 0.0


# --------------------------------------------------------- gate call contract


class Clock:
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


class AbortNTimesTx:
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


def run_chain(clock, *, abort_times, max_attempts=5, gate=None, deadline=None):
    """Drive one retry chain whose body aborts ``abort_times`` times then lands."""
    state = {'n': 0}

    def operation(tx):
        state['n'] += 1
        if state['n'] <= abort_times:
            raise Aborted('synthetic commit contention')
        return 'ok'

    kwargs = {
        'operation_name': 'probe',
        'sleep': clock.sleep,
        'random_value': clock.random_value,
        'monotonic': clock.monotonic,
        'max_attempts': max_attempts,
    }
    if gate is not None:
        kwargs['inter_attempt_gate'] = gate
    if deadline is not None:
        kwargs['deadline'] = deadline
    return run_with_transaction_contention_retry(lambda: AbortNTimesTx(0), operation, **kwargs)


def test_gate_not_called_when_first_attempt_commits():
    clock = Clock()
    calls = []

    run_chain(clock, abort_times=0, gate=calls.append)

    assert calls == []


def test_gate_not_called_without_retries_even_when_supplied():
    clock = Clock()
    calls = []

    run_chain(clock, abort_times=0, max_attempts=1, gate=calls.append)

    assert calls == []


@pytest.mark.parametrize('abort_times', [1, 2, 3, 4])
def test_gate_called_once_per_failed_rung_with_failed_attempt(abort_times):
    clock = Clock()
    calls = []

    run_chain(clock, abort_times=abort_times, gate=calls.append)

    assert calls == list(range(1, abort_times + 1))


def test_gate_not_called_for_non_contention_failure():
    clock = Clock()
    calls = []

    def operation(tx):
        raise ValueError('not contention')

    with pytest.raises(ValueError):
        run_with_transaction_contention_retry(
            lambda: AbortNTimesTx(0),
            operation,
            operation_name='probe',
            sleep=clock.sleep,
            random_value=clock.random_value,
            monotonic=clock.monotonic,
            inter_attempt_gate=calls.append,
        )

    assert calls == []
    assert clock.sleeps == []


def test_gate_not_called_on_the_exhausting_attempt():
    clock = Clock()
    calls = []

    with pytest.raises(FirestoreContentionExhausted):
        run_chain(clock, abort_times=10**6, max_attempts=3, gate=calls.append)

    assert calls == [1, 2]


def test_gate_wait_joins_the_equal_jitter_sleep():
    clock = Clock()
    run_chain(clock, abort_times=2, gate=lambda attempt: 0.5)
    assert clock.sleeps == [0.2 + 0.5, 0.4 + 0.5]


def test_bare_schedule_unchanged_when_gate_returns_zero():
    clock = Clock(jitter=0.0)
    run_chain(clock, abort_times=2, gate=lambda attempt: 0.0)
    assert clock.sleeps == [0.1, 0.2]


@pytest.mark.parametrize('answer', [True, False, '0.5', None, float('nan'), float('inf'), 0.0, -1.0])
def test_hostile_gate_answer_collapses_to_zero(answer):
    clock = Clock(jitter=0.0)
    run_chain(clock, abort_times=2, gate=lambda attempt: answer)
    assert clock.sleeps == [0.1, 0.2]


def test_raising_gate_collapses_to_zero_and_chain_recovers():
    clock = Clock(jitter=0.0)

    def hostile(attempt):
        raise RuntimeError('gate down')

    result = run_chain(clock, abort_times=2, gate=hostile)
    assert result == 'ok'
    assert clock.sleeps == [0.1, 0.2]


def test_gate_wait_added_even_at_the_widest_rung():
    clock = Clock(jitter=1.0)
    run_chain(clock, abort_times=4, gate=lambda attempt: 4.0)
    assert clock.sleeps == [0.2 + 4.0, 0.4 + 4.0, 0.8 + 4.0, 1.6 + 4.0]


# ------------------------------------------------------------ deadline gates


def test_deadline_refuses_retry_when_gate_exceeds_remaining():
    clock = Clock()  # now stays fixed: remaining is 0.25 forever
    calls = []

    def gate(attempt):
        calls.append(attempt)
        return 5.0

    with pytest.raises(FirestoreContentionExhausted) as caught:
        run_chain(clock, abort_times=10**6, max_attempts=3, gate=gate, deadline=100.25)

    assert caught.value.reason == 'deadline_exhausted'
    assert calls == [1]  # the gate was consulted for the refused retry
    assert clock.sleeps == []


def test_deadline_allows_retry_when_jitter_plus_gate_fits():
    clock = Clock(jitter=0.0)
    calls = []

    def gate(attempt):
        calls.append(attempt)
        return 0.05

    result = run_chain(clock, abort_times=1, gate=gate, deadline=200.0)

    assert result == 'ok'
    assert calls == [1]
    assert clock.sleeps == [pytest.approx(0.15)]


def test_deadline_never_refuses_the_first_attempt_even_with_gate():
    clock = Clock()
    calls = []

    with pytest.raises(FirestoreContentionExhausted) as caught:
        run_chain(clock, abort_times=10**6, max_attempts=1, gate=lambda attempt: 99.0, deadline=100.0)

    assert caught.value.reason == 'attempts_exhausted'
    assert calls == []
    assert clock.sleeps == []


def test_deadline_exhausted_log_carries_gate_ms(caplog):
    import logging

    clock = Clock()
    with caplog.at_level(logging.ERROR, logger='database.firestore_transaction_retry'):
        with pytest.raises(FirestoreContentionExhausted):
            run_chain(clock, abort_times=10**6, max_attempts=2, gate=lambda attempt: 1.0, deadline=100.25)

    line = [record.getMessage() for record in caplog.records if 'deadline_exhausted' in record.getMessage()][0]
    assert 'gate_ms=1000' in line
    assert 'delay_ms=200' in line


def test_retry_log_carries_gate_ms_even_when_zero(caplog):
    import logging

    clock = Clock(jitter=1.0)
    with caplog.at_level(logging.INFO, logger='database.firestore_transaction_retry'):
        run_chain(clock, abort_times=1)

    line = [record.getMessage() for record in caplog.records if 'outcome=retry' in record.getMessage()][0]
    assert 'outcome=retry delay_ms=200 gate_ms=0' in line


def test_retry_log_carries_nonzero_gate_ms(caplog):
    import logging

    clock = Clock(jitter=1.0)
    with caplog.at_level(logging.INFO, logger='database.firestore_transaction_retry'):
        run_chain(clock, abort_times=1, gate=lambda attempt: 0.75)

    line = [record.getMessage() for record in caplog.records if 'outcome=retry' in record.getMessage()][0]
    assert 'outcome=retry delay_ms=200 gate_ms=750' in line


def test_recovered_line_unchanged_by_the_gate(caplog):
    import logging

    clock = Clock(jitter=1.0)
    with caplog.at_level(logging.INFO, logger='database.firestore_transaction_retry'):
        run_chain(clock, abort_times=1, gate=lambda attempt: 0.1)

    recovered = [record.getMessage() for record in caplog.records if 'outcome=recovered' in record.getMessage()]
    assert recovered == ['firestore_transaction_contention operation=probe attempt=2/5 outcome=recovered']


# ------------------------------------------------------- store wiring pins


def exhaust_label(store, label, times=1):
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


def exhausting_client():
    client = Mock()
    client.transaction.side_effect = lambda max_attempts=5: AbortNTimesTx(10**6)
    return client


@pytest.fixture
def dev_store(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    return storage.FirestoreStore('batch_pipeline_dev', firestore_client=exhausting_client())


def make_mid_chain_store(monkeypatch, clock, *, aborts=2, arm_at=None):
    """A dev store whose body aborts ``aborts`` times; ``arm_at`` arms mid-flight.

    The retry helper runs on the injected clock: sleeps are recorded, never
    real, and the jitter is deterministic.
    """
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
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
    client.transaction.side_effect = lambda max_attempts=5: AbortNTimesTx(0)
    store = storage.FirestoreStore('batch_pipeline_dev', firestore_client=client, storm_damper=damper)
    real_arm = damper.arm
    runs = {'n': 0}
    armed = {'done': False}

    def body(tx):
        runs['n'] += 1
        if arm_at is not None and runs['n'] == arm_at and not armed['done']:
            armed['done'] = True
            real_arm('batch_merge_commit')
        if runs['n'] <= aborts:
            raise Aborted('synthetic mid-chain')
        return 'committed'

    return store, damper, body


def test_store_run_succeeds_through_a_gated_chain(monkeypatch):
    clock = Clock()
    store, _damper, body = make_mid_chain_store(monkeypatch, clock, aborts=1)
    assert store.run(body, operation='batch_merge_commit') == 'committed'
    assert clock.sleeps == [pytest.approx(0.2)]  # one bare retry rung, no window anywhere


def test_store_exhaustion_still_stamps_retry_after(monkeypatch, dev_store):
    error = exhaust_label(dev_store, 'batch_merge_commit')
    assert error.retry_after > 0.0


def test_peek_matches_consult_generation_on_a_quiet_label(monkeypatch, dev_store):
    residual, generation = dev_store._storm_damper.peek('batch_merge_commit')
    assert residual == 0.0
    assert generation == 0


def test_peek_reads_an_armed_window_without_sleeping(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = Clock(now=100.0, jitter=1.0)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    damper.arm('batch_merge_commit')
    sleeps_before = list(clock.sleeps)
    residual, generation = damper.peek('batch_merge_commit')
    assert residual == pytest.approx(0.25)
    assert generation == 1
    assert clock.sleeps == sleeps_before  # peek never sleeps


def test_peek_is_never_negative_for_an_expired_window(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = Clock(now=100.0, jitter=1.0)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    damper.arm('batch_merge_commit')
    clock.advance(999.0)
    residual, generation = damper.peek('batch_merge_commit')
    assert residual == 0.0
    assert generation == 1


def test_consult_still_sleeps_the_residual(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = Clock(now=100.0, jitter=1.0)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    damper.arm('batch_merge_commit')
    waited, generation = damper.consult('batch_merge_commit')
    assert waited == pytest.approx(0.25)
    assert generation == 1
    assert clock.sleeps == [pytest.approx(0.25)]


def test_scope_mid_ladder_log_names_label_attempt_and_wait(monkeypatch, caplog):
    import logging

    clock = Clock(now=100.0, jitter=1.0)
    store, _damper, body = make_mid_chain_store(monkeypatch, clock, aborts=2, arm_at=2)

    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        assert store.run(body, operation='batch_merge_commit') == 'committed'

    lines = [record.getMessage() for record in caplog.records if 'scope=mid_ladder' in record.getMessage()]
    assert len(lines) == 1
    assert 'operation=batch_merge_commit' in lines[0]
    assert 'attempt=2' in lines[0]
    assert 'waited_ms=250' in lines[0]


def test_gate_waits_out_a_sibling_window_mid_chain(monkeypatch):
    clock = Clock(now=100.0, jitter=1.0)
    store, _damper, body = make_mid_chain_store(monkeypatch, clock, aborts=2, arm_at=2)

    assert store.run(body, operation='batch_merge_commit') == 'committed'
    # rung 1: bare jitter. rung 2: jitter plus the sibling window seen mid-flight.
    assert clock.sleeps[0] == pytest.approx(0.2)
    assert clock.sleeps[1] == pytest.approx(0.4 + 0.25)


def test_success_clears_a_window_armed_mid_chain(monkeypatch):
    clock = Clock(now=100.0, jitter=1.0)
    store, damper, body = make_mid_chain_store(monkeypatch, clock, aborts=2, arm_at=2)

    assert store.run(body, operation='batch_merge_commit') == 'committed'
    residual, generation = damper.peek('batch_merge_commit')
    assert residual == 0.0
    assert generation == 0


def test_no_gate_when_the_storm_damper_kill_switch_is_off(monkeypatch, caplog):
    import logging

    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED', 'false')
    clock = Clock(now=100.0, jitter=1.0)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    damper.arm('batch_merge_commit')  # window armed on the damper object...
    client = Mock()
    client.transaction.side_effect = lambda max_attempts=5: AbortNTimesTx(0)
    store = storage.FirestoreStore('batch_pipeline_dev', firestore_client=client, storm_damper=damper)
    runs = {'n': 0}

    def body(tx):
        runs['n'] += 1
        if runs['n'] <= 1:
            raise Aborted('synthetic mid-chain')
        return 'committed'

    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        assert store.run(body, operation='batch_merge_commit') == 'committed'
    # ...but a dormant damper is never consulted: no entry sleep, no mid-ladder
    # gate wait, and the retry chain rides the bare ladder through real time.
    assert not [record for record in caplog.records if 'scope=mid_ladder' in record.getMessage()]
    assert clock.sleeps == []
    # The armed window survives untouched: a dormant damper never clears it.
    residual, generation = damper.peek('batch_merge_commit')
    assert residual == pytest.approx(0.25)
    assert generation == 1


def test_no_gate_when_contention_retry_kill_switch_is_off(monkeypatch, caplog):
    import logging

    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_RETRY_ENABLED', 'false')
    clock = Clock(now=100.0, jitter=1.0)
    damper = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    damper.arm('batch_merge_commit')
    client = Mock()
    client.transaction.side_effect = lambda max_attempts=5: AbortNTimesTx(0)
    store = storage.FirestoreStore('batch_pipeline_dev', firestore_client=client, storm_damper=damper)
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        assert store.run(lambda tx: 'committed', operation='batch_merge_commit') == 'committed'
    assert not [record for record in caplog.records if 'scope=mid_ladder' in record.getMessage()]
    assert clock.sleeps == []
