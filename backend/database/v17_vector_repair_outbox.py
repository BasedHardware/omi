"""Backward-compatible shim — implementation lives in ``database.memory_vector_repair_outbox`` (WS-G7)."""

from database.memory_vector_repair_outbox import (
    V17_VECTOR_REPAIR_PURGE_OUTBOX_EVENT_TYPE,
    V17_VECTOR_REPAIR_PURGE_OUTBOX_SCHEMA_VERSION,
    build_v17_vector_repair_purge_outbox_records,
    write_v17_vector_repair_purge_outbox_records,
)

__all__ = [
    "V17_VECTOR_REPAIR_PURGE_OUTBOX_EVENT_TYPE",
    "V17_VECTOR_REPAIR_PURGE_OUTBOX_SCHEMA_VERSION",
    "build_v17_vector_repair_purge_outbox_records",
    "write_v17_vector_repair_purge_outbox_records",
]
