"""Canonical alias module for ``utils.memory.v17_v3_request_adapter`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from utils.memory.v17_v3_request_adapter import (
    LEGACY_FIRST_PAGE_LIMIT_OVERRIDE,
    LEGACY_V3_MAX_LIMIT,
    LEGACY_V3_READ_MODE,
    LEGACY_V3_READ_SOURCE,
    V17V3AdaptedRequest,
    V17V3RequestAdapterError,
    V17_V3_DEFAULT_LIMIT,
    V17_V3_MAX_LIMIT,
    adapt_v17_v3_request_parameters,
)

__all__ = [
    "LEGACY_FIRST_PAGE_LIMIT_OVERRIDE",
    "LEGACY_V3_MAX_LIMIT",
    "LEGACY_V3_READ_MODE",
    "LEGACY_V3_READ_SOURCE",
    "V17V3AdaptedRequest",
    "V17V3RequestAdapterError",
    "V17_V3_DEFAULT_LIMIT",
    "V17_V3_MAX_LIMIT",
    "adapt_v17_v3_request_parameters",
]
