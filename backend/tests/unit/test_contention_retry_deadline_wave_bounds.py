"""Deadline-scoped contention budgets keep their accepted wall bounds under the wave bridge.

The wave-bridge cap grows the no-deadline chain's four inter-attempt gaps to a
1.5-3.0 s window (attempt 5 starts up to 3.0 s after the first abort). Callers
that own a wall-clock budget — the sync
handler's request budget, the batch projection claim's 300 s lease — must be
exactly as bounded as before: the reserve gate and the never-past-deadline
sleep do not move with the cap, attempt 1 is never refused, and the
``deadline + one in-flight attempt`` bound still holds at maximum jitter.
The 30 s reserve floor also still dominates the 4 s cap, so a retry the gate
admits can always afford its jitter sleep.

Failure-Class: FC-contention-chain-spends-its-budget-inside-one-abort-wave
"""

import logging
import threading
from contextvars import copy_context

import pytest
from google.api_core.exceptions import Aborted, InvalidArgument

from database.firestore_transaction_retry import (
    FIRESTORE_TRANSACTION_CHAIN_SECONDS,
    RETRY_RESERVE_FLOOR_SECONDS,
    _MAX_DELAY_SECONDS,
    FirestoreContentionExhausted,
    equal_jitter_delay,
    run_with_transaction_contention_retry,
    transaction_retry_deadline_scope,
)

EXPIRED = 'The referenced transaction has expired or is no longer valid.'

SYNC_HANDLER_RETRY_BUDGET_SECONDS = 1380.0 - 120.0
PROJECTION_CLAIM_RETRY_BUDGET_SECONDS = 300.0


class FakeClock:
    """Monotonic clock the operation and the retry loop share; sleeps advance it."""

    def __init__(self, now: float = 1000.0):
        self.now = now

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def expired() -> InvalidArgument:
    return InvalidArgument(EXPIRED)


def aborted() -> Aborted:
    return Aborted('read contention')


def test_wave_bridge_cap_stays_below_the_reserve_floor():
    # A retry the reserve gate admits has at least RETRY_RESERVE_FLOOR_SECONDS
    # left, so its jitter sleep (at most the cap) can never be the overspend
    # that trips the deadline. The wave bridge must not grow the cap past the
    # floor or gated budgets would need a new bound proof.
    assert _MAX_DELAY_SECONDS < RETRY_RESERVE_FLOOR_SECONDS


def test_attempt_one_sleep_truncation_is_unchanged_by_the_cap():
    # Attempt 1 is never gated; its 0.2s maximum jitter still truncates at a
    # deadline with less remaining. The wave bridge only grew the tail rungs.
    clock = FakeClock()
    calls = []

    def operation(transaction):
        calls.append(transaction)
        clock.now += FIRESTORE_TRANSACTION_CHAIN_SECONDS
        raise expired()

    start = clock.monotonic()
    with pytest.raises(FirestoreContentionExhausted) as raised:
        run_with_transaction_contention_retry(
            lambda: object(),
            operation,
            operation_name='clamped_first',
            deadline=start + FIRESTORE_TRANSACTION_CHAIN_SECONDS + 0.05,
            sleep=clock.sleep,
            random_value=lambda: 1,
            monotonic=clock.monotonic,
        )
    assert raised.value.reason == 'deadline_exhausted'
    assert len(calls) == 1
    assert clock.monotonic() - start == pytest.approx(FIRESTORE_TRANSACTION_CHAIN_SECONDS, abs=0.001)


@pytest.mark.parametrize(
    'budget_seconds,expected_attempts',
    [(SYNC_HANDLER_RETRY_BUDGET_SECONDS, 4), (PROJECTION_CLAIM_RETRY_BUDGET_SECONDS, 1)],
)
def test_real_caller_budgets_stop_at_the_reserve_gate_not_the_deadline(budget_seconds, expected_attempts):
    # The wave-bridge tail rungs do not move these bounds: after each 270s
    # chain the 405s reserve (1.5 x observed) decides, and the accepted
    # deadline + one in-flight attempt bound still holds at maximum jitter.
    clock = FakeClock()
    attempts = []

    def operation(transaction):
        attempts.append(1)
        clock.now += FIRESTORE_TRANSACTION_CHAIN_SECONDS
        raise aborted()

    start = clock.monotonic()
    with pytest.raises(FirestoreContentionExhausted) as raised:
        run_with_transaction_contention_retry(
            lambda: object(),
            operation,
            operation_name='budgeted',
            deadline=start + budget_seconds,
            sleep=clock.sleep,
            random_value=lambda: 1,
            monotonic=clock.monotonic,
        )
    assert raised.value.reason == 'deadline_exhausted'
    assert len(attempts) == expected_attempts
    assert clock.monotonic() - start <= budget_seconds + FIRESTORE_TRANSACTION_CHAIN_SECONDS


