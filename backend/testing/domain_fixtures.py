"""Domain contract matrix. All seeded documents are synthetic and loopback-only.

Postgres discovery is shared with store_fixtures; B1 supplies the domain factory.
Required backends fail instead of silently skipping missing infrastructure.
"""

from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import uuid4

import pytest

from database.folders import FirestoreFolders
from database.people import FirestorePeople
from database.ports.base import SpaceStore
from database.ports.folders import FoldersRepo
from database.ports.people import PeopleRepo
from database.space_store import FirestoreSpaceStore
from testing.domain_sim.store import SimSpaceStore
from testing.store_fixtures import (
    BackendUnavailable,
    LocalPostgres,
    _emulator_client,
    postgres_dsn,
    required_backends,
)

DOMAIN_BACKENDS = ('sim', 'emulator')


@dataclass
class DomainHarness:
    name: str
    uid_suffix: str = field(default_factory=lambda: uuid4().hex)
    cleanup_steps: list[Callable[[], None]] = field(default_factory=list)
    _stores: dict[str, Any] = field(default_factory=dict)
    _client: Any = None

    def uid(self, label: str) -> str:
        return f'port-test-{label}-{self.uid_suffix}'

    def space(self, label: str) -> str:
        return self.uid(label)

    def store(self, space_id: str) -> SpaceStore:
        if not space_id.endswith('-' + self.uid_suffix):
            raise ValueError('space must belong to this synthetic harness')
        if space_id not in self._stores:
            self._stores[space_id] = (
                SimSpaceStore(space_id)
                if self.name == 'sim'
                else FirestoreSpaceStore(space_id, firestore_client=self._client)
            )
        return self._stores[space_id]

    def folders(self, space_id: str) -> FoldersRepo:
        self.store(space_id)
        return self._stores[space_id].folders

    def people(self, space_id: str) -> PeopleRepo:
        self.store(space_id)
        return self._stores[space_id].people

    def seed(self, space_id: str, entity: str, entity_id: str, data: dict) -> None:
        """Synthetic legacy/cross-domain fixtures, never part of the domain protocol."""
        if not space_id.endswith(self.uid_suffix) or entity not in ('folders', 'people', 'conversations'):
            raise ValueError('seed must belong to this harness')
        self.store(space_id)
        if self.name == 'sim':
            self._stores[space_id].state[entity][entity_id] = {**data, 'id': entity_id}
        else:
            self._client.collection('users').document(space_id).collection(entity).document(entity_id).set(data)

    def read(self, space_id: str, entity: str, entity_id: str) -> dict | None:
        """Inspect a synthetic cross-domain fixture without exposing adapter internals."""
        if not space_id.endswith('-' + self.uid_suffix) or entity not in ('folders', 'people', 'conversations'):
            raise ValueError('read must belong to this harness')
        self.store(space_id)
        if self.name == 'sim':
            row = self._stores[space_id].state[entity].get(entity_id)
            return dict(row) if row is not None else None
        return (
            self._client.collection('users').document(space_id).collection(entity).document(entity_id).get().to_dict()
        )

    def close(self) -> None:
        for step in reversed(self.cleanup_steps):
            step()


def build_backend(name: str) -> DomainHarness:
    if name == 'postgres':
        raise BackendUnavailable('postgres domain adapter lands with the cells store (B1)')
    if name not in DOMAIN_BACKENDS:
        raise ValueError(name)
    harness = DomainHarness(name)
    if name == 'emulator':
        harness._client = _emulator_client()

        def cleanup():
            try:
                for space_id in harness._stores:
                    harness._client.recursive_delete(harness._client.collection('users').document(space_id))
            finally:
                harness._client.close()

        harness.cleanup_steps.append(cleanup)
    return harness


@pytest.fixture(params=DOMAIN_BACKENDS + (('postgres',) if 'postgres' in required_backends() else ()))
def domain_backend(request):
    try:
        harness = build_backend(request.param)
    except BackendUnavailable as exc:
        if request.param in required_backends():
            pytest.fail(str(exc))
        pytest.skip(str(exc))
    try:
        yield harness
    finally:
        harness.close()
