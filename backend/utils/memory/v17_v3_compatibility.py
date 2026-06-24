"""Backward-compatible shim — implementation lives in ``utils.memory.v3_compatibility`` (WS-G8b)."""

from utils.memory.v3_compatibility import (
    decide_v17_v3_compatibility,
    describe_v17_cursor_mode,
    ENROLLED_FAIL_CLOSED_CONTROL_STATES,
    SUPPORTED_ENROLLED_CONTROL_STATES,
    V17V3CompatibilityContext,
    V17V3CompatibilityDecision,
    V17V3CompatibilityReadPath,
    V17V3CursorMode,
    V3CompatibilityContext,
    V3CompatibilityDecision,
    V3CompatibilityReadPath,
    V3CursorMode,
    _fail_closed,
    _headers,
)

__all__ = [
    "decide_v17_v3_compatibility",
    "describe_v17_cursor_mode",
    "ENROLLED_FAIL_CLOSED_CONTROL_STATES",
    "SUPPORTED_ENROLLED_CONTROL_STATES",
    "V17V3CompatibilityContext",
    "V17V3CompatibilityDecision",
    "V17V3CompatibilityReadPath",
    "V17V3CursorMode",
    "V3CompatibilityContext",
    "V3CompatibilityDecision",
    "V3CompatibilityReadPath",
    "V3CursorMode",
    "_fail_closed",
    "_headers",
]
