"""Thin adapter over existing memory apply/read services for canonical-cohort MemoryService."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast

from database._client import db as default_db_client
from database import knowledge_graph as kg_db
from database.review_queue import purge_stale_review_conflicts_for_memories
from utils.memory.atom_keyword_index import (
    delete_atom_keyword_doc,
    keyword_search_memory_ids,
    merge_memory_search_ids,
    purge_user_atom_keyword_index,
    sync_atom_keyword_index_for_item,
)
from utils.client_device import DeviceScopeRequest
from utils.memory.device_scope_filter import filter_items_by_device_scope
from utils.memory.canonical_visibility_filter import filter_canonical_default_visible_items
from database.memory_collections import MemoryCollections
from database.memory_apply_store import apply_long_term_patch_firestore, atomic_bump_source_generation
from database.memory_vector_repair_outbox import build_vector_repair_purge_outbox_records
from models.memory_domain import (
    MemoryLayer as DomainMemoryLayer,
    MemoryProcessingState,
    assert_legal_state,
    physical_status_to_record_status,
)
from models.memory_evidence import (
    ArtifactPreservationState,
    MemoryEvidence,
    ProvenanceVisibility,
    RedactionStatus,
    SourceState,
    SourceStateReason,
)
from models.memories import Evidence, MemoryDB, MemoryCategory, decide_initial_memory_tier
from models.memory_apply import ApplyStatus, MemoryControlState
from models.memory_contracts import DurablePatchDecision, LifecycleState, deterministic_contract_id
from models.memory_operations import MemoryOperation, MemoryOperationType
from models.product_memory import MemoryAccessPolicy, MemoryItemStatus, MemoryLayer, MemoryItem
from utils.memory.memory_system import MemorySystem, resolve_memory_system
from utils.retrieval.hybrid import rrf_rerank
from utils.memory.canonical_vector_sync import delete_canonical_memory_vector, sync_canonical_memory_vector
from utils.memory.product_memory_read_service import fetch_authoritative_product_memory_items
from utils.memory.v3_account_generation_source import read_memory_v3_trusted_account_generation

logger = logging.getLogger(__name__)

# Q5: canonical Pinecone ids are neutral ``mem_…`` memory ids (not ``memvec:`` or ``{uid}-{id}``).
# Canonical writes upsert neutral-metadata vectors directly; purge paths use neutral ids only.

_ALLOWED_MEMORY_VISIBILITIES = {"private", "public", "shared"}
Payload = Dict[str, Any]
SortKey = tuple[int, datetime | int]


def _payload_or_empty(value: object) -> Payload:
    return cast(Payload, value) if isinstance(value, dict) else {}


def _snapshot_payload(snapshot: Any) -> Payload:
    return _payload_or_empty(snapshot.to_dict() if getattr(snapshot, "exists", False) else {})


def neutral_vector_id_for_memory(memory_id: str) -> str:
    """Return the canonical neutral vector id for a memory item (identity = ``memory_id``)."""
    return memory_id


def invalidate_kg_for_memory_retraction(uid: str, memory_ids: List[str], *, db_client: Any = None) -> None:
    """Prune retracted/superseded memory citations from the user's KG."""
    if not memory_ids:
        return
    client = db_client if db_client is not None else default_db_client
    if resolve_memory_system(uid, db_client=client) != MemorySystem.CANONICAL:
        return
    pruned = kg_db.prune_memory_citations_from_kg(uid, memory_ids, db_client=client)
    logger.info(
        "kg_citations_pruned uid=%s retracted_memory_count=%d pruned_entities=%d",
        uid,
        len(memory_ids),
        pruned,
    )


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
    tier_value = item.get("tier") or MemoryLayer.short_term.value
    tier = tier_value if isinstance(tier_value, MemoryLayer) else MemoryLayer(tier_value)
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


