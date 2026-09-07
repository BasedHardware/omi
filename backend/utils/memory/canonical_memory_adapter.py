"""Thin adapter over canonical apply/read services for the universal MemoryService."""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Collection, Dict, List, Optional, Sequence, Tuple, cast

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from database._client import db as default_db_client
from database import knowledge_graph as kg_db
from database.firestore_index_registry import UNIVERSAL_CANONICAL_LIST_SCAN_QUERY
from database.review_queue import purge_stale_review_conflicts_for_memories
from utils.client_device import DeviceScopeRequest
from utils.memory.device_scope_filter import filter_items_by_device_scope
from utils.memory.canonical_lineage import (
    canonical_lineage_root,
    canonical_lineage_survivor_sort_key,
    collapse_canonical_lineages,
)
from utils.memory.canonical_visibility_filter import filter_canonical_default_visible_items
from utils.memory.belief_model import (
    SUBJECT_SCOPE_ALIASES,
    belief_model_enabled,
    horizon_from_extraction,
    public_belief_overlay,
    public_belief_overlay_json,
    subject_scope_from_extraction,
)
from database.memory_collections import MemoryCollections
from database.memory_apply_store import (
    CanonicalApplyWrite,
    CanonicalMemoryTombstoneConflict,
    CanonicalMemoryTombstoneLimitError,
    CanonicalReviewResolution,
    CanonicalReviewResolutionConflict,
    ConversationSourceReplacementConflict,
    apply_direct_user_long_term_patch_firestore,
    apply_long_term_patch_firestore,
    read_trigger_feedback_replay_firestore,
    replace_conversation_source_firestore,
    tombstone_memory_items_firestore,
    privacy_deletion_receipt_id,
)
from database.legal_holds import (
    LegalHoldAuthorityUnavailable,
    current_destructive_operation_token,
    destructive_operation_gate,
)
from database.memory_vector_repair_outbox import build_vector_repair_purge_outbox_records
from database.memory_vector_metadata import canonical_memory_provider_id
from database.account_deletion_projection_fence import read_account_deletion_projection_fence
from utils.other.list_budget import ListReadBudget, budgeted_document_get, budgeted_stream_list
from models.memory_domain import (
    MemoryLayer as DomainMemoryLayer,
    MemoryProcessingState,
    assert_legal_state,
    physical_status_to_record_status,
)
from models.memory_evidence import (
    ArtifactRef,
    ArtifactPreservationState,
    MemoryEvidence,
    SourceState,
)
from models.memories import Evidence, MemoryDB, MemoryCategory, SubjectAttribution, decide_initial_memory_tier
from models.memory_apply import (
    ApplyResult,
    ApplyStatus,
    MemoryControlState,
    MemoryWriterClass,
    apply_long_term_patch_transaction,
    build_patch_mutation_identity,
    require_writer_admitted,
)
from models.memory_contracts import DurablePatchDecision, LifecycleState, deterministic_contract_id
from models.memory_operations import MemoryLedgerReopenReceipt, MemoryOperation, MemoryOperationType
from models.memory_source_replacement import ConversationSourceReplacementReceipt
from models.jit_trigger_feedback import JITTriggerFeedbackReceipt
from models.product_memory import (
    LedgerWriteReason,
    MAX_MEMORY_ARGUMENTS_JSON_BYTES,
    MemoryAccessPolicy,
    MemoryItemStatus,
    MemoryKind,
    MemoryLayer,
    MemorySubjectScope,
    ProcessingState,
    MemoryItem,
    is_archive_access_eligible,
)
from utils.memory.short_term_lifecycle import default_short_term_expiry
from utils.memory.required_promotion import (
    REQUIRED_PROCESSING_STATUS_PENDING,
    REQUIRED_PROCESSING_STATUS_REJECTED,
    REQUIRED_PROCESSOR_ID,
    REQUIRED_PROCESSOR_VERSION,
    REQUIRED_PROMOTION_STATUS_PENDING,
)
from utils.memory.memory_system import ensure_canonical_apply_control_state
from utils.memory.jit_trigger_contract import TriggerFeedback, TriggerFeedbackAction, apply_trigger_feedback
from utils.retrieval.hybrid import rrf_rerank
from utils.memory.canonical_vector_sync import delete_canonical_memory_vector
from utils.memory.product_memory_read_service import (
    fetch_authoritative_product_memory_items,
    fetch_authoritative_product_memory_items_by_ids,
    fetch_authoritative_product_memory_items_for_source,
    fetch_authoritative_superseded_memory_items_for_targets,
)
from utils.memory.v3.account_generation_source import read_memory_v3_trusted_account_generation

logger = logging.getLogger(__name__)

# Canonical item identity remains ``memory_id``. Shared external providers use
# a user-scoped opaque projection id so one account can never overwrite another.

_ALLOWED_MEMORY_VISIBILITIES = {"private", "public", "shared"}
Payload = Dict[str, Any]
SortKey = tuple[int, datetime | int]
UserMutationPatchBuilder = Callable[[MemoryItem, datetime], Tuple[Payload, Payload]]
_LEDGER_WRITE_AUTHORITY = object()
_DIRECT_USER_LEDGER_WRITE_AUTHORITY = object()
_DIRECT_USER_LEDGER_EVIDENCE_TYPES = {
    "explicit_user_statement",
    "explicit_user_correction",
    "explicit_user_reopen",
    "explicit_user_revert",
}


def mint_direct_user_write_authority() -> object:
    """Mint the in-process capability held by authenticated user routes.

    The returned object carries no user data and is intentionally checked by
    identity.  Internal integration and extraction callers cannot opt into
    the direct-user ledger seam by setting a payload field.
    """

    return _DIRECT_USER_LEDGER_WRITE_AUTHORITY


def is_direct_user_write_authority(value: object | None) -> bool:
    """Return whether ``value`` is the route-minted direct-user capability."""

    return value is _DIRECT_USER_LEDGER_WRITE_AUTHORITY


# ``knowledge_ledger`` imports this adapter, so the wire discriminator cannot
# be imported back without a cycle. Keep this private copy contract-tested.
_LEDGER_SCHEMA_VERSION = "knowledge_ledger.v1"

# Concurrent same-account canonical writes race the account-global control
# CAS inside the conversation source replacement. Retraction — the delete and
# merge path — converges across those races instead of failing (#11726).
_RETRACT_CONFLICT_ATTEMPTS = 5
_RETRACT_CONFLICT_BACKOFF_SECONDS = (0.05, 0.1, 0.25, 0.5)
# Extraction races the same control CAS but runs inside conversation processing,
# which has no outer convergence loop: an immediate retry re-reads the control a
# peer just advanced, so same-account writers keep losing in lockstep and the
# whole enrichment fails. Back the replacement's own rounds off by default.
_REPLACEMENT_CONFLICT_BACKOFF_SECONDS = (0.05, 0.1, 0.25, 0.5)
# Retraction already wraps this call in the converging loop above; keeping its
# inner rounds immediate stops the delete path's latency budget being multiplied.
_IMMEDIATE_REPLACEMENT_RETRY_BACKOFF = (0.0, 0.0)
_SETTLED_PROMOTION_FIELDS = frozenset(
    {
        "route",
        "reconciliation",
        "target_memory_id",
        "relationship_to_user",
        "aboutness",
        "basis_for_memory",
        "confidence",
        "rationale",
        "processed_at",
        "processed_by",
        "from_tier",
        "to_tier",
        "promoted_at",
        "graph_plan",
        "admission_receipt",
    }
)


class CanonicalBatchMutationLimitError(ValueError):
    """Raised before commit when a canonical batch cannot fit one transaction."""


class CanonicalMemoryNotFoundError(ValueError):
    """Raised when an item is absent or already tombstoned during an atomic batch read."""


class ConversationReplacementConflictError(RuntimeError):
    """Conversation source replacement exhausted its bounded conflict retries.

    Subclasses :class:`RuntimeError` so pre-existing callers keep their
    ``except RuntimeError`` contract. Callers that can retry the operation —
    cascade delete, merge — get a typed signal instead of an opaque 500
    (#11726).
    """


def _payload_or_empty(value: object) -> Payload:
    return cast(Payload, value) if isinstance(value, dict) else {}


def _bounded_memory_arguments(value: object) -> Dict[str, Any]:
    """Project only JSON-safe proposition arguments within the graph bound.

    ``MemoryItem.arguments`` is typed as a JSON-shaped mapping, but the
    historical model predates a serialized-size validator on that field. Keep
    the released MemoryDB projection bounded and fail closed for malformed or
    oversized nested values rather than emitting an unbounded payload.
    """

    if not isinstance(value, dict):
        return {}
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        if len(encoded.encode("utf-8")) > MAX_MEMORY_ARGUMENTS_JSON_BYTES:
            return {}
        return copy.deepcopy(value)
    except (TypeError, ValueError, OverflowError, RecursionError):
        return {}


def _snapshot_payload(snapshot: Any) -> Payload:
    return _payload_or_empty(snapshot.to_dict() if getattr(snapshot, "exists", False) else {})


def _clear_settled_promotion_route(promotion: Payload) -> Payload:
    """Return pending metadata without a stale terminal consolidation decision."""
    for field in _SETTLED_PROMOTION_FIELDS:
        promotion.pop(field, None)
    return promotion


def invalidate_kg_for_memory_retraction(uid: str, memory_ids: List[str], *, db_client: Any = None) -> None:
    """Prune retracted/superseded memory citations from the user's KG."""
    if not memory_ids:
        return
    client = db_client if db_client is not None else default_db_client
    pruned = kg_db.prune_memory_citations_from_kg(uid, memory_ids, db_client=client)
    logger.info(
        "kg_citations_pruned uid=%s retracted_memory_count=%d pruned_entities=%d",
        uid,
        len(memory_ids),
        pruned,
    )


def extraction_memory_id(
    *,
    uid: str,
    source_id: str,
    content: str,
    subject_entity_id: Optional[str] = None,
) -> str:
    """Hash-derived neutral memory id, partitioned by non-default subject."""
    identity = {"uid": uid, "source_id": source_id, "content": (content or "").strip()}
    normalized_subject = (subject_entity_id or "").strip()
    if normalized_subject and normalized_subject != "user":
        identity["subject_entity_id"] = normalized_subject
    return (
        "mem_"
        + deterministic_contract_id(
            "canonical-extraction-memory",
            identity,
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
        is_locked=bool(item.get("is_locked", False)),
        visibility=item.get("visibility") or "private",
        memory_tier=tier,
        valid_at=updated_at,
        ledger_schema_version=item.get("ledger_schema_version"),
        kind=item.get("kind"),
        subject_scope=item.get("subject_scope"),
        slot=item.get("slot"),
        curation_weight=int(item.get("curation_weight") or 0),
        intent_backed=bool(item.get("intent_backed", False)),
        write_reason=item.get("write_reason"),
    )


def memory_item_to_memorydb(item: MemoryItem) -> MemoryDB:
    """Map authoritative memory memory_items row to legacy MemoryDB response shape."""
    conversation_id = None
    evidence_payload: List[Payload] = []
    promotion = item.promotion or {}
    raw_submission = promotion.get("submission")
    raw_receipt = promotion.get("processing_receipt")
    submission: Payload = cast(Payload, raw_submission) if isinstance(raw_submission, dict) else {}
    receipt: Payload = cast(Payload, raw_receipt) if isinstance(raw_receipt, dict) else {}
    for evidence in item.evidence:
        artifact_ref = evidence.artifact_refs[0].model_dump(mode="json") if evidence.artifact_refs else {}
        evidence_payload.append(
            {
                "evidence_id": evidence.evidence_id,
                "source_id": evidence.source_id,
                "source_type": evidence.source_type,
                "source_signal": "manual" if item.user_asserted else str(submission.get("source_surface") or "api"),
                "extractor_id": receipt.get("processor_id") or "canonical_memory_adapter",
                "extractor_version": receipt.get("processor_version") or "v1",
                "artifact_ref": artifact_ref,
                "capture_confidence": 0.5,
                "independence_group": evidence.source_id or evidence.source_type,
                "redaction_status": evidence.redaction_status.value,
                "created_at": item.captured_at,
                "client_device_id": evidence.client_device_id,
            }
        )
        if evidence.source_type == "conversation" and evidence.source_id:
            conversation_id = evidence.source_id

    category_raw = promotion.get("category", MemoryCategory.interesting.value)
    try:
        category = MemoryCategory(category_raw)
    except ValueError:
        category = MemoryCategory.interesting
    tags = list(promotion.get("tags") or [])
    reviewed = bool(promotion.get("reviewed", False))
    is_baseline = bool(promotion.get("is_baseline", False))
    is_locked = bool(promotion.get("is_locked", False))
    is_read = bool(promotion.get("is_read", False))
    is_dismissed = bool(promotion.get("is_dismissed", False))
    user_review = promotion.get("user_review")
    source_attribution = _payload_or_empty(promotion.get("source_attribution"))
    raw_subject_attribution = source_attribution.get("subject_attribution", SubjectAttribution.unknown.value)
    try:
        subject_attribution = SubjectAttribution(raw_subject_attribution)
    except (TypeError, ValueError):
        subject_attribution = SubjectAttribution.unknown

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
        is_baseline=is_baseline,
        is_locked=is_locked,
        is_read=is_read,
        is_dismissed=is_dismissed,
        user_review=user_review,
        visibility=item.visibility,
        evidence=evidence_payload,
        memory_tier=item.tier,
        primary_capture_device=item.primary_capture_device,
        capture_device_ids=item.capture_device_ids or [],
        subject_entity_id=item.subject_entity_id,
        subject_attribution=subject_attribution,
        ledger_schema_version=item.ledger_schema_version,
        kind=item.kind if item.ledger_schema_version else None,
        subject_scope=item.subject_scope if item.ledger_schema_version else None,
        slot=item.slot,
        body=item.body,
        valid_at=item.valid_from or item.captured_at,
        invalid_at=item.valid_to,
        superseded_by=item.superseded_by,
        canonical_memory_id=item.canonical_memory_id,
        ledger_status=item.status if item.ledger_schema_version else None,
        curation_weight=item.curation_weight,
        trigger_condition=item.trigger_condition,
        # MemoryItem validates this as a JSON object; preserve the canonical
        # proposition arguments for ledger mirrors instead of silently
        # degrading entity/alias context to content-only text.
        arguments=_bounded_memory_arguments(item.arguments),
        intent_backed=item.intent_backed,
        write_reason=item.write_reason,
        **public_belief_overlay(item, now=datetime.now(timezone.utc)),
    )


def _canonical_lineage_root(item: MemoryItem, *, items_by_id: Dict[str, MemoryItem]) -> str:
    """Resolve one item to its authoritative alias target without trusting cycles."""
    return canonical_lineage_root(item, items_by_id=items_by_id)


def _lineage_survivor_sort_key(item: MemoryItem, *, lineage_root: str) -> tuple[int, int, float, str]:
    """Prefer the Long-term canonical survivor, then the newest deterministic row."""
    return canonical_lineage_survivor_sort_key(item, lineage_root=lineage_root)


def _deduplicate_canonical_items(
    items: List[MemoryItem],
    *,
    lineage_context: Optional[List[MemoryItem]] = None,
) -> List[MemoryItem]:
    """Collapse default-read aliases without moving a lineage behind its freshest evidence."""
    return collapse_canonical_lineages(
        items,
        lineage_context=lineage_context,
        survivor_context=items,
    )


def _deduplicate_canonical_search_candidates(
    candidates: List[Payload],
    *,
    lineage_items_by_id: Dict[str, MemoryItem],
    survivor_items_by_id: Dict[str, MemoryItem],
) -> List[Payload]:
    """Collapse alias lineages while preserving the best query position for each."""
    grouped: Dict[str, List[tuple[int, Payload]]] = {}
    for position, candidate in enumerate(candidates):
        item = cast(MemoryItem, candidate["item"])
        lineage_root = _canonical_lineage_root(item, items_by_id=lineage_items_by_id)
        grouped.setdefault(lineage_root, []).append((position, candidate))

    deduplicated: List[tuple[int, Payload]] = []
    for lineage_root, entries in grouped.items():
        candidate_items = {cast(MemoryItem, candidate["item"]).memory_id: candidate for _, candidate in entries}
        canonical_item = survivor_items_by_id.get(lineage_root)
        if canonical_item is not None:
            candidate_items.setdefault(
                canonical_item.memory_id,
                {
                    "id": canonical_item.memory_id,
                    "content": canonical_item.content or "",
                    "category": "interesting",
                    "vector_score": 0.0,
                    "item": canonical_item,
                },
            )
        survivor = min(
            (cast(MemoryItem, candidate["item"]) for candidate in candidate_items.values()),
            key=lambda item: _lineage_survivor_sort_key(item, lineage_root=lineage_root),
        )
        selected = dict(candidate_items[survivor.memory_id])
        selected["vector_score"] = max(float(candidate.get("vector_score", 0.0)) for _, candidate in entries)
        deduplicated.append((min(position for position, _ in entries), selected))

    deduplicated.sort(key=lambda entry: (entry[0], cast(MemoryItem, entry[1]["item"]).memory_id))
    return [candidate for _, candidate in deduplicated]


