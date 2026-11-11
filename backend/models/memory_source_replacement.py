"""Committed receipt for one idempotent conversation-source replacement."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from pydantic import BaseModel, Field, field_validator

from models.memory_apply import MemoryControlState


class ConversationSourceReplacementReceipt(BaseModel):
    replacement_id: str
    replacement_digest: str
    uid: str
    conversation_id: str
    operation_id: str
    control_state: MemoryControlState
    retracted_memory_ids: List[str] = Field(default_factory=list)
    committed_memory_ids: List[str] = Field(default_factory=list)
    reactivated_memory_ids: List[str] = Field(default_factory=list)
    tombstoned_evidence_ids: List[str] = Field(default_factory=list)
    committed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator(
        "replacement_id",
        "replacement_digest",
        "uid",
        "conversation_id",
        "operation_id",
    )
    @classmethod
    def validate_nonblank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("source replacement identifiers must not be blank")
        return value

    @field_validator("committed_at")
    @classmethod
    def validate_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("source replacement timestamp must be timezone-aware")
        return value.astimezone(timezone.utc)


__all__ = ["ConversationSourceReplacementReceipt"]
