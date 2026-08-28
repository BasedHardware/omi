"""Firestore outbox and lease state for durable conversation finalization.

Cloud Tasks is deliberately only a wake-up mechanism.  The durable source of
truth is one Firestore job per ``(uid, conversation_id, finalization_revision)``.
No transcript, credential, request header, or raw exception is stored here.
"""

from __future__ import annotations

import os
from hashlib import sha256
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Literal, Mapping, TypedDict

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from database import conversations as conversations_db
from database._client import document_id_from_seed, get_firestore_client
from database.firestore_transaction_retry import run_with_transaction_contention_retry
from database.firestore_index_registry import (
    FINALIZATION_OLDEST_NONTERMINAL_QUERY,
    MEETING_RECEIPTS_DUE_QUERY,
)

CONVERSATIONS_COLLECTION = 'conversations'
FINALIZATION_JOBS_COLLECTION = 'conversation_finalization_jobs'
# This projection starts at the first release that writes terminal outcomes.
# It intentionally does not backfill historical jobs: terminal writes for rows
# without this generation remain durable on the job itself but cannot move the
# new denominator.  Reading this fixed shard set is safe on every replica.
FINALIZATION_PROJECTION_COLLECTION = 'conversation_finalization_projection_shards'
FINALIZATION_PROJECTION_GENERATION = 'terminal-outcomes-v1'
FINALIZATION_PROJECTION_SHARD_COUNT = 16

FinalizationJobStatus = Literal['queued', 'leased', 'completed', 'dead_letter', 'blocked_byok']
TERMINAL_JOB_STATUSES = frozenset({'completed', 'dead_letter'})
NONTERMINAL_JOB_STATUSES = frozenset({'queued', 'leased', 'blocked_byok'})
DEFAULT_LEASE_SECONDS = 1500
DEFAULT_RECONCILE_STALE_SECONDS = 300
# Conservative: the synchronous legacy route admits processing with no durable
# job, and its request thread is not killed by the HTTP timeout, so the orphan
# window must exceed any plausible live synchronous process_conversation run.
DEFAULT_ORPHAN_RECONCILE_STALE_SECONDS = 900
# A BYOK job can only ever run inside a live pusher session that presents the
# user's request-scoped keys. Once that session is gone nothing owns the row:
# the Cloud Tasks worker refuses `requires_byok` jobs and the credential-free
# reconciler only selects rows carrying `reconcile_after_at`, which every BYOK
# transition deletes. Seven days is deliberately far longer than any plausible
# reconnect window.
DEFAULT_BYOK_ABANDONED_AFTER_SECONDS = 14 * 86_400
BYOK_ABANDONED_FAILURE_CODE = 'byok_session_abandoned'
MEETING_RECEIPT_SCHEMA_VERSION = 1
MEETING_RECEIPT_RECONCILE_AFTER = timedelta(minutes=10)


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


class ByokAbandonment(TypedDict):
    """Terminal disposition of one stranded BYOK finalization job.

    ``status`` is ``abandoned`` only when this call committed the terminal;
    ``fenced`` means an expected ownership CAS loss and ``missing`` an absent
    row.  ``conversation_outcome`` separates the two very different real shapes:
    ``closed`` (the bound conversation was still ``processing`` and this call
    ended its lifecycle) from ``already_terminal`` / ``unbound`` / ``missing``
    (the conversation was finalized by the inline pusher lane, or moved on, and
    the job row was pure orphaned bookkeeping).
    """

    status: str
    conversation_outcome: str


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


def get_byok_abandoned_after() -> timedelta:
    """Return the bounded age after which a stranded BYOK job is abandoned.

    Bounds the server-owned last-activity instant on the job. Clamped to a
    one-day floor, so a live session that legitimately reconnects always wins,
    and a 90-day ceiling, so an operator misconfiguration cannot defer the
    disposition of an unownable row for an unbounded period. Classified as a
    reliability recovery knob; the deploy default is unset, so the built-in
    14-day default applies.
    """
    try:
        seconds = int(
            os.getenv('LISTEN_FINALIZATION_BYOK_ABANDONED_SECONDS', str(DEFAULT_BYOK_ABANDONED_AFTER_SECONDS))
        )
    except ValueError:
        seconds = DEFAULT_BYOK_ABANDONED_AFTER_SECONDS
    return timedelta(seconds=min(90 * 86_400, max(86_400, seconds)))


