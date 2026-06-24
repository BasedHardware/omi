"""Canonical alias module for ``utils.memory.v17_v3_write_convergence`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from utils.memory.v17_v3_write_convergence import (
    V17V3ExternalWriteOperation,
    V17V3WriteConvergenceContext,
    V17V3WriteConvergenceDecision,
    V17V3WriteConvergenceStatus,
    decide_v17_v3_write_convergence,
)

__all__ = [
    "V17V3ExternalWriteOperation",
    "V17V3WriteConvergenceContext",
    "V17V3WriteConvergenceDecision",
    "V17V3WriteConvergenceStatus",
    "decide_v17_v3_write_convergence",
]
