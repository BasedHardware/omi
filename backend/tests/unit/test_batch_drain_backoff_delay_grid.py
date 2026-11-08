"""Exact backoff-schedule grid for the deferred publication-drain lane.
Every armed attempt waits one documented backoff step: 0.5s at attempt 1, doubling to the 8s cap. This grid pins the schedule attempt by attempt as literals, so any retune of the wave shape is a reviewed diff against this file and the parity doc.

Failure-Class: FC-publication-drain-contention-exhaustion-left-without-a-convergence-owner
"""

import pytest

import utils.batch_pipeline.pump as pump_module

try:
    # Parent revisions without the lane collect fine and fail at runtime —
    # that runtime failure is this grid's RED half.
    from utils.batch_pipeline.pump import (
        DRAIN_BACKLOG_CONTINUATION_ATTEMPTS,
        DRAIN_RETRY_BASE_SECONDS,
        DRAIN_RETRY_LEDGER_CAP,
        DRAIN_RETRY_MAX_ATTEMPTS,
        DRAIN_RETRY_MAX_SECONDS,
        deferred_drain_delay,
    )
except ImportError:
    pass


def test_delay_attempt_01_is_the_documented_step():
    assert deferred_drain_delay(1) == 0.5


def test_delay_attempt_02_is_the_documented_step():
    assert deferred_drain_delay(2) == 1.0


def test_delay_attempt_03_is_the_documented_step():
    assert deferred_drain_delay(3) == 2.0


def test_delay_attempt_04_is_the_documented_step():
    assert deferred_drain_delay(4) == 4.0


def test_delay_attempt_05_is_the_documented_step():
    assert deferred_drain_delay(5) == 8.0


def test_delay_attempt_06_is_the_documented_step():
    assert deferred_drain_delay(6) == 8.0


def test_delay_attempt_07_is_the_documented_step():
    assert deferred_drain_delay(7) == 8.0


def test_delay_attempt_08_is_the_documented_step():
    assert deferred_drain_delay(8) == 8.0


def test_delay_attempt_09_is_the_documented_step():
    assert deferred_drain_delay(9) == 8.0


def test_delay_attempt_10_is_the_documented_step():
    assert deferred_drain_delay(10) == 8.0


def test_delay_attempt_11_is_the_documented_step():
    assert deferred_drain_delay(11) == 8.0


def test_delay_attempt_12_is_the_documented_step():
    assert deferred_drain_delay(12) == 8.0


def test_delay_attempt_13_is_the_documented_step():
    assert deferred_drain_delay(13) == 8.0


def test_delay_attempt_14_is_the_documented_step():
    assert deferred_drain_delay(14) == 8.0


def test_delay_attempt_15_is_the_documented_step():
    assert deferred_drain_delay(15) == 8.0


def test_delay_attempt_16_is_the_documented_step():
    assert deferred_drain_delay(16) == 8.0


def test_delay_attempt_17_is_the_documented_step():
    assert deferred_drain_delay(17) == 8.0


def test_delay_attempt_18_is_the_documented_step():
    assert deferred_drain_delay(18) == 8.0


def test_delay_attempt_19_is_the_documented_step():
    assert deferred_drain_delay(19) == 8.0


def test_delay_attempt_20_is_the_documented_step():
    assert deferred_drain_delay(20) == 8.0


def test_delay_attempt_21_is_the_documented_step():
    assert deferred_drain_delay(21) == 8.0


def test_delay_attempt_22_is_the_documented_step():
    assert deferred_drain_delay(22) == 8.0


def test_delay_attempt_23_is_the_documented_step():
    assert deferred_drain_delay(23) == 8.0


def test_delay_attempt_24_is_the_documented_step():
    assert deferred_drain_delay(24) == 8.0


def test_delay_attempt_25_is_the_documented_step():
    assert deferred_drain_delay(25) == 8.0


def test_delay_attempt_26_is_the_documented_step():
    assert deferred_drain_delay(26) == 8.0


def test_delay_attempt_27_is_the_documented_step():
    assert deferred_drain_delay(27) == 8.0


