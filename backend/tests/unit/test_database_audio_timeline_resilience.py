"""Hermetic unit tests for input validation, boundary guards, and error resilience
in backend/database/audio_timeline.py.
"""

import math
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


# ---------------------------------------------------------------------------
# chunk_span validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_chunk", [None, "not-a-mapping", 123, []])
def test_chunk_span_rejects_non_mapping(invalid_chunk):
    assert chunk_span(invalid_chunk) is None  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "bad_span",
    [
        {"start": float("nan"), "samples": 16000, "sample_rate": 16000},
        {"start": float("inf"), "samples": 16000, "sample_rate": 16000},
        {"start": 0.0, "samples": 0, "sample_rate": 16000},
        {"start": 0.0, "samples": -10, "sample_rate": 16000},
        {"start": 0.0, "samples": 16000, "sample_rate": 0},
        {"start": 0.0, "samples": 16000, "sample_rate": -16000},
        {"start": "not-a-number", "samples": 16000, "sample_rate": 16000},
    ],
)
def test_chunk_span_rejects_malformed_values(bad_span):
    assert chunk_span({"span": bad_span}) is None


def test_chunk_span_valid():
    res = chunk_span({"span": {"start": "1.5", "samples": "16000", "sample_rate": "16000"}})
    assert res == {"start": 1.5, "samples": 16000, "sample_rate": 16000}


# ---------------------------------------------------------------------------
# span_blob_metadata validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_span", [None, "not-a-mapping", 123])
def test_span_blob_metadata_rejects_non_mapping(invalid_span):
    with pytest.raises(ValueError, match="span must be a mapping"):
        span_blob_metadata(invalid_span)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "bad_span",
    [
        {"start": float("nan"), "samples": 16000, "sample_rate": 16000},
        {"start": 0.0, "samples": 0, "sample_rate": 16000},
        {"start": 0.0, "samples": 16000, "sample_rate": 0},
        {"samples": 16000, "sample_rate": 16000},
    ],
)
def test_span_blob_metadata_rejects_invalid_values(bad_span):
    with pytest.raises(ValueError):
        span_blob_metadata(bad_span)


def test_span_blob_metadata_valid():
    res = span_blob_metadata({"start": 2.5, "samples": 32000, "sample_rate": 16000})
    assert res == {"v2_start": "2.5", "v2_samples": "32000", "v2_sample_rate": "16000"}


# ---------------------------------------------------------------------------
# parse_span_blob_metadata validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_metadata", [None, "string", 123, []])
def test_parse_span_blob_metadata_rejects_non_dict(invalid_metadata):
    assert parse_span_blob_metadata(invalid_metadata) is None  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "bad_metadata",
    [
        {"v2_start": "nan", "v2_samples": "16000", "v2_sample_rate": "16000"},
        {"v2_start": "0.0", "v2_samples": "0", "v2_sample_rate": "16000"},
        {"v2_start": "0.0", "v2_samples": "16000", "v2_sample_rate": "-1"},
        {"v2_start": "0.0"},
    ],
)
def test_parse_span_blob_metadata_rejects_bad_values(bad_metadata):
    assert parse_span_blob_metadata(bad_metadata) is None


def test_parse_span_blob_metadata_valid():
    res = parse_span_blob_metadata({"v2_start": "0.5", "v2_samples": "8000", "v2_sample_rate": "16000"})
    assert res == {"start": 0.5, "samples": 8000, "sample_rate": 16000}


# ---------------------------------------------------------------------------
# chunk_span_bounds & span_valid
# ---------------------------------------------------------------------------


def test_span_valid_rules():
    assert span_valid(0.0, 1.0) is True
    assert span_valid(1.0, 1.0) is False
    assert span_valid(2.0, 1.0) is False
    assert span_valid(float("nan"), 1.0) is False
    assert span_valid(0.0, float("inf")) is False


@pytest.mark.parametrize(
    "bad_item",
    [
        None,
        {"start": True, "end": False},
        {"start": 1.0},  # missing end
        [1.0],  # wrong length
        [1.0, 2.0, 3.0],  # wrong length
        {"start": "not-num", "end": 2.0},
        {"start": 5.0, "end": 2.0},  # inverted
    ],
)
def test_chunk_span_bounds_rejects_bad_items(bad_item):
    assert chunk_span_bounds(bad_item) is None


def test_chunk_span_bounds_accepts_formats():
    assert chunk_span_bounds({"start": 1.0, "end": 2.5}) == (1.0, 2.5)
    assert chunk_span_bounds([1.0, 2.5]) == (1.0, 2.5)
    assert chunk_span_bounds((1.0, 2.5)) == (1.0, 2.5)


# ---------------------------------------------------------------------------
# group_chunks_by_coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("invalid_chunks", [None, "not-a-list", 123, {}])
def test_group_chunks_by_coverage_rejects_non_list(invalid_chunks):
    assert group_chunks_by_coverage(invalid_chunks, gap_threshold=1.0) == []  # type: ignore[arg-type]


def test_group_chunks_by_coverage_empty_list():
    assert group_chunks_by_coverage([], gap_threshold=1.0) == []


def test_group_chunks_by_coverage_handles_malformed_items():
    chunks = [
        None,
        "not-a-dict",
        {"timestamp": 10.0},
        {"missing_timestamp": 20.0},
        {"timestamp": 12.0},
    ]
    # Should not crash on malformed items
    groups = group_chunks_by_coverage(chunks, gap_threshold=5.0)  # type: ignore[arg-type]
    assert len(groups) >= 1


def test_group_chunks_by_coverage_bounds_thresholds():
    chunks = [{"timestamp": 10.0}, {"timestamp": 20.0}]
    # Negative gap_threshold is clamped to 0.0
    groups = group_chunks_by_coverage(chunks, gap_threshold=-5.0, tolerance=-1.0)
    assert len(groups) == 2  # Separated because 20 - 10 > 0.0


def test_group_chunks_by_coverage_legacy_grouping():
    chunks = [
        {"timestamp": 10.0},
        {"timestamp": 12.0},  # gap = 2.0 <= 5.0 -> same group
        {"timestamp": 25.0},  # gap = 13.0 > 5.0 -> new group
    ]
    groups = group_chunks_by_coverage(chunks, gap_threshold=5.0)
    assert len(groups) == 2
    assert len(groups[0]) == 2
    assert len(groups[1]) == 1
