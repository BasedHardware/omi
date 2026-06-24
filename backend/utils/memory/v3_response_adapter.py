"""Canonical alias module for ``utils.memory.v17_v3_response_adapter`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from utils.memory.v17_v3_response_adapter import (
    V17V3MemoryResponse,
    V17V3ResponseShapeError,
    adapt_v17_v3_memory_response,
)

__all__ = [
    "V17V3MemoryResponse",
    "V17V3ResponseShapeError",
    "adapt_v17_v3_memory_response",
]
