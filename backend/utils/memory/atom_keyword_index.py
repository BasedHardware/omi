"""Typesense keyword index for canonical long-term memory atoms (WS-M).

Prod-inert: indexing and search run only for the canonical cohort and only for
``layer=long_term``, ``status=active``, ``processing_state=processed`` items.
Users on ``e2ee`` data protection are skipped (same posture as conversation Typesense).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database._client import db as default_db_client
from models.product_memory import MemoryItemStatus, MemoryTier, ProcessingState, V17MemoryItem
from utils.memory.memory_system import MemorySystem, resolve_memory_system
from utils.memory.product_memory_read_service import fetch_authoritative_product_memory_items

logger = logging.getLogger(__name__)

MEMORIES_COLLECTION = "memories"
_DEFAULT_CATEGORY = "interesting"


def _typesense_client():
    from utils.conversations.search import client

    return client


@dataclass(frozen=True)
class AtomKeywordRebuildReport:
    uid: str
    skipped_reason: Optional[str] = None
    indexed_count: int = 0
    expected_count: int = 0
    verified: bool = False


def is_indexable_long_term_atom(item: V17MemoryItem) -> bool:
    """Return True when the atom belongs in the durable keyword index."""
    return (
        item.tier == MemoryTier.long_term
        and item.status == MemoryItemStatus.active
        and item.processing_state == ProcessingState.processed
        and bool((item.content or "").strip())
    )


def user_allows_atom_keyword_index(uid: str, *, db_client=None) -> bool:
    """Canonical cohort + conversation-Typesense-compatible data protection."""
    if resolve_memory_system(uid, db_client=db_client) != MemorySystem.CANONICAL:
        return False
    from database.users import get_data_protection_level

    return get_data_protection_level(uid) != "e2ee"


def _created_at_epoch(item: V17MemoryItem) -> int:
    captured = item.captured_at
    if captured.tzinfo is None:
        captured = captured.replace(tzinfo=timezone.utc)
    return int(captured.timestamp())


def _entity_terms_for_item(item: V17MemoryItem) -> str:
    """Flatten any structured hints on the item into searchable tokens."""
    terms: List[str] = []
    promotion = item.promotion or {}
    for key in ("entity", "entity_name", "subject"):
        value = promotion.get(key)
        if isinstance(value, str) and value.strip():
            terms.append(value.strip())
    aliases = promotion.get("aliases")
    if isinstance(aliases, list):
        terms.extend(str(alias).strip() for alias in aliases if str(alias).strip())
    return " ".join(terms)


def _predicate_for_item(item: V17MemoryItem) -> str:
    promotion = item.promotion or {}
    predicate = promotion.get("predicate")
    return predicate.strip() if isinstance(predicate, str) else ""


def build_atom_keyword_document(item: V17MemoryItem) -> Dict[str, Any]:
    """Build a Typesense document for one indexable long-term atom."""
    return {
        "id": item.memory_id,
        "memory_id": item.memory_id,
        "userId": item.uid,
        "content": item.content or "",
        "category": _DEFAULT_CATEGORY,
        "layer": MemoryTier.long_term.value,
        "status": MemoryItemStatus.active.value,
        "entity_terms": _entity_terms_for_item(item),
        "predicate": _predicate_for_item(item),
        "created_at": _created_at_epoch(item),
    }


def merge_memory_search_ids(keyword_ids: List[str], vector_ids: List[str]) -> List[str]:
    """Merge keyword and vector memory ids, keyword hits first, deduplicated."""
    return list(keyword_ids) + [memory_id for memory_id in vector_ids if memory_id not in keyword_ids]


def ensure_memories_collection() -> None:
    """Create the ``memories`` Typesense collection when missing (idempotent)."""
    try:
        _typesense_client().collections[MEMORIES_COLLECTION].retrieve()
        return
    except Exception:
        pass

    schema = {
        "name": MEMORIES_COLLECTION,
        "fields": [
            {"name": "memory_id", "type": "string"},
            {"name": "userId", "type": "string", "facet": True},
            {"name": "content", "type": "string"},
            {"name": "category", "type": "string", "facet": True, "optional": True},
            {"name": "layer", "type": "string", "facet": True},
            {"name": "status", "type": "string", "facet": True},
            {"name": "entity_terms", "type": "string", "optional": True},
            {"name": "predicate", "type": "string", "optional": True},
            {"name": "created_at", "type": "int64"},
        ],
        "default_sorting_field": "created_at",
    }
    _typesense_client().collections.create(schema)


def upsert_atom_keyword_doc(item: V17MemoryItem) -> bool:
    """Upsert one long-term atom when indexable; no-op otherwise."""
    if not user_allows_atom_keyword_index(item.uid):
        return False
    if not is_indexable_long_term_atom(item):
        return False
    try:
        ensure_memories_collection()
        doc = build_atom_keyword_document(item)
        _typesense_client().collections[MEMORIES_COLLECTION].documents.upsert(doc)
        return True
    except Exception as exc:
        logger.warning(
            "upsert_atom_keyword_doc failed uid=%s memory_id=%s: %s",
            item.uid,
            item.memory_id,
            exc,
        )
        return False


def delete_atom_keyword_doc(uid: str, memory_id: str) -> None:
    """Remove one keyword doc. Canonical-gated; legacy users are no-ops."""
    if not user_allows_atom_keyword_index(uid):
        return
    if not memory_id:
        return
    try:
        _typesense_client().collections[MEMORIES_COLLECTION].documents[memory_id].delete()
    except Exception as exc:
        logger.warning("delete_atom_keyword_doc failed uid=%s memory_id=%s: %s", uid, memory_id, exc)


def purge_user_atom_keyword_index(uid: str) -> int:
    """Delete all keyword docs for a canonical user. Returns deleted count when available."""
    if not user_allows_atom_keyword_index(uid):
        return 0
    try:
        result = _typesense_client().collections[MEMORIES_COLLECTION].documents.delete({"filter_by": f"userId:={uid}"})
        return int(result.get("num_deleted") or 0)
    except Exception as exc:
        logger.warning("purge_user_atom_keyword_index failed uid=%s: %s", uid, exc)
        return 0


def sync_atom_keyword_index_for_item(item: V17MemoryItem, *, db_client=None) -> None:
    """Index or purge one atom based on its current authoritative state."""
    if not user_allows_atom_keyword_index(item.uid, db_client=db_client):
        return
    if is_indexable_long_term_atom(item):
        upsert_atom_keyword_doc(item)
    else:
        delete_atom_keyword_doc(item.uid, item.memory_id)


def keyword_search_memory_ids(
    uid: str,
    query: str,
    *,
    limit: int = 5,
    start_date: int = None,
    end_date: int = None,
) -> List[str]:
    """Typesense keyword search returning memory ids for hybrid retrieval.

    Fail-open: any search error returns [] so callers can fall back to vector-only results.
    """
    if not user_allows_atom_keyword_index(uid):
        return []
    if not (query or "").strip():
        return []
    try:
        filter_by = f"userId:={uid} && layer:={MemoryTier.long_term.value} && status:={MemoryItemStatus.active.value}"
        if start_date is not None:
            filter_by = filter_by + f" && created_at:>={start_date}"
        if end_date is not None:
            filter_by = filter_by + f" && created_at:<={end_date}"

        search_parameters = {
            "q": query,
            "query_by": "content,entity_terms,predicate",
            "filter_by": filter_by,
            "sort_by": "created_at:desc",
            "per_page": max(1, min(limit, 60)),
            "page": 1,
        }
        results = _typesense_client().collections[MEMORIES_COLLECTION].documents.search(search_parameters)
        memory_ids: List[str] = []
        for hit in results.get("hits", []):
            doc = hit.get("document") or {}
            memory_id = doc.get("memory_id") or doc.get("id")
            if memory_id:
                memory_ids.append(memory_id)
        return memory_ids
    except Exception as exc:
        logger.warning("keyword_search_memory_ids failed uid=%s, falling back to vector-only: %s", uid, exc)
        return []


def rebuild_atom_keyword_index(uid: str, *, db_client=None) -> AtomKeywordRebuildReport:
    """Rebuild the keyword index for one user from the canonical store (idempotent)."""
    client = db_client if db_client is not None else default_db_client
    if not user_allows_atom_keyword_index(uid, db_client=client):
        return AtomKeywordRebuildReport(uid=uid, skipped_reason="not_indexable_user")

    items = fetch_authoritative_product_memory_items(uid=uid, db_client=client)
    indexable = [item for item in items if is_indexable_long_term_atom(item)]

    purge_user_atom_keyword_index(uid)
    indexed = 0
    for item in indexable:
        if upsert_atom_keyword_doc(item):
            indexed += 1

    expected = len(indexable)
    return AtomKeywordRebuildReport(
        uid=uid,
        indexed_count=indexed,
        expected_count=expected,
        verified=indexed == expected,
    )


def typesense_configured() -> bool:
    """Return True when Typesense env vars are present."""
    return bool(os.getenv("TYPESENSE_HOST") and os.getenv("TYPESENSE_API_KEY"))