def _canonical_search_result_sort_key(candidate: Payload) -> tuple[float, float, float, str]:
    """Make hybrid-score ties stable while allowing fresh unique Short-term evidence."""
    item = cast(MemoryItem, candidate["item"])
    return (
        -float(candidate.get("_hybrid_score", 0.0)),
        -float(candidate.get("vector_score", 0.0)),
        -item.updated_at.timestamp(),
        item.memory_id,
    )


def read_canonical_memories(
    uid: str,
    *,
    limit: int = 100,
    offset: int = 0,
    db_client: Any = None,
    device_scope_request: Optional[DeviceScopeRequest] = None,
    include_pending_processing: bool = False,
    include_archive: bool = False,
    now: Optional[datetime] = None,
    budget: Optional[ListReadBudget] = None,
) -> List[MemoryDB]:
    """Read canonical items, optionally exposing explicit pending submissions.

    Pending text is withheld by default so agent/chat consumers cannot use raw
    submissions. Dedicated memory-list APIs opt in and display those records as
    Short-term while processing is underway.

    Archive rows stay excluded unless ``include_archive`` is an explicit owner
    opt-in. That flag is the only way this default list gains
    ``archive_capability``; chat/MCP archive routes keep their own grants.
    With a ``budget`` the authoritative item stream runs under the request's
    per-RPC timeout and charges every fetched row (#11831).
    """
    client = db_client if db_client is not None else default_db_client
    device_scope = device_scope_request.device_scope if device_scope_request else "all"
    client_device_id = device_scope_request.client_device_id if device_scope_request else None
    items = fetch_authoritative_product_memory_items(uid=uid, db_client=client, budget=budget)
    current_time = now or datetime.now(timezone.utc)
    archive_explicit = bool(include_archive)
    policy = MemoryAccessPolicy.for_omi_chat(archive_capability=archive_explicit)
    visible = filter_canonical_default_visible_items(items, policy=policy, now=current_time)
    visible_by_id = {item.memory_id: item for item in visible}
    if archive_explicit:
        for item in items:
            # MemoryLayer.archive is visible only with archive_capability + explicit opt-in.
            if is_archive_access_eligible(item, policy, now=current_time).allowed:
                visible_by_id.setdefault(item.memory_id, item)
    if include_pending_processing:
        for item in items:
            promotion = item.promotion or {}
            if (
                item.tier == MemoryLayer.short_term
                and item.status == MemoryItemStatus.active
                and item.processing_state == ProcessingState.pending
                and item.source_state == SourceState.active
                and promotion.get("required") is True
                and promotion.get("user_review") is not False
            ):
                visible_by_id[item.memory_id] = item
        visible = sorted(visible_by_id.values(), key=lambda item: (-item.updated_at.timestamp(), item.memory_id))
    else:
        visible = [
            item
            for item in sorted(visible_by_id.values(), key=lambda item: (-item.updated_at.timestamp(), item.memory_id))
            if item.processing_state == ProcessingState.processed
        ]
    visible = filter_items_by_device_scope(
        visible,
        device_scope=device_scope if device_scope in ("current", "all", "explicit") else "all",
        client_device_id=client_device_id,
    )
    visible = _deduplicate_canonical_items(visible, lineage_context=items)
    paged = visible[offset : offset + limit]
    return [memory_item_to_memorydb(item) for item in paged]


_CANONICAL_SCAN_PAGE_MAX = 500
_CANONICAL_SCAN_LINEAGE_MAX_HOPS = 12
_LEDGER_SEARCH_MAX_PROVIDER_CANDIDATES = 60
CanonicalScanCursor = tuple[datetime, str]
CanonicalScanSlot = tuple[Optional[MemoryDB], CanonicalScanCursor]


@dataclass(frozen=True)
class BoundedLedgerSearchHydration:
    """Named result for bounded provider-candidate and lineage hydration."""

    candidate_items: Tuple[MemoryItem, ...]
    lineage_items_by_id: Dict[str, MemoryItem]
    survivor_items_by_id: Dict[str, MemoryItem]


def _coerce_scan_updated_at(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _canonical_scan_item_visible(
    item: MemoryItem,
    *,
    policy: MemoryAccessPolicy,
    now: datetime,
    include_pending_processing: bool,
    include_archive: bool,
    device_scope: str,
    client_device_id: Optional[str],
) -> bool:
    """Apply list visibility predicates to one raw scan row without full-set loads."""
    default_visible = filter_canonical_default_visible_items([item], policy=policy, now=now)
    visible = bool(default_visible)
    if include_archive and is_archive_access_eligible(item, policy, now=now).allowed:
        visible = True
    if include_pending_processing:
        promotion = item.promotion or {}
        if (
            item.tier == MemoryLayer.short_term
            and item.status == MemoryItemStatus.active
            and item.processing_state == ProcessingState.pending
            and item.source_state == SourceState.active
            and promotion.get("required") is True
            and promotion.get("user_review") is not False
        ):
            visible = True
    elif item.processing_state != ProcessingState.processed:
        visible = False
    if not visible:
        return False
    scoped = filter_items_by_device_scope(
        [item],
        device_scope=device_scope if device_scope in ("current", "all", "explicit") else "all",
        client_device_id=client_device_id,
    )
    return bool(scoped)


def _read_canonical_memory_item_for_lineage(
    uid: str,
    memory_id: str,
    *,
    db_client: Any,
    budget: Optional[ListReadBudget] = None,
) -> Optional[MemoryItem]:
    """Read one canonical document for lineage traversal without status filtering.

    Snapshot/document id is the sole identity authority. Payload ``memory_id`` or
    ``uid`` mismatches fail closed. Non-active (superseded/hidden/tombstoned)
    rows are returned so callers can traverse restricted intermediates.
    """
    requested_id = (memory_id or "").strip()
    if not requested_id:
        return None
    path = f"{MemoryCollections(uid=uid).memory_items}/{requested_id}"
    snapshot = budgeted_document_get(db_client.document(path), budget)
    if not getattr(snapshot, "exists", False):
        return None
    doc_id = getattr(snapshot, "id", None)
    if not isinstance(doc_id, str) or not doc_id.strip():
        raise ValueError(f"canonical lineage target missing document id: requested {requested_id}")
    if doc_id != requested_id:
        raise ValueError(f"canonical lineage document id mismatch: requested {requested_id}, found {doc_id}")
    raw_payload: object = snapshot.to_dict()
    payload = cast(Dict[str, Any], raw_payload) if isinstance(raw_payload, dict) else {}
    item = MemoryItem.model_validate(payload)
    if item.memory_id != doc_id:
        raise ValueError(f"canonical memory id mismatch: requested {requested_id}, found {item.memory_id}")
    if item.uid != uid:
        raise ValueError(f"canonical memory uid mismatch: expected {uid}, got {item.uid}")
    return item


def _hydrate_bounded_ledger_search_items(
    uid: str,
    candidate_ids: Sequence[str],
    *,
    db_client: Any,
    policy: MemoryAccessPolicy,
    now: datetime,
    device_scope: str,
    client_device_id: Optional[str],
) -> BoundedLedgerSearchHydration:
    """Hydrate provider candidates plus a bounded canonical lineage closure.

    Ledger search must never turn a provider candidate into an account-wide
    canonical collection scan. Candidate rows are read in one bounded batch;
    each of at most twelve lineage hops reads only the next ids referenced by
    that batch. Every point is checked against both the owning path and the
    Firestore document id by the read-service seam.
    """

    requested_ids = list(dict.fromkeys(memory_id for memory_id in candidate_ids if memory_id))[
        :_LEDGER_SEARCH_MAX_PROVIDER_CANDIDATES
    ]
    if not requested_ids:
        return BoundedLedgerSearchHydration(
            candidate_items=(),
            lineage_items_by_id={},
            survivor_items_by_id={},
        )

    hydrated_by_id: Dict[str, MemoryItem] = {}
    frontier = fetch_authoritative_product_memory_items_by_ids(uid, requested_ids, db_client=db_client)
    for item in frontier:
        hydrated_by_id[item.memory_id] = item

    seen_ids = set(requested_ids)
    for _ in range(_CANONICAL_SCAN_LINEAGE_MAX_HOPS):
        next_ids = [
            target_id
            for item in frontier
            if (target_id := (item.canonical_memory_id or item.superseded_by or "").strip())
            and target_id not in seen_ids
        ]
        next_ids = list(dict.fromkeys(next_ids))[:_LEDGER_SEARCH_MAX_PROVIDER_CANDIDATES]
        if not next_ids:
            break
        seen_ids.update(next_ids)
        frontier = fetch_authoritative_product_memory_items_by_ids(uid, next_ids, db_client=db_client)
        for item in frontier:
            hydrated_by_id[item.memory_id] = item

    all_items = list(hydrated_by_id.values())
    visible_items = filter_canonical_default_visible_items(all_items, policy=policy, now=now)
    scoped_items = filter_items_by_device_scope(
        visible_items,
        device_scope=device_scope if device_scope in ("current", "all", "explicit") else "all",
        client_device_id=client_device_id,
    )
    return BoundedLedgerSearchHydration(
        candidate_items=tuple(hydrated_by_id[memory_id] for memory_id in requested_ids if memory_id in hydrated_by_id),
        lineage_items_by_id=hydrated_by_id,
        survivor_items_by_id={item.memory_id: item for item in scoped_items},
    )


def _ledger_search_lineage_is_complete(item: MemoryItem, *, lineage_items_by_id: Dict[str, MemoryItem]) -> bool:
    """Require a candidate's canonical lineage to terminate in bounded data."""

    current = item
    visited: set[str] = set()
    for _ in range(_CANONICAL_SCAN_LINEAGE_MAX_HOPS + 1):
        if current.memory_id in visited:
            return True
        visited.add(current.memory_id)
        target_id = (current.canonical_memory_id or current.superseded_by or "").strip()
        if not target_id or target_id == current.memory_id:
            return True
        target = lineage_items_by_id.get(target_id)
        if target is None:
            return False
        current = target
    # The closure was bounded before a terminating root was observed.
    return False


def _canonical_scan_lineage_suppressed(
    item: MemoryItem,
    *,
    uid: str,
    db_client: Any,
    policy: MemoryAccessPolicy,
    now: datetime,
    include_pending_processing: bool,
    include_archive: bool,
    device_scope: str,
    client_device_id: Optional[str],
    budget: Optional[ListReadBudget] = None,
) -> bool:
    """Suppress a visible alias when a visible authoritative survivor wins.

    Bounded identity-checked point-follow of ``canonical_memory_id`` /
    ``superseded_by`` (max ``_CANONICAL_SCAN_LINEAGE_MAX_HOPS``). Non-visible
    superseded/hidden/tombstoned nodes are traversal-only. Never reloads the
    full canonical set. Cycles stop the walk; payload id/uid mismatches fail
    closed without inventing a survivor.
    """
    outbound = (item.canonical_memory_id or item.superseded_by or "").strip()
    if not outbound or outbound == item.memory_id:
        return False

    closure_by_id: Dict[str, MemoryItem] = {item.memory_id: item}
    path: List[str] = [item.memory_id]
    position_by_id: Dict[str, int] = {item.memory_id: 0}
    current = item
    lineage_root = item.memory_id

    for _ in range(_CANONICAL_SCAN_LINEAGE_MAX_HOPS):
        next_id = (current.canonical_memory_id or current.superseded_by or "").strip()
        if not next_id or next_id == current.memory_id:
            lineage_root = current.memory_id
            break
        cycle_start = position_by_id.get(next_id)
        if cycle_start is not None:
            lineage_root = min(path[cycle_start:])
            break
        try:
            target = _read_canonical_memory_item_for_lineage(uid, next_id, db_client=db_client, budget=budget)
        except ValueError:
            # Payload/id/uid mismatch fail-closed for that hop: stop walking and
            # only evaluate identity-checked nodes already in the closure.
            break
        if target is None:
            # Unresolved pointer: treat the missing id as the chain end/root.
            lineage_root = next_id
            break
        closure_by_id[target.memory_id] = target
        position_by_id[target.memory_id] = len(path)
        path.append(target.memory_id)
        current = target
        lineage_root = current.memory_id
    else:
        lineage_root = current.memory_id

    visible_candidates = [
        candidate
        for candidate in closure_by_id.values()
        if candidate.memory_id != item.memory_id
        and _canonical_scan_item_visible(
            candidate,
            policy=policy,
            now=now,
            include_pending_processing=include_pending_processing,
            include_archive=include_archive,
            device_scope=device_scope,
            client_device_id=client_device_id,
        )
    ]
    if not visible_candidates:
        return False
    item_key = canonical_lineage_survivor_sort_key(item, lineage_root=lineage_root)
    return any(
        canonical_lineage_survivor_sort_key(candidate, lineage_root=lineage_root) < item_key
        for candidate in visible_candidates
    )


def read_canonical_scan_page(
    uid: str,
    *,
    limit: int = 100,
    start_after: Optional[CanonicalScanCursor] = None,
    db_client: Any = None,
    device_scope_request: Optional[DeviceScopeRequest] = None,
    include_pending_processing: bool = False,
    include_archive: bool = False,
    now: Optional[datetime] = None,
    budget: Optional[ListReadBudget] = None,
) -> Tuple[List[CanonicalScanSlot], bool]:
    """Read one bounded canonical raw scan page via Firestore keyset order.

    Each slot corresponds to one raw ``memory_items`` document in newest-first
    ``updated_at DESC, __name__ ASC`` order. ``None`` memory means the row was
    filtered by access/device/pending/archive/lineage policy and must still
    advance the scan cursor. ``snapshot.id`` is the sole ``__name__`` authority;
    payload ``memory_id`` mismatches fail closed as filtered slots. Callers
    over-fetch additional pages when filters shrink the visible stream. Never
    loads the full canonical set.
    """
    client = db_client if db_client is not None else default_db_client
    bounded_limit = max(1, min(int(limit or 100), _CANONICAL_SCAN_PAGE_MAX))
    device_scope = device_scope_request.device_scope if device_scope_request else "all"
    client_device_id = device_scope_request.client_device_id if device_scope_request else None
    current_time = now or datetime.now(timezone.utc)
    archive_explicit = bool(include_archive)
    policy = MemoryAccessPolicy.for_omi_chat(archive_capability=archive_explicit)

    items_ref = client.collection(MemoryCollections(uid=uid).memory_items)
    query = UNIVERSAL_CANONICAL_LIST_SCAN_QUERY.build(
        items_ref,
        {},
        field_filter_factory=FieldFilter,
    )
    query = query.order_by('updated_at', direction=firestore.Query.DESCENDING).order_by('__name__')
    if start_after is not None:
        cursor_time, cursor_memory_id = start_after
        if not cursor_memory_id.strip():
            raise ValueError('canonical scan cursor memory_id must not be blank')
        query = query.start_after(
            {
                'updated_at': _coerce_scan_updated_at(cursor_time),
                '__name__': items_ref.document(cursor_memory_id),
            }
        )
    snapshots = budgeted_stream_list(query.limit(bounded_limit), budget)
    slots: List[CanonicalScanSlot] = []
    for snapshot in snapshots:
        doc_id = getattr(snapshot, 'id', None)
        if not isinstance(doc_id, str) or not doc_id.strip():
            continue
        raw_payload = cast(object, snapshot.to_dict())
        payload = cast(Dict[str, Any], raw_payload) if isinstance(raw_payload, dict) else {}
        updated_raw = payload.get('updated_at')
        if isinstance(updated_raw, datetime):
            scan_updated_at = _coerce_scan_updated_at(updated_raw)
        else:
            scan_updated_at = datetime.fromtimestamp(0, tz=timezone.utc)
        scan_cursor = (scan_updated_at, doc_id)
        try:
            item = MemoryItem.model_validate(payload)
        except Exception:
            # Malformed docs still consume scan position via snapshot identity.
            slots.append((None, scan_cursor))
            continue
        if item.uid != uid:
            raise ValueError(f'memory item uid mismatch: expected {uid}, got {item.uid}')
        if item.memory_id != doc_id:
            # Fail closed: payload identity must match document __name__.
            slots.append((None, scan_cursor))
            continue
        if not _canonical_scan_item_visible(
            item,
            policy=policy,
            now=current_time,
            include_pending_processing=include_pending_processing,
            include_archive=archive_explicit,
            device_scope=device_scope,
            client_device_id=client_device_id,
        ):
            slots.append((None, scan_cursor))
            continue
        if _canonical_scan_lineage_suppressed(
            item,
            uid=uid,
            db_client=client,
            policy=policy,
            now=current_time,
            include_pending_processing=include_pending_processing,
            include_archive=archive_explicit,
            device_scope=device_scope,
            client_device_id=client_device_id,
            budget=budget,
        ):
            slots.append((None, scan_cursor))
            continue
        slots.append((memory_item_to_memorydb(item), scan_cursor))
    exhausted = len(snapshots) < bounded_limit
    return slots, exhausted


def search_canonical_memories(
    uid: str,
    query: str,
    *,
    limit: int = 5,
    db_client: Any = None,
    vector_query: Any = None,
    device_scope_request: Optional[DeviceScopeRequest] = None,
    item_filter: Optional[Callable[[MemoryItem], bool]] = None,
    ledger_kinds: Optional[Collection[str]] = None,
) -> List[Dict[str, Any]]:
    """Hybrid search over default-visible Short-term and Long-term memories."""
    client = db_client if db_client is not None else default_db_client
    device_scope = device_scope_request.device_scope if device_scope_request else "all"
    client_device_id = device_scope_request.client_device_id if device_scope_request else None
    capped_limit = max(1, min(limit, 20))
    fetch_limit = min(capped_limit * 3, 60)
    normalized_query = (query or "").strip()

    if not normalized_query:
        if ledger_kinds is not None:
            return []
        memories = read_canonical_memories(
            uid,
            limit=capped_limit,
            offset=0,
            db_client=client,
            device_scope_request=device_scope_request,
        )
        return [
            {
                "memory_id": memory.id,
                "content": memory.content,
                "tier": memory.memory_tier.value if memory.memory_tier is not None else MemoryLayer.short_term.value,
                "date": memory.updated_at.isoformat(),
                "visibility": memory.visibility,
                "is_locked": memory.is_locked,
                **public_belief_overlay_json(memory, now=datetime.now(timezone.utc)),
            }
            for memory in memories[:capped_limit]
        ]

    from utils.memory.atom_keyword_index import (
        keyword_search_ledger_memory_ids,
        keyword_search_memory_ids,
        merge_memory_search_ids,
        require_typesense_projection_ready,
    )

    if ledger_kinds is None:
        keyword_ids = keyword_search_memory_ids(uid, normalized_query, limit=fetch_limit, db_client=client)
    else:
        require_typesense_projection_ready(uid)
        keyword_ids = keyword_search_ledger_memory_ids(
            uid,
            normalized_query,
            kinds=ledger_kinds,
            limit=fetch_limit,
            db_client=client,
        )
    if vector_query is None:
        from database.vector_db import query_memory_vector_candidates

        vector_query_fn = query_memory_vector_candidates
    else:
        vector_query_fn = vector_query
    if ledger_kinds is None:
        vector_result = vector_query_fn(uid, normalized_query, limit=fetch_limit)
    else:
        vector_result = vector_query_fn(
            uid,
            normalized_query,
            limit=fetch_limit,
            ledger_kinds=sorted(ledger_kinds),
        )
    vector_ids = [hit.memory_id for hit in vector_result.hits if hit.memory_id]
    merged_ids = merge_memory_search_ids(keyword_ids, vector_ids)
    if not merged_ids:
        return []

    now = datetime.now(timezone.utc)
    policy = MemoryAccessPolicy.for_omi_chat(archive_capability=False)
    if ledger_kinds is None:
        all_items = fetch_authoritative_product_memory_items(uid=uid, db_client=client)
        visible_items = filter_canonical_default_visible_items(all_items, policy=policy, now=now)
        scoped_items = filter_items_by_device_scope(
            visible_items,
            device_scope=device_scope if device_scope in ("current", "all", "explicit") else "all",
            client_device_id=client_device_id,
        )
        lineage_items_by_id = {item.memory_id: item for item in all_items}
        survivor_items_by_id = {item.memory_id: item for item in scoped_items}
        candidate_ids = merged_ids
    else:
        hydration = _hydrate_bounded_ledger_search_items(
            uid,
            merged_ids,
            db_client=client,
            policy=policy,
            now=now,
            device_scope=device_scope,
            client_device_id=client_device_id,
        )
        candidate_items = list(hydration.candidate_items)
        lineage_items_by_id = hydration.lineage_items_by_id
        survivor_items_by_id = hydration.survivor_items_by_id
        candidate_items = [
            item
            for item in candidate_items
            if _ledger_search_lineage_is_complete(item, lineage_items_by_id=lineage_items_by_id)
        ]
        candidate_ids = [item.memory_id for item in candidate_items]
    vector_scores = {hit.memory_id: float(hit.score or 0.0) for hit in vector_result.hits}

    candidates: List[Payload] = []
    for memory_id in candidate_ids:
        item = survivor_items_by_id.get(memory_id)
        if item is None or (item_filter is not None and not item_filter(item)):
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

    deduplicated = _deduplicate_canonical_search_candidates(
        candidates,
        lineage_items_by_id=lineage_items_by_id,
        survivor_items_by_id=survivor_items_by_id,
    )
    reranked = rrf_rerank(normalized_query, deduplicated, len(deduplicated))
    reranked.sort(key=_canonical_search_result_sort_key)
    reranked = reranked[:capped_limit]
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
                "is_locked": bool((item.promotion or {}).get("is_locked", False)),
                "ledger_schema_version": item.ledger_schema_version,
                "kind": item.kind.value if item.ledger_schema_version else None,
                "subject_scope": item.subject_scope.value if item.ledger_schema_version else None,
                "slot": item.slot,
                "curation_weight": item.curation_weight,
                "intent_backed": item.intent_backed,
                "write_reason": item.write_reason.value if item.write_reason else None,
                **public_belief_overlay_json(item, now=datetime.now(timezone.utc)),
            }
        )
    return results


