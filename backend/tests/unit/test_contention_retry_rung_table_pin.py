"""The wave-bridge rung table, pinned rung by rung as a closed contract.

The contention chain's delay schedule is the change this family ships: the
high bound doubles per attempt (``0.2s, 0.4s, 0.8s, 1.6s, 3.2s, 4.0s cap``)
and every draw is uniform on ``[high / 2, high)``. This suite pins each rung
of that table explicitly — high, low and midpoint for attempts 1 through 10 —
plus the former-schedule comparisons that make the growth reviewable at a
glance, the exact inter-attempt gap sums for chains of every depth, and the
landing time of a wave-bridged fifth attempt at each jitter extreme.

Failure-Class: FC-contention-chain-spends-its-budget-inside-one-abort-wave
"""

import pytest
from google.api_core.exceptions import Aborted

from database.firestore_transaction_retry import (
    _INITIAL_MAX_DELAY_SECONDS,
    _MAX_DELAY_SECONDS,
    DEFAULT_MAX_ATTEMPTS,
    FirestoreContentionExhausted,
    equal_jitter_delay,
    run_with_transaction_contention_retry,
)


class FakeClock:
    def __init__(self, now: float = 1000.0):
        self.now = now

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def aborted():
    return Aborted('read contention')


def exhausted_chain_sleeps(clock, attempts, jitter):
    """Run an always-aborting chain of ``attempts`` attempts; return its gaps."""
    sleeps = []
    state = {'n': 0}

    def operation(transaction):
        state['n'] += 1
        raise aborted()

    with pytest.raises(FirestoreContentionExhausted):
        run_with_transaction_contention_retry(
            lambda: object(),
            operation,
            operation_name='rungs',
            max_attempts=attempts,
            sleep=lambda seconds: (sleeps.append(seconds), clock.sleep(seconds)) and None,
            random_value=lambda: jitter,
            monotonic=clock.monotonic,
        )
    return sleeps


# --------------------------------------------------------------------------
# High bounds — maximum jitter is the high edge of each rung
# --------------------------------------------------------------------------


def test_rung_1_high_at_maximum_jitter():
    assert equal_jitter_delay(1, random_value=lambda: 1.0) == 0.2


def test_rung_2_high_at_maximum_jitter():
    assert equal_jitter_delay(2, random_value=lambda: 1.0) == 0.4


def test_rung_3_high_at_maximum_jitter():
    assert equal_jitter_delay(3, random_value=lambda: 1.0) == 0.8


def test_rung_4_high_at_maximum_jitter():
    assert equal_jitter_delay(4, random_value=lambda: 1.0) == 1.6


def test_rung_5_high_at_maximum_jitter():
    assert equal_jitter_delay(5, random_value=lambda: 1.0) == 3.2


def test_rung_6_high_is_capped():
    assert equal_jitter_delay(6, random_value=lambda: 1.0) == 4.0


def test_rung_7_high_is_capped():
    assert equal_jitter_delay(7, random_value=lambda: 1.0) == 4.0


def test_rung_8_high_is_capped():
    assert equal_jitter_delay(8, random_value=lambda: 1.0) == 4.0


def test_rung_10_high_is_capped():
    assert equal_jitter_delay(10, random_value=lambda: 1.0) == 4.0


# --------------------------------------------------------------------------
# Low bounds — zero jitter is the low edge of each rung
# --------------------------------------------------------------------------


def test_rung_1_low_at_zero_jitter():
    assert equal_jitter_delay(1, random_value=lambda: 0.0) == 0.1


def test_rung_2_low_at_zero_jitter():
    assert equal_jitter_delay(2, random_value=lambda: 0.0) == 0.2


def test_rung_3_low_at_zero_jitter():
    assert equal_jitter_delay(3, random_value=lambda: 0.0) == 0.4


def test_rung_4_low_at_zero_jitter():
    assert equal_jitter_delay(4, random_value=lambda: 0.0) == 0.8


def test_rung_5_low_at_zero_jitter():
    assert equal_jitter_delay(5, random_value=lambda: 0.0) == 1.6


def test_rung_6_low_is_half_the_cap():
    assert equal_jitter_delay(6, random_value=lambda: 0.0) == 2.0


def test_rung_8_low_is_half_the_cap():
    assert equal_jitter_delay(8, random_value=lambda: 0.0) == 2.0


def test_rung_10_low_is_half_the_cap():
    assert equal_jitter_delay(10, random_value=lambda: 0.0) == 2.0


# --------------------------------------------------------------------------
# Midpoints — the center of each jitter band
# --------------------------------------------------------------------------


