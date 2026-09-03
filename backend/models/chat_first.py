"""Strict contracts for chat-first structured-block and proactive-intent admission."""

from datetime import datetime
from hashlib import sha256
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from models.task_intelligence import StableId


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


class ChatFirstSubject(_StrictModel):
    kind: Literal['task', 'goal', 'capture', 'cold_start']
    id: StableId


class QuestionOption(_StrictModel):
    option_id: StableId
    label: str = Field(min_length=1, max_length=80)
    prepared_answer: str = Field(min_length=1, max_length=500)
    defer: bool = False


class ColdStartSequence(_StrictModel):
    """Explicit local-only identity for the fixed sparse cold-start script."""

    sequence_id: StableId
    step: int = Field(ge=1, le=3)


class QuestionCardSpec(_StrictModel):
    type: Literal['questionCard']
    question_id: StableId
    text: str = Field(min_length=1, max_length=300)
    subject: ChatFirstSubject
    options: list[QuestionOption] = Field(min_length=1, max_length=4)
    cold_start_sequence: ColdStartSequence | None = None

    @model_validator(mode='after')
    def validate_options(self):
        option_ids = [option.option_id for option in self.options]
        if len(option_ids) != len(set(option_ids)):
            raise ValueError('question option IDs must be unique')
        if sum(option.defer for option in self.options) > 1:
            raise ValueError('question card may contain at most one defer option')
        is_cold_start = self.subject.kind == 'cold_start'
        if is_cold_start != (self.cold_start_sequence is not None):
            raise ValueError('cold-start subject and sequence descriptor must be paired')
        if self.cold_start_sequence is not None:
            if self.subject.id != self.cold_start_sequence.sequence_id:
                raise ValueError('cold-start subject must match sequence identity')
            if self.cold_start_sequence.step != 1:
                raise ValueError('server cold-start intent must begin at sequence step one')
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


class ConversationLinkActionItemSpec(_StrictModel):
    description: str = Field(min_length=1, max_length=300)
    task_id: StableId | None = None


class ConversationLinkSpec(_StrictModel):
    type: Literal['conversationLink']
    conversation_id: StableId
    summary: str = Field(min_length=1, max_length=200)
    recommended_action_items: list[ConversationLinkActionItemSpec] = Field(default_factory=list, max_length=8)


class MemoryLinkSpec(_StrictModel):
    type: Literal['memoryLink']
    memory_id: StableId
    summary: str = Field(min_length=1, max_length=200)


class MemoryReviewItemSpec(_StrictModel):
    """One reviewable claim about the owner, as the desktop adapter sends it.

    ``content`` and ``category`` are permitted to arrive empty: the desktop
    adapter forwards whatever the daily-summary block carried, and the client
    codec — not this contract — decides an empty row is not worth rendering.
    Rejecting the whole card over one blank field would journal nothing at all.
    """

    memory_id: StableId
    content: str = Field(max_length=1000)
    category: str = Field(default='', max_length=64)


class MemoryReviewCardSpec(_StrictModel):
    """The daily-summary review rows, journaled through the chat-first tool.

    ``summary_id`` and ``date`` are opaque provenance the card carries back to
    its summary; the adapter substitutes an empty string when the source block
    had neither, so neither is an identity this contract can constrain.
    """

    type: Literal['memoryReviewCard']
    summary_id: str = Field(default='', max_length=128)
    date: str = Field(default='', max_length=32)
    # The generator selects three (``MEMORIES_LEARNED_LIMIT``); the bound is the
    # ceiling on the entity reads one card costs, not a product limit.
    items: list[MemoryReviewItemSpec] = Field(min_length=1, max_length=8)


ChatFirstBlockSpec = Annotated[
    Union[
        QuestionCardSpec,
        TaskCardSpec,
        GoalLinkSpec,
        CaptureLinkSpec,
        ConversationLinkSpec,
        MemoryLinkSpec,
    ],
    Field(discriminator='type'),
]

