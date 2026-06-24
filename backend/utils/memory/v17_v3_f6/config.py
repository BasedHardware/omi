"""Backward-compatible shim — implementation in ``utils.memory.v3_f6.config`` (WS-G8b)."""

from utils.memory.v3_f6.config import (
    AUDIT_FIELDS,
    AuditSettings,
    EvidenceLimits,
    EvidenceTarget,
    EvidenceTargetRegistry,
    INDEX_FIELDS,
    LIMIT_FIELDS,
    PLACEHOLDER_MARKERS,
    require_exact_fields,
    TARGET_FIELDS,
    ValidationError,
    _has_placeholder,
    _parse_target,
    _require_exact_fields,
)

__all__ = [
    "AUDIT_FIELDS",
    "AuditSettings",
    "EvidenceLimits",
    "EvidenceTarget",
    "EvidenceTargetRegistry",
    "INDEX_FIELDS",
    "LIMIT_FIELDS",
    "PLACEHOLDER_MARKERS",
    "require_exact_fields",
    "TARGET_FIELDS",
    "ValidationError",
    "_has_placeholder",
    "_parse_target",
    "_require_exact_fields",
]
