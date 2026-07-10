"""Persistence for attributable task feedback and derived attention projections."""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional, cast

from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from database._client import get_firestore_client
from models.task_recommendation import (
    DecisionRecord,
    FeedbackCreate,
    FeedbackRecord,
    InterventionCreate,
    InterventionRecord,
    NormalizedContextSnapshot,
    OpenLoopSnapshot,
    OutcomeCreate,
    OutcomeRecord,
    SnapshotReceipt,
    WhatMattersNowProjection,
)

FEEDBACK_COLLECTION = 'task_feedback'
OUTCOMES_COLLECTION = 'task_outcomes'
INTERVENTIONS_COLLECTION = 'task_interventions'
ATTENTION_OVERRIDES_COLLECTION = 'task_attention_overrides'
PROJECTIONS_COLLECTION = 'task_recommendation_projections'
DECISIONS_COLLECTION = 'task_recommendation_decisions'
CONTEXT_SNAPSHOTS_COLLECTION = 'task_context_snapshots'
OPEN_LOOP_SNAPSHOTS_COLLECTION = 'task_open_loop_snapshots'
MAX_DECISION_HISTORY_PER_DEVICE = 24


class TaskRecommendationStoreError(RuntimeError):
    pass


class IdempotencyConflictError(TaskRecommendationStoreError):
    pass


class InterventionNotFoundError(TaskRecommendationStoreError):
    pass


class AttributionChainNotFoundError(TaskRecommendationStoreError):
    pass


class StaleSnapshotError(TaskRecommendationStoreError):
    pass


def _get_db(firestore_client: Any = None) -> Any:
    return firestore_client or get_firestore_client()


def _user_ref(uid: str, *, firestore_client: Any = None):
    return _get_db(firestore_client).collection('users').document(uid)


def _snapshot_dict(snapshot: Any) -> dict[str, Any]:
    payload = snapshot.to_dict()
    return cast(dict[str, Any], payload) if isinstance(payload, dict) else {}


def _stable_id(prefix: str, *parts: object) -> str:
    raw = '\x1f'.join(str(part) for part in parts).encode('utf-8')
    return f'{prefix}_{hashlib.sha256(raw).hexdigest()[:32]}'


