"""Internal output schema shared by all v2 notes arms (no app-client wire change)."""

from __future__ import annotations

from typing import Any, Literal, Optional, cast
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from models.conversation_emoji import CATEGORY_EMOJI, DEFAULT_EMOJI, NEUTRAL_EMOJI, fallback_emoji
from models.conversation_enums import CategoryEnum
from models.structured import Structured
from models.structured_extraction import (
    AgentNotesParticipant,
    ExtractedActionItem,
    ExtractedEvent,
    ExtractedInsight,
    ExtractedRichSection,
    MeetingType,
    SALIENCE_DESCRIPTION,
)

# A submission that never chose an emoji must not silently store the pydantic
# default: every conversation served with the v2 contract would pin 🧠 (the
# 2026-10-23 rollout). The shared category fallback in models.conversation_emoji
# is the deterministic stand-in; it is re-exported here for the existing
# notes-output importers (backfill tooling, tests).
__all__ = ['CATEGORY_EMOJI', 'DEFAULT_EMOJI', 'NEUTRAL_EMOJI', 'fallback_emoji']


class NotesOutput(BaseModel):
    """One schema, independent of the legacy parser's subtype-coercing validators."""

    title: str = ''
    overview: str = ''
    emoji: str = Field(description='An emoji to represent the conversation', default=DEFAULT_EMOJI)
    category: CategoryEnum = CategoryEnum.other
    sections: list[ExtractedRichSection] = Field(default_factory=list)
    action_items: list[ExtractedActionItem] = Field(default_factory=list)
    events: list[ExtractedEvent] = Field(default_factory=list)
    participants: list[AgentNotesParticipant] = Field(default_factory=list)
    salience: Optional[Literal['highlight', 'background']] = Field(default=None, description=SALIENCE_DESCRIPTION)
    meeting_type: Optional[MeetingType] = None
    insights: list[ExtractedInsight] = Field(default_factory=list)

    @model_validator(mode='before')
    @classmethod
    def keep_usable_content(cls, data: Any) -> Any:
        """A malformed optional item must not cost every other grounded field."""
        if not isinstance(data, dict):
            return data
        data = dict(data)
        for field in ('title', 'overview', 'emoji'):
            if data.get(field) is None:
                data.pop(field, None)
        for field, vocabulary in (('salience', ('highlight', 'background')), ('meeting_type', MeetingType.__args__)):
            value = data.get(field)
            if value is not None:
                normalized = value.strip().lower() if isinstance(value, str) else None
                data[field] = normalized if normalized in vocabulary else None
        children: dict[str, type[BaseModel]] = {
            'sections': ExtractedRichSection,
            'action_items': ExtractedActionItem,
            'events': ExtractedEvent,
            'participants': AgentNotesParticipant,
            'insights': ExtractedInsight,
        }
        for field, model in children.items():
            values = data.get(field)
            if values is None:
                data.pop(field, None)
                continue
            if not isinstance(values, list):
                continue
            kept = []
            for value in values:
                try:
                    kept.append(model.model_validate(value))
                except ValidationError:
                    # No source text, names or IDs enter diagnostic logs.
                    continue
            data[field] = kept
        return data

    @field_validator('category', mode='before')
    @classmethod
    def valid_category(cls, value: Any) -> CategoryEnum:
        try:
            return CategoryEnum(value)
        except (ValueError, TypeError):
            return CategoryEnum.other

    def to_structured(self) -> Structured:
        structured = Structured(
            title=self.title,
            overview=self.overview,
            emoji=fallback_emoji(self.emoji, self.category),
            category=cast(
                Any, self.category
            ),  # SDK and backend enums share values; Pydantic converts at this boundary.
            sections=[section.to_section() for section in self.sections],
            action_items=[item.to_action_item() for item in self.action_items],
            events=[event.to_event() for event in self.events],
        )
        if self.participants:
            structured.participants = [person.to_participant() for person in self.participants]
        if self.salience is not None:
            structured.salience = self.salience
        if self.meeting_type is not None:
            structured.meeting_type = self.meeting_type
        if self.insights:
            structured.insights = [insight.to_insight() for insight in self.insights]
        return structured


def submit_tool() -> dict[str, Any]:
    """The agent's terminal tool and one-shot parser expose the exact same schema."""
    return {
        'type': 'function',
        'function': {
            'name': 'submit_notes',
            'description': 'Submit complete notes under the shared output contract.',
            'parameters': NotesOutput.model_json_schema(),
        },
    }
