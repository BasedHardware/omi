"""Backward-compatible shim — implementation lives in ``database.memory_vector_repair_outbox_telemetry`` (WS-G7)."""

from database.memory_vector_repair_outbox_telemetry import (
    V17VectorRepairOutboxTelemetryConfig,
    V17_VECTOR_REPAIR_OUTBOX_WORKER_COMPONENT,
    emit_v17_vector_repair_outbox_worker_telemetry,
)

__all__ = [
    "V17VectorRepairOutboxTelemetryConfig",
    "V17_VECTOR_REPAIR_OUTBOX_WORKER_COMPONENT",
    "emit_v17_vector_repair_outbox_worker_telemetry",
]
