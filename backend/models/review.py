"""Review v1 wire contract shared with the mobile client."""

from datetime import datetime
from typing import Literal, Optional, get_args

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator, model_serializer

from models.dream_edit import Edit, MemoryHygieneEdit, Term
from models.agent_edit import HarnessEdit

EntityType = Literal['person', 'organization', 'project']
ReviewKind = Literal['speaker', 'task', 'same_person', 'spelling']
ReviewKindV2 = Literal['speaker', 'task', 'same_person', 'spelling', 'agent_proposal']


class PersonRef(BaseModel):
    person_id: str
    name: str
    organization: Optional[str] = None


class EntityRef(BaseModel):
    entity_id: str
    type: EntityType
    name: str


class EntitySummary(EntityRef):
    subtitle: Optional[str] = None
    conversation_count: int = Field(default=0, ge=0)
    signals: list[str] = Field(default_factory=list)


class ReviewEvidence(BaseModel):
    quote: str
    speaker_label: Optional[str] = None
    at: Optional[datetime] = None
    conversation_id: Optional[str] = None
    conversation_title: Optional[str] = None


class TranscriptLine(BaseModel):
    speaker_label: str
    text: str
    at: Optional[datetime] = None
    is_target: bool


class SpeakerItem(BaseModel):
    prompt_id: str
    conversation_id: str
    conversation_title: str
    start: float
    end: float
    candidates: list[PersonRef] = Field(default_factory=list, max_length=3)
    affected_conversation_count: int = Field(ge=1)
    context: list[TranscriptLine] = Field(default_factory=list, max_length=3)


class TaskItem(BaseModel):
    candidate_id: str
    description: str
    due_at: Optional[datetime] = None
    workstream_id: Optional[str] = None
    workstream_title: Optional[str] = None
    evidence: Optional[ReviewEvidence] = None


class SamePersonItem(BaseModel):
    left: EntitySummary
    right: EntitySummary
    reason: str


class SpellingContextSegment(BaseModel):
    text: str
    speaker_label: Optional[str] = None
    is_user: bool = False


class SpellingContext(BaseModel):
    conversation_title: str
    conversation_date: Optional[datetime] = None
    segments: list[SpellingContextSegment] = Field(min_length=1, max_length=3)
    main_index: int = Field(ge=0, le=2)
    quote_start: Optional[int] = Field(default=None, ge=0, description='Inclusive UTF-16 offset in the main segment.')
    quote_end: Optional[int] = Field(default=None, ge=0, description='Exclusive UTF-16 offset in the main segment.')


class SpellingQuestionPayload(BaseModel):
    term_id: str
    options: list[str] = Field(min_length=2, max_length=3)
    allow_custom: bool


class SpellingItem(SpellingQuestionPayload):
    context: Optional[SpellingContext] = Field(
        default=None, description='Server-computed surrounding speech for this question.'
    )


class AgentProposalItem(BaseModel):
    target_label: str = ''
    other_label: Optional[str] = None
    # Validated full fact contents for hygiene proposals so approval surfaces
    # show the real row, not the 180-character label prefix. None = not sent.
    target_content: Optional[str] = None
    other_content: Optional[str] = None
    # Retain the existing wire arm: older mobile decoders read `edit` and its
    # string kind, and would drop proposals sent under a new sibling arm.
    edit: Optional[Edit] = None
    operation: Optional[HarnessEdit | MemoryHygieneEdit] = None

    @model_validator(mode='before')
    @classmethod
    def additive_operation(cls, value):
        if not isinstance(value, dict):
            return value
        value = dict(value)
        edit = value.get('operation') or value.get('edit')
        payload = edit.model_dump() if isinstance(edit, BaseModel) else edit
        if payload and (
            isinstance(edit, (HarnessEdit, MemoryHygieneEdit))
            or payload.get('kind') not in get_args(Edit.model_fields['kind'].annotation)
        ):
            value['operation'] = edit
            kind = payload['kind']
            legacy = {
                'retire_memory': 'memory',
                'supersede_memory': 'memory',
                'dismiss_person': 'merge_people',
                'merge_tasks': 'retire_task',
                'merge_conversations': 'overview',
                'set_language': 'overview',
            }.get(kind, kind)
            # Preserve the released response branch and enum. Rich new operation
            # data is additive; acceptance resolves the server-owned operation.
            mirror = {key: payload[key] for key in Edit.model_fields if key in payload}
            mirror['kind'] = legacy
            mirror['other'] = mirror.get('other', '') if legacy in {'merge_people', 'merge_memories'} else ''
            if legacy in {'overview', 'title'}:
                mirror['target'] = payload['target'].split('#')[0]
                mirror['evidence'] = [mirror['target']]
                mirror['before'] = ''
                mirror['after'] = payload.get('after') or payload['reason'][:1000]
            value['edit'] = mirror
        return value

    vocabulary: Optional[Term] = None

    @model_serializer(mode='wrap')
    def preserve_existing_wire(self, handler):
        data = handler(self)
        for field in ('target_content', 'other_content', 'operation'):
            if getattr(self, field) is None:
                data.pop(field, None)
        return data

    @model_validator(mode='after')
    def single_operation(self):
        if sum(item is not None for item in (self.edit, self.vocabulary)) != 1:
            raise ValueError('Exactly one agent operation is required')
        return self


