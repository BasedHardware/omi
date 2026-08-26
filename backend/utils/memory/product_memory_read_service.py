"""Canonical product memory read service module (WS-G8a).

Neutral ``product_memory_read_service`` is the source of truth. Legacy ``product_memory_read_service`` remains an importable alias.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, Iterator, List, Optional, cast

from google.cloud.firestore_v1 import FieldFilter

from database.firestore_index_registry import (
    CONVERSATION_SOURCE_MEMORY_QUERY,
    SUPERSEDED_MEMORY_BY_CANONICAL_TARGET_QUERY,
    SUPERSEDED_MEMORY_BY_LEGACY_TARGET_QUERY,
)
from database.memory_collections import MemoryCollections
from models.product_memory import MemoryAccessPolicy, MemoryItem, MemoryItemStatus
from utils.memory.memory_read_api import query_archive_product_memory_items
from utils.other.list_budget import ListReadBudget

DEFAULT_PRODUCT_MEMORY_READ_LIMIT = 100
MAX_PRODUCT_MEMORY_READ_LIMIT = 500
SOURCE_REPLACEMENT_QUERY_PAGE_LIMIT = 100
FIRESTORE_IN_QUERY_MAX_VALUES = 30


def fetch_default_product_memory_search(
    uid: str,
    query: str,
    *,
    db_client: Any,
    policy: MemoryAccessPolicy,
    now: Optional[datetime] = None,
    limit: int = DEFAULT_PRODUCT_MEMORY_READ_LIMIT,
    offset: int = 0,
) -> Dict[str, Any]:
    """Return the universal default-memory product view.

    The lazy import avoids a module cycle: ``MemoryService`` uses this module's
    authoritative canonical-item iterator internally, while this released
    product seam delegates the final mixed-origin view back to the universal
    repository.
    """
    bounded_limit = _validate_limit(limit)
    bounded_offset = _validate_offset(offset)
    from utils.memory.memory_service import MemoryService

    return MemoryService(db_client=db_client).default_product_search(
        uid,
        query,
        policy=policy,
        now=now,
        limit=bounded_limit,
        offset=bounded_offset,
    )


def fetch_archive_product_memory_search(
    uid: str,
    query: str,
    *,
    db_client: Any,
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
    items = fetch_authoritative_product_memory_items(uid=uid, db_client=db_client)
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


def iter_authoritative_product_memory_items(
    uid: str,
    *,
    db_client: Any,
    budget: Optional["ListReadBudget"] = None,
) -> Iterator[MemoryItem]:
    """Stream validated authoritative memory items for one user.

    With a ``budget`` the collection stream runs under the request's per-RPC
    timeout and each fetched row is charged (#11831).
    """
    collection_path = MemoryCollections(uid=uid).memory_items
    if budget is None:
        snapshots: Iterator[Any] = db_client.collection(collection_path).stream()
    else:
        timeout = budget.rpc_timeout()
        try:
            snapshots = db_client.collection(collection_path).stream(timeout=timeout)
        except TypeError:
            # Test fakes predating the budget seam.
            snapshots = db_client.collection(collection_path).stream()
    for snapshot in snapshots:
        if budget is not None:
            budget.charge(1)
        raw_payload: object = snapshot.to_dict()
        payload = cast(Dict[str, Any], raw_payload) if isinstance(raw_payload, dict) else {}
        item = MemoryItem.model_validate(payload)
        if item.uid != uid:
            raise ValueError(f"memory item uid mismatch: expected {uid}, got {item.uid}")
        yield item


def fetch_authoritative_product_memory_items(
    uid: str,
    *,
    db_client: Any,
    budget: Optional["ListReadBudget"] = None,
) -> List[MemoryItem]:
    """Load and coerce all authoritative memory product memory item docs for one user."""

    return sorted(
        iter_authoritative_product_memory_items(uid, db_client=db_client, budget=budget),
        key=_memory_item_sort_key,
    )


def fetch_authoritative_product_memory_items_for_source(
    uid: str,
    source_id: str,
    *,
    db_client: Any,
    page_size: int = SOURCE_REPLACEMENT_QUERY_PAGE_LIMIT,
) -> List[MemoryItem]:
    """Load one complete source cohort through the indexed, cursor-paged boundary."""

    if not source_id or not source_id.strip():
        raise ValueError('source_id must not be blank')
    query = CONVERSATION_SOURCE_MEMORY_QUERY.build(
        db_client.collection(MemoryCollections(uid=uid).memory_items),
        {'source_id': source_id},
        field_filter_factory=FieldFilter,
    ).order_by('__name__')
    return _fetch_authoritative_memory_query_pages(
        uid,
        query=query,
        page_size=page_size,
    )


def fetch_authoritative_superseded_memory_items_for_targets(
    uid: str,
    target_memory_ids: Iterable[str],
    *,
    db_client: Any,
    page_size: int = SOURCE_REPLACEMENT_QUERY_PAGE_LIMIT,
) -> List[MemoryItem]:
    """Load superseded aliases of target rows, including the pre-canonical edge."""

    normalized_target_ids = sorted(
        {memory_id.strip() for memory_id in target_memory_ids if memory_id and memory_id.strip()}
    )
    if not normalized_target_ids:
        return []

    collection = db_client.collection(MemoryCollections(uid=uid).memory_items)
    items_by_id: Dict[str, MemoryItem] = {}
    for offset in range(0, len(normalized_target_ids), FIRESTORE_IN_QUERY_MAX_VALUES):
        target_chunk = normalized_target_ids[offset : offset + FIRESTORE_IN_QUERY_MAX_VALUES]
        for spec in (
            SUPERSEDED_MEMORY_BY_CANONICAL_TARGET_QUERY,
            SUPERSEDED_MEMORY_BY_LEGACY_TARGET_QUERY,
        ):
            query = spec.build(
                collection,
                {
                    'status': MemoryItemStatus.superseded.value,
                    'target_memory_ids': target_chunk,
                },
                field_filter_factory=FieldFilter,
            ).order_by('__name__')
            for item in _fetch_authoritative_memory_query_pages(
                uid,
                query=query,
                page_size=page_size,
            ):
                items_by_id[item.memory_id] = item
    return sorted(items_by_id.values(), key=lambda item: item.memory_id)


def _fetch_authoritative_memory_query_pages(
    uid: str,
    *,
    query: Any,
    page_size: int,
) -> List[MemoryItem]:
    if page_size < 1 or page_size > SOURCE_REPLACEMENT_QUERY_PAGE_LIMIT:
        raise ValueError(f'page_size must be between 1 and {SOURCE_REPLACEMENT_QUERY_PAGE_LIMIT}')

    items: List[MemoryItem] = []
    cursor: Any = None
    while True:
        page_query = query.start_after(cursor) if cursor is not None else query
        snapshots = list(page_query.limit(page_size).stream())
        for snapshot in snapshots:
            raw_payload: object = snapshot.to_dict()
            payload = cast(Dict[str, Any], raw_payload) if isinstance(raw_payload, dict) else {}
            item = MemoryItem.model_validate(payload)
            if item.uid != uid:
                raise ValueError(f'memory item uid mismatch: expected {uid}, got {item.uid}')
            items.append(item)
        if len(snapshots) < page_size:
            break
        cursor = snapshots[-1]
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
