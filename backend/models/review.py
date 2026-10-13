"""Review v1 wire contract shared with the mobile client."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from models.dream_edit import Edit, Term

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


class SpellingItem(BaseModel):
    term_id: str
    options: list[str] = Field(min_length=2, max_length=3)
    allow_custom: bool


class AgentProposalItem(BaseModel):
    target_label: str = ''
    other_label: Optional[str] = None
    edit: Optional[Edit] = None
    vocabulary: Optional[Term] = None

    @model_validator(mode='after')
    def single_operation(self):
        if (self.edit is not None) + (self.vocabulary is not None) != 1:
            raise ValueError('Exactly one agent operation is required')
        return self


class ReviewQuestionPayload(BaseModel):
    """Shared question payload, without choosing a legacy or Dream evidence contract."""

    item_id: str
    kind: ReviewKind
    title: str
    created_at: datetime
    speaker: Optional[SpeakerItem] = None
    task: Optional[TaskItem] = None
    same_person: Optional[SamePersonItem] = None
    spelling: Optional[SpellingItem] = None

    @model_validator(mode='after')
    def matching_payload(self):
        arms = ['speaker', 'task', 'same_person', 'spelling', 'agent_proposal']
        if [arm for arm in arms if getattr(self, arm, None) is not None] != [self.kind]:
            raise ValueError('Exactly the matching kind payload is required')
        return self


class ReviewItem(ReviewQuestionPayload):
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


class ReviewChange(BaseModel):
    change_id: str
    kind: Literal[
        'rename', 'merge_memories', 'update_person', 'label_speaker', 'title_conversation', 'close_task', 'other'
    ]
    title: str
    reason: Optional[str] = None
    snippet: Optional[str] = None
    refs: list[ChangeRef] = Field(default_factory=list)
    created_at: datetime
    undone: bool = False


class ReviewChangesResponse(BaseModel):
    changes: list[ReviewChange]
    next_cursor: Optional[str] = None
