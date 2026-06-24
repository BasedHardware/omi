"""NON-DESTRUCTIVE legacy → canonical long-term backfill (WS-C).

Safety contract (locked directive):
- **COPY only** — reads legacy ``users/{uid}/memories`` via ``get_non_filtered_memories``
  (read-only); applies the same active-row filter as ``get_memories`` in-process. Writes canonical
  ``memory_items`` via ``apply_long_term_patch_firestore``. Legacy rows are **never** deleted,
  updated, or invalidated by this module.
- **Idempotent (Q4)** — deterministic canonical ``memory_id`` per legacy row (hash of uid + legacy id).
- **Resumable** — per-user checkpoint on ``memory_control/state`` (``legacy_backfill_*`` fields).
- **Dry-run** — reports intended writes without touching canonical or legacy stores.
- **Count-verified** — reconciles active legacy source count vs backfilled long_term destination ids.

Admin-only: invoke explicitly per uid; no cron, no auto-run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence

from database._client import db as default_db_client
from database.memories import get_non_filtered_memories
from database.memory_collections import V17Collections
from database.memory_apply_store import apply_long_term_patch_firestore
from models.memory_domain import (
    MemoryLayer as DomainMemoryLayer,
    MemoryProcessingState,
    assert_legal_state,
    physical_status_to_record_status,
)
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.memory_apply import ApplyStatus, MemoryControlState
from models.memory_contracts import DurablePatchDecision, LifecycleState, deterministic_contract_id
from models.memory_operations import MemoryOperation, MemoryOperationType
from models.product_memory import MemoryItemStatus, MemoryLayer, ProcessingState, V17MemoryItem
from utils.memory.atom_keyword_index import sync_atom_keyword_index_for_item
from utils.memory.canonical_vector_sync import sync_canonical_memory_vector
from utils.memory.product_memory_read_service import fetch_authoritative_product_memory_items

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 50
LEGACY_SCAN_PAGE_SIZE = 500


@dataclass(frozen=True)
class BackfillReport:
    uid: str
    dry_run: bool
    source_count: int
    intended_count: int
    written_count: int
    skipped_already_present: int
    destination_count: int
    verified: bool
    discrepancy: Optional[str] = None
    resumed_from_index: int = 0
    completed: bool = False
    legacy_rows_touched: int = 0
    vector_sync_failures: int = 0
    errors: List[str] = field(default_factory=list)


def legacy_backfill_memory_id(*, uid: str, legacy_memory_id: str) -> str:
    """Q4 hash-derived neutral canonical id for one legacy row."""
    return (
        "mem_"
        + deterministic_contract_id(
            "legacy-backfill-memory",
            {"uid": uid, "legacy_memory_id": legacy_memory_id},
        )[:32]
    )


def legacy_backfill_idempotency_key(*, uid: str, legacy_memory_id: str) -> str:
    return deterministic_contract_id(
        "legacy-backfill-idempotency",
        {"uid": uid, "legacy_memory_id": legacy_memory_id},
    )


def legacy_source_fingerprint(legacy_rows: Sequence[Dict[str, Any]]) -> str:
    legacy_ids = sorted(row.get("id") or "" for row in legacy_rows)
    return deterministic_contract_id("legacy-backfill-source-set", {"legacy_ids": legacy_ids})


def _coerce_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def is_active_legacy_row(row: dict) -> bool:
    """Mirror ``get_memories`` default semantics: active, non-user-rejected rows only."""
    return row.get("user_review") is not False and row.get("invalid_at") is None


def _fetch_active_legacy_memories(
    uid: str,
    *,
    get_non_filtered_memories_fn: Callable[..., List[dict]],
    scan_page_size: int = LEGACY_SCAN_PAGE_SIZE,
) -> List[dict]:
    """Read-only scan of active legacy memories (never writes).

    Paginates over the raw Firestore page from ``get_non_filtered_memories`` so
    ``len(page) < page_size`` reliably signals end-of-data even when many rows in
    a page are inactive and filtered out here.
    """
    all_rows: List[dict] = []
    offset = 0
    page_size = scan_page_size
    while True:
        page = get_non_filtered_memories_fn(uid, limit=page_size, offset=offset)
        if not page:
            break
        for row in page:
            if is_active_legacy_row(row):
                all_rows.append(row)
        if len(page) < page_size:
            break
        offset += page_size
    return sorted(all_rows, key=lambda row: row.get("id") or "")


def _read_control_state(uid: str, *, db_client, create_if_missing: bool = True) -> MemoryControlState:
    collections = V17Collections(uid=uid)
    ref = db_client.document(collections.memory_control_state)
    snapshot = ref.get()
    if getattr(snapshot, "exists", False):
        return MemoryControlState(**(snapshot.to_dict() or {}))
    control = MemoryControlState(uid=uid, head_commit_id="head0", account_generation=1, source_generation=1)
    if create_if_missing:
        ref.set(control.model_dump(mode="json"))
    return control


def _persist_control_state(control: MemoryControlState, *, db_client) -> None:
    db_client.document(V17Collections(uid=control.uid).memory_control_state).set(control.model_dump(mode="json"))


def _legacy_evidence_id(*, uid: str, legacy_memory_id: str, index: int) -> str:
    return (
        "ev_lb_"
        + deterministic_contract_id(
            "legacy-backfill-evidence",
            {"uid": uid, "legacy_memory_id": legacy_memory_id, "index": index},
        )[:28]
    )


def _build_backfill_evidence(
    *,
    uid: str,
    legacy_row: dict,
    index: int,
) -> MemoryEvidence:
    legacy_id = legacy_row.get("id") or f"legacy_{index}"
    conversation_id = legacy_row.get("conversation_id") or legacy_row.get("memory_id")
    raw_evidence = legacy_row.get("evidence") or []
    if raw_evidence and isinstance(raw_evidence[0], dict) and raw_evidence[0].get("evidence_id"):
        first = raw_evidence[0]
        source_id = first.get("source_id") or conversation_id or legacy_id
        source_type = first.get("source_type") or ("conversation" if conversation_id else "legacy_memory")
        return MemoryEvidence(
            evidence_id=first["evidence_id"],
            source_type=source_type,
            source_id=source_id,
            source_version="v1",
            conversation_id=conversation_id if source_type == "conversation" else None,
            artifact_preservation=ArtifactPreservationState.preserved,
        )

    source_id = conversation_id or legacy_id
    source_type = "conversation" if conversation_id else "legacy_memory"
    return MemoryEvidence(
        evidence_id=_legacy_evidence_id(uid=uid, legacy_memory_id=legacy_id, index=index),
        source_type=source_type,
        source_id=source_id,
        source_version="v1",
        conversation_id=conversation_id if source_type == "conversation" else None,
        artifact_preservation=ArtifactPreservationState.preserved,
    )


def _persist_evidence(uid: str, evidence: MemoryEvidence, *, db_client) -> None:
    collections = V17Collections(uid=uid)
    path = f"{collections.memory_evidence}/{evidence.evidence_id}"
    ref = db_client.document(path)
    if not ref.get().exists:
        ref.set(evidence.model_dump(mode="json"))


def _ensure_backfill_operation(
    *,
    uid: str,
    legacy_row: dict,
    canonical_memory_id: str,
    control: MemoryControlState,
    run_id: str,
    evidence_ids: List[str],
    db_client,
) -> MemoryOperation:
    legacy_id = legacy_row.get("id") or canonical_memory_id
    content = (legacy_row.get("content") or "").strip()
    logical_payload = {
        "decision": DurablePatchDecision.add.value,
        "memory_text": content,
        "result_status": LifecycleState.active.value,
    }
    operation = MemoryOperation.new(
        uid=uid,
        operation_type=MemoryOperationType.long_term_apply,
        source_packet_id=f"legacy_backfill_{legacy_id}",
        target_memory_id=None,
        evidence_ids=evidence_ids,
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


def _apply_one_legacy_row(
    *,
    uid: str,
    legacy_row: dict,
    index: int,
    control: MemoryControlState,
    run_id: str,
    db_client,
) -> tuple[MemoryControlState, bool, Optional[str], bool]:
    """Write one canonical long_term item. Returns (control, written, skip_reason, vector_sync_failed)."""
    legacy_id = legacy_row.get("id") or f"legacy_{index}"
    content = (legacy_row.get("content") or "").strip()
    if not content:
        return control, False, "empty_content", False

    canonical_memory_id = legacy_backfill_memory_id(uid=uid, legacy_memory_id=legacy_id)
    existing_path = f"{V17Collections(uid=uid).memory_items}/{canonical_memory_id}"
    existing_snapshot = db_client.document(existing_path).get()
    if getattr(existing_snapshot, "exists", False):
        existing = V17MemoryItem.model_validate(existing_snapshot.to_dict() or {})
        if (
            existing.tier == MemoryLayer.long_term
            and existing.status == MemoryItemStatus.active
            and existing.processing_state == ProcessingState.processed
        ):
            return control, False, "already_present", False

    evidence = _build_backfill_evidence(uid=uid, legacy_row=legacy_row, index=index)
    _persist_evidence(uid, evidence, db_client=db_client)

    operation = _ensure_backfill_operation(
        uid=uid,
        legacy_row=legacy_row,
        canonical_memory_id=canonical_memory_id,
        control=control,
        run_id=run_id,
        evidence_ids=[evidence.evidence_id],
        db_client=db_client,
    )

    idempotency_key = legacy_backfill_idempotency_key(uid=uid, legacy_memory_id=legacy_id)
    patch_payload = {
        "patch_id": f"patch_lb_{idempotency_key[:24]}",
        "packet_id": f"legacy_backfill_{legacy_id}",
        "run_id": run_id,
        "observed_head_commit_id": control.head_commit_id,
        "idempotency_key": idempotency_key,
        "decision": DurablePatchDecision.add.value,
        "result_status": LifecycleState.active.value,
        "evidence_ids": [evidence.evidence_id],
        "new_memory_id": canonical_memory_id,
        "memory_text": content,
        "confidence": "medium",
        "relationship_to_user": "self",
        "initial_tier": MemoryLayer.long_term.value,
    }

    result = apply_long_term_patch_firestore(
        uid=uid,
        operation_id=operation.operation_id,
        patch_payload=patch_payload,
        db_client=db_client,
    )
    if result.status not in {ApplyStatus.committed, ApplyStatus.idempotent_skip}:
        raise RuntimeError(f"legacy backfill apply failed for {legacy_id}: {result.status} ({result.reason})")

    item = result.memory_items[0] if result.memory_items else None
    if item is None and result.status == ApplyStatus.idempotent_skip:
        snapshot = db_client.document(f"{V17Collections(uid=uid).memory_items}/{canonical_memory_id}").get()
        if getattr(snapshot, "exists", False):
            item = V17MemoryItem(**(snapshot.to_dict() or {}))

    vector_sync_failed = False

    def _record_vector_sync_failure() -> None:
        nonlocal vector_sync_failed
        vector_sync_failed = True

    if item is not None:
        assert_legal_state(
            DomainMemoryLayer(item.tier.value),
            physical_status_to_record_status(item.status.value),
            MemoryProcessingState(item.processing_state.value),
        )
        sync_atom_keyword_index_for_item(item, db_client=db_client)
        sync_canonical_memory_vector(item, on_hard_failure=_record_vector_sync_failure)

    written = result.status == ApplyStatus.committed
    return result.control_state, written, None if written else "idempotent_skip", vector_sync_failed


def _expected_backfill_memory_ids(uid: str, legacy_rows: Sequence[dict]) -> List[str]:
    ids: List[str] = []
    for index, row in enumerate(legacy_rows):
        legacy_id = row.get("id") or f"legacy_{index}"
        content = (row.get("content") or "").strip()
        if not content:
            continue
        ids.append(legacy_backfill_memory_id(uid=uid, legacy_memory_id=legacy_id))
    return ids


def _count_destination_backfill_items(
    uid: str,
    expected_ids: Sequence[str],
    *,
    db_client,
) -> int:
    if not expected_ids:
        return 0
    expected = set(expected_ids)
    items = fetch_authoritative_product_memory_items(uid=uid, db_client=db_client)
    count = 0
    for item in items:
        if item.memory_id not in expected:
            continue
        if item.tier != MemoryLayer.long_term:
            continue
        if item.status != MemoryItemStatus.active:
            continue
        if item.processing_state != ProcessingState.processed:
            continue
        count += 1
    return count


def reconcile_backfill_counts(
    uid: str,
    legacy_rows: Sequence[dict],
    *,
    db_client=None,
) -> tuple[int, int, bool, Optional[str]]:
    """Return (source_count, destination_count, verified, discrepancy)."""
    client = db_client if db_client is not None else default_db_client
    eligible_rows = [row for row in legacy_rows if (row.get("content") or "").strip()]
    source_count = len(eligible_rows)
    expected_ids = _expected_backfill_memory_ids(uid, eligible_rows)
    destination_count = _count_destination_backfill_items(uid, expected_ids, db_client=client)
    verified = source_count == destination_count
    discrepancy = None
    if not verified:
        discrepancy = f"source={source_count} destination={destination_count}"
    return source_count, destination_count, verified, discrepancy


def backfill_user(
    uid: str,
    *,
    dry_run: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    resume: bool = True,
    db_client=None,
    get_non_filtered_memories_fn: Callable[..., List[dict]] = get_non_filtered_memories,
    run_id: Optional[str] = None,
) -> BackfillReport:
    """Copy active legacy memories into canonical long_term items.

    **Does not modify or delete legacy data** — read-only on ``database.memories``.
    """
    client = db_client if db_client is not None else default_db_client
    effective_run_id = run_id or f"legacy_backfill_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    legacy_rows = _fetch_active_legacy_memories(uid, get_non_filtered_memories_fn=get_non_filtered_memories_fn)
    fingerprint = legacy_source_fingerprint(legacy_rows)
    eligible_rows = [row for row in legacy_rows if (row.get("content") or "").strip()]
    source_count = len(eligible_rows)

    if dry_run:
        control = _read_control_state(uid, db_client=client, create_if_missing=False)
        start_index = 0
        if resume and control.legacy_backfill_source_fingerprint == fingerprint:
            start_index = min(control.legacy_backfill_processed_count, source_count)
        intended_count = max(0, source_count - start_index)
        _, destination_count, verified, discrepancy = reconcile_backfill_counts(uid, eligible_rows, db_client=client)
        return BackfillReport(
            uid=uid,
            dry_run=True,
            source_count=source_count,
            intended_count=intended_count,
            written_count=0,
            skipped_already_present=0,
            destination_count=destination_count,
            verified=verified,
            discrepancy=discrepancy,
            resumed_from_index=start_index,
            completed=False,
            legacy_rows_touched=0,
        )

    control = _read_control_state(uid, db_client=client)
    start_index = 0
    if resume and control.legacy_backfill_source_fingerprint == fingerprint:
        start_index = min(control.legacy_backfill_processed_count, source_count)
    elif (
        resume and control.legacy_backfill_processed_count and control.legacy_backfill_source_fingerprint != fingerprint
    ):
        logger.warning(
            "legacy backfill source set changed for %s (fingerprint mismatch); restarting from 0",
            uid,
        )
        start_index = 0

    intended_count = max(0, source_count - start_index)
    written_count = 0
    skipped_already_present = 0
    vector_sync_failures = 0
    errors: List[str] = []

    processed_index = start_index
    while processed_index < source_count:
        legacy_row = eligible_rows[processed_index]
        try:
            control, written, skip_reason, row_vector_sync_failed = _apply_one_legacy_row(
                uid=uid,
                legacy_row=legacy_row,
                index=processed_index,
                control=control,
                run_id=effective_run_id,
                db_client=client,
            )
            if written:
                written_count += 1
            elif skip_reason in {"already_present", "idempotent_skip"}:
                skipped_already_present += 1
            if row_vector_sync_failed:
                vector_sync_failures += 1
        except Exception as exc:
            logger.exception("legacy backfill failed for %s row %s", uid, legacy_row.get("id"))
            errors.append(f"{legacy_row.get('id')}: {exc}")
            break

        processed_index += 1
        control = control.model_copy(
            update={
                "legacy_backfill_processed_count": processed_index,
                "legacy_backfill_source_fingerprint": fingerprint,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        _persist_control_state(control, db_client=client)

        if batch_size > 0 and (processed_index - start_index) % max(1, batch_size) == 0:
            logger.debug("legacy backfill checkpoint for %s at %s/%s", uid, processed_index, source_count)

    completed = processed_index >= source_count and not errors
    if completed:
        control = control.model_copy(
            update={
                "legacy_backfill_processed_count": source_count,
                "legacy_backfill_source_fingerprint": fingerprint,
                "legacy_backfill_completed_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
        )
        _persist_control_state(control, db_client=client)

    _, destination_count, verified, discrepancy = reconcile_backfill_counts(uid, eligible_rows, db_client=client)

    return BackfillReport(
        uid=uid,
        dry_run=False,
        source_count=source_count,
        intended_count=intended_count,
        written_count=written_count,
        skipped_already_present=skipped_already_present,
        destination_count=destination_count,
        verified=verified,
        discrepancy=discrepancy,
        resumed_from_index=start_index,
        completed=completed,
        legacy_rows_touched=0,
        vector_sync_failures=vector_sync_failures,
        errors=errors,
    )
