"""Canonical vector repair outbox worker (WS-G7)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, cast

from google.cloud import firestore

from database.memory_collections import MemoryCollections
from database.memory_vector_repair_outbox_telemetry import (
    VectorRepairOutboxTelemetryConfig,
    emit_vector_repair_outbox_worker_telemetry,
)
from models.memory_evidence import SourceState
from models.product_memory import MemoryItemStatus

VECTOR_REPAIR_OUTBOX_PENDING_STATUS = "pending"
VECTOR_REPAIR_OUTBOX_IN_PROGRESS_STATUS = "in_progress"
VECTOR_REPAIR_OUTBOX_COMPLETED_STATUS = "completed"
VECTOR_REPAIR_OUTBOX_DEAD_LETTER_STATUS = "dead_letter"
VECTOR_REPAIR_PURGE_EVENT_TYPE = "vector_repair_purge"

_DELETE_REASONS = {"missing_authoritative_item"}
_TOMBSTONE_STATUSES = {"deleted", "tombstoned", "purged", MemoryItemStatus.tombstoned.value}
_TOMBSTONE_SOURCE_STATES = {SourceState.missing.value, SourceState.tombstoned.value, SourceState.purged.value}


def _typed_transactional(func: Callable[..., Any]) -> Callable[..., Any]:
    """Typed shim around firestore.transactional (SDK stub gap)."""
    return firestore.transactional(func)  # type: ignore[reportUnknownMemberType]  # firestore transactional decorator is untyped


@dataclass(frozen=True)
class VectorRepairOutboxWorkerTickConfig:
    """Server-owned config for one vector repair outbox worker tick.

    The default is intentionally disabled/fail-closed. Cloud Run/Tasks or a
    scheduler may construct this from server env/control-plane state, but this
    module does not schedule itself or create production infrastructure.
    """

    enabled: bool = False
    worker_id: str = "memory-vector-repair-outbox-worker-disabled"
    limit: int = 25
    lease_seconds: int = 300
    max_attempts: int = 3


def run_vector_repair_outbox_worker_tick(
    *,
    db_client: Any,
    uid: str,
    config: VectorRepairOutboxWorkerTickConfig,
    authoritative_item_loader: Callable[[Dict[str, Any]], Optional[Any]],
    vector_deleter: Callable[[Dict[str, Any]], Any],
    vector_repairer: Callable[[Dict[str, Any], Any], Any],
    now: Optional[datetime] = None,
    telemetry_emitter: Optional[Callable[[Dict[str, Any]], Any]] = None,
    telemetry_config: Optional[VectorRepairOutboxTelemetryConfig] = None,
    backlog: Optional[Dict[str, Any]] = None,
    duration_ms: Optional[int] = None,
) -> Dict[str, Any]:
    """Run one explicit, fake-injectable lease/process/ack worker tick.

    This is the Cloud Run/Tasks/scheduler execution contract seam for memory vector
    repair outbox work: a caller with server-owned config invokes one bounded
    tick for one uid, leases due pending records, processes them through injected
    authoritative loader and vector adapter functions, and applies ack/retry/
    dead-letter patches through the Firestore ack writer. It is disabled by
    default and does not register a production scheduler.
    """
    _validate_worker_tick_inputs(uid=uid, config=config)
    summary = _empty_worker_tick_summary(uid=uid, config=config)
    if not config.enabled:
        return _attach_vector_repair_outbox_worker_telemetry(
            summary,
            telemetry_emitter=telemetry_emitter,
            telemetry_config=telemetry_config,
            backlog=backlog,
            duration_ms=duration_ms,
        )

    try:
        leased = lease_vector_repair_purge_outbox_records(
            db_client=db_client,
            uid=uid,
            worker_id=config.worker_id,
            limit=config.limit,
            lease_seconds=config.lease_seconds,
            now=now,
        )
    except Exception as exc:
        summary["errors"].append({"stage": "lease", "error": str(exc)})
        return _attach_vector_repair_outbox_worker_telemetry(
            summary,
            telemetry_emitter=telemetry_emitter,
            telemetry_config=telemetry_config,
            backlog=backlog,
            duration_ms=duration_ms,
        )

    summary["leased_count"] = len(leased)

    def ack_record(record: Dict[str, Any], patch: Dict[str, Any]) -> None:
        try:
            ack_vector_repair_purge_outbox_record(db_client=db_client, record=record, patch=patch, now=now)
        except Exception as exc:
            summary["ack_failed_count"] += 1
            summary["errors"].append(
                {"stage": "ack", "record_id": str(record.get("record_id") or ""), "error": str(exc)}
            )
            if patch.get("status") == VECTOR_REPAIR_OUTBOX_COMPLETED_STATUS:
                raise

    processed = process_vector_repair_purge_outbox_records(
        leased,
        authoritative_item_loader=authoritative_item_loader,
        vector_deleter=vector_deleter,
        vector_repairer=vector_repairer,
        outbox_updater=ack_record,
        max_attempts=config.max_attempts,
        now=now,
    )
    summary["processed_count"] = processed["processed_count"]
    summary["skipped_count"] = processed["skipped_count"]
    summary["failed_count"] = processed["failed_count"]
    summary["actions"] = processed["actions"]
    return _attach_vector_repair_outbox_worker_telemetry(
        summary,
        telemetry_emitter=telemetry_emitter,
        telemetry_config=telemetry_config,
        backlog=backlog,
        duration_ms=duration_ms,
    )


def _attach_vector_repair_outbox_worker_telemetry(
    summary: Dict[str, Any],
    *,
    telemetry_emitter: Optional[Callable[[Dict[str, Any]], Any]],
    telemetry_config: Optional[VectorRepairOutboxTelemetryConfig],
    backlog: Optional[Dict[str, Any]],
    duration_ms: Optional[int],
) -> Dict[str, Any]:
    if telemetry_emitter is None or telemetry_config is None:
        return summary
    output = dict(summary)
    output["telemetry"] = emit_vector_repair_outbox_worker_telemetry(
        tick_summary=output,
        emitter=telemetry_emitter,
        config=telemetry_config,
        backlog=backlog,
        duration_ms=duration_ms,
    )
    return output


def _validate_worker_tick_inputs(*, uid: str, config: VectorRepairOutboxWorkerTickConfig) -> None:
    if not isinstance(uid, str) or not uid.strip():  # type: ignore[reportUnnecessaryIsInstance]  # defensive runtime guard for untyped callers
        raise ValueError("uid is required")
    if not isinstance(config, VectorRepairOutboxWorkerTickConfig):  # type: ignore[reportUnnecessaryIsInstance]  # defensive runtime guard for untyped callers
        raise ValueError("config is required")
    if not isinstance(config.enabled, bool):  # type: ignore[reportUnnecessaryIsInstance]  # defensive runtime guard for untyped callers
        raise ValueError("config.enabled must be boolean")
    if not isinstance(config.worker_id, str) or not config.worker_id.strip():  # type: ignore[reportUnnecessaryIsInstance]  # defensive runtime guard for untyped callers
        raise ValueError("config.worker_id is required")
    if config.limit < 1:
        raise ValueError("config.limit must be positive")
    if config.lease_seconds < 1:
        raise ValueError("config.lease_seconds must be positive")
    if config.max_attempts < 1:
        raise ValueError("config.max_attempts must be positive")


def _empty_worker_tick_summary(*, uid: str, config: VectorRepairOutboxWorkerTickConfig) -> Dict[str, Any]:
    return {
        "enabled": config.enabled,
        "worker_id": config.worker_id,
        "uid": uid,
        "leased_count": 0,
        "processed_count": 0,
        "skipped_count": 0,
        "failed_count": 0,
        "ack_failed_count": 0,
        "actions": [],
        "errors": [],
    }


def lease_vector_repair_purge_outbox_records(
    *,
    db_client: Any,
    uid: str,
    worker_id: str,
    limit: int = 25,
    lease_seconds: int = 300,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Select and claim pending memory vector repair/purge outbox records.

    This is a narrow Firestore/fake-friendly seam for
    `users/{uid}/memory_outbox/*`. It intentionally does not start a production
    worker. The concurrency contract is: query pending/available records, then
    re-read each document before claiming and update only if it is still pending
    and still available. Real Firestore deployments should run this read/check/
    update in a transaction; this helper keeps the contract injectable and
    emulator-testable while production concurrency/IAM validation remains a gate.

    Returned records preserve the original pending status so they can be passed
    to `process_vector_repair_purge_outbox_records(...)`; the stored document
    is marked `in_progress` with lease metadata to prevent duplicate leases.
    """
    if not isinstance(uid, str) or not uid.strip():  # type: ignore[reportUnnecessaryIsInstance]  # defensive runtime guard for untyped callers
        raise ValueError("uid is required")
    if not isinstance(worker_id, str) or not worker_id.strip():  # type: ignore[reportUnnecessaryIsInstance]  # defensive runtime guard for untyped callers
        raise ValueError("worker_id is required")
    if limit < 1:
        raise ValueError("limit must be positive")
    if lease_seconds < 1:
        raise ValueError("lease_seconds must be positive")

    observed_now = _observed_now(now)
    now_iso = observed_now.isoformat()
    lease_expires_at = (observed_now + timedelta(seconds=lease_seconds)).isoformat()
    collection_path = MemoryCollections(uid=uid).memory_outbox
    pending_query = (
        db_client.collection(collection_path)
        .where("event_type", "==", VECTOR_REPAIR_PURGE_EVENT_TYPE)
        .where("status", "==", VECTOR_REPAIR_OUTBOX_PENDING_STATUS)
        .where("available_at", "<=", now_iso)
        .limit(limit)
    )
    expired_lease_query = (
        db_client.collection(collection_path)
        .where("event_type", "==", VECTOR_REPAIR_PURGE_EVENT_TYPE)
        .where("status", "==", VECTOR_REPAIR_OUTBOX_IN_PROGRESS_STATUS)
        .where("lease_expires_at", "<=", now_iso)
        .limit(limit)
    )

    leased: List[Dict[str, Any]] = []
    seen_paths: set[str] = set()
    for query in (pending_query, expired_lease_query):
        for snapshot in query.stream():
            if len(leased) >= limit:
                return leased
            path = getattr(getattr(snapshot, "reference", None), "path", f"{collection_path}/{snapshot.id}")
            if path in seen_paths:
                continue
            seen_paths.add(path)
            claimed = _claim_vector_repair_purge_outbox_snapshot(
                db_client=db_client,
                path=path,
                worker_id=worker_id,
                now_iso=now_iso,
                lease_expires_at=lease_expires_at,
            )
            if claimed is not None:
                leased.append(claimed)
    return leased


