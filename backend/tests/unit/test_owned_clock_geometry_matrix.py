"""Owned-clock boundary geometry matrix across captured extents and recognition lanes.

One contract, every extent: a recognition clock is owned by a capture only
when its midpoint lies inside it. Words wholly before the capture (TDT
start-state ghosts) and wholly at-or-past its end (frame-quantized tails)
drop at every window length the pipeline cuts; edge-straddlers clamp to the
captured extent; malformed in-domain clocks still fail closed. The matrix is
written as literal cases because every (extent, geometry) pair is a distinct
production boundary — sub-frame windows, the one-sample edge, minute and
hour-long units — and because a parametrized case would collapse the
per-extent expected clocks the contract must produce exactly.

Pure-function geometry, cross-lane parity (GPU window function and recovery
validator), and the compose-with-strict-validator guarantee are pinned here.
Non-dropped clocks stay in raw ascending order in every composite, matching
how recognition hypotheses actually arrive.
"""

import pytest

from utils.batch_pipeline.recovery_disposition import RecoveryFailure, at_stage
from utils.batch_pipeline.recovery_recognizers import validate_response
from utils.batch_pipeline.word_validation import BatchValidationError, bounded_window_words

RATE = 16000
SPANS = [{'start': 0.0, 'end': 2.0}]


def word(text, start, end):
    return {'word': text, 'timestamp': [start, end]}


def raw(text, start, end):
    return {'text': text, 'timestamp': [start, end]}


def test_pre_window_ghost_geometry_on_a_0_02_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('pre_window_ghost', -0.05, -0.01)], 0.02) == []


def test_straddling_start_geometry_on_a_0_02_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('straddling_start', -0.02, 0.01)], 0.02) == []


def test_straddling_to_end_geometry_on_a_0_02_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('straddling_to_end', -0.02, 0.12000000000000001)], 0.02) == []


def test_tail_at_end_geometry_on_a_0_02_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('tail_at_end', 0.02, 0.07)], 0.02) == []


def test_tail_far_past_geometry_on_a_0_02_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('tail_far_past', 1.02, 2.02)], 0.02) == []


def test_kept_mid_geometry_on_a_0_02_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('kept_mid', 0.005, 0.01)], 0.02) == [word('kept_mid', 0.005, 0.01)]


def test_point_at_start_geometry_on_a_0_02_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('point_at_start', 0.0, 0.0)], 0.02) == [word('point_at_start', 0, 0.0)]


def test_pre_window_ghost_geometry_on_a_0_1_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('pre_window_ghost', -0.05, -0.01)], 0.1) == []


def test_straddling_start_geometry_on_a_0_1_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('straddling_start', -0.02, 0.05)], 0.1) == [word('straddling_start', 0, 0.05)]


def test_straddling_to_end_geometry_on_a_0_1_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('straddling_to_end', -0.02, 0.2)], 0.1) == [word('straddling_to_end', 0, 0.1)]


def test_tail_at_end_geometry_on_a_0_1_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('tail_at_end', 0.1, 0.15000000000000002)], 0.1) == []


def test_tail_far_past_geometry_on_a_0_1_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('tail_far_past', 1.1, 2.1)], 0.1) == []


def test_kept_mid_geometry_on_a_0_1_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('kept_mid', 0.025, 0.05)], 0.1) == [word('kept_mid', 0.025, 0.05)]


def test_point_at_start_geometry_on_a_0_1_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('point_at_start', 0.0, 0.0)], 0.1) == [word('point_at_start', 0, 0.0)]


def test_pre_window_ghost_geometry_on_a_0_25_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('pre_window_ghost', -0.05, -0.01)], 0.25) == []


def test_straddling_start_geometry_on_a_0_25_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('straddling_start', -0.02, 0.125)], 0.25) == [word('straddling_start', 0, 0.125)]


def test_straddling_to_end_geometry_on_a_0_25_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('straddling_to_end', -0.02, 0.35)], 0.25) == [word('straddling_to_end', 0, 0.25)]


def test_tail_at_end_geometry_on_a_0_25_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('tail_at_end', 0.25, 0.3)], 0.25) == []


