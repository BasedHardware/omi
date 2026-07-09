"""Sync canonical-cohort memory items to Pinecone using neutral vector ids + metadata."""

from __future__ import annotations

import logging
from typing import Callable, Optional

from models.memory_evidence import SourceState
from models.product_memory import MemoryItemStatus, MemoryItem

logger = logging.getLogger(__name__)


def delete_canonical_memory_vector(uid: str, memory_id: str) -> None:
    """Delete a canonical neutral-id vector (identity = memory_id)."""
    try:
        from database.vector_db import delete_pinecone_memory_vectors_by_id

        delete_pinecone_memory_vectors_by_id([memory_id])
    except Exception:
        logger.exception(
            "canonical vector delete failed memory_id=%s uid=%s",
            memory_id,
            uid,
        )


def sync_canonical_memory_vector(
    item: MemoryItem,
    *,
    projection_commit_id: Optional[str] = None,
    on_hard_failure: Optional[Callable[[], None]] = None,
) -> bool:
    """Upsert one live canonical memory item vector. Returns True when an upsert was attempted."""
    if item.status != MemoryItemStatus.active or item.source_state != SourceState.active:
        return False
    content = (item.content or "").strip()
    if not content:
        return False

    try:
        from database.vector_db import upsert_canonical_memory_vector

        result = upsert_canonical_memory_vector(item, projection_commit_id=projection_commit_id)
    except Exception:
        logger.exception(
            "canonical vector sync failed memory_id=%s uid=%s",
            item.memory_id,
            item.uid,
        )
        if on_hard_failure is not None:
            on_hard_failure()
        return False
    if result is None:
        logger.warning("canonical vector sync skipped memory_id=%s uid=%s", item.memory_id, item.uid)
        return False
    return True
