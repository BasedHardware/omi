"""Canonical alias module for ``utils.memory.v17_vector_search_telemetry`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from utils.memory.v17_vector_search_telemetry import (
    V17VectorSearchTelemetryConfig,
    V17_VECTOR_SEARCH_COMPONENT,
    emit_v17_vector_search_telemetry,
)

__all__ = [
    "V17VectorSearchTelemetryConfig",
    "V17_VECTOR_SEARCH_COMPONENT",
    "emit_v17_vector_search_telemetry",
]