def _ensure_control_state(uid: str, *, db_client: Any) -> MemoryControlState:
    return ensure_canonical_apply_control_state(uid, db_client=db_client)


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
    raw_source_version = evidence_data.get("source_version")
    source_version = (
        raw_source_version.strip() if isinstance(raw_source_version, str) and raw_source_version.strip() else "v1"
    )
    raw_quote_refs = evidence_data.get("quote_refs")
    quote_refs: List[Dict[str, Any]] = []
    if isinstance(raw_quote_refs, list):
        for raw_quote_ref in cast(List[object], raw_quote_refs):
            if isinstance(raw_quote_ref, dict):
                quote_refs.append(dict(cast(Dict[str, Any], raw_quote_ref)))
    raw_artifacts = evidence_data.get("artifact_refs")
    if not isinstance(raw_artifacts, list):
        raw_artifact = evidence_data.get("artifact_ref")
        raw_artifacts = [raw_artifact] if isinstance(raw_artifact, dict) and raw_artifact else []
    artifact_refs: List[ArtifactRef] = []
    for raw_artifact in cast(List[object], raw_artifacts):
        if not isinstance(raw_artifact, dict):
            continue
        artifact_payload = dict(cast(Dict[str, Any], raw_artifact))
        artifact_payload.setdefault("preservation", ArtifactPreservationState.preserved.value)
        artifact_refs.append(ArtifactRef(**artifact_payload))
    return MemoryEvidence(
        evidence_id=evidence_data["evidence_id"],
        source_type=evidence_data.get("source_type") or "conversation",
        source_id=source_id,
        source_version=source_version,
        conversation_id=(
            conversation_id if (evidence_data.get("source_type") or "conversation") == "conversation" else None
        ),
        artifact_preservation=ArtifactPreservationState.preserved,
        artifact_refs=artifact_refs,
        quote_refs=quote_refs,
        client_device_id=client_device_id,
    )


def _resolve_initial_tier_value(data: Dict[str, Any]) -> str:
    if data.get("ledger_schema_version") == "knowledge_ledger.v1":
        # ``tier`` is retained only as a released-client projection. Ledger
        # rows are durable at creation and never enter the ST elevation loop.
        return MemoryLayer.long_term.value
    raw_tier = data.get("memory_tier")
    if raw_tier is not None:
        if hasattr(raw_tier, "value"):
            raw_tier = raw_tier.value
        # Product/API callers may express durability intent, but only the
        # canonical admission pipeline may create Long-term rows. All ordinary
        # adapter writes enter through Short-term first.
        if str(raw_tier) == MemoryLayer.long_term.value:
            return MemoryLayer.short_term.value
        return str(raw_tier)
    durability = data.get("durability")
    if (durability or "").lower() == MemoryLayer.long_term.value:
        return MemoryLayer.short_term.value
    if _user_asserted_from_payload(data):
        return MemoryLayer.short_term.value
    return decide_initial_memory_tier(False, durability).value


def _visibility_from_payload(data: Dict[str, Any]) -> str:
    visibility = (data.get("visibility") or "private").strip()
    return visibility if visibility in _ALLOWED_MEMORY_VISIBILITIES else "private"


def _user_asserted_from_payload(data: Dict[str, Any]) -> bool:
    if "manually_added" in data:
        return bool(data.get("manually_added"))
    return bool(data.get("user_asserted"))


def _conversation_extracted_claim(data: Dict[str, Any]) -> bool:
    """True only for conversation capture. Manual/API/integration writes skip the classifier."""
    if _user_asserted_from_payload(data):
        return False
    if data.get("conversation_id"):
        return True
    for raw in data.get("evidence") or []:
        if isinstance(raw, dict) and (raw.get("source_type") or "") == "conversation":
            return True
        if getattr(raw, "source_type", None) == "conversation":
            return True
    return False


def _product_metadata_from_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {}
    category = data.get("category")
    if category is not None:
        metadata["category"] = category.value if hasattr(category, "value") else str(category)
    tags = data.get("tags")
    if tags:
        metadata["tags"] = list(tags)
    if "is_locked" in data:
        metadata["is_locked"] = bool(data.get("is_locked"))
    raw_attribution = data.get("subject_attribution")
    attribution = (
        raw_attribution.value if isinstance(raw_attribution, SubjectAttribution) else str(raw_attribution or "")
    )
    if attribution not in {value.value for value in SubjectAttribution}:
        attribution = SubjectAttribution.unknown.value
    subject_entity_id = data.get("subject_entity_id")
    source_attribution: Dict[str, Any] = {
        "subject_attribution": attribution,
        "subject_entity_id": (
            subject_entity_id.strip() if isinstance(subject_entity_id, str) and subject_entity_id.strip() else None
        ),
    }
    raw_subject_kind = data.get("subject_kind")
    subject_kind = str(raw_subject_kind or "").strip().lower()
    if subject_kind in {"user", "speaker", "person", "entity", "unknown"}:
        source_attribution["subject_kind"] = subject_kind
    metadata["source_attribution"] = source_attribution
    return metadata


def _relationship_to_user_from_payload(data: Dict[str, Any]) -> str:
    raw_attribution = data.get("subject_attribution")
    attribution = (
        raw_attribution.value if isinstance(raw_attribution, SubjectAttribution) else str(raw_attribution or "")
    )
    if attribution == SubjectAttribution.user.value:
        return "self"
    return "unclear"


def _validate_memory_item_for_write(item: MemoryItem) -> MemoryItem:
    item = MemoryItem.model_validate(item.model_dump(mode="python"))
    if item.visibility not in _ALLOWED_MEMORY_VISIBILITIES:
        raise ValueError("visibility must be private, public, or shared")
    return item


def _persist_memory_item(  # pyright: ignore[reportUnusedFunction]  # intercepted by write-path contract tests
    uid: str, item: MemoryItem, *, db_client: Any
) -> None:
    item = _validate_memory_item_for_write(item)
    path = f"{MemoryCollections(uid=uid).memory_items}/{item.memory_id}"
    db_client.document(path).set(item.model_dump(mode="json"))


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
    return [_legacy_evidence_to_memory(evidence.model_dump(), conversation_id=conversation_id)]


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
    if item.uid != uid:
        raise ValueError(f"canonical memory uid mismatch: expected {uid}, got {item.uid}")
    return item


def read_canonical_memory_item(uid: str, memory_id: str, *, db_client: Any = None) -> Optional[MemoryItem]:
    """Read one active canonical memory item from the authoritative product store."""
    client = db_client if db_client is not None else default_db_client
    return _read_canonical_memory_item(uid, memory_id, db_client=client)


def _canonical_extraction_apply_write(
    uid: str,
    data: Dict[str, Any],
    *,
    control: MemoryControlState,
    evidence_items: Optional[List[MemoryEvidence]] = None,
) -> tuple[CanonicalApplyWrite, str]:
    content = (data.get("content") or "").strip()
    if not content:
        raise ValueError("canonical write requires non-empty content")

    conversation_id = data.get("conversation_id")
    source_id = conversation_id or data.get("id") or "unknown"
    subject_entity_id = str(data.get("subject_entity_id") or "").strip() or None
    memory_id = data.get("id") or extraction_memory_id(
        uid=uid,
        source_id=source_id,
        content=content,
        subject_entity_id=subject_entity_id,
    )
    idempotency_identity = {"uid": uid, "source_id": source_id, "content": content}
    if data.get("ledger_schema_version") == "knowledge_ledger.v1":
        # Ledger row identity includes the intent-serving action. Two distinct
        # actions may validly derive the same text from one source; collapsing
        # them at the older extraction idempotency key would commit the wrong
        # row id and lose provenance.
        idempotency_identity["ledger_memory_id"] = memory_id
    if subject_entity_id and subject_entity_id != "user":
        idempotency_identity["subject_entity_id"] = subject_entity_id
    idempotency_key = deterministic_contract_id(
        "canonical-extraction-idempotency",
        idempotency_identity,
    )

    if evidence_items is None:
        evidence_items = _evidence_items_from_payload(data)
    raw_evidence = [
        cast(Payload, raw) for raw in cast(List[object], data.get("evidence") or []) if isinstance(raw, dict)
    ]
    device_ids, primary_device = _ordered_capture_devices_from_evidence(raw_evidence)
    promotion_metadata = dict(data["promotion"]) if isinstance(data.get("promotion"), dict) else {}
    promotion_metadata.update(_product_metadata_from_payload(data))

    ledger_schema_version = data.get("ledger_schema_version")
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
        "relationship_to_user": _relationship_to_user_from_payload(data),
        "initial_tier": _resolve_initial_tier_value(data),
        "visibility": _visibility_from_payload(data),
        "user_asserted": _user_asserted_from_payload(data),
    }
    for ledger_key in (
        "ledger_schema_version",
        "kind",
        "subject_scope",
        "half_life_days",
        "belief_class",
        "slot",
        "body",
        "valid_from",
        "valid_to",
        "curation_weight",
        "trigger_condition",
        "intent_backed",
        "write_reason",
    ):
        if ledger_key in data and data[ledger_key] is not None:
            patch_payload[ledger_key] = data[ledger_key]
    raw_scope = patch_payload.get("subject_scope")
    if isinstance(raw_scope, str) and raw_scope in SUBJECT_SCOPE_ALIASES:
        patch_payload["subject_scope"] = SUBJECT_SCOPE_ALIASES[raw_scope]
    if belief_model_enabled():
        if "valid_to" not in patch_payload and data.get("invalid_at") is not None:
            patch_payload["valid_to"] = data["invalid_at"]
        if "subject_scope" not in patch_payload:
            if _conversation_extracted_claim(data):
                attribution = data.get("subject_attribution")
                attribution_value = getattr(attribution, "value", attribution)
                user_name = data.get("user_name")
                patch_payload["subject_scope"] = subject_scope_from_extraction(
                    extracted_scope=data.get("subject_scope"),
                    attribution=str(attribution_value or ""),
                    about=data.get("about"),
                    user_name=user_name if isinstance(user_name, str) else None,
                )
            else:
                patch_payload["subject_scope"] = "primary_user"
        if "belief_class" not in patch_payload:
            resolved_class, resolved_half_life = horizon_from_extraction(
                belief_class=data.get("belief_class"),
                half_life_days_override=data.get("half_life_days"),
                user_asserted=_user_asserted_from_payload(data),
            )
            patch_payload["belief_class"] = resolved_class
            if resolved_half_life is not None:
                patch_payload["half_life_days"] = resolved_half_life
    supersedes = [str(value).strip() for value in (data.get("supersedes") or []) if str(value).strip()]
    if supersedes:
        patch_payload["supersedes"] = sorted(set(supersedes))
    if promotion_metadata:
        patch_payload["promotion"] = promotion_metadata
    if data.get("subject_entity_id"):
        patch_payload["subject_entity_id"] = data["subject_entity_id"]
    if data.get("predicate"):
        patch_payload["predicate"] = data["predicate"]
    if data.get("arguments"):
        patch_payload["arguments"] = data["arguments"]
    if data.get("sensitivity_labels"):
        patch_payload["sensitivity_labels"] = data["sensitivity_labels"]
    if device_ids:
        patch_payload["capture_device_ids"] = device_ids
        patch_payload["primary_capture_device"] = primary_device

    mutation_identity = build_patch_mutation_identity(patch_payload)
    patch_payload["mutation_metadata"] = mutation_identity
    logical_payload = {
        "decision": "add",
        "memory_text": content,
        "result_status": LifecycleState.active.value,
        "subject_entity_id": data.get("subject_entity_id"),
        "predicate": data.get("predicate"),
        "arguments": data.get("arguments") or {},
        "supersedes": patch_payload.get("supersedes") or [],
        "mutation_metadata": mutation_identity,
    }
    operation = MemoryOperation.new(
        uid=uid,
        operation_type=(
            MemoryOperationType.ledger_mutation
            if ledger_schema_version == "knowledge_ledger.v1"
            else MemoryOperationType.source_candidate
        ),
        source_packet_id=source_id,
        target_memory_id=None,
        evidence_ids=[item.evidence_id for item in evidence_items],
        logical_payload=logical_payload,
        account_generation=control.account_generation,
        source_generation=control.source_generation,
        observed_head_commit_id=control.head_commit_id,
    )
    return (
        CanonicalApplyWrite(
            operation=operation,
            patch_payload=patch_payload,
            evidence=evidence_items,
        ),
        memory_id,
    )


