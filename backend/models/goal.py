"""Canonical goal contracts with released-client compatibility fields."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from models.action_item import EvidenceRef
from models.task_intelligence import StableId


class GoalType(str, Enum):
    boolean = 'boolean'
    scale = 'scale'
    numeric = 'numeric'


class GoalStatus(str, Enum):
    background = 'background'
    focused = 'focused'
    paused = 'paused'
    achieved = 'achieved'
    abandoned = 'abandoned'


class GoalSource(str, Enum):
    user = 'user'
    ai_suggested = 'ai_suggested'
    imported = 'imported'


class GoalRelationshipDisposition(str, Enum):
    retain = 'retain'
    detach = 'detach'


class GoalMetric(BaseModel):
    model_config = ConfigDict(extra='forbid')

    type: GoalType
    current: float
    target: float
    min: Optional[float] = None
    max: Optional[float] = None
    unit: Optional[str] = Field(default=None, max_length=64)

    @model_validator(mode='after')
    def validate_bounds(self):
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError('metric min must not exceed max')
        return self


class GoalCreate(BaseModel):
    """Canonical create shape; legacy numeric fields remain accepted at this boundary."""

    model_config = ConfigDict(extra='forbid')

    title: str = Field(min_length=1, max_length=500)
    desired_outcome: Optional[str] = Field(default=None, max_length=2000)
    why_it_matters: Optional[str] = Field(default=None, max_length=2000)
    success_criteria: list[str] = Field(default_factory=list, max_length=20)
    horizon_at: Optional[datetime] = None
    status: GoalStatus = GoalStatus.background
    metric: Optional[GoalMetric] = None
    source: GoalSource = GoalSource.user

    # Released request compatibility.
    goal_type: Optional[GoalType] = None
    target_value: Optional[float] = None
    current_value: Optional[float] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    unit: Optional[str] = Field(default=None, max_length=64)

    @model_validator(mode='after')
    def normalize_legacy_metric(self):
        self.title = self.title.strip()
        if not self.title:
            raise ValueError('title cannot be blank')
        if self.desired_outcome is None:
            self.desired_outcome = self.title
        if self.status == GoalStatus.focused:
            raise ValueError('create the goal first, then focus it explicitly')
        self.success_criteria = [criterion.strip() for criterion in self.success_criteria if criterion.strip()]
        if self.metric is None and (self.target_value is not None or self.goal_type is not None):
            self.metric = GoalMetric(
                type=self.goal_type or GoalType.scale,
                current=self.current_value if self.current_value is not None else 0,
                target=self.target_value if self.target_value is not None else 0,
                min=self.min_value,
                max=self.max_value,
                unit=self.unit,
            )
        return self


class GoalUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    title: Optional[str] = Field(default=None, min_length=1, max_length=500)
    desired_outcome: Optional[str] = Field(default=None, max_length=2000)
    why_it_matters: Optional[str] = Field(default=None, max_length=2000)
    success_criteria: Optional[list[str]] = Field(default=None, max_length=20)
    horizon_at: Optional[datetime] = None
    metric: Optional[GoalMetric] = None
    clear_metric: bool = False

    # Released request compatibility.
    target_value: Optional[float] = None
    current_value: Optional[float] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    unit: Optional[str] = Field(default=None, max_length=64)

    @model_validator(mode='after')
    def protect_required_fields(self):
        for field_name in ('title', 'desired_outcome', 'success_criteria'):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f'{field_name} cannot be null')
        for field_name in ('target_value', 'current_value'):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f'{field_name} cannot be null; use clear_metric to remove the metric')
        if self.title is not None:
            self.title = self.title.strip()
            if not self.title:
                raise ValueError('title cannot be blank')
        if self.desired_outcome is not None:
            self.desired_outcome = self.desired_outcome.strip()
            if not self.desired_outcome:
                raise ValueError('desired_outcome cannot be blank')
        return self


class GoalFocusRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    replacement_goal_id: Optional[StableId] = None
    focus_rank: Optional[int] = Field(default=None, ge=0, le=4)


class GoalLifecycleRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    status: GoalStatus
    relationship_disposition: GoalRelationshipDisposition

    @model_validator(mode='after')
    def validate_terminal_status(self):
        if self.status not in {GoalStatus.paused, GoalStatus.achieved, GoalStatus.abandoned}:
            raise ValueError('goal lifecycle transition must pause or end the goal')
        return self


class GoalProgressEventKind(str, Enum):
    evidence = 'evidence'
    metric_update = 'metric_update'
    milestone = 'milestone'
    status_change = 'status_change'


class GoalProgressEventCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    kind: GoalProgressEventKind
    summary: str = Field(min_length=1, max_length=1000)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list, max_length=50)
    metric: Optional[GoalMetric] = None


class GoalProgressEvent(BaseModel):
    model_config = ConfigDict(extra='forbid')

    event_id: StableId
    goal_id: StableId
    sequence: int = Field(ge=1)
    kind: GoalProgressEventKind
    summary: str = Field(min_length=1, max_length=1000)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list, max_length=50)
    metric: Optional[GoalMetric] = None
    created_at: datetime


class GoalResponse(BaseModel):
    """Canonical response plus non-null aliases required by released clients."""

    id: StableId
    goal_id: StableId
    title: str
    desired_outcome: str
    why_it_matters: Optional[str] = None
    success_criteria: list[str] = Field(default_factory=list)
    horizon_at: Optional[datetime] = None
    status: GoalStatus
    focus_rank: Optional[int] = None
    metric: Optional[GoalMetric] = None
    source: GoalSource
    created_at: datetime
    updated_at: datetime
    ended_at: Optional[datetime] = None
    latest_progress_sequence: int = 0

    # Released response compatibility.
    goal_type: str
    target_value: float
    current_value: float
    min_value: float
    max_value: float
    unit: Optional[str] = None
    is_active: bool
    advice: Optional[str] = None


class GoalHistoryEntryResponse(BaseModel):
    date: str
    value: float
    recorded_at: datetime


class GoalDeleteResponse(BaseModel):
    success: bool
    deleted_id: str


class GoalSuggestionResponse(BaseModel):
    suggested_title: str
    suggested_type: str
    suggested_target: float
    suggested_min: float = 0
    suggested_max: float = 10
    reasoning: str


class AdviceResponse(BaseModel):
    advice: str


__all__ = [
    'AdviceResponse',
    'GoalCreate',
    'GoalDeleteResponse',
    'GoalFocusRequest',
    'GoalHistoryEntryResponse',
    'GoalLifecycleRequest',
    'GoalMetric',
    'GoalProgressEvent',
    'GoalProgressEventCreate',
    'GoalProgressEventKind',
    'GoalRelationshipDisposition',
    'GoalResponse',
    'GoalSource',
    'GoalStatus',
    'GoalSuggestionResponse',
    'GoalType',
    'GoalUpdate',
]
