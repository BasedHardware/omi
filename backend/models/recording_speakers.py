"""Recording speaker edits, shared by episode and conversation entry points."""

from typing import Optional

from pydantic import BaseModel, Field, model_validator


class RecordingSelection(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=200)
    segment_ids: list[str] = Field(min_length=1, max_length=10000)
    speaker_id: Optional[int] = None


class RecordingVoice(BaseModel):
    speaker_id_scope: str = Field(min_length=1, max_length=256)
    stream_speaker: str = Field(min_length=1, max_length=100)


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


class RecordingSpeakerResponse(BaseModel):
    episode_id: Optional[str] = None
    conversations: list[RecordingMemberCount]
    applied_count: int
