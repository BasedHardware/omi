"""Regression coverage for issue #19047.

``chunk_span_bounds`` rejected Pydantic v2 ``BaseModel`` span carriers because
they do not inherit from ``collections.abc.Mapping`` — while the write path
(``database/conversations.py``) stores ``chunk_spans`` as ``ChunkSpan``
models. The read path must accept what the write path stores.

The fix is duck-typed (``hasattr``) so ``database/audio_timeline.py`` stays
import-free per its module contract; these tests prove both the real
``ChunkSpan`` model and a stdlib-only attribute stub are accepted, and that
fail-closed behavior on malformed values is unchanged.
"""

from __future__ import annotations

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from database.audio_timeline import chunk_span_bounds
from models.audio_file import ChunkSpan


class _AttrSpan:
    """Stdlib-only attribute-style span carrier (no pydantic)."""

    def __init__(self, start, end):
        self.start = start
        self.end = end


def test_accepts_pydantic_chunk_span():
    span = ChunkSpan(start=1.5, end=3.25)
    assert chunk_span_bounds(span) == (1.5, 3.25)


def test_accepts_attribute_stub():
    assert chunk_span_bounds(_AttrSpan(0.0, 2.0)) == (0.0, 2.0)


def test_accepts_mapping_and_pair_unchanged():
    assert chunk_span_bounds({"start": 1.0, "end": 2.0}) == (1.0, 2.0)
    assert chunk_span_bounds([1.0, 2.0]) == (1.0, 2.0)
    assert chunk_span_bounds((1.0, 2.0)) == (1.0, 2.0)


def test_fail_closed_on_bad_values():
    # bool start/end still rejected (not coerced to 1.0/0.0)
    assert chunk_span_bounds(_AttrSpan(True, 2.0)) is None
    assert chunk_span_bounds(_AttrSpan(1.0, False)) is None
    # non-numeric / non-finite / inverted still rejected
    assert chunk_span_bounds(_AttrSpan("nope", 2.0)) is None
    assert chunk_span_bounds(_AttrSpan(float("inf"), 2.0)) is None
    assert chunk_span_bounds(_AttrSpan(3.0, 2.0)) is None
    assert chunk_span_bounds(_AttrSpan(2.0, 2.0)) is None
    # missing attributes / wrong shapes still rejected
    assert chunk_span_bounds(object()) is None
    assert chunk_span_bounds(None) is None
    assert chunk_span_bounds([1.0]) is None
    assert chunk_span_bounds("start,end") is None


def test_round_trip_write_path_shape():
    """The exact shape the write path stores must survive the read path."""
    spans = [ChunkSpan(start=round(s, 3), end=round(e, 3)) for s, e in [(0.0, 1.5), (1.5, 3.0)]]
    bounds = [chunk_span_bounds(item) for item in spans]
    assert bounds == [(0.0, 1.5), (1.5, 3.0)]
    assert all(b is not None for b in bounds)
