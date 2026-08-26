"""Canonical Short-term maintenance and the sole L2 routing handoff.

The historical generic promotion pass was intentionally removed. Broad L1
observations remain Short-term until ``run_canonical_consolidation`` returns one
validated, item-addressed terminal route. A durable route commits the
Short-term-to-Long-term transition and its graph assertion in one transaction.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from database import knowledge_graph as kg_db
from database._client import db as default_db_client
from database.memory_collections import MemoryCollections
from database.memory_outbox_worker import (
    CanonicalMemoryOutboxSideEffects,
    CanonicalMemoryOutboxWorkerConfig,
    run_canonical_memory_outbox_worker_tick,
)
from database.review_queue import purge_stale_review_conflicts_for_memories
from jobs.short_term_lifecycle_worker import (
    FirestoreShortTermLifecycleTransitionStore,
    fetch_expired_short_term_memory_items_firestore,
    process_short_term_lifecycle_item,
)
from models.product_memory import MemoryItem, MemoryItemStatus, MemoryLayer, ProcessingState
from utils.memory.atom_keyword_index import delete_atom_keyword_doc, sync_atom_keyword_index_for_item
from models.memory_apply import MemoryControlState
from utils.memory.canonical_consolidation import (
    CONSOLIDATION_ATTEMPT_LEASE_SECONDS,
    ConsolidationAgentDecision,
    ConsolidationReport,
    apply_consolidation_decision,
    run_canonical_consolidation,
)
from utils.memory.canonical_required_processing import (
    REQUIRED_PROCESSING_ATTEMPT_LEASE_SECONDS,
    RequiredMemoryProcessingReport,
    RequiredMemoryProcessor,
    run_required_memory_processing,
)
from utils.memory.canonical_vector_sync import delete_canonical_memory_vector, sync_canonical_memory_vector
from utils.memory.memory_system import (
    MemorySystem as MemorySystem,  # compatibility export for legacy test doubles
    ensure_canonical_apply_control_state,
    resolve_memory_system as resolve_memory_system,  # compatibility export; universal routing does not call it
)
from utils.memory.short_term_lifecycle import ShortTermDisposition, effective_short_term_expiry

logger = logging.getLogger(__name__)


def _coerce_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass
class CanonicalShortTermLifecycleReport:
    uid: str
    skipped_reason: Optional[str] = None
    lifecycle_created_count: int = 0
    lifecycle_existing_count: int = 0
    lifecycle_terminal_count: int = 0


@dataclass
class CanonicalShortTermMaintenanceReport:
    uid: str
    skipped_reason: Optional[str] = None
    required_processing: Optional[RequiredMemoryProcessingReport] = None
    consolidation: Optional[ConsolidationReport] = None
    lifecycle: Optional[CanonicalShortTermLifecycleReport] = None
    outbox: Optional[Dict[str, Any]] = None

    @property
    def promoted_count(self) -> int:
        return len(self.consolidation.promoted_memory_ids) if self.consolidation is not None else 0

    @property
    def routed_count(self) -> int:
        return len(self.consolidation.batched_memory_ids) if self.consolidation is not None else 0


def _delete_atom_projection_and_citations(uid: str, memory_id: str, *, db_client: Any) -> bool:
    """Delete every keyword/KG/review projection owned by one canonical memory."""
    kg_db.delete_memory_graph_assertion(uid, memory_id, db_client=db_client)
    if not delete_atom_keyword_doc(uid, memory_id, db_client=db_client):
        return False
    kg_db.prune_memory_citations_from_kg(uid, [memory_id], db_client=db_client)
    item_path = f"{MemoryCollections(uid=uid).memory_items}/{memory_id}"
    snapshot = db_client.document(item_path).get()
    authoritative_item: Optional[MemoryItem] = None
    if getattr(snapshot, "exists", False):
        raw_item: object = snapshot.to_dict()
        if not isinstance(raw_item, dict):
            raise ValueError("authoritative memory item payload is invalid")
        authoritative_item = MemoryItem.model_validate(raw_item)
    preserve_pending_review = (
        authoritative_item is not None
        and authoritative_item.status == MemoryItemStatus.active
        # explicit_archive_memory: review outcomes are intentionally retained outside default reads.
        and authoritative_item.tier == MemoryLayer.archive
        and (authoritative_item.promotion or {}).get("route") == "review"
    )
    if not preserve_pending_review:
        purge_stale_review_conflicts_for_memories(
            uid,
            [memory_id],
            reason="memory_outbox_projection_deleted",
            db_client=db_client,
        )
    return True


def _canonical_outbox_side_effects(*, db_client: Any) -> CanonicalMemoryOutboxSideEffects:
    def projection_upsert(item: MemoryItem, account_generation: int) -> bool:
        del account_generation
        return sync_atom_keyword_index_for_item(item, db_client=db_client)

    def projection_delete(uid: str, memory_id: str, account_generation: int) -> bool:
        del account_generation
        return _delete_atom_projection_and_citations(uid, memory_id, db_client=db_client)

    def vector_upsert(item: MemoryItem, commit_id: str) -> bool:
        return sync_canonical_memory_vector(item, projection_commit_id=commit_id)

    return CanonicalMemoryOutboxSideEffects(
        projection_upsert=projection_upsert,
        projection_delete=projection_delete,
        vector_upsert=vector_upsert,
        vector_delete=delete_canonical_memory_vector,
    )


def _canonical_outbox_worker_config(*, run_id: str) -> CanonicalMemoryOutboxWorkerConfig:
    return CanonicalMemoryOutboxWorkerConfig(
        worker_id=f"canonical-maintenance:{run_id}"[:200],
        limit=100,
        scan_limit=500,
        lease_seconds=300,
        max_attempts=5,
        base_backoff_seconds=30,
        max_backoff_seconds=1800,
    )


def _drain_canonical_outbox(
    uid: str,
    *,
    db_client: Any,
    run_id: str,
    now: datetime,
    max_ticks: int = 5,
) -> Dict[str, Any]:
    """Drain a bounded pass, not just one page, so one maintenance run projects its own commits."""
    config = _canonical_outbox_worker_config(run_id=run_id)
    aggregate: Dict[str, Any] = {
        "uid": uid,
        "worker_id": config.worker_id,
        "ticks": 0,
        "leased_count": 0,
        "delivered_count": 0,
        "stale_settled_count": 0,
        "barrier_count": 0,
        "retryable_failure_count": 0,
        "dead_letter_count": 0,
        "ack_failed_count": 0,
        "actions": [],
        "errors": [],
    }
    side_effects = _canonical_outbox_side_effects(db_client=db_client)
    for _tick in range(max_ticks):
        summary = run_canonical_memory_outbox_worker_tick(
            db_client=db_client,
            uid=uid,
            config=config,
            side_effects=side_effects,
            now=now,
        )
        aggregate["ticks"] += 1
        for key in (
            "leased_count",
            "delivered_count",
            "stale_settled_count",
            "barrier_count",
            "retryable_failure_count",
            "dead_letter_count",
            "ack_failed_count",
        ):
            aggregate[key] += int(summary.get(key) or 0)
        aggregate["actions"].extend(summary.get("actions") or [])
        aggregate["errors"].extend(summary.get("errors") or [])
        if int(summary.get("leased_count") or 0) < config.limit:
            break
    return aggregate


def _merge_canonical_outbox_summaries(*summaries: Dict[str, Any]) -> Dict[str, Any]:
    """Combine independently bounded outbox passes into one maintenance report."""
    if not summaries:
        raise ValueError("at least one outbox summary is required")
    merged: Dict[str, Any] = {
        "uid": summaries[0]["uid"],
        "worker_id": summaries[0]["worker_id"],
        "ticks": 0,
        "leased_count": 0,
        "delivered_count": 0,
        "stale_settled_count": 0,
        "barrier_count": 0,
        "retryable_failure_count": 0,
        "dead_letter_count": 0,
        "ack_failed_count": 0,
        "actions": [],
        "errors": [],
    }
    for summary in summaries:
        for key in (
            "ticks",
            "leased_count",
            "delivered_count",
            "stale_settled_count",
            "barrier_count",
            "retryable_failure_count",
            "dead_letter_count",
            "ack_failed_count",
        ):
            merged[key] += int(summary.get(key) or 0)
        merged["actions"].extend(summary.get("actions") or [])
        merged["errors"].extend(summary.get("errors") or [])
    return merged


def run_canonical_short_term_ttl_lifecycle(
    uid: str,
    *,
    db_client: Any = None,
    now: Optional[datetime] = None,
    run_id: str,
    limit: Optional[int] = None,
) -> CanonicalShortTermLifecycleReport:
    """Audit expiry and settle indexed Short-term items through canonical L2 apply."""
    client: Any = db_client if db_client is not None else default_db_client
    current_time = _coerce_aware_utc(now or datetime.now(timezone.utc))

    # Universal accounts lazily receive the apply ledger.  Integrity failures
    # propagate and fail this UID closed; they never select a legacy lifecycle.
    ensure_canonical_apply_control_state(uid, db_client=client)

    items = fetch_expired_short_term_memory_items_firestore(
        uid=uid,
        db_client=client,
        now=current_time,
        limit=limit,
    )
    store = FirestoreShortTermLifecycleTransitionStore(db_client=client, now=current_time)
    created = 0
    existing = 0
    terminal = 0
    for item in items:
        disposition = None
        if item.tier == MemoryLayer.short_term and effective_short_term_expiry(item) <= current_time:
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
            logger.warning(
                "canonical_short_term_ttl_lifecycle: expired_without_recorded_disposition "
                "uid=%s memory_id=%s run_id=%s",
                uid,
                item.memory_id,
                run_id,
            )
        else:
            existing += 1
            logger.info(
                "canonical_short_term_ttl_lifecycle: expired_with_recorded_disposition "
                "uid=%s memory_id=%s run_id=%s",
                uid,
                item.memory_id,
                run_id,
            )
        if (
            disposition == ShortTermDisposition.reject_or_hide
            and item.status == MemoryItemStatus.active
            and item.processing_state == ProcessingState.processed
        ):
            control_snapshot = client.document(MemoryCollections(uid=uid).memory_apply_control_state).get()
            if not getattr(control_snapshot, "exists", False):
                raise RuntimeError("canonical memory control state is missing")
            raw_control = control_snapshot.to_dict()
            if not isinstance(raw_control, dict):
                raise RuntimeError("canonical memory control state is invalid")
            apply_consolidation_decision(
                uid,
                decision=ConsolidationAgentDecision(
                    source_memory_id=item.memory_id,
                    route="reject",
                    reconciliation="create",
                    relationship_to_user="unclear",
                    aboutness="unclear",
                    basis_for_memory="weak_or_none",
                    confidence="high",
                    rationale="Short-term TTL expired before durable admission.",
                ),
                pending_by_id={item.memory_id: item},
                control=MemoryControlState.model_validate(raw_control),
                run_id=f"{run_id}:ttl",
                now=current_time,
                db_client=client,
            )
            terminal += 1
            logger.info(
                "canonical_short_term_ttl_lifecycle: expired_terminal_disposition_applied "
                "uid=%s memory_id=%s disposition=%s run_id=%s",
                uid,
                item.memory_id,
                disposition.value,
                run_id,
            )

    return CanonicalShortTermLifecycleReport(
        uid=uid,
        lifecycle_created_count=created,
        lifecycle_existing_count=existing,
        lifecycle_terminal_count=terminal,
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
    required_processing_attempt_lease_seconds: int = REQUIRED_PROCESSING_ATTEMPT_LEASE_SECONDS,
    required_processing_result_guard: Optional[Callable[[], None]] = None,
    required_processing_limit: int = 0,
    consolidation_attempt_lease_seconds: int = CONSOLIDATION_ATTEMPT_LEASE_SECONDS,
    consolidation_result_guard: Optional[Callable[[], None]] = None,
) -> CanonicalShortTermMaintenanceReport:
    """Drain prior projections, run maintenance phases, then project their commits."""
    client: Any = db_client if db_client is not None else default_db_client
    ensure_canonical_apply_control_state(uid, db_client=client)

    current_time = _coerce_aware_utc(now or datetime.now(timezone.utc))
    # Settle already-committed invalidations before reading Short-term rows.
    # A malformed row must not starve an unrelated privacy/delete projection.
    pre_outbox_now = current_time if now is not None else datetime.now(timezone.utc)
    pre_outbox = _drain_canonical_outbox(
        uid,
        db_client=client,
        run_id=run_id,
        now=pre_outbox_now,
    )
    if required_processing_limit > 0:
        required_processing = run_required_memory_processing(
            uid,
            db_client=client,
            processor=required_processor,
            now=current_time,
            attempt_lease_seconds=required_processing_attempt_lease_seconds,
            result_guard=required_processing_result_guard,
            limit=required_processing_limit,
        )
    else:
        required_processing = RequiredMemoryProcessingReport(uid=uid)
    lifecycle = run_canonical_short_term_ttl_lifecycle(
        uid,
        db_client=client,
        now=current_time,
        run_id=run_id,
    )
    consolidation = run_canonical_consolidation(
        uid,
        db_client=client,
        now=current_time,
        run_id=run_id,
        llm_invoke=llm_invoke,
        recurrence_signal_sink=recurrence_signal_sink,
        attempt_lease_seconds=consolidation_attempt_lease_seconds,
        result_guard=consolidation_result_guard,
    )
    # In production, use a post-commit timestamp so events created during this
    # pass are immediately due. Explicit test/replay clocks remain deterministic.
    outbox_now = current_time if now is not None else datetime.now(timezone.utc)
    post_outbox = _drain_canonical_outbox(
        uid,
        db_client=client,
        run_id=run_id,
        now=outbox_now,
    )
    outbox = _merge_canonical_outbox_summaries(pre_outbox, post_outbox)
    return CanonicalShortTermMaintenanceReport(
        uid=uid,
        required_processing=required_processing,
        consolidation=consolidation,
        lifecycle=lifecycle,
        outbox=outbox,
    )


__all__ = [
    "CanonicalShortTermLifecycleReport",
    "CanonicalShortTermMaintenanceReport",
    "run_canonical_short_term_maintenance",
    "run_canonical_short_term_ttl_lifecycle",
]
