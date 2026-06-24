"""Backward-compatible shim — implementation lives in ``utils.memory.v3_projection_readiness`` (WS-G8b)."""

from utils.memory.v3_projection_readiness import (
    decide_v17_v3_projection_readiness,
    V17_DERIVED_COMPATIBILITY_PROJECTION_SOURCE,
    V17V3ProjectionReadinessContext,
    V17V3ProjectionReadinessDecision,
    V17V3ProjectionReadinessState,
    V3ProjectionReadinessContext,
    V3ProjectionReadinessDecision,
    V3ProjectionReadinessState,
    _blocked,
    _Blocker,
    _first_blocker,
)

__all__ = [
    "decide_v17_v3_projection_readiness",
    "V17_DERIVED_COMPATIBILITY_PROJECTION_SOURCE",
    "V17V3ProjectionReadinessContext",
    "V17V3ProjectionReadinessDecision",
    "V17V3ProjectionReadinessState",
    "V3ProjectionReadinessContext",
    "V3ProjectionReadinessDecision",
    "V3ProjectionReadinessState",
    "_blocked",
    "_Blocker",
    "_first_blocker",
]