def _claim_result(
    status: str,
    lease_epoch: int | None = None,
    attempt_count: int = 0,
    created_at: datetime | None = None,
) -> FinalizationClaim:
    return {
        'status': status,
        'lease_epoch': lease_epoch,
        'attempt_count': attempt_count,
        'created_at': created_at,
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


def _uid_from_conversation_path(path: str) -> str | None:
    """Return the uid from a ``users/{uid}/conversations/{conversation_id}`` path."""
    parts = path.split('/')
    if len(parts) == 4 and parts[0] == 'users' and parts[2] == CONVERSATIONS_COLLECTION:
        return parts[1]
    return None


def _job_ref(client: Any, job_id: str) -> Any:
    return client.collection(FINALIZATION_JOBS_COLLECTION).document(job_id)


def _projection_shard(job_id: str) -> int:
    """Choose a stable aggregate shard without exposing job identity in metrics."""
    return int.from_bytes(sha256(job_id.encode('utf-8')).digest()[:4], 'big') % FINALIZATION_PROJECTION_SHARD_COUNT


def _projection_shard_id(generation: str, shard: int) -> str:
    return f'{generation}-{shard:02d}'


def _projection_ref_for_job(projection_collection: Any, job: Mapping[str, Any]) -> Any | None:
    generation = job.get('projection_generation')
    shard = job.get('projection_shard')
    if not isinstance(generation, str) or not isinstance(shard, int):
        return None
    if generation != FINALIZATION_PROJECTION_GENERATION or not 0 <= shard < FINALIZATION_PROJECTION_SHARD_COUNT:
        return None
    return projection_collection.document(_projection_shard_id(generation, shard))


def _record_projection_delta(
    transaction: Any, projection_collection: Any | None, job: Mapping[str, Any], **deltas: int
) -> None:
    """Atomically add state deltas for an admitted projection generation.

    A terminal replay returns before this helper, and Firestore retries rerun
    the transaction against a fresh snapshot. Therefore each committed state
    transition contributes exactly once without a per-job metrics side record.
    """
    if projection_collection is None:
        return
    shard_ref = _projection_ref_for_job(projection_collection, job)
    if shard_ref is None:
        return
    fields: dict[str, Any] = {
        'generation': FINALIZATION_PROJECTION_GENERATION,
        'shard': int(job['projection_shard']),
    }
    fields.update({name: firestore.Increment(delta) for name, delta in deltas.items() if delta})
    if len(fields) == 2:
        return
    transaction.set(shard_ref, fields, merge=True)


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
    projection_collection: Any | None = None,
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
        'client_platform': conversation.get('client_platform'),
        # REST finalization has historically forced enrichment while the listen
        # pipeline retains its existing default. Persist the choice with the
        # immutable finalization generation so a replay cannot change it.
        'force_process': force_process,
        'fanout_key': admission['fanout_key'],
        'fanout_status': 'pending',
        'dispatch_generation': 1,
        'attempt_count': 0,
        'task_retry_count': 0,
        'projection_generation': FINALIZATION_PROJECTION_GENERATION,
        'projection_shard': _projection_shard(job_id),
        'created_at': now,
        'updated_at': now,
        'dispatch_requested_at': now,
    }
    if not requires_byok:
        job['reconcile_after_at'] = now + get_finalization_reconcile_stale_after()
    transaction.set(job_ref, job)
    _record_projection_delta(
        transaction,
        projection_collection,
        job,
        accepted=1,
        **({'blocked_byok': 1} if requires_byok else {'queued': 1}),
    )
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
    projection_collection = client.collection(FINALIZATION_PROJECTION_COLLECTION)

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
            projection_collection=projection_collection,
            force_process=force_process,
            extra_updates=extra_updates,
        )

    return run_with_transaction_contention_retry(
        client.transaction,
        create_intent_in_transaction,
        operation_name='conversation_finalization_intent',
    )


def _resume_blocked_byok_job_txn(
    transaction: Any, job_ref: Any, now: datetime, projection_collection: Any | None = None
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
        _record_projection_delta(transaction, projection_collection, job, blocked_byok=-1, queued=1)
        job['status'] = 'queued'
    return _intent_from_job(snapshot.id, job)


def resume_blocked_byok_job_for_live_session(job_id: str, *, firestore_client: Any = None) -> FinalizationIntent:
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_resume_blocked_byok_job_txn)
    return transactional(
        transaction,
        _job_ref(client, job_id),
        _now(),
        client.collection(FINALIZATION_PROJECTION_COLLECTION),
    )


def _claim_finalization_job_txn(
    transaction: Any,
    job_ref: Any,
    dispatch_generation: int,
    allow_byok: bool,
    lease_seconds: int,
    now: datetime,
    expected_uid: str | None = None,
    expected_conversation_id: str | None = None,
    projection_collection: Any | None = None,
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
    if status == 'queued':
        _record_projection_delta(transaction, projection_collection, job, queued=-1, leased=1)
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
        client.collection(FINALIZATION_PROJECTION_COLLECTION),
    )


def _mark_finalization_completed_txn(
    transaction: Any,
    job_ref: Any,
    dispatch_generation: int,
    lease_epoch: int,
    now: datetime,
    projection_collection: Any | None = None,
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
            'terminal_outcome': 'success',
            'updated_at': now,
            'lease_expires_at': now,
            'reconcile_after_at': firestore.DELETE_FIELD,
            'last_failure_code': None,
        },
    )
    _record_projection_delta(transaction, projection_collection, job, leased=-1, completed=1, success=1)
    return True


def mark_finalization_completed(
    job_id: str, dispatch_generation: int, lease_epoch: int, *, firestore_client: Any = None
) -> bool:
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_mark_finalization_completed_txn)
    return transactional(
        transaction,
        _job_ref(client, job_id),
        dispatch_generation,
        lease_epoch,
        _now(),
        client.collection(FINALIZATION_PROJECTION_COLLECTION),
    )


