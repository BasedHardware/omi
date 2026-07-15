"""Firestore outbox and lease state for durable listen finalization.

Cloud Tasks is deliberately only a wake-up mechanism.  The durable source of
truth is one Firestore job per ``(uid, conversation_id, finalization_revision)``.
No transcript, credential, request header, or raw exception is stored here.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Literal, Mapping, NotRequired, TypedDict

from google.cloud import firestore

from database._client import document_id_from_seed, get_firestore_client

CONVERSATIONS_COLLECTION = 'conversations'
FINALIZATION_JOBS_COLLECTION = 'conversation_finalization_jobs'

FinalizationJobStatus = Literal['queued', 'leased', 'completed', 'dead_letter', 'blocked_byok']
TERMINAL_JOB_STATUSES = frozenset({'completed', 'dead_letter'})
NONTERMINAL_JOB_STATUSES = frozenset({'queued', 'leased', 'blocked_byok'})
DEFAULT_LEASE_SECONDS = 1500
DEFAULT_RECONCILE_STALE_SECONDS = 300


class FinalizationIntent(TypedDict):
    job_id: str | None
    status: str
    dispatch_generation: int | None
    requires_byok: bool
    fanout_key: str | None
    newly_created: NotRequired[bool]


class FinalizationAdmission(TypedDict):
    """Pure lifecycle-service decision evaluated inside the outbox transaction."""

    accepted: bool
    terminal: bool
    reason: str
    fanout_key: str | None


class FinalizationFanoutClaim(TypedDict):
    """Ownership result for the durable external-integration fanout."""

    status: str
    fanout_key: str | None


class FinalizationClaim(TypedDict):
    """Result of a claim, including the per-claim ownership fence."""

    status: str
    lease_epoch: int | None
    attempt_count: int
    accepted_at_epoch_seconds: float | None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_finalization_reconcile_stale_after() -> timedelta:
    """Return the bounded delay before a missed handoff becomes replayable."""
    try:
        seconds = int(os.getenv('LISTEN_FINALIZATION_RECONCILE_STALE_SECONDS', str(DEFAULT_RECONCILE_STALE_SECONDS)))
    except ValueError:
        seconds = DEFAULT_RECONCILE_STALE_SECONDS
    return timedelta(seconds=max(30, seconds))


def _claim_result(
    status: str,
    lease_epoch: int | None = None,
    attempt_count: int = 0,
    accepted_at_epoch_seconds: float | None = None,
) -> FinalizationClaim:
    return {
        'status': status,
        'lease_epoch': lease_epoch,
        'attempt_count': attempt_count,
        'accepted_at_epoch_seconds': accepted_at_epoch_seconds,
    }


def _is_current_lease(job: dict[str, Any], dispatch_generation: int, lease_epoch: int) -> bool:
    return (
        job.get('status') == 'leased'
        and int(job.get('dispatch_generation') or 1) == dispatch_generation
        and int(job.get('lease_epoch') or 0) == lease_epoch
    )


def _client(firestore_client: Any = None) -> Any:
    return firestore_client if firestore_client is not None else get_firestore_client()


def _conversation_ref(client: Any, uid: str, conversation_id: str) -> Any:
    return client.collection('users').document(uid).collection(CONVERSATIONS_COLLECTION).document(conversation_id)


def _job_ref(client: Any, job_id: str) -> Any:
    return client.collection(FINALIZATION_JOBS_COLLECTION).document(job_id)


def _job_id(uid: str, conversation_id: str, revision: int) -> str:
    return document_id_from_seed(f'listen-finalization:{uid}:{conversation_id}:{revision}')


def _intent_from_job(job_id: str, data: dict[str, Any]) -> FinalizationIntent:
    return {
        'job_id': job_id,
        'status': str(data.get('status') or 'queued'),
        'dispatch_generation': int(data.get('dispatch_generation') or 1),
        'requires_byok': bool(data.get('requires_byok')),
        'fanout_key': data.get('fanout_key') if isinstance(data.get('fanout_key'), str) else None,
    }


def _no_finalization_intent(status: str) -> FinalizationIntent:
    return {
        'job_id': None,
        'status': status,
        'dispatch_generation': None,
        'requires_byok': False,
        'fanout_key': None,
    }


def _conversation_has_finalization_content(
    conversation: Mapping[str, Any], conversation_ref: Any, transaction: Any
) -> bool:
    """Read current and pre-marker photo content within the admission transaction."""
    if conversation.get('has_content') or conversation.get('transcript_segments') or conversation.get('photos'):
        return True
    # `has_content` was added after photo-only listen recordings already
    # existed. Keep their durable child documents admissible until all legacy
    # rows have naturally finalized, without moving the read outside this
    # transaction's authoritative snapshot.
    return next(iter(conversation_ref.collection('photos').limit(1).stream(transaction=transaction)), None) is not None


def _create_or_get_finalization_intent_txn(
    transaction: Any,
    conversation_ref: Any,
    jobs_collection: Any,
    uid: str,
    conversation_id: str,
    requires_byok: bool,
    finalization_admission: Callable[[Mapping[str, Any]], FinalizationAdmission],
    now: datetime,
) -> FinalizationIntent:
    """Persist finalization ownership before any pusher or task handoff."""
    conversation_snapshot = conversation_ref.get(transaction=transaction)
    if not getattr(conversation_snapshot, 'exists', False):
        return _no_finalization_intent('missing')

    conversation = conversation_snapshot.to_dict() or {}
    if conversation.get('deferred'):
        return _no_finalization_intent('deferred')
    if not _conversation_has_finalization_content(conversation, conversation_ref, transaction):
        return _no_finalization_intent('no_content')

    # The lifecycle service owns this pure decision, but it is evaluated while
    # Firestore holds the conversation transaction snapshot. A late disconnect
    # therefore cannot reopen a failed/discarded terminal row after a stale
    # pre-transaction read.
    admission = finalization_admission(conversation)
    if admission['terminal']:
        return _no_finalization_intent(admission['reason'])

    existing_job_id = conversation.get('finalization_job_id')
    if isinstance(existing_job_id, str) and existing_job_id:
        existing_ref = jobs_collection.document(existing_job_id)
        existing_snapshot = existing_ref.get(transaction=transaction)
        if getattr(existing_snapshot, 'exists', False):
            return _intent_from_job(existing_job_id, existing_snapshot.to_dict() or {})

    if not admission['accepted'] or not admission['fanout_key']:
        return _no_finalization_intent(admission['reason'])

    revision = int(conversation.get('finalization_revision') or 0) + 1
    job_id = _job_id(uid, conversation_id, revision)
    job_ref = jobs_collection.document(job_id)
    job_snapshot = job_ref.get(transaction=transaction)
    if getattr(job_snapshot, 'exists', False):
        job = job_snapshot.to_dict() or {}
        transaction.update(
            conversation_ref,
            {
                'status': 'processing',
                'finalization_job_id': job_id,
                'finalization_revision': revision,
                'finalization_status': job.get('status', 'queued'),
            },
        )
        return _intent_from_job(job_id, job)

    status: FinalizationJobStatus = 'blocked_byok' if requires_byok else 'queued'
    job = {
        'schema_version': 1,
        'uid': uid,
        'conversation_id': conversation_id,
        'finalization_revision': revision,
        'status': status,
        'requires_byok': requires_byok,
        'fanout_key': admission['fanout_key'],
        'fanout_status': 'pending',
        'dispatch_generation': 1,
        'attempt_count': 0,
        'task_retry_count': 0,
        'created_at': now,
        'updated_at': now,
        'dispatch_requested_at': now,
    }
    if not requires_byok:
        job['reconcile_after_at'] = now + get_finalization_reconcile_stale_after()
    transaction.set(job_ref, job)
    transaction.update(
        conversation_ref,
        {
            'status': 'processing',
            'finalization_job_id': job_id,
            'finalization_revision': revision,
            'finalization_status': status,
        },
    )
    intent = _intent_from_job(job_id, job)
    intent['newly_created'] = True
    return intent


def create_or_get_finalization_intent(
    uid: str,
    conversation_id: str,
    *,
    requires_byok: bool,
    finalization_admission: Callable[[Mapping[str, Any]], FinalizationAdmission],
    firestore_client: Any = None,
) -> FinalizationIntent:
    client = _client(firestore_client)
    conversation_ref = _conversation_ref(client, uid, conversation_id)
    transaction = client.transaction()
    transactional = firestore.transactional(_create_or_get_finalization_intent_txn)
    return transactional(
        transaction,
        conversation_ref,
        client.collection(FINALIZATION_JOBS_COLLECTION),
        uid,
        conversation_id,
        requires_byok,
        finalization_admission,
        _now(),
    )


def _resume_blocked_byok_job_txn(transaction: Any, job_ref: Any, now: datetime) -> FinalizationIntent:
    snapshot = job_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return {
            'job_id': None,
            'status': 'missing',
            'dispatch_generation': None,
            'requires_byok': False,
            'fanout_key': None,
        }
    job = snapshot.to_dict() or {}
    if job.get('status') == 'blocked_byok' and job.get('requires_byok'):
        transaction.update(
            job_ref,
            {
                'status': 'queued',
                'updated_at': now,
                'last_byok_resume_at': now,
                # BYOK jobs must only be resumed by the live pusher session,
                # never by the credential-free Cloud Tasks reconciler.
                'reconcile_after_at': firestore.DELETE_FIELD,
            },
        )
        job['status'] = 'queued'
    return _intent_from_job(snapshot.id, job)


def resume_blocked_byok_job_for_live_session(job_id: str, *, firestore_client: Any = None) -> FinalizationIntent:
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_resume_blocked_byok_job_txn)
    return transactional(transaction, _job_ref(client, job_id), _now())


def _claim_finalization_job_txn(
    transaction: Any,
    job_ref: Any,
    dispatch_generation: int,
    allow_byok: bool,
    lease_seconds: int,
    now: datetime,
    expected_uid: str | None = None,
    expected_conversation_id: str | None = None,
) -> FinalizationClaim:
    snapshot = job_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return _claim_result('missing')
    job = snapshot.to_dict() or {}
    status = str(job.get('status') or '')
    if expected_uid is not None and job.get('uid') != expected_uid:
        return _claim_result('identity_mismatch')
    if expected_conversation_id is not None and job.get('conversation_id') != expected_conversation_id:
        return _claim_result('identity_mismatch')
    if status == 'completed' and job.get('finalization_outcome') == 'fenced':
        return _claim_result('fenced')
    if status in TERMINAL_JOB_STATUSES:
        return _claim_result(status)
    if bool(job.get('requires_byok')) and not allow_byok:
        return _claim_result('blocked_byok')
    if status == 'blocked_byok':
        return _claim_result('blocked_byok')
    if int(job.get('dispatch_generation') or 1) != dispatch_generation:
        return _claim_result('stale_generation')
    if status == 'leased':
        lease_expires_at = job.get('lease_expires_at')
        if isinstance(lease_expires_at, datetime) and lease_expires_at > now:
            return _claim_result('leased')
    if status not in ('queued', 'leased'):
        return _claim_result('not_actionable')

    lease_epoch = int(job.get('lease_epoch') or 0) + 1
    lease_expires_at = now + timedelta(seconds=lease_seconds)
    attempt_count = int(job.get('attempt_count') or 0) + 1

    transaction.update(
        job_ref,
        {
            'status': 'leased',
            'leased_at': now,
            'lease_expires_at': lease_expires_at,
            # A lease epoch fences a worker that resumes after another worker
            # has reclaimed its expired lease. Terminal writes must present it.
            'lease_epoch': lease_epoch,
            'reconcile_after_at': (firestore.DELETE_FIELD if bool(job.get('requires_byok')) else lease_expires_at),
            'updated_at': now,
            # The claimer owns the attempt budget: an inline (pusher) worker has
            # no Cloud Tasks retry count to fence its terminal attempt with.
            'attempt_count': attempt_count,
        },
    )
    created_at = job.get('created_at')
    accepted_at_epoch_seconds = created_at.timestamp() if isinstance(created_at, datetime) else None
    return _claim_result('claimed', lease_epoch, attempt_count, accepted_at_epoch_seconds)


def claim_finalization_job(
    job_id: str,
    dispatch_generation: int,
    *,
    allow_byok: bool = False,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    expected_uid: str | None = None,
    expected_conversation_id: str | None = None,
    firestore_client: Any = None,
) -> FinalizationClaim:
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_claim_finalization_job_txn)
    return transactional(
        transaction,
        _job_ref(client, job_id),
        dispatch_generation,
        allow_byok,
        lease_seconds,
        _now(),
        expected_uid,
        expected_conversation_id,
    )


def _mark_finalization_completed_txn(
    transaction: Any, job_ref: Any, dispatch_generation: int, lease_epoch: int, now: datetime
) -> bool:
    snapshot = job_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return False
    job = snapshot.to_dict() or {}
    if job.get('status') == 'completed':
        return int(job.get('lease_epoch') or 0) == lease_epoch
    if not _is_current_lease(job, dispatch_generation, lease_epoch):
        return False
    if job.get('fanout_status') != 'completed':
        return False
    transaction.update(
        job_ref,
        {
            'status': 'completed',
            'completed_at': now,
            'updated_at': now,
            'lease_expires_at': now,
            'reconcile_after_at': firestore.DELETE_FIELD,
            'last_failure_code': None,
        },
    )
    return True


def mark_finalization_completed(
    job_id: str, dispatch_generation: int, lease_epoch: int, *, firestore_client: Any = None
) -> bool:
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_mark_finalization_completed_txn)
    return transactional(transaction, _job_ref(client, job_id), dispatch_generation, lease_epoch, _now())


def _mark_finalization_fenced_txn(
    transaction: Any, job_ref: Any, dispatch_generation: int, lease_epoch: int, now: datetime
) -> bool:
    """Terminally complete a current lease that was fenced before fanout.

    A discard or newer lifecycle generation can win after the job lease was
    acquired. That is a successful no-fanout terminal outcome, not a retryable
    processing failure. It must remain distinct from normal completion so a
    replay cannot mistake it for a delivered external integration.
    """
    snapshot = job_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return False
    job = snapshot.to_dict() or {}
    if job.get('status') == 'completed':
        return job.get('finalization_outcome') == 'fenced' and int(job.get('lease_epoch') or 0) == lease_epoch
    if not _is_current_lease(job, dispatch_generation, lease_epoch):
        return False
    if job.get('fanout_status') not in (None, 'pending'):
        return False
    transaction.update(job_ref, _fenced_finalization_update(now))
    return True


def mark_finalization_fenced(
    job_id: str, dispatch_generation: int, lease_epoch: int, *, firestore_client: Any = None
) -> bool:
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_mark_finalization_fenced_txn)
    return transactional(transaction, _job_ref(client, job_id), dispatch_generation, lease_epoch, _now())


def _fanout_key(job: dict[str, Any]) -> str:
    key = job.get('fanout_key')
    if isinstance(key, str) and key:
        return key
    # Backfill jobs created before the durable fanout boundary on their first
    # retry. The key is deterministic per immutable finalization revision.
    return f"conversation:{job.get('conversation_id', '')}:finalization:{int(job.get('finalization_revision') or 1)}"


def _fenced_finalization_update(now: datetime) -> dict[str, Any]:
    """Return the terminal no-fanout state shared by every fencing boundary."""
    return {
        'status': 'completed',
        'completed_at': now,
        'updated_at': now,
        'lease_expires_at': now,
        'reconcile_after_at': firestore.DELETE_FIELD,
        'last_failure_code': None,
        'finalization_outcome': 'fenced',
        'fanout_status': 'fenced',
        'fanout_fenced_at': now,
    }


def _fanout_claim(status: str, fanout_key: str | None) -> FinalizationFanoutClaim:
    return {'status': status, 'fanout_key': fanout_key}


def _conversation_admits_fanout(conversation: Mapping[str, Any], job: Mapping[str, Any], job_id: str) -> bool:
    """Require the immutable job binding to still name a completed conversation."""
    if conversation.get('discarded') or conversation.get('status') != 'completed':
        return False
    if conversation.get('finalization_job_id') != job_id:
        return False
    try:
        return int(conversation.get('finalization_revision') or 0) == int(job.get('finalization_revision') or 0)
    except (TypeError, ValueError):
        return False


def _claim_finalization_fanout_txn(
    transaction: Any,
    job_ref: Any,
    dispatch_generation: int,
    lease_epoch: int,
    now: datetime,
    conversation_ref_for_job: Callable[[str, str], Any],
) -> FinalizationFanoutClaim:
    """Claim fanout only if this job still owns the completed conversation.

    Reading the conversation in this Firestore transaction makes a concurrent
    discard or newer finalization revision retry the transaction before the
    fanout lease can commit.  The losing state is terminally fenced here,
    rather than leaving a retryable leased job for either worker to replay.
    """
    snapshot = job_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return _fanout_claim('missing', None)
    job = snapshot.to_dict() or {}
    fanout_key = _fanout_key(job)
    if job.get('fanout_status') == 'completed':
        return _fanout_claim('completed', fanout_key)
    if not _is_current_lease(job, dispatch_generation, lease_epoch):
        return _fanout_claim('lease_conflict', fanout_key)

    uid = job.get('uid')
    conversation_id = job.get('conversation_id')
    if not isinstance(uid, str) or not uid or not isinstance(conversation_id, str) or not conversation_id:
        transaction.update(job_ref, _fenced_finalization_update(now))
        return _fanout_claim('fenced', fanout_key)

    conversation_ref = conversation_ref_for_job(uid, conversation_id)
    conversation_snapshot = conversation_ref.get(transaction=transaction)
    conversation = conversation_snapshot.to_dict() if getattr(conversation_snapshot, 'exists', False) else None
    if not isinstance(conversation, Mapping) or not _conversation_admits_fanout(conversation, job, job_ref.id):
        transaction.update(job_ref, _fenced_finalization_update(now))
        return _fanout_claim('fenced', fanout_key)

    transaction.update(
        job_ref,
        {
            'fanout_key': fanout_key,
            'fanout_status': 'leased',
            'fanout_lease_epoch': lease_epoch,
            'fanout_started_at': now,
            'updated_at': now,
        },
    )
    return _fanout_claim('claimed', fanout_key)


def claim_finalization_fanout(
    job_id: str,
    dispatch_generation: int,
    lease_epoch: int,
    *,
    firestore_client: Any = None,
) -> FinalizationFanoutClaim:
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_claim_finalization_fanout_txn)
    return transactional(
        transaction,
        _job_ref(client, job_id),
        dispatch_generation,
        lease_epoch,
        _now(),
        lambda uid, conversation_id: _conversation_ref(client, uid, conversation_id),
    )


def _mark_finalization_fanout_completed_txn(
    transaction: Any,
    job_ref: Any,
    dispatch_generation: int,
    lease_epoch: int,
    now: datetime,
) -> bool:
    snapshot = job_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return False
    job = snapshot.to_dict() or {}
    if job.get('fanout_status') == 'completed':
        return int(job.get('fanout_lease_epoch') or 0) == lease_epoch
    if not _is_current_lease(job, dispatch_generation, lease_epoch):
        return False
    transaction.update(
        job_ref,
        {
            'fanout_status': 'completed',
            'fanout_completed_at': now,
            'updated_at': now,
        },
    )
    return True


def mark_finalization_fanout_completed(
    job_id: str,
    dispatch_generation: int,
    lease_epoch: int,
    *,
    firestore_client: Any = None,
) -> bool:
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_mark_finalization_fanout_completed_txn)
    return transactional(transaction, _job_ref(client, job_id), dispatch_generation, lease_epoch, _now())


def _mark_finalization_retryable_txn(
    transaction: Any, job_ref: Any, dispatch_generation: int, lease_epoch: int, failure_code: str, now: datetime
) -> bool:
    snapshot = job_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return False
    job = snapshot.to_dict() or {}
    if not _is_current_lease(job, dispatch_generation, lease_epoch):
        return False
    transaction.update(
        job_ref,
        {
            'status': 'queued',
            'updated_at': now,
            'lease_expires_at': now,
            'reconcile_after_at': (
                firestore.DELETE_FIELD
                if bool(job.get('requires_byok'))
                else now + get_finalization_reconcile_stale_after()
            ),
            'last_failure_code': failure_code,
        },
    )
    return True


def mark_finalization_retryable(
    job_id: str,
    dispatch_generation: int,
    lease_epoch: int,
    failure_code: str = 'processing_failed',
    *,
    firestore_client: Any = None,
) -> bool:
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_mark_finalization_retryable_txn)
    return transactional(transaction, _job_ref(client, job_id), dispatch_generation, lease_epoch, failure_code, _now())


def _mark_finalization_dead_letter_txn(
    transaction: Any, job_ref: Any, dispatch_generation: int, lease_epoch: int, retry_count: int, now: datetime
) -> bool:
    snapshot = job_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return False
    job = snapshot.to_dict() or {}
    if not _is_current_lease(job, dispatch_generation, lease_epoch):
        return False
    transaction.update(
        job_ref,
        {
            'status': 'dead_letter',
            'updated_at': now,
            'terminal_at': now,
            'lease_expires_at': now,
            'reconcile_after_at': firestore.DELETE_FIELD,
            'task_retry_count': retry_count,
            'last_failure_code': 'final_attempt_failed',
        },
    )
    return True


def mark_finalization_dead_letter(
    job_id: str, dispatch_generation: int, lease_epoch: int, retry_count: int, *, firestore_client: Any = None
) -> bool:
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_mark_finalization_dead_letter_txn)
    return transactional(transaction, _job_ref(client, job_id), dispatch_generation, lease_epoch, retry_count, _now())


def get_finalization_job(job_id: str, *, firestore_client: Any = None) -> dict[str, Any] | None:
    snapshot = _job_ref(_client(firestore_client), job_id).get()
    if not getattr(snapshot, 'exists', False):
        return None
    return snapshot.to_dict() or {}


def _claim_finalization_replay_txn(
    transaction: Any, job_ref: Any, stale_after: timedelta, now: datetime
) -> FinalizationIntent:
    snapshot = job_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return {
            'job_id': None,
            'status': 'missing',
            'dispatch_generation': None,
            'requires_byok': False,
            'fanout_key': None,
        }
    job = snapshot.to_dict() or {}
    status = str(job.get('status') or '')
    if status == 'blocked_byok' or status in TERMINAL_JOB_STATUSES:
        return _intent_from_job(snapshot.id, job)
    if status == 'leased':
        lease_expires_at = job.get('lease_expires_at')
        if isinstance(lease_expires_at, datetime) and lease_expires_at > now:
            return _intent_from_job(snapshot.id, job)
    if status == 'queued':
        dispatch_requested_at = job.get('dispatch_requested_at')
        if isinstance(dispatch_requested_at, datetime) and dispatch_requested_at > now - stale_after:
            return _intent_from_job(snapshot.id, job)
    if status not in ('queued', 'leased'):
        return _intent_from_job(snapshot.id, job)

    generation = int(job.get('dispatch_generation') or 1) + 1
    transaction.update(
        job_ref,
        {
            'status': 'queued',
            'dispatch_generation': generation,
            'dispatch_requested_at': now,
            'updated_at': now,
            'lease_expires_at': now,
            'reconcile_after_at': now + stale_after,
        },
    )
    job['status'] = 'queued'
    job['dispatch_generation'] = generation
    return _intent_from_job(snapshot.id, job)


def claim_finalization_replay(
    job_id: str, *, stale_after: timedelta, firestore_client: Any = None
) -> FinalizationIntent:
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_claim_finalization_replay_txn)
    return transactional(transaction, _job_ref(client, job_id), stale_after, _now())


def get_finalization_replay_candidates(*, limit: int = 100, firestore_client: Any = None) -> list[dict[str, Any]]:
    """Return a bounded server-side page of jobs whose replay delay elapsed."""
    client = _client(firestore_client)
    result: list[dict[str, Any]] = []
    collection = client.collection(FINALIZATION_JOBS_COLLECTION)
    query = collection.where('reconcile_after_at', '<=', _now()).limit(max(1, min(limit, 100)))
    for snapshot in query.stream():
        job = snapshot.to_dict() or {}
        if job.get('status') in {'queued', 'leased'}:
            result.append(job | {'job_id': snapshot.id})
    return result


def get_finalization_job_summary(*, firestore_client: Any = None) -> dict[str, float | int]:
    """Privacy-safe aggregate counts plus a bounded overdue-age sample."""
    client = _client(firestore_client)
    now = _now()
    collection = client.collection(FINALIZATION_JOBS_COLLECTION)
    counts: dict[str, int] = {}
    for status in (*NONTERMINAL_JOB_STATUSES, *TERMINAL_JOB_STATUSES):
        aggregate = collection.where('status', '==', status).count().get()
        counts[status] = int(aggregate[0][0].value) if aggregate and aggregate[0] else 0

    oldest_age_seconds = 0.0
    # The bounded due page prevents historical terminal rows from making the
    # periodic metric collection an ever-growing Firestore scan.
    for snapshot in collection.where('reconcile_after_at', '<=', now).limit(100).stream():
        created_at = (snapshot.to_dict() or {}).get('created_at')
        if isinstance(created_at, datetime):
            oldest_age_seconds = max(oldest_age_seconds, max(0.0, (now - created_at).total_seconds()))
    return {
        'queued': counts['queued'],
        'leased': counts['leased'],
        'blocked_byok': counts['blocked_byok'],
        'completed': counts['completed'],
        'dead_letter': counts['dead_letter'],
        'oldest_nonterminal_age_seconds': oldest_age_seconds,
    }
