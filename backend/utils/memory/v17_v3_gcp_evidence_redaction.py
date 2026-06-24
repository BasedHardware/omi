"""Backward-compatible shim — implementation lives in ``utils.memory.v3_gcp_evidence_redaction`` (WS-G8b)."""

from utils.memory.v3_gcp_evidence_redaction import (
    AUDIT_FIELDS,
    fingerprint,
    FINGERPRINT_RE,
    FingerprintContractError,
    FORBIDDEN_FIELD_FRAGMENTS,
    FORBIDDEN_VALUE_PATTERNS,
    HMAC_KEY,
    OBSERVATION_FIELDS,
    READ_BOUNDS_FIELDS,
    RedactionContractError,
    render_redacted_evidence_json,
    TOP_LEVEL_FIELDS,
    validate_redacted_evidence,
)

__all__ = [
    "AUDIT_FIELDS",
    "fingerprint",
    "FINGERPRINT_RE",
    "FingerprintContractError",
    "FORBIDDEN_FIELD_FRAGMENTS",
    "FORBIDDEN_VALUE_PATTERNS",
    "HMAC_KEY",
    "OBSERVATION_FIELDS",
    "READ_BOUNDS_FIELDS",
    "RedactionContractError",
    "render_redacted_evidence_json",
    "TOP_LEVEL_FIELDS",
    "validate_redacted_evidence",
]