def _mark_finalization_fenced_txn(
    transaction: Any,
    job_ref: Any,
    dispatch_generation: int,
    lease_epoch: int,
    now: datetime,
    projection_collection: Any | None = None,
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
    _record_projection_delta(transaction, projection_collection, job, leased=-1, completed=1, stale=1)
    return True


def mark_finalization_fenced(
    job_id: str, dispatch_generation: int, lease_epoch: int, *, firestore_client: Any = None
) -> bool:
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_mark_finalization_fenced_txn)
    return transactional(
        transaction,
        _job_ref(client, job_id),
        dispatch_generation,
        lease_epoch,
        _now(),
        client.collection(FINALIZATION_PROJECTION_COLLECTION),
    )


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
        'terminal_outcome': 'stale',
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
    projection_collection: Any | None = None,
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
        _record_projection_delta(transaction, projection_collection, job, leased=-1, completed=1, stale=1)
        return _fanout_claim('fenced', fanout_key)

    conversation_ref = conversation_ref_for_job(uid, conversation_id)
    conversation_snapshot = conversation_ref.get(transaction=transaction)
    conversation = conversation_snapshot.to_dict() if getattr(conversation_snapshot, 'exists', False) else None
    if not isinstance(conversation, Mapping) or not _conversation_admits_fanout(conversation, job, job_ref.id):
        transaction.update(job_ref, _fenced_finalization_update(now))
        _record_projection_delta(transaction, projection_collection, job, leased=-1, completed=1, stale=1)
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
        client.collection(FINALIZATION_PROJECTION_COLLECTION),
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
    return transactional(
        transaction,
        _job_ref(client, job_id),
        dispatch_generation,
        lease_epoch,
        _now(),
    )


def _mark_finalization_retryable_txn(
    transaction: Any,
    job_ref: Any,
    dispatch_generation: int,
    lease_epoch: int,
    failure_code: str,
    now: datetime,
    projection_collection: Any | None = None,
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
    _record_projection_delta(transaction, projection_collection, job, leased=-1, queued=1)
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
    return transactional(
        transaction,
        _job_ref(client, job_id),
        dispatch_generation,
        lease_epoch,
        failure_code,
        _now(),
        client.collection(FINALIZATION_PROJECTION_COLLECTION),
    )


def _mark_finalization_dead_letter_txn(
    transaction: Any,
    job_ref: Any,
    dispatch_generation: int,
    lease_epoch: int,
    retry_count: int,
    now: datetime,
    conversation_ref_for_job: Callable[[str, str], Any] | None = None,
    projection_collection: Any | None = None,
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
            'terminal_outcome': 'failure',
            'lease_expires_at': now,
            'reconcile_after_at': firestore.DELETE_FIELD,
            'task_retry_count': retry_count,
            'last_failure_code': 'final_attempt_failed',
        },
    )
    _record_projection_delta(transaction, projection_collection, job, leased=-1, dead_letter=1, failure=1)
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
        client.collection(FINALIZATION_PROJECTION_COLLECTION),
    )


def get_finalization_job(job_id: str, *, firestore_client: Any = None) -> dict[str, Any] | None:
    snapshot = _job_ref(_client(firestore_client), job_id).get()
    if not getattr(snapshot, 'exists', False):
        return None
    return snapshot.to_dict() or {}


