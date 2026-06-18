from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class SourceState(str, Enum):
    active = "active"
    missing = "missing"
    tombstoned = "tombstoned"
    purged = "purged"


class ProvenanceVisibility(str, Enum):
    visible = "visible"
    redacted = "redacted"
    hidden = "hidden"


class RedactionStatus(str, Enum):
    active = "active"
    redacted = "redacted"
    tombstoned = "tombstoned"
    purged = "purged"


class MemoryEvidence(BaseModel):
    evidence_id: str
    source_type: str
    source_id: Optional[str] = None
    source_version: Optional[str] = None
    conversation_id: Optional[str] = None
    artifact_refs: List[Dict[str, Any]] = Field(default_factory=list)
    quote_refs: List[Dict[str, Any]] = Field(default_factory=list)
    content_hash: Optional[str] = None
    lineage_id: Optional[str] = None
    source_state: SourceState = SourceState.active
    provenance_visibility: ProvenanceVisibility = ProvenanceVisibility.visible
    redaction_status: RedactionStatus = RedactionStatus.active
    encryption_or_redaction_status: Optional[str] = None
    missing_source_reason: Optional[str] = None
    patch_id: Optional[str] = None
    commit_id: Optional[str] = None

    @model_validator(mode="after")
    def validate_source_identity(self):
        if self.source_state == SourceState.active:
            if not self.source_id:
                raise ValueError("active evidence requires source_id")
            if not self.source_version:
                raise ValueError("active evidence requires source_version")
        if self.source_state in {SourceState.missing, SourceState.tombstoned, SourceState.purged}:
            if not self.missing_source_reason and not self.source_id:
                raise ValueError("non-active source evidence requires source_id or missing_source_reason")
        return self