# What a client may ask the journal to accept, which is a superset of what the
# server emits. ``memoryReviewCard`` is authored by the daily-summary card on the
# client and journaled back; no proactive intent ever produces one. Keeping it out
# of ``ChatFirstBlockSpec`` keeps it out of the materialization *response* schema,
# where a new union branch is a breaking change for every released app client.
ChatFirstJournalBlockSpec = Annotated[
    Union[
        QuestionCardSpec,
        TaskCardSpec,
        GoalLinkSpec,
        CaptureLinkSpec,
        ConversationLinkSpec,
        MemoryLinkSpec,
        MemoryReviewCardSpec,
    ],
    Field(discriminator='type'),
]

LegacyChatFirstBlockSpec = Annotated[
    Union[QuestionCardSpec, TaskCardSpec, GoalLinkSpec, CaptureLinkSpec, MemoryLinkSpec],
    Field(discriminator='type'),
]


class ChatFirstBlockValidationRequest(_StrictModel):
    source_surface: Literal['main_chat']
    control_generation: int = Field(ge=0)
    owner_fence: StableId
    run_id: StableId
    attempt_id: StableId
    blocks: list[ChatFirstJournalBlockSpec] = Field(min_length=1, max_length=8)


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


ProactiveIntentSource = Literal[
    'daily_opener',
    'capture_arrival',
    'deferral_reraise',
    'agent_judgment',
    'cold_start_rich',
    'cold_start_sparse',
]
ProactiveIntentDeliveryState = Literal['ready', 'pending_kernel_receipt', 'delivered', 'dead_letter']
MaterializableProactiveIntentDeliveryState = Literal['ready', 'pending_kernel_receipt', 'delivered']
ColdStartSequenceTerminalState = Literal['completed', 'abandoned']


class ProactiveIntent(_StrictModel):
    """A server-side instruction, not a Chat transcript row.

    The local desktop kernel is the sole writer of the visible assistant turn.
    This record remains deliverable until that kernel has committed and
    acknowledged its stable ``intent_id``; cold-start intents make that
    explicit as ``pending_kernel_receipt``.
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
    materialization_attempts: int = Field(default=0, ge=0)
    last_rejection_code: str | None = Field(default=None, min_length=1, max_length=64, pattern=r'^[a-z0-9_]+$')
    last_rejection_at: datetime | None = None
    fetch_count: int = Field(default=0, ge=0)
    last_fetched_at: datetime | None = None
    first_deferred_at: datetime | None = None
    last_deferral_at: datetime | None = None
    dead_letter_reason: str | None = Field(default=None, min_length=1, max_length=128, pattern=r'^[a-z0-9_:.-]+$')
    requeue_count: int = Field(default=0, ge=0, le=1)
    # This is a terminal local-journal receipt on the same sparse cold-start
    # intent, never an operator-owned completion switch. It is the bounded
    # server projection needed to stop suppressing agent-tier turns once the
    # sequence has actually ended in the canonical transcript.
    cold_start_sequence_terminal_state: ColdStartSequenceTerminalState | None = None
    cold_start_sequence_terminal_receipt_id: StableId | None = None

    # Firestore documents outlive individual backend revisions.  Stored-state
    # readers must tolerate fields written by newer revisions during rolling
    # deploys; request/response models remain strict.
    model_config = ConfigDict(extra='ignore', frozen=True)

    @field_validator('delivery_state', mode='before')
    @classmethod
    def unknown_delivery_states_are_terminal_on_read(cls, value):
        return value if value in {'ready', 'pending_kernel_receipt', 'delivered', 'dead_letter'} else 'dead_letter'

    @model_validator(mode='after')
    def validate_cold_start_sequence_state(self):
        has_terminal_receipt = self.cold_start_sequence_terminal_receipt_id is not None
        has_terminal_state = self.cold_start_sequence_terminal_state is not None
        if has_terminal_receipt != has_terminal_state:
            raise ValueError('cold-start terminal state and receipt must be paired')
        if self.source == 'cold_start_sparse':
            if self.subject is None or self.subject.kind != 'cold_start':
                raise ValueError('sparse cold-start intent requires a cold-start subject')
        elif has_terminal_receipt:
            raise ValueError('only sparse cold-start intents may carry a terminal receipt')
        return self

    @property
    def consumes_turn_budget(self) -> bool:
        return self.source == 'agent_judgment'


class DeadLetteredProactiveIntent(ProactiveIntent):
    """Full terminal record stored outside the rolling reader's collection."""

    delivery_state: Literal['dead_letter'] = 'dead_letter'  # pyright: ignore[reportIncompatibleVariableOverride]
    dead_letter_reason: str = Field(  # pyright: ignore[reportIncompatibleVariableOverride]
        default='unknown', min_length=1, max_length=128, pattern=r'^[a-z0-9_:.-]+$'
    )


