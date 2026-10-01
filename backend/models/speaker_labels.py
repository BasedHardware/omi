from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class RejectSpeakerRequest(BaseModel):
    kind: Literal['not_me', 'not_person', 'not_a_person']
    person_id: Optional[str] = None
    segment_ids: Optional[List[str]] = None

    @model_validator(mode='after')
    def not_person_requires_person_id(self) -> 'RejectSpeakerRequest':
        if self.segment_ids is not None and not self.segment_ids:
            raise ValueError('segment_ids must be non-empty when provided')
        if self.kind == 'not_person':
            if not (self.person_id and self.person_id.strip()):
                raise ValueError('person_id is required when kind is not_person')
        else:
            self.person_id = None
        return self


class VoiceMatch(BaseModel):
    conversation_id: str
    title: str
    started_at: datetime
    speaker_id: int
    talk_seconds: float
    segment_ids: List[str]
    clip_start: float
    clip_end: float
    match_level: Literal['strong', 'likely']


class VoiceMatchesResponse(BaseModel):
    matches: List[VoiceMatch] = Field(default_factory=list)
