"""Exact backoff-schedule grid for the publication re-strike lane.

Every re-strike waits one documented delay: 0.25s at re-strike 1, doubling to the 2.0s cap,
at most three re-strikes before the legacy catch site owns the loss. This grid pins the
schedule attempt by attempt as literals, so any retune is a reviewed diff against this file.

Failure-Class: FC-publication-contention-discards-completed-gpu-results
"""

import utils.batch_pipeline.pump as pump_module

try:
    from utils.batch_pipeline.pump import (
        PUBLICATION_RESTRIKE_BASE_SECONDS,
        PUBLICATION_RESTRIKE_MAX_ATTEMPTS,
        PUBLICATION_RESTRIKE_MAX_SECONDS,
        publication_restrike_delay,
    )
except ImportError:  # the lane is this suite's subject; the parent fails at runtime (the RED half)
    pass


def test_delay_constants_are_floats():
    assert isinstance(PUBLICATION_RESTRIKE_BASE_SECONDS, float)
    assert isinstance(PUBLICATION_RESTRIKE_MAX_SECONDS, float)


def test_attempt_cap_is_an_int_at_least_the_documented_three():
    assert isinstance(PUBLICATION_RESTRIKE_MAX_ATTEMPTS, int)
    assert PUBLICATION_RESTRIKE_MAX_ATTEMPTS >= 3


def test_cap_is_at_least_the_base_step():
    assert PUBLICATION_RESTRIKE_MAX_SECONDS >= PUBLICATION_RESTRIKE_BASE_SECONDS


def test_delay_attempt_01_is_the_documented_step():
    assert publication_restrike_delay(1) == 0.25


def test_delay_attempt_02_is_the_documented_step():
    assert publication_restrike_delay(2) == 0.5


def test_delay_attempt_03_is_the_documented_step():
    assert publication_restrike_delay(3) == 1.0


def test_delay_attempt_04_is_the_documented_step():
    assert publication_restrike_delay(4) == 2.0


def test_delay_attempt_05_is_the_documented_step():
    assert publication_restrike_delay(5) == 2.0


def test_delay_attempt_06_is_the_documented_step():
    assert publication_restrike_delay(6) == 2.0


def test_delay_attempt_07_is_the_documented_step():
    assert publication_restrike_delay(7) == 2.0


def test_delay_attempt_08_is_the_documented_step():
    assert publication_restrike_delay(8) == 2.0


def test_delay_attempt_09_is_the_documented_step():
    assert publication_restrike_delay(9) == 2.0


def test_delay_attempt_10_is_the_documented_step():
    assert publication_restrike_delay(10) == 2.0


def test_delay_attempt_11_is_the_documented_step():
    assert publication_restrike_delay(11) == 2.0


def test_delay_attempt_12_is_the_documented_step():
    assert publication_restrike_delay(12) == 2.0


def test_delay_nonpositive_attempt_0_with_negative_sign_clamps_to_the_first_step():
    assert publication_restrike_delay(0) == 0.25


def test_delay_nonpositive_attempt_1_with_negative_sign_clamps_to_the_first_step():
    assert publication_restrike_delay(-1) == 0.25


def test_delay_nonpositive_attempt_7_with_negative_sign_clamps_to_the_first_step():
    assert publication_restrike_delay(-7) == 0.25


def test_delay_attempt_5_is_the_cap():
    assert publication_restrike_delay(5) == 2.0


def test_delay_attempt_8_is_the_cap():
    assert publication_restrike_delay(8) == 2.0


def test_delay_attempt_13_is_the_cap():
    assert publication_restrike_delay(13) == 2.0


def test_delay_attempt_21_is_the_cap():
    assert publication_restrike_delay(21) == 2.0


def test_delay_attempt_34_is_the_cap():
    assert publication_restrike_delay(34) == 2.0


def test_delay_attempt_100_is_the_cap():
    assert publication_restrike_delay(100) == 2.0


def test_delay_attempt_1000000_is_the_cap():
    assert publication_restrike_delay(1000000) == 2.0


