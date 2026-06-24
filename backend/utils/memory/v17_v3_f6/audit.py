"""Backward-compatible shim — implementation in ``utils.memory.v3_f6.audit`` (WS-G8b)."""

from utils.memory.v3_f6.audit import (
    assess_audit_correlation,
    AuditCorrelationResult,
    AuditLogClient,
    AuditLogEvent,
    AuditQuery,
    WRITE_METHOD_MARKERS,
    _audit_method_is_write,
    _method_family,
)

__all__ = [
    "assess_audit_correlation",
    "AuditCorrelationResult",
    "AuditLogClient",
    "AuditLogEvent",
    "AuditQuery",
    "WRITE_METHOD_MARKERS",
    "_audit_method_is_write",
    "_method_family",
]
