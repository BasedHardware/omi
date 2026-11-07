"""The reserve gate's boundaries under the wave-bridge schedule, named row by row.

A retry (attempt 2 onward) starts only while the remaining wall-clock budget
covers ``max(last attempt's observed duration x 1.5, 30 s)``. The wave-bridge
cap does not move that gate: this suite walks its boundaries exactly — the
admitting and refusing sides of the 30 s floor for short attempts, the 1.5x
observed-duration reserve for long chains, the attempt-1 sleep truncation at
the 0.2 s jitter, and the acceptance boundary where an admitted retry's sleep
always fits because the floor dominates the cap.

Failure-Class: FC-contention-chain-spends-its-budget-inside-one-abort-wave
"""

import logging

import pytest
from google.api_core.exceptions import InvalidArgument

from database.firestore_transaction_retry import (
    FIRESTORE_TRANSACTION_CHAIN_SECONDS,
    RETRY_RESERVE_FACTOR,
    RETRY_RESERVE_FLOOR_SECONDS,
    _MAX_DELAY_SECONDS,
    FirestoreContentionExhausted,
    run_with_transaction_contention_retry,
    transaction_retry_deadline_scope,
)

EXPIRED = 'The referenced transaction has expired or is no longer valid.'


class FakeClock:
    def __init__(self, now: float = 1000.0):
        self.now = now

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def expired():
    return InvalidArgument(EXPIRED)


def aborted():
    from google.api_core.exceptions import Aborted

    return Aborted('read contention')


def run_chain(clock, budget_seconds, attempt_seconds=0.0, error_factory=None, max_attempts=5):
    """Always-failing chain under a deadline; return (attempts_run, reason_or_None)."""
    attempts = []
    error_factory = error_factory or expired

    def operation(transaction):
        attempts.append(1)
        clock.now += attempt_seconds
        raise error_factory()

    start = clock.monotonic()
    try:
        run_with_transaction_contention_retry(
            lambda: object(),
            operation,
            operation_name='gate',
            deadline=start + budget_seconds,
            sleep=clock.sleep,
            random_value=lambda: 1,
            monotonic=clock.monotonic,
            max_attempts=max_attempts,
        )
    except FirestoreContentionExhausted as raised:
        return len(attempts), raised.reason
    return len(attempts), None


# --------------------------------------------------------------------------
# The 30 s floor with sub-second attempts
# --------------------------------------------------------------------------


def test_budget_of_two_floor_windows_admits_two_attempts():
    # 0.1s attempts + jitter sleeps: after attempt 1 (0.1s + 0.2s gap), 30.2s
    # remain >= the 30s floor -> admit; after attempt 2 (0.1s + 0.4s gap),
    # 29.7s remain -> refuse at the attempt-3 gate.
    attempts, reason = run_chain(FakeClock(), 30.5, attempt_seconds=0.1)
    assert (attempts, reason) == (2, 'deadline_exhausted')


def test_budget_at_one_floor_window_admits_only_one_retry():
    attempts, reason = run_chain(FakeClock(), 30.1, attempt_seconds=0.1)
    # 0.1s attempt + 0.2s jitter leaves 29.8s: below the floor, no second try.
    assert attempts == 1
    assert reason == 'deadline_exhausted'


def test_budget_just_below_the_floor_refuses_the_first_retry():
    attempts, reason = run_chain(FakeClock(), 30.05, attempt_seconds=0.1)
    # After the 0.1s attempt, 29.95s remain: below the floor, no retry.
    assert (attempts, reason) == (1, 'deadline_exhausted')


def test_budget_at_the_floor_refuses_the_first_retry():
    attempts, reason = run_chain(FakeClock(), 30.0, attempt_seconds=0.1)
    assert (attempts, reason) == (1, 'deadline_exhausted')


def test_budget_below_the_floor_still_runs_attempt_one():
    attempts, reason = run_chain(FakeClock(), 1.0, attempt_seconds=0.1)
    assert (attempts, reason) == (1, 'deadline_exhausted')


def test_zero_budget_still_runs_attempt_one():
    attempts, reason = run_chain(FakeClock(), 0.0)
    assert (attempts, reason) == (1, 'deadline_exhausted')


