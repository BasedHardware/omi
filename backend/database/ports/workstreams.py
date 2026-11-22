"""Typed workstreams storage contracts, independent of SDK and wire models."""

from __future__ import annotations

from typing import Any, Protocol
from pydantic import BaseModel, ConfigDict


class WorkstreamStoreError(RuntimeError):
    pass


class WorkstreamNotFoundError(WorkstreamStoreError):
    pass


class WorkstreamConflictError(WorkstreamStoreError):
    pass


class WorkstreamGenerationMismatchError(WorkstreamStoreError):
    pass


class WorkstreamEntity(BaseModel):
    model_config = ConfigDict(extra='allow')
    id: str = ''
    workstream_id: str = ''
    goal_id: str | None = None
    title: str = ''
    status: str | None = None
    account_generation: int = 0
    revision: int = 1


class WorkstreamCreate(BaseModel):
    data: dict[str, Any]


class WorkstreamUpdate(BaseModel):
    data: dict[str, Any]


class WorkstreamEventEntity(BaseModel):
    model_config = ConfigDict(extra='allow')
    event_id: str
    workstream_id: str
    sequence: int = 0


class ArtifactDescriptorEntity(BaseModel):
    model_config = ConfigDict(extra='allow')
    artifact_id: str
    workstream_id: str
    status: str | None = None


class ContinuationCheckpointEntity(BaseModel):
    model_config = ConfigDict(extra='allow')
    checkpoint_id: str
    workstream_id: str


class WorkstreamsTx(Protocol):

    def get(self, workstream_id: str) -> WorkstreamEntity | None: ...

    def create(self, draft: WorkstreamCreate, *, mutation_id: str | None = None) -> WorkstreamEntity: ...

    def update(
        self, workstream_id: str, patch: WorkstreamUpdate, *, idempotency_key: str, account_generation: int
    ) -> WorkstreamEntity: ...

    def append_event(
        self, workstream_id: str, event: dict[str, Any], *, idempotency_key: str, account_generation: int
    ) -> WorkstreamEventEntity: ...

    def create_artifact_descriptor(
        self, workstream_id: str, proposal: dict[str, Any], *, idempotency_key: str, account_generation: int
    ) -> ArtifactDescriptorEntity: ...

    def transition_artifact_status(
        self,
        workstream_id: str,
        artifact_id: str,
        request: dict[str, Any],
        *,
        idempotency_key: str,
        account_generation: int,
    ) -> ArtifactDescriptorEntity: ...

    def upsert_continuation_checkpoint(
        self, workstream_id: str, checkpoint: dict[str, Any], *, idempotency_key: str, account_generation: int
    ) -> ContinuationCheckpointEntity: ...

    def resolve_candidate(self, candidate: dict[str, Any], account_generation: int) -> dict[str, Any]: ...

    def resolve_work_intent(
        self, request: dict[str, Any], *, idempotency_key: str, account_generation: int
    ) -> dict[str, Any]: ...

    def import_task_goal_links(
        self, request: dict[str, Any], *, idempotency_key: str, account_generation: int
    ) -> dict[str, Any]: ...


class WorkstreamsRepo(WorkstreamsTx, Protocol):
    """Standalone aggregate read views retain the serving module contracts."""

    def list_open(self, *, limit: int = 500, account_generation: int | None = None) -> list[WorkstreamEntity]: ...

    def list_for_goal(
        self, goal_id: str, *, include_archived: bool = False, limit: int = 100
    ) -> list[WorkstreamEntity]: ...

    def list_events(
        self, workstream_id: str, *, after_sequence: int = 0, limit: int = 100
    ) -> list[WorkstreamEventEntity]: ...

    def list_artifact_descriptors(self, workstream_id: str, *, limit: int = 100) -> list[ArtifactDescriptorEntity]: ...

    def list_continuation_checkpoints(self, workstream_id: str) -> list[ContinuationCheckpointEntity]: ...

    def get_goal_detail(self, goal_id: str) -> dict[str, Any]: ...

    def get_workstream_detail(self, workstream_id: str) -> dict[str, Any]: ...

    def purge(self, space_id: str) -> int: ...
