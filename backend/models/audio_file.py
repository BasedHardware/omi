from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class AudioFile(BaseModel):
    id: str = Field(description="Unique identifier for the audio file")
    uid: str = Field(description="User ID who owns this audio file")
    conversation_id: str = Field(description="ID of the conversation this audio belongs to")
    chunk_timestamps: List[float] = Field(description="List of chunk timestamps (for on-demand merging)")
    provider: str = Field(default="gcp", description="Storage provider (e.g., 'gcp')")
    started_at: Optional[datetime] = Field(
        default=None, description="When this audio file started (absolute timestamp)"
    )
    duration: float = Field(description="Duration in seconds")
    # Audio-timeline v2: authoritative contiguous coverage as [start, end]
    # wall-epoch second pairs, populated from blob metadata at upload time.
    # Absent on legacy files; a v1-only chunk list is at best a candidate,
    # never proof of full coverage.
    chunk_spans: Optional[List[List[float]]] = Field(
        default=None, description="Validated contiguous coverage spans (v2 only)"
    )
