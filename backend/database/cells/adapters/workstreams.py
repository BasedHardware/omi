"""Cell-backed workstreams domain operations; writes use the shared cell flush."""

from __future__ import annotations

import hashlib
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from database.ports.action_items import ActionItemDraft, TaskRelationshipRule
from database.ports.goals import GoalNotFoundError
from database.read_boundary import parse_payload_strict
from models.workstream import WorkstreamEvent, WorkstreamUpdate as WorkstreamPatch
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


from ._base import ACCOUNT_GENERATION_SQL, EVENT_SEQUENCE_SQL, WorkflowRepo, atomic, event_payloads, generation_matches


class CellWorkstreams(WorkflowRepo):
    domain = 'workstreams'
    entity_type = WorkstreamEntity
    collection = 'workstreams'
    generation_error = WorkstreamGenerationMismatchError

    def _require(self, workstream_id, generation):
        self._generation(generation)
        row = self._read(workstream_id)
        if row is None:
            raise WorkstreamNotFoundError(workstream_id)
        if not generation_matches(row, generation):
            raise WorkstreamGenerationMismatchError('workstream account generation mismatch')
        return row

    @atomic
    def get(self, workstream_id: str) -> WorkstreamEntity | None:
        return self._entity(self._read(workstream_id), entity_id=workstream_id)

    @atomic
    def create(self, draft: WorkstreamCreate, *, mutation_id: str | None = None) -> WorkstreamEntity:
        def build():
            data = deepcopy(draft.data)
            generation = self._generation()
            self.store.action_items.validate_task_relationship(
                TaskRelationshipRule(goal_id=data.get('goal_id'), account_generation=generation)
            )
            wid = data.get('workstream_id') or data.get('id') or 'workstream_' + uuid.uuid4().hex
            now = datetime.now(timezone.utc)
            row: dict[str, Any] = {
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

    @atomic
    def list_open(self, *, limit: int = 500, account_generation: int | None = None) -> list[WorkstreamEntity]:
        where, args = "q_status='open'", []
        if account_generation is not None:
            where += " AND " + ACCOUNT_GENERATION_SQL
            args.append(account_generation)
        return [
            self._entity({**row, 'id': eid})
            for eid, row in self.store.query(
                'workstreams', where, args, order='q_updated_at DESC NULLS LAST, entity_id COLLATE "C"', limit=limit
            )
        ]

    @atomic
    def list_for_goal(
        self, goal_id: str, *, include_archived: bool = False, limit: int = 100
    ) -> list[WorkstreamEntity]:
        # Preserve the historical id-window, then archive-filter and sort it.
        rows = self.store.query('workstreams', 'q_goal_id=%s', [goal_id], limit=limit)
        rows = [
            self._entity({**row, 'id': eid}) for eid, row in rows if include_archived or row.get('status') != 'archived'
        ]
        return sorted(
            rows,
            key=lambda row: (row.model_extra or {}).get('updated_at') or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )

    @atomic
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
        result: dict[str, Any] = {
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

    @atomic
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

    @atomic
    def list_events(
        self, workstream_id: str, *, after_sequence: int = 0, limit: int = 100
    ) -> list[WorkstreamEventEntity]:
        rows = self.store.query(
            'workstream_events',
            f"starts_with(entity_id,%s) AND ({EVENT_SEQUENCE_SQL}) > %s",
            [workstream_id + '/', after_sequence],
            order=f'({EVENT_SEQUENCE_SQL}), entity_id COLLATE "C"',
            limit=limit,
        )
        return [WorkstreamEventEntity.model_construct(**row) for row in event_payloads(WorkstreamEvent, rows)]

    @atomic
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
            row: dict[str, Any] = {
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

    @atomic
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

    @atomic
    def list_artifact_descriptors(self, workstream_id: str, *, limit: int = 100) -> list[ArtifactDescriptorEntity]:
        rows = self.store.query(
            'workstream_artifacts',
            "jsonb_typeof(doc->'workstream_id')='string' AND doc->>'workstream_id'=%s",
            [workstream_id],
            order="q_created_at DESC",
            limit=limit,
        )
        return [ArtifactDescriptorEntity.model_construct(**deepcopy(row)) for _, row in rows]

    @atomic
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
            result: dict[str, Any] = {
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

    @atomic
    def list_continuation_checkpoints(self, workstream_id: str) -> list[ContinuationCheckpointEntity]:
        return [
            ContinuationCheckpointEntity.model_construct(**deepcopy(r))
            for r in self.store.state['workstream_checkpoints'].values()
            if r['workstream_id'] == workstream_id
        ]

    @atomic
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

    @atomic
    def resolve_work_intent(
        self, request: dict[str, Any], *, idempotency_key: str, account_generation: int
    ) -> dict[str, Any]:
        self._generation(account_generation)

        def build():
            tid = request.get('task_id', '')
            if request.get('origin') == 'task':
                task = self.store.state['action_items'].get(request['task_id'])
                if task is None:
                    raise WorkstreamNotFoundError(request['task_id'])
                if not (generation_matches(task, 0) or generation_matches(task, account_generation)):
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
                            'title': request.get('title') or (task or {}).get('description', 'Work'),
                            'objective': request.get('objective') or (task or {}).get('description', 'Work'),
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
                    task.update(
                        workstream_id=wid, account_generation=account_generation, updated_at=datetime.now(timezone.utc)
                    )
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

    @atomic
    def import_task_goal_links(
        self, request: dict[str, Any], *, idempotency_key: str, account_generation: int
    ) -> dict[str, Any]:
        self._generation(account_generation)

        def build():
            imported = unchanged = 0
            failed = []
            # Lock in flush order: entities alphabetically, ids sorted within.
            self._lock_in_order('action_items', [link['task_id'] for link in request['links']])
            self._lock_in_order('goals', [link['goal_id'] for link in request['links']])
            self._lock_in_order(
                'workstreams',
                [
                    (self.store.state['action_items'].get(link['task_id']) or {}).get('workstream_id')
                    for link in request['links']
                ],
            )
            for link in request['links']:
                task = self.store.state['action_items'].get(link['task_id'])
                goal = self.store.state['goals'].get(link['goal_id'])
                valid = (
                    task is not None
                    and goal is not None
                    and (generation_matches(task, 0) or generation_matches(task, account_generation))
                    and generation_matches(goal, account_generation)
                    and task.get('goal_id') in (None, link['goal_id'])
                )
                if valid and task.get('workstream_id'):
                    ws = self._rows().get(task['workstream_id'])
                    valid = (
                        ws is not None
                        and ws.get('goal_id') == link['goal_id']
                        and generation_matches(ws, account_generation)
                    )
                if not valid:
                    failed.append(link['task_id'])
                elif task.get('goal_id') == link['goal_id']:
                    unchanged += 1
                    if generation_matches(task, 0):
                        self._write_task()
                        task.update(account_generation=account_generation, updated_at=datetime.now(timezone.utc))
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

    @atomic
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

    @atomic
    def get_workstream_detail(self, workstream_id: str) -> dict[str, Any]:
        row = self.get(workstream_id)
        if row is None:
            raise WorkstreamNotFoundError(workstream_id)
        return {
            'workstream': row.model_dump(),
            'recent_events': [r.model_dump() for r in self.list_events(workstream_id)],
            'tasks': [r.model_dump() for r in self.store.action_items.iter_all() if r.workstream_id == workstream_id],
        }

    @atomic
    def purge(self, space_id: str) -> int:
        count = super().purge(space_id)
        for entity in ('workstream_events', 'workstream_artifacts', 'workstream_checkpoints'):
            count += len(self.store.state[entity])
            self.store.state[entity].clear()
        return count