def test_rung_1_midpoint():
    assert equal_jitter_delay(1, random_value=lambda: 0.5) == pytest.approx(0.15)


def test_rung_2_midpoint():
    assert equal_jitter_delay(2, random_value=lambda: 0.5) == pytest.approx(0.3)


def test_rung_3_midpoint():
    assert equal_jitter_delay(3, random_value=lambda: 0.5) == pytest.approx(0.6)


def test_rung_4_midpoint():
    assert equal_jitter_delay(4, random_value=lambda: 0.5) == pytest.approx(1.2)


def test_rung_5_midpoint():
    assert equal_jitter_delay(5, random_value=lambda: 0.5) == pytest.approx(2.4)


def test_rung_6_midpoint_is_three_seconds():
    assert equal_jitter_delay(6, random_value=lambda: 0.5) == pytest.approx(3.0)


def test_rung_10_midpoint_is_three_seconds():
    assert equal_jitter_delay(10, random_value=lambda: 0.5) == pytest.approx(3.0)


# --------------------------------------------------------------------------
# Former schedule comparisons — where the growth is, rung by rung
# --------------------------------------------------------------------------


def test_rung_1_matches_the_former_schedule():
    assert equal_jitter_delay(1, random_value=lambda: 1.0) == min(0.2, 1.0)


def test_rung_2_matches_the_former_schedule():
    assert equal_jitter_delay(2, random_value=lambda: 1.0) == min(0.4, 1.0)


def test_rung_3_matches_the_former_schedule():
    assert equal_jitter_delay(3, random_value=lambda: 1.0) == min(0.8, 1.0)


def test_rung_4_grows_past_the_former_cap():
    assert equal_jitter_delay(4, random_value=lambda: 1.0) == 1.6 > min(1.6, 1.0)


def test_rung_5_grows_past_the_former_cap():
    assert equal_jitter_delay(5, random_value=lambda: 1.0) == 3.2 > min(3.2, 1.0)


def test_rung_6_grows_past_the_former_cap():
    assert equal_jitter_delay(6, random_value=lambda: 1.0) == 4.0 > min(6.4, 1.0)


def test_rung_7_grows_past_the_former_cap():
    assert equal_jitter_delay(7, random_value=lambda: 1.0) == 4.0 > 1.0


def test_rung_10_grows_past_the_former_cap():
    assert equal_jitter_delay(10, random_value=lambda: 1.0) == 4.0 > 1.0


# --------------------------------------------------------------------------
# Cap and initial-rung constants
# --------------------------------------------------------------------------


def test_the_cap_is_four_seconds():
    assert _MAX_DELAY_SECONDS == 4.0


def test_the_initial_rung_is_unchanged():
    assert _INITIAL_MAX_DELAY_SECONDS == 0.2


def test_the_default_attempt_budget_is_unchanged():
    assert DEFAULT_MAX_ATTEMPTS == 5


def test_the_cap_binds_from_attempt_six():
    assert 0.2 * (2**5) > _MAX_DELAY_SECONDS  # the uncapped sixth rung
    assert 0.2 * (2**4) < _MAX_DELAY_SECONDS  # the fifth rung still uncapped


def test_every_rung_through_twenty_stays_at_the_cap_high():
    for attempt in range(6, 21):
        assert equal_jitter_delay(attempt, random_value=lambda: 1.0) == _MAX_DELAY_SECONDS


def test_every_rung_through_twenty_stays_at_the_cap_low():
    for attempt in range(6, 21):
        assert equal_jitter_delay(attempt, random_value=lambda: 0.0) == _MAX_DELAY_SECONDS / 2


# --------------------------------------------------------------------------
# Gap sums — the exact window a chain of each depth spans at the extremes
# --------------------------------------------------------------------------


def test_one_attempt_chain_sleeps_nothing():
    assert exhausted_chain_sleeps(FakeClock(), 1, 1.0) == []


def test_two_attempt_chain_gap_at_maximum_jitter():
    assert exhausted_chain_sleeps(FakeClock(), 2, 1.0) == [0.2]


def test_two_attempt_chain_gap_at_minimum_jitter():
    assert exhausted_chain_sleeps(FakeClock(), 2, 0.0) == [0.1]


def test_three_attempt_chain_gaps_at_maximum_jitter():
    assert exhausted_chain_sleeps(FakeClock(), 3, 1.0) == [0.2, 0.4]


def test_three_attempt_chain_gaps_at_minimum_jitter():
    assert exhausted_chain_sleeps(FakeClock(), 3, 0.0) == [0.1, 0.2]


