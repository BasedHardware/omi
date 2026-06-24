"""Canonical alias module for ``database.v17_non_active_memory_routes`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from database.v17_non_active_memory_routes import (
    NonActiveRoute,
    NonActiveRouteOutcome,
    NonActiveRouteStoreConflict,
    PersistedNonActiveRouteOutcome,
    persist_non_active_route_outcome,
)

__all__ = [
    "NonActiveRoute",
    "NonActiveRouteOutcome",
    "NonActiveRouteStoreConflict",
    "PersistedNonActiveRouteOutcome",
    "persist_non_active_route_outcome",
]
