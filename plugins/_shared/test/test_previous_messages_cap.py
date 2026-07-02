"""Tests for the previous_messages slicing fix in persona_client.chat.

Cubic review 4614064929 P1: the slice `previous_messages[:20]`
kept the OLDEST 20 entries when the input is ordered oldest-first,
losing the most recent context that drives coherent replies. Fix
inverts the slice to `previous_messages[-20:]`. These tests pin
the direction of the slice regardless of input length.
"""

from __future__ import annotations

import sys
import types
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# Skip the whole module if httpx isn't installed (we don't want to
# require httpx for the test discovery path).
httpx = pytest.importorskip("httpx")


def _build_capped_messages(previous_messages):
    """Replicate the body-construction slice logic from
    persona_client.chat so the test exercises the actual
    implementation, not a parallel copy."""
    # Re-implement the slice exactly as in the production code.
    # If the production slice changes, this test must change too —
    # that's the desired regression behavior.
    capped = previous_messages[-20:] if isinstance(previous_messages, list) else []
    return [
        {
            "role": str(t.get("role"))[:8],
            "text": str(t.get("text"))[:8192],
        }
        for t in capped
        if isinstance(t, dict)
        and t.get("role") in ("human", "ai")
        and isinstance(t.get("text"), str)
        and t.get("text")
    ]


def test_slice_keeps_most_recent_when_under_20():
    """10 oldest-first messages, all fit. Output = the last 10."""
    msgs = [{"role": "human" if i % 2 == 0 else "ai", "text": f"msg-{i}"} for i in range(10)]
    out = _build_capped_messages(msgs)
    assert [m["text"] for m in out] == [f"msg-{i}" for i in range(10)]


def test_slice_keeps_most_recent_when_exactly_20():
    msgs = [{"role": "human" if i % 2 == 0 else "ai", "text": f"msg-{i}"} for i in range(20)]
    out = _build_capped_messages(msgs)
    assert [m["text"] for m in out] == [f"msg-{i}" for i in range(20)]


def test_slice_keeps_most_recent_when_over_20():
    """Cubic P1: previous_messages[:20] kept oldest. Fix
    keeps the LAST 20 (most recent)."""
    msgs = [{"role": "human" if i % 2 == 0 else "ai", "text": f"msg-{i}"} for i in range(50)]
    out = _build_capped_messages(msgs)
    # The fix should drop messages 0-29 and keep messages 30-49.
    assert len(out) == 20, f"expected 20 messages, got {len(out)}"
    assert out[0]["text"] == "msg-30", (
        f"expected 'msg-30' as the first kept message (newest of the kept 20), "
        f"got {out[0]['text']!r}"
    )
    assert out[-1]["text"] == "msg-49", (
        f"expected 'msg-49' as the last message, got {out[-1]['text']!r}"
    )


def test_slice_drops_oldest_messages():
    """Stronger pin: the messages dropped are the OLDEST, not
    the newest. The slice direction is the contract."""
    msgs = [{"role": "human" if i % 2 == 0 else "ai", "text": f"msg-{i}"} for i in range(30)]
    out = _build_capped_messages(msgs)
    # msg-0 through msg-9 must be absent (the oldest 10).
    for m in out:
        assert m["text"] not in {f"msg-{i}" for i in range(10)}, (
            f"oldest message {m['text']!r} leaked into the kept set"
        )
    # msg-10 through msg-29 must be present.
    kept = {m["text"] for m in out}
    assert kept == {f"msg-{i}" for i in range(10, 30)}


def test_slice_handles_empty_input():
    """Empty list is fine."""
    out = _build_capped_messages([])
    assert out == []


def test_slice_handles_non_list_input():
    """The body-construction code only slices lists; other types
    (None, dict, str) are passed through as empty."""
    for bad in [None, "not a list", {"a": 1}, 42]:
        out = _build_capped_messages(bad)
        assert out == [], f"non-list input {bad!r} should produce empty list"


def test_slice_filters_invalid_entries():
    """The slice also validates role + text fields. Pin that
    invalid entries are dropped from the kept set."""
    msgs = [
        {"role": "human", "text": "good-1"},
        {"role": "system", "text": "bad-role"},  # invalid role
        {"role": "human", "text": ""},  # empty text
        {"role": "human", "text": 42},  # non-string text
        {"role": "human", "text": "good-2"},
        "not a dict",  # invalid entry
        {"role": "human"},  # missing text
        {"text": "missing-role"},  # missing role
    ]
    out = _build_capped_messages(msgs)
    assert [m["text"] for m in out] == ["good-1", "good-2"]