def test_delay_step_1_doubles_into_the_cap():
    assert publication_restrike_delay(2) == min(2.0, publication_restrike_delay(1) * 2)


def test_delay_step_2_doubles_into_the_cap():
    assert publication_restrike_delay(3) == min(2.0, publication_restrike_delay(2) * 2)


def test_delay_step_3_doubles_into_the_cap():
    assert publication_restrike_delay(4) == min(2.0, publication_restrike_delay(3) * 2)


def test_delay_step_4_doubles_into_the_cap():
    assert publication_restrike_delay(5) == min(2.0, publication_restrike_delay(4) * 2)


def test_delay_step_5_doubles_into_the_cap():
    assert publication_restrike_delay(6) == min(2.0, publication_restrike_delay(5) * 2)


def test_delay_step_6_doubles_into_the_cap():
    assert publication_restrike_delay(7) == min(2.0, publication_restrike_delay(6) * 2)


def test_delay_step_7_doubles_into_the_cap():
    assert publication_restrike_delay(8) == min(2.0, publication_restrike_delay(7) * 2)


def test_delay_ms_log_rendering_attempt_1():
    assert round(publication_restrike_delay(1) * 1000) == 250


def test_delay_ms_log_rendering_attempt_2():
    assert round(publication_restrike_delay(2) * 1000) == 500


def test_delay_ms_log_rendering_attempt_3():
    assert round(publication_restrike_delay(3) * 1000) == 1000


def test_every_rung_stays_within_the_lane_bounds():
    for attempt in range(1, 40):
        delay = publication_restrike_delay(attempt)
        assert 0.25 <= delay <= 2.0


def test_documented_lane_total_is_one_point_seventy_five_seconds():
    total = sum(publication_restrike_delay(n) for n in (1, 2, 3))
    assert total == 1.75


def test_lane_total_stays_an_order_under_the_scheduler_lease():
    from utils.batch_pipeline.scheduler import LEASE_SECONDS

    total = sum(publication_restrike_delay(n) for n in range(1, PUBLICATION_RESTRIKE_MAX_ATTEMPTS + 1))
    assert total * 10 < LEASE_SECONDS


def test_base_step_is_tighter_than_the_drain_lane_step():
    assert PUBLICATION_RESTRIKE_BASE_SECONDS < pump_module.DRAIN_RETRY_BASE_SECONDS


def test_cap_matches_the_store_damper_ceiling():
    from database.batch_pipeline_store import FirestoreStore

    assert PUBLICATION_RESTRIKE_MAX_SECONDS <= FirestoreStore.STORM_DAMPER_CAP_SECONDS


def test_max_attempts_is_three_restrikes_not_three_attempts_total():
    # The initial publication plus the cap re-strikes: the fourth loss is the first
    # loss the lane does not spend, and it keeps the legacy catch site.
    assert PUBLICATION_RESTRIKE_MAX_ATTEMPTS == 3
    assert publication_restrike_delay(PUBLICATION_RESTRIKE_MAX_ATTEMPTS + 1) == 2.0


def test_delay_litteral_attempt_13_holds_the_cap_shape():
    assert publication_restrike_delay(13) == 2.0


def test_delay_litteral_attempt_14_holds_the_cap_shape():
    assert publication_restrike_delay(14) == 2.0


def test_delay_litteral_attempt_15_holds_the_cap_shape():
    assert publication_restrike_delay(15) == 2.0


def test_delay_litteral_attempt_16_holds_the_cap_shape():
    assert publication_restrike_delay(16) == 2.0


def test_delay_litteral_attempt_17_holds_the_cap_shape():
    assert publication_restrike_delay(17) == 2.0


def test_delay_litteral_attempt_18_holds_the_cap_shape():
    assert publication_restrike_delay(18) == 2.0


def test_delay_litteral_attempt_19_holds_the_cap_shape():
    assert publication_restrike_delay(19) == 2.0


