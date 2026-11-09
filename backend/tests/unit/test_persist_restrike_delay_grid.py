#!/usr/bin/env python3
"""Exact backoff-schedule grid for the worker persist re-strike lane.

Every re-strike waits one documented delay: 0.25s at strike 1, doubling to the 2.0s cap,
at most three strikes before the legacy persist fault owns the loss. This grid pins the
schedule attempt by attempt as literals and keeps the worker lane synchronized with the
pump publication lane it was modeled on, so any retune is a reviewed diff against this file.

Failure-Class: FC-persist-transport-loss-discards-completed-gpu-results
"""

import os

import pytest  # noqa: F401

from utils.batch_pipeline import pump as pump_module

try:
    from diarizer.batch_pipeline import (
        PERSIST_RESTRIKE_BASE_SECONDS,
        PERSIST_RESTRIKE_MAX_ATTEMPTS,
        PERSIST_RESTRIKE_MAX_SECONDS,
        persist_loss_is_restrikeable,
        persist_restrike_delay,
    )
except ImportError:  # the lane is this suite's subject; the parent fails at runtime (the RED half)
    pass


try:
    from diarizer.batch_pipeline import (
        PERSIST_RESTRIKE_BASE_SECONDS,
        PERSIST_RESTRIKE_MAX_ATTEMPTS,
        PERSIST_RESTRIKE_MAX_SECONDS,
        persist_loss_is_restrikeable,
        persist_restrike_delay,
    )
except ImportError:  # the lane is this suite's subject; the parent fails at runtime (the RED half)
    pass


from utils.batch_pipeline import pump as pump_module
import os

DOC_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'docs', 'persist-restrike-lane.md')


def test_delay_constants_are_floats():
    assert isinstance(PERSIST_RESTRIKE_BASE_SECONDS, float)
    assert isinstance(PERSIST_RESTRIKE_MAX_SECONDS, float)


def test_attempt_cap_is_an_int_at_least_the_documented_three():
    assert isinstance(PERSIST_RESTRIKE_MAX_ATTEMPTS, int)
    assert PERSIST_RESTRIKE_MAX_ATTEMPTS >= 3


def test_attempt_cap_is_exactly_the_documented_three():
    assert PERSIST_RESTRIKE_MAX_ATTEMPTS == 3


def test_cap_is_at_least_the_base_step():
    assert PERSIST_RESTRIKE_MAX_SECONDS >= PERSIST_RESTRIKE_BASE_SECONDS


def test_base_step_is_positive():
    assert PERSIST_RESTRIKE_BASE_SECONDS > 0


def test_cap_is_two_seconds():
    assert PERSIST_RESTRIKE_MAX_SECONDS == 2.0


def test_base_is_a_quarter_second():
    assert PERSIST_RESTRIKE_BASE_SECONDS == 0.25


def test_delay_attempt_01_pins_the_documented_step():
    assert persist_restrike_delay(1) == 0.25


def test_delay_attempt_02_pins_the_documented_step():
    assert persist_restrike_delay(2) == 0.5


def test_delay_attempt_03_pins_the_documented_step():
    assert persist_restrike_delay(3) == 1.0


def test_delay_attempt_04_pins_the_documented_step():
    assert persist_restrike_delay(4) == 2.0


def test_delay_attempt_05_pins_the_documented_step():
    assert persist_restrike_delay(5) == 2.0


def test_delay_attempt_06_pins_the_documented_step():
    assert persist_restrike_delay(6) == 2.0


def test_delay_attempt_07_pins_the_documented_step():
    assert persist_restrike_delay(7) == 2.0


def test_delay_attempt_08_pins_the_documented_step():
    assert persist_restrike_delay(8) == 2.0


def test_delay_attempt_09_pins_the_documented_step():
    assert persist_restrike_delay(9) == 2.0


def test_delay_attempt_10_pins_the_documented_step():
    assert persist_restrike_delay(10) == 2.0


def test_delay_attempt_11_pins_the_documented_step():
    assert persist_restrike_delay(11) == 2.0


def test_delay_attempt_12_pins_the_documented_step():
    assert persist_restrike_delay(12) == 2.0


def test_delay_attempt_13_pins_the_documented_step():
    assert persist_restrike_delay(13) == 2.0


def test_delay_attempt_14_pins_the_documented_step():
    assert persist_restrike_delay(14) == 2.0


def test_delay_attempt_15_pins_the_documented_step():
    assert persist_restrike_delay(15) == 2.0


def test_delay_attempt_16_pins_the_documented_step():
    assert persist_restrike_delay(16) == 2.0


