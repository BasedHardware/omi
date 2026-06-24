"""Canonical alias module for ``utils.memory.v17_v3_cursor`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from utils.memory.v17_v3_cursor import (
    V17V3CursorClaims,
    V17V3CursorContext,
    V17V3CursorError,
    V17V3CursorPageRequest,
    V17V3Keyset,
    create_v17_v3_cursor,
    parse_v17_v3_cursor,
    validate_v17_v3_cursor_request,
)

__all__ = [
    "V17V3CursorClaims",
    "V17V3CursorContext",
    "V17V3CursorError",
    "V17V3CursorPageRequest",
    "V17V3Keyset",
    "create_v17_v3_cursor",
    "parse_v17_v3_cursor",
    "validate_v17_v3_cursor_request",
]
