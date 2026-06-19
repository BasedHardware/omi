from datetime import datetime, timedelta, timezone

from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.v17_memory_search_gateway import SearchDecision, SearchMode, SearchVectorHit, hydrate_and_filter_vector_hits
from models.v17_product_memory import (
    MemoryAccessPolicy,
    MemoryItemStatus,
    MemoryTier,
    ProcessingState,
    V17MemoryItem,
    new_memory_id,
)


def _item(memory_id, *, tier=MemoryTier.short_term, status=MemoryItemStatus.active, expires_at=None, sensitive=False):
    now = datetime.now(timezone.utc)
    return V17MemoryItem(
        memory_id=memory_id,
        uid="u1",
        version=1,
        tier=tier,
        status=status,
        processing_state=ProcessingState.processed,
        content=f"Memory {memory_id}",
        evidence=[
            MemoryEvidence(
                evidence_id=f"ev_{memory_id}",
                source_id="conv1",
                source_type="conversation",
                source_version="v1",
                artifact_preservation=ArtifactPreservationState.preserved,
            )
        ],
        source_state=SourceState.active,
        sensitivity_labels=["credential"] if sensitive else [],
        visibility="private",
        user_asserted=False,
        captured_at=now - timedelta(days=1),
        updated_at=now,
        expires_at=expires_at if expires_at is not None else now + timedelta(days=30),
        ledger_commit_id="commit1" if tier == MemoryTier.long_term else None,
        ledger_sequence=1 if tier == MemoryTier.long_term else None,
    )


def test_search_gateway_hydrates_authoritative_items_and_drops_stale_or_missing_hits():
    item = _item("mem1")
    hits = [
        SearchVectorHit(memory_id="mem1", score=0.9, projection_commit_id="commit1", vector_updated_at=item.updated_at),
        SearchVectorHit(
            memory_id="missing", score=0.8, projection_commit_id="commit1", vector_updated_at=item.updated_at
        ),
    ]

    result = hydrate_and_filter_vector_hits(
        hits=hits,
        authoritative_items={"mem1": item},
        policy=MemoryAccessPolicy.for_omi_chat(),
        mode=SearchMode.default,
        required_projection_commit_id="commit1",
    )

    assert [entry.item.memory_id for entry in result.results] == ["mem1"]
    assert result.decisions["missing"] == SearchDecision.missing_authoritative_item


def test_search_gateway_fail_closed_on_stale_projection_or_default_archive_access():
    archive = _item("arch1", tier=MemoryTier.archive, expires_at=None)
    stale = _item("mem_stale")
    hits = [
        SearchVectorHit(
            memory_id="arch1", score=0.9, projection_commit_id="commit1", vector_updated_at=archive.updated_at
        ),
        SearchVectorHit(
            memory_id="mem_stale", score=0.8, projection_commit_id="old", vector_updated_at=stale.updated_at
        ),
    ]

    result = hydrate_and_filter_vector_hits(
        hits=hits,
        authoritative_items={"arch1": archive, "mem_stale": stale},
        policy=MemoryAccessPolicy.for_omi_chat(),
        mode=SearchMode.default,
        required_projection_commit_id="commit1",
    )

    assert result.results == []
    assert result.decisions["arch1"] == SearchDecision.access_denied
    assert result.decisions["mem_stale"] == SearchDecision.stale_projection


def test_explicit_archive_query_requires_archive_capability_and_still_rejects_sensitive_items():
    archive = _item("arch1", tier=MemoryTier.archive, expires_at=None)
    secret = _item("secret1", tier=MemoryTier.archive, expires_at=None, sensitive=True)
    hits = [
        SearchVectorHit(
            memory_id="arch1", score=0.9, projection_commit_id="commit1", vector_updated_at=archive.updated_at
        ),
        SearchVectorHit(
            memory_id="secret1", score=0.8, projection_commit_id="commit1", vector_updated_at=secret.updated_at
        ),
    ]

    result = hydrate_and_filter_vector_hits(
        hits=hits,
        authoritative_items={"arch1": archive, "secret1": secret},
        policy=MemoryAccessPolicy.for_omi_chat(archive_capability=True),
        mode=SearchMode.archive_explicit,
        required_projection_commit_id="commit1",
    )

    assert [entry.item.memory_id for entry in result.results] == ["arch1"]
    assert result.decisions["secret1"] == SearchDecision.access_denied
