"""Staged tasks — AI-generated tasks awaiting user promotion to action items.

Response wire shapes for /v1/staged-tasks*. Source of truth for the staged-task
response schema; routers/database construct dicts matching these fields.

Collection: users/{uid}/staged_tasks.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class StagedTask(BaseModel):
    """A single staged task awaiting promotion to an action item."""

    id: str = Field(description='Unique staged-task identifier.')
    description: str = Field(description='Task description text.')
    completed: bool = Field(description='Whether the staged task has been closed or promoted.')
    created_at: datetime = Field(description='Creation timestamp (UTC).')
    updated_at: datetime = Field(description='Last update timestamp (UTC).')
    due_at: Optional[datetime] = Field(default=None, description='Optional due date for the task.')
    source: Optional[str] = Field(default=None, description='Origin of the task, e.g. a screenshot extraction.')
    priority: Optional[str] = Field(default=None, description='Task priority, e.g. "high", "medium", "low".')
    metadata: Optional[str] = Field(default=None, description='Opaque metadata associated with the task.')
    category: Optional[str] = Field(default=None, description='Task category.')
    relevance_score: Optional[int] = Field(
        default=None, description='Relevance score (0-1000) used for promotion ordering.'
    )


class StagedTaskListResponse(BaseModel):
    """Paginated list of staged tasks."""

    items: list[StagedTask] = Field(description='Staged tasks for the current page.')
    has_more: bool = Field(description='Whether additional pages of staged tasks exist beyond this result.')


class PromoteStagedTaskResponse(BaseModel):
    """Outcome of promoting the top-relevance staged task to an action item."""

    promoted: bool = Field(description='Whether a staged task was promoted to an action item.')
    reason: Optional[str] = Field(
        default=None, description='Why promotion was skipped, e.g. "No staged tasks available".'
    )
    # `promoted_task` is an action_item document owned by the action_items domain
    # (canonical response model: ActionItemResponse in routers/action_items.py, which
    # intentionally omits staged-enrichment fields like source/priority/category).
    # It is kept as an opaque dict here so every stored field survives serialization
    # without duplicating the action_item schema in the staged-task domain.
    promoted_task: Optional[dict] = Field(default=None, description='The promoted action_item document, if any.')


class MigrateConversationItemsResponse(BaseModel):
    """Outcome of migrating conversation items to staged tasks.

    Preserves the `migrated` count that the handler returns alongside the status ack;
    using StatusResponse here would silently drop it (Pydantic extra='ignore').
    """

    status: str = Field(default='ok', description='Ack status, e.g. "ok".')
    migrated: int = Field(default=0, description='Number of conversation items migrated to staged tasks.')
    deleted: int = Field(default=0, description='Number of items deleted during migration (reserved; currently 0).')
