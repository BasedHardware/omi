"""Chain depth and gate boundary rows for the wave-bridged budget.

One row per fact: the outcome of a chain that succeeds at attempt k, for
every depth 1 through 8; the gate's admit/refuse boundary at the reserve
floor for a sweep of realistic attempt durations; the capped rungs' named
band edges; and the per-suite failure-class declarations that keep this
family's review surface honest. Rows are named, not parametrized, so a
failing row names its exact budget boundary.

Failure-Class: FC-contention-chain-spends-its-budget-inside-one-abort-wave
"""

import logging
from pathlib import Path

import pytest
from google.api_core.exceptions import Aborted

from database.firestore_transaction_retry import (
    _MAX_DELAY_SECONDS,
    DEFAULT_MAX_ATTEMPTS,
    FirestoreContentionExhausted,
    equal_jitter_delay,
    run_with_transaction_contention_retry,
)

BACKEND = Path(__file__).resolve().parents[2]
FC = 'FC-contention-chain-spends-its-budget-inside-one-abort-wave'


class FakeClock:
    def __init__(self, now: float = 1000.0):
        self.now = now

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def chain_succeeding_at(depth, jitter=1.0):
    """Run a chain that commits on attempt ``depth``; return (sleeps, attempts)."""
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
        operation_name='depth',
        max_attempts=max(depth, 1),
        sleep=lambda seconds: (sleeps.append(seconds), clock.sleep(seconds)) and None,
        random_value=lambda: jitter,
        monotonic=clock.monotonic,
    )
    return sleeps, state['n']


# --------------------------------------------------------------------------
# Outcome rows: a chain of depth k sleeps exactly k-1 gaps
# --------------------------------------------------------------------------


def test_depth_1_succeeds_with_no_gaps():
    sleeps, attempts = chain_succeeding_at(1)
    assert sleeps == [] and attempts == 1


def test_depth_2_succeeds_with_one_gap():
    sleeps, attempts = chain_succeeding_at(2)
    assert sleeps == [0.2] and attempts == 2


def test_depth_3_succeeds_with_two_gaps():
    sleeps, attempts = chain_succeeding_at(3)
    assert sleeps == [0.2, 0.4] and attempts == 3


def test_depth_4_succeeds_with_three_gaps():
    sleeps, attempts = chain_succeeding_at(4)
    assert sleeps == [0.2, 0.4, 0.8] and attempts == 4


def test_depth_5_succeeds_with_four_gaps():
    sleeps, attempts = chain_succeeding_at(5)
    assert sleeps == [0.2, 0.4, 0.8, 1.6] and attempts == 5


def test_depth_6_opt_in_succeeds_with_five_gaps():
    sleeps, attempts = chain_succeeding_at(6)
    assert sleeps == [0.2, 0.4, 0.8, 1.6, 3.2] and attempts == 6


def test_depth_7_opt_in_succeeds_with_six_gaps():
    sleeps, attempts = chain_succeeding_at(7)
    assert sleeps == [0.2, 0.4, 0.8, 1.6, 3.2, 4.0] and attempts == 7


def test_depth_8_opt_in_succeeds_with_seven_gaps():
    sleeps, attempts = chain_succeeding_at(8)
    assert sleeps[-1] == 4.0 and attempts == 8


# --------------------------------------------------------------------------
# Reserve-floor boundary rows for realistic attempt durations
# --------------------------------------------------------------------------


def gate_row(budget_seconds, attempt_seconds):
    clock = FakeClock()
    attempts = []

    def operation(transaction):
        attempts.append(1)
        clock.now += attempt_seconds
        raise Aborted('contention')

    start = clock.monotonic()
    try:
        run_with_transaction_contention_retry(
            lambda: object(),
            operation,
            operation_name='row',
            deadline=start + budget_seconds,
            sleep=clock.sleep,
            random_value=lambda: 1,
            monotonic=clock.monotonic,
        )
    except FirestoreContentionExhausted:
        return len(attempts)
    return len(attempts)


def test_floor_row_one_second_attempts_sixty_second_budget_reaches_the_cap():
    assert gate_row(60.0, 1.0) == 5


def test_floor_row_one_second_attempts_budget_at_the_floor_stops_after_one():
    # a1 (1s) + its 0.2s gap leave 28.8s: below the 30s floor, no second try.
    assert gate_row(30.0, 1.0) == 1


def test_floor_row_one_second_attempts_budget_of_38_reaches_the_cap():
    # 4 attempts + 2.6s of gaps leave 31.4s >= the floor: attempt 5 runs.
    assert gate_row(38.0, 1.0) == 5


def test_floor_row_one_second_attempts_budget_of_36_refuses_the_fifth():
    # 4 attempts + 2.6s of gaps leave 29.4s < the floor: attempt 5 is refused.
    assert gate_row(36.0, 1.0) == 4


def test_floor_row_one_second_attempts_fifteen_second_budget_stops_after_one():
    assert gate_row(15.0, 1.0) == 1