def test_negative_budget_still_runs_attempt_one():
    attempts, reason = run_chain(FakeClock(), -5.0)
    assert (attempts, reason) == (1, 'deadline_exhausted')


def test_short_attempts_inside_a_sixty_second_budget_reach_the_attempt_cap():
    attempts, reason = run_chain(FakeClock(), 60.0, attempt_seconds=5.0, error_factory=aborted)
    # Sixty seconds minus five 5s attempts minus the 1.5s of gaps stays above
    # the floor until the fifth attempt completes: the attempt cap decides.
    assert (attempts, reason) == (5, 'attempts_exhausted')


def test_one_twenty_second_budget_with_tens_reaches_the_cap():
    attempts, reason = run_chain(FakeClock(), 120.0, attempt_seconds=10.0, error_factory=aborted)
    assert (attempts, reason) == (5, 'attempts_exhausted')


# --------------------------------------------------------------------------
# The 1.5x observed-duration reserve with long attempts
# --------------------------------------------------------------------------


def test_one_270s_attempt_inside_a_405s_budget_runs_one_attempt():
    attempts, reason = run_chain(FakeClock(), 405.0, attempt_seconds=270.0)
    assert (attempts, reason) == (1, 'deadline_exhausted')


def test_one_270s_attempt_inside_a_676s_budget_runs_two_attempts():
    # After attempt 1: 406.1s remain >= the 405s reserve -> admit; after
    # attempt 2: 136.1s < 405s -> refuse at the attempt-3 gate.
    attempts, reason = run_chain(FakeClock(), 676.1, attempt_seconds=270.0)
    assert (attempts, reason) == (2, 'deadline_exhausted')


def test_reserve_is_one_point_five_times_the_observed_duration():
    assert RETRY_RESERVE_FACTOR == 1.5
    attempts, reason = run_chain(FakeClock(), 601.0, attempt_seconds=400.0)
    # Reserve after attempt 1 = 600s; remaining 201s -> refuse immediately.
    assert (attempts, reason) == (1, 'deadline_exhausted')


def test_reserve_floor_is_thirty_seconds():
    assert RETRY_RESERVE_FLOOR_SECONDS == 30.0


def test_generous_budget_lets_the_full_chain_run():
    attempts, reason = run_chain(FakeClock(), 5000.0, attempt_seconds=270.0, error_factory=aborted)
    assert (attempts, reason) == (5, 'attempts_exhausted')


def test_the_accepted_wall_bound_holds_at_the_boundary_budget():
    clock = FakeClock()
    attempts, reason = run_chain(clock, 676.1, attempt_seconds=270.0)
    assert clock.now - 1000.0 <= 676.1 + 270.0  # deadline + one in-flight attempt


def test_max_jitter_gaps_fit_a_budget_the_gate_admitted():
    # A 700s budget with 270s attempts: two attempts run, both jitter gaps
    # (0.2s, 0.4s) are charged inside the budget — never past the deadline.
    clock = FakeClock()
    attempts, reason = run_chain(clock, 700.0, attempt_seconds=270.0)
    assert attempts == 2
    assert clock.now - 1000.0 < 700.0


# --------------------------------------------------------------------------
# Attempt-1 sleep truncation at the 0.2s jitter boundary
# --------------------------------------------------------------------------


def test_budget_leaves_less_than_the_first_jitter_no_sleep_runs():
    # Attempt 1 = 270s; 0.15s remain: below the 0.2s maximum first jitter.
    clock = FakeClock()
    attempts, reason = run_chain(clock, 270.15, attempt_seconds=270.0)
    assert (attempts, reason) == (1, 'deadline_exhausted')
    assert clock.now - 1000.0 == pytest.approx(270.0)


def test_budget_leaves_exactly_the_first_jitter_the_sleep_runs():
    # 0.2s remain: the jitter sleep is charged exactly, then the attempt-2
    # gate refuses (nothing left against the 30s floor).
    clock = FakeClock()
    attempts, reason = run_chain(clock, 270.2, attempt_seconds=270.0)
    assert attempts == 1
    assert clock.now - 1000.0 == pytest.approx(270.2)


def test_budget_leaves_more_than_the_first_jitter_then_the_gate_refuses():
    clock = FakeClock()
    attempts, reason = run_chain(clock, 270.3, attempt_seconds=270.0)
    assert attempts == 1
    assert clock.now - 1000.0 == pytest.approx(270.2)