def memory_item_to_memorydb(item: MemoryItem) -> MemoryDB:
    """Map authoritative memory memory_items row to legacy MemoryDB response shape."""
    conversation_id = None
    evidence_payload: List[Payload] = []
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
                "client_device_id": evidence.client_device_id,
            }
        )
        if evidence.source_type == "conversation" and evidence.source_id:
            conversation_id = evidence.source_id

    promotion = item.promotion or {}
    category_raw = promotion.get("category", MemoryCategory.interesting.value)
    try:
        category = MemoryCategory(category_raw)
    except ValueError:
        category = MemoryCategory.interesting
    tags = list(promotion.get("tags") or [])
    reviewed = bool(promotion.get("reviewed", False))
    user_review = promotion.get("user_review")

    return MemoryDB(
        id=item.memory_id,
        uid=item.uid,
        content=item.content or "",
        category=category,
        tags=tags,
        created_at=item.captured_at,
        updated_at=item.updated_at,
        conversation_id=conversation_id,
        manually_added=item.user_asserted,
        reviewed=reviewed,
        user_review=user_review,
        visibility=item.visibility,
        evidence=evidence_payload,
        memory_tier=item.tier,
        valid_at=item.captured_at,
        primary_capture_device=item.primary_capture_device,
        capture_device_ids=item.capture_device_ids or [],
    )


def read_canonical_memories(
    uid: str,
    *,
    limit: int = 100,
    offset: int = 0,
    db_client: Any = None,
    device_scope_request: Optional[DeviceScopeRequest] = None,
) -> List[MemoryDB]:
    """Read default-visible canonical items using the shared product-memory filter."""
    client = db_client if db_client is not None else default_db_client
    device_scope = device_scope_request.device_scope if device_scope_request else "all"
    client_device_id = device_scope_request.client_device_id if device_scope_request else None
    items = fetch_authoritative_product_memory_items(uid=uid, db_client=client)
    now = datetime.now(timezone.utc)
    policy = MemoryAccessPolicy.for_omi_chat(archive_capability=False)
    visible = filter_canonical_default_visible_items(items, policy=policy, now=now)
    visible = filter_items_by_device_scope(
        visible,
        device_scope=device_scope if device_scope in ("current", "all", "explicit") else "all",
        client_device_id=client_device_id,
    )
    paged = visible[offset : offset + limit]
    return [memory_item_to_memorydb(item) for item in paged]


def search_canonical_memories(
    uid: str,
    query: str,
    *,
    limit: int = 5,
    db_client: Any = None,
    vector_query: Any = None,
    device_scope_request: Optional[DeviceScopeRequest] = None,
) -> List[Dict[str, Any]]:
    """Hybrid keyword (Typesense) + vector search over canonical long-term atoms."""
    client = db_client if db_client is not None else default_db_client
    device_scope = device_scope_request.device_scope if device_scope_request else "all"
    client_device_id = device_scope_request.client_device_id if device_scope_request else None
    capped_limit = max(1, min(limit, 20))
    fetch_limit = min(capped_limit * 3, 60)
    normalized_query = (query or "").strip()

    if not normalized_query:
        memories = read_canonical_memories(uid, limit=capped_limit, offset=0, db_client=client)
        return [
            {
                "memory_id": memory.id,
                "content": memory.content,
                "tier": memory.memory_tier.value if memory.memory_tier is not None else MemoryLayer.short_term.value,
                "date": memory.updated_at.isoformat(),
                "visibility": memory.visibility,
            }
            for memory in memories[:capped_limit]
        ]

    keyword_ids = keyword_search_memory_ids(uid, normalized_query, limit=fetch_limit, db_client=client)
    if vector_query is None:
        from database.vector_db import query_memory_vector_candidates

        vector_query_fn = query_memory_vector_candidates
    else:
        vector_query_fn = vector_query
    vector_result = vector_query_fn(uid, normalized_query, limit=fetch_limit)
    vector_ids = [hit.memory_id for hit in vector_result.hits if hit.memory_id]
    merged_ids = merge_memory_search_ids(keyword_ids, vector_ids)
    if not merged_ids:
        return []

    now = datetime.now(timezone.utc)
    policy = MemoryAccessPolicy.for_omi_chat(archive_capability=False)
    all_items = fetch_authoritative_product_memory_items(uid=uid, db_client=client)
    visible_items = filter_canonical_default_visible_items(all_items, policy=policy, now=now)
    items_by_id = {item.memory_id: item for item in visible_items}
    vector_scores = {hit.memory_id: float(hit.score or 0.0) for hit in vector_result.hits}

    candidates: List[Payload] = []
    for memory_id in merged_ids:
        item = items_by_id.get(memory_id)
        if item is None:
            continue
        if item.tier != MemoryLayer.long_term:
            continue
        scoped = filter_items_by_device_scope(
            [item],
            device_scope=device_scope if device_scope in ("current", "all", "explicit") else "all",
            client_device_id=client_device_id,
        )
        if not scoped:
            continue
        candidates.append(
            {
                "id": item.memory_id,
                "content": item.content or "",
                "category": "interesting",
                "vector_score": vector_scores.get(memory_id, 0.0),
                "item": item,
            }
        )

    reranked = rrf_rerank(normalized_query, candidates, capped_limit)
    results: List[Dict[str, Any]] = []
    for candidate in reranked:
        item = cast(MemoryItem, candidate["item"])
        results.append(
            {
                "memory_id": item.memory_id,
                "content": item.content or "",
                "tier": item.tier.value,
                "date": item.updated_at.isoformat(),
                "visibility": item.visibility,
            }
        )
    return results


