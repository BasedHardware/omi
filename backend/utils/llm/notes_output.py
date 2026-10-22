"""Internal output schema shared by all v2 notes arms (no app-client wire change)."""

from __future__ import annotations

from typing import Optional
from pydantic import Field, model_validator
from models.structured_extraction import (
    AgentNotesSubmission,
    ExtractedInsight,
    ExtractedRichSection,
    MeetingType,
    ExtractedActionItem,
    ExtractedEvent,
    _keep_usable_content,
)


class NotesOutput(AgentNotesSubmission):
    sections: list[ExtractedRichSection] = Field(default_factory=list)
    meeting_type: Optional[MeetingType] = None
    insights: list[ExtractedInsight] = Field(default_factory=list)

    @model_validator(mode='before')
    @classmethod
    def keep_usable_content(cls, data):
        # Override the base validator: it otherwise coerces richer section instances
        # back to ExtractedSection before the subclass field validator sees them.
        return _keep_usable_content(
            data, {'sections': ExtractedRichSection, 'action_items': ExtractedActionItem, 'events': ExtractedEvent}
        )

    def to_structured(self):
        structured = super().to_structured()
        if self.meeting_type is not None:
            structured.meeting_type = self.meeting_type
        if self.insights:
            structured.insights = [insight.to_insight() for insight in self.insights]
        return structured


def submit_tool() -> dict:
    """The agent's terminal tool and one-shot parser expose the exact same schema."""
    return {
        'type': 'function',
        'function': {
            'name': 'submit_notes',
            'description': 'Submit complete notes under the shared output contract.',
            'parameters': NotesOutput.model_json_schema(),
        },
    }
