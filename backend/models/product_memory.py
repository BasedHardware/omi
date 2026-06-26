import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from models.memory_evidence import MemoryEvidence, SourceState


class MemoryLayer(str, Enum):
    short_term = "short_term"
    long_term = "long_term"
    archive = "archive"


# Legacy memory name — same enum, kept for backward-compatible imports.
MemoryTier = MemoryLayer


class MemoryItemStatus(str, Enum):
    active = "active"
    superseded = "superseded"
    hidden = "hidden"
    tombstoned = "tombstoned"


class ProcessingState(str, Enum):
    pending = "pending"
    processed = "processed"
    blocked = "blocked"


class MemoryConsumer(str, Enum):
    omi_chat = "omi_chat"
    agent = "agent"
    third_party = "third_party"
    developer_api = "developer_api"
    mcp = "mcp"
    admin_debug = "admin_debug"
    eval = "eval"
    unknown = "unknown"


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    reason: str


@dataclass(frozen=True)
class MemoryAccessPolicy:
    consumer: MemoryConsumer
    app_has_default_memory_grant: bool = False
    archive_capability: bool = False
    raw_provenance_capability: bool = False

    @classmethod
    def for_omi_chat(cls, archive_capability: bool = False) -> "MemoryAccessPolicy":
        return cls(
            consumer=MemoryConsumer.omi_chat, app_has_default_memory_grant=True, archive_capability=archive_capability
        )

    @classmethod
    def for_third_party(
        cls, app_has_default_memory_grant: bool = False, archive_capability: bool = False
    ) -> "MemoryAccessPolicy":
        return cls(
            consumer=MemoryConsumer.third_party,
            app_has_default_memory_grant=app_has_default_memory_grant,
            archive_capability=archive_capability,
        )


class MemoryItemAlias(BaseModel):
    old_memory_id: str
    canonical_memory_id: str
    uid: str
    reason: str
    created_at: datetime

    @model_validator(mode="after")
    def validate_alias(self):
        if self.old_memory_id == self.canonical_memory_id:
            raise ValueError("alias cannot point to self")
        return self


MemoryItemAlias = MemoryItemAlias


class MemoryItem(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    memory_id: str
    uid: str
    canonical_memory_id: Optional[str] = None
    version: int
    tier: MemoryLayer
    status: MemoryItemStatus
    processing_state: ProcessingState
    content: Optional[str]
    evidence: List[MemoryEvidence] = Field(default_factory=list)
    source_state: SourceState
    sensitivity_labels: List[str]
    visibility: str
    user_asserted: bool
    captured_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime] = None
    ledger_commit_id: Optional[str] = None
    ledger_sequence: Optional[int] = None
    item_revision: int = 1
    source_commit_id: Optional[str] = None
    source_commit_sequence: Optional[int] = None
    content_hash: Optional[str] = None
    account_generation: int = 0
    promotion: Optional[Dict[str, Any]] = None
    capture_device_ids: List[str] = Field(default_factory=list)
    primary_capture_device: Optional[str] = None
    corroboration_count: int = 0
    last_corroborated_at: Optional[datetime] = None
    confidence: Optional[float] = None
    superseded_by: Optional[str] = None
    subject_entity_id: Optional[str] = None
    predicate: Optional[str] = None
    arguments: Dict[str, Any] = Field(default_factory=dict)
    kg_extracted: bool = False

    @field_validator("memory_id", "uid", "visibility")
    @classmethod
    def validate_nonblank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("required fields must not be blank")
        return value

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: int) -> int:
        if value < 1:
            raise ValueError("version must be positive")
        return value

    @field_validator("captured_at", "updated_at", "expires_at")
    @classmethod
    def validate_timezone(cls, value: Optional[datetime]) -> Optional[datetime]:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("timestamps must be timezone-aware")
        return value

    @field_validator("sensitivity_labels")
    @classmethod
    def normalize_sensitivity(cls, value: List[str]) -> List[str]:
        return sorted({label.strip().lower() for label in value if label and label.strip()})

    @model_validator(mode="after")
    def validate_tier_invariants(self):
        if self.updated_at < self.captured_at:
            raise ValueError("updated_at must be >= captured_at")
        if self.status == MemoryItemStatus.active and not (self.content or "").strip():
            raise ValueError("active memory requires content")
        if self.tier == MemoryLayer.short_term:
            if self.expires_at is None:
                raise ValueError("short_term memory requires expires_at")
            if self.expires_at <= self.captured_at:
                raise ValueError("short_term expires_at must be after captured_at")
        if self.tier == MemoryLayer.long_term and self.status == MemoryItemStatus.active:
            if not self.ledger_commit_id:
                raise ValueError("active long_term memory requires ledger_commit_id")
            if self.ledger_sequence is None:
                raise ValueError("active long_term memory requires ledger_sequence")
            if self.processing_state != ProcessingState.processed:
                raise ValueError("active long_term memory requires processing_state=processed")
        if self.source_state == SourceState.active and not self.user_asserted:
            if not any(e.source_state == SourceState.active for e in self.evidence):
                raise ValueError("active source memory requires at least one active evidence record")
        return self