def test_four_attempt_chain_gaps_at_maximum_jitter():
    assert exhausted_chain_sleeps(FakeClock(), 4, 1.0) == [0.2, 0.4, 0.8]


def test_four_attempt_chain_gaps_at_minimum_jitter():
    assert exhausted_chain_sleeps(FakeClock(), 4, 0.0) == [0.1, 0.2, 0.4]


def test_five_attempt_chain_gaps_at_maximum_jitter():
    assert exhausted_chain_sleeps(FakeClock(), 5, 1.0) == [0.2, 0.4, 0.8, 1.6]


def test_five_attempt_chain_gaps_at_minimum_jitter():
    assert exhausted_chain_sleeps(FakeClock(), 5, 0.0) == [0.1, 0.2, 0.4, 0.8]


def test_five_attempt_chain_window_grew_from_the_former_two_point_four():
    clock = FakeClock()
    assert sum(exhausted_chain_sleeps(clock, 5, 1.0)) == 3.0


def test_five_attempt_chain_window_grew_from_the_former_one_point_two():
    clock = FakeClock()
    assert sum(exhausted_chain_sleeps(clock, 5, 0.0)) == 1.5


def test_six_attempt_opt_in_chain_carries_the_grown_fifth_rung():
    clock = FakeClock()
    assert exhausted_chain_sleeps(clock, 6, 1.0) == [0.2, 0.4, 0.8, 1.6, 3.2]


def test_six_attempt_opt_in_chain_window_is_six_point_two_seconds():
    clock = FakeClock()
    assert sum(exhausted_chain_sleeps(clock, 6, 1.0)) == pytest.approx(6.2)


def test_seven_attempt_opt_in_chain_hits_the_capped_rung():
    clock = FakeClock()
    assert exhausted_chain_sleeps(clock, 7, 1.0) == [0.2, 0.4, 0.8, 1.6, 3.2, 4.0]


def test_eight_attempt_opt_in_chain_window_is_fourteen_point_two_seconds():
    clock = FakeClock()
    assert sum(exhausted_chain_sleeps(clock, 8, 1.0)) == pytest.approx(14.2)


# --------------------------------------------------------------------------
# Wave-bridge landing time — when attempt 5 starts, per jitter extreme
# --------------------------------------------------------------------------


def bridged_fifth_attempt_time(jitter, wave_ends=3.0):
    clock = FakeClock()
    seen = []

    def operation(transaction):
        seen.append(clock.now - 1000.0)
        if clock.now < 1000.0 + wave_ends:
            raise aborted()
        return 'committed'

    run_with_transaction_contention_retry(
        lambda: object(),
        operation,
        operation_name='landing',
        sleep=clock.sleep,
        random_value=lambda: jitter,
        monotonic=clock.monotonic,
    )
    return seen


def test_wave_bridged_fifth_attempt_lands_at_three_seconds_maximum_jitter():
    assert bridged_fifth_attempt_time(1.0)[-1] == pytest.approx(3.0)


def test_wave_bridged_fifth_attempt_lands_at_one_point_five_seconds_minimum_jitter():
    seen = bridged_fifth_attempt_time(0.0, wave_ends=1.5)
    assert seen[-1] == pytest.approx(1.5)
    assert len(seen) == 5


def test_wave_bridged_fifth_attempt_lands_between_the_extremes_midpoint_jitter():
    seen = bridged_fifth_attempt_time(0.5, wave_ends=2.25)
    assert seen[-1] == pytest.approx(2.25)
    assert len(seen) == 5


def test_former_schedule_landed_attempt_five_at_two_point_four_maximum_jitter():
    # The four gaps under the 1.0s cap: 0.2 + 0.4 + 0.8 + 1.0.
    former = 0.2 + 0.4 + 0.8 + min(0.2 * (2**3), 1.0)
    assert former == pytest.approx(2.4)
    assert former < bridged_fifth_attempt_time(1.0)[-1]


def test_the_bridge_window_covers_waves_ending_between_the_schedules():
    # A wave that ends at t=2.7s: the former schedule's attempt 5 (2.4s)
    # landed inside it; the bridged schedule's attempt 5 (3.0s) lands after.
    clock = FakeClock()
    seen = []

    def operation(transaction):
        seen.append(clock.now - 1000.0)
        if clock.now < 1000.0 + 2.7:
            raise aborted()
        return 'committed'

    run_with_transaction_contention_retry(
        lambda: object(),
        operation,
        operation_name='narrow_wave',
        sleep=clock.sleep,
        random_value=lambda: 1.0,
        monotonic=clock.monotonic,
    )
    assert len(seen) == 5
    assert seen[-1] == pytest.approx(3.0)
