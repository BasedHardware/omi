"""Recording speaker edits, shared by episode and conversation entry points."""

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from models.transcript_segment import TranscriptSegment


class RecordingTranscriptSegment(TranscriptSegment):
    stream_speaker: str


class RecordingTranscriptMember(BaseModel):
    id: str
    recording_offset_seconds: float
    transcript_segments: list[RecordingTranscriptSegment]


class RecordingTranscriptResponse(BaseModel):
    coverage: Literal['complete', 'partial'] = 'partial'
    enabled: bool
    episode_id: Optional[str] = None
    conversations: list[RecordingTranscriptMember]


class RecordingVoice(BaseModel):
    speaker_id_scope: str = Field(min_length=1, max_length=256)
    stream_speaker: str = Field(min_length=1, max_length=100)


class RecordingSelection(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=200)
    segment_ids: list[str] = Field(min_length=1, max_length=10000)
    speaker_id: Optional[int] = None
    voice: Optional[RecordingVoice] = None


class RecordingSpeakerRequest(BaseModel):
    person_id: Optional[str] = None
    is_user: bool = False
    selections: list[RecordingSelection] = Field(default_factory=list, max_length=100)
    voice: Optional[RecordingVoice] = None
    whole_recording: bool = True
    use_for_speech_training: bool = True

    @model_validator(mode='after')
    def one_identity(self):
        if bool(self.selections) == bool(self.voice):
            raise ValueError('Supply selected lines or one recording voice')
        if self.is_user and self.person_id:
            raise ValueError('Choose a person or the account owner')
        return self


class RecordingMemberCount(BaseModel):
    conversation_id: str
    applied_count: int
    error: Optional[str] = None


class RecordingSpeakerResponse(BaseModel):
    coverage: Literal['complete', 'partial'] = 'partial'
    episode_id: Optional[str] = None
    conversations: list[RecordingMemberCount]
    applied_count: int


class RecordingStaleDetail(BaseModel):
    code: Literal['stale_speaker']
    message: str


class RecordingSpeakerConflict(BaseModel):
    detail: Literal['recording_speaker_rename_disabled'] | RecordingStaleDetail


class RecordingSpeakerLimit(BaseModel):
    detail: Literal['recording_speaker_limit_exceeded']
