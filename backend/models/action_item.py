"""Canonical action-item contracts and legacy compatibility projections."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from models.task_intelligence import StableId


class TaskStatus(str, Enum):
    active = 'active'
    completed = 'completed'
    cancelled = 'cancelled'
    superseded = 'superseded'


class TaskOwner(str, Enum):
    user = 'user'
    other = 'other'
    unknown = 'unknown'


class TaskPriority(str, Enum):
    high = 'high'
    medium = 'medium'
    low = 'low'


class EvidenceKind(str, Enum):
    conversation = 'conversation'
    memory_item = 'memory_item'
    workstream_event = 'workstream_event'
    artifact = 'artifact'
    chat_message = 'chat_message'
    local_screen = 'local_screen'
    external = 'external'


class EvidenceScope(str, Enum):
    canonical = 'canonical'
    device_local = 'device_local'


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    kind: EvidenceKind
    id: StableId
    version: Optional[str] = Field(default=None, max_length=128)
    scope: EvidenceScope
    device_id: Optional[StableId] = None
    excerpt_hash: Optional[str] = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    transcript_segment_ids: Optional[list[StableId]] = None
    start_seconds: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    end_seconds: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)

    @model_validator(mode='after')
    def validate_scope(self):
        if self.scope == EvidenceScope.device_local and not self.device_id:
            raise ValueError('device_local evidence requires device_id')
        if self.scope == EvidenceScope.canonical and self.device_id is not None:
            raise ValueError('canonical evidence cannot carry device_id')
        if self.kind == EvidenceKind.local_screen and self.scope != EvidenceScope.device_local:
            raise ValueError('local_screen evidence must be device_local')
        if self.start_seconds is not None and self.end_seconds is not None and self.end_seconds < self.start_seconds:
            raise ValueError('end_seconds must be greater than or equal to start_seconds')
        return self


class CanonicalTaskCreate(BaseModel):
    """Shared create contract accepted by every task-writing surface."""

    model_config = ConfigDict(extra='forbid')

    description: str = Field(min_length=1, max_length=4096)
    status: Optional[TaskStatus] = None
    completed: Optional[bool] = None
    goal_id: Optional[StableId] = None
    workstream_id: Optional[StableId] = None
    owner: TaskOwner = TaskOwner.user
    due_at: Optional[AwareDatetime] = None
    due_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    source: str = Field(default='manual', min_length=1, max_length=64)
    provenance: list[EvidenceRef] = Field(default_factory=list)
    priority: Optional[TaskPriority] = None
    sort_order: int = 0
    indent_level: int = Field(default=0, ge=0, le=3)
    recurrence_rule: Optional[str] = Field(default=None, max_length=128)
    recurrence_parent_id: Optional[StableId] = None
    conversation_id: Optional[StableId] = None
    is_locked: bool = False
    exported: bool = False
    export_date: Optional[AwareDatetime] = None
    export_platform: Optional[str] = Field(default=None, max_length=64)
    apple_reminder_id: Optional[str] = Field(default=None, max_length=512)

    @model_validator(mode='after')
    def reconcile_legacy_completed(self):
        if self.status is None:
            self.status = TaskStatus.completed if self.completed is True else TaskStatus.active
        expected_completed = self.status == TaskStatus.completed
        if self.completed is not None and self.completed != expected_completed:
            raise ValueError('completed must agree with status')
        self.completed = expected_completed
        return self

    def storage_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode='python', exclude_none=True)
        payload['provenance'] = [
            ref.model_dump(mode='python', exclude_none=True, exclude_defaults=True) for ref in self.provenance
        ]
        return payload


class CanonicalTaskUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    description: Optional[str] = Field(default=None, min_length=1, max_length=4096)
    status: Optional[TaskStatus] = None
    completed: Optional[bool] = None
    goal_id: Optional[StableId] = None
    workstream_id: Optional[StableId] = None
    owner: Optional[TaskOwner] = None
    due_at: Optional[AwareDatetime] = None
    due_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    source: Optional[str] = Field(default=None, min_length=1, max_length=64)
    provenance: Optional[list[EvidenceRef]] = None
    priority: Optional[TaskPriority] = None
    sort_order: Optional[int] = None
    indent_level: Optional[int] = Field(default=None, ge=0, le=3)
    recurrence_rule: Optional[str] = Field(default=None, max_length=128)
    recurrence_parent_id: Optional[StableId] = None
    superseded_by: Optional[StableId] = None
    exported: Optional[bool] = None
    export_date: Optional[AwareDatetime] = None
    export_platform: Optional[str] = Field(default=None, max_length=64)
    apple_reminder_id: Optional[str] = Field(default=None, max_length=512)

    @model_validator(mode='after')
    def reconcile_legacy_completed(self):
        if self.status is not None and self.completed is not None:
            if self.completed != (self.status == TaskStatus.completed):
                raise ValueError('completed must agree with status')
        elif self.status is not None:
            self.completed = self.status == TaskStatus.completed
        elif self.completed is not None:
            self.status = TaskStatus.completed if self.completed else TaskStatus.active
        if not self.model_fields_set:
            raise ValueError('at least one task field is required')
        return self

    def storage_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode='python', exclude_unset=True)
        if self.provenance is not None:
            payload['provenance'] = [
                ref.model_dump(mode='python', exclude_none=True, exclude_defaults=True) for ref in self.provenance
            ]
        return {
            key: value
            for key, value in payload.items()
            if key in self.model_fields_set or key in {'status', 'completed'}
        }


class ActionItemCreateRequest(CanonicalTaskCreate):
    """Released-client adapter; unknown historical fields remain ignored at this route boundary."""

    model_config = ConfigDict(extra='ignore')


class ActionItemUpdateRequest(CanonicalTaskUpdate):
    """Released-client adapter with the desktop's explicit due-date clearing flag."""

    model_config = ConfigDict(extra='ignore')

    clear_due_at: bool = False

    def storage_payload(self) -> dict[str, Any]:
        payload = super().storage_payload()
        payload.pop('clear_due_at', None)
        if self.clear_due_at:
            payload['due_at'] = None
        return payload


