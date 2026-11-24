"""Synthetic capture coverage proof: holes refuse, identical overlaps count once."""

from datetime import datetime, timedelta, timezone

import pytest

from utils.batch_pipeline.no_speech_coverage import (
    CoverageIncomplete,
    RATE,
    capture_bounds,
    covered_pcm,
    source_start,
)

START = datetime(2026, 11, 1, tzinfo=timezone.utc)
ORIGIN = START.timestamp()
ROW = {'started_at': START, 'finished_at': START + timedelta(seconds=8)}
PCM = b'\x01\x00' * (8 * RATE)


def test_full_coverage_accepts_out_of_order_objects():
    assert covered_pcm(ROW, [(ORIGIN + 4, PCM[4 * RATE * 2 :]), (ORIGIN, PCM[: 4 * RATE * 2])], 7200) == PCM


def test_overlapping_and_contained_sources_count_each_frame_once():
    sources = [(ORIGIN, PCM[: 6 * RATE * 2]), (ORIGIN + 2, PCM[2 * RATE * 2 :]), (ORIGIN + 3, PCM[: 2 * RATE * 2])]
    assert covered_pcm(ROW, sources, 7200) == PCM


def test_conflicting_overlap_refuses_even_with_complete_union():
    with pytest.raises(CoverageIncomplete):
        covered_pcm(ROW, [(ORIGIN, PCM), (ORIGIN + 2, b'\x02\x00' * RATE)], 7200)


@pytest.mark.parametrize('left,right', [(0, 3), (3, 8), (0, 7.9)])
def test_boundary_or_interior_missing_audio_refuses(left, right):
    sources = [(ORIGIN + left, PCM[: round((right - left) * RATE) * 2])]
    if (left, right) == (0, 3):
        sources.append((ORIGIN + 4, PCM[: 4 * RATE * 2]))
    with pytest.raises(CoverageIncomplete):
        covered_pcm(ROW, sources, 7200)


def test_missing_frame_tolerance_is_cumulative_across_boundaries_and_gaps():
    # Three individually small 10 ms holes exceed the total 20 ms allowance.
    sources = [(ORIGIN + 0.01, PCM[: 3 * RATE * 2]), (ORIGIN + 3.02, PCM[: round(4.97 * RATE) * 2])]
    with pytest.raises(CoverageIncomplete):
        covered_pcm(ROW, sources, 7200)
    # A single 10 ms timestamp-rounding hole is explicitly tolerated.
    result = covered_pcm(ROW, [(ORIGIN + 0.01, PCM[: round(7.99 * RATE) * 2])], 7200)
    assert len(result) == len(PCM)
    assert result[: 160 * 2] == b'\0\0' * 160


@pytest.mark.parametrize(
    'change', [{}, {'finished_at': START}, {'started_at': None}, {'started_at': START.replace(tzinfo=None)}]
)
def test_missing_invalid_or_naive_capture_interval_refuses(change):
    row = {} if not change else {**ROW, **change}
    with pytest.raises(CoverageIncomplete):
        capture_bounds(row, 7200)


@pytest.mark.parametrize(
    'change',
    [
        {'capture_start': None},
        {'capture_start': 'nan'},
        {'capture_end': None},
        {'capture_end': ORIGIN + 9},
        {'gap_count': None},
        {'gap_count': 'unknown'},
        {'gap_count': 1},
    ],
)
def test_unproven_object_timing_or_internal_gaps_refuse(change):
    ref = {
        'path': 'raw-live/owner/capture/object.flac',
        'metadata': {'capture_start': str(ORIGIN), 'capture_end': str(ORIGIN + 8), 'gap_count': '0', **change},
    }
    with pytest.raises(CoverageIncomplete):
        source_start(ref, PCM)


def test_numeric_string_metadata_and_canonical_filename_timing():
    ref = {
        'path': f'raw-live/owner/capture/audio_omi_pcm16_16000_1_fs160_{ORIGIN}.bin',
        'metadata': {'capture_end': str(ORIGIN + 8), 'gap_count': '0'},
    }
    assert source_start(ref, PCM) == ORIGIN
    ref['metadata']['capture_start'] = str(ORIGIN)
    assert source_start(ref, PCM) == ORIGIN
