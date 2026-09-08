import logging
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Tuple, Type

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from models.conversation_enums import CategoryEnum
from models.structured import ActionItem, Event, Section, Structured

logger = logging.getLogger(__name__)

CAPTURE_OWNERS: Tuple[str, ...] = ('user', 'other', 'unknown')

# The extractor is asked for a fixed vocabulary on these fields, but it answers outside of it often
# enough to matter: on 2026-08-19 it returned a speaker's name for capture_owner on three items of
# one conversation, pydantic raised literal_error, and the whole StructuredExtraction failed to
# parse — so conversation processing returned HTTP 500 and the user got no summary at all. One
# out-of-vocabulary token must never cost the conversation; an unusable value is worth exactly as
# much as the field being absent, which is what these Optionals already model.
_OPTIONAL_LITERAL_VOCABULARIES: Dict[str, Tuple[str, ...]] = {
    'capture_kind': ('explicit_command', 'clear_commitment', 'direct_request', 'inferred_next_step'),
    'capture_owner': CAPTURE_OWNERS,
    'due_certainty': ('confirmed', 'tentative'),
    'candidate_action': ('create', 'update', 'complete'),
}

# The same principle applies one level up. Every list on the extraction is optional detail --
# `default_factory=list` already says an empty one is a valid conversation -- but pydantic fails the
# WHOLE model when a single element is unusable, so one malformed item costs the user their title,
# summary and every other item. That is what shipped: on 2026-08-17/18 the extractor answered
# `duration: 0` for an event, value_error propagated out of `_get_structured`, and the conversation
# came back HTTP 500 with no summary at all; 30 more `Conversation processing failed: ValidationError`
# 500s on POST /v1/dev/user/conversations followed on 2026-08-20. Drop the element the extractor made
# unusable and keep the conversation, and log which field it was -- the prod signature carried no
# traceback, so there was no way to tell one of these apart from the next.
_DEFAULTED_SCALARS: Tuple[str, ...] = ('title', 'overview', 'emoji')


def _usable_elements(values: Any, element_model: Type[BaseModel], field: str) -> Any:
    if not isinstance(values, list):
        return values

    usable: List[Any] = []
    for element in values:
        if isinstance(element, element_model):
            usable.append(element)
            continue
        try:
            usable.append(element_model.model_validate(element))
        except ValidationError as error:
            # `include_input=False` is what keeps the extractor's text -- the user's own words --
            # out of the log; location and error type are all that is needed to name the field.
            logger.warning(
                'Dropping unusable %s element from conversation extraction: %s',
                field,
                [
                    f"{'.'.join(str(part) for part in item['loc'])}: {item['type']}"
                    for item in error.errors(include_input=False)
                ],
            )
    return usable


def _keep_usable_content(data: Any, element_models: Dict[str, Type[BaseModel]]) -> Any:
    if not isinstance(data, dict):
        return data

    coerced = dict(data)
    for field in _DEFAULTED_SCALARS:
        if coerced.get(field, '') is None:
            del coerced[field]
    for field, element_model in element_models.items():
        if field not in coerced:
            continue
        if coerced[field] is None:
            del coerced[field]
            continue
        coerced[field] = _usable_elements(coerced[field], element_model, field)
    return coerced


