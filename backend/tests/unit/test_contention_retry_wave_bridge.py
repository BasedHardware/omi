"""The contention chain's delay schedule bridges a multi-second abort wave.

The bounded chain gives one Firestore transaction five attempts. Its early
retry rungs stay sub-second so a transient single-abort collision recovers
immediately; the tail rungs grow so the chain's cumulative backoff spans the
multi-second window a real contention storm stays hot. Before the wave-bridge
cap the whole budget landed inside one storm window: every attempt aborted,
the chain exhausted at ``attempt=5/5 outcome=exhausted``, and only the NEXT
store entry (the storm damper's spaced re-strike) ever found the document
quiet. These tests pin the ladder shape, the bridged budget window, and the
recovery an in-wave storm now gets against the same stub that exhausts the
old schedule.

Failure-Class: FC-contention-chain-spends-its-budget-inside-one-abort-wave
"""

import logging

import pytest
from google.api_core.exceptions import Aborted, InvalidArgument

import database.firestore_transaction_retry as retry_module
from database.batch_pipeline_store import FirestoreStore
from database.firestore_transaction_retry import (
    _INITIAL_MAX_DELAY_SECONDS,
    _MAX_DELAY_SECONDS,
    DEFAULT_MAX_ATTEMPTS,
    FirestoreContentionExhausted,
    equal_jitter_delay,
    run_with_transaction_contention_retry,
)

EXPIRED = 'The referenced transaction has expired or is no longer valid.'


class FakeClock:
    """Monotonic clock the operation and the retry loop share; sleeps advance it."""

    def __init__(self, now: float = 1000.0):
        self.now = now

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def aborted() -> Aborted:
    return Aborted('read contention')


def expired() -> InvalidArgument:
    return InvalidArgument(EXPIRED)


# The documented ladder: the high bound doubles per attempt until the cap.
EXPECTED_HIGH_BOUNDS = {
    1: 0.2,
    2: 0.4,
    3: 0.8,
    4: 1.6,
    5: 3.2,
    6: 4.0,
    7: 4.0,
    12: 4.0,
}


@pytest.mark.parametrize('attempt', sorted(EXPECTED_HIGH_BOUNDS))
def test_high_bound_doubles_per_attempt_until_the_cap(attempt):
    assert equal_jitter_delay(attempt, random_value=lambda: 1.0) == EXPECTED_HIGH_BOUNDS[attempt]


@pytest.mark.parametrize('attempt', sorted(EXPECTED_HIGH_BOUNDS))
def test_delay_stays_within_the_equal_jitter_band(attempt):
    low, high = EXPECTED_HIGH_BOUNDS[attempt] / 2, EXPECTED_HIGH_BOUNDS[attempt]
    assert low <= equal_jitter_delay(attempt, random_value=lambda: 0.0) < high + 1e-12


@pytest.mark.parametrize('fraction,share', [(0.0, 0.5), (0.25, 0.625), (0.5, 0.75), (0.75, 0.875), (1.0, 1.0)])
def test_equal_jitter_draws_uniformly_between_half_and_the_full_high(fraction, share):
    attempt = 5
    assert equal_jitter_delay(attempt, random_value=lambda: fraction) == pytest.approx(
        EXPECTED_HIGH_BOUNDS[attempt] * share
    )


@pytest.mark.parametrize('attempt', [1, 2, 3])
def test_early_rungs_stay_sub_second(attempt):
    # The transient single-abort collision path is unchanged: a short chain
    # still recovers immediately instead of waiting out the new tail rungs.
    assert equal_jitter_delay(attempt, random_value=lambda: 1.0) < 1.0


def test_attempt_four_exceeds_the_former_one_second_cap():
    assert equal_jitter_delay(4, random_value=lambda: 1.0) > 1.0


def test_attempt_five_bridges_a_three_second_wave():
    assert equal_jitter_delay(5, random_value=lambda: 1.0) >= 3.0


def test_cap_matches_the_storm_damper_ceiling():
    assert _MAX_DELAY_SECONDS == FirestoreStore.STORM_DAMPER_CAP_SECONDS


