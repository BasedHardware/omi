from datetime import datetime, timedelta, timezone

from database.memory_vector_metadata import (
    build_archive_memory_vector_filter,
    build_default_memory_vector_filter,
    build_memory_vector_metadata,
    deterministic_memory_vector_id,
    parse_search_vector_hit,
)
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.memory_search_gateway import SearchDecision
from models.product_memory import MemoryItemStatus, MemoryTier, ProcessingState, MemoryItem


def _item(
    memory_id="mem1",
    *,
    tier=MemoryTier.short_term,
    status=MemoryItemStatus.active,
    processing_state=ProcessingState.pending,
    source_state=SourceState.active,
    sensitive=False,
):
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    return MemoryItem(
        memory_id=memory_id,
        uid="uid-1",
        version=2,
        tier=tier,
        status=status,
        processing_state=processing_state,
        content=f"content {memory_id}",
        evidence=[
            MemoryEvidence(
                evidence_id=f"ev_{memory_id}",
                source_id="conv-1",
                source_type="conversation",
                source_version="v1",
                artifact_preservation=ArtifactPreservationState.preserved,
            )
        ],
        source_state=source_state,
        sensitivity_labels=["credential"] if sensitive else [],
        visibility="private",
        user_asserted=False,
        captured_at=now - timedelta(days=1),
        updated_at=now,
        expires_at=now + timedelta(days=30) if tier == MemoryTier.short_term else None,
        ledger_commit_id="commit-ledger" if tier == MemoryTier.long_term else None,
        ledger_sequence=7 if tier == MemoryTier.long_term else None,
        item_revision=3,
        source_commit_id="source-commit-1",
        content_hash="hash-1",
        account_generation=11,
    )


def test_deterministic_memory_vector_ids_are_prefixed_and_tier_revision_scoped():
    short_id = deterministic_memory_vector_id("uid-1", "same-memory", MemoryTier.short_term, 3)
    archive_id = deterministic_memory_vector_id("uid-1", "same-memory", MemoryTier.archive, 3)
    next_revision_id = deterministic_memory_vector_id("uid-1", "same-memory", MemoryTier.short_term, 4)

    assert short_id == deterministic_memory_vector_id("uid-1", "same-memory", MemoryTier.short_term, 3)
    assert short_id.startswith("memvec:")
    assert len({short_id, archive_id, next_revision_id, "uid-1-same-memory"}) == 4


def test_memory_vector_metadata_carries_required_hydration_and_filter_fields():
    item = _item(tier=MemoryTier.long_term, processing_state=ProcessingState.processed)
    metadata = build_memory_vector_metadata(
        item,
        projection_commit_id="projection-commit-1",
        vector_updated_at=datetime(2026, 6, 19, 12, 5, tzinfo=timezone.utc),
    )

    assert metadata["memory_schema_version"] == 1
    assert metadata["uid"] == "uid-1"
    assert metadata["memory_id"] == "mem1"
    assert metadata["memory_layer"] == "long_term"
    assert metadata["status"] == "active"
    assert metadata["processing_state"] == "processed"
    assert metadata["source_state"] == "active"
    assert metadata["visibility"] == "private"
    assert metadata["restricted_sensitivity"] is False
    assert metadata["account_generation"] == 11
    assert metadata["item_revision"] == 3
    assert metadata["source_commit_id"] == "source-commit-1"
    assert metadata["content_hash"] == "hash-1"
    assert metadata["projection_commit_id"] == "projection-commit-1"
    assert metadata["vector_updated_at"] == "2026-06-19T12:05:00+00:00"


def test_default_and_archive_filters_are_explicit_tier_safe_and_exclude_hidden_tombstoned_sensitive_records():
    default_filter = build_default_memory_vector_filter("uid-1")
    archive_filter = build_archive_memory_vector_filter("uid-1")

    assert {"memory_layer": {"$in": ["short_term", "long_term"]}} in default_filter["$and"]
    assert {"memory_layer": {"$eq": "archive"}} in archive_filter["$and"]
    for pinecone_filter in (default_filter, archive_filter):
        assert {"uid": {"$eq": "uid-1"}} in pinecone_filter["$and"]
        assert {"memory_schema_version": {"$eq": 1}} in pinecone_filter["$and"]
        assert {"status": {"$eq": "active"}} in pinecone_filter["$and"]
        assert {"source_state": {"$eq": "active"}} in pinecone_filter["$and"]
        assert {"restricted_sensitivity": {"$eq": False}} in pinecone_filter["$and"]


def test_parse_memory_vector_hit_fails_closed_when_required_metadata_is_missing_or_malformed():
    item = _item()
    metadata = build_memory_vector_metadata(
        item,
        projection_commit_id="projection-commit-1",
        vector_updated_at=datetime(2026, 6, 19, 12, 5, tzinfo=timezone.utc),
    )

    parsed = parse_search_vector_hit({"score": 0.91, "metadata": metadata})

    assert parsed.decision == SearchDecision.allowed
    assert parsed.hit is not None
    assert parsed.hit.memory_id == "mem1"
    assert parsed.hit.projection_commit_id == "projection-commit-1"
    assert parsed.hit.uid == "uid-1"
    assert parsed.hit.account_generation == 11
    assert parsed.hit.item_revision == 3
    assert parsed.hit.source_commit_id == "source-commit-1"
    assert parsed.hit.content_hash == "hash-1"

    missing_projection = dict(metadata)
    missing_projection.pop("projection_commit_id")
    rejected = parse_search_vector_hit({"score": 0.5, "metadata": missing_projection})
    assert rejected.decision == SearchDecision.stale_vector
    assert rejected.hit is None

    malformed_timestamp = dict(metadata)
    malformed_timestamp["vector_updated_at"] = "not-a-time"
    rejected = parse_search_vector_hit({"score": 0.5, "metadata": malformed_timestamp})
    assert rejected.decision == SearchDecision.stale_vector
    assert rejected.hit is None
