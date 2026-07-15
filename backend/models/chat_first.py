"""Strict contracts for chat-first structured-block and proactive-intent admission."""

from datetime import datetime
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


ProactiveIntentSource = Literal['daily_opener', 'capture_arrival', 'deferral_reraise', 'agent_judgment']
ProactiveIntentDeliveryState = Literal['ready', 'delivered']


class ProactiveIntent(_StrictModel):
    """A server-side instruction, not a Chat transcript row.

    The local desktop kernel is the sole writer of the visible assistant turn.
    This record remains ready until that kernel has committed and acknowledged
    its stable ``intent_id``.
    """

    intent_id: StableId
    continuity_key: StableId
    account_generation: int = Field(ge=0)
    source: ProactiveIntentSource
    subject: ChatFirstSubject | None = None
    blocks: list[ChatFirstBlockSpec] = Field(min_length=1, max_length=8)
    delivery_state: ProactiveIntentDeliveryState = 'ready'
    created_at: datetime
    delivered_at: datetime | None = None
    materialization_receipt_id: StableId | None = None

    @property
    def consumes_turn_budget(self) -> bool:
        return self.source == 'agent_judgment'


class ProactiveBudgetReservation(_StrictModel):
    intent_id: StableId
    expires_at: datetime


class ProactiveBudgetState(_StrictModel):
    """Private server accounting for proactive agent turns only."""

    account_generation: int = Field(ge=0)
    materialized_at: list[datetime] = Field(default_factory=list, max_length=64)
    reservations: list[ProactiveBudgetReservation] = Field(default_factory=list, max_length=16)


class ProactiveMaterializationReceipt(_StrictModel):
    """Content-free receipt emitted only after the local journal commits."""

    intent_id: StableId
    receipt_id: StableId


class MaterializePromptsRequest(_StrictModel):
    source_surface: Literal['main_chat']
    control_generation: int = Field(ge=0)
    owner_fence: StableId
    window_foreground: bool = False
    receipts: list[ProactiveMaterializationReceipt] = Field(default_factory=list, max_length=16)

    @model_validator(mode='after')
    def validate_unique_receipts(self):
        intent_ids = [receipt.intent_id for receipt in self.receipts]
        if len(intent_ids) != len(set(intent_ids)):
            raise ValueError('materialization receipt intent IDs must be unique')
        return self


class MaterializePromptsResponse(_StrictModel):
    intents: list[ProactiveIntent] = Field(default_factory=list)


class DeferralCreateRequest(_StrictModel):
    """The idempotent server receiver for the kernel-owned deferral outbox."""

    source_surface: Literal['main_chat']
    control_generation: int = Field(ge=0)
    owner_fence: StableId
    continuity_key: StableId
    subject: ChatFirstSubject
    question: QuestionCardSpec

    @model_validator(mode='after')
    def require_question_subject_match(self):
        if self.question.subject != self.subject:
            raise ValueError('deferral question subject must match the deferred subject')
        return self


class ProactiveDeferral(_StrictModel):
    """Durable, server-side record delivered by the kernel's deferral outbox."""

    deferral_id: StableId
    continuity_key: StableId
    account_generation: int = Field(ge=0)
    subject: ChatFirstSubject
    question: QuestionCardSpec
    created_at: datetime
    due_at: datetime
    state: Literal['pending', 'released'] = 'pending'
    released_intent_id: StableId | None = None


class DeferralReceipt(_StrictModel):
    deferral_id: StableId
    due_at: datetime
    state: Literal['pending', 'released']


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
    'DeferralCreateRequest',
    'DeferralReceipt',
    'GoalLinkSpec',
    'MaterializePromptsRequest',
    'MaterializePromptsResponse',
    'ProactiveBudgetReservation',
    'ProactiveBudgetState',
    'ProactiveDeferral',
    'ProactiveIntent',
    'ProactiveMaterializationReceipt',
    'QuestionCardSpec',
    'QuestionOption',
    'TaskCardSpec',
    'stable_block_id',
]
