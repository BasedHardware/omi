"""Universal Candidate lifecycle contracts for task and workstream proposals."""

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator
from pydantic.annotated_handlers import GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from typing_extensions import TypeAliasType

from models.action_item import EvidenceRef, TaskChangePayload, TaskCreatePayload, TaskStatus
from models.task_intelligence import StableId, TaskWorkflowMode


class CandidateSubjectKind(str, Enum):
    task = 'task'
    workstream = 'workstream'


class CandidateAction(str, Enum):
    create = 'create'
    update = 'update'
    complete = 'complete'
    cancel = 'cancel'
    supersede = 'supersede'


class CandidateStatus(str, Enum):
    pending = 'pending'
    accepted = 'accepted'
    rejected = 'rejected'
    expired = 'expired'


class WorkstreamProposal(BaseModel):
    model_config = ConfigDict(extra='forbid')

    title: str = Field(min_length=1, max_length=256)
    objective: str = Field(min_length=1, max_length=2048)
    anchor_task: TaskCreatePayload


class CandidateEnvelope(BaseModel):
    model_config = ConfigDict(extra='forbid')

    capture_confidence: float = Field(ge=0, le=1)
    ownership_confidence: float = Field(ge=0, le=1)
    goal_id: Optional[StableId] = None
    workstream_id: Optional[StableId] = None
    evidence_refs: list[EvidenceRef] = Field(min_length=1)
    source_surface: str = Field(min_length=1, max_length=64)


class TaskCreateCandidate(CandidateEnvelope):
    subject_kind: Literal[CandidateSubjectKind.task] = CandidateSubjectKind.task
    proposed_action: Literal[CandidateAction.create] = CandidateAction.create
    task_change: TaskCreatePayload


class TaskMutationCandidate(CandidateEnvelope):
    subject_kind: Literal[CandidateSubjectKind.task] = CandidateSubjectKind.task
    task_id: StableId
    task_change: TaskChangePayload

    @model_validator(mode='after')
    def validate_action_specific_change(self):
        proposed_action = CandidateAction(getattr(self, 'proposed_action'))
        required_status = {
            CandidateAction.complete: TaskStatus.completed,
            CandidateAction.cancel: TaskStatus.cancelled,
            CandidateAction.supersede: TaskStatus.superseded,
        }.get(proposed_action)
        if required_status is not None and self.task_change.status != required_status:
            raise ValueError(f'{proposed_action.value} Candidate requires status={required_status.value}')
        if proposed_action == CandidateAction.supersede and self.task_change.superseded_by is None:
            raise ValueError('supersede Candidate requires superseded_by')
        return self


class TaskUpdateCandidate(TaskMutationCandidate):
    proposed_action: Literal[CandidateAction.update] = CandidateAction.update


class TaskCompleteCandidate(TaskMutationCandidate):
    proposed_action: Literal[CandidateAction.complete] = CandidateAction.complete


class TaskCancelCandidate(TaskMutationCandidate):
    proposed_action: Literal[CandidateAction.cancel] = CandidateAction.cancel


class TaskSupersedeCandidate(TaskMutationCandidate):
    proposed_action: Literal[CandidateAction.supersede] = CandidateAction.supersede


class WorkstreamCreateCandidate(CandidateEnvelope):
    subject_kind: Literal[CandidateSubjectKind.workstream] = CandidateSubjectKind.workstream
    proposed_action: Literal[CandidateAction.create] = CandidateAction.create
    workstream_proposal: WorkstreamProposal


TaskCandidate = TypeAliasType(
    'TaskCandidate',
    Annotated[
        Union[
            TaskCreateCandidate,
            TaskUpdateCandidate,
            TaskCompleteCandidate,
            TaskCancelCandidate,
            TaskSupersedeCandidate,
        ],
        Field(discriminator='proposed_action'),
    ],
)
CandidateCreateUnion = Annotated[
    Union[TaskCandidate, WorkstreamCreateCandidate],
    Field(discriminator='subject_kind'),
]


