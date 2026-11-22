"""Canonical workstream persistence and atomic task/workflow transactions."""

from __future__ import annotations

from uuid import uuid4
import hashlib
import json
from database.ports.workstreams import (
    WorkstreamStoreError,
    WorkstreamNotFoundError,
    WorkstreamConflictError,
    WorkstreamGenerationMismatchError,
    WorkstreamEntity,
    WorkstreamCreate,
    WorkstreamUpdate as PortWorkstreamUpdate,
    WorkstreamEventEntity,
    ArtifactDescriptorEntity,
    ContinuationCheckpointEntity,
)
from contextlib import nullcontext
from copy import deepcopy
from database.action_item_fence import fenced_action_item_commit
from datetime import datetime, timezone
from typing import Any, Optional, cast

from google.cloud import firestore

from google.cloud.firestore_v1 import FieldFilter
from database import action_items as action_items_db
import database.goals as goals_db
from database.action_items_cache import bump_action_items_list_version
from database import candidates as candidates_db
from database._client import get_firestore_client
from database.staged_promote_cache import invalidate_around_write
from database.read_boundary import parse_payload_strict, parse_snapshot_or_none, parse_snapshot_strict, parse_snapshots
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


def _get_db(firestore_client: Any = None) -> Any:
    return firestore_client or get_firestore_client()


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


def _user_ref(uid: str, *, firestore_client: Any = None):
    return _get_db(firestore_client).collection('users').document(uid)


def _workstream_ref(uid: str, workstream_id: str, *, firestore_client: Any = None):
    return _user_ref(uid, firestore_client=firestore_client).collection(WORKSTREAMS_COLLECTION).document(workstream_id)


def _task_ref(uid: str, task_id: str, *, firestore_client: Any = None):
    return _user_ref(uid, firestore_client=firestore_client).collection(ACTION_ITEMS_COLLECTION).document(task_id)


def _candidate_ref(uid: str, candidate_id: str, *, firestore_client: Any = None):
    return _user_ref(uid, firestore_client=firestore_client).collection(CANDIDATES_COLLECTION).document(candidate_id)


def _candidate_outbox_ref(uid: str, candidate_id: str, *, firestore_client: Any = None):
    return (
        _user_ref(uid, firestore_client=firestore_client)
        .collection(CANDIDATE_INTEGRATION_OUTBOX_COLLECTION)
        .document(candidate_id)
    )


def _control_ref(uid: str, *, firestore_client: Any = None):
    return (
        _user_ref(uid, firestore_client=firestore_client)
        .collection(TASK_INTELLIGENCE_CONTROL_COLLECTION)
        .document(TASK_INTELLIGENCE_CONTROL_DOCUMENT)
    )


def _mutation_receipt_ref(
    uid: str,
    *,
    operation: str,
    idempotency_key: str,
    account_generation: int,
    firestore_client: Any,
):
    receipt_id = _stable_id('mutation', uid, account_generation, operation, idempotency_key)
    return (
        _user_ref(uid, firestore_client=firestore_client).collection(MUTATION_RECEIPTS_COLLECTION).document(receipt_id)
    )


def _mutation_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str).encode('utf-8')
    ).hexdigest()


def _begin_mutation(
    write_transaction: Any,
    *,
    uid: str,
    operation: str,
    idempotency_key: str,
    account_generation: int,
    request_payload: Any,
    firestore_client: Any,
) -> tuple[Any, Optional[dict[str, Any]], str]:
    control_snapshot = _control_ref(uid, firestore_client=firestore_client).get(transaction=write_transaction)
    _validate_control(control_snapshot, uid=uid, account_generation=account_generation)
    receipt_ref = _mutation_receipt_ref(
        uid,
        operation=operation,
        idempotency_key=idempotency_key,
        account_generation=account_generation,
        firestore_client=firestore_client,
    )
    request_hash = _mutation_hash(request_payload)
    receipt_snapshot = receipt_ref.get(transaction=write_transaction)
    if not receipt_snapshot.exists:
        return receipt_ref, None, request_hash
    receipt = _snapshot_dict(receipt_snapshot)
    if receipt.get('request_hash') != request_hash:
        raise WorkstreamConflictError('idempotency key was reused with different content')
    result = receipt.get('result')
    if not isinstance(result, dict):
        raise WorkstreamConflictError('idempotent mutation receipt is incomplete')
    return receipt_ref, cast(dict[str, Any], result), request_hash


def _finish_mutation(
    write_transaction: Any,
    receipt_ref: Any,
    *,
    request_hash: str,
    result: dict[str, Any],
    now: datetime,
) -> None:
    write_transaction.create(
        receipt_ref,
        {'request_hash': request_hash, 'result': result, 'created_at': now},
    )


def _validate_control(snapshot: Any, *, uid: str, account_generation: int) -> None:
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
    transaction: Any,
    firestore_client: Any,
) -> None:
    if goal_id is None:
        return
    snapshot = goals_db.goal_document_ref(uid, goal_id, firestore_client=firestore_client).get(transaction=transaction)
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
    firestore_client: Any = None,
) -> Optional[Workstream]:
    snapshot = _workstream_ref(uid, workstream_id, firestore_client=firestore_client).get()
    if not snapshot.exists:
        return None
    payload = _snapshot_dict(snapshot)
    if account_generation is not None and payload.get('account_generation', 0) != account_generation:
        return None
    return parse_snapshot_or_none(Workstream, snapshot, payload_from_snapshot=_workstream_payload)


def get_workstream_goal_id(uid: str, workstream_id: str, *, firestore_client: Any = None) -> Optional[str]:
    workstream = get_workstream(uid, workstream_id, firestore_client=firestore_client)
    if workstream is None:
        raise WorkstreamNotFoundError(workstream_id)
    return workstream.goal_id


def get_task_workflow_control(uid: str, *, firestore_client: Any = None) -> TaskWorkflowControl:
    snapshot = _control_ref(uid, firestore_client=firestore_client).get()
    if not snapshot.exists:
        return TaskWorkflowControl()
    return parse_snapshot_strict(TaskWorkflowControl, snapshot)


def list_open_workstreams(
    uid: str,
    *,
    limit: int = 500,
    account_generation: Optional[int] = None,
    firestore_client: Any = None,
) -> list[Workstream]:
    query = (
        _user_ref(uid, firestore_client=firestore_client)
        .collection(WORKSTREAMS_COLLECTION)
        .where(filter=FieldFilter('status', '==', WorkstreamStatus.open.value))
    )
    if account_generation is not None and account_generation > 0:
        query = query.where(filter=FieldFilter('account_generation', '==', account_generation))
    query = query.limit(limit)
    snapshots = list(query.stream())
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
    firestore_client: Any = None,
) -> list[Workstream]:
    query = (
        _user_ref(uid, firestore_client=firestore_client)
        .collection(WORKSTREAMS_COLLECTION)
        .where(filter=FieldFilter('goal_id', '==', goal_id))
        .limit(limit)
    )
    records = parse_snapshots(Workstream, query.stream(), payload_from_snapshot=_workstream_payload)
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
    firestore_client: Any = None,
) -> Workstream:
    return FirestoreWorkstreams(uid, firestore_client=firestore_client).update_document(
        workstream_id, update, idempotency_key=idempotency_key, account_generation=account_generation
    )