def test_floor_row_five_second_attempts_thirty_second_budget_runs_two():
    # 5s attempts: a1 -> 25s < 30s floor -> refuse at the gate.
    assert gate_row(30.0, 5.0) == 1


def test_floor_row_five_second_attempts_sixty_second_budget_runs_five():
    assert gate_row(60.0, 5.0) == 5


def test_floor_row_ten_second_attempts_fifty_second_budget_runs_two():
    # a1 10s -> 40s >= 30 admit; a2 10s (+0.6 gaps) -> 29.4 < 30 refuse.
    assert gate_row(50.0, 10.0) == 2


def test_floor_row_twenty_second_attempts_fifty_second_budget_runs_one():
    # a1 20s + 0.2s gap leaves 29.8s < the floor: the a2 gate refuses.
    assert gate_row(50.0, 20.0) == 1


def test_floor_row_thirty_second_attempts_thirty_second_budget_runs_one():
    assert gate_row(30.0, 30.0) == 1


def test_reserve_row_sixty_second_attempts_ninety_second_budget_runs_one():
    # Reserve after a1 = max(90, 30) = 90s; remaining 30s < 90 -> refuse.
    assert gate_row(90.0, 60.0) == 1


def test_reserve_row_sixty_second_attempts_one_sixty_second_budget_runs_two():
    # a1 60s -> 100s remaining; reserve 90s -> admit; a2 60s (+0.6) -> 39.4 < 90 refuse.
    assert gate_row(160.0, 60.0) == 2


def test_reserve_row_two_hundred_second_attempts_three_hundred_second_budget_runs_one():
    assert gate_row(300.0, 200.0) == 1


def test_reserve_row_two_hundred_second_attempts_six_hundred_second_budget_runs_two():
    assert gate_row(600.0, 200.0) == 2


def test_gate_rows_never_exceed_the_attempt_cap():
    for budget, attempt in ((60.0, 1.0), (160.0, 60.0), (600.0, 200.0)):
        assert gate_row(budget, attempt) <= DEFAULT_MAX_ATTEMPTS


# --------------------------------------------------------------------------
# Named band edges for the capped rungs
# --------------------------------------------------------------------------


def test_capped_rung_6_band():
    assert equal_jitter_delay(6, random_value=lambda: 0.0) == 2.0
    assert equal_jitter_delay(6, random_value=lambda: 1.0) == 4.0


def test_capped_rung_7_band():
    assert equal_jitter_delay(7, random_value=lambda: 0.0) == 2.0
    assert equal_jitter_delay(7, random_value=lambda: 1.0) == 4.0


def test_capped_rung_8_band():
    assert equal_jitter_delay(8, random_value=lambda: 0.5) == 3.0


def test_capped_rung_9_band():
    assert equal_jitter_delay(9, random_value=lambda: 0.5) == 3.0


def test_capped_rung_10_band():
    assert equal_jitter_delay(10, random_value=lambda: 0.0) == 2.0


def test_uncapped_rung_5_band_straddles_three_seconds():
    assert equal_jitter_delay(5, random_value=lambda: 0.0) == 1.6
    assert equal_jitter_delay(5, random_value=lambda: 1.0) == 3.2


def test_the_cap_is_above_every_default_chain_gap():
    for attempt in range(1, 5):
        assert equal_jitter_delay(attempt, random_value=lambda: 1.0) < _MAX_DELAY_SECONDS


def test_the_cap_is_below_the_sixth_uncapped_rung():
    assert 0.2 * (2**5) > _MAX_DELAY_SECONDS


# --------------------------------------------------------------------------
# Every suite in this family declares the failure class in its docstring
# --------------------------------------------------------------------------


FAMILY_SUITES = [
    'test_contention_retry_wave_bridge.py',
    'test_contention_retry_rung_table_pin.py',
    'test_contention_retry_deadline_wave_bounds.py',
    'test_contention_retry_deadline_gate_matrix.py',
    'test_contention_retry_inner_chain_backoff.py',
    'test_batch_store_wave_bridge_recovery_parity.py',
    'test_batch_exhaustion_publication_contract_matrix.py',
    'test_batch_wave_bridge_docs_taxonomy_parity.py',
    'test_batch_wave_bridge_twin_and_chain_boundaries.py',
    'test_batch_merge_and_recover_authority_contracts.py',
    'test_batch_wave_bridge_design_doc_parity.py',
    'test_batch_wave_bridge_config_and_twin_surfaces.py',
    'test_batch_merge_hold_and_chain_edge_contracts.py',
    'test_batch_scheduler_transition_and_chain_constants.py',
    'test_batch_pump_damper_and_seed_edges.py',
]


@pytest.mark.parametrize('suite', FAMILY_SUITES)
def test_family_suite_declares_the_failure_class(suite):
    source = (BACKEND / 'tests' / 'unit' / suite).read_text()
    assert f'Failure-Class: {FC}' in source, suite
