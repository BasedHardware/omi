"""Backward-compatible shim — implementation lives in ``database.memory_vector_repair_outbox_worker`` (WS-G7)."""

from database.memory_vector_repair_outbox_worker import (
    V17VectorRepairOutboxWorkerTickConfig,
    V17_VECTOR_REPAIR_OUTBOX_COMPLETED_STATUS,
    V17_VECTOR_REPAIR_OUTBOX_DEAD_LETTER_STATUS,
    V17_VECTOR_REPAIR_OUTBOX_IN_PROGRESS_STATUS,
    V17_VECTOR_REPAIR_OUTBOX_PENDING_STATUS,
    V17_VECTOR_REPAIR_PURGE_EVENT_TYPE,
    ack_v17_vector_repair_purge_outbox_record,
    lease_v17_vector_repair_purge_outbox_records,
    process_v17_vector_repair_purge_outbox_records,
    run_v17_vector_repair_outbox_worker_tick,
)

__all__ = [
    "V17VectorRepairOutboxWorkerTickConfig",
    "V17_VECTOR_REPAIR_OUTBOX_COMPLETED_STATUS",
    "V17_VECTOR_REPAIR_OUTBOX_DEAD_LETTER_STATUS",
    "V17_VECTOR_REPAIR_OUTBOX_IN_PROGRESS_STATUS",
    "V17_VECTOR_REPAIR_OUTBOX_PENDING_STATUS",
    "V17_VECTOR_REPAIR_PURGE_EVENT_TYPE",
    "ack_v17_vector_repair_purge_outbox_record",
    "lease_v17_vector_repair_purge_outbox_records",
    "process_v17_vector_repair_purge_outbox_records",
    "run_v17_vector_repair_outbox_worker_tick",
]
