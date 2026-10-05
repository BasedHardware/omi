"""Extraction-only identity evidence. None of this grants voice-teaching authority."""

from typing import Literal, Optional

from pydantic import BaseModel, Field, StrictInt, StrictStr, model_validator

from models.structured_extraction import ExtractedParticipant, RichStructuredExtraction


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


class SpeakerLabeledExtraction(RichStructuredExtraction[LabeledParticipant]):
    participants: list[LabeledParticipant] = Field(default_factory=list)
    owner: Optional[LabeledParticipant] = Field(default=None, description='Account owner only; omit when unknown')

    @model_validator(mode='before')
    @classmethod
    def keep_labeled_participants(cls, value):
        if isinstance(value, dict) and isinstance(value.get('participants'), list):
            participants = []
            for item in value['participants']:
                try:
                    participants.append(LabeledParticipant.model_validate(item))
                except (ValueError, TypeError):
                    continue
            value = {**value, 'participants': participants}
        return value

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

    def to_structured(self):
        result = super().to_structured()
        # Underscore attributes survive model_copy but stay outside declared
        # fields, JSON, persisted notes, and the shared client schema.
        candidates = [
            SpeakerCandidate(
                name=participant.name or '',
                is_owner=is_owner,
                is_ai_agent=participant.is_ai_agent,
                bindings=participant.speaker_bindings,
            )
            for participant, is_owner in [*((p, False) for p in self.participants), (self.owner, True)]
            # A participant without bindings can never be admitted; dropping it
            # here skips the entitlement and catalog reads its rejection would
            # otherwise still perform.
            if isinstance(participant, LabeledParticipant) and participant.speaker_bindings
        ]
        setattr(result, '_summary_speaker_candidates', candidates)
        setattr(result, '_summary_speaker_roster', None)
        return result
