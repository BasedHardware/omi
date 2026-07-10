"""Stable task-intelligence contracts shared by rollout and telemetry code."""

from enum import Enum
from typing import Annotated, Literal, Optional

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

StableId = Annotated[
    str,
    StringConstraints(strip_whitespace=False, min_length=1, max_length=128, pattern=r'^[A-Za-z0-9][A-Za-z0-9._:-]*$'),
]


class TaskWorkflowMode(str, Enum):
    off = 'off'
    shadow = 'shadow'
    write = 'write'
    read = 'read'


class TaskIntelligenceEventType(str, Enum):
    candidate_captured = 'candidate_captured'
    candidate_resolved = 'candidate_resolved'
    intervention_presented = 'intervention_presented'
    feedback_recorded = 'feedback_recorded'
    outcome_recorded = 'outcome_recorded'


class TaskIntelligenceSourceClass(str, Enum):
    manual = 'manual'
    conversation = 'conversation'
    screen = 'screen'
    agent = 'agent'
    integration = 'integration'
    import_share = 'import_share'
    recurrence = 'recurrence'


class TaskIntelligenceConfidenceBand(str, Enum):
    low = 'low'
    medium = 'medium'
    high = 'high'
    explicit = 'explicit'


class TaskIntelligenceResolutionCode(str, Enum):
    accepted = 'accepted'
    rejected = 'rejected'
    expired = 'expired'


class TaskIntelligenceFeedbackAction(str, Enum):
    do_now = 'do_now'
    later = 'later'
    dismiss = 'dismiss'
    accept_candidate = 'accept_candidate'
    edit = 'edit'
    complete = 'complete'


class TaskIntelligenceFeedbackReason(str, Enum):
    already_handled = 'already_handled'
    not_mine = 'not_mine'
    not_useful = 'not_useful'


class TaskIntelligenceOutcomeCode(str, Enum):
    task_completed = 'task_completed'
    artifact_approved = 'artifact_approved'
    artifact_delivered = 'artifact_delivered'
    decision_resolved = 'decision_resolved'
    agent_output_applied = 'agent_output_applied'
    workstream_advanced = 'workstream_advanced'


class TaskIntelligenceRolloutDecision(BaseModel):
    """Pure rollout decision; memory cohort membership is an independent input."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    uid: str = Field(min_length=1)
    workflow_mode: TaskWorkflowMode
    memory_cohort_eligible: bool
    account_generation: int = Field(default=0, ge=0)
    legacy_reads_authoritative: bool
    legacy_writes_enabled: bool
    intelligence_evaluation_enabled: bool
    canonical_sidecar_writes_enabled: bool
    canonical_reads_authoritative: bool
    compatibility_projection_required: bool
    intelligence_product_enabled: bool


class TaskIntelligenceAttributionEvent(BaseModel):
    """Privacy-safe attribution envelope.

    The absence of a free-form metadata/content field is intentional. Analytics
    stores stable identifiers and bounded enums only; private task or evidence
    content remains in its authoritative product domain.
    """

    model_config = ConfigDict(extra='forbid', frozen=True)

    schema_version: Literal[1]
    event_id: StableId
    event_type: TaskIntelligenceEventType
    source_class: TaskIntelligenceSourceClass
    confidence_band: Optional[TaskIntelligenceConfidenceBand] = None
    attribution_chain_id: Optional[StableId] = None
    intervention_id: Optional[StableId] = None
    candidate_id: Optional[StableId] = None
    task_id: Optional[StableId] = None
    workstream_id: Optional[StableId] = None
    artifact_id: Optional[StableId] = None
    decision_id: Optional[StableId] = None
    resolution_code: Optional[TaskIntelligenceResolutionCode] = None
    feedback_action: Optional[TaskIntelligenceFeedbackAction] = None
    feedback_reason: Optional[TaskIntelligenceFeedbackReason] = None
    outcome_code: Optional[TaskIntelligenceOutcomeCode] = None
    occurred_at: AwareDatetime

    @model_validator(mode='after')
    def require_event_specific_linkage(self):
        subject_ids = (self.candidate_id, self.task_id, self.workstream_id, self.artifact_id, self.decision_id)
        has_subject = any(subject_ids)
        if self.event_type == TaskIntelligenceEventType.candidate_captured and not self.candidate_id:
            raise ValueError('candidate_captured requires candidate_id')
        if self.event_type == TaskIntelligenceEventType.candidate_resolved:
            if not self.candidate_id or not self.resolution_code:
                raise ValueError('candidate_resolved requires candidate_id and resolution_code')
            if self.resolution_code == TaskIntelligenceResolutionCode.accepted and not any(
                (self.task_id, self.workstream_id)
            ):
                raise ValueError('accepted candidate_resolved requires a task_id or workstream_id')
        if self.event_type == TaskIntelligenceEventType.intervention_presented:
            if not self.intervention_id or not has_subject:
                raise ValueError('intervention_presented requires intervention_id and subject')
        if self.event_type == TaskIntelligenceEventType.feedback_recorded:
            if not self.intervention_id or not has_subject or not self.feedback_action:
                raise ValueError('feedback_recorded requires intervention_id, subject, and feedback_action')
            if self.feedback_reason and self.feedback_action != TaskIntelligenceFeedbackAction.dismiss:
                raise ValueError('feedback_reason is only valid for dismiss feedback')
        if self.event_type == TaskIntelligenceEventType.outcome_recorded:
            if not self.attribution_chain_id or not has_subject or not self.outcome_code:
                raise ValueError('outcome_recorded requires attribution_chain_id, subject, and outcome_code')
        return self


__all__ = [
    'TaskIntelligenceAttributionEvent',
    'TaskIntelligenceConfidenceBand',
    'TaskIntelligenceEventType',
    'TaskIntelligenceFeedbackAction',
    'TaskIntelligenceFeedbackReason',
    'TaskIntelligenceOutcomeCode',
    'TaskIntelligenceResolutionCode',
    'TaskIntelligenceRolloutDecision',
    'TaskIntelligenceSourceClass',
    'TaskWorkflowMode',
]
