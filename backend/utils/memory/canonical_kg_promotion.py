"""KG extraction on long-term promotion + citation pruning on retraction (WS-O O-W2)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from database._client import db as default_db_client
from database.memory_collections import MemoryCollections
from models.product_memory import MemoryItem, MemoryLayer
from utils.llm.knowledge_graph import extract_knowledge_from_memory
from utils.memory.memory_system import MemorySystem, resolve_memory_system

logger = logging.getLogger(__name__)


def _content_for_kg_extraction(item: MemoryItem) -> str:
    content = (item.content or "").strip()
    predicate = getattr(item, "predicate", None)
    subject_entity_id = getattr(item, "subject_entity_id", None)
    arguments = getattr(item, "arguments", None) or {}
    args_suffix = ""
    if arguments:
        args_suffix = f" ({' '.join(f'{key}={value}' for key, value in arguments.items())})"

    if predicate and subject_entity_id:
        return f"[{subject_entity_id}] {predicate}{args_suffix}: {content}"
    if predicate:
        return f"{predicate}{args_suffix}: {content}"
    return content


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
    client = db_client if db_client is not None else default_db_client
    if resolve_memory_system(uid, db_client=client) != MemorySystem.CANONICAL:
        return False
    if item.tier != MemoryLayer.long_term:
        return False
    if getattr(item, "kg_extracted", False):
        return False
    content = (item.content or "").strip()
    if not content:
        return False

    content_for_kg = _content_for_kg_extraction(item)

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
