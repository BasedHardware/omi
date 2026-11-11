from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from models.memory_apply import memory_content_hash
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.product_memory import MemoryItem, MemoryItemStatus, MemoryLayer, ProcessingState
from utils.memory import rejected_memory_feedback as feedback

NOW = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
UID = "uid-rejection-feedback"


class _Snapshot:
    def __init__(self, item: MemoryItem):
        self.id = item.memory_id
        self.exists = True
        self._payload = item.model_dump(mode="python")

    def to_dict(self):
        return self._payload


def _item(
    memory_id: str,
    content: str,
    *,
    user_review: bool | None = False,
    sensitivity_labels: list[str] | None = None,
    updated_at: datetime = NOW,
    status: MemoryItemStatus = MemoryItemStatus.active,
    source_state: SourceState = SourceState.active,
) -> MemoryItem:
    evidence = MemoryEvidence(
        evidence_id=f"ev-{memory_id}",
        source_id=f"conv-{memory_id}",
        source_type="conversation",
        source_version="v1",
        artifact_preservation=ArtifactPreservationState.preserved,
    )
    return MemoryItem(
        memory_id=memory_id,
        uid=UID,
        version=1,
        tier=MemoryLayer.short_term,
        status=status,
        processing_state=ProcessingState.processed,
        content=content,
        evidence=[evidence],
        source_state=source_state,
        sensitivity_labels=sensitivity_labels or [],
        visibility="private",
        user_asserted=False,
        captured_at=updated_at - timedelta(hours=1),
        updated_at=updated_at,
        expires_at=updated_at + timedelta(hours=48),
        ledger_commit_id="commit-1",
        ledger_sequence=1,
        item_revision=1,
        source_commit_id="commit-1",
        content_hash=memory_content_hash(content=content, evidence_ids=[evidence.evidence_id]),
        account_generation=1,
        promotion={"reviewed": user_review is not None, "user_review": user_review},
    )


def _query_with_batches(*batches: list[MemoryItem]):
    query = MagicMock()
    query.order_by.return_value = query
    query.limit.return_value = query
    query.stream.side_effect = [[_Snapshot(item) for item in batch] for batch in batches]
    spec = MagicMock()
    spec.build.return_value = query
    return spec, query


def test_recent_rejected_feedback_is_bounded_sensitivity_safe_cached_and_invalidatable(monkeypatch):
    eligible = [
        _item(f"mem-{index}", f"Rejected durable-looking fact {index} " + "x" * 400)
        for index in range(feedback.REJECTED_MEMORY_FEEDBACK_QUERY_LIMIT + 4)
    ]
    restricted = [
        _item(
            f"mem-restricted-{label}",
            f"restricted {label} detail must never enter a prompt",
            sensitivity_labels=[label],
        )
        for label in sorted(feedback.RESTRICTED_SENSITIVITY_LABELS)
    ]
    accepted = _item("mem-accepted", "Owner accepted this memory", user_review=True)
    hidden = _item("mem-hidden", "Owner rejection retained after terminal routing", status=MemoryItemStatus.hidden)
    tombstoned = _item(
        "mem-tombstoned",
        "Tombstoned source must not enter a prompt",
        source_state=SourceState.tombstoned,
    )
    stale = _item(
        "mem-stale",
        "Old rejection outside the feedback window",
        updated_at=NOW - feedback.REJECTED_MEMORY_FEEDBACK_MAX_AGE - timedelta(seconds=1),
    )
    refreshed = _item("mem-refreshed", "New rejection after cache invalidation")
    spec, query = _query_with_batches(
        [*restricted, accepted, stale, tombstoned, hidden, *eligible],
        [refreshed],
    )
    monkeypatch.setattr(feedback, "RECENT_REJECTED_MEMORY_FEEDBACK_QUERY", spec)
    feedback.clear_rejected_memory_feedback_cache()
    db = MagicMock()

    first = feedback.get_recent_rejected_memory_examples(UID, db_client=db, now=NOW)
    cached = feedback.get_recent_rejected_memory_examples(UID, db_client=db, now=NOW)

    assert cached == first
    assert len(first) == feedback.REJECTED_MEMORY_FEEDBACK_QUERY_LIMIT
    assert all(len(example) <= feedback.REJECTED_MEMORY_FEEDBACK_ITEM_MAX_CHARS for example in first)
    assert sum(len(example) for example in first) <= feedback.REJECTED_MEMORY_FEEDBACK_TOTAL_MAX_CHARS
    assert "restricted" not in " ".join(first)
    assert "Owner accepted" not in " ".join(first)
    assert "Old rejection" not in " ".join(first)
    assert "Tombstoned source" not in " ".join(first)
    assert any("retained after terminal routing" in example for example in first)
    assert query.stream.call_count == 1
    query.limit.assert_called_once_with(feedback.REJECTED_MEMORY_FEEDBACK_SCAN_LIMIT)
    spec.build.assert_called_once()

    feedback.clear_rejected_memory_feedback_cache(UID)
    assert feedback.get_recent_rejected_memory_examples(UID, db_client=db, now=NOW) == (
        "New rejection after cache invalidation",
    )
    assert query.stream.call_count == 2
