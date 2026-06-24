"""Canonical alias module for ``utils.memory.v17_v3_projection_readiness`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from utils.memory.v17_v3_projection_readiness import (
    V17V3ProjectionReadinessContext,
    V17V3ProjectionReadinessDecision,
    V17V3ProjectionReadinessState,
    V17_DERIVED_COMPATIBILITY_PROJECTION_SOURCE,
    decide_v17_v3_projection_readiness,
)

__all__ = [
    "V17V3ProjectionReadinessContext",
    "V17V3ProjectionReadinessDecision",
    "V17V3ProjectionReadinessState",
    "V17_DERIVED_COMPATIBILITY_PROJECTION_SOURCE",
    "decide_v17_v3_projection_readiness",
]
