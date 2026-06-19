from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from database.v17_collections import V17Collections
from models.v17_product_memory import MemoryAccessPolicy, V17MemoryItem
from utils.memory.v17_read_api import query_default_product_memory_items

DEFAULT_PRODUCT_MEMORY_READ_LIMIT = 100
MAX_PRODUCT_MEMORY_READ_LIMIT = 500


def fetch_default_product_memory_search(
    uid: str,
    query: str,
    *,
    db_client,
    policy: MemoryAccessPolicy,
    now: Optional[datetime] = None,
    limit: int = DEFAULT_PRODUCT_MEMORY_READ_LIMIT,
    offset: int = 0,
) -> Dict[str, Any]:
    """Fetch authoritative V17 `memory_items` and return default-visible product search results.

    This is the concrete T19/T21 read-service seam for product callers: it reads
    `users/{uid}/memory_items`, coerces documents to `V17MemoryItem`, delegates
    default visibility to `query_default_product_memory_items(...)`, then paginates
    the filtered/matched results. Archive remains unavailable here by design; use
    the explicit archive query seam for archive-capable product surfaces.
    """

    bounded_limit = _validate_limit(limit)
    bounded_offset = _validate_offset(offset)
    items = fetch_authoritative_product_memory_items(uid=uid, db_client=db_client)
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


def fetch_authoritative_product_memory_items(uid: str, *, db_client) -> List[V17MemoryItem]:
    """Load and coerce all authoritative V17 product memory item docs for one user."""

    collection_path = V17Collections(uid=uid).memory_items
    items = []
    for snapshot in db_client.collection(collection_path).stream():
        payload = snapshot.to_dict() or {}
        item = V17MemoryItem.model_validate(payload)
        if item.uid != uid:
            raise ValueError(f'memory item uid mismatch: expected {uid}, got {item.uid}')
        items.append(item)
    return sorted(items, key=_memory_item_sort_key)


def _memory_item_sort_key(item: V17MemoryItem):
    return (-item.updated_at.timestamp(), item.memory_id)


def _validate_limit(limit: int) -> int:
    if limit < 1 or limit > MAX_PRODUCT_MEMORY_READ_LIMIT:
        raise ValueError(f'limit must be between 1 and {MAX_PRODUCT_MEMORY_READ_LIMIT}')
    return limit


def _validate_offset(offset: int) -> int:
    if offset < 0:
        raise ValueError('offset must be non-negative')
    return offset