def test_initial_rung_is_unchanged():
    assert _INITIAL_MAX_DELAY_SECONDS == 0.2


def test_default_attempt_budget_is_unchanged():
    assert DEFAULT_MAX_ATTEMPTS == 5


@pytest.mark.parametrize('attempt', [0, -1, -7])
def test_non_positive_attempt_is_refused(attempt):
    with pytest.raises(ValueError):
        equal_jitter_delay(attempt)


def test_zero_jitter_gives_the_low_edge():
    assert equal_jitter_delay(1, random_value=lambda: 0.0) == 0.1


def test_full_jitter_gives_the_high_edge():
    assert equal_jitter_delay(1, random_value=lambda: 1.0) == 0.2


def test_jitter_values_outside_the_unit_interval_are_clamped():
    assert equal_jitter_delay(1, random_value=lambda: 42.0) == 0.2
    assert equal_jitter_delay(1, random_value=lambda: -3.0) == 0.1


def test_ladder_is_monotone_non_decreasing_across_the_first_six_attempts():
    highs = [equal_jitter_delay(attempt, random_value=lambda: 1.0) for attempt in range(1, 7)]
    assert highs == sorted(highs)


def test_capped_attempts_hold_the_cap_exactly():
    for attempt in (6, 7, 8, 9, 10, 25):
        assert equal_jitter_delay(attempt, random_value=lambda: 1.0) == _MAX_DELAY_SECONDS


def test_five_attempt_budget_spans_the_wave_bridge_window_at_maximum_jitter():
    clock = FakeClock()
    sleeps = []
    attempt_state = {'n': 0}

    def operation(transaction):
        attempt_state['n'] += 1
        if attempt_state['n'] < DEFAULT_MAX_ATTEMPTS:
            raise aborted()

    def record_sleep(seconds):
        sleeps.append(seconds)
        clock.sleep(seconds)

    run_with_transaction_contention_retry(
        lambda: object(),
        operation,
        operation_name='bridged',
        sleep=record_sleep,
        random_value=lambda: 1.0,
        monotonic=clock.monotonic,
    )
    assert sleeps == [0.2, 0.4, 0.8, 1.6]
    assert clock.now - 1000.0 == pytest.approx(3.0)


def test_five_attempt_budget_spans_the_wave_bridge_window_at_minimum_jitter():
    clock = FakeClock()
    sleeps = []
    attempt_state = {'n': 0}

    def operation(transaction):
        attempt_state['n'] += 1
        if attempt_state['n'] < DEFAULT_MAX_ATTEMPTS:
            raise aborted()

    def record_sleep(seconds):
        sleeps.append(seconds)
        clock.sleep(seconds)

    run_with_transaction_contention_retry(
        lambda: object(),
        operation,
        operation_name='bridged_low',
        sleep=record_sleep,
        random_value=lambda: 0.0,
        monotonic=clock.monotonic,
    )
    assert sleeps == [0.1, 0.2, 0.4, 0.8]
    assert clock.now - 1000.0 == pytest.approx(1.5)


def test_wave_that_ends_at_three_seconds_is_bridged_instead_of_exhausted():
    """The core wave-bridge scenario.

    The hot document's writers keep committing until t+3.0s and go quiet
    after. Every attempt before the wave ends aborts; an attempt at or after
    it succeeds. The stub is identical for both schedules — only the chain's
    own tail rungs decide whether attempt 5 lands inside or after the wave.
    """
    clock = FakeClock()
    WAVE_ENDS = 1000.0 + 3.0
    seen = []

    def operation(transaction):
        seen.append(clock.monotonic() - 1000.0)
        if clock.monotonic() < WAVE_ENDS:
            raise aborted()
        return 'committed'

    result = run_with_transaction_contention_retry(
        lambda: object(),
        operation,
        operation_name='wave',
        sleep=clock.sleep,
        random_value=lambda: 1.0,  # maximum jitter: the widest bridge
        monotonic=clock.monotonic,
    )
    assert result == 'committed'
    assert len(seen) == DEFAULT_MAX_ATTEMPTS
    assert seen[-1] == pytest.approx(3.0)  # attempt 5 lands exactly at the wave end


