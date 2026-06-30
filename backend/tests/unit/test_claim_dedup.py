"""Unit tests for claim (triple) deduplication logic."""

from __future__ import annotations

from datetime import datetime, timezone

from utils.memory_ingestion.models import (
    ConfidenceLabel,
    DerivedTriple,
    EntityRef,
    FrameObject,
)
from utils.memory_ingestion.pipeline import _dedupe_triples


def _make_triple(
    triple_id: str,
    subject_name: str,
    predicate: str,
    object_value: str,
    source_frame_id: str = "frame-1",
) -> DerivedTriple:
    return DerivedTriple(
        triple_id=triple_id,
        source_frame_id=source_frame_id,
        subject=EntityRef(entity_id=f"ent-{subject_name}", entity_type="person", canonical_name=subject_name),
        predicate=predicate,
        object=FrameObject(object_type="literal", value=object_value),
        confidence="high",
    )


class TestDedupeTriples:
    def test_no_dedup_needed(self):
        triples = [
            _make_triple("t1", "Alice", "lives_in", "Paris"),
            _make_triple("t2", "Bob", "works_at", "Acme"),
        ]
        result = _dedupe_triples(triples)
        assert len(result) == 2

    def test_exact_key_dedup_keeps_shortest_object(self):
        """Same (subject, predicate, frame_id) → keep the most concise object."""
        triples = [
            _make_triple("t1", "Alice", "lives_in", "Alice lives in Paris which is in France"),
            _make_triple("t2", "Alice", "lives_in", "Paris"),
            _make_triple("t3", "Alice", "lives_in", "Alice resides in the city of Paris"),
        ]
        result = _dedupe_triples(triples)
        assert len(result) == 1
        assert result[0].triple_id == "t2"  # shortest object value

    def test_different_frames_are_kept(self):
        """Different source_frame_ids for same subject+predicate are NOT deduped."""
        triples = [
            _make_triple("t1", "Alice", "lives_in", "Paris", source_frame_id="frame-a"),
            _make_triple("t2", "Alice", "lives_in", "London", source_frame_id="frame-b"),
        ]
        result = _dedupe_triples(triples)
        assert len(result) == 2

    def test_near_duplicate_suppression(self):
        """Canonical texts within edit-distance < 5 are collapsed."""
        triples = [
            _make_triple("t1", "Alice", "lives_in", "Paris", source_frame_id="f1"),
            _make_triple("t2", "Alice", "livs_in", "Paris", source_frame_id="f2"),  # typo in predicate
            _make_triple("t3", "Bob", "works_at", "Acme", source_frame_id="f3"),
        ]
        result = _dedupe_triples(triples)
        # t1 and t2 should collapse (edit distance < 5 on canonical), plus t3
        assert len(result) == 2

    def test_empty_input(self):
        assert _dedupe_triples([]) == []

    def test_single_triple_passthrough(self):
        triples = [_make_triple("t1", "Alice", "likes", "pizza")]
        result = _dedupe_triples(triples)
        assert len(result) == 1
        assert result[0].triple_id == "t1"
