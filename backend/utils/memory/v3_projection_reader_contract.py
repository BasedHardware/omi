"""Canonical alias module for ``utils.memory.v17_v3_projection_reader_contract`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from utils.memory.v17_v3_projection_reader_contract import (
    V17V3ProjectionCursor,
    V17V3ProjectionFailureReason,
    V17V3ProjectionPage,
    V17V3ProjectionReadError,
    V17V3ProjectionReadRequest,
    V17V3ProjectionState,
    V17_V3_COMPATIBILITY_PROJECTION_SCHEMA_VERSION,
    V17_V3_COMPATIBILITY_PROJECTION_SOURCE,
    V17_V3_COMPATIBILITY_PROJECTION_VERSION,
)

__all__ = [
    "V17V3ProjectionCursor",
    "V17V3ProjectionFailureReason",
    "V17V3ProjectionPage",
    "V17V3ProjectionReadError",
    "V17V3ProjectionReadRequest",
    "V17V3ProjectionState",
    "V17_V3_COMPATIBILITY_PROJECTION_SCHEMA_VERSION",
    "V17_V3_COMPATIBILITY_PROJECTION_SOURCE",
    "V17_V3_COMPATIBILITY_PROJECTION_VERSION",
]