class CandidateCreate(RootModel[CandidateCreateUnion]):
    """Strict request union; each wire arm contains only fields valid for that action."""

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        schema = handler(core_schema)
        if 'anyOf' in schema:
            schema['oneOf'] = schema.pop('anyOf')
        return schema

    @property
    def subject_kind(self) -> CandidateSubjectKind:
        return CandidateSubjectKind(self.root.subject_kind)

    @property
    def proposed_action(self) -> CandidateAction:
        return CandidateAction(self.root.proposed_action)

    @property
    def task_id(self) -> Optional[StableId]:
        return getattr(self.root, 'task_id', None)

    @property
    def task_change(self) -> Optional[TaskCreatePayload | TaskChangePayload]:
        return getattr(self.root, 'task_change', None)

    @property
    def workstream_proposal(self) -> Optional[WorkstreamProposal]:
        return getattr(self.root, 'workstream_proposal', None)

    @property
    def capture_confidence(self) -> float:
        return self.root.capture_confidence

    @property
    def ownership_confidence(self) -> float:
        return self.root.ownership_confidence

    @property
    def goal_id(self) -> Optional[StableId]:
        return self.root.goal_id

    @property
    def workstream_id(self) -> Optional[StableId]:
        return self.root.workstream_id

    @property
    def evidence_refs(self) -> list[EvidenceRef]:
        return self.root.evidence_refs

    @property
    def source_surface(self) -> str:
        return self.root.source_surface


class CandidateRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    subject_kind: CandidateSubjectKind
    proposed_action: CandidateAction
    task_id: Optional[StableId] = None
    task_change: Optional[TaskCreatePayload | TaskChangePayload] = None
    workstream_proposal: Optional[WorkstreamProposal] = None
    capture_confidence: float = Field(ge=0, le=1)
    ownership_confidence: float = Field(ge=0, le=1)
    goal_id: Optional[StableId] = None
    workstream_id: Optional[StableId] = None
    evidence_refs: list[EvidenceRef] = Field(min_length=1)
    source_surface: str = Field(min_length=1, max_length=64)
    candidate_id: StableId
    status: CandidateStatus = CandidateStatus.pending
    account_generation: int = Field(ge=0)
    idempotency_key: StableId
    resolution_reason: Optional[str] = Field(default=None, max_length=64)
    result_task_id: Optional[StableId] = None
    result_workstream_id: Optional[StableId] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        schema = handler(core_schema)
        properties = schema['properties']
        stable_id_schema = properties['task_id']['anyOf'][0]
        task_create_ref = properties['task_change']['anyOf'][0]
        task_change_ref = properties['task_change']['anyOf'][1]
        workstream_ref = properties['workstream_proposal']['anyOf'][0]

        def task_change_schema(*, status: Optional[TaskStatus] = None, require_superseded_by: bool = False):
            constraints: dict[str, Any] = {}
            if status is not None:
                constraints.setdefault('properties', {})['status'] = {'const': status.value}
                constraints.setdefault('required', []).append('status')
            if require_superseded_by:
                constraints.setdefault('required', []).append('superseded_by')
            return {'allOf': [task_change_ref, constraints]} if constraints else task_change_ref

        def task_arm(action: CandidateAction, change: dict[str, Any]):
            return {
                'properties': {
                    'subject_kind': {'const': CandidateSubjectKind.task.value},
                    'proposed_action': {'const': action.value},
                    'task_id': stable_id_schema if action != CandidateAction.create else {'type': 'null'},
                    'task_change': change,
                    'workstream_proposal': {'type': 'null'},
                },
                'required': ['task_change'] + (['task_id'] if action != CandidateAction.create else []),
            }

        schema['oneOf'] = [
            task_arm(CandidateAction.create, task_create_ref),
            task_arm(CandidateAction.update, task_change_schema()),
            task_arm(CandidateAction.complete, task_change_schema(status=TaskStatus.completed)),
            task_arm(CandidateAction.cancel, task_change_schema(status=TaskStatus.cancelled)),
            task_arm(
                CandidateAction.supersede,
                task_change_schema(status=TaskStatus.superseded, require_superseded_by=True),
            ),
            {
                'properties': {
                    'subject_kind': {'const': CandidateSubjectKind.workstream.value},
                    'proposed_action': {'const': CandidateAction.create.value},
                    'task_id': {'type': 'null'},
                    'task_change': {'type': 'null'},
                    'workstream_proposal': workstream_ref,
                },
                'required': ['workstream_proposal'],
            },
        ]
        return schema

    @model_validator(mode='before')
    @classmethod
    def validate_proposal_shape(cls, value: Any):
        if not isinstance(value, dict):
            return value
        record_fields = {
            'candidate_id',
            'status',
            'account_generation',
            'idempotency_key',
            'resolution_reason',
            'result_task_id',
            'result_workstream_id',
            'created_at',
            'resolved_at',
        }
        proposal = CandidateCreate.model_validate(
            {key: item for key, item in value.items() if key not in record_fields and item is not None}
        )
        normalized = dict(value)
        normalized['subject_kind'] = proposal.subject_kind
        normalized['proposed_action'] = proposal.proposed_action
        normalized['task_id'] = proposal.task_id
        normalized['task_change'] = proposal.task_change
        normalized['workstream_proposal'] = proposal.workstream_proposal
        return normalized

    @model_validator(mode='after')
    def validate_resolution(self):
        if self.status == CandidateStatus.pending:
            if self.resolved_at is not None or self.resolution_reason is not None:
                raise ValueError('pending Candidate cannot have resolution metadata')
        elif self.resolved_at is None:
            raise ValueError('resolved Candidate requires resolved_at')
        if self.status == CandidateStatus.accepted:
            if self.subject_kind == CandidateSubjectKind.task and self.result_task_id is None:
                raise ValueError('accepted task Candidate requires result_task_id')
            if self.subject_kind == CandidateSubjectKind.workstream and self.result_workstream_id is None:
                raise ValueError('accepted workstream Candidate requires result_workstream_id')
        return self

    def as_proposal(self) -> CandidateCreate:
        record_fields = {
            'candidate_id',
            'status',
            'account_generation',
            'idempotency_key',
            'resolution_reason',
            'result_task_id',
            'result_workstream_id',
            'created_at',
            'resolved_at',
        }
        return CandidateCreate.model_validate(
            {
                key: value
                for key, value in self.model_dump(mode='python').items()
                if key not in record_fields and value is not None
            }
        )

    @classmethod
    def from_storage(cls, value: dict[str, Any]) -> 'CandidateRecord':
        return cls.model_validate(value)


