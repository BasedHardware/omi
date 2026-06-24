"""Backward-compatible shim — implementation lives in ``utils.memory.v3_gcp_evidence_config`` (WS-G8b)."""

from utils.memory.v3_gcp_evidence_config import (
    AUDIT_FIELDS,
    AuditSettings,
    DEFAULT_APPROVED_METADATA_PATHS,
    DEFAULT_EVIDENCE_TARGETS,
    DEFAULT_INDEX_EXPECTATIONS,
    EvidenceLimits,
    EvidenceTarget,
    EvidenceTargetRegistry,
    INDEX_FIELDS,
    LIMIT_FIELDS,
    PLACEHOLDER_MARKERS,
    TARGET_FIELDS,
    ValidationError,
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
