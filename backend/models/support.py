"""Private support response allowlists. Never serialize a customer document directly."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from models.conversation_enums import PostProcessingStatus


class SupportLookupResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    uid: str
    email: str
    plan: str
    last_active_at: datetime | None = None
    last_active_platform: str | None = None
    transcription_seconds_used: float
    transcription_seconds_limit: int | None = None
    transcription_seconds_remaining: float | None = None
    fair_use_stage: str


class SupportTraceRow(BaseModel):
    model_config = ConfigDict(extra='forbid')

    conversation_id: str
    started_at: datetime
    duration_seconds: float | None = None
    status: str
    postprocessing_status: PostProcessingStatus | None = None
    captured: bool
    synced: bool
    processed: bool
    saved: bool
    discarded: bool = False
    deleted: bool = False
    failed: bool
    failure_stage: Literal['capture', 'sync', 'process', 'save'] | None = None
    audio_present: bool
    has_transcript: bool


class SupportTraceResponse(BaseModel):
    model_config = ConfigDict(extra='forbid', populate_by_name=True)

    email: str
    uid: str
    window_from: datetime = Field(validation_alias='from', serialization_alias='from')
    window_to: datetime = Field(validation_alias='to', serialization_alias='to')
    truncated: bool
    rows: list[SupportTraceRow]
