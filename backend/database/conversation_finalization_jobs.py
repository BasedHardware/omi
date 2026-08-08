"""Durable outbox and lease state for conversation finalization (storage port).

The durable source of truth is one job per ``(uid, conversation_id, finalization_revision)`` under
the ``conversation_finalization_jobs`` collection. No transcript, credential, request header, or raw
exception is stored here. All persistence goes through the backend-neutral storage port
(``database.store``); no storage SDK type crosses this module's boundary.

Transactions use ``_store().run_transaction(fn)``: every ``fn(tx)`` performs all reads before any
write (the store forbids read-after-write inside a transaction). The cross-user orphan sweep is a
single-equality ``query_group`` on ``status == 'processing'`` paged by the port's document-name
keyset; each result carries its full logical path so the parent uid is recoverable.
"""

from __future__ import annotations

import os
from hashlib import sha256
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Literal, Mapping, TypedDict

from database import conversations as conversations_db
from database.document_ids import document_id_from_seed
from database.store import get_document_store
from database.store.sentinels import DELETE, Increment

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


def _store():
    return get_document_store()


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


def _conversation_path(uid: str, conversation_id: str) -> str:
    return f'users/{uid}/{CONVERSATIONS_COLLECTION}/{conversation_id}'


def _uid_from_conversation_path(path: str) -> str | None:
    """Return the uid from a ``users/{uid}/conversations/{conversation_id}`` path."""
    parts = path.split('/')
    if len(parts) == 4 and parts[0] == 'users' and parts[2] == CONVERSATIONS_COLLECTION:
        return parts[1]
    return None


def _job_path(job_id: str) -> str:
    return f'{FINALIZATION_JOBS_COLLECTION}/{job_id}'


def _projection_shard(job_id: str) -> int:
    """Choose a stable aggregate shard without exposing job identity in metrics."""
    return int.from_bytes(sha256(job_id.encode('utf-8')).digest()[:4], 'big') % FINALIZATION_PROJECTION_SHARD_COUNT


def _projection_shard_id(generation: str, shard: int) -> str:
    return f'{generation}-{shard:02d}'


def _projection_shard_path_for_job(job: Mapping[str, Any]) -> str | None:
    generation = job.get('projection_generation')
    shard = job.get('projection_shard')
    if not isinstance(generation, str) or not isinstance(shard, int):
        return None
    if generation != FINALIZATION_PROJECTION_GENERATION or not 0 <= shard < FINALIZATION_PROJECTION_SHARD_COUNT:
        return None
    return f'{FINALIZATION_PROJECTION_COLLECTION}/{_projection_shard_id(generation, shard)}'


def _record_projection_delta(transaction: Any, job: Mapping[str, Any], **deltas: int) -> None:
    """Atomically add state deltas for an admitted projection generation.

    A terminal replay returns before this helper, and store retries rerun the
    transaction against a fresh snapshot. Therefore each committed state
    transition contributes exactly once without a per-job metrics side record.
    """
    shard_path = _projection_shard_path_for_job(job)
    if shard_path is None:
        return
    fields: dict[str, Any] = {
        'generation': FINALIZATION_PROJECTION_GENERATION,
        'shard': int(job['projection_shard']),
    }
    fields.update({name: Increment(delta) for name, delta in deltas.items() if delta})
    if len(fields) == 2:
        return
    transaction.set(shard_path, fields, merge=True)


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


def _conversation_has_finalization_content(uid: str, conversation: Mapping[str, Any], has_photos: bool) -> bool:
    """Decide admissibility from the transaction's conversation snapshot.

    ``has_photos`` is read just before the outbox transaction: the neutral store's
    transaction is point-based (no in-transaction collection query), so the legacy
    photo-only fallback cannot be evaluated on the transaction snapshot. At
    finalization the recording has ended and photo child documents are stable, so
    the pre-transaction existence check is authoritative. ``has_content`` was added
    after photo-only listen recordings already existed; keep their durable child
    documents admissible until all legacy rows have naturally finalized.
    """
    if conversations_db.raw_conversation_has_content(uid, dict(conversation)):
        return True
    return has_photos


