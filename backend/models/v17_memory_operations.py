"""Backward-compatible shim — canonical definitions live in ``models.memory_operations`` (WS-G G6)."""

from models.memory_operations import (
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
