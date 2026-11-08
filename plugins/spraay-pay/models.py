"""Pydantic models for Omi webhook payloads.

Field names follow what Omi's backend sends (backend/utils/app_integrations.py),
which differs from the public docs in two ways that both are accepted here:
real-time calls POST ``{"session_id", "segments"}`` rather than a bare array, and
segments carry ``speaker_id`` rather than ``speakerId``.
"""

from __future__ import annotations

from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


class _OmiModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class TranscriptSegment(_OmiModel):
    id: str | None = None
    text: str = ""
    speaker: str | None = None
    speaker_id: int | None = Field(default=None, validation_alias=AliasChoices("speaker_id", "speakerId"))
    is_user: bool = False
    start: float = 0.0
    end: float = 0.0


class TranscriptPayload(_OmiModel):
    session_id: str | None = None
    segments: list[TranscriptSegment] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def accept_documented_array(cls, data: Any) -> Any:
        return {"segments": data} if isinstance(data, list) else data


class Structured(_OmiModel):
    title: str = ""
    overview: str = ""
    category: str | None = None


class MemoryPayload(_OmiModel):
    id: str
    transcript_segments: list[TranscriptSegment] = Field(default_factory=list)
    structured: Structured = Field(default_factory=Structured)
    discarded: bool = False


class ChatToolRequest(_OmiModel):
    uid: str = Field(min_length=1)
    app_id: str | None = None
    tool_name: str | None = None


class PayRequest(ChatToolRequest):
    command: str


class ConfirmRequest(ChatToolRequest):
    code: str
