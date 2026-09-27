"""Wire models for speaker tag prompts ("Is this you?" / "Who is this?")."""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class SpeakerTagPromptKind(str, Enum):
    # "Is this you?" — free for everyone; confirms or corrects the owner's voice.
    owner_check = 'owner_check'
    # "Is this <name>?" — an automatic match the user has not reviewed yet.
    confirm_person = 'confirm_person'
    # "Who is this?" — an unnamed voice.
    identify = 'identify'


class SpeakerTagPromptOrigin(str, Enum):
    """What the system believed about the voice before asking."""

    auto_user = 'auto_user'  # automatically labeled as the owner
    auto_person = 'auto_person'  # automatically matched to a person
    unnamed = 'unnamed'  # no label


class SpeakerTagPromptAnswer(str, Enum):
    me = 'me'  # That's me
    not_me = 'not_me'  # Not me
    person = 'person'  # An existing person (also "Yes" on confirm_person)
    new_person = 'new_person'  # A new name typed by the user
    someone_else = 'someone_else'  # Someone I don't know / not them
    skip = 'skip'  # Not sure


class SpeakerTagPromptQualityOutcome(str, Enum):
    """Bounded, privacy-safe quality label derived from one answer.

    Auto-labels the user reviewed yield precision (confirmed vs rejected);
    unnamed voices the user names yield misses (recall gaps).
    """

    owner_auto_confirmed = 'owner_auto_confirmed'
    owner_auto_rejected = 'owner_auto_rejected'
    owner_missed = 'owner_missed'
    owner_unmatched_not_owner = 'owner_unmatched_not_owner'
    person_auto_confirmed = 'person_auto_confirmed'
    person_auto_corrected = 'person_auto_corrected'
    person_missed_known = 'person_missed_known'
    person_not_enrolled = 'person_not_enrolled'
    unknown_voice = 'unknown_voice'
    skipped = 'skipped'


class SpeakerTagPrompt(BaseModel):
    id: str
    kind: SpeakerTagPromptKind
    origin: SpeakerTagPromptOrigin
    conversation_id: str
    conversation_title: str = ''
    conversation_started_at: Optional[datetime] = None
    speaker_id: int
    segment_ids: List[str]
    clip_start: float = Field(description='Clip start, seconds from conversation start')
    clip_end: float = Field(description='Clip end, seconds from conversation start')
    excerpt: str = ''
    suggested_person_id: Optional[str] = None
    suggested_person_name: Optional[str] = None
    suggested_person_ids: List[str] = Field(default_factory=list)


class SpeakerTagPromptsResponse(BaseModel):
    prompts: List[SpeakerTagPrompt] = Field(default_factory=list)
    # True until the user has seen their first set; the client shows the inline
    # "save voices of other people" toggle only then.
    first_time: bool = False
    save_other_voice_profiles: bool = True
    # Why the list is empty, for client analytics: disabled | cooldown | no_candidates | ok.
    status: str = 'ok'
    next_eligible_at: Optional[datetime] = None


class SpeakerTagPromptsShownRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    prompt_ids: List[str] = Field(default_factory=list, max_length=10)


class SpeakerTagPromptsShownResponse(BaseModel):
    first_time: bool


class SpeakerTagPromptAnswerRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    prompt_id: str = Field(min_length=1, max_length=64)
    kind: SpeakerTagPromptKind
    origin: SpeakerTagPromptOrigin
    conversation_id: str = Field(min_length=1, max_length=128)
    speaker_id: int = Field(ge=0)
    segment_ids: List[str] = Field(min_length=1, max_length=50)
    answer: SpeakerTagPromptAnswer
    person_id: Optional[str] = Field(default=None, max_length=128)
    name: Optional[str] = Field(default=None, min_length=2, max_length=40)
    suggested_person_id: Optional[str] = Field(default=None, max_length=128)
    first_time: bool = False


class SpeakerTagPromptAnswerResponse(BaseModel):
    status: str = 'ok'
    person_id: Optional[str] = None
    quality_outcome: SpeakerTagPromptQualityOutcome
    voice_sample_queued: bool = False


class SpeakerTagPromptClip(BaseModel):
    """A short clip of the user's own stored audio, as base64 WAV (16 kHz mono PCM16)."""

    audio_base64: str
    content_type: str = 'audio/wav'
    duration_seconds: float


class VoiceProfileSettings(BaseModel):
    speaker_tag_prompts_enabled: bool = True
    save_other_voice_profiles: bool = True


class VoiceProfileSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    speaker_tag_prompts_enabled: Optional[bool] = None
    save_other_voice_profiles: Optional[bool] = None
    # Where the change came from, for analytics only: settings | first_prompt.
    source: Optional[str] = Field(default=None, pattern='^(settings|first_prompt)$')