@pytest.mark.parametrize(
    'budget_seconds,attempt_seconds,error_factory,expected_attempts,expected_reason',
    [
        pytest.param(None, 270.0, aborted, 5, 'attempts_exhausted', id='no-deadline-keeps-attempt-bound'),
        pytest.param(
            1260.0, 270.0, aborted, 4, 'deadline_exhausted', id='sync-handler-budget-stops-at-the-reserve-gate'
        ),
        pytest.param(300.0, 270.0, expired, 1, 'deadline_exhausted', id='projection-claim-budget-gate'),
        pytest.param(0.0, 270.0, expired, 1, 'deadline_exhausted', id='zero-budget-still-runs-one-attempt'),
        pytest.param(60.0, 5.0, aborted, 5, 'attempts_exhausted', id='short-attempts-reach-the-cap-inside-a-budget'),
        pytest.param(10.0, 5.0, expired, 1, 'deadline_exhausted', id='budget-below-the-reserve-floor-stops-after-one'),
    ],
)
def test_deadline_bounds_unchanged_at_maximum_jitter(
    budget_seconds, attempt_seconds, error_factory, expected_attempts, expected_reason
):
    clock = FakeClock()
    calls = []

    def operation(transaction):
        calls.append(transaction)
        clock.now += attempt_seconds
        raise error_factory()

    start = clock.monotonic()
    deadline = None if budget_seconds is None else start + budget_seconds
    with pytest.raises(FirestoreContentionExhausted) as raised:
        run_with_transaction_contention_retry(
            lambda: object(),
            operation,
            operation_name='bounded',
            deadline=deadline,
            sleep=clock.sleep,
            random_value=lambda: 1,
            monotonic=clock.monotonic,
        )
    assert raised.value.reason == expected_reason
    assert len(calls) == expected_attempts
    if budget_seconds is not None:
        assert clock.monotonic() - start <= budget_seconds + attempt_seconds


def test_full_storm_inside_a_generous_budget_reaches_the_attempt_cap():
    # A 2000s budget admits every gate (reserve 405s after each 270s attempt),
    # so the wave-bridge chain still ends at the attempt cap, never the gate.
    clock = FakeClock()
    attempts = []

    def operation(transaction):
        attempts.append(1)
        clock.now += FIRESTORE_TRANSACTION_CHAIN_SECONDS
        raise aborted()

    start = clock.monotonic()
    with pytest.raises(FirestoreContentionExhausted) as raised:
        run_with_transaction_contention_retry(
            lambda: object(),
            operation,
            operation_name='generous',
            deadline=start + 2000.0,
            sleep=clock.sleep,
            random_value=lambda: 1,
            monotonic=clock.monotonic,
        )
    assert raised.value.reason == 'attempts_exhausted'
    assert len(attempts) == 5


def test_reserve_gate_uses_the_last_attempts_observed_duration():
    clock = FakeClock()

    def operation(transaction):
        clock.now += 300.0
        raise expired()

    start = clock.monotonic()
    with pytest.raises(FirestoreContentionExhausted) as raised:
        run_with_transaction_contention_retry(
            lambda: object(),
            operation,
            operation_name='observed',
            deadline=start + 1000.0,
            sleep=clock.sleep,
            random_value=lambda: 1,
            monotonic=clock.monotonic,
        )
    assert raised.value.reason == 'deadline_exhausted'
    # 2 x 300s attempts + maximum jitter (0.2s + 0.4s); the third gate sees
    # 399.4s remaining against a 450s reserve. The early rungs are unchanged.
    assert clock.monotonic() - start == pytest.approx(600.6, abs=0.001)