class ReviewQuestionBase(BaseModel):
    """Shared question payload, without choosing a legacy or Dream evidence contract."""

    item_id: str
    kind: ReviewKind
    title: str
    created_at: datetime
    speaker: Optional[SpeakerItem] = None
    task: Optional[TaskItem] = None
    same_person: Optional[SamePersonItem] = None

    @model_validator(mode='after')
    def matching_payload(self):
        arms = ['speaker', 'task', 'same_person', 'spelling', 'agent_proposal']
        if [arm for arm in arms if getattr(self, arm, None) is not None] != [self.kind]:
            raise ValueError('Exactly the matching kind payload is required')
        return self


class ReviewQuestionPayload(ReviewQuestionBase):
    spelling: Optional[SpellingQuestionPayload] = None


class ReviewItem(ReviewQuestionBase):
    spelling: Optional[SpellingItem] = None
    quote: Optional[str] = None
    source_ref: Optional[str] = None


class ReviewItemV2(BaseModel):
    item_id: str
    kind: ReviewKindV2
    title: str
    quote: Optional[str] = None
    source_ref: Optional[str] = None
    created_at: datetime
    speaker: Optional[SpeakerItem] = None
    task: Optional[TaskItem] = None
    same_person: Optional[SamePersonItem] = None
    spelling: Optional[SpellingItem] = None
    agent_proposal: Optional[AgentProposalItem] = None

    @model_validator(mode='after')
    def matching_payload(self):
        arms = ['speaker', 'task', 'same_person', 'spelling', 'agent_proposal']
        if [arm for arm in arms if getattr(self, arm) is not None] != [self.kind]:
            raise ValueError('Exactly the matching kind payload is required')
        return self


class ReviewItemsResponse(BaseModel):
    items: list[ReviewItem] = Field(max_length=3)
    remaining_today: int = Field(ge=0, le=3)


class ReviewItemsResponseV2(BaseModel):
    items: list[ReviewItemV2] = Field(max_length=3)
    remaining_today: int = Field(ge=0, le=3)


class SpeakerAnswer(BaseModel):
    model_config = ConfigDict(extra='forbid')
    person_id: Optional[str] = Field(default=None, min_length=1, max_length=128)
    new_person_name: Optional[str] = Field(default=None, min_length=2, max_length=40)
    is_me: bool = False

    @model_validator(mode='after')
    def single_identity(self):
        if sum([self.person_id is not None, self.new_person_name is not None, self.is_me]) != 1:
            raise ValueError('Choose one speaker identity')
        return self


class TaskAnswer(BaseModel):
    model_config = ConfigDict(extra='forbid')
    decision: Literal['accept', 'dismiss']
    dismiss_reason: Optional[Literal['already_done', 'not_mine', 'not_useful']] = None
    edited_description: Optional[str] = Field(default=None, min_length=1, max_length=4096)
    due_at: Optional[AwareDatetime] = None
    workstream_id: Optional[str] = Field(default=None, min_length=1, max_length=128)