def append_workstream_event(
    uid: str,
    workstream_id: str,
    event: WorkstreamEventCreate,
    *,
    idempotency_key: str,
    account_generation: int,
    firestore_client: Any = None,
    required_status: Optional[WorkstreamStatus] = None,
) -> WorkstreamEvent:
    return FirestoreWorkstreams(uid, firestore_client=firestore_client).append_event_document(
        workstream_id,
        event,
        idempotency_key=idempotency_key,
        account_generation=account_generation,
        required_status=required_status,
    )


def list_workstream_events(
    uid: str,
    workstream_id: str,
    *,
    after_sequence: int = 0,
    limit: int = 100,
    firestore_client: Any = None,
) -> list[WorkstreamEvent]:
    query = (
        _workstream_ref(uid, workstream_id, firestore_client=firestore_client)
        .collection(EVENTS_COLLECTION)
        .where(filter=FieldFilter('sequence', '>', after_sequence))
        .order_by('sequence', direction=firestore.Query.ASCENDING)
        .limit(limit)
    )
    return parse_snapshots(WorkstreamEvent, query.stream())


def create_artifact_descriptor(
    uid: str,
    workstream_id: str,
    proposal: ArtifactDescriptorCreate,
    *,
    idempotency_key: str,
    account_generation: int,
    firestore_client: Any = None,
) -> ArtifactDescriptor:
    return FirestoreWorkstreams(uid, firestore_client=firestore_client).create_artifact_document(
        workstream_id, proposal, idempotency_key=idempotency_key, account_generation=account_generation
    )


def transition_artifact_status(
    uid: str,
    workstream_id: str,
    artifact_id: str,
    request: ArtifactStatusTransitionRequest,
    *,
    idempotency_key: str,
    account_generation: int,
    firestore_client: Any = None,
) -> ArtifactDescriptor:
    return FirestoreWorkstreams(uid, firestore_client=firestore_client).transition_artifact_document(
        workstream_id, artifact_id, request, idempotency_key=idempotency_key, account_generation=account_generation
    )


def list_artifact_descriptors(
    uid: str,
    workstream_id: str,
    *,
    limit: int = 100,
    firestore_client: Any = None,
) -> list[ArtifactDescriptor]:
    query = (
        _workstream_ref(uid, workstream_id, firestore_client=firestore_client)
        .collection(ARTIFACTS_COLLECTION)
        .order_by('created_at', direction=firestore.Query.DESCENDING)
        .limit(limit)
    )
    return parse_snapshots(ArtifactDescriptor, query.stream())


def upsert_continuation_checkpoint(
    uid: str,
    workstream_id: str,
    checkpoint: ContinuationCheckpointUpsert,
    *,
    idempotency_key: str,
    account_generation: int,
    firestore_client: Any = None,
) -> ContinuationCheckpoint:
    return FirestoreWorkstreams(uid, firestore_client=firestore_client).upsert_checkpoint_document(
        workstream_id, checkpoint, idempotency_key=idempotency_key, account_generation=account_generation
    )


def list_continuation_checkpoints(
    uid: str,
    workstream_id: str,
    *,
    firestore_client: Any = None,
) -> list[ContinuationCheckpoint]:
    snapshots = (
        _workstream_ref(uid, workstream_id, firestore_client=firestore_client)
        .collection(CHECKPOINTS_COLLECTION)
        .stream()
    )
    return parse_snapshots(ContinuationCheckpoint, snapshots)


@invalidate_around_write
def resolve_workstream_candidate(
    uid: str,
    candidate: CandidateRecord,
    account_generation: int,
    *,
    firestore_client: Any = None,
) -> CandidateResolutionReceipt:
    return FirestoreWorkstreams(uid, firestore_client=firestore_client).resolve_candidate_document(
        candidate, account_generation
    )


def resolve_work_intent(
    uid: str,
    request: TaskOriginWorkIntent | GoalOriginWorkIntent,
    *,
    idempotency_key: str,
    account_generation: int,
    firestore_client: Any = None,
) -> WorkIntentReceipt:
    return FirestoreWorkstreams(uid, firestore_client=firestore_client).resolve_intent_document(
        request, idempotency_key=idempotency_key, account_generation=account_generation
    )


def import_task_goal_links(
    uid: str,
    request: TaskGoalLinkImportRequest,
    *,
    idempotency_key: str,
    account_generation: int,
    firestore_client: Any = None,
) -> TaskGoalLinkImportReport:
    return FirestoreWorkstreams(uid, firestore_client=firestore_client).import_links_documents(
        request, idempotency_key=idempotency_key, account_generation=account_generation
    )


def get_goal_detail(uid: str, goal_id: str, *, firestore_client: Any = None) -> GoalDetailProjection:
    client = _get_db(firestore_client)
    goal = goals_db.get_goal_by_id(uid, goal_id, firestore_client=client)
    if goal is None:
        raise WorkstreamNotFoundError(f'goal:{goal_id}')
    user_ref = _user_ref(uid, firestore_client=client)
    task_snapshots = (
        user_ref.collection(ACTION_ITEMS_COLLECTION).where(filter=FieldFilter('goal_id', '==', goal_id)).stream()
    )
    tasks = _task_responses_from_snapshots(task_snapshots, context='goal_detail')
    return GoalDetailProjection(
        goal=GoalResponse.model_validate(goals_db.ensure_released_goal_aliases(goal)),
        active_threads=list_workstreams_for_goal(uid, goal_id, firestore_client=client),
        tasks=tasks,
        progress_events=goals_db.list_goal_progress_events(uid, goal_id, firestore_client=client),
    )


