"""Independent domain reference adapter; no SDK, IO, or Firestore-shaped objects."""

from __future__ import annotations

import os
import base64
import hashlib
import json
import uuid
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timezone
from functools import wraps
from threading import RLock
from typing import Any, Callable, Iterator, TypeVar
from zoneinfo import ZoneInfo
from database.action_item_codec import prepare_action_item_for_read, prepare_action_item_for_write
from database.ports.action_items import (
    ActionItemDraft,
    ActionItemEntity,
    TaskRelationshipRule,
    TaskRelationshipConflictError,
)
from database.ports.goals import (
    GoalCreate,
    GoalUpdate,
    GoalEntity,
    GoalProgressEventEntity,
    GoalConflictError,
    GoalNotFoundError,
)
from database.read_boundary import parse_payload_strict
from models.workstream import WorkstreamEvent, WorkstreamUpdate as WorkstreamPatch
from models.goal import GoalProgressEvent
from pydantic import ValidationError
from database.ports.workstreams import (
    WorkstreamCreate,
    WorkstreamUpdate,
    WorkstreamEntity,
    WorkstreamEventEntity,
    ArtifactDescriptorEntity,
    ContinuationCheckpointEntity,
    WorkstreamNotFoundError,
    WorkstreamConflictError,
    WorkstreamGenerationMismatchError,
)

from database.ports.base import MutationConflict, Page, RevisionConflict, SpaceTx
from database.ports.folders import FolderCreate, FolderEntity, FolderUpdate, SYSTEM_FOLDERS
from database.ports.people import GenerationFence, PersonDraft, PersonEntity
from models.other import VoiceReadiness, voice_readiness

T = TypeVar('T')


