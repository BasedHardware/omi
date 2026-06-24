"""Canonical alias module for ``utils.memory.v17_v3_composed_get_service`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from utils.memory.v17_v3_composed_get_service import (
    BuildSnapshot,
    DecideDependency,
    DecodeCursor,
    DependencyStatus,
    EncodeCursor,
    NormalizeRequest,
    NowMs,
    ReadLegacy,
    ReadProjection,
    SnapshotStatus,
    V17V3ComposedAdapters,
    V17V3ComposedCursor,
    V17V3ComposedDependencyDecision,
    V17V3ComposedExecutionContext,
    V17V3ComposedGrant,
    V17V3ComposedProjectionPage,
    V17V3ComposedRequest,
    V17V3ComposedRequestParams,
    V17V3ComposedResponse,
    V17V3ComposedRow,
    V17V3ComposedSnapshotDecision,
    compose_v17_v3_get,
)

__all__ = [
    "BuildSnapshot",
    "DecideDependency",
    "DecodeCursor",
    "DependencyStatus",
    "EncodeCursor",
    "NormalizeRequest",
    "NowMs",
    "ReadLegacy",
    "ReadProjection",
    "SnapshotStatus",
    "V17V3ComposedAdapters",
    "V17V3ComposedCursor",
    "V17V3ComposedDependencyDecision",
    "V17V3ComposedExecutionContext",
    "V17V3ComposedGrant",
    "V17V3ComposedProjectionPage",
    "V17V3ComposedRequest",
    "V17V3ComposedRequestParams",
    "V17V3ComposedResponse",
    "V17V3ComposedRow",
    "V17V3ComposedSnapshotDecision",
    "compose_v17_v3_get",
]