def get_workstream_detail(
    uid: str,
    workstream_id: str,
    *,
    firestore_client: Any = None,
) -> WorkstreamDetailProjection:
    client = _get_db(firestore_client)
    workstream = get_workstream(uid, workstream_id, firestore_client=client)
    if workstream is None:
        raise WorkstreamNotFoundError(workstream_id)
    task_snapshots = (
        _user_ref(uid, firestore_client=client)
        .collection(ACTION_ITEMS_COLLECTION)
        .where(filter=FieldFilter('workstream_id', '==', workstream_id))
        .stream()
    )
    tasks = _task_responses_from_snapshots(task_snapshots, context='workstream_detail')
    return WorkstreamDetailProjection(
        workstream=workstream,
        # The journal is contiguous: every append sets sequence to
        # latest_event_sequence + 1 in the same transaction. Reading from
        # latest_event_sequence - 100 returns the newest 100 events in the
        # ascending order the response already promises. The default
        # after_sequence=0 always returned sequences 1..100, so a thread past
        # 100 events never showed its newest changes.
        recent_events=list_workstream_events(
            uid,
            workstream_id,
            after_sequence=max(0, workstream.latest_event_sequence - 100),
            firestore_client=client,
        ),
        tasks=tasks,
        artifacts=list_artifact_descriptors(uid, workstream_id, firestore_client=client),
        checkpoints=list_continuation_checkpoints(uid, workstream_id, firestore_client=client),
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


class FirestoreWorkstreams:

    def __init__(self, space_id: str, *, firestore_client: Any = None, transaction: Any = None):
        self.space_id = space_id
        self.client = _get_db(firestore_client)
        self.transaction = transaction
        self.commit_context: Any = None

    def _read(self, ref):
        return ref.get(transaction=self.transaction) if self.transaction is not None else ref.get()

    def _post_commit(self, callback):
        if self.commit_context is not None:
            self.commit_context.after_commit(callback)
        elif self.transaction is None:
            callback()
        else:
            raise RuntimeError('task post-commit effects require a SpaceStore commit context')

    def _transaction_write(self, transaction, operation, ref, *args, **kwargs):
        self._touch()
        return getattr(transaction, operation)(ref, *args, **kwargs)

    def _apply_transaction(self, fn, transaction, *, task_writes=False):
        if self.transaction is not None:
            if task_writes and self.commit_context is None:
                raise RuntimeError('task writes require a SpaceStore commit context')
            return getattr(fn, 'to_wrap', fn)(self.transaction)
        with self._fence() if task_writes else nullcontext():
            return fn(transaction)

    def _touch(self):
        pass

    def _fence(self):
        return fenced_action_item_commit(self.space_id)

    def update_document(
        self,
        workstream_id: str,
        update: WorkstreamUpdate,
        *,
        idempotency_key: str,
        account_generation: int,
        firestore_client: Any = None,
    ) -> Workstream:
        uid = self.space_id
        client = self.client
        ref = _workstream_ref(uid, workstream_id, firestore_client=client)
        patch = update.model_dump(mode='python', exclude_unset=True)
        transaction = client.transaction()
        now = datetime.now(timezone.utc)

        @firestore.transactional
        def apply(write_transaction):
            receipt_ref, stored_result, request_hash = _begin_mutation(
                write_transaction,
                uid=uid,
                operation=f'workstream-update:{workstream_id}',
                idempotency_key=idempotency_key,
                account_generation=account_generation,
                request_payload=update.model_dump(mode='json', exclude_unset=True),
                firestore_client=client,
            )
            if stored_result is not None:
                return Workstream.model_validate(stored_result)
            snapshot = ref.get(transaction=write_transaction)
            if not snapshot.exists:
                raise WorkstreamNotFoundError(workstream_id)
            _assert_workstream_generation(snapshot, account_generation=account_generation)
            result = _workstream_from_snapshot(snapshot).model_copy(update={**patch, 'updated_at': now})
            self._transaction_write(write_transaction, 'update', ref, {**patch, 'updated_at': now})
            result_payload = result.model_dump(mode='python')
            _finish_mutation(write_transaction, receipt_ref, request_hash=request_hash, result=result_payload, now=now)
            return result

        return self._apply_transaction(apply, transaction)

    def append_event_document(
        self,
        workstream_id: str,
        event: WorkstreamEventCreate,
        *,
        idempotency_key: str,
        account_generation: int,
        firestore_client: Any = None,
        required_status: Optional[WorkstreamStatus] = None,
    ) -> WorkstreamEvent:
        uid = self.space_id
        client = self.client
        workstream_ref = _workstream_ref(uid, workstream_id, firestore_client=client)
        transaction = client.transaction()
        now = datetime.now(timezone.utc)
        event_id = _stable_id('wse', uid, workstream_id, account_generation, idempotency_key)
        event_ref = workstream_ref.collection(EVENTS_COLLECTION).document(event_id)

        @firestore.transactional
        def apply(write_transaction):
            control_snapshot = _control_ref(uid, firestore_client=client).get(transaction=write_transaction)
            _validate_control(control_snapshot, uid=uid, account_generation=account_generation)
            workstream_snapshot = workstream_ref.get(transaction=write_transaction)
            if not workstream_snapshot.exists:
                raise WorkstreamNotFoundError(workstream_id)
            _assert_workstream_generation(workstream_snapshot, account_generation=account_generation)
            existing = event_ref.get(transaction=write_transaction)
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
            self._transaction_write(write_transaction, 'create', event_ref, record.model_dump(mode='python'))
            self._transaction_write(
                write_transaction,
                'update',
                workstream_ref,
                {'latest_event_sequence': sequence, 'last_meaningful_progress_at': now, 'updated_at': now},
            )
            return record

        return self._apply_transaction(apply, transaction)

    def create_artifact_document(
        self,
        workstream_id: str,
        proposal: ArtifactDescriptorCreate,
        *,
        idempotency_key: str,
        account_generation: int,
        firestore_client: Any = None,
    ) -> ArtifactDescriptor:
        uid = self.space_id
        client = self.client
        workstream_ref = _workstream_ref(uid, workstream_id, firestore_client=client)
        artifact_id = _stable_id('artifact', uid, workstream_id, proposal.logical_key, proposal.version)
        artifact_ref = workstream_ref.collection(ARTIFACTS_COLLECTION).document(artifact_id)
        head_ref = workstream_ref.collection(ARTIFACT_HEADS_COLLECTION).document(
            _stable_id('artifact-head', uid, workstream_id, proposal.logical_key)
        )
        transaction = client.transaction()
        now = datetime.now(timezone.utc)

        @firestore.transactional
        def apply(write_transaction):
            receipt_ref, stored_result, request_hash = _begin_mutation(
                write_transaction,
                uid=uid,
                operation=f'artifact-create:{workstream_id}',
                idempotency_key=idempotency_key,
                account_generation=account_generation,
                request_payload=proposal.model_dump(mode='json'),
                firestore_client=client,
            )
            if stored_result is not None:
                return ArtifactDescriptor.model_validate(stored_result)
            workstream_snapshot = workstream_ref.get(transaction=write_transaction)
            if not workstream_snapshot.exists:
                raise WorkstreamNotFoundError(workstream_id)
            _assert_workstream_generation(workstream_snapshot, account_generation=account_generation)
            existing = artifact_ref.get(transaction=write_transaction)
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
                    write_transaction,
                    receipt_ref,
                    request_hash=request_hash,
                    result=stored.model_dump(mode='python'),
                    now=now,
                )
                return stored
            head_snapshot = head_ref.get(transaction=write_transaction)
            superseded_ref = None
            if head_snapshot.exists:
                head = _snapshot_dict(head_snapshot)
                expected_version = int(head.get('version', 0)) + 1
                expected_artifact_id = head.get('artifact_id')
                if proposal.version != expected_version or proposal.supersedes_artifact_id != expected_artifact_id:
                    raise WorkstreamConflictError(
                        'artifact version must advance and supersede the current logical head'
                    )
                superseded_ref = workstream_ref.collection(ARTIFACTS_COLLECTION).document(str(expected_artifact_id))
                superseded_snapshot = superseded_ref.get(transaction=write_transaction)
                if not superseded_snapshot.exists:
                    raise WorkstreamConflictError('artifact head points to a missing descriptor')
                superseded = parse_snapshot_strict(ArtifactDescriptor, superseded_snapshot)
                if superseded.logical_key != proposal.logical_key or superseded.status == ArtifactStatus.superseded:
                    raise WorkstreamConflictError('artifact head is not a live version of this logical artifact')
            elif proposal.version != 1 or proposal.supersedes_artifact_id is not None:
                raise WorkstreamConflictError(
                    'the first logical artifact version must be version 1 without supersession'
                )
            if proposal.supersedes_artifact_id is not None and (not proposal.evidence_event_ids):
                raise WorkstreamConflictError(
                    'artifact revisions must cite the journal evidence that caused the change'
                )
            for event_id in proposal.evidence_event_ids:
                evidence_snapshot = (
                    workstream_ref.collection(EVENTS_COLLECTION).document(event_id).get(transaction=write_transaction)
                )
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
            self._transaction_write(write_transaction, 'create', artifact_ref, record.model_dump(mode='python'))
            self._transaction_write(
                write_transaction,
                'create',
                workstream_ref.collection(EVENTS_COLLECTION).document(event_id),
                event.model_dump(mode='python'),
            )
            if superseded_ref is not None:
                self._transaction_write(
                    write_transaction, 'update', superseded_ref, {'status': ArtifactStatus.superseded.value}
                )
            self._transaction_write(
                write_transaction,
                'set',
                head_ref,
                {
                    'logical_key': proposal.logical_key,
                    'artifact_id': artifact_id,
                    'version': proposal.version,
                    'updated_at': now,
                },
            )
            self._transaction_write(
                write_transaction,
                'update',
                workstream_ref,
                {'latest_event_sequence': sequence, 'last_meaningful_progress_at': now, 'updated_at': now},
            )
            _finish_mutation(
                write_transaction,
                receipt_ref,
                request_hash=request_hash,
                result=record.model_dump(mode='python'),
                now=now,
            )
            return record

        return self._apply_transaction(apply, transaction)

    def transition_artifact_document(
        self,
        workstream_id: str,
        artifact_id: str,
        request: ArtifactStatusTransitionRequest,
        *,
        idempotency_key: str,
        account_generation: int,
        firestore_client: Any = None,
    ) -> ArtifactDescriptor:
        uid = self.space_id
        client = self.client
        workstream_ref = _workstream_ref(uid, workstream_id, firestore_client=client)
        artifact_ref = workstream_ref.collection(ARTIFACTS_COLLECTION).document(artifact_id)
        transaction = client.transaction()
        now = datetime.now(timezone.utc)
        allowed_transitions = {
            ArtifactStatus.draft: ArtifactStatus.awaiting_review,
            ArtifactStatus.awaiting_review: ArtifactStatus.approved,
            ArtifactStatus.approved: ArtifactStatus.delivered,
        }

        @firestore.transactional
        def apply(write_transaction):
            receipt_ref, stored_result, request_hash = _begin_mutation(
                write_transaction,
                uid=uid,
                operation=f'artifact-status:{workstream_id}:{artifact_id}',
                idempotency_key=idempotency_key,
                account_generation=account_generation,
                request_payload=request.model_dump(mode='json'),
                firestore_client=client,
            )
            if stored_result is not None:
                return ArtifactDescriptor.model_validate(stored_result)
            workstream_snapshot = workstream_ref.get(transaction=write_transaction)
            if not workstream_snapshot.exists:
                raise WorkstreamNotFoundError(workstream_id)
            _assert_workstream_generation(workstream_snapshot, account_generation=account_generation)
            artifact_snapshot = artifact_ref.get(transaction=write_transaction)
            if not artifact_snapshot.exists:
                raise WorkstreamNotFoundError(artifact_id)
            artifact = parse_snapshot_strict(ArtifactDescriptor, artifact_snapshot)
            if artifact.status == request.status:
                _finish_mutation(
                    write_transaction,
                    receipt_ref,
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
            self._transaction_write(write_transaction, 'update', artifact_ref, {'status': request.status.value})
            self._transaction_write(
                write_transaction,
                'create',
                workstream_ref.collection(EVENTS_COLLECTION).document(event.event_id),
                event.model_dump(mode='python'),
            )
            self._transaction_write(
                write_transaction,
                'update',
                workstream_ref,
                {'latest_event_sequence': sequence, 'last_meaningful_progress_at': now, 'updated_at': now},
            )
            result = artifact.model_copy(update={'status': request.status})
            _finish_mutation(
                write_transaction,
                receipt_ref,
                request_hash=request_hash,
                result=result.model_dump(mode='python'),
                now=now,
            )
            return result

        return self._apply_transaction(apply, transaction)

    def upsert_checkpoint_document(
        self,
        workstream_id: str,
        checkpoint: ContinuationCheckpointUpsert,
        *,
        idempotency_key: str,
        account_generation: int,
        firestore_client: Any = None,
    ) -> ContinuationCheckpoint:
        uid = self.space_id
        client = self.client
        workstream_ref = _workstream_ref(uid, workstream_id, firestore_client=client)
        checkpoint_id = _stable_id('checkpoint', uid, workstream_id, checkpoint.runtime_id)
        checkpoint_ref = workstream_ref.collection(CHECKPOINTS_COLLECTION).document(checkpoint_id)
        transaction = client.transaction()
        now = datetime.now(timezone.utc)

        @firestore.transactional
        def apply(write_transaction):
            receipt_ref, stored_result, request_hash = _begin_mutation(
                write_transaction,
                uid=uid,
                operation=f'checkpoint-upsert:{workstream_id}:{checkpoint.runtime_id}',
                idempotency_key=idempotency_key,
                account_generation=account_generation,
                request_payload=checkpoint.model_dump(mode='json'),
                firestore_client=client,
            )
            if stored_result is not None:
                return ContinuationCheckpoint.model_validate(stored_result)
            workstream_snapshot = workstream_ref.get(transaction=write_transaction)
            if not workstream_snapshot.exists:
                raise WorkstreamNotFoundError(workstream_id)
            _assert_workstream_generation(workstream_snapshot, account_generation=account_generation)
            workstream = _workstream_from_snapshot(workstream_snapshot)
            if checkpoint.last_event_sequence > workstream.latest_event_sequence:
                raise WorkstreamConflictError('checkpoint cannot advance beyond the workstream journal')
            checkpoint_snapshot = checkpoint_ref.get(transaction=write_transaction)
            if checkpoint_snapshot.exists:
                existing = parse_snapshot_strict(ContinuationCheckpoint, checkpoint_snapshot)
                if checkpoint.last_event_sequence < existing.last_event_sequence:
                    raise WorkstreamConflictError('checkpoint sequence cannot move backwards')
                if checkpoint.last_event_sequence == existing.last_event_sequence:
                    equivalent = (
                        checkpoint.runtime_id == existing.runtime_id
                        and checkpoint.context_summary == existing.context_summary
                        and (checkpoint.evidence_refs == existing.evidence_refs)
                    )
                    if not equivalent:
                        raise WorkstreamConflictError('checkpoint sequence already stores different content')
                    _finish_mutation(
                        write_transaction,
                        receipt_ref,
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
            self._transaction_write(write_transaction, 'set', checkpoint_ref, record.model_dump(mode='python'))
            _finish_mutation(
                write_transaction,
                receipt_ref,
                request_hash=request_hash,
                result=record.model_dump(mode='python'),
                now=now,
            )
            return record

        return self._apply_transaction(apply, transaction)

    def resolve_candidate_document(
        self, candidate: CandidateRecord, account_generation: int, *, firestore_client: Any = None
    ) -> CandidateResolutionReceipt:
        uid = self.space_id
        if candidate.subject_kind != CandidateSubjectKind.workstream or candidate.workstream_proposal is None:
            raise WorkstreamConflictError('Candidate is not a workstream create proposal')
        client = self.client
        candidate_ref = _candidate_ref(uid, candidate.candidate_id, firestore_client=client)
        workstream_id = _stable_id('workstream', uid, account_generation, candidate.candidate_id)
        task_id = _stable_id('task', uid, account_generation, candidate.candidate_id)
        workstream_ref = _workstream_ref(uid, workstream_id, firestore_client=client)
        task_ref = _task_ref(uid, task_id, firestore_client=client)
        transaction = client.transaction()

        @firestore.transactional
        def apply(write_transaction):
            control_snapshot = _control_ref(uid, firestore_client=client).get(transaction=write_transaction)
            _validate_control(control_snapshot, uid=uid, account_generation=account_generation)
            candidate_snapshot = candidate_ref.get(transaction=write_transaction)
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
            now = datetime.now(timezone.utc)
            if candidates_db.candidate_has_lapsed(stored_candidate, now=now):
                raise WorkstreamConflictError('Candidate suggestion has expired')
            proposal = stored_candidate.workstream_proposal
            if proposal is None:
                raise WorkstreamConflictError('stored Candidate has no workstream proposal')
            _assert_goal_exists(
                uid,
                stored_candidate.goal_id,
                account_generation=account_generation,
                transaction=write_transaction,
                firestore_client=client,
            )
            workstream_snapshot = workstream_ref.get(transaction=write_transaction)
            task_snapshot = task_ref.get(transaction=write_transaction)
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
            self._transaction_write(
                write_transaction,
                'create',
                workstream_ref,
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
            self._transaction_write(
                write_transaction, 'create', workstream_ref.collection(EVENTS_COLLECTION).document(event_id), event_data
            )
            self._task_write(
                write_transaction,
                'create',
                task_ref,
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
            self._transaction_write(
                write_transaction,
                'update',
                candidate_ref,
                {
                    'status': CandidateStatus.accepted.value,
                    'resolution_reason': 'accepted',
                    'result_task_id': task_id,
                    'result_workstream_id': workstream_id,
                    'resolved_at': now,
                },
            )
            self._transaction_write(
                write_transaction,
                'create',
                _candidate_outbox_ref(uid, stored_candidate.candidate_id, firestore_client=client),
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

        receipt = self._apply_transaction(apply, transaction, task_writes=True)
        if receipt.newly_resolved:
            self._post_commit(lambda: bump_action_items_list_version(uid))
        return receipt

    def resolve_intent_document(
        self,
        request: TaskOriginWorkIntent | GoalOriginWorkIntent,
        *,
        idempotency_key: str,
        account_generation: int,
        firestore_client: Any = None,
    ) -> WorkIntentReceipt:
        uid = self.space_id
        if not idempotency_key.strip():
            raise ValueError('idempotency_key is required')
        client = self.client
        receipt_id = _stable_id('intent', uid, account_generation, idempotency_key)
        receipt_ref = (
            _user_ref(uid, firestore_client=client).collection(WORK_INTENT_RECEIPTS_COLLECTION).document(receipt_id)
        )
        request_hash = hashlib.sha256(
            json.dumps(request.model_dump(mode='json'), sort_keys=True, separators=(',', ':')).encode('utf-8')
        ).hexdigest()
        transaction = client.transaction()
        now = datetime.now(timezone.utc)

        @firestore.transactional
        def apply(write_transaction):
            control_snapshot = _control_ref(uid, firestore_client=client).get(transaction=write_transaction)
            _validate_control(control_snapshot, uid=uid, account_generation=account_generation)
            receipt_snapshot = receipt_ref.get(transaction=write_transaction)
            if receipt_snapshot.exists:
                stored = _snapshot_dict(receipt_snapshot)
                if stored.get('request_hash') != request_hash:
                    raise WorkstreamConflictError('idempotency key was reused with another intent')
                stored.pop('request_hash', None)
                return (WorkIntentReceipt.model_validate(stored), False)
            newly_created = False
            task_written = False
            if isinstance(request, TaskOriginWorkIntent):
                task_ref = _task_ref(uid, request.task_id, firestore_client=client)
                task_snapshot = task_ref.get(transaction=write_transaction)
                if not task_snapshot.exists:
                    raise WorkstreamNotFoundError(f'task:{request.task_id}')
                task = _snapshot_dict(task_snapshot)
                task_generation = int(task.get('account_generation', 0))
                if task_generation not in {0, account_generation}:
                    raise WorkstreamGenerationMismatchError('task account generation mismatch')
                existing_workstream_id = task.get('workstream_id')
                goal_id = task.get('goal_id')
                legacy_goal_ref = None
                if isinstance(goal_id, str) and goal_id:
                    goal_ref = goals_db.goal_document_ref(uid, goal_id, firestore_client=client)
                    goal_snapshot = goal_ref.get(transaction=write_transaction)
                    if not goal_snapshot.exists:
                        raise WorkstreamConflictError('goal does not exist')
                    goal_payload = goals_db.normalize_goal_storage(_snapshot_dict(goal_snapshot), goal_id=goal_id)
                    goal_generation = int(goal_payload.get('account_generation', 0))
                    if goal_generation not in {0, account_generation}:
                        raise WorkstreamGenerationMismatchError('goal account generation mismatch')
                    if goal_payload['status'] in {GoalStatus.achieved.value, GoalStatus.abandoned.value}:
                        raise WorkstreamConflictError('ended goal cannot receive new work')
                    if goal_generation == 0:
                        legacy_goal_ref = goal_ref
                if isinstance(existing_workstream_id, str) and existing_workstream_id:
                    existing_workstream = _workstream_ref(uid, existing_workstream_id, firestore_client=client).get(
                        transaction=write_transaction
                    )
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
                    if legacy_goal_ref is not None:
                        self._transaction_write(
                            write_transaction,
                            'update',
                            legacy_goal_ref,
                            {'account_generation': account_generation, 'updated_at': now},
                        )
                    if task_generation == 0:
                        self._task_write(
                            write_transaction,
                            'update',
                            task_ref,
                            {'account_generation': account_generation, 'updated_at': now},
                        )
                        task_written = True
                    if workstream_generation == 0:
                        self._transaction_write(
                            write_transaction,
                            'update',
                            _workstream_ref(uid, workstream_id, firestore_client=client),
                            {'account_generation': account_generation, 'updated_at': now},
                        )
                else:
                    workstream_id = _stable_id('workstream', uid, account_generation, 'task', request.task_id)
                    task_id = request.task_id
                    workstream_ref = _workstream_ref(uid, workstream_id, firestore_client=client)
                    workstream_snapshot = workstream_ref.get(transaction=write_transaction)
                    if workstream_snapshot.exists:
                        existing = _workstream_from_snapshot(workstream_snapshot)
                        if existing.goal_id != goal_id:
                            raise WorkstreamConflictError('deterministic workstream goal collision')
                    if legacy_goal_ref is not None:
                        self._transaction_write(
                            write_transaction,
                            'update',
                            legacy_goal_ref,
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
                        self._transaction_write(
                            write_transaction,
                            'create',
                            workstream_ref,
                            _workstream_storage(
                                workstream_id=workstream_id,
                                title=request.title or str(task.get('description') or 'Task'),
                                objective=request.objective or str(task.get('description') or 'Advance this task'),
                                goal_id=goal_id,
                                now=now,
                                account_generation=account_generation,
                            ),
                        )
                        self._transaction_write(
                            write_transaction,
                            'create',
                            workstream_ref.collection(EVENTS_COLLECTION).document(event_id),
                            event_data,
                        )
                        newly_created = True
                    self._task_write(
                        write_transaction,
                        'update',
                        task_ref,
                        {'workstream_id': workstream_id, 'account_generation': account_generation, 'updated_at': now},
                    )
                    task_written = True
            else:
                goal_id = request.goal_id
                _assert_goal_exists(
                    uid,
                    goal_id,
                    account_generation=account_generation,
                    transaction=write_transaction,
                    firestore_client=client,
                )
                workstream_id = _stable_id('workstream', uid, 'goal-intent', receipt_id)
                task_id = _stable_id('task', uid, 'goal-intent', receipt_id)
                workstream_ref = _workstream_ref(uid, workstream_id, firestore_client=client)
                task_ref = _task_ref(uid, task_id, firestore_client=client)
                if (
                    workstream_ref.get(transaction=write_transaction).exists
                    or task_ref.get(transaction=write_transaction).exists
                ):
                    raise WorkstreamConflictError('deterministic goal-origin intent id collision')
                event_id, event_data = _initial_event_storage(
                    uid=uid,
                    workstream_id=workstream_id,
                    source_key=f'goal:{goal_id}:{receipt_id}',
                    summary='Work initiated from a goal by the user',
                    evidence_refs=[],
                    now=now,
                )
                self._transaction_write(
                    write_transaction,
                    'create',
                    workstream_ref,
                    _workstream_storage(
                        workstream_id=workstream_id,
                        title=request.title,
                        objective=request.objective,
                        goal_id=goal_id,
                        now=now,
                        account_generation=account_generation,
                    ),
                )
                self._transaction_write(
                    write_transaction,
                    'create',
                    workstream_ref.collection(EVENTS_COLLECTION).document(event_id),
                    event_data,
                )
                self._task_write(
                    write_transaction,
                    'create',
                    task_ref,
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
                task_written = True
            receipt = WorkIntentReceipt(
                receipt_id=receipt_id,
                workstream_id=workstream_id,
                task_id=task_id,
                goal_id=goal_id,
                newly_created=newly_created,
                created_at=now,
            )
            self._transaction_write(
                write_transaction,
                'create',
                receipt_ref,
                {**receipt.model_dump(mode='python'), 'request_hash': request_hash},
            )
            return (receipt, task_written)

        receipt, task_written = self._apply_transaction(apply, transaction, task_writes=True)
        if task_written:
            self._post_commit(lambda: bump_action_items_list_version(uid))
        return receipt

    def import_links_documents(
        self,
        request: TaskGoalLinkImportRequest,
        *,
        idempotency_key: str,
        account_generation: int,
        firestore_client: Any = None,
    ) -> TaskGoalLinkImportReport:
        uid = self.space_id
        client = self.client
        request_payload = request.model_dump(mode='json')
        operation = 'task-goal-link-import'
        request_hash = _mutation_hash(request_payload)
        receipt_ref = _mutation_receipt_ref(
            uid,
            operation=operation,
            idempotency_key=idempotency_key,
            account_generation=account_generation,
            firestore_client=client,
        )
        reservation_transaction = client.transaction()
        reservation_now = datetime.now(timezone.utc)

        @firestore.transactional
        def reserve(write_transaction):
            control_snapshot = _control_ref(uid, firestore_client=client).get(transaction=write_transaction)
            _validate_control(control_snapshot, uid=uid, account_generation=account_generation)
            receipt_snapshot = receipt_ref.get(transaction=write_transaction)
            if receipt_snapshot.exists:
                receipt = _snapshot_dict(receipt_snapshot)
                if receipt.get('request_hash') != request_hash:
                    raise WorkstreamConflictError('idempotency key was reused with different content')
                result = receipt.get('result')
                return cast(Optional[dict[str, Any]], result if isinstance(result, dict) else None)
            self._transaction_write(
                write_transaction,
                'create',
                receipt_ref,
                {
                    'request_hash': request_hash,
                    'status': 'processing',
                    'outcomes': {},
                    'created_at': reservation_now,
                    'updated_at': reservation_now,
                },
            )
            return None

        stored_result = self._apply_transaction(reserve, reservation_transaction)
        if stored_result is not None:
            return TaskGoalLinkImportReport.model_validate(stored_result)
        tasks_written = False
        for index, link in enumerate(request.links):
            task_ref = _task_ref(uid, link.task_id, firestore_client=client)
            goal_ref = goals_db.goal_document_ref(uid, link.goal_id, firestore_client=client)
            transaction = client.transaction()

            @firestore.transactional
            def apply(write_transaction):
                nonlocal tasks_written
                control_snapshot = _control_ref(uid, firestore_client=client).get(transaction=write_transaction)
                _validate_control(control_snapshot, uid=uid, account_generation=account_generation)
                receipt_snapshot = receipt_ref.get(transaction=write_transaction)
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
                task_snapshot = task_ref.get(transaction=write_transaction)
                goal_snapshot = goal_ref.get(transaction=write_transaction)
                if not task_snapshot.exists or not goal_snapshot.exists:
                    outcome = 'failed'
                else:
                    task = _snapshot_dict(task_snapshot)
                    workstream_id = task.get('workstream_id')
                    relationship_valid = True
                    if isinstance(workstream_id, str) and workstream_id:
                        workstream_snapshot = _workstream_ref(uid, workstream_id, firestore_client=client).get(
                            transaction=write_transaction
                        )
                        relationship_valid = bool(
                            workstream_snapshot.exists
                            and _snapshot_dict(workstream_snapshot).get('goal_id') == link.goal_id
                            and (_snapshot_dict(workstream_snapshot).get('account_generation', 0) == account_generation)
                        )
                    goal_generation_matches = (
                        _snapshot_dict(goal_snapshot).get('account_generation', 0) == account_generation
                    )
                    current_goal_id = task.get('goal_id')
                    task_generation = int(task.get('account_generation', 0))
                    if (
                        task_generation not in {0, account_generation}
                        or not goal_generation_matches
                        or (not relationship_valid)
                        or (current_goal_id not in {None, link.goal_id})
                    ):
                        outcome = 'failed'
                    elif current_goal_id == link.goal_id:
                        outcome = 'unchanged'
                        if task_generation == 0:
                            self._task_write(
                                write_transaction,
                                'update',
                                task_ref,
                                {'account_generation': account_generation, 'updated_at': datetime.now(timezone.utc)},
                            )
                            tasks_written = True
                    else:
                        outcome = 'imported'
                        self._task_write(
                            write_transaction,
                            'update',
                            task_ref,
                            {
                                'goal_id': link.goal_id,
                                'account_generation': account_generation,
                                'updated_at': datetime.now(timezone.utc),
                            },
                        )
                        tasks_written = True
                outcomes[outcome_key] = outcome
                self._transaction_write(
                    write_transaction,
                    'update',
                    receipt_ref,
                    {'outcomes': outcomes, 'updated_at': datetime.now(timezone.utc)},
                )
                return outcome

            self._apply_transaction(apply, transaction, task_writes=True)
        if tasks_written:
            self._post_commit(lambda: bump_action_items_list_version(uid))
        completion_transaction = client.transaction()
        now = datetime.now(timezone.utc)

        @firestore.transactional
        def complete(write_transaction):
            control_snapshot = _control_ref(uid, firestore_client=client).get(transaction=write_transaction)
            _validate_control(control_snapshot, uid=uid, account_generation=account_generation)
            receipt_snapshot = receipt_ref.get(transaction=write_transaction)
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
            self._transaction_write(
                write_transaction,
                'update',
                receipt_ref,
                {
                    'status': 'complete',
                    'result': report.model_dump(mode='python'),
                    'updated_at': now,
                    'completed_at': now,
                },
            )
            return report

        return self._apply_transaction(complete, completion_transaction)

    def get(self, workstream_id: str) -> WorkstreamEntity | None:
        snapshot = self._read(_workstream_ref(self.space_id, workstream_id, firestore_client=self.client))
        return (
            WorkstreamEntity.model_construct(
                **cast(dict[str, Any], deepcopy({**_snapshot_dict(snapshot), 'id': workstream_id}))
            )
            if snapshot.exists
            else None
        )

    def create(self, draft: WorkstreamCreate, *, mutation_id: str | None = None) -> WorkstreamEntity:
        from database.folders import port_mutation_digest, read_port_mutation, write_port_mutation

        data = deepcopy(draft.data)
        wid = (
            data.get('workstream_id')
            or data.get('id')
            or _stable_id('workstream', self.space_id, mutation_id or uuid4().hex)
        )
        if self.transaction is None:

            @firestore.transactional
            def apply(transaction):
                return FirestoreWorkstreams(
                    self.space_id, firestore_client=self.client, transaction=transaction
                ).create(draft, mutation_id=mutation_id)

            return apply(self.client.transaction())
        owner = _user_ref(self.space_id, firestore_client=self.client)
        digest = port_mutation_digest('workstreams', 'create', data)
        prior = read_port_mutation(owner, self.transaction, mutation_id, digest)
        if prior is not None:
            return WorkstreamEntity.model_construct(**deepcopy(prior['result']))
        control = self._read(_control_ref(self.space_id, firestore_client=self.client))
        generation = _snapshot_dict(control).get('account_generation', 0) if control.exists else 0
        _assert_goal_exists(
            self.space_id,
            data.get('goal_id'),
            account_generation=generation,
            transaction=self.transaction,
            firestore_client=self.client,
        )
        now = datetime.now(timezone.utc)
        payload = {
            **_workstream_storage(
                workstream_id=wid,
                title=data.get('title', 'Work'),
                objective=data.get('objective', data.get('title', 'Work')),
                goal_id=data.get('goal_id'),
                now=now,
                account_generation=generation,
                latest_event_sequence=0,
            ),
            **data,
            'workstream_id': wid,
        }
        payload.pop('id', None)
        payload.pop('revision', None)
        self.transaction.create(_workstream_ref(self.space_id, wid, firestore_client=self.client), payload)
        write_port_mutation(owner, self.transaction, mutation_id, digest, 'workstreams', wid, result=payload)
        return WorkstreamEntity.model_construct(**cast(dict[str, Any], payload))

    def list_open(self, *, limit: int = 500, account_generation: int | None = None) -> list[WorkstreamEntity]:
        return [
            WorkstreamEntity.model_construct(**row.model_dump(mode='python'))
            for row in list_open_workstreams(
                self.space_id, limit=limit, account_generation=account_generation, firestore_client=self.client
            )
        ]

    def list_for_goal(
        self, goal_id: str, *, include_archived: bool = False, limit: int = 100
    ) -> list[WorkstreamEntity]:
        return [
            WorkstreamEntity.model_construct(**row.model_dump(mode='python'))
            for row in list_workstreams_for_goal(
                self.space_id, goal_id, include_archived=include_archived, limit=limit, firestore_client=self.client
            )
        ]

    def update(
        self, workstream_id: str, patch: PortWorkstreamUpdate, *, idempotency_key: str, account_generation: int
    ) -> WorkstreamEntity:
        result = self.update_document(
            workstream_id,
            parse_payload_strict(
                WorkstreamUpdate,
                patch.data,
                document_path=f'users/{self.space_id}/workstreams/{workstream_id}/<update>',
            ),
            idempotency_key=idempotency_key,
            account_generation=account_generation,
        )
        return WorkstreamEntity.model_construct(**result.model_dump(mode='python'))

    def append_event(
        self, workstream_id: str, event: dict[str, Any], *, idempotency_key: str, account_generation: int
    ) -> WorkstreamEventEntity:
        result = self.append_event_document(
            workstream_id,
            parse_payload_strict(
                WorkstreamEventCreate,
                event,
                document_path=f'users/{self.space_id}/workstreams/{workstream_id}/events/<input>',
            ),
            idempotency_key=idempotency_key,
            account_generation=account_generation,
        )
        return WorkstreamEventEntity.model_construct(**result.model_dump(mode='python'))

    def list_events(
        self, workstream_id: str, *, after_sequence: int = 0, limit: int = 100
    ) -> list[WorkstreamEventEntity]:
        return [
            WorkstreamEventEntity.model_construct(**row.model_dump(mode='python'))
            for row in list_workstream_events(
                self.space_id, workstream_id, after_sequence=after_sequence, limit=limit, firestore_client=self.client
            )
        ]

    def create_artifact_descriptor(
        self, workstream_id: str, proposal: dict[str, Any], *, idempotency_key: str, account_generation: int
    ) -> ArtifactDescriptorEntity:
        result = self.create_artifact_document(
            workstream_id,
            parse_payload_strict(
                ArtifactDescriptorCreate,
                proposal,
                document_path=f'users/{self.space_id}/workstreams/{workstream_id}/artifact_refs/<input>',
            ),
            idempotency_key=idempotency_key,
            account_generation=account_generation,
        )
        return ArtifactDescriptorEntity.model_construct(**result.model_dump(mode='python'))

    def transition_artifact_status(
        self,
        workstream_id: str,
        artifact_id: str,
        request: dict[str, Any],
        *,
        idempotency_key: str,
        account_generation: int,
    ) -> ArtifactDescriptorEntity:
        result = self.transition_artifact_document(
            workstream_id,
            artifact_id,
            parse_payload_strict(
                ArtifactStatusTransitionRequest,
                request,
                document_path=f'users/{self.space_id}/workstreams/{workstream_id}/artifact_refs/<transition>',
            ),
            idempotency_key=idempotency_key,
            account_generation=account_generation,
        )
        return ArtifactDescriptorEntity.model_construct(**result.model_dump(mode='python'))

    def list_artifact_descriptors(self, workstream_id: str, *, limit: int = 100) -> list[ArtifactDescriptorEntity]:
        return [
            ArtifactDescriptorEntity.model_construct(**row.model_dump(mode='python'))
            for row in list_artifact_descriptors(
                self.space_id, workstream_id, limit=limit, firestore_client=self.client
            )
        ]

    def upsert_continuation_checkpoint(
        self, workstream_id: str, checkpoint: dict[str, Any], *, idempotency_key: str, account_generation: int
    ) -> ContinuationCheckpointEntity:
        result = self.upsert_checkpoint_document(
            workstream_id,
            parse_payload_strict(
                ContinuationCheckpointUpsert,
                checkpoint,
                document_path=f'users/{self.space_id}/workstreams/{workstream_id}/continuation_checkpoints/<input>',
            ),
            idempotency_key=idempotency_key,
            account_generation=account_generation,
        )
        return ContinuationCheckpointEntity.model_construct(**result.model_dump(mode='python'))

    def list_continuation_checkpoints(self, workstream_id: str) -> list[ContinuationCheckpointEntity]:
        return [
            ContinuationCheckpointEntity.model_construct(**row.model_dump(mode='python'))
            for row in list_continuation_checkpoints(self.space_id, workstream_id, firestore_client=self.client)
        ]

    def resolve_candidate(self, candidate: dict[str, Any], account_generation: int) -> dict[str, Any]:
        return self.resolve_candidate_document(
            parse_payload_strict(CandidateRecord, candidate, document_path=f'users/{self.space_id}/candidates/<input>'),
            account_generation,
        ).model_dump(mode='python')

    def resolve_work_intent(
        self, request: dict[str, Any], *, idempotency_key: str, account_generation: int
    ) -> dict[str, Any]:
        model = TaskOriginWorkIntent if request.get('origin') == 'task' else GoalOriginWorkIntent
        return self.resolve_intent_document(
            parse_payload_strict(model, request, document_path=f'users/{self.space_id}/work_intent_receipts/<input>'),
            idempotency_key=idempotency_key,
            account_generation=account_generation,
        ).model_dump(mode='python')

    def import_task_goal_links(
        self, request: dict[str, Any], *, idempotency_key: str, account_generation: int
    ) -> dict[str, Any]:
        if self.transaction is not None:
            return self._import_links_atomic(
                parse_payload_strict(
                    TaskGoalLinkImportRequest, request, document_path=f'users/{self.space_id}/workstreams/<import>'
                ),
                idempotency_key,
                account_generation,
            )
        return self.import_links_documents(
            parse_payload_strict(
                TaskGoalLinkImportRequest, request, document_path=f'users/{self.space_id}/workstreams/<import>'
            ),
            idempotency_key=idempotency_key,
            account_generation=account_generation,
        ).model_dump(mode='python')

    def get_goal_detail(self, goal_id: str) -> dict[str, Any]:
        return get_goal_detail(self.space_id, goal_id, firestore_client=self.client).model_dump(mode='python')

    def get_workstream_detail(self, workstream_id: str) -> dict[str, Any]:
        return get_workstream_detail(self.space_id, workstream_id, firestore_client=self.client).model_dump(
            mode='python'
        )

    def purge(self, space_id: str) -> int:
        if space_id != self.space_id:
            raise ValueError('purge must belong to this space')
        owner = _user_ref(space_id, firestore_client=self.client)
        count = 0
        for collection in (
            WORKSTREAMS_COLLECTION,
            WORK_INTENT_RECEIPTS_COLLECTION,
            MUTATION_RECEIPTS_COLLECTION,
            'port_mutations',
        ):
            for doc in owner.collection(collection).stream():
                data = doc.to_dict() or {}
                if collection == 'port_mutations' and data.get('entity') != 'workstreams':
                    continue
                if collection == MUTATION_RECEIPTS_COLLECTION and 'desired_outcome' in data.get('result', {}):
                    continue
                count += 1
                self.client.recursive_delete(doc.reference)
        return count

    def _task_write(self, transaction, operation, ref, payload):
        repo = action_items_db.FirestoreActionItems(
            self.space_id, firestore_client=self.client, transaction=transaction
        )
        repo.commit_context = self.commit_context
        return repo.stage_write(operation, ref.id, payload)

    def _import_links_atomic(self, request, idempotency_key, account_generation):
        """UoW variant reads the entire bounded import before staging any row.

        The module's resumable, per-link transaction policy remains unchanged.
        """
        receipt_ref, prior, request_hash = _begin_mutation(
            self.transaction,
            uid=self.space_id,
            operation='task-goal-link-import-atomic',
            idempotency_key=idempotency_key,
            account_generation=account_generation,
            request_payload=request.model_dump(mode='json'),
            firestore_client=self.client,
        )
        if prior is not None:
            return prior
        tasks = action_items_db.FirestoreActionItems(
            self.space_id, firestore_client=self.client, transaction=self.transaction
        )
        tasks.commit_context = self.commit_context
        planned = []
        failed = []
        unchanged = imported = 0
        for link in request.links:
            task = tasks.get(link.task_id)
            goal = goals_db.FirestoreGoals(
                self.space_id, firestore_client=self.client, transaction=self.transaction
            ).get(link.goal_id)
            valid = (
                task is not None
                and goal is not None
                and task.account_generation in (None, 0, account_generation)
                and goal.account_generation == account_generation
                and task.goal_id in (None, link.goal_id)
            )
            if valid and task is not None and task.workstream_id:
                workstream = self.get(task.workstream_id)
                valid = (
                    workstream is not None
                    and workstream.goal_id == link.goal_id
                    and workstream.account_generation == account_generation
                )
            if not valid:
                failed.append(link.task_id)
            elif task is not None and task.goal_id == link.goal_id:
                unchanged += 1
                if not task.account_generation:
                    planned.append((link.task_id, {'account_generation': account_generation}))
            else:
                imported += 1
                planned.append((link.task_id, {'goal_id': link.goal_id, 'account_generation': account_generation}))
        now = datetime.now(timezone.utc)
        for task_id, patch in planned:
            tasks.stage_write('update', task_id, {**patch, 'updated_at': now})
        report = {'imported': imported, 'unchanged': unchanged, 'failed': len(failed), 'failure_task_ids': failed}
        _finish_mutation(self.transaction, receipt_ref, request_hash=request_hash, result=report, now=now)
        if planned:
            self._post_commit(lambda: bump_action_items_list_version(self.space_id))
        return report
