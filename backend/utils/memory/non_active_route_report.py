"""Canonical alias module for ``utils.memory.v17_non_active_route_report`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from utils.memory.v17_non_active_route_report import (
    fetch_non_active_route_audit_report,
)

__all__ = [
    "fetch_non_active_route_audit_report",
]
