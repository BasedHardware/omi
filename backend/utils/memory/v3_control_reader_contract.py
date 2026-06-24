"""Canonical alias module for ``utils.memory.v17_v3_control_reader_contract`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from utils.memory.v17_v3_control_reader_contract import (
    V17V3ControlDecisionReason,
    V17V3ControlReadResult,
    V17V3ControlReader,
    V17V3ControlReaderRequest,
    V17V3ControlRouteDecision,
    V17V3ControlRouteFamily,
    V17V3ControlState,
    decide_v17_v3_control_route,
)

__all__ = [
    "V17V3ControlDecisionReason",
    "V17V3ControlReadResult",
    "V17V3ControlReader",
    "V17V3ControlReaderRequest",
    "V17V3ControlRouteDecision",
    "V17V3ControlRouteFamily",
    "V17V3ControlState",
    "decide_v17_v3_control_route",
]