def test_wave_longer_than_the_budget_still_exhausts_with_the_closed_reason():
    """The bridge is bounded: a wave outlasting the schedule still exhausts."""
    clock = FakeClock()
    WAVE_ENDS = 1000.0 + 30.0

    def operation(transaction):
        if clock.monotonic() < WAVE_ENDS:
            raise aborted()
        return 'committed'

    with pytest.raises(FirestoreContentionExhausted) as raised:
        run_with_transaction_contention_retry(
            lambda: object(),
            operation,
            operation_name='long_wave',
            sleep=clock.sleep,
            random_value=lambda: 1.0,
            monotonic=clock.monotonic,
        )
    assert raised.value.reason == 'attempts_exhausted'


def test_exhaustion_message_names_the_operation():
    clock = FakeClock()

    def operation(transaction):
        raise aborted()

    with pytest.raises(FirestoreContentionExhausted) as raised:
        run_with_transaction_contention_retry(
            lambda: object(),
            operation,
            operation_name='named_operation',
            sleep=clock.sleep,
            random_value=lambda: 1.0,
            monotonic=clock.monotonic,
        )
    assert 'named_operation' in str(raised.value)


def test_exhaustion_chains_from_the_last_contention_error():
    clock = FakeClock()

    def operation(transaction):
        raise aborted()

    with pytest.raises(FirestoreContentionExhausted) as raised:
        run_with_transaction_contention_retry(
            lambda: object(),
            operation,
            operation_name='chained',
            sleep=clock.sleep,
            random_value=lambda: 1.0,
            monotonic=clock.monotonic,
        )
    assert isinstance(raised.value.__cause__, Aborted)


def test_recovery_after_in_wave_retries_logs_outcome_recovered(caplog):
    clock = FakeClock()
    WAVE_ENDS = 1000.0 + 3.0

    def operation(transaction):
        if clock.monotonic() < WAVE_ENDS:
            raise aborted()
        return 'committed'

    with caplog.at_level(logging.INFO, logger='database.firestore_transaction_retry'):
        run_with_transaction_contention_retry(
            lambda: object(),
            operation,
            operation_name='recovered_wave',
            sleep=clock.sleep,
            random_value=lambda: 1.0,
            monotonic=clock.monotonic,
        )
    recovered = [line for line in caplog.messages if 'outcome=recovered' in line]
    assert len(recovered) == 1
    assert 'attempt=5/5' in recovered[0]
    assert 'operation=recovered_wave' in recovered[0]


def test_exhaustion_logs_the_attempt_cap_exactly_once(caplog):
    clock = FakeClock()

    def operation(transaction):
        raise aborted()

    with caplog.at_level(logging.ERROR, logger='database.firestore_transaction_retry'):
        with pytest.raises(FirestoreContentionExhausted):
            run_with_transaction_contention_retry(
                lambda: object(),
                operation,
                operation_name='exhaust_once',
                sleep=clock.sleep,
                random_value=lambda: 1.0,
                monotonic=clock.monotonic,
            )
    exhausted = [line for line in caplog.messages if 'outcome=exhausted' in line]
    assert exhausted == ['firestore_transaction_contention operation=exhaust_once attempt=5/5 outcome=exhausted']


def test_every_retry_gap_is_logged_with_its_delay(caplog):
    clock = FakeClock()
    attempt_state = {'n': 0}

    def operation(transaction):
        attempt_state['n'] += 1
        if attempt_state['n'] < 3:
            raise aborted()

    with caplog.at_level(logging.WARNING, logger='database.firestore_transaction_retry'):
        run_with_transaction_contention_retry(
            lambda: object(),
            operation,
            operation_name='gap_log',
            sleep=clock.sleep,
            random_value=lambda: 1.0,
            monotonic=clock.monotonic,
        )
    retry_lines = [line for line in caplog.messages if 'outcome=retry' in line]
    assert len(retry_lines) == 2
    assert 'attempt=1/5' in retry_lines[0] and 'delay_ms=200' in retry_lines[0]
    assert 'attempt=2/5' in retry_lines[1] and 'delay_ms=400' in retry_lines[1]


