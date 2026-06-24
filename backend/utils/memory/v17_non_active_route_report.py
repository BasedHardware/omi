"""Backward-compatible shim — implementation lives in ``utils.memory.non_active_route_report`` (WS-G8a)."""

from utils.memory.non_active_route_report import (
    fetch_non_active_route_audit_report,
)

__all__ = [
    "fetch_non_active_route_audit_report",
]
