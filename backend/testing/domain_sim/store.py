"""Independent domain reference adapter; no SDK, IO, or Firestore-shaped objects."""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from functools import wraps
from threading import RLock
from typing import Callable, TypeVar

from database.ports.base import MutationConflict, Page, RevisionConflict, SpaceTx
from database.ports.folders import FolderCreate, FolderEntity, FolderUpdate, SYSTEM_FOLDERS
from database.ports.people import GenerationFence, PersonDraft, PersonEntity
from models.other import VoiceReadiness, voice_readiness

T = TypeVar('T')


def _scalar_order(value):
    if value is None:
        return (0, 0)
    if isinstance(value, bool):
        return (1, value)
    if isinstance(value, (int, float)):
        return (2, value)
    if isinstance(value, datetime):
        return (3, value.timestamp())
    if isinstance(value, str):
        return (4, value.encode())
    return (5, repr(value))


def _locked(fn):
    @wraps(fn)
    def call(self, *args, **kwargs):
        with self.store.lock:
            return fn(self, *args, **kwargs)

    return call


class SimSpaceStore:
    def __init__(self, space_id: str):
        self.space_id = space_id
        self.lock = RLock()
        self.state = {'folders': {}, 'people': {}, 'conversations': {}, 'receipts': {}, 'generation': 0}
        self.folders = SimFolders(self)
        self.people = SimPeople(self)

    def run(self, body: Callable[[SpaceTx], T]) -> T:
        with self.lock:
            before = deepcopy(self.state)
            try:
                return body(self)
            except BaseException:
                self.state = before
                raise

    def run_with_contention_retry(self, body: Callable[[SpaceTx], T], *, operation_name: str) -> T:
        return self.run(body)


class _Repo:
    def __init__(self, store: SimSpaceStore):
        self.store = store

    def receipt(self, mutation_id, operation, data):
        digest = hashlib.sha256(json.dumps([operation, data], sort_keys=True, default=str).encode()).hexdigest()
        prior = self.store.state['receipts'].get(mutation_id) if mutation_id is not None else None
        if prior is not None and prior[0] != digest:
            raise MutationConflict(mutation_id)
        return digest, prior[1] if prior is not None else None

    def save(self, mutation_id, digest, result):
        if mutation_id is not None:
            self.store.state['receipts'][mutation_id] = (digest, deepcopy(result))

    def check(self, entity, entity_id, data, expected_revision):
        revision = data.get('revision', 1)
        if expected_revision is not None and revision != expected_revision:
            raise RevisionConflict(self.store.space_id, entity, entity_id, revision)
        return revision


