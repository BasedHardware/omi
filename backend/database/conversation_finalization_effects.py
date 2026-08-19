"""Storage contract for durable conversation search-index effects."""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Callable, Literal, Mapping, TypedDict
from uuid import uuid4

FINALIZATION_FANOUT_PLAN_VERSION = 2
FINALIZATION_EFFECT_PLAN_MODE_ENV = 'CONVERSATION_FINALIZATION_EFFECT_PLAN_MODE'
FINALIZATION_EFFECT_PLAN_MODES = frozenset({'standby', 'active'})
REQUIRED_EFFECT_KEYS = ('structured_vector', 'transcript_vectors')
FINALIZATION_INCARNATION_FIELD = 'finalization_incarnation_id'
FINALIZATION_VECTOR_GENERATION_FIELD = 'finalization_vector_generation_id'
TRANSCRIPT_VECTOR_COUNT_FIELD = 'transcript_vector_count'
VECTOR_CLEANUP_PENDING_FIELD = 'vector_cleanup_pending'
FINALIZATION_EFFECT_SOURCE_FINGERPRINT_FIELD = 'finalization_effect_source_fingerprint'
FINALIZATION_EFFECT_SOURCE_FIELDS = (
    'structured',
    'user_title',
    'transcript_segments',
    'transcript_segments_compressed',
    'created_at',
    'started_at',
    'source',
    'external_data',
)
FinalizationEffectBoundaryStatus = Literal['completed', 'conversation_missing', 'conversation_replaced', 'conflict']


class FinalizationFanoutClaim(TypedDict):
    status: str
    fanout_key: str | None
    plan_version: int
    completed_effects: tuple[str, ...]
    finalization_incarnation_id: str | None
    finalization_vector_generation_id: str | None
    transcript_vector_count: int | None


def stamp_finalization_incarnation(data: dict[str, Any], existing: Mapping[str, Any] | None = None) -> None:
    """Keep one server-owned identity for the lifetime of a conversation row."""
    existing_id = existing.get(FINALIZATION_INCARNATION_FIELD) if existing is not None else None
    data[FINALIZATION_INCARNATION_FIELD] = existing_id if isinstance(existing_id, str) and existing_id else uuid4().hex


def finalization_effect_plan_mode() -> str:
    """Return the safe rollout mode for newly created finalization jobs."""
    configured = os.getenv(FINALIZATION_EFFECT_PLAN_MODE_ENV, 'standby').strip().lower()
    return configured if configured in FINALIZATION_EFFECT_PLAN_MODES else 'standby'


def fanout_plan_version(job: Mapping[str, Any] | None) -> int:
    """Read a stored plan version, preserving unversioned v1 compatibility."""
    if job is None or 'fanout_plan_version' not in job:
        return 1
    value = job['fanout_plan_version']
    if isinstance(value, int) and not isinstance(value, bool) and value >= 1:
        return value
    return 0


def completed_effects(job: Mapping[str, Any] | None) -> tuple[str, ...]:
    """Return recognized checkpoints in stable execution order."""
    if job is None:
        return ()
    values = job.get('completed_effects')
    if not isinstance(values, (list, tuple, set, frozenset)):
        return ()
    completed = {value for value in values if isinstance(value, str)}
    return tuple(effect for effect in REQUIRED_EFFECT_KEYS if effect in completed)


def finalization_incarnation_id(job: Mapping[str, Any] | None) -> str | None:
    value = job.get(FINALIZATION_INCARNATION_FIELD) if job is not None else None
    return value if isinstance(value, str) and value else None


def finalization_vector_generation_id(job: Mapping[str, Any] | None) -> str | None:
    value = job.get(FINALIZATION_VECTOR_GENERATION_FIELD) if job is not None else None
    return value if isinstance(value, str) and value else None


def transcript_vector_count(job: Mapping[str, Any] | None) -> int | None:
    value = job.get(TRANSCRIPT_VECTOR_COUNT_FIELD) if job is not None else None
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _canonical_source_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_source_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_source_value(item) for item in value]
    if isinstance(value, datetime):
        normalized = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return {'datetime': normalized.astimezone(timezone.utc).isoformat()}
    if isinstance(value, bytes):
        return {'bytes': base64.b64encode(value).decode('ascii')}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return {'type': type(value).__name__, 'value': str(value)}