def _create_or_get_finalization_intent_txn(
    transaction: Any,
    uid: str,
    conversation_id: str,
    requires_byok: bool,
    finalization_admission: Callable[[Mapping[str, Any]], FinalizationAdmission],
    now: datetime,
    *,
    has_photos: bool,
    force_process: bool = False,
    extra_updates: Mapping[str, Any] | None = None,
) -> FinalizationIntent:
    """Persist finalization ownership before any pusher or task handoff."""
    conversation_path = _conversation_path(uid, conversation_id)
    conversation_snapshot = transaction.get(conversation_path)
    if not conversation_snapshot.exists:
        return _no_finalization_intent('missing')

    conversation = conversation_snapshot.to_dict() or {}
    if conversation.get('deferred'):
        return _no_finalization_intent('deferred')
    if not _conversation_has_finalization_content(uid, conversation, has_photos):
        return _no_finalization_intent('no_content')

    # The lifecycle service owns this pure decision, but it is evaluated while
    # the store holds the conversation transaction snapshot. A late disconnect
    # therefore cannot reopen a failed/discarded terminal row after a stale
    # pre-transaction read.
    admission = finalization_admission(conversation)
    if admission['terminal']:
        return _no_finalization_intent(admission['reason'])

    existing_job_id = conversation.get('finalization_job_id')
    if isinstance(existing_job_id, str) and existing_job_id:
        existing_snapshot = transaction.get(_job_path(existing_job_id))
        if existing_snapshot.exists:
            return _intent_from_job(existing_job_id, existing_snapshot.to_dict() or {})

    if not admission['accepted'] or not admission['fanout_key']:
        return _no_finalization_intent(admission['reason'])

    revision = int(conversation.get('finalization_revision') or 0) + 1
    job_id = _job_id(uid, conversation_id, revision)
    job_path = _job_path(job_id)
    job_snapshot = transaction.get(job_path)
    if job_snapshot.exists:
        job = job_snapshot.to_dict() or {}
        transaction.update(
            conversation_path,
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
        'projection_generation': FINALIZATION_PROJECTION_GENERATION,
        'projection_shard': _projection_shard(job_id),
        'created_at': now,
        'updated_at': now,
        'dispatch_requested_at': now,
    }
    if not requires_byok:
        job['reconcile_after_at'] = now + get_finalization_reconcile_stale_after()
    transaction.set(job_path, job)
    _record_projection_delta(
        transaction,
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
    transaction.update(conversation_path, conversation_updates)
    return _intent_from_job(job_id, job, created=True)


def create_or_get_finalization_intent(
    uid: str,
    conversation_id: str,
    *,
    requires_byok: bool,
    finalization_admission: Callable[[Mapping[str, Any]], FinalizationAdmission],
    force_process: bool = False,
    extra_updates: Mapping[str, Any] | None = None,
) -> FinalizationIntent:
    # The photo-only legacy fallback needs a collection read, which the store's
    # point-based transaction cannot serve; read it just before the transaction
    # (photo child documents are stable once the recording has ended).
    photos_path = f'{_conversation_path(uid, conversation_id)}/photos'
    has_photos = bool(_store().query(photos_path, limit=1))

    def create_intent_in_transaction(transaction: Any) -> FinalizationIntent:
        return _create_or_get_finalization_intent_txn(
            transaction,
            uid,
            conversation_id,
            requires_byok,
            finalization_admission,
            _now(),
            has_photos=has_photos,
            force_process=force_process,
            extra_updates=extra_updates,
        )

    # Concurrent REST finalizers contend on the conversation row; the store owns
    # the bounded transaction retry (a fresh snapshot per attempt).
    return _store().run_transaction(create_intent_in_transaction, attempts=5)


def _resume_blocked_byok_job_txn(transaction: Any, job_id: str, now: datetime) -> FinalizationIntent:
    snapshot = transaction.get(_job_path(job_id))
    if not snapshot.exists:
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
            _job_path(job_id),
            {
                'status': 'queued',
                'updated_at': now,
                'last_byok_resume_at': now,
                # BYOK jobs must only be resumed by the live pusher session,
                # never by the credential-free Cloud Tasks reconciler.
                'reconcile_after_at': DELETE,
            },
        )
        _record_projection_delta(transaction, job, blocked_byok=-1, queued=1)
        job['status'] = 'queued'
    return _intent_from_job(snapshot.id, job)


