"""Developer API speech projection preserves captured text alongside corrections."""

from typing import Optional
from pydantic import BaseModel, ConfigDict


class SimpleTranscriptSegment(BaseModel):
    model_config = ConfigDict(title='DeveloperTranscriptSegment')

    id: Optional[str] = None
    text: str
    original_text: Optional[str] = None
    speaker_id: Optional[int] = None
    speaker_name: Optional[str] = None
    start: float
    end: float
