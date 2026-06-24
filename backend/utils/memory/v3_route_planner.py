"""Canonical alias module for ``utils.memory.v17_v3_route_planner`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from utils.memory.v17_v3_route_planner import (
    V17V3RouteExecutionPlan,
    V17V3RoutePlanInput,
    plan_v17_v3_memory_route,
)

__all__ = [
    "V17V3RouteExecutionPlan",
    "V17V3RoutePlanInput",
    "plan_v17_v3_memory_route",
]