def test_tail_far_past_geometry_on_a_0_25_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('tail_far_past', 1.25, 2.25)], 0.25) == []


def test_kept_mid_geometry_on_a_0_25_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('kept_mid', 0.0625, 0.125)], 0.25) == [word('kept_mid', 0.0625, 0.125)]


def test_point_at_start_geometry_on_a_0_25_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('point_at_start', 0.0, 0.0)], 0.25) == [word('point_at_start', 0, 0.0)]


def test_pre_window_ghost_geometry_on_a_0_5_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('pre_window_ghost', -0.05, -0.01)], 0.5) == []


def test_straddling_start_geometry_on_a_0_5_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('straddling_start', -0.02, 0.25)], 0.5) == [word('straddling_start', 0, 0.25)]


def test_straddling_to_end_geometry_on_a_0_5_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('straddling_to_end', -0.02, 0.6)], 0.5) == [word('straddling_to_end', 0, 0.5)]


def test_tail_at_end_geometry_on_a_0_5_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('tail_at_end', 0.5, 0.55)], 0.5) == []


def test_tail_far_past_geometry_on_a_0_5_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('tail_far_past', 1.5, 2.5)], 0.5) == []


def test_kept_mid_geometry_on_a_0_5_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('kept_mid', 0.125, 0.25)], 0.5) == [word('kept_mid', 0.125, 0.25)]


def test_point_at_start_geometry_on_a_0_5_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('point_at_start', 0.0, 0.0)], 0.5) == [word('point_at_start', 0, 0.0)]


def test_pre_window_ghost_geometry_on_a_1_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('pre_window_ghost', -0.05, -0.01)], 1.0) == []


def test_straddling_start_geometry_on_a_1_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('straddling_start', -0.02, 0.5)], 1.0) == [word('straddling_start', 0, 0.5)]


def test_straddling_to_end_geometry_on_a_1_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('straddling_to_end', -0.02, 1.1)], 1.0) == [word('straddling_to_end', 0, 1.0)]


def test_tail_at_end_geometry_on_a_1_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('tail_at_end', 1.0, 1.05)], 1.0) == []


def test_tail_far_past_geometry_on_a_1_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('tail_far_past', 2.0, 3.0)], 1.0) == []


def test_kept_mid_geometry_on_a_1_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('kept_mid', 0.25, 0.5)], 1.0) == [word('kept_mid', 0.25, 0.5)]


def test_point_at_start_geometry_on_a_1_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('point_at_start', 0.0, 0.0)], 1.0) == [word('point_at_start', 0, 0.0)]


def test_pre_window_ghost_geometry_on_a_2_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('pre_window_ghost', -0.05, -0.01)], 2.0) == []


def test_straddling_start_geometry_on_a_2_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('straddling_start', -0.02, 1.0)], 2.0) == [word('straddling_start', 0, 1.0)]


def test_straddling_to_end_geometry_on_a_2_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('straddling_to_end', -0.02, 2.1)], 2.0) == [word('straddling_to_end', 0, 2.0)]


def test_tail_at_end_geometry_on_a_2_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('tail_at_end', 2.0, 2.05)], 2.0) == []


def test_tail_far_past_geometry_on_a_2_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('tail_far_past', 3.0, 4.0)], 2.0) == []


def test_kept_mid_geometry_on_a_2_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('kept_mid', 0.5, 1.0)], 2.0) == [word('kept_mid', 0.5, 1.0)]


def test_point_at_start_geometry_on_a_2_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('point_at_start', 0.0, 0.0)], 2.0) == [word('point_at_start', 0, 0.0)]


def test_pre_window_ghost_geometry_on_a_4_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('pre_window_ghost', -0.05, -0.01)], 4.0) == []


def test_straddling_start_geometry_on_a_4_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('straddling_start', -0.02, 2.0)], 4.0) == [word('straddling_start', 0, 2.0)]


def test_straddling_to_end_geometry_on_a_4_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('straddling_to_end', -0.02, 4.1)], 4.0) == [word('straddling_to_end', 0, 4.0)]


