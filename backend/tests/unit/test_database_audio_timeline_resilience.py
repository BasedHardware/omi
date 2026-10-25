"""Hermetic resilience unit tests for backend/database/audio_timeline.py.

Validates defensive boundaries for NaN/inf values, type assertions, metadata
constructors, and graceful splitting on corrupted chunk timestamps.
"""

from __future__ import annotations

import math
from typing import Dict, List, Mapping

import pytest

from database.audio_timeline import (
    COVERAGE_TOLERANCE_SECONDS,
    chunk_span,
    chunk_span_bounds,
    group_chunks_by_coverage,
    parse_span_blob_metadata,
    span_blob_metadata,
    span_valid,
)


class TestChunkSpanResilience:
    @pytest.mark.parametrize(
        'bad_start',
        [float('nan'), float('inf'), float('-inf'), 'nan', 'inf', None, [], {}],
    )
    def test_chunk_span_rejects_non_finite_or_invalid_start(self, bad_start):
        chunk = {'span': {'start': bad_start, 'samples': 16000, 'sample_rate': 16000}}
        assert chunk_span(chunk) is None

    @pytest.mark.parametrize(
        'samples,rate',
        [
            (0, 16000),
            (-1, 16000),
            (-100, 16000),
            (16000, 0),
            (16000, -1),
            (0, 0),
            (-5, -5),
            ('bad', 16000),
            (16000, 'bad'),
        ],
    )
    def test_chunk_span_rejects_non_positive_or_invalid_samples_rate(self, samples, rate):
        chunk = {'span': {'start': 0.0, 'samples': samples, 'sample_rate': rate}}
        assert chunk_span(chunk) is None

    @pytest.mark.parametrize(
        'bad_chunk',
        [None, '', 123, 45.6, [], (), object(), {'span': None}, {'span': 'string'}, {'span': []}],
    )
    def test_chunk_span_rejects_non_mapping_chunk_or_span(self, bad_chunk):
        assert chunk_span(bad_chunk) is None

    def test_chunk_span_valid_mapping(self):
        valid = {'span': {'start': '12.5', 'samples': '8000', 'sample_rate': '16000'}}
        span = chunk_span(valid)
        assert span == {'start': 12.5, 'samples': 8000, 'sample_rate': 16000}


class TestSpanBlobMetadataResilience:
    @pytest.mark.parametrize(
        'bad_span',
        [None, '', 123, [], (), object()],
    )
    def test_span_blob_metadata_rejects_non_mapping(self, bad_span):
        with pytest.raises(ValueError, match='span must be a Mapping'):
            span_blob_metadata(bad_span)

    @pytest.mark.parametrize(
        'bad_fields',
        [
            {'start': 0.0, 'samples': 16000},  # missing sample_rate
            {'start': 0.0, 'sample_rate': 16000},  # missing samples
            {'samples': 16000, 'sample_rate': 16000},  # missing start
            {'start': 'abc', 'samples': 16000, 'sample_rate': 16000},
            {'start': 0.0, 'samples': 'abc', 'sample_rate': 16000},
            {'start': 0.0, 'samples': 16000, 'sample_rate': 'abc'},
        ],
    )
    def test_span_blob_metadata_raises_on_missing_or_corrupt_fields(self, bad_fields):
        with pytest.raises(ValueError, match='Invalid span fields'):
            span_blob_metadata(bad_fields)

    @pytest.mark.parametrize(
        'bad_values',
        [
            {'start': float('nan'), 'samples': 16000, 'sample_rate': 16000},
            {'start': float('inf'), 'samples': 16000, 'sample_rate': 16000},
            {'start': float('-inf'), 'samples': 16000, 'sample_rate': 16000},
            {'start': 0.0, 'samples': 0, 'sample_rate': 16000},
            {'start': 0.0, 'samples': -5, 'sample_rate': 16000},
            {'start': 0.0, 'samples': 16000, 'sample_rate': 0},
            {'start': 0.0, 'samples': 16000, 'sample_rate': -10},
        ],
    )
    def test_span_blob_metadata_raises_on_non_positive_or_infinite_values(self, bad_values):
        with pytest.raises(ValueError, match='Span values must be finite and positive'):
            span_blob_metadata(bad_values)

    def test_span_blob_metadata_valid(self):
        meta = span_blob_metadata({'start': 1.25, 'samples': 16000, 'sample_rate': 16000})
        assert meta == {
            'v2_start': '1.25',
            'v2_samples': '16000',
            'v2_sample_rate': '16000',
        }


