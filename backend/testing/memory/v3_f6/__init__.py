"""Canonical package for ``testing.memory.v3_f6`` (WS-G8b)."""

from __future__ import annotations

from testing.memory.v3_f6.aggregate import (
    F6_LOCAL_GATE_IDS,
    GCP_ACCESS_GATE_IDS,
    NON_CLAIMS,
    build_pre_gcp_aggregate_report,
)
from testing.memory.v3_f6.audit import (
    WRITE_METHOD_MARKERS,
    AuditCorrelationResult,
    AuditLogClient,
    AuditLogEvent,
    AuditQuery,
    _audit_method_is_write,
    _method_family,
    assess_audit_correlation,
)
from testing.memory.v3_f6.identity_iam import (
    FORBIDDEN_BROAD_ROLES,
    FORBIDDEN_WRITE_PERMISSIONS,
    REQUIRED_READ_PERMISSIONS,
    IdentityIamSource,
    IdentityIamTarget,
    IdentityIamVerificationResult,
    verify_identity_iam,
)
from testing.memory.v3_f6.local_doubles import (
    FakeAuditLogClient,
    FakeIdentityIamSource,
    FakeReadEvidenceTransport,
)
from testing.memory.v3_f6.read_evidence import (
    GENERIC_OR_RAW_METHODS,
    MUTATOR_TOKENS,
    EvidenceClientConfig,
    ReadEvidenceRequest,
    ReadEvidenceTransport,
    ReadOnlyEvidenceClient,
    _method_is_forbidden,
)
from testing.memory.v3_f6.run_context import RunRecord

__all__ = [
    "AuditCorrelationResult",
    "AuditLogClient",
    "AuditLogEvent",
    "AuditQuery",
    "EvidenceClientConfig",
    "F6_LOCAL_GATE_IDS",
    "FORBIDDEN_BROAD_ROLES",
    "FORBIDDEN_WRITE_PERMISSIONS",
    "FakeAuditLogClient",
    "FakeIdentityIamSource",
    "FakeReadEvidenceTransport",
    "GCP_ACCESS_GATE_IDS",
    "GENERIC_OR_RAW_METHODS",
    "IdentityIamSource",
    "IdentityIamTarget",
    "IdentityIamVerificationResult",
    "MUTATOR_TOKENS",
    "NON_CLAIMS",
    "REQUIRED_READ_PERMISSIONS",
    "ReadEvidenceRequest",
    "ReadEvidenceTransport",
    "ReadOnlyEvidenceClient",
    "RunRecord",
    "WRITE_METHOD_MARKERS",
    "_audit_method_is_write",
    "_method_family",
    "_method_is_forbidden",
    "assess_audit_correlation",
    "build_pre_gcp_aggregate_report",
    "build_report_from_current_local_contracts",
    "verify_identity_iam",
]


def __getattr__(name: str):
    if name == "build_report_from_current_local_contracts":
        from testing.memory.v3_f6.local_smoke import build_report_from_current_local_contracts

        return build_report_from_current_local_contracts
    raise AttributeError(name)