def test_new_tail_rungs_fit_inside_a_gate_that_admits_them():
    # A 2000s budget admits every gate, so the chain reaches the attempt cap;
    # every jitter sleep (including the new 1.6s fourth rung) lands inside the
    # budget and stays below the 30s reserve floor — the sleep is never the
    # overspend that trips the deadline.
    clock = FakeClock()
    attempts = []
    recorded = []

    def operation(transaction):
        attempts.append(1)
        clock.now += FIRESTORE_TRANSACTION_CHAIN_SECONDS
        raise aborted()

    def record_sleep(seconds):
        recorded.append(seconds)
        clock.sleep(seconds)

    start = clock.monotonic()
    with pytest.raises(FirestoreContentionExhausted) as raised:
        run_with_transaction_contention_retry(
            lambda: object(),
            operation,
            operation_name='gate_fit',
            deadline=start + 2000.0,
            sleep=record_sleep,
            random_value=lambda: 1,
            monotonic=clock.monotonic,
        )
    assert raised.value.reason == 'attempts_exhausted'
    assert len(attempts) == 5
    assert recorded == [0.2, 0.4, 0.8, 1.6]
    assert clock.monotonic() - start <= 2000.0 + FIRESTORE_TRANSACTION_CHAIN_SECONDS
    assert all(seconds < RETRY_RESERVE_FLOOR_SECONDS for seconds in recorded)


def test_gate_log_reports_remaining_and_reserve_millis(caplog):
    clock = FakeClock()

    def operation(transaction):
        clock.now += FIRESTORE_TRANSACTION_CHAIN_SECONDS
        raise expired()

    with caplog.at_level(logging.ERROR, logger='database.firestore_transaction_retry'):
        with pytest.raises(FirestoreContentionExhausted):
            run_with_transaction_contention_retry(
                lambda: object(),
                operation,
                operation_name='gate_ms',
                deadline=clock.monotonic() + FIRESTORE_TRANSACTION_CHAIN_SECONDS + 10.0,
                sleep=clock.sleep,
                monotonic=clock.monotonic,
            )
    [line] = [message for message in caplog.messages if 'outcome=deadline_exhausted' in message]
    assert 'remaining_ms=' in line and 'reserve_ms=' in line
    assert 'operation=gate_ms' in line
    assert EXPIRED not in line


def test_sleep_truncation_log_reports_the_delay_millis(caplog):
    clock = FakeClock()

    def operation(transaction):
        clock.now += FIRESTORE_TRANSACTION_CHAIN_SECONDS
        raise expired()

    with caplog.at_level(logging.ERROR, logger='database.firestore_transaction_retry'):
        with pytest.raises(FirestoreContentionExhausted):
            run_with_transaction_contention_retry(
                lambda: object(),
                operation,
                operation_name='clamp_ms',
                deadline=clock.monotonic() + FIRESTORE_TRANSACTION_CHAIN_SECONDS + 0.05,
                sleep=clock.sleep,
                random_value=lambda: 1,
                monotonic=clock.monotonic,
            )
    [line] = [message for message in caplog.messages if 'outcome=deadline_exhausted' in message]
    assert 'delay_ms=200' in line
    assert 'attempt=1/5' in line


def test_ambient_deadline_scope_drives_the_gate():
    clock = FakeClock()
    attempts = []

    def operation(transaction):
        attempts.append(1)
        clock.now += FIRESTORE_TRANSACTION_CHAIN_SECONDS
        raise expired()

    start = clock.monotonic()
    with transaction_retry_deadline_scope(start + 10.0):
        with pytest.raises(FirestoreContentionExhausted) as raised:
            run_with_transaction_contention_retry(
                lambda: object(),
                operation,
                operation_name='ambient',
                sleep=clock.sleep,
                monotonic=clock.monotonic,
            )
    assert raised.value.reason == 'deadline_exhausted'
    assert len(attempts) == 1


def test_nested_none_scope_opts_back_out():
    clock = FakeClock()
    attempts = []

    def operation(transaction):
        attempts.append(1)
        raise expired()

    start = clock.monotonic()
    with transaction_retry_deadline_scope(start + 10.0):
        with transaction_retry_deadline_scope(None):
            with pytest.raises(FirestoreContentionExhausted) as raised:
                run_with_transaction_contention_retry(
                    lambda: object(),
                    operation,
                    operation_name='opted_out',
                    sleep=clock.sleep,
                    monotonic=clock.monotonic,
                )
    # Without a deadline the expired-id ceiling applies, not the outer scope.
    assert raised.value.reason == 'attempts_exhausted'
    assert len(attempts) == 3


