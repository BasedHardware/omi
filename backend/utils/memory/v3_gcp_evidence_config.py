"""Canonical alias module for ``utils.memory.v17_v3_gcp_evidence_config`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from utils.memory.v17_v3_gcp_evidence_config import (
    AUDIT_FIELDS,
    DEFAULT_APPROVED_METADATA_PATHS,
    DEFAULT_EVIDENCE_TARGETS,
    DEFAULT_INDEX_EXPECTATIONS,
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