def test_delay_attempt_28_is_the_documented_step():
    assert deferred_drain_delay(28) == 8.0


def test_delay_attempt_29_is_the_documented_step():
    assert deferred_drain_delay(29) == 8.0


def test_delay_attempt_30_is_the_documented_step():
    assert deferred_drain_delay(30) == 8.0


def test_delay_attempt_31_is_the_documented_step():
    assert deferred_drain_delay(31) == 8.0


def test_delay_attempt_32_is_the_documented_step():
    assert deferred_drain_delay(32) == 8.0


def test_delay_attempt_33_is_the_documented_step():
    assert deferred_drain_delay(33) == 8.0


def test_delay_attempt_34_is_the_documented_step():
    assert deferred_drain_delay(34) == 8.0


def test_delay_attempt_35_is_the_documented_step():
    assert deferred_drain_delay(35) == 8.0


def test_delay_attempt_36_is_the_documented_step():
    assert deferred_drain_delay(36) == 8.0


def test_delay_attempt_37_is_the_documented_step():
    assert deferred_drain_delay(37) == 8.0


def test_delay_attempt_38_is_the_documented_step():
    assert deferred_drain_delay(38) == 8.0


def test_delay_attempt_39_is_the_documented_step():
    assert deferred_drain_delay(39) == 8.0


def test_delay_attempt_40_is_the_documented_step():
    assert deferred_drain_delay(40) == 8.0


def test_delay_attempt_41_is_the_documented_step():
    assert deferred_drain_delay(41) == 8.0


def test_delay_attempt_42_is_the_documented_step():
    assert deferred_drain_delay(42) == 8.0


def test_delay_attempt_43_is_the_documented_step():
    assert deferred_drain_delay(43) == 8.0


def test_delay_attempt_44_is_the_documented_step():
    assert deferred_drain_delay(44) == 8.0


def test_delay_attempt_45_is_the_documented_step():
    assert deferred_drain_delay(45) == 8.0


def test_delay_attempt_46_is_the_documented_step():
    assert deferred_drain_delay(46) == 8.0


def test_delay_attempt_47_is_the_documented_step():
    assert deferred_drain_delay(47) == 8.0


def test_delay_attempt_48_is_the_documented_step():
    assert deferred_drain_delay(48) == 8.0


def test_delay_attempt_49_is_the_documented_step():
    assert deferred_drain_delay(49) == 8.0


def test_delay_attempt_50_is_the_documented_step():
    assert deferred_drain_delay(50) == 8.0


def test_delay_attempt_51_is_the_documented_step():
    assert deferred_drain_delay(51) == 8.0


def test_delay_attempt_52_is_the_documented_step():
    assert deferred_drain_delay(52) == 8.0


def test_delay_attempt_53_is_the_documented_step():
    assert deferred_drain_delay(53) == 8.0


def test_delay_attempt_54_is_the_documented_step():
    assert deferred_drain_delay(54) == 8.0


def test_delay_attempt_55_is_the_documented_step():
    assert deferred_drain_delay(55) == 8.0


def test_delay_attempt_56_is_the_documented_step():
    assert deferred_drain_delay(56) == 8.0


def test_delay_attempt_57_is_the_documented_step():
    assert deferred_drain_delay(57) == 8.0


def test_delay_attempt_58_is_the_documented_step():
    assert deferred_drain_delay(58) == 8.0


def test_delay_attempt_59_is_the_documented_step():
    assert deferred_drain_delay(59) == 8.0


def test_delay_attempt_60_is_the_documented_step():
    assert deferred_drain_delay(60) == 8.0


def test_delay_attempt_61_is_the_documented_step():
    assert deferred_drain_delay(61) == 8.0


def test_delay_attempt_62_is_the_documented_step():
    assert deferred_drain_delay(62) == 8.0


def test_delay_attempt_63_is_the_documented_step():
    assert deferred_drain_delay(63) == 8.0


def test_delay_attempt_64_is_the_documented_step():
    assert deferred_drain_delay(64) == 8.0