def _chat_encode(value):
    """Independent reference for the chat snapshot wire encoding."""
    if isinstance(value, datetime):
        return {'__chat_datetime__': value.isoformat()}
    if isinstance(value, bytes):
        return {'__chat_bytes__': base64.b64encode(value).decode()}
    if isinstance(value, dict):
        return {key: _chat_encode(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_chat_encode(item) for item in value]
    return value


def _sim_generation_matches(row: dict, expected: int) -> bool:
    """Twin of the cells generation filter: missing is 0, only JSON numbers match."""
    if 'account_generation' not in row:
        return expected == 0
    stored = row['account_generation']
    return isinstance(stored, (int, float)) and not isinstance(stored, bool) and stored == expected


def _sim_jsonb_text(value) -> str:
    """Render like PostgreSQL jsonb::text: object keys by (length, bytes)."""
    if isinstance(value, dict):
        keys = sorted(value, key=lambda key: (len(key.encode()), key.encode()))
        return (
            '{'
            + ', '.join(f'{json.dumps(key, ensure_ascii=False)}: {_sim_jsonb_text(value[key])}' for key in keys)
            + '}'
        )
    if isinstance(value, (list, tuple)):
        return '[' + ', '.join(_sim_jsonb_text(item) for item in value) + ']'
    return json.dumps(value, ensure_ascii=False, default=str)


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
    return (5, _sim_jsonb_text(value))


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
        for entity in (
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
            'receipt_domains',
        ):
            self.state[entity] = {}
        self.fence_log = []
        self._fences = None
        self.action_items = SimActionItems(self)
        self.goals = SimGoals(self)
        self.workstreams = SimWorkstreams(self)
        self.folders = SimFolders(self)
        self.people = SimPeople(self)

    def register_commit_fence(self, fence) -> None:
        if self._fences is None:
            raise RuntimeError('commit fences require a unit of work')
        self._fences.append(fence)

    def _task_write(self):
        if self._fences is None:
            self.fence_log.extend(['before_commit', 'after_commit:True'])
        elif 'task' not in self._fences:
            self._fences.append('task')

    def run(self, body: Callable[[SpaceTx], T]) -> T:
        with self.lock:
            before = deepcopy(self.state)
            parent = self._fences
            if parent is not None:
                return body(self)
            self._fences = []
            committed = False
            try:
                result = body(self)
                for fence in self._fences:
                    if fence == 'task':
                        self.fence_log.append('before_commit')
                    else:
                        fence.before_commit()
                committed = True
                return result
            except BaseException:
                self.state = before
                raise
            finally:
                try:
                    with ExitStack() as cleanup:
                        for fence in reversed(self._fences):
                            if fence == 'task':
                                if committed:
                                    cleanup.callback(self.fence_log.append, 'after_commit:True')
                            else:
                                cleanup.callback(fence.after_commit, committed)
                finally:
                    self._fences = parent

    def run_with_contention_retry(self, body: Callable[[SpaceTx], T], *, operation_name: str) -> T:
        return self.run(body)


class _Repo:
    def __init__(self, store: SimSpaceStore):
        self.store = store

    def receipt_entry(self, mutation_id, operation, data):
        digest = hashlib.sha256(json.dumps([operation, data], sort_keys=True, default=str).encode()).hexdigest()
        prior = self.store.state['receipts'].get(mutation_id) if mutation_id is not None else None
        if prior is not None and prior[0] != digest:
            raise MutationConflict(mutation_id)
        return digest, prior

    def receipt(self, mutation_id, operation, data):
        digest, prior = self.receipt_entry(mutation_id, operation, data)
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
            ({**row, 'id': eid} for eid, row in self.store.state['folders'].items() if 'order' in row),
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
        return self.entity({**row, 'id': folder_id}) if row is not None else None

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
        return self.entity({**row, 'id': folder_id})

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
                conv.update(folder_id=target)
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
            {**row, 'id': eid}
            for eid, row in self.store.state['conversations'].items()
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
        return PersonEntity.model_construct(**{**deepcopy(row), 'id': person_id})

    @_locked
    def get_or_create_by_name(self, draft: PersonDraft, *, mutation_id: str | None = None) -> PersonEntity:
        digest, prior = self.receipt(mutation_id, 'people.create', draft.model_dump())
        if prior is not None:
            return PersonEntity.model_construct(
                **self._project({**(self.store.state['people'].get(prior) or {}), 'id': prior})
            )
        existing_id = next(
            (
                eid
                for eid, row in sorted(self.store.state['people'].items(), key=lambda pair: pair[0].encode())
                if row.get('name') == draft.name and row.get('is_dismissed') is not True
            ),
            None,
        )
        existing = self.store.state['people'].get(existing_id) if existing_id is not None else None
        if existing is None:
            data = {**draft.model_dump(), 'revision': 1}
            self.store.state['people'][draft.id] = {**data, 'is_user_created': True}
            self.store.state['generation'] += 1
        else:
            data = self._project({**existing, 'id': existing_id})
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


# Workflow reference state is domain-shaped, independently modeled from SDK IO.
class _WorkflowRepo(_Repo):
    entity_type = None
    collection = ''

    def _entity(self, row, *, entity_id=None):
        if row is None:
            return None
        data = deepcopy(row)
        if entity_id is not None:
            data['id'] = entity_id
        return self.entity_type.model_construct(**data)

    def _rows(self):
        return self.store.state[self.collection]

    def _read(self, entity_id):
        return self._rows().get(entity_id)

    def _write_task(self):
        self.store._task_write()

    def _generation(self, expected=None):
        control = self.store.state['task_intelligence_control'].get('state', {})
        generation = control.get('account_generation', 0)
        if expected is not None and (generation != expected or control.get('writes_blocked')):
            raise self.generation_error('account generation mismatch')
        return generation

    def _idempotent(self, operation, key, request, body):
        digest, prior = self.receipt_entry(key, operation, request)
        if prior is not None:
            return deepcopy(prior[1])
        result = body()
        self.save(key, digest, result)
        return result

    def save(self, mutation_id, digest, result):
        super().save(mutation_id, digest, result)
        if mutation_id is not None:
            self.store.state['receipt_domains'][mutation_id] = self.collection

    def purge(self, space_id: str) -> int:
        if space_id != self.store.space_id:
            raise ValueError('purge must belong to this space')
        count = len(self._rows())
        self._rows().clear()
        for key, domain in list(self.store.state['receipt_domains'].items()):
            if domain == self.collection:
                self.store.state['receipts'].pop(key, None)
                del self.store.state['receipt_domains'][key]
                count += 1
        if self.collection == 'action_items':
            count += len(self.store.state['task_intelligence_control'])
            self.store.state['task_intelligence_control'].clear()
        return count


class SimActionItems(_WorkflowRepo):
    entity_type = ActionItemEntity
    collection = 'action_items'

    def read_control(self) -> dict[str, Any]:
        return deepcopy(self.store.state['task_intelligence_control'].get('state', {}))

    def validate_task_relationship(self, rule: TaskRelationshipRule) -> None:
        if rule.goal_id is not None:
            goal = self.store.goals.get(rule.goal_id)
            if goal is None:
                raise TaskRelationshipConflictError('goal does not exist')
            if rule.account_generation is not None and not _sim_generation_matches(
                self.store.state['goals'].get(rule.goal_id) or {}, rule.account_generation
            ):
                raise TaskRelationshipConflictError('goal account generation mismatch')
            if not rule.allow_ended_goal and (
                goal.status in ('achieved', 'abandoned')
                or (goal.status is None and goal.model_extra.get('is_active') is False)
            ):
                raise TaskRelationshipConflictError('ended goal cannot receive new task links')
        if rule.workstream_id is not None:
            workstream = self.store.workstreams.get(rule.workstream_id)
            if workstream is None:
                raise TaskRelationshipConflictError('workstream does not exist')
            if rule.account_generation is not None and not _sim_generation_matches(
                self.store.state['workstreams'].get(rule.workstream_id) or {}, rule.account_generation
            ):
                raise TaskRelationshipConflictError('workstream account generation mismatch')
            if workstream.goal_id != rule.goal_id:
                raise TaskRelationshipConflictError('task goal_id must match workstream goal_id')

    @_locked
    def create(
        self,
        draft: ActionItemDraft,
        *,
        idempotency_key: str | None = None,
        document_id: str | None = None,
        reuse_finished: bool = True,
        mutation_id: str | None = None,
    ) -> str:
        request = [draft.data, idempotency_key, document_id, reuse_finished]
        digest, prior = self.receipt(mutation_id, 'action_items.create', request)
        if prior is not None:
            return prior
        if document_id is not None and not document_id:
            raise ValueError('document_id must not be empty')
        generation = self.read_control().get('account_generation', 0)
        if idempotency_key:
            for entity_id, row in sorted(self._rows().items(), key=lambda pair: pair[0].encode()):
                if (
                    row.get('idempotency_key') == idempotency_key
                    and _sim_generation_matches(row, generation)
                    and not row.get('deleted')
                ):
                    if reuse_finished or (not row.get('completed') and row.get('status', 'active') == 'active'):
                        self.save(mutation_id, digest, entity_id)
                        return entity_id
        if document_id is not None and document_id in self._rows():
            if not _sim_generation_matches(self._rows()[document_id], generation):
                raise TaskRelationshipConflictError('document id belongs to another account generation')
            return document_id
        data = prepare_action_item_for_write(draft.data)
        self.validate_task_relationship(
            TaskRelationshipRule(
                goal_id=data.get('goal_id'), workstream_id=data.get('workstream_id'), account_generation=generation
            )
        )
        now = datetime.now(timezone.utc)
        for field in ('created_at', 'updated_at'):
            if not data.get(field):
                data[field] = now
        if data.get('completed') and not data.get('completed_at'):
            data['completed_at'] = now
        entity_id = document_id or uuid.uuid4().hex
        if idempotency_key:
            data['idempotency_key'] = idempotency_key
        self._write_task()
        self._rows()[entity_id] = {**data, 'id': entity_id, 'account_generation': generation}
        self.save(mutation_id, digest, entity_id)
        return entity_id

    @_locked
    def create_batch(self, drafts: list[ActionItemDraft], *, document_ids: list[str | None] | None = None) -> list[str]:
        if len(drafts) > 400 or (document_ids is not None and len(drafts) != len(document_ids)):
            raise ValueError('invalid task batch')
        generation = int(self.read_control().get('account_generation', 0))
        prepared = []
        now = datetime.now(timezone.utc)
        for i, draft in enumerate(drafts):
            data = prepare_action_item_for_write(draft.data)
            self.validate_task_relationship(
                TaskRelationshipRule(
                    goal_id=data.get('goal_id'), workstream_id=data.get('workstream_id'), account_generation=generation
                )
            )
            entity_id = document_ids[i] if document_ids is not None else None
            if entity_id == '':
                raise ValueError('document id must not be empty')
            entity_id = entity_id or uuid.uuid4().hex
            for field in ('created_at', 'updated_at'):
                if not data.get(field):
                    data[field] = now
            if data.get('completed') and not data.get('completed_at'):
                data['completed_at'] = now
            prepared.append((entity_id, {**data, 'id': entity_id, 'account_generation': generation}))
        for entity_id, data in prepared:
            self._write_task()
            # The existing Firestore batch uses set, including occupied ids.
            self._rows()[entity_id] = data
        return [entity_id for entity_id, _ in prepared]

    @_locked
    def update(
        self,
        action_item_id: str,
        patch: dict[str, Any],
        *,
        expected_chat_state: dict[str, Any] | None = None,
        expected_revision: int | None = None,
        mutation_id: str | None = None,
    ) -> bool:
        digest, prior = self.receipt(mutation_id, 'action_items.update', [action_item_id, patch, expected_revision])
        if prior is not None:
            return prior
        row = self._read(action_item_id)
        if row is None:
            return False
        revision = self.check('action_items', action_item_id, row, expected_revision)
        payload = prepare_action_item_for_write(patch, partial=True)
        goal_id, workstream_id = payload.get('goal_id', row.get('goal_id')), payload.get(
            'workstream_id', row.get('workstream_id')
        )
        if 'goal_id' in payload or 'workstream_id' in payload:
            self.validate_task_relationship(
                TaskRelationshipRule(
                    goal_id=goal_id,
                    workstream_id=workstream_id,
                    allow_ended_goal=(goal_id, workstream_id) == (row.get('goal_id'), row.get('workstream_id')),
                )
            )
        if payload.get('exported') is True:
            payload['sync_requested'] = False
        if payload.get('completed') is True and row.get('completed') is True:
            payload['completed_at'] = row.get('completed_at')
        if expected_chat_state is not None:
            fields = ('description', 'completed', 'completed_at', 'due_at', 'updated_at', 'deleted', 'deleted_at')
            prior_chat = {key: row[key] for key in fields if key in row}
            if _chat_encode(prior_chat) != expected_chat_state['before']:
                raise PermissionError('Edit target changed before write')
            expected_chat_state['after'] = _chat_encode({**prior_chat, **payload})
        if (
            expected_chat_state is None
            and os.getenv('OMI_DEV_ACTION_ITEMS_SKIP_NOOP_WRITES_ENABLED', '').lower() != 'false'
            and 'updated_at' not in payload
            and all(
                k in row
                and type(row[k]) is type(v)
                and type(v) in (type(None), bool, int, float, str, datetime)
                and row[k] == v
                for k, v in payload.items()
            )
        ):
            self.save(mutation_id, digest, True)
            return True
        self._write_task()
        row.update(
            payload,
            updated_at=datetime.now(timezone.utc),
            revision=(revision + 1 if expected_revision is not None else row.get('revision', 0) + 2),
        )
        self.save(mutation_id, digest, True)
        return True

    @_locked
    def delete(self, action_item_id: str) -> bool:
        if action_item_id not in self._rows():
            return False
        self._write_task()
        del self._rows()[action_item_id]
        return True

    @_locked
    def delete_batch(self, ids: list[str]) -> list[str]:
        for entity_id in ids:
            self.delete(entity_id)
        return list(ids)

    @_locked
    def retire_for_conversation(
        self, conversation_id: str, *, active_ids: list[str], replacements: dict[str, str] | None = None
    ) -> int:
        rows = [
            (entity_id, row)
            for entity_id, row in self._rows().items()
            if row.get('conversation_id') == conversation_id and entity_id not in active_ids
        ]
        for entity_id, row in rows:
            replacement = (replacements or {}).get(entity_id)
            self._write_task()
            row.update(
                deleted=True,
                status='superseded' if replacement else 'cancelled',
                completed=False,
                completed_at=None,
                superseded_by=replacement,
                updated_at=datetime.now(timezone.utc),
            )
        return len(rows)

    @_locked
    def get(self, action_item_id: str) -> ActionItemEntity | None:
        row = self._read(action_item_id)
        return (
            self._entity(prepare_action_item_for_read(deepcopy(row)), entity_id=action_item_id)
            if row is not None
            else None
        )

    def get_by_ids(self, ids: list[str]) -> list[ActionItemEntity]:
        return [row for row in (self.get(i) for i in ids) if row is not None]

    def iter_all(self) -> Iterator[ActionItemEntity]:
        for entity_id in sorted(self._rows(), key=lambda v: v.encode()):
            if not self._rows()[entity_id].get('deleted'):
                yield self.get(entity_id)

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
    ) -> Page[ActionItemEntity]:
        if limit is not None and limit <= 0:
            raise ValueError('limit must be positive')
        rows = [
            r
            for r in self.iter_all()
            if (conversation_id is None or r.conversation_id == conversation_id)
            and (completed is None or bool(r.completed) == completed)
        ]
        for field, lower, upper in [('created_at', start_date, end_date), ('due_at', due_start_date, due_end_date)]:
            rows = [
                r
                for r in rows
                if (lower is None or (getattr(r, field) is not None and getattr(r, field) >= lower))
                and (upper is None or (getattr(r, field) is not None and getattr(r, field) <= upper))
            ]

        def key(r):
            return (
                bool(r.completed),
                r.due_at is None,
                (r.due_at or datetime.max.replace(tzinfo=timezone.utc)).timestamp(),
                -(r.created_at or datetime.min.replace(tzinfo=timezone.utc)).timestamp(),
                r.id,
            )

        rows.sort(key=key)
        if cursor is not None:
            prior = json.loads(base64.urlsafe_b64decode(cursor))
            rows = [r for r in rows if list(key(r)) > prior]
        items = rows if limit is None else rows[:limit]
        next_cursor = (
            base64.urlsafe_b64encode(json.dumps(list(key(items[-1]))).encode()).decode()
            if items and len(items) < len(rows)
            else None
        )
        return Page(items, next_cursor)

    def find_active_by_description(self, description: str) -> ActionItemEntity | None:
        def normalized(value):
            return value.strip().removeprefix('[screen] ').removesuffix(' [screen]').strip().lower()

        target = normalized(description)
        return (
            next((r for r in self.list(completed=False).items if normalized(r.description) == target), None)
            if target
            else None
        )

    def list_ids(self, *, completed: bool | None = None) -> list[str]:
        return (
            sorted(self._rows(), key=lambda v: v.encode())
            if completed is None
            else [r.id for r in self.list(completed=completed).items]
        )

    def sync_page(
        self, *, updated_since: datetime | None = None, limit: int = 100, cursor: str | None = None
    ) -> Page[ActionItemEntity]:
        if limit <= 0:
            raise ValueError('limit must be positive')
        rows = [self.get(key) for key, raw in self._rows().items() if raw.get('updated_at') is not None]
        rows = [row for row in rows if updated_since is None or row.updated_at >= updated_since]
        rows.sort(key=lambda row: (row.updated_at, row.id.encode()))
        if cursor is not None:
            timestamp, entity_id = json.loads(base64.urlsafe_b64decode(cursor))
            rows = [
                row for row in rows if (row.updated_at.timestamp(), row.id.encode()) > (timestamp, entity_id.encode())
            ]
        items = rows[:limit]
        resume = (
            base64.urlsafe_b64encode(json.dumps([items[-1].updated_at.timestamp(), items[-1].id]).encode()).decode()
            if items and len(rows) > limit
            else None
        )
        return Page(items, resume)