def ack_vector_repair_purge_outbox_record(
    *,
    db_client: Any,
    record: Dict[str, Any],
    patch: Dict[str, Any],
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Apply a worker ack/retry/dead-letter patch to one outbox document.

    Supports the patch shape emitted by
    `process_vector_repair_purge_outbox_records(...)`: `in_progress`,
    `completed`, `pending` retry, or `dead_letter`, with fields such as
    `attempt_count`, `last_error`, and `action`. Write failures deliberately
    propagate so callers can account for ambiguous acks instead of dropping them.
    """
    if not isinstance(patch, dict) or not patch:  # type: ignore[reportUnnecessaryIsInstance]  # defensive runtime guard for untyped callers
        raise ValueError("patch is required")
    path = record.get("outbox_path")
    if not isinstance(path, str) or not path.strip():
        uid = _required_str(record, "uid")
        record_id = _required_str(record, "record_id")
        path = f"{MemoryCollections(uid=uid).memory_outbox}/{record_id}"
    ack_patch = dict(patch)
    ack_patch["updated_at"] = _iso_now(now)
    db_client.document(path).update(ack_patch)
    return ack_patch


def _claim_vector_repair_purge_outbox_snapshot(
    *,
    db_client: Any,
    path: str,
    worker_id: str,
    now_iso: str,
    lease_expires_at: str,
) -> Optional[Dict[str, Any]]:
    transaction_factory = getattr(db_client, "transaction", None)
    if callable(transaction_factory):
        transaction = transaction_factory()
        if transaction.__class__.__module__.startswith("google.cloud.firestore"):
            return _claim_vector_repair_purge_outbox_snapshot_in_firestore_transaction(
                transaction,
                db_client=db_client,
                path=path,
                worker_id=worker_id,
                now_iso=now_iso,
                lease_expires_at=lease_expires_at,
            )
        return _claim_vector_repair_purge_outbox_snapshot_in_transaction(
            transaction=transaction,
            db_client=db_client,
            path=path,
            worker_id=worker_id,
            now_iso=now_iso,
            lease_expires_at=lease_expires_at,
        )

    return _claim_vector_repair_purge_outbox_snapshot_without_transaction(
        db_client=db_client,
        path=path,
        worker_id=worker_id,
        now_iso=now_iso,
        lease_expires_at=lease_expires_at,
    )


@_typed_transactional
def _claim_vector_repair_purge_outbox_snapshot_in_firestore_transaction(
    transaction: Any,
    *,
    db_client: Any,
    path: str,
    worker_id: str,
    now_iso: str,
    lease_expires_at: str,
) -> Optional[Dict[str, Any]]:
    return _claim_vector_repair_purge_outbox_snapshot_in_transaction(
        transaction=transaction,
        db_client=db_client,
        path=path,
        worker_id=worker_id,
        now_iso=now_iso,
        lease_expires_at=lease_expires_at,
    )


def _claim_vector_repair_purge_outbox_snapshot_in_transaction(
    *,
    transaction: Any,
    db_client: Any,
    path: str,
    worker_id: str,
    now_iso: str,
    lease_expires_at: str,
) -> Optional[Dict[str, Any]]:
    doc_ref = db_client.document(path)
    snapshot = doc_ref.get(transaction=transaction)
    if not getattr(snapshot, "exists", False):
        return None
    record: Dict[str, Any] = cast(Dict[str, Any], snapshot.to_dict() or {})
    if not _is_claimable_vector_repair_purge_outbox_record(record=record, now_iso=now_iso):
        return None
    record["outbox_path"] = path
    record["status"] = VECTOR_REPAIR_OUTBOX_PENDING_STATUS
    transaction.update(doc_ref, _lease_patch(worker_id=worker_id, now_iso=now_iso, lease_expires_at=lease_expires_at))
    return record


def _claim_vector_repair_purge_outbox_snapshot_without_transaction(
    *,
    db_client: Any,
    path: str,
    worker_id: str,
    now_iso: str,
    lease_expires_at: str,
) -> Optional[Dict[str, Any]]:
    doc_ref = db_client.document(path)
    snapshot = doc_ref.get()
    if not getattr(snapshot, "exists", False):
        return None
    record: Dict[str, Any] = cast(Dict[str, Any], snapshot.to_dict() or {})
    if not _is_claimable_vector_repair_purge_outbox_record(record=record, now_iso=now_iso):
        return None
    record["outbox_path"] = path
    record["status"] = VECTOR_REPAIR_OUTBOX_PENDING_STATUS
    doc_ref.update(_lease_patch(worker_id=worker_id, now_iso=now_iso, lease_expires_at=lease_expires_at))
    return record


def _is_claimable_vector_repair_purge_outbox_record(*, record: Dict[str, Any], now_iso: str) -> bool:
    if record.get("event_type") != VECTOR_REPAIR_PURGE_EVENT_TYPE:
        return False
    status = record.get("status")
    if status == VECTOR_REPAIR_OUTBOX_PENDING_STATUS:
        available_at = record.get("available_at")
        return isinstance(available_at, str) and available_at <= now_iso
    if status == VECTOR_REPAIR_OUTBOX_IN_PROGRESS_STATUS:
        lease_expires_at = record.get("lease_expires_at")
        return isinstance(lease_expires_at, str) and lease_expires_at <= now_iso
    return False


def _lease_patch(*, worker_id: str, now_iso: str, lease_expires_at: str) -> Dict[str, Any]:
    return {
        "status": VECTOR_REPAIR_OUTBOX_IN_PROGRESS_STATUS,
        "lease_owner": worker_id,
        "leased_at": now_iso,
        "locked_at": now_iso,
        "lease_expires_at": lease_expires_at,
        "updated_at": now_iso,
    }


def process_vector_repair_purge_outbox_records(
    records: Iterable[Dict[str, Any]],
    *,
    authoritative_item_loader: Callable[[Dict[str, Any]], Optional[Any]],
    vector_deleter: Callable[[Dict[str, Any]], Any],
    vector_repairer: Callable[[Dict[str, Any], Any], Any],
    outbox_updater: Callable[[Dict[str, Any], Dict[str, Any]], Any],
    max_attempts: int = 3,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Process prepared memory vector repair/purge outbox records with fake-injected side effects.

    This is the first narrow worker seam only. It does not start a background
    worker and it does not import or call Pinecone directly. Callers inject the
    authoritative item loader, vector delete/repair functions, and outbox patch
    writer so unit tests can prove idempotency, tombstone precedence, and retry
    semantics without real infrastructure.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    observed_now = _iso_now(now)
    seen_idempotency_keys: set[str] = set()
    actions: List[Dict[str, str]] = []
    processed_count = 0
    skipped_count = 0
    failed_count = 0

    for record in records:
        idempotency_key = _required_str(record, "idempotency_key")
        record_id = _required_str(record, "record_id")
        status = record.get("status")
        if status != VECTOR_REPAIR_OUTBOX_PENDING_STATUS:
            skipped_count += 1
            continue
        if record.get("event_type") != VECTOR_REPAIR_PURGE_EVENT_TYPE:
            skipped_count += 1
            continue
        if idempotency_key in seen_idempotency_keys:
            skipped_count += 1
            continue
        seen_idempotency_keys.add(idempotency_key)

        action = "delete" if _should_delete_without_authoritative_load(record) else None
        item = None
        try:
            outbox_updater(
                record,
                {
                    "status": VECTOR_REPAIR_OUTBOX_IN_PROGRESS_STATUS,
                    "locked_at": observed_now,
                    "last_error": None,
                },
            )
            if action is None:
                item = authoritative_item_loader(record)
                action = _decide_delete_or_repair(record=record, authoritative_item=item)
            if action == "delete":
                vector_deleter(record)
            elif action == "repair":
                vector_repairer(record, item)
            else:
                raise ValueError(f"unsupported vector repair action: {action}")
            outbox_updater(
                record,
                {
                    "status": VECTOR_REPAIR_OUTBOX_COMPLETED_STATUS,
                    "action": action,
                    "completed_at": observed_now,
                    "last_error": None,
                },
            )
            processed_count += 1
            actions.append({"record_id": record_id, "idempotency_key": idempotency_key, "action": action})
        except Exception as exc:
            failed_count += 1
            next_attempt_count = int(record.get("attempt_count") or 0) + 1
            next_status = (
                VECTOR_REPAIR_OUTBOX_DEAD_LETTER_STATUS
                if next_attempt_count >= max_attempts
                else VECTOR_REPAIR_OUTBOX_PENDING_STATUS
            )
            outbox_updater(
                record,
                {
                    "status": next_status,
                    "attempt_count": next_attempt_count,
                    "last_error": str(exc),
                    "failed_at": observed_now,
                    "action": action or "unknown",
                },
            )

    return {
        "processed_count": processed_count,
        "skipped_count": skipped_count,
        "failed_count": failed_count,
        "actions": actions,
    }


def _decide_delete_or_repair(*, record: Dict[str, Any], authoritative_item: Optional[Any]) -> str:
    if authoritative_item is None:
        return "delete"
    if _has_tombstone_or_delete_precedence(authoritative_item):
        return "delete"
    if _required_str(record, "reason") in _DELETE_REASONS:
        return "delete"
    return "repair"


def _should_delete_without_authoritative_load(record: Dict[str, Any]) -> bool:
    return _required_str(record, "reason") in _DELETE_REASONS


def _has_tombstone_or_delete_precedence(item: Any) -> bool:
    status = _get_item_value(item, "status")
    source_state = _get_item_value(item, "source_state")
    deleted = _get_item_value(item, "deleted")
    tombstoned = _get_item_value(item, "tombstoned")
    if deleted is True or tombstoned is True:
        return True
    return _enum_or_raw(status) in _TOMBSTONE_STATUSES or _enum_or_raw(source_state) in _TOMBSTONE_SOURCE_STATES


def _get_item_value(item: Any, key: str) -> Any:
    if isinstance(item, dict):
        typed_item: Dict[str, Any] = cast(Dict[str, Any], item)
        return typed_item.get(key)
    return getattr(item, key, None)


def _enum_or_raw(value: Any) -> Any:
    return getattr(value, "value", value)


def _required_str(value: Dict[str, Any], key: str) -> str:
    raw = value.get(key)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{key} is required")
    return raw


def _observed_now(value: Optional[datetime]) -> datetime:
    observed = value or datetime.now(timezone.utc)
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return observed


def _iso_now(value: Optional[datetime]) -> str:
    return _observed_now(value).isoformat()


__all__ = [
    "VectorRepairOutboxWorkerTickConfig",
    "VECTOR_REPAIR_OUTBOX_COMPLETED_STATUS",
    "VECTOR_REPAIR_OUTBOX_DEAD_LETTER_STATUS",
    "VECTOR_REPAIR_OUTBOX_IN_PROGRESS_STATUS",
    "VECTOR_REPAIR_OUTBOX_PENDING_STATUS",
    "VECTOR_REPAIR_PURGE_EVENT_TYPE",
    "ack_vector_repair_purge_outbox_record",
    "lease_vector_repair_purge_outbox_records",
    "process_vector_repair_purge_outbox_records",
    "run_vector_repair_outbox_worker_tick",
]
