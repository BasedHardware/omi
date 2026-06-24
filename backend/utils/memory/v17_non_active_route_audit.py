"""Backward-compatible shim — implementation lives in ``utils.memory.non_active_route_audit`` (WS-G8a)."""

from utils.memory.non_active_route_audit import (
    NonActiveRouteAuditEvidence,
    NonActiveRouteAuditReport,
    build_non_active_route_audit_report,
)

__all__ = [
    "NonActiveRouteAuditEvidence",
    "NonActiveRouteAuditReport",
    "build_non_active_route_audit_report",
]