def test_tail_at_end_geometry_on_a_4_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('tail_at_end', 4.0, 4.05)], 4.0) == []


def test_tail_far_past_geometry_on_a_4_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('tail_far_past', 5.0, 6.0)], 4.0) == []


def test_kept_mid_geometry_on_a_4_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('kept_mid', 1.0, 2.0)], 4.0) == [word('kept_mid', 1.0, 2.0)]


def test_point_at_start_geometry_on_a_4_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('point_at_start', 0.0, 0.0)], 4.0) == [word('point_at_start', 0, 0.0)]


def test_pre_window_ghost_geometry_on_a_8_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('pre_window_ghost', -0.05, -0.01)], 8.0) == []


def test_straddling_start_geometry_on_a_8_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('straddling_start', -0.02, 4.0)], 8.0) == [word('straddling_start', 0, 4.0)]


def test_straddling_to_end_geometry_on_a_8_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('straddling_to_end', -0.02, 8.1)], 8.0) == [word('straddling_to_end', 0, 8.0)]


def test_tail_at_end_geometry_on_a_8_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('tail_at_end', 8.0, 8.05)], 8.0) == []


def test_tail_far_past_geometry_on_a_8_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('tail_far_past', 9.0, 10.0)], 8.0) == []


def test_kept_mid_geometry_on_a_8_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('kept_mid', 2.0, 4.0)], 8.0) == [word('kept_mid', 2.0, 4.0)]


def test_point_at_start_geometry_on_a_8_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('point_at_start', 0.0, 0.0)], 8.0) == [word('point_at_start', 0, 0.0)]


def test_pre_window_ghost_geometry_on_a_30_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('pre_window_ghost', -0.05, -0.01)], 30.0) == []


def test_straddling_start_geometry_on_a_30_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('straddling_start', -0.02, 15.0)], 30.0) == [word('straddling_start', 0, 15.0)]


def test_straddling_to_end_geometry_on_a_30_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('straddling_to_end', -0.02, 30.1)], 30.0) == [word('straddling_to_end', 0, 30.0)]


def test_tail_at_end_geometry_on_a_30_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('tail_at_end', 30.0, 30.05)], 30.0) == []


def test_tail_far_past_geometry_on_a_30_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('tail_far_past', 31.0, 32.0)], 30.0) == []


def test_kept_mid_geometry_on_a_30_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('kept_mid', 7.5, 15.0)], 30.0) == [word('kept_mid', 7.5, 15.0)]


def test_point_at_start_geometry_on_a_30_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('point_at_start', 0.0, 0.0)], 30.0) == [word('point_at_start', 0, 0.0)]


def test_pre_window_ghost_geometry_on_a_45_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('pre_window_ghost', -0.05, -0.01)], 45.0) == []


def test_straddling_start_geometry_on_a_45_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('straddling_start', -0.02, 22.5)], 45.0) == [word('straddling_start', 0, 22.5)]


def test_straddling_to_end_geometry_on_a_45_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('straddling_to_end', -0.02, 45.1)], 45.0) == [word('straddling_to_end', 0, 45.0)]


def test_tail_at_end_geometry_on_a_45_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('tail_at_end', 45.0, 45.05)], 45.0) == []


def test_tail_far_past_geometry_on_a_45_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('tail_far_past', 46.0, 47.0)], 45.0) == []


def test_kept_mid_geometry_on_a_45_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('kept_mid', 11.25, 22.5)], 45.0) == [word('kept_mid', 11.25, 22.5)]


def test_point_at_start_geometry_on_a_45_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('point_at_start', 0.0, 0.0)], 45.0) == [word('point_at_start', 0, 0.0)]


def test_pre_window_ghost_geometry_on_a_600_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('pre_window_ghost', -0.05, -0.01)], 600.0) == []


def test_straddling_start_geometry_on_a_600_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('straddling_start', -0.02, 300.0)], 600.0) == [word('straddling_start', 0, 300.0)]


def test_straddling_to_end_geometry_on_a_600_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('straddling_to_end', -0.02, 600.1)], 600.0) == [
        word('straddling_to_end', 0, 600.0)
    ]