def _record_meeting_receipt_txn(
    transaction: Any,
    conversation_ref: Any,
    jobs_collection: Any,
    uid: str,
    conversation_id: str,
    finalization_job_id: str | None,
    eligible: bool,
    reason: str,
    duration_s: float,
    dedup_speech_s: float,
    now: datetime,
) -> dict[str, Any]:
    """Create the finalization-job receipt once and project its verdict to the conversation."""
    conversation_snapshot = conversation_ref.get(transaction=transaction)
    if not getattr(conversation_snapshot, 'exists', False):
        return {'status': 'missing'}
    conversation = conversation_snapshot.to_dict() or {}
    existing_job_id = conversation.get('finalization_job_id')
    job_id = (
        finalization_job_id
        if isinstance(finalization_job_id, str) and finalization_job_id
        else (
            existing_job_id
            if isinstance(existing_job_id, str) and existing_job_id
            else _job_id(uid, conversation_id, int(conversation.get('finalization_revision') or 0) + 1)
        )
    )
    job_ref = jobs_collection.document(job_id)
    job_snapshot = job_ref.get(transaction=transaction)
    job = (job_snapshot.to_dict() or {}) if getattr(job_snapshot, 'exists', False) else {}
    if job and (job.get('uid') != uid or job.get('conversation_id') != conversation_id):
        return {'status': 'identity_mismatch'}

    receipt = {
        'meeting_receipt_schema_version': MEETING_RECEIPT_SCHEMA_VERSION,
        'meeting_treatment_eligible': eligible,
        'meeting_treatment_reason': reason,
        'meeting_duration_s': duration_s,
        'meeting_dedup_speech_s': dedup_speech_s,
        'meeting_receipt_created_at': now,
        'meeting_receipt_updated_at': now,
        'meeting_receipt_reconcile_after_at': now + MEETING_RECEIPT_RECONCILE_AFTER,
        'meeting_receipt_intent_id': None,
        'meeting_receipt_intent_persisted_at': None,
        'meeting_receipt_materialized_at': None,
    }
    if job.get('meeting_receipt_schema_version') == MEETING_RECEIPT_SCHEMA_VERSION:
        receipt = {
            key: job.get(key)
            for key in (
                'meeting_receipt_schema_version',
                'meeting_treatment_eligible',
                'meeting_treatment_reason',
                'meeting_duration_s',
                'meeting_dedup_speech_s',
                'meeting_receipt_created_at',
                'meeting_receipt_updated_at',
                'meeting_receipt_reconcile_after_at',
                'meeting_receipt_intent_id',
                'meeting_receipt_intent_persisted_at',
                'meeting_receipt_materialized_at',
            )
            if key in job
        }
    elif job:
        transaction.update(job_ref, receipt)
    else:
        revision = int(conversation.get('finalization_revision') or 0) + 1
        transaction.set(
            job_ref,
            {
                'schema_version': 1,
                'uid': uid,
                'conversation_id': conversation_id,
                'finalization_revision': revision,
                'status': 'completed',
                'requires_byok': False,
                'force_process': False,
                'fanout_key': f'conversation:{conversation_id}:finalization',
                'fanout_status': 'completed',
                'fanout_completed_at': now,
                'finalization_outcome': 'success',
                'terminal_outcome': 'success',
                'terminal_at': now,
                'dispatch_generation': 1,
                'attempt_count': 1,
                'task_retry_count': 0,
                'created_at': now,
                'updated_at': now,
                **receipt,
            },
        )

    conversation_updates = {
        'finalization_job_id': job_id,
        'meeting_treatment_eligible': bool(receipt['meeting_treatment_eligible']),
        'meeting_treatment_reason': receipt['meeting_treatment_reason'],
        'meeting_duration_s': receipt['meeting_duration_s'],
        'meeting_dedup_speech_s': receipt['meeting_dedup_speech_s'],
    }
    if not existing_job_id:
        conversation_updates['finalization_revision'] = int(conversation.get('finalization_revision') or 0) + 1
        conversation_updates['finalization_status'] = 'completed'
    transaction.update(conversation_ref, conversation_updates)
    return {'status': 'recorded', 'job_id': job_id, **receipt}


def record_meeting_receipt(
    uid: str,
    conversation_id: str,
    *,
    finalization_job_id: str | None,
    eligible: bool,
    reason: str,
    duration_s: float,
    dedup_speech_s: float,
    firestore_client: Any = None,
) -> dict[str, Any]:
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_record_meeting_receipt_txn)
    return transactional(
        transaction,
        _conversation_ref(client, uid, conversation_id),
        client.collection(FINALIZATION_JOBS_COLLECTION),
        uid,
        conversation_id,
        finalization_job_id,
        eligible,
        reason,
        duration_s,
        dedup_speech_s,
        _now(),
    )


def mark_meeting_receipt_intent_persisted(job_id: str, intent_id: str, *, firestore_client: Any = None) -> bool:
    client = _client(firestore_client)
    job_ref = _job_ref(client, job_id)
    transaction = client.transaction()

    @firestore.transactional
    def apply(write_transaction: Any) -> bool:
        snapshot = job_ref.get(transaction=write_transaction)
        if not getattr(snapshot, 'exists', False):
            return False
        job = snapshot.to_dict() or {}
        existing = job.get('meeting_receipt_intent_id')
        if isinstance(existing, str):
            return existing == intent_id
        now = _now()
        write_transaction.update(
            job_ref,
            {
                'meeting_receipt_intent_id': intent_id,
                'meeting_receipt_intent_persisted_at': now,
                'meeting_receipt_updated_at': now,
            },
        )
        return True

    return apply(transaction)


def mark_meeting_receipt_materialized(
    uid: str,
    conversation_id: str,
    intent_id: str,
    *,
    materialized_at: datetime,
    firestore_client: Any = None,
) -> bool:
    client = _client(firestore_client)
    conversation_ref = _conversation_ref(client, uid, conversation_id)
    transaction = client.transaction()

    @firestore.transactional
    def apply(write_transaction: Any) -> bool:
        conversation_snapshot = conversation_ref.get(transaction=write_transaction)
        if not getattr(conversation_snapshot, 'exists', False):
            return False
        job_id = (conversation_snapshot.to_dict() or {}).get('finalization_job_id')
        if not isinstance(job_id, str) or not job_id:
            return False
        job_ref = _job_ref(client, job_id)
        job_snapshot = job_ref.get(transaction=write_transaction)
        if not getattr(job_snapshot, 'exists', False):
            return False
        job = job_snapshot.to_dict() or {}
        if job.get('meeting_receipt_intent_id') != intent_id:
            return False
        if job.get('meeting_receipt_materialized_at') is None:
            write_transaction.update(
                job_ref,
                {
                    'meeting_receipt_materialized_at': materialized_at,
                    'meeting_receipt_updated_at': materialized_at,
                },
            )
        return True

    return apply(transaction)