class ExtractedActionItem(BaseModel):
    description: str = Field(description="The action item to be completed")
    due_at: Optional[datetime] = Field(default=None, description="When the action item is due")
    capture_kind: Optional[Literal['explicit_command', 'clear_commitment', 'direct_request', 'inferred_next_step']] = (
        None
    )
    capture_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    ownership_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    capture_owner: Optional[Literal['user', 'other', 'unknown']] = None
    owner_name: Optional[str] = None
    context: Optional[str] = None
    due_certainty: Optional[Literal['confirmed', 'tentative']] = None
    concrete_deliverable: Optional[bool] = Field(
        default=None,
        description='True only when the commitment names a concrete deliverable or outcome',
    )
    candidate_action: Optional[Literal['create', 'update', 'complete']] = None
    target_task_id: Optional[str] = None
    source_segment_ids: List[str] = Field(
        default_factory=list,
        description='Transcript segment IDs that directly support this action item',
    )

    @model_validator(mode='before')
    @classmethod
    def drop_out_of_vocabulary_literals(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        coerced = dict(data)
        for field, vocabulary in _OPTIONAL_LITERAL_VOCABULARIES.items():
            value = coerced.get(field)
            if value is None or value in vocabulary:
                continue
            normalized = value.strip().lower() if isinstance(value, str) else None
            if normalized in vocabulary:
                coerced[field] = normalized
                continue
            # A name where an owner class belongs still says the owner is somebody other than the
            # user, and owner_name is where that name is meant to live.
            if field == 'capture_owner' and normalized:
                coerced[field] = 'other'
                if not coerced.get('owner_name'):
                    coerced['owner_name'] = value.strip()
                continue
            coerced[field] = None
        return coerced

    def to_action_item(self) -> ActionItem:
        return ActionItem(
            description=self.description,
            due_at=self.due_at,
            capture_kind=self.capture_kind,
            capture_confidence=self.capture_confidence,
            ownership_confidence=self.ownership_confidence,
            capture_owner=self.capture_owner,
            owner_name=self.owner_name,
            context=self.context,
            due_certainty=self.due_certainty,
            concrete_deliverable=self.concrete_deliverable,
            candidate_action=self.candidate_action,
            target_task_id=self.target_task_id,
            source_segment_ids=self.source_segment_ids,
        )


class ActionItemsExtraction(BaseModel):
    action_items: List[ExtractedActionItem] = Field(
        description="A list of action items from the conversation",
        default_factory=list,
    )

    @model_validator(mode='before')
    @classmethod
    def keep_usable_content(cls, data: Any) -> Any:
        return _keep_usable_content(data, {'action_items': ExtractedActionItem})

    def to_action_items(self) -> List[ActionItem]:
        return [item.to_action_item() for item in self.action_items]


class ConversationStructureExtraction(BaseModel):
    title: str = Field(description="A title/name for this conversation", default='')
    overview: str = Field(
        description="A brief overview of the conversation, highlighting the key details from it",
        default='',
    )
    emoji: str = Field(description="An emoji to represent the conversation", default='🧠')
    category: CategoryEnum = Field(description="A category for this conversation", default=CategoryEnum.other)

    @field_validator('category', mode='before')
    @classmethod
    def set_category_default_on_error(cls, v: Any) -> CategoryEnum:
        if isinstance(v, CategoryEnum):
            return v
        try:
            return CategoryEnum(v)
        except ValueError:
            return CategoryEnum.other


class ExtractedEvent(BaseModel):
    title: str = Field(description="The title of the event")
    description: str = Field(description="A brief description of the event", default='')
    start: datetime = Field(description="The start date and time of the event")
    duration: int = Field(description="The duration of the event in minutes", default=30)

    @model_validator(mode='before')
    @classmethod
    def default_unusable_duration(cls, data: Any) -> Any:
        """Fall back to the documented default instead of rejecting the event.

        A non-positive or unparseable duration still leaves a real event on the calendar; the field
        already declares 30 minutes as its answer for "the extractor did not say", which is exactly
        what a `0` means here.
        """
        if not isinstance(data, dict) or 'duration' not in data:
            return data

        try:
            minutes = int(data['duration'])
        except (TypeError, ValueError):
            minutes = 0

        coerced = dict(data)
        if minutes > 0:
            coerced['duration'] = minutes
        else:
            del coerced['duration']
        return coerced

    def to_event(self) -> Event:
        return Event(
            title=self.title,
            description=self.description,
            start=self.start,
            duration=self.duration,
            created=False,
        )


class ExtractedSection(BaseModel):
    heading: str = Field(description='A descriptive heading chosen for this conversation')
    body_markdown: str = Field(description='Free-form markdown containing the section details')
    source_segment_ids: List[str] = Field(
        default_factory=list,
        description='Transcript segment IDs that directly support this section',
    )

    def to_section(self) -> Section:
        return Section(
            heading=self.heading,
            body_markdown=self.body_markdown,
            source_segment_ids=self.source_segment_ids,
        )


class StructuredExtraction(BaseModel):
    title: str = Field(description="A title/name for this conversation", default='')
    overview: str = Field(
        description="A brief overview of the conversation, highlighting the key details from it",
        default='',
    )
    emoji: str = Field(description="An emoji to represent the conversation", default='🧠')
    category: CategoryEnum = Field(description="A category for this conversation", default=CategoryEnum.other)
    sections: List[ExtractedSection] = Field(
        description='Detailed, free-form note sections in the model-chosen structure', default_factory=list
    )
    action_items: List[ExtractedActionItem] = Field(
        description="A list of action items from the conversation",
        default_factory=list,
    )
    events: List[ExtractedEvent] = Field(
        description="A list of events extracted from the conversation, that the user must have on his calendar.",
        default_factory=list,
    )

    @model_validator(mode='before')
    @classmethod
    def keep_usable_content(cls, data: Any) -> Any:
        return _keep_usable_content(
            data,
            {'sections': ExtractedSection, 'action_items': ExtractedActionItem, 'events': ExtractedEvent},
        )

    @field_validator('category', mode='before')
    @classmethod
    def set_category_default_on_error(cls, v: Any) -> CategoryEnum:
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
            sections=[section.to_section() for section in self.sections],
            action_items=[item.to_action_item() for item in self.action_items],
            events=[event.to_event() for event in self.events],
        )