def _ensure_control_state(uid: str, *, db_client: Any) -> MemoryControlState:
    collections = MemoryCollections(uid=uid)
    ref = db_client.document(collections.memory_apply_control_state)
    snapshot = ref.get()
    if getattr(snapshot, "exists", False):
        return MemoryControlState(**_snapshot_payload(snapshot))

    control = MemoryControlState(uid=uid, head_commit_id="head0", account_generation=1, source_generation=1)
    ref.set(control.model_dump(mode="json"))
    return control


def _ordered_capture_devices_from_evidence(raw_evidence: List[Payload]) -> tuple[List[str], Optional[str]]:
    """Unique capture device ids ordered by earliest evidence created_at, then list order."""
    keyed: list[tuple[SortKey, str]] = []
    for index, raw in enumerate(raw_evidence or []):
        device_id = raw.get("client_device_id")
        if not device_id:
            artifact_ref = _payload_or_empty(raw.get("artifact_ref"))
            device_id = artifact_ref.get("client_device_id")
        if not isinstance(device_id, str) or not device_id:
            continue
        created_at = raw.get("created_at")
        if isinstance(created_at, datetime):
            sort_key = (0, created_at)
        elif isinstance(created_at, str) and created_at.strip():
            try:
                sort_key = (0, datetime.fromisoformat(created_at.replace("Z", "+00:00")))
            except ValueError:
                sort_key = (1, index)
        else:
            sort_key = (1, index)
        keyed.append((sort_key, device_id))

    keyed.sort(key=lambda item: item[0])
    device_ids: List[str] = []
    seen: set[str] = set()
    for _, device_id in keyed:
        if device_id in seen:
            continue
        seen.add(device_id)
        device_ids.append(device_id)
    return device_ids, (device_ids[0] if device_ids else None)


def _legacy_evidence_to_memory(evidence_data: Dict[str, Any], *, conversation_id: Optional[str]) -> MemoryEvidence:
    source_id = (
        evidence_data.get("source_id")
        or conversation_id
        or (f"external:{evidence_data['evidence_id']}" if evidence_data.get("evidence_id") else None)
    )
    client_device_id = evidence_data.get("client_device_id")
    if not client_device_id:
        artifact_ref = _payload_or_empty(evidence_data.get("artifact_ref"))
        client_device_id = artifact_ref.get("client_device_id")
    if not isinstance(client_device_id, str):
        client_device_id = None
    return MemoryEvidence(
        evidence_id=evidence_data["evidence_id"],
        source_type=evidence_data.get("source_type") or "conversation",
        source_id=source_id,
        source_version="v1",
        conversation_id=(
            conversation_id if (evidence_data.get("source_type") or "conversation") == "conversation" else None
        ),
        artifact_preservation=ArtifactPreservationState.preserved,
        client_device_id=client_device_id,
    )


