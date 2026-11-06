"""Typed task storage contracts. Wire validation belongs to callers."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterator, List, Protocol

from pydantic import BaseModel, ConfigDict
from .base import Page


class ActionItemTransactionLimitError(ValueError):
    """An atomic task operation would exceed the adapter's transaction budget."""


class TaskRelationshipConflictError(ValueError):
    pass


class ActionItemEntity(BaseModel):
    model_config = ConfigDict(extra='allow')
    id: str
    description: str = ''
    completed: bool | None = None
    deleted: bool | None = None
    status: str | None = None
    due_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None
    goal_id: str | None = None
    workstream_id: str | None = None
    conversation_id: str | None = None
    account_generation: int | None = None
    revision: int = 1


class ActionItemDraft(BaseModel):
    model_config = ConfigDict(extra='allow')
    data: dict[str, Any]


class TaskRelationshipRule(BaseModel):
    goal_id: str | None = None
    workstream_id: str | None = None
    allow_ended_goal: bool = False
    account_generation: int | None = None


class ActionItemsTx(Protocol):
    def read_control(self) -> dict[str, Any]: ...

    def validate_task_relationship(self, rule: TaskRelationshipRule) -> None: ...

    def create(
        self,
        draft: ActionItemDraft,
        *,
        idempotency_key: str | None = None,
        document_id: str | None = None,
        reuse_finished: bool = True,
        mutation_id: str | None = None,
    ) -> str: ...

    def create_batch(
        self, drafts: List[ActionItemDraft], *, document_ids: List[str | None] | None = None
    ) -> List[str]: ...

    def update(
        self,
        action_item_id: str,
        patch: dict[str, Any],
        *,
        expected_chat_state: dict[str, Any] | None = None,
        expected_revision: int | None = None,
        mutation_id: str | None = None,
    ) -> bool: ...

    def delete(self, action_item_id: str) -> bool: ...

    def delete_batch(self, ids: List[str]) -> List[str]: ...

    def retire_for_conversation(
        self, conversation_id: str, *, active_ids: List[str], replacements: dict[str, str] | None = None
    ) -> int: ...


class ActionItemsRepo(ActionItemsTx, Protocol):
    def get(self, action_item_id: str) -> ActionItemEntity | None: ...

    def get_by_ids(self, ids: List[str]) -> List[ActionItemEntity]: ...

    def list(
        self,
        *,
        conversation_id: str | None = None,
        completed: bool | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        due_start_date: datetime | None = None,
        due_end_date: datetime | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> Page[ActionItemEntity]: ...

    def find_active_by_description(self, description: str) -> ActionItemEntity | None: ...

    def list_ids(self, *, completed: bool | None = None) -> List[str]: ...

    def iter_all(self) -> Iterator[ActionItemEntity]: ...

    def purge(self, space_id: str) -> int: ...

    def sync_page(
        self, *, updated_since: datetime | None = None, limit: int = 100, cursor: str | None = None
    ) -> Page[ActionItemEntity]: ...
