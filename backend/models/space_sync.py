"""Wire models for the dark spaces device-sync protocol."""

import json
from datetime import datetime
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, StrictInt, field_validator


class SpaceChangeEntry(BaseModel):
    seq: int
    entity: str
    entity_id: str
    op: Literal['upsert', 'delete']
    rev: int
    actor_uid: str
    client_mutation_id: str | None
    ts: float


class SpaceRow(BaseModel):
    entity: str
    entity_id: str
    author_id: str
    rev: int
    doc: dict[str, Any]
    updated_at: float


class SpaceChangesResponse(BaseModel):
    entries: list[SpaceChangeEntry]
    rows: list[SpaceRow]
    next_cursor: int
    head: int
    epoch: int


class SpaceSnapshotResponse(BaseModel):
    rows: list[SpaceRow]
    entries: list[SpaceChangeEntry]
    next_page_token: str | None
    head: int
    epoch: int


class SpaceCursorRequest(BaseModel):
    model_config = {'extra': 'forbid'}

    device_id: str = Field(pattern=r'^[A-Za-z0-9_.:@-]{1,128}$')
    last_seq: int = Field(ge=0)


class SpaceCursorResponse(BaseModel):
    status: Literal['ok']
    last_seq: int
    head: int
    epoch: int


class PatchSpaceEntityOperation(BaseModel):
    model_config = {'extra': 'forbid'}

    type: Literal['patch']
    fields: dict[str, Any]


class DeleteSpaceEntityOperation(BaseModel):
    model_config = {'extra': 'forbid'}

    type: Literal['delete']


SpaceMutationOperation = Annotated[
    Union[PatchSpaceEntityOperation, DeleteSpaceEntityOperation], Field(discriminator='type')
]


class SpaceMutationRequest(BaseModel):
    model_config = {'extra': 'forbid'}

    entity: str = Field(pattern=r'^[a-z][a-z0-9_]{0,39}$')
    entity_id: str = Field(min_length=1, max_length=256, pattern=r'^[^\x00]{1,256}$')
    client_mutation_id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9._:-]*$', max_length=128)
    # StrictInt first preserves integer sequence tokens instead of coercing them to dates.
    base_revision: Union[StrictInt, datetime]
    operation: SpaceMutationOperation

    @field_validator('base_revision', mode='before')
    @classmethod
    def revision_token(cls, value):
        if isinstance(value, bool) or not isinstance(value, (int, str, datetime)):
            raise ValueError('base_revision must be an integer or timezone-aware datetime')
        return value

    @field_validator('base_revision')
    @classmethod
    def aware_revision(cls, value):
        if isinstance(value, datetime) and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError('base_revision datetime must be timezone-aware')
        return value

    @field_validator('operation')
    @classmethod
    def bounded_operation(cls, value):
        encoded = json.dumps(value.model_dump(mode='json'), sort_keys=True, separators=(',', ':'), ensure_ascii=True)
        if len(encoded.encode('utf-8')) > 128 * 1024:
            raise ValueError('operation exceeds 128 KiB')
        return value


class SpaceMutationResponse(BaseModel):
    status: Literal['ok']
    client_mutation_id: str
    entity: str
    entity_id: str
    rev: int
    seq: int
    replayed: bool


class SpaceMutationConflictResponse(BaseModel):
    status: Literal['conflict']
    code: Literal['base_revision_mismatch', 'mutation_id_reused', 'revision_unavailable']
    client_mutation_id: str
    entity: str
    entity_id: str
    row: SpaceRow | None