def resume_blocked_byok_job_for_live_session(job_id: str) -> FinalizationIntent:
    return _store().run_transaction(lambda tx: _resume_blocked_byok_job_txn(tx, job_id, _now()))


def _claim_finalization_job_txn(
    transaction: Any,
    job_id: str,
    dispatch_generation: int,
    allow_byok: bool,
    lease_seconds: int,
    now: datetime,
    expected_uid: str | None = None,
    expected_conversation_id: str | None = None,
) -> FinalizationClaim:
    snapshot = transaction.get(_job_path(job_id))
    if not snapshot.exists:
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
        _job_path(job_id),
        {
            'status': 'leased',
            'leased_at': now,
            'lease_expires_at': lease_expires_at,
            # A lease epoch fences a worker that resumes after another worker
            # has reclaimed its expired lease. Terminal writes must present it.
            'lease_epoch': lease_epoch,
            'reconcile_after_at': (DELETE if bool(job.get('requires_byok')) else lease_expires_at),
            'updated_at': now,
            # The claimer owns the attempt budget: an inline (pusher) worker has
            # no Cloud Tasks retry count to fence its terminal attempt with.
            'attempt_count': attempt_count,
        },
    )
    if status == 'queued':
        _record_projection_delta(transaction, job, queued=-1, leased=1)
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
) -> FinalizationClaim:
    return _store().run_transaction(
        lambda tx: _claim_finalization_job_txn(
            tx,
            job_id,
            dispatch_generation,
            allow_byok,
            lease_seconds,
            _now(),
            expected_uid,
            expected_conversation_id,
        )
    )


def _mark_finalization_completed_txn(
    transaction: Any,
    job_id: str,
    dispatch_generation: int,
    lease_epoch: int,
    now: datetime,
) -> bool:
    snapshot = transaction.get(_job_path(job_id))
    if not snapshot.exists:
        return False
    job = snapshot.to_dict() or {}
    if job.get('status') == 'completed':
        return int(job.get('lease_epoch') or 0) == lease_epoch
    if not _is_current_lease(job, dispatch_generation, lease_epoch):
        return False
    if job.get('fanout_status') != 'completed':
        return False
    transaction.update(
        _job_path(job_id),
        {
            'status': 'completed',
            'completed_at': now,
            'terminal_outcome': 'success',
            'updated_at': now,
            'lease_expires_at': now,
            'reconcile_after_at': DELETE,
            'last_failure_code': None,
        },
    )
    _record_projection_delta(transaction, job, leased=-1, completed=1, success=1)
    return True


def mark_finalization_completed(job_id: str, dispatch_generation: int, lease_epoch: int) -> bool:
    return _store().run_transaction(
        lambda tx: _mark_finalization_completed_txn(tx, job_id, dispatch_generation, lease_epoch, _now())
    )