_PRESERVED_EVIDENCE_SECURITY_FIELDS = (
    "redaction_status",
    "provenance_visibility",
    "encryption_or_redaction_status",
)


def _preserved_evidence_security_fields(existing_data: Dict[str, Any]) -> Dict[str, Any]:
    """Carry forward security/redaction fields when reactivating evidence on reprocess."""
    preserved: Dict[str, Any] = {}
    for field in _PRESERVED_EVIDENCE_SECURITY_FIELDS:
        value = existing_data.get(field)
        if value is None:
            continue
        if field == "redaction_status":
            preserved[field] = value if isinstance(value, RedactionStatus) else RedactionStatus(value)
        elif field == "provenance_visibility":
            preserved[field] = value if isinstance(value, ProvenanceVisibility) else ProvenanceVisibility(value)
        elif field == "encryption_or_redaction_status":
            preserved[field] = value if isinstance(value, RedactionStatus) else RedactionStatus(value)
    return preserved


def _persist_evidence(uid: str, evidence: MemoryEvidence, *, db_client: Any) -> None:
    collections = MemoryCollections(uid=uid)
    path = f"{collections.memory_evidence}/{evidence.evidence_id}"
    ref = db_client.document(path)
    snapshot = ref.get()
    reactivation_updates: Dict[str, Any] = {
        "source_state": SourceState.active,
        "source_state_reason": None,
    }
    if getattr(snapshot, "exists", False):
        reactivation_updates.update(_preserved_evidence_security_fields(_snapshot_payload(snapshot)))
    active_evidence = evidence.model_copy(update=reactivation_updates)
    ref.set(active_evidence.model_dump(mode="json"))


def _bump_source_generation(uid: str, *, db_client: Any) -> MemoryControlState:
    """Advance source_generation so re-extract gets a fresh operation identity space (Q7)."""
    return atomic_bump_source_generation(uid, db_client=db_client)


def _resolve_initial_tier_value(data: Dict[str, Any]) -> str:
    raw_tier = data.get("memory_tier")
    if raw_tier is not None:
        if hasattr(raw_tier, "value"):
            return raw_tier.value
        return str(raw_tier)
    durability = data.get("durability")
    if (durability or "").lower() == MemoryLayer.long_term.value:
        return MemoryLayer.long_term.value
    if _user_asserted_from_payload(data):
        return MemoryLayer.short_term.value
    return decide_initial_memory_tier(False, durability).value


def _visibility_from_payload(data: Dict[str, Any]) -> str:
    visibility = (data.get("visibility") or "private").strip()
    return visibility if visibility in {"public", "private"} else "private"


def _user_asserted_from_payload(data: Dict[str, Any]) -> bool:
    if "manually_added" in data:
        return bool(data.get("manually_added"))
    return bool(data.get("user_asserted"))


def _product_metadata_from_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {}
    category = data.get("category")
    if category is not None:
        metadata["category"] = category.value if hasattr(category, "value") else str(category)
    tags = data.get("tags")
    if tags:
        metadata["tags"] = list(tags)
    return metadata


def _apply_product_metadata(item: MemoryItem, metadata: Dict[str, Any]) -> MemoryItem:
    if not metadata:
        return item
    promotion = dict(item.promotion or {})
    promotion.update(metadata)
    return item.model_copy(update={"promotion": promotion})


