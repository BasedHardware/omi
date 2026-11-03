"""Wire contracts for the owner-scoped processing projection and recovery API."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class PendingWorkItem(BaseModel):
    id: str
    kind: Literal['conversation', 'sync_job']
    state: Literal['queued', 'transcribing', 'summarizing']
    conversation_ids: list[str]
    started_at: datetime | None
    duration_seconds: float
    updated_at: datetime | None


class PendingWorkSnapshot(BaseModel):
    enabled: bool
    items: list[PendingWorkItem]
    attention_unseen_count: int


class AttentionRetryStatus(BaseModel):
    state: Literal['none', 'in_progress', 'succeeded', 'failed']
    operation_id: str | None


class AttentionItem(BaseModel):
    id: str
    kind: Literal['conversation_summary_failed']
    conversation_id: str
    title: str | None
    started_at: datetime | None
    duration_seconds: float
    failure_code: str
    retryable: bool
    created_at: datetime
    seen: bool
    retry: AttentionRetryStatus


class AttentionItemsPage(BaseModel):
    enabled: bool
    items: list[AttentionItem]
    unseen_count: int


class AttentionRetryResponse(BaseModel):
    operation_id: str
    state: Literal['in_progress', 'succeeded', 'failed']


class AttentionRetryAllOperation(AttentionRetryResponse):
    id: str


class AttentionRetryAllResponse(BaseModel):
    operations: list[AttentionRetryAllOperation]


class RetryAllRequest(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=200)


class SeenRequest(BaseModel):
    ids: list[str] = Field(default_factory=list, max_length=100, json_schema_extra={'default': []})
    all: bool = False