def _mark_finalization_fenced_txn(
    transaction: Any,
    job_id: str,
    dispatch_generation: int,
    lease_epoch: int,
    now: datetime,
) -> bool:
    """Terminally complete a current lease that was fenced before fanout.

    A discard or newer lifecycle generation can win after the job lease was
    acquired. That is a successful no-fanout terminal outcome, not a retryable
    processing failure. It must remain distinct from normal completion so a
    replay cannot mistake it for a delivered external integration.
    """
    snapshot = transaction.get(_job_path(job_id))
    if not snapshot.exists:
        return False
    job = snapshot.to_dict() or {}
    if job.get('status') == 'completed':
        return job.get('finalization_outcome') == 'fenced' and int(job.get('lease_epoch') or 0) == lease_epoch
    if not _is_current_lease(job, dispatch_generation, lease_epoch):
        return False
    if job.get('fanout_status') not in (None, 'pending'):
        return False
    transaction.update(_job_path(job_id), _fenced_finalization_update(now))
    _record_projection_delta(transaction, job, leased=-1, completed=1, stale=1)
    return True


def mark_finalization_fenced(job_id: str, dispatch_generation: int, lease_epoch: int) -> bool:
    return _store().run_transaction(
        lambda tx: _mark_finalization_fenced_txn(tx, job_id, dispatch_generation, lease_epoch, _now())
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
        'reconcile_after_at': DELETE,
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
    job_id: str,
    dispatch_generation: int,
    lease_epoch: int,
    now: datetime,
) -> FinalizationFanoutClaim:
    """Claim fanout only if this job still owns the completed conversation.

    Reading the conversation in this transaction makes a concurrent discard or
    newer finalization revision retry the transaction before the fanout lease can
    commit.  The losing state is terminally fenced here, rather than leaving a
    retryable leased job for either worker to replay.
    """
    snapshot = transaction.get(_job_path(job_id))
    if not snapshot.exists:
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
        transaction.update(_job_path(job_id), _fenced_finalization_update(now))
        _record_projection_delta(transaction, job, leased=-1, completed=1, stale=1)
        return _fanout_claim('fenced', fanout_key)

    conversation_snapshot = transaction.get(_conversation_path(uid, conversation_id))
    conversation = conversation_snapshot.to_dict() if conversation_snapshot.exists else None
    if not isinstance(conversation, Mapping) or not _conversation_admits_fanout(conversation, job, job_id):
        transaction.update(_job_path(job_id), _fenced_finalization_update(now))
        _record_projection_delta(transaction, job, leased=-1, completed=1, stale=1)
        return _fanout_claim('fenced', fanout_key)

    transaction.update(
        _job_path(job_id),
        {
            'fanout_key': fanout_key,
            'fanout_status': 'leased',
            'fanout_lease_epoch': lease_epoch,
            'fanout_started_at': now,
            'updated_at': now,
        },
    )
    return _fanout_claim('claimed', fanout_key)


def claim_finalization_fanout(job_id: str, dispatch_generation: int, lease_epoch: int) -> FinalizationFanoutClaim:
    return _store().run_transaction(
        lambda tx: _claim_finalization_fanout_txn(tx, job_id, dispatch_generation, lease_epoch, _now())
    )


def _mark_finalization_fanout_completed_txn(
    transaction: Any,
    job_id: str,
    dispatch_generation: int,
    lease_epoch: int,
    now: datetime,
) -> bool:
    snapshot = transaction.get(_job_path(job_id))
    if not snapshot.exists:
        return False
    job = snapshot.to_dict() or {}
    if job.get('fanout_status') == 'completed':
        return int(job.get('fanout_lease_epoch') or 0) == lease_epoch
    if not _is_current_lease(job, dispatch_generation, lease_epoch):
        return False
    transaction.update(
        _job_path(job_id),
        {
            'fanout_status': 'completed',
            'fanout_completed_at': now,
            'updated_at': now,
        },
    )
    return True


def mark_finalization_fanout_completed(job_id: str, dispatch_generation: int, lease_epoch: int) -> bool:
    return _store().run_transaction(
        lambda tx: _mark_finalization_fanout_completed_txn(tx, job_id, dispatch_generation, lease_epoch, _now())
    )


