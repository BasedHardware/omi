"""Canonical alias module for ``database.v17_vector_repair_outbox_worker`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from database.v17_vector_repair_outbox_worker import (
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
