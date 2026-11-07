"""Minimum-jitter depth rows and the remaining gate boundaries.

The counterpart rows to the depth-and-gate matrix at the low jitter edge: a
chain of depth k under zero jitter spans the low edge of each of its k-1
gaps, the exhausted opt-in chains' low-edge windows, and four more gate rows
for the transition budgets between the attempt cap and the reserve floor.

Failure-Class: FC-contention-chain-spends-its-budget-inside-one-abort-wave
"""

import pytest
from google.api_core.exceptions import Aborted

from database.firestore_transaction_retry import FirestoreContentionExhausted, run_with_transaction_contention_retry


class FakeClock:
    def __init__(self, now: float = 1000.0):
        self.now = now

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def depth_row(depth, jitter=0.0):
    clock = FakeClock()
    sleeps = []
    state = {'n': 0}

    def operation(transaction):
        state['n'] += 1
        if state['n'] < depth:
            raise Aborted('contention')
        return 'committed'

    run_with_transaction_contention_retry(
        lambda: object(),
        operation,
        operation_name='low',
        max_attempts=max(depth, 1),
        sleep=lambda seconds: (sleeps.append(seconds), clock.sleep(seconds)) and None,
        random_value=lambda: jitter,
        monotonic=clock.monotonic,
    )
    return sleeps, state['n']


def test_low_jitter_depth_2_gaps_are_the_low_edge():
    sleeps, attempts = depth_row(2)
    assert sleeps == [0.1] and attempts == 2


def test_low_jitter_depth_3_gaps_are_the_low_edges():
    sleeps, attempts = depth_row(3)
    assert sleeps == [0.1, 0.2] and attempts == 3


def test_low_jitter_depth_4_gaps_are_the_low_edges():
    sleeps, attempts = depth_row(4)
    assert sleeps == [0.1, 0.2, 0.4] and attempts == 4


def test_low_jitter_depth_5_gaps_are_the_low_edges():
    sleeps, attempts = depth_row(5)
    assert sleeps == [0.1, 0.2, 0.4, 0.8] and attempts == 5


def test_low_jitter_depth_6_opt_in_gaps_are_the_low_edges():
    sleeps, attempts = depth_row(6)
    assert sleeps == [0.1, 0.2, 0.4, 0.8, 1.6] and attempts == 6


def test_low_jitter_depth_7_opt_in_gaps_are_the_low_edges():
    # The sixth gap is inside the cap: its low edge is half of 4.0s.
    sleeps, attempts = depth_row(7)
    assert sleeps == [0.1, 0.2, 0.4, 0.8, 1.6, 2.0] and attempts == 7


def exhausted_row(depth, jitter=0.0):
    clock = FakeClock()
    sleeps = []
    state = {'n': 0}

    def operation(transaction):
        state['n'] += 1
        raise Aborted('contention')

    with pytest.raises(FirestoreContentionExhausted):
        run_with_transaction_contention_retry(
            lambda: object(),
            operation,
            operation_name='lowex',
            max_attempts=depth,
            sleep=lambda seconds: (sleeps.append(seconds), clock.sleep(seconds)) and None,
            random_value=lambda: jitter,
            monotonic=clock.monotonic,
        )
    return sleeps, state['n']


def test_low_jitter_exhausted_depth_6_window_is_three_point_one():
    sleeps, attempts = exhausted_row(6)
    assert sum(sleeps) == pytest.approx(3.1)
    assert attempts == 6


def test_low_jitter_exhausted_depth_7_window_is_five_point_one():
    sleeps, attempts = exhausted_row(7)
    assert sum(sleeps) == pytest.approx(5.1)
    assert attempts == 7


# --------------------------------------------------------------------------
# Gate rows for the cap-versus-floor transition budgets (1 s attempts)
# --------------------------------------------------------------------------


def gate_row(budget_seconds, attempt_seconds):
    clock = FakeClock()
    attempts = []

    def operation(transaction):
        attempts.append(1)
        clock.now += attempt_seconds
        raise Aborted('contention')

    try:
        run_with_transaction_contention_retry(
            lambda: object(),
            operation,
            operation_name='t',
            deadline=clock.monotonic() + budget_seconds,
            sleep=clock.sleep,
            random_value=lambda: 1,
            monotonic=clock.monotonic,
        )
    except FirestoreContentionExhausted:
        return len(attempts)
    return len(attempts)


def test_gate_row_32_seconds_runs_two_attempts():
    # a1 1s + 0.2s gap leaves 30.8s >= 30 floor -> admit; a2 1s + 0.4s gap
    # leaves 29.4s < floor -> refuse at the a3 gate.
    assert gate_row(32.0, 1.0) == 2


def test_gate_row_35_seconds_runs_four_attempts():
    # The a4 gate sees 31.4s >= the floor; the a5 gate sees 29.6s and refuses.
    assert gate_row(35.0, 1.0) == 4


def test_gate_row_34_seconds_runs_three_attempts():
    assert gate_row(34.0, 1.0) == 3


def test_gate_row_33_seconds_runs_three_attempts():
    # After a2 (1s + 0.4s): 30.4s >= 30 admit; a3 (1s + 0.8s): 28.8 < 30 refuse.
    assert gate_row(33.0, 1.0) == 3


def test_gate_rows_are_monotone_in_the_budget():
    budgets = [28.0, 30.0, 32.0, 33.0, 34.0, 35.0, 38.0]
    runs = [gate_row(b, 1.0) for b in budgets]
    assert runs == sorted(runs)