class MaterializableProactiveIntent(_StrictModel):
    """Wire-safe intent state; terminal dead letters never leave the store."""

    intent_id: StableId
    continuity_key: StableId
    account_generation: int = Field(ge=0)
    source: ProactiveIntentSource
    subject: ChatFirstSubject | None = None
    blocks: list[ChatFirstBlockSpec] = Field(min_length=1, max_length=8)
    delivery_state: MaterializableProactiveIntentDeliveryState = 'ready'
    created_at: datetime
    delivered_at: datetime | None = None
    materialization_receipt_id: StableId | None = None
    materialization_attempts: int = Field(default=0, ge=0)
    requeue_count: int = Field(default=0, ge=0, le=1, exclude=True)
    last_rejection_code: str | None = Field(default=None, min_length=1, max_length=64, pattern=r'^[a-z0-9_]+$')
    last_rejection_at: datetime | None = None
    fetch_count: int = Field(default=0, ge=0)
    last_fetched_at: datetime | None = None
    dead_letter_reason: str | None = Field(default=None, min_length=1, max_length=128, pattern=r'^[a-z0-9_:.-]+$')
    cold_start_sequence_terminal_state: ColdStartSequenceTerminalState | None = None
    cold_start_sequence_terminal_receipt_id: StableId | None = None


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


class ProactiveMaterializationRejection(_StrictModel):
    """Content-free typed rejection emitted by the local kernel."""

    intent_id: StableId
    code: str = Field(min_length=1, max_length=64, pattern=r'^[a-z0-9_]+$')
    message: str | None = Field(default=None, max_length=300)


class ProactiveMaterializationDeferral(_StrictModel):
    """A fetched intent the kernel intentionally left behind a transcript tail."""

    intent_id: StableId
    code: Literal['tail_question', 'streaming_tail']


class ProactiveMaterializationReceiptOutcome(_StrictModel):
    intent_id: StableId
    outcome: Literal['acknowledged', 'already_terminal', 'missing', 'conflict', 'generation_mismatch']


class ProactiveMaterializationRejectionOutcome(_StrictModel):
    intent_id: StableId
    outcome: Literal['recorded', 'absorbed', 'generation_mismatch', 'malformed', 'missing']


class ColdStartSequenceTerminalReceipt(_StrictModel):
    """A durable local-journal acknowledgement that sparse sequencing ended."""

    sequence_id: StableId
    receipt_id: StableId
    terminal_state: ColdStartSequenceTerminalState


class MaterializePromptsRequest(_StrictModel):
    source_surface: Literal['main_chat']
    control_generation: int = Field(ge=0)
    owner_fence: StableId
    window_foreground: bool = False
    initial_page_loaded: bool = False
    receipts: list[ProactiveMaterializationReceipt] = Field(default_factory=list, max_length=16)
    rejections: list[ProactiveMaterializationRejection] = Field(default_factory=list, max_length=16)
    deferrals: list[ProactiveMaterializationDeferral] = Field(default_factory=list, max_length=16)
    cold_start_sequence_terminal_receipts: list[ColdStartSequenceTerminalReceipt] = Field(
        default_factory=list, max_length=16
    )

    @model_validator(mode='after')
    def validate_unique_receipts(self):
        intent_ids = [receipt.intent_id for receipt in self.receipts]
        if len(intent_ids) != len(set(intent_ids)):
            raise ValueError('materialization receipt intent IDs must be unique')
        rejection_ids = [rejection.intent_id for rejection in self.rejections]
        if len(rejection_ids) != len(set(rejection_ids)):
            raise ValueError('materialization rejection intent IDs must be unique')
        if set(intent_ids) & set(rejection_ids):
            raise ValueError('an intent cannot be both acknowledged and rejected')
        deferral_ids = [deferral.intent_id for deferral in self.deferrals]
        if len(deferral_ids) != len(set(deferral_ids)):
            raise ValueError('materialization deferral intent IDs must be unique')
        if set(intent_ids) & set(deferral_ids) or set(rejection_ids) & set(deferral_ids):
            raise ValueError('an intent cannot have more than one materialization outcome')
        sequence_ids = [receipt.sequence_id for receipt in self.cold_start_sequence_terminal_receipts]
        if len(sequence_ids) != len(set(sequence_ids)):
            raise ValueError('cold-start terminal receipt sequence IDs must be unique')
        return self