def _validate_memory_item_for_write(item: MemoryItem) -> MemoryItem:
    item = MemoryItem.model_validate(item.model_dump(mode="python"))
    if item.visibility not in _ALLOWED_MEMORY_VISIBILITIES:
        raise ValueError("visibility must be private, public, or shared")
    return item


def _persist_memory_item(uid: str, item: MemoryItem, *, db_client: Any) -> None:
    item = _validate_memory_item_for_write(item)
    path = f"{MemoryCollections(uid=uid).memory_items}/{item.memory_id}"
    db_client.document(path).set(item.model_dump(mode="json"))


def _validated_memory_item_copy(item: MemoryItem, updates: Dict[str, Any]) -> MemoryItem:
    payload = item.model_dump(mode="python")
    payload.update(updates)
    return _validate_memory_item_for_write(MemoryItem.model_validate(payload))


def _evidence_items_from_payload(data: Dict[str, Any]) -> List[MemoryEvidence]:
    conversation_id = data.get("conversation_id")
    evidence_items: List[MemoryEvidence] = []
    raw_evidence: object = data.get("evidence") or []
    for raw in cast(List[object], raw_evidence):
        raw_payload = _payload_or_empty(raw)
        if raw_payload.get("evidence_id"):
            evidence_items.append(_legacy_evidence_to_memory(raw_payload, conversation_id=conversation_id))
    if evidence_items:
        return evidence_items

    memory_id = data.get("id") or "pending"
    source_id = conversation_id or data.get("app_id") or f"external:{memory_id}"
    manually_added = bool(data.get("manually_added"))
    if conversation_id:
        source_type = "conversation"
    elif data.get("app_id"):
        source_type = f"integration:{data['app_id']}"
    else:
        source_type = "api"
    source_signal = "manual" if manually_added else "api"
    evidence = Evidence.from_source(
        source_id=source_id,
        source_type=source_type,
        source_signal=source_signal,
        extractor_id=data.get("extractor_id") or ("manual_note" if manually_added else "external_write"),
        extractor_version="v1",
        artifact_ref=data.get("artifact_ref") or {},
        independence_group=source_id,
    )
    return [_legacy_evidence_to_memory(evidence.dict(), conversation_id=conversation_id)]


def _read_canonical_memory_item(uid: str, memory_id: str, *, db_client: Any) -> Optional[MemoryItem]:
    path = f"{MemoryCollections(uid=uid).memory_items}/{memory_id}"
    snapshot = db_client.document(path).get()
    if not getattr(snapshot, "exists", False):
        return None
    item = MemoryItem(**_snapshot_payload(snapshot))
    if item.status != MemoryItemStatus.active:
        return None
    if item.memory_id != memory_id:
        raise ValueError(f"canonical memory id mismatch: requested {memory_id}, found {item.memory_id}")
    return item


def read_canonical_memory_item(uid: str, memory_id: str, *, db_client: Any = None) -> Optional[MemoryItem]:
    """Read one active canonical memory item from the authoritative product store."""
    client = db_client if db_client is not None else default_db_client
    return _read_canonical_memory_item(uid, memory_id, db_client=client)


