from datetime import datetime, timedelta, timezone

from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState, SourceStateReason
from models.memory_contracts import L1MemoryArchiveItem, LifecycleState, WorkingMemoryObservation
from models.product_memory import MemoryAccessPolicy, MemoryItemStatus, MemoryTier, ProcessingState, MemoryItem
from utils.memory.memory_read_api import (
    query_archive_product_memory_items,
    query_default_product_memory_items,
    query_durable_memory,
    query_l1_archive,
    query_memory_context,
    query_working_memory,
)

NOW = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)


def _working(content, status="working"):
    return WorkingMemoryObservation(
        observation_id=f"obs_{status}_{content[:4]}",
        content=content,
        status=status,
        confidence="medium",
        evidence_ids=["ev_1"],
        source_refs=[{"quote": "I want automatic memory capture.", "source_id": "src_1"}],
    )


def _durable(memory_id, content, status="active", superseded_by=None):
    return {
        "id": memory_id,
        "content": content,
        "status": status,
        "confidence": "high",
        "created_at": "2026-06-17T00:00:00Z",
        "source": "ledger",
        "evidence_set": [{"evidence_id": "ev_2", "quote": "Automatic memory is better.", "source_id": "src_2"}],
        "superseded_by": superseded_by,
    }


def _evidence(source_state=SourceState.active):
    source_state_reason = SourceStateReason.deleted_by_user if source_state != SourceState.active else None
    return MemoryEvidence(
        evidence_id="ev_product",
        source_id="src_product",
        source_type="conversation",
        source_version="v1",
        quote_refs=[{"text": "User prefers automatic capture."}],
        content_hash="hash_product",
        source_state=source_state,
        source_state_reason=source_state_reason,
        artifact_preservation=ArtifactPreservationState.preserved,
    )


def _product_item(memory_id: str, content: str, **overrides) -> MemoryItem:
    base = {
        "memory_id": memory_id,
        "uid": "user_1",
        "version": 1,
        "tier": MemoryTier.short_term,
        "status": MemoryItemStatus.active,
        "processing_state": ProcessingState.pending,
        "content": content,
        "evidence": [_evidence()],
        "source_state": SourceState.active,
        "sensitivity_labels": [],
        "visibility": "private",
        "user_asserted": False,
        "captured_at": NOW - timedelta(days=1),
        "updated_at": NOW - timedelta(hours=1),
        "expires_at": NOW + timedelta(days=29),
    }
    base.update(overrides)
    if base["source_state"] != SourceState.active:
        base["evidence"] = [_evidence(base["source_state"])]
    return MemoryItem(**base)


def test_query_working_memory_returns_labeled_non_stable_records():
    results = query_working_memory("automatic", [_working("User wants automatic memory capture.")])

    assert results[0]["memory_layer"] == "working"
    assert results[0]["lifecycle_status"] == "working"
    assert results[0]["agent_use"] == "working_context_not_stable_profile"
    assert results[0]["evidence"][0]["quote"] == "I want automatic memory capture."


def test_query_durable_memory_excludes_superseded_current_truth_by_default():
    records = [
        _durable("mem_old", "User uses manual notes.", status="superseded", superseded_by="mem_new"),
        _durable("mem_new", "User prefers automatic memory capture."),
    ]

    results = query_durable_memory("memory", records)

    assert [result["memory_id"] for result in results] == ["mem_new"]
    assert results[0]["agent_use"] == "stable_profile_fact"


def test_query_memory_context_mixes_l1_and_l2_but_preserves_labels():
    results = query_memory_context(
        "automatic",
        working_records=[
            _working("User may want automatic capture."),
            _working("Automatic capture needs review.", status="review"),
        ],
        durable_records=[_durable("mem_active", "User prefers automatic memory capture.")],
    )

    assert {result["memory_layer"] for result in results} == {"working", "durable"}
    uses = {result["agent_use"] for result in results}
    assert "stable_profile_fact" in uses
    assert "working_context_not_stable_profile" in uses
    assert "review_only_not_profile_fact" in uses
    assert all("lifecycle_status" in result for result in results)


def _archive(text, archive_class="general", source_id="src_archive"):
    return L1MemoryArchiveItem(
        user_id="user_1",
        source_id=source_id,
        source_type="voice_transcript",
        text=text,
        archive_class=archive_class,
        evidence_quotes=[text],
        source_refs=[{"quote": text, "source_id": source_id}],
    )


def test_query_l1_archive_returns_general_evidence_not_profile_facts():
    results = query_l1_archive(
        "Rust fog",
        [
            _archive("User was troubleshooting Rust fog and TAA settings."),
            _archive(
                "User shared a password manager credential.", archive_class="sensitive", source_id="src_sensitive"
            ),
        ],
    )

    assert len(results) == 1
    assert results[0]["memory_layer"] == "l1_archive"
    assert results[0]["archive_class"] == "general"
    assert results[0]["agent_use"] == "archived_evidence_not_stable_profile"
    assert results[0]["evidence"][0]["quote"] == "User was troubleshooting Rust fog and TAA settings."


