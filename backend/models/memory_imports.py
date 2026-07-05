from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class MemoryImportRunStatus(str, Enum):
    received = "received"
    extracting = "extracting"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class MemoryImportArtifactSourceState(str, Enum):
    active = "active"
    tombstoned = "tombstoned"
    purged = "purged"


class MemoryImportBatchItem(BaseModel):
    external_id: Optional[str] = None
    occurred_at: Optional[datetime] = None
    title: Optional[str] = None
    snippet: Optional[str] = None
    content: Optional[str] = None
    content_hash: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    client_device_id: Optional[str] = None

    @field_validator("external_id", "title", "snippet", "content", "content_hash", "client_device_id")
    @classmethod
    def normalize_optional_string(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def require_identity_or_content(self):
        if not self.external_id and not self.content_hash and not (self.content or self.snippet or self.title):
            raise ValueError("import artifact requires external_id, content_hash, or textual content")
        return self


class MemoryImportBatchRequest(BaseModel):
    source_type: str
    import_run_id: Optional[str] = None
    source_account_hash: Optional[str] = None
    importer_version: str = "v1"
    extractor_version: Optional[str] = None
    items: List[MemoryImportBatchItem] = Field(default_factory=list, max_length=100)

    @field_validator("source_type", "import_run_id", "source_account_hash", "importer_version", "extractor_version")
    @classmethod
    def normalize_source_string(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def require_source_type(self):
        if not self.source_type:
            raise ValueError("source_type is required")
        return self


class MemoryImportBatchResponse(BaseModel):
    run_id: str
    artifacts_received: int
    artifacts_created: int
    artifacts_deduped: int
    candidates_created: int = 0
    status: MemoryImportRunStatus = MemoryImportRunStatus.received


class MemoryImportRun(BaseModel):
    run_id: str
    uid: str
    source_type: str
    source_account_hash: Optional[str] = None
    importer_version: str
    extractor_version: Optional[str] = None
    status: MemoryImportRunStatus = MemoryImportRunStatus.received
    artifact_count: int = 0
    candidate_count: int = 0
    accepted_count: int = 0
    promoted_count: int = 0
    deduped_count: int = 0
    started_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    last_error: Optional[str] = None


class MemoryImportArtifact(BaseModel):
    artifact_id: str
    uid: str
    run_id: str
    source_type: str
    external_id: Optional[str] = None
    content_hash: str
    title: Optional[str] = None
    snippet: Optional[str] = None
    redacted_body: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    occurred_at: Optional[datetime] = None
    captured_at: datetime
    client_device_id: Optional[str] = None
    source_state: MemoryImportArtifactSourceState = MemoryImportArtifactSourceState.active
    redaction_status: str = "redacted_or_summary"
    sensitivity_labels: List[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @field_validator("sensitivity_labels")
    @classmethod
    def normalize_sensitivity_labels(cls, value: List[str]) -> List[str]:
        return sorted({label.strip().lower() for label in value if label and label.strip()})


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
