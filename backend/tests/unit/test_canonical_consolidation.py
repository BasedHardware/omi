"""Schema contracts for deterministic retention and owed intake dispositions."""

from datetime import datetime, timedelta, timezone
import pytest
from models.memory_apply import memory_content_hash
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.product_memory import MemoryTier, MemoryItemStatus, ProcessingState, MemoryItem
from utils.memory.canonical_consolidation import ConsolidationAgentDecision

NOW = datetime(2026, 6, 20, 12, tzinfo=timezone.utc)
UID = "uid-canonical"


def _item(
    memory_id: str,
    content: str,
    *,
    tier: MemoryTier = MemoryTier.short_term,
    sensitivity_labels: list[str] | None = None,
) -> MemoryItem:
    evidence = MemoryEvidence(
        evidence_id=f"ev_{memory_id}",
        source_id="conv-1",
        source_type="conversation",
        source_version="v1",
        artifact_preservation=ArtifactPreservationState.preserved,
        quote_refs=[{"quote": content, "speaker": "user"}],
    )
    return MemoryItem(
        memory_id=memory_id,
        uid=UID,
        version=1,
        tier=tier,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content=content,
        evidence=[evidence],
        source_state=SourceState.active,
        sensitivity_labels=sensitivity_labels or [],
        visibility="private",
        user_asserted=False,
        captured_at=NOW - timedelta(hours=1),
        updated_at=NOW,
        expires_at=NOW + timedelta(days=30) if tier == MemoryTier.short_term else None,
        ledger_commit_id="commit-1",
        ledger_sequence=1,
        item_revision=1,
        source_commit_id="commit-1",
        content_hash=memory_content_hash(content=content, evidence_ids=[evidence.evidence_id]),
        account_generation=1,
        subject_entity_id="user",
        promotion={
            "source_attribution": {
                "subject_entity_id": "user",
                "subject_attribution": "user",
            }
        },
    )


def _promote(item: MemoryItem, **overrides) -> ConsolidationAgentDecision:
    values = {
        "source_memory_id": item.memory_id,
        "route": "promote",
        "reconciliation": "create",
        "memory_text": f"The user said: {item.content}",
        "evidence_ids": [evidence.evidence_id for evidence in item.evidence],
        "subject_entity_id": "user",
        "predicate": "stated_preference",
        "arguments": {"preference": item.content},
        "relationship_to_user": "self",
        "aboutness": "primary_user",
        "basis_for_memory": "explicit",
        "confidence": "high",
    }
    values.update(overrides)
    return ConsolidationAgentDecision(**values)


def test_promote_decision_requires_structured_graph_and_durable_basis():
    item = _item("mem_a", "Enjoys hiking")
    with pytest.raises(ValueError, match="graph|subject|predicate"):
        ConsolidationAgentDecision(
            source_memory_id=item.memory_id,
            route="promote",
            memory_text="The user enjoys hiking.",
            evidence_ids=["ev_mem_a"],
            relationship_to_user="self",
            basis_for_memory="explicit",
        )
    with pytest.raises(ValueError, match="basis"):
        _promote(item, basis_for_memory="weak_or_none")


def test_promote_decision_rejects_incoherent_reconciliation_mutations():
    item = _item("mem_a", "Enjoys hiking")
    with pytest.raises(ValueError, match="duplicate"):
        _promote(item, reconciliation="duplicate", target_memory_id="mem_old")
    with pytest.raises(ValueError, match="supersede its target"):
        _promote(item, reconciliation="replace", target_memory_id="mem_old")
    with pytest.raises(ValueError, match="cannot supersede"):
        _promote(item, reconciliation="keep_both", supersedes=["mem_old"])
