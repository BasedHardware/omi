"""Canonical alias module for ``database.v17_vector_repair_outbox_telemetry`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from database.v17_vector_repair_outbox_telemetry import (
    V17VectorRepairOutboxTelemetryConfig,
    V17_VECTOR_REPAIR_OUTBOX_WORKER_COMPONENT,
    emit_v17_vector_repair_outbox_worker_telemetry,
)

__all__ = [
    "V17VectorRepairOutboxTelemetryConfig",
    "V17_VECTOR_REPAIR_OUTBOX_WORKER_COMPONENT",
    "emit_v17_vector_repair_outbox_worker_telemetry",
]
