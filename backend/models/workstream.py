"""Canonical backend-owned workstream, journal, artifact, and checkpoint contracts."""

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from models.action_item import ActionItemResponse, EvidenceRef
from models.goal import GoalProgressEvent, GoalResponse
from models.task_intelligence import StableId


class WorkstreamStatus(str, Enum):
    open = 'open'
    paused = 'paused'
    completed = 'completed'
    archived = 'archived'


class WorkstreamEventKind(str, Enum):
    user_note = 'user_note'
    conversation = 'conversation'
    message = 'message'
    screen_observation = 'screen_observation'
    task_change = 'task_change'
    decision = 'decision'
    agent_update = 'agent_update'
    artifact_version = 'artifact_version'
    external_update = 'external_update'
    system = 'system'


class WorkstreamSensitivity(str, Enum):
    normal = 'normal'
    sensitive = 'sensitive'
    restricted = 'restricted'


class WorkstreamCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    title: str = Field(min_length=1, max_length=256)
    objective: str = Field(min_length=1, max_length=2048)
    goal_id: Optional[StableId] = None
    current_state_summary: str = Field(default='', max_length=4000)
    next_review_at: Optional[datetime] = None


class WorkstreamUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    title: Optional[str] = Field(default=None, min_length=1, max_length=256)
    objective: Optional[str] = Field(default=None, min_length=1, max_length=2048)
    status: Optional[WorkstreamStatus] = None
    current_state_summary: Optional[str] = Field(default=None, max_length=4000)
    next_review_at: Optional[datetime] = None

    @model_validator(mode='after')
    def require_explicit_valid_patch(self):
        if not self.model_fields_set:
            raise ValueError('at least one workstream field is required')
        for field_name in ('title', 'objective', 'status', 'current_state_summary'):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f'{field_name} cannot be null')
        return self


class Workstream(BaseModel):
    model_config = ConfigDict(extra='forbid')

    workstream_id: StableId
    goal_id: Optional[StableId] = None
    title: str = Field(min_length=1, max_length=256)
    objective: str = Field(min_length=1, max_length=2048)
    status: WorkstreamStatus
    current_state_summary: str = Field(default='', max_length=4000)
    next_review_at: Optional[datetime] = None
    last_meaningful_progress_at: Optional[datetime] = None
    latest_event_sequence: int = Field(default=0, ge=0)
    created_at: datetime
    updated_at: datetime


class WorkstreamEventCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    kind: WorkstreamEventKind
    summary: str = Field(min_length=1, max_length=2000)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list, max_length=50)
    sensitivity: WorkstreamSensitivity = WorkstreamSensitivity.normal


class WorkstreamEvent(BaseModel):
    model_config = ConfigDict(extra='forbid')

    event_id: StableId
    workstream_id: StableId
    sequence: int = Field(ge=1)
    kind: WorkstreamEventKind
    summary: str = Field(min_length=1, max_length=2000)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list, max_length=50)
    sensitivity: WorkstreamSensitivity
    created_at: datetime


class ArtifactStatus(str, Enum):
    draft = 'draft'
    awaiting_review = 'awaiting_review'
    approved = 'approved'
    delivered = 'delivered'
    superseded = 'superseded'


class ArtifactDescriptorCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    logical_key: str = Field(min_length=1, max_length=256)
    version: int = Field(ge=1)
    supersedes_artifact_id: Optional[StableId] = None
    kind: str = Field(min_length=1, max_length=64)
    uri: str = Field(min_length=1, max_length=2048)
    content_hash: str = Field(min_length=16, max_length=128)
    source_run_id: Optional[StableId] = None
    evidence_event_ids: list[StableId] = Field(default_factory=list, max_length=100)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list, max_length=50)


class ArtifactDescriptor(ArtifactDescriptorCreate):
    artifact_id: StableId
    workstream_id: StableId
    status: ArtifactStatus = ArtifactStatus.draft
    created_at: datetime


class ArtifactStatusTransitionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    status: ArtifactStatus


class ContinuationCheckpointUpsert(BaseModel):
    model_config = ConfigDict(extra='forbid')

    runtime_id: StableId
    last_event_sequence: int = Field(ge=0)
    context_summary: str = Field(max_length=4000)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list, max_length=50)


class ContinuationCheckpoint(ContinuationCheckpointUpsert):
    checkpoint_id: StableId
    workstream_id: StableId
    updated_at: datetime


class TaskOriginWorkIntent(BaseModel):
    model_config = ConfigDict(extra='forbid')

    origin: Literal['task'] = 'task'
    task_id: StableId
    title: Optional[str] = Field(default=None, max_length=256)
    objective: Optional[str] = Field(default=None, max_length=2048)


class GoalOriginWorkIntent(BaseModel):
    model_config = ConfigDict(extra='forbid')

    origin: Literal['goal'] = 'goal'
    goal_id: StableId
    title: str = Field(min_length=1, max_length=256)
    objective: str = Field(min_length=1, max_length=2048)
    anchor_task_description: str = Field(min_length=1, max_length=2000)


WorkIntentRequest = Annotated[Union[TaskOriginWorkIntent, GoalOriginWorkIntent], Field(discriminator='origin')]


class WorkIntentReceipt(BaseModel):
    model_config = ConfigDict(extra='forbid')

    receipt_id: StableId
    workstream_id: StableId
    task_id: StableId
    goal_id: Optional[StableId] = None
    newly_created: bool
    created_at: datetime


class GoalDetailProjection(BaseModel):
    model_config = ConfigDict(extra='forbid')

    goal: GoalResponse
    active_threads: list[Workstream]
    tasks: list[ActionItemResponse]
    progress_events: list[GoalProgressEvent]


class WorkstreamDetailProjection(BaseModel):
    model_config = ConfigDict(extra='forbid')

    workstream: Workstream
    recent_events: list[WorkstreamEvent]
    tasks: list[ActionItemResponse]
    artifacts: list[ArtifactDescriptor]
    checkpoints: list[ContinuationCheckpoint]


class TaskGoalLinkImport(BaseModel):
    model_config = ConfigDict(extra='forbid')

    task_id: StableId
    goal_id: StableId


class TaskGoalLinkImportRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    links: list[TaskGoalLinkImport] = Field(max_length=500)


class TaskGoalLinkImportReport(BaseModel):
    imported: int
    unchanged: int
    failed: int
    failure_task_ids: list[StableId]


__all__ = [
    'ArtifactDescriptor',
    'ArtifactDescriptorCreate',
    'ArtifactStatus',
    'ArtifactStatusTransitionRequest',
    'ContinuationCheckpoint',
    'ContinuationCheckpointUpsert',
    'GoalDetailProjection',
    'GoalOriginWorkIntent',
    'TaskGoalLinkImportReport',
    'TaskGoalLinkImportRequest',
    'TaskOriginWorkIntent',
    'WorkIntentReceipt',
    'WorkIntentRequest',
    'Workstream',
    'WorkstreamCreate',
    'WorkstreamDetailProjection',
    'WorkstreamEvent',
    'WorkstreamEventCreate',
    'WorkstreamEventKind',
    'WorkstreamSensitivity',
    'WorkstreamStatus',
    'WorkstreamUpdate',
]
