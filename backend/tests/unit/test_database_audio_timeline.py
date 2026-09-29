"""Hermetic unit tests for backend/database/audio_timeline.py."""

from __future__ import annotations

import os
import sys
from typing import Any, Mapping

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from database.audio_timeline import (
    chunk_span,
    chunk_span_bounds,
    group_chunks_by_coverage,
    parse_span_blob_metadata,
    span_blob_metadata,
    span_valid,
)


class _StubMapping(Mapping[str, Any]):
    """Custom mapping double for duck-type coverage."""

    def __init__(self, data: dict[str, Any]):
        self._data = data

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)


class _AttrDouble:
    """Attribute-style double without mapping inheritance."""

    def __init__(self, **kwargs: Any):
        for k, v in kwargs.items():
            setattr(self, k, v)


# ==========================================
# 1. Tests for chunk_span
# ==========================================


def test_chunk_span_valid():
    chunk = {"span": {"start": 0.0, "samples": 16000, "sample_rate": 16000}}
    assert chunk_span(chunk) == {"start": 0.0, "samples": 16000, "sample_rate": 16000}


def test_chunk_span_coercion():
    chunk = {"span": {"start": "1.25", "samples": "8000", "sample_rate": "16000"}}
    assert chunk_span(chunk) == {"start": 1.25, "samples": 8000, "sample_rate": 16000}


def test_chunk_span_custom_mapping():
    inner = _StubMapping({"start": 2.0, "samples": 32000, "sample_rate": 16000})
    chunk = _StubMapping({"span": inner})
    assert chunk_span(chunk) == {"start": 2.0, "samples": 32000, "sample_rate": 16000}


def test_chunk_span_rejects_bools():
    # bool is a subclass of int in Python; must not coerce to 0/1
    assert chunk_span({"span": {"start": True, "samples": 16000, "sample_rate": 16000}}) is None
    assert chunk_span({"span": {"start": 0.0, "samples": True, "sample_rate": 16000}}) is None
    assert chunk_span({"span": {"start": 0.0, "samples": 16000, "sample_rate": True}}) is None
    assert chunk_span({"span": {"start": False, "samples": False, "sample_rate": False}}) is None


def test_chunk_span_rejects_non_finite_and_negative():
    assert chunk_span({"span": {"start": float("nan"), "samples": 16000, "sample_rate": 16000}}) is None
    assert chunk_span({"span": {"start": float("inf"), "samples": 16000, "sample_rate": 16000}}) is None
    assert chunk_span({"span": {"start": float("-inf"), "samples": 16000, "sample_rate": 16000}}) is None
    assert chunk_span({"span": {"start": -0.5, "samples": 16000, "sample_rate": 16000}}) is None


def test_chunk_span_rejects_zero_and_negative_samples_or_rate():
    assert chunk_span({"span": {"start": 0.0, "samples": 0, "sample_rate": 16000}}) is None
    assert chunk_span({"span": {"start": 0.0, "samples": -100, "sample_rate": 16000}}) is None
    assert chunk_span({"span": {"start": 0.0, "samples": 16000, "sample_rate": 0}}) is None
    assert chunk_span({"span": {"start": 0.0, "samples": 16000, "sample_rate": -16000}}) is None


def test_chunk_span_rejects_malformed_inputs():
    assert chunk_span(None) is None
    assert chunk_span("invalid") is None
    assert chunk_span(123) is None
    assert chunk_span([]) is None
    assert chunk_span({}) is None
    assert chunk_span({"span": None}) is None
    assert chunk_span({"span": "not_a_dict"}) is None
    assert chunk_span({"span": []}) is None
    assert chunk_span({"span": {"start": "not_a_number", "samples": 100, "sample_rate": 16000}}) is None
    assert chunk_span({"span": {"samples": 100, "sample_rate": 16000}}) is None  # missing start


# ==========================================
# 2. Tests for span_blob_metadata
# ==========================================


def test_span_blob_metadata_valid():
    span = {"start": 1.5, "samples": 32000, "sample_rate": 16000}
    meta = span_blob_metadata(span)
    assert meta == {
        "v2_start": "1.5",
        "v2_samples": "32000",
        "v2_sample_rate": "16000",
    }


def test_span_blob_metadata_rejects_invalid_types():
    with pytest.raises(TypeError):
        span_blob_metadata(None)
    with pytest.raises(TypeError):
        span_blob_metadata("not_a_mapping")
    with pytest.raises(TypeError):
        span_blob_metadata([1, 2, 3])


