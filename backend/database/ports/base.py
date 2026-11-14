"""Backend-neutral, per-space units of work. Personal space ids equal user ids."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, Protocol, TypeVar, TYPE_CHECKING

if TYPE_CHECKING:
    from .action_items import ActionItemsTx
    from .goals import GoalsTx
    from .workstreams import WorkstreamsTx
    from .folders import FoldersTx
    from .people import PeopleTx

SpaceId = str
T = TypeVar('T')


class RevisionConflict(Exception):
    def __init__(self, space_id: SpaceId, entity: str, entity_id: str, current_revision: int):
        self.space_id, self.entity, self.entity_id = space_id, entity, entity_id
        self.current_revision = current_revision
        super().__init__(f'{entity}/{entity_id}: revision conflict ({current_revision})')


class MutationConflict(Exception):
    def __init__(self, mutation_id: str):
        self.mutation_id = mutation_id
        super().__init__(f'mutation {mutation_id}: conflicting replay')


@dataclass(frozen=True)
class Page(Generic[T]):
    items: list[T]
    next_cursor: str | None


class CommitFence(Protocol):
    def before_commit(self) -> None: ...

    def after_commit(self, committed: bool) -> None: ...


class SpaceTx(Protocol):
    """Restartable transaction body; complete all reads before the first write.

    A1 does not buffer writes. A second read-then-write operation after a write
    is invalid on Firestore. Do not perform external IO or irreversible effects.
    """

    @property
    def space_id(self) -> SpaceId: ...

    @property
    def folders(self) -> FoldersTx: ...

    @property
    def people(self) -> PeopleTx: ...

    @property
    def action_items(self) -> ActionItemsTx: ...

    @property
    def goals(self) -> GoalsTx: ...

    @property
    def workstreams(self) -> WorkstreamsTx: ...

    def register_commit_fence(self, fence: CommitFence) -> None: ...


class SpaceStore(Protocol):
    def run(self, body: Callable[[SpaceTx], T]) -> T: ...

    def run_with_contention_retry(self, body: Callable[[SpaceTx], T], *, operation_name: str) -> T: ...
