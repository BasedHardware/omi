"""Backward-compatible shim — implementation in ``utils.memory.v3_f6.protocol`` (WS-G8b)."""

from utils.memory.v3_f6.protocol import (
    AggregateDecision,
    ArtifactVersion,
    EvidenceTargetName,
    GateStatus,
)

__all__ = [
    "AggregateDecision",
    "ArtifactVersion",
    "EvidenceTargetName",
    "GateStatus",
]
