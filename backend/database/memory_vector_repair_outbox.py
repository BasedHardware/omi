"""Canonical vector repair/purge outbox record builder (WS-G7)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database.memory_collections import MemoryCollections
from models.memory_contracts import deterministic_contract_id

VECTOR_REPAIR_PURGE_OUTBOX_EVENT_TYPE = "vector_repair_purge"
VECTOR_REPAIR_PURGE_OUTBOX_SCHEMA_VERSION = 1


def build_vector_repair_purge_outbox_records(
    *,
    uid: str,
    candidates: List[Dict[str, Any]],
    queued_at: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Transform stale vector repair/purge candidates into deterministic outbox records.

    This is a durable, fake-injectable seam only: records are suitable for
    `users/{uid}/memory_outbox/{record_id}` persistence or an injected test
    writer, but this module does not call Pinecone or perform deletion/repair.
    The stable record id is the idempotency contract for retrying the same stale
    vector observation.
    """
    if not uid.strip():
        raise ValueError("uid is required")
    if not candidates:
        return []
    queued = queued_at or datetime.now(timezone.utc)
    if queued.tzinfo is None or queued.utcoffset() is None:
        raise ValueError("queued_at must be timezone-aware")

    records: List[Dict[str, Any]] = []
    for candidate in candidates:
        vector_id = _required_str(candidate, "vector_id")
        memory_id = _required_str(candidate, "memory_id")
        reason = _required_str(candidate, "reason")
        required_projection_commit_id = _required_str(candidate, "required_projection_commit_id")
        required_account_generation = _required_int(candidate, "required_account_generation")
        record_id = _record_id(
            uid=uid,
            vector_id=vector_id,
            memory_id=memory_id,
            reason=reason,
            required_projection_commit_id=required_projection_commit_id,
            required_account_generation=required_account_generation,
        )
        outbox_path = f"{MemoryCollections(uid=uid).memory_outbox}/{record_id}"
        records.append(
            {
                "schema_version": VECTOR_REPAIR_PURGE_OUTBOX_SCHEMA_VERSION,
                "record_id": record_id,
                "idempotency_key": record_id,
                "uid": uid,
                "event_type": VECTOR_REPAIR_PURGE_OUTBOX_EVENT_TYPE,
                "status": "pending",
                "vector_id": vector_id,
                "memory_id": memory_id,
                "reason": reason,
                "decision": candidate.get("decision"),
                "required_projection_commit_id": required_projection_commit_id,
                "observed_projection_commit_id": candidate.get("observed_projection_commit_id"),
                "required_account_generation": required_account_generation,
                "observed_account_generation": candidate.get("observed_account_generation"),
                "authoritative_account_generation": candidate.get("authoritative_account_generation"),
                "observed_item_revision": candidate.get("observed_item_revision"),
                "authoritative_item_revision": candidate.get("authoritative_item_revision"),
                "observed_source_commit_id": candidate.get("observed_source_commit_id"),
                "authoritative_source_commit_id": candidate.get("authoritative_source_commit_id"),
                "observed_content_hash": candidate.get("observed_content_hash"),
                "authoritative_content_hash": candidate.get("authoritative_content_hash"),
                "outbox_path": outbox_path,
                "available_at": queued.isoformat(),
                "queued_at": queued.isoformat(),
                "attempt_count": 0,
                "last_error": None,
                "payload": dict(candidate),
            }
        )
    return records


def write_vector_repair_purge_outbox_records(*, db_client: Any, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Persist prepared vector repair/purge records with stable ids.

    The function is deliberately small and fake-friendly. Callers may inject a
    different writer in unit tests or in a future Cloud Tasks/worker seam. A
    later production worker must still implement tombstone precedence, retries,
    error telemetry, and real Pinecone delete/repair; this helper only persists
    deterministic pending records.
    """
    if not records:
        return []
    for record in records:
        path = _required_str(record, "outbox_path")
        db_client.document(path).set(dict(record))
    return records


def _record_id(
    *,
    uid: str,
    vector_id: str,
    memory_id: str,
    reason: str,
    required_projection_commit_id: str,
    required_account_generation: int,
) -> str:
    digest = deterministic_contract_id(
        "memory-vector-repair-purge-outbox",
        {
            "uid": uid,
            "vector_id": vector_id,
            "memory_id": memory_id,
            "reason": reason,
            "required_projection_commit_id": required_projection_commit_id,
            "required_account_generation": required_account_generation,
        },
    )
    return f"memvrp_{digest[:32]}"


def _required_str(value: Dict[str, Any], key: str) -> str:
    raw = value.get(key)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{key} is required")
    return raw


def _required_int(value: Dict[str, Any], key: str) -> int:
    raw = value.get(key)
    if not isinstance(raw, int):
        raise ValueError(f"{key} is required")
    return raw


__all__ = [
    "VECTOR_REPAIR_PURGE_OUTBOX_EVENT_TYPE",
    "VECTOR_REPAIR_PURGE_OUTBOX_SCHEMA_VERSION",
    "build_vector_repair_purge_outbox_records",
    "write_vector_repair_purge_outbox_records",
]