def get_meeting_receipt_reconcile_candidates(
    *, limit: int = 100, now: datetime | None = None, firestore_client: Any = None
) -> list[dict[str, Any]]:
    """Return eligible receipts old enough to repair and still missing an intent id."""
    client = _client(firestore_client)
    cutoff = now or _now()
    query = MEETING_RECEIPTS_DUE_QUERY.build(
        client.collection(FINALIZATION_JOBS_COLLECTION),
        {
            'meeting_treatment_eligible': True,
            'meeting_receipt_intent_id': None,
            'meeting_receipt_reconcile_after_at': cutoff,
        },
        field_filter_factory=FieldFilter,
    )
    query = query.limit(max(1, min(limit, 100)))
    candidates: list[dict[str, Any]] = []
    for snapshot in query.stream():
        job = snapshot.to_dict() or {}
        candidates.append(job | {'job_id': snapshot.id})
    return candidates


def get_meeting_receipt_backfill_candidates(
    *,
    limit: int = 100,
    max_scan: int = 2000,
    resume_after_path: str | None = None,
    firestore_client: Any = None,
) -> dict[str, Any]:
    """Scan completed conversations fairly for legacy desktop meetings without receipts."""
    client = _client(firestore_client)
    page_size = max(1, min(limit, 100))
    collected: list[dict[str, Any]] = []
    scanned = 0
    last_path: str | None = None
    exhausted = False
    cursor_snapshot: Any = None
    if resume_after_path:
        fetched = client.document(resume_after_path).get()
        if getattr(fetched, 'exists', False):
            cursor_snapshot = fetched

    while len(collected) < limit and scanned < max_scan:
        query = client.collection_group(CONVERSATIONS_COLLECTION).where(
            filter=firestore.FieldFilter('status', '==', 'completed')
        )
        query = query.limit(page_size)
        if cursor_snapshot is not None:
            query = query.start_after(cursor_snapshot)
        page = list(query.stream())
        if not page:
            exhausted = True
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
            external_data = data.get('external_data') or {}
            source = data.get('source')
            source = getattr(source, 'value', source)
            if (
                source != 'desktop'
                or not isinstance(external_data, Mapping)
                or external_data.get('conversation_role') != 'meeting'
                or data.get('meeting_treatment_reason')
            ):
                continue
            collected.append({'uid': uid, 'conversation_id': snapshot.id, 'conversation': data | {'id': snapshot.id}})
            if len(collected) >= limit:
                break
        if scanned > max_scan:
            break
        if len(page) < page_size:
            exhausted = True
            break
        cursor_snapshot = page[-1]

    return {
        'candidates': collected,
        'resume_after_path': None if exhausted else last_path,
        'exhausted': exhausted,
    }


def _claim_finalization_replay_txn(
    transaction: Any,
    job_ref: Any,
    stale_after: timedelta,
    now: datetime,
    projection_collection: Any | None = None,
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
    if status == 'leased':
        _record_projection_delta(transaction, projection_collection, job, leased=-1, queued=1)
    job['status'] = 'queued'
    job['dispatch_generation'] = generation
    return _intent_from_job(snapshot.id, job)


def claim_finalization_replay(
    job_id: str, *, stale_after: timedelta, firestore_client: Any = None
) -> FinalizationIntent:
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_claim_finalization_replay_txn)
    return transactional(
        transaction,
        _job_ref(client, job_id),
        stale_after,
        _now(),
        client.collection(FINALIZATION_PROJECTION_COLLECTION),
    )


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
MEETING_RECEIPT_SWEEP_STATE_DOC = 'meeting_receipt_backfill_sweep'
BYOK_ABANDONMENT_SWEEP_STATE_DOC = 'byok_abandonment_sweep'


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


def get_meeting_receipt_backfill_cursor(*, firestore_client: Any = None) -> dict[str, Any]:
    client = _client(firestore_client)
    snapshot = (
        client.collection(STALE_PROCESSING_SWEEP_STATE_COLLECTION).document(MEETING_RECEIPT_SWEEP_STATE_DOC).get()
    )
    if not getattr(snapshot, 'exists', False):
        return {'resume_after_path': None, 'generation': 0}
    data = snapshot.to_dict() or {}
    path = data.get('resume_after_path')
    return {
        'resume_after_path': path if isinstance(path, str) else None,
        'generation': int(data.get('generation', 0)),
    }


