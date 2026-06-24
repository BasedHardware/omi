"""Backward-compatible shim — implementation lives in ``utils.memory.vector_search_telemetry`` (WS-G8a)."""

from utils.memory.vector_search_telemetry import (
    V17VectorSearchTelemetryConfig,
    V17_VECTOR_SEARCH_COMPONENT,
    emit_v17_vector_search_telemetry,
)

__all__ = [
    "V17VectorSearchTelemetryConfig",
    "V17_VECTOR_SEARCH_COMPONENT",
    "emit_v17_vector_search_telemetry",
]
