"""Canonical-cohort short-term promotion + TTL lifecycle (WS-B).

Promotion policy (Q3): batch-or-daily — promote when promotable count reaches the batch
threshold **or** ≥24h since ``last_promotion_run_at``, whichever comes first.

Promotability rule (canonical cohort only):
- ``tier=short_term``, ``status=active``, ``processing_state=processed``
- ``expires_at`` is in the future (not TTL-expired)
- ``source_state=active``

Promotion applies a layer transition ``short_term → long_term`` on the **same** record via
``apply_long_term_patch_firestore`` (update decision), audited in
``short_term_lifecycle_transitions`` and ``promotion`` on the memory item.

TTL: expired short-term items are hidden from default reads by the existing access policy;
the lifecycle worker records audit transitions (reused semantics from
``jobs/v17_short_term_lifecycle_worker.py``).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from database._client import db as default_db_client
from database.memory_collections import V17Collections
from database.memory_apply_store import apply_long_term_patch_firestore
from jobs.short_term_lifecycle_worker import (
    FirestoreShortTermLifecycleTransitionStore,
    ShortTermLifecycleTransitionRecord,
    build_short_term_lifecycle_transition_record,
    fetch_short_term_memory_items_firestore,
    process_short_term_lifecycle_item,
)
from models.memory_domain import (
    MemoryLayer,
    MemoryProcessingState,
    assert_legal_state,
    physical_status_to_record_status,
)
from models.memory_evidence import SourceState
from models.memory_apply import ApplyStatus, MemoryControlState
from models.memory_contracts import DurablePatchDecision, LifecycleState, deterministic_contract_id
from models.memory_operations import MemoryOperation, MemoryOperationType
from models.product_memory import MemoryItemStatus, MemoryTier, ProcessingState, V17MemoryItem
from utils.memory.atom_keyword_index import sync_atom_keyword_index_for_item
from utils.memory.memory_system import MemorySystem, resolve_memory_system
from utils.memory.short_term_lifecycle import ShortTermDisposition, evaluate_short_term_lifecycle

logger = logging.getLogger(__name__)

DEFAULT_PROMOTION_BATCH_THRESHOLD = 25
PROMOTION_BATCH_THRESHOLD_ENV = "MEMORY_CANONICAL_PROMOTION_BATCH_THRESHOLD"
PROMOTION_DAILY_INTERVAL = timedelta(hours=24)
PROMOTION_BY = "canonical_short_term_promotion"


def promotion_batch_threshold() -> int:
    raw = os.getenv(PROMOTION_BATCH_THRESHOLD_ENV, str(DEFAULT_PROMOTION_BATCH_THRESHOLD))
    try:
        value = int(raw)
    except ValueError:
        value = DEFAULT_PROMOTION_BATCH_THRESHOLD
    return max(1, value)


def _coerce_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def is_promotable_short_term_item(item: V17MemoryItem, *, now: datetime) -> bool:
    """Conservative promotability: active, processed, unexpired short_term."""
    current_time = _coerce_aware_utc(now)
    if item.tier != MemoryTier.short_term:
        return False
    if item.status != MemoryItemStatus.active:
        return False
    if item.processing_state != ProcessingState.processed:
        return False
    if item.source_state != SourceState.active:
        return False
    if item.expires_at is not None and item.expires_at <= current_time:
        return False
    return True


def list_promotable_short_term_items(
    uid: str,
    *,
    db_client=None,
    now: Optional[datetime] = None,
) -> List[V17MemoryItem]:
    client = db_client if db_client is not None else default_db_client
    current_time = _coerce_aware_utc(now or datetime.now(timezone.utc))
    items = fetch_short_term_memory_items_firestore(uid=uid, db_client=client)
    promotable = [item for item in items if is_promotable_short_term_item(item, now=current_time)]
    return sorted(promotable, key=lambda item: item.memory_id)


def promotion_trigger_reason(
    *,
    promotable_count: int,
    last_promotion_run_at: Optional[datetime],
    now: datetime,
    batch_threshold: Optional[int] = None,
) -> Optional[str]:
    """Return trigger reason when batch-or-daily fires; None when neither condition met."""
    if promotable_count <= 0:
        return None
    threshold = batch_threshold if batch_threshold is not None else promotion_batch_threshold()
    if promotable_count >= threshold:
        return "batch_threshold"
    current_time = _coerce_aware_utc(now)
    if last_promotion_run_at is None:
        return "daily_elapsed"
    if current_time - _coerce_aware_utc(last_promotion_run_at) >= PROMOTION_DAILY_INTERVAL:
        return "daily_elapsed"
    return None


def _read_control_state(uid: str, *, db_client) -> MemoryControlState:
    collections = V17Collections(uid=uid)
    ref = db_client.document(collections.memory_control_state)
    snapshot = ref.get()
    if getattr(snapshot, "exists", False):
        return MemoryControlState(**(snapshot.to_dict() or {}))
    control = MemoryControlState(uid=uid, head_commit_id="head0", account_generation=1, source_generation=1)
    ref.set(control.model_dump(mode="json"))
    return control


def _persist_control_state(control: MemoryControlState, *, db_client) -> None:
    db_client.document(V17Collections(uid=control.uid).memory_control_state).set(control.model_dump(mode="json"))


def _ensure_promotion_operation(
    *,
    uid: str,
    item: V17MemoryItem,
    control: MemoryControlState,
    run_id: str,
    db_client,
) -> MemoryOperation:
    logical_payload = {
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
    op_path = f"{V17Collections(uid=uid).memory_operations}/{operation.operation_id}"
    op_ref = db_client.document(op_path)
    if not op_ref.get().exists:
        op_ref.set(operation.model_dump(mode="json"))
    return operation


def promote_short_term_item_via_apply(
    uid: str,
    item: V17MemoryItem,
    *,
    control: MemoryControlState,
    run_id: str,
    trigger_reason: str,
    now: datetime,
    db_client=None,
) -> V17MemoryItem:
    """Promote one short_term item to long_term through the authoritative apply path."""
    if item.tier == MemoryTier.long_term:
        return item
    if not is_promotable_short_term_item(item, now=now):
        raise ValueError(f"memory item {item.memory_id} is not promotable")

    client = db_client if db_client is not None else default_db_client
    current_time = _coerce_aware_utc(now)
    operation = _ensure_promotion_operation(uid=uid, item=item, control=control, run_id=run_id, db_client=client)
    idempotency_key = deterministic_contract_id(
        "canonical-short-term-promotion",
        {"uid": uid, "memory_id": item.memory_id, "from_layer": MemoryTier.short_term.value},
    )
    promotion_audit = {
        "from_layer": MemoryTier.short_term.value,
        "to_layer": MemoryTier.long_term.value,
        "reason": trigger_reason,
        "at": current_time.isoformat(),
        "by": PROMOTION_BY,
    }
    patch_payload = {
        "patch_id": f"patch_promote_{idempotency_key[:24]}",
        "packet_id": f"promotion_{run_id}",
        "run_id": run_id,
        "observed_head_commit_id": control.head_commit_id,
        "idempotency_key": idempotency_key,
        "decision": DurablePatchDecision.update.value,
        "result_status": LifecycleState.active.value,
        "target_memory_id": item.memory_id,
        "memory_text": item.content,
        "target_tier": MemoryTier.long_term.value,
        "evidence_ids": [evidence.evidence_id for evidence in item.evidence],
        "promotion_audit": promotion_audit,
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
        snapshot = client.document(f"{V17Collections(uid=uid).memory_items}/{item.memory_id}").get()
        if getattr(snapshot, "exists", False):
            promoted = V17MemoryItem(**(snapshot.to_dict() or {}))

    assert_legal_state(
        MemoryLayer(promoted.tier.value),
        physical_status_to_record_status(promoted.status.value),
        MemoryProcessingState(promoted.processing_state.value),
    )
    if promoted.tier != MemoryTier.long_term:
        raise RuntimeError(f"promotion did not land long_term for {item.memory_id}")
    sync_atom_keyword_index_for_item(promoted, db_client=client)
    return promoted


def _audit_promotion_transition(
    item: V17MemoryItem,
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
    promoted_memory_ids: List[str] = field(default_factory=list)
    transition_records: List[ShortTermLifecycleTransitionRecord] = field(default_factory=list)
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
    promotion: Optional[ShortTermPromotionReport] = None
    lifecycle: Optional[CanonicalShortTermLifecycleReport] = None


def run_canonical_short_term_promotion(
    uid: str,
    *,
    db_client=None,
    now: Optional[datetime] = None,
    run_id: str,
    batch_threshold: Optional[int] = None,
) -> ShortTermPromotionReport:
    """Batch-or-daily promotion entry point for one canonical user."""
    client = db_client if db_client is not None else default_db_client
    current_time = _coerce_aware_utc(now or datetime.now(timezone.utc))

    if resolve_memory_system(uid, db_client=client) != MemorySystem.CANONICAL:
        return ShortTermPromotionReport(uid=uid, skipped_reason="not_canonical_cohort")

    promotable = list_promotable_short_term_items(uid, db_client=client, now=current_time)
    control = _read_control_state(uid, db_client=client)
    trigger = promotion_trigger_reason(
        promotable_count=len(promotable),
        last_promotion_run_at=control.last_promotion_run_at,
        now=current_time,
        batch_threshold=batch_threshold,
    )
    if trigger is None:
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
        promoted = promote_short_term_item_via_apply(
            uid,
            item,
            control=control,
            run_id=run_id,
            trigger_reason=trigger,
            now=current_time,
            db_client=client,
        )
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
    db_client=None,
    now: Optional[datetime] = None,
    run_id: str,
    limit: Optional[int] = None,
) -> CanonicalShortTermLifecycleReport:
    """TTL/decay audit for canonical short_term via the existing lifecycle worker."""
    client = db_client if db_client is not None else default_db_client
    current_time = _coerce_aware_utc(now or datetime.now(timezone.utc))

    if resolve_memory_system(uid, db_client=client) != MemorySystem.CANONICAL:
        return CanonicalShortTermLifecycleReport(uid=uid, skipped_reason="not_canonical_cohort")

    items = fetch_short_term_memory_items_firestore(uid=uid, db_client=client, limit=limit)
    store = FirestoreShortTermLifecycleTransitionStore(db_client=client, now=current_time)
    created = 0
    existing = 0
    for item in items:
        disposition = None
        if item.expires_at and item.expires_at <= current_time and item.tier == MemoryTier.short_term:
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
    db_client=None,
    now: Optional[datetime] = None,
    run_id: str,
) -> CanonicalShortTermMaintenanceReport:
    """Canonical-only wrapper: TTL audit then batch-or-daily promotion."""
    client = db_client if db_client is not None else default_db_client
    if resolve_memory_system(uid, db_client=client) != MemorySystem.CANONICAL:
        return CanonicalShortTermMaintenanceReport(uid=uid, skipped_reason="not_canonical_cohort")

    current_time = _coerce_aware_utc(now or datetime.now(timezone.utc))
    lifecycle = run_canonical_short_term_ttl_lifecycle(uid, db_client=client, now=current_time, run_id=run_id)
    promotion = run_canonical_short_term_promotion(uid, db_client=client, now=current_time, run_id=run_id)
    return CanonicalShortTermMaintenanceReport(uid=uid, promotion=promotion, lifecycle=lifecycle)


def count_promotable_short_term_items(uid: str, *, db_client=None, now: Optional[datetime] = None) -> int:
    return len(list_promotable_short_term_items(uid, db_client=db_client, now=now))
