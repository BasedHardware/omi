"""Typed cell UoW composed over CellStore.run; no pools are created at import.

Each attempt owns its identity map. Rows are loaded under cell row locks, changed
rows are staged through put/delete, and CellStore remains the sole writer of seq,
feed and replay metadata. List methods push filters, ordering and limits to SQL.
"""

from __future__ import annotations

import time
from collections.abc import MutableMapping
from contextlib import ExitStack
from copy import deepcopy
from typing import Any, Callable, TypeVar

from database.action_item_fence import ActionItemCommitFence
from database.action_items_cache import bump_action_items_list_version
from database.cells.adapters import AdapterRegistry
from database.cells.errors import BaseRevisionMismatch, MutationIdReused
from database.cells.store import CellStore
from database.ports.base import MutationConflict, RevisionConflict, SpaceTx
from database.jobstore.codec import canonical, dumps
from database.action_item_codec import prepare_action_item_for_write
from .action_items import CellActionItems
from .folders import CellFolders
from .goals import CellGoals
from .people import CellPeople
from .workstreams import CellWorkstreams

T = TypeVar('T')
_MISSING = object()


class _Rows(MutableMapping):
    """An attempt-local identity map, not an eager copy of the collection.

    Mutation algorithms may edit a loaded row in place. Only changed addresses
    are staged at the end of the body. Enumeration is explicit and SQL lists do
    not enumerate this map. Missing keys retain CellTransaction's advisory lock.
    """

    def __init__(self, owner, entity):
        self.owner, self.entity = owner, entity
        self.rows, self.before = {}, {}

    def __getitem__(self, key):
        if key not in self.rows:
            raw = self.owner.raw
            row = raw.get(self.entity, key)
            exists = raw.cache[(self.entity, key)] is not None
            self.rows[key] = row if exists else _MISSING
            self.before[key] = deepcopy(row) if exists else _MISSING
        if self.rows[key] is _MISSING:
            raise KeyError(key)
        return self.rows[key]

    def __setitem__(self, key, value):
        self.get(key)
        self.rows[key] = deepcopy(value)

    def __delitem__(self, key):
        self[key]
        self.rows[key] = _MISSING

    def __iter__(self):
        for key, _ in self.owner.query(self.entity):
            self.get(key)
        return iter([key for key, row in self.rows.items() if row is not _MISSING])

    def __len__(self):
        return sum(1 for _ in self)

    def changed(self, key):
        row, before = self.rows[key], self.before[key]
        if row is before:
            return False
        return row is _MISSING or before is _MISSING or canonical(row) != canonical(before)

    def stage(self):
        for key, row in self.rows.items():
            before = self.before[key]
            if not self.changed(key):
                continue
            cached = self.owner.raw.cache[(self.entity, key)]
            expected = cached[0] if cached is not None else None
            if row is _MISSING:
                if self.entity == 'workflow_mutation_receipts':
                    # Domain purge removes the independent native replay record
                    # together with its result receipt under the same space lock.
                    self.owner.raw.conn.execute(
                        'DELETE FROM mutation_receipts WHERE space_id=%s AND client_mutation_id=%s',
                        (self.owner.space_id, key),
                    )
                self.owner.raw.delete(self.entity, key, expected_rev=expected)
            else:
                if self.entity == 'action_items':
                    # Related-domain operations edit task links too. Normalize
                    # only their patch so untouched legacy fields stay verbatim.
                    if before is _MISSING:
                        row = prepare_action_item_for_write(row)
                    else:
                        patch = {
                            k: v for k, v in row.items() if k not in before or canonical(v) != canonical(before[k])
                        }
                        row = {**row, **prepare_action_item_for_write(patch, partial=True)}
                receipt = self.entity == 'workflow_mutation_receipts'
                self.owner.raw.put(
                    self.entity,
                    key,
                    row,
                    expected_rev=expected,
                    client_mutation_id=key if receipt else None,
                    fingerprint=row['digest'] if receipt else None,
                )


class _State:
    def __init__(self, owner):
        self.owner, self.maps = owner, {}

    def __getitem__(self, entity):
        if entity == 'generation':
            return self['people_generation'].get('state', {}).get('value', 0)
        entity = 'workflow_mutation_receipts' if entity == 'receipts' else entity
        if entity not in self.maps:
            self.maps[entity] = _Rows(self.owner, entity)
        return self.maps[entity]

    def __setitem__(self, entity, value):
        if entity != 'generation':
            raise KeyError(entity)
        self['people_generation']['state'] = {'value': value}