def _mark_finalization_retryable_txn(
    transaction: Any,
    job_id: str,
    dispatch_generation: int,
    lease_epoch: int,
    failure_code: str,
    now: datetime,
) -> bool:
    snapshot = transaction.get(_job_path(job_id))
    if not snapshot.exists:
        return False
    job = snapshot.to_dict() or {}
    if not _is_current_lease(job, dispatch_generation, lease_epoch):
        return False
    transaction.update(
        _job_path(job_id),
        {
            'status': 'queued',
            'updated_at': now,
            'lease_expires_at': now,
            'reconcile_after_at': (
                DELETE if bool(job.get('requires_byok')) else now + get_finalization_reconcile_stale_after()
            ),
            'last_failure_code': failure_code,
        },
    )
    _record_projection_delta(transaction, job, leased=-1, queued=1)
    return True


def mark_finalization_retryable(
    job_id: str,
    dispatch_generation: int,
    lease_epoch: int,
    failure_code: str = 'processing_failed',
) -> bool:
    return _store().run_transaction(
        lambda tx: _mark_finalization_retryable_txn(tx, job_id, dispatch_generation, lease_epoch, failure_code, _now())
    )


def _mark_finalization_dead_letter_txn(
    transaction: Any,
    job_id: str,
    dispatch_generation: int,
    lease_epoch: int,
    retry_count: int,
    now: datetime,
    close_bound_conversation: bool = True,
) -> bool:
    snapshot = transaction.get(_job_path(job_id))
    if not snapshot.exists:
        return False
    job = snapshot.to_dict() or {}
    if not _is_current_lease(job, dispatch_generation, lease_epoch):
        return False
    conversation_path = None
    conversation = None
    uid = job.get('uid')
    conversation_id = job.get('conversation_id')
    if (
        close_bound_conversation
        and isinstance(uid, str)
        and uid
        and isinstance(conversation_id, str)
        and conversation_id
    ):
        # Read the bound conversation before the first transaction write. A
        # final worker failure must close its still-current processing
        # generation atomically with dead-lettering the job; otherwise a crash
        # between independent writes strands the customer on processing.
        conversation_path = _conversation_path(uid, conversation_id)
        conversation_snapshot = transaction.get(conversation_path)
        conversation = conversation_snapshot.to_dict() if conversation_snapshot.exists else None
    transaction.update(
        _job_path(job_id),
        {
            'status': 'dead_letter',
            'updated_at': now,
            'terminal_at': now,
            'terminal_outcome': 'failure',
            'lease_expires_at': now,
            'reconcile_after_at': DELETE,
            'task_retry_count': retry_count,
            'last_failure_code': 'final_attempt_failed',
        },
    )
    _record_projection_delta(transaction, job, leased=-1, dead_letter=1, failure=1)
    if (
        conversation_path is not None
        and isinstance(conversation, Mapping)
        and conversation.get('status') == 'processing'
        and not conversation.get('discarded')
        and conversation.get('finalization_job_id') == job_id
        and conversation.get('finalization_revision') == job.get('finalization_revision')
    ):
        transaction.update(
            conversation_path,
            {
                'status': 'failed',
                'discarded': True,
                'finalization_status': 'dead_letter',
            },
        )
    return True


def mark_finalization_dead_letter(
    job_id: str, dispatch_generation: int, lease_epoch: int, retry_count: int
) -> bool:
    return _store().run_transaction(
        lambda tx: _mark_finalization_dead_letter_txn(tx, job_id, dispatch_generation, lease_epoch, retry_count, _now())
    )


def get_finalization_job(job_id: str) -> dict[str, Any] | None:
    snapshot = _store().get(_job_path(job_id))
    if not snapshot.exists:
        return None
    return snapshot.to_dict() or {}


def _claim_finalization_replay_txn(
    transaction: Any,
    job_id: str,
    stale_after: timedelta,
    now: datetime,
) -> FinalizationIntent:
    snapshot = transaction.get(_job_path(job_id))
    if not snapshot.exists:
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
        _job_path(job_id),
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
        _record_projection_delta(transaction, job, leased=-1, queued=1)
    job['status'] = 'queued'
    job['dispatch_generation'] = generation
    return _intent_from_job(snapshot.id, job)


