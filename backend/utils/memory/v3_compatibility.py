"""Canonical alias module for ``utils.memory.v17_v3_compatibility`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from utils.memory.v17_v3_compatibility import (
    ENROLLED_FAIL_CLOSED_CONTROL_STATES,
    SUPPORTED_ENROLLED_CONTROL_STATES,
    V17V3CompatibilityContext,
    V17V3CompatibilityDecision,
    V17V3CompatibilityReadPath,
    V17V3CursorMode,
    decide_v17_v3_compatibility,
    describe_v17_cursor_mode,
)

__all__ = [
    "ENROLLED_FAIL_CLOSED_CONTROL_STATES",
    "SUPPORTED_ENROLLED_CONTROL_STATES",
    "V17V3CompatibilityContext",
    "V17V3CompatibilityDecision",
    "V17V3CompatibilityReadPath",
    "V17V3CursorMode",
    "decide_v17_v3_compatibility",
    "describe_v17_cursor_mode",
]
