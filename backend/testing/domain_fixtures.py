"""Domain contract matrix. All seeded documents are synthetic and loopback-only.

Postgres discovery is shared with store_fixtures; B1 supplies the domain factory.
Required backends fail instead of silently skipping missing infrastructure.
"""

from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import uuid4

import pytest

from database.cells.adapters import CellSpaceStore
from database.cells.store import CellStore
from database.jobstore.connection import Pool
from testing.cells_fixtures import cells_dsn

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

DOMAIN_BACKENDS = ('sim', 'emulator', 'postgres')
WORKFLOW_ENTITIES = (
    'action_items',
    'goals',
    'workstreams',
    'goal_events',
    'goal_history',
    'workstream_events',
    'workstream_artifacts',
    'workstream_checkpoints',
    'task_intelligence_control',
    'workflow_mutation_receipts',
    'users',
)


@dataclass
class DomainHarness:
    name: str
    uid_suffix: str = field(default_factory=lambda: uuid4().hex)
    cleanup_steps: list[Callable[[], None]] = field(default_factory=list)
    _stores: dict[str, Any] = field(default_factory=dict)
    _client: Any = None
    _pool: Any = None

    def uid(self, label: str) -> str:
        return f'port-test-{label}-{self.uid_suffix}'

    def space(self, label: str) -> str:
        return self.uid(label)

    def store(self, space_id: str) -> SpaceStore:
        if not space_id.endswith('-' + self.uid_suffix):
            raise ValueError('space must belong to this synthetic harness')
        if space_id not in self._stores:
            if self.name == 'postgres':
                # Explicit synthetic enrollment; compatible with B2 admission.
                with self._pool.connection() as conn:
                    conn.execute(
                        'INSERT INTO space_heads (space_id,next_seq,epoch,updated_at) VALUES (%s,0,1,0) ON CONFLICT DO NOTHING',
                        (space_id,),
                    )
                self._stores[space_id] = CellSpaceStore(self._pool, space_id)
                return self._stores[space_id]
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

    def action_items(self, space_id):
        self.store(space_id)
        return self._stores[space_id].action_items

    def goals(self, space_id):
        self.store(space_id)
        return self._stores[space_id].goals

    def workstreams(self, space_id):
        self.store(space_id)
        return self._stores[space_id].workstreams

    def _entity_ref(self, space_id, entity, entity_id):
        owner = self._client.collection('users').document(space_id)
        if entity == 'users':
            return owner
        nested = {
            'goal_events': ('goals', 'events'),
            'goal_history': ('goals', 'goal_history'),
            'workstream_events': ('workstreams', 'events'),
            'workstream_artifacts': ('workstreams', 'artifact_refs'),
            'workstream_checkpoints': ('workstreams', 'continuation_checkpoints'),
        }
        if entity in nested:
            parent, child = nested[entity]
            parent_id, child_id = entity_id.split('/', 1)
            return owner.collection(parent).document(parent_id).collection(child).document(child_id)
        return owner.collection(entity).document(entity_id)

    def seed(self, space_id: str, entity: str, entity_id: str, data: dict) -> None:
        """Synthetic legacy/cross-domain fixtures, never part of the domain protocol."""
        if (
            not space_id.endswith(self.uid_suffix)
            or entity not in ('folders', 'people', 'conversations') + WORKFLOW_ENTITIES
        ):
            raise ValueError('seed must belong to this harness')
        self.store(space_id)
        if self.name == 'sim':
            self._stores[space_id].state[entity][entity_id] = dict(data)
        elif self.name == 'postgres':
            self._stores[space_id].cell.run(
                space_id, lambda tx: tx.put(entity, entity_id, data), actor_uid=space_id, now=0
            )
        else:
            self._entity_ref(space_id, entity, entity_id).set(data)

    def read(self, space_id: str, entity: str, entity_id: str) -> dict | None:
        """Inspect a synthetic cross-domain fixture without exposing adapter internals."""
        if (
            not space_id.endswith('-' + self.uid_suffix)
            or entity not in ('folders', 'people', 'conversations') + WORKFLOW_ENTITIES
        ):
            raise ValueError('read must belong to this harness')
        self.store(space_id)
        if self.name == 'sim':
            row = self._stores[space_id].state[entity].get(entity_id)
            return dict(row) if row is not None else None
        if self.name == 'postgres':
            return self._stores[space_id].cell.read_doc(space_id, entity, entity_id) or None
        return self._entity_ref(space_id, entity, entity_id).get().to_dict()

    def close(self) -> None:
        for step in reversed(self.cleanup_steps):
            step()


def build_backend(name: str) -> DomainHarness:
    if name not in DOMAIN_BACKENDS:
        raise ValueError(name)
    harness = DomainHarness(name)
    if name == 'postgres':
        harness._pool = Pool(cells_dsn(), size=2)

        def cleanup():
            try:
                cell = CellStore(harness._pool)
                for space_id in harness._stores:
                    cell.purge_space(space_id)
            finally:
                harness._pool.close()

        harness.cleanup_steps.append(cleanup)
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


@pytest.fixture(params=DOMAIN_BACKENDS)
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