def test_tail_at_end_geometry_on_a_600_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('tail_at_end', 600.0, 600.05)], 600.0) == []


def test_tail_far_past_geometry_on_a_600_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('tail_far_past', 601.0, 602.0)], 600.0) == []


def test_kept_mid_geometry_on_a_600_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('kept_mid', 150.0, 300.0)], 600.0) == [word('kept_mid', 150.0, 300.0)]


def test_point_at_start_geometry_on_a_600_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('point_at_start', 0.0, 0.0)], 600.0) == [word('point_at_start', 0, 0.0)]


def test_pre_window_ghost_geometry_on_a_1800_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('pre_window_ghost', -0.05, -0.01)], 1800.0) == []


def test_straddling_start_geometry_on_a_1800_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('straddling_start', -0.02, 900.0)], 1800.0) == [
        word('straddling_start', 0, 900.0)
    ]


def test_straddling_to_end_geometry_on_a_1800_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('straddling_to_end', -0.02, 1800.1)], 1800.0) == [
        word('straddling_to_end', 0, 1800.0)
    ]


def test_tail_at_end_geometry_on_a_1800_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('tail_at_end', 1800.0, 1800.05)], 1800.0) == []


def test_tail_far_past_geometry_on_a_1800_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('tail_far_past', 1801.0, 1802.0)], 1800.0) == []


def test_kept_mid_geometry_on_a_1800_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('kept_mid', 450.0, 900.0)], 1800.0) == [word('kept_mid', 450.0, 900.0)]


def test_point_at_start_geometry_on_a_1800_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('point_at_start', 0.0, 0.0)], 1800.0) == [word('point_at_start', 0, 0.0)]


def test_pre_window_ghost_geometry_on_a_3600_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('pre_window_ghost', -0.05, -0.01)], 3600.0) == []


def test_straddling_start_geometry_on_a_3600_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('straddling_start', -0.02, 1800.0)], 3600.0) == [
        word('straddling_start', 0, 1800.0)
    ]


def test_straddling_to_end_geometry_on_a_3600_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('straddling_to_end', -0.02, 3600.1)], 3600.0) == [
        word('straddling_to_end', 0, 3600.0)
    ]


def test_tail_at_end_geometry_on_a_3600_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('tail_at_end', 3600.0, 3600.05)], 3600.0) == []


def test_tail_far_past_geometry_on_a_3600_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('tail_far_past', 3601.0, 3602.0)], 3600.0) == []


def test_kept_mid_geometry_on_a_3600_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('kept_mid', 900.0, 1800.0)], 3600.0) == [word('kept_mid', 900.0, 1800.0)]


def test_point_at_start_geometry_on_a_3600_0_second_extent_is_owned_by_the_contract():
    assert bounded_window_words([word('point_at_start', 0.0, 0.0)], 3600.0) == [word('point_at_start', 0, 0.0)]


# --- Multi-word composites: ghosts and tails never disturb kept order ---------------


def test_ghost_tail_and_two_kept_words_on_a_four_second_extent():
    rows = [word('ghost', -3.0, -1.0), word('a', 0.5, 1.0), word('b', 1.5, 2.0), word('tail', 4.0, 4.2)]
    assert bounded_window_words(rows, 4.0) == [word('a', 0.5, 1.0), word('b', 1.5, 2.0)]


def test_ghosts_between_every_kept_word_on_a_thirty_second_extent():
    rows = [
        word('a', 1.0, 2.0),
        word('g1', -1.0, -0.5),
        word('b', 3.0, 4.0),
        word('g2', -2.0, -1.5),
        word('c', 5.0, 6.0),
        word('g3', -3.0, -2.5),
    ]
    assert bounded_window_words(rows, 30.0) == [
        word('a', 1.0, 2.0),
        word('b', 3.0, 4.0),
        word('c', 5.0, 6.0),
    ]