def advance_meeting_receipt_backfill_cursor(
    expected_generation: int, new_resume_after_path: str | None, *, firestore_client: Any = None
) -> bool:
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_advance_stale_processing_sweep_cursor_txn)
    return transactional(
        transaction,
        client.collection(STALE_PROCESSING_SWEEP_STATE_COLLECTION).document(MEETING_RECEIPT_SWEEP_STATE_DOC),
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


def _complete_unstampable_orphan_conversation_txn(
    transaction: Any, conversation_ref: Any, stale_before: datetime
) -> bool:
    """Terminalize a legacy orphan whose admission fence can never be stamped.

    A conversation sitting at Firestore's 1 MiB document ceiling rejects every
    growing write, so ``stamp_processing_admission_if_absent`` can never migrate
    it: the row would stay ``processing`` for good while the sweep retries it
    forever. The snapshot's server-owned ``update_time`` stands in for the fence
    the document cannot carry — only a row no writer (including a live processor,
    which is equally unable to write to it) has touched since ``stale_before`` is
    terminalized. Every other ownership fence still applies, and the terminal
    write only shrinks the document, so it fits where the stamp did not.
    """
    snapshot = conversation_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return False
    data = snapshot.to_dict() or {}
    if data.get('status') != 'processing':
        return False
    if data.get('discarded') or data.get('deferred') or data.get('finalization_job_id'):
        return False
    if isinstance(data.get('processing_admitted_at'), datetime):
        return False  # no longer a legacy row: the admission-fenced path owns it
    last_written = getattr(snapshot, 'update_time', None)
    if not isinstance(last_written, datetime) or last_written > stale_before:
        return False
    transaction.update(conversation_ref, {'status': 'completed'})
    return True


def complete_unstampable_orphan_conversation(
    uid: str, conversation_id: str, *, stale_after: timedelta, firestore_client: Any = None
) -> bool:
    """Terminalize a legacy orphan that is too large to accept the admission fence."""
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_complete_unstampable_orphan_conversation_txn)
    return transactional(transaction, _conversation_ref(client, uid, conversation_id), _now() - stale_after)


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


def _job_last_activity_at(job: Mapping[str, Any]) -> datetime | None:
    """Return the most recent server-owned activity instant on a job."""
    for field in ('updated_at', 'created_at'):
        value = job.get(field)
        if isinstance(value, datetime):
            return value
    return None


def get_abandoned_byok_job_candidates(
    *,
    abandoned_after: timedelta,
    limit: int = 100,
    max_scan: int = 2000,
    resume_after_path: str | None = None,
    firestore_client: Any = None,
) -> dict[str, Any]:
    """Return a bounded window of BYOK jobs that no consumer can ever claim again.

    A ``requires_byok`` job is executable only by a live pusher session holding
    the user's request-scoped keys. Every BYOK transition deletes
    ``reconcile_after_at`` on purpose, so such a row is invisible to
    ``get_finalization_replay_candidates``; the Cloud Tasks worker separately
    refuses it in ``_claim_finalization_job_txn``. Once the session ends the row
    is owned by nobody at all. This sweep gives it an owner for exactly one
    purpose: a truthful terminal. It never replays finalization, and it never
    reads, brokers, or substitutes a credential.

    Eligibility (all client-side, re-verified inside the terminal transaction):

    * ``status`` in ``queued`` / ``leased`` -- terminal rows are done, and
      ``blocked_byok`` is deliberately excluded because that state is still
      legitimately waiting for a live session to present keys, and it is already
      visible on the ``blocked_byok`` gauge.
    * an expired lease, if ``leased`` -- a live worker still owns a valid lease.
    * a server-owned last-activity instant older than ``abandoned_after``. A row
      whose age cannot be established is skipped rather than terminalized.

    The cross-collection sweep is a single-equality query on
    ``requires_byok == True``, served by Firestore's automatic single-field index
    (no composite index is registered or deployed). Because exclusion happens
    after the page cap, the sweep pages with a ``start_after`` cursor and stops
    after ``max_scan`` rows; the caller persists ``resume_after_path`` (or
    ``None`` once ``exhausted``) so repeated bounded sweeps cover the whole
    collection and a stable terminal prefix cannot starve a later stranded row.

    Returns ``{'candidates', 'resume_after_path', 'exhausted'}``.
    """
    client = _client(firestore_client)
    now = _now()
    cutoff = now - abandoned_after
    page_size = max(1, min(limit, 100))
    collection = client.collection(FINALIZATION_JOBS_COLLECTION)
    collected: list[dict[str, Any]] = []
    scanned = 0
    last_path: str | None = None
    exhausted = False

    cursor_snapshot: Any = None
    if resume_after_path:
        fetched = client.document(resume_after_path).get()
        if getattr(fetched, 'exists', False):
            cursor_snapshot = fetched
        # A vanished cursor document wraps the sweep back to the top (safe re-scan).

    while len(collected) < limit and scanned < max_scan:
        query = collection.where(filter=firestore.FieldFilter('requires_byok', '==', True)).limit(page_size)
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
            reference = getattr(snapshot, 'reference', None)
            last_path = getattr(reference, 'path', None) or f'{FINALIZATION_JOBS_COLLECTION}/{snapshot.id}'
            job = snapshot.to_dict() or {}
            status = str(job.get('status') or '')
            if status not in ('queued', 'leased'):
                continue
            if status == 'leased':
                lease_expires_at = job.get('lease_expires_at')
                if isinstance(lease_expires_at, datetime) and lease_expires_at > now:
                    continue  # a live worker still owns this lease
            last_activity = _job_last_activity_at(job)
            if last_activity is None or last_activity > cutoff:
                continue  # unknown age, or still inside the reconnect window
            collected.append(job | {'job_id': snapshot.id, 'last_activity_at': last_activity})
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


def _byok_abandonment(status: str, conversation_outcome: str = 'none') -> ByokAbandonment:
    return {'status': status, 'conversation_outcome': conversation_outcome}