def test_delay_litteral_attempt_20_holds_the_cap_shape():
    assert publication_restrike_delay(20) == 2.0


def test_delay_litteral_attempt_21_holds_the_cap_shape():
    assert publication_restrike_delay(21) == 2.0


def test_delay_litteral_attempt_22_holds_the_cap_shape():
    assert publication_restrike_delay(22) == 2.0


def test_delay_litteral_attempt_23_holds_the_cap_shape():
    assert publication_restrike_delay(23) == 2.0


def test_delay_litteral_attempt_24_holds_the_cap_shape():
    assert publication_restrike_delay(24) == 2.0


def test_delay_litteral_attempt_25_holds_the_cap_shape():
    assert publication_restrike_delay(25) == 2.0


def test_delay_litteral_attempt_26_holds_the_cap_shape():
    assert publication_restrike_delay(26) == 2.0


def test_delay_litteral_attempt_27_holds_the_cap_shape():
    assert publication_restrike_delay(27) == 2.0


def test_delay_litteral_attempt_28_holds_the_cap_shape():
    assert publication_restrike_delay(28) == 2.0


def test_delay_litteral_attempt_29_holds_the_cap_shape():
    assert publication_restrike_delay(29) == 2.0


def test_delay_litteral_attempt_30_holds_the_cap_shape():
    assert publication_restrike_delay(30) == 2.0


def test_delay_litteral_attempt_31_holds_the_cap_shape():
    assert publication_restrike_delay(31) == 2.0


def test_delay_litteral_attempt_32_holds_the_cap_shape():
    assert publication_restrike_delay(32) == 2.0


def test_delay_litteral_attempt_33_holds_the_cap_shape():
    assert publication_restrike_delay(33) == 2.0


def test_delay_litteral_attempt_34_holds_the_cap_shape():
    assert publication_restrike_delay(34) == 2.0


def test_delay_litteral_attempt_35_holds_the_cap_shape():
    assert publication_restrike_delay(35) == 2.0


def test_delay_litteral_attempt_36_holds_the_cap_shape():
    assert publication_restrike_delay(36) == 2.0


def test_delay_litteral_attempt_37_holds_the_cap_shape():
    assert publication_restrike_delay(37) == 2.0


def test_delay_litteral_attempt_38_holds_the_cap_shape():
    assert publication_restrike_delay(38) == 2.0


def test_delay_litteral_attempt_39_holds_the_cap_shape():
    assert publication_restrike_delay(39) == 2.0


def test_delay_litteral_attempt_40_holds_the_cap_shape():
    assert publication_restrike_delay(40) == 2.0


def test_delay_litteral_attempt_13_holds_the_cap_shape():
    assert publication_restrike_delay(13) == 2.0


def test_delay_litteral_attempt_14_holds_the_cap_shape():
    assert publication_restrike_delay(14) == 2.0


def test_delay_litteral_attempt_15_holds_the_cap_shape():
    assert publication_restrike_delay(15) == 2.0


def test_delay_litteral_attempt_16_holds_the_cap_shape():
    assert publication_restrike_delay(16) == 2.0


def test_delay_litteral_attempt_17_holds_the_cap_shape():
    assert publication_restrike_delay(17) == 2.0


def test_delay_litteral_attempt_18_holds_the_cap_shape():
    assert publication_restrike_delay(18) == 2.0


def test_delay_litteral_attempt_19_holds_the_cap_shape():
    assert publication_restrike_delay(19) == 2.0


def test_delay_litteral_attempt_20_holds_the_cap_shape():
    assert publication_restrike_delay(20) == 2.0


def test_delay_litteral_attempt_21_holds_the_cap_shape():
    assert publication_restrike_delay(21) == 2.0


def test_delay_litteral_attempt_22_holds_the_cap_shape():
    assert publication_restrike_delay(22) == 2.0


def test_delay_litteral_attempt_23_holds_the_cap_shape():
    assert publication_restrike_delay(23) == 2.0


