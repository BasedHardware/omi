"""Backward-compatible shim — implementation lives in ``utils.memory.v3_write_convergence`` (WS-G8b)."""

from utils.memory.v3_write_convergence import (
    decide_v17_v3_write_convergence,
    V17V3ExternalWriteOperation,
    V17V3WriteConvergenceContext,
    V17V3WriteConvergenceDecision,
    V17V3WriteConvergenceStatus,
    V3ExternalWriteOperation,
    V3WriteConvergenceContext,
    V3WriteConvergenceDecision,
    V3WriteConvergenceStatus,
    _blocked,
    _disabled_safe_pilot,
    _first_blocker,
    _headers,
)

__all__ = [
    "decide_v17_v3_write_convergence",
    "V17V3ExternalWriteOperation",
    "V17V3WriteConvergenceContext",
    "V17V3WriteConvergenceDecision",
    "V17V3WriteConvergenceStatus",
    "V3ExternalWriteOperation",
    "V3WriteConvergenceContext",
    "V3WriteConvergenceDecision",
    "V3WriteConvergenceStatus",
    "_blocked",
    "_disabled_safe_pilot",
    "_first_blocker",
    "_headers",
]
