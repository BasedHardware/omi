"""Backward-compatible shim — implementation in ``utils.memory.v3_f6.local_doubles`` (WS-G8b)."""

from utils.memory.v3_f6.local_doubles import (
    AuditLogEvent,
    AuditQuery,
    FakeAuditLogClient,
    FakeIdentityIamSource,
    FakeReadEvidenceTransport,
    ReadEvidenceRequest,
)

__all__ = [
    "AuditLogEvent",
    "AuditQuery",
    "FakeAuditLogClient",
    "FakeIdentityIamSource",
    "FakeReadEvidenceTransport",
    "ReadEvidenceRequest",
]
