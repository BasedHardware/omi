"""Strict, content-free contracts for chat-first structured-block admission."""

from hashlib import sha256
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from models.task_intelligence import StableId


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


class ChatFirstSubject(_StrictModel):
    kind: Literal['task', 'goal', 'capture']
    id: StableId


class QuestionOption(_StrictModel):
    option_id: StableId
    label: str = Field(min_length=1, max_length=80)
    prepared_answer: str = Field(min_length=1, max_length=500)
    defer: bool = False


class QuestionCardSpec(_StrictModel):
    type: Literal['questionCard']
    question_id: StableId
    text: str = Field(min_length=1, max_length=300)
    subject: ChatFirstSubject
    options: list[QuestionOption] = Field(min_length=1, max_length=4)

    @model_validator(mode='after')
    def validate_options(self):
        option_ids = [option.option_id for option in self.options]
        if len(option_ids) != len(set(option_ids)):
            raise ValueError('question option IDs must be unique')
        if sum(option.defer for option in self.options) > 1:
            raise ValueError('question card may contain at most one defer option')
        return self


class TaskCardSpec(_StrictModel):
    type: Literal['taskCard']
    task_id: StableId


class GoalLinkSpec(_StrictModel):
    type: Literal['goalLink']
    goal_id: StableId
    summary: str = Field(min_length=1, max_length=200)


class CaptureLinkSpec(_StrictModel):
    type: Literal['captureLink']
    conversation_id: StableId
    moment_timestamp_ms: int | None = Field(default=None, ge=0)
    summary: str = Field(min_length=1, max_length=200)


ChatFirstBlockSpec = Annotated[
    Union[QuestionCardSpec, TaskCardSpec, GoalLinkSpec, CaptureLinkSpec],
    Field(discriminator='type'),
]


class ChatFirstBlockValidationRequest(_StrictModel):
    source_surface: Literal['main_chat']
    control_generation: int = Field(ge=0)
    owner_fence: StableId
    run_id: StableId
    attempt_id: StableId
    blocks: list[ChatFirstBlockSpec] = Field(min_length=1, max_length=8)


class ChatFirstBlockValidationReceipt(_StrictModel):
    accepted: bool
    code: Literal[
        'accepted',
        'capability_unavailable',
        'generation_mismatch',
        'entity_unavailable',
        'invalid_request',
    ]
    blocks: list[dict[str, object]] = Field(default_factory=list)


def stable_block_id(*, uid: str, generation: int, block: ChatFirstBlockSpec) -> str:
    """Generate an opaque, retry-stable block ID without exposing block text."""

    canonical = block.model_dump_json(exclude_none=True)
    digest = sha256(f'{uid}:{generation}:{canonical}'.encode()).hexdigest()[:24]
    return f'cfb_{digest}'


__all__ = [
    'CaptureLinkSpec',
    'ChatFirstBlockSpec',
    'ChatFirstBlockValidationReceipt',
    'ChatFirstBlockValidationRequest',
    'ChatFirstSubject',
    'GoalLinkSpec',
    'QuestionCardSpec',
    'QuestionOption',
    'TaskCardSpec',
    'stable_block_id',
]
