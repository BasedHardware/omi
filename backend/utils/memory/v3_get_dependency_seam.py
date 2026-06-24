"""Canonical alias module for ``utils.memory.v17_v3_get_dependency_seam`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from utils.memory.v17_v3_get_dependency_seam import (
    DecisionKind,
    DependencyAdapter,
    DependencyStatus,
    LOW_CARDINALITY_DECISION_CODES,
    V17V3GetDependencyAdapters,
    V17V3GetDependencyChainResult,
    V17V3GetDependencyContext,
    V17V3GetDependencyDecision,
    plan_v17_v3_get_dependency_chain,
)

__all__ = [
    "DecisionKind",
    "DependencyAdapter",
    "DependencyStatus",
    "LOW_CARDINALITY_DECISION_CODES",
    "V17V3GetDependencyAdapters",
    "V17V3GetDependencyChainResult",
    "V17V3GetDependencyContext",
    "V17V3GetDependencyDecision",
    "plan_v17_v3_get_dependency_chain",
]
