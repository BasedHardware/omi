"""Canonical product memory read service module (WS-G8a).

Neutral ``product_memory_read_service`` is the source of truth. Legacy ``product_memory_read_service`` remains an importable alias.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, cast

from database import document_store
from database.firestore_index_registry import (
    CONVERSATION_SOURCE_MEMORY_QUERY,
    SUPERSEDED_MEMORY_BY_CANONICAL_TARGET_QUERY,
    SUPERSEDED_MEMORY_BY_LEGACY_TARGET_QUERY,
)
from database.memory_collections import MemoryCollections
from database.store import get_document_store
from models.product_memory import MemoryAccessPolicy, MemoryItem, MemoryItemStatus
from utils.memory.memory_read_api import query_archive_product_memory_items, query_default_product_memory_items

DEFAULT_PRODUCT_MEMORY_READ_LIMIT = 100
MAX_PRODUCT_MEMORY_READ_LIMIT = 500
SOURCE_REPLACEMENT_QUERY_PAGE_LIMIT = 100
FIRESTORE_IN_QUERY_MAX_VALUES = 30


def _store() -> Any:
    return get_document_store()


def fetch_default_product_memory_search(
    uid: str,
    query: str,
    *,
    policy: MemoryAccessPolicy,
    now: Optional[datetime] = None,
    limit: int = DEFAULT_PRODUCT_MEMORY_READ_LIMIT,
    offset: int = 0,
) -> Dict[str, Any]:
    """Fetch authoritative memory `memory_items` and return default-visible product search results.

    This is the concrete T19/T21 read-service seam for product callers: it reads
    `users/{uid}/memory_items`, coerces documents to `MemoryItem`, delegates
    default visibility to `query_default_product_memory_items(...)`, then paginates
    the filtered/matched results. Archive remains unavailable here by design; use
    the explicit archive query seam for archive-capable product surfaces.
    """

    bounded_limit = _validate_limit(limit)
    bounded_offset = _validate_offset(offset)
    items = fetch_authoritative_product_memory_items(uid=uid)
    results = query_default_product_memory_items(query, items, policy=policy, now=now)
    total_count = len(results)
    paged_items = results[bounded_offset : bounded_offset + bounded_limit]
    return {
        'uid': uid,
        'query': query,
        'items': paged_items,
        'total_count': total_count,
        'returned_count': len(paged_items),
        'limit': bounded_limit,
        'offset': bounded_offset,
        'archive_default_visible': False,
    }


def fetch_archive_product_memory_search(
    uid: str,
    query: str,
    *,
    policy: MemoryAccessPolicy,
    now: Optional[datetime] = None,
    limit: int = DEFAULT_PRODUCT_MEMORY_READ_LIMIT,
    offset: int = 0,
) -> Dict[str, Any]:
    """Fetch authoritative memory `memory_items` and return explicit archive search results.

    Archive search is intentionally separate from default product reads. Callers
    must pass a policy with `archive_capability=True`; without it, the underlying
    archive query returns no items and this response advertises the denied gate.
    """

    bounded_limit = _validate_limit(limit)
    bounded_offset = _validate_offset(offset)
    items = fetch_authoritative_product_memory_items(uid=uid)
    results = query_archive_product_memory_items(query, items, policy=policy, now=now)
    total_count = len(results)
    paged_items = results[bounded_offset : bounded_offset + bounded_limit]
    return {
        'uid': uid,
        'query': query,
        'items': paged_items,
        'total_count': total_count,
        'returned_count': len(paged_items),
        'limit': bounded_limit,
        'offset': bounded_offset,
        'archive_default_visible': False,
        'archive_capability_required': True,
        'archive_capability_granted': policy.archive_capability,
    }


def fetch_authoritative_product_memory_items(uid: str) -> List[MemoryItem]:
    """Load and coerce all authoritative memory product memory item docs for one user."""

    collection_path = MemoryCollections(uid=uid).memory_items
    items: List[MemoryItem] = []
    for snapshot in document_store.stream_collection(collection_path):
        raw_payload: object = snapshot.to_dict()
        payload = cast(Dict[str, Any], raw_payload) if isinstance(raw_payload, dict) else {}
        item = MemoryItem.model_validate(payload)
        if item.uid != uid:
            raise ValueError(f'memory item uid mismatch: expected {uid}, got {item.uid}')
        items.append(item)
    return sorted(items, key=_memory_item_sort_key)


def fetch_authoritative_product_memory_items_for_source(
    uid: str,
    source_id: str,
    *,
    page_size: int = SOURCE_REPLACEMENT_QUERY_PAGE_LIMIT,
) -> List[MemoryItem]:
    """Load one complete source cohort through the indexed, cursor-paged boundary."""

    if not source_id or not source_id.strip():
        raise ValueError('source_id must not be blank')
    collection_path = MemoryCollections(uid=uid).memory_items
    filters = _neutral_filters(CONVERSATION_SOURCE_MEMORY_QUERY, {'source_id': source_id})
    return _fetch_authoritative_memory_query_pages(
        uid,
        collection=collection_path,
        filters=filters,
        page_size=page_size,
    )


def fetch_authoritative_superseded_memory_items_for_targets(
    uid: str,
    target_memory_ids: Iterable[str],
    *,
    page_size: int = SOURCE_REPLACEMENT_QUERY_PAGE_LIMIT,
) -> List[MemoryItem]:
    """Load superseded aliases of target rows, including the pre-canonical edge."""

    normalized_target_ids = sorted(
        {memory_id.strip() for memory_id in target_memory_ids if memory_id and memory_id.strip()}
    )
    if not normalized_target_ids:
        return []

    collection_path = MemoryCollections(uid=uid).memory_items
    items_by_id: Dict[str, MemoryItem] = {}
    for offset in range(0, len(normalized_target_ids), FIRESTORE_IN_QUERY_MAX_VALUES):
        target_chunk = normalized_target_ids[offset : offset + FIRESTORE_IN_QUERY_MAX_VALUES]
        for spec in (
            SUPERSEDED_MEMORY_BY_CANONICAL_TARGET_QUERY,
            SUPERSEDED_MEMORY_BY_LEGACY_TARGET_QUERY,
        ):
            filters = _neutral_filters(
                spec,
                {
                    'status': MemoryItemStatus.superseded.value,
                    'target_memory_ids': target_chunk,
                },
            )
            for item in _fetch_authoritative_memory_query_pages(
                uid,
                collection=collection_path,
                filters=filters,
                page_size=page_size,
            ):
                items_by_id[item.memory_id] = item
    return sorted(items_by_id.values(), key=lambda item: item.memory_id)


def _neutral_filters(spec: Any, values: Dict[str, Any]) -> List[tuple]:
    """Resolve a registered query spec's declared filters into neutral ``(field, op, value)`` tuples.

    Mirrors ``FirestoreQuerySpec.build``'s value resolution, but targets the storage port instead of a
    raw Firestore collection so the same indexed shape runs on Firestore or Mongo (ADR-0022/0028).
    """

    filters: List[tuple] = []
    for query_filter in spec.filters:
        try:
            value = values[query_filter.value_name]
        except KeyError as exc:
            raise ValueError(f'{spec.identifier} requires {query_filter.value_name!r}') from exc
        filters.append((query_filter.field_path, query_filter.operator, value))
    return filters


def _fetch_authoritative_memory_query_pages(
    uid: str,
    *,
    collection: str,
    filters: List[tuple],
    page_size: int,
) -> List[MemoryItem]:
    if page_size < 1 or page_size > SOURCE_REPLACEMENT_QUERY_PAGE_LIMIT:
        raise ValueError(f'page_size must be between 1 and {SOURCE_REPLACEMENT_QUERY_PAGE_LIMIT}')

    items: List[MemoryItem] = []
    offset = 0
    while True:
        # No explicit order_by: the port returns documents in document-name order (the portable
        # equivalent of Firestore's implicit ``__name__`` ordering), so offset paging is stable.
        page = _store().query(collection, filters=filters, limit=page_size, offset=offset)
        for record in page:
            raw_payload: object = record.to_dict()
            payload = cast(Dict[str, Any], raw_payload) if isinstance(raw_payload, dict) else {}
            item = MemoryItem.model_validate(payload)
            if item.uid != uid:
                raise ValueError(f'memory item uid mismatch: expected {uid}, got {item.uid}')
            items.append(item)
        if len(page) < page_size:
            break
        offset += page_size
    return items


def _memory_item_sort_key(item: MemoryItem) -> tuple[float, str]:
    return (-item.updated_at.timestamp(), item.memory_id)


def _validate_limit(limit: int) -> int:
    if limit < 1 or limit > MAX_PRODUCT_MEMORY_READ_LIMIT:
        raise ValueError(f'limit must be between 1 and {MAX_PRODUCT_MEMORY_READ_LIMIT}')
    return limit


def _validate_offset(offset: int) -> int:
    if offset < 0:
        raise ValueError('offset must be non-negative')
    return offset
