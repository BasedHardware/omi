"""Canonical module for ``utils.memory.v3_gcp_evidence_redaction`` (WS-G8b).

Neutral ``v3_gcp_evidence_redaction`` is the source of truth. Legacy ``v17_v3_gcp_evidence_redaction`` remains an importable alias.
"""

from __future__ import annotations

from utils.memory.v3_f6.redaction import (
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

# Neutral symbol aliases (V17 names remain valid via shim)
