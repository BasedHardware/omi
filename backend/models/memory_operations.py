"""Canonical alias module for ``models.v17_memory_operations`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from models.v17_memory_operations import (
    MemoryOperation,
    MemoryOperationStatus,
    MemoryOperationType,
    OperationLogicalPayload,
    build_operation_id,
    logical_payload_digest,
)

__all__ = [
    "MemoryOperation",
    "MemoryOperationStatus",
    "MemoryOperationType",
    "OperationLogicalPayload",
    "build_operation_id",
    "logical_payload_digest",
]