class CellSpaceTx:
    bound = True
    folders: CellFolders
    people: CellPeople
    action_items: CellActionItems
    goals: CellGoals
    workstreams: CellWorkstreams

    def __init__(self, raw, adapters):
        self.raw, self.space_id = raw, raw.space_id
        self.state = _State(self)
        self.fences = []
        self.task_fence = None
        registry = AdapterRegistry()
        for domain, adapter in adapters:
            registry.register(domain, lambda _raw, factory=adapter: factory(self))
            setattr(self, domain, registry.bind(domain, raw))

    def register_commit_fence(self, fence) -> None:
        self.fences.append(fence)

    def _task_write(self):
        if self.task_fence is None:
            self.task_fence = ActionItemCommitFence(self.space_id)
            self.register_commit_fence(self.task_fence)

    def query(
        self,
        entity,
        where='',
        params=(),
        order='entity_id COLLATE "C"',
        limit=None,
        offset=0,
        *,
        columns='entity_id, doc',
    ):
        """Internal SQL fragments are constants owned by domain adapters."""
        identity = self.state.maps.get(entity)
        edits = {} if identity is None else {key: row for key, row in identity.rows.items() if identity.changed(key)}
        args = [self.space_id, entity]
        sql = 'SELECT ' + columns + ' FROM cell_docs WHERE space_id=%s AND entity=%s'
        if edits:
            # A relational overlay preserves read-your-writes without flushing
            # early or reading the entire collection into Python. LIMIT still
            # applies to the combined database + attempt-local view.
            projections: dict[str, Any] = {
                'q_completed': "doc->'completed'='true'::jsonb",
                'q_deleted': "doc->'deleted'='true'::jsonb",
                'q_order': "doc->'order'",
            }
            for field in ('due_at', 'created_at', 'updated_at'):
                projections['q_' + field] = "cell_query_timestamp(doc->'" + field + "')"
            # Mirror migration 0004 exactly: key projections keep only JSON
            # strings; status keeps its text cast.
            for field in ('conversation_id', 'idempotency_key', 'goal_id'):
                projections['q_' + field] = (
                    "CASE WHEN jsonb_typeof(doc->'" + field + "')='string' THEN doc->>'" + field + "' END"
                )
            projections['q_status'] = "doc->>'status'"
            overlay_columns = 'entity_id, doc, ' + ', '.join(projections)
            expressions = 'entity_id, doc, ' + ', '.join(projections.values())
            values = [{'entity_id': key, 'doc': row} for key, row in edits.items() if row is not _MISSING]
            sql = (
                'WITH domain_rows AS (SELECT ' + overlay_columns + ' FROM cell_docs '
                'WHERE space_id=%s AND entity=%s AND entity_id <> ALL(%s) UNION ALL SELECT '
                + expressions
                + ' FROM jsonb_to_recordset(%s::jsonb) AS overlay(entity_id text, doc jsonb)) '
                'SELECT ' + columns + ' FROM domain_rows WHERE TRUE'
            )
            args.extend([list(edits), dumps(values)])
        if where:
            sql += ' AND (' + where + ')'
        args.extend(params)
        sql += ' ORDER BY ' + order
        if limit is not None:
            if limit < 0:
                raise ValueError('limit must be nonnegative')
            sql += ' LIMIT %s'
            args.append(limit)
        if offset:
            sql += ' OFFSET %s'
            args.append(offset)
        return self.raw.conn.execute(sql, args).fetchall()

    def stage(self):
        for rows in self.state.maps.values():
            rows.stage()
        # Task changes from lifecycle/import/purge also register the same fence.
        if any(m.entity == 'action_items' for m in self.raw.mutations):
            self._task_write()


class CellSpaceStore:
    bound = False

    def __init__(self, pool, space_id: str, *, actor_uid=None):
        self.pool, self.space_id = pool, space_id
        self.actor_uid = actor_uid or space_id
        self.cell = CellStore(pool)
        self.adapters = (
            ('folders', CellFolders),
            ('people', CellPeople),
            ('action_items', CellActionItems),
            ('goals', CellGoals),
            ('workstreams', CellWorkstreams),
        )
        for domain, adapter in self.adapters:
            setattr(self, domain, adapter(self))

    def run(self, body: Callable[[SpaceTx], T]) -> T:
        attempts = []
        committed = False

        def attempt(raw):
            # Serialize typed domain algorithms (including collection predicates)
            # per space. As in raw bodies, row locks precede the admission/seq
            # head, acquired only by raw.flush after all row locks are held.
            raw.conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))', ('typed-space:' + self.space_id,))
            tx = CellSpaceTx(raw, self.adapters)
            attempts.append(tx)
            result = body(tx)
            tx.stage()
            for fence in tx.fences:
                fence.before_commit()
            # CellStore calls raw.flush immediately after this return; tickets
            # remain held through flush AND the actual connection commit.
            return result

        try:
            result = self.cell.run(self.space_id, attempt, actor_uid=self.actor_uid, now=time.time()).value
            committed = True
            return result
        except MutationIdReused as exc:
            raise MutationConflict(exc.client_mutation_id) from exc
        except BaseRevisionMismatch as exc:
            pending = attempts[-1].raw.mutations if attempts else []
            address = next((m for m in pending if m.expected_rev is not None), None)
            raise RevisionConflict(
                self.space_id,
                address.entity if address else 'cell',
                address.entity_id if address else '',
                exc.current_rev or 0,
            ) from exc
        finally:
            with ExitStack() as cleanup:
                for index, tx in enumerate(attempts):
                    success = committed and index == len(attempts) - 1
                    if success and any(m.entity == 'action_items' for m in tx.raw.mutations):
                        cleanup.callback(bump_action_items_list_version, self.space_id)
                    for fence in tx.fences:
                        cleanup.callback(fence.after_commit, success)

    def run_with_contention_retry(self, body: Callable[[SpaceTx], T], *, operation_name: str) -> T:
        return self.run(body)