class MaterializePromptsResponse(_StrictModel):
    intents: list[MaterializableProactiveIntent] = Field(default_factory=list)
    receipt_outcomes: list[ProactiveMaterializationReceiptOutcome] = Field(default_factory=list)
    rejection_outcomes: list[ProactiveMaterializationRejectionOutcome] = Field(default_factory=list)

    @field_validator('intents', mode='before')
    @classmethod
    def narrow_internal_intents_for_wire(cls, intents):
        return [
            (
                intent.model_dump(exclude={'first_deferred_at', 'last_deferral_at'})
                if isinstance(intent, ProactiveIntent)
                else intent
            )
            for intent in intents
        ]


class LegacyProactiveIntent(_StrictModel):
    intent_id: StableId
    continuity_key: StableId
    account_generation: int = Field(ge=0)
    source: ProactiveIntentSource
    subject: ChatFirstSubject | None = None
    blocks: list[LegacyChatFirstBlockSpec] = Field(min_length=1, max_length=8)
    delivery_state: MaterializableProactiveIntentDeliveryState = 'ready'
    created_at: datetime
    delivered_at: datetime | None = None
    materialization_receipt_id: StableId | None = None
    materialization_attempts: int = Field(default=0, ge=0)
    last_rejection_code: str | None = None
    last_rejection_at: datetime | None = None
    fetch_count: int = Field(default=0, ge=0)
    last_fetched_at: datetime | None = None
    dead_letter_reason: str | None = None
    cold_start_sequence_terminal_state: ColdStartSequenceTerminalState | None = None
    cold_start_sequence_terminal_receipt_id: StableId | None = None


class LegacyMaterializePromptsResponse(_StrictModel):
    intents: list[LegacyProactiveIntent] = Field(default_factory=list)


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
        if self.subject.kind == 'cold_start':
            raise ValueError('cold-start question cards cannot be deferred')
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


def stable_block_id(*, uid: str, generation: int, block: ChatFirstJournalBlockSpec) -> str:
    """Generate an opaque, retry-stable block ID without exposing block text."""

    canonical = block.model_dump_json(exclude_none=True)
    digest = sha256(f'{uid}:{generation}:{canonical}'.encode()).hexdigest()[:24]
    return f'cfb_{digest}'


__all__ = [
    'CaptureLinkSpec',
    'ConversationLinkSpec',
    'ChatFirstBlockSpec',
    'ChatFirstJournalBlockSpec',
    'ChatFirstBlockValidationReceipt',
    'ChatFirstBlockValidationRequest',
    'ChatFirstSubject',
    'ColdStartSequenceTerminalReceipt',
    'ColdStartSequenceTerminalState',
    'ColdStartSequence',
    'DeferralCreateRequest',
    'DeferralReceipt',
    'GoalLinkSpec',
    'MaterializePromptsRequest',
    'MaterializePromptsResponse',
    'MemoryLinkSpec',
    'MemoryReviewCardSpec',
    'MemoryReviewItemSpec',
    'ProactiveBudgetReservation',
    'ProactiveBudgetState',
    'ProactiveDeferral',
    'ProactiveIntent',
    'ProactiveMaterializationReceipt',
    'ProactiveMaterializationRejection',
    'QuestionCardSpec',
    'QuestionOption',
    'TaskCardSpec',
    'stable_block_id',
]
