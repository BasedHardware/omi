"""Wire contracts for the additive just-in-time screen-frame request queue.

The queue carries metadata only.  Pixels are uploaded by the owning desktop
device through the existing screen-sync path and are never accepted in this
API model or emitted as telemetry.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FrameRequestState(str, Enum):
    requested = "requested"
    claimed = "claimed"
    uploaded = "uploaded"
    attached = "attached"
    offline = "offline"
    pruned = "pruned"
    failed = "failed"
    expired = "expired"
    cancelled = "cancelled"


TERMINAL_FRAME_REQUEST_STATES = frozenset(
    {
        FrameRequestState.attached,
        FrameRequestState.offline,
        FrameRequestState.pruned,
        FrameRequestState.failed,
        FrameRequestState.expired,
        FrameRequestState.cancelled,
    }
)


class FrameRequest(BaseModel):
    """Owner-scoped request and its auditable lifecycle state."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=128)
    uid: str = Field(min_length=1, max_length=256)
    device_id: str = Field(min_length=1, max_length=256)
    account_generation: int = Field(default=0, ge=0)
    dedupe_key: str = Field(min_length=1, max_length=256)
    # The identity is reusable after a terminal/expired attempt.  These fields
    # make that boundary explicit instead of letting a forever-stable document
    # id starve future requests.
    dedupe_window: int = Field(default=0, ge=0)
    attempt_number: int = Field(default=0, ge=0)
    conversation_id: str | None = Field(default=None, max_length=256)
    screenshot_id: str | None = Field(default=None, max_length=256)
    state: FrameRequestState = FrameRequestState.requested
    created_at: datetime
    expires_at: datetime
    claimed_at: datetime | None = None
    uploaded_at: datetime | None = None
    attached_at: datetime | None = None
    terminal_reason: str | None = Field(default=None, max_length=240)
    byte_count: int = Field(default=0, ge=0, le=10 * 1024 * 1024)
    content_type: str | None = Field(default=None, max_length=100)
    storage_id: str | None = Field(default=None, max_length=256)

    @field_validator("uid", "device_id", "request_id", "dedupe_key", mode="before")
    @classmethod
    def _strip_required_strings(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise TypeError("frame request identifiers must be strings")
        value = value.strip()
        if not value:
            raise ValueError("frame request identifiers must not be blank")
        return value

    @field_validator("request_id")
    @classmethod
    def _validate_request_id(cls, value: str) -> str:
        if "/" in value or "\\" in value:
            raise ValueError("request_id must be one opaque path segment")
        return value

    @field_validator("conversation_id", "screenshot_id", "terminal_reason", "content_type", "storage_id", mode="before")
    @classmethod
    def _strip_optional_strings(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("frame request optional fields must be strings")
        value = value.strip()
        return value or None

    @field_validator("storage_id")
    @classmethod
    def _validate_storage_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if "/" in value or "\\" in value or value.startswith(("http:", "https:")):
            raise ValueError("storage_id must be an opaque owner-scoped identifier")
        return value

    @field_validator("created_at", "expires_at", "claimed_at", "uploaded_at", "attached_at")
    @classmethod
    def _normalize_datetime(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def _validate_lifecycle(self) -> FrameRequest:
        if self.expires_at < self.created_at:
            raise ValueError("frame request expiry must not precede creation")
        if self.state == FrameRequestState.attached and not self.conversation_id:
            raise ValueError("attached frame requests require a conversation")
        if self.state == FrameRequestState.attached and self.expires_at != self.created_at:
            raise ValueError("attached frame requests must not carry a time-based expiry")
        if self.state == FrameRequestState.attached and self.terminal_reason:
            raise ValueError("attached frame requests do not carry a terminal reason")
        if (
            self.state in TERMINAL_FRAME_REQUEST_STATES
            and self.state != FrameRequestState.attached
            and not self.terminal_reason
        ):
            raise ValueError("terminal frame requests require a bounded reason")
        if self.state == FrameRequestState.uploaded and not self.storage_id:
            raise ValueError("uploaded frame requests require a storage id")
        return self


class CreateFrameRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(min_length=1, max_length=256)
    account_generation: int = Field(default=0, ge=0)
    dedupe_key: str = Field(min_length=1, max_length=256)
    conversation_id: str | None = Field(default=None, max_length=256)
    screenshot_id: str | None = Field(default=None, max_length=256)
    requested_ttl_seconds: int | None = Field(default=None, ge=1, le=7 * 24 * 60 * 60)


class FrameRequestStateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: FrameRequestState
    device_id: str = Field(min_length=1, max_length=256)
    account_generation: int = Field(default=0, ge=0)
    terminal_reason: str | None = Field(default=None, max_length=240)
    storage_id: str | None = Field(default=None, max_length=256)
    byte_count: int = Field(default=0, ge=0, le=10 * 1024 * 1024)
    content_type: str | None = Field(default=None, max_length=100)

    @field_validator("storage_id")
    @classmethod
    def _validate_storage_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if "/" in value or "\\" in value or value.startswith(("http:", "https:")):
            raise ValueError("storage_id must be an opaque owner-scoped identifier")
        return value or None


class FrameRequestPromotion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(min_length=1, max_length=256)
    account_generation: int = Field(default=0, ge=0)
    conversation_id: str = Field(min_length=1, max_length=256)


class FrameRequestEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request: FrameRequest
    deduplicated: bool = False


class FrameRequestBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requests: list[FrameRequest] = Field(default_factory=list, max_length=32)
