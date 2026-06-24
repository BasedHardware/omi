"""Canonical alias module for ``utils.memory.v17_v3_production_runtime`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from utils.memory.v17_v3_production_runtime import (
    V17V3GetRuntime,
    V17V3GetSourceDecision,
    build_v17_v3_production_runtime,
)

__all__ = [
    "V17V3GetRuntime",
    "V17V3GetSourceDecision",
    "build_v17_v3_production_runtime",
]
