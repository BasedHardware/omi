"""Canonical vector metadata builders and parsers (WS-G7).

Neutral builders serve the canonical-cohort memory path. Legacy ``build_v17_*`` builders
remain for the disabled repair adapter path.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from models.memory_search_gateway import SearchDecision, SearchVectorHit
from models.product_memory import MemoryTier, V17MemoryItem

V17_MEMORY_VECTOR_SCHEMA_VERSION = 1
V17_MEMORY_VECTOR_ID_PREFIX = "v17mem"

# Neutral canonical-memory vector schema (prod greenfield — no v17 metadata on canonical path).
MEMORY_VECTOR_SCHEMA_VERSION = 1
RESTRICTED_SENSITIVITY_LABELS = {
    "credential",
    "secret",
    "financial",
    "health",
    "intimate",
    "minor",
    "minors",
    "workplace_confidential",
    "identity_authentication",
}


@dataclass(frozen=True)
class ParsedV17VectorHit:
    hit: Optional[SearchVectorHit]
    decision: SearchDecision
    reason: str


@dataclass(frozen=True)
class ParsedMemoryVectorHit:
    hit: Optional[SearchVectorHit]
    decision: SearchDecision
    reason: str


def deterministic_v17_memory_vector_id(uid: str, memory_id: str, tier: MemoryTier | str, item_revision: int) -> str:
    """Return a V17-only vector ID that cannot collide with legacy ``{uid}-{memory_id}`` IDs."""
    tier_value = tier.value if isinstance(tier, MemoryTier) else str(tier)
    payload = f"{uid}\0{memory_id}\0{tier_value}\0{int(item_revision)}".encode("utf-8")
    return f"{V17_MEMORY_VECTOR_ID_PREFIX}:{hashlib.sha256(payload).hexdigest()}"


def _shared_memory_vector_metadata_fields(
    item: V17MemoryItem,
    *,
    projection_commit_id: str,
    vector_updated_at: datetime,
) -> Dict[str, Any]:
    if not projection_commit_id or not projection_commit_id.strip():
        raise ValueError("projection_commit_id is required")
    if vector_updated_at.tzinfo is None or vector_updated_at.utcoffset() is None:
        raise ValueError("vector_updated_at must be timezone-aware")
    labels = sorted({label.strip().lower() for label in item.sensitivity_labels if label and label.strip()})
    return {
        "uid": item.uid,
        "memory_id": item.memory_id,
        "status": item.status.value,
        "processing_state": item.processing_state.value,
        "source_state": item.source_state.value,
        "visibility": item.visibility,
        "sensitivity_labels": labels,
        "restricted_sensitivity": bool(set(labels).intersection(RESTRICTED_SENSITIVITY_LABELS)),
        "account_generation": item.account_generation,
        "item_revision": item.item_revision,
        "source_commit_id": item.source_commit_id,
        "content_hash": item.content_hash,
        "projection_commit_id": projection_commit_id,
        "vector_updated_at": vector_updated_at.isoformat(),
    }


def build_v17_memory_vector_metadata(
    item: V17MemoryItem,
    *,
    projection_commit_id: str,
    vector_updated_at: datetime,
) -> Dict[str, Any]:
    shared = _shared_memory_vector_metadata_fields(
        item, projection_commit_id=projection_commit_id, vector_updated_at=vector_updated_at
    )
    return {
        "v17_schema_version": V17_MEMORY_VECTOR_SCHEMA_VERSION,
        "memory_tier": item.tier.value,
        **shared,
    }


def build_memory_vector_metadata(
    item: V17MemoryItem,
    *,
    projection_commit_id: str,
    vector_updated_at: datetime,
) -> Dict[str, Any]:
    """Neutral metadata for canonical-cohort Pinecone vectors (``memory_layer``, ``memory_schema_version``)."""
    shared = _shared_memory_vector_metadata_fields(
        item, projection_commit_id=projection_commit_id, vector_updated_at=vector_updated_at
    )
    return {
        "memory_schema_version": MEMORY_VECTOR_SCHEMA_VERSION,
        "memory_layer": item.tier.value,
        **shared,
    }


def build_v17_default_memory_vector_filter(uid: str) -> Dict[str, Any]:
    return _base_v17_filter(uid, {"memory_tier": {"$in": [MemoryTier.short_term.value, MemoryTier.long_term.value]}})


def build_v17_archive_memory_vector_filter(uid: str) -> Dict[str, Any]:
    return _base_v17_filter(uid, {"memory_tier": {"$eq": MemoryTier.archive.value}})


def build_default_memory_vector_filter(uid: str) -> Dict[str, Any]:
    return _base_memory_vector_filter(
        uid, {"memory_layer": {"$in": [MemoryTier.short_term.value, MemoryTier.long_term.value]}}
    )


def build_archive_memory_vector_filter(uid: str) -> Dict[str, Any]:
    return _base_memory_vector_filter(uid, {"memory_layer": {"$eq": MemoryTier.archive.value}})


def parse_memory_search_vector_hit(match: Dict[str, Any]) -> ParsedMemoryVectorHit:
    metadata = match.get("metadata") or {}
    try:
        if metadata.get("memory_schema_version") != MEMORY_VECTOR_SCHEMA_VERSION:
            raise ValueError("wrong_schema")
        memory_id = _required_str(metadata, "memory_id")
        projection_commit_id = _required_str(metadata, "projection_commit_id")
        vector_updated_at = _parse_timestamp(_required_str(metadata, "vector_updated_at"))
        score = float(match.get("score", 0.0))
        hit = SearchVectorHit(
            vector_id=_optional_match_id(match),
            memory_id=memory_id,
            score=score,
            projection_commit_id=projection_commit_id,
            vector_updated_at=vector_updated_at,
            uid=_optional_str(metadata, "uid"),
            account_generation=_optional_int(metadata, "account_generation"),
            item_revision=_optional_int(metadata, "item_revision"),
            source_commit_id=_optional_str(metadata, "source_commit_id"),
            content_hash=_optional_str(metadata, "content_hash"),
        )
    except (TypeError, ValueError):
        return ParsedMemoryVectorHit(
            hit=None, decision=SearchDecision.stale_vector, reason="invalid_or_missing_vector_metadata"
        )
    return ParsedMemoryVectorHit(hit=hit, decision=SearchDecision.allowed, reason="parsed")


def parse_v17_search_vector_hit(match: Dict[str, Any]) -> ParsedV17VectorHit:
    metadata = match.get("metadata") or {}
    try:
        if metadata.get("v17_schema_version") != V17_MEMORY_VECTOR_SCHEMA_VERSION:
            raise ValueError("wrong_schema")
        memory_id = _required_str(metadata, "memory_id")
        projection_commit_id = _required_str(metadata, "projection_commit_id")
        vector_updated_at = _parse_timestamp(_required_str(metadata, "vector_updated_at"))
        score = float(match.get("score", 0.0))
        hit = SearchVectorHit(
            vector_id=_optional_match_id(match),
            memory_id=memory_id,
            score=score,
            projection_commit_id=projection_commit_id,
            vector_updated_at=vector_updated_at,
            uid=_optional_str(metadata, "uid"),
            account_generation=_optional_int(metadata, "account_generation"),
            item_revision=_optional_int(metadata, "item_revision"),
            source_commit_id=_optional_str(metadata, "source_commit_id"),
            content_hash=_optional_str(metadata, "content_hash"),
        )
    except (TypeError, ValueError):
        return ParsedV17VectorHit(
            hit=None, decision=SearchDecision.stale_vector, reason="invalid_or_missing_vector_metadata"
        )
    return ParsedV17VectorHit(hit=hit, decision=SearchDecision.allowed, reason="parsed")


def _base_v17_filter(uid: str, tier_filter: Dict[str, Any]) -> Dict[str, Any]:
    if not uid or not uid.strip():
        raise ValueError("uid is required")
    return {
        "$and": [
            {"uid": {"$eq": uid}},
            {"v17_schema_version": {"$eq": V17_MEMORY_VECTOR_SCHEMA_VERSION}},
            tier_filter,
            *_active_memory_vector_filter_clauses(),
        ]
    }


def _active_memory_vector_filter_clauses() -> list[Dict[str, Any]]:
    return [
        {"status": {"$eq": "active"}},
        {"source_state": {"$eq": "active"}},
        {"visibility": {"$in": ["private", "public", "shared"]}},
        {"restricted_sensitivity": {"$eq": False}},
    ]


def _base_memory_vector_filter(uid: str, layer_filter: Dict[str, Any]) -> Dict[str, Any]:
    if not uid or not uid.strip():
        raise ValueError("uid is required")
    return {
        "$and": [
            {"uid": {"$eq": uid}},
            {"memory_schema_version": {"$eq": MEMORY_VECTOR_SCHEMA_VERSION}},
            layer_filter,
            *_active_memory_vector_filter_clauses(),
        ]
    }


def _optional_match_id(match: Dict[str, Any]) -> Optional[str]:
    value = match.get("id")
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("id")
    return value


def _required_str(metadata: Dict[str, Any], key: str) -> str:
    value = metadata.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(key)
    return value


def _optional_str(metadata: Dict[str, Any], key: str) -> Optional[str]:
    value = metadata.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(key)
    return value


def _optional_int(metadata: Dict[str, Any], key: str) -> Optional[int]:
    value = metadata.get(key)
    if value is None:
        return None
    return int(value)


def _parse_timestamp(value: str) -> datetime:
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("naive_timestamp")
    return timestamp


__all__ = [
    "MEMORY_VECTOR_SCHEMA_VERSION",
    "V17_MEMORY_VECTOR_ID_PREFIX",
    "V17_MEMORY_VECTOR_SCHEMA_VERSION",
    "RESTRICTED_SENSITIVITY_LABELS",
    "ParsedMemoryVectorHit",
    "ParsedV17VectorHit",
    "build_archive_memory_vector_filter",
    "build_default_memory_vector_filter",
    "build_memory_vector_metadata",
    "build_v17_archive_memory_vector_filter",
    "build_v17_default_memory_vector_filter",
    "build_v17_memory_vector_metadata",
    "deterministic_v17_memory_vector_id",
    "parse_memory_search_vector_hit",
    "parse_v17_search_vector_hit",
]
