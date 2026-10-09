"""Dream self-report v1. Deliberately excludes internal refs and model diagnostics."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DreamRunRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')


class DreamReportEdit(BaseModel):
    kind: str
    target_label: str
    before: str
    after: str
    reason: str
    evidence_count: int
    outcome: Literal['shadow', 'applied', 'suppressed', 'suggest_only', 'edit_cap', 'invalid_evidence']


class DreamReportQuestion(BaseModel):
    kind: str
    text: str


class DreamReportTask(BaseModel):
    description: str


class DreamReportTerm(BaseModel):
    kind: str
    spelling: str
    aliases: list[str]


class DreamReportFeedback(BaseModel):
    component: str
    failure_class: str
    severity: str
    count: int


class DreamRun(BaseModel):
    run_id: str
    created_at: datetime
    trigger: Literal['schedule', 'manual']
    status: Literal['complete', 'failed', 'deadline', 'idle']
    error_type: str | None = None
    records_read: int = 0
    records_queued_after: int = 0
    dirty_dropped: int = 0
    tokens: int = 0
    cost_usd: float = 0
    edits: list[DreamReportEdit] = Field(default_factory=list)
    questions: list[DreamReportQuestion] = Field(default_factory=list)
    slow_tasks: list[DreamReportTask] = Field(default_factory=list)
    vocabulary: list[DreamReportTerm] = Field(default_factory=list)
    feedback: list[DreamReportFeedback] = Field(default_factory=list)
    privacy_rejected: int = 0


class DreamRunsResponse(BaseModel):
    mode: Literal['shadow', 'on']
    passes_today: int
    passes_limit: int
    manual_runs_today: int
    manual_runs_limit: int
    queued_changes: int
    runs: list[DreamRun]