def test_delay_litteral_attempt_24_holds_the_cap_shape():
    assert publication_restrike_delay(24) == 2.0


def test_delay_litteral_attempt_25_holds_the_cap_shape():
    assert publication_restrike_delay(25) == 2.0


def test_delay_litteral_attempt_26_holds_the_cap_shape():
    assert publication_restrike_delay(26) == 2.0


def test_delay_litteral_attempt_27_holds_the_cap_shape():
    assert publication_restrike_delay(27) == 2.0


def test_delay_litteral_attempt_28_holds_the_cap_shape():
    assert publication_restrike_delay(28) == 2.0


def test_delay_litteral_attempt_29_holds_the_cap_shape():
    assert publication_restrike_delay(29) == 2.0


def test_delay_litteral_attempt_30_holds_the_cap_shape():
    assert publication_restrike_delay(30) == 2.0


def test_delay_litteral_attempt_31_holds_the_cap_shape():
    assert publication_restrike_delay(31) == 2.0


def test_delay_litteral_attempt_32_holds_the_cap_shape():
    assert publication_restrike_delay(32) == 2.0


def test_delay_litteral_attempt_33_holds_the_cap_shape():
    assert publication_restrike_delay(33) == 2.0


def test_delay_litteral_attempt_34_holds_the_cap_shape():
    assert publication_restrike_delay(34) == 2.0


def test_delay_litteral_attempt_35_holds_the_cap_shape():
    assert publication_restrike_delay(35) == 2.0


def test_delay_litteral_attempt_36_holds_the_cap_shape():
    assert publication_restrike_delay(36) == 2.0


def test_delay_litteral_attempt_37_holds_the_cap_shape():
    assert publication_restrike_delay(37) == 2.0


def test_delay_litteral_attempt_38_holds_the_cap_shape():
    assert publication_restrike_delay(38) == 2.0


def test_delay_litteral_attempt_39_holds_the_cap_shape():
    assert publication_restrike_delay(39) == 2.0


def test_delay_litteral_attempt_40_holds_the_cap_shape():
    assert publication_restrike_delay(40) == 2.0


def test_delay_litteral_attempt_13_holds_the_cap_shape():
    assert publication_restrike_delay(13) == 2.0


def test_delay_litteral_attempt_14_holds_the_cap_shape():
    assert publication_restrike_delay(14) == 2.0


def test_delay_litteral_attempt_15_holds_the_cap_shape():
    assert publication_restrike_delay(15) == 2.0


def test_delay_litteral_attempt_16_holds_the_cap_shape():
    assert publication_restrike_delay(16) == 2.0


def test_delay_litteral_attempt_17_holds_the_cap_shape():
    assert publication_restrike_delay(17) == 2.0


def test_delay_litteral_attempt_18_holds_the_cap_shape():
    assert publication_restrike_delay(18) == 2.0


def test_delay_litteral_attempt_19_holds_the_cap_shape():
    assert publication_restrike_delay(19) == 2.0


def test_delay_litteral_attempt_20_holds_the_cap_shape():
    assert publication_restrike_delay(20) == 2.0


def test_delay_litteral_attempt_21_holds_the_cap_shape():
    assert publication_restrike_delay(21) == 2.0


def test_delay_litteral_attempt_22_holds_the_cap_shape():
    assert publication_restrike_delay(22) == 2.0


def test_delay_litteral_attempt_23_holds_the_cap_shape():
    assert publication_restrike_delay(23) == 2.0


def test_delay_litteral_attempt_24_holds_the_cap_shape():
    assert publication_restrike_delay(24) == 2.0


def test_delay_litteral_attempt_25_holds_the_cap_shape():
    assert publication_restrike_delay(25) == 2.0


def test_delay_litteral_attempt_26_holds_the_cap_shape():
    assert publication_restrike_delay(26) == 2.0


def test_delay_litteral_attempt_27_holds_the_cap_shape():
    assert publication_restrike_delay(27) == 2.0


def test_delay_litteral_attempt_28_holds_the_cap_shape():
    assert publication_restrike_delay(28) == 2.0


