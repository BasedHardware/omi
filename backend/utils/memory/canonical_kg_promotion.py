"""KG extraction on long-term promotion + citation pruning on retraction (WS-O O-W2)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from database._client import db as default_db_client
from database.memory_collections import MemoryCollections
from models.product_memory import MemoryItem, MemoryLayer
from utils.llm.knowledge_graph import extract_knowledge_from_memory

logger = logging.getLogger(__name__)


def set_canonical_memory_kg_extracted(uid: str, memory_id: str, *, db_client=None) -> None:
    client = db_client if db_client is not None else default_db_client
    path = f"{MemoryCollections(uid=uid).memory_items}/{memory_id}"
    ref = client.document(path)
    ref.set({"kg_extracted": True, "updated_at": datetime.now(timezone.utc)}, merge=True)


def extract_kg_for_promoted_memory(
    uid: str,
    item: MemoryItem,
    *,
    user_name: str = "User",
    db_client=None,
) -> bool:
    """Extract KG nodes/edges for a newly promoted long_term memory. Returns True on success."""
    if item.tier != MemoryLayer.long_term:
        return False
    if getattr(item, "kg_extracted", False):
        return False
    content = (item.content or "").strip()
    if not content:
        return False

    predicate = getattr(item, "predicate", None)
    subject_entity_id = getattr(item, "subject_entity_id", None)
    if predicate and subject_entity_id:
        content_for_kg = f"[{subject_entity_id}] {predicate}: {content}"
    else:
        content_for_kg = content

    try:
        result = extract_knowledge_from_memory(uid, content_for_kg, item.memory_id, user_name=user_name)
    except Exception:
        logger.exception("kg_extraction_failed uid=%s memory_id=%s", uid, item.memory_id)
        return False
    if result is None:
        return False
    set_canonical_memory_kg_extracted(uid, item.memory_id, db_client=db_client)
    logger.info(
        "kg_extracted_on_promotion uid=%s memory_id=%s nodes=%d edges=%d",
        uid,
        item.memory_id,
        len(result.get("nodes") or []),
        len(result.get("edges") or []),
    )
    return True
