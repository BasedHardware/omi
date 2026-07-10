"""Backend conversation adapter for the shared capture policy."""

from dataclasses import dataclass
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from models.action_item import EvidenceRef, TaskChangePayload, TaskCreatePayload, TaskOwner, TaskStatus
from models.candidate import CandidateCreate, CandidateSubjectKind, CandidateAction
from utils.task_intelligence.capture_policy import CapturePolicyResult, run_capture_policy


class BackendCaptureSignals(BaseModel):
    model_config = ConfigDict(extra='forbid')

    explicit_command: bool = False
    clear_commitment: bool = False
    concrete_deliverable: bool = False
    direct_request: bool = False
    inferred_next_step: bool = False
    owner: TaskOwner = TaskOwner.unknown
    public_broadcast: bool = False
    direct_mention: bool = False
    already_done: bool = False
    duplicate_of: Optional[str] = None
    refines_task: Optional[str] = None
    capture_confidence: float = Field(default=0.5, ge=0, le=1)
    ownership_confidence: float = Field(default=0.5, ge=0, le=1)

    def policy_signals(self) -> dict[str, Any]:
        return self.model_dump(mode='json')


@dataclass(frozen=True)
class BackendCaptureDecision:
    policy: CapturePolicyResult
    candidate: Optional[CandidateCreate]


def adapt_backend_capture(
    task: TaskCreatePayload,
    *,
    evidence_ref: EvidenceRef,
    source_surface: str,
    signals: BackendCaptureSignals,
    goal_id: Optional[str] = None,
    workstream_id: Optional[str] = None,
) -> BackendCaptureDecision:
    policy = run_capture_policy(signals.policy_signals())
    if policy.outcome == 'ignore':
        return BackendCaptureDecision(policy=policy, candidate=None)
    proposed_action = CandidateAction.create
    task_id = None
    task_change: TaskCreatePayload | TaskChangePayload = task
    if policy.outcome in {'propose_enrichment', 'propose_update'}:
        proposed_action = CandidateAction.update
        task_id = signals.duplicate_of or signals.refines_task
        if task_id is None:
            return BackendCaptureDecision(policy=policy, candidate=None)
        task_change = TaskChangePayload(description=task.description, due_at=task.due_at)
    elif policy.outcome == 'propose_completion':
        proposed_action = CandidateAction.complete
        task_id = signals.duplicate_of or signals.refines_task
        if task_id is None:
            return BackendCaptureDecision(policy=policy, candidate=None)
        task_change = TaskChangePayload(status=TaskStatus.completed)
    proposal_data: dict[str, Any] = {
        'subject_kind': CandidateSubjectKind.task,
        'proposed_action': proposed_action,
        'task_change': task_change,
        'capture_confidence': signals.capture_confidence,
        'ownership_confidence': signals.ownership_confidence,
        'goal_id': goal_id,
        'workstream_id': workstream_id,
        'evidence_refs': [evidence_ref],
        'source_surface': source_surface,
    }
    if task_id is not None:
        proposal_data['task_id'] = task_id
    proposal = CandidateCreate.model_validate(proposal_data)
    return BackendCaptureDecision(policy=policy, candidate=proposal)


__all__ = ['BackendCaptureDecision', 'BackendCaptureSignals', 'adapt_backend_capture']