def write_canonical_extraction_memory(uid: str, data: Dict[str, Any], *, db_client: Any = None) -> str:
    """Persist one memory to memory_items + ledger (extraction or external/manual writes)."""
    client = db_client if db_client is not None else default_db_client
    content = (data.get("content") or "").strip()
    if not content:
        raise ValueError("canonical write requires non-empty content")

    conversation_id = data.get("conversation_id")
    source_id = conversation_id or data.get("id") or "unknown"
    memory_id = data.get("id") or extraction_memory_id(uid=uid, source_id=source_id, content=content)
    idempotency_key = deterministic_contract_id(
        "canonical-extraction-idempotency",
        {"uid": uid, "source_id": source_id, "content": content},
    )

    evidence_items = _evidence_items_from_payload(data)

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
    op_ref = client.document(f"{MemoryCollections(uid=uid).memory_operations}/{operation.operation_id}")
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
        "initial_tier": _resolve_initial_tier_value(data),
        "visibility": _visibility_from_payload(data),
        "user_asserted": _user_asserted_from_payload(data),
    }
    if isinstance(data.get("promotion"), dict):
        patch_payload["promotion"] = dict(data["promotion"])
    if data.get("subject_entity_id"):
        patch_payload["subject_entity_id"] = data["subject_entity_id"]
    if data.get("predicate"):
        patch_payload["predicate"] = data["predicate"]
    if data.get("arguments"):
        patch_payload["arguments"] = data["arguments"]

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
    if item is None and result.status == ApplyStatus.idempotent_skip:
        snapshot = client.document(f"{MemoryCollections(uid=uid).memory_items}/{committed_id}").get()
        if getattr(snapshot, "exists", False):
            item = MemoryItem(**_snapshot_payload(snapshot))

    if item is not None:
        product_metadata = _product_metadata_from_payload(data)
        if product_metadata:
            item = _apply_product_metadata(item, product_metadata)
            _persist_memory_item(uid, item, db_client=client)
        assert_legal_state(
            DomainMemoryLayer(item.tier.value),
            physical_status_to_record_status(item.status.value),
            MemoryProcessingState(item.processing_state.value),
        )
        raw_evidence = [
            cast(Payload, raw) for raw in cast(List[object], data.get("evidence") or []) if isinstance(raw, dict)
        ]
        device_ids, primary_device = _ordered_capture_devices_from_evidence(raw_evidence)
        if device_ids:
            item_ref = client.document(f"{MemoryCollections(uid=uid).memory_items}/{item.memory_id}")
            item_ref.set(
                {
                    "capture_device_ids": device_ids,
                    "primary_capture_device": primary_device,
                },
                merge=True,
            )
            item = item.model_copy(
                update={
                    "capture_device_ids": device_ids,
                    "primary_capture_device": primary_device,
                }
            )
        sync_atom_keyword_index_for_item(item, db_client=client)
        sync_canonical_memory_vector(item)

    return committed_id


def write_canonical_external_memory(uid: str, data: Dict[str, Any], *, db_client: Any = None) -> str:
    """Persist a manual/API/integration memory via the canonical apply path."""
    return write_canonical_extraction_memory(uid, data, db_client=db_client)


def update_canonical_memory_content(uid: str, memory_id: str, content: str, *, db_client: Any = None) -> MemoryItem:
    client = db_client if db_client is not None else default_db_client
    item = _read_canonical_memory_item(uid, memory_id, db_client=client)
    if item is None:
        raise ValueError(f"canonical memory not found: {memory_id}")
    trimmed = (content or "").strip()
    if not trimmed:
        raise ValueError("canonical update requires non-empty content")
    now = datetime.now(timezone.utc)
    updated = _validated_memory_item_copy(item, {"content": trimmed, "updated_at": now, "user_asserted": True})
    _persist_memory_item(uid, updated, db_client=client)
    if (
        updated.tier == MemoryLayer.long_term
        and getattr(updated, "kg_extracted", False)
        and resolve_memory_system(uid, db_client=client) == MemorySystem.CANONICAL
    ):
        invalidate_kg_for_memory_retraction(uid, [memory_id], db_client=client)
        updated = _validated_memory_item_copy(updated, {"kg_extracted": False, "updated_at": now})
        client.document(f"{MemoryCollections(uid=uid).memory_items}/{memory_id}").set(
            {"kg_extracted": False, "updated_at": now},
            merge=True,
        )
        from utils.memory.canonical_kg_promotion import extract_kg_for_promoted_memory

        kg_result = extract_kg_for_promoted_memory(uid, updated, db_client=client)
        if kg_result.success:
            updated = _validated_memory_item_copy(updated, {"kg_extracted": True})
    sync_atom_keyword_index_for_item(updated, db_client=client)
    sync_canonical_memory_vector(updated)
    return updated