def _abandon_byok_finalization_job_txn(
    transaction: Any,
    job_ref: Any,
    expected_status: str,
    expected_dispatch_generation: int,
    expected_lease_epoch: int,
    cutoff: datetime,
    now: datetime,
    conversation_ref_for_job: Callable[[str, str], Any] | None = None,
    projection_collection: Any | None = None,
) -> ByokAbandonment:
    """Terminalize exactly the scanned unownable BYOK generation, fencing every live owner.

    Verified inside the transaction, immediately before the write: the job still
    requires BYOK, is still non-terminal and not ``blocked_byok``, still carries
    the scanned status / dispatch generation / lease epoch (so a live session
    that resumed or claimed it in the meantime wins), holds no unexpired lease,
    and is still older than the abandonment cutoff. Any divergence is an expected
    CAS fencing, never a terminalization of live work.

    The terminal is honest: ``dead_letter`` with ``last_failure_code``
    ``byok_session_abandoned``, distinct from ``final_attempt_failed``. No
    finalization is attempted and no fanout is delivered.

    The bound conversation is read before the first write, so its terminal (when
    it is still ``processing``) commits atomically with the job's. It is moved to
    ``completed`` rather than ``failed``/``discarded``: exactly the choice
    ``complete_orphan_conversation`` makes, so the user's recording stays
    retrievable and reprocessable with their own keys instead of being hidden.
    """
    snapshot = job_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return _byok_abandonment('missing')
    job = snapshot.to_dict() or {}
    status = str(job.get('status') or '')
    if not bool(job.get('requires_byok')):
        return _byok_abandonment('fenced')
    if status not in ('queued', 'leased') or status != expected_status:
        return _byok_abandonment('fenced')
    if int(job.get('dispatch_generation') or 1) != expected_dispatch_generation:
        return _byok_abandonment('fenced')
    if int(job.get('lease_epoch') or 0) != expected_lease_epoch:
        return _byok_abandonment('fenced')
    if status == 'leased':
        lease_expires_at = job.get('lease_expires_at')
        if isinstance(lease_expires_at, datetime) and lease_expires_at > now:
            return _byok_abandonment('fenced')
    last_activity = _job_last_activity_at(job)
    if last_activity is None or last_activity > cutoff:
        return _byok_abandonment('fenced')

    uid = job.get('uid')
    conversation_id = job.get('conversation_id')
    conversation_ref = None
    conversation: Any = None
    if (
        conversation_ref_for_job is not None
        and isinstance(uid, str)
        and uid
        and isinstance(conversation_id, str)
        and conversation_id
    ):
        # Read the bound conversation before the first transaction write: the
        # customer must never be left on `processing` by a crash between two
        # independent writes.
        conversation_ref = conversation_ref_for_job(uid, conversation_id)
        conversation_snapshot = conversation_ref.get(transaction=transaction)
        conversation = conversation_snapshot.to_dict() if getattr(conversation_snapshot, 'exists', False) else None

    transaction.update(
        job_ref,
        {
            'status': 'dead_letter',
            'updated_at': now,
            'terminal_at': now,
            'terminal_outcome': 'failure',
            'finalization_outcome': BYOK_ABANDONED_FAILURE_CODE,
            'lease_expires_at': now,
            'reconcile_after_at': firestore.DELETE_FIELD,
            # Nothing was ever delivered to an external integration.
            'fanout_status': 'fenced',
            'fanout_fenced_at': now,
            'last_failure_code': BYOK_ABANDONED_FAILURE_CODE,
        },
    )
    _record_projection_delta(
        transaction,
        projection_collection,
        job,
        queued=-1 if status == 'queued' else 0,
        leased=-1 if status == 'leased' else 0,
        dead_letter=1,
        failure=1,
    )

    if conversation_ref is None or not isinstance(conversation, Mapping):
        return _byok_abandonment('abandoned', 'missing')
    if conversation.get('finalization_job_id') != job_ref.id or conversation.get('finalization_revision') != job.get(
        'finalization_revision'
    ):
        return _byok_abandonment('abandoned', 'unbound')
    if conversation.get('status') != 'processing' or conversation.get('discarded'):
        # The inline pusher lane already finalized this conversation; the job row
        # was orphaned bookkeeping, so only the job needed a terminal.
        return _byok_abandonment('abandoned', 'already_terminal')
    if conversation.get('deferred'):
        # A desktop lazy row intentionally stays on `processing` and is owned by
        # its own lane, exactly as the bare-`processing` sweep treats it.
        return _byok_abandonment('abandoned', 'deferred')
    transaction.update(conversation_ref, {'status': 'completed', 'finalization_status': 'dead_letter'})
    return _byok_abandonment('abandoned', 'closed')


def abandon_byok_finalization_job(
    job_id: str,
    *,
    expected_status: str,
    expected_dispatch_generation: int,
    expected_lease_epoch: int,
    abandoned_after: timedelta,
    firestore_client: Any = None,
) -> ByokAbandonment:
    """Close one unownable BYOK job through its generation/ownership fence."""
    client = _client(firestore_client)
    now = _now()
    transaction = client.transaction()
    transactional = firestore.transactional(_abandon_byok_finalization_job_txn)
    return transactional(
        transaction,
        _job_ref(client, job_id),
        expected_status,
        expected_dispatch_generation,
        expected_lease_epoch,
        now - abandoned_after,
        now,
        lambda uid, conversation_id: _conversation_ref(client, uid, conversation_id),
        client.collection(FINALIZATION_PROJECTION_COLLECTION),
    )