def test_tail_words_between_kept_words_on_a_sixty_second_extent():
    rows = [word('a', 1.0, 2.0), word('t1', 60.5, 61.0), word('b', 3.0, 4.0), word('t2', 70.0, 71.0)]
    assert bounded_window_words(rows, 60.0) == [word('a', 1.0, 2.0), word('b', 3.0, 4.0)]


def test_both_edges_of_an_hour_long_unit_drop_cleanly():
    rows = [word('ghost', -10.0, -5.0), word('kept', 100.0, 200.0), word('tail', 3600.0, 3601.0)]
    assert bounded_window_words(rows, 3600.0) == [word('kept', 100.0, 200.0)]


def test_sub_frame_extent_owns_only_midpoints_inside_it():
    rows = [word('ghost', -0.005, -0.001), word('straddle', -0.004, 0.05), word('kept', 0.005, 0.01)]
    assert bounded_window_words(rows, 0.02) == [word('kept', 0.005, 0.01)]


# --- Sample-precision edges -----------------------------------------------------------


def test_ghost_ending_one_sample_below_zero_drops():
    assert bounded_window_words([word('ghost', -2 / RATE, -1 / RATE)], 0.5) == []


def test_ghost_ending_exactly_one_sample_below_zero_drops_and_one_sample_straddler_clamps():
    assert bounded_window_words([word('straddle', -1 / RATE, 1 / RATE)], 0.5) == [word('straddle', 0.0, 1 / RATE)]


def test_kept_word_ending_exactly_at_the_extent_is_never_clamped_shorter():
    assert bounded_window_words([word('kept', 0.25, 0.5)], 0.5) == [word('kept', 0.25, 0.5)]


def test_kept_word_ending_one_sample_past_the_extent_clamps_to_it():
    assert bounded_window_words([word('kept', 0.25, 0.5 + 1 / RATE)], 0.5) == [word('kept', 0.25, 0.5)]


def test_point_word_exactly_at_the_end_is_a_tail_and_drops():
    assert bounded_window_words([word('point', 0.5, 0.5)], 0.5) == []


def test_point_word_at_the_start_is_owned():
    assert bounded_window_words([word('point', 0.0, 0.0)], 0.5) == [word('point', 0.0, 0.0)]


def test_zero_length_extent_drops_every_clock_including_the_origin_point():
    assert bounded_window_words([word('a', 0.0, 0.0)], 0.0) == []


def test_zero_length_extent_still_drops_ghosts_without_a_raise():
    assert bounded_window_words([word('ghost', -1.0, -0.5)], 0.0) == []


# --- Malformed classes stay closed at every extent ---------------------------------------


def test_reversed_clocks_raise_on_the_sub_frame_extent():
    with pytest.raises(BatchValidationError, match='word_clock'):
        bounded_window_words([word('bad', 0.01, 0.005)], 0.02)


def test_reversed_clocks_raise_on_the_hour_extent():
    with pytest.raises(BatchValidationError, match='word_clock'):
        bounded_window_words([word('bad', 2000.0, 1000.0)], 3600.0)


def test_nan_clocks_raise_on_the_minute_extent():
    with pytest.raises(BatchValidationError, match='word_clock'):
        bounded_window_words([word('bad', float('nan'), 10.0)], 60.0)


def test_infinite_end_raises_on_the_quarter_second_extent():
    with pytest.raises(BatchValidationError, match='word_clock'):
        bounded_window_words([word('bad', 0.1, float('inf'))], 0.25)


def test_unparseable_shape_raises_on_the_two_second_extent():
    with pytest.raises(BatchValidationError, match='word_shape'):
        bounded_window_words([{'word': 'bad', 'timestamp': [0.1, 0.2, 0.3]}], 2.0)


def test_in_window_blank_raises_on_the_eight_second_extent():
    with pytest.raises(BatchValidationError, match='word_sequence'):
        bounded_window_words([word('  ', 1.0, 2.0)], 8.0)


def test_ghost_sibling_does_not_mask_an_in_window_raise():
    with pytest.raises(BatchValidationError, match='word_clock'):
        bounded_window_words([word('ghost', -9.0, -8.0), word('bad', 3.0, 2.0)], 4.0)