def test_span_blob_metadata_rejects_missing_keys():
    with pytest.raises(ValueError):
        span_blob_metadata({"samples": 1000, "sample_rate": 16000})


def test_span_blob_metadata_rejects_bools():
    with pytest.raises(ValueError):
        span_blob_metadata({"start": True, "samples": 16000, "sample_rate": 16000})
    with pytest.raises(ValueError):
        span_blob_metadata({"start": 0.0, "samples": True, "sample_rate": 16000})


def test_span_blob_metadata_rejects_non_finite_or_negative():
    with pytest.raises(ValueError):
        span_blob_metadata({"start": float("nan"), "samples": 16000, "sample_rate": 16000})
    with pytest.raises(ValueError):
        span_blob_metadata({"start": -1.0, "samples": 16000, "sample_rate": 16000})
    with pytest.raises(ValueError):
        span_blob_metadata({"start": 0.0, "samples": 0, "sample_rate": 16000})


# ==========================================
# 3. Tests for parse_span_blob_metadata
# ==========================================


def test_parse_span_blob_metadata_valid():
    meta = {"v2_start": "0.5", "v2_samples": "16000", "v2_sample_rate": "16000"}
    assert parse_span_blob_metadata(meta) == {"start": 0.5, "samples": 16000, "sample_rate": 16000}


def test_parse_span_blob_metadata_roundtrip():
    original = {"start": 2.125, "samples": 24000, "sample_rate": 16000}
    meta = span_blob_metadata(original)
    rehydrated = parse_span_blob_metadata(meta)
    assert rehydrated == original


def test_parse_span_blob_metadata_fail_closed_on_non_mapping():
    # Only real mapping is accepted; attribute doubles must fail closed
    assert parse_span_blob_metadata(None) is None
    assert parse_span_blob_metadata("v2_start=0.5") is None
    assert parse_span_blob_metadata(_AttrDouble(v2_start="0.5", v2_samples="100", v2_sample_rate="16000")) is None


def test_parse_span_blob_metadata_rejects_bools_and_bad_values():
    assert parse_span_blob_metadata({"v2_start": True, "v2_samples": "16000", "v2_sample_rate": "16000"}) is None
    assert parse_span_blob_metadata({"v2_start": "0.0", "v2_samples": True, "v2_sample_rate": "16000"}) is None
    assert parse_span_blob_metadata({"v2_start": "nan", "v2_samples": "16000", "v2_sample_rate": "16000"}) is None
    assert parse_span_blob_metadata({"v2_start": "-1.0", "v2_samples": "16000", "v2_sample_rate": "16000"}) is None
    assert parse_span_blob_metadata({"v2_start": "0.0", "v2_samples": "0", "v2_sample_rate": "16000"}) is None
    assert parse_span_blob_metadata({"v2_start": "0.0", "v2_samples": "-100", "v2_sample_rate": "16000"}) is None
    assert parse_span_blob_metadata({"v2_start": "0.0", "v2_samples": "16000", "v2_sample_rate": "invalid"}) is None
    assert parse_span_blob_metadata({}) is None


# ==========================================
# 4. Tests for span_valid
# ==========================================


def test_span_valid_boundaries():
    assert span_valid(0.0, 1.0) is True
    assert span_valid(10.5, 20.0) is True
    assert span_valid(1.0, 1.0) is False  # zero duration
    assert span_valid(2.0, 1.0) is False  # inverted
    assert span_valid(-1.0, 1.0) is False  # negative start
    assert span_valid(float("nan"), 1.0) is False
    assert span_valid(0.0, float("nan")) is False
    assert span_valid(0.0, float("inf")) is False


# ==========================================
# 5. Tests for chunk_span_bounds
# ==========================================


def test_chunk_span_bounds_shapes():
    assert chunk_span_bounds({"start": 0.0, "end": 2.0}) == (0.0, 2.0)
    assert chunk_span_bounds([0.0, 2.0]) == (0.0, 2.0)
    assert chunk_span_bounds((0.0, 2.0)) == (0.0, 2.0)
    assert chunk_span_bounds(_AttrDouble(start=0.0, end=2.0)) == (0.0, 2.0)


def test_chunk_span_bounds_invalids():
    assert chunk_span_bounds(None) is None
    assert chunk_span_bounds([]) is None
    assert chunk_span_bounds([1.0]) is None
    assert chunk_span_bounds([1.0, 2.0, 3.0]) is None
    assert chunk_span_bounds({"start": True, "end": 2.0}) is None
    assert chunk_span_bounds({"start": 0.0, "end": False}) is None
    assert chunk_span_bounds({"start": -1.0, "end": 2.0}) is None
    assert chunk_span_bounds({"start": 2.0, "end": 1.0}) is None


