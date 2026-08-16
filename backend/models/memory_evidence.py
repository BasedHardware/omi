from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class SourceState(str, Enum):
    active = "active"
    missing = "missing"
    tombstoned = "tombstoned"
    purged = "purged"


class SourceStateReason(str, Enum):
    ephemeral_already_missing = "ephemeral_already_missing"
    dropped_before_copy = "dropped_before_copy"
    deleted_by_user = "deleted_by_user"
    account_purged = "account_purged"
    copy_failed = "copy_failed"
    explicit_loss = "explicit_loss"
    not_applicable = "not_applicable"


class ArtifactPreservationState(str, Enum):
    preserved = "preserved"
    ephemeral_already_missing = "ephemeral_already_missing"
    dropped_before_copy = "dropped_before_copy"
    deleted_by_user = "deleted_by_user"
    account_purged = "account_purged"
    copy_failed = "copy_failed"
    explicit_loss = "explicit_loss"
    not_applicable = "not_applicable"


class ProvenanceVisibility(str, Enum):
    visible = "visible"
    redacted = "redacted"
    hidden = "hidden"


class RedactionStatus(str, Enum):
    active = "active"
    redacted = "redacted"
    tombstoned = "tombstoned"
    purged = "purged"


class ArtifactRef(BaseModel):
    artifact_id: Optional[str] = None
    uri: Optional[str] = None
    checksum: Optional[str] = None
    size_bytes: Optional[int] = None
    preservation: ArtifactPreservationState

    @field_validator("artifact_id", "uri", "checksum")
    @classmethod
    def validate_optional_nonblank(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            raise ValueError("artifact fields must not be whitespace")
        return value


class MemoryEvidence(BaseModel):
    evidence_id: str
    source_type: str
    source_id: Optional[str] = None
    source_version: Optional[str] = None
    conversation_id: Optional[str] = None
    artifact_refs: List[ArtifactRef] = Field(default_factory=list)
    artifact_preservation: ArtifactPreservationState
    quote_refs: List[Dict[str, Any]] = Field(default_factory=list[Dict[str, Any]])
    content_hash: Optional[str] = None
    lineage_id: Optional[str] = None
    source_state: SourceState = SourceState.active
    source_state_reason: Optional[SourceStateReason] = None
    provenance_visibility: ProvenanceVisibility = ProvenanceVisibility.visible
    redaction_status: RedactionStatus = RedactionStatus.active
    encryption_or_redaction_status: RedactionStatus = RedactionStatus.active
    patch_id: Optional[str] = None
    commit_id: Optional[str] = None
    client_device_id: Optional[str] = None

    @field_validator("evidence_id", "source_type")
    @classmethod
    def validate_required_nonblank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("required evidence fields must not be whitespace")
        return value

    @field_validator("source_id", "source_version", "conversation_id", "content_hash", "lineage_id")
    @classmethod
    def validate_optional_nonblank(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            raise ValueError("optional evidence fields must not be whitespace")
        return value

    @field_validator("client_device_id")
    @classmethod
    def validate_client_device_id(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            raise ValueError("client_device_id must not be whitespace")
        return value

    @model_validator(mode="after")
    def validate_source_identity(self):
        if self.source_state == SourceState.active:
            if not self.source_id:
                raise ValueError("active evidence requires source_id")
            if not self.source_version:
                raise ValueError("active evidence requires source_version")
        if self.source_state in {SourceState.missing, SourceState.tombstoned, SourceState.purged}:
            if not self.source_state_reason:
                raise ValueError("non-active source evidence requires source_state_reason")
        if (
            self.conversation_id
            and self.source_type == "conversation"
            and self.source_id
            and self.conversation_id != self.source_id
        ):
            raise ValueError("conversation_id must match source_id for conversation evidence")
        if self.artifact_refs:
            for artifact in self.artifact_refs:
                if artifact.preservation != self.artifact_preservation:
                    raise ValueError("artifact_refs preservation must match evidence artifact_preservation")
        return self
