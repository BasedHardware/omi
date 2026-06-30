"""Serialized protocol tokens for memory-V3-F6 artifacts.

Constants in this module are the canonical spellings emitted to JSON. They are
plain strings so existing artifact JSON types remain unchanged.
"""

from __future__ import annotations

from typing import Final, Literal

ArtifactVersion = Literal["memory-V3-F6B", "memory-V3-F6F", "memory-V3-F6H"]
GateStatus = Literal["PASS", "PRE_GCP_READY", "BLOCKED", "BLOCKED_ON_GCP_ACCESS", "MISSING"]
AggregateDecision = Literal["BLOCKED_ON_GCP_ACCESS", "NO_GO"]
EvidenceTargetName = Literal["dev", "prod"]

ARTIFACT_VERSION_F6B: Final[ArtifactVersion] = "memory-V3-F6B"
ARTIFACT_VERSION_F6F: Final[ArtifactVersion] = "memory-V3-F6F"
ARTIFACT_VERSION_F6H: Final[ArtifactVersion] = "memory-V3-F6H"

STATUS_PASS: Final[GateStatus] = "PASS"
STATUS_PRE_GCP_READY: Final[GateStatus] = "PRE_GCP_READY"
STATUS_BLOCKED: Final[GateStatus] = "BLOCKED"
STATUS_BLOCKED_ON_GCP_ACCESS: Final[GateStatus] = "BLOCKED_ON_GCP_ACCESS"
STATUS_MISSING: Final[GateStatus] = "MISSING"

DECISION_BLOCKED_ON_GCP_ACCESS: Final[AggregateDecision] = "BLOCKED_ON_GCP_ACCESS"
DECISION_NO_GO: Final[AggregateDecision] = "NO_GO"

TARGET_DEV: Final[EvidenceTargetName] = "dev"
TARGET_PROD: Final[EvidenceTargetName] = "prod"
