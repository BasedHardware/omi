"""Canonical memory-V3-F6 read-only contract exports."""

from __future__ import annotations

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
    "FORBIDDEN_BROAD_ROLES",
    "FORBIDDEN_WRITE_PERMISSIONS",
    "FakeAuditLogClient",
    "FakeIdentityIamSource",
    "FakeReadEvidenceTransport",
    "GENERIC_OR_RAW_METHODS",
    "IdentityIamSource",
    "IdentityIamTarget",
    "IdentityIamVerificationResult",
    "MUTATOR_TOKENS",
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
    "verify_identity_iam",
]
