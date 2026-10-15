from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class ChunkSpan(BaseModel):
    """One contiguous stretch of stored PCM, in wall-epoch seconds."""

    start: float = Field(ge=0)
    end: float = Field(ge=0)

    @model_validator(mode='after')
    def validate_span(self):
        if self.end < self.start:
            raise ValueError('span end must not precede start')
        return self


class AudioFile(BaseModel):
    id: str = Field(description="Unique identifier for the audio file")
    uid: str = Field(description="User ID who owns this audio file")
    conversation_id: str = Field(description="ID of the conversation this audio belongs to")
    chunk_timestamps: List[float] = Field(description="List of chunk timestamps (for on-demand merging)")
    provider: str = Field(default="gcp", min_length=1, description="Storage provider (e.g., 'gcp')")
    started_at: Optional[datetime] = Field(
        default=None, description="When this audio file started (absolute timestamp)"
    )
    duration: float = Field(ge=0, description="Duration in seconds")
    # Audio-timeline v2: authoritative contiguous coverage as {start, end}
    # wall-epoch second objects (Firestore cannot store nested arrays),
    # populated from blob metadata at upload time.
    # Absent on legacy files; a v1-only chunk list is at best a candidate,
    # never proof of full coverage.
    chunk_spans: Optional[List[ChunkSpan]] = Field(
        default=None, description="Validated contiguous coverage spans (v2 only)"
    )

    @field_validator('chunk_timestamps', mode='before')
    @classmethod
    def _validate_chunk_timestamps(cls, v: object) -> object:
        if v is None:
            return v
        if not isinstance(v, list):
            raise ValueError('chunk_timestamps must be a list')
        for ts in v:
            if not isinstance(ts, (int, float)) or ts < 0:
                raise ValueError('chunk timestamp must be a non-negative number')
        return v
