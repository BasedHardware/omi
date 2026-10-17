"""Developer API speech projection preserves captured text alongside corrections."""

from typing import Optional
from pydantic import BaseModel, ConfigDict, model_serializer


class SimpleTranscriptSegment(BaseModel):
    model_config = ConfigDict(title='DeveloperTranscriptSegment')

    id: Optional[str] = None
    text: str
    original_text: Optional[str] = None
    speaker_id: Optional[int] = None
    speaker_name: Optional[str] = None
    start: float
    end: float

    @model_serializer(mode='wrap')
    def omit_absent_original(self, handler):
        data = handler(self)
        if self.original_text is None:
            data.pop('original_text', None)
        return data
