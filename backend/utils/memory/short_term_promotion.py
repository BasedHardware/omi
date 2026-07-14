"""Canonical-cohort short-term promotion + TTL lifecycle (WS-B).

Promotion policy (Q3): batch-or-daily — promote when promotable count reaches the batch
threshold **or** ≥24h since ``last_promotion_run_at``, whichever comes first.

On a user's **first** promotion evaluation (``last_promotion_run_at`` unset), only the
batch threshold may fire — not the daily cadence. That prevents the first hourly cron
tick after whitelist from mass-promoting every short-term item. A successful promotion
run stamps ``last_promotion_run_at``; daily eligibility applies on subsequent ticks.

Promotability rule (canonical cohort only):
- ``tier=short_term``, ``status=active``, ``processing_state=processed``
- ``expires_at`` is in the future (not TTL-expired)
- ``source_state=active``

Promotion applies a layer transition ``short_term → long_term`` on the **same** record via
``apply_long_term_patch_firestore`` (update decision), audited in
``short_term_lifecycle_transitions`` and ``promotion`` on the memory item.

TTL: expired short-term items are hidden from default reads by the existing access policy;
the lifecycle worker records audit transitions (reused semantics from
``jobs/short_term_lifecycle_worker.py``).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Set, cast

from database._client import db as default_db_client
from database.memory_collections import MemoryCollections
from database.memory_apply_store import apply_long_term_patch_firestore
from jobs.short_term_lifecycle_worker import (
    FirestoreShortTermLifecycleTransitionStore,
    ShortTermLifecycleTransitionRecord,
    build_short_term_lifecycle_transition_record,
    fetch_short_term_memory_items_firestore,
    process_short_term_lifecycle_item,
)
from models.memory_domain import (
    MemoryLayer as DomainMemoryLayer,
    MemoryProcessingState,
    assert_legal_state,
    physical_status_to_record_status,
)
from models.memory_evidence import SourceState
from models.memory_apply import ApplyStatus, MemoryControlState
from models.memory_contracts import DurablePatchDecision, LifecycleState, deterministic_contract_id
from models.memory_operations import MemoryOperation, MemoryOperationType
from models.memory_admission import valid_required_processing_receipt
from models.product_memory import MemoryItemStatus, MemoryLayer, ProcessingState, MemoryItem
from utils.memory.atom_keyword_index import sync_atom_keyword_index_for_item
from utils.memory.canonical_consolidation import ConsolidationReport, run_canonical_consolidation
from utils.memory.canonical_required_processing import (
    RequiredMemoryProcessingReport,
    RequiredMemoryProcessor,
    run_required_memory_processing,
)
from utils.memory.required_promotion import (
    REQUIRED_PROCESSING_STATUS_PROCESSED,
    REQUIRED_PROMOTION_STATUS_PROMOTED,
    REQUIRED_PROMOTION_STATUSES,
)
from utils.memory.canonical_kg_promotion import CanonicalKgPromotionResult, extract_kg_for_promoted_memory
from utils.memory.canonical_vector_sync import sync_canonical_memory_vector
from utils.memory.memory_system import MemorySystem, resolve_memory_system
from utils.memory.short_term_lifecycle import ShortTermDisposition, evaluate_short_term_lifecycle

logger = logging.getLogger(__name__)

# Batch-or-daily promotion policy: promote when promotable count reaches this threshold.
DEFAULT_PROMOTION_BATCH_THRESHOLD = 25
PROMOTION_DAILY_INTERVAL = timedelta(hours=24)
PROMOTION_BY = "canonical_short_term_promotion"
MEMORY_CANONICAL_PROMOTION_FAST_TRACK_ENABLED_ENV = "MEMORY_CANONICAL_PROMOTION_FAST_TRACK_ENABLED"
Payload = Dict[str, Any]


def _empty_str_list() -> List[str]:
    return []


def _empty_transition_records() -> List[ShortTermLifecycleTransitionRecord]:
    return []


def _snapshot_payload(snapshot: Any) -> Payload:
    if not getattr(snapshot, "exists", False):
        return {}
    raw = snapshot.to_dict()
    return cast(Payload, raw) if isinstance(raw, dict) else {}


def promotion_fast_track_enabled() -> bool:
    raw = os.getenv(MEMORY_CANONICAL_PROMOTION_FAST_TRACK_ENABLED_ENV, "false")
    return raw.lower() == "true"


def promotion_batch_threshold() -> int:
    return DEFAULT_PROMOTION_BATCH_THRESHOLD


def _coerce_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def is_promotable_short_term_item(item: MemoryItem, *, now: datetime) -> bool:
    """Conservative promotability: active, processed, unexpired short_term."""
    current_time = _coerce_aware_utc(now)
    if item.tier != MemoryLayer.short_term:
        return False
    if item.status != MemoryItemStatus.active:
        return False
    if item.processing_state != ProcessingState.processed:
        return False
    if item.source_state != SourceState.active:
        return False
    if item.expires_at is not None and item.expires_at <= current_time:
        return False
    promotion = item.promotion or {}
    if promotion.get("user_review") is False:
        return False
    if promotion.get("required"):
        if promotion.get("processing_status") != REQUIRED_PROCESSING_STATUS_PROCESSED:
            return False
        if not valid_required_processing_receipt(
            content=item.content or "",
            item_revision=item.item_revision,
            promotion=promotion,
        ):
            return False
    return True


def list_promotable_short_term_items(
    uid: str,
    *,
    db_client: Any = None,
    now: Optional[datetime] = None,
) -> List[MemoryItem]:
    client: Any = db_client if db_client is not None else default_db_client
    current_time = _coerce_aware_utc(now or datetime.now(timezone.utc))
    items = fetch_short_term_memory_items_firestore(uid=uid, db_client=client)
    promotable = [item for item in items if is_promotable_short_term_item(item, now=current_time)]
    return sorted(promotable, key=lambda item: item.memory_id)


def is_fast_track_promotable(item: MemoryItem) -> bool:
    """O-W7 default: user_asserted only (env-gated, default-off)."""
    return promotion_fast_track_enabled() and bool(item.user_asserted)


def is_required_promotion_item(item: MemoryItem) -> bool:
    promotion = item.promotion or {}
    return (
        bool(promotion.get("required"))
        and promotion.get("user_review") is not False
        and promotion.get("status") in REQUIRED_PROMOTION_STATUSES
        and promotion.get("processing_status") == REQUIRED_PROCESSING_STATUS_PROCESSED
        and valid_required_processing_receipt(
            content=item.content or "",
            item_revision=item.item_revision,
            promotion=promotion,
        )
    )


def list_required_promotion_items(items: List[MemoryItem]) -> List[MemoryItem]:
    return [item for item in items if is_required_promotion_item(item)]


def _normalized_text(value: Optional[str]) -> str:
    return " ".join((value or "").strip().lower().split())


def _exact_long_term_duplicate(uid: str, item: MemoryItem, *, db_client: Any) -> Optional[MemoryItem]:
    normalized_content = _normalized_text(item.content)
    if not normalized_content:
        return None
    snapshots = (
        db_client.collection(MemoryCollections(uid=uid).memory_items)
        .where("tier", "==", MemoryLayer.long_term.value)
        .stream()
    )
    for snapshot in snapshots:
        payload = _snapshot_payload(snapshot)
        if not payload:
            continue
        candidate = MemoryItem(**payload)
        if candidate.uid != uid or candidate.status != MemoryItemStatus.active:
            continue
        if _normalized_text(candidate.content) != normalized_content:
            continue
        if item.subject_entity_id and candidate.subject_entity_id != item.subject_entity_id:
            continue
        if item.predicate and candidate.predicate != item.predicate:
            continue
        if item.arguments and dict(candidate.arguments or {}) != dict(item.arguments or {}):
            continue
        return candidate
    return None


def _merge_required_promotion_duplicate(
    uid: str,
    item: MemoryItem,
    existing: MemoryItem,
    *,
    control: MemoryControlState,
    run_id: str,
    trigger_reason: str,
    now: datetime,
    db_client: Any,
) -> tuple[MemoryItem, bool]:
    evidence_by_id = {evidence.evidence_id: evidence for evidence in existing.evidence}
    for evidence in item.evidence:
        evidence_by_id.setdefault(evidence.evidence_id, evidence)
    merged_evidence_ids = [evidence.evidence_id for evidence in evidence_by_id.values()]
    merge_idempotency_key = deterministic_contract_id(
        "canonical-required-promotion-duplicate-merge",
        {"uid": uid, "source_memory_id": item.memory_id, "target_memory_id": existing.memory_id},
    )
    merge_operation = _ensure_required_promotion_update_operation(
        uid=uid,
        target_memory_id=existing.memory_id,
        evidence_ids=merged_evidence_ids,
        logical_payload={
            "decision": DurablePatchDecision.update.value,
            "target_memory_id": existing.memory_id,
            "memory_text": existing.content,
            "result_status": LifecycleState.active.value,
        },
        control=control,
        source_packet_id=f"promotion_merge_{merge_idempotency_key}",
        db_client=db_client,
    )
    merge_result = apply_long_term_patch_firestore(
        uid=uid,
        operation_id=merge_operation.operation_id,
        patch_payload={
            "patch_id": f"patch_req_merge_{merge_idempotency_key[:24]}",
            "packet_id": f"promotion_{run_id}",
            "run_id": run_id,
            "observed_head_commit_id": control.head_commit_id,
            "idempotency_key": merge_idempotency_key,
            "decision": DurablePatchDecision.update.value,
            "result_status": LifecycleState.active.value,
            "target_memory_id": existing.memory_id,
            "memory_text": existing.content,
            "evidence_ids": merged_evidence_ids,
            "corroboration_count": existing.corroboration_count + 1,
            "last_corroborated_at": now.isoformat(),
        },
        db_client=db_client,
    )
    if merge_result.status not in {ApplyStatus.committed, ApplyStatus.idempotent_skip}:
        raise RuntimeError(
            f"required-promotion duplicate merge failed for {item.memory_id}: "
            f"{merge_result.status} ({merge_result.reason})"
        )
    merged_existing = (
        merge_result.memory_items[0]
        if merge_result.memory_items
        else _read_memory_item(
            uid,
            existing.memory_id,
            db_client=db_client,
        )
    )
    if merged_existing is None:
        raise RuntimeError(f"required-promotion duplicate merge lost target {existing.memory_id}")

    source_promotion = dict(item.promotion or {})
    source_promotion.update(
        {
            "status": "merged",
            "target_memory_id": existing.memory_id,
            "merged_at": now.isoformat(),
            "trigger_reason": trigger_reason,
        }
    )
    supersede_control = _read_control_state(uid, db_client=db_client)
    supersede_idempotency_key = deterministic_contract_id(
        "canonical-required-promotion-duplicate-supersede",
        {"uid": uid, "source_memory_id": item.memory_id, "target_memory_id": existing.memory_id},
    )
    supersede_operation = _ensure_required_promotion_update_operation(
        uid=uid,
        target_memory_id=item.memory_id,
        evidence_ids=[],
        logical_payload={
            "decision": DurablePatchDecision.update.value,
            "target_memory_id": item.memory_id,
            "result_status": LifecycleState.superseded.value,
        },
        control=supersede_control,
        source_packet_id=f"promotion_merge_supersede_{supersede_idempotency_key}",
        db_client=db_client,
    )
    supersede_result = apply_long_term_patch_firestore(
        uid=uid,
        operation_id=supersede_operation.operation_id,
        patch_payload={
            "patch_id": f"patch_req_sup_{supersede_idempotency_key[:24]}",
            "packet_id": f"promotion_{run_id}",
            "run_id": run_id,
            "observed_head_commit_id": supersede_control.head_commit_id,
            "idempotency_key": supersede_idempotency_key,
            "decision": DurablePatchDecision.update.value,
            "result_status": LifecycleState.superseded.value,
            "target_memory_id": item.memory_id,
            "memory_text": None,
            "evidence_ids": [],
            "promotion_audit": source_promotion,
            "superseded_by": existing.memory_id,
        },
        db_client=db_client,
    )
    if supersede_result.status not in {ApplyStatus.committed, ApplyStatus.idempotent_skip}:
        raise RuntimeError(
            f"required-promotion duplicate supersede failed for {item.memory_id}: "
            f"{supersede_result.status} ({supersede_result.reason})"
        )
    keyword_sync_succeeded = sync_atom_keyword_index_for_item(merged_existing, db_client=db_client)
    return merged_existing, keyword_sync_succeeded


def _ensure_required_promotion_update_operation(
    *,
    uid: str,
    target_memory_id: str,
    evidence_ids: List[str],
    logical_payload: Payload,
    control: MemoryControlState,
    source_packet_id: str,
    db_client: Any,
) -> MemoryOperation:
    operation = MemoryOperation.new(
        uid=uid,
        operation_type=MemoryOperationType.long_term_apply,
        source_packet_id=source_packet_id,
        target_memory_id=target_memory_id,
        evidence_ids=evidence_ids,
        logical_payload=logical_payload,
        account_generation=control.account_generation,
        source_generation=control.source_generation,
        observed_head_commit_id=control.head_commit_id,
    )
    op_path = f"{MemoryCollections(uid=uid).memory_operations}/{operation.operation_id}"
    op_ref = db_client.document(op_path)
    if not op_ref.get().exists:
        op_ref.set(operation.model_dump(mode="json"))
    return operation


def _read_memory_item(uid: str, memory_id: str, *, db_client: Any) -> Optional[MemoryItem]:
    payload = _snapshot_payload(db_client.document(f"{MemoryCollections(uid=uid).memory_items}/{memory_id}").get())
    if not payload:
        return None
    return MemoryItem(**payload)


def list_fast_track_promotable_items(
    uid: str,
    *,
    db_client: Any = None,
    now: Optional[datetime] = None,
) -> List[MemoryItem]:
    client: Any = db_client if db_client is not None else default_db_client
    current_time = _coerce_aware_utc(now or datetime.now(timezone.utc))
    return [
        item
        for item in list_promotable_short_term_items(uid, db_client=client, now=current_time)
        if is_fast_track_promotable(item)
    ]


def promotion_trigger_reason(
    *,
    promotable_count: int,
    last_promotion_run_at: Optional[datetime],
    now: datetime,
    batch_threshold: Optional[int] = None,
    required_promotion_count: int = 0,
) -> Optional[str]:
    """Return trigger reason when batch-or-daily fires; None when neither condition met.

    When ``last_promotion_run_at`` is unset (first evaluation for this user), only the
    batch threshold can trigger promotion — daily cadence requires a prior successful run.
    """
    if promotable_count <= 0:
        return None
    if required_promotion_count > 0:
        return "required_promotion"
    threshold = batch_threshold if batch_threshold is not None else promotion_batch_threshold()
    if promotable_count >= threshold:
        return "batch_threshold"
    if last_promotion_run_at is None:
        return None
    current_time = _coerce_aware_utc(now)
    if current_time - _coerce_aware_utc(last_promotion_run_at) >= PROMOTION_DAILY_INTERVAL:
        return "daily_elapsed"
    return None


def _read_control_state(uid: str, *, db_client: Any) -> MemoryControlState:
    collections = MemoryCollections(uid=uid)
    ref = db_client.document(collections.memory_apply_control_state)
    payload = _snapshot_payload(ref.get())
    if payload:
        return MemoryControlState(**payload)
    control = MemoryControlState(uid=uid, head_commit_id="head0", account_generation=1, source_generation=1)
    ref.set(control.model_dump(mode="json"))
    return control


def _persist_control_state(control: MemoryControlState, *, db_client: Any) -> None:
    # Write only the two fields promotion owns, with merge=True. A full-document
    # .set() overwrote the entire control doc from a non-transactional read snapshot,
    # so a concurrent apply_long_term_patch_firestore transaction landing between that
    # read and this write had its head_commit_id / commit_sequence / projection &
    # vector watermarks silently reverted (lost update). Mirrors the consolidation
    # writer (canonical_consolidation._persist_control_state).
    db_client.document(MemoryCollections(uid=control.uid).memory_apply_control_state).set(
        {
            "last_promotion_run_at": (
                control.last_promotion_run_at.isoformat() if control.last_promotion_run_at is not None else None
            ),
            "updated_at": control.updated_at.isoformat(),
        },
        merge=True,
    )


def _ensure_promotion_operation(
    *,
    uid: str,
    item: MemoryItem,
    control: MemoryControlState,
    run_id: str,
    db_client: Any,
) -> MemoryOperation:
    logical_payload: Payload = {
        "decision": DurablePatchDecision.update.value,
        "target_memory_id": item.memory_id,
        "memory_text": item.content,
        "result_status": LifecycleState.active.value,
    }
    operation = MemoryOperation.new(
        uid=uid,
        operation_type=MemoryOperationType.long_term_apply,
        source_packet_id=f"promotion_{run_id}",
        target_memory_id=item.memory_id,
        evidence_ids=[evidence.evidence_id for evidence in item.evidence],
        logical_payload=logical_payload,
        account_generation=control.account_generation,
        source_generation=control.source_generation,
        observed_head_commit_id=control.head_commit_id,
    )
    op_path = f"{MemoryCollections(uid=uid).memory_operations}/{operation.operation_id}"
    op_ref = db_client.document(op_path)
    if not op_ref.get().exists:
        op_ref.set(operation.model_dump(mode="json"))
    return operation


def promote_short_term_item_via_apply(
    uid: str,
    item: MemoryItem,
    *,
    control: MemoryControlState,
    run_id: str,
    trigger_reason: str,
    now: datetime,
    db_client: Any = None,
) -> tuple[MemoryItem, bool, CanonicalKgPromotionResult, bool]:
    """Promote one short_term item to long_term through the authoritative apply path.

    Firestore promotion commits even when external side effects fail. The returned
    vector bool is True when Pinecone upsert hard-failed, and the KG result exposes
    extraction failures or empty-but-successful extractions for rollout auditing.
    """
    if item.tier == MemoryLayer.long_term:
        return item, False, CanonicalKgPromotionResult(skipped_reason="already_long_term"), True
    if not is_promotable_short_term_item(item, now=now):
        raise ValueError(f"memory item {item.memory_id} is not promotable")

    client: Any = db_client if db_client is not None else default_db_client
    if resolve_memory_system(uid, db_client=client) != MemorySystem.CANONICAL:
        raise ValueError(f"promotion refused for non-canonical cohort uid={uid}")
    current_time = _coerce_aware_utc(now)
    if is_required_promotion_item(item):
        existing_duplicate = _exact_long_term_duplicate(uid, item, db_client=client)
        if existing_duplicate is not None:
            merged_item, keyword_sync_succeeded = _merge_required_promotion_duplicate(
                uid,
                item,
                existing_duplicate,
                control=control,
                run_id=run_id,
                trigger_reason=trigger_reason,
                now=current_time,
                db_client=client,
            )
            return (
                merged_item,
                False,
                CanonicalKgPromotionResult(skipped_reason="merged_into_existing"),
                keyword_sync_succeeded,
            )
    operation = _ensure_promotion_operation(uid=uid, item=item, control=control, run_id=run_id, db_client=client)
    idempotency_key = deterministic_contract_id(
        "canonical-short-term-promotion",
        {"uid": uid, "memory_id": item.memory_id, "from_layer": MemoryLayer.short_term.value},
    )
    promotion_audit = dict(item.promotion or {})
    if promotion_audit.get("required"):
        promotion_audit["status"] = REQUIRED_PROMOTION_STATUS_PROMOTED
    promotion_audit.update({"promoted_at": current_time.isoformat(), "trigger_reason": trigger_reason})
    promotion_audit.update(
        {
            "from_layer": MemoryLayer.short_term.value,
            "to_layer": MemoryLayer.long_term.value,
            "reason": trigger_reason,
            "at": current_time.isoformat(),
            "by": PROMOTION_BY,
        }
    )
    patch_payload: Payload = {
        "patch_id": f"patch_promote_{idempotency_key[:24]}",
        "packet_id": f"promotion_{run_id}",
        "run_id": run_id,
        "observed_head_commit_id": control.head_commit_id,
        "idempotency_key": idempotency_key,
        "decision": DurablePatchDecision.update.value,
        "result_status": LifecycleState.active.value,
        "target_memory_id": item.memory_id,
        "memory_text": item.content,
        "target_tier": MemoryLayer.long_term.value,
        "evidence_ids": [evidence.evidence_id for evidence in item.evidence],
        "promotion_audit": promotion_audit,
        "expected_item_revision": item.item_revision,
        "expected_content_hash": item.content_hash,
    }

    result = apply_long_term_patch_firestore(
        uid=uid,
        operation_id=operation.operation_id,
        patch_payload=patch_payload,
        db_client=client,
    )
    if result.status not in {ApplyStatus.committed, ApplyStatus.idempotent_skip}:
        raise RuntimeError(f"promotion apply failed for {item.memory_id}: {result.status} ({result.reason})")

    promoted = result.memory_items[0] if result.memory_items else item
    if result.status == ApplyStatus.idempotent_skip:
        payload = _snapshot_payload(
            client.document(f"{MemoryCollections(uid=uid).memory_items}/{item.memory_id}").get()
        )
        if payload:
            promoted = MemoryItem(**payload)

    assert_legal_state(
        DomainMemoryLayer(promoted.tier.value),
        physical_status_to_record_status(promoted.status.value),
        MemoryProcessingState(promoted.processing_state.value),
    )
    if promoted.tier != MemoryLayer.long_term:
        raise RuntimeError(f"promotion did not land long_term for {item.memory_id}")
    keyword_sync_succeeded = sync_atom_keyword_index_for_item(promoted, db_client=client)
    vector_sync_failed = False

    def _record_vector_sync_failure() -> None:
        nonlocal vector_sync_failed
        vector_sync_failed = True

    sync_canonical_memory_vector(promoted, on_hard_failure=_record_vector_sync_failure)
    kg_result = extract_kg_for_promoted_memory(uid, promoted, db_client=client)
    return promoted, vector_sync_failed, kg_result, keyword_sync_succeeded


def _audit_promotion_transition(
    item: MemoryItem,
    *,
    store: FirestoreShortTermLifecycleTransitionStore,
    run_id: str,
    now: datetime,
) -> ShortTermLifecycleTransitionRecord:
    decision = evaluate_short_term_lifecycle(
        item,
        now=_coerce_aware_utc(now),
        disposition=ShortTermDisposition.promote_to_long_term,
    )
    record = build_short_term_lifecycle_transition_record(item, decision=decision, run_id=run_id)
    store.persist_short_term_lifecycle_transition(record)
    return record


@dataclass
class ShortTermPromotionReport:
    uid: str
    skipped_reason: Optional[str] = None
    trigger_reason: Optional[str] = None
    promotable_count: int = 0
    promoted_memory_ids: List[str] = field(default_factory=_empty_str_list)
    transition_records: List[ShortTermLifecycleTransitionRecord] = field(default_factory=_empty_transition_records)
    vector_sync_failures: int = 0
    keyword_sync_failures: int = 0
    kg_extraction_failures: int = 0
    kg_extraction_empty: int = 0
    kg_nodes_created: int = 0
    kg_edges_created: int = 0
    last_promotion_run_at: Optional[datetime] = None

    @property
    def promoted_count(self) -> int:
        return len(self.promoted_memory_ids)


@dataclass
class CanonicalShortTermLifecycleReport:
    uid: str
    skipped_reason: Optional[str] = None
    lifecycle_created_count: int = 0
    lifecycle_existing_count: int = 0


@dataclass
class CanonicalShortTermMaintenanceReport:
    uid: str
    skipped_reason: Optional[str] = None
    required_processing: Optional[RequiredMemoryProcessingReport] = None
    consolidation: Optional[ConsolidationReport] = None
    promotion: Optional[ShortTermPromotionReport] = None
    lifecycle: Optional[CanonicalShortTermLifecycleReport] = None


def run_canonical_short_term_promotion(
    uid: str,
    *,
    db_client: Any = None,
    now: Optional[datetime] = None,
    run_id: str,
    batch_threshold: Optional[int] = None,
    consolidation_batched_ids: Optional[Set[str]] = None,
) -> ShortTermPromotionReport:
    """Batch-or-daily promotion entry point for one canonical user.

    ``consolidation_batched_ids`` gate semantics (maintenance pass only):

    - ``None``: consolidation did not fire this pass (not due / disabled) — no batch gate.
    - empty set: consolidation fired but failed or was watermark-blocked — defer all promotion.
    - non-empty set: consolidation completed cleanly — only batched survivors may promote.
    """
    client: Any = db_client if db_client is not None else default_db_client
    current_time = _coerce_aware_utc(now or datetime.now(timezone.utc))

    if resolve_memory_system(uid, db_client=client) != MemorySystem.CANONICAL:
        return ShortTermPromotionReport(uid=uid, skipped_reason="not_canonical_cohort")

    promotable = list_promotable_short_term_items(uid, db_client=client, now=current_time)
    allowed: Optional[Set[str]] = None
    if consolidation_batched_ids is not None:
        if not consolidation_batched_ids:
            return ShortTermPromotionReport(
                uid=uid,
                skipped_reason="consolidation_watermark_blocked",
                promotable_count=len(promotable),
                last_promotion_run_at=_read_control_state(uid, db_client=client).last_promotion_run_at,
            )
        allowed = set(consolidation_batched_ids)
        promotable = [item for item in promotable if item.memory_id in allowed]
    fast_track = list_fast_track_promotable_items(uid, db_client=client, now=current_time)
    required_promotion = list_required_promotion_items(promotable)
    control = _read_control_state(uid, db_client=client)
    trigger = promotion_trigger_reason(
        promotable_count=len(promotable),
        last_promotion_run_at=control.last_promotion_run_at,
        now=current_time,
        batch_threshold=batch_threshold,
        required_promotion_count=len(required_promotion),
    )
    if trigger == "required_promotion":
        promotable = required_promotion
    elif trigger is None and fast_track:
        trigger = "user_asserted_fast_track"
        if allowed is not None:
            promotable = [item for item in fast_track if item.memory_id in allowed]
        else:
            promotable = fast_track
    elif trigger is None:
        return ShortTermPromotionReport(
            uid=uid,
            skipped_reason="promotion_not_due",
            promotable_count=len(promotable),
            last_promotion_run_at=control.last_promotion_run_at,
        )

    report = ShortTermPromotionReport(
        uid=uid,
        trigger_reason=trigger,
        promotable_count=len(promotable),
        last_promotion_run_at=control.last_promotion_run_at,
    )
    transition_store = FirestoreShortTermLifecycleTransitionStore(db_client=client, now=current_time)

    for item in promotable:
        control = _read_control_state(uid, db_client=client)
        promoted, vector_sync_failed, kg_result, keyword_sync_succeeded = promote_short_term_item_via_apply(
            uid,
            item,
            control=control,
            run_id=run_id,
            trigger_reason=trigger,
            now=current_time,
            db_client=client,
        )
        if vector_sync_failed:
            report.vector_sync_failures += 1
        if not keyword_sync_succeeded:
            report.keyword_sync_failures += 1
        if kg_result.attempted and not kg_result.success:
            report.kg_extraction_failures += 1
        if kg_result.empty:
            report.kg_extraction_empty += 1
        report.kg_nodes_created += kg_result.node_count
        report.kg_edges_created += kg_result.edge_count
        report.promoted_memory_ids.append(promoted.memory_id)
        report.transition_records.append(
            _audit_promotion_transition(item, store=transition_store, run_id=run_id, now=current_time)
        )

    updated_control = _read_control_state(uid, db_client=client).model_copy(
        update={"last_promotion_run_at": current_time, "updated_at": current_time}
    )
    _persist_control_state(updated_control, db_client=client)
    report.last_promotion_run_at = current_time
    return report


def run_canonical_short_term_ttl_lifecycle(
    uid: str,
    *,
    db_client: Any = None,
    now: Optional[datetime] = None,
    run_id: str,
    limit: Optional[int] = None,
) -> CanonicalShortTermLifecycleReport:
    """TTL/decay audit for canonical short_term via the existing lifecycle worker."""
    client: Any = db_client if db_client is not None else default_db_client
    current_time = _coerce_aware_utc(now or datetime.now(timezone.utc))

    if resolve_memory_system(uid, db_client=client) != MemorySystem.CANONICAL:
        return CanonicalShortTermLifecycleReport(uid=uid, skipped_reason="not_canonical_cohort")

    items = fetch_short_term_memory_items_firestore(uid=uid, db_client=client, limit=limit)
    store = FirestoreShortTermLifecycleTransitionStore(db_client=client, now=current_time)
    created = 0
    existing = 0
    for item in items:
        disposition = None
        if item.expires_at and item.expires_at <= current_time and item.tier == MemoryLayer.short_term:
            disposition = ShortTermDisposition.reject_or_hide
        record, was_created = process_short_term_lifecycle_item(
            item,
            store=store,
            now=current_time,
            run_id=run_id,
            disposition=disposition,
        )
        if record is None:
            continue
        if was_created:
            created += 1
        else:
            existing += 1

    return CanonicalShortTermLifecycleReport(
        uid=uid,
        lifecycle_created_count=created,
        lifecycle_existing_count=existing,
    )


def run_canonical_short_term_maintenance(
    uid: str,
    *,
    db_client: Any = None,
    now: Optional[datetime] = None,
    run_id: str,
    llm_invoke: Optional[Callable[[str], str]] = None,
    recurrence_signal_sink: Optional[Callable[..., int]] = None,
    required_processor: Optional[RequiredMemoryProcessor] = None,
) -> CanonicalShortTermMaintenanceReport:
    """Canonical-only wrapper: required processing → TTL → consolidation → promotion."""
    client: Any = db_client if db_client is not None else default_db_client
    if resolve_memory_system(uid, db_client=client) != MemorySystem.CANONICAL:
        return CanonicalShortTermMaintenanceReport(uid=uid, skipped_reason="not_canonical_cohort")

    current_time = _coerce_aware_utc(now or datetime.now(timezone.utc))
    required_processing = run_required_memory_processing(
        uid,
        db_client=client,
        processor=required_processor,
        now=current_time,
    )
    lifecycle = run_canonical_short_term_ttl_lifecycle(uid, db_client=client, now=current_time, run_id=run_id)
    consolidation = run_canonical_consolidation(
        uid,
        db_client=client,
        now=current_time,
        run_id=run_id,
        llm_invoke=llm_invoke,
        recurrence_signal_sink=recurrence_signal_sink,
    )
    # Promotion gate: None = consolidation did not fire; empty set = fired but blocked (defer all);
    # non-empty set = fired cleanly — only items batched this pass may promote.
    if consolidation.trigger_reason and consolidation.watermark_blocked:
        promotion_batched_ids: Optional[Set[str]] = set()
    elif consolidation.trigger_reason and consolidation.batched_memory_ids:
        promotion_batched_ids = set(consolidation.batched_memory_ids)
    else:
        promotion_batched_ids = None

    promotion = run_canonical_short_term_promotion(
        uid,
        db_client=client,
        now=current_time,
        run_id=run_id,
        consolidation_batched_ids=promotion_batched_ids,
    )
    return CanonicalShortTermMaintenanceReport(
        uid=uid,
        required_processing=required_processing,
        consolidation=consolidation,
        promotion=promotion,
        lifecycle=lifecycle,
    )


def count_promotable_short_term_items(uid: str, *, db_client: Any = None, now: Optional[datetime] = None) -> int:
    return len(list_promotable_short_term_items(uid, db_client=db_client, now=now))