def test_query_default_product_memory_items_applies_product_filter_before_matching():
    fresh_short = _product_item("fresh-short", "User prefers automatic capture.")
    stale_short = _product_item(
        "stale-short",
        "User likes stale automatic capture.",
        captured_at=NOW - timedelta(days=45),
        updated_at=NOW - timedelta(days=2),
        expires_at=NOW - timedelta(seconds=1),
    )
    long_term = _product_item(
        "long-term",
        "User prefers automatic long-term memory.",
        tier=MemoryTier.long_term,
        processing_state=ProcessingState.processed,
        expires_at=None,
        ledger_commit_id="commit1",
        ledger_sequence=1,
    )
    archive = _product_item(
        "archive",
        "User archived automatic context.",
        tier=MemoryTier.archive,
        processing_state=ProcessingState.processed,
        expires_at=None,
    )

    results = query_default_product_memory_items(
        "automatic", [stale_short, archive, fresh_short, long_term], policy=MemoryAccessPolicy.for_omi_chat(), now=NOW
    )

    assert [result["memory_id"] for result in results] == ["fresh-short", "long-term"]
    assert {result["tier"] for result in results} == {"short_term", "long_term"}
    assert results[0]["memory_layer"] == "product_memory"
    assert results[0]["agent_use"] == "default_access_memory"


def test_query_default_product_memory_items_keeps_processed_short_term_visible():
    processed_short = _product_item(
        "processed-short",
        "User prefers processed short-term capture.",
        processing_state=ProcessingState.processed,
        ledger_commit_id="commit1",
        ledger_sequence=1,
        source_commit_id="commit1",
        source_commit_sequence=1,
        content_hash="hash_processed",
    )

    results = query_default_product_memory_items(
        "processed", [processed_short], policy=MemoryAccessPolicy.for_omi_chat(), now=NOW
    )

    assert [result["memory_id"] for result in results] == ["processed-short"]
    assert results[0]["access_reason"] == "default_memory_allowed"
    assert results[0]["processing_state"] == "processed"


def test_query_default_product_memory_items_excludes_tombstoned_and_restricted_sensitivity():
    tombstoned = _product_item(
        "tombstoned-short",
        "User tombstoned short-term memory.",
        source_state=SourceState.tombstoned,
    )
    restricted = _product_item(
        "restricted-short",
        "User restricted sensitivity memory.",
        processing_state=ProcessingState.processed,
        sensitivity_labels=["credential"],
        ledger_commit_id="commit1",
        ledger_sequence=1,
        source_commit_id="commit1",
        source_commit_sequence=1,
        content_hash="hash_restricted",
    )

    results = query_default_product_memory_items(
        "User",
        [tombstoned, restricted],
        policy=MemoryAccessPolicy.for_omi_chat(),
        now=NOW,
    )

    assert results == []


def test_query_archive_product_memory_items_is_explicit_and_capability_gated():
    archive = _product_item(
        "archive",
        "User archived Rust fog context.",
        tier=MemoryTier.archive,
        processing_state=ProcessingState.processed,
        expires_at=None,
    )
    fresh_short = _product_item("fresh-short", "User prefers Rust settings.")

    default_results = query_default_product_memory_items(
        "Rust", [archive, fresh_short], policy=MemoryAccessPolicy.for_omi_chat(), now=NOW
    )
    denied_archive_results = query_archive_product_memory_items(
        "Rust", [archive, fresh_short], policy=MemoryAccessPolicy.for_omi_chat(), now=NOW
    )
    allowed_archive_results = query_archive_product_memory_items(
        "Rust", [archive, fresh_short], policy=MemoryAccessPolicy.for_omi_chat(archive_capability=True), now=NOW
    )

    assert [result["memory_id"] for result in default_results] == ["fresh-short"]
    assert denied_archive_results == []
    assert [result["memory_id"] for result in allowed_archive_results] == ["archive"]
    assert allowed_archive_results[0]["agent_use"] == "explicit_archive_memory"


def test_query_memory_context_uses_l2_first_and_only_searches_l1_when_requested():
    durable_records = [_durable("mem_active", "User prefers automatic memory capture.")]
    archive_records = [_archive("User was troubleshooting Rust fog and TAA settings.")]

    default_results = query_memory_context(
        "Rust fog",
        working_records=[],
        durable_records=durable_records,
        l1_archive_records=archive_records,
    )
    archive_results = query_memory_context(
        "Rust fog",
        working_records=[],
        durable_records=durable_records,
        l1_archive_records=archive_records,
        include_l1_archive=True,
    )

    assert default_results == []
    assert archive_results[0]["memory_layer"] == "l1_archive"
