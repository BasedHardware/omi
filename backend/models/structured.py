import sys
from datetime import datetime
from pathlib import Path
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_serializer

_SDK_SRC = Path(__file__).resolve().parents[2] / 'plugins' / 'omi-plugin-sdk' / 'src'
if _SDK_SRC.exists() and str(_SDK_SRC) not in sys.path:
    sys.path.insert(0, str(_SDK_SRC))

try:
    from omi_plugin_sdk.models import ActionItem, Event, Insight, MeetingType, Participant, Section, Structured
except ModuleNotFoundError:
    from models.conversation_enums import CategoryEnum

    MeetingType = Literal[
        'interview', 'intro', 'sales', 'customer', 'one_on_one', 'team_sync', 'planning', 'demo', 'social', 'other'
    ]

    _OMIT_WHEN_UNSET = ('meeting_type', 'participants', 'insights')

    def _drop_unset_fields(model: BaseModel, data: dict, fields: tuple) -> dict:
        for field_name in fields:
            if field_name not in model.model_fields_set:
                data.pop(field_name, None)
        return data

    class ActionItem(BaseModel):
        description: str = Field(description='The action item to be completed')
        completed: bool = False
        created_at: Optional[datetime] = Field(default=None, description='When the action item was created')
        updated_at: Optional[datetime] = Field(default=None, description='When the action item was last updated')
        due_at: Optional[datetime] = Field(default=None, description='When the action item is due')
        completed_at: Optional[datetime] = Field(default=None, description='When the action item was completed')
        conversation_id: Optional[str] = Field(
            default=None, description='ID of the conversation this action item came from'
        )
        capture_kind: Optional[
            Literal['explicit_command', 'clear_commitment', 'direct_request', 'inferred_next_step']
        ] = None
        capture_confidence: Optional[float] = Field(default=None, ge=0, le=1)
        ownership_confidence: Optional[float] = Field(default=None, ge=0, le=1)
        capture_owner: Optional[Literal['user', 'other', 'unknown']] = None
        owner_name: Optional[str] = Field(default=None, description="The person's name when the owner is known")
        context: Optional[str] = Field(default=None, description='One line explaining why or how the item matters')
        due_certainty: Optional[Literal['confirmed', 'tentative']] = Field(
            default=None, description='Whether the due date was confirmed or only discussed tentatively'
        )
        concrete_deliverable: Optional[bool] = Field(
            default=None,
            description='True only when the commitment names a concrete deliverable or outcome',
        )
        candidate_action: Optional[Literal['create', 'update', 'complete']] = None
        target_task_id: Optional[str] = None
        source_segment_ids: List[str] = Field(default_factory=list)

        @staticmethod
        def actions_to_string(action_items: List['ActionItem']) -> str:
            if not action_items:
                return 'None'

            result = []
            for item in action_items:
                status = 'completed' if item.completed else 'pending'
                line = f'- {item.description} ({status})'

                timestamps = []
                if item.created_at:
                    timestamps.append(f"Created: {item.created_at.strftime('%Y-%m-%d %H:%M:%S')} UTC")
                if item.due_at:
                    timestamps.append(f"Due: {item.due_at.strftime('%Y-%m-%d %H:%M:%S')} UTC")
                if item.completed_at:
                    timestamps.append(f"Completed: {item.completed_at.strftime('%Y-%m-%d %H:%M:%S')} UTC")

                if timestamps:
                    line += f" [{', '.join(timestamps)}]"

                result.append(line)

            return '\n'.join(result)

    class Event(BaseModel):
        title: str = Field(description='The title of the event')
        description: str = Field(description='A brief description of the event', default='')
        start: datetime = Field(description='The start date and time of the event')
        duration: int = Field(description='The duration of the event in minutes', default=30)
        created: bool = False

        def as_dict_cleaned_dates(self):
            event_dict = self.model_dump()
            event_dict['start'] = event_dict['start'].isoformat()
            return event_dict

        @staticmethod
        def events_to_string(events: List['Event']) -> str:
            if not events:
                return 'None'
            return '\n'.join(
                [
                    f"- {event.title} (Starts: {event.start.strftime('%Y-%m-%d %H:%M:%S %Z')}, Duration: {event.duration} mins)"
                    for event in events
                ]
            )

    class Section(BaseModel):
        heading: str = Field(description='A descriptive heading chosen for this conversation')
        body_markdown: str = Field(description='Free-form markdown containing the section details')
        source_segment_ids: List[str] = Field(
            default_factory=list, description='Transcript segment IDs that directly support this section'
        )
        kind: Literal['main', 'side_notes'] = Field(
            default='main', description='Whether the section is primary recap or the closing side-notes section'
        )

        @model_serializer(mode='wrap')
        def _omit_unset_kind(self, handler):
            return _drop_unset_fields(self, handler(self), ('kind',))

    class Participant(BaseModel):
        name: Optional[str] = Field(default=None, description="Participant's display name")
        email: Optional[str] = Field(default=None, description="Participant's email address")
        organization: Optional[str] = Field(default=None, description="Participant's organization when known")
        role: Optional[str] = Field(default=None, description="Participant's role or relationship when known")
        is_ai_agent: bool = Field(default=False, description='True for AI notetakers and assistants, never people')
        source: Literal['roster', 'transcript'] = Field(
            description="Whether meeting metadata ('roster') or only the conversation evidences this participant"
        )

    class Insight(BaseModel):
        text: str = Field(description='One insight connecting background context to this conversation')
        kind: Literal['prior_meeting', 'goal', 'memory', 'person'] = Field(
            description='Which background source the insight draws on'
        )

    class Structured(BaseModel):
        title: str = Field(description='A title/name for this conversation', default='')
        overview: str = Field(
            description='A brief overview of the conversation, highlighting the key details from it',
            default='',
        )
        emoji: str = Field(description='An emoji to represent the conversation', default='🧠')
        category: CategoryEnum = Field(description='A category for this conversation', default=CategoryEnum.other)
        sections: List[Section] = Field(
            description='Detailed, free-form note sections in the model-chosen structure', default_factory=list
        )
        action_items: List[ActionItem] = Field(
            description='A list of action items from the conversation', default_factory=list
        )
        events: List[Event] = Field(
            description='A list of events extracted from the conversation, that the user must have on his calendar.',
            default_factory=list,
        )
        meeting_type: Optional[MeetingType] = Field(
            default=None, description='The kind of meeting, when the capture is a meeting'
        )
        participants: List[Participant] = Field(
            default_factory=list,
            description='People and AI agents evidenced by the meeting roster or the transcript; never the account owner',
        )
        insights: List[Insight] = Field(
            default_factory=list,
            description='Insights connecting supplied background context to this conversation; empty without background',
        )

        @model_serializer(mode='wrap')
        def _omit_unset_rich_fields(self, handler):
            return _drop_unset_fields(self, handler(self), _OMIT_WHEN_UNSET)

        @field_validator('category', mode='before')
        @classmethod
        def set_category_default_on_error(cls, value):
            if isinstance(value, CategoryEnum):
                return value
            try:
                return CategoryEnum(value)
            except ValueError:
                return CategoryEnum.other

        def __str__(self):
            result = (
                f"{str(self.title).capitalize()} ({str(self.category.value).capitalize()})\n"
                f"{str(self.overview).capitalize()}\n"
            )

            if self.action_items:
                result += f'Action Items:\n{ActionItem.actions_to_string(self.action_items)}\n'

            if self.events:
                result += f'Events:\n{Event.events_to_string(self.events)}\n'
            return result.strip()


__all__ = ['ActionItem', 'Event', 'Insight', 'MeetingType', 'Participant', 'Section', 'Structured']