class SimFolders(_Repo):
    def entity(self, row):
        return FolderEntity.model_construct(**deepcopy(row))

    @_locked
    def list(self, *, limit: int | None = None, cursor: str | None = None) -> Page[FolderEntity]:
        if limit is not None and limit <= 0:
            raise ValueError('limit must be positive')
        rows = sorted(
            (row for row in self.store.state['folders'].values() if 'order' in row),
            key=lambda row: (_scalar_order(row['order']), row['id'].encode()),
        )
        if cursor is not None:
            order, entity_id = json.loads(base64.urlsafe_b64decode(cursor))
            rows = [
                row
                for row in rows
                if (_scalar_order(row['order']), row['id'].encode()) > (_scalar_order(order), entity_id.encode())
            ]
        items = rows if limit is None else rows[:limit]
        next_cursor = None
        if items and len(items) < len(rows):
            next_cursor = base64.urlsafe_b64encode(
                json.dumps([items[-1].get('order', 0), items[-1]['id']]).encode()
            ).decode()
        return Page([self.entity(row) for row in items], next_cursor)

    @_locked
    def get(self, folder_id: str) -> FolderEntity | None:
        row = self.store.state['folders'].get(folder_id)
        return self.entity(row) if row is not None else None

    @_locked
    def create(self, draft: FolderCreate, *, mutation_id: str | None = None) -> FolderEntity:
        digest, prior = self.receipt(mutation_id, 'folders.create', draft.model_dump())
        if prior is not None:
            current = self.get(prior)
            if current is None:
                raise MutationConflict(mutation_id)
            return current
        existing = sorted(
            (row['order'] for row in self.store.state['folders'].values() if 'order' in row), key=_scalar_order
        )
        highest = existing[-1] if existing else 0
        order = (highest if type(highest) is int else 0) + 1
        now = datetime.now(timezone.utc)
        row = FolderEntity(
            id=str(uuid.uuid4()),
            **{**draft.model_dump(), 'color': draft.color or '#6B7280', 'icon': draft.icon or '📁'},
            order=order,
            created_at=now,
            updated_at=now,
        )
        self.store.state['folders'][row.id] = row.model_dump()
        self.save(mutation_id, digest, row.id)
        return row

    @_locked
    def update(
        self,
        folder_id: str,
        patch: FolderUpdate,
        *,
        expected_revision: int | None = None,
        mutation_id: str | None = None,
    ) -> FolderEntity | None:
        digest, prior = self.receipt(mutation_id, 'folders.update', [folder_id, patch.model_dump(exclude_unset=True)])
        row = self.store.state['folders'].get(folder_id)
        if row is None or prior is not None:
            return self.get(folder_id)
        revision = self.check('folders', folder_id, row, expected_revision)
        data = {
            k: v
            for k, v in patch.model_dump(exclude_unset=True).items()
            if v is not None or k not in ('name', 'color', 'icon', 'order')
        }
        if data:
            row.update(data, updated_at=datetime.now(timezone.utc), revision=revision + 1)
        self.save(mutation_id, digest, folder_id)
        return self.entity(row)

    @_locked
    def get_by_category_mapping(self, category_mapping: str) -> FolderEntity | None:
        return next((row for row in self.list().items if row.category_mapping == category_mapping), None)

    @_locked
    def delete(
        self,
        folder_id: str,
        *,
        move_to_folder_id: str | None = None,
        expected_revision: int | None = None,
        mutation_id: str | None = None,
    ) -> bool:
        digest, prior = self.receipt(mutation_id, 'folders.delete', [folder_id, move_to_folder_id])
        if prior is not None:
            return prior
        row = self.store.state['folders'].get(folder_id)
        if expected_revision is not None:
            if row is None:
                return False
            self.check('folders', folder_id, row, expected_revision)
        target = move_to_folder_id
        if not target:
            default = next((f for f in self.list().items if f.is_default and f.id != folder_id), None)
            target = default.id if default else None
        for conv in self.store.state['conversations'].values():
            if conv.get('folder_id') == folder_id:
                conv.update(folder_id=target, folder_user_set=True)
        if target:
            self.refresh_conversation_count(target)
        self.store.state['folders'].pop(folder_id, None)
        self.save(mutation_id, digest, True)
        return True

    @_locked
    def reorder(self, folder_ids: list[str], *, mutation_id: str | None = None) -> bool:
        digest, prior = self.receipt(mutation_id, 'folders.reorder', folder_ids)
        if prior is not None:
            return prior
        for fid in folder_ids:
            if fid not in self.store.state['folders']:
                raise KeyError(fid)
        for order, fid in enumerate(folder_ids):
            row = self.store.state['folders'][fid]
            row.update(order=order, updated_at=datetime.now(timezone.utc), revision=row.get('revision', 0) + 2)
        self.save(mutation_id, digest, True)
        return True

    @_locked
    def initialize_system(self, *, mutation_id: str | None = None) -> list[FolderEntity]:
        digest, prior = self.receipt(mutation_id, 'folders.initialize', None)
        if self.store.state['folders'] or prior is not None:
            if prior is None:
                self.save(mutation_id, digest, True)
            return self.list().items
        now = datetime.now(timezone.utc)
        for order, config in enumerate(SYSTEM_FOLDERS):
            # IDs are adapter-owned. Their exact encoding is outside the contract.
            fid = str(uuid.uuid5(uuid.NAMESPACE_URL, self.store.space_id + '/' + config['category_mapping']))
            row = FolderEntity(id=fid, **config, is_system=True, order=order, created_at=now, updated_at=now)
            self.store.state['folders'][fid] = row.model_dump()
        self.save(mutation_id, digest, True)
        return self.list().items

    @_locked
    def conversations_in_folder(
        self, folder_id: str, *, limit: int = 100, offset: int = 0, include_discarded: bool = False
    ) -> list[dict]:
        rows = [
            row
            for row in self.store.state['conversations'].values()
            if row.get('folder_id') == folder_id and (include_discarded or row.get('discarded') is False)
        ]
        rows.sort(key=lambda row: row['created_at'], reverse=True)
        return deepcopy([row for row in rows[offset : offset + limit] if not row.get('deleted')])

    @_locked
    def refresh_conversation_count(
        self, folder_id: str, *, expected_revision: int | None = None, mutation_id: str | None = None
    ) -> int:
        digest, prior = self.receipt(mutation_id, 'folders.count', folder_id)
        if prior is not None:
            return prior
        count = sum(
            row.get('folder_id') == folder_id and row.get('discarded') is False
            for row in self.store.state['conversations'].values()
        )
        row = self.store.state['folders'].get(folder_id)
        if row is not None:
            revision = self.check('folders', folder_id, row, expected_revision)
            row.update(conversation_count=count, revision=row.get('revision', 0) + 2)
        self.save(mutation_id, digest, count)
        return count

    @_locked
    def move_conversation(self, conversation_id: str, folder_id: str | None, *, mutation_id: str | None = None) -> bool:
        return bool(self._move([conversation_id], folder_id, mutation_id, 'move'))

    @_locked
    def bulk_move_conversations(
        self, conversation_ids: list[str], folder_id: str, *, mutation_id: str | None = None
    ) -> int:
        return self._move(conversation_ids, folder_id, mutation_id, 'bulk')

    def _move(self, ids, folder_id, mutation_id, operation):
        digest, prior = self.receipt(mutation_id, 'folders.' + operation, [ids, folder_id])
        if prior is not None:
            return prior
        if not ids:
            self.save(mutation_id, digest, 0)
            return 0
        affected = {folder_id} if folder_id else set()
        count = 0
        for cid in dict.fromkeys(ids):
            row = self.store.state['conversations'].get(cid)
            if row is not None:
                if row.get('folder_id'):
                    affected.add(row['folder_id'])
                row.update(folder_id=folder_id, folder_user_set=True)
                count += 1
        for fid in affected:
            self.refresh_conversation_count(fid)
        self.save(mutation_id, digest, count)
        return count