_DUPLICATE_ADD_ROW_REASON = "add patch new_memory_id already exists"


def _existing_identical_add_row(
    uid: str,
    *,
    result: ApplyResult,
    memory_id: str,
    data: Dict[str, Any],
    db_client: Any,
) -> Optional[MemoryItem]:
    """Resolve an add collision against an already-committed identical row.

    Operation identity folds the observed head commit into the operation id, so
    a duplicate submission is only replay-idempotent while the account head has
    not moved. Re-sending the same memory after any other ledger write proposes
    a fresh operation whose add then collides with the deterministically derived
    row id. The requested row already exists with the same content, so the write
    is complete rather than failed. A collision with different content — a
    client-supplied id reused for new text — is still an error, and a row that
    is no longer active keeps failing so a resurrected id can never masquerade
    as a fresh create.
    """
    if result.status != ApplyStatus.invalid_patch or result.reason != _DUPLICATE_ADD_ROW_REASON:
        return None
    snapshot = db_client.document(f"{MemoryCollections(uid=uid).memory_items}/{memory_id}").get()
    if not getattr(snapshot, "exists", False):
        return None
    item = MemoryItem(**_snapshot_payload(snapshot))
    if item.status != MemoryItemStatus.active:
        return None
    if (item.promotion or {}).get("user_review") is False:
        # A rejected row remains active for audit/history, but it is not a
        # successful retry target.  Reusing it would silently resurrect a
        # user-rejected statement under the old content-derived identity.
        return None
    if (item.content or "").strip() != (data.get("content") or "").strip():
        return None
    return item


def write_canonical_extraction_memory(
    uid: str,
    data: Dict[str, Any],
    *,
    db_client: Any = None,
    evidence_items: Optional[List[MemoryEvidence]] = None,
    _ledger_authority: object | None = None,
    _direct_user_authority: object | None = None,
    required_source_item: Optional[MemoryItem] = None,
    ledger_reopen_receipt: Optional[MemoryLedgerReopenReceipt] = None,
    review_resolution: Optional[CanonicalReviewResolution] = None,
    admit_neighbors: bool = True,
) -> str:
    """Persist one memory to memory_items + ledger (extraction or external/manual writes)."""
    if data.get("ledger_schema_version") is not None and _ledger_authority is not _LEDGER_WRITE_AUTHORITY:
        raise ValueError("knowledge ledger writes require the dedicated ledger authority")
    client = db_client if db_client is not None else default_db_client
    control = _ensure_control_state(uid, db_client=client)
    direct_user_authorized = _direct_user_authority is _DIRECT_USER_LEDGER_WRITE_AUTHORITY
    if direct_user_authorized:
        writer_class = MemoryWriterClass.user
    else:
        writer_class = (
            MemoryWriterClass.ledger
            if data.get("ledger_schema_version") == _LEDGER_SCHEMA_VERSION
            else MemoryWriterClass.compatibility
        )
    require_writer_admitted(control, writer_class)
    write, memory_id = _canonical_extraction_apply_write(
        uid,
        data,
        control=control,
        evidence_items=evidence_items,
    )
    result = None
    for _attempt in range(3):
        apply_patch = (
            apply_direct_user_long_term_patch_firestore if direct_user_authorized else apply_long_term_patch_firestore
        )
        result = apply_patch(
            uid=uid,
            operation_id=write.operation.operation_id,
            patch_payload=write.patch_payload,
            proposed_operation=write.operation,
            proposed_evidence=write.evidence,
            review_resolution=review_resolution,
            required_source_item=required_source_item,
            ledger_reopen_receipt=ledger_reopen_receipt,
            allow_ledger_migration=False,
            db_client=client,
        )
        if result.status != ApplyStatus.retryable_head_mismatch:
            break
    assert result is not None
    if result.status not in {ApplyStatus.committed, ApplyStatus.idempotent_skip}:
        duplicate_row = _existing_identical_add_row(
            uid,
            result=result,
            memory_id=memory_id,
            data=data,
            db_client=client,
        )
        if duplicate_row is None:
            raise RuntimeError(f"canonical write failed: {result.status} ({result.reason})")
        logger.info(
            "canonical duplicate add resolved to existing row uid=%s memory_id=%s",
            uid,
            duplicate_row.memory_id,
        )
        assert_legal_state(
            DomainMemoryLayer(duplicate_row.tier.value),
            physical_status_to_record_status(duplicate_row.status.value),
            MemoryProcessingState(duplicate_row.processing_state.value),
        )
        return duplicate_row.memory_id

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
        assert_legal_state(
            DomainMemoryLayer(item.tier.value),
            physical_status_to_record_status(item.status.value),
            MemoryProcessingState(item.processing_state.value),
        )

    if admit_neighbors and belief_model_enabled() and item is not None:
        from utils.memory.belief_evidence import admit_claim_against_neighbors

        try:
            admit_claim_against_neighbors(
                uid,
                committed_id,
                item.content or data.get("content") or "",
                db_client=client,
                new_user_asserted=bool(item.user_asserted),
            )
        except Exception:
            logger.warning("belief evidence admission skipped memory_id=%s", committed_id, exc_info=False)

    return committed_id


_EXTERNAL_EVIDENCE_REISSUE_LIMIT = 25


def _reissued_external_evidence(
    uid: str,
    evidence_items: List[MemoryEvidence],
    *,
    db_client: Any,
) -> List[MemoryEvidence]:
    """Mint a fresh evidence identity when an external submission reuses a retired one.

    External evidence ids are derived from the submitted content, and evidence
    source_state is monotonic per identity. Deleting a memory tombstones its
    evidence, so re-adding the same text would otherwise reuse the tombstoned
    identity and fail the apply source gate on every retry. The new submission is
    a new source artifact and gets its own identity; the tombstone stays retired.
    Conversation-sourced evidence keeps the retired identity: a deleted
    conversation is a deleted source, not a fresh one.
    """
    collections = MemoryCollections(uid=uid)
    reissued: List[MemoryEvidence] = []
    for item in evidence_items:
        if item.conversation_id or item.source_type == "conversation":
            reissued.append(item)
            continue
        evidence_id = item.evidence_id
        for attempt in range(1, _EXTERNAL_EVIDENCE_REISSUE_LIMIT + 1):
            snapshot = db_client.document(f"{collections.memory_evidence}/{evidence_id}").get()
            if not getattr(snapshot, "exists", False):
                break
            stored = _snapshot_payload(snapshot)
            if SourceState(stored.get("source_state") or SourceState.active.value) == SourceState.active:
                break
            evidence_id = (
                "ev_"
                + deterministic_contract_id(
                    "canonical-external-evidence-reissue",
                    {"evidence_id": item.evidence_id, "attempt": attempt},
                )[:32]
            )
        else:
            raise RuntimeError("canonical external write exhausted evidence identity reissues")
        reissued.append(
            item if evidence_id == item.evidence_id else item.model_copy(update={"evidence_id": evidence_id})
        )
    return reissued


def write_canonical_external_memory(
    uid: str,
    data: Dict[str, Any],
    *,
    db_client: Any = None,
    review_resolution: Optional[CanonicalReviewResolution] = None,
) -> str:
    """Persist a manual/API/integration memory via the canonical apply path.

    After writer-mode cutover these creates stay admitted as user writes so
    POST /v3/memories and desktop create_memory do not 503 in ledger mode.
    """
    if data.get("ledger_schema_version") is not None:
        raise ValueError("knowledge ledger writes require the dedicated ledger authority")
    client = db_client if db_client is not None else default_db_client
    original_evidence = _evidence_items_from_payload(data)
    reissued_evidence = _reissued_external_evidence(uid, original_evidence, db_client=client)
    payload = dict(data)
    original_memory_id = str(data.get("id") or "").strip()
    was_privacy_deleted = False
    if original_memory_id:
        receipt = client.document(
            f"{MemoryCollections(uid=uid).memory_deletion_receipts}/"
            f"{privacy_deletion_receipt_id(uid, original_memory_id)}"
        ).get()
        was_privacy_deleted = bool(getattr(receipt, "exists", False))
    if was_privacy_deleted and not any(
        item.conversation_id or item.source_type == "conversation" for item in original_evidence
    ):
        reissued_evidence = [
            item.model_copy(update={"evidence_id": f"ev_{secrets.token_hex(16)}"}) for item in original_evidence
        ]
        payload["id"] = f"mem_{secrets.token_hex(16)}"
    if [item.evidence_id for item in reissued_evidence] != [item.evidence_id for item in original_evidence]:
        # A manually re-added fact is a new source artifact. Give the new row a
        # fresh deterministic identity derived from its newly minted evidence;
        # the deleted row and evidence remain immutable history.
        if not was_privacy_deleted:
            payload["id"] = (
                "mem_"
                + deterministic_contract_id(
                    "canonical-external-memory-reissue",
                    {
                        "uid": uid,
                        "original_memory_id": data.get("id"),
                        "evidence_ids": [item.evidence_id for item in reissued_evidence],
                    },
                )[:32]
            )
    memory_id = write_canonical_extraction_memory(
        uid,
        payload,
        db_client=client,
        evidence_items=reissued_evidence,
        review_resolution=review_resolution,
        _direct_user_authority=_DIRECT_USER_LEDGER_WRITE_AUTHORITY,
        admit_neighbors=False,
    )
    if belief_model_enabled():
        from utils.memory.belief_evidence import schedule_belief_admission

        schedule_belief_admission(
            uid,
            memory_id,
            str(payload.get("content") or ""),
            db_client=client,
            new_user_asserted=bool(payload.get("manually_added") or payload.get("user_asserted")),
        )
    return memory_id


def write_canonical_knowledge_ledger_memory(
    uid: str,
    data: Dict[str, Any],
    *,
    db_client: Any = None,
    required_source_item: Optional[MemoryItem] = None,
    ledger_reopen_receipt: Optional[MemoryLedgerReopenReceipt] = None,
) -> str:
    """Dedicated canonical boundary for exactly ``knowledge_ledger.v1`` rows."""
    if data.get("ledger_schema_version") != "knowledge_ledger.v1":
        raise ValueError("dedicated ledger writes require knowledge_ledger.v1")
    client = db_client if db_client is not None else default_db_client
    reopen_evidence = (
        _evidence_items_from_payload(data)
        if ledger_reopen_receipt is not None
        else _reissued_external_evidence(
            uid,
            _evidence_items_from_payload(data),
            db_client=client,
        )
    )
    return write_canonical_extraction_memory(
        uid,
        data,
        db_client=client,
        _ledger_authority=_LEDGER_WRITE_AUTHORITY,
        required_source_item=required_source_item,
        ledger_reopen_receipt=ledger_reopen_receipt,
        evidence_items=reopen_evidence,
    )


def write_canonical_direct_user_knowledge_ledger_memory(
    uid: str,
    data: Dict[str, Any],
    *,
    db_client: Any = None,
    required_source_item: Optional[MemoryItem] = None,
    ledger_reopen_receipt: Optional[MemoryLedgerReopenReceipt] = None,
) -> str:
    """Dedicated boundary for an explicit user fact or correction append."""

    evidence = _evidence_items_from_payload(data)
    is_initial_user_fact = (
        data.get("ledger_schema_version") == _LEDGER_SCHEMA_VERSION
        and data.get("write_reason") == LedgerWriteReason.direct_user_statement.value
        and data.get("user_asserted") is True
        and not data.get("supersedes")
        and ledger_reopen_receipt is None
        and any(item.source_type == "explicit_user_statement" for item in evidence)
    )
    is_user_amendment = (
        data.get("ledger_schema_version") == _LEDGER_SCHEMA_VERSION
        and data.get("write_reason") == LedgerWriteReason.direct_user_statement.value
        and data.get("user_asserted") is True
        and (bool(data.get("supersedes")) or ledger_reopen_receipt is not None)
        and any(
            item.source_type in {"explicit_user_correction", "explicit_user_reopen", "explicit_user_revert"}
            for item in evidence
        )
    )
    if not (is_initial_user_fact or is_user_amendment):
        raise ValueError("direct user ledger writes require an explicit user fact or append authority")
    client = db_client if db_client is not None else default_db_client
    evidence_items = (
        evidence if ledger_reopen_receipt is not None else _reissued_external_evidence(uid, evidence, db_client=client)
    )
    return write_canonical_extraction_memory(
        uid,
        data,
        db_client=client,
        _ledger_authority=_LEDGER_WRITE_AUTHORITY,
        _direct_user_authority=_DIRECT_USER_LEDGER_WRITE_AUTHORITY,
        required_source_item=required_source_item,
        ledger_reopen_receipt=ledger_reopen_receipt,
        evidence_items=evidence_items,
    )


def close_canonical_ledger_item(
    uid: str,
    memory_id: str,
    *,
    valid_to: Optional[datetime] = None,
    db_client: Any = None,
) -> MemoryItem:
    """Close one ledger row while preserving it as searchable history."""
    client = db_client if db_client is not None else default_db_client

    def already_closed() -> Optional[MemoryItem]:
        existing = _read_canonical_memory_item_for_lineage(uid, memory_id, db_client=client)
        if existing is None or existing.ledger_schema_version != "knowledge_ledger.v1":
            return None
        if existing.status != MemoryItemStatus.superseded or existing.valid_to is None:
            return None
        if valid_to is not None and existing.valid_to != valid_to:
            raise ValueError("ledger row was already closed at a different valid_to")
        return existing

    closed = already_closed()
    if closed is not None:
        return closed

    def build_patch(item: MemoryItem, now: datetime) -> Tuple[Payload, Payload]:
        if item.ledger_schema_version != "knowledge_ledger.v1":
            raise ValueError("only knowledge ledger rows may be closed with this operation")
        closed_at = valid_to or now
        if closed_at.tzinfo is None or closed_at.utcoffset() is None:
            raise ValueError("valid_to must be timezone-aware")
        if closed_at < (item.valid_from or item.captured_at):
            raise ValueError("valid_to must not precede valid_from")
        return (
            {"result_status": LifecycleState.superseded.value},
            {"valid_to": closed_at},
        )

    try:
        _, updated = _apply_canonical_user_mutation(
            uid,
            memory_id,
            mutation_kind="ledger_close",
            build_patch=build_patch,
            operation_type=MemoryOperationType.ledger_mutation,
            db_client=client,
        )
    except ValueError as exc:
        # A concurrent close may win after our initial active read. Re-read
        # non-active history and accept only the identical terminal outcome.
        closed = already_closed()
        if closed is None:
            raise exc
        return closed
    return updated


