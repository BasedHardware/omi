"""Firestore outbox and lease state for durable conversation finalization.

Cloud Tasks is deliberately only a wake-up mechanism.  The durable source of
truth is one Firestore job per ``(uid, conversation_id, finalization_revision)``.
No transcript, credential, request header, or raw exception is stored here.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Literal, Mapping, TypedDict

from google.cloud import firestore

from database import conversations as conversations_db
from database._client import document_id_from_seed, get_firestore_client
from database.firestore_transaction_retry import run_with_transaction_contention_retry

CONVERSATIONS_COLLECTION = 'conversations'
FINALIZATION_JOBS_COLLECTION = 'conversation_finalization_jobs'

FinalizationJobStatus = Literal['queued', 'leased', 'completed', 'dead_letter', 'blocked_byok']
TERMINAL_JOB_STATUSES = frozenset({'completed', 'dead_letter'})
NONTERMINAL_JOB_STATUSES = frozenset({'queued', 'leased', 'blocked_byok'})
DEFAULT_LEASE_SECONDS = 1500
DEFAULT_RECONCILE_STALE_SECONDS = 300
# Conservative: the synchronous legacy route admits processing with no durable
# job, and its request thread is not killed by the HTTP timeout, so the orphan
# window must exceed any plausible live synchronous process_conversation run.
DEFAULT_ORPHAN_RECONCILE_STALE_SECONDS = 900


class FinalizationIntent(TypedDict):
    job_id: str | None
    status: str
    dispatch_generation: int | None
    requires_byok: bool
    fanout_key: str | None
    created: bool


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
    created_at: datetime | None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_finalization_reconcile_stale_after() -> timedelta:
    """Return the bounded delay before a missed handoff becomes replayable."""
    try:
        seconds = int(os.getenv('LISTEN_FINALIZATION_RECONCILE_STALE_SECONDS', str(DEFAULT_RECONCILE_STALE_SECONDS)))
    except ValueError:
        seconds = DEFAULT_RECONCILE_STALE_SECONDS
    return timedelta(seconds=max(30, seconds))


def get_stale_processing_orphan_after() -> timedelta:
    """Return the bounded delay before a bare-`processing` row is a crash orphan.

    Bounds the authoritative, server-owned admission fence
    (``processing_admitted_at``), never caller-controlled ``created_at``. Distinct
    from the durable-job replay window (which a lease already bounds); this path
    owns no lease, so the value is clamped to a conservative floor (300s, longer
    than any plausible live synchronous ``process_conversation`` run) and a
    one-day ceiling so an operator misconfiguration cannot defer recovery for an
    unbounded period. Classified as a reliability recovery knob; deploy default
    is unset so the floor applies.
    """
    try:
        seconds = int(
            os.getenv('LISTEN_FINALIZATION_ORPHAN_STALE_SECONDS', str(DEFAULT_ORPHAN_RECONCILE_STALE_SECONDS))
        )
    except ValueError:
        seconds = DEFAULT_ORPHAN_RECONCILE_STALE_SECONDS
    return timedelta(seconds=min(86_400, max(300, seconds)))


def _claim_result(
    status: str,
    lease_epoch: int | None = None,
    attempt_count: int = 0,
    created_at: datetime | None = None,
) -> FinalizationClaim:
    return {'status': status, 'lease_epoch': lease_epoch, 'attempt_count': attempt_count, 'created_at': created_at}


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


def _uid_from_conversation_path(path: str) -> str | None:
    """Return the uid from a ``users/{uid}/conversations/{conversation_id}`` path."""
    parts = path.split('/')
    if len(parts) == 4 and parts[0] == 'users' and parts[2] == CONVERSATIONS_COLLECTION:
        return parts[1]
    return None


def _job_ref(client: Any, job_id: str) -> Any:
    return client.collection(FINALIZATION_JOBS_COLLECTION).document(job_id)


def _job_id(uid: str, conversation_id: str, revision: int) -> str:
    return document_id_from_seed(f'listen-finalization:{uid}:{conversation_id}:{revision}')


def _intent_from_job(job_id: str, data: dict[str, Any], *, created: bool = False) -> FinalizationIntent:
    return {
        'job_id': job_id,
        'status': str(data.get('status') or 'queued'),
        'dispatch_generation': int(data.get('dispatch_generation') or 1),
        'requires_byok': bool(data.get('requires_byok')),
        'fanout_key': data.get('fanout_key') if isinstance(data.get('fanout_key'), str) else None,
        'created': created,
    }


def _no_finalization_intent(status: str) -> FinalizationIntent:
    return {
        'job_id': None,
        'status': status,
        'dispatch_generation': None,
        'requires_byok': False,
        'fanout_key': None,
        'created': False,
    }


def _conversation_has_finalization_content(
    uid: str, conversation: Mapping[str, Any], conversation_ref: Any, transaction: Any
) -> bool:
    """Read current and pre-marker photo content within the admission transaction."""
    if conversations_db.raw_conversation_has_content(uid, dict(conversation)):
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
    *,
    force_process: bool = False,
    extra_updates: Mapping[str, Any] | None = None,
) -> FinalizationIntent:
    """Persist finalization ownership before any pusher or task handoff."""
    conversation_snapshot = conversation_ref.get(transaction=transaction)
    if not getattr(conversation_snapshot, 'exists', False):
        return _no_finalization_intent('missing')

    conversation = conversation_snapshot.to_dict() or {}
    if conversation.get('deferred'):
        return _no_finalization_intent('deferred')
    if not _conversation_has_finalization_content(uid, conversation, conversation_ref, transaction):
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
        # REST finalization has historically forced enrichment while the listen
        # pipeline retains its existing default. Persist the choice with the
        # immutable finalization generation so a replay cannot change it.
        'force_process': force_process,
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
    conversation_updates = dict(extra_updates or {})
    # Lifecycle fields are authoritative to this outbox transaction. Callers
    # may atomically persist request metadata (for example calendar context),
    # but cannot override the accepted generation's identity or status.
    conversation_updates.update(
        {
            'status': 'processing',
            'finalization_job_id': job_id,
            'finalization_revision': revision,
            'finalization_status': status,
        }
    )
    transaction.update(conversation_ref, conversation_updates)
    return _intent_from_job(job_id, job, created=True)


def create_or_get_finalization_intent(
    uid: str,
    conversation_id: str,
    *,
    requires_byok: bool,
    finalization_admission: Callable[[Mapping[str, Any]], FinalizationAdmission],
    force_process: bool = False,
    extra_updates: Mapping[str, Any] | None = None,
    firestore_client: Any = None,
) -> FinalizationIntent:
    client = _client(firestore_client)
    conversation_ref = _conversation_ref(client, uid, conversation_id)
    jobs_collection = client.collection(FINALIZATION_JOBS_COLLECTION)

    def create_intent_in_transaction(transaction: Any) -> FinalizationIntent:
        # The Firestore SDK's transactional wrapper retains retry state. Build
        # it for this outer attempt so concurrent REST finalizers always get a
        # fresh transaction and wrapper after read-time contention.
        transactional = firestore.transactional(_create_or_get_finalization_intent_txn)
        return transactional(
            transaction,
            conversation_ref,
            jobs_collection,
            uid,
            conversation_id,
            requires_byok,
            finalization_admission,
            _now(),
            force_process=force_process,
            extra_updates=extra_updates,
        )

    return run_with_transaction_contention_retry(
        client.transaction,
        create_intent_in_transaction,
        operation_name='conversation_finalization_intent',
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
            'created': False,
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
    return _claim_result(
        'claimed',
        lease_epoch,
        attempt_count,
        created_at if isinstance(created_at, datetime) else None,
    )


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
    transaction: Any,
    job_ref: Any,
    dispatch_generation: int,
    lease_epoch: int,
    retry_count: int,
    now: datetime,
    conversation_ref_for_job: Callable[[str, str], Any] | None = None,
) -> bool:
    snapshot = job_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return False
    job = snapshot.to_dict() or {}
    if not _is_current_lease(job, dispatch_generation, lease_epoch):
        return False
    conversation_ref = None
    conversation = None
    uid = job.get('uid')
    conversation_id = job.get('conversation_id')
    if (
        conversation_ref_for_job is not None
        and isinstance(uid, str)
        and uid
        and isinstance(conversation_id, str)
        and conversation_id
    ):
        # Read the bound conversation before the first transaction write. A
        # final worker failure must close its still-current processing
        # generation atomically with dead-lettering the job; otherwise a crash
        # between independent writes strands the customer on processing.
        conversation_ref = conversation_ref_for_job(uid, conversation_id)
        conversation_snapshot = conversation_ref.get(transaction=transaction)
        conversation = conversation_snapshot.to_dict() if getattr(conversation_snapshot, 'exists', False) else None
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
    if (
        conversation_ref is not None
        and isinstance(conversation, Mapping)
        and conversation.get('status') == 'processing'
        and not conversation.get('discarded')
        and conversation.get('finalization_job_id') == job_ref.id
        and conversation.get('finalization_revision') == job.get('finalization_revision')
    ):
        transaction.update(
            conversation_ref,
            {
                'status': 'failed',
                'discarded': True,
                'finalization_status': 'dead_letter',
            },
        )
    return True


def mark_finalization_dead_letter(
    job_id: str, dispatch_generation: int, lease_epoch: int, retry_count: int, *, firestore_client: Any = None
) -> bool:
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_mark_finalization_dead_letter_txn)
    return transactional(
        transaction,
        _job_ref(client, job_id),
        dispatch_generation,
        lease_epoch,
        retry_count,
        _now(),
        lambda uid, conversation_id: _conversation_ref(client, uid, conversation_id),
    )


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
            'created': False,
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


def get_stale_processing_orphan_candidates(
    *,
    stale_after: timedelta,
    limit: int = 100,
    max_scan: int = 2000,
    resume_after_path: str | None = None,
    firestore_client: Any = None,
) -> dict[str, Any]:
    """Return a bounded window of actionable bare-`processing` conversations.

    Eligibility is bounded by the authoritative, server-owned admission fence
    ``processing_admitted_at`` — never caller-controlled ``created_at``. A bare
    ``processing`` row (no ``finalization_job_id``) that is not ``deferred`` is:

    * returned with ``legacy=False`` when its admission age exceeds
      ``stale_after`` (a genuine crash orphan ready for exactly one terminal), and
    * returned with ``legacy=True`` when it predates the admission stamp (a
      stranded legacy row the caller must migrate by stamping the fence, never
      terminalized on first sight).

    Fresh admissions under ``stale_after`` are filtered out and never returned.

    The cross-user sweep is a single-equality ``collection_group`` query on
    ``status == 'processing'``. A single-field equality query is served by
    Firestore's automatic single-field index, so no composite index is registered
    or deployed and the query is deliberately not collection-scoped. Because
    client-side exclusion (deferred / durable-job-owned / fresh / legacy) happens
    after the page cap, the sweep pages with a ``start_after`` cursor so a stable
    first page of excluded rows cannot starve a later eligible orphan.

    Eventual discovery is guaranteed by a **persisted, rotated sweep cursor**.
    Each invocation resumes from ``resume_after_path`` (the last-examined row) and
    examines at most ``max_scan`` rows; when the collection is exhausted the
    cursor wraps (``exhausted=True``), so a stable excluded prefix larger than any
    per-invocation bound cannot permanently hide a later orphan — repeated bounded
    sweeps cover the whole collection. The caller persists ``resume_after_path``
    (or ``None`` once ``exhausted``) between invocations.

    Returns ``{'candidates', 'resume_after_path', 'exhausted'}``.
    """
    client = _client(firestore_client)
    cutoff = _now() - stale_after
    page_size = max(1, min(limit, 100))
    collected: list[dict[str, Any]] = []
    scanned = 0
    last_path: str | None = None
    exhausted = False

    cursor_snapshot: Any = None
    if resume_after_path:
        fetched = client.document(resume_after_path).get()
        if getattr(fetched, 'exists', False):
            cursor_snapshot = fetched  # resume the collection-group scan
        # A vanished cursor document wraps the sweep back to the top (safe re-scan).

    while len(collected) < limit and scanned < max_scan:
        query = client.collection_group(CONVERSATIONS_COLLECTION).where(
            filter=firestore.FieldFilter('status', '==', 'processing')
        )
        query = query.limit(page_size)
        if cursor_snapshot is not None:
            query = query.start_after(cursor_snapshot)
        page = list(query.stream())
        if not page:
            exhausted = True  # reached the tail of the collection from the cursor
            break
        for snapshot in page:
            scanned += 1
            if scanned > max_scan:
                break
            last_path = snapshot.reference.path
            uid = _uid_from_conversation_path(snapshot.reference.path)
            if uid is None:
                continue
            data = snapshot.to_dict() or {}
            if data.get('deferred') or data.get('finalization_job_id'):
                continue
            admitted_at = data.get('processing_admitted_at')
            if isinstance(admitted_at, datetime):
                if admitted_at > cutoff:
                    continue  # fresh admission still under the conservative threshold
                collected.append(
                    {'uid': uid, 'conversation_id': snapshot.id, 'processing_admitted_at': admitted_at, 'legacy': False}
                )
            else:
                collected.append(
                    {'uid': uid, 'conversation_id': snapshot.id, 'processing_admitted_at': None, 'legacy': True}
                )
            if len(collected) >= limit:
                break
        if scanned > max_scan:
            break  # bounded work for this invocation; the cursor persists progress
        if len(page) < page_size:
            exhausted = True  # partial page => reached the tail
            break
        cursor_snapshot = page[-1]

    return {
        'candidates': collected,
        'resume_after_path': None if exhausted else last_path,
        'exhausted': exhausted,
    }


STALE_PROCESSING_SWEEP_STATE_COLLECTION = 'conversation_recovery_state'
STALE_PROCESSING_SWEEP_STATE_DOC = 'stale_processing_sweep'


def get_stale_processing_sweep_cursor(*, firestore_client: Any = None) -> dict[str, Any]:
    """Return the persisted sweep cursor and its CAS generation.

    Returns ``{'resume_after_path': str | None, 'generation': int}``. The
    generation is the compare-and-swap token a caller must hold to advance the
    cursor; ``0`` when the document has never been written. Multiple backend-listen
    pods share this single cursor, so the generation prevents a delayed scan from
    rewinding another pod's advance.
    """
    client = _client(firestore_client)
    snapshot = (
        client.collection(STALE_PROCESSING_SWEEP_STATE_COLLECTION).document(STALE_PROCESSING_SWEEP_STATE_DOC).get()
    )
    if not getattr(snapshot, 'exists', False):
        return {'resume_after_path': None, 'generation': 0}
    data = snapshot.to_dict() or {}
    path = data.get('resume_after_path')
    return {
        'resume_after_path': path if isinstance(path, str) else None,
        'generation': int(data.get('generation', 0)),
    }


def _advance_stale_processing_sweep_cursor_txn(
    transaction: Any, doc_ref: Any, expected_generation: int, new_resume_after_path: str | None, now: datetime
) -> bool:
    """CAS-update the sweep cursor inside a Firestore transaction.

    Returns ``True`` only when the persisted generation still equals
    ``expected_generation`` — proving no other pod advanced the cursor between
    this pod's read and write. On success the cursor advances and the generation
    bumps, so a delayed competing writer holding the old generation is fenced out
    (``False``) and cannot rewind progress.
    """
    snapshot = doc_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        current_generation = 0
    else:
        current_generation = int((snapshot.to_dict() or {}).get('generation', 0))
    if current_generation != expected_generation:
        return False
    transaction.set(
        doc_ref,
        {'resume_after_path': new_resume_after_path, 'generation': current_generation + 1, 'updated_at': now},
    )
    return True


def advance_stale_processing_sweep_cursor(
    expected_generation: int, new_resume_after_path: str | None, *, firestore_client: Any = None
) -> bool:
    """Atomically advance the sweep cursor; ``None`` rotates the next sweep to the top.

    Returns ``False`` when another pod already advanced the cursor (the CAS
    generation changed). The caller's sweep work is still valid — the exact-
    generation fence in ``complete_orphan_conversation`` prevents double-terminalization
    — but the cursor does not advance from this pod's perspective, so the next sweep
    safely re-scans the same window.
    """
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_advance_stale_processing_sweep_cursor_txn)
    return transactional(
        transaction,
        client.collection(STALE_PROCESSING_SWEEP_STATE_COLLECTION).document(STALE_PROCESSING_SWEEP_STATE_DOC),
        expected_generation,
        new_resume_after_path,
        _now(),
    )


def _stamp_processing_admission_if_absent_txn(transaction: Any, conversation_ref: Any, now: datetime) -> bool:
    """Server-owned migration: stamp the admission fence on a legacy processing row.

    Returns ``True`` only when a bare ``processing`` row lacking a valid
    ``processing_admitted_at`` was stamped with ``now``. A row already stamped, in
    any other lifecycle state, or absent is left untouched. The stamp is the sole
    authority the orphan sweep trusts; it never terminalizes a row here.
    """
    snapshot = conversation_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return False
    data = snapshot.to_dict() or {}
    if data.get('status') != 'processing':
        return False
    if isinstance(data.get('processing_admitted_at'), datetime):
        return False
    transaction.update(conversation_ref, {'processing_admitted_at': now})
    return True


def stamp_processing_admission_if_absent(uid: str, conversation_id: str, *, firestore_client: Any = None) -> bool:
    """Stamp the authoritative admission fence on a legacy processing conversation."""
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_stamp_processing_admission_if_absent_txn)
    return transactional(transaction, _conversation_ref(client, uid, conversation_id), _now())


def _complete_orphan_conversation_txn(
    transaction: Any, conversation_ref: Any, expected_admitted_at: datetime | None, now: datetime
) -> bool:
    """Terminalize exactly the scanned orphan generation, fencing every live owner.

    Verified immediately before the write, inside the transaction:
    * still ``processing`` (not already completed/discarded/merging),
    * not ``deferred`` (a desktop lazy row that intentionally stays on processing),
    * no ``finalization_job_id`` (a finalizer attached durable ownership after
      discovery), and
    * ``processing_admitted_at`` still equals the scanned generation (the processor
      has not renewed its lease or been re-admitted).

    Only when every assumption still holds is the row moved to ``completed``. Any
    divergence is an expected CAS fencing (``False``), never a terminalization of
    live or durable-owned work.
    """
    del now  # the terminal write carries no timestamp; the fence is the generation
    snapshot = conversation_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return False
    data = snapshot.to_dict() or {}
    if data.get('status') != 'processing':
        return False
    if data.get('discarded') or data.get('deferred') or data.get('finalization_job_id'):
        return False
    admitted_at = data.get('processing_admitted_at')
    if not isinstance(admitted_at, datetime) or admitted_at != expected_admitted_at:
        return False
    transaction.update(conversation_ref, {'status': 'completed'})
    return True


def complete_orphan_conversation(
    uid: str, conversation_id: str, *, expected_admitted_at: datetime | None, firestore_client: Any = None
) -> bool:
    """Close one crash orphan through the generation/ownership fence."""
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_complete_orphan_conversation_txn)
    return transactional(transaction, _conversation_ref(client, uid, conversation_id), expected_admitted_at, _now())


def _renew_processing_lease_txn(transaction: Any, conversation_ref: Any, now: datetime) -> bool:
    """Refresh the admission lease on a still-processing row owned by a live processor."""
    snapshot = conversation_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return False
    data = snapshot.to_dict() or {}
    if data.get('status') != 'processing' or data.get('discarded'):
        return False
    transaction.update(conversation_ref, {'processing_admitted_at': now})
    return True


def renew_processing_lease(uid: str, conversation_id: str, *, firestore_client: Any = None) -> bool:
    """Renew the server-owned admission lease so recovery cannot mistake a live processor for a crash."""
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_renew_processing_lease_txn)
    return transactional(transaction, _conversation_ref(client, uid, conversation_id), _now())


def _reacquire_deferred_processing_txn(transaction: Any, conversation_ref: Any, now: datetime) -> bool:
    """Atomically clear ``deferred`` and renew the admission lease.

    This eliminates the window between clearing ``deferred`` and the first
    heartbeat renewal where the orphan sweep could terminalize the row.  If
    the row is no longer ``processing`` or was discarded, the transition
    fails closed so a stale processor produces no derived side effects.
    """
    snapshot = conversation_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return False
    data = snapshot.to_dict() or {}
    if data.get('status') != 'processing' or data.get('discarded'):
        return False
    transaction.update(conversation_ref, {'deferred': False, 'processing_admitted_at': now})
    return True


def reacquire_deferred_processing(uid: str, conversation_id: str, *, firestore_client: Any = None) -> bool:
    """Atomically clear deferred and renew the admission lease in one transaction."""
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_reacquire_deferred_processing_txn)
    return transactional(transaction, _conversation_ref(client, uid, conversation_id), _now())


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
