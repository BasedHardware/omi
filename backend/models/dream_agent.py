"""Typed dream tools. Evidence references address records already read this pass."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from models.review import ReviewItem


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Cluster(Strict):
    refs: list[str] = Field(min_length=1, max_length=20)
    problem: Literal['spelling', 'duplicates', 'entity', 'tasks', 'quality']


class Triage(Strict):
    clusters: list[Cluster] = Field(default_factory=list, max_length=12)


class Edit(Strict):
    kind: Literal[
        'spelling',
        'title',
        'overview',
        'memory',
        'merge_people',
        'entity_summary',
        'close_task',
        'retire_task',
        'merge_memories',
    ]
    target: str
    other: str = ''
    before: str = ''
    after: str = ''
    reason: str = Field(min_length=1, max_length=1000)
    evidence: list[str] = Field(min_length=1, max_length=10)

    @model_validator(mode='after')
    def conversation_summary(self):
        if self.kind in {'title', 'overview'}:
            collection, separator, key = self.target.partition('/')
            if collection != 'conversations' or not separator or not key or '/' in key:
                raise ValueError('Summary edits require a conversation target')
            if self.target not in self.evidence or self.other:
                raise ValueError('Summary edits require their conversation as evidence and no other target')
            limit = 120 if self.kind == 'title' else 1000
            if not self.after.strip() or len(self.after) > limit or self.before == self.after:
                raise ValueError('Summary edits require a short changed value')
        return self


class Term(Strict):
    kind: Literal['person', 'organization', 'project', 'jargon']
    spelling: str = Field(min_length=1, max_length=50)
    aliases: list[str] = Field(default_factory=list, max_length=5)
    evidence: list[str] = Field(min_length=1, max_length=10)


class FrameQuestion(Strict):
    screen_ref: str
    question: str = Field(min_length=1, max_length=500)


class Feedback(Strict):
    component: Literal['transcription', 'notes', 'memory', 'people', 'entities', 'tasks', 'dream']
    failure_class: Literal[
        'spelling', 'duplicate', 'missing_evidence', 'stale_state', 'routing', 'budget', 'success', 'none', 'ok'
    ]
    severity: Literal['info', 'warning', 'error']
    count: int = Field(ge=1, le=10000)
    latency_ms: float = Field(ge=0, le=3600000, allow_inf_nan=False)
    error_rate: float = Field(ge=0, le=1, allow_inf_nan=False)
    reproduction: str = Field(min_length=1, max_length=500)


class SlowTask(Strict):
    description: str = Field(min_length=1, max_length=4096)
    evidence: list[str] = Field(min_length=1, max_length=10)


class Plan(Strict):
    edits: list[Edit] = Field(default_factory=list, max_length=50)
    questions: list[ReviewItem] = Field(default_factory=list, max_length=3)
    vocabulary: list[Term] = Field(default_factory=list, max_length=100)
    frames: list[FrameQuestion] = Field(default_factory=list, max_length=3)
    feedback: list[Feedback] = Field(default_factory=list, max_length=10)
    slow_tasks: list[SlowTask] = Field(default_factory=list, max_length=3)