def close_canonical_legacy_generated_history(
    uid: str,
    memory_id: str,
    *,
    expected_item_revision: int,
    expected_tier: MemoryLayer,
    valid_to: Optional[datetime] = None,
    db_client: Any = None,
) -> MemoryItem:
    """Idempotently close one surviving legacy Short-term row as history."""
    client = db_client if db_client is not None else default_db_client

    def already_closed() -> Optional[MemoryItem]:
        item = _read_canonical_memory_item_for_lineage(uid, memory_id, db_client=client)
        if (
            item is not None
            and item.status == MemoryItemStatus.superseded
            and item.arguments.get("history_class") == "legacy_generated"
            and item.valid_to is not None
        ):
            return item
        return None

    if closed := already_closed():
        return closed

    def build_patch(item: MemoryItem, now: datetime) -> Tuple[Payload, Payload]:
        if item.item_revision != expected_item_revision:
            raise ValueError("legacy Short-term adjudication source revision changed")
        if (
            item.tier != expected_tier
            or item.status != MemoryItemStatus.active
            or item.ledger_schema_version is not None
        ):
            raise ValueError("only active pre-ledger Short-term rows may be adjudicated")
        closed_at = valid_to or now
        if closed_at.tzinfo is None or closed_at.utcoffset() is None:
            raise ValueError("legacy Short-term adjudication valid_to must be timezone-aware")
        subject_scope = (
            MemorySubjectScope.third_party
            if item.subject_entity_id and item.subject_entity_id != "user"
            else MemorySubjectScope.primary_user
        )
        # This is not merely an inactive pre-ledger row. Give the preserved
        # record the canonical ledger shape and exact migration provenance so
        # the explicit historical-fact tool can retrieve it while every
        # current/default prompt path continues to exclude it.
        return (
            {"result_status": LifecycleState.superseded.value},
            {
                "valid_to": max(closed_at, item.captured_at),
                "arguments": {**item.arguments, "history_class": "legacy_generated"},
                "ledger_schema_version": _LEDGER_SCHEMA_VERSION,
                "kind": MemoryKind.fact.value,
                "subject_scope": subject_scope.value,
                "intent_backed": False,
                "write_reason": LedgerWriteReason.legacy_migration.value,
            },
        )

    try:
        _, updated = _apply_canonical_user_mutation(
            uid,
            memory_id,
            mutation_kind=f"legacy_short_term_adjudication:r{expected_item_revision}",
            build_patch=build_patch,
            operation_type=MemoryOperationType.ledger_mutation,
            allow_ledger_migration=True,
            db_client=client,
        )
    except ValueError as exc:
        if closed := already_closed():
            return closed
        raise exc
    return updated


def _read_replacement_control(uid: str, *, db_client: Any) -> MemoryControlState:
    return ensure_canonical_apply_control_state(uid, db_client=db_client)


def _conversation_replacement_payload(
    uid: str,
    conversation_id: str,
    data: Dict[str, Any],
    *,
    source_generation: int,
) -> Dict[str, Any]:
    payload = copy.deepcopy(data)
    content = str(payload.get("content") or "").strip()
    if not content:
        raise ValueError("canonical conversation replacement requires non-empty content")
    memory_id = payload.get("id") or extraction_memory_id(
        uid=uid,
        source_id=conversation_id,
        content=content,
        subject_entity_id=str(payload.get("subject_entity_id") or "").strip() or None,
    )
    payload["id"] = memory_id
    payload["conversation_id"] = conversation_id
    source_version = f"source_generation:{source_generation}"
    raw_evidence = payload.get("evidence")
    if not isinstance(raw_evidence, list) or not raw_evidence:
        raise ValueError("canonical conversation replacement requires source evidence")
    for index, raw in enumerate(cast(List[object], raw_evidence)):
        if not isinstance(raw, dict):
            raise ValueError("canonical conversation replacement evidence must be an object")
        evidence = cast(Payload, raw)
        evidence_id = (
            "ev_"
            + deterministic_contract_id(
                "canonical-conversation-evidence",
                {
                    "uid": uid,
                    "source_id": conversation_id,
                    "source_version": source_version,
                    "memory_id": memory_id,
                    "index": index,
                },
            )[:32]
        )
        evidence.update(
            {
                "evidence_id": evidence_id,
                "source_id": conversation_id,
                "source_type": "conversation",
                "source_version": source_version,
            }
        )
        quote_refs = evidence.get("quote_refs")
        if isinstance(quote_refs, list):
            for raw_quote in cast(List[object], quote_refs):
                if isinstance(raw_quote, dict):
                    cast(Payload, raw_quote).update(
                        {
                            "source_id": conversation_id,
                            "source_version": source_version,
                        }
                    )
    return payload


def _conversation_replacement_digest(
    uid: str,
    conversation_id: str,
    items: List[Dict[str, Any]],
) -> str:
    semantic_items: List[Dict[str, Any]] = []
    for item in items:
        evidence_payloads: List[Dict[str, Any]] = []
        raw_evidence = item.get("evidence")
        if isinstance(raw_evidence, list):
            for raw in cast(List[object], raw_evidence):
                if not isinstance(raw, dict):
                    continue
                evidence = cast(Payload, raw)
                evidence_payloads.append(
                    {
                        "source_type": evidence.get("source_type"),
                        "source_signal": evidence.get("source_signal"),
                        "extractor_id": evidence.get("extractor_id"),
                        "extractor_version": evidence.get("extractor_version"),
                        "artifact_ref": evidence.get("artifact_ref") or {},
                        "client_device_id": evidence.get("client_device_id"),
                        "quote_refs": evidence.get("quote_refs") or [],
                    }
                )
        semantic_items.append(
            {
                "id": item.get("id"),
                "content": item.get("content"),
                "category": item.get("category"),
                "tags": item.get("tags") or [],
                "visibility": item.get("visibility"),
                "subject_entity_id": item.get("subject_entity_id"),
                "subject_attribution": item.get("subject_attribution"),
                "subject_kind": item.get("subject_kind"),
                "sensitivity_labels": item.get("sensitivity_labels") or [],
                "evidence": evidence_payloads,
            }
        )
    semantic_items.sort(key=lambda item: (str(item.get("id") or ""), str(item.get("content") or "")))
    return deterministic_contract_id(
        "canonical-conversation-source-replacement",
        {
            "uid": uid,
            "conversation_id": conversation_id,
            "items": semantic_items,
        },
    )


def _backoff_before_replacement_retry(attempt: int, schedule: Sequence[float]) -> None:
    """Pause between conversation-replacement conflict rounds.

    A zero or missing entry keeps the round immediate, which is what callers
    that own an outer converging loop pass.
    """
    if attempt >= len(schedule):
        return
    delay = schedule[attempt]
    if delay > 0:
        time.sleep(delay)


