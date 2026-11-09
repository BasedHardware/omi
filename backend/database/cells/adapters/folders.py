"""Cell-backed folders domain operations; writes use the shared cell flush."""

from __future__ import annotations

import base64
import json
import uuid
from copy import deepcopy
from datetime import datetime, timezone

from database.ports.base import MutationConflict, Page
from database.ports.folders import FolderCreate, FolderEntity, FolderUpdate, SYSTEM_FOLDERS

from ._base import Repo, atomic, scalar_order

# The immutable SQL function is shared with the expression index. Return its
# exact value for cursors too: Python repr differs from jsonb::text for legacy
# objects/arrays, and Python timestamps can lose PostgreSQL's numeric precision.
_FOLDER_KEY = 'cell_folder_order_key(q_order)'


class CellFolders(Repo):
    domain = 'folders'

    @atomic
    def entity(self, row):
        return FolderEntity.model_construct(**deepcopy(row))

    @atomic
    def list(self, *, limit: int | None = None, cursor: str | None = None) -> Page[FolderEntity]:
        if limit is not None and limit <= 0:
            raise ValueError('limit must be positive')
        where, args = 'q_order IS NOT NULL', []
        if cursor is not None:
            value, eid = json.loads(base64.urlsafe_b64decode(cursor))
            where += ' AND (' + _FOLDER_KEY + ', entity_id COLLATE "C") > (%s::jsonb,%s)'
            args = [value, eid]
        rows = self.store.query(
            'folders',
            where,
            args,
            order=_FOLDER_KEY + ', entity_id COLLATE "C"',
            limit=None if limit is None else limit + 1,
            columns='entity_id, doc, ' + _FOLDER_KEY + '::text',
        )
        more = limit is not None and len(rows) > limit
        page = rows if limit is None else rows[:limit]
        items = [self.entity({**row, 'id': eid}) for eid, row, _ in page]
        resume = base64.urlsafe_b64encode(json.dumps([page[-1][2], page[-1][0]]).encode()).decode() if more else None
        return Page(items, resume)

    @atomic
    def get(self, folder_id: str) -> FolderEntity | None:
        row = self.store.state['folders'].get(folder_id)
        return self.entity({**row, 'id': folder_id}) if row is not None else None

    @atomic
    def create(self, draft: FolderCreate, *, mutation_id: str | None = None) -> FolderEntity:
        digest, prior = self.receipt(mutation_id, 'folders.create', draft.model_dump())
        if prior is not None:
            current = self.get(prior)
            if current is None:
                assert mutation_id is not None
                raise MutationConflict(mutation_id)
            return current
        existing = sorted(
            (row['order'] for row in self.store.state['folders'].values() if 'order' in row), key=scalar_order
        )
        highest = existing[-1] if existing else 0
        order = (highest if type(highest) is int else 0) + 1
        now = datetime.now(timezone.utc)
        row = FolderEntity(
            id=str(uuid.uuid4()),
            name=draft.name,
            description=draft.description,
            color=draft.color or '#6B7280',
            icon=draft.icon or '📁',
            order=order,
            created_at=now,
            updated_at=now,
        )
        self.store.state['folders'][row.id] = row.model_dump()
        self.save(mutation_id, digest, row.id)
        return row

    @atomic
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

    @atomic
    def get_by_category_mapping(self, category_mapping: str) -> FolderEntity | None:
        return next((row for row in self.list().items if row.category_mapping == category_mapping), None)

    @atomic
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
        # Lock in flush order: conversations before folders.
        moved = [conv for conv in self.store.state['conversations'].values() if conv.get('folder_id') == folder_id]
        target = move_to_folder_id
        if not target:
            default = next((f for f in self.list().items if f.is_default and f.id != folder_id), None)
            target = default.id if default else None
        self._lock_in_order('folders', [folder_id, target])
        row = self.store.state['folders'].get(folder_id)
        if expected_revision is not None:
            if row is None:
                return False
            self.check('folders', folder_id, row, expected_revision)
        for conv in moved:
            conv.update(folder_id=target)
        if target:
            self.refresh_conversation_count(target)
        self.store.state['folders'].pop(folder_id, None)
        self.save(mutation_id, digest, True)
        return True

    @atomic
    def reorder(self, folder_ids: list[str], *, mutation_id: str | None = None) -> bool:
        digest, prior = self.receipt(mutation_id, 'folders.reorder', folder_ids)
        if prior is not None:
            return prior
        self._lock_in_order('folders', folder_ids)
        for fid in folder_ids:
            if fid not in self.store.state['folders']:
                raise KeyError(fid)
        for order, fid in enumerate(folder_ids):
            row = self.store.state['folders'][fid]
            row.update(order=order, updated_at=datetime.now(timezone.utc), revision=row.get('revision', 0) + 2)
        self.save(mutation_id, digest, True)
        return True

    @atomic
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

    @atomic
    def conversations_in_folder(
        self, folder_id: str, *, limit: int = 100, offset: int = 0, include_discarded: bool = False
    ) -> list[dict]:
        where = "jsonb_typeof(doc->'folder_id')='string' AND doc->>'folder_id'=%s"
        if not include_discarded:
            where += " AND doc->'discarded'='false'::jsonb"
        rows = self.store.query(
            'conversations',
            where,
            [folder_id],
            order='q_created_at DESC, entity_id COLLATE "C"',
            limit=limit,
            offset=offset,
        )
        return [{**row, 'id': eid} for eid, row in rows if not row.get('deleted')]

    @atomic
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
            self.check('folders', folder_id, row, expected_revision)
            row.update(conversation_count=count, revision=row.get('revision', 0) + 2)
        self.save(mutation_id, digest, count)
        return count

    @atomic
    def move_conversation(self, conversation_id: str, folder_id: str | None, *, mutation_id: str | None = None) -> bool:
        return bool(self._move([conversation_id], folder_id, mutation_id, 'move'))

    @atomic
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
        self._lock_in_order('conversations', ids)
        for cid in dict.fromkeys(ids):
            row = self.store.state['conversations'].get(cid)
            if row is not None:
                if row.get('folder_id'):
                    affected.add(row['folder_id'])
                row.update(folder_id=folder_id, folder_user_set=True)
                count += 1
        for fid in sorted(affected):
            self.refresh_conversation_count(fid)
        self.save(mutation_id, digest, count)
        return count
