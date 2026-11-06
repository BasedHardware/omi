"""Typed goals storage contracts, independent of SDK and wire models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol
from pydantic import BaseModel, ConfigDict


class GoalStoreError(RuntimeError):
    pass


class GoalNotFoundError(GoalStoreError):
    pass


class GoalConflictError(GoalStoreError):
    pass


class GoalValidationError(GoalStoreError):
    """Request input rejected at the store seam (e.g. an alias merge that makes
    the metric contradict itself). Maps to 422 at the route, not 500."""

    pass


class GoalEntity(BaseModel):
    model_config = ConfigDict(extra='allow')
    id: str
    goal_id: str | None = None
    title: str = ''
    status: str | None = None
    account_generation: int = 0
    revision: int = 1


class GoalCreate(BaseModel):
    data: dict[str, Any]


class GoalUpdate(BaseModel):
    data: dict[str, Any]


class GoalProgressEventEntity(BaseModel):
    model_config = ConfigDict(extra='allow')
    event_id: str
    goal_id: str
    sequence: int = 0
    created_at: datetime | None = None


class GoalsTx(Protocol):

    def get(self, goal_id: str) -> GoalEntity | None: ...

    def create(self, draft: GoalCreate, *, mutation_id: str | None = None) -> GoalEntity: ...

    def create_idempotent(self, draft: GoalCreate, *, idempotency_key: str, account_generation: int) -> GoalEntity: ...

    def update(
        self, goal_id: str, patch: GoalUpdate, *, expected_revision: int | None = None, mutation_id: str | None = None
    ) -> GoalEntity | None: ...

    def focus(
        self,
        goal_id: str,
        *,
        idempotency_key: str,
        account_generation: int,
        replacement_goal_id: str | None = None,
        focus_rank: int | None = None,
        focus_cap: int = 5,
    ) -> GoalEntity: ...

    def unfocus(self, goal_id: str, *, idempotency_key: str, account_generation: int) -> GoalEntity: ...

    def transition_lifecycle(
        self, goal_id: str, *, status: str, relationship_disposition: str, idempotency_key: str, account_generation: int
    ) -> GoalEntity: ...

    def append_progress_event(
        self, goal_id: str, event: dict[str, Any], *, idempotency_key: str, account_generation: int
    ) -> GoalProgressEventEntity: ...

    def update_progress(
        self,
        goal_id: str,
        current_value: float,
        *,
        idempotency_key: str | None = None,
        account_generation: int | None = None,
    ) -> GoalEntity | None: ...

    def delete(self, goal_id: str) -> bool: ...

    def read_control(self) -> dict[str, Any]: ...

    def write_control(self, patch: dict[str, Any]) -> None: ...

    def begin_mutation(
        self, *, operation: str, idempotency_key: str, account_generation: int, request: dict[str, Any]
    ) -> dict[str, Any] | None: ...

    def finish_mutation(
        self,
        *,
        operation: str,
        idempotency_key: str,
        account_generation: int,
        request: dict[str, Any],
        result: dict[str, Any],
    ) -> None: ...


class GoalsRepo(GoalsTx, Protocol):
    """Standalone aggregate read views retain the serving module contracts."""

    def get_user_goal(self) -> GoalEntity | None: ...

    def get_user_goals(self, limit: int = 3) -> list[GoalEntity]: ...

    def get_all(self, *, include_inactive: bool = False, limit: int | None = None) -> list[GoalEntity]: ...

    def list_progress_events(self, goal_id: str, *, limit: int = 100) -> list[GoalProgressEventEntity]: ...

    def get_history(self, goal_id: str, *, days: int = 30) -> list[dict[str, Any]]: ...

    def purge(self, space_id: str) -> int: ...