@pytest.mark.parametrize('max_attempts', [1, 2, 3, 4])
def test_shorter_budgets_keep_their_attempt_count_but_inherit_the_ladder(max_attempts):
    clock = FakeClock()
    attempts = []

    def operation(transaction):
        attempts.append(clock.monotonic())
        raise aborted()

    with pytest.raises(FirestoreContentionExhausted):
        run_with_transaction_contention_retry(
            lambda: object(),
            operation,
            operation_name='short',
            max_attempts=max_attempts,
            sleep=clock.sleep,
            random_value=lambda: 1.0,
            monotonic=clock.monotonic,
        )
    assert len(attempts) == max_attempts


@pytest.mark.parametrize('max_attempts', [0, -2])
def test_non_positive_attempt_budget_is_refused(max_attempts):
    with pytest.raises(ValueError):
        run_with_transaction_contention_retry(
            lambda: object(), lambda tx: None, operation_name='x', max_attempts=max_attempts
        )


def test_non_contention_errors_are_never_replayed():
    clock = FakeClock()
    attempts = []

    def operation(transaction):
        attempts.append(1)
        raise KeyError('unrelated')

    with pytest.raises(KeyError):
        run_with_transaction_contention_retry(
            lambda: object(), operation, operation_name='unrelated', sleep=clock.sleep, monotonic=clock.monotonic
        )
    assert len(attempts) == 1
    assert clock.now == 1000.0


def test_contention_hidden_behind_a_cause_chain_is_still_replayed():
    clock = FakeClock()
    attempt_state = {'n': 0}

    def operation(transaction):
        attempt_state['n'] += 1
        if attempt_state['n'] < 2:
            try:
                raise aborted()
            except Aborted as error:
                raise RuntimeError('adapter wrapper') from error
        return 'ok'

    assert (
        run_with_transaction_contention_retry(
            lambda: object(), operation, operation_name='wrapped', sleep=clock.sleep, monotonic=clock.monotonic
        )
        == 'ok'
    )
    assert attempt_state['n'] == 2


def test_expired_transactions_keep_the_three_chain_ceiling_without_a_deadline():
    clock = FakeClock()
    attempts = []

    def operation(transaction):
        attempts.append(1)
        raise expired()

    with pytest.raises(FirestoreContentionExhausted) as raised:
        run_with_transaction_contention_retry(
            lambda: object(), operation, operation_name='expiring', sleep=clock.sleep, monotonic=clock.monotonic
        )
    assert len(attempts) == 3
    assert raised.value.reason == 'attempts_exhausted'


def test_aborted_contention_keeps_the_full_attempt_cap_without_a_deadline():
    clock = FakeClock()
    attempts = []

    def operation(transaction):
        attempts.append(1)
        raise aborted()

    with pytest.raises(FirestoreContentionExhausted):
        run_with_transaction_contention_retry(
            lambda: object(), operation, operation_name='aborting', sleep=clock.sleep, monotonic=clock.monotonic
        )
    assert len(attempts) == 5


def test_expired_interleaving_keeps_the_full_aborted_budget():
    clock = FakeClock()
    attempts = []

    def operation(transaction):
        attempts.append(1)
        raise expired() if len(attempts) % 2 == 0 else aborted()

    with pytest.raises(FirestoreContentionExhausted) as raised:
        run_with_transaction_contention_retry(
            lambda: object(), operation, operation_name='mixed', sleep=clock.sleep, monotonic=clock.monotonic
        )
    # Expired chains interleaved with Aborted contention never shorten the
    # aborted budget: the chain runs to the full attempt cap.
    assert len(attempts) == 5
    assert raised.value.reason == 'attempts_exhausted'


