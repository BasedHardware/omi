"""Persistence for attributable task feedback and derived attention projections."""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional, cast

from config.canonical_memory_cohort import is_canonical_memory_user
from pydantic import ValidationError

from database.read_boundary import parse_snapshot_or_none, parse_snapshot_strict
from database.store import get_document_store
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
from models.task_intelligence import TaskWorkflowControl
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)

FEEDBACK_COLLECTION = 'task_feedback'
OUTCOMES_COLLECTION = 'task_outcomes'
INTERVENTIONS_COLLECTION = 'task_interventions'
ATTENTION_OVERRIDES_COLLECTION = 'task_attention_overrides'
PROJECTIONS_COLLECTION = 'task_recommendation_projections'
DECISIONS_COLLECTION = 'task_recommendation_decisions'
CONTEXT_SNAPSHOTS_COLLECTION = 'task_context_snapshots'
OPEN_LOOP_SNAPSHOTS_COLLECTION = 'task_open_loop_snapshots'
SNAPSHOT_RECEIPTS_COLLECTION = 'task_snapshot_receipts'
MAX_DECISION_HISTORY_PER_DEVICE = 24
TASK_INTELLIGENCE_CONTROL_COLLECTION = 'task_intelligence_control'
TASK_INTELLIGENCE_CONTROL_DOCUMENT = 'state'


def _store():
    return get_document_store()


def _collection_path(uid: str, collection: str) -> str:
    return f'users/{uid}/{collection}'


def _document_path(uid: str, collection: str, document_id: str) -> str:
    return f'users/{uid}/{collection}/{document_id}'


def _control_path(uid: str) -> str:
    return f'users/{uid}/{TASK_INTELLIGENCE_CONTROL_COLLECTION}/{TASK_INTELLIGENCE_CONTROL_DOCUMENT}'


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


class RecommendationGenerationMismatchError(TaskRecommendationStoreError):
    pass


def _validate_generation(
    snapshot: Any,
    *,
    uid: str,
    account_generation: int,
) -> None:
    if not is_canonical_memory_user(uid):
        raise RecommendationGenerationMismatchError('canonical task intelligence is not enabled')
    control = TaskWorkflowControl()
    if snapshot.exists:
        control = parse_snapshot_strict(TaskWorkflowControl, snapshot)
    if control.account_generation != account_generation:
        raise RecommendationGenerationMismatchError('account generation mismatch')