class CandidateListResponse(BaseModel):
    candidates: list[CandidateRecord]
    has_more: bool = False


class CandidateResolutionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    reason: Optional[str] = Field(default=None, max_length=64)


class CandidateResolutionReceipt(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    candidate_id: StableId
    status: CandidateStatus
    receipt_id: StableId
    task_id: Optional[StableId] = None
    workstream_id: Optional[StableId] = None
    newly_resolved: bool
    resolved_at: datetime


class CandidateMigrationReport(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    workflow_mode: TaskWorkflowMode
    account_generation: int = Field(ge=0)
    dry_run: bool
    scanned: int = Field(ge=0)
    created: int = Field(ge=0)
    reconciled: int = Field(ge=0)
    unchanged: int = Field(ge=0)
    failed: int = Field(ge=0)
    failure_ids: list[StableId]
    checkpoint: Optional[StableId] = None


class CandidateMigrationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    after_id: Optional[StableId] = None
    limit: int = Field(default=500, ge=1, le=500)


__all__ = [
    'CandidateAction',
    'CandidateCreate',
    'CandidateListResponse',
    'CandidateMigrationReport',
    'CandidateMigrationRequest',
    'CandidateRecord',
    'CandidateResolutionReceipt',
    'CandidateResolutionRequest',
    'CandidateStatus',
    'CandidateSubjectKind',
    'TaskCancelCandidate',
    'TaskCompleteCandidate',
    'TaskCreateCandidate',
    'TaskSupersedeCandidate',
    'TaskUpdateCandidate',
    'WorkstreamCreateCandidate',
    'WorkstreamProposal',
]