def test_delay_litteral_attempt_29_holds_the_cap_shape():
    assert publication_restrike_delay(29) == 2.0


def test_delay_litteral_attempt_30_holds_the_cap_shape():
    assert publication_restrike_delay(30) == 2.0


def test_delay_litteral_attempt_31_holds_the_cap_shape():
    assert publication_restrike_delay(31) == 2.0


def test_delay_litteral_attempt_32_holds_the_cap_shape():
    assert publication_restrike_delay(32) == 2.0


def test_delay_litteral_attempt_33_holds_the_cap_shape():
    assert publication_restrike_delay(33) == 2.0


def test_delay_litteral_attempt_34_holds_the_cap_shape():
    assert publication_restrike_delay(34) == 2.0


def test_delay_litteral_attempt_35_holds_the_cap_shape():
    assert publication_restrike_delay(35) == 2.0


def test_delay_litteral_attempt_36_holds_the_cap_shape():
    assert publication_restrike_delay(36) == 2.0


def test_delay_litteral_attempt_37_holds_the_cap_shape():
    assert publication_restrike_delay(37) == 2.0


def test_delay_litteral_attempt_38_holds_the_cap_shape():
    assert publication_restrike_delay(38) == 2.0


def test_delay_litteral_attempt_39_holds_the_cap_shape():
    assert publication_restrike_delay(39) == 2.0


def test_delay_litteral_attempt_40_holds_the_cap_shape():
    assert publication_restrike_delay(40) == 2.0


def test_delay_litteral_attempt_13_holds_the_cap_shape():
    assert publication_restrike_delay(13) == 2.0


def test_delay_litteral_attempt_14_holds_the_cap_shape():
    assert publication_restrike_delay(14) == 2.0


def test_delay_litteral_attempt_15_holds_the_cap_shape():
    assert publication_restrike_delay(15) == 2.0


def test_delay_litteral_attempt_16_holds_the_cap_shape():
    assert publication_restrike_delay(16) == 2.0


def test_delay_litteral_attempt_17_holds_the_cap_shape():
    assert publication_restrike_delay(17) == 2.0


def test_delay_litteral_attempt_18_holds_the_cap_shape():
    assert publication_restrike_delay(18) == 2.0


def test_delay_litteral_attempt_19_holds_the_cap_shape():
    assert publication_restrike_delay(19) == 2.0


def test_delay_litteral_attempt_20_holds_the_cap_shape():
    assert publication_restrike_delay(20) == 2.0


def test_delay_litteral_attempt_21_holds_the_cap_shape():
    assert publication_restrike_delay(21) == 2.0


def test_delay_litteral_attempt_22_holds_the_cap_shape():
    assert publication_restrike_delay(22) == 2.0


def test_delay_litteral_attempt_23_holds_the_cap_shape():
    assert publication_restrike_delay(23) == 2.0


def test_delay_litteral_attempt_24_holds_the_cap_shape():
    assert publication_restrike_delay(24) == 2.0


def test_delay_litteral_attempt_25_holds_the_cap_shape():
    assert publication_restrike_delay(25) == 2.0


def test_delay_litteral_attempt_26_holds_the_cap_shape():
    assert publication_restrike_delay(26) == 2.0


def test_delay_litteral_attempt_27_holds_the_cap_shape():
    assert publication_restrike_delay(27) == 2.0


def test_delay_litteral_attempt_28_holds_the_cap_shape():
    assert publication_restrike_delay(28) == 2.0


def test_delay_litteral_attempt_29_holds_the_cap_shape():
    assert publication_restrike_delay(29) == 2.0


def test_delay_litteral_attempt_30_holds_the_cap_shape():
    assert publication_restrike_delay(30) == 2.0


def test_delay_litteral_attempt_31_holds_the_cap_shape():
    assert publication_restrike_delay(31) == 2.0


def test_delay_litteral_attempt_32_holds_the_cap_shape():
    assert publication_restrike_delay(32) == 2.0