def test_delay_sub_attempt_00_falls_back_to_the_base_step():
    assert deferred_drain_delay(0) == 0.5


def test_delay_sub_attempt_01_falls_back_to_the_base_step():
    assert deferred_drain_delay(-1) == 0.5


def test_delay_sub_attempt_10_falls_back_to_the_base_step():
    assert deferred_drain_delay(-10) == 0.5


def test_delay_from_01_to_02_never_decreases():
    assert deferred_drain_delay(2) >= deferred_drain_delay(1)


def test_delay_from_02_to_03_never_decreases():
    assert deferred_drain_delay(3) >= deferred_drain_delay(2)


def test_delay_from_03_to_04_never_decreases():
    assert deferred_drain_delay(4) >= deferred_drain_delay(3)


def test_delay_from_04_to_05_never_decreases():
    assert deferred_drain_delay(5) >= deferred_drain_delay(4)


def test_delay_from_05_to_06_never_decreases():
    assert deferred_drain_delay(6) >= deferred_drain_delay(5)


def test_delay_from_06_to_07_never_decreases():
    assert deferred_drain_delay(7) >= deferred_drain_delay(6)


def test_delay_from_07_to_08_never_decreases():
    assert deferred_drain_delay(8) >= deferred_drain_delay(7)


def test_delay_from_08_to_09_never_decreases():
    assert deferred_drain_delay(9) >= deferred_drain_delay(8)


def test_delay_from_09_to_10_never_decreases():
    assert deferred_drain_delay(10) >= deferred_drain_delay(9)


def test_delay_from_10_to_11_never_decreases():
    assert deferred_drain_delay(11) >= deferred_drain_delay(10)


def test_delay_from_11_to_12_never_decreases():
    assert deferred_drain_delay(12) >= deferred_drain_delay(11)


def test_delay_from_12_to_13_never_decreases():
    assert deferred_drain_delay(13) >= deferred_drain_delay(12)


def test_delay_from_13_to_14_never_decreases():
    assert deferred_drain_delay(14) >= deferred_drain_delay(13)


def test_delay_from_14_to_15_never_decreases():
    assert deferred_drain_delay(15) >= deferred_drain_delay(14)


def test_delay_from_15_to_16_never_decreases():
    assert deferred_drain_delay(16) >= deferred_drain_delay(15)


def test_delay_from_16_to_17_never_decreases():
    assert deferred_drain_delay(17) >= deferred_drain_delay(16)


def test_delay_attempt_05_sits_at_the_cap():
    assert deferred_drain_delay(5) == 8.0 == DRAIN_RETRY_MAX_SECONDS


def test_delay_attempt_06_sits_at_the_cap():
    assert deferred_drain_delay(6) == 8.0 == DRAIN_RETRY_MAX_SECONDS


def test_delay_attempt_07_sits_at_the_cap():
    assert deferred_drain_delay(7) == 8.0 == DRAIN_RETRY_MAX_SECONDS


def test_delay_attempt_33_sits_at_the_cap():
    assert deferred_drain_delay(33) == 8.0 == DRAIN_RETRY_MAX_SECONDS


def test_budget_constant_drain_retry_base_seconds_is_the_documented_value():
    assert DRAIN_RETRY_BASE_SECONDS == 0.5


def test_budget_constant_drain_retry_max_seconds_is_the_documented_value():
    assert DRAIN_RETRY_MAX_SECONDS == 8.0


def test_budget_constant_drain_retry_max_attempts_is_the_documented_value():
    assert DRAIN_RETRY_MAX_ATTEMPTS == 6


def test_budget_constant_drain_backlog_continuation_attempts_is_the_documented_value():
    assert DRAIN_BACKLOG_CONTINUATION_ATTEMPTS == 4


def test_budget_constant_drain_retry_ledger_cap_is_the_documented_value():
    assert DRAIN_RETRY_LEDGER_CAP == 512


def test_every_first_six_steps_are_floats():
    for attempt in range(1, 7):
        assert isinstance(deferred_drain_delay(attempt), float)
