"""Typed People preference operations; heterogeneous learning fields pass through."""

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict


class PersonEntity(BaseModel):
    model_config = ConfigDict(extra='allow')
    id: str
    name: str = ''
    pinned: bool | None = None
    pinned_at: datetime | None = None
    is_dismissed: bool | None = None
    is_user_created: bool | None = None
    updated_at: datetime | None = None
    revision: int = 1


class PersonDraft(BaseModel):
    model_config = ConfigDict(extra='allow')
    id: str
    name: str


class GenerationFence(BaseModel):
    value: int
    token: str


class PeopleTx(Protocol):
    def set_pinned(
        self,
        person_id: str,
        pinned: bool,
        *,
        now: datetime | None = None,
        expected_revision: int | None = None,
        mutation_id: str | None = None,
    ) -> PersonEntity | None: ...

    def get_or_create_by_name(self, draft: PersonDraft, *, mutation_id: str | None = None) -> PersonEntity: ...

    def read_generation(self) -> GenerationFence | None: ...


class PeopleRepo(PeopleTx, Protocol):
    pass
