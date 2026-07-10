"""Versioned workflow association and recurrence-consumption contracts."""

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from models.action_item import EvidenceRef
from models.memory_recurrence import CanonicalRecurrenceSignal
from models.task_intelligence import StableId


class AssociationEvidence(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    evidence_id: StableId
    summary: str = Field(min_length=1, max_length=2000)
    evidence_refs: list[EvidenceRef] = Field(min_length=1, max_length=50)


class AssociationCandidateView(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    workstream_id: StableId
    objective: str = Field(min_length=1, max_length=2048)
    current_state_summary: str = Field(max_length=4000)


class AssociationAdjudicationInput(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    schema_version: Literal[1] = 1
    policy_version: Literal['association.v1'] = 'association.v1'
    evidence_summary: str = Field(min_length=1, max_length=2000)
    candidates: list[AssociationCandidateView] = Field(min_length=1, max_length=5)


class AssociationReason(str, Enum):
    selected = 'selected'
    no_match = 'no_match'
    immaterial = 'immaterial'
    ambiguous = 'ambiguous'
    model_unavailable = 'model_unavailable'


class AssociationJudgment(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    schema_version: Literal[1] = 1
    policy_version: Literal['association.v1'] = 'association.v1'
    workstream_id: Optional[StableId] = None
    material: bool
    reason: AssociationReason
    event_summary: Optional[str] = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode='after')
    def validate_selection(self):
        if self.material and self.workstream_id is None:
            raise ValueError('material association requires workstream_id')
        if self.material and self.reason != AssociationReason.selected:
            raise ValueError('material association requires selected reason')
        if self.material and self.event_summary is None:
            raise ValueError('material association requires a minimized event_summary')
        if not self.material and self.reason == AssociationReason.selected:
            raise ValueError('selected reason requires material association')
        if not self.material and self.event_summary is not None:
            raise ValueError('non-material association must not emit an event_summary')
        if not self.material and self.workstream_id is not None and self.reason != AssociationReason.immaterial:
            raise ValueError('a non-material workstream selection requires immaterial reason')
        if not self.material and self.workstream_id is None and self.reason == AssociationReason.immaterial:
            raise ValueError('immaterial reason requires a workstream selection')
        return self


class AssociationOutcomeKind(str, Enum):
    not_canonical_cohort = 'not_canonical_cohort'
    workflow_disabled = 'workflow_disabled'
    no_candidates = 'no_candidates'
    no_match = 'no_match'
    immaterial = 'immaterial'
    minimization_rejected = 'minimization_rejected'
    would_append = 'would_append'
    appended = 'appended'


class AssociationOutcome(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    outcome: AssociationOutcomeKind
    retrieved_candidate_ids: list[StableId] = Field(default_factory=list, max_length=20)
    hydrated_candidate_ids: list[StableId] = Field(default_factory=list, max_length=5)
    workstream_id: Optional[StableId] = None
    event_id: Optional[StableId] = None
    judgment_reason: Optional[AssociationReason] = None
    policy_version: Literal['association.v1'] = 'association.v1'


class WorkstreamIndexRebuildReport(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    uid: str
    index_version: Literal['workstream-association-v2'] = 'workstream-association-v2'
    source_count: int = Field(ge=0)
    indexed_count: int = Field(ge=0)
    failed_workstream_ids: list[StableId] = Field(default_factory=list)


class RecurrenceOutcomeKind(str, Enum):
    not_canonical_cohort = 'not_canonical_cohort'
    workflow_disabled = 'workflow_disabled'
    below_threshold = 'below_threshold'
    would_create = 'would_create'
    candidate_created = 'candidate_created'


class RecurrenceConsumptionOutcome(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    outcome: RecurrenceOutcomeKind
    signal_id: StableId
    candidate_id: Optional[StableId] = None
    idempotency_key: Optional[StableId] = None


class RecurrenceInboxStatus(str, Enum):
    pending = 'pending'
    completed = 'completed'


class RecurrenceInboxReceipt(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    receipt_id: StableId
    loop_key: StableId
    account_generation: int = Field(ge=0)
    status: RecurrenceInboxStatus
    signal: CanonicalRecurrenceSignal
    attempts: int = Field(default=0, ge=0)
    last_outcome: Optional[RecurrenceOutcomeKind] = None
    last_error_code: Optional[StableId] = None
    created_at: datetime
    updated_at: datetime


__all__ = [
    'AssociationAdjudicationInput',
    'AssociationCandidateView',
    'AssociationEvidence',
    'AssociationJudgment',
    'AssociationOutcome',
    'AssociationOutcomeKind',
    'AssociationReason',
    'RecurrenceConsumptionOutcome',
    'RecurrenceInboxReceipt',
    'RecurrenceInboxStatus',
    'RecurrenceOutcomeKind',
    'WorkstreamIndexRebuildReport',
]