class SimPeople(_Repo):
    @_locked
    def set_pinned(
        self,
        person_id: str,
        pinned: bool,
        *,
        now: datetime | None = None,
        expected_revision: int | None = None,
        mutation_id: str | None = None,
    ) -> PersonEntity | None:
        digest, prior = self.receipt(mutation_id, 'people.pin', [person_id, pinned])
        row = self.store.state['people'].get(person_id)
        if row is None:
            return None
        if prior is None:
            revision = self.check('people', person_id, row, expected_revision)
            if bool(row.get('pinned')) != pinned:
                now = now or datetime.now(timezone.utc)
                row.update(pinned=pinned, pinned_at=now if pinned else None, updated_at=now, revision=revision + 1)
                self.store.state['generation'] += 1
            self.save(mutation_id, digest, person_id)
        return PersonEntity.model_construct(**deepcopy(row))

    @_locked
    def get_or_create_by_name(self, draft: PersonDraft, *, mutation_id: str | None = None) -> PersonEntity:
        digest, prior = self.receipt(mutation_id, 'people.create', draft.model_dump())
        if prior is not None:
            return PersonEntity.model_construct(**self._project(self.store.state['people'][prior]))
        existing = next(
            (
                row
                for row in sorted(self.store.state['people'].values(), key=lambda value: value['id'].encode())
                if row.get('name') == draft.name and row.get('is_dismissed') is not True
            ),
            None,
        )
        if existing is None:
            data = {**draft.model_dump(), 'revision': 1}
            self.store.state['people'][draft.id] = {**data, 'is_user_created': True}
            self.store.state['generation'] += 1
        else:
            data = self._project(existing)
        self.save(mutation_id, digest, data['id'])
        return PersonEntity.model_construct(**data)

    @staticmethod
    def _project(person: dict) -> dict:
        # The reference has no learning-job ledger; model the settled, no-job
        # projection and preserve all unrelated heterogeneous fields.
        data = deepcopy(person)
        if data.get('voice_learning_state') != 'disabled' and voice_readiness(data) == VoiceReadiness.ready:
            data['voice_learning_state'] = 'learned'
        elif data.get('voice_learning_state') in (None, 'pending', 'learned'):
            data['voice_learning_state'] = 'unknown'
        if data.get('voice_learning_state') != 'needs_more_speech':
            data['voice_needed_seconds'] = None
        return data

    @_locked
    def read_generation(self) -> GenerationFence | None:
        generation = self.store.state['generation']
        return GenerationFence(value=generation, token=str(generation)) if generation else None