class SamePersonAnswer(BaseModel):
    model_config = ConfigDict(extra='forbid')
    decision: Literal['yes', 'no', 'not_sure']


class SpellingAnswer(BaseModel):
    model_config = ConfigDict(extra='forbid')
    value: str = Field(min_length=1, max_length=200)


class AgentProposalAnswer(BaseModel):
    model_config = ConfigDict(extra='forbid')
    decision: Literal['accept', 'dismiss']


class ReviewAnswer(BaseModel):
    model_config = ConfigDict(extra='forbid')
    speaker: Optional[SpeakerAnswer] = None
    task: Optional[TaskAnswer] = None
    same_person: Optional[SamePersonAnswer] = None
    spelling: Optional[SpellingAnswer] = None
    not_sure: bool = False

    @model_validator(mode='after')
    def single_answer(self):
        count = sum(
            getattr(self, arm, None) is not None
            for arm in ['speaker', 'task', 'same_person', 'spelling', 'agent_proposal']
        )
        if count != (0 if self.not_sure else 1):
            raise ValueError('Supply one answer or generic not_sure')
        return self


class ReviewAnswerV2(BaseModel):
    model_config = ConfigDict(extra='forbid')
    speaker: Optional[SpeakerAnswer] = None
    task: Optional[TaskAnswer] = None
    same_person: Optional[SamePersonAnswer] = None
    spelling: Optional[SpellingAnswer] = None
    agent_proposal: Optional[AgentProposalAnswer] = None
    not_sure: bool = False

    @model_validator(mode='after')
    def single_answer(self):
        count = sum(
            getattr(self, arm) is not None for arm in ['speaker', 'task', 'same_person', 'spelling', 'agent_proposal']
        )
        if count != (0 if self.not_sure else 1):
            raise ValueError('Supply one answer or generic not_sure')
        return self


class ReviewAnswerReceipt(BaseModel):
    item_id: str
    applied: bool
    remaining_today: int


class ChangeRef(BaseModel):
    type: Literal['person', 'organization', 'project', 'conversation', 'memory', 'task']
    id: str
    label: str


class ReviewChangeDiff(BaseModel):
    """Bounded before/after excerpt. Released clients ignore this object.

    ``group_key`` is stable for the same term change across conversations so a
    client can group by change, by conversation, or by term.
    """

    target_label: Optional[str] = Field(default=None, max_length=180)
    field: Optional[str] = Field(default=None, max_length=64)
    before: Optional[str] = Field(default=None, max_length=500)
    after: Optional[str] = Field(default=None, max_length=500)
    context_before: Optional[str] = Field(default=None, max_length=120)
    context_after: Optional[str] = Field(default=None, max_length=120)
    occurrences: Optional[int] = Field(default=None, ge=0, le=10000)
    source_title: Optional[str] = Field(default=None, max_length=200)
    source_started_at: Optional[datetime] = None
    group_key: Optional[str] = Field(default=None, max_length=128)

    @model_serializer(mode='wrap')
    def omit_empty(self, handler):
        data = handler(self)
        return {key: value for key, value in data.items() if value is not None}


class ReviewChange(BaseModel):
    change_id: str
    kind: Literal[
        'rename', 'merge_memories', 'update_person', 'label_speaker', 'title_conversation', 'close_task', 'other'
    ]
    title: str
    reason: Optional[str] = None
    snippet: Optional[str] = None
    edit_kind: Optional[str] = Field(default=None, max_length=64)
    before: Optional[str] = Field(default=None, max_length=4000)
    after: Optional[str] = Field(default=None, max_length=4000)
    context: Optional[SpellingContext] = None
    refs: list[ChangeRef] = Field(default_factory=list)
    created_at: datetime
    undone: bool = False
    diff: Optional[ReviewChangeDiff] = Field(
        default=None,
        description=(
            'Optional before/after excerpt with surrounding context. '
            'Released clients ignore it. Never a whole transcript.'
        ),
    )

    @model_serializer(mode='wrap')
    def omit_empty_diff(self, handler):
        data = handler(self)
        if data.get('diff') is None:
            data.pop('diff', None)
        return data


class ReviewChangesResponse(BaseModel):
    changes: list[ReviewChange]
    next_cursor: Optional[str] = None