def claim_finalization_replay(job_id: str, *, stale_after: timedelta) -> FinalizationIntent:
    return _store().run_transaction(lambda tx: _claim_finalization_replay_txn(tx, job_id, stale_after, _now()))


def get_finalization_replay_candidates(*, limit: int = 100) -> list[dict[str, Any]]:
    """Return a bounded server-side page of jobs whose replay delay elapsed."""
    result: list[dict[str, Any]] = []
    docs = _store().query(
        FINALIZATION_JOBS_COLLECTION,
        filters=[('reconcile_after_at', '<=', _now())],
        limit=max(1, min(limit, 100)),
    )
    for snapshot in docs:
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

    The cross-user sweep is a single-equality ``query_group`` on
    ``status == 'processing'``. Because client-side exclusion (deferred /
    durable-job-owned / fresh / legacy) happens after the page cap, the sweep
    pages with the store's document-name keyset (``start_after``) so a stable
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
    cutoff = _now() - stale_after
    page_size = max(1, min(limit, 100))
    collected: list[dict[str, Any]] = []
    scanned = 0
    last_path: str | None = None
    exhausted = False

    start_after: str | None = None
    if resume_after_path:
        # Resume the collection-group scan after the persisted cursor path. A
        # vanished cursor document wraps the sweep back to the top (safe re-scan).
        if _store().exists(resume_after_path):
            start_after = resume_after_path

    while len(collected) < limit and scanned < max_scan:
        page = _store().query_group(
            CONVERSATIONS_COLLECTION,
            filters=[('status', '==', 'processing')],
            limit=page_size,
            start_after=start_after,
        )
        if not page:
            exhausted = True  # reached the tail of the collection from the cursor
            break
        for snapshot in page:
            scanned += 1
            if scanned > max_scan:
                break
            last_path = snapshot.path
            uid = _uid_from_conversation_path(snapshot.path)
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
        start_after = page[-1].path

    return {
        'candidates': collected,
        'resume_after_path': None if exhausted else last_path,
        'exhausted': exhausted,
    }


STALE_PROCESSING_SWEEP_STATE_COLLECTION = 'conversation_recovery_state'
STALE_PROCESSING_SWEEP_STATE_DOC = 'stale_processing_sweep'


def _sweep_state_path() -> str:
    return f'{STALE_PROCESSING_SWEEP_STATE_COLLECTION}/{STALE_PROCESSING_SWEEP_STATE_DOC}'


def get_stale_processing_sweep_cursor() -> dict[str, Any]:
    """Return the persisted sweep cursor and its CAS generation.

    Returns ``{'resume_after_path': str | None, 'generation': int}``. The
    generation is the compare-and-swap token a caller must hold to advance the
    cursor; ``0`` when the document has never been written. Multiple backend-listen
    pods share this single cursor, so the generation prevents a delayed scan from
    rewinding another pod's advance.
    """
    snapshot = _store().get(_sweep_state_path())
    if not snapshot.exists:
        return {'resume_after_path': None, 'generation': 0}
    data = snapshot.to_dict() or {}
    path = data.get('resume_after_path')
    return {
        'resume_after_path': path if isinstance(path, str) else None,
        'generation': int(data.get('generation', 0)),
    }


def _advance_stale_processing_sweep_cursor_txn(
    transaction: Any, expected_generation: int, new_resume_after_path: str | None, now: datetime
) -> bool:
    """CAS-update the sweep cursor inside a store transaction.

    Returns ``True`` only when the persisted generation still equals
    ``expected_generation`` — proving no other pod advanced the cursor between
    this pod's read and write. On success the cursor advances and the generation
    bumps, so a delayed competing writer holding the old generation is fenced out
    (``False``) and cannot rewind progress.
    """
    snapshot = transaction.get(_sweep_state_path())
    if not snapshot.exists:
        current_generation = 0
    else:
        current_generation = int((snapshot.to_dict() or {}).get('generation', 0))
    if current_generation != expected_generation:
        return False
    transaction.set(
        _sweep_state_path(),
        {'resume_after_path': new_resume_after_path, 'generation': current_generation + 1, 'updated_at': now},
    )
    return True


