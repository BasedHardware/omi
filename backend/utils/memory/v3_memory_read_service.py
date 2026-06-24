"""Canonical alias module for ``utils.memory.v17_v3_memory_read_service`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from utils.memory.v17_v3_memory_read_service import (
    V17V3MemoryReadRequest,
    V17V3MemoryReadServiceInput,
    V17V3MemoryReadServiceResult,
    V17_V3_READ_MODE,
    V17_V3_READ_SOURCE,
    plan_v17_v3_memory_read,
)

__all__ = [
    "V17V3MemoryReadRequest",
    "V17V3MemoryReadServiceInput",
    "V17V3MemoryReadServiceResult",
    "V17_V3_READ_MODE",
    "V17_V3_READ_SOURCE",
    "plan_v17_v3_memory_read",
]