def update_canonical_memory_visibility(
    uid: str, memory_id: str, visibility: str, *, db_client: Any = None
) -> MemoryItem:
    client = db_client if db_client is not None else default_db_client
    item = _read_canonical_memory_item(uid, memory_id, db_client=client)
    if item is None:
        raise ValueError(f"canonical memory not found: {memory_id}")
    now = datetime.now(timezone.utc)
    updated = _validated_memory_item_copy(item, {"visibility": visibility, "updated_at": now})
    _persist_memory_item(uid, updated, db_client=client)
    sync_atom_keyword_index_for_item(updated, db_client=client)
    sync_canonical_memory_vector(updated)
    return updated


def update_canonical_memory_review(uid: str, memory_id: str, value: bool, *, db_client: Any = None) -> MemoryItem:
    client = db_client if db_client is not None else default_db_client
    item = _read_canonical_memory_item(uid, memory_id, db_client=client)
    if item is None:
        raise ValueError(f"canonical memory not found: {memory_id}")
    now = datetime.now(timezone.utc)
    promotion = dict(item.promotion or {})
    promotion["reviewed"] = True
    promotion["user_review"] = value
    updated = _validated_memory_item_copy(item, {"promotion": promotion, "updated_at": now})
    _persist_memory_item(uid, updated, db_client=client)
    return updated


def update_canonical_memory_product_fields(
    uid: str,
    memory_id: str,
    *,
    tags: Optional[List[str]] = None,
    category: Optional[str] = None,
    db_client: Any = None,
) -> MemoryItem:
    client = db_client if db_client is not None else default_db_client
    item = _read_canonical_memory_item(uid, memory_id, db_client=client)
    if item is None:
        raise ValueError(f"canonical memory not found: {memory_id}")
    metadata: Dict[str, Any] = {}
    if tags is not None:
        metadata["tags"] = list(tags)
    if category is not None:
        metadata["category"] = category
    if not metadata:
        return item
    now = datetime.now(timezone.utc)
    updated = _validated_memory_item_copy(_apply_product_metadata(item, metadata), {"updated_at": now})
    _persist_memory_item(uid, updated, db_client=client)
    return updated


def _item_sourced_from_conversation(item: MemoryItem, conversation_id: str) -> bool:
    for evidence in item.evidence:
        if evidence.source_id == conversation_id:
            return True
        if evidence.conversation_id == conversation_id:
            return True
    return False


def _tombstone_memory_item(uid: str, item: MemoryItem, *, db_client: Any, reason: str) -> None:
    collections = MemoryCollections(uid=uid)
    now = datetime.now(timezone.utc)
    trusted = read_memory_v3_trusted_account_generation(uid=uid, db_client=db_client)
    account_generation = trusted.account_generation if trusted.read_error_reason is None else 1
    projection_commit_id = trusted.head_commit_id or "head0"

    tombstoned_evidence: List[MemoryEvidence] = []
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

    updated_item = _validated_memory_item_copy(
        item,
        {
            "status": MemoryItemStatus.tombstoned,
            "source_state": SourceState.tombstoned,
            "content": None,
            "evidence": tombstoned_evidence,
            "updated_at": now,
        },
    )
    _persist_memory_item(uid, updated_item, db_client=db_client)

    purge_candidates = [
        {
            "vector_id": neutral_vector_id_for_memory(item.memory_id),
            "memory_id": item.memory_id,
            "reason": reason,
            "required_projection_commit_id": projection_commit_id,
            "required_account_generation": account_generation,
            "authoritative_account_generation": account_generation,
        }
    ]
    for record in build_vector_repair_purge_outbox_records(uid=uid, candidates=purge_candidates):
        db_client.document(record["outbox_path"]).set(record)

    delete_canonical_memory_vector(uid, item.memory_id)
    delete_atom_keyword_doc(uid, item.memory_id, db_client=db_client)
    purge_stale_review_conflicts_for_memories(uid, [item.memory_id], reason=reason, db_client=db_client)