def test_zero_length_extent_still_raises_for_in_domain_malformed_clocks():
    with pytest.raises(BatchValidationError, match='word_clock'):
        bounded_window_words([word('bad', 0.3, 0.2)], 0.0)


# --- Cross-lane parity on identical geometry ----------------------------------------------


def recovery_words(raw_rows, duration=0.5):
    words, _language = validate_response((raw_rows, 'en'), duration, SPANS, multilingual=False)
    return words


def recovery_mapped(raw_rows):
    return [{'text': row['text'], 'word': row['text'], 'timestamp': row['timestamp']} for row in raw_rows]


def test_recovery_lane_parity_matrix_case():
    raw_rows = [raw('ghost', -3.0, -1.0), raw('straddle', -0.1, 0.3), raw('kept', 0.2, 0.4), raw('tail', 0.5, 0.6)]
    words = recovery_words(raw_rows)
    assert words == bounded_window_words(recovery_mapped(raw_rows), 0.5)


def test_recovery_lane_parity_on_a_minute_extent():
    raw_rows = [raw('ghost', -30.0, -20.0), raw('kept', 10.0, 20.0), raw('tail', 60.0, 60.5)]
    words = recovery_words(raw_rows, duration=60.0)
    assert words == bounded_window_words(recovery_mapped(raw_rows), 60.0)


def test_recovery_lane_parity_on_an_eight_second_extent():
    raw_rows = [raw('ghost', -3.0, -1.0), raw('kept', 2.0, 3.0), raw('tail', 8.0, 8.2)]
    words = recovery_words(raw_rows, duration=8.0)
    assert words == bounded_window_words(recovery_mapped(raw_rows), 8.0)


def test_recovery_lane_through_at_stage_classifies_outside_only_as_empty():
    with pytest.raises(RecoveryFailure) as raised:
        at_stage(
            'response_validation',
            'invalid_response',
            lambda: validate_response(([raw('ghost', -3.0, -1.0)], 'en'), 0.5, SPANS, multilingual=False),
        )
    assert raised.value.reason == 'empty_asr'


def test_recovery_lane_through_at_stage_classifies_malformed_as_invalid():
    with pytest.raises(RecoveryFailure) as raised:
        at_stage(
            'response_validation',
            'invalid_response',
            lambda: validate_response(([raw('bad', 0.3, 0.2)], 'en'), 0.5, SPANS, multilingual=False),
        )
    assert raised.value.reason == 'invalid_response'


def test_shared_function_never_returns_clocks_past_the_strict_tolerance():
    from utils.batch_pipeline.word_validation import validate_words

    for rows, duration in (
        ([word('kept', 0.1, 0.55)], 0.5),
        ([word('straddle', -0.2, 0.6)], 0.5),
        ([word('kept', 10.0, 10.2)], 10.0),
    ):
        assert validate_words(bounded_window_words(rows, duration), duration) == bounded_window_words(rows, duration)


def test_geometry_matrix_stays_idempotent_per_extent():
    for rows in ([word('ghost', -3.0, -1.0), word('kept', 0.1, 0.3)], [word('kept', 0.25, 0.5 + 1 / RATE)]):
        once = bounded_window_words(rows, 0.5)
        assert bounded_window_words(once, 0.5) == once


def test_full_composite_on_an_eight_second_extent():
    rows = [
        word('ghost', -3.0, -1.0),
        word('straddle', -0.1, 1.0),
        word('point', 0.0, 0.0),
        word('kept', 2.0, 3.0),
        word('tail', 8.0, 8.1),
    ]
    assert bounded_window_words(rows, 8.0) == [
        word('straddle', 0.0, 1.0),
        word('point', 0.0, 0.0),
        word('kept', 2.0, 3.0),
    ]


def test_shared_function_output_passes_the_strict_validator_at_the_hour_extent():
    from utils.batch_pipeline.word_validation import validate_words

    rows = [word('ghost', -10.0, -5.0), word('kept', 100.0, 200.0)]
    kept = bounded_window_words(rows, 3600.0)
    assert validate_words(kept, 3600.0) == kept
