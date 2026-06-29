from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from models.conversation_enums import CategoryEnum
from models.structured import ActionItem, Event, Structured


class ExtractedActionItem(BaseModel):
    description: str = Field(description="The action item to be completed")
    due_at: Optional[datetime] = Field(default=None, description="When the action item is due")

    def to_action_item(self) -> ActionItem:
        return ActionItem(description=self.description, due_at=self.due_at)


class ActionItemsExtraction(BaseModel):
    action_items: List[ExtractedActionItem] = Field(
        description="A list of action items from the conversation",
        default=[],
    )

    def to_action_items(self) -> List[ActionItem]:
        return [item.to_action_item() for item in self.action_items]


class ExtractedEvent(BaseModel):
    title: str = Field(description="The title of the event")
    description: str = Field(description="A brief description of the event", default='')
    start: datetime = Field(description="The start date and time of the event")
    duration: int = Field(description="The duration of the event in minutes", default=30)

    def to_event(self) -> Event:
        return Event(
            title=self.title,
            description=self.description,
            start=self.start,
            duration=self.duration,
            created=False,
        )


class StructuredExtraction(BaseModel):
    title: str = Field(description="A title/name for this conversation", default='')
    overview: str = Field(
        description="A brief overview of the conversation, highlighting the key details from it",
        default='',
    )
    emoji: str = Field(description="An emoji to represent the conversation", default='🧠')
    category: CategoryEnum = Field(description="A category for this conversation", default=CategoryEnum.other)
    action_items: List[ExtractedActionItem] = Field(
        description="A list of action items from the conversation",
        default=[],
    )
    events: List[ExtractedEvent] = Field(
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

    def to_structured(self) -> Structured:
        return Structured(
            title=self.title,
            overview=self.overview,
            emoji=self.emoji,
            category=self.category,
            action_items=[item.to_action_item() for item in self.action_items],
            events=[event.to_event() for event in self.events],
        )
