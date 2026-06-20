"""Compatibility facade for V17-V3-F6 strict evidence redaction/output contract."""

from __future__ import annotations

from utils.memory.v17_v3_f6.redaction import (
    AUDIT_FIELDS,
    FINGERPRINT_RE,
    FORBIDDEN_FIELD_FRAGMENTS,
    FORBIDDEN_VALUE_PATTERNS,
    HMAC_KEY,
    OBSERVATION_FIELDS,
    READ_BOUNDS_FIELDS,
    TOP_LEVEL_FIELDS,
    FingerprintContractError,
    RedactionContractError,
    fingerprint,
    render_redacted_evidence_json,
    validate_redacted_evidence,
)

__all__ = [
    "AUDIT_FIELDS",
    "FINGERPRINT_RE",
    "FORBIDDEN_FIELD_FRAGMENTS",
    "FORBIDDEN_VALUE_PATTERNS",
    "FingerprintContractError",
    "HMAC_KEY",
    "OBSERVATION_FIELDS",
    "READ_BOUNDS_FIELDS",
    "RedactionContractError",
    "TOP_LEVEL_FIELDS",
    "fingerprint",
    "render_redacted_evidence_json",
    "validate_redacted_evidence",
]
