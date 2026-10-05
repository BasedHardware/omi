"""Extraction-only identity evidence. None of this grants voice-teaching authority."""

from typing import Literal, Optional

from pydantic import BaseModel, Field, PrivateAttr, StrictInt, StrictStr, model_validator

from models.structured import Structured
from models.structured_extraction import ExtractedParticipant, RichStructuredExtraction
from utils.conversations.meeting_participants import MeetingRoster


class SpeakerBinding(BaseModel):
    speaker_id: StrictInt = Field(ge=0, description='Exact numeric spk key in the transcript')
    confidence: Literal['high', 'medium', 'low'] = 'low'
    evidence_segment_ids: list[StrictStr] = Field(default_factory=list, min_length=1, max_length=2)
    evidence_kind: Literal['self_introduction', 'contextual'] = 'contextual'


class LabeledParticipant(ExtractedParticipant):
    speaker_bindings: list[SpeakerBinding] = Field(default_factory=list, max_length=8)

    @model_validator(mode='before')
    @classmethod
    def keep_note_on_bad_bindings(cls, value):
        if not isinstance(value, dict):
            return value
        try:
            bindings = value.get('speaker_bindings', [])
            if not isinstance(bindings, list) or len(bindings) > 8:
                raise ValueError('invalid bindings')
            for binding in bindings:
                SpeakerBinding.model_validate(binding)
        except (ValueError, TypeError):
            value = {**value, 'speaker_bindings': []}
        return value


class SpeakerCandidate(BaseModel):
    name: str
    is_owner: bool = False
    is_ai_agent: bool = False
    bindings: list[SpeakerBinding] = Field(default_factory=list)


class NotesWithSpeakerCandidates(Structured):
    # Private attributes survive deterministic presentation repair but never enter
    # the client schema, JSON, external app payload, or persisted note document.
    _summary_speaker_candidates: list[SpeakerCandidate] = PrivateAttr(default_factory=list)
    _summary_speaker_roster: Optional[MeetingRoster] = PrivateAttr(default=None)


class SpeakerLabeledExtraction(RichStructuredExtraction):
    participants: list[LabeledParticipant] = Field(default_factory=list)
    owner: Optional[LabeledParticipant] = Field(default=None, description='Account owner only; omit when unknown')

    @model_validator(mode='before')
    @classmethod
    def keep_usable_rich_content(cls, value):
        if isinstance(value, dict) and isinstance(value.get('participants'), list):
            participants = []
            for item in value['participants']:
                try:
                    participants.append(LabeledParticipant.model_validate(item))
                except (ValueError, TypeError):
                    continue
            value = {**value, 'participants': participants}
        return RichStructuredExtraction.keep_usable_rich_content(value)

    @model_validator(mode='before')
    @classmethod
    def keep_owner_optional(cls, value):
        if not isinstance(value, dict):
            return value
        value = dict(value)
        if value.get('owner') is not None:
            try:
                value['owner'] = LabeledParticipant.model_validate(value['owner'])
            except (ValueError, TypeError):
                value['owner'] = None
        return value

    def to_structured(self) -> Structured:
        base = super().to_structured()
        result = NotesWithSpeakerCandidates.model_validate(base.model_dump(exclude_unset=True))
        result._summary_speaker_candidates = [
            SpeakerCandidate(
                name=participant.name or '',
                is_owner=is_owner,
                is_ai_agent=participant.is_ai_agent,
                bindings=participant.speaker_bindings,
            )
            for participant, is_owner in [*((p, False) for p in self.participants), (self.owner, True)]
            if isinstance(participant, LabeledParticipant)
        ]
        return result
