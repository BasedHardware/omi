"""Canonical workstream persistence and atomic task/workflow transactions.

All persistence goes through the backend-neutral storage port (``database.store``); no storage SDK
type crosses this module's boundary. Transactions use ``_store().run_transaction(fn)``: every
``fn(tx)`` performs all reads before any write (the store forbids read-after-write inside a
transaction). The neutral transaction handle exposes only ``get``/``set``/``update``/``delete`` —
there is no ``create``, so a create-if-absent is an existence read followed by ``set``.
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional, cast

from config.canonical_memory_cohort import is_canonical_memory_user

import database.goals as goals_db
from database.read_boundary import parse_snapshot_or_none, parse_snapshot_strict, parse_snapshots
from database.store import get_document_store
from models.action_item import ActionItemResponse, TaskOwner, TaskPriority, TaskStatus
from models.candidate import CandidateRecord, CandidateResolutionReceipt, CandidateStatus, CandidateSubjectKind
from models.goal import GoalResponse, GoalStatus
from models.task_intelligence import TaskWorkflowControl
from models.workstream import (
    ArtifactDescriptor,
    ArtifactDescriptorCreate,
    ArtifactStatus,
    ArtifactStatusTransitionRequest,
    ContinuationCheckpoint,
    ContinuationCheckpointUpsert,
    GoalDetailProjection,
    GoalOriginWorkIntent,
    TaskGoalLinkImportReport,
    TaskGoalLinkImportRequest,
    TaskOriginWorkIntent,
    WorkIntentReceipt,
    Workstream,
    WorkstreamDetailProjection,
    WorkstreamEvent,
    WorkstreamEventCreate,
    WorkstreamEventKind,
    WorkstreamSensitivity,
    WorkstreamStatus,
    WorkstreamUpdate,
)

WORKSTREAMS_COLLECTION = 'workstreams'
GOALS_COLLECTION = 'goals'
EVENTS_COLLECTION = 'events'
ARTIFACTS_COLLECTION = 'artifact_refs'
ARTIFACT_HEADS_COLLECTION = 'artifact_heads'
CHECKPOINTS_COLLECTION = 'continuation_checkpoints'
WORK_INTENT_RECEIPTS_COLLECTION = 'work_intent_receipts'
MUTATION_RECEIPTS_COLLECTION = 'workflow_mutation_receipts'
CANDIDATES_COLLECTION = 'candidates'
ACTION_ITEMS_COLLECTION = 'action_items'
CANDIDATE_INTEGRATION_OUTBOX_COLLECTION = 'candidate_integration_outbox'
TASK_INTELLIGENCE_CONTROL_COLLECTION = 'task_intelligence_control'
TASK_INTELLIGENCE_CONTROL_DOCUMENT = 'state'


def _store():
    return get_document_store()


class WorkstreamStoreError(RuntimeError):
    pass


class WorkstreamNotFoundError(WorkstreamStoreError):
    pass


class WorkstreamConflictError(WorkstreamStoreError):
    pass


class WorkstreamGenerationMismatchError(WorkstreamStoreError):
    pass


def _stable_id(prefix: str, *parts: object) -> str:
    payload = '\x1f'.join(str(part) for part in parts).encode('utf-8')
    return f'{prefix}_{hashlib.sha256(payload).hexdigest()[:32]}'


def _snapshot_dict(snapshot: Any) -> dict[str, Any]:
    payload = snapshot.to_dict()
    return cast(dict[str, Any], payload) if isinstance(payload, dict) else {}


def _task_responses_from_snapshots(snapshots: Any, *, context: str) -> list[ActionItemResponse]:
    del context  # The shared boundary logs a structural summary and document path instead.
    active_snapshots = (snapshot for snapshot in snapshots if not _snapshot_dict(snapshot).get('deleted'))
    return parse_snapshots(ActionItemResponse, active_snapshots, document_id_field='id')


# --- logical path helpers (collection/document chains) ---


def _user_path(uid: str) -> str:
    return f'users/{uid}'


def _workstreams_collection_path(uid: str) -> str:
    return f'{_user_path(uid)}/{WORKSTREAMS_COLLECTION}'


def _workstream_path(uid: str, workstream_id: str) -> str:
    return f'{_workstreams_collection_path(uid)}/{workstream_id}'


def _events_collection_path(uid: str, workstream_id: str) -> str:
    return f'{_workstream_path(uid, workstream_id)}/{EVENTS_COLLECTION}'


def _event_path(uid: str, workstream_id: str, event_id: str) -> str:
    return f'{_events_collection_path(uid, workstream_id)}/{event_id}'


def _artifacts_collection_path(uid: str, workstream_id: str) -> str:
    return f'{_workstream_path(uid, workstream_id)}/{ARTIFACTS_COLLECTION}'


def _artifact_path(uid: str, workstream_id: str, artifact_id: str) -> str:
    return f'{_artifacts_collection_path(uid, workstream_id)}/{artifact_id}'


def _artifact_head_path(uid: str, workstream_id: str, head_id: str) -> str:
    return f'{_workstream_path(uid, workstream_id)}/{ARTIFACT_HEADS_COLLECTION}/{head_id}'


def _checkpoints_collection_path(uid: str, workstream_id: str) -> str:
    return f'{_workstream_path(uid, workstream_id)}/{CHECKPOINTS_COLLECTION}'


def _checkpoint_path(uid: str, workstream_id: str, checkpoint_id: str) -> str:
    return f'{_checkpoints_collection_path(uid, workstream_id)}/{checkpoint_id}'


def _tasks_collection_path(uid: str) -> str:
    return f'{_user_path(uid)}/{ACTION_ITEMS_COLLECTION}'


def _task_path(uid: str, task_id: str) -> str:
    return f'{_tasks_collection_path(uid)}/{task_id}'


def _goal_path(uid: str, goal_id: str) -> str:
    # goals is on the storage port and no longer exposes a Firestore-ref seam; this transactional
    # module owns the goal document path it reads/writes inside its own store transactions (the path
    # is goals' canonical layout).
    return f'{_user_path(uid)}/{GOALS_COLLECTION}/{goal_id}'


def _candidate_path(uid: str, candidate_id: str) -> str:
    return f'{_user_path(uid)}/{CANDIDATES_COLLECTION}/{candidate_id}'


def _candidate_outbox_path(uid: str, candidate_id: str) -> str:
    return f'{_user_path(uid)}/{CANDIDATE_INTEGRATION_OUTBOX_COLLECTION}/{candidate_id}'


def _control_path(uid: str) -> str:
    return f'{_user_path(uid)}/{TASK_INTELLIGENCE_CONTROL_COLLECTION}/{TASK_INTELLIGENCE_CONTROL_DOCUMENT}'


def _work_intent_receipt_path(uid: str, receipt_id: str) -> str:
    return f'{_user_path(uid)}/{WORK_INTENT_RECEIPTS_COLLECTION}/{receipt_id}'


def _mutation_receipt_path(
    uid: str,
    *,
    operation: str,
    idempotency_key: str,
    account_generation: int,
) -> str:
    receipt_id = _stable_id('mutation', uid, account_generation, operation, idempotency_key)
    return f'{_user_path(uid)}/{MUTATION_RECEIPTS_COLLECTION}/{receipt_id}'


def _mutation_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str).encode('utf-8')
    ).hexdigest()


def _begin_mutation(
    tx: Any,
    *,
    uid: str,
    operation: str,
    idempotency_key: str,
    account_generation: int,
    request_payload: Any,
) -> tuple[str, Optional[dict[str, Any]], str]:
    control_snapshot = tx.get(_control_path(uid))
    _validate_control(control_snapshot, uid=uid, account_generation=account_generation)
    receipt_path = _mutation_receipt_path(
        uid,
        operation=operation,
        idempotency_key=idempotency_key,
        account_generation=account_generation,
    )
    request_hash = _mutation_hash(request_payload)
    receipt_snapshot = tx.get(receipt_path)
    if not receipt_snapshot.exists:
        return receipt_path, None, request_hash
    receipt = _snapshot_dict(receipt_snapshot)
    if receipt.get('request_hash') != request_hash:
        raise WorkstreamConflictError('idempotency key was reused with different content')
    result = receipt.get('result')
    if not isinstance(result, dict):
        raise WorkstreamConflictError('idempotent mutation receipt is incomplete')
    return receipt_path, cast(dict[str, Any], result), request_hash


def _finish_mutation(
    tx: Any,
    receipt_path: str,
    *,
    request_hash: str,
    result: dict[str, Any],
    now: datetime,
) -> None:
    # Reached only when the receipt did not exist at ``_begin_mutation``, so an unconditional set
    # stands in for the create the neutral transaction handle does not expose.
    tx.set(
        receipt_path,
        {'request_hash': request_hash, 'result': result, 'created_at': now},
    )


def _validate_control(snapshot: Any, *, uid: str, account_generation: int) -> None:
    if not is_canonical_memory_user(uid):
        raise WorkstreamConflictError('canonical task intelligence is not enabled')
    control = TaskWorkflowControl()
    if snapshot.exists:
        control = parse_snapshot_strict(TaskWorkflowControl, snapshot)
    if control.account_generation != account_generation:
        raise WorkstreamGenerationMismatchError('account generation mismatch')


def _assert_workstream_generation(snapshot: Any, *, account_generation: int) -> None:
    payload = _snapshot_dict(snapshot)
    if int(payload.get('account_generation', 0)) != account_generation:
        raise WorkstreamGenerationMismatchError('workstream account generation mismatch')


def _workstream_payload(snapshot: Any) -> dict[str, Any]:
    payload = _snapshot_dict(snapshot)
    payload.pop('account_generation', None)
    return payload


def _workstream_from_snapshot(snapshot: Any) -> Workstream:
    return parse_snapshot_strict(Workstream, snapshot, payload_from_snapshot=_workstream_payload)


def _task_storage(
    *,
    task_id: str,
    description: str,
    goal_id: Optional[str],
    workstream_id: str,
    source: str,
    now: datetime,
    owner: TaskOwner = TaskOwner.user,
    provenance: Optional[list[dict[str, Any]]] = None,
    due_at: Optional[datetime] = None,
    due_confidence: Optional[float] = None,
    priority: Optional[TaskPriority] = None,
    recurrence_rule: Optional[str] = None,
    recurrence_parent_id: Optional[str] = None,
    account_generation: int = 0,
) -> dict[str, Any]:
    return {
        'id': task_id,
        'task_id': task_id,
        'description': description,
        'status': TaskStatus.active.value,
        'completed': False,
        'goal_id': goal_id,
        'workstream_id': workstream_id,
        'owner': owner.value,
        'due_at': due_at,
        'due_confidence': due_confidence,
        'priority': priority.value if priority is not None else None,
        'recurrence_rule': recurrence_rule,
        'recurrence_parent_id': recurrence_parent_id,
        'source': source,
        'provenance': provenance or [],
        'sort_order': 0,
        'indent_level': 0,
        'created_at': now,
        'updated_at': now,
        'account_generation': account_generation,
    }


def _workstream_storage(
    *,
    workstream_id: str,
    title: str,
    objective: str,
    goal_id: Optional[str],
    now: datetime,
    summary: str = '',
    latest_event_sequence: int = 1,
    account_generation: int = 0,
) -> dict[str, Any]:
    payload = Workstream(
        workstream_id=workstream_id,
        goal_id=goal_id,
        title=title,
        objective=objective,
        status=WorkstreamStatus.open,
        current_state_summary=summary,
        last_meaningful_progress_at=now,
        latest_event_sequence=latest_event_sequence,
        created_at=now,
        updated_at=now,
    ).model_dump(mode='python', exclude_none=True)
    payload['account_generation'] = account_generation
    return payload


def _initial_event_storage(
    *,
    uid: str,
    workstream_id: str,
    source_key: str,
    summary: str,
    evidence_refs: list[Any],
    now: datetime,
) -> tuple[str, dict[str, Any]]:
    event_id = _stable_id('wse', uid, workstream_id, source_key)
    event = WorkstreamEvent(
        event_id=event_id,
        workstream_id=workstream_id,
        sequence=1,
        kind=WorkstreamEventKind.system,
        summary=summary,
        evidence_refs=evidence_refs,
        sensitivity=WorkstreamSensitivity.normal,
        created_at=now,
    )
    return event_id, event.model_dump(mode='python')


def _assert_goal_exists(
    uid: str,
    goal_id: Optional[str],
    *,
    account_generation: int,
    tx: Any,
) -> None:
    if goal_id is None:
        return
    snapshot = tx.get(_goal_path(uid, goal_id))
    if not snapshot.exists:
        raise WorkstreamConflictError('goal does not exist')
    goal = goals_db.normalize_goal_storage(_snapshot_dict(snapshot), goal_id=goal_id)
    if goal.get('account_generation', 0) != account_generation:
        raise WorkstreamGenerationMismatchError('goal account generation mismatch')
    if goal['status'] in {GoalStatus.achieved.value, GoalStatus.abandoned.value}:
        raise WorkstreamConflictError('ended goal cannot receive new work')


def get_workstream(
    uid: str,
    workstream_id: str,
    *,
    account_generation: Optional[int] = None,
) -> Optional[Workstream]:
    snapshot = _store().get(_workstream_path(uid, workstream_id))
    if not snapshot.exists:
        return None
    payload = _snapshot_dict(snapshot)
    if account_generation is not None and payload.get('account_generation', 0) != account_generation:
        return None
    return parse_snapshot_or_none(Workstream, snapshot, payload_from_snapshot=_workstream_payload)


def get_workstream_goal_id(uid: str, workstream_id: str) -> Optional[str]:
    workstream = get_workstream(uid, workstream_id)
    if workstream is None:
        raise WorkstreamNotFoundError(workstream_id)
    return workstream.goal_id


def get_task_workflow_control(uid: str) -> TaskWorkflowControl:
    snapshot = _store().get(_control_path(uid))
    if not snapshot.exists:
        return TaskWorkflowControl()
    return parse_snapshot_strict(TaskWorkflowControl, snapshot)


def list_open_workstreams(
    uid: str,
    *,
    limit: int = 500,
    account_generation: Optional[int] = None,
) -> list[Workstream]:
    filters: list[tuple[str, str, Any]] = [('status', '==', WorkstreamStatus.open.value)]
    if account_generation is not None and account_generation > 0:
        filters.append(('account_generation', '==', account_generation))
    snapshots = _store().query(_workstreams_collection_path(uid), filters=filters, limit=limit)
    if account_generation == 0:
        snapshots = [snapshot for snapshot in snapshots if _snapshot_dict(snapshot).get('account_generation', 0) == 0]
    records = parse_snapshots(Workstream, snapshots, payload_from_snapshot=_workstream_payload)
    records.sort(key=lambda record: record.updated_at, reverse=True)
    return records


def list_workstreams_for_goal(
    uid: str,
    goal_id: str,
    *,
    include_archived: bool = False,
    limit: int = 100,
) -> list[Workstream]:
    snapshots = _store().query(
        _workstreams_collection_path(uid), filters=[('goal_id', '==', goal_id)], limit=limit
    )
    records = parse_snapshots(Workstream, snapshots, payload_from_snapshot=_workstream_payload)
    if not include_archived:
        records = [record for record in records if record.status != WorkstreamStatus.archived]
    records.sort(key=lambda record: record.updated_at, reverse=True)
    return records


def update_workstream(
    uid: str,
    workstream_id: str,
    update: WorkstreamUpdate,
    *,
    idempotency_key: str,
    account_generation: int,
) -> Workstream:
    workstream_path = _workstream_path(uid, workstream_id)
    patch = update.model_dump(mode='python', exclude_unset=True)
    now = datetime.now(timezone.utc)

    def apply(tx):
        receipt_path, stored_result, request_hash = _begin_mutation(
            tx,
            uid=uid,
            operation=f'workstream-update:{workstream_id}',
            idempotency_key=idempotency_key,
            account_generation=account_generation,
            request_payload=update.model_dump(mode='json', exclude_unset=True),
        )
        if stored_result is not None:
            return Workstream.model_validate(stored_result)
        snapshot = tx.get(workstream_path)
        if not snapshot.exists:
            raise WorkstreamNotFoundError(workstream_id)
        _assert_workstream_generation(snapshot, account_generation=account_generation)
        result = _workstream_from_snapshot(snapshot).model_copy(update={**patch, 'updated_at': now})
        tx.update(workstream_path, {**patch, 'updated_at': now})
        result_payload = result.model_dump(mode='python')
        _finish_mutation(
            tx,
            receipt_path,
            request_hash=request_hash,
            result=result_payload,
            now=now,
        )
        return result

    return _store().run_transaction(apply)


def append_workstream_event(
    uid: str,
    workstream_id: str,
    event: WorkstreamEventCreate,
    *,
    idempotency_key: str,
    account_generation: int,
    required_status: Optional[WorkstreamStatus] = None,
) -> WorkstreamEvent:
    workstream_path = _workstream_path(uid, workstream_id)
    now = datetime.now(timezone.utc)
    event_id = _stable_id('wse', uid, workstream_id, account_generation, idempotency_key)
    event_path = _event_path(uid, workstream_id, event_id)

    def apply(tx):
        control_snapshot = tx.get(_control_path(uid))
        _validate_control(control_snapshot, uid=uid, account_generation=account_generation)
        workstream_snapshot = tx.get(workstream_path)
        if not workstream_snapshot.exists:
            raise WorkstreamNotFoundError(workstream_id)
        _assert_workstream_generation(workstream_snapshot, account_generation=account_generation)
        existing = tx.get(event_path)
        if existing.exists:
            stored = parse_snapshot_strict(WorkstreamEvent, existing)
            stored_proposal = WorkstreamEventCreate(
                kind=stored.kind,
                summary=stored.summary,
                evidence_refs=stored.evidence_refs,
                sensitivity=stored.sensitivity,
            )
            if stored_proposal != event:
                raise WorkstreamConflictError('event idempotency key was reused with different content')
            return stored
        workstream = _workstream_from_snapshot(workstream_snapshot)
        if required_status is not None and workstream.status != required_status:
            raise WorkstreamConflictError(f'workstream must be {required_status.value}')
        sequence = workstream.latest_event_sequence + 1
        record = WorkstreamEvent(
            event_id=event_id,
            workstream_id=workstream_id,
            sequence=sequence,
            kind=event.kind,
            summary=event.summary,
            evidence_refs=event.evidence_refs,
            sensitivity=event.sensitivity,
            created_at=now,
        )
        tx.set(event_path, record.model_dump(mode='python'))
        tx.update(
            workstream_path,
            {'latest_event_sequence': sequence, 'last_meaningful_progress_at': now, 'updated_at': now},
        )
        return record

    return _store().run_transaction(apply)


def list_workstream_events(
    uid: str,
    workstream_id: str,
    *,
    after_sequence: int = 0,
    limit: int = 100,
) -> list[WorkstreamEvent]:
    snapshots = _store().query(
        _events_collection_path(uid, workstream_id),
        filters=[('sequence', '>', after_sequence)],
        order_by='sequence',
        direction='asc',
        limit=limit,
    )
    return parse_snapshots(WorkstreamEvent, snapshots)


def create_artifact_descriptor(
    uid: str,
    workstream_id: str,
    proposal: ArtifactDescriptorCreate,
    *,
    idempotency_key: str,
    account_generation: int,
) -> ArtifactDescriptor:
    workstream_path = _workstream_path(uid, workstream_id)
    artifact_id = _stable_id('artifact', uid, workstream_id, proposal.logical_key, proposal.version)
    artifact_path = _artifact_path(uid, workstream_id, artifact_id)
    head_path = _artifact_head_path(
        uid, workstream_id, _stable_id('artifact-head', uid, workstream_id, proposal.logical_key)
    )
    now = datetime.now(timezone.utc)

    def apply(tx):
        receipt_path, stored_result, request_hash = _begin_mutation(
            tx,
            uid=uid,
            operation=f'artifact-create:{workstream_id}',
            idempotency_key=idempotency_key,
            account_generation=account_generation,
            request_payload=proposal.model_dump(mode='json'),
        )
        if stored_result is not None:
            return ArtifactDescriptor.model_validate(stored_result)
        workstream_snapshot = tx.get(workstream_path)
        if not workstream_snapshot.exists:
            raise WorkstreamNotFoundError(workstream_id)
        _assert_workstream_generation(workstream_snapshot, account_generation=account_generation)
        existing = tx.get(artifact_path)
        record = ArtifactDescriptor(
            **proposal.model_dump(mode='python'),
            artifact_id=artifact_id,
            workstream_id=workstream_id,
            status=ArtifactStatus.draft,
            created_at=now,
        )
        if existing.exists:
            stored = parse_snapshot_strict(ArtifactDescriptor, existing)
            proposal_fields = set(ArtifactDescriptorCreate.model_fields)
            if stored.model_dump(mode='python', include=proposal_fields) != proposal.model_dump(mode='python'):
                raise WorkstreamConflictError('artifact version already exists with different content')
            _finish_mutation(
                tx,
                receipt_path,
                request_hash=request_hash,
                result=stored.model_dump(mode='python'),
                now=now,
            )
            return stored
        head_snapshot = tx.get(head_path)
        superseded_path = None
        if head_snapshot.exists:
            head = _snapshot_dict(head_snapshot)
            expected_version = int(head.get('version', 0)) + 1
            expected_artifact_id = head.get('artifact_id')
            if proposal.version != expected_version or proposal.supersedes_artifact_id != expected_artifact_id:
                raise WorkstreamConflictError('artifact version must advance and supersede the current logical head')
            superseded_path = _artifact_path(uid, workstream_id, str(expected_artifact_id))
            superseded_snapshot = tx.get(superseded_path)
            if not superseded_snapshot.exists:
                raise WorkstreamConflictError('artifact head points to a missing descriptor')
            superseded = parse_snapshot_strict(ArtifactDescriptor, superseded_snapshot)
            if superseded.logical_key != proposal.logical_key or superseded.status == ArtifactStatus.superseded:
                raise WorkstreamConflictError('artifact head is not a live version of this logical artifact')
        elif proposal.version != 1 or proposal.supersedes_artifact_id is not None:
            raise WorkstreamConflictError('the first logical artifact version must be version 1 without supersession')
        if proposal.supersedes_artifact_id is not None and not proposal.evidence_event_ids:
            raise WorkstreamConflictError('artifact revisions must cite the journal evidence that caused the change')
        for evidence_event_id in proposal.evidence_event_ids:
            evidence_snapshot = tx.get(_event_path(uid, workstream_id, evidence_event_id))
            if not evidence_snapshot.exists:
                raise WorkstreamConflictError('artifact references a missing workstream event')
        workstream = _workstream_from_snapshot(workstream_snapshot)
        sequence = workstream.latest_event_sequence + 1
        event_id = _stable_id('wse', uid, workstream_id, 'artifact', artifact_id)
        event = WorkstreamEvent(
            event_id=event_id,
            workstream_id=workstream_id,
            sequence=sequence,
            kind=WorkstreamEventKind.artifact_version,
            summary=f'Artifact {proposal.logical_key} version {proposal.version} created',
            evidence_refs=proposal.evidence_refs,
            sensitivity=WorkstreamSensitivity.normal,
            created_at=now,
        )
        tx.set(artifact_path, record.model_dump(mode='python'))
        tx.set(_event_path(uid, workstream_id, event_id), event.model_dump(mode='python'))
        if superseded_path is not None:
            tx.update(superseded_path, {'status': ArtifactStatus.superseded.value})
        tx.set(
            head_path,
            {
                'logical_key': proposal.logical_key,
                'artifact_id': artifact_id,
                'version': proposal.version,
                'updated_at': now,
            },
        )
        tx.update(
            workstream_path,
            {'latest_event_sequence': sequence, 'last_meaningful_progress_at': now, 'updated_at': now},
        )
        _finish_mutation(
            tx,
            receipt_path,
            request_hash=request_hash,
            result=record.model_dump(mode='python'),
            now=now,
        )
        return record

    return _store().run_transaction(apply)


def transition_artifact_status(
    uid: str,
    workstream_id: str,
    artifact_id: str,
    request: ArtifactStatusTransitionRequest,
    *,
    idempotency_key: str,
    account_generation: int,
) -> ArtifactDescriptor:
    workstream_path = _workstream_path(uid, workstream_id)
    artifact_path = _artifact_path(uid, workstream_id, artifact_id)
    now = datetime.now(timezone.utc)
    allowed_transitions = {
        ArtifactStatus.draft: ArtifactStatus.awaiting_review,
        ArtifactStatus.awaiting_review: ArtifactStatus.approved,
        ArtifactStatus.approved: ArtifactStatus.delivered,
    }

    def apply(tx):
        receipt_path, stored_result, request_hash = _begin_mutation(
            tx,
            uid=uid,
            operation=f'artifact-status:{workstream_id}:{artifact_id}',
            idempotency_key=idempotency_key,
            account_generation=account_generation,
            request_payload=request.model_dump(mode='json'),
        )
        if stored_result is not None:
            return ArtifactDescriptor.model_validate(stored_result)
        workstream_snapshot = tx.get(workstream_path)
        if not workstream_snapshot.exists:
            raise WorkstreamNotFoundError(workstream_id)
        _assert_workstream_generation(workstream_snapshot, account_generation=account_generation)
        artifact_snapshot = tx.get(artifact_path)
        if not artifact_snapshot.exists:
            raise WorkstreamNotFoundError(artifact_id)
        artifact = parse_snapshot_strict(ArtifactDescriptor, artifact_snapshot)
        if artifact.status == request.status:
            _finish_mutation(
                tx,
                receipt_path,
                request_hash=request_hash,
                result=artifact.model_dump(mode='python'),
                now=now,
            )
            return artifact
        if allowed_transitions.get(artifact.status) != request.status:
            raise WorkstreamConflictError('artifact status transition is not allowed')
        workstream = _workstream_from_snapshot(workstream_snapshot)
        sequence = workstream.latest_event_sequence + 1
        event = WorkstreamEvent(
            event_id=_stable_id('wse', uid, workstream_id, 'artifact-status', artifact_id, request.status.value),
            workstream_id=workstream_id,
            sequence=sequence,
            kind=WorkstreamEventKind.system,
            summary=f'Artifact {artifact.logical_key} version {artifact.version} moved to {request.status.value}',
            evidence_refs=artifact.evidence_refs,
            sensitivity=WorkstreamSensitivity.normal,
            created_at=now,
        )
        tx.update(artifact_path, {'status': request.status.value})
        tx.set(_event_path(uid, workstream_id, event.event_id), event.model_dump(mode='python'))
        tx.update(
            workstream_path,
            {'latest_event_sequence': sequence, 'last_meaningful_progress_at': now, 'updated_at': now},
        )
        result = artifact.model_copy(update={'status': request.status})
        _finish_mutation(
            tx,
            receipt_path,
            request_hash=request_hash,
            result=result.model_dump(mode='python'),
            now=now,
        )
        return result

    return _store().run_transaction(apply)


def list_artifact_descriptors(
    uid: str,
    workstream_id: str,
    *,
    limit: int = 100,
) -> list[ArtifactDescriptor]:
    snapshots = _store().query(
        _artifacts_collection_path(uid, workstream_id),
        order_by='created_at',
        direction='desc',
        limit=limit,
    )
    return parse_snapshots(ArtifactDescriptor, snapshots)


def upsert_continuation_checkpoint(
    uid: str,
    workstream_id: str,
    checkpoint: ContinuationCheckpointUpsert,
    *,
    idempotency_key: str,
    account_generation: int,
) -> ContinuationCheckpoint:
    workstream_path = _workstream_path(uid, workstream_id)
    checkpoint_id = _stable_id('checkpoint', uid, workstream_id, checkpoint.runtime_id)
    checkpoint_path = _checkpoint_path(uid, workstream_id, checkpoint_id)
    now = datetime.now(timezone.utc)

    def apply(tx):
        receipt_path, stored_result, request_hash = _begin_mutation(
            tx,
            uid=uid,
            operation=f'checkpoint-upsert:{workstream_id}:{checkpoint.runtime_id}',
            idempotency_key=idempotency_key,
            account_generation=account_generation,
            request_payload=checkpoint.model_dump(mode='json'),
        )
        if stored_result is not None:
            return ContinuationCheckpoint.model_validate(stored_result)
        workstream_snapshot = tx.get(workstream_path)
        if not workstream_snapshot.exists:
            raise WorkstreamNotFoundError(workstream_id)
        _assert_workstream_generation(workstream_snapshot, account_generation=account_generation)
        workstream = _workstream_from_snapshot(workstream_snapshot)
        if checkpoint.last_event_sequence > workstream.latest_event_sequence:
            raise WorkstreamConflictError('checkpoint cannot advance beyond the workstream journal')
        checkpoint_snapshot = tx.get(checkpoint_path)
        if checkpoint_snapshot.exists:
            existing = parse_snapshot_strict(ContinuationCheckpoint, checkpoint_snapshot)
            if checkpoint.last_event_sequence < existing.last_event_sequence:
                raise WorkstreamConflictError('checkpoint sequence cannot move backwards')
            if checkpoint.last_event_sequence == existing.last_event_sequence:
                equivalent = (
                    checkpoint.runtime_id == existing.runtime_id
                    and checkpoint.context_summary == existing.context_summary
                    and checkpoint.evidence_refs == existing.evidence_refs
                )
                if not equivalent:
                    raise WorkstreamConflictError('checkpoint sequence already stores different content')
                _finish_mutation(
                    tx,
                    receipt_path,
                    request_hash=request_hash,
                    result=existing.model_dump(mode='python'),
                    now=now,
                )
                return existing
        record = ContinuationCheckpoint(
            **checkpoint.model_dump(mode='python'),
            checkpoint_id=checkpoint_id,
            workstream_id=workstream_id,
            updated_at=now,
        )
        tx.set(checkpoint_path, record.model_dump(mode='python'))
        _finish_mutation(
            tx,
            receipt_path,
            request_hash=request_hash,
            result=record.model_dump(mode='python'),
            now=now,
        )
        return record

    return _store().run_transaction(apply)


def list_continuation_checkpoints(
    uid: str,
    workstream_id: str,
) -> list[ContinuationCheckpoint]:
    snapshots = _store().query(_checkpoints_collection_path(uid, workstream_id))
    return parse_snapshots(ContinuationCheckpoint, snapshots)


def resolve_workstream_candidate(
    uid: str,
    candidate: CandidateRecord,
    account_generation: int,
) -> CandidateResolutionReceipt:
    if candidate.subject_kind != CandidateSubjectKind.workstream or candidate.workstream_proposal is None:
        raise WorkstreamConflictError('Candidate is not a workstream create proposal')
    candidate_path = _candidate_path(uid, candidate.candidate_id)
    workstream_id = _stable_id('workstream', uid, account_generation, candidate.candidate_id)
    task_id = _stable_id('task', uid, account_generation, candidate.candidate_id)
    workstream_path = _workstream_path(uid, workstream_id)
    task_path = _task_path(uid, task_id)
    now = datetime.now(timezone.utc)

    def apply(tx):
        control_snapshot = tx.get(_control_path(uid))
        _validate_control(control_snapshot, uid=uid, account_generation=account_generation)
        candidate_snapshot = tx.get(candidate_path)
        if not candidate_snapshot.exists:
            raise WorkstreamNotFoundError(candidate.candidate_id)
        stored_candidate = parse_snapshot_strict(CandidateRecord, candidate_snapshot)
        if stored_candidate.account_generation != account_generation:
            raise WorkstreamGenerationMismatchError('Candidate account generation mismatch')
        if stored_candidate.status == CandidateStatus.accepted:
            return CandidateResolutionReceipt(
                candidate_id=stored_candidate.candidate_id,
                status=CandidateStatus.accepted,
                receipt_id=_stable_id('receipt', stored_candidate.candidate_id, account_generation, 'accepted'),
                task_id=stored_candidate.result_task_id,
                workstream_id=stored_candidate.result_workstream_id,
                newly_resolved=False,
                resolved_at=cast(datetime, stored_candidate.resolved_at),
            )
        if stored_candidate.status != CandidateStatus.pending:
            raise WorkstreamConflictError(f'Candidate already {stored_candidate.status.value}')
        proposal = stored_candidate.workstream_proposal
        if proposal is None:
            raise WorkstreamConflictError('stored Candidate has no workstream proposal')
        _assert_goal_exists(
            uid,
            stored_candidate.goal_id,
            account_generation=account_generation,
            tx=tx,
        )
        workstream_snapshot = tx.get(workstream_path)
        task_snapshot = tx.get(task_path)
        if workstream_snapshot.exists or task_snapshot.exists:
            raise WorkstreamConflictError('deterministic workstream resolution id collision')
        event_id, event_data = _initial_event_storage(
            uid=uid,
            workstream_id=workstream_id,
            source_key=stored_candidate.candidate_id,
            summary='Work initiated from an accepted suggestion',
            evidence_refs=stored_candidate.evidence_refs,
            now=now,
        )
        tx.set(
            workstream_path,
            _workstream_storage(
                workstream_id=workstream_id,
                title=proposal.title,
                objective=proposal.objective,
                goal_id=stored_candidate.goal_id,
                summary=proposal.objective,
                now=now,
                account_generation=account_generation,
            ),
        )
        tx.set(_event_path(uid, workstream_id, event_id), event_data)
        tx.set(
            task_path,
            _task_storage(
                task_id=task_id,
                description=proposal.anchor_task.description,
                goal_id=stored_candidate.goal_id,
                workstream_id=workstream_id,
                source=stored_candidate.source_surface,
                owner=proposal.anchor_task.owner,
                provenance=[ref.model_dump(mode='python') for ref in stored_candidate.evidence_refs],
                due_at=proposal.anchor_task.due_at,
                due_confidence=proposal.anchor_task.due_confidence,
                priority=proposal.anchor_task.priority,
                recurrence_rule=proposal.anchor_task.recurrence_rule,
                recurrence_parent_id=proposal.anchor_task.recurrence_parent_id,
                now=now,
                account_generation=account_generation,
            ),
        )
        tx.update(
            candidate_path,
            {
                'status': CandidateStatus.accepted.value,
                'resolution_reason': 'accepted',
                'result_task_id': task_id,
                'result_workstream_id': workstream_id,
                'resolved_at': now,
            },
        )
        tx.set(
            _candidate_outbox_path(uid, stored_candidate.candidate_id),
            {
                'outbox_id': stored_candidate.candidate_id,
                'candidate_id': stored_candidate.candidate_id,
                'task_id': task_id,
                'account_generation': account_generation,
                'status': 'pending',
                'attempt_count': 0,
                'created_at': now,
                'updated_at': now,
            },
        )
        return CandidateResolutionReceipt(
            candidate_id=stored_candidate.candidate_id,
            status=CandidateStatus.accepted,
            receipt_id=_stable_id('receipt', stored_candidate.candidate_id, account_generation, 'accepted'),
            task_id=task_id,
            workstream_id=workstream_id,
            newly_resolved=True,
            resolved_at=now,
        )

    return _store().run_transaction(apply)


def resolve_work_intent(
    uid: str,
    request: TaskOriginWorkIntent | GoalOriginWorkIntent,
    *,
    idempotency_key: str,
    account_generation: int,
) -> WorkIntentReceipt:
    if not idempotency_key.strip():
        raise ValueError('idempotency_key is required')
    receipt_id = _stable_id('intent', uid, account_generation, idempotency_key)
    receipt_path = _work_intent_receipt_path(uid, receipt_id)
    request_hash = hashlib.sha256(
        json.dumps(request.model_dump(mode='json'), sort_keys=True, separators=(',', ':')).encode('utf-8')
    ).hexdigest()
    now = datetime.now(timezone.utc)

    def apply(tx):
        control_snapshot = tx.get(_control_path(uid))
        _validate_control(control_snapshot, uid=uid, account_generation=account_generation)
        receipt_snapshot = tx.get(receipt_path)
        if receipt_snapshot.exists:
            stored = _snapshot_dict(receipt_snapshot)
            if stored.get('request_hash') != request_hash:
                raise WorkstreamConflictError('idempotency key was reused with another intent')
            stored.pop('request_hash', None)
            return WorkIntentReceipt.model_validate(stored)

        newly_created = False
        if isinstance(request, TaskOriginWorkIntent):
            task_path = _task_path(uid, request.task_id)
            task_snapshot = tx.get(task_path)
            if not task_snapshot.exists:
                raise WorkstreamNotFoundError(f'task:{request.task_id}')
            task = _snapshot_dict(task_snapshot)
            task_generation = int(task.get('account_generation', 0))
            if task_generation not in {0, account_generation}:
                raise WorkstreamGenerationMismatchError('task account generation mismatch')
            existing_workstream_id = task.get('workstream_id')
            goal_id = task.get('goal_id')
            legacy_goal_path = None
            if isinstance(goal_id, str) and goal_id:
                goal_path = _goal_path(uid, goal_id)
                goal_snapshot = tx.get(goal_path)
                if not goal_snapshot.exists:
                    raise WorkstreamConflictError('goal does not exist')
                goal_payload = goals_db.normalize_goal_storage(_snapshot_dict(goal_snapshot), goal_id=goal_id)
                goal_generation = int(goal_payload.get('account_generation', 0))
                if goal_generation not in {0, account_generation}:
                    raise WorkstreamGenerationMismatchError('goal account generation mismatch')
                if goal_payload['status'] in {GoalStatus.achieved.value, GoalStatus.abandoned.value}:
                    raise WorkstreamConflictError('ended goal cannot receive new work')
                if goal_generation == 0:
                    legacy_goal_path = goal_path
            if isinstance(existing_workstream_id, str) and existing_workstream_id:
                existing_workstream = tx.get(_workstream_path(uid, existing_workstream_id))
                if not existing_workstream.exists:
                    raise WorkstreamConflictError('task points to a missing workstream')
                existing_payload = _snapshot_dict(existing_workstream)
                workstream_generation = int(existing_payload.get('account_generation', 0))
                if workstream_generation not in {0, account_generation}:
                    raise WorkstreamGenerationMismatchError('workstream account generation mismatch')
                workstream = _workstream_from_snapshot(existing_workstream)
                if workstream.goal_id != goal_id:
                    raise WorkstreamConflictError('task and workstream goals disagree')
                workstream_id = existing_workstream_id
                task_id = request.task_id
                if legacy_goal_path is not None:
                    tx.update(
                        legacy_goal_path,
                        {'account_generation': account_generation, 'updated_at': now},
                    )
                if task_generation == 0:
                    tx.update(
                        task_path,
                        {'account_generation': account_generation, 'updated_at': now},
                    )
                if workstream_generation == 0:
                    tx.update(
                        _workstream_path(uid, workstream_id),
                        {'account_generation': account_generation, 'updated_at': now},
                    )
            else:
                workstream_id = _stable_id('workstream', uid, account_generation, 'task', request.task_id)
                task_id = request.task_id
                workstream_path = _workstream_path(uid, workstream_id)
                workstream_snapshot = tx.get(workstream_path)
                if workstream_snapshot.exists:
                    existing = _workstream_from_snapshot(workstream_snapshot)
                    if existing.goal_id != goal_id:
                        raise WorkstreamConflictError('deterministic workstream goal collision')
                if legacy_goal_path is not None:
                    tx.update(
                        legacy_goal_path,
                        {'account_generation': account_generation, 'updated_at': now},
                    )
                if not workstream_snapshot.exists:
                    event_id, event_data = _initial_event_storage(
                        uid=uid,
                        workstream_id=workstream_id,
                        source_key=f'task:{request.task_id}',
                        summary='Work initiated by the user',
                        evidence_refs=[],
                        now=now,
                    )
                    tx.set(
                        workstream_path,
                        _workstream_storage(
                            workstream_id=workstream_id,
                            title=request.title or str(task.get('description') or 'Task'),
                            objective=request.objective or str(task.get('description') or 'Advance this task'),
                            goal_id=goal_id,
                            now=now,
                            account_generation=account_generation,
                        ),
                    )
                    tx.set(_event_path(uid, workstream_id, event_id), event_data)
                    newly_created = True
                tx.update(
                    task_path,
                    {
                        'workstream_id': workstream_id,
                        'account_generation': account_generation,
                        'updated_at': now,
                    },
                )
        else:
            goal_id = request.goal_id
            _assert_goal_exists(
                uid,
                goal_id,
                account_generation=account_generation,
                tx=tx,
            )
            workstream_id = _stable_id('workstream', uid, 'goal-intent', receipt_id)
            task_id = _stable_id('task', uid, 'goal-intent', receipt_id)
            workstream_path = _workstream_path(uid, workstream_id)
            task_path = _task_path(uid, task_id)
            if tx.get(workstream_path).exists or tx.get(task_path).exists:
                raise WorkstreamConflictError('deterministic goal-origin intent id collision')
            event_id, event_data = _initial_event_storage(
                uid=uid,
                workstream_id=workstream_id,
                source_key=f'goal:{goal_id}:{receipt_id}',
                summary='Work initiated from a goal by the user',
                evidence_refs=[],
                now=now,
            )
            tx.set(
                workstream_path,
                _workstream_storage(
                    workstream_id=workstream_id,
                    title=request.title,
                    objective=request.objective,
                    goal_id=goal_id,
                    now=now,
                    account_generation=account_generation,
                ),
            )
            tx.set(_event_path(uid, workstream_id, event_id), event_data)
            tx.set(
                task_path,
                _task_storage(
                    task_id=task_id,
                    description=request.anchor_task_description,
                    goal_id=goal_id,
                    workstream_id=workstream_id,
                    source='explicit_goal_intent',
                    now=now,
                    account_generation=account_generation,
                ),
            )
            newly_created = True

        receipt = WorkIntentReceipt(
            receipt_id=receipt_id,
            workstream_id=workstream_id,
            task_id=task_id,
            goal_id=goal_id,
            newly_created=newly_created,
            created_at=now,
        )
        tx.set(receipt_path, {**receipt.model_dump(mode='python'), 'request_hash': request_hash})
        return receipt

    return _store().run_transaction(apply)


def import_task_goal_links(
    uid: str,
    request: TaskGoalLinkImportRequest,
    *,
    idempotency_key: str,
    account_generation: int,
) -> TaskGoalLinkImportReport:
    request_payload = request.model_dump(mode='json')
    operation = 'task-goal-link-import'
    request_hash = _mutation_hash(request_payload)
    receipt_path = _mutation_receipt_path(
        uid,
        operation=operation,
        idempotency_key=idempotency_key,
        account_generation=account_generation,
    )
    reservation_now = datetime.now(timezone.utc)

    def reserve(tx):
        control_snapshot = tx.get(_control_path(uid))
        _validate_control(control_snapshot, uid=uid, account_generation=account_generation)
        receipt_snapshot = tx.get(receipt_path)
        if receipt_snapshot.exists:
            receipt = _snapshot_dict(receipt_snapshot)
            if receipt.get('request_hash') != request_hash:
                raise WorkstreamConflictError('idempotency key was reused with different content')
            result = receipt.get('result')
            return cast(Optional[dict[str, Any]], result if isinstance(result, dict) else None)
        tx.set(
            receipt_path,
            {
                'request_hash': request_hash,
                'status': 'processing',
                'outcomes': {},
                'created_at': reservation_now,
                'updated_at': reservation_now,
            },
        )
        return None

    stored_result = _store().run_transaction(reserve)
    if stored_result is not None:
        return TaskGoalLinkImportReport.model_validate(stored_result)
    for index, link in enumerate(request.links):
        task_path = _task_path(uid, link.task_id)
        goal_path = _goal_path(uid, link.goal_id)

        def apply(tx, index=index, link=link, task_path=task_path, goal_path=goal_path):
            control_snapshot = tx.get(_control_path(uid))
            _validate_control(control_snapshot, uid=uid, account_generation=account_generation)
            receipt_snapshot = tx.get(receipt_path)
            if not receipt_snapshot.exists:
                raise WorkstreamConflictError('migration receipt disappeared')
            receipt = _snapshot_dict(receipt_snapshot)
            if receipt.get('request_hash') != request_hash:
                raise WorkstreamConflictError('migration receipt changed request identity')
            outcomes = receipt.get('outcomes')
            outcomes = dict(outcomes) if isinstance(outcomes, dict) else {}
            outcome_key = str(index)
            existing_outcome = outcomes.get(outcome_key)
            if isinstance(existing_outcome, str):
                return existing_outcome
            task_snapshot = tx.get(task_path)
            goal_snapshot = tx.get(goal_path)
            if not task_snapshot.exists or not goal_snapshot.exists:
                outcome = 'failed'
            else:
                task = _snapshot_dict(task_snapshot)
                workstream_id = task.get('workstream_id')
                relationship_valid = True
                if isinstance(workstream_id, str) and workstream_id:
                    workstream_snapshot = tx.get(_workstream_path(uid, workstream_id))
                    relationship_valid = bool(
                        workstream_snapshot.exists
                        and _snapshot_dict(workstream_snapshot).get('goal_id') == link.goal_id
                        and _snapshot_dict(workstream_snapshot).get('account_generation', 0) == account_generation
                    )
                goal_generation_matches = (
                    _snapshot_dict(goal_snapshot).get('account_generation', 0) == account_generation
                )
                current_goal_id = task.get('goal_id')
                task_generation = int(task.get('account_generation', 0))
                if (
                    task_generation not in {0, account_generation}
                    or not goal_generation_matches
                    or not relationship_valid
                    or current_goal_id not in {None, link.goal_id}
                ):
                    outcome = 'failed'
                elif current_goal_id == link.goal_id:
                    outcome = 'unchanged'
                    if task_generation == 0:
                        tx.update(
                            task_path,
                            {
                                'account_generation': account_generation,
                                'updated_at': datetime.now(timezone.utc),
                            },
                        )
                else:
                    outcome = 'imported'
                    tx.update(
                        task_path,
                        {
                            'goal_id': link.goal_id,
                            'account_generation': account_generation,
                            'updated_at': datetime.now(timezone.utc),
                        },
                    )
            outcomes[outcome_key] = outcome
            tx.update(receipt_path, {'outcomes': outcomes, 'updated_at': datetime.now(timezone.utc)})
            return outcome

        _store().run_transaction(apply)
    now = datetime.now(timezone.utc)

    def complete(tx):
        control_snapshot = tx.get(_control_path(uid))
        _validate_control(control_snapshot, uid=uid, account_generation=account_generation)
        receipt_snapshot = tx.get(receipt_path)
        if not receipt_snapshot.exists:
            raise WorkstreamConflictError('migration receipt disappeared')
        receipt = _snapshot_dict(receipt_snapshot)
        if receipt.get('request_hash') != request_hash:
            raise WorkstreamConflictError('migration receipt changed request identity')
        stored = receipt.get('result')
        if isinstance(stored, dict):
            return TaskGoalLinkImportReport.model_validate(stored)
        outcomes = receipt.get('outcomes')
        outcomes = dict(outcomes) if isinstance(outcomes, dict) else {}
        if len(outcomes) != len(request.links):
            raise WorkstreamConflictError('migration receipt is incomplete')
        ordered_outcomes = [outcomes[str(index)] for index in range(len(request.links))]
        report = TaskGoalLinkImportReport(
            imported=ordered_outcomes.count('imported'),
            unchanged=ordered_outcomes.count('unchanged'),
            failed=ordered_outcomes.count('failed'),
            failure_task_ids=[
                link.task_id for index, link in enumerate(request.links) if ordered_outcomes[index] == 'failed'
            ],
        )
        tx.update(
            receipt_path,
            {
                'status': 'complete',
                'result': report.model_dump(mode='python'),
                'updated_at': now,
                'completed_at': now,
            },
        )
        return report

    return _store().run_transaction(complete)


def get_goal_detail(uid: str, goal_id: str) -> GoalDetailProjection:
    goal = goals_db.get_goal_by_id(uid, goal_id)
    if goal is None:
        raise WorkstreamNotFoundError(f'goal:{goal_id}')
    task_snapshots = _store().query(_tasks_collection_path(uid), filters=[('goal_id', '==', goal_id)])
    tasks = _task_responses_from_snapshots(task_snapshots, context='goal_detail')
    return GoalDetailProjection(
        goal=GoalResponse.model_validate(goals_db.ensure_released_goal_aliases(goal)),
        active_threads=list_workstreams_for_goal(uid, goal_id),
        tasks=tasks,
        progress_events=goals_db.list_goal_progress_events(uid, goal_id),
    )


def get_workstream_detail(
    uid: str,
    workstream_id: str,
) -> WorkstreamDetailProjection:
    workstream = get_workstream(uid, workstream_id)
    if workstream is None:
        raise WorkstreamNotFoundError(workstream_id)
    task_snapshots = _store().query(
        _tasks_collection_path(uid), filters=[('workstream_id', '==', workstream_id)]
    )
    tasks = _task_responses_from_snapshots(task_snapshots, context='workstream_detail')
    return WorkstreamDetailProjection(
        workstream=workstream,
        recent_events=list_workstream_events(uid, workstream_id),
        tasks=tasks,
        artifacts=list_artifact_descriptors(uid, workstream_id),
        checkpoints=list_continuation_checkpoints(uid, workstream_id),
    )


__all__ = [
    'WorkstreamConflictError',
    'WorkstreamGenerationMismatchError',
    'WorkstreamNotFoundError',
    'WorkstreamStoreError',
    'append_workstream_event',
    'create_artifact_descriptor',
    'get_goal_detail',
    'get_workstream',
    'get_workstream_detail',
    'get_workstream_goal_id',
    'import_task_goal_links',
    'list_artifact_descriptors',
    'list_continuation_checkpoints',
    'list_workstream_events',
    'list_workstreams_for_goal',
    'resolve_work_intent',
    'resolve_workstream_candidate',
    'transition_artifact_status',
    'update_workstream',
    'upsert_continuation_checkpoint',
]
