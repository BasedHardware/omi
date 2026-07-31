"""Canonical Pinecone adapter for vector repair/purge worker (WS-G7)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, Optional, cast

from database.memory_vector_metadata import (
    build_canonical_memory_vector_delete_filter,
    build_memory_vector_metadata,
    canonical_memory_provider_id,
)
from models.memory_evidence import SourceState
from models.product_memory import MemoryItemStatus, MemoryItem

# Existing production memory vectors use Pinecone namespace ns2 in database/vector_db.py.
# Keep this seam explicit and injectable so unit tests never import/call the real Pinecone client.
VECTOR_REPAIR_PINECONE_NAMESPACE = "ns2"


class VectorRepairNotReady(RuntimeError):
    """Raised when a repair record lacks authoritative source data needed to rebuild a memory vector."""


def make_pinecone_vector_deleter(
    *,
    delete_vectors: Callable[..., Any],
    namespace: str = VECTOR_REPAIR_PINECONE_NAMESPACE,
) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    """Return a worker-compatible deleter for memory vector repair/purge records.

    Cleanup is fenced by canonical UID + memory metadata, so a legacy bare-ID
    row cannot make one user's repair delete another user's scoped projection.
    """

    _validate_namespace(namespace)

    def delete_record(record: Dict[str, Any]) -> Dict[str, Any]:
        vector_id = _required_str(record, "vector_id")
        uid = _required_str(record, "uid")
        memory_id = _required_str(record, "memory_id")
        delete_filter = build_canonical_memory_vector_delete_filter(uid, memory_id)
        pinecone_result = delete_vectors(filter=delete_filter, namespace=namespace)
        return {
            "action": "delete",
            "filter": delete_filter,
            "namespace": namespace,
            "vector_ids": [vector_id],
            "pinecone_result": pinecone_result,
        }

    return delete_record


def make_pinecone_vector_repairer(
    *,
    embed_text: Callable[[str], Iterable[float]],
    delete_vectors: Callable[..., Any],
    upsert_vectors: Callable[..., Any],
    namespace: str = VECTOR_REPAIR_PINECONE_NAMESPACE,
    now: Optional[datetime] = None,
) -> Callable[[Dict[str, Any], Any], Dict[str, Any]]:
    """Return a worker-compatible repairer that upserts an authoritative memory vector.

    This seam rebuilds only from live authoritative memory item data plus the
    outbox record's required projection fence. It deliberately does not fake
    embeddings: callers must inject `embed_text`. If content or freshness/source
    fields are missing, it raises `VectorRepairNotReady` before any embed or
    upsert side effect so the existing worker retry/dead-letter path records the
    not-ready state deterministically.
    """

    _validate_namespace(namespace)
    vector_updated_at = _observed_now(now)

    def repair_record(record: Dict[str, Any], authoritative_item: Any) -> Dict[str, Any]:
        item = _coerce_live_authoritative_item(authoritative_item)
        projection_commit_id = _required_str(record, "required_projection_commit_id")
        content = _required_item_str(item, "content")
        _required_item_str(item, "source_commit_id")
        _required_item_str(item, "content_hash")
        if item.source_state != SourceState.active or item.status != MemoryItemStatus.active:
            raise VectorRepairNotReady("authoritative item is not live/active")

        vector_id = canonical_memory_provider_id(item.uid, item.memory_id)
        metadata = build_memory_vector_metadata(
            item,
            projection_commit_id=projection_commit_id,
            vector_updated_at=vector_updated_at,
        )
        values = list(embed_text(content))
        if not values:
            raise VectorRepairNotReady("embedding result is empty")
        payload = {"id": vector_id, "values": values, "metadata": metadata}
        # Remove every prior provider identity for this canonical memory before
        # replacing it. Failure aborts the repair so the outbox retries.
        delete_filter = build_canonical_memory_vector_delete_filter(item.uid, item.memory_id)
        delete_result = delete_vectors(filter=delete_filter, namespace=namespace)
        pinecone_result = upsert_vectors(vectors=[payload], namespace=namespace)
        return {
            "action": "repair",
            "delete_filter": delete_filter,
            "delete_result": delete_result,
            "namespace": namespace,
            "vector_id": vector_id,
            "pinecone_result": pinecone_result,
        }

    return repair_record


def _coerce_live_authoritative_item(item: Any) -> MemoryItem:
    if isinstance(item, MemoryItem):
        return item
    if isinstance(item, dict):
        try:
            return MemoryItem(**cast(Dict[str, Any], item))
        except Exception as exc:
            raise VectorRepairNotReady(f"authoritative item is not repairable: {exc}") from exc
    raise VectorRepairNotReady("authoritative item is missing or has unsupported type")


def _required_item_str(item: MemoryItem, key: str) -> str:
    value = getattr(item, key, None)
    if not isinstance(value, str) or not value.strip():
        raise VectorRepairNotReady(f"authoritative item {key} is required")
    return value


def _required_str(value: Dict[str, Any], key: str) -> str:
    raw = value.get(key)
    if not isinstance(raw, str) or not raw.strip():
        raise VectorRepairNotReady(f"record {key} is required")
    return raw


def _validate_namespace(namespace: str) -> None:
    if not isinstance(namespace, str) or not namespace.strip():  # type: ignore[reportUnnecessaryIsInstance]  # defensive runtime guard for untyped callers
        raise ValueError("namespace is required")


def _observed_now(value: Optional[datetime]) -> datetime:
    observed = value or datetime.now(timezone.utc)
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return observed


__all__ = [
    "VectorRepairNotReady",
    "VECTOR_REPAIR_PINECONE_NAMESPACE",
    "make_pinecone_vector_deleter",
    "make_pinecone_vector_repairer",
]