def replace_conversation_sourced_memories(
    uid: str,
    conversation_id: str,
    items: List[Dict[str, Any]],
    *,
    db_client: Any = None,
    conflict_backoff_seconds: Sequence[float] = _REPLACEMENT_CONFLICT_BACKOFF_SECONDS,
    empty_set_intent: str = "retraction",
) -> Dict[str, Any]:
    """Atomically replace one conversation's complete canonical memory set.

    Every same-account canonical write races the account-global control CAS, so
    a conflicted round must re-plan against the control the peer left behind.
    ``conflict_backoff_seconds`` bounds those rounds: one entry per retry, and
    the number of attempts is ``len(...) + 1``.

    ``empty_set_intent`` states what an empty ``items`` means for this caller
    (FC-destructive-gate-keyed-on-proxy-for-intent: emptiness alone cannot
    carry intent). ``"retraction"`` — the default, and the only meaning before
    this parameter existed — treats it as "remove this conversation's rows",
    which demands ``explicit_memory_deletion`` authority whenever rows exist.
    ``"extraction"`` declares the empty set an extraction outcome: when the
    conversation already has rows and no deletion gate is held, the existing
    rows are kept and the call resolves as a no-op instead of failing —
    extraction variance is not permission to destroy knowledge.
    """
    if empty_set_intent not in {"retraction", "extraction"}:
        raise ValueError(f"unknown empty_set_intent: {empty_set_intent!r}")
    client = db_client if db_client is not None else default_db_client
    replacement_digest = _conversation_replacement_digest(uid, conversation_id, items)
    replacement_id = f"replace_{replacement_digest[:32]}"
    last_conflict: Optional[ConversationSourceReplacementConflict] = None
    for _attempt in range(len(conflict_backoff_seconds) + 1):
        observed_control = _read_replacement_control(uid, db_client=client)
        expected_source_items = [
            item
            for item in fetch_authoritative_product_memory_items_for_source(
                uid,
                conversation_id,
                db_client=client,
            )
            if item.status != MemoryItemStatus.tombstoned and _item_sourced_from_conversation(item, conversation_id)
        ]
        terminal_source_ids = [
            item.memory_id
            for item in expected_source_items
            if item.status == MemoryItemStatus.active
            and not (item.canonical_memory_id or item.superseded_by or "").strip()
        ]
        expected_reactivation_items = [
            item
            for item in fetch_authoritative_superseded_memory_items_for_targets(
                uid,
                terminal_source_ids,
                db_client=client,
            )
            if item.source_state == SourceState.active and not _item_sourced_from_conversation(item, conversation_id)
        ]
        if not items and not expected_source_items:
            # Nothing extracted, and nothing of this conversation's already in
            # the ledger. Falling through sends an empty write set into
            # ``replace_conversation_source_firestore``, whose empty-replacement
            # branch demands an ``explicit_memory_deletion`` token -- a
            # deliberate rule, because emptying a conversation normally
            # *retracts* its rows.
            #
            # Emptiness alone cannot tell the two callers apart. An explicit
            # retraction that happens to remove nothing must still be recorded,
            # advancing the source generation (WS-J delete-privacy contract).
            # Conversation finalization that simply extracted nothing is an
            # ordinary outcome owing no record, and holds no gate -- so it died
            # here with LegalHoldAuthorityUnavailable.
            #
            # The gate itself is what distinguishes them, so ask it without
            # letting the answer be fatal. Holding it means a deliberate
            # deletion: fall through and record. Not holding it means there is
            # provably nothing to do and no authority is required.
            #
            # This never relaxes the rule: an empty replacement that would
            # genuinely retract rows has a non-empty ``expected_source_items``,
            # never reaches here, and is still refused without authority.
            # ``expected_reactivation_items`` derives from
            # ``terminal_source_ids``, itself derived from
            # ``expected_source_items``, so it is necessarily empty here too.
            try:
                current_destructive_operation_token(uid, kind="explicit_memory_deletion")
            except LegalHoldAuthorityUnavailable:
                return {
                    "retracted_memory_ids": [],
                    "committed_memory_ids": [],
                    "reactivated_memory_ids": [],
                    "vector_delete_ids": [],
                    "tombstoned_evidence_ids": [],
                    "source_generation": observed_control.source_generation,
                }
        if not items and expected_source_items and empty_set_intent == "extraction":
            # An extraction that produced nothing over a conversation that
            # already has canonical rows. Falling through would retract those
            # rows, and the retraction branch rightly demands an
            # ``explicit_memory_deletion`` token the extraction path never
            # holds — the residual LegalHoldAuthorityUnavailable 500s on
            # conversation reprocess after #12410. Extraction emptiness is
            # model variance, not deletion intent: keep the rows and resolve
            # as a no-op. A caller that genuinely holds the deletion gate is
            # performing a deliberate deletion and still falls through so the
            # retraction is recorded.
            try:
                current_destructive_operation_token(uid, kind="explicit_memory_deletion")
            except LegalHoldAuthorityUnavailable:
                logger.info(
                    "conversation extraction was empty; keeping %d existing canonical rows uid=%s conversation_id=%s",
                    len(expected_source_items),
                    uid,
                    conversation_id,
                )
                return {
                    "retracted_memory_ids": [],
                    "committed_memory_ids": [],
                    "reactivated_memory_ids": [],
                    "vector_delete_ids": [],
                    "tombstoned_evidence_ids": [],
                    "source_generation": observed_control.source_generation,
                }
        confirmed_control = _read_replacement_control(uid, db_client=client)
        if (
            observed_control.head_commit_id != confirmed_control.head_commit_id
            or observed_control.account_generation != confirmed_control.account_generation
            or observed_control.source_generation != confirmed_control.source_generation
            or observed_control.commit_sequence != confirmed_control.commit_sequence
        ):
            last_conflict = ConversationSourceReplacementConflict(
                "memory control changed during conversation source scan"
            )
            _backoff_before_replacement_retry(_attempt, conflict_backoff_seconds)
            continue
        observed_control = confirmed_control
        next_generation = observed_control.source_generation + 1
        prepared_payloads = [
            _conversation_replacement_payload(
                uid,
                conversation_id,
                item,
                source_generation=next_generation,
            )
            for item in items
        ]
        planning_control = observed_control.model_copy(
            update={
                "source_generation": next_generation,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        replacement_operation = MemoryOperation.new(
            uid=uid,
            operation_type=MemoryOperationType.source_replacement,
            source_packet_id=conversation_id,
            target_memory_id=None,
            evidence_ids=[],
            logical_payload={
                "decision": "source_replace",
                "replacement_id": replacement_id,
                "replacement_digest": replacement_digest,
                "conversation_id": conversation_id,
                "new_memory_ids": sorted(str(payload.get("id") or "") for payload in prepared_payloads),
            },
            account_generation=planning_control.account_generation,
            source_generation=planning_control.source_generation,
            observed_head_commit_id=planning_control.head_commit_id,
        )
        replacement_commit_id = planning_control.next_commit_id(replacement_operation.operation_id)
        planning_control = planning_control.advance_head(replacement_commit_id)
        writes: List[CanonicalApplyWrite] = []
        for payload in prepared_payloads:
            write, _ = _canonical_extraction_apply_write(uid, payload, control=planning_control)
            preview_payload = dict(write.patch_payload)
            preview_payload["evidence"] = write.evidence
            preview = apply_long_term_patch_transaction(
                control_state=planning_control,
                operation=write.operation,
                patch_payload=preview_payload,
            )
            if preview.status != ApplyStatus.committed:
                raise RuntimeError(
                    f"canonical conversation replacement planning failed: " f"{preview.status.value} ({preview.reason})"
                )
            writes.append(write)
            planning_control = preview.control_state
        try:
            result = replace_conversation_source_firestore(
                uid=uid,
                conversation_id=conversation_id,
                replacement_id=replacement_id,
                replacement_digest=replacement_digest,
                replacement_operation=replacement_operation,
                observed_control=observed_control,
                expected_source_items=expected_source_items,
                expected_reactivation_items=expected_reactivation_items,
                writes=writes,
                deletion_gate_token=(
                    current_destructive_operation_token(uid, kind="explicit_memory_deletion") if not items else None
                ),
                db_client=client,
            )
            break
        except ConversationSourceReplacementConflict as exc:
            last_conflict = exc
            _backoff_before_replacement_retry(_attempt, conflict_backoff_seconds)
    else:
        raise ConversationReplacementConflictError(
            "canonical conversation replacement conflicted repeatedly"
        ) from last_conflict

    committed_ids = set(result.committed_memory_ids)
    cleanup_ids = [memory_id for memory_id in result.retracted_memory_ids if memory_id not in committed_ids]
    purge_canonical_memory_projections(
        uid,
        cleanup_ids,
        db_client=client,
        reason="conversation_reprocess_retract",
        preserve_source_replacement_receipts=True,
    )
    if belief_model_enabled() and result.committed_memory_ids:
        from utils.memory.belief_evidence import admit_committed_claims

        admit_committed_claims(uid, result.committed_memory_ids, items, db_client=client)
    return {
        "retracted_memory_ids": result.retracted_memory_ids,
        "committed_memory_ids": result.committed_memory_ids,
        "reactivated_memory_ids": result.reactivated_memory_ids,
        "vector_delete_ids": result.retracted_memory_ids,
        "tombstoned_evidence_ids": result.tombstoned_evidence_ids,
        "source_generation": result.control_state.source_generation,
    }


def _apply_canonical_user_mutation(
    uid: str,
    memory_id: str,
    *,
    mutation_kind: str,
    build_patch: UserMutationPatchBuilder,
    operation_type: MemoryOperationType = MemoryOperationType.user_mutation,
    allow_ledger_migration: bool = False,
    review_resolution: Optional[CanonicalReviewResolution] = None,
    trigger_feedback_receipt: Optional[JITTriggerFeedbackReceipt] = None,
    db_client: Any,
) -> Tuple[MemoryItem, MemoryItem]:
    """Apply one ordinary user mutation through the canonical transaction boundary."""
    for _attempt in range(3):
        item = _read_canonical_memory_item(uid, memory_id, db_client=db_client)
        if item is None:
            raise ValueError(f"canonical memory not found: {memory_id}")
        control = _ensure_control_state(uid, db_client=db_client)
        writer_class = MemoryWriterClass.ledger if allow_ledger_migration else MemoryWriterClass.user
        require_writer_admitted(
            control,
            writer_class,
            allow_ledger_migration=allow_ledger_migration,
        )
        now = max(datetime.now(timezone.utc), item.captured_at, item.updated_at)
        logical_updates, patch_updates = build_patch(item, now)
        logical_payload: Payload = {
            "decision": DurablePatchDecision.update.value,
            "target_memory_id": memory_id,
            "result_status": LifecycleState.active.value,
            **logical_updates,
        }
        evidence_ids = [evidence.evidence_id for evidence in item.evidence]
        mutation_identity = build_patch_mutation_identity(
            {
                **logical_payload,
                "evidence_ids": evidence_ids,
                "expected_item_revision": item.item_revision,
                "expected_content_hash": item.content_hash,
                **patch_updates,
            }
        )
        logical_payload["mutation_metadata"] = mutation_identity
        idempotency_key = deterministic_contract_id(
            "canonical-memory-user-mutation",
            {
                "uid": uid,
                "memory_id": memory_id,
                "item_revision": item.item_revision,
                "mutation_kind": mutation_kind,
                "logical_payload": logical_payload,
            },
        )
        operation = MemoryOperation.new(
            uid=uid,
            operation_type=operation_type,
            source_packet_id=(
                f"user_mutation:{mutation_kind}:{memory_id}:r{item.item_revision}:" f"{idempotency_key[:16]}"
            ),
            target_memory_id=memory_id,
            evidence_ids=evidence_ids,
            logical_payload=logical_payload,
            account_generation=control.account_generation,
            source_generation=control.source_generation,
            observed_head_commit_id=control.head_commit_id,
        )
        patch_payload: Payload = {
            "patch_id": f"patch_user_{idempotency_key[:24]}",
            "packet_id": f"user_mutation:{mutation_kind}:{memory_id}",
            "run_id": f"user_mutation:{mutation_kind}:{memory_id}",
            "observed_head_commit_id": control.head_commit_id,
            "idempotency_key": idempotency_key,
            **logical_payload,
            "evidence_ids": evidence_ids,
            "expected_item_revision": item.item_revision,
            "expected_content_hash": item.content_hash,
            **patch_updates,
        }
        patch_payload["mutation_metadata"] = mutation_identity
        apply_patch = (
            apply_long_term_patch_firestore if allow_ledger_migration else apply_direct_user_long_term_patch_firestore
        )
        result = apply_patch(
            uid=uid,
            operation_id=operation.operation_id,
            patch_payload=patch_payload,
            proposed_operation=operation,
            review_resolution=review_resolution,
            allow_ledger_migration=allow_ledger_migration,
            trigger_feedback_receipt=trigger_feedback_receipt,
            db_client=db_client,
        )
        if result.status in {ApplyStatus.committed, ApplyStatus.idempotent_skip}:
            updated = (
                result.memory_items[0]
                if result.memory_items
                else _read_canonical_memory_item(uid, memory_id, db_client=db_client)
            )
            if updated is None:
                raise RuntimeError("canonical user mutation committed without an active memory item")
            return item, updated
        if result.status == ApplyStatus.retryable_head_mismatch or (
            result.status == ApplyStatus.invalid_patch and "expected_" in (result.reason or "")
        ):
            continue
        raise RuntimeError(f"canonical user mutation failed: {result.status} ({result.reason})")
    raise RuntimeError("canonical user mutation conflicted repeatedly")


apply_canonical_user_mutation = _apply_canonical_user_mutation


@dataclass(frozen=True)
class CanonicalTriggerFeedbackResult:
    item: MemoryItem
    applied: bool
    receipt: JITTriggerFeedbackReceipt


def apply_canonical_trigger_feedback(
    uid: str,
    memory_id: str,
    *,
    event_id: str,
    expected_account_generation: int,
    expected_item_revision: int,
    feedback: Any,
    db_client: Any = None,
) -> CanonicalTriggerFeedbackResult:
    """Persist explicit trigger feedback through the canonical head transaction.

    The receipt contains only bounded identifiers, action, and timestamps. It
    is written atomically with the item revision and canonical head so replay,
    account deletion, and competing revisions cannot produce split authority.
    """

    client = db_client if db_client is not None else default_db_client
    parsed_feedback = TriggerFeedback.model_validate(feedback)
    normalized_uid = uid.strip()
    normalized_memory_id = memory_id.strip()
    normalized_event_id = event_id.strip()
    if parsed_feedback.note is not None:
        raise ValueError("durable trigger feedback must be content-free")
    if parsed_feedback.action not in {
        TriggerFeedbackAction.useful,
        TriggerFeedbackAction.false_positive,
        TriggerFeedbackAction.snooze,
        TriggerFeedbackAction.disable,
        TriggerFeedbackAction.missed_or_late,
    }:
        raise ValueError("unsupported durable trigger feedback action")
    receipt_payload: Payload = {
        "schema_version": "jit_trigger_feedback.v1",
        "uid": normalized_uid,
        "feedback_id": parsed_feedback.feedback_id,
        "event_id": normalized_event_id,
        "trigger_memory_id": normalized_memory_id,
        "account_generation": expected_account_generation,
        "expected_trigger_revision": expected_item_revision,
        "action": parsed_feedback.action.value,
        "recorded_at": parsed_feedback.recorded_at.isoformat(),
        "snoozed_until": (
            parsed_feedback.snoozed_until.isoformat() if parsed_feedback.snoozed_until is not None else None
        ),
    }
    request_hash = hashlib.sha256(
        json.dumps(receipt_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    proposed_receipt = JITTriggerFeedbackReceipt.model_validate({**receipt_payload, "request_hash": request_hash})
    replay = read_trigger_feedback_replay_firestore(
        normalized_uid,
        feedback_id=parsed_feedback.feedback_id,
        request_hash=request_hash,
        db_client=client,
    )
    if replay is not None:
        current, existing_receipt = replay
        return CanonicalTriggerFeedbackResult(item=current, applied=False, receipt=existing_receipt)

    initial = _read_canonical_memory_item(normalized_uid, normalized_memory_id, db_client=client)
    if initial is None:
        raise ValueError("feedback target is unavailable")
    if (
        initial.uid != normalized_uid
        or initial.account_generation != expected_account_generation
        or initial.item_revision != expected_item_revision
        or initial.kind != MemoryKind.trigger
        or initial.ledger_schema_version != _LEDGER_SCHEMA_VERSION
    ):
        raise ValueError("feedback target authority fence is stale")
    preview = apply_trigger_feedback(initial, parsed_feedback)
    if not preview.applied:
        raise RuntimeError("trigger feedback state exists without its durable receipt")

    def build_patch(item: MemoryItem, _now: datetime) -> Tuple[Payload, Payload]:
        if (
            item.account_generation != expected_account_generation
            or item.item_revision != expected_item_revision
            or item.kind != MemoryKind.trigger
            or item.ledger_schema_version != _LEDGER_SCHEMA_VERSION
        ):
            raise ValueError("feedback target authority fence is stale")
        updated = apply_trigger_feedback(item, parsed_feedback)
        if not updated.applied:
            raise RuntimeError("trigger feedback state exists without its durable receipt")
        result_status = (
            LifecycleState.hidden.value
            if updated.item.status == MemoryItemStatus.hidden
            else LifecycleState.active.value
        )
        return (
            {"result_status": result_status},
            {
                "arguments": updated.item.arguments,
                "curation_weight": updated.item.curation_weight,
            },
        )

    _, updated = _apply_canonical_user_mutation(
        normalized_uid,
        normalized_memory_id,
        mutation_kind=f"jit_trigger_feedback:{parsed_feedback.feedback_id}",
        build_patch=build_patch,
        operation_type=MemoryOperationType.ledger_mutation,
        trigger_feedback_receipt=proposed_receipt,
        db_client=client,
    )
    committed_snapshot = client.document(
        f"{MemoryCollections(uid=normalized_uid).jit_trigger_feedback}/{parsed_feedback.feedback_id}"
    ).get()
    if not getattr(committed_snapshot, "exists", False):
        raise RuntimeError("trigger feedback committed without its durable receipt")
    committed_receipt = JITTriggerFeedbackReceipt.model_validate(committed_snapshot.to_dict() or {})
    if committed_receipt.request_hash != request_hash:
        raise RuntimeError("trigger feedback receipt changed after commit")
    return CanonicalTriggerFeedbackResult(item=updated, applied=True, receipt=committed_receipt)


def adapt_canonical_memory_to_knowledge_ledger(
    uid: str,
    memory_id: str,
    *,
    expected_item_revision: int,
    updates: Dict[str, Any],
    db_client: Any = None,
) -> MemoryItem:
    """Idempotently adapt one active Long-term row in place to ledger metadata.

    This is a migration primitive, not a scanner or rollout switch. Callers
    must authorize and bound the cohort separately, then write the per-user
    completion marker only after every blocking row is adjudicated.
    """
    client = db_client if db_client is not None else default_db_client
    expected_updates = dict(updates)
    if expected_updates.get("ledger_schema_version") != "knowledge_ledger.v1":
        raise ValueError("ledger migration requires knowledge_ledger.v1 updates")

    def matches_existing(item: MemoryItem) -> bool:
        for key, expected in expected_updates.items():
            actual = getattr(item, key)
            if hasattr(actual, "value"):
                actual = actual.value
            if hasattr(expected, "value"):
                expected = expected.value
            if actual != expected:
                return False
        return True

    existing = _read_canonical_memory_item_for_lineage(uid, memory_id, db_client=client)
    if existing is None:
        raise ValueError(f"canonical memory not found: {memory_id}")
    if existing.ledger_schema_version == "knowledge_ledger.v1":
        if not matches_existing(existing):
            raise ValueError("existing ledger migration metadata conflicts with the requested plan")
        return existing

    def build_patch(item: MemoryItem, _now: datetime) -> Tuple[Payload, Payload]:
        if item.item_revision != expected_item_revision:
            raise ValueError("ledger migration source revision changed")
        if item.tier != MemoryLayer.long_term or item.status != MemoryItemStatus.active:
            raise ValueError("ledger migration only adapts active Long-term rows")
        if item.ledger_schema_version is not None:
            raise ValueError("canonical row already belongs to another ledger schema")
        return ({"result_status": LifecycleState.active.value}, expected_updates)

    _, updated = _apply_canonical_user_mutation(
        uid,
        memory_id,
        mutation_kind=f"knowledge_ledger_migration:r{expected_item_revision}",
        build_patch=build_patch,
        operation_type=MemoryOperationType.ledger_mutation,
        allow_ledger_migration=True,
        db_client=client,
    )
    return updated


def update_canonical_memory_content(uid: str, memory_id: str, content: str, *, db_client: Any = None) -> MemoryItem:
    client = db_client if db_client is not None else default_db_client
    trimmed = (content or "").strip()
    if not trimmed:
        raise ValueError("canonical update requires non-empty content")

    def build_patch(item: MemoryItem, now: datetime) -> Tuple[Payload, Payload]:
        promotion = _clear_settled_promotion_route(dict(item.promotion or {}))
        prior_receipt = promotion.pop("processing_receipt", None)
        processing_history = list(promotion.get("processing_history") or [])
        if isinstance(prior_receipt, dict):
            processing_history.append(prior_receipt)
        prior_submission = promotion.get("submission")
        submission_history = list(promotion.get("submission_history") or [])
        if isinstance(prior_submission, dict):
            submission_history.append(prior_submission)
        promotion.update(
            {
                "required": True,
                "status": REQUIRED_PROMOTION_STATUS_PENDING,
                "processing_status": REQUIRED_PROCESSING_STATUS_PENDING,
                "processor_id": REQUIRED_PROCESSOR_ID,
                "processor_version": REQUIRED_PROCESSOR_VERSION,
                "reason": "manual_user_correction",
                "source_surface": "memory_edit",
                "attempt_count": 0,
                "reviewed": True,
                "user_review": True,
                "processing_history": processing_history[-10:],
                "submission_history": submission_history[-10:],
                "submission": {
                    "submission_id": f"{memory_id}:revision:{item.item_revision + 1}",
                    "source_surface": "memory_edit",
                    "source_type": "manual_edit",
                    "source_id": memory_id,
                    "content_hash": hashlib.sha256(trimmed.encode("utf-8")).hexdigest(),
                    "submitted_at": now.isoformat(),
                },
            }
        )
        return (
            {
                "memory_text": trimmed,
                "target_tier": MemoryLayer.short_term.value,
                "target_user_asserted": True,
                "clear_graph_assertion": True,
            },
            {
                "promotion_audit": promotion,
                "expires_at": default_short_term_expiry(now),
                "kg_extracted": False,
                **(
                    {
                        "last_corroborated_at": now,
                        "corroboration_count": int(item.corroboration_count or 0) + 1,
                    }
                    if belief_model_enabled()
                    else {}
                ),
            },
        )

    previous, updated = _apply_canonical_user_mutation(
        uid,
        memory_id,
        mutation_kind="content_edit",
        build_patch=build_patch,
        db_client=client,
    )
    if previous.tier == MemoryLayer.long_term or previous.graph_ready or previous.kg_extracted:
        invalidate_kg_for_memory_retraction(uid, [memory_id], db_client=client)
    return updated


def refine_canonical_memory(
    uid: str,
    memory_id: str,
    arg_changes: Dict[str, Any],
    *,
    db_client: Any = None,
    review_resolution: Optional[CanonicalReviewResolution] = None,
) -> MemoryItem:
    """Apply a released review-queue correction through canonical state.

    Historical review records can carry structured argument changes in addition
    to replacement content. One canonical patch preserves those changes and
    returns the item to required Short-term processing; no historical writer is
    involved.
    """

    if not arg_changes:
        raise ValueError("canonical refinement requires argument changes")
    client = db_client if db_client is not None else default_db_client

    def build_patch(item: MemoryItem, now: datetime) -> Tuple[Payload, Payload]:
        replacement_content = item.content or ""
        arguments = dict(item.arguments or {})
        for key, raw_change in arg_changes.items():
            value = raw_change.get("to") if isinstance(raw_change, dict) and "to" in raw_change else raw_change
            if key == "content":
                if not isinstance(value, str) or not value.strip():
                    raise ValueError("canonical refinement content must be non-empty")
                replacement_content = value.strip()
            elif key != "edited":
                arguments[key] = value

        promotion = _clear_settled_promotion_route(dict(item.promotion or {}))
        prior_receipt = promotion.pop("processing_receipt", None)
        processing_history = list(promotion.get("processing_history") or [])
        if isinstance(prior_receipt, dict):
            processing_history.append(prior_receipt)
        promotion.update(
            {
                "required": True,
                "status": REQUIRED_PROMOTION_STATUS_PENDING,
                "processing_status": REQUIRED_PROCESSING_STATUS_PENDING,
                "processor_id": REQUIRED_PROCESSOR_ID,
                "processor_version": REQUIRED_PROCESSOR_VERSION,
                "reason": "manual_review_refinement",
                "source_surface": "memory_review_queue",
                "attempt_count": 0,
                "reviewed": True,
                "user_review": True,
                "processing_history": processing_history[-10:],
                "review_correction": copy.deepcopy(arg_changes),
            }
        )
        return (
            {
                "memory_text": replacement_content,
                "arguments": arguments,
                "target_tier": MemoryLayer.short_term.value,
                "target_user_asserted": True,
                "clear_graph_assertion": True,
            },
            {
                "promotion_audit": promotion,
                "expires_at": default_short_term_expiry(now),
                "kg_extracted": False,
            },
        )

    previous, updated = _apply_canonical_user_mutation(
        uid,
        memory_id,
        mutation_kind="review_refinement",
        build_patch=build_patch,
        review_resolution=review_resolution,
        db_client=client,
    )
    if previous.tier == MemoryLayer.long_term or previous.graph_ready or previous.kg_extracted:
        invalidate_kg_for_memory_retraction(uid, [memory_id], db_client=client)
    return updated


def update_canonical_memory_visibility(
    uid: str, memory_id: str, visibility: str, *, db_client: Any = None
) -> MemoryItem:
    client = db_client if db_client is not None else default_db_client
    if visibility not in _ALLOWED_MEMORY_VISIBILITIES:
        raise ValueError("visibility must be private, public, or shared")

    def build_patch(_item: MemoryItem, _now: datetime) -> Tuple[Payload, Payload]:
        return {"target_visibility": visibility}, {}

    _, updated = _apply_canonical_user_mutation(
        uid,
        memory_id,
        mutation_kind="visibility",
        build_patch=build_patch,
        db_client=client,
    )
    return updated


def update_canonical_memory_review(uid: str, memory_id: str, value: bool, *, db_client: Any = None) -> MemoryItem:
    client = db_client if db_client is not None else default_db_client

    def build_patch(item: MemoryItem, now: datetime) -> Tuple[Payload, Payload]:
        promotion = dict(item.promotion or {})
        promotion["reviewed"] = True
        promotion["user_review"] = value
        if promotion.get("required") is True and item.processing_state == ProcessingState.pending:
            if value and promotion.get("processing_status") == REQUIRED_PROCESSING_STATUS_REJECTED:
                promotion["processing_status"] = REQUIRED_PROCESSING_STATUS_PENDING
            elif not value:
                promotion["processing_status"] = REQUIRED_PROCESSING_STATUS_REJECTED
        patch_updates: Payload = {"promotion_audit": promotion}
        if not value:
            patch_updates["kg_extracted"] = False
        logical_updates: Payload = {}
        if belief_model_enabled():
            from utils.memory.belief_evidence import EvidenceEventJudgment, EvidenceEventKind, patch_for_evidence_event

            event = EvidenceEventKind.restated if value else EvidenceEventKind.contradicted
            patch = patch_for_evidence_event(
                item,
                EvidenceEventJudgment(event=event, target_memory_id=memory_id, rationale="explicit user review"),
                pointer="user_review",
                now=now,
                new_is_as_authoritative=False if not value else True,
            )
            if patch is not None:
                logical_updates, event_extra = patch
                patch_updates.update(event_extra)
        return logical_updates, patch_updates

    previous, updated = _apply_canonical_user_mutation(
        uid,
        memory_id,
        mutation_kind=f"review:{value}",
        build_patch=build_patch,
        db_client=client,
    )
    if not value and (previous.tier == MemoryLayer.long_term or previous.graph_ready or previous.kg_extracted):
        invalidate_kg_for_memory_retraction(uid, [memory_id], db_client=client)
    return updated


def resolve_canonical_memory_review(
    uid: str,
    memory_id: str,
    *,
    review_id: str,
    decision: str,
    correction: Optional[Dict[str, Any]] = None,
    reason: str = "",
    db_client: Any = None,
) -> Dict[str, Any]:
    """Resolve a canonical review without creating legacy memory authority.

    Accepted and corrected candidates return to pending Short-term so the
    canonical consolidation route remains the only Long-term admission owner.
    Rejected and dropped candidates are privacy-tombstoned through the same
    ledger transaction used by product deletion.
    """
    if decision not in {"accept", "correct", "reject", "drop"}:
        raise ValueError(f"unsupported canonical review decision: {decision}")
    client = db_client if db_client is not None else default_db_client
    item_path = f"{MemoryCollections(uid=uid).memory_items}/{memory_id}"
    item_snapshot = client.document(item_path).get()
    if not getattr(item_snapshot, "exists", False):
        raise CanonicalMemoryNotFoundError(f"canonical memory not found: {memory_id}")
    item = MemoryItem(**_snapshot_payload(item_snapshot))
    if item.uid != uid or item.memory_id != memory_id:
        raise CanonicalMemoryNotFoundError(f"canonical memory identity mismatch: {memory_id}")

    correction_payload = correction if isinstance(correction, dict) else {}
    if decision == "correct":
        correction_text = correction_payload.get("memory_text") or correction_payload.get("content")
        correction_args = correction_payload.get("arg_changes")
        if not (
            isinstance(correction_text, str)
            and correction_text.strip()
            or isinstance(correction_args, dict)
            and bool(correction_args)
        ):
            raise ValueError("canonical correct review resolution requires a non-empty correction")
    elif correction:
        raise ValueError(f"canonical {decision} review resolution does not accept correction data")

    review_resolution = CanonicalReviewResolution(
        review_id=review_id,
        memory_id=memory_id,
        decision=decision,
        reason=reason,
    )

    if decision in {"reject", "drop"}:
        with destructive_operation_gate(
            uid,
            kind="explicit_memory_deletion",
            firestore_client=client,
        ):
            try:
                tombstoned = _tombstone_memory_items_transaction(
                    uid,
                    [memory_id],
                    db_client=client,
                    reason=f"canonical_review_{decision}",
                    review_resolution=review_resolution,
                )
            except CanonicalReviewResolutionConflict as exc:
                prior_decision = (exc.review_item or {}).get("decision")
                if exc.status == "already_resolved" and prior_decision == decision:
                    # Older resolved rows may predate transactional review
                    # redaction. Replay is successful only after every
                    # review/correction projection has also been scrubbed.
                    purge_stale_review_conflicts_for_memories(
                        uid,
                        [memory_id],
                        reason=f"canonical_review_{decision}_replay",
                        db_client=client,
                        include_legacy_commits=True,
                    )
                    return {
                        "commit": {"commit_id": (exc.review_item or {}).get("resolution_commit_id")},
                        "memory_id": memory_id,
                        "decision": decision,
                        "idempotent": True,
                    }
                raise
            # This is required privacy work, not a best-effort latency
            # optimization. Keep the legal-hold gate until it succeeds so the
            # operation cannot report completion with plaintext derived rows.
            purge_stale_review_conflicts_for_memories(
                uid,
                [memory_id],
                reason=f"canonical_review_{decision}",
                db_client=client,
                include_legacy_commits=True,
            )
            purge_canonical_memory_projections(
                uid,
                [memory_id],
                db_client=client,
                reason=f"canonical_review_{decision}",
                include_review_queue=False,
            )
            resolved = tombstoned[0]
            return {
                "commit": {"commit_id": resolved.ledger_commit_id},
                "memory_id": memory_id,
                "decision": decision,
            }

    replacement_content = (
        correction_payload.get("memory_text") or correction_payload.get("content")
        if decision == "correct"
        else item.content
    )
    if not isinstance(replacement_content, str) or not replacement_content.strip():
        replacement_content = item.content or ""
    replacement_content = replacement_content.strip()
    if not replacement_content:
        raise ValueError("canonical review resolution requires memory content")
    arg_changes_raw: object = correction_payload.get("arg_changes")
    arg_changes = (
        cast(Dict[str, Any], arg_changes_raw) if decision == "correct" and isinstance(arg_changes_raw, dict) else {}
    )

    def build_patch(current: MemoryItem, now: datetime) -> Tuple[Payload, Payload]:
        next_promotion = _clear_settled_promotion_route(dict(current.promotion or {}))
        prior_receipt = next_promotion.pop("processing_receipt", None)
        processing_history = list(next_promotion.get("processing_history") or [])
        if isinstance(prior_receipt, dict):
            processing_history.append(prior_receipt)
        correction_audit: Payload = {}
        if arg_changes:
            correction_audit["arg_changes"] = copy.deepcopy(arg_changes)
        target_fact_id = correction_payload.get("target_fact_id")
        if isinstance(target_fact_id, str) and target_fact_id.strip():
            correction_audit["target_fact_id"] = target_fact_id.strip()
        if decision == "correct":
            correction_audit["corrected_content_hash"] = hashlib.sha256(replacement_content.encode("utf-8")).hexdigest()
        next_promotion.update(
            {
                "required": True,
                "status": REQUIRED_PROMOTION_STATUS_PENDING,
                "processing_status": REQUIRED_PROCESSING_STATUS_PENDING,
                "processor_id": REQUIRED_PROCESSOR_ID,
                "processor_version": REQUIRED_PROCESSOR_VERSION,
                "reason": f"canonical_review_{decision}",
                "source_surface": "memory_review_queue",
                "attempt_count": 0,
                "processing_history": processing_history[-10:],
                "reviewed": True,
                "user_review": True,
                "review_resolution_id": review_id,
                "review_decision": decision,
                "review_correction": correction_audit if decision == "correct" else None,
            }
        )
        logical: Payload = {
            "memory_text": replacement_content,
            "target_tier": MemoryLayer.short_term.value,
            "target_user_asserted": True,
            "clear_graph_assertion": current.graph_ready or current.kg_extracted,
        }
        if arg_changes:
            logical["arguments"] = {**current.arguments, **arg_changes}
        return (
            logical,
            {
                "promotion_audit": next_promotion,
                "expires_at": default_short_term_expiry(now),
                "kg_extracted": False,
            },
        )

    try:
        previous, updated = _apply_canonical_user_mutation(
            uid,
            memory_id,
            mutation_kind=f"review_resolution:{review_id}:{decision}",
            build_patch=build_patch,
            review_resolution=review_resolution,
            db_client=client,
        )
    except CanonicalReviewResolutionConflict as exc:
        prior_decision = (exc.review_item or {}).get("decision")
        if exc.status == "already_resolved" and prior_decision == decision:
            return {
                "commit": {"commit_id": (exc.review_item or {}).get("resolution_commit_id")},
                "memory_id": memory_id,
                "decision": decision,
                "idempotent": True,
            }
        raise
    if previous.graph_ready or previous.kg_extracted:
        invalidate_kg_for_memory_retraction(uid, [memory_id], db_client=client)
    return {
        "commit": {"commit_id": updated.ledger_commit_id},
        "memory_id": memory_id,
        "decision": decision,
    }


def update_canonical_memory_product_fields(
    uid: str,
    memory_id: str,
    *,
    tags: Optional[List[str]] = None,
    category: Optional[str] = None,
    is_baseline: Optional[bool] = None,
    is_read: Optional[bool] = None,
    is_dismissed: Optional[bool] = None,
    db_client: Any = None,
) -> MemoryItem:
    client = db_client if db_client is not None else default_db_client
    metadata: Dict[str, Any] = {}
    if tags is not None:
        metadata["tags"] = list(tags)
    if category is not None:
        metadata["category"] = category
    if is_baseline is not None:
        metadata["is_baseline"] = is_baseline
    if is_read is not None:
        metadata["is_read"] = bool(is_read)
    if is_dismissed is not None:
        metadata["is_dismissed"] = bool(is_dismissed)
    if not metadata:
        item = _read_canonical_memory_item(uid, memory_id, db_client=client)
        if item is None:
            raise ValueError(f"canonical memory not found: {memory_id}")
        return item

    def build_patch(item: MemoryItem, _now: datetime) -> Tuple[Payload, Payload]:
        promotion = dict(item.promotion or {})
        promotion.update(metadata)
        return {}, {"promotion_audit": promotion}

    _, updated = _apply_canonical_user_mutation(
        uid,
        memory_id,
        mutation_kind="product_metadata",
        build_patch=build_patch,
        db_client=client,
    )
    return updated


def _item_sourced_from_conversation(item: MemoryItem, conversation_id: str) -> bool:
    for evidence in item.evidence:
        if evidence.source_id == conversation_id:
            return True
        if evidence.conversation_id == conversation_id:
            return True
    return False


def _tombstone_memory_items_transaction(
    uid: str,
    memory_ids: List[str],
    *,
    db_client: Any,
    reason: str,
    expand_lineages: bool = False,
    not_found_error: type[ValueError] = CanonicalMemoryNotFoundError,
    authoritative_items: Optional[List[MemoryItem]] = None,
    review_resolution: Optional[CanonicalReviewResolution] = None,
) -> List[MemoryItem]:
    """Hold legal-hold authority across planning, commit, and privacy cleanup."""

    with destructive_operation_gate(
        uid,
        kind="explicit_memory_deletion",
        firestore_client=db_client,
    ):
        return _tombstone_memory_items_under_gate(
            uid,
            memory_ids,
            db_client=db_client,
            reason=reason,
            expand_lineages=expand_lineages,
            not_found_error=not_found_error,
            authoritative_items=authoritative_items,
            review_resolution=review_resolution,
        )


def _tombstone_memory_items_under_gate(
    uid: str,
    memory_ids: List[str],
    *,
    db_client: Any,
    reason: str,
    expand_lineages: bool = False,
    not_found_error: type[ValueError] = CanonicalMemoryNotFoundError,
    authoritative_items: Optional[List[MemoryItem]] = None,
    review_resolution: Optional[CanonicalReviewResolution] = None,
) -> List[MemoryItem]:
    """Plan under a control fence, then journal one atomic privacy commit."""
    if not memory_ids:
        return []

    requested_ids = list(dict.fromkeys(memory_ids))
    last_conflict: Optional[CanonicalMemoryTombstoneConflict] = None
    planned_items = authoritative_items
    for _attempt in range(3):
        observed_control = _read_replacement_control(uid, db_client=db_client)
        all_items = (
            planned_items
            if planned_items is not None
            else fetch_authoritative_product_memory_items(
                uid=uid,
                db_client=db_client,
            )
        )
        items_by_id = {item.memory_id: item for item in all_items}
        selected_ids = requested_ids
        if expand_lineages:
            selected_ids = _non_tombstoned_lineage_memory_ids(
                uid,
                requested_ids,
                db_client=db_client,
                not_found_error=not_found_error,
                items=all_items,
            )
        selected_items: List[MemoryItem] = []
        for memory_id in selected_ids:
            item = items_by_id.get(memory_id)
            if item is None or item.status == MemoryItemStatus.tombstoned:
                raise not_found_error(f"canonical memory not found: {memory_id}")
            selected_items.append(item)
        selected_id_set = set(selected_ids)
        preserved_evidence_ids = {
            evidence.evidence_id
            for item in all_items
            if item.status != MemoryItemStatus.tombstoned and item.memory_id not in selected_id_set
            for evidence in item.evidence
        }

        confirmed_control = _read_replacement_control(uid, db_client=db_client)
        if (
            observed_control.head_commit_id != confirmed_control.head_commit_id
            or observed_control.account_generation != confirmed_control.account_generation
            or observed_control.source_generation != confirmed_control.source_generation
            or observed_control.commit_sequence != confirmed_control.commit_sequence
        ):
            last_conflict = CanonicalMemoryTombstoneConflict("memory control changed during privacy source scan")
            continue
        try:
            result = tombstone_memory_items_firestore(
                uid=uid,
                reason=reason,
                observed_control=confirmed_control,
                expected_items=selected_items,
                preserved_evidence_ids=preserved_evidence_ids,
                deletion_gate_token=current_destructive_operation_token(uid, kind="explicit_memory_deletion"),
                review_resolution=review_resolution,
                db_client=db_client,
            )
        except CanonicalMemoryTombstoneLimitError as exc:
            raise CanonicalBatchMutationLimitError(str(exc)) from exc
        except CanonicalMemoryTombstoneConflict as exc:
            last_conflict = exc
            planned_items = None
            continue
        return result.memory_items
    raise RuntimeError("canonical privacy tombstone conflicted repeatedly") from last_conflict


def _privacy_tombstone_batches(items: List[MemoryItem]) -> List[List[MemoryItem]]:
    """Pack delete-all work under Firestore's exact transaction mutation cap."""
    batches: List[List[MemoryItem]] = []
    current: List[MemoryItem] = []
    current_evidence_ids: set[str] = set()
    for item in items:
        candidate_evidence_ids = current_evidence_ids.union(evidence.evidence_id for evidence in item.evidence)
        candidate_mutations = 4 + (4 * (len(current) + 1)) + len(candidate_evidence_ids)
        if current and candidate_mutations > 500:
            batches.append(current)
            current = []
            current_evidence_ids = set()
            candidate_evidence_ids = {evidence.evidence_id for evidence in item.evidence}
            candidate_mutations = 8 + len(candidate_evidence_ids)
        if candidate_mutations > 500:
            raise CanonicalBatchMutationLimitError(
                f"canonical memory {item.memory_id} alone exceeds Firestore's 500-mutation transaction limit"
            )
        current.append(item)
        current_evidence_ids = candidate_evidence_ids
    if current:
        batches.append(current)
    return batches


def _run_immediate_privacy_cleanup(
    uid: str,
    memory_id: str,
    *,
    db_client: Any,
    reason: str,
    include_review_queue: bool = True,
    preserve_source_replacement_receipts: bool = False,
) -> None:
    """Synchronously prove content-bearing derived copies are absent.

    The projection outbox remains crash/retry authority, but an explicit
    privacy operation must not acknowledge success while a provider still
    retains plaintext or source identifiers.
    """

    def _delete_keyword_projection() -> bool:
        from utils.memory.atom_keyword_index import delete_atom_keyword_doc

        return delete_atom_keyword_doc(uid, memory_id, db_client=db_client)

    if not delete_canonical_memory_vector(uid, memory_id):
        raise RuntimeError("canonical vector privacy cleanup unavailable")
    kg_db.delete_memory_graph_assertion(uid, memory_id, db_client=db_client)
    if not _delete_keyword_projection():
        raise RuntimeError("canonical keyword privacy cleanup unavailable")
    if include_review_queue:
        purge_stale_review_conflicts_for_memories(
            uid,
            [memory_id],
            reason=reason,
            db_client=db_client,
            include_legacy_commits=True,
            preserve_source_replacement_receipts=preserve_source_replacement_receipts,
        )


def purge_canonical_memory_projections(
    uid: str,
    memory_ids: List[str],
    *,
    db_client: Any,
    reason: str,
    include_review_queue: bool = True,
    preserve_source_replacement_receipts: bool = False,
) -> None:
    """Fail closed until every content-bearing canonical projection is gone."""

    unique_ids = list(dict.fromkeys(memory_id for memory_id in memory_ids if memory_id))
    for memory_id in unique_ids:
        _run_immediate_privacy_cleanup(
            uid,
            memory_id,
            db_client=db_client,
            reason=reason,
            include_review_queue=False,
            preserve_source_replacement_receipts=preserve_source_replacement_receipts,
        )
    if include_review_queue and unique_ids:
        purge_stale_review_conflicts_for_memories(
            uid,
            unique_ids,
            reason=reason,
            db_client=db_client,
            include_legacy_commits=True,
            preserve_source_replacement_receipts=preserve_source_replacement_receipts,
        )
    invalidate_kg_for_memory_retraction(uid, unique_ids, db_client=db_client)
    from database.memory_ledger import finalize_canonical_privacy_tombstones

    finalize_canonical_privacy_tombstones(
        uid,
        unique_ids,
        firestore_client=db_client,
        preserve_source_replacement_receipts=preserve_source_replacement_receipts,
    )


def _non_tombstoned_lineage_memory_ids(
    uid: str,
    requested_memory_ids: List[str],
    *,
    db_client: Any,
    not_found_error: type[ValueError],
    items: Optional[List[MemoryItem]] = None,
) -> List[str]:
    """Expand requested items to every non-tombstoned member of their lineages."""

    authoritative_items = (
        items if items is not None else fetch_authoritative_product_memory_items(uid=uid, db_client=db_client)
    )
    items_by_id = {item.memory_id: item for item in authoritative_items}
    lineage_roots: set[str] = set()
    for memory_id in dict.fromkeys(requested_memory_ids):
        item = items_by_id.get(memory_id)
        if item is None or item.status == MemoryItemStatus.tombstoned:
            raise not_found_error(f"canonical memory not found: {memory_id}")
        lineage_roots.add(_canonical_lineage_root(item, items_by_id=items_by_id))

    return sorted(
        item.memory_id
        for item in authoritative_items
        if item.status != MemoryItemStatus.tombstoned
        and _canonical_lineage_root(item, items_by_id=items_by_id) in lineage_roots
    )


def canonical_memory_lineage_ids(
    uid: str,
    requested_memory_ids: List[str],
    *,
    db_client: Any = None,
) -> List[str]:
    """Return the complete canonical lineage, including privacy tombstones.

    Explicit-deletion retries use this after the authoritative transaction has
    already tombstoned the requested row. Retained canonical alias pointers are
    content-free and keep the physical legacy cleanup set reconstructible.
    """

    client = db_client if db_client is not None else default_db_client
    items = fetch_authoritative_product_memory_items(uid=uid, db_client=client)
    items_by_id = {item.memory_id: item for item in items}
    roots: set[str] = set()
    for memory_id in dict.fromkeys(requested_memory_ids):
        item = items_by_id.get(memory_id)
        if item is None:
            raise CanonicalMemoryNotFoundError(f"canonical memory not found: {memory_id}")
        roots.add(_canonical_lineage_root(item, items_by_id=items_by_id))
    return sorted(item.memory_id for item in items if _canonical_lineage_root(item, items_by_id=items_by_id) in roots)


def _retracted_source_completion_control(
    uid: str,
    conversation_id: str,
    *,
    db_client: Any,
) -> Optional[MemoryControlState]:
    """Control state proving this source has nothing left to retract.

    Mirrors the double-read fence the replacement loop itself uses: the cohort
    scan only counts when the account-global control did not move while it
    ran. ``None`` means completion is unproven — callers must keep retrying
    the real replacement instead of treating the source as retracted.
    """
    before = _read_replacement_control(uid, db_client=db_client)
    live_source_items = [
        item
        for item in fetch_authoritative_product_memory_items_for_source(
            uid,
            conversation_id,
            db_client=db_client,
        )
        if item.status != MemoryItemStatus.tombstoned and _item_sourced_from_conversation(item, conversation_id)
    ]
    if live_source_items:
        return None
    after = _read_replacement_control(uid, db_client=db_client)
    if (
        before.head_commit_id != after.head_commit_id
        or before.account_generation != after.account_generation
        or before.source_generation != after.source_generation
        or before.commit_sequence != after.commit_sequence
    ):
        return None
    return after


def _already_retracted_result(
    uid: str,
    conversation_id: str,
    control: MemoryControlState,
    *,
    db_client: Any,
) -> Dict[str, Any]:
    """Recover the committed empty replacement, including cleanup identities.

    A canonical retraction may commit and then fail required derived-data
    cleanup. On retry the live source scan is empty, so the durable replacement
    receipt is the only complete, content-free inventory of IDs that must be
    scrubbed before success can be reported.
    """

    replacement_digest = _conversation_replacement_digest(uid, conversation_id, [])
    replacement_id = f"replace_{replacement_digest[:32]}"
    snapshot = db_client.document(f"{MemoryCollections(uid=uid).memory_source_replacements}/{replacement_id}").get()
    if not getattr(snapshot, "exists", False):
        # Successful cleanup removes the receipt last. A later idempotent retry
        # has already proven the source is empty under a stable control read, so
        # no remaining cleanup identities need recovery.
        return {
            "retracted_memory_ids": [],
            "committed_memory_ids": [],
            "reactivated_memory_ids": [],
            "vector_delete_ids": [],
            "tombstoned_evidence_ids": [],
            "source_generation": control.source_generation,
        }
    receipt = ConversationSourceReplacementReceipt.model_validate(_snapshot_payload(snapshot))
    if (
        receipt.uid != uid
        or receipt.conversation_id != conversation_id
        or receipt.replacement_id != replacement_id
        or receipt.replacement_digest != replacement_digest
        or receipt.control_state.account_generation != control.account_generation
        or receipt.committed_memory_ids
    ):
        raise ConversationReplacementConflictError("committed empty replacement receipt is invalid")
    return {
        "retracted_memory_ids": list(receipt.retracted_memory_ids),
        "committed_memory_ids": [],
        "reactivated_memory_ids": list(receipt.reactivated_memory_ids),
        "vector_delete_ids": list(receipt.retracted_memory_ids),
        "tombstoned_evidence_ids": list(receipt.tombstoned_evidence_ids),
        "source_generation": control.source_generation,
    }


def _retract_conversation_sourced_memories_under_gate(
    uid: str,
    conversation_id: str,
    *,
    db_client: Any = None,
) -> Dict[str, Any]:
    """Atomically replace one conversation's complete source set with nothing.

    Concurrent same-account canonical writes — parallel cascade deletes,
    extractions, merges — all race the account-global control CAS inside
    :func:`replace_conversation_sourced_memories`, whose three immediate
    attempts exhaust under sustained contention (#11726). A retraction
    converges instead of failing: after each conflict round it re-checks,
    under the same double-read control fence, whether the source is already
    empty. That covers both a peer worker that committed this retraction and
    a repeat delete whose committed receipt went stale after another
    conversation's replacement advanced the generation. A source that still
    has live items after every bounded round keeps raising, so callers fail
    closed with the conversation and its memories intact.
    """
    client = db_client if db_client is not None else default_db_client
    last_conflict: Optional[ConversationReplacementConflictError] = None
    for attempt in range(_RETRACT_CONFLICT_ATTEMPTS):
        try:
            return replace_conversation_sourced_memories(
                uid,
                conversation_id,
                [],
                db_client=client,
                conflict_backoff_seconds=_IMMEDIATE_REPLACEMENT_RETRY_BACKOFF,
            )
        except ConversationReplacementConflictError as exc:
            last_conflict = exc
            try:
                completed_control = _retracted_source_completion_control(uid, conversation_id, db_client=client)
            except Exception:
                # A rescue-check read failure must not reintroduce the 500
                # storm this loop exists to end — keep converging instead.
                logger.exception(
                    "canonical retraction completion check failed uid=%s conversation_id=%s",
                    uid,
                    conversation_id,
                )
                completed_control = None
            if completed_control is not None:
                return _already_retracted_result(
                    uid,
                    conversation_id,
                    completed_control,
                    db_client=client,
                )
            if attempt + 1 < _RETRACT_CONFLICT_ATTEMPTS:
                time.sleep(_RETRACT_CONFLICT_BACKOFF_SECONDS[min(attempt, len(_RETRACT_CONFLICT_BACKOFF_SECONDS) - 1)])
    raise ConversationReplacementConflictError(
        "canonical conversation retraction conflicted repeatedly"
    ) from last_conflict


def retract_conversation_sourced_memories(uid: str, conversation_id: str, *, db_client: Any = None) -> Dict[str, Any]:
    client = db_client if db_client is not None else default_db_client
    with destructive_operation_gate(
        uid,
        kind="explicit_memory_deletion",
        firestore_client=client,
    ):
        return _retract_conversation_sourced_memories_under_gate(
            uid,
            conversation_id,
            db_client=client,
        )


def delete_canonical_memory(uid: str, memory_id: str, *, db_client: Any = None) -> List[str]:
    client = db_client if db_client is not None else default_db_client
    with destructive_operation_gate(
        uid,
        kind="explicit_memory_deletion",
        firestore_client=client,
    ):
        return _delete_canonical_memory_under_gate(uid, memory_id, db_client=client)


def _delete_canonical_memory_under_gate(uid: str, memory_id: str, *, db_client: Any) -> List[str]:
    client = db_client
    tombstoned_items = _tombstone_memory_items_transaction(
        uid,
        [memory_id],
        db_client=client,
        reason="canonical_memory_delete",
        expand_lineages=True,
        not_found_error=ValueError,
    )
    lineage_ids = [item.memory_id for item in tombstoned_items]
    purge_canonical_memory_projections(
        uid,
        lineage_ids,
        db_client=client,
        reason="canonical_memory_delete",
    )
    return lineage_ids


def delete_canonical_memories_batch(uid: str, memory_ids: List[str], *, db_client: Any = None) -> List[str]:
    """Atomically tombstone a bounded set of complete canonical lineages.

    Firestore transactions retry when any read document changes, so a concurrent
    delete between validation and commit cannot leave a partially applied batch.
    Derived-index cleanup runs after the authoritative transaction commits.
    Search/vector/KG cleanup remains outbox-backed best effort, while review
    rows are synchronously scrubbed because they may contain plaintext.
    """
    if not memory_ids:
        return []

    client = db_client if db_client is not None else default_db_client
    with destructive_operation_gate(
        uid,
        kind="explicit_memory_deletion",
        firestore_client=client,
    ):
        return _delete_canonical_memories_batch_under_gate(uid, memory_ids, db_client=client)


def _delete_canonical_memories_batch_under_gate(
    uid: str,
    memory_ids: List[str],
    *,
    db_client: Any,
) -> List[str]:
    client = db_client
    tombstoned_items = _tombstone_memory_items_transaction(
        uid,
        memory_ids,
        db_client=client,
        reason="canonical_memory_delete_batch",
        expand_lineages=True,
        not_found_error=CanonicalMemoryNotFoundError,
    )
    lineage_ids = [item.memory_id for item in tombstoned_items]

    purge_canonical_memory_projections(
        uid,
        lineage_ids,
        db_client=client,
        reason="canonical_memory_delete_batch",
    )
    return lineage_ids


def _delete_canonical_memories_matching(
    uid: str,
    *,
    db_client: Any = None,
    should_delete: Callable[[MemoryItem], bool],
    should_cleanup: Callable[[MemoryItem], bool],
    reason: str,
) -> None:
    client = db_client if db_client is not None else default_db_client
    cleanup_ids: set[str] = set()
    completed = False
    for _round in range(5):
        observed_control = _read_replacement_control(uid, db_client=client)
        items = fetch_authoritative_product_memory_items(uid=uid, db_client=client)
        confirmed_control = _read_replacement_control(uid, db_client=client)
        if (
            observed_control.head_commit_id != confirmed_control.head_commit_id
            or observed_control.account_generation != confirmed_control.account_generation
            or observed_control.source_generation != confirmed_control.source_generation
            or observed_control.commit_sequence != confirmed_control.commit_sequence
        ):
            continue
        candidates = [item for item in items if should_delete(item)]
        cleanup_ids.update(item.memory_id for item in items if should_cleanup(item))
        if not candidates:
            completed = True
            break

        current_by_id = {item.memory_id: item for item in items}
        for batch in _privacy_tombstone_batches(candidates):
            tombstoned = _tombstone_memory_items_transaction(
                uid,
                [item.memory_id for item in batch],
                db_client=client,
                reason=reason,
                authoritative_items=list(current_by_id.values()),
            )
            for item in tombstoned:
                current_by_id[item.memory_id] = item
                cleanup_ids.add(item.memory_id)
    if not completed:
        raise RuntimeError("canonical delete-all conflicted with repeated concurrent writes")

    if cleanup_ids:
        purge_canonical_memory_projections(
            uid,
            sorted(cleanup_ids),
            db_client=client,
            reason=reason,
        )


def delete_all_canonical_memories(uid: str, *, db_client: Any = None) -> None:
    client = db_client if db_client is not None else default_db_client
    with destructive_operation_gate(
        uid,
        kind="explicit_memory_deletion",
        firestore_client=client,
    ):
        _delete_canonical_memories_matching(
            uid,
            db_client=client,
            should_delete=lambda item: item.status != MemoryItemStatus.tombstoned,
            should_cleanup=lambda item: True,
            reason="canonical_memory_delete_all",
        )


def delete_default_canonical_memories(uid: str, *, db_client: Any = None) -> None:
    """Privacy-delete default-access tiers while leaving Archive untouched (not_archive)."""
    client = db_client if db_client is not None else default_db_client
    with destructive_operation_gate(
        uid,
        kind="explicit_memory_deletion",
        firestore_client=client,
    ):
        _delete_canonical_memories_matching(
            uid,
            db_client=client,
            # not_archive: explicit default-tier privacy deletion scope.
            should_delete=lambda item: item.status != MemoryItemStatus.tombstoned and item.tier != MemoryLayer.archive,
            # not_archive: completed tombstones in the same deletion scope.
            should_cleanup=lambda item: item.tier != MemoryLayer.archive,
            reason="canonical_memory_delete_default",
        )


def purge_canonical_derived_user_data(uid: str, *, db_client: Any = None) -> Dict[str, Any]:
    """Purge every user-fenced memory projection during account deletion.

    Provider cleanup cannot depend on Firestore item enumeration: a prior
    partial wipe may have removed the authoritative documents while leaving
    old bare-ID or current user-scoped projections behind.
    """
    client = db_client if db_client is not None else default_db_client
    deletion_fence = read_account_deletion_projection_fence(uid, db_client=client)
    if not deletion_fence.blocks_projection_writes:
        raise RuntimeError("canonical provider purge requires an active account-deletion fence")
    processing_query = (
        client.collection(MemoryCollections(uid=uid).memory_outbox)
        .where(filter=FieldFilter("status", "==", "processing"))
        .limit(1)
    )
    if list(processing_query.stream()):
        raise RuntimeError("canonical provider purge deferred until leased projection work drains")

    items = fetch_authoritative_product_memory_items(uid=uid, db_client=client)
    memory_ids = [item.memory_id for item in items]
    vector_ids = [canonical_memory_provider_id(uid, memory_id) for memory_id in memory_ids]

    from database.vector_db import delete_canonical_memory_vectors

    if not delete_canonical_memory_vectors(uid):
        raise RuntimeError("canonical vector purge could not reach the provider")

    from utils.memory.atom_keyword_index import purge_user_atom_keyword_index

    keyword_deleted = purge_user_atom_keyword_index(uid, db_client=client, force=True, raise_on_failure=True)
    kg_db.delete_knowledge_graph(uid, db_client=client)

    trusted = read_memory_v3_trusted_account_generation(uid=uid, db_client=client)
    account_generation = trusted.account_generation if trusted.read_error_reason is None else 1
    projection_commit_id = trusted.head_commit_id or "head0"
    for item in items:
        purge_candidates = [
            {
                "vector_id": canonical_memory_provider_id(uid, item.memory_id),
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
        "reason": "user_scoped_provider_purge",
        "vector_ids": vector_ids,
        "memory_ids": memory_ids,
        "keyword_docs_deleted": keyword_deleted,
    }
