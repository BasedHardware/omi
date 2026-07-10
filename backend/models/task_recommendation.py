"""Canonical feedback, attention, and What Matters Now contracts."""

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from models.action_item import EvidenceRef
from models.task_intelligence import (
    StableId,
    TaskIntelligenceFeedbackAction,
    TaskIntelligenceFeedbackReason,
    TaskIntelligenceOutcomeCode,
)


class RecommendationSubjectKind(str, Enum):
    candidate = 'candidate'
    task = 'task'
    workstream = 'workstream'
    artifact = 'artifact'
    decision = 'decision'
    agent_open_loop = 'agent_open_loop'


class FeedbackSubjectKind(str, Enum):
    candidate = 'candidate'
    task = 'task'
    workstream = 'workstream'
    artifact = 'artifact'
    decision = 'decision'


class InterventionSurface(str, Enum):
    suggested = 'suggested'
    what_matters_now = 'what_matters_now'


class ContextMatchSignal(str, Enum):
    app = 'app'
    person = 'person'
    document = 'document'
    meeting = 'meeting'


class OpenLoopKind(str, Enum):
    task = 'task'
    artifact = 'artifact'
    decision = 'decision'
    approval = 'approval'
    external_wait = 'external_wait'


class OpenLoopStatus(str, Enum):
    open = 'open'
    blocked = 'blocked'
    awaiting_user = 'awaiting_user'
    awaiting_external = 'awaiting_external'


