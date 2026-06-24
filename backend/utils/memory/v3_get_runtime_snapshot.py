"""Canonical alias module for ``utils.memory.v17_v3_get_runtime_snapshot`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from utils.memory.v17_v3_get_runtime_snapshot import (
    LOW_CARDINALITY_RUNTIME_SNAPSHOT_REASONS,
    SnapshotStatus,
    V17V3GetRuntimeSnapshot,
    V17V3GetRuntimeSnapshotInput,
    V17V3GetRuntimeSnapshotResult,
    build_v17_v3_get_runtime_snapshot,
)

__all__ = [
    "LOW_CARDINALITY_RUNTIME_SNAPSHOT_REASONS",
    "SnapshotStatus",
    "V17V3GetRuntimeSnapshot",
    "V17V3GetRuntimeSnapshotInput",
    "V17V3GetRuntimeSnapshotResult",
    "build_v17_v3_get_runtime_snapshot",
]