def retract_conversation_sourced_memories(uid: str, conversation_id: str, *, db_client: Any = None) -> Dict[str, Any]:
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
    invalidate_kg_for_memory_retraction(uid, retracted_ids, db_client=client)

    return {
        "retracted_memory_ids": retracted_ids,
        "vector_delete_ids": retracted_ids,
        "tombstoned_evidence_ids": [],
        "source_generation": bumped_control.source_generation,
    }


def delete_canonical_memory(uid: str, memory_id: str, *, db_client: Any = None) -> None:
    client = db_client if db_client is not None else default_db_client
    item = _read_canonical_memory_item(uid, memory_id, db_client=client)
    if item is None:
        raise ValueError(f"canonical memory not found: {memory_id}")
    _tombstone_memory_item(uid, item, db_client=client, reason="canonical_memory_delete")
    invalidate_kg_for_memory_retraction(uid, [memory_id], db_client=client)


def delete_all_canonical_memories(uid: str, *, db_client: Any = None) -> None:
    client = db_client if db_client is not None else default_db_client
    items = fetch_authoritative_product_memory_items(uid=uid, db_client=client)
    deleted_ids: List[str] = []
    for item in items:
        if item.status == MemoryItemStatus.active:
            _tombstone_memory_item(uid, item, db_client=client, reason="canonical_memory_delete_all")
            deleted_ids.append(item.memory_id)
    if deleted_ids:
        invalidate_kg_for_memory_retraction(uid, deleted_ids, db_client=client)


def purge_canonical_derived_user_data(uid: str, *, db_client: Any = None) -> Dict[str, Any]:
    """Best-effort purge of canonical Pinecone vectors, keyword index, and KG data.

    Purges based on existing canonical artifacts (memory_items docs) rather than
    current cohort membership, so a canonical user removed from
    ``CANONICAL_MEMORY_USERS`` for rollback/kill-switch before account deletion
    still has their derived data cleaned up. Legacy users have no canonical
    memory_items docs, so the purge is inert for them.
    """
    client = db_client if db_client is not None else default_db_client
    items = fetch_authoritative_product_memory_items(uid=uid, db_client=client)
    if not items:
        return {"purged": False, "reason": "not_canonical_cohort", "vector_ids": [], "memory_ids": []}

    memory_ids = [item.memory_id for item in items]
    vector_ids = [neutral_vector_id_for_memory(memory_id) for memory_id in memory_ids]

    if vector_ids:
        from database.vector_db import delete_pinecone_memory_vectors_by_id

        vector_deleted = delete_pinecone_memory_vectors_by_id(vector_ids)
        if vector_deleted < len(vector_ids):
            raise RuntimeError(f"canonical vector purge only deleted {vector_deleted}/{len(vector_ids)} vectors")

    keyword_deleted = purge_user_atom_keyword_index(uid, db_client=client, force=True, raise_on_failure=True)
    kg_db.delete_knowledge_graph(uid, db_client=client)

    trusted = read_memory_v3_trusted_account_generation(uid=uid, db_client=client)
    account_generation = trusted.account_generation if trusted.read_error_reason is None else 1
    projection_commit_id = trusted.head_commit_id or "head0"
    for item in items:
        purge_candidates = [
            {
                "vector_id": neutral_vector_id_for_memory(item.memory_id),
                "memory_id": item.memory_id,
                "reason": "account_delete_canonical_purge",
                "required_projection_commit_id": projection_commit_id,
                "required_account_generation": account_generation,
                "authoritative_account_generation": account_generation,
            }
        ]
        for record in build_vector_repair_purge_outbox_records(uid=uid, candidates=purge_candidates):
            client.document(record["outbox_path"]).set(record)

    return {
        "purged": True,
        "reason": "canonical_artifacts_found",
        "vector_ids": vector_ids,
        "memory_ids": memory_ids,
        "keyword_docs_deleted": keyword_deleted,
    }
