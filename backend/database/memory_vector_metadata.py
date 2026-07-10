"""Canonical vector metadata builders and parsers (WS-G7).

Neutral builders serve the canonical-cohort memory path. Legacy ``build_memory_*`` builders
remain for the disabled repair adapter path.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional, cast

from models.memory_search_gateway import SearchDecision, SearchVectorHit
from models.product_memory import MemoryTier, MemoryItem

MEMORY_VECTOR_SCHEMA_VERSION = 1
MEMORY_VECTOR_ID_PREFIX = "memvec"

# Neutral canonical-memory vector schema (prod greenfield — no legacy metadata on canonical path).
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
class ParsedVectorHit:
    hit: Optional[SearchVectorHit]
    decision: SearchDecision
    reason: str


@dataclass(frozen=True)
class ParsedMemoryVectorHit:
    hit: Optional[SearchVectorHit]
    decision: SearchDecision
    reason: str


def deterministic_memory_vector_id(uid: str, memory_id: str, tier: MemoryTier | str, item_revision: int) -> str:
    """Return a memory-only vector ID that cannot collide with legacy ``{uid}-{memory_id}`` IDs."""
    tier_value = tier.value if isinstance(tier, MemoryTier) else str(tier)
    payload = f"{uid}\0{memory_id}\0{tier_value}\0{int(item_revision)}".encode("utf-8")
    return f"{MEMORY_VECTOR_ID_PREFIX}:{hashlib.sha256(payload).hexdigest()}"


def _shared_memory_vector_metadata_fields(
    item: MemoryItem,
    *,
    projection_commit_id: str,
    vector_updated_at: datetime,
) -> Dict[str, Any]:
    if not projection_commit_id or not projection_commit_id.strip():
        raise ValueError("projection_commit_id is required")
    if vector_updated_at.tzinfo is None or vector_updated_at.utcoffset() is None:
        raise ValueError("vector_updated_at must be timezone-aware")
    labels = sorted({label.strip().lower() for label in item.sensitivity_labels if label and label.strip()})
    shared = {
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
    device_ids = sorted({d for d in (item.capture_device_ids or []) if d})
    if not device_ids and item.primary_capture_device:
        device_ids = [item.primary_capture_device]
    if device_ids:
        shared["capture_device_ids"] = device_ids
    return strip_null_metadata_values(shared)


def build_memory_vector_metadata(
    item: MemoryItem,
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


def strip_null_metadata_values(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Return Pinecone-safe metadata without null values."""
    return {key: value for key, value in metadata.items() if value is not None}


def build_default_memory_vector_filter(uid: str) -> Dict[str, Any]:
    return _base_memory_vector_filter(
        uid, {"memory_layer": {"$in": [MemoryTier.short_term.value, MemoryTier.long_term.value]}}
    )


def build_archive_memory_vector_filter(uid: str) -> Dict[str, Any]:
    return _base_memory_vector_filter(uid, {"memory_layer": {"$eq": MemoryTier.archive.value}})


def parse_memory_search_vector_hit(match: Dict[str, Any]) -> ParsedMemoryVectorHit:
    raw_metadata = match.get("metadata")
    metadata: Dict[str, Any] = cast(Dict[str, Any], raw_metadata) if isinstance(raw_metadata, dict) else {}
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


def parse_search_vector_hit(match: Dict[str, Any]) -> ParsedVectorHit:
    raw_metadata = match.get("metadata")
    metadata: Dict[str, Any] = cast(Dict[str, Any], raw_metadata) if isinstance(raw_metadata, dict) else {}
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
        return ParsedVectorHit(
            hit=None, decision=SearchDecision.stale_vector, reason="invalid_or_missing_vector_metadata"
        )
    return ParsedVectorHit(hit=hit, decision=SearchDecision.allowed, reason="parsed")


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
    "MEMORY_VECTOR_ID_PREFIX",
    "RESTRICTED_SENSITIVITY_LABELS",
    "ParsedMemoryVectorHit",
    "ParsedVectorHit",
    "build_archive_memory_vector_filter",
    "build_default_memory_vector_filter",
    "build_memory_vector_metadata",
    "deterministic_memory_vector_id",
    "parse_memory_search_vector_hit",
    "parse_search_vector_hit",
    "strip_null_metadata_values",
]