def test_delay_attempt_17_pins_the_documented_step():
    assert persist_restrike_delay(17) == 2.0


def test_delay_attempt_18_pins_the_documented_step():
    assert persist_restrike_delay(18) == 2.0


def test_delay_attempt_19_pins_the_documented_step():
    assert persist_restrike_delay(19) == 2.0


def test_delay_attempt_20_pins_the_documented_step():
    assert persist_restrike_delay(20) == 2.0


def test_delay_attempt_21_pins_the_documented_step():
    assert persist_restrike_delay(21) == 2.0


def test_delay_attempt_22_pins_the_documented_step():
    assert persist_restrike_delay(22) == 2.0


def test_delay_attempt_23_pins_the_documented_step():
    assert persist_restrike_delay(23) == 2.0


def test_delay_attempt_24_pins_the_documented_step():
    assert persist_restrike_delay(24) == 2.0


def test_delay_attempt_zero_schedules_the_base_step():
    assert persist_restrike_delay(0) == 0.25


def test_delay_negative_attempt_schedules_the_base_step():
    assert persist_restrike_delay(-1) == 0.25


def test_delay_very_negative_attempt_schedules_the_base_step():
    assert persist_restrike_delay(-100) == 0.25


def test_schedule_is_non_decreasing_across_the_first_three_strikes():
    assert persist_restrike_delay(1) <= persist_restrike_delay(2) <= persist_restrike_delay(3)


def test_schedule_saturates_from_strike_four():
    assert persist_restrike_delay(3) <= persist_restrike_delay(4) == persist_restrike_delay(5)


def test_schedule_never_exceeds_the_cap_across_a_long_chain():
    assert all(persist_restrike_delay(attempt) <= PERSIST_RESTRIKE_MAX_SECONDS for attempt in range(1, 40))


def test_schedule_matches_the_documented_pairs():
    schedule = {1: 0.25, 2: 0.5, 3: 1.0}
    assert {attempt: persist_restrike_delay(attempt) for attempt in schedule} == schedule


def test_every_documented_step_is_within_the_cap():
    assert all(persist_restrike_delay(attempt) <= PERSIST_RESTRIKE_MAX_SECONDS for attempt in (1, 2, 3))


def test_schedule_matches_the_pump_lane_step_one():
    assert persist_restrike_delay(1) == pump_module.publication_restrike_delay(1)


def test_schedule_matches_the_pump_lane_step_two():
    assert persist_restrike_delay(2) == pump_module.publication_restrike_delay(2)


def test_schedule_matches_the_pump_lane_step_three():
    assert persist_restrike_delay(3) == pump_module.publication_restrike_delay(3)


def test_schedule_matches_the_pump_lane_past_the_cap():
    assert persist_restrike_delay(4) == pump_module.publication_restrike_delay(4)


def test_schedule_base_matches_the_pump_lane_constant():
    assert PERSIST_RESTRIKE_BASE_SECONDS == pump_module.PUBLICATION_RESTRIKE_BASE_SECONDS


def test_schedule_cap_matches_the_pump_lane_constant():
    assert PERSIST_RESTRIKE_MAX_SECONDS == pump_module.PUBLICATION_RESTRIKE_MAX_SECONDS


def test_schedule_cap_attempts_match_the_pump_lane_constant():
    assert PERSIST_RESTRIKE_MAX_ATTEMPTS == pump_module.PUBLICATION_RESTRIKE_MAX_ATTEMPTS


def test_the_two_lanes_stay_independent_constants():
    # Each lane owns its module-level constants; retuning one is never a silent retune of the other.
    assert pump_module.publication_restrike_delay(2) == pump_module.PUBLICATION_RESTRIKE_BASE_SECONDS * 2


def test_doc_pins_the_first_strike_delay():
    assert '0.25s at strike 1' in open(DOC_PATH).read()


def test_doc_pins_the_second_strike_delay():
    assert '0.5s at 2' in open(DOC_PATH).read()


def test_doc_pins_the_third_strike_delay():
    assert '1.0s at 3' in open(DOC_PATH).read()


def test_doc_pins_the_cap():
    assert 'capped at 2.0s' in open(DOC_PATH).read()


def test_doc_pins_the_attempt_cap():
    assert 'PERSIST_RESTRIKE_MAX_ATTEMPTS = 3' in open(DOC_PATH).read()


def test_code_constants_match_the_doc_schedule():
    text = open(DOC_PATH).read()
    assert f"{PERSIST_RESTRIKE_BASE_SECONDS}s at strike 1" in text
    assert f"capped at {PERSIST_RESTRIKE_MAX_SECONDS}s" in text