def test_expired_chains_alone_stop_at_the_three_chain_ceiling():
    clock = FakeClock()
    attempts = []

    def operation(transaction):
        attempts.append(1)
        if len(attempts) < 3:
            raise expired()
        return 'settled'

    assert (
        run_with_transaction_contention_retry(
            lambda: object(), operation, operation_name='expire_then_ok', sleep=clock.sleep, monotonic=clock.monotonic
        )
        == 'settled'
    )
    assert len(attempts) == 3


def test_mid_chain_success_stops_the_budget_cleanly():
    clock = FakeClock()
    attempt_state = {'n': 0}

    def operation(transaction):
        attempt_state['n'] += 1
        return 'done' if attempt_state['n'] >= 4 else (_ for _ in ()).throw(aborted())

    assert (
        run_with_transaction_contention_retry(
            lambda: object(),
            operation,
            operation_name='mid',
            sleep=clock.sleep,
            random_value=lambda: 1.0,
            monotonic=clock.monotonic,
        )
        == 'done'
    )
    assert attempt_state['n'] == 4


def test_sleep_receives_the_equal_jitter_draw_not_the_high_bound():
    clock = FakeClock()
    sleeps = []
    attempt_state = {'n': 0}

    def operation(transaction):
        attempt_state['n'] += 1
        if attempt_state['n'] < 2:
            raise aborted()

    run_with_transaction_contention_retry(
        lambda: object(),
        operation,
        operation_name='draw',
        sleep=lambda seconds: sleeps.append(seconds),
        random_value=lambda: 0.5,  # mid-band draw
        monotonic=clock.monotonic,
    )
    assert sleeps == [pytest.approx(0.15)]  # 0.75 x the 0.2s attempt-1 high


def test_transaction_factory_is_fresh_per_attempt():
    clock = FakeClock()
    kept = []
    attempt_state = {'n': 0}

    def factory():
        transaction = ('txn', len(kept))
        kept.append(transaction)  # keep the object alive: ids must not collide by reuse
        return transaction

    def operation(transaction):
        attempt_state['n'] += 1
        if attempt_state['n'] < 3:
            raise aborted()

    run_with_transaction_contention_retry(
        factory,
        operation,
        operation_name='fresh',
        sleep=clock.sleep,
        monotonic=clock.monotonic,
    )
    assert len({id(transaction) for transaction in kept}) == 3


def test_module_exports_the_documented_cap():
    assert retry_module._MAX_DELAY_SECONDS == 4.0


# --------------------------------------------------------------------------
# Exhaustive rung table: the wave-bridge schedule is a closed contract
# --------------------------------------------------------------------------


@pytest.mark.parametrize('attempt', range(1, 17))
def test_rung_high_bounds_follow_the_doubling_ladder(attempt):
    expected = min(0.2 * (2 ** (attempt - 1)), 4.0)
    assert equal_jitter_delay(attempt, random_value=lambda: 1.0) == pytest.approx(expected)


@pytest.mark.parametrize('attempt', range(1, 17))
def test_rung_low_bounds_are_half_the_high_bound(attempt):
    expected_low = min(0.2 * (2 ** (attempt - 1)), 4.0) / 2
    assert equal_jitter_delay(attempt, random_value=lambda: 0.0) == pytest.approx(expected_low)


@pytest.mark.parametrize('attempt,jitter', [(a, j) for a in range(1, 9) for j in (0.0, 0.25, 0.5, 0.75, 1.0)])
def test_rung_jitter_interpolation_is_linear(attempt, jitter):
    high = min(0.2 * (2 ** (attempt - 1)), 4.0)
    expected = high / 2 + (high / 2) * jitter
    assert equal_jitter_delay(attempt, random_value=lambda: jitter) == pytest.approx(expected)


@pytest.mark.parametrize('attempt', [4, 5, 6])
def test_tail_rungs_grew_from_the_former_schedule(attempt):
    former_high = min(0.2 * (2 ** (attempt - 1)), 1.0)
    assert equal_jitter_delay(attempt, random_value=lambda: 1.0) > former_high


@pytest.mark.parametrize('attempt', [1, 2])
def test_early_rungs_equal_the_former_schedule(attempt):
    assert equal_jitter_delay(attempt, random_value=lambda: 1.0) == 0.2 * (2 ** (attempt - 1))