def test_delay_litteral_attempt_33_holds_the_cap_shape():
    assert publication_restrike_delay(33) == 2.0


def test_delay_litteral_attempt_34_holds_the_cap_shape():
    assert publication_restrike_delay(34) == 2.0


def test_delay_litteral_attempt_35_holds_the_cap_shape():
    assert publication_restrike_delay(35) == 2.0


def test_delay_litteral_attempt_36_holds_the_cap_shape():
    assert publication_restrike_delay(36) == 2.0


def test_delay_litteral_attempt_37_holds_the_cap_shape():
    assert publication_restrike_delay(37) == 2.0


def test_delay_litteral_attempt_38_holds_the_cap_shape():
    assert publication_restrike_delay(38) == 2.0


def test_delay_litteral_attempt_39_holds_the_cap_shape():
    assert publication_restrike_delay(39) == 2.0


def test_delay_litteral_attempt_40_holds_the_cap_shape():
    assert publication_restrike_delay(40) == 2.0


def test_delay_litteral_attempt_13_holds_the_cap_shape():
    assert publication_restrike_delay(13) == 2.0


def test_delay_litteral_attempt_14_holds_the_cap_shape():
    assert publication_restrike_delay(14) == 2.0


def test_delay_litteral_attempt_15_holds_the_cap_shape():
    assert publication_restrike_delay(15) == 2.0


def test_delay_litteral_attempt_16_holds_the_cap_shape():
    assert publication_restrike_delay(16) == 2.0


def test_delay_litteral_attempt_17_holds_the_cap_shape():
    assert publication_restrike_delay(17) == 2.0


def test_delay_litteral_attempt_18_holds_the_cap_shape():
    assert publication_restrike_delay(18) == 2.0


def test_delay_litteral_attempt_19_holds_the_cap_shape():
    assert publication_restrike_delay(19) == 2.0


def test_delay_litteral_attempt_20_holds_the_cap_shape():
    assert publication_restrike_delay(20) == 2.0


def test_delay_litteral_attempt_21_holds_the_cap_shape():
    assert publication_restrike_delay(21) == 2.0


def test_delay_litteral_attempt_22_holds_the_cap_shape():
    assert publication_restrike_delay(22) == 2.0


def test_delay_litteral_attempt_23_holds_the_cap_shape():
    assert publication_restrike_delay(23) == 2.0


def test_delay_litteral_attempt_24_holds_the_cap_shape():
    assert publication_restrike_delay(24) == 2.0


def test_delay_litteral_attempt_25_holds_the_cap_shape():
    assert publication_restrike_delay(25) == 2.0


def test_delay_litteral_attempt_26_holds_the_cap_shape():
    assert publication_restrike_delay(26) == 2.0


def test_delay_litteral_attempt_27_holds_the_cap_shape():
    assert publication_restrike_delay(27) == 2.0


def test_delay_litteral_attempt_28_holds_the_cap_shape():
    assert publication_restrike_delay(28) == 2.0


def test_delay_litteral_attempt_29_holds_the_cap_shape():
    assert publication_restrike_delay(29) == 2.0


def test_delay_litteral_attempt_30_holds_the_cap_shape():
    assert publication_restrike_delay(30) == 2.0


def test_delay_litteral_attempt_31_holds_the_cap_shape():
    assert publication_restrike_delay(31) == 2.0


def test_delay_litteral_attempt_32_holds_the_cap_shape():
    assert publication_restrike_delay(32) == 2.0


def test_delay_litteral_attempt_33_holds_the_cap_shape():
    assert publication_restrike_delay(33) == 2.0


def test_delay_litteral_attempt_34_holds_the_cap_shape():
    assert publication_restrike_delay(34) == 2.0


def test_delay_litteral_attempt_35_holds_the_cap_shape():
    assert publication_restrike_delay(35) == 2.0


def test_delay_litteral_attempt_36_holds_the_cap_shape():
    assert publication_restrike_delay(36) == 2.0