class ActionItemResponse(BaseModel):
    """Canonical response plus stable fields required by deployed old clients."""

    model_config = ConfigDict(extra='ignore')

    id: StableId
    task_id: Optional[StableId] = None
    description: str
    status: TaskStatus = TaskStatus.active
    completed: bool
    goal_id: Optional[StableId] = None
    workstream_id: Optional[StableId] = None
    owner: TaskOwner = TaskOwner.unknown
    due_at: Optional[datetime] = None
    due_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    source: str = 'legacy'
    provenance: list[EvidenceRef] = Field(default_factory=list)
    priority: Optional[TaskPriority] = None
    sort_order: int = 0
    indent_level: int = 0
    recurrence_rule: Optional[str] = None
    recurrence_parent_id: Optional[StableId] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    superseded_by: Optional[StableId] = None
    conversation_id: Optional[str] = None
    is_locked: bool = False
    exported: bool = False
    export_date: Optional[datetime] = None
    export_platform: Optional[str] = None
    apple_reminder_id: Optional[str] = None

    @model_validator(mode='before')
    @classmethod
    def project_legacy_fields(cls, value: Any):
        if not isinstance(value, dict):
            return value
        data = dict(value)
        data.setdefault('task_id', data.get('id'))
        if 'status' not in data and 'completed' in data:
            if data.get('deleted'):
                data['status'] = TaskStatus.cancelled
            else:
                data['status'] = TaskStatus.completed if data.get('completed') else TaskStatus.active
        if 'completed' not in data and 'status' in data:
            data['completed'] = data['status'] == TaskStatus.completed or data['status'] == TaskStatus.completed.value
        data.setdefault('owner', TaskOwner.unknown)
        data.setdefault('source', 'legacy')
        data.setdefault('provenance', [])
        return data

    @field_validator('due_at', 'created_at', 'updated_at', 'completed_at', 'export_date', mode='after')
    @classmethod
    def _naive_timestamps_are_utc(cls, value: Optional[datetime]) -> Optional[datetime]:
        # Firestore timestamps are UTC; a naive one leaking through serializes
        # without an offset, which Dart/JS decode as LOCAL wall time and Swift's
        # ISO8601 decoder rejects outright. Stamp UTC so every emitted timestamp
        # carries an explicit offset (contracts/parity/README.md). utcoffset()
        # rather than tzinfo: a tzinfo whose utcoffset() returns None is still
        # semantically naive and would serialize offsetless all the same.
        if value is not None and value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class ActionItemsResponse(BaseModel):
    """List envelope; ``truncated`` is set only when the request's list-read
    budget ended the aggregate scan early (#11831) — such pages may not be a
    complete prefix, so ``has_more`` is forced true as well."""

    action_items: list[ActionItemResponse]
    has_more: bool = False
    truncated: bool = False


class ActionItemsSearchResponse(BaseModel):
    action_items: list[ActionItemResponse]


class ConversationActionItemsResponse(BaseModel):
    action_items: list[ActionItemResponse]
    conversation_id: str


class PendingSyncResponse(BaseModel):
    pending_export: list[ActionItemResponse]
    synced_items: list[ActionItemResponse]


class TaskCreatePayload(BaseModel):
    """Candidate task-create payload; envelope metadata is intentionally absent."""

    model_config = ConfigDict(extra='forbid')

    description: str = Field(min_length=1, max_length=4096)
    owner: TaskOwner = TaskOwner.unknown
    due_at: Optional[AwareDatetime] = None
    due_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    priority: Optional[TaskPriority] = None
    recurrence_rule: Optional[str] = Field(default=None, max_length=128)
    recurrence_parent_id: Optional[StableId] = None


class TaskChangePayload(BaseModel):
    model_config = ConfigDict(extra='forbid')

    description: Optional[str] = Field(default=None, min_length=1, max_length=4096)
    status: Optional[TaskStatus] = None
    owner: Optional[TaskOwner] = None
    due_at: Optional[AwareDatetime] = None
    due_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    priority: Optional[TaskPriority] = None
    recurrence_rule: Optional[str] = Field(default=None, max_length=128)
    recurrence_parent_id: Optional[StableId] = None
    superseded_by: Optional[StableId] = None

    @model_validator(mode='after')
    def require_change(self):
        if not self.model_fields_set:
            raise ValueError('task change requires at least one field')
        return self


__all__ = [
    'ActionItemResponse',
    'ActionItemCreateRequest',
    'ActionItemUpdateRequest',
    'ActionItemsResponse',
    'ActionItemsSearchResponse',
    'CanonicalTaskCreate',
    'CanonicalTaskUpdate',
    'ConversationActionItemsResponse',
    'EvidenceKind',
    'EvidenceRef',
    'EvidenceScope',
    'PendingSyncResponse',
    'TaskChangePayload',
    'TaskCreatePayload',
    'TaskOwner',
    'TaskPriority',
    'TaskStatus',
]
