"""Thin adapter over existing V17 apply/read services for canonical-cohort MemoryService."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database._client import db as default_db_client
from database.product_memory_items import filter_default_product_memory_items
from database.v17_collections import V17Collections
from database.v17_memory_apply_store import apply_long_term_patch_firestore
from database.v17_vector_repair_outbox import build_v17_vector_repair_purge_outbox_records
from models.memory_domain import MemoryLayer, MemoryProcessingState, MemoryRecordStatus, assert_legal_state
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState, SourceStateReason
from models.memories import MemoryDB, MemoryCategory
from models.v17_memory_apply import ApplyStatus, MemoryControlState
from models.v17_memory_contracts import DurablePatchDecision, LifecycleState, deterministic_contract_id
from models.v17_memory_operations import MemoryOperation, MemoryOperationType
from models.v17_product_memory import (
    MemoryAccessPolicy,
    MemoryItemStatus,
    MemoryTier,
    ProcessingState,
    V17MemoryItem,
    is_default_access_eligible,
)
from utils.memory.v17_product_memory_read_service import fetch_authoritative_product_memory_items
from utils.memory.v17_v3_account_generation_source import read_v17_v3_trusted_account_generation

logger = logging.getLogger(__name__)

# L2 lifecycle hides processed short_term until disposition workers run (WS-B).
# WS-I extractions land as processed short_term and must remain default-visible.
_L2_PROCESSED_REQUIRES_DISPOSITION = "short_term_l2_processed_requires_explicit_lifecycle_disposition"


def extraction_memory_id(*, uid: str, source_id: str, content: str) -> str:
    """Hash-derived neutral memory id (Q4/Q5)."""
    return (
        "mem_"
        + deterministic_contract_id(
            "canonical-extraction-memory",
            {"uid": uid, "source_id": source_id, "content": (content or "").strip()},
        )[:32]
    )


def search_result_to_memorydb(uid: str, item: Dict[str, Any]) -> MemoryDB:
    updated_at = item.get("date") or item.get("updated_at")
    if isinstance(updated_at, str):
        updated_at = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    if not isinstance(updated_at, datetime):
        updated_at = datetime.now(timezone.utc)
    tier_value = item.get("tier") or MemoryTier.short_term.value
    tier = tier_value if isinstance(tier_value, MemoryTier) else MemoryTier(tier_value)
    return MemoryDB(
        id=item["memory_id"],
        uid=uid,
        content=item.get("content") or "",
        category=MemoryCategory.interesting,
        tags=[],
        created_at=updated_at,
        updated_at=updated_at,
        manually_added=False,
        reviewed=False,
        visibility=item.get("visibility") or "private",
        memory_tier=tier,
        valid_at=updated_at,
    )


def v17_memory_item_to_memorydb(item: V17MemoryItem) -> MemoryDB:
    """Map authoritative V17 memory_items row to legacy MemoryDB response shape."""
    conversation_id = None
    evidence_payload = []
    for evidence in item.evidence:
        evidence_payload.append(
            {
                "evidence_id": evidence.evidence_id,
                "source_id": evidence.source_id,
                "source_type": evidence.source_type,
                "source_signal": "transcription",
                "extractor_id": "canonical_memory_adapter",
                "extractor_version": "v1",
                "artifact_ref": {},
                "capture_confidence": 0.5,
                "independence_group": evidence.source_id or evidence.source_type,
                "redaction_status": evidence.redaction_status.value,
                "created_at": item.captured_at,
            }
        )
        if evidence.source_type == "conversation" and evidence.source_id:
            conversation_id = evidence.source_id

    return MemoryDB(
        id=item.memory_id,
        uid=item.uid,
        content=item.content or "",
        category=MemoryCategory.interesting,
        tags=[],
        created_at=item.captured_at,
        updated_at=item.updated_at,
        conversation_id=conversation_id,
        manually_added=item.user_asserted,
        reviewed=False,
        visibility=item.visibility,
        evidence=evidence_payload,
        memory_tier=item.tier,
        valid_at=item.captured_at,
    )


def read_canonical_memories(
    uid: str,
    *,
    limit: int = 100,
    offset: int = 0,
    db_client=None,
) -> List[MemoryDB]:
    """Read default-visible canonical items using the shared product-memory filter."""
    client = db_client if db_client is not None else default_db_client
    items = fetch_authoritative_product_memory_items(uid=uid, db_client=client)
    now = datetime.now(timezone.utc)
    policy = MemoryAccessPolicy.for_omi_chat(archive_capability=False)
    report = filter_default_product_memory_items(items, policy=policy, now=now)
    visible_by_id = {item.memory_id: item for item in report.visible_items}

    # Reconcile WS-I extraction state: processed short_term passes access policy but is
    # withheld by L2 lifecycle until explicit disposition (promotion is WS-B).
    for item in items:
        if item.memory_id in visible_by_id:
            continue
        decision = report.decisions.get(item.memory_id)
        if decision is None or not decision.lifecycle_reason:
            continue
        if (
            decision.lifecycle_reason == _L2_PROCESSED_REQUIRES_DISPOSITION
            and item.tier == MemoryTier.short_term
            and item.status == MemoryItemStatus.active
            and item.processing_state == ProcessingState.processed
            and is_default_access_eligible(item, policy, now=now).allowed
        ):
            visible_by_id[item.memory_id] = item

    visible = sorted(visible_by_id.values(), key=lambda item: (-item.updated_at.timestamp(), item.memory_id))
    paged = visible[offset : offset + limit]
    return [v17_memory_item_to_memorydb(item) for item in paged]


def search_canonical_memories(
    uid: str,
    query: str,
    *,
    limit: int = 5,
    db_client=None,
) -> List[Dict[str, Any]]:
    """Keyword search over WS-I default-visible canonical items."""
    client = db_client if db_client is not None else default_db_client
    memories = read_canonical_memories(uid, limit=500, offset=0, db_client=client)
    query_tokens = {token.lower() for token in (query or "").split() if len(token) > 2}
    if not query_tokens:
        return [
            {
                "memory_id": memory.id,
                "content": memory.content,
                "tier": memory.memory_tier.value,
                "date": memory.updated_at.isoformat(),
                "visibility": memory.visibility,
            }
            for memory in memories[:limit]
        ]

    matches = []
    for memory in memories:
        content_lower = (memory.content or "").lower()
        if any(token in content_lower for token in query_tokens):
            matches.append(
                {
                    "memory_id": memory.id,
                    "content": memory.content,
                    "tier": memory.memory_tier.value,
                    "date": memory.updated_at.isoformat(),
                    "visibility": memory.visibility,
                }
            )
    return matches[: max(1, min(limit, 20))]


def _ensure_control_state(uid: str, *, db_client) -> MemoryControlState:
    collections = V17Collections(uid=uid)
    ref = db_client.document(collections.memory_control_state)
    snapshot = ref.get()
    if getattr(snapshot, "exists", False):
        return MemoryControlState(**(snapshot.to_dict() or {}))

    control = MemoryControlState(uid=uid, head_commit_id="head0", account_generation=1, source_generation=1)
    ref.set(control.model_dump(mode="json"))
    return control


def _legacy_evidence_to_v17(evidence_data: Dict[str, Any], *, conversation_id: Optional[str]) -> MemoryEvidence:
    source_id = evidence_data.get("source_id") or conversation_id
    return MemoryEvidence(
        evidence_id=evidence_data["evidence_id"],
        source_type=evidence_data.get("source_type") or "conversation",
        source_id=source_id,
        source_version="v1",
        conversation_id=(
            conversation_id if (evidence_data.get("source_type") or "conversation") == "conversation" else None
        ),
        artifact_preservation=ArtifactPreservationState.preserved,
    )


def _persist_evidence(uid: str, evidence: MemoryEvidence, *, db_client) -> None:
    collections = V17Collections(uid=uid)
    path = f"{collections.memory_evidence}/{evidence.evidence_id}"
    ref = db_client.document(path)
    active_evidence = evidence.model_copy(
        update={
            "source_state": SourceState.active,
            "source_state_reason": None,
        }
    )
    ref.set(active_evidence.model_dump(mode="json"))


def _bump_source_generation(uid: str, *, db_client) -> MemoryControlState:
    """Advance source_generation so re-extract gets a fresh operation identity space (Q7)."""
    control = _ensure_control_state(uid, db_client=db_client)
    bumped = control.model_copy(
        update={
            "source_generation": control.source_generation + 1,
            "updated_at": datetime.now(timezone.utc),
        }
    )
    db_client.document(V17Collections(uid=uid).memory_control_state).set(bumped.model_dump(mode="json"))
    return bumped


def write_canonical_extraction_memory(uid: str, data: Dict[str, Any], *, db_client=None) -> str:
    """Persist one extracted memory to memory_items + ledger at short_term/active/processed."""
    client = db_client if db_client is not None else default_db_client
    content = (data.get("content") or "").strip()
    if not content:
        raise ValueError("canonical write requires non-empty content")

    conversation_id = data.get("conversation_id") or data.get("memory_id")
    source_id = conversation_id or data.get("id") or "unknown"
    memory_id = data.get("id") or extraction_memory_id(uid=uid, source_id=source_id, content=content)
    idempotency_key = deterministic_contract_id(
        "canonical-extraction-idempotency",
        {"uid": uid, "source_id": source_id, "content": content},
    )

    evidence_items: List[MemoryEvidence] = []
    for raw in data.get("evidence") or []:
        if isinstance(raw, dict) and raw.get("evidence_id"):
            evidence_items.append(_legacy_evidence_to_v17(raw, conversation_id=conversation_id))
    if not evidence_items:
        raise ValueError("canonical write requires at least one evidence record")

    control = _ensure_control_state(uid, db_client=client)
    for evidence in evidence_items:
        _persist_evidence(uid, evidence, db_client=client)

    logical_payload = {
        "decision": "add",
        "memory_text": content,
        "result_status": LifecycleState.active.value,
    }
    operation = MemoryOperation.new(
        uid=uid,
        operation_type=MemoryOperationType.source_candidate,
        source_packet_id=source_id,
        target_memory_id=None,
        evidence_ids=[item.evidence_id for item in evidence_items],
        logical_payload=logical_payload,
        account_generation=control.account_generation,
        source_generation=control.source_generation,
        observed_head_commit_id=control.head_commit_id,
    )
    op_ref = client.document(f"{V17Collections(uid=uid).memory_operations}/{operation.operation_id}")
    if not op_ref.get().exists:
        op_ref.set(operation.model_dump(mode="json"))

    patch_payload = {
        "patch_id": f"patch_{idempotency_key[:24]}",
        "packet_id": source_id,
        "run_id": f"extract_{source_id}",
        "observed_head_commit_id": control.head_commit_id,
        "idempotency_key": idempotency_key,
        "decision": DurablePatchDecision.add.value,
        "result_status": LifecycleState.active.value,
        "evidence_ids": [item.evidence_id for item in evidence_items],
        "new_memory_id": memory_id,
        "memory_text": content,
        "confidence": "medium",
        "relationship_to_user": "self",
        "initial_tier": MemoryTier.short_term.value,
    }

    result = apply_long_term_patch_firestore(
        uid=uid,
        operation_id=operation.operation_id,
        patch_payload=patch_payload,
        db_client=client,
    )
    if result.status not in {ApplyStatus.committed, ApplyStatus.idempotent_skip}:
        raise RuntimeError(f"canonical write failed: {result.status} ({result.reason})")

    committed_id = memory_id
    if result.memory_items:
        committed_id = result.memory_items[0].memory_id
    elif result.operation.committed_memory_item_ids:
        committed_id = result.operation.committed_memory_item_ids[0]

    item = result.memory_items[0] if result.memory_items else None
    if item is not None:
        assert_legal_state(
            MemoryLayer(item.tier.value),
            MemoryRecordStatus(item.status.value),
            MemoryProcessingState(item.processing_state.value),
        )

    return committed_id


def _item_sourced_from_conversation(item: V17MemoryItem, conversation_id: str) -> bool:
    for evidence in item.evidence:
        if evidence.source_id == conversation_id:
            return True
        if evidence.conversation_id == conversation_id:
            return True
    return False


def _tombstone_memory_item(uid: str, item: V17MemoryItem, *, db_client, reason: str) -> None:
    collections = V17Collections(uid=uid)
    now = datetime.now(timezone.utc)
    trusted = read_v17_v3_trusted_account_generation(uid=uid, db_client=db_client)
    account_generation = trusted.account_generation if trusted.read_error_reason is None else 1
    projection_commit_id = trusted.head_commit_id or "head0"

    tombstoned_evidence = []
    for evidence in item.evidence:
        next_evidence = evidence.model_copy(
            update={
                "source_state": SourceState.tombstoned,
                "source_state_reason": SourceStateReason.deleted_by_user,
            }
        )
        tombstoned_evidence.append(next_evidence)
        ev_ref = db_client.document(f"{collections.memory_evidence}/{evidence.evidence_id}")
        if ev_ref.get().exists:
            ev_ref.set(next_evidence.model_dump(mode="json"))

    updated_item = item.model_copy(
        update={
            "status": MemoryItemStatus.tombstoned,
            "source_state": SourceState.tombstoned,
            "content": None,
            "evidence": tombstoned_evidence,
            "updated_at": now,
        }
    )
    db_client.document(f"{collections.memory_items}/{item.memory_id}").set(updated_item.model_dump(mode="json"))

    purge_candidates = [
        {
            "vector_id": item.memory_id,
            "memory_id": item.memory_id,
            "reason": reason,
            "required_projection_commit_id": projection_commit_id,
            "required_account_generation": account_generation,
            "authoritative_account_generation": account_generation,
        }
    ]
    for record in build_v17_vector_repair_purge_outbox_records(uid=uid, candidates=purge_candidates):
        db_client.document(record["outbox_path"]).set(record)


def retract_conversation_sourced_memories(uid: str, conversation_id: str, *, db_client=None) -> Dict[str, Any]:
    """Full retract for reprocess: tombstone items, purge vectors, bump source_generation."""
    client = db_client if db_client is not None else default_db_client
    items = fetch_authoritative_product_memory_items(uid=uid, db_client=client)
    retracted_ids: List[str] = []

    for item in items:
        if item.status != MemoryItemStatus.active:
            continue
        if not _item_sourced_from_conversation(item, conversation_id):
            continue
        _tombstone_memory_item(uid, item, db_client=client, reason="conversation_reprocess_retract")
        retracted_ids.append(item.memory_id)

    bumped_control = _bump_source_generation(uid, db_client=client)

    return {
        "retracted_memory_ids": retracted_ids,
        "vector_delete_ids": retracted_ids,
        "tombstoned_evidence_ids": [],
        "source_generation": bumped_control.source_generation,
    }


def delete_canonical_memory(uid: str, memory_id: str, *, db_client=None) -> None:
    client = db_client if db_client is not None else default_db_client
    path = f"{V17Collections(uid=uid).memory_items}/{memory_id}"
    snapshot = client.document(path).get()
    if not getattr(snapshot, "exists", False):
        return
    item = V17MemoryItem.model_validate(snapshot.to_dict() or {})
    if item.status == MemoryItemStatus.active:
        _tombstone_memory_item(uid, item, db_client=client, reason="canonical_memory_delete")


def delete_all_canonical_memories(uid: str, *, db_client=None) -> None:
    client = db_client if db_client is not None else default_db_client
    items = fetch_authoritative_product_memory_items(uid=uid, db_client=client)
    for item in items:
        if item.status == MemoryItemStatus.active:
            _tombstone_memory_item(uid, item, db_client=client, reason="canonical_memory_delete_all")
