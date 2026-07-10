"""Authoritative memory API field contract.

Canonical lifecycle fields (`memory_tier` plus serialized `layer`) are only
product-visible for users whose request is routed through canonical memory.
Legacy users must stay untiered at API boundaries so desktop/mobile clients do
not infer Short-term/Long-term rollout state from internal defaults.
"""

from enum import Enum
from typing import Any, Dict, Iterable

from pydantic import BaseModel


class MemoryApiExposure(str, Enum):
    LEGACY = "legacy"
    CANONICAL = "canonical"


CANONICAL_LIFECYCLE_FIELDS = frozenset({"memory_tier", "layer", "tier", "expires_at"})
MEMORY_INTERNAL_FIELDS = frozenset(
    {
        "memory_only",
        "memory_default_memory",
        "memory_source",
        "memory_policy",
        "source",
        "policy",
        "cursor",
        "read_source",
        "read_decision",
        "source_policy",
        "archive_default_available",
        "archive_default_visible",
        "stale_short_term_default_visible",
    }
)


def _payload(value: BaseModel | Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump()
    return dict(value)


def memory_api_payload(value: BaseModel | Dict[str, Any], exposure: MemoryApiExposure) -> Dict[str, Any]:
    """Serialize one memory for the requested API exposure."""
    payload = _payload(value)
    for field in MEMORY_INTERNAL_FIELDS:
        payload.pop(field, None)
    if exposure == MemoryApiExposure.LEGACY:
        for field in CANONICAL_LIFECYCLE_FIELDS:
            payload.pop(field, None)
    elif exposure == MemoryApiExposure.CANONICAL:
        tier = payload.get("memory_tier") or payload.get("tier")
        if tier is not None and payload.get("layer") is None:
            payload["layer"] = tier
    return payload


def memory_api_payloads(
    values: Iterable[BaseModel | Dict[str, Any]], exposure: MemoryApiExposure
) -> list[Dict[str, Any]]:
    return [memory_api_payload(value, exposure) for value in values]


def memory_write_payload(value: BaseModel | Dict[str, Any], exposure: MemoryApiExposure) -> Dict[str, Any]:
    """Serialize one memory for persistence through the selected memory system."""
    return memory_api_payload(value, exposure)