def test_nested_scopes_take_the_inner_deadline():
    clock = FakeClock()
    attempts = []

    def operation(transaction):
        attempts.append(1)
        clock.now += FIRESTORE_TRANSACTION_CHAIN_SECONDS
        raise expired()

    start = clock.monotonic()
    with transaction_retry_deadline_scope(start + 10.0):
        with transaction_retry_deadline_scope(start + 400.0):
            with pytest.raises(FirestoreContentionExhausted) as raised:
                run_with_transaction_contention_retry(
                    lambda: object(), operation, operation_name='inner', sleep=clock.sleep, monotonic=clock.monotonic
                )
    assert len(attempts) == 1
    assert raised.value.reason == 'deadline_exhausted'


def test_scope_survives_exit_from_a_foreign_context():
    """A caller may enter the scope in one Context and exit it in another.

    The batch projection follow-up enters its claim in one ``run_blocking``
    leaf and releases it in a later leaf; ``reset`` refuses foreign tokens and
    the scope must tolerate that silently, not raise. The whole scenario runs
    inside throwaway contexts so the main test context is never modified.
    """
    holder = []

    def entering():
        scope = transaction_retry_deadline_scope(1234.5)
        scope.__enter__()
        holder.append(scope)

    def exiting():
        try:
            holder[0].__exit__(None, None, None)
            return True
        except Exception as error:  # any leak here breaks executor leaves
            return error

    entry_context = copy_context()
    entry_context.run(entering)  # the deadline lives only in this context
    foreign_context = copy_context()  # never observed the set
    outcome = foreign_context.run(exiting)
    assert outcome is True


def test_scope_reset_restores_the_previous_value():
    clock = FakeClock()

    def operation(transaction):
        raise aborted()

    start = clock.monotonic()
    with transaction_retry_deadline_scope(start + 10.0):
        with pytest.raises(FirestoreContentionExhausted) as scoped:
            run_with_transaction_contention_retry(
                lambda: object(), operation, operation_name='scoped', sleep=clock.sleep, monotonic=clock.monotonic
            )
        assert scoped.value.reason == 'deadline_exhausted'
    # After the scope exits, no ambient deadline is visible.
    with pytest.raises(FirestoreContentionExhausted) as bare:
        run_with_transaction_contention_retry(
            lambda: object(), operation, operation_name='bare', sleep=clock.sleep, monotonic=clock.monotonic
        )
    assert bare.value.reason == 'attempts_exhausted'


def test_threaded_callers_do_not_leak_the_scope():
    """``run_blocking`` copies ContextVars into executor leaves; the scope
    must stay local to the entering thread's chain of contexts."""
    errors = []

    def leaf():
        clock = FakeClock()

        def operation(transaction):
            raise aborted()

        try:
            with pytest.raises(FirestoreContentionExhausted) as raised:
                run_with_transaction_contention_retry(
                    lambda: object(), operation, operation_name='leaf', sleep=clock.sleep, monotonic=clock.monotonic
                )
            errors.append(raised.value.reason)
        except Exception as error:  # a leaked deadline would surface here as deadline_exhausted
            errors.append(error)

    with transaction_retry_deadline_scope(0.0):
        threads = [threading.Thread(target=leaf) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    assert errors == ['attempts_exhausted'] * 4


def test_explicit_deadline_parameter_wins_over_the_ambient_scope():
    clock = FakeClock()
    attempts = []

    def operation(transaction):
        attempts.append(1)
        clock.now += FIRESTORE_TRANSACTION_CHAIN_SECONDS
        raise expired()

    start = clock.monotonic()
    with transaction_retry_deadline_scope(start + 10.0):
        with pytest.raises(FirestoreContentionExhausted) as raised:
            run_with_transaction_contention_retry(
                lambda: object(),
                operation,
                operation_name='explicit',
                deadline=start + 1000.0,
                sleep=clock.sleep,
                monotonic=clock.monotonic,
            )
    # The explicit 1000s budget governs; the ambient 10s scope is ignored.
    assert len(attempts) >= 3
    assert raised.value.reason in {'deadline_exhausted', 'attempts_exhausted'}


@pytest.mark.parametrize('attempt', [1, 2, 3, 4, 5])
def test_every_ladder_rung_fits_inside_the_reserve_floor(attempt):
    assert equal_jitter_delay(attempt, random_value=lambda: 1.0) < RETRY_RESERVE_FLOOR_SECONDS