# ==========================================
# 6. Tests for group_chunks_by_coverage
# ==========================================


def test_group_chunks_by_coverage_empty():
    assert group_chunks_by_coverage([], gap_threshold=90.0) == []
    assert group_chunks_by_coverage(None, gap_threshold=90.0) == []  # type: ignore[arg-type]


def test_group_chunks_by_coverage_v2_contiguous():
    chunks = [
        {"timestamp": 100.0, "span": {"start": 0.0, "samples": 16000, "sample_rate": 16000}},
        {"timestamp": 101.0, "span": {"start": 1.0, "samples": 16000, "sample_rate": 16000}},
        {"timestamp": 102.0, "span": {"start": 2.0, "samples": 16000, "sample_rate": 16000}},
    ]
    groups = group_chunks_by_coverage(chunks, gap_threshold=90.0)
    assert len(groups) == 1
    assert len(groups[0]) == 3


def test_group_chunks_by_coverage_v2_split_on_gap():
    chunks = [
        {"timestamp": 100.0, "span": {"start": 0.0, "samples": 16000, "sample_rate": 16000}},
        {"timestamp": 101.0, "span": {"start": 1.0, "samples": 16000, "sample_rate": 16000}},
        # Gap of 0.5s between end 2.0 and next start 2.5
        {"timestamp": 105.0, "span": {"start": 2.5, "samples": 16000, "sample_rate": 16000}},
    ]
    groups = group_chunks_by_coverage(chunks, gap_threshold=90.0)
    assert len(groups) == 2
    assert len(groups[0]) == 2
    assert len(groups[1]) == 1


def test_group_chunks_by_coverage_v2_split_on_overlap():
    chunks = [
        {"timestamp": 100.0, "span": {"start": 0.0, "samples": 16000, "sample_rate": 16000}},
        # Overlap: previous end 1.0, this start 0.8
        {"timestamp": 101.0, "span": {"start": 0.8, "samples": 16000, "sample_rate": 16000}},
    ]
    groups = group_chunks_by_coverage(chunks, gap_threshold=90.0)
    assert len(groups) == 2


def test_group_chunks_by_coverage_legacy_fallback_gap_threshold():
    chunks = [
        {"timestamp": 10.0},
        {"timestamp": 20.0},
        # Gap of 100s > gap_threshold 90s
        {"timestamp": 120.0},
    ]
    groups = group_chunks_by_coverage(chunks, gap_threshold=90.0)
    assert len(groups) == 2
    assert len(groups[0]) == 2
    assert len(groups[1]) == 1


def test_group_chunks_by_coverage_resilience_missing_timestamp():
    # If chunks are missing timestamp, must not crash with KeyError
    chunks = [
        {"id": "chunk_1"},
        {"id": "chunk_2", "timestamp": 10.0},
        {"id": "chunk_3"},
    ]
    groups = group_chunks_by_coverage(chunks, gap_threshold=90.0)
    # Should safely partition instead of crashing
    assert len(groups) == 3


def test_group_chunks_by_coverage_resilience_corrupted_timestamps():
    # String timestamps, booleans, NaNs, None
    chunks = [
        {"timestamp": "not_a_number"},
        {"timestamp": True},
        {"timestamp": float("nan")},
        {"timestamp": None},
        {"timestamp": 50.0},
    ]
    groups = group_chunks_by_coverage(chunks, gap_threshold=90.0)
    assert len(groups) == 5


def test_group_chunks_by_coverage_resilience_non_dict_elements():
    # Non-dict chunk elements must not crash with AttributeError
    chunks = [
        None,
        {"timestamp": 1.0},
        "corrupted_chunk_string",
        {"timestamp": 2.0},
    ]
    groups = group_chunks_by_coverage(chunks, gap_threshold=90.0)
    assert len(groups) >= 3


def test_group_chunks_by_coverage_tolerance_customization():
    chunks = [
        {"timestamp": 100.0, "span": {"start": 0.0, "samples": 16000, "sample_rate": 16000}},
        # Diff is 0.005s (5ms > default tolerance 1ms, but < 10ms)
        {"timestamp": 101.0, "span": {"start": 1.005, "samples": 16000, "sample_rate": 16000}},
    ]
    # Default tolerance (1ms): splits
    assert len(group_chunks_by_coverage(chunks, gap_threshold=90.0)) == 2
    # Custom tolerance (10ms): stays in one group
    assert len(group_chunks_by_coverage(chunks, gap_threshold=90.0, tolerance=0.010)) == 1