MemoryItem = MemoryItem


def new_memory_id() -> str:
    return f"mem_{uuid.uuid4().hex}"


def _base_policy_checks(item: MemoryItem, policy: MemoryAccessPolicy, now: datetime) -> Optional[AccessDecision]:
    if item.status != MemoryItemStatus.active:
        return AccessDecision(False, "not_active")
    if item.processing_state == ProcessingState.blocked:
        return AccessDecision(False, "processing_blocked")
    if item.source_state in {SourceState.tombstoned, SourceState.purged}:
        return AccessDecision(False, "source_not_active")
    if item.tier == MemoryLayer.short_term and item.expires_at and item.expires_at <= now:
        return AccessDecision(False, "short_term_expired")
    if policy.consumer == MemoryConsumer.unknown:
        return AccessDecision(False, "unknown_consumer")
    if _has_restricted_sensitivity(item):
        return AccessDecision(False, "restricted_sensitivity")
    if item.visibility not in {"private", "public", "shared"}:
        return AccessDecision(False, "unknown_visibility")
    return None


def _has_restricted_sensitivity(item: MemoryItem) -> bool:
    restricted = {
        "credential",
        "secret",
        "financial",
        "health",
        "intimate",
        "minor",
        "minors",
        "workplace_confidential",
        "identity_authentication",
    }
    return bool(set(item.sensitivity_labels).intersection(restricted))


def is_default_access_eligible(
    item: MemoryItem, policy: MemoryAccessPolicy, now: Optional[datetime] = None
) -> AccessDecision:
    current_time = now or datetime.now(timezone.utc)
    base = _base_policy_checks(item, policy, current_time)
    if base is not None:
        return base
    if item.tier == MemoryLayer.archive:
        return AccessDecision(False, "archive_requires_explicit_query")
    if policy.consumer in {MemoryConsumer.third_party, MemoryConsumer.developer_api, MemoryConsumer.mcp}:
        if not policy.app_has_default_memory_grant:
            return AccessDecision(False, "missing_default_memory_grant")
    if item.tier in {MemoryLayer.short_term, MemoryLayer.long_term}:
        return AccessDecision(True, "default_memory_allowed")
    return AccessDecision(False, "unsupported_tier")


def is_archive_access_eligible(
    item: MemoryItem, policy: MemoryAccessPolicy, now: Optional[datetime] = None
) -> AccessDecision:
    current_time = now or datetime.now(timezone.utc)
    base = _base_policy_checks(item, policy, current_time)
    if base is not None:
        return base
    if item.tier != MemoryLayer.archive:
        return AccessDecision(False, "not_archive")
    if not policy.archive_capability:
        return AccessDecision(False, "missing_archive_capability")
    return AccessDecision(True, "archive_explicit_allowed")


def derived_default_access_allowed(item: MemoryItem, consumer: str) -> bool:
    try:
        policy = MemoryAccessPolicy(consumer=MemoryConsumer(consumer), app_has_default_memory_grant=True)
    except ValueError:
        policy = MemoryAccessPolicy(consumer=MemoryConsumer.unknown)
    return is_default_access_eligible(item, policy).allowed


__all__ = [
    "AccessDecision",
    "MemoryAccessPolicy",
    "MemoryConsumer",
    "MemoryItem",
    "MemoryItemAlias",
    "MemoryItemStatus",
    "MemoryLayer",
    "MemoryTier",
    "ProcessingState",
    "MemoryItem",
    "MemoryItemAlias",
    "derived_default_access_allowed",
    "is_archive_access_eligible",
    "is_default_access_eligible",
    "new_memory_id",
]