class DeterministicFacts(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    days_to_due: Optional[float] = None
    someone_blocked: bool = False
    has_concrete_next_action: bool
    focused_goal_linked: bool = False
    context_match_signals: list[ContextMatchSignal] = Field(default_factory=list, max_length=4)
    capture_confidence: float = Field(ge=0, le=1)

    @model_validator(mode='after')
    def require_unique_context_signals(self):
        if len(self.context_match_signals) != len(set(self.context_match_signals)):
            raise ValueError('context_match_signals must be unique')
        return self


class ShortlistEligibility(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    open: bool
    unexpired: bool
    passes_recommendation_gates: bool
    recent_material_activity: bool
    inside_due_window: bool


class Recommendation(BaseModel):
    model_config = ConfigDict(extra='forbid')

    intervention_id: StableId
    output_version: StableId
    subject_kind: RecommendationSubjectKind
    subject_id: StableId
    feedback_subject_kind: FeedbackSubjectKind
    feedback_subject_id: StableId
    destination_task_id: Optional[StableId] = None
    destination_workstream_id: Optional[StableId] = None
    headline: str = Field(min_length=1, max_length=256)
    why_now: str = Field(min_length=1, max_length=1024)
    goal_or_workstream_label: Optional[str] = Field(default=None, max_length=256)
    recommended_action: str = Field(min_length=1, max_length=128)
    alternative_action: Optional[str] = Field(default=None, max_length=128)
    evidence_preview: str = Field(max_length=512)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list, max_length=50)
    dedupe_key: StableId
    expires_at: AwareDatetime


class WhatMattersNowProjection(BaseModel):
    model_config = ConfigDict(extra='forbid')

    schema_version: Literal[1] = 1
    evaluation_id: StableId
    output_version: StableId
    material_version: StableId
    generated_at: AwareDatetime
    expires_at: AwareDatetime
    recommendations: list[Recommendation] = Field(max_length=3)


class FeedbackCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    subject_kind: FeedbackSubjectKind
    subject_id: StableId
    intervention_id: Optional[StableId] = None
    action: TaskIntelligenceFeedbackAction
    reason: Optional[TaskIntelligenceFeedbackReason] = None
    context_snapshot_hash: Optional[str] = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    later_until: Optional[AwareDatetime] = None

    @model_validator(mode='after')
    def validate_action(self):
        if self.reason is not None and self.action != TaskIntelligenceFeedbackAction.dismiss:
            raise ValueError('reason is only valid for dismiss feedback')
        if self.later_until is not None and self.action != TaskIntelligenceFeedbackAction.later:
            raise ValueError('later_until is only valid for later feedback')
        if (
            self.action
            in {
                TaskIntelligenceFeedbackAction.do_now,
                TaskIntelligenceFeedbackAction.later,
                TaskIntelligenceFeedbackAction.dismiss,
            }
            and self.intervention_id is None
        ):
            raise ValueError(f'{self.action.value} feedback requires intervention_id')
        return self


class InterventionCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    surface: InterventionSurface
    subject_kind: FeedbackSubjectKind
    subject_id: StableId
    dedupe_key: StableId
    evidence_refs: list[EvidenceRef] = Field(default_factory=list, max_length=50)
    expires_at: AwareDatetime


class InterventionRecord(InterventionCreate):
    intervention_id: StableId
    attribution_chain_id: StableId
    created_at: AwareDatetime


class FeedbackRecord(FeedbackCreate):
    feedback_id: StableId
    attribution_chain_id: StableId
    created_at: AwareDatetime
    dedupe_key: Optional[StableId] = None
    proposed_completion: bool = False
    proposed_completion_candidate_id: Optional[StableId] = None


class OutcomeCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    attribution_chain_id: StableId
    subject_kind: FeedbackSubjectKind
    subject_id: StableId
    outcome_code: TaskIntelligenceOutcomeCode


class OutcomeRecord(OutcomeCreate):
    outcome_id: StableId
    occurred_at: AwareDatetime


class NormalizedContextMatch(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    subject_kind: RecommendationSubjectKind
    subject_id: StableId
    signals: list[ContextMatchSignal] = Field(min_length=1, max_length=4)

    @model_validator(mode='after')
    def require_unique_signals(self):
        if len(self.signals) != len(set(self.signals)):
            raise ValueError('signals must be unique')
        return self


class NormalizedContextSnapshot(BaseModel):
    """A bounded local match result; raw local context has no field to enter through."""

    model_config = ConfigDict(extra='forbid')

    schema_version: Literal[1] = 1
    device_id: StableId
    snapshot_id: StableId
    matches: list[NormalizedContextMatch] = Field(default_factory=list, max_length=32)
    generated_at: AwareDatetime
    expires_at: AwareDatetime


class OpenLoopDescriptor(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    loop_id: StableId
    kind: OpenLoopKind
    subject_id: StableId
    status: OpenLoopStatus
    next_action_code: StableId
    blocking_on_id: Optional[StableId] = None
    updated_at: AwareDatetime


class OpenLoopSnapshot(BaseModel):
    model_config = ConfigDict(extra='forbid')

    schema_version: Literal[1] = 1
    device_id: StableId
    owner: StableId
    runtime_id: StableId
    workstream_id: StableId
    conversation_id: StableId
    context_packet_version: StableId
    checkpoint_ref: Optional[StableId] = None
    open_loop_snapshot: list[OpenLoopDescriptor] = Field(default_factory=list, max_length=32)
    generated_at: AwareDatetime
    expires_at: AwareDatetime


class EvaluationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    device_id: Optional[StableId] = None
    material_hint: Optional[StableId] = None


class DecisionRecord(BaseModel):
    """Debug-only audit record. It intentionally contains no prompt or model reasoning."""

    model_config = ConfigDict(extra='forbid')

    evaluation_id: StableId
    subject_kind: RecommendationSubjectKind
    subject_id: StableId
    shortlist_ids: list[StableId] = Field(max_length=20)
    facts_snapshot: DeterministicFacts
    eligibility: ShortlistEligibility
    prompt_version: StableId
    policy_version: StableId
    fact_definition_version: StableId
    model_version: StableId
    decision_summary: str = Field(max_length=1024)
    reason_codes: list[str] = Field(max_length=8)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list, max_length=50)
    final_output_ref: StableId
    evaluated_at: AwareDatetime
    expires_at: AwareDatetime


class DecisionDebugProjection(BaseModel):
    model_config = ConfigDict(extra='forbid')

    projection: WhatMattersNowProjection
    decisions: list[DecisionRecord]


class SnapshotReceipt(BaseModel):
    model_config = ConfigDict(extra='forbid')

    snapshot_id: StableId
    replaced: bool
    expires_at: datetime


__all__ = [
    'ContextMatchSignal',
    'DecisionDebugProjection',
    'DecisionRecord',
    'DeterministicFacts',
    'EvaluationRequest',
    'FeedbackCreate',
    'FeedbackRecord',
    'FeedbackSubjectKind',
    'InterventionCreate',
    'InterventionRecord',
    'InterventionSurface',
    'NormalizedContextMatch',
    'NormalizedContextSnapshot',
    'OpenLoopDescriptor',
    'OpenLoopKind',
    'OpenLoopSnapshot',
    'OpenLoopStatus',
    'OutcomeCreate',
    'OutcomeRecord',
    'Recommendation',
    'RecommendationSubjectKind',
    'ShortlistEligibility',
    'SnapshotReceipt',
    'WhatMattersNowProjection',
]
