"""KG extraction on long-term promotion + citation pruning on retraction (WS-O O-W2)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any, Optional, cast

from google.api_core.exceptions import NotFound as FirestoreNotFound

from database._client import db as default_db_client
from database.memory_collections import MemoryCollections
from models.product_memory import MemoryItem, MemoryLayer
from utils.llm.knowledge_graph import extract_knowledge_from_memory
from utils.memory.memory_system import MemorySystem, resolve_memory_system

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CanonicalKgPromotionResult:
    attempted: bool = False
    success: bool = False
    skipped_reason: Optional[str] = None
    node_count: int = 0
    edge_count: int = 0

    @property
    def empty(self) -> bool:
        return self.success and self.node_count == 0 and self.edge_count == 0


def _content_for_kg_extraction(item: MemoryItem) -> str:
    content = (item.content or "").strip()
    predicate = getattr(item, "predicate", None)
    subject_entity_id = getattr(item, "subject_entity_id", None)
    raw_arguments = getattr(item, "arguments", None)
    arguments = cast(dict[str, Any], raw_arguments) if isinstance(raw_arguments, dict) else {}
    args_suffix = ""
    if arguments:
        args_suffix = f" ({' '.join(f'{key}={value}' for key, value in arguments.items())})"

    if predicate and subject_entity_id:
        return f"[{subject_entity_id}] {predicate}{args_suffix}: {content}"
    if predicate:
        return f"{predicate}{args_suffix}: {content}"
    return content


def set_canonical_memory_kg_extracted(uid: str, memory_id: str, *, db_client: Any = None) -> bool:
    client: Any = db_client if db_client is not None else default_db_client
    path = f"{MemoryCollections(uid=uid).memory_items}/{memory_id}"
    ref = client.document(path)
    try:
        ref.update({"kg_extracted": True, "updated_at": datetime.now(timezone.utc)})
        return True
    except FirestoreNotFound:
        logger.warning(
            "Skipping stale canonical memory kg_extracted update: document no longer exists uid=%s",
            uid,
        )
        return False


def set_canonical_memory_kg_extracted_without_touching_updated_at(
    uid: str, memory_id: str, *, db_client: Any = None
) -> bool:
    """Mark KG extraction complete without changing the product-memory timestamp."""
    client: Any = db_client if db_client is not None else default_db_client
    path = f"{MemoryCollections(uid=uid).memory_items}/{memory_id}"
    ref = client.document(path)
    try:
        ref.update({"kg_extracted": True})
        return True
    except FirestoreNotFound:
        logger.warning(
            "Skipping stale canonical memory kg_extracted update: document no longer exists uid=%s",
            uid,
        )
        return False


def extract_kg_for_promoted_memory(
    uid: str,
    item: MemoryItem,
    *,
    user_name: str = "User",
    db_client: Any = None,
    preserve_item_updated_at: bool = False,
) -> CanonicalKgPromotionResult:
    """Extract KG nodes/edges for a newly promoted long_term memory."""
    client: Any = db_client if db_client is not None else default_db_client
    if resolve_memory_system(uid, db_client=client) != MemorySystem.CANONICAL:
        return CanonicalKgPromotionResult(skipped_reason="not_canonical_cohort")
    if item.tier != MemoryLayer.long_term:
        return CanonicalKgPromotionResult(skipped_reason="not_long_term")
    if getattr(item, "kg_extracted", False):
        return CanonicalKgPromotionResult(skipped_reason="already_extracted")
    content = (item.content or "").strip()
    if not content:
        return CanonicalKgPromotionResult(skipped_reason="empty_content")

    content_for_kg = _content_for_kg_extraction(item)

    try:
        result = extract_knowledge_from_memory(
            uid,
            content_for_kg,
            item.memory_id,
            user_name=user_name,
            db_client=client,
            strict_parse=True,
        )
    except Exception:
        logger.exception("kg_extraction_failed uid=%s memory_id=%s", uid, item.memory_id)
        return CanonicalKgPromotionResult(attempted=True, skipped_reason="exception")
    if result is None:
        return CanonicalKgPromotionResult(attempted=True, skipped_reason="extractor_failed")
    if preserve_item_updated_at:
        set_canonical_memory_kg_extracted_without_touching_updated_at(uid, item.memory_id, db_client=db_client)
    else:
        set_canonical_memory_kg_extracted(uid, item.memory_id, db_client=db_client)
    node_count = len(result.get("nodes") or [])
    edge_count = len(result.get("edges") or [])
    logger.info(
        "kg_extracted_on_promotion uid=%s memory_id=%s nodes=%d edges=%d",
        uid,
        item.memory_id,
        node_count,
        edge_count,
    )
    return CanonicalKgPromotionResult(attempted=True, success=True, node_count=node_count, edge_count=edge_count)
