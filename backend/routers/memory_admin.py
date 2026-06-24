"""Canonical alias module for ``routers.v17_memory_admin`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from routers.v17_memory_admin import (
    get_v17_non_active_route_report,
    get_v17_read_rollout_decision,
    post_v17_short_term_lifecycle_run,
    router,
)

__all__ = [
    "get_v17_non_active_route_report",
    "get_v17_read_rollout_decision",
    "post_v17_short_term_lifecycle_run",
    "router",
]
