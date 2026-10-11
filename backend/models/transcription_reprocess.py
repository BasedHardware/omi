"""Wire contract for stored-audio transcription reprocess failures."""

from pydantic import BaseModel, Field


class TranscriptionReprocessErrorDetail(BaseModel):
    code: str = Field(description='Stable reason: no_audio, no_speech, or failed. Clients tolerate future reasons.')
    message: str | None = None


class TranscriptionReprocessErrorResponse(BaseModel):
    detail: TranscriptionReprocessErrorDetail
