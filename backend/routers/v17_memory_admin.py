"""Backward-compatible shim — implementation in ``routers.memory_admin`` (WS-G9)."""

from routers.memory_admin import (
    db,
    fetch_non_active_route_audit_report,
    get_v17_non_active_route_report,
    get_v17_read_rollout_decision,
    post_v17_short_term_lifecycle_run,
    router,
    run_short_term_lifecycle_firestore,
)

__all__ = [
    "db",
    "fetch_non_active_route_audit_report",
    "get_v17_non_active_route_report",
    "get_v17_read_rollout_decision",
    "post_v17_short_term_lifecycle_run",
    "router",
    "run_short_term_lifecycle_firestore",
]
