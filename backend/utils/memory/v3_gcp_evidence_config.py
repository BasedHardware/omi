"""Canonical module for ``utils.memory.v3_gcp_evidence_config`` (WS-G8b)."""

from __future__ import annotations

from utils.memory.v3_f6.config import (
    AUDIT_FIELDS,
    INDEX_FIELDS,
    LIMIT_FIELDS,
    PLACEHOLDER_MARKERS,
    TARGET_FIELDS,
    AuditSettings,
    EvidenceLimits,
    EvidenceTarget,
    EvidenceTargetRegistry,
    ValidationError,
)
from utils.memory.v3_f6.local_defaults import (
    DEFAULT_APPROVED_METADATA_PATHS,
    DEFAULT_EVIDENCE_TARGETS,
    DEFAULT_INDEX_EXPECTATIONS,
)

__all__ = [
    "AUDIT_FIELDS",
    "AuditSettings",
    "DEFAULT_APPROVED_METADATA_PATHS",
    "DEFAULT_EVIDENCE_TARGETS",
    "DEFAULT_INDEX_EXPECTATIONS",
    "EvidenceLimits",
    "EvidenceTarget",
    "EvidenceTargetRegistry",
    "INDEX_FIELDS",
    "LIMIT_FIELDS",
    "PLACEHOLDER_MARKERS",
    "TARGET_FIELDS",
    "ValidationError",
]

# Neutral symbol aliases (memory names remain valid via shim)
