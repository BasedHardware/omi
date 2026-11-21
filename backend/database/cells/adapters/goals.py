"""Cell-backed goals domain operations; writes use the shared cell flush."""

from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo
from database.ports.goals import (
    GoalCreate,
    GoalUpdate,
    GoalEntity,
    GoalProgressEventEntity,
    GoalConflictError,
    GoalNotFoundError,
)


from models.goal import GoalProgressEvent

from ._base import EVENT_SEQUENCE_DESC_SQL, WorkflowRepo, atomic, event_payloads


class CellGoals(WorkflowRepo):
    domain = 'goals'
    entity_type = GoalEntity
    collection = 'goals'
    generation_error = GoalConflictError

    @atomic
    def get(self, goal_id: str) -> GoalEntity | None:
        return self._entity(self._read(goal_id), entity_id=goal_id)

    @atomic
    def create(self, draft: GoalCreate, *, mutation_id: str | None = None) -> GoalEntity:
        def build():
            data = deepcopy(draft.data)
            if not data.get('title') or not (data.get('desired_outcome') or data.get('title')):
                raise ValueError('goal title and desired_outcome are required')
            if data.get('status') == 'focused':
                raise GoalConflictError('use explicit focus management after creating a goal')
            gid = data.get('goal_id') or data.get('id') or 'goal_' + uuid.uuid4().hex[:12]
            now = datetime.now(timezone.utc)
            row: dict[str, Any] = {
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

    @atomic
    def create_idempotent(self, draft: GoalCreate, *, idempotency_key: str, account_generation: int) -> GoalEntity:
        self._generation(account_generation)
        return self.create(draft, mutation_id='goal-create:' + str(account_generation) + ':' + idempotency_key)

    @atomic
    def get_user_goal(self) -> GoalEntity | None:
        rows = self.get_user_goals(100)
        rows.sort(
            key=lambda r: (
                0 if r.status == 'focused' else 1,
                (r.model_extra or {}).get('focus_rank') if (r.model_extra or {}).get('focus_rank') is not None else 5,
                (r.model_extra or {}).get('created_at') or datetime.min.replace(tzinfo=timezone.utc),
            )
        )
        return rows[0] if rows else None

    @atomic
    def get_user_goals(self, limit: int = 3) -> list[GoalEntity]:
        rows = self.store.query(
            'goals',
            "doc->'is_active'='true'::jsonb AND (q_status IS NULL OR q_status NOT IN ('achieved','abandoned'))",
            order='q_created_at ASC NULLS FIRST, entity_id COLLATE "C"',
            limit=max(0, limit),
        )
        return [self._entity({**row, 'id': eid}) for eid, row in rows]

    @atomic
    def get_all(self, *, include_inactive: bool = False, limit: int | None = None) -> list[GoalEntity]:
        where = (
            ''
            if include_inactive
            else "doc->'is_active'='true'::jsonb AND (q_status IS NULL OR q_status NOT IN ('achieved','abandoned'))"
        )
        return [
            self._entity({**row, 'id': eid})
            for eid, row in self.store.query(
                'goals', where, order='q_created_at DESC NULLS LAST, entity_id COLLATE "C"', limit=limit
            )
        ]

    @atomic
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

    @atomic
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
            # Enumerate (and so lock, sorted) before the single-row read.
            focused = {eid: r for eid, r in self._rows().items() if r.get('status') == 'focused' and eid != goal_id}
            row = self._read(goal_id)
            if row is None:
                raise GoalNotFoundError(goal_id)
            if row.get('status') in ('achieved', 'abandoned'):
                raise GoalConflictError('ended goals cannot be focused')
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

    @atomic
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

    @atomic
    def transition_lifecycle(
        self, goal_id: str, *, status: str, relationship_disposition: str, idempotency_key: str, account_generation: int
    ) -> GoalEntity:
        self._generation(account_generation)
        if status not in ('paused', 'achieved', 'abandoned'):
            raise ValueError('invalid goal lifecycle target')
        if relationship_disposition not in ('retain', 'detach'):
            raise ValueError('invalid goal relationship disposition')

        def build():
            detach = relationship_disposition == 'detach'
            # Lock in flush order: action_items, then goals, then workstreams.
            tasks = (
                [t for t in self.store.state['action_items'].values() if t.get('goal_id') == goal_id] if detach else []
            )
            row = self._read(goal_id)
            if row is None:
                raise GoalNotFoundError(goal_id)
            now = datetime.now(timezone.utc)
            if detach:
                for task in tasks:
                    self._write_task()
                    task.update(goal_id=None, updated_at=now)
                for workstream in self.store.state['workstreams'].values():
                    if workstream.get('goal_id') == goal_id:
                        workstream.update(goal_id=None, updated_at=now)
            row.update(
                status=status,
                focus_rank=None,
                is_active=status not in ('achieved', 'abandoned'),
                relationship_disposition=relationship_disposition,
                updated_at=now,
                ended_at=now if status in ('achieved', 'abandoned') else None,
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

    @atomic
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
            data: dict[str, Any] = {
                **deepcopy(event),
                'event_id': eid,
                'goal_id': goal_id,
                'sequence': sequence,
                'created_at': now,
            }
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

    @atomic
    def list_progress_events(self, goal_id: str, *, limit: int = 100) -> list[GoalProgressEventEntity]:
        rows = self.store.query(
            'goal_events',
            "starts_with(entity_id,%s) AND doc ? 'sequence'",
            [goal_id + '/'],
            order=EVENT_SEQUENCE_DESC_SQL,
            limit=limit,
        )
        return [GoalProgressEventEntity.model_construct(**row) for row in event_payloads(GoalProgressEvent, rows)]

    @atomic
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
        metric: dict[str, Any] = {**(row.get('metric') or {'type': 'numeric', 'target': 0}), 'current': current_value}
        self.append_progress_event(
            goal_id,
            {'kind': 'metric_update', 'summary': 'Metric updated', 'metric': metric},
            idempotency_key=idempotency_key or uuid.uuid4().hex,
            account_generation=self._generation() if account_generation is None else account_generation,
        )
        return self.get(goal_id)

    @atomic
    def get_history(self, goal_id: str, *, days: int = 30) -> list[dict[str, Any]]:
        return [
            deepcopy(row)
            for _, row in self.store.query(
                'goal_history', "starts_with(entity_id,%s)", [goal_id + '/'], order="doc->>'date' DESC", limit=days
            )
        ]

    @atomic
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

    @atomic
    def read_control(self) -> dict[str, Any]:
        return deepcopy(self.store.state['task_intelligence_control'].get('state', {}))

    @atomic
    def write_control(self, patch: dict[str, Any]) -> None:
        self.store.state['task_intelligence_control'].setdefault('state', {}).update(deepcopy(patch))

    @atomic
    def begin_mutation(
        self, *, operation: str, idempotency_key: str, account_generation: int, request: dict[str, Any]
    ) -> dict[str, Any] | None:
        self._generation(account_generation)
        _, prior = self.receipt(f'{operation}:{account_generation}:{idempotency_key}', operation, request)
        return prior

    @atomic
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

    @atomic
    def purge(self, space_id: str) -> int:
        count = super().purge(space_id)
        for entity in (
            'goal_events',
            'goal_history',
            'task_intelligence_control',
        ):
            count += len(self.store.state[entity])
            self.store.state[entity].clear()
        return count