def advance_stale_processing_sweep_cursor(expected_generation: int, new_resume_after_path: str | None) -> bool:
    """Atomically advance the sweep cursor; ``None`` rotates the next sweep to the top.

    Returns ``False`` when another pod already advanced the cursor (the CAS
    generation changed). The caller's sweep work is still valid — the exact-
    generation fence in ``complete_orphan_conversation`` prevents double-terminalization
    — but the cursor does not advance from this pod's perspective, so the next sweep
    safely re-scans the same window.
    """
    return _store().run_transaction(
        lambda tx: _advance_stale_processing_sweep_cursor_txn(tx, expected_generation, new_resume_after_path, _now())
    )


def _stamp_processing_admission_if_absent_txn(transaction: Any, conversation_path: str, now: datetime) -> bool:
    """Server-owned migration: stamp the admission fence on a legacy processing row.

    Returns ``True`` only when a bare ``processing`` row lacking a valid
    ``processing_admitted_at`` was stamped with ``now``. A row already stamped, in
    any other lifecycle state, or absent is left untouched. The stamp is the sole
    authority the orphan sweep trusts; it never terminalizes a row here.
    """
    snapshot = transaction.get(conversation_path)
    if not snapshot.exists:
        return False
    data = snapshot.to_dict() or {}
    if data.get('status') != 'processing':
        return False
    if isinstance(data.get('processing_admitted_at'), datetime):
        return False
    transaction.update(conversation_path, {'processing_admitted_at': now})
    return True


def stamp_processing_admission_if_absent(uid: str, conversation_id: str) -> bool:
    """Stamp the authoritative admission fence on a legacy processing conversation."""
    return _store().run_transaction(
        lambda tx: _stamp_processing_admission_if_absent_txn(tx, _conversation_path(uid, conversation_id), _now())
    )


def _complete_unstampable_orphan_conversation_txn(
    transaction: Any, conversation_path: str, stale_before: datetime
) -> bool:
    """Terminalize a legacy orphan whose admission fence can never be stamped.

    A conversation sitting at the store's document-size ceiling rejects every
    growing write, so ``stamp_processing_admission_if_absent`` can never migrate
    it: the row would stay ``processing`` for good while the sweep retries it
    forever. The snapshot's server-owned last-write revision stands in for the
    fence the document cannot carry — only a row no writer (including a live
    processor, which is equally unable to write to it) has touched since
    ``stale_before`` is terminalized. Every other ownership fence still applies,
    and the terminal write only shrinks the document, so it fits where the stamp
    did not.
    """
    snapshot = transaction.get(conversation_path)
    if not snapshot.exists:
        return False
    data = snapshot.to_dict() or {}
    if data.get('status') != 'processing':
        return False
    if data.get('discarded') or data.get('deferred') or data.get('finalization_job_id'):
        return False
    if isinstance(data.get('processing_admitted_at'), datetime):
        return False  # no longer a legacy row: the admission-fenced path owns it
    last_written = snapshot.updated_at
    if not isinstance(last_written, datetime) or last_written > stale_before:
        return False
    transaction.update(conversation_path, {'status': 'completed'})
    return True


def complete_unstampable_orphan_conversation(uid: str, conversation_id: str, *, stale_after: timedelta) -> bool:
    """Terminalize a legacy orphan that is too large to accept the admission fence."""
    return _store().run_transaction(
        lambda tx: _complete_unstampable_orphan_conversation_txn(
            tx, _conversation_path(uid, conversation_id), _now() - stale_after
        )
    )