def _request_hash(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()


def get_intervention(uid: str, intervention_id: str, *, firestore_client: Any = None) -> Optional[dict[str, Any]]:
    snapshot = (
        _user_ref(uid, firestore_client=firestore_client)
        .collection(INTERVENTIONS_COLLECTION)
        .document(intervention_id)
        .get()
    )
    return _snapshot_dict(snapshot) if snapshot.exists else None


def create_intervention(
    uid: str,
    request: InterventionCreate,
    *,
    idempotency_key: str,
    now: datetime,
    firestore_client: Any = None,
) -> tuple[InterventionRecord, bool]:
    user_ref = _user_ref(uid, firestore_client=firestore_client)
    intervention_id = _stable_id('intervention', uid, request.surface.value, idempotency_key)
    record = InterventionRecord(
        **request.model_dump(mode='python'),
        intervention_id=intervention_id,
        attribution_chain_id=_stable_id('attr', uid, intervention_id),
        created_at=now,
    )
    payload = record.model_dump(mode='python')
    payload['_request_hash'] = _request_hash(request.model_dump(mode='json'))
    ref = user_ref.collection(INTERVENTIONS_COLLECTION).document(intervention_id)
    try:
        ref.create(payload)
    except AlreadyExists:
        stored = _snapshot_dict(ref.get())
        if stored.get('_request_hash') != payload['_request_hash']:
            raise IdempotencyConflictError('idempotency key was used for a different intervention')
        stored.pop('_request_hash', None)
        return InterventionRecord.model_validate(stored), False
    return record, True


def save_projection(
    uid: str,
    *,
    device_scope: str,
    projection: WhatMattersNowProjection,
    decisions: list[DecisionRecord],
    firestore_client: Any = None,
) -> WhatMattersNowProjection:
    client = _get_db(firestore_client)
    user_ref = _user_ref(uid, firestore_client=client)
    projection_ref = user_ref.collection(PROJECTIONS_COLLECTION).document(device_scope)
    decisions_collection = user_ref.collection(DECISIONS_COLLECTION)
    decision_ref = decisions_collection.document(_stable_id('decision', device_scope, projection.evaluation_id))
    transaction = client.transaction()

    @firestore.transactional
    def publish(write_transaction: Any) -> tuple[WhatMattersNowProjection, bool]:
        current_snapshot = projection_ref.get(transaction=write_transaction)
        if current_snapshot.exists:
            current = WhatMattersNowProjection.model_validate(_snapshot_dict(current_snapshot))
            if current.generated_at > projection.generated_at or (
                current.material_version == projection.material_version and current.expires_at > projection.generated_at
            ):
                return current, False
        intervention_writes = []
        for recommendation in projection.recommendations:
            intervention_payload = recommendation.model_dump(mode='python')
            intervention_ref = user_ref.collection(INTERVENTIONS_COLLECTION).document(recommendation.intervention_id)
            existing_intervention = intervention_ref.get(transaction=write_transaction)
            existing_created_at = (
                _snapshot_dict(existing_intervention).get('created_at') if existing_intervention.exists else None
            )
            intervention_payload.update(
                {
                    'evaluation_id': projection.evaluation_id,
                    'attribution_chain_id': _stable_id('attr', uid, recommendation.intervention_id),
                    'surface': 'what_matters_now',
                    'feedback_subject_kind': recommendation.feedback_subject_kind.value,
                    'feedback_subject_id': recommendation.feedback_subject_id,
                    'created_at': existing_created_at or projection.generated_at,
                }
            )
            intervention_writes.append((intervention_ref, intervention_payload))
        write_transaction.set(projection_ref, projection.model_dump(mode='python'))
        write_transaction.set(
            decision_ref,
            {
                'device_scope': device_scope,
                'evaluation_id': projection.evaluation_id,
                'evaluated_at': projection.generated_at,
                'expires_at': projection.expires_at,
                'projection': projection.model_dump(mode='python'),
                'decisions': [decision.model_dump(mode='python') for decision in decisions],
            },
        )
        for intervention_ref, intervention_payload in intervention_writes:
            write_transaction.set(intervention_ref, intervention_payload)
        return projection, True

    published_projection, did_publish = publish(transaction)
    if not did_publish:
        return published_projection

    batch = client.batch()
    history = []
    for snapshot in decisions_collection.where('device_scope', '==', device_scope).stream():
        payload = _snapshot_dict(snapshot)
        if payload.get('evaluation_id') == projection.evaluation_id:
            continue
        history.append((payload.get('evaluated_at'), payload.get('expires_at'), snapshot.reference))
    history.sort(key=lambda item: item[0] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    for index, (_, expires_at, ref) in enumerate(history):
        if expires_at is None or expires_at <= projection.generated_at or index >= MAX_DECISION_HISTORY_PER_DEVICE - 1:
            batch.delete(ref)
    batch.commit()
    return published_projection


def get_projection(
    uid: str,
    *,
    device_scope: str,
    now: datetime,
    include_expired: bool = False,
    firestore_client: Any = None,
) -> Optional[WhatMattersNowProjection]:
    snapshot = (
        _user_ref(uid, firestore_client=firestore_client)
        .collection(PROJECTIONS_COLLECTION)
        .document(device_scope)
        .get()
    )
    if not snapshot.exists:
        return None
    projection = WhatMattersNowProjection.model_validate(_snapshot_dict(snapshot))
    return projection if include_expired or projection.expires_at > now else None


def get_decisions(
    uid: str,
    evaluation_id: str,
    *,
    device_scope: str,
    firestore_client: Any = None,
) -> list[DecisionRecord]:
    snapshot = (
        _user_ref(uid, firestore_client=firestore_client)
        .collection(DECISIONS_COLLECTION)
        .document(_stable_id('decision', device_scope, evaluation_id))
        .get()
    )
    if not snapshot.exists:
        return []
    payload = _snapshot_dict(snapshot)
    if payload.get('evaluation_id') != evaluation_id:
        return []
    raw_records = payload.get('decisions')
    if not isinstance(raw_records, list):
        return []
    records = [DecisionRecord.model_validate(record) for record in raw_records]
    records.sort(key=lambda record: record.subject_id)
    return records


def get_evaluation_projection(
    uid: str,
    evaluation_id: str,
    *,
    device_scope: str,
    now: datetime,
    firestore_client: Any = None,
) -> Optional[WhatMattersNowProjection]:
    snapshot = (
        _user_ref(uid, firestore_client=firestore_client)
        .collection(DECISIONS_COLLECTION)
        .document(_stable_id('decision', device_scope, evaluation_id))
        .get()
    )
    if not snapshot.exists:
        return None
    payload = _snapshot_dict(snapshot)
    raw_projection = payload.get('projection')
    if not isinstance(raw_projection, dict):
        return None
    projection = WhatMattersNowProjection.model_validate(raw_projection)
    if projection.evaluation_id != evaluation_id or projection.expires_at <= now:
        return None
    return projection


def create_feedback(
    uid: str,
    request: FeedbackCreate,
    *,
    idempotency_key: str,
    now: datetime,
    override_expires_at: Optional[datetime],
    firestore_client: Any = None,
) -> tuple[FeedbackRecord, bool]:
    client = _get_db(firestore_client)
    user_ref = _user_ref(uid, firestore_client=client)
    intervention: Optional[dict[str, Any]] = None
    if request.intervention_id is not None:
        intervention = get_intervention(uid, request.intervention_id, firestore_client=client)
        if intervention is None:
            raise InterventionNotFoundError(request.intervention_id)
        intervention_subject_kind = intervention.get('feedback_subject_kind', intervention.get('subject_kind'))
        intervention_subject_id = intervention.get('feedback_subject_id', intervention.get('subject_id'))
        if intervention_subject_kind != request.subject_kind.value or intervention_subject_id != request.subject_id:
            raise IdempotencyConflictError('feedback subject does not match intervention')

    feedback_id = _stable_id('feedback', uid, idempotency_key)
    attribution_chain_id = (
        str(intervention['attribution_chain_id'])
        if intervention is not None
        else _stable_id('attr', uid, request.subject_kind.value, request.subject_id)
    )
    dedupe_key = str(intervention['dedupe_key']) if intervention is not None else None
    proposed_completion = request.reason is not None and request.reason.value == 'already_handled'
    record = FeedbackRecord(
        **request.model_dump(mode='python'),
        feedback_id=feedback_id,
        attribution_chain_id=attribution_chain_id,
        created_at=now,
        dedupe_key=dedupe_key,
        proposed_completion=proposed_completion,
    )
    payload = record.model_dump(mode='python')
    payload['_request_hash'] = _request_hash(request.model_dump(mode='json'))
    ref = user_ref.collection(FEEDBACK_COLLECTION).document(feedback_id)
    newly_recorded = True
    try:
        ref.create(payload)
    except AlreadyExists:
        stored = _snapshot_dict(ref.get())
        if stored.get('_request_hash') != payload['_request_hash']:
            raise IdempotencyConflictError('idempotency key was used for different feedback')
        stored.pop('_request_hash', None)
        record = FeedbackRecord.model_validate(stored)
        newly_recorded = False

    if override_expires_at is not None and dedupe_key is not None:
        override_id = _stable_id('override', uid, dedupe_key)
        user_ref.collection(ATTENTION_OVERRIDES_COLLECTION).document(override_id).set(
            {
                'override_id': override_id,
                'dedupe_key': dedupe_key,
                'intervention_id': request.intervention_id,
                'feedback_id': feedback_id,
                'action': request.action.value,
                'reason': request.reason.value if request.reason is not None else None,
                'created_at': now,
                'expires_at': override_expires_at,
            }
        )
    return record, newly_recorded


def list_active_override_dedupe_keys(
    uid: str,
    *,
    now: datetime,
    firestore_client: Any = None,
) -> set[str]:
    query = (
        _user_ref(uid, firestore_client=firestore_client)
        .collection(ATTENTION_OVERRIDES_COLLECTION)
        .where('expires_at', '>', now)
    )
    return {
        str(payload['dedupe_key'])
        for snapshot in query.stream()
        if (payload := _snapshot_dict(snapshot)).get('dedupe_key')
    }


def link_feedback_completion_candidate(
    uid: str,
    feedback_id: str,
    candidate_id: str,
    *,
    firestore_client: Any = None,
) -> None:
    (
        _user_ref(uid, firestore_client=firestore_client)
        .collection(FEEDBACK_COLLECTION)
        .document(feedback_id)
        .update({'proposed_completion_candidate_id': candidate_id})
    )


def _first_chain_record(user_ref: Any, collection_name: str, attribution_chain_id: str) -> Optional[dict[str, Any]]:
    matches = list(
        user_ref.collection(collection_name)
        .where(filter=FieldFilter('attribution_chain_id', '==', attribution_chain_id))
        .limit(1)
        .stream()
    )
    return _snapshot_dict(matches[0]) if matches else None


def _outcome_matches_chain(user_ref: Any, request: OutcomeCreate, source: dict[str, Any]) -> bool:
    raw_source_kind = source.get('feedback_subject_kind') or source.get('subject_kind') or ''
    source_kind = str(getattr(raw_source_kind, 'value', raw_source_kind))
    source_id = str(source.get('feedback_subject_id') or source.get('subject_id') or '')
    allowed: set[tuple[str, str]] = {(source_kind, source_id)}
    workstream_ids: set[str] = set()

    if source_kind == 'candidate':
        candidate_snapshot = user_ref.collection('candidates').document(source_id).get()
        if candidate_snapshot.exists:
            candidate = _snapshot_dict(candidate_snapshot)
            result_task_id = candidate.get('result_task_id')
            result_workstream_id = candidate.get('result_workstream_id')
            if isinstance(result_task_id, str):
                allowed.add(('task', result_task_id))
                task_snapshot = user_ref.collection('action_items').document(result_task_id).get()
                if task_snapshot.exists:
                    task_workstream_id = _snapshot_dict(task_snapshot).get('workstream_id')
                    if isinstance(task_workstream_id, str):
                        workstream_ids.add(task_workstream_id)
            if isinstance(result_workstream_id, str):
                workstream_ids.add(result_workstream_id)
    elif source_kind == 'task':
        task_snapshot = user_ref.collection('action_items').document(source_id).get()
        if task_snapshot.exists:
            workstream_id = _snapshot_dict(task_snapshot).get('workstream_id')
            if isinstance(workstream_id, str):
                workstream_ids.add(workstream_id)
    elif source_kind == 'workstream':
        workstream_ids.add(source_id)

    allowed.update(('workstream', workstream_id) for workstream_id in workstream_ids)
    if request.subject_kind.value == 'artifact':
        for workstream_id in workstream_ids:
            artifact = (
                user_ref.collection('workstreams')
                .document(workstream_id)
                .collection('artifact_refs')
                .document(request.subject_id)
                .get()
            )
            if artifact.exists:
                allowed.add(('artifact', request.subject_id))
                break

    expected_kind = {
        'task_completed': 'task',
        'artifact_approved': 'artifact',
        'artifact_delivered': 'artifact',
        'decision_resolved': 'decision',
        'agent_output_applied': 'workstream',
        'workstream_advanced': 'workstream',
    }[request.outcome_code.value]
    return request.subject_kind.value == expected_kind and (request.subject_kind.value, request.subject_id) in allowed


def create_outcome(
    uid: str,
    request: OutcomeCreate,
    *,
    idempotency_key: str,
    now: datetime,
    firestore_client: Any = None,
) -> tuple[OutcomeRecord, bool]:
    user_ref = _user_ref(uid, firestore_client=firestore_client)
    source = _first_chain_record(user_ref, INTERVENTIONS_COLLECTION, request.attribution_chain_id)
    if source is None:
        source = _first_chain_record(user_ref, FEEDBACK_COLLECTION, request.attribution_chain_id)
    if source is None:
        raise AttributionChainNotFoundError(request.attribution_chain_id)
    if not _outcome_matches_chain(user_ref, request, source):
        raise IdempotencyConflictError('outcome subject or code does not match attribution chain')
    outcome_id = _stable_id('outcome', uid, idempotency_key)
    record = OutcomeRecord(**request.model_dump(mode='python'), outcome_id=outcome_id, occurred_at=now)
    payload = record.model_dump(mode='python')
    payload['_request_hash'] = _request_hash(request.model_dump(mode='json'))
    ref = user_ref.collection(OUTCOMES_COLLECTION).document(outcome_id)
    try:
        ref.create(payload)
    except AlreadyExists:
        stored = _snapshot_dict(ref.get())
        if stored.get('_request_hash') != payload['_request_hash']:
            raise IdempotencyConflictError('idempotency key was used for a different outcome')
        stored.pop('_request_hash', None)
        return OutcomeRecord.model_validate(stored), False
    return record, True


def replace_context_snapshot(
    uid: str,
    snapshot: NormalizedContextSnapshot,
    *,
    firestore_client: Any = None,
) -> SnapshotReceipt:
    client = _get_db(firestore_client)
    ref = _user_ref(uid, firestore_client=client).collection(CONTEXT_SNAPSHOTS_COLLECTION).document(snapshot.device_id)
    transaction = client.transaction()

    @firestore.transactional
    def apply(write_transaction):
        stored_snapshot = ref.get(transaction=write_transaction)
        replaced = stored_snapshot.exists
        if replaced:
            stored = NormalizedContextSnapshot.model_validate(_snapshot_dict(stored_snapshot))
            if snapshot.generated_at < stored.generated_at:
                raise StaleSnapshotError('context snapshot is older than stored state')
            if snapshot.generated_at == stored.generated_at and snapshot != stored:
                raise IdempotencyConflictError('context snapshot timestamp was reused for different state')
        write_transaction.set(ref, snapshot.model_dump(mode='python'))
        return SnapshotReceipt(snapshot_id=snapshot.snapshot_id, replaced=replaced, expires_at=snapshot.expires_at)

    return apply(transaction)


def get_context_snapshot(
    uid: str,
    device_id: str,
    *,
    now: datetime,
    firestore_client: Any = None,
) -> Optional[NormalizedContextSnapshot]:
    ref = _user_ref(uid, firestore_client=firestore_client).collection(CONTEXT_SNAPSHOTS_COLLECTION).document(device_id)
    snapshot = ref.get()
    if not snapshot.exists:
        return None
    record = NormalizedContextSnapshot.model_validate(_snapshot_dict(snapshot))
    if record.expires_at <= now:
        ref.delete()
        return None
    return record


def replace_open_loop_snapshot(
    uid: str,
    snapshot: OpenLoopSnapshot,
    *,
    firestore_client: Any = None,
) -> SnapshotReceipt:
    client = _get_db(firestore_client)
    snapshot_key = _stable_id('loop-snapshot', snapshot.device_id, snapshot.runtime_id, snapshot.workstream_id)
    ref = _user_ref(uid, firestore_client=client).collection(OPEN_LOOP_SNAPSHOTS_COLLECTION).document(snapshot_key)
    transaction = client.transaction()

    @firestore.transactional
    def apply(write_transaction):
        stored_snapshot = ref.get(transaction=write_transaction)
        replaced = stored_snapshot.exists
        if replaced:
            stored = OpenLoopSnapshot.model_validate(_snapshot_dict(stored_snapshot))
            if snapshot.generated_at < stored.generated_at:
                raise StaleSnapshotError('open-loop snapshot is older than stored state')
            if snapshot.generated_at == stored.generated_at and snapshot != stored:
                raise IdempotencyConflictError('open-loop snapshot timestamp was reused for different state')
        write_transaction.set(ref, snapshot.model_dump(mode='python'))
        return SnapshotReceipt(snapshot_id=snapshot_key, replaced=replaced, expires_at=snapshot.expires_at)

    return apply(transaction)


def list_open_loop_snapshots(
    uid: str,
    *,
    device_id: str,
    now: datetime,
    firestore_client: Any = None,
) -> list[OpenLoopSnapshot]:
    collection = _user_ref(uid, firestore_client=firestore_client).collection(OPEN_LOOP_SNAPSHOTS_COLLECTION)
    query = collection.where('device_id', '==', device_id)
    records: list[OpenLoopSnapshot] = []
    for snapshot in query.stream():
        record = OpenLoopSnapshot.model_validate(_snapshot_dict(snapshot))
        if record.expires_at <= now:
            snapshot.reference.delete()
            continue
        records.append(record)
    records.sort(key=lambda record: (record.workstream_id, record.runtime_id))
    return records


def load_canonical_product_state(uid: str, *, firestore_client: Any = None) -> dict[str, list[dict[str, Any]]]:
    """Load bounded canonical state; device-local execution state is loaded separately."""

    user_ref = _user_ref(uid, firestore_client=firestore_client)

    def load_collection(name: str, limit: int) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for snapshot in user_ref.collection(name).limit(limit).stream():
            payload = _snapshot_dict(snapshot)
            payload.setdefault('id', snapshot.id)
            records.append(payload)
        return records

    tasks = load_collection('action_items', 500)
    candidates = load_collection('candidates', 200)
    goals = load_collection('goals', 100)
    workstreams = load_collection('workstreams', 200)
    artifacts: list[dict[str, Any]] = []
    workstream_events: list[dict[str, Any]] = []
    for workstream in workstreams:
        if len(artifacts) >= 200 and len(workstream_events) >= 200:
            break
        workstream_id = str(workstream.get('workstream_id') or workstream.get('id') or '')
        if not workstream_id:
            continue
        workstream_ref = user_ref.collection('workstreams').document(workstream_id)
        if len(artifacts) < 200:
            for snapshot in workstream_ref.collection('artifact_refs').limit(100).stream():
                payload = _snapshot_dict(snapshot)
                payload.setdefault('artifact_id', snapshot.id)
                payload.setdefault('workstream_id', workstream_id)
                artifacts.append(payload)
                if len(artifacts) >= 200:
                    break
        if len(workstream_events) < 200:
            for snapshot in (
                workstream_ref.collection('events')
                .order_by('sequence', direction=firestore.Query.DESCENDING)
                .limit(20)
                .stream()
            ):
                payload = _snapshot_dict(snapshot)
                payload.setdefault('event_id', snapshot.id)
                payload.setdefault('workstream_id', workstream_id)
                workstream_events.append(payload)
                if len(workstream_events) >= 200:
                    break
    return {
        'tasks': tasks,
        'candidates': candidates,
        'goals': goals,
        'workstreams': workstreams,
        'artifacts': artifacts,
        'workstream_events': workstream_events,
    }


__all__ = [
    'IdempotencyConflictError',
    'AttributionChainNotFoundError',
    'InterventionNotFoundError',
    'TaskRecommendationStoreError',
    'StaleSnapshotError',
    'create_feedback',
    'create_intervention',
    'create_outcome',
    'get_context_snapshot',
    'get_decisions',
    'get_evaluation_projection',
    'get_intervention',
    'get_projection',
    'list_active_override_dedupe_keys',
    'link_feedback_completion_candidate',
    'list_open_loop_snapshots',
    'load_canonical_product_state',
    'replace_context_snapshot',
    'replace_open_loop_snapshot',
    'save_projection',
]