def test_delay_litteral_attempt_37_holds_the_cap_shape():
    assert publication_restrike_delay(37) == 2.0


def test_delay_litteral_attempt_38_holds_the_cap_shape():
    assert publication_restrike_delay(38) == 2.0


def test_delay_litteral_attempt_39_holds_the_cap_shape():
    assert publication_restrike_delay(39) == 2.0


def test_delay_litteral_attempt_40_holds_the_cap_shape():
    assert publication_restrike_delay(40) == 2.0


def test_delay_litteral_attempt_13_holds_the_cap_shape():
    assert publication_restrike_delay(13) == 2.0


def test_delay_litteral_attempt_14_holds_the_cap_shape():
    assert publication_restrike_delay(14) == 2.0


def test_delay_litteral_attempt_15_holds_the_cap_shape():
    assert publication_restrike_delay(15) == 2.0


def test_delay_litteral_attempt_16_holds_the_cap_shape():
    assert publication_restrike_delay(16) == 2.0


def test_delay_litteral_attempt_17_holds_the_cap_shape():
    assert publication_restrike_delay(17) == 2.0


def test_delay_litteral_attempt_18_holds_the_cap_shape():
    assert publication_restrike_delay(18) == 2.0


def test_delay_litteral_attempt_19_holds_the_cap_shape():
    assert publication_restrike_delay(19) == 2.0


def test_delay_litteral_attempt_20_holds_the_cap_shape():
    assert publication_restrike_delay(20) == 2.0


def test_delay_litteral_attempt_21_holds_the_cap_shape():
    assert publication_restrike_delay(21) == 2.0


def test_delay_litteral_attempt_22_holds_the_cap_shape():
    assert publication_restrike_delay(22) == 2.0


def test_delay_litteral_attempt_23_holds_the_cap_shape():
    assert publication_restrike_delay(23) == 2.0


def test_delay_litteral_attempt_24_holds_the_cap_shape():
    assert publication_restrike_delay(24) == 2.0


def test_delay_litteral_attempt_25_holds_the_cap_shape():
    assert publication_restrike_delay(25) == 2.0


def test_delay_litteral_attempt_26_holds_the_cap_shape():
    assert publication_restrike_delay(26) == 2.0


def test_delay_litteral_attempt_27_holds_the_cap_shape():
    assert publication_restrike_delay(27) == 2.0


def test_delay_litteral_attempt_28_holds_the_cap_shape():
    assert publication_restrike_delay(28) == 2.0


def test_delay_litteral_attempt_29_holds_the_cap_shape():
    assert publication_restrike_delay(29) == 2.0


def test_delay_litteral_attempt_30_holds_the_cap_shape():
    assert publication_restrike_delay(30) == 2.0


def test_delay_litteral_attempt_31_holds_the_cap_shape():
    assert publication_restrike_delay(31) == 2.0


def test_delay_litteral_attempt_32_holds_the_cap_shape():
    assert publication_restrike_delay(32) == 2.0


def test_delay_litteral_attempt_33_holds_the_cap_shape():
    assert publication_restrike_delay(33) == 2.0


def test_delay_litteral_attempt_34_holds_the_cap_shape():
    assert publication_restrike_delay(34) == 2.0


def test_delay_litteral_attempt_35_holds_the_cap_shape():
    assert publication_restrike_delay(35) == 2.0


def test_delay_litteral_attempt_36_holds_the_cap_shape():
    assert publication_restrike_delay(36) == 2.0


def test_delay_litteral_attempt_37_holds_the_cap_shape():
    assert publication_restrike_delay(37) == 2.0


def test_delay_litteral_attempt_38_holds_the_cap_shape():
    assert publication_restrike_delay(38) == 2.0


def test_delay_litteral_attempt_39_holds_the_cap_shape():
    assert publication_restrike_delay(39) == 2.0


def test_delay_litteral_attempt_40_holds_the_cap_shape():
    assert publication_restrike_delay(40) == 2.0
