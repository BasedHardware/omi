"""Content-free authority receipts for bounded JIT proactive work."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from models.memory_evidence import SourceState
from models.product_memory import (
    RESTRICTED_SENSITIVITY_LABELS,
    MemoryItem,
    MemoryItemStatus,
    MemoryKind,
    MemoryLayer,
    MemorySubjectScope,
    ProcessingState,
)

JIT_PLANNED_NOTIFICATIONS_PER_TRIGGER_PER_DAY = 1
JIT_TOTAL_PROACTIVE_NOTIFICATIONS_PER_DAY = 3
JIT_AMBIGUOUS_NANO_TRIAGES_PER_DAY = 8
JIT_FULL_TURNS_PER_CANDIDATE = 1
JIT_TOTAL_FULL_TURNS_PER_DAY = 3
JIT_MAX_CALENDAR_EVENTS = 32
JIT_POLICY_VALID_FOR_SECONDS = 30
JIT_CONTENT_FREE_ID_PATTERN = r"^[0-9a-f]{64}$"

JITProactivityOperation = Literal[
    "planned_notification",
    "ambient_notification",
    "nano_triage",
    "full_turn",
]


class JITProactivityEventReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["jit_proactivity_event.v1"] = "jit_proactivity_event.v1"
    uid: str
    event_id: str
    candidate_id: str
    operation: JITProactivityOperation
    account_generation: int = Field(ge=0)
    trigger_memory_id: str | None = None
    trigger_revision: int | None = Field(default=None, ge=1)
    parent_event_id: str | None = Field(default=None, pattern=JIT_CONTENT_FREE_ID_PATTERN)
    budget_day: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    budget_timezone: str = Field(default="UTC", min_length=1, max_length=64)
    device_id: str
    created_at: datetime
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    feedback_id: str | None = None

    @field_validator("uid")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized or len(normalized) > 128 or "/" in normalized:
            raise ValueError("JIT proactivity identifier is invalid")
        return normalized

    @field_validator("event_id", "candidate_id", "device_id")
    @classmethod
    def validate_content_free_identifier(cls, value: str) -> str:
        normalized = (value or "").strip()
        if len(normalized) != 64 or any(character not in "0123456789abcdef" for character in normalized):
            raise ValueError("JIT proactivity identifier must be a content-free SHA-256 digest")
        return normalized

    @field_validator("trigger_memory_id", "feedback_id")
    @classmethod
    def validate_optional_identifier(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized or len(normalized) > 256 or "/" in normalized:
            raise ValueError("JIT trigger identifier is invalid")
        return normalized

    @field_validator("created_at")
    @classmethod
    def validate_aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("JIT proactivity receipt time must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_trigger_pair(self) -> "JITProactivityEventReceipt":
        if (self.trigger_memory_id is None) != (self.trigger_revision is None):
            raise ValueError("JIT trigger id and revision must be supplied together")
        if self.operation == "planned_notification" and self.trigger_memory_id is None:
            raise ValueError("planned notification requires trigger authority")
        if self.operation == "full_turn":
            if self.parent_event_id is None:
                raise ValueError("full turn requires a notification-admission parent")
        elif self.parent_event_id is not None:
            raise ValueError("parent event is only valid for a full turn")
        return self


def is_jit_trigger_paid_authority(item: MemoryItem, *, at: datetime) -> bool:
    """Pure model-layer fence shared by snapshots and paid reservations."""

    action = item.trigger_condition.get("action")
    prompt = action.get("prompt") if isinstance(action, dict) else None
    return bool(
        item.ledger_schema_version == "knowledge_ledger.v1"
        and item.kind == MemoryKind.trigger
        and item.tier == MemoryLayer.long_term
        and item.processing_state == ProcessingState.processed
        and item.status == MemoryItemStatus.active
        and item.valid_to is None
        and item.superseded_by is None
        and (item.valid_from is None or item.valid_from <= at)
        and item.source_state == SourceState.active
        and any(evidence.source_state == SourceState.active for evidence in item.evidence)
        and item.intent_backed
        and item.subject_scope == MemorySubjectScope.primary_user
        and not set(item.sensitivity_labels).intersection(RESTRICTED_SENSITIVITY_LABELS)
        and isinstance(action, dict)
        and action.get("type") == "agent_prompt"
        and isinstance(prompt, str)
        and 0 < len(" ".join(prompt.split())) <= 2_000
    )


__all__ = [
    "JITProactivityEventReceipt",
    "JITProactivityOperation",
    "JIT_PLANNED_NOTIFICATIONS_PER_TRIGGER_PER_DAY",
    "JIT_TOTAL_PROACTIVE_NOTIFICATIONS_PER_DAY",
    "JIT_AMBIGUOUS_NANO_TRIAGES_PER_DAY",
    "JIT_FULL_TURNS_PER_CANDIDATE",
    "JIT_TOTAL_FULL_TURNS_PER_DAY",
    "JIT_MAX_CALENDAR_EVENTS",
    "JIT_POLICY_VALID_FOR_SECONDS",
    "JIT_CONTENT_FREE_ID_PATTERN",
    "is_jit_trigger_paid_authority",
]
