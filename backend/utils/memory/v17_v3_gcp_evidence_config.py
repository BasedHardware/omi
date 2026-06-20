"""Compatibility facade for V17-V3-F6 evidence target config.

Canonical schema/validation lives in :mod:`utils.memory.v17_v3_f6.config`;
local placeholder defaults live in :mod:`utils.memory.v17_v3_f6.local_defaults`.
This module preserves the original public import surface.
"""

from __future__ import annotations

from utils.memory.v17_v3_f6.config import (
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
from utils.memory.v17_v3_f6.local_defaults import (
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