class SimGoals(_WorkflowRepo):
    entity_type = GoalEntity
    collection = 'goals'
    generation_error = GoalConflictError

    def get(self, goal_id: str) -> GoalEntity | None:
        return self._entity(self._read(goal_id), entity_id=goal_id)

    @_locked
    def create(self, draft: GoalCreate, *, mutation_id: str | None = None) -> GoalEntity:
        def build():
            data = deepcopy(draft.data)
            if not data.get('title') or not (data.get('desired_outcome') or data.get('title')):
                raise ValueError('goal title and desired_outcome are required')
            if data.get('status') == 'focused':
                raise GoalConflictError('use explicit focus management after creating a goal')
            gid = data.get('goal_id') or data.get('id') or 'goal_' + uuid.uuid4().hex[:12]
            now = datetime.now(timezone.utc)
            row = {
                **data,
                'id': gid,
                'goal_id': gid,
                'status': data.get('status', 'background'),
                'focus_rank': None,
                'account_generation': self._generation(),
                'latest_progress_sequence': 0,
                'is_active': data.get('status') not in ('achieved', 'abandoned'),
                'created_at': now,
                'updated_at': now,
            }
            self._rows()[gid] = row
            return row

        return self._entity(self._idempotent('goals.create', mutation_id, draft.data, build))

    def create_idempotent(self, draft: GoalCreate, *, idempotency_key: str, account_generation: int) -> GoalEntity:
        self._generation(account_generation)
        return self.create(draft, mutation_id='goal-create:' + str(account_generation) + ':' + idempotency_key)

    def get_user_goal(self) -> GoalEntity | None:
        rows = self.get_user_goals(100)
        rows.sort(
            key=lambda r: (
                0 if r.status == 'focused' else 1,
                r.model_extra.get('focus_rank') if r.model_extra.get('focus_rank') is not None else 5,
                r.model_extra.get('created_at') or datetime.min.replace(tzinfo=timezone.utc),
            )
        )
        return rows[0] if rows else None

    def get_user_goals(self, limit: int = 3) -> list[GoalEntity]:
        rows = [
            {**r, 'id': eid}
            for eid, r in self._rows().items()
            if r.get('is_active') is True and r.get('status') not in ('achieved', 'abandoned')
        ]
        rows.sort(key=lambda r: r.get('created_at') or datetime.min.replace(tzinfo=timezone.utc))
        return [self._entity(r) for r in rows[: max(0, limit)]]

    def get_all(self, *, include_inactive: bool = False, limit: int | None = None) -> list[GoalEntity]:
        rows = [
            {**r, 'id': eid}
            for eid, r in self._rows().items()
            if include_inactive or (r.get('is_active') is True and r.get('status') not in ('achieved', 'abandoned'))
        ]
        rows.sort(key=lambda r: r.get('created_at') or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return [self._entity(r) for r in (rows if limit is None else rows[:limit])]

    @_locked
    def update(
        self, goal_id: str, patch: GoalUpdate, *, expected_revision: int | None = None, mutation_id: str | None = None
    ) -> GoalEntity | None:
        # Identity and generation move only through their own checked operations.
        if forbidden := sorted(set(patch.data) & {'id', 'goal_id', 'account_generation'}):
            raise ValueError(f'goal update cannot change {", ".join(forbidden)}')

        def build():
            row = self._read(goal_id)
            if row is None:
                return None
            revision = self.check('goals', goal_id, row, expected_revision)
            data = {k: v for k, v in patch.data.items() if k not in ('status', 'focus_rank')}
            row.update(
                data,
                updated_at=datetime.now(timezone.utc),
                revision=revision + 1 if expected_revision is not None else row.get('revision', 0) + 2,
            )
            return row

        return self._entity(
            self._idempotent('goals.update', mutation_id, [goal_id, patch.data, expected_revision], build),
            entity_id=goal_id,
        )

    @_locked
    def focus(
        self,
        goal_id: str,
        *,
        idempotency_key: str,
        account_generation: int,
        replacement_goal_id: str | None = None,
        focus_rank: int | None = None,
        focus_cap: int = 5,
    ) -> GoalEntity:
        self._generation(account_generation)

        def build():
            row = self._read(goal_id)
            if row is None:
                raise GoalNotFoundError(goal_id)
            if row.get('status') in ('achieved', 'abandoned'):
                raise GoalConflictError('ended goals cannot be focused')
            focused = {eid: r for eid, r in self._rows().items() if r.get('status') == 'focused' and eid != goal_id}
            if row.get('status') == 'focused' and focus_rank in (None, row.get('focus_rank')):
                return row
            replacement = None
            if len(focused) >= focus_cap:
                replacement = focused.get(replacement_goal_id)
                if replacement is None:
                    raise GoalConflictError('focus set is full; replacement_goal_id is required')
            occupied = {r.get('focus_rank') for r in focused.values() if r is not replacement}
            rank = focus_rank if focus_rank is not None else next((r for r in range(focus_cap) if r not in occupied), 0)
            if rank in occupied:
                raise GoalConflictError('focus_rank is already occupied')
            if replacement is not None:
                replacement.update(status='background', focus_rank=None, updated_at=datetime.now(timezone.utc))
            row.update(status='focused', focus_rank=rank, is_active=True, updated_at=datetime.now(timezone.utc))
            return row

        return self._entity(
            self._idempotent(
                'goals.focus',
                f'focus:{goal_id}:{idempotency_key}',
                [account_generation, replacement_goal_id, focus_rank],
                build,
            ),
            entity_id=goal_id,
        )

    def unfocus(self, goal_id: str, *, idempotency_key: str, account_generation: int) -> GoalEntity:
        self._generation(account_generation)

        def build():
            row = self._read(goal_id)
            if row is None:
                raise GoalNotFoundError(goal_id)
            if row.get('status') == 'focused':
                row.update(status='background', focus_rank=None, updated_at=datetime.now(timezone.utc))
            return row

        return self._entity(
            self._idempotent('goals.unfocus', f'unfocus:{goal_id}:{idempotency_key}', [account_generation], build),
            entity_id=goal_id,
        )

    def transition_lifecycle(
        self, goal_id: str, *, status: str, relationship_disposition: str, idempotency_key: str, account_generation: int
    ) -> GoalEntity:
        self._generation(account_generation)
        if status not in ('paused', 'achieved', 'abandoned'):
            raise ValueError('invalid goal lifecycle target')
        if relationship_disposition not in ('retain', 'detach'):
            raise ValueError('invalid goal relationship disposition')

        def build():
            row = self._read(goal_id)
            if row is None:
                raise GoalNotFoundError(goal_id)
            if relationship_disposition == 'detach':
                for task in self.store.state['action_items'].values():
                    if task.get('goal_id') == goal_id:
                        self._write_task()
                        task['goal_id'] = None
                for workstream in self.store.state['workstreams'].values():
                    if workstream.get('goal_id') == goal_id:
                        workstream['goal_id'] = None
            row.update(
                status=status,
                focus_rank=None,
                is_active=status not in ('achieved', 'abandoned'),
                relationship_disposition=relationship_disposition,
                updated_at=datetime.now(timezone.utc),
            )
            return row

        return self._entity(
            self._idempotent(
                'goals.lifecycle',
                f'lifecycle:{goal_id}:{idempotency_key}',
                [status, relationship_disposition, account_generation],
                build,
            ),
            entity_id=goal_id,
        )

    def _history_date_str(self, now: datetime) -> str:
        # Match database.goals: absent/falsy zones and any lookup/conversion
        # failure fall back to the UTC date supplied by the progress writer.
        try:
            payload = self.store.state['users'].get('profile')
            zone = payload.get('time_zone') if isinstance(payload, dict) else None
            if not zone:
                return now.strftime('%Y-%m-%d')
            return now.astimezone(ZoneInfo(str(zone))).strftime('%Y-%m-%d')
        except Exception:
            return now.strftime('%Y-%m-%d')

    def append_progress_event(
        self, goal_id: str, event: dict[str, Any], *, idempotency_key: str, account_generation: int
    ) -> GoalProgressEventEntity:
        self._generation(account_generation)

        def build():
            row = self._read(goal_id)
            if row is None:
                raise GoalNotFoundError(goal_id)
            now = datetime.now(timezone.utc)
            sequence = row.get('latest_progress_sequence', 0) + 1
            eid = 'gpe_' + uuid.uuid4().hex
            data = {**deepcopy(event), 'event_id': eid, 'goal_id': goal_id, 'sequence': sequence, 'created_at': now}
            self.store.state['goal_events'][goal_id + '/' + eid] = data
            row.update(latest_progress_sequence=sequence, updated_at=now)
            if event.get('metric') is not None:
                row['metric'] = deepcopy(event['metric'])
                day = self._history_date_str(now)
                self.store.state['goal_history'][goal_id + '/' + day] = {
                    'date': day,
                    'value': event['metric']['current'],
                    'recorded_at': now,
                }
            return data

        return GoalProgressEventEntity.model_construct(
            **self._idempotent('goals.event', f'event:{goal_id}:{idempotency_key}', [event, account_generation], build)
        )

    def list_progress_events(self, goal_id: str, *, limit: int = 100) -> list[GoalProgressEventEntity]:
        rows = [
            (k, v)
            for k, v in self.store.state['goal_events'].items()
            if k.startswith(goal_id + '/') and 'sequence' in v
        ]
        rows.sort(key=lambda pair: (_scalar_order(pair[1]['sequence']), pair[0]), reverse=True)
        result = []
        for _, row in rows[:limit]:
            try:
                parsed = GoalProgressEvent.model_validate(deepcopy(row))
            except (ValidationError, TypeError):
                continue
            result.append(GoalProgressEventEntity.model_construct(**parsed.model_dump()))
        return result

    def update_progress(
        self,
        goal_id: str,
        current_value: float,
        *,
        idempotency_key: str | None = None,
        account_generation: int | None = None,
    ) -> GoalEntity | None:
        row = self._read(goal_id)
        if row is None:
            return None
        metric = {**(row.get('metric') or {'type': 'numeric', 'target': 0}), 'current': current_value}
        self.append_progress_event(
            goal_id,
            {'kind': 'metric_update', 'summary': 'Metric updated', 'metric': metric},
            idempotency_key=idempotency_key or uuid.uuid4().hex,
            account_generation=self._generation() if account_generation is None else account_generation,
        )
        return self.get(goal_id)

    def get_history(self, goal_id: str, *, days: int = 30) -> list[dict[str, Any]]:
        rows = [deepcopy(v) for k, v in self.store.state['goal_history'].items() if k.startswith(goal_id + '/')]
        return sorted(rows, key=lambda r: r['date'], reverse=True)[:days]

    def delete(self, goal_id: str) -> bool:
        row = self._read(goal_id)
        if row is None:
            return False
        row.update(
            status='abandoned',
            focus_rank=None,
            is_active=False,
            relationship_disposition='retain',
            updated_at=datetime.now(timezone.utc),
            ended_at=datetime.now(timezone.utc),
        )
        return True

    def read_control(self) -> dict[str, Any]:
        return deepcopy(self.store.state['task_intelligence_control'].get('state', {}))

    def write_control(self, patch: dict[str, Any]) -> None:
        self.store.state['task_intelligence_control'].setdefault('state', {}).update(deepcopy(patch))

    def begin_mutation(
        self, *, operation: str, idempotency_key: str, account_generation: int, request: dict[str, Any]
    ) -> dict[str, Any] | None:
        self._generation(account_generation)
        _, prior = self.receipt(f'{operation}:{account_generation}:{idempotency_key}', operation, request)
        return prior

    def finish_mutation(
        self,
        *,
        operation: str,
        idempotency_key: str,
        account_generation: int,
        request: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        digest, _ = self.receipt(f'{operation}:{account_generation}:{idempotency_key}', operation, request)
        self.save(f'{operation}:{account_generation}:{idempotency_key}', digest, result)

    def purge(self, space_id: str) -> int:
        count = super().purge(space_id)
        for entity in (
            'goal_events',
            'goal_history',
            'task_intelligence_control',
            'workflow_mutation_receipts',
        ):
            count += len(self.store.state[entity])
            self.store.state[entity].clear()
        return count


class SimWorkstreams(_WorkflowRepo):
    entity_type = WorkstreamEntity
    collection = 'workstreams'
    generation_error = WorkstreamGenerationMismatchError

    def _require(self, workstream_id, generation):
        self._generation(generation)
        row = self._read(workstream_id)
        if row is None:
            raise WorkstreamNotFoundError(workstream_id)
        if not _sim_generation_matches(row, generation):
            raise WorkstreamGenerationMismatchError('workstream account generation mismatch')
        return row

    def get(self, workstream_id: str) -> WorkstreamEntity | None:
        return self._entity(self._read(workstream_id), entity_id=workstream_id)

    @_locked
    def create(self, draft: WorkstreamCreate, *, mutation_id: str | None = None) -> WorkstreamEntity:
        def build():
            data = deepcopy(draft.data)
            generation = self._generation()
            self.store.action_items.validate_task_relationship(
                TaskRelationshipRule(goal_id=data.get('goal_id'), account_generation=generation)
            )
            wid = data.get('workstream_id') or data.get('id') or 'workstream_' + uuid.uuid4().hex
            now = datetime.now(timezone.utc)
            row = {
                **data,
                'id': wid,
                'workstream_id': wid,
                'objective': data.get('objective', data.get('title', 'Work')),
                'status': data.get('status', 'open'),
                'current_state_summary': data.get('current_state_summary', ''),
                'latest_event_sequence': 0,
                'account_generation': generation,
                'revision': 1,
                'created_at': now,
                'updated_at': now,
            }
            self._rows()[wid] = row
            return row

        return self._entity(self._idempotent('workstreams.create', mutation_id, draft.data, build))

    def list_open(self, *, limit: int = 500, account_generation: int | None = None) -> list[WorkstreamEntity]:
        rows = [
            {**r, 'id': eid}
            for eid, r in self._rows().items()
            if r.get('status') == 'open'
            and (account_generation is None or _sim_generation_matches(r, account_generation))
        ]
        return [self._entity(r) for r in sorted(rows, key=lambda r: r['updated_at'], reverse=True)[:limit]]

    def list_for_goal(
        self, goal_id: str, *, include_archived: bool = False, limit: int = 100
    ) -> list[WorkstreamEntity]:
        rows = [
            {**r, 'id': eid}
            for eid, r in sorted(self._rows().items(), key=lambda pair: pair[0].encode())
            if r.get('goal_id') == goal_id
        ][:limit]
        rows = [r for r in rows if include_archived or r.get('status') != 'archived']
        return [self._entity(r) for r in sorted(rows, key=lambda r: r['updated_at'], reverse=True)]

    @_locked
    def update(
        self, workstream_id: str, patch: WorkstreamUpdate, *, idempotency_key: str, account_generation: int
    ) -> WorkstreamEntity:
        data = parse_payload_strict(
            WorkstreamPatch,
            patch.data,
            document_path=f'users/{self.store.space_id}/workstreams/{workstream_id}/<update>',
        ).model_dump(mode='python', exclude_unset=True)
        row = self._require(workstream_id, account_generation)

        def build():
            row.update(deepcopy(data), updated_at=datetime.now(timezone.utc))
            return row

        return self._entity(
            self._idempotent(
                'workstreams.update',
                f'ws-update:{workstream_id}:{idempotency_key}',
                [patch.data, account_generation],
                build,
            ),
            entity_id=workstream_id,
        )

    def _event(self, workstream_id, event):
        row = self._rows()[workstream_id]
        sequence = row.get('latest_event_sequence', 0) + 1
        eid = 'wse_' + uuid.uuid4().hex
        now = datetime.now(timezone.utc)
        result = {
            **deepcopy(event),
            'event_id': eid,
            'workstream_id': workstream_id,
            'sequence': sequence,
            'created_at': now,
            'sensitivity': event.get('sensitivity', 'normal'),
        }
        self.store.state['workstream_events'][workstream_id + '/' + eid] = result
        row.update(latest_event_sequence=sequence, updated_at=now, last_meaningful_progress_at=now)
        return result

    @_locked
    def append_event(
        self, workstream_id: str, event: dict[str, Any], *, idempotency_key: str, account_generation: int
    ) -> WorkstreamEventEntity:
        self._require(workstream_id, account_generation)
        result = self._idempotent(
            'workstreams.event',
            f'ws-event:{workstream_id}:{idempotency_key}',
            [event, account_generation],
            lambda: self._event(workstream_id, event),
        )
        return WorkstreamEventEntity.model_construct(**result)

    def list_events(
        self, workstream_id: str, *, after_sequence: int = 0, limit: int = 100
    ) -> list[WorkstreamEventEntity]:
        # Firestore inequality filters match the operand's numeric type, unlike
        # an unfiltered order_by which includes every stored sequence type.
        rows = [
            (k, v)
            for k, v in self.store.state['workstream_events'].items()
            if k.startswith(workstream_id + '/')
            and isinstance(v.get('sequence'), (int, float))
            and not isinstance(v['sequence'], bool)
            and v['sequence'] > after_sequence
        ]
        rows.sort(key=lambda pair: (pair[1]['sequence'], pair[0]))
        result = []
        for _, row in rows[:limit]:
            try:
                parsed = WorkstreamEvent.model_validate(deepcopy(row))
            except (ValidationError, TypeError):
                continue
            result.append(WorkstreamEventEntity.model_construct(**parsed.model_dump()))
        return result

    @_locked
    def create_artifact_descriptor(
        self, workstream_id: str, proposal: dict[str, Any], *, idempotency_key: str, account_generation: int
    ) -> ArtifactDescriptorEntity:
        self._require(workstream_id, account_generation)

        def build():
            rows = [
                r
                for r in self.store.state['workstream_artifacts'].values()
                if r['workstream_id'] == workstream_id and r['logical_key'] == proposal['logical_key']
            ]
            head = max(rows, key=lambda r: r['version']) if rows else None
            if head is None and (proposal['version'] != 1 or proposal.get('supersedes_artifact_id') is not None):
                raise WorkstreamConflictError(
                    'the first logical artifact version must be version 1 without supersession'
                )
            if head is not None and (
                proposal['version'] != head['version'] + 1
                or proposal.get('supersedes_artifact_id') != head['artifact_id']
                or not proposal.get('evidence_event_ids')
            ):
                raise WorkstreamConflictError('artifact version must advance and supersede the current logical head')
            for eid in proposal.get('evidence_event_ids', []):
                if workstream_id + '/' + eid not in self.store.state['workstream_events']:
                    raise WorkstreamConflictError('artifact references a missing workstream event')
            aid = 'artifact_' + uuid.uuid4().hex
            row = {
                **deepcopy(proposal),
                'artifact_id': aid,
                'workstream_id': workstream_id,
                'status': 'draft',
                'created_at': datetime.now(timezone.utc),
            }
            self.store.state['workstream_artifacts'][workstream_id + '/' + aid] = row
            if head is not None:
                head['status'] = 'superseded'
            self._event(workstream_id, {'kind': 'artifact_version', 'summary': 'Artifact version created'})
            return row

        return ArtifactDescriptorEntity.model_construct(
            **self._idempotent(
                'workstreams.artifact',
                f'artifact:{workstream_id}:{idempotency_key}',
                [proposal, account_generation],
                build,
            )
        )

    @_locked
    def transition_artifact_status(
        self,
        workstream_id: str,
        artifact_id: str,
        request: dict[str, Any],
        *,
        idempotency_key: str,
        account_generation: int,
    ) -> ArtifactDescriptorEntity:
        self._require(workstream_id, account_generation)

        def build():
            row = self.store.state['workstream_artifacts'].get(workstream_id + '/' + artifact_id)
            if row is None:
                raise WorkstreamNotFoundError(artifact_id)
            target = request['status']
            if row['status'] != target:
                if {'draft': 'awaiting_review', 'awaiting_review': 'approved', 'approved': 'delivered'}.get(
                    row['status']
                ) != target:
                    raise WorkstreamConflictError('artifact status transition is not allowed')
                row['status'] = target
                self._event(workstream_id, {'kind': 'system', 'summary': 'Artifact status changed'})
            return row

        return ArtifactDescriptorEntity.model_construct(
            **self._idempotent(
                'workstreams.artifact-status',
                f'artifact-status:{artifact_id}:{idempotency_key}',
                [request, account_generation],
                build,
            )
        )

    def list_artifact_descriptors(self, workstream_id: str, *, limit: int = 100) -> list[ArtifactDescriptorEntity]:
        rows = [r for r in self.store.state['workstream_artifacts'].values() if r['workstream_id'] == workstream_id]
        return [
            ArtifactDescriptorEntity.model_construct(**deepcopy(r))
            for r in sorted(rows, key=lambda r: r['created_at'], reverse=True)[:limit]
        ]

    @_locked
    def upsert_continuation_checkpoint(
        self, workstream_id: str, checkpoint: dict[str, Any], *, idempotency_key: str, account_generation: int
    ) -> ContinuationCheckpointEntity:
        row = self._require(workstream_id, account_generation)

        def build():
            if checkpoint['last_event_sequence'] > row.get('latest_event_sequence', 0):
                raise WorkstreamConflictError('checkpoint is ahead of journal')
            cid = 'checkpoint_' + hashlib.sha256((workstream_id + checkpoint['runtime_id']).encode()).hexdigest()[:32]
            key = workstream_id + '/' + cid
            previous = self.store.state['workstream_checkpoints'].get(key)
            if previous is not None and checkpoint['last_event_sequence'] < previous['last_event_sequence']:
                raise WorkstreamConflictError('checkpoint cannot move backward')
            result = {
                **deepcopy(checkpoint),
                'checkpoint_id': cid,
                'workstream_id': workstream_id,
                'updated_at': datetime.now(timezone.utc),
            }
            self.store.state['workstream_checkpoints'][key] = result
            return result

        return ContinuationCheckpointEntity.model_construct(
            **self._idempotent(
                'workstreams.checkpoint',
                f'checkpoint:{workstream_id}:{idempotency_key}',
                [checkpoint, account_generation],
                build,
            )
        )

    def list_continuation_checkpoints(self, workstream_id: str) -> list[ContinuationCheckpointEntity]:
        return [
            ContinuationCheckpointEntity.model_construct(**deepcopy(r))
            for r in self.store.state['workstream_checkpoints'].values()
            if r['workstream_id'] == workstream_id
        ]

    def resolve_candidate(self, candidate: dict[str, Any], account_generation: int) -> dict[str, Any]:
        self._generation(account_generation)
        if candidate.get('subject_kind') != 'workstream' or candidate.get('workstream_proposal') is None:
            raise WorkstreamConflictError('Candidate is not a workstream create proposal')
        proposal = candidate['workstream_proposal']
        receipt = self.resolve_work_intent(
            {
                'origin': 'goal',
                'goal_id': candidate.get('goal_id'),
                'title': proposal['title'],
                'objective': proposal['objective'],
                'anchor_task_description': proposal['anchor_task']['description'],
            },
            idempotency_key='candidate:' + candidate['candidate_id'],
            account_generation=account_generation,
        )
        return {
            'candidate_id': candidate['candidate_id'],
            'status': 'accepted',
            'receipt_id': receipt['receipt_id'],
            'task_id': receipt['task_id'],
            'workstream_id': receipt['workstream_id'],
            'newly_resolved': receipt['newly_created'],
            'resolved_at': receipt['created_at'],
        }

    @_locked
    def resolve_work_intent(
        self, request: dict[str, Any], *, idempotency_key: str, account_generation: int
    ) -> dict[str, Any]:
        self._generation(account_generation)

        def build():
            if request.get('origin') == 'task':
                task = self.store.state['action_items'].get(request['task_id'])
                if task is None:
                    raise WorkstreamNotFoundError(request['task_id'])
                if not (_sim_generation_matches(task, 0) or _sim_generation_matches(task, account_generation)):
                    raise WorkstreamGenerationMismatchError('task account generation mismatch')
                gid = task.get('goal_id')
                tid = request['task_id']
            else:
                gid = request.get('goal_id')
                task = None
            self.store.action_items.validate_task_relationship(
                TaskRelationshipRule(goal_id=gid, account_generation=account_generation)
            )
            if task is not None and task.get('workstream_id'):
                wid = task['workstream_id']
                created = False
            else:
                ws = self.create(
                    WorkstreamCreate(
                        data={
                            'title': request.get('title') or task.get('description', 'Work'),
                            'objective': request.get('objective') or task.get('description', 'Work'),
                            'goal_id': gid,
                        }
                    )
                )
                wid = ws.workstream_id
                if task is None:
                    tid = self.store.action_items.create(
                        ActionItemDraft(
                            data={
                                'description': request['anchor_task_description'],
                                'goal_id': gid,
                                'workstream_id': wid,
                            }
                        )
                    )
                else:
                    self._write_task()
                    task.update(workstream_id=wid, account_generation=account_generation)
                self._event(wid, {'kind': 'system', 'summary': 'Work initiated'})
                created = True
            return {
                'receipt_id': 'intent_' + uuid.uuid4().hex,
                'workstream_id': wid,
                'task_id': tid,
                'goal_id': gid,
                'newly_created': created,
                'created_at': datetime.now(timezone.utc),
            }

        return self._idempotent('workstreams.intent', 'intent:' + idempotency_key, [request, account_generation], build)

    @_locked
    def import_task_goal_links(
        self, request: dict[str, Any], *, idempotency_key: str, account_generation: int
    ) -> dict[str, Any]:
        self._generation(account_generation)

        def build():
            imported = unchanged = 0
            failed = []
            for link in request['links']:
                task = self.store.state['action_items'].get(link['task_id'])
                goal = self.store.state['goals'].get(link['goal_id'])
                valid = (
                    task is not None
                    and goal is not None
                    and (_sim_generation_matches(task, 0) or _sim_generation_matches(task, account_generation))
                    and _sim_generation_matches(goal, account_generation)
                    and task.get('goal_id') in (None, link['goal_id'])
                )
                if valid and task.get('workstream_id'):
                    ws = self._rows().get(task['workstream_id'])
                    valid = (
                        ws is not None
                        and ws.get('goal_id') == link['goal_id']
                        and _sim_generation_matches(ws, account_generation)
                    )
                if not valid:
                    failed.append(link['task_id'])
                elif task.get('goal_id') == link['goal_id']:
                    unchanged += 1
                    if _sim_generation_matches(task, 0):
                        self._write_task()
                        task['account_generation'] = account_generation
                else:
                    imported += 1
                    self._write_task()
                    task.update(
                        goal_id=link['goal_id'],
                        account_generation=account_generation,
                        updated_at=datetime.now(timezone.utc),
                    )
            return {'imported': imported, 'unchanged': unchanged, 'failed': len(failed), 'failure_task_ids': failed}

        return self._idempotent('workstreams.import', 'import:' + idempotency_key, [request, account_generation], build)

    def get_goal_detail(self, goal_id: str) -> dict[str, Any]:
        goal = self.store.goals.get(goal_id)
        if goal is None:
            raise GoalNotFoundError(goal_id)
        return {
            'goal': goal.model_dump(),
            'active_threads': [r.model_dump() for r in self.list_for_goal(goal_id)],
            'tasks': [r.model_dump() for r in self.store.action_items.iter_all() if r.goal_id == goal_id],
            'progress_events': [r.model_dump() for r in self.store.goals.list_progress_events(goal_id)],
        }

    def get_workstream_detail(self, workstream_id: str) -> dict[str, Any]:
        row = self.get(workstream_id)
        if row is None:
            raise WorkstreamNotFoundError(workstream_id)
        return {
            'workstream': row.model_dump(),
            'recent_events': [r.model_dump() for r in self.list_events(workstream_id)],
            'tasks': [r.model_dump() for r in self.store.action_items.iter_all() if r.workstream_id == workstream_id],
        }

    def purge(self, space_id: str) -> int:
        count = super().purge(space_id)
        for entity in ('workstream_events', 'workstream_artifacts', 'workstream_checkpoints'):
            count += len(self.store.state[entity])
            self.store.state[entity].clear()
        return count
