import uuid
from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from models.memory_evidence import MemoryEvidence, SourceState


class MemoryTier(str, Enum):
    short_term = "short_term"
    long_term = "long_term"
    archive = "archive"


class MemoryItemStatus(str, Enum):
    active = "active"
    superseded = "superseded"
    hidden = "hidden"
    tombstoned = "tombstoned"


class ProcessingState(str, Enum):
    pending = "pending"
    processed = "processed"
    blocked = "blocked"


class V17MemoryItemAlias(BaseModel):
    old_memory_id: str
    canonical_memory_id: str
    uid: str
    reason: str
    created_at: datetime


class V17MemoryItem(BaseModel):
    memory_id: str
    uid: str
    canonical_memory_id: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)
    version: int = 1
    tier: MemoryTier
    status: MemoryItemStatus = MemoryItemStatus.active
    processing_state: ProcessingState = ProcessingState.pending
    content: Optional[str] = None
    evidence: List[MemoryEvidence] = Field(default_factory=list)
    source_state: SourceState = SourceState.active
    sensitivity_labels: List[str] = Field(default_factory=list)
    visibility: str = "private"
    user_asserted: bool = False
    captured_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime] = None
    ledger_commit_id: Optional[str] = None
    ledger_sequence: Optional[int] = None

    @field_validator("memory_id")
    @classmethod
    def validate_memory_id(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("memory_id is required")
        return value

    @field_validator("uid")
    @classmethod
    def validate_uid(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("uid is required")
        return value

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: int) -> int:
        if value < 1:
            raise ValueError("version must be positive")
        return value

    @model_validator(mode="after")
    def validate_tier_invariants(self):
        if self.tier == MemoryTier.short_term and self.status == MemoryItemStatus.active:
            if self.expires_at is None:
                raise ValueError("active short_term memory requires expires_at")
        if self.tier == MemoryTier.long_term and self.status == MemoryItemStatus.active:
            if not self.ledger_commit_id:
                raise ValueError("active long_term memory requires ledger_commit_id")
            if self.ledger_sequence is None:
                raise ValueError("active long_term memory requires ledger_sequence")
        if self.tier == MemoryTier.archive and self.user_asserted:
            raise ValueError("archive memory cannot be user_asserted active memory")
        if self.source_state == SourceState.active and not self.evidence and not self.user_asserted:
            raise ValueError("non-user-asserted active-source memory requires evidence")
        return self


def new_memory_id() -> str:
    return f"mem_{uuid.uuid4().hex}"


def derived_default_access_allowed(item: V17MemoryItem, consumer: str) -> bool:
    if item.status != MemoryItemStatus.active:
        return False
    if item.source_state in {SourceState.tombstoned, SourceState.purged}:
        return False
    if "credential" in item.sensitivity_labels or "secret" in item.sensitivity_labels:
        return False
    if item.tier == MemoryTier.archive:
        return consumer in {"archive_explicit", "admin_debug", "eval"}
    if item.tier in {MemoryTier.short_term, MemoryTier.long_term}:
        return consumer not in {"archive_only"}
    return False