def _complete_orphan_conversation_txn(
    transaction: Any, conversation_path: str, expected_admitted_at: datetime | None
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
    snapshot = transaction.get(conversation_path)
    if not snapshot.exists:
        return False
    data = snapshot.to_dict() or {}
    if data.get('status') != 'processing':
        return False
    if data.get('discarded') or data.get('deferred') or data.get('finalization_job_id'):
        return False
    admitted_at = data.get('processing_admitted_at')
    if not isinstance(admitted_at, datetime) or admitted_at != expected_admitted_at:
        return False
    transaction.update(conversation_path, {'status': 'completed'})
    return True


def complete_orphan_conversation(uid: str, conversation_id: str, *, expected_admitted_at: datetime | None) -> bool:
    """Close one crash orphan through the generation/ownership fence."""
    return _store().run_transaction(
        lambda tx: _complete_orphan_conversation_txn(tx, _conversation_path(uid, conversation_id), expected_admitted_at)
    )


def _renew_processing_lease_txn(transaction: Any, conversation_path: str, now: datetime) -> bool:
    """Refresh the admission lease on a still-processing row owned by a live processor."""
    snapshot = transaction.get(conversation_path)
    if not snapshot.exists:
        return False
    data = snapshot.to_dict() or {}
    if data.get('status') != 'processing' or data.get('discarded'):
        return False
    transaction.update(conversation_path, {'processing_admitted_at': now})
    return True


def renew_processing_lease(uid: str, conversation_id: str) -> bool:
    """Renew the server-owned admission lease so recovery cannot mistake a live processor for a crash."""
    return _store().run_transaction(
        lambda tx: _renew_processing_lease_txn(tx, _conversation_path(uid, conversation_id), _now())
    )


def _reacquire_deferred_processing_txn(transaction: Any, conversation_path: str, now: datetime) -> bool:
    """Atomically clear ``deferred`` and renew the admission lease.

    This eliminates the window between clearing ``deferred`` and the first
    heartbeat renewal where the orphan sweep could terminalize the row.  If
    the row is no longer ``processing`` or was discarded, the transition
    fails closed so a stale processor produces no derived side effects.
    """
    snapshot = transaction.get(conversation_path)
    if not snapshot.exists:
        return False
    data = snapshot.to_dict() or {}
    if data.get('status') != 'processing' or data.get('discarded'):
        return False
    transaction.update(conversation_path, {'deferred': False, 'processing_admitted_at': now})
    return True


def reacquire_deferred_processing(uid: str, conversation_id: str) -> bool:
    """Atomically clear deferred and renew the admission lease in one transaction."""
    return _store().run_transaction(
        lambda tx: _reacquire_deferred_processing_txn(tx, _conversation_path(uid, conversation_id), _now())
    )


def get_finalization_job_summary() -> dict[str, float | int]:
    """Read one generation's fixed shard fan-in plus a bounded overdue-age sample.

    This deliberately never aggregates ``conversation_finalization_jobs``. A
    backend-listen replica performs exactly ``FINALIZATION_PROJECTION_SHARD_COUNT``
    projection-document reads, regardless of terminal history size. Pre-release
    jobs carry no generation and remain absent from this new denominator; their
    terminal field is still preserved on the authoritative job document.
    """
    now = _now()
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
        shard_id = _projection_shard_id(FINALIZATION_PROJECTION_GENERATION, shard)
        snapshot = _store().get(f'{FINALIZATION_PROJECTION_COLLECTION}/{shard_id}')
        if not snapshot.exists:
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

    oldest_age_seconds = 0.0
    # The bounded due page prevents historical terminal rows from making the
    # periodic metric collection an ever-growing store scan.
    due = _store().query(
        FINALIZATION_JOBS_COLLECTION, filters=[('reconcile_after_at', '<=', now)], limit=100
    )
    for snapshot in due:
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
