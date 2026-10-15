"""Regression test for the speaker-id collision fixed in #21201.

Before: ``reallocate`` was a single flag across the whole merge — one source
carrying a manual speaker assignment (or a manual/carried label) made it
False for EVERY source, so an untagged conversation's voices kept ids that
collided with the tagged conversation's. Two fixes together: (1) the
renumber is per-source — a manually-tagged conversation keeps its ids, an
untagged one still renumbers; (2) the allocator is hydrated with the tagged
sources' reserved ids first, so reallocated voices land above the tagged
range instead of renumbering onto the same id.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from utils.conversations.merge_conversations import _merge_transcript_segments


def _seg(speaker_id, text, start=0.0, end=1.0, label_source=None):
    s = {"speaker_id": speaker_id, "text": text, "start": start, "end": end, "is_user": False}
    if label_source:
        s["speaker_label_source"] = label_source
    return s


def _conv(cid, segments, manual=None):
    return {
        "id": cid,
        "transcript_segments": segments,
        "manual_speaker_assignments": manual or {},
        "started_at": None,
        "finished_at": None,
    }


def test_untagged_source_renumbers_above_the_tagged_voice():
    tagged = _conv("c1", [_seg(1, "alice says hi")], manual={"speakers": {"1": {"name": "Alice"}}})
    untagged = _conv("c2", [_seg(1, "bob says hey", start=10.0, end=11.0)])
    merged = _merge_transcript_segments([tagged, untagged])
    tagged_seg = next(s for s in merged if s["text"].startswith("alice"))
    untagged_seg = next(s for s in merged if s["text"].startswith("bob"))
    # the tagged voice keeps id 1; the untagged voice renumbers above it.
    assert tagged_seg["speaker_id"] == 1
    assert untagged_seg["speaker_id"] != 1


def test_all_untagged_sources_still_renumber():
    a = _conv("c1", [_seg(1, "first")])
    b = _conv("c2", [_seg(1, "second", start=5.0, end=6.0)])
    merged = _merge_transcript_segments([a, b])
    ids = {s["speaker_id"] for s in merged}
    assert len(ids) == 2, "two untagged voices sharing id 1 should renumber apart"


def test_all_tagged_sources_keep_their_ids():
    receipt = {"speakers": {"1": {"name": "A"}}}
    a = _conv("c1", [_seg(1, "alice", label_source="manual")], manual=receipt)
    b = _conv("c2", [_seg(1, "carol", start=5.0, end=6.0, label_source="manual")], manual=receipt)
    merged = _merge_transcript_segments([a, b])
    assert all(s["speaker_id"] == 1 for s in merged), "both tagged sources keep id 1"


def test_carried_label_counts_as_tagged():
    # a 'carried' label_source is a manual provenance — the source keeps its ids
    carried = _conv("c1", [_seg(1, "kept", label_source="carried")])
    untagged = _conv("c2", [_seg(1, "moved", start=5.0, end=6.0)])
    merged = _merge_transcript_segments([carried, untagged])
    kept = next(s for s in merged if s["text"] == "kept")
    moved = next(s for s in merged if s["text"] == "moved")
    assert kept["speaker_id"] == 1
    assert moved["speaker_id"] != 1
