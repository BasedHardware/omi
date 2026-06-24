"""Sync canonical-cohort memory items to Pinecone using neutral vector ids + metadata."""

from __future__ import annotations

import logging
from typing import Optional

from models.memory_evidence import SourceState
from models.product_memory import MemoryItemStatus, V17MemoryItem

logger = logging.getLogger(__name__)


def sync_canonical_memory_vector(item: V17MemoryItem, *, projection_commit_id: Optional[str] = None) -> bool:
    """Upsert one live canonical memory item vector. Returns True when an upsert was attempted."""
    if item.status != MemoryItemStatus.active or item.source_state != SourceState.active:
        return False
    content = (item.content or "").strip()
    if not content:
        return False

    from database.vector_db import upsert_canonical_memory_vector

    result = upsert_canonical_memory_vector(item, projection_commit_id=projection_commit_id)
    if result is None:
        logger.warning("canonical vector sync skipped memory_id=%s uid=%s", item.memory_id, item.uid)
        return False
    return True
