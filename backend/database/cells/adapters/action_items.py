"""Cell-backed action items domain operations; writes use the shared cell flush."""

from __future__ import annotations

import os
import base64
import json
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Iterator
from database import chat_edits
from database.action_item_codec import prepare_action_item_for_read, prepare_action_item_for_write
from database.ports.action_items import (
    ActionItemDraft,
    ActionItemEntity,
    TaskRelationshipRule,
    TaskRelationshipConflictError,
)

from database.ports.base import Page

from ._base import ACCOUNT_GENERATION_SQL, WorkflowRepo, atomic, generation_matches

# Normalize DESC created time to a negative epoch for a uniform keyset. The UTC
# conversion makes EXTRACT immutable, so migration 0003 can index the same key.
_LIST_KEY = """coalesce(q_completed,false), (q_due_at IS NULL),
    coalesce(extract(epoch FROM q_due_at AT TIME ZONE 'UTC'),'Infinity'::numeric),
    -coalesce(extract(epoch FROM q_created_at AT TIME ZONE 'UTC'),'-Infinity'::numeric),
    entity_id COLLATE "C" """


class CellActionItems(WorkflowRepo):
    domain = 'action_items'
    entity_type = ActionItemEntity
    collection = 'action_items'

    @atomic
    def read_control(self) -> dict[str, Any]:
        return deepcopy(self.store.state['task_intelligence_control'].get('state', {}))

    @atomic
    def validate_task_relationship(self, rule: TaskRelationshipRule) -> None:
        if rule.goal_id is not None:
            goal = self.store.goals.get(rule.goal_id)
            if goal is None:
                raise TaskRelationshipConflictError('goal does not exist')
            if rule.account_generation is not None and not generation_matches(
                self.store.goals._read(rule.goal_id) or {}, rule.account_generation
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
            if rule.account_generation is not None and not generation_matches(
                self.store.workstreams._read(rule.workstream_id) or {}, rule.account_generation
            ):
                raise TaskRelationshipConflictError('workstream account generation mismatch')
            if workstream.goal_id != rule.goal_id:
                raise TaskRelationshipConflictError('task goal_id must match workstream goal_id')

    @atomic
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
            where = "q_idempotency_key=%s AND " + ACCOUNT_GENERATION_SQL + " AND q_deleted IS DISTINCT FROM TRUE"
            if not reuse_finished:
                where += " AND q_completed IS DISTINCT FROM TRUE AND coalesce(q_status,'active')='active'"
            matches = self.store.query('action_items', where, [idempotency_key, generation], limit=1)
            if matches:
                entity_id = matches[0][0]
                self.save(mutation_id, digest, entity_id)
                return entity_id
        if document_id is not None and document_id in self._rows():
            if not generation_matches(self._rows()[document_id], generation):
                raise TaskRelationshipConflictError('document id belongs to another account generation')
            self.save(mutation_id, digest, document_id)
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

    @atomic
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

    @atomic
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
            prior_chat = {key: row[key] for key in chat_edits.FIELDS['task'] if key in row}
            if chat_edits.encode(prior_chat) != expected_chat_state['before']:
                raise PermissionError('Edit target changed before write')
            expected_chat_state['after'] = chat_edits.encode({**prior_chat, **payload})
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

    @atomic
    def delete(self, action_item_id: str) -> bool:
        if action_item_id not in self._rows():
            return False
        self._write_task()
        del self._rows()[action_item_id]
        return True

    @atomic
    def delete_batch(self, ids: list[str]) -> list[str]:
        self._lock_in_order('action_items', ids)
        for entity_id in ids:
            self.delete(entity_id)
        return list(ids)

    @atomic
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

    @atomic
    def get(self, action_item_id: str) -> ActionItemEntity | None:
        row = self._read(action_item_id)
        return (
            self._entity(prepare_action_item_for_read(deepcopy(row)), entity_id=action_item_id)
            if row is not None
            else None
        )

    @atomic
    def get_by_ids(self, ids: list[str]) -> list[ActionItemEntity]:
        self._lock_in_order('action_items', ids)
        return [row for row in (self.get(i) for i in ids) if row is not None]

    @atomic
    def iter_all(self) -> Iterator[ActionItemEntity]:
        for entity_id in sorted(self._rows(), key=lambda v: v.encode()):
            if not self._rows()[entity_id].get('deleted'):
                row = self.get(entity_id)
                if row is not None:
                    yield row

    @atomic
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
        filters, params = ['q_deleted IS DISTINCT FROM TRUE'], []
        if conversation_id is not None:
            filters.append('q_conversation_id=%s')
            params.append(conversation_id)
        if completed is not None:
            filters.append('coalesce(q_completed,false)=%s')
            params.append(completed)
        for column, lower, upper in [
            ('q_created_at', start_date, end_date),
            ('q_due_at', due_start_date, due_end_date),
        ]:
            if lower is not None:
                filters.append(column + '>=%s')
                params.append(lower)
            if upper is not None:
                filters.append(column + '<=%s')
                params.append(upper)
        if cursor is not None:
            filters.append('(' + _LIST_KEY + ') > (%s,%s,%s,%s,%s)')
            params.extend(json.loads(base64.urlsafe_b64decode(cursor)))
        rows = self.store.query(
            'action_items', ' AND '.join(filters), params, order=_LIST_KEY, limit=None if limit is None else limit + 1
        )
        items = [self._entity(prepare_action_item_for_read({**row, 'id': eid})) for eid, row in rows]
        more = limit is not None and len(items) > limit
        items = items if limit is None else items[:limit]
        resume = None
        if more and items:
            last = items[-1]
            resume = base64.urlsafe_b64encode(
                json.dumps(
                    [
                        bool(last.completed),
                        last.due_at is None,
                        last.due_at.timestamp() if last.due_at else float('inf'),
                        -last.created_at.timestamp() if last.created_at else float('inf'),
                        last.id,
                    ]
                ).encode()
            ).decode()
        return Page(items, resume)

    @atomic
    def find_active_by_description(self, description: str) -> ActionItemEntity | None:
        def normalized(value):
            return value.strip().removeprefix('[screen] ').removesuffix(' [screen]').strip().lower()

        target = normalized(description)
        return (
            next((r for r in self.list(completed=False).items if normalized(r.description) == target), None)
            if target
            else None
        )

    @atomic
    def list_ids(self, *, completed: bool | None = None) -> list[str]:
        return (
            sorted(self._rows(), key=lambda v: v.encode())
            if completed is None
            else [r.id for r in self.list(completed=completed).items]
        )

    @atomic
    def sync_page(
        self, *, updated_since: datetime | None = None, limit: int = 100, cursor: str | None = None
    ) -> Page[ActionItemEntity]:
        if limit <= 0:
            raise ValueError('limit must be positive')
        filters, args = ['q_updated_at IS NOT NULL'], []
        if updated_since is not None:
            filters.append('q_updated_at >= %s')
            args.append(updated_since)
        if cursor is not None:
            timestamp, eid = json.loads(base64.urlsafe_b64decode(cursor))
            filters.append('(q_updated_at, entity_id COLLATE "C") > (%s,%s)')
            args.extend([datetime.fromtimestamp(timestamp, timezone.utc), eid])
        rows = self.store.query(
            'action_items', ' AND '.join(filters), args, order='q_updated_at, entity_id COLLATE "C"', limit=limit + 1
        )
        items = [self._entity(prepare_action_item_for_read({**row, 'id': eid})) for eid, row in rows[:limit]]
        resume = None
        if len(rows) > limit:
            last = items[-1]
            assert last.updated_at is not None
            resume = base64.urlsafe_b64encode(json.dumps([last.updated_at.timestamp(), last.id]).encode()).decode()
        return Page(items, resume)
