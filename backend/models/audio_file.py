from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ChunkSpan(BaseModel):
    """One contiguous stretch of stored PCM, in wall-epoch seconds."""

    start: float
    end: float


class AudioFile(BaseModel):
    id: str = Field(description="Unique identifier for the audio file")
    source_fingerprint: Optional[str] = None
    uid: str = Field(description="User ID who owns this audio file")
    conversation_id: str = Field(description="ID of the conversation this audio belongs to")
    chunk_timestamps: List[float] = Field(description="List of chunk timestamps (for on-demand merging)")
    provider: str = Field(default="gcp", description="Storage provider (e.g., 'gcp')")
    started_at: Optional[datetime] = Field(
        default=None, description="When this audio file started (absolute timestamp)"
    )
    duration: float = Field(description="Duration in seconds")
    # Audio-timeline v2: authoritative contiguous coverage as {start, end}
    # wall-epoch second objects (Firestore cannot store nested arrays),
    # populated from blob metadata at upload time.
    # Absent on legacy files; a v1-only chunk list is at best a candidate,
    # never proof of full coverage.
    chunk_spans: Optional[List[ChunkSpan]] = Field(
        default=None, description="Validated contiguous coverage spans (v2 only)"
    )
    # Server-clock (capture-skew normalized) start of this part's first chunk,
    # from chunk blob metadata. The playback manifest's wall offsets use it;
    # chunk_timestamps/started_at keep the raw capture clock for storage
    # identity. Absent when any chunk in the group predates skew persistence.
    playback_start: Optional[float] = Field(
        default=None, description="Normalized server-clock start for playback wall math (v2 only)"
    )
