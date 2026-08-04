"""Contracts for the durable legacy-to-canonical memory migration job.

This is deliberately a *job* record, not an item manifest.  A legacy source
can change while canonical processing enriches an item, so a captured list of
canonical revisions is never a safe cutover condition.  The job stores only
opaque source/page digests and canonical operation ids; memory content and
legacy record identifiers stay in their authoritative stores.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import List, Optional
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

MIGRATION_SCHEMA_VERSION = "canonical_memory_migration.v2"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class MigrationState(str, Enum):
    pending = "pending"
    running = "running"
    barrier_pending = "barrier_pending"
    draining = "draining"
    verifying = "verifying"
    soaking = "soaking"
    complete = "complete"
    paused = "paused"
    blocked = "blocked"
    aborted = "aborted"


class MigrationSurface(str, Enum):
    canonical = "canonical"
    graph = "graph"
    projection = "projection"
    outbox = "outbox"


class MigrationBlockCode(str, Enum):
    # Shared by graph enrichment; retained as validation outcome codes rather
    # than as item-manifest migration state.
    missing_required_processing_receipt = "missing_required_processing_receipt"
    restricted_item = "restricted_item"
    review_rejected = "review_rejected"
    stale_fence = "stale_fence"
    source_changed = "source_changed"
    source_unavailable = "source_unavailable"
    lease_lost = "lease_lost"
    surface_not_converged = "surface_not_converged"
    cutover_not_authorized = "cutover_not_authorized"
    verification_failed = "verification_failed"


class MigrationClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner_instance_id: str
    claim_epoch: int
    claim_id: str
    expires_at: AwareDatetime
    renewed_at: AwareDatetime

    @field_validator("owner_instance_id", "claim_id")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("claim identifiers must not be blank")
        return value.strip()

    @field_validator("claim_epoch")
    @classmethod
    def positive_epoch(cls, value: int) -> int:
        if value < 1:
            raise ValueError("claim epoch must be positive")
        return value

    def expired(self, now: Optional[datetime] = None) -> bool:
        return self.expires_at <= (now or _now())

    def renew(self, *, ttl_seconds: float) -> "MigrationClaim":
        if ttl_seconds <= 0:
            raise ValueError("claim ttl must be positive")
        now = _now()
        return self.model_copy(update={"renewed_at": now, "expires_at": now + timedelta(seconds=ttl_seconds)})


class MigrationPageReceipt(BaseModel):
    """Immutable receipt for one source page; no raw source ids or content."""

    model_config = ConfigDict(extra="forbid")

    page_id: str
    source_cursor: str
    source_digest: str
    operation_ids: List[str] = Field(default_factory=list)
    terminal_outcome_count: int = 0
    created_at: AwareDatetime = Field(default_factory=_now)

    @field_validator("page_id", "source_cursor", "source_digest")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("page receipt fields must not be blank")
        return value.strip()


class MigrationVerificationCertificate(BaseModel):
    """Verifier-issued convergence proof, bound to exactly one migration job.

    This is deliberately more than a report saying that a few collections look
    healthy.  The persistence layer rejects a certificate unless every identity
    and version fence below agrees with the claimed job and the live cutover
    documents.  A production verifier must also authenticate the certificate
    before it is attached (see ``MigrationCertificateVerifier``).
    """

    model_config = ConfigDict(extra="forbid")

    uid: str
    job_id: str
    account_generation: int
    source_generation: int
    transform_version: str
    policy_version: str
    source_adapter_version: str
    projection_rebuild_id: str
    verifier_id: str
    verification_run_id: str
    signature: str
    canonical_head_commit_id: str
    canonical_head_sequence: int
    source_snapshot_token: str
    source_digest: str
    required_surfaces: List[MigrationSurface]
    converged_surfaces: List[MigrationSurface]
    mismatch_count: int = 0
    verified_at: AwareDatetime = Field(default_factory=_now)

    @field_validator(
        "uid",
        "job_id",
        "transform_version",
        "policy_version",
        "source_adapter_version",
        "projection_rebuild_id",
        "verifier_id",
        "verification_run_id",
        "signature",
        "canonical_head_commit_id",
        "source_snapshot_token",
        "source_digest",
    )
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("certificate fence fields must not be blank")
        return value.strip()

    @model_validator(mode="after")
    def exact_convergence(self) -> "MigrationVerificationCertificate":
        if (
            self.canonical_head_sequence < 0
            or self.account_generation < 0
            or self.source_generation < 0
            or self.mismatch_count < 0
        ):
            raise ValueError("certificate counters must be nonnegative")
        if self.mismatch_count:
            raise ValueError("a cutover certificate cannot contain mismatches")
        if set(self.required_surfaces) != set(self.converged_surfaces):
            raise ValueError("certificate requires every requested surface to converge")
        return self


class CanonicalMigrationJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = MIGRATION_SCHEMA_VERSION
    uid: str
    job_id: str
    migration_type: str = "legacy_to_canonical"
    transform_version: str
    policy_version: str
    source_adapter_version: str
    required_surfaces: List[MigrationSurface]
    account_generation: int
    source_generation: int
    state: MigrationState = MigrationState.pending
    version: int = 0
    claim: Optional[MigrationClaim] = None
    source_snapshot_token: Optional[str] = None
    source_digest: Optional[str] = None
    barrier_operation_id: Optional[str] = None
    certificate: Optional[MigrationVerificationCertificate] = None
    cutover_head_commit_id: Optional[str] = None
    created_at: AwareDatetime = Field(default_factory=_now)
    updated_at: AwareDatetime = Field(default_factory=_now)

    @field_validator("uid", "job_id", "transform_version", "policy_version", "source_adapter_version")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("migration job identity/version must not be blank")
        return value.strip()

    @field_validator("account_generation", "source_generation", "version")
    @classmethod
    def nonnegative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("migration counters must be nonnegative")
        return value

    @model_validator(mode="after")
    def state_requirements(self) -> "CanonicalMigrationJob":
        if self.state == MigrationState.complete and (self.certificate is None or not self.cutover_head_commit_id):
            raise ValueError("complete migration requires certificate and cutover head")
        if self.cutover_head_commit_id and self.certificate is None:
            raise ValueError("cutover requires a verification certificate")
        return self

    def certificate_matches(self, certificate: MigrationVerificationCertificate) -> bool:
        """Whether a verifier result is for this immutable migration identity."""
        return (
            certificate.uid == self.uid
            and certificate.job_id == self.job_id
            and certificate.account_generation == self.account_generation
            and certificate.source_generation == self.source_generation
            and certificate.transform_version == self.transform_version
            and certificate.policy_version == self.policy_version
            and certificate.source_adapter_version == self.source_adapter_version
            and certificate.source_snapshot_token == self.source_snapshot_token
            and certificate.source_digest == self.source_digest
            and set(certificate.required_surfaces) == set(self.required_surfaces)
        )

    @classmethod
    def new(
        cls,
        *,
        uid: str,
        transform_version: str,
        policy_version: str,
        source_adapter_version: str,
        account_generation: int,
        source_generation: int,
        required_surfaces: List[MigrationSurface],
        job_id: Optional[str] = None,
    ) -> "CanonicalMigrationJob":
        return cls(
            uid=uid,
            job_id=job_id or f"mmj_{uuid4().hex}",
            transform_version=transform_version,
            policy_version=policy_version,
            source_adapter_version=source_adapter_version,
            account_generation=account_generation,
            source_generation=source_generation,
            required_surfaces=required_surfaces,
        )


__all__ = [
    "CanonicalMigrationJob",
    "MigrationBlockCode",
    "MigrationClaim",
    "MigrationPageReceipt",
    "MigrationState",
    "MigrationSurface",
    "MigrationVerificationCertificate",
    "MIGRATION_SCHEMA_VERSION",
]
