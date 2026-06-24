"""Backward-compatible shim — implementation lives in ``database.memory_non_active_routes`` (WS-G7)."""

from database.memory_non_active_routes import (
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
