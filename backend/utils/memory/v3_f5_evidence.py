"""Canonical alias module for ``utils.memory.v17_v3_f5_evidence`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from utils.memory.v17_v3_f5_evidence import (
    APPROVED_PATHS,
    BROAD_ROLES,
    EXPECTED_APPROVAL_ARTIFACT_PATH,
    EXPECTED_APPROVAL_SUBJECT,
    EXPECTED_ENVIRONMENT,
    EXPECTED_ORACLE_REVIEW_ARTIFACT,
    EXPECTED_PRINCIPAL,
    EXPECTED_PROJECT_ID,
    EXPECTED_PROJECT_NUMBER,
    EvidenceRunConfig,
    FORBIDDEN_WRITE_PERMISSIONS,
    FakeEvidenceClient,
    HMAC_KEY,
    MUTATOR_NAMES,
    REQUIRED_INDEXES,
    REQUIRED_READ_PERMISSIONS,
    ReadOnlyEvidenceClient,
    SENSITIVE_KEYS,
    TOP_LEVEL_ALLOWLIST,
    build_evidence_report,
    fingerprint,
    render_redacted_json,
    static_mutation_guard,
    validate_gates,
)

__all__ = [
    "APPROVED_PATHS",
    "BROAD_ROLES",
    "EXPECTED_APPROVAL_ARTIFACT_PATH",
    "EXPECTED_APPROVAL_SUBJECT",
    "EXPECTED_ENVIRONMENT",
    "EXPECTED_ORACLE_REVIEW_ARTIFACT",
    "EXPECTED_PRINCIPAL",
    "EXPECTED_PROJECT_ID",
    "EXPECTED_PROJECT_NUMBER",
    "EvidenceRunConfig",
    "FORBIDDEN_WRITE_PERMISSIONS",
    "FakeEvidenceClient",
    "HMAC_KEY",
    "MUTATOR_NAMES",
    "REQUIRED_INDEXES",
    "REQUIRED_READ_PERMISSIONS",
    "ReadOnlyEvidenceClient",
    "SENSITIVE_KEYS",
    "TOP_LEVEL_ALLOWLIST",
    "build_evidence_report",
    "fingerprint",
    "render_redacted_json",
    "static_mutation_guard",
    "validate_gates",
]
