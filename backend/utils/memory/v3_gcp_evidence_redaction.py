"""Canonical alias module for ``utils.memory.v17_v3_gcp_evidence_redaction`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from utils.memory.v17_v3_gcp_evidence_redaction import (
    AUDIT_FIELDS,
    FINGERPRINT_RE,
    FORBIDDEN_FIELD_FRAGMENTS,
    FORBIDDEN_VALUE_PATTERNS,
    FingerprintContractError,
    HMAC_KEY,
    OBSERVATION_FIELDS,
    READ_BOUNDS_FIELDS,
    RedactionContractError,
    TOP_LEVEL_FIELDS,
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