def _without_generation(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result.pop('account_generation', None)
    result.pop('_override_expires_at', None)
    result.pop('_receipt_id', None)
    return result


def _snapshot_dict(snapshot: Any) -> dict[str, Any]:
    payload = snapshot.to_dict()
    return cast(dict[str, Any], payload) if isinstance(payload, dict) else {}


def _record_malformed_embedded_payload(*, evaluation_id: str, error: ValidationError) -> None:
    error_types = [
        str(item.get('type', 'unknown')) for item in error.errors(include_input=False, include_url=False)[:5]
    ]
    logger.warning(
        'Malformed embedded stored payload evaluation_id=%s validation_types=%s', evaluation_id, error_types
    )
    record_fallback(
        component='firestore_read',
        from_mode='firestore_document',
        to_mode='skip_malformed_document',
        reason='malformed_doc',
        outcome='degraded',
        log=logger,
    )


def _stable_id(prefix: str, *parts: object) -> str:
    raw = '\x1f'.join(str(part) for part in parts).encode('utf-8')
    return f'{prefix}_{hashlib.sha256(raw).hexdigest()[:32]}'


def _request_hash(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()


def _cleanup_expired_snapshot_receipts(uid: str, *, now: datetime) -> None:
    receipts_path = _collection_path(uid, SNAPSHOT_RECEIPTS_COLLECTION)
    for doc in _store().query(receipts_path, filters=[('expires_at', '<=', now)], limit=50):
        _store().delete(doc.path)


def get_intervention(
    uid: str,
    intervention_id: str,
    *,
    account_generation: int = 0,
) -> Optional[dict[str, Any]]:
    snapshot = _store().get(_document_path(uid, INTERVENTIONS_COLLECTION, intervention_id))
    payload = _snapshot_dict(snapshot) if snapshot.exists else None
    return payload if payload is not None and payload.get('account_generation') == account_generation else None


def create_intervention(
    uid: str,
    request: InterventionCreate,
    *,
    idempotency_key: str,
    account_generation: int = 0,
    now: datetime,
) -> tuple[InterventionRecord, bool]:
    intervention_id = _stable_id('intervention', uid, account_generation, request.surface.value, idempotency_key)
    record = InterventionRecord(
        **request.model_dump(mode='python'),
        intervention_id=intervention_id,
        attribution_chain_id=_stable_id('attr', uid, account_generation, intervention_id),
        created_at=now,
    )
    payload = record.model_dump(mode='python')
    payload['_request_hash'] = _request_hash(request.model_dump(mode='json'))
    payload['account_generation'] = account_generation
    ref_path = _document_path(uid, INTERVENTIONS_COLLECTION, intervention_id)
    control_path = _control_path(uid)

    def apply(transaction):
        _validate_generation(transaction.get(control_path), uid=uid, account_generation=account_generation)
        existing = transaction.get(ref_path)
        if not existing.exists:
            transaction.set(ref_path, payload)
            return record, True
        stored = _snapshot_dict(existing)
        if stored.get('_request_hash') != payload['_request_hash']:
            raise IdempotencyConflictError('idempotency key was used for a different intervention')
        stored.pop('_request_hash', None)
        return (
            parse_snapshot_strict(
                InterventionRecord, existing, payload_from_snapshot=lambda _snapshot: _without_generation(stored)
            ),
            False,
        )

    return _store().run_transaction(apply)


def save_projection(
    uid: str,
    *,
    device_scope: str,
    projection: WhatMattersNowProjection,
    decisions: list[DecisionRecord],
    account_generation: int = 0,
) -> WhatMattersNowProjection:
    projection_path = _document_path(
        uid, PROJECTIONS_COLLECTION, _stable_id('projection', account_generation, device_scope)
    )
    decisions_path = _collection_path(uid, DECISIONS_COLLECTION)
    decision_path = f"{decisions_path}/{_stable_id('decision', account_generation, device_scope, projection.evaluation_id)}"
    control_path = _control_path(uid)

    def publish(transaction: Any) -> tuple[WhatMattersNowProjection, bool]:
        _validate_generation(transaction.get(control_path), uid=uid, account_generation=account_generation)
        current_snapshot = transaction.get(projection_path)
        if current_snapshot.exists:
            current = parse_snapshot_strict(
                WhatMattersNowProjection,
                current_snapshot,
                payload_from_snapshot=lambda _snapshot: _without_generation(_snapshot_dict(current_snapshot)),
            )
            if current.generated_at > projection.generated_at or (
                current.material_version == projection.material_version and current.expires_at > projection.generated_at
            ):
                return current, False
        intervention_writes = []
        for recommendation in projection.recommendations:
            intervention_payload = recommendation.model_dump(mode='python')
            intervention_path = _document_path(uid, INTERVENTIONS_COLLECTION, recommendation.intervention_id)
            existing_intervention = transaction.get(intervention_path)
            existing_created_at = (
                _snapshot_dict(existing_intervention).get('created_at') if existing_intervention.exists else None
            )
            intervention_payload.update(
                {
                    'evaluation_id': projection.evaluation_id,
                    'attribution_chain_id': _stable_id('attr', uid, recommendation.intervention_id),
                    'account_generation': account_generation,
                    'surface': 'what_matters_now',
                    'feedback_subject_kind': recommendation.feedback_subject_kind.value,
                    'feedback_subject_id': recommendation.feedback_subject_id,
                    'created_at': existing_created_at or projection.generated_at,
                }
            )
            intervention_writes.append((intervention_path, intervention_payload))
        projection_payload = projection.model_dump(mode='python')
        projection_payload['account_generation'] = account_generation
        transaction.set(projection_path, projection_payload)
        transaction.set(
            decision_path,
            {
                'device_scope': device_scope,
                'account_generation': account_generation,
                'evaluation_id': projection.evaluation_id,
                'evaluated_at': projection.generated_at,
                'expires_at': projection.expires_at,
                'projection': projection.model_dump(mode='python'),
                'decisions': [decision.model_dump(mode='python') for decision in decisions],
            },
        )
        for intervention_path, intervention_payload in intervention_writes:
            transaction.set(intervention_path, intervention_payload)
        return projection, True

    published_projection, did_publish = _store().run_transaction(publish)
    if not did_publish:
        return published_projection

    store = _store()
    batch = store.batch()
    history = []
    for doc in store.query(
        decisions_path,
        filters=[('device_scope', '==', device_scope), ('account_generation', '==', account_generation)],
    ):
        payload = _snapshot_dict(doc)
        if payload.get('evaluation_id') == projection.evaluation_id:
            continue
        history.append((payload.get('evaluated_at'), payload.get('expires_at'), doc.path))
    history.sort(key=lambda item: item[0] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    for index, (_, expires_at, path) in enumerate(history):
        if expires_at is None or expires_at <= projection.generated_at or index >= MAX_DECISION_HISTORY_PER_DEVICE - 1:
            batch.delete(path)
    batch.commit()
    return published_projection


def get_projection(
    uid: str,
    *,
    device_scope: str,
    now: datetime,
    include_expired: bool = False,
    account_generation: int = 0,
) -> Optional[WhatMattersNowProjection]:
    ref_path = _document_path(
        uid, PROJECTIONS_COLLECTION, _stable_id('projection', account_generation, device_scope)
    )
    control_path = _control_path(uid)

    def read(transaction):
        _validate_generation(transaction.get(control_path), uid=uid, account_generation=account_generation)
        return transaction.get(ref_path)

    snapshot = _store().run_transaction(read)
    if not snapshot.exists:
        return None
    payload = _snapshot_dict(snapshot)
    if payload.get('account_generation') != account_generation:
        return None
    projection = parse_snapshot_or_none(
        WhatMattersNowProjection,
        snapshot,
        payload_from_snapshot=lambda _snapshot: _without_generation(payload),
    )
    if projection is None:
        return None
    return projection if include_expired or projection.expires_at > now else None


def _decision_records(raw_records: list[Any], evaluation_id: str) -> list[DecisionRecord]:
    """Build DecisionRecord objects from stored decision dicts, skipping a malformed one.

    DecisionRecord is extra='forbid', so a legacy or schema-drifted audit record would raise
    ValidationError and 500 the whole recommendation read. Skip such a record rather than fail the
    batch; unexpected errors still propagate. Sorted by subject_id to match the caller.
    """
    records: list[DecisionRecord] = []
    for record in raw_records:
        try:
            records.append(DecisionRecord.model_validate(record))
        except ValidationError as e:
            _record_malformed_embedded_payload(evaluation_id=evaluation_id, error=e)
    records.sort(key=lambda record: record.subject_id)
    return records


def get_decisions(
    uid: str,
    evaluation_id: str,
    *,
    device_scope: str,
    account_generation: int = 0,
) -> list[DecisionRecord]:
    ref_path = _document_path(
        uid, DECISIONS_COLLECTION, _stable_id('decision', account_generation, device_scope, evaluation_id)
    )
    control_path = _control_path(uid)

    def read(transaction):
        _validate_generation(transaction.get(control_path), uid=uid, account_generation=account_generation)
        return transaction.get(ref_path)

    snapshot = _store().run_transaction(read)
    if not snapshot.exists:
        return []
    payload = _snapshot_dict(snapshot)
    if payload.get('evaluation_id') != evaluation_id or payload.get('account_generation') != account_generation:
        return []
    raw_records = payload.get('decisions')
    if not isinstance(raw_records, list):
        return []
    return _decision_records(raw_records, evaluation_id)


def _valid_evaluation_projection(
    raw_projection: Any, evaluation_id: str, now: datetime
) -> Optional[WhatMattersNowProjection]:
    """Build a WhatMattersNowProjection from a stored projection dict, or None if unusable.

    The stored projection was validated with no guard, so a legacy or schema-drifted doc would raise
    ValidationError and 500 the recommendation read. Treat a malformed (or non-dict, stale, or
    id-mismatched) projection as absent, consistent with this reader's other None returns.
    """
    if not isinstance(raw_projection, dict):
        return None
    try:
        projection = WhatMattersNowProjection.model_validate(raw_projection)
    except ValidationError as e:
        _record_malformed_embedded_payload(evaluation_id=evaluation_id, error=e)
        return None
    if projection.evaluation_id != evaluation_id or projection.expires_at <= now:
        return None
    return projection


def get_evaluation_projection(
    uid: str,
    evaluation_id: str,
    *,
    device_scope: str,
    now: datetime,
    account_generation: int = 0,
) -> Optional[WhatMattersNowProjection]:
    ref_path = _document_path(
        uid, DECISIONS_COLLECTION, _stable_id('decision', account_generation, device_scope, evaluation_id)
    )
    control_path = _control_path(uid)

    def read(transaction):
        _validate_generation(transaction.get(control_path), uid=uid, account_generation=account_generation)
        return transaction.get(ref_path)

    snapshot = _store().run_transaction(read)
    if not snapshot.exists:
        return None
    payload = _snapshot_dict(snapshot)
    if payload.get('account_generation') != account_generation:
        return None
    return _valid_evaluation_projection(payload.get('projection'), evaluation_id, now)


def create_feedback(
    uid: str,
    request: FeedbackCreate,
    *,
    idempotency_key: str,
    now: datetime,
    override_expires_at: Optional[datetime],
    account_generation: int = 0,
) -> tuple[FeedbackRecord, bool]:
    feedback_id = _stable_id('feedback', uid, account_generation, idempotency_key)
    attribution_chain_id = _stable_id('attr', uid, account_generation, request.subject_kind.value, request.subject_id)
    dedupe_key: Optional[str] = None
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
    payload['account_generation'] = account_generation
    payload['_override_expires_at'] = override_expires_at
    ref_path = _document_path(uid, FEEDBACK_COLLECTION, feedback_id)
    control_path = _control_path(uid)

    def apply(transaction):
        nonlocal attribution_chain_id, dedupe_key, record, payload
        _validate_generation(transaction.get(control_path), uid=uid, account_generation=account_generation)
        if request.intervention_id is not None:
            intervention_path = _document_path(uid, INTERVENTIONS_COLLECTION, request.intervention_id)
            intervention_snapshot = transaction.get(intervention_path)
            intervention_payload = _snapshot_dict(intervention_snapshot)
            if not intervention_snapshot.exists or intervention_payload.get('account_generation') != account_generation:
                raise InterventionNotFoundError(request.intervention_id)
            intervention_subject_kind = intervention_payload.get(
                'feedback_subject_kind', intervention_payload.get('subject_kind')
            )
            intervention_subject_id = intervention_payload.get(
                'feedback_subject_id', intervention_payload.get('subject_id')
            )
            if intervention_subject_kind != request.subject_kind.value or intervention_subject_id != request.subject_id:
                raise IdempotencyConflictError('feedback subject does not match intervention')
            attribution_chain_id = str(intervention_payload['attribution_chain_id'])
            dedupe_key = str(intervention_payload['dedupe_key'])
            record = record.model_copy(update={'attribution_chain_id': attribution_chain_id, 'dedupe_key': dedupe_key})
            payload = record.model_dump(mode='python') | {
                '_request_hash': _request_hash(request.model_dump(mode='json')),
                'account_generation': account_generation,
                '_override_expires_at': override_expires_at,
            }
        existing = transaction.get(ref_path)
        if existing.exists:
            stored = _snapshot_dict(existing)
            if stored.get('_request_hash') != payload['_request_hash']:
                raise IdempotencyConflictError('idempotency key was used for different feedback')
            stored_dedupe_key = stored.get('dedupe_key')
            stored_override_expiry = stored.get('_override_expires_at')
            if isinstance(stored_dedupe_key, str) and isinstance(stored_override_expiry, datetime):
                override_id = _stable_id('override', uid, account_generation, stored_dedupe_key)
                override_path = _document_path(uid, ATTENTION_OVERRIDES_COLLECTION, override_id)
                if not transaction.get(override_path).exists:
                    transaction.set(
                        override_path,
                        {
                            'override_id': override_id,
                            'account_generation': account_generation,
                            'dedupe_key': stored_dedupe_key,
                            'intervention_id': request.intervention_id,
                            'feedback_id': feedback_id,
                            'action': request.action.value,
                            'reason': request.reason.value if request.reason is not None else None,
                            'created_at': stored.get('created_at', now),
                            'expires_at': stored_override_expiry,
                        },
                    )
            stored.pop('_request_hash', None)
            return (
                parse_snapshot_strict(
                    FeedbackRecord, existing, payload_from_snapshot=lambda _snapshot: _without_generation(stored)
                ),
                False,
            )
        transaction.set(ref_path, payload)
        if override_expires_at is not None and dedupe_key is not None:
            override_id = _stable_id('override', uid, account_generation, dedupe_key)
            transaction.set(
                _document_path(uid, ATTENTION_OVERRIDES_COLLECTION, override_id),
                {
                    'override_id': override_id,
                    'account_generation': account_generation,
                    'dedupe_key': dedupe_key,
                    'intervention_id': request.intervention_id,
                    'feedback_id': feedback_id,
                    'action': request.action.value,
                    'reason': request.reason.value if request.reason is not None else None,
                    'created_at': now,
                    'expires_at': override_expires_at,
                },
            )
        return record, True

    return _store().run_transaction(apply)


def list_active_override_dedupe_keys(
    uid: str,
    *,
    now: datetime,
    account_generation: int = 0,
) -> set[str]:
    # Composite index for this (account_generation ==, expires_at >) serving query is declared in
    # the shared index registry as task_attention_overrides_active_by_generation.
    docs = _store().query(
        _collection_path(uid, ATTENTION_OVERRIDES_COLLECTION),
        filters=[('account_generation', '==', account_generation), ('expires_at', '>', now)],
    )
    return {
        str(payload['dedupe_key'])
        for doc in docs
        if (payload := _snapshot_dict(doc)).get('dedupe_key')
    }


def link_feedback_completion_candidate(
    uid: str,
    feedback_id: str,
    candidate_id: str,
    *,
    account_generation: int,
) -> None:
    ref_path = _document_path(uid, FEEDBACK_COLLECTION, feedback_id)
    control_path = _control_path(uid)

    def apply(transaction):
        _validate_generation(transaction.get(control_path), uid=uid, account_generation=account_generation)
        snapshot = transaction.get(ref_path)
        payload = _snapshot_dict(snapshot)
        if not snapshot.exists or payload.get('account_generation') != account_generation:
            raise RecommendationGenerationMismatchError('feedback generation mismatch')
        payload['proposed_completion_candidate_id'] = candidate_id
        transaction.set(ref_path, payload)

    _store().run_transaction(apply)


def _first_chain_record(
    uid: str, collection_name: str, attribution_chain_id: str, account_generation: int
) -> Optional[dict[str, Any]]:
    matches = _store().query(
        _collection_path(uid, collection_name),
        filters=[
            ('attribution_chain_id', '==', attribution_chain_id),
            ('account_generation', '==', account_generation),
        ],
        limit=1,
    )
    return _snapshot_dict(matches[0]) if matches else None


def _outcome_matches_chain(uid: str, request: OutcomeCreate, source: dict[str, Any]) -> bool:
    raw_source_kind = source.get('feedback_subject_kind') or source.get('subject_kind') or ''
    source_kind = str(getattr(raw_source_kind, 'value', raw_source_kind))
    source_id = str(source.get('feedback_subject_id') or source.get('subject_id') or '')
    allowed: set[tuple[str, str]] = {(source_kind, source_id)}
    workstream_ids: set[str] = set()

    if source_kind == 'candidate':
        candidate_snapshot = _store().get(_document_path(uid, 'candidates', source_id))
        if candidate_snapshot.exists:
            candidate = _snapshot_dict(candidate_snapshot)
            result_task_id = candidate.get('result_task_id')
            result_workstream_id = candidate.get('result_workstream_id')
            if isinstance(result_task_id, str):
                allowed.add(('task', result_task_id))
                task_snapshot = _store().get(_document_path(uid, 'action_items', result_task_id))
                if task_snapshot.exists:
                    task_workstream_id = _snapshot_dict(task_snapshot).get('workstream_id')
                    if isinstance(task_workstream_id, str):
                        workstream_ids.add(task_workstream_id)
            if isinstance(result_workstream_id, str):
                workstream_ids.add(result_workstream_id)
    elif source_kind == 'task':
        task_snapshot = _store().get(_document_path(uid, 'action_items', source_id))
        if task_snapshot.exists:
            workstream_id = _snapshot_dict(task_snapshot).get('workstream_id')
            if isinstance(workstream_id, str):
                workstream_ids.add(workstream_id)
    elif source_kind == 'workstream':
        workstream_ids.add(source_id)

    allowed.update(('workstream', workstream_id) for workstream_id in workstream_ids)
    if request.subject_kind.value == 'artifact':
        for workstream_id in workstream_ids:
            artifact = _store().get(
                f'{_document_path(uid, "workstreams", workstream_id)}/artifact_refs/{request.subject_id}'
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
    account_generation: int = 0,
) -> tuple[OutcomeRecord, bool]:
    source = _first_chain_record(uid, INTERVENTIONS_COLLECTION, request.attribution_chain_id, account_generation)
    if source is None:
        source = _first_chain_record(uid, FEEDBACK_COLLECTION, request.attribution_chain_id, account_generation)
    if source is None:
        raise AttributionChainNotFoundError(request.attribution_chain_id)
    if not _outcome_matches_chain(uid, request, source):
        raise IdempotencyConflictError('outcome subject or code does not match attribution chain')
    outcome_id = _stable_id('outcome', uid, account_generation, idempotency_key)
    record = OutcomeRecord(**request.model_dump(mode='python'), outcome_id=outcome_id, occurred_at=now)
    payload = record.model_dump(mode='python')
    payload['_request_hash'] = _request_hash(request.model_dump(mode='json'))
    payload['account_generation'] = account_generation
    ref_path = _document_path(uid, OUTCOMES_COLLECTION, outcome_id)
    control_path = _control_path(uid)

    def apply(transaction):
        _validate_generation(transaction.get(control_path), uid=uid, account_generation=account_generation)
        existing = transaction.get(ref_path)
        if not existing.exists:
            transaction.set(ref_path, payload)
            return record, True
        stored = _snapshot_dict(existing)
        if stored.get('_request_hash') != payload['_request_hash']:
            raise IdempotencyConflictError('idempotency key was used for a different outcome')
        stored.pop('_request_hash', None)
        return (
            parse_snapshot_strict(
                OutcomeRecord, existing, payload_from_snapshot=lambda _snapshot: _without_generation(stored)
            ),
            False,
        )

    return _store().run_transaction(apply)


def replace_context_snapshot(
    uid: str,
    snapshot: NormalizedContextSnapshot,
    *,
    account_generation: int = 0,
    idempotency_key: str | None = None,
) -> SnapshotReceipt:
    ref_path = _document_path(
        uid, CONTEXT_SNAPSHOTS_COLLECTION, _stable_id('context', account_generation, snapshot.device_id)
    )
    control_path = _control_path(uid)
    request_key = idempotency_key or snapshot.snapshot_id
    request_hash = _request_hash(snapshot.model_dump(mode='json'))
    receipt_id = _stable_id('snapshot-receipt', account_generation, 'context', request_key)
    receipt_path = _document_path(uid, SNAPSHOT_RECEIPTS_COLLECTION, receipt_id)

    def apply(transaction):
        _validate_generation(
            transaction.get(control_path),
            uid=uid,
            account_generation=account_generation,
        )
        prior_receipt = transaction.get(receipt_path)
        if prior_receipt.exists:
            prior = _snapshot_dict(prior_receipt)
            if prior.get('request_hash') != request_hash:
                raise IdempotencyConflictError('idempotency key was used for a different context snapshot')
            return SnapshotReceipt.model_validate(prior['receipt'])
        stored_snapshot = transaction.get(ref_path)
        replaced = stored_snapshot.exists
        if replaced:
            stored_payload = _snapshot_dict(stored_snapshot)
            stored = parse_snapshot_strict(
                NormalizedContextSnapshot,
                stored_snapshot,
                payload_from_snapshot=lambda _snapshot: _without_generation(stored_payload),
            )
            if snapshot.generated_at < stored.generated_at:
                raise StaleSnapshotError('context snapshot is older than stored state')
            if snapshot.generated_at == stored.generated_at and snapshot != stored:
                raise IdempotencyConflictError('context snapshot timestamp was reused for different state')
        payload = snapshot.model_dump(mode='python')
        payload['account_generation'] = account_generation
        payload['_receipt_id'] = receipt_id
        transaction.set(ref_path, payload)
        receipt = SnapshotReceipt(snapshot_id=snapshot.snapshot_id, replaced=replaced, expires_at=snapshot.expires_at)
        transaction.set(
            receipt_path,
            {
                'account_generation': account_generation,
                'request_hash': request_hash,
                'receipt': receipt.model_dump(mode='python'),
                'expires_at': snapshot.expires_at,
            },
        )
        return receipt

    result = _store().run_transaction(apply)
    _cleanup_expired_snapshot_receipts(uid, now=snapshot.generated_at)
    return result


def get_context_snapshot(
    uid: str,
    device_id: str,
    *,
    now: datetime,
    account_generation: int = 0,
) -> Optional[NormalizedContextSnapshot]:
    ref_path = _document_path(
        uid, CONTEXT_SNAPSHOTS_COLLECTION, _stable_id('context', account_generation, device_id)
    )
    snapshot = _store().get(ref_path)
    if not snapshot.exists:
        return None
    payload = _snapshot_dict(snapshot)
    if payload.get('account_generation') != account_generation:
        return None
    record = parse_snapshot_or_none(
        NormalizedContextSnapshot,
        snapshot,
        payload_from_snapshot=lambda _snapshot: _without_generation(payload),
    )
    if record is None:
        return None
    if record.expires_at <= now:
        _store().delete(ref_path)
        receipt_id = payload.get('_receipt_id')
        if isinstance(receipt_id, str):
            _store().delete(_document_path(uid, SNAPSHOT_RECEIPTS_COLLECTION, receipt_id))
        _cleanup_expired_snapshot_receipts(uid, now=now)
        return None
    return record


def replace_open_loop_snapshot(
    uid: str,
    snapshot: OpenLoopSnapshot,
    *,
    account_generation: int = 0,
    idempotency_key: str | None = None,
) -> SnapshotReceipt:
    snapshot_key = _stable_id(
        'loop-snapshot', account_generation, snapshot.device_id, snapshot.runtime_id, snapshot.workstream_id
    )
    ref_path = _document_path(uid, OPEN_LOOP_SNAPSHOTS_COLLECTION, snapshot_key)
    control_path = _control_path(uid)
    request_key = idempotency_key or snapshot_key
    request_hash = _request_hash(snapshot.model_dump(mode='json'))
    receipt_id = _stable_id('snapshot-receipt', account_generation, 'open-loop', request_key)
    receipt_path = _document_path(uid, SNAPSHOT_RECEIPTS_COLLECTION, receipt_id)

    def apply(transaction):
        _validate_generation(
            transaction.get(control_path),
            uid=uid,
            account_generation=account_generation,
        )
        prior_receipt = transaction.get(receipt_path)
        if prior_receipt.exists:
            prior = _snapshot_dict(prior_receipt)
            if prior.get('request_hash') != request_hash:
                raise IdempotencyConflictError('idempotency key was used for a different open-loop snapshot')
            return SnapshotReceipt.model_validate(prior['receipt'])
        stored_snapshot = transaction.get(ref_path)
        replaced = stored_snapshot.exists
        if replaced:
            stored_payload = _snapshot_dict(stored_snapshot)
            stored = parse_snapshot_strict(
                OpenLoopSnapshot,
                stored_snapshot,
                payload_from_snapshot=lambda _snapshot: _without_generation(stored_payload),
            )
            if snapshot.generated_at < stored.generated_at:
                raise StaleSnapshotError('open-loop snapshot is older than stored state')
            if snapshot.generated_at == stored.generated_at and snapshot != stored:
                raise IdempotencyConflictError('open-loop snapshot timestamp was reused for different state')
        payload = snapshot.model_dump(mode='python')
        payload['account_generation'] = account_generation
        payload['_receipt_id'] = receipt_id
        transaction.set(ref_path, payload)
        receipt = SnapshotReceipt(snapshot_id=snapshot_key, replaced=replaced, expires_at=snapshot.expires_at)
        transaction.set(
            receipt_path,
            {
                'account_generation': account_generation,
                'request_hash': request_hash,
                'receipt': receipt.model_dump(mode='python'),
                'expires_at': snapshot.expires_at,
            },
        )
        return receipt

    result = _store().run_transaction(apply)
    _cleanup_expired_snapshot_receipts(uid, now=snapshot.generated_at)
    return result


def list_open_loop_snapshots(
    uid: str,
    *,
    device_id: str,
    now: datetime,
    account_generation: int,
) -> list[OpenLoopSnapshot]:
    loops_path = _collection_path(uid, OPEN_LOOP_SNAPSHOTS_COLLECTION)
    docs = _store().query(
        loops_path,
        filters=[('device_id', '==', device_id), ('account_generation', '==', account_generation)],
    )
    records: list[OpenLoopSnapshot] = []
    for doc in docs:
        payload = _snapshot_dict(doc)
        record = parse_snapshot_or_none(
            OpenLoopSnapshot,
            doc,
            payload_from_snapshot=lambda _snapshot: _without_generation(payload),
        )
        if record is None:
            continue
        if record.expires_at <= now:
            _store().delete(doc.path)
            receipt_id = payload.get('_receipt_id')
            if isinstance(receipt_id, str):
                _store().delete(_document_path(uid, SNAPSHOT_RECEIPTS_COLLECTION, receipt_id))
            continue
        records.append(record)
    _cleanup_expired_snapshot_receipts(uid, now=now)
    records.sort(key=lambda record: (record.workstream_id, record.runtime_id))
    return records


def load_canonical_product_state(
    uid: str, *, account_generation: int = 0
) -> dict[str, list[dict[str, Any]]]:
    """Load bounded canonical state; device-local execution state is loaded separately."""

    store = _store()

    def load_collection(name: str, limit: int) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        collection_path = _collection_path(uid, name)
        if account_generation > 0:
            docs = store.query(collection_path, filters=[('account_generation', '==', account_generation)], limit=limit)
        else:
            docs = store.query(collection_path, limit=limit)
        for doc in docs:
            payload = _snapshot_dict(doc)
            payload.setdefault('id', doc.id)
            stored_generation = payload.get('account_generation', 0)
            if stored_generation == account_generation:
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
        workstream_path = _document_path(uid, 'workstreams', workstream_id)
        if len(artifacts) < 200:
            for doc in store.query(f'{workstream_path}/artifact_refs', limit=100):
                payload = _snapshot_dict(doc)
                payload.setdefault('artifact_id', doc.id)
                payload.setdefault('workstream_id', workstream_id)
                artifacts.append(payload)
                if len(artifacts) >= 200:
                    break
        if len(workstream_events) < 200:
            for doc in store.query(f'{workstream_path}/events', order_by='sequence', direction='desc', limit=20):
                payload = _snapshot_dict(doc)
                payload.setdefault('event_id', doc.id)
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
    'RecommendationGenerationMismatchError',
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
