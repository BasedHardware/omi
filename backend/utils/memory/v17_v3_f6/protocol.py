"""Backward-compatible shim — implementation in ``utils.memory.v3_f6.protocol`` (WS-G8b)."""

from utils.memory.v3_f6.protocol import (
    ARTIFACT_VERSION_F6B,
    ARTIFACT_VERSION_F6F,
    ARTIFACT_VERSION_F6H,
    AggregateDecision,
    ArtifactVersion,
    DECISION_BLOCKED_ON_GCP_ACCESS,
    DECISION_NO_GO,
    EvidenceTargetName,
    GateStatus,
    STATUS_BLOCKED,
    STATUS_BLOCKED_ON_GCP_ACCESS,
    STATUS_MISSING,
    STATUS_PASS,
    STATUS_PRE_GCP_READY,
    TARGET_DEV,
    TARGET_PROD,
)

__all__ = [
    "ARTIFACT_VERSION_F6B",
    "ARTIFACT_VERSION_F6F",
    "ARTIFACT_VERSION_F6H",
    "AggregateDecision",
    "ArtifactVersion",
    "DECISION_BLOCKED_ON_GCP_ACCESS",
    "DECISION_NO_GO",
    "EvidenceTargetName",
    "GateStatus",
    "STATUS_BLOCKED",
    "STATUS_BLOCKED_ON_GCP_ACCESS",
    "STATUS_MISSING",
    "STATUS_PASS",
    "STATUS_PRE_GCP_READY",
    "TARGET_DEV",
    "TARGET_PROD",
]
