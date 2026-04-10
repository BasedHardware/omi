from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from models.conversation_enums import CategoryEnum


class ActionItem(BaseModel):
    description: str = Field(description="The action item to be completed")
    completed: bool = False
    created_at: Optional[datetime] = Field(default=None, description="When the action item was created")
    updated_at: Optional[datetime] = Field(default=None, description="When the action item was last updated")
    due_at: Optional[datetime] = Field(default=None, description="When the action item is due")
    completed_at: Optional[datetime] = Field(default=None, description="When the action item was completed")
    conversation_id: Optional[str] = Field(
        default=None, description="ID of the conversation this action item came from"
    )

    @staticmethod
    def actions_to_string(action_items: List['ActionItem']) -> str:
        if not action_items:
            return 'None'

        result = []
        for item in action_items:
            status = 'completed' if item.completed else 'pending'
            line = f"- {item.description} ({status})"

            # Add timestamp information
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
    title: str = Field(description="The title of the event")
    description: str = Field(description="A brief description of the event", default='')
    start: datetime = Field(description="The start date and time of the event")
    duration: int = Field(description="The duration of the event in minutes", default=30)
    created: bool = False

    def as_dict_cleaned_dates(self):
        event_dict = self.dict()
        event_dict['start'] = event_dict['start'].isoformat()
        return event_dict

    @staticmethod
    def events_to_string(events: List['Event']) -> str:
        if not events:
            return 'None'
        # Format the datetime for better readability in the prompt
        return '\n'.join(
            [
                f"- {event.title} (Starts: {event.start.strftime('%Y-%m-%d %H:%M:%S %Z')}, Duration: {event.duration} mins)"
                for event in events
            ]
        )


class ActionItemsExtraction(BaseModel):
    action_items: List[ActionItem] = Field(description="A list of action items from the conversation", default=[])


class Structured(BaseModel):
    title: str = Field(description="A title/name for this conversation", default='')
    overview: str = Field(
        description="A brief overview of the conversation, highlighting the key details from it",
        default='',
    )
    emoji: str = Field(description="An emoji to represent the conversation", default='🧠')
    category: CategoryEnum = Field(description="A category for this conversation", default=CategoryEnum.other)
    action_items: List[ActionItem] = Field(description="A list of action items from the conversation", default=[])
    events: List[Event] = Field(
        description="A list of events extracted from the conversation, that the user must have on his calendar.",
        default=[],
    )

    @field_validator('category', mode='before')
    @classmethod
    def set_category_default_on_error(cls, v: any) -> 'CategoryEnum':
        if isinstance(v, CategoryEnum):
            return v
        try:
            return CategoryEnum(v)
        except ValueError:
            return CategoryEnum.other

    def __str__(self):
        result = (
            f"{str(self.title).capitalize()} ({str(self.category.value).capitalize()})\n"
            f"{str(self.overview).capitalize()}\n"
        )

        if self.action_items:
            result += f"Action Items:\n{ActionItem.actions_to_string(self.action_items)}\n"

        if self.events:
            result += f"Events:\n{Event.events_to_string(self.events)}\n"
        return result.strip()
