from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional

from database.v17_collections import V17Collections
from models.memory_evidence import SourceState
from models.v17_product_memory import MemoryItemStatus

V17_VECTOR_REPAIR_OUTBOX_PENDING_STATUS = "pending"
V17_VECTOR_REPAIR_OUTBOX_IN_PROGRESS_STATUS = "in_progress"
V17_VECTOR_REPAIR_OUTBOX_COMPLETED_STATUS = "completed"
V17_VECTOR_REPAIR_OUTBOX_DEAD_LETTER_STATUS = "dead_letter"
V17_VECTOR_REPAIR_PURGE_EVENT_TYPE = "vector_repair_purge"

_TERMINAL_OR_LEASED_STATUSES = {
    V17_VECTOR_REPAIR_OUTBOX_IN_PROGRESS_STATUS,
    V17_VECTOR_REPAIR_OUTBOX_COMPLETED_STATUS,
    V17_VECTOR_REPAIR_OUTBOX_DEAD_LETTER_STATUS,
}
_DELETE_REASONS = {"missing_authoritative_item"}
_TOMBSTONE_STATUSES = {"deleted", "tombstoned", "purged", MemoryItemStatus.tombstoned.value}
_TOMBSTONE_SOURCE_STATES = {SourceState.missing.value, SourceState.tombstoned.value, SourceState.purged.value}


def lease_v17_vector_repair_purge_outbox_records(
    *,
    db_client,
    uid: str,
    worker_id: str,
    limit: int = 25,
    lease_seconds: int = 300,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Select and claim pending V17 vector repair/purge outbox records.

    This is a narrow Firestore/fake-friendly seam for
    `users/{uid}/memory_outbox/*`. It intentionally does not start a production
    worker. The concurrency contract is: query pending/available records, then
    re-read each document before claiming and update only if it is still pending
    and still available. Real Firestore deployments should run this read/check/
    update in a transaction; this helper keeps the contract injectable and
    emulator-testable while production concurrency/IAM validation remains a gate.

    Returned records preserve the original pending status so they can be passed
    to `process_v17_vector_repair_purge_outbox_records(...)`; the stored document
    is marked `in_progress` with lease metadata to prevent duplicate leases.
    """
    if not isinstance(uid, str) or not uid.strip():
        raise ValueError("uid is required")
    if not isinstance(worker_id, str) or not worker_id.strip():
        raise ValueError("worker_id is required")
    if limit < 1:
        raise ValueError("limit must be positive")
    if lease_seconds < 1:
        raise ValueError("lease_seconds must be positive")

    observed_now = _observed_now(now)
    now_iso = observed_now.isoformat()
    lease_expires_at = (observed_now + timedelta(seconds=lease_seconds)).isoformat()
    collection_path = V17Collections(uid=uid).memory_outbox
    query = (
        db_client.collection(collection_path)
        .where("event_type", "==", V17_VECTOR_REPAIR_PURGE_EVENT_TYPE)
        .where("status", "==", V17_VECTOR_REPAIR_OUTBOX_PENDING_STATUS)
        .where("available_at", "<=", now_iso)
        .limit(limit)
    )

    leased: List[Dict[str, Any]] = []
    for snapshot in query.stream():
        path = getattr(getattr(snapshot, "reference", None), "path", f"{collection_path}/{snapshot.id}")
        claimed = _claim_v17_vector_repair_purge_outbox_snapshot(
            db_client=db_client,
            path=path,
            worker_id=worker_id,
            now_iso=now_iso,
            lease_expires_at=lease_expires_at,
        )
        if claimed is not None:
            leased.append(claimed)
    return leased


def ack_v17_vector_repair_purge_outbox_record(
    *,
    db_client,
    record: Dict[str, Any],
    patch: Dict[str, Any],
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Apply a worker ack/retry/dead-letter patch to one outbox document.

    Supports the patch shape emitted by
    `process_v17_vector_repair_purge_outbox_records(...)`: `in_progress`,
    `completed`, `pending` retry, or `dead_letter`, with fields such as
    `attempt_count`, `last_error`, and `action`. Write failures deliberately
    propagate so callers can account for ambiguous acks instead of dropping them.
    """
    if not isinstance(patch, dict) or not patch:
        raise ValueError("patch is required")
    path = record.get("outbox_path")
    if not isinstance(path, str) or not path.strip():
        uid = _required_str(record, "uid")
        record_id = _required_str(record, "record_id")
        path = f"{V17Collections(uid=uid).memory_outbox}/{record_id}"
    ack_patch = dict(patch)
    ack_patch["updated_at"] = _iso_now(now)
    db_client.document(path).update(ack_patch)
    return ack_patch


def _claim_v17_vector_repair_purge_outbox_snapshot(
    *,
    db_client,
    path: str,
    worker_id: str,
    now_iso: str,
    lease_expires_at: str,
) -> Optional[Dict[str, Any]]:
    doc_ref = db_client.document(path)
    snapshot = doc_ref.get()
    if not getattr(snapshot, "exists", False):
        return None
    record = snapshot.to_dict() or {}
    if record.get("event_type") != V17_VECTOR_REPAIR_PURGE_EVENT_TYPE:
        return None
    if record.get("status") != V17_VECTOR_REPAIR_OUTBOX_PENDING_STATUS:
        return None
    available_at = record.get("available_at")
    if not isinstance(available_at, str) or available_at > now_iso:
        return None
    record["outbox_path"] = path
    doc_ref.update(
        {
            "status": V17_VECTOR_REPAIR_OUTBOX_IN_PROGRESS_STATUS,
            "lease_owner": worker_id,
            "leased_at": now_iso,
            "locked_at": now_iso,
            "lease_expires_at": lease_expires_at,
            "updated_at": now_iso,
        }
    )
    return record


def process_v17_vector_repair_purge_outbox_records(
    records: Iterable[Dict[str, Any]],
    *,
    authoritative_item_loader: Callable[[Dict[str, Any]], Optional[Any]],
    vector_deleter: Callable[[Dict[str, Any]], Any],
    vector_repairer: Callable[[Dict[str, Any], Any], Any],
    outbox_updater: Callable[[Dict[str, Any], Dict[str, Any]], Any],
    max_attempts: int = 3,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Process prepared V17 vector repair/purge outbox records with fake-injected side effects.

    This is the first narrow worker seam only. It does not start a background
    worker and it does not import or call Pinecone directly. Callers inject the
    authoritative item loader, vector delete/repair functions, and outbox patch
    writer so unit tests can prove idempotency, tombstone precedence, and retry
    semantics without real infrastructure.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    observed_now = _iso_now(now)
    seen_idempotency_keys = set()
    actions: List[Dict[str, str]] = []
    processed_count = 0
    skipped_count = 0
    failed_count = 0

    for record in records:
        idempotency_key = _required_str(record, "idempotency_key")
        record_id = _required_str(record, "record_id")
        status = record.get("status")
        if status != V17_VECTOR_REPAIR_OUTBOX_PENDING_STATUS:
            skipped_count += 1
            continue
        if record.get("event_type") != V17_VECTOR_REPAIR_PURGE_EVENT_TYPE:
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
                    "status": V17_VECTOR_REPAIR_OUTBOX_IN_PROGRESS_STATUS,
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
                    "status": V17_VECTOR_REPAIR_OUTBOX_COMPLETED_STATUS,
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
                V17_VECTOR_REPAIR_OUTBOX_DEAD_LETTER_STATUS
                if next_attempt_count >= max_attempts
                else V17_VECTOR_REPAIR_OUTBOX_PENDING_STATUS
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
        return item.get(key)
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