def finalization_effect_source_fingerprint(conversation: Mapping[str, Any]) -> str:
    """Hash only vector-relevant source fields without retaining conversation content."""
    source = {field: _canonical_source_value(conversation.get(field)) for field in FINALIZATION_EFFECT_SOURCE_FIELDS}
    payload = json.dumps(source, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    return sha256(payload).hexdigest()


def _valid_source_fingerprint(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in '0123456789abcdef' for character in value)


def fanout_claim(
    status: str,
    key: str | None,
    job: Mapping[str, Any] | None = None,
) -> FinalizationFanoutClaim:
    return {
        'status': status,
        'fanout_key': key,
        'plan_version': fanout_plan_version(job),
        'completed_effects': completed_effects(job),
        'finalization_incarnation_id': finalization_incarnation_id(job),
        'finalization_vector_generation_id': finalization_vector_generation_id(job),
        'transcript_vector_count': transcript_vector_count(job),
    }


def fanout_key(job: Mapping[str, Any]) -> str:
    key = job.get('fanout_key')
    if isinstance(key, str) and key:
        return key
    incarnation = finalization_incarnation_id(job)
    generation = f':incarnation:{incarnation}' if incarnation else ''
    return (
        f"conversation:{job.get('conversation_id', '')}{generation}:"
        f"finalization:{int(job.get('finalization_revision') or 1)}"
    )


def _conversation_admits_job_binding(
    conversation: Mapping[str, Any],
    job: Mapping[str, Any],
    job_id: str,
) -> bool:
    if (
        conversation.get('discarded')
        or conversation.get(VECTOR_CLEANUP_PENDING_FIELD)
        or conversation.get('status') != 'completed'
    ):
        return False
    if conversation.get('finalization_job_id') != job_id:
        return False
    job_incarnation = finalization_incarnation_id(job)
    if job_incarnation is not None and conversation.get(FINALIZATION_INCARNATION_FIELD) != job_incarnation:
        return False
    try:
        return int(conversation.get('finalization_revision') or 0) == int(job.get('finalization_revision') or 0)
    except (TypeError, ValueError):
        return False


def conversation_admits_fanout(
    conversation: Mapping[str, Any],
    job: Mapping[str, Any],
    job_id: str,
) -> bool:
    """Require both the immutable row binding and exact effect source."""
    if not _conversation_admits_job_binding(conversation, job, job_id):
        return False
    if (
        fanout_plan_version(job) != FINALIZATION_FANOUT_PLAN_VERSION
        and FINALIZATION_EFFECT_SOURCE_FINGERPRINT_FIELD not in job
    ):
        return True
    source_fingerprint = job.get(FINALIZATION_EFFECT_SOURCE_FINGERPRINT_FIELD)
    return _valid_source_fingerprint(
        source_fingerprint
    ) and source_fingerprint == finalization_effect_source_fingerprint(conversation)


def claim_fanout_txn(
    transaction: Any,
    job_ref: Any,
    dispatch_generation: int,
    lease_epoch: int,
    now: Any,
    *,
    is_current_lease: Callable[[dict[str, Any], int, int], bool],
    conversation_ref_for_job: Callable[[str, str], Any],
    fenced_update: Callable[[Any], Mapping[str, Any]],
    record_projection: Callable[[Any, Mapping[str, Any]], None],
    delete_field: Any,
) -> FinalizationFanoutClaim:
    """Claim required effects and external fanout against one source snapshot."""
    snapshot = job_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return fanout_claim('missing', None)
    job = snapshot.to_dict() or {}
    key = fanout_key(job)
    plan_version = fanout_plan_version(job)
    fanout_completed = job.get('fanout_status') == 'completed'
    cleanup_safe = finalization_vector_generation_id(job) is not None
    if (
        fanout_completed
        and plan_version == FINALIZATION_FANOUT_PLAN_VERSION
        and completed_effects(job) == REQUIRED_EFFECT_KEYS
    ):
        uid = job.get('uid')
        conversation_id = job.get('conversation_id')
        if isinstance(uid, str) and uid and isinstance(conversation_id, str) and conversation_id:
            completed_snapshot = conversation_ref_for_job(uid, conversation_id).get(transaction=transaction)
            completed_conversation = (
                completed_snapshot.to_dict() if getattr(completed_snapshot, 'exists', False) else None
            )
            if not isinstance(completed_conversation, Mapping) or not conversation_admits_fanout(
                completed_conversation, job, job_ref.id
            ):
                return fanout_claim('completed_cleanup_required' if cleanup_safe else 'completed', key, job)
        return fanout_claim('completed', key, job)
    if not is_current_lease(job, dispatch_generation, lease_epoch):
        return fanout_claim('lease_conflict', key, job)
    if job.get('fanout_status') == 'leased' and int(job.get('fanout_lease_epoch') or 0) != lease_epoch:
        return fanout_claim('draining', key, job)

    uid = job.get('uid')
    conversation_id = job.get('conversation_id')
    if not isinstance(uid, str) or not uid or not isinstance(conversation_id, str) or not conversation_id:
        if fanout_completed and plan_version == 1:
            return fanout_claim('completed', key, job)
        transaction.update(job_ref, dict(fenced_update(now)))
        record_projection(transaction, job)
        return fanout_claim('fenced', key, job)

    conversation_snapshot = conversation_ref_for_job(uid, conversation_id).get(transaction=transaction)
    conversation = conversation_snapshot.to_dict() if getattr(conversation_snapshot, 'exists', False) else None
    source_fingerprint_uninitialized = (
        plan_version == FINALIZATION_FANOUT_PLAN_VERSION
        and FINALIZATION_EFFECT_SOURCE_FINGERPRINT_FIELD not in job
        and not completed_effects(job)
        and not fanout_completed
    )
    conversation_is_current = isinstance(conversation, Mapping) and (
        (source_fingerprint_uninitialized and _conversation_admits_job_binding(conversation, job, job_ref.id))
        or conversation_admits_fanout(conversation, job, job_ref.id)
    )
    if fanout_completed and plan_version == 1:
        return fanout_claim(
            'completed_cleanup_required' if not conversation_is_current and cleanup_safe else 'completed',
            key,
            job,
        )
    if not conversation_is_current:
        if cleanup_safe:
            return fanout_claim('cleanup_required', key, job)
        transaction.update(job_ref, dict(fenced_update(now)))
        record_projection(transaction, job)
        return fanout_claim('fenced', key, job)

    assert isinstance(conversation, Mapping)
    source_fingerprint = finalization_effect_source_fingerprint(conversation)
    transaction.update(
        job_ref,
        {
            'fanout_key': key,
            'fanout_status': 'leased',
            'fanout_lease_epoch': lease_epoch,
            'fanout_started_at': now,
            **({'fanout_completed_at': delete_field} if job.get('fanout_status') == 'completed' else {}),
            **(
                {FINALIZATION_EFFECT_SOURCE_FINGERPRINT_FIELD: source_fingerprint}
                if source_fingerprint_uninitialized
                else {}
            ),
            'updated_at': now,
        },
    )
    return fanout_claim('claimed', key, job)


def validate_effect_owner_txn(
    transaction: Any,
    job_ref: Any,
    dispatch_generation: int,
    lease_epoch: int,
    *,
    is_current_lease: Callable[[dict[str, Any], int, int], bool],
    conversation_ref_for_job: Callable[[str, str], Any],
    conversation_admits_fanout: Callable[[Mapping[str, Any], Mapping[str, Any], str], bool],
) -> tuple[FinalizationEffectBoundaryStatus, dict[str, Any]]:
    """Recheck the lease and conversation after one vector mutation."""
    snapshot = job_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return 'conflict', {}
    job = snapshot.to_dict() or {}
    plan_version = fanout_plan_version(job)
    if plan_version not in (1, FINALIZATION_FANOUT_PLAN_VERSION):
        return 'conflict', job
    uid = job.get('uid')
    conversation_id = job.get('conversation_id')
    if not isinstance(uid, str) or not uid or not isinstance(conversation_id, str) or not conversation_id:
        return 'conflict', job
    conversation_snapshot = conversation_ref_for_job(uid, conversation_id).get(transaction=transaction)
    if not getattr(conversation_snapshot, 'exists', False):
        return 'conversation_missing', job
    if not is_current_lease(job, dispatch_generation, lease_epoch):
        return 'conflict', job
    fanout_status = job.get('fanout_status')
    if plan_version == FINALIZATION_FANOUT_PLAN_VERSION:
        if not _valid_source_fingerprint(job.get(FINALIZATION_EFFECT_SOURCE_FINGERPRINT_FIELD)):
            return 'conflict', job
        if fanout_status != 'leased' or int(job.get('fanout_lease_epoch') or 0) != lease_epoch:
            return 'conflict', job
    elif fanout_status == 'leased':
        if int(job.get('fanout_lease_epoch') or 0) != lease_epoch:
            return 'conflict', job
    elif fanout_status != 'completed':
        return 'conflict', job
    conversation = conversation_snapshot.to_dict()
    if not isinstance(conversation, Mapping) or not conversation_admits_fanout(conversation, job, job_ref.id):
        return 'conversation_replaced', job
    return 'completed', job


def prepare_effect_txn(
    transaction: Any,
    job_ref: Any,
    dispatch_generation: int,
    lease_epoch: int,
    effect: str,
    resource_count: int,
    now: Any,
    *,
    is_current_lease: Callable[[dict[str, Any], int, int], bool],
    conversation_ref_for_job: Callable[[str, str], Any],
    conversation_admits_fanout: Callable[[Mapping[str, Any], Mapping[str, Any], str], bool],
) -> FinalizationEffectBoundaryStatus:
    """Persist content-free cleanup coordinates before a vector writer starts."""
    if effect not in REQUIRED_EFFECT_KEYS or isinstance(resource_count, bool) or resource_count < 0:
        return 'conflict'
    status, job = validate_effect_owner_txn(
        transaction,
        job_ref,
        dispatch_generation,
        lease_epoch,
        is_current_lease=is_current_lease,
        conversation_ref_for_job=conversation_ref_for_job,
        conversation_admits_fanout=conversation_admits_fanout,
    )
    if status != 'completed' or effect != 'transcript_vectors':
        return status
    existing = job.get(TRANSCRIPT_VECTOR_COUNT_FIELD)
    if existing is not None and existing != resource_count:
        return 'conflict'
    uid = job.get('uid')
    conversation_id = job.get('conversation_id')
    if not isinstance(uid, str) or not uid or not isinstance(conversation_id, str) or not conversation_id:
        return 'conflict'
    transaction.update(
        conversation_ref_for_job(uid, conversation_id),
        {TRANSCRIPT_VECTOR_COUNT_FIELD: resource_count},
    )
    if existing is None:
        transaction.update(job_ref, {TRANSCRIPT_VECTOR_COUNT_FIELD: resource_count, 'updated_at': now})
    return 'completed'


def complete_effect_txn(
    transaction: Any,
    job_ref: Any,
    dispatch_generation: int,
    lease_epoch: int,
    effect: str,
    now: Any,
    *,
    is_current_lease: Callable[[dict[str, Any], int, int], bool],
    conversation_ref_for_job: Callable[[str, str], Any],
    conversation_admits_fanout: Callable[[Mapping[str, Any], Mapping[str, Any], str], bool],
    persist_effect: bool = True,
) -> FinalizationEffectBoundaryStatus:
    """Checkpoint one vector only while its source conversation still exists."""
    status, job = validate_effect_owner_txn(
        transaction,
        job_ref,
        dispatch_generation,
        lease_epoch,
        is_current_lease=is_current_lease,
        conversation_ref_for_job=conversation_ref_for_job,
        conversation_admits_fanout=conversation_admits_fanout,
    )
    if effect not in REQUIRED_EFFECT_KEYS:
        return 'conflict'
    if status != 'completed':
        return status
    plan_version = fanout_plan_version(job)
    if plan_version == 1:
        return 'completed'
    if plan_version != FINALIZATION_FANOUT_PLAN_VERSION:
        return 'conflict'
    if not persist_effect:
        return 'completed'
    existing = completed_effects(job)
    if effect in existing:
        return 'completed'
    completed = set(existing)
    completed.add(effect)
    transaction.update(
        job_ref,
        {
            'completed_effects': [key for key in REQUIRED_EFFECT_KEYS if key in completed],
            'updated_at': now,
        },
    )
    return 'completed'


def cleanup_fence_txn(
    transaction: Any,
    job_ref: Any,
    dispatch_generation: int,
    lease_epoch: int,
    now: Any,
    *,
    is_current_lease: Callable[[dict[str, Any], int, int], bool],
    conversation_ref_for_job: Callable[[str, str], Any],
    conversation_admits_fanout: Callable[[Mapping[str, Any], Mapping[str, Any], str], bool],
    fenced_update: Callable[[Any], Mapping[str, Any]],
    record_projection: Callable[[Any, Mapping[str, Any]], None],
) -> bool:
    """Close an old job only after exact generation cleanup and a source reread."""
    snapshot = job_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return False
    job = snapshot.to_dict() or {}
    uid = job.get('uid')
    conversation_id = job.get('conversation_id')
    if not isinstance(uid, str) or not uid or not isinstance(conversation_id, str) or not conversation_id:
        return False
    conversation_snapshot = conversation_ref_for_job(uid, conversation_id).get(transaction=transaction)
    conversation = conversation_snapshot.to_dict() if getattr(conversation_snapshot, 'exists', False) else None
    if (
        isinstance(conversation, Mapping) and conversation_admits_fanout(conversation, job, job_ref.id)
    ) or not is_current_lease(job, dispatch_generation, lease_epoch):
        return False
    if job.get('fanout_status') not in (None, 'pending', 'leased'):
        return False
    if job.get('fanout_status') == 'leased' and int(job.get('fanout_lease_epoch') or 0) != lease_epoch:
        return False
    transaction.update(job_ref, dict(fenced_update(now)))
    record_projection(transaction, job)
    return True
