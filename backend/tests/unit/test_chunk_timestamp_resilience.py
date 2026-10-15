"""#19726 — group_chunks_by_coverage survives chunks with missing/bad timestamps.

Before the fix, a chunk lacking 'timestamp' (or a non-numeric one) raised
KeyError/TypeError mid-grouping. Malformed timestamps now fall back to merging.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from database.audio_timeline import group_chunks_by_coverage


def _chunk(ts, **extra):
    return {'timestamp': ts, **extra}


def test_missing_timestamp_merges_instead_of_keyerror():
    chunks = [_chunk(0.0), {'foo': 'no-ts'}, _chunk(1.0)]
    groups = group_chunks_by_coverage(chunks, gap_threshold=30.0)
    assert len(groups) == 1  # the timestamp-less chunk merges, never crashes


def test_non_numeric_timestamp_merges_instead_of_typeerror():
    chunks = [_chunk(0.0), {'timestamp': 'not-a-number'}, _chunk(1.0)]
    assert len(group_chunks_by_coverage(chunks, gap_threshold=30.0)) == 1


def test_none_timestamp_merges():
    chunks = [_chunk(0.0), {'timestamp': None}, _chunk(1.0)]
    assert len(group_chunks_by_coverage(chunks, gap_threshold=30.0)) == 1


def test_real_gap_still_splits():
    chunks = [_chunk(0.0), _chunk(100.0), _chunk(101.0)]
    groups = group_chunks_by_coverage(chunks, gap_threshold=30.0)
    assert len(groups) == 2
    assert [len(g) for g in groups] == [1, 2]


def test_mixed_malformed_mid_gap_chain():
    # malformed chunk between two good ones — merges with the first group,
    # and the later real gap still splits.
    chunks = [_chunk(0.0), {}, _chunk(5.0), _chunk(500.0)]
    groups = group_chunks_by_coverage(chunks, gap_threshold=30.0)
    assert len(groups) == 2
    assert len(groups[0]) == 3 and len(groups[1]) == 1
