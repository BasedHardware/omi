"""Typed dream tools. Evidence references address records already read this pass."""

from typing import Literal

from datetime import datetime, timezone
import json
from uuid import uuid5, NAMESPACE_URL

from pydantic import Field, model_validator

from models.review import ReviewQuestionPayload
from models.dream_edit import Edit, Term, Strict


class Cluster(Strict):
    refs: list[str] = Field(min_length=1, max_length=20)
    problem: Literal['spelling', 'duplicates', 'entity', 'tasks', 'quality']


class Triage(Strict):
    clusters: list[Cluster] = Field(default_factory=list, max_length=12)


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


class DreamReviewItem(ReviewQuestionPayload):
    item_id: str = Field(default='', description='Assigned by the server; model values are ignored.')
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description='Assigned by the server at creation; model values are ignored.',
    )

    @model_validator(mode='before')
    @classmethod
    def server_identity(cls, value):
        if isinstance(value, dict):
            identity = json.dumps([value.get('kind'), value.get('source_ref'), value.get('quote')], ensure_ascii=False)
            return {
                **value,
                'item_id': str(value.get('kind', 'question')) + ':' + str(uuid5(NAMESPACE_URL, identity)),
                'created_at': datetime.now(timezone.utc),
            }
        return value

    source_ref: str = Field(
        min_length=1,
        description='Supplied record ref containing the exact quote; optional #segment-id or #start-seconds restricts the quote to that transcript segment.',
    )
    quote: str = Field(
        min_length=1,
        description='Exact verbatim quote from source_ref. A question costs user attention; ask only if the answer changes what future agents should believe.',
    )


class Plan(Strict):
    edits: list[Edit] = Field(default_factory=list, max_length=50)
    questions: list[DreamReviewItem] = Field(default_factory=list, max_length=3)
    vocabulary: list[Term] = Field(default_factory=list, max_length=100)
    frames: list[FrameQuestion] = Field(default_factory=list, max_length=3)
    feedback: list[Feedback] = Field(default_factory=list, max_length=10)
    slow_tasks: list[SlowTask] = Field(default_factory=list, max_length=3)