def get_byok_abandonment_sweep_cursor(*, firestore_client: Any = None) -> dict[str, Any]:
    """Return the persisted BYOK sweep cursor and its CAS generation."""
    client = _client(firestore_client)
    snapshot = (
        client.collection(STALE_PROCESSING_SWEEP_STATE_COLLECTION).document(BYOK_ABANDONMENT_SWEEP_STATE_DOC).get()
    )
    if not getattr(snapshot, 'exists', False):
        return {'resume_after_path': None, 'generation': 0}
    data = snapshot.to_dict() or {}
    path = data.get('resume_after_path')
    return {
        'resume_after_path': path if isinstance(path, str) else None,
        'generation': int(data.get('generation', 0)),
    }


def advance_byok_abandonment_sweep_cursor(
    expected_generation: int, new_resume_after_path: str | None, *, firestore_client: Any = None
) -> bool:
    """Atomically advance the BYOK sweep cursor; ``None`` rotates the next sweep to the top."""
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_advance_stale_processing_sweep_cursor_txn)
    return transactional(
        transaction,
        client.collection(STALE_PROCESSING_SWEEP_STATE_COLLECTION).document(BYOK_ABANDONMENT_SWEEP_STATE_DOC),
        expected_generation,
        new_resume_after_path,
        _now(),
    )


def get_finalization_job_summary(*, firestore_client: Any = None) -> dict[str, float | int]:
    """Read one generation's fixed shard fan-in plus the oldest unfinished job.

    This deliberately never aggregates ``conversation_finalization_jobs``. A
    backend-listen replica performs exactly ``FINALIZATION_PROJECTION_SHARD_COUNT``
    projection-document reads, regardless of terminal history size. Pre-release
    jobs carry no generation and remain absent from this new denominator; their
    terminal field is still preserved on the authoritative job document.
    """
    client = _client(firestore_client)
    now = _now()
    jobs_collection = client.collection(FINALIZATION_JOBS_COLLECTION)
    projection_collection = client.collection(FINALIZATION_PROJECTION_COLLECTION)
    totals = {
        name: 0
        for name in (
            'accepted',
            'queued',
            'leased',
            'blocked_byok',
            'completed',
            'dead_letter',
            'success',
            'failure',
            'stale',
        )
    }
    for shard in range(FINALIZATION_PROJECTION_SHARD_COUNT):
        snapshot = projection_collection.document(_projection_shard_id(FINALIZATION_PROJECTION_GENERATION, shard)).get()
        if not getattr(snapshot, 'exists', False):
            continue
        data = snapshot.to_dict() or {}
        # A malformed or stale document cannot contaminate this generation's
        # denominator. The writer is the sole producer of matching documents.
        if data.get('generation') != FINALIZATION_PROJECTION_GENERATION or data.get('shard') != shard:
            continue
        for name in totals:
            value = data.get(name, 0)
            if isinstance(value, (int, float)):
                totals[name] += int(value)

    # The age of the oldest unfinished job is asked of ``status`` directly, one
    # ordered single-document read per nonterminal status.  The previous
    # implementation paged ``reconcile_after_at <= now`` instead, which made the
    # gauge structurally unable to see the population it exists to report:
    # ``reconcile_after_at`` is deleted outright on the BYOK resume and BYOK
    # retry paths, so every BYOK job was invisible to it and the gauge read 0
    # while hundreds of jobs sat unfinished for weeks.  Ordering by
    # ``created_at`` also makes this the actual oldest row rather than the
    # oldest of an arbitrary page.  Cost stays bounded and independent of
    # terminal history: one indexed read per nonterminal status.
    oldest_age_seconds = 0.0
    for status in sorted(NONTERMINAL_JOB_STATUSES):
        oldest_query = (
            FINALIZATION_OLDEST_NONTERMINAL_QUERY.build(
                jobs_collection, {'status': status}, field_filter_factory=FieldFilter
            )
            .order_by('created_at')
            .limit(1)
        )
        for snapshot in oldest_query.stream():
            created_at = (snapshot.to_dict() or {}).get('created_at')
            if isinstance(created_at, datetime):
                oldest_age_seconds = max(oldest_age_seconds, max(0.0, (now - created_at).total_seconds()))
    return {
        'accepted': totals['accepted'],
        'success': totals['success'],
        'failure': totals['failure'],
        'stale': totals['stale'],
        'nonterminal': totals['queued'] + totals['leased'],
        'queued': totals['queued'],
        'leased': totals['leased'],
        'blocked_byok': totals['blocked_byok'],
        'completed': totals['completed'],
        'dead_letter': totals['dead_letter'],
        # Every admitted generation terminal transition writes an outcome.
        # Historical terminals are intentionally out of this bounded generation.
        'terminal_unknown': 0,
        'oldest_nonterminal_age_seconds': oldest_age_seconds,
    }