def test_sleep_truncation_logs_the_delay_and_attempt(caplog):
    clock = FakeClock()
    with caplog.at_level(logging.ERROR, logger='database.firestore_transaction_retry'):
        run_chain(clock, 270.15, attempt_seconds=270.0)
    lines = [record.getMessage() for record in caplog.records if 'deadline_exhausted' in record.getMessage()]
    assert len(lines) == 1
    assert 'attempt=1/5' in lines[0]
    assert 'delay_ms=200' in lines[0]
    assert 'remaining_ms=150' in lines[0]


def test_gate_refusal_logs_remaining_and_reserve(caplog):
    clock = FakeClock()
    with caplog.at_level(logging.ERROR, logger='database.firestore_transaction_retry'):
        run_chain(clock, 405.0, attempt_seconds=270.0)
    lines = [record.getMessage() for record in caplog.records if 'deadline_exhausted' in record.getMessage()]
    assert len(lines) == 1
    assert 'attempt=2/5' in lines[0]
    # 405 - 270 (attempt 1) - 0.2 (its jitter sleep) = 134.8s remaining.
    assert 'remaining_ms=134800' in lines[0]
    assert 'reserve_ms=405000' in lines[0]


def test_no_deadline_scope_never_gates():
    clock = FakeClock()
    attempts = []

    def operation(transaction):
        attempts.append(1)
        clock.now += 270.0
        raise expired()

    start = clock.monotonic()
    with transaction_retry_deadline_scope(None):
        with pytest.raises(FirestoreContentionExhausted):
            run_with_transaction_contention_retry(
                lambda: object(),
                operation,
                operation_name='ungated',
                sleep=clock.sleep,
                random_value=lambda: 1,
                monotonic=clock.monotonic,
            )
    assert len(attempts) == 3  # the expired-chain ceiling, not a gate


# --------------------------------------------------------------------------
# The gate and the cap stay independent
# --------------------------------------------------------------------------


def test_the_cap_is_never_the_thing_the_gate_measures():
    # The gate measures the last attempt's observed duration and the floor;
    # the jitter cap only bounds the sleep between attempts. A budget sized
    # exactly at the cap is refused by the floor, not by a delay.
    attempts, reason = run_chain(FakeClock(), _MAX_DELAY_SECONDS, attempt_seconds=0.5)
    assert (attempts, reason) == (1, 'deadline_exhausted')


def test_a_full_chain_lifetime_attempt_never_gates_attempt_one():
    attempts, reason = run_chain(
        clock := FakeClock(), FIRESTORE_TRANSACTION_CHAIN_SECONDS, attempt_seconds=FIRESTORE_TRANSACTION_CHAIN_SECONDS
    )
    assert (attempts, reason) == (1, 'deadline_exhausted')


def test_an_expired_budget_can_only_remove_retries_never_attempt_one():
    """The gate never refuses attempt 1, and it stops the loop before a second
    attempt when the budget is already gone: a dead budget cannot resurrect
    the chain, but it never made attempt 1 worse than running once."""
    clock = FakeClock()
    seen = []

    def operation(transaction):
        seen.append(1)
        clock.now += 270.0
        raise expired()

    start = clock.monotonic()
    with pytest.raises(FirestoreContentionExhausted) as raised:
        run_with_transaction_contention_retry(
            lambda: object(),
            operation,
            operation_name='dead_budget',
            deadline=start + 1.0,
            sleep=clock.sleep,
            random_value=lambda: 1,
            monotonic=clock.monotonic,
        )
    assert raised.value.reason == 'deadline_exhausted'
    assert len(seen) == 1


def test_without_a_deadline_a_dead_wave_lands_on_attempt_two():
    """The counterpart: with no budget in scope the retry runs, and a wave
    that died during attempt 1 commits there."""
    clock = FakeClock()
    seen = []

    def operation(transaction):
        seen.append(1)
        if len(seen) == 1:
            clock.now += 270.0
            raise expired()
        return 'committed'

    run_with_transaction_contention_retry(
        lambda: object(),
        operation,
        operation_name='no_budget_recovery',
        sleep=clock.sleep,
        random_value=lambda: 1,
        monotonic=clock.monotonic,
    )
    assert seen == [1, 1]