class TestParseSpanBlobMetadataResilience:
    @pytest.mark.parametrize(
        'bad_meta',
        [None, '', 123, [], (), object()],
    )
    def test_parse_span_blob_metadata_rejects_non_mapping(self, bad_meta):
        assert parse_span_blob_metadata(bad_meta) is None

    @pytest.mark.parametrize(
        'corrupt_meta',
        [
            {'v2_start': 'nan', 'v2_samples': '16000', 'v2_sample_rate': '16000'},
            {'v2_start': 'inf', 'v2_samples': '16000', 'v2_sample_rate': '16000'},
            {'v2_start': '-inf', 'v2_samples': '16000', 'v2_sample_rate': '16000'},
            {'v2_start': '0.0', 'v2_samples': '0', 'v2_sample_rate': '16000'},
            {'v2_start': '0.0', 'v2_samples': '-10', 'v2_sample_rate': '16000'},
            {'v2_start': '0.0', 'v2_samples': '16000', 'v2_sample_rate': '0'},
            {'v2_start': '0.0', 'v2_samples': '16000', 'v2_sample_rate': '-5'},
            {'v2_start': 'invalid', 'v2_samples': '16000', 'v2_sample_rate': '16000'},
            {'v2_samples': '16000', 'v2_sample_rate': '16000'},
        ],
    )
    def test_parse_span_blob_metadata_rejects_corrupted_metadata(self, corrupt_meta):
        assert parse_span_blob_metadata(corrupt_meta) is None

    def test_parse_span_blob_metadata_valid(self):
        valid = {'v2_start': '4.5', 'v2_samples': '32000', 'v2_sample_rate': '16000'}
        span = parse_span_blob_metadata(valid)
        assert span == {'start': 4.5, 'samples': 32000, 'sample_rate': 16000}


class TestGroupChunksByCoverageResilience:
    @pytest.mark.parametrize('bad_chunks', [None, '', 123, {'a': 1}])
    def test_group_chunks_by_coverage_rejects_non_list(self, bad_chunks):
        assert group_chunks_by_coverage(bad_chunks, gap_threshold=1.0) == []

    def test_group_chunks_by_coverage_empty(self):
        assert group_chunks_by_coverage([], gap_threshold=1.0) == []

    @pytest.mark.parametrize(
        'bad_threshold',
        [float('nan'), float('inf'), float('-inf'), None, 'bad'],
    )
    def test_group_chunks_by_coverage_clamps_invalid_gap_threshold_to_zero(self, bad_threshold):
        chunks_with_gap = [
            {'timestamp': 100.0, 'span': {'start': 0.0, 'samples': 16000, 'sample_rate': 16000}},
            {'timestamp': 100.5, 'span': {'start': 1.0, 'samples': 16000, 'sample_rate': 16000}},
        ]
        # Any positive timestamp gap (0.5 > 0.0) splits into 2 groups, exactly matching gap_threshold=0.0
        assert group_chunks_by_coverage(chunks_with_gap, gap_threshold=bad_threshold) == group_chunks_by_coverage(
            chunks_with_gap, gap_threshold=0.0
        )
        assert len(group_chunks_by_coverage(chunks_with_gap, gap_threshold=bad_threshold)) == 2

        chunks_no_gap = [
            {'timestamp': 100.0, 'span': {'start': 0.0, 'samples': 16000, 'sample_rate': 16000}},
            {'timestamp': 100.0, 'span': {'start': 1.0, 'samples': 16000, 'sample_rate': 16000}},
        ]
        assert len(group_chunks_by_coverage(chunks_no_gap, gap_threshold=bad_threshold)) == 1

    @pytest.mark.parametrize(
        'bad_tolerance',
        [float('nan'), float('inf'), float('-inf'), None, 'bad'],
    )
    def test_group_chunks_by_coverage_clamps_invalid_tolerance_to_default(self, bad_tolerance):
        chunks = [
            {'timestamp': 100.0, 'span': {'start': 0.0, 'samples': 16000, 'sample_rate': 16000}},
            {'timestamp': 101.0, 'span': {'start': 1.0005, 'samples': 16000, 'sample_rate': 16000}},
        ]
        # Diff is 0.0005 <= COVERAGE_TOLERANCE_SECONDS (0.001), so contiguous
        groups = group_chunks_by_coverage(chunks, gap_threshold=5.0, tolerance=bad_tolerance)
        assert len(groups) == 1

    def test_group_chunks_by_coverage_splits_on_corrupt_legacy_timestamps(self):
        chunks = [
            {'timestamp': 100.0},
            {'timestamp': 'malformed_string'},
            {'timestamp': None},
            {},  # missing timestamp
            {'timestamp': 105.0},
        ]
        groups = group_chunks_by_coverage(chunks, gap_threshold=2.0)
        # Corrupted timestamps split groups safely instead of crashing KeyError/TypeError
        assert len(groups) == 5
        assert groups[0] == [{'timestamp': 100.0}]
        assert groups[1] == [{'timestamp': 'malformed_string'}]
        assert groups[2] == [{'timestamp': None}]
        assert groups[3] == [{}]
        assert groups[4] == [{'timestamp': 105.0}]

    def test_group_chunks_by_coverage_handles_non_mapping_elements_gracefully(self):
        chunks = [
            {'timestamp': 100.0},
            'not_a_dict',
            None,
            {'timestamp': 101.0},
        ]
        groups = group_chunks_by_coverage(chunks, gap_threshold=2.0)
        assert len(groups) == 4

    def test_group_chunks_by_coverage_span_with_nan_falls_back_to_legacy(self):
        chunks = [
            {'timestamp': 100.0, 'span': {'start': float('nan'), 'samples': 16000, 'sample_rate': 16000}},
            {'timestamp': 101.0, 'span': {'start': 1.0, 'samples': 16000, 'sample_rate': 16000}},
        ]
        # Span with NaN causes v2_listing to be False, falling back to legacy timestamp check
        groups = group_chunks_by_coverage(chunks, gap_threshold=2.0)
        assert len(groups) == 1  # diff 101.0 - 100.0 = 1.0 <= 2.0
