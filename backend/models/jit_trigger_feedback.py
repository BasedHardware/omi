"""Content-free durable receipts for explicit JIT trigger feedback."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from models.jit_proactivity import JIT_CONTENT_FREE_ID_PATTERN

JITTriggerFeedbackAction = Literal["useful", "false_positive", "snooze", "disable", "missed_or_late"]


class JITTriggerFeedbackReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["jit_trigger_feedback.v1"] = "jit_trigger_feedback.v1"
    uid: str
    feedback_id: str = Field(pattern=JIT_CONTENT_FREE_ID_PATTERN)
    event_id: str = Field(pattern=JIT_CONTENT_FREE_ID_PATTERN)
    trigger_memory_id: str
    account_generation: int = Field(ge=0)
    expected_trigger_revision: int = Field(ge=1)
    action: JITTriggerFeedbackAction
    recorded_at: datetime
    snoozed_until: datetime | None = None
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    applied_trigger_revision: int | None = Field(default=None, ge=1)

    @field_validator("uid", "trigger_memory_id")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized or len(normalized) > 256 or "/" in normalized:
            raise ValueError("trigger feedback identifier is invalid")
        return normalized

    @field_validator("recorded_at", "snoozed_until")
    @classmethod
    def validate_aware_time(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("trigger feedback timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_snooze(self) -> "JITTriggerFeedbackReceipt":
        if self.action == "snooze" and self.snoozed_until is None:
            raise ValueError("snooze feedback requires snoozed_until")
        if self.action != "snooze" and self.snoozed_until is not None:
            raise ValueError("snoozed_until is only valid for snooze feedback")
        if self.snoozed_until is not None and self.snoozed_until <= self.recorded_at:
            raise ValueError("snoozed_until must be after recorded_at")
        return self


__all__ = ["JITTriggerFeedbackAction", "JITTriggerFeedbackReceipt"]