@pytest.mark.parametrize('jitter', [0.0, 0.25, 0.5, 0.75, 1.0])
def test_five_attempt_chain_window_at_jitter(jitter):
    clock = FakeClock()
    sleeps = []
    attempt_state = {'n': 0}

    def operation(transaction):
        attempt_state['n'] += 1
        if attempt_state['n'] < DEFAULT_MAX_ATTEMPTS:
            raise aborted()

    run_with_transaction_contention_retry(
        lambda: object(),
        operation,
        operation_name='window',
        sleep=lambda seconds: (sleeps.append(seconds), clock.sleep(seconds)) and None,
        random_value=lambda: jitter,
        monotonic=clock.monotonic,
    )
    highs = [min(0.2 * (2 ** (k - 1)), 4.0) for k in range(1, 5)]
    expected = sum(h / 2 + (h / 2) * jitter for h in highs)
    assert sum(sleeps) == pytest.approx(expected)
    assert clock.now - 1000.0 == pytest.approx(expected)


@pytest.mark.parametrize('attempts', [1, 2, 3, 4, 5])
def test_budget_window_is_the_sum_of_inter_attempt_gaps(attempts):
    clock = FakeClock()
    sleeps = []
    attempt_state = {'n': 0}

    def operation(transaction):
        attempt_state['n'] += 1
        raise aborted()

    def record_sleep(seconds):
        sleeps.append(seconds)
        clock.sleep(seconds)

    with pytest.raises(FirestoreContentionExhausted):
        run_with_transaction_contention_retry(
            lambda: object(),
            operation,
            operation_name='sum',
            max_attempts=attempts,
            sleep=record_sleep,
            random_value=lambda: 1.0,
            monotonic=clock.monotonic,
        )
    assert len(sleeps) == attempts - 1


def test_full_budget_window_grows_to_three_seconds_at_maximum_jitter():
    # Former schedule: gaps 0.2+0.4+0.8+1.0 = 2.4s at maximum jitter. The
    # wave-bridge schedule: 0.2+0.4+0.8+1.6 = 3.0s across the four gaps.
    clock = FakeClock()
    attempt_state = {'n': 0}

    def operation(transaction):
        attempt_state['n'] += 1
        raise aborted()

    with pytest.raises(FirestoreContentionExhausted):
        run_with_transaction_contention_retry(
            lambda: object(),
            operation,
            operation_name='ceil',
            sleep=clock.sleep,
            random_value=lambda: 1.0,
            monotonic=clock.monotonic,
        )
    assert clock.now - 1000.0 == pytest.approx(3.0)


def test_budget_window_at_minimum_jitter_is_one_point_five_seconds():
    clock = FakeClock()
    attempt_state = {'n': 0}

    def operation(transaction):
        attempt_state['n'] += 1
        raise aborted()

    with pytest.raises(FirestoreContentionExhausted):
        run_with_transaction_contention_retry(
            lambda: object(),
            operation,
            operation_name='floor',
            sleep=clock.sleep,
            random_value=lambda: 0.0,
            monotonic=clock.monotonic,
        )
    assert clock.now - 1000.0 == pytest.approx(1.5)


@pytest.mark.parametrize('jitter', [0.0, 0.5, 1.0])
def test_wave_bridged_recovery_keeps_the_chain_window_bounded(jitter):
    # A successful wave bridge (four aborts, fifth attempt commits) keeps the
    # whole chain inside a bounded sleep window at every jitter point.
    clock = FakeClock()
    attempt_state = {'n': 0}

    def operation(transaction):
        attempt_state['n'] += 1
        if attempt_state['n'] < 5:
            raise aborted()
        return 'committed'

    run_with_transaction_contention_retry(
        lambda: object(),
        operation,
        operation_name='room',
        sleep=clock.sleep,
        random_value=lambda: jitter,
        monotonic=clock.monotonic,
    )
    assert attempt_state['n'] == 5
    assert clock.now - 1000.0 < 7.0
