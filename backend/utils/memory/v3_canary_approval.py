"""Canonical alias module for ``utils.memory.v17_v3_canary_approval`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from utils.memory.v17_v3_canary_approval import (
    APPROVAL_STATUSES,
    CANARY_COHORTS,
    ROUTE_SCOPE,
    SCHEMA_VERSION,
    V17V3CanaryApprovalArtifact,
    V17V3CanaryApprovalArtifactReader,
    V17V3CanaryApprovalDecision,
    build_v17_v3_canary_approval_telemetry_labels,
    read_v17_v3_canary_approval_artifact_decision,
    validate_v17_v3_canary_approval_artifact,
)

__all__ = [
    "APPROVAL_STATUSES",
    "CANARY_COHORTS",
    "ROUTE_SCOPE",
    "SCHEMA_VERSION",
    "V17V3CanaryApprovalArtifact",
    "V17V3CanaryApprovalArtifactReader",
    "V17V3CanaryApprovalDecision",
    "build_v17_v3_canary_approval_telemetry_labels",
    "read_v17_v3_canary_approval_artifact_decision",
    "validate_v17_v3_canary_approval_artifact",
]
