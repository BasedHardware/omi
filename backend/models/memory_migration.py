"""Durable per-user canonical-memory migration contracts.

The migration controller is deliberately a small state machine.  It stores
only server-authored identifiers, fences, manifests, and work metadata; raw
memory content remains owned by the canonical memory stores and apply path.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from models.memory_contracts import deterministic_contract_id

MIGRATION_SCHEMA_VERSION = "canonical_memory_migration.v1"
MIGRATION_MANIFEST_SCHEMA_VERSION = "canonical_memory_migration_manifest.v1"
MIGRATION_WORK_SCHEMA_VERSION = "canonical_memory_migration_work.v1"
MIGRATION_LEASE_SCHEMA_VERSION = "canonical_memory_migration_lease.v1"


class MigrationPhase(str, Enum):
    inventoried = "inventoried"
    write_enrolled = "write_enrolled"
    staged = "staged"
    canonical_processing = "canonical_processing"
    graph_enrichment = "graph_enrichment"
    projection_convergence = "projection_convergence"
    verified = "verified"
    read_cutover = "read_cutover"
    failed = "failed"
    paused = "paused"


# A failed/paused run may only resume at the phase recorded in resume_phase.
# It may never skip a postcondition-bearing phase.
_PHASE_TRANSITIONS: Dict[MigrationPhase, frozenset[MigrationPhase]] = {
    MigrationPhase.inventoried: frozenset(
        {MigrationPhase.write_enrolled, MigrationPhase.failed, MigrationPhase.paused}
    ),
    MigrationPhase.write_enrolled: frozenset({MigrationPhase.staged, MigrationPhase.failed, MigrationPhase.paused}),
    MigrationPhase.staged: frozenset(
        {MigrationPhase.canonical_processing, MigrationPhase.failed, MigrationPhase.paused}
    ),
    MigrationPhase.canonical_processing: frozenset(
        {MigrationPhase.graph_enrichment, MigrationPhase.failed, MigrationPhase.paused}
    ),
    MigrationPhase.graph_enrichment: frozenset(
        {MigrationPhase.projection_convergence, MigrationPhase.failed, MigrationPhase.paused}
    ),
    MigrationPhase.projection_convergence: frozenset(
        {MigrationPhase.verified, MigrationPhase.failed, MigrationPhase.paused}
    ),
    MigrationPhase.verified: frozenset({MigrationPhase.read_cutover, MigrationPhase.failed, MigrationPhase.paused}),
    MigrationPhase.read_cutover: frozenset(),
    MigrationPhase.failed: frozenset(),
    MigrationPhase.paused: frozenset(),
}


class MigrationTransitionError(ValueError):
    """Raised when a checkpoint tries to skip or regress a migration phase."""


def validate_migration_transition(current: MigrationPhase, target: MigrationPhase) -> None:
    """Validate one durable transition; idempotent writes are allowed."""
    if current == target:
        return
    if target not in _PHASE_TRANSITIONS[current]:
        raise MigrationTransitionError(f"invalid canonical migration transition: {current.value} -> {target.value}")


class MigrationBlockCode(str, Enum):
    missing_required_processing_receipt = "missing_required_processing_receipt"
    malformed_required_processing_receipt = "malformed_required_processing_receipt"
    restricted_item = "restricted_item"
    review_rejected = "review_rejected"
    stale_fence = "stale_fence"
    graph_plan_invalid = "graph_plan_invalid"
    projection_not_converged = "projection_not_converged"
    outbox_not_drained = "outbox_not_drained"
    inventory_unstable = "inventory_unstable"
    lease_lost = "lease_lost"
    verification_failed = "verification_failed"


class MigrationBlockingState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: MigrationBlockCode
    message: str
    item_id: Optional[str] = None
    retryable: bool = False
    details: Dict[str, Any] = Field(default_factory=dict)
    occurred_at: AwareDatetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("blocking state message must not be blank")
        return value.strip()


class MigrationFence(BaseModel):
    """Identity fence shared by every phase and every work record."""

    account_generation: int
    source_generation: int
    inventory_id: str
    inventory_fingerprint: str
    observed_head_commit_id: str
    observed_head_sequence: int = 0

    @field_validator("account_generation", "source_generation", "observed_head_sequence")
    @classmethod
    def validate_nonnegative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("migration fence counters must be nonnegative")
        return value

    @field_validator("inventory_id", "inventory_fingerprint", "observed_head_commit_id")
    @classmethod
    def validate_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("migration fence identifiers must not be blank")
        return value.strip()


class MigrationLease(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = MIGRATION_LEASE_SCHEMA_VERSION
    uid: str
    owner_id: str
    ownership_epoch: int
    expires_at: AwareDatetime
    renewed_at: AwareDatetime

    @field_validator("uid", "owner_id")
    @classmethod
    def validate_identity(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("migration lease identity must not be blank")
        return value.strip()

    @field_validator("ownership_epoch")
    @classmethod
    def validate_epoch(cls, value: int) -> int:
        if value < 1:
            raise ValueError("ownership_epoch must be positive")
        return value

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        current = now or datetime.now(timezone.utc)
        return self.expires_at <= current

    def renewed(self, *, owner_id: str, ownership_epoch: int, ttl_seconds: float) -> "MigrationLease":
        if owner_id != self.owner_id or ownership_epoch != self.ownership_epoch:
            raise ValueError("migration lease ownership epoch mismatch")
        if ttl_seconds <= 0:
            raise ValueError("lease ttl must be positive")
        now = datetime.now(timezone.utc)
        return self.model_copy(update={"renewed_at": now, "expires_at": now + timedelta(seconds=ttl_seconds)})


class CanonicalMigrationCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = MIGRATION_SCHEMA_VERSION
    uid: str
    phase: MigrationPhase = MigrationPhase.inventoried
    version: int = 0
    fence: MigrationFence
    lease: Optional[MigrationLease] = None
    resume_phase: Optional[MigrationPhase] = None
    manifest_id: Optional[str] = None
    blocking: Optional[MigrationBlockingState] = None
    verified_at: Optional[AwareDatetime] = None
    updated_at: AwareDatetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("uid")
    @classmethod
    def validate_uid(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("migration uid must not be blank")
        return value.strip()

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: int) -> int:
        if value < 0:
            raise ValueError("checkpoint version must be nonnegative")
        return value

    @model_validator(mode="after")
    def validate_phase_data(self) -> "CanonicalMigrationCheckpoint":
        if self.phase in {MigrationPhase.failed, MigrationPhase.paused} and self.resume_phase is None:
            raise ValueError("failed/paused checkpoints require resume_phase")
        if self.phase not in {MigrationPhase.failed, MigrationPhase.paused} and self.resume_phase is not None:
            raise ValueError("resume_phase is only valid for failed/paused checkpoints")
        if self.phase in {MigrationPhase.verified, MigrationPhase.read_cutover} and self.verified_at is None:
            raise ValueError("verified/read_cutover checkpoints require verified_at")
        return self

    def transition(
        self,
        target: MigrationPhase,
        *,
        blocking: Optional[MigrationBlockingState] = None,
        lease: Optional[MigrationLease] = None,
        manifest_id: Optional[str] = None,
        verified_at: Optional[datetime] = None,
        resume_phase: Optional[MigrationPhase] = None,
    ) -> "CanonicalMigrationCheckpoint":
        if target in {MigrationPhase.failed, MigrationPhase.paused}:
            if self.phase == MigrationPhase.read_cutover:
                raise MigrationTransitionError("read_cutover is terminal and cannot be paused or failed")
            resume = resume_phase or (
                self.phase if self.phase not in {MigrationPhase.failed, MigrationPhase.paused} else self.resume_phase
            )
            if resume is None:
                raise MigrationTransitionError("failed/paused transition has no resumable phase")
            return self.model_copy(
                update={
                    "phase": target,
                    "resume_phase": resume,
                    "blocking": blocking,
                    "lease": lease if lease is not None else self.lease,
                    "manifest_id": manifest_id or self.manifest_id,
                    "updated_at": datetime.now(timezone.utc),
                }
            )
        if self.phase in {MigrationPhase.failed, MigrationPhase.paused}:
            if self.resume_phase != target:
                raise MigrationTransitionError(
                    f"resume target must match recorded phase: {self.resume_phase} -> {target.value}"
                )
        else:
            validate_migration_transition(self.phase, target)
        if target == MigrationPhase.read_cutover and self.verified_at is None:
            raise MigrationTransitionError("read_cutover requires a verified_at timestamp")
        return self.model_copy(
            update={
                "phase": target,
                "resume_phase": None,
                "blocking": blocking,
                "lease": lease if lease is not None else self.lease,
                "manifest_id": manifest_id or self.manifest_id,
                "verified_at": (
                    (verified_at or datetime.now(timezone.utc))
                    if target == MigrationPhase.verified
                    else self.verified_at
                ),
                "updated_at": datetime.now(timezone.utc),
            }
        )


class MigrationInventory(BaseModel):
    """Stable inventory snapshot used to build a resumable manifest."""

    schema_version: str = "canonical_memory_migration_inventory.v1"
    uid: str
    inventory_id: str
    fingerprint: str
    account_generation: int
    source_generation: int
    head_commit_id: str
    head_sequence: int = 0
    item_ids: List[str] = Field(default_factory=list)
    item_revisions: Dict[str, int] = Field(default_factory=dict)
    item_content_hashes: Dict[str, str] = Field(default_factory=dict)
    item_evidence_ids: Dict[str, List[str]] = Field(default_factory=dict)
    stable: bool = False
    bounded_delta: bool = False
    captured_at: AwareDatetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("uid", "inventory_id", "fingerprint", "head_commit_id")
    @classmethod
    def validate_required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("inventory identifiers must not be blank")
        return value.strip()

    @field_validator("item_ids")
    @classmethod
    def normalize_item_ids(cls, value: List[str]) -> List[str]:
        return sorted({item.strip() for item in value if item and item.strip()})

    @model_validator(mode="after")
    def validate_item_fences(self) -> "MigrationInventory":
        item_ids = set(self.item_ids)
        if set(self.item_revisions) != item_ids:
            raise ValueError("inventory item_revisions must represent every and only item_ids")
        if set(self.item_content_hashes) != item_ids:
            raise ValueError("inventory item_content_hashes must represent every and only item_ids")
        if set(self.item_evidence_ids) != item_ids:
            raise ValueError("inventory item_evidence_ids must represent every and only item_ids")
        for item_id in self.item_ids:
            revision = self.item_revisions[item_id]
            if revision < 1:
                raise ValueError(f"inventory item revision must be positive: {item_id}")
            content_hash = self.item_content_hashes[item_id]
            if not content_hash.strip():
                raise ValueError(f"inventory content hash must be nonblank: {item_id}")
            evidence = self.item_evidence_ids[item_id]
            if not evidence or any(not value.strip() for value in evidence):
                raise ValueError(f"inventory item requires nonblank evidence ids: {item_id}")
            if len(set(evidence)) != len(evidence):
                raise ValueError(f"inventory item evidence ids must be unique: {item_id}")
        return self


class CanonicalMigrationManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = MIGRATION_MANIFEST_SCHEMA_VERSION
    manifest_id: str
    uid: str
    fence: MigrationFence
    item_ids: List[str] = Field(default_factory=list)
    item_revisions: Dict[str, int] = Field(default_factory=dict)
    item_content_hashes: Dict[str, str] = Field(default_factory=dict)
    item_evidence_ids: Dict[str, List[str]] = Field(default_factory=dict)
    stable_inventory: bool = False
    bounded_delta: bool = False
    created_at: AwareDatetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("item_ids")
    @classmethod
    def normalize_manifest_item_ids(cls, value: List[str]) -> List[str]:
        return sorted({item.strip() for item in value if item and item.strip()})

    @model_validator(mode="after")
    def validate_item_fences(self) -> "CanonicalMigrationManifest":
        item_ids = set(self.item_ids)
        if set(self.item_revisions) != item_ids:
            raise ValueError("manifest item_revisions must represent every and only item_ids")
        if set(self.item_content_hashes) != item_ids:
            raise ValueError("manifest item_content_hashes must represent every and only item_ids")
        if set(self.item_evidence_ids) != item_ids:
            raise ValueError("manifest item_evidence_ids must represent every and only item_ids")
        for item_id in self.item_ids:
            if self.item_revisions[item_id] < 1:
                raise ValueError(f"manifest item revision must be positive: {item_id}")
            if not self.item_content_hashes[item_id].strip():
                raise ValueError(f"manifest content hash must be nonblank: {item_id}")
            evidence = self.item_evidence_ids[item_id]
            if not evidence or any(not value.strip() for value in evidence):
                raise ValueError(f"manifest item requires evidence ids: {item_id}")
            if len(set(evidence)) != len(evidence):
                raise ValueError(f"manifest item evidence ids must be unique: {item_id}")
        return self

    @classmethod
    def from_inventory(cls, inventory: MigrationInventory) -> "CanonicalMigrationManifest":
        fence = MigrationFence(
            account_generation=inventory.account_generation,
            source_generation=inventory.source_generation,
            inventory_id=inventory.inventory_id,
            inventory_fingerprint=inventory.fingerprint,
            observed_head_commit_id=inventory.head_commit_id,
            observed_head_sequence=inventory.head_sequence,
        )
        manifest_id = (
            "mmf_"
            + deterministic_contract_id(
                "canonical-memory-migration-manifest",
                {
                    "uid": inventory.uid,
                    "fence": fence.model_dump(mode="json"),
                    "item_ids": inventory.item_ids,
                    "item_revisions": inventory.item_revisions,
                    "item_content_hashes": inventory.item_content_hashes,
                    "item_evidence_ids": inventory.item_evidence_ids,
                },
            )[:32]
        )
        return cls(
            manifest_id=manifest_id,
            uid=inventory.uid,
            fence=fence,
            item_ids=inventory.item_ids,
            item_revisions=dict(inventory.item_revisions),
            item_content_hashes=dict(inventory.item_content_hashes),
            item_evidence_ids={key: list(value) for key, value in inventory.item_evidence_ids.items()},
            stable_inventory=inventory.stable,
            bounded_delta=inventory.bounded_delta,
        )


class MigrationWorkStatus(str, Enum):
    pending = "pending"
    planned = "planned"
    applying = "applying"
    applied = "applied"
    blocked = "blocked"
    failed = "failed"


class CanonicalMigrationWorkRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = MIGRATION_WORK_SCHEMA_VERSION
    uid: str
    manifest_id: str
    item_id: str
    status: MigrationWorkStatus = MigrationWorkStatus.pending
    item_revision: int
    content_hash: str
    evidence_ids: List[str] = Field(default_factory=list)
    account_generation: int
    source_generation: int
    plan: Optional[Dict[str, Any]] = None
    receipt: Optional[Dict[str, Any]] = None
    operation_id: Optional[str] = None
    blocking: Optional[MigrationBlockingState] = None
    attempt_count: int = 0
    updated_at: AwareDatetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("uid", "manifest_id", "item_id", "content_hash")
    @classmethod
    def validate_required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("migration work identity must not be blank")
        return value.strip()

    @field_validator("item_revision", "account_generation", "source_generation", "attempt_count")
    @classmethod
    def validate_counters(cls, value: int) -> int:
        if value < 0:
            raise ValueError("migration work counters must be nonnegative")
        return value

    @field_validator("item_revision")
    @classmethod
    def validate_item_revision(cls, value: int) -> int:
        if value < 1:
            raise ValueError("migration work item_revision must be positive")
        return value

    @field_validator("evidence_ids")
    @classmethod
    def normalize_evidence_ids(cls, value: List[str]) -> List[str]:
        normalized = sorted({item.strip() for item in value if item and item.strip()})
        if not normalized:
            raise ValueError("migration work record requires evidence ids")
        if len(normalized) != len(value):
            raise ValueError("migration work evidence ids must be unique and nonblank")
        return normalized


__all__ = [
    "CanonicalMigrationCheckpoint",
    "CanonicalMigrationManifest",
    "CanonicalMigrationWorkRecord",
    "MigrationBlockCode",
    "MigrationBlockingState",
    "MigrationFence",
    "MigrationInventory",
    "MigrationLease",
    "MigrationPhase",
    "MigrationTransitionError",
    "MigrationWorkStatus",
    "MIGRATION_SCHEMA_VERSION",
    "validate_migration_transition",
]
