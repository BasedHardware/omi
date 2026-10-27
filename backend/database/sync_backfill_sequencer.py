"""Durable per-UID dispatch ownership for accepted backfill sync jobs.

Pending jobs are separate documents so a large account never grows a single
Firestore document without bound. Only one payload per UID is active; Cloud
Tasks sees that job only after its owner/epoch has committed.
"""

from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from google.cloud import firestore
from google.api_core.exceptions import NotFound
from prometheus_client import Counter

from database._client import get_firestore_client
from database import sync_redrive
from database.sync_ledger import is_valid_completed_sync_content_result
from config.firestore_read_levers import lever_enabled
from config.sync_owner_concurrency import backlog_threshold, preparation_width
from utils.sync import stage as sync_stage
from utils.sync.backfill_order import newest_first
from utils.sync.retry_hygiene import dispatch_cap

logger = logging.getLogger(__name__)
OWNER_REPAIRED = Counter('sync_backfill_owner_repaired', 'Missing backfill owners recreated')

COLLECTION = 'sync_backfill_sequencer'

# Must match utils.cloud_tasks.SYNC_JOB_BUDGET_DEFERRALS_PAYLOAD_KEY (pinned by
# test): the handler-budget chain count rides task payloads, and a lease-expiry
# redrive re-dispatches the owner's original ``active_payload`` — without this
# persisted copy the redrive would restart the chain at zero.
BUDGET_DEFERRALS_PAYLOAD_KEY = 'budget_deferrals'
PENDING_COLLECTION = 'sync_backfill_pending'
LEASE_SECONDS = 30 * 60  # Running lease; queue wait is unbounded by the dispatch deadline.
HEARTBEAT_SECONDS = 120
DEFAULT_REPAIR_WINDOW_SECONDS = 30 * 60
DISPATCH_RETRY_SECONDS = 5 * 60
WAIT_ALERT_SECONDS = 12 * 60 * 60  # Well before Redis job / staged blob expiry.


def enabled() -> bool:
    """An absent setting and phase-one dev/prod manifests keep direct dispatch."""
    return production_stage() and os.getenv('SYNC_BACKFILL_UID_SEQUENCER', 'off').strip().lower() == 'on'


def production_stage() -> bool:
    """The legacy registry belongs exclusively to the production runtime.

    The customer Firestore project is also mounted in dev, so the Firestore
    project ID cannot identify the sequencer owner.
    """
    return sync_stage.production_stage()


def _require_production() -> None:
    if not production_stage():
        raise RuntimeError('sync backfill UID sequencer registry is production-only')


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _root(client: Any, uid: str) -> Any:
    return client.collection(COLLECTION).document(uid)


def _pending_ref(client: Any, uid: str, job_id: str) -> Any:
    return client.collection(PENDING_COLLECTION).document(job_id)


def _pending_for_uid(client: Any, uid: str) -> Any:
    return client.collection(PENDING_COLLECTION).where('uid', '==', uid)


def _data(snapshot: Any) -> dict[str, Any]:
    return snapshot.to_dict() or {} if getattr(snapshot, 'exists', False) else {}


def is_registered(uid: str, job_id: str, *, firestore_client: Any = None) -> bool:
    """Resolve an uncertain admission acknowledgement without dropping durable work."""
    _require_production()
    client = firestore_client or get_firestore_client()
    if _data(_pending_ref(client, uid, job_id).get()):
        return True
    return _data(_root(client, uid).get()).get('active_job_id') == job_id


def _ensure_owner(
    transaction: Any, root: Any, owner: dict[str, Any], current: datetime, *, repair_at: Optional[datetime] = None
) -> bool:
    """Create or wake an owner after all reads, without resetting its epoch."""
    if owner:
        if 'reconcile_at' not in owner:
            transaction.update(root, {'reconcile_at': current, 'updated_at': current})
        return False
    data = {'epoch': 0, 'reconcile_at': repair_at or current, 'updated_at': current}
    if repair_at is not None:
        data['repair_not_before'] = repair_at
    transaction.set(root, data)
    return True


def repair_window_seconds(value: Optional[int] = None) -> int:
    window = (
        value
        if value is not None
        else int(os.getenv('SYNC_BACKFILL_OWNER_REPAIR_WINDOW_SECONDS', str(DEFAULT_REPAIR_WINDOW_SECONDS)))
    )
    if window < 1:
        raise ValueError('repair window must be positive')
    return window


def _repair_waiting(owner: dict[str, Any], current: datetime) -> bool:
    deadline = owner.get('repair_not_before')
    return isinstance(deadline, datetime) and deadline > current


def _has_pending(client: Any, uid: str, *, transaction: Any, excluding_job_id: Optional[str] = None) -> bool:
    # Two unordered entries suffice to prove a successor when retiring one.
    docs = _pending_for_uid(client, uid).limit(2 if excluding_job_id is not None else 1).stream(transaction=transaction)
    return any(doc.id != excluding_job_id for doc in docs)


def repair_owner(
    uid: str,
    *,
    dry_run: bool = False,
    repair_window: Optional[int] = None,
    firestore_client: Any = None,
    now: Optional[datetime] = None,
) -> bool:
    """Repair only while pending entries still exist for this UID.

    The queue and owner are read together: a stale scan cannot resurrect
    an empty queue or overwrite a concurrent dispatch. Dry-run uses a read-only
    transaction and reports whether a repair would be needed. Scheduled repair
    is spread over the configured window and respected by pending fallback kicks.
    """
    _require_production()
    client = firestore_client or get_firestore_client()
    root = _root(client, uid)
    current = now or _now()
    repair_at = current + timedelta(seconds=1 + secrets.randbelow(repair_window_seconds(repair_window)))

    @firestore.transactional
    def commit(transaction: Any) -> bool:
        owner = _data(root.get(transaction=transaction))
        if owner:
            return False
        if not _has_pending(client, uid, transaction=transaction):
            return False
        return True if dry_run else _ensure_owner(transaction, root, owner, current, repair_at=repair_at)

    repaired = commit(client.transaction(read_only=True) if dry_run else client.transaction())
    if repaired and not dry_run:
        OWNER_REPAIRED.inc()
        logger.info('event=sync_backfill_owner_repaired count=1')
    return repaired


def _release_owner(transaction: Any, root: Any, owner: dict[str, Any], current: datetime, *, has_pending: bool) -> None:
    # Retain the fencing epoch indefinitely. Missing reconcile_at excludes an
    # empty owner from the range query; admission transactionally wakes it.
    data = {
        'epoch': max(int(owner.get('epoch') or 0), int(owner.get('active_epoch') or 0)),
        'updated_at': current,
    }
    if has_pending:
        data['reconcile_at'] = current
    transaction.set(root, data)


def register_job(
    uid: str,
    job_id: str,
    payload: dict[str, Any],
    oldest_capture_at: Optional[float],
    *,
    firestore_client: Any = None,
    now: Optional[datetime] = None,
) -> bool:
    """Persist an accepted job before 202; safe to repeat after an uncertain write."""
    _require_production()
    client = firestore_client or get_firestore_client()
    root = _root(client, uid)
    pending = _pending_ref(client, uid, job_id)
    accepted_at = now or _now()
    try:
        sort_at = (
            datetime.fromtimestamp(oldest_capture_at, timezone.utc) if oldest_capture_at is not None else accepted_at
        )
    except (OverflowError, OSError, ValueError):
        sort_at = accepted_at

    @firestore.transactional
    def commit(transaction: Any) -> bool:
        # Match claim/release/parking lock order; reading pending first can
        # deadlock a concurrent owner-first presence query in pessimistic mode.
        owner = _data(root.get(transaction=transaction))
        existing = _data(pending.get(transaction=transaction))
        if existing or owner.get('active_job_id') == job_id:
            _ensure_owner(transaction, root, owner, accepted_at)
            return False
        _ensure_owner(transaction, root, owner, accepted_at)
        transaction.set(
            pending,
            {
                'job_id': job_id,
                'uid': uid,
                'payload': payload,
                'sort_at': sort_at,
                'accepted_at': accepted_at,
                'reconcile_at': accepted_at + timedelta(seconds=HEARTBEAT_SECONDS),
            },
        )
        return True

    created = commit(client.transaction())
    if created:
        logger.info('event=sync_uid_sequencer action=registered outcome=queued')
    return created


def _first_pending(client: Any, uid: str, *, transaction: Any = None) -> Optional[dict[str, Any]]:
    query = _pending_for_uid(client, uid)
    query = (
        query.order_by('sort_at', direction=firestore.Query.DESCENDING)
        if newest_first(uid)
        else query.order_by('sort_at')
    )
    docs = list(query.limit(1).stream(transaction=transaction))
    return {'id': docs[0].id, **_data(docs[0])} if docs else None


def has_pending(uid: str, *, firestore_client: Any = None) -> bool:
    _require_production()
    client = firestore_client or get_firestore_client()
    return _first_pending(client, uid) is not None


def waiting_sample(uid: str, *, firestore_client: Any = None, now: Optional[datetime] = None) -> dict[str, Any]:
    _require_production()
    client = firestore_client or get_firestore_client()
    if lever_enabled('backfill_task_reads', uid):
        # Preserve capped depth, oldest identity, and missing-order-field
        # semantics. The read-only transaction pins both RPCs to one snapshot;
        # an independent head/count pair could disagree during dispatch.
        @firestore.transactional
        def read(transaction: Any) -> dict[str, Any]:
            query = _pending_for_uid(client, uid).order_by('accepted_at')
            docs = list(query.limit(2).stream(transaction=transaction))
            if not docs:
                return {'depth': 0, 'age_seconds': 0.0, 'job_id': ''}
            depth = len(docs)
            if depth == 2:
                depth = int(query.limit(100).count().get(transaction=transaction)[0][0].value)
            accepted_at = _data(docs[0]).get('accepted_at')
            age = (
                max(0.0, ((now or _now()) - accepted_at).total_seconds()) if isinstance(accepted_at, datetime) else 0.0
            )
            return {'depth': depth, 'age_seconds': age, 'job_id': docs[0].id}

        return read(client.transaction(read_only=True))
    docs = list(_pending_for_uid(client, uid).order_by('accepted_at').limit(100).stream())
    if not docs:
        return {'depth': 0, 'age_seconds': 0.0, 'job_id': ''}
    accepted_at = _data(docs[0]).get('accepted_at')
    age = max(0.0, ((now or _now()) - accepted_at).total_seconds()) if isinstance(accepted_at, datetime) else 0.0
    return {'depth': len(docs), 'age_seconds': age, 'job_id': docs[0].id}


def due_pending(
    *, limit: int = 100, firestore_client: Any = None, now: Optional[datetime] = None
) -> list[dict[str, Any]]:
    _require_production()
    client = firestore_client or get_firestore_client()
    docs = (
        client.collection(PENDING_COLLECTION)
        .where('reconcile_at', '<=', now or _now())
        .limit(max(1, min(limit, 500)))
        .stream()
    )
    return [{'id': doc.id, **_data(doc)} for doc in docs]


def defer_pending(job_id: str, *, firestore_client: Any = None, now: Optional[datetime] = None) -> None:
    _require_production()
    client = firestore_client or get_firestore_client()
    try:
        client.collection(PENDING_COLLECTION).document(job_id).update(
            {'reconcile_at': (now or _now()) + timedelta(minutes=5)}
        )
    except NotFound:
        pass  # Another dispatcher already claimed this pending document.


def pending_head(uid: str, *, firestore_client: Any = None) -> Optional[dict[str, Any]]:
    """Inspect a candidate; retirement rechecks owner and candidate atomically."""
    _require_production()
    client = firestore_client or get_firestore_client()
    owner = _data(_root(client, uid).get())
    if owner.get('active_job_id') or _repair_waiting(owner, _now()):
        return None
    return _first_pending(client, uid)


def preparation_candidates(uid: str, job_id: str, epoch: int, *, firestore_client: Any = None) -> list[dict[str, Any]]:
    """Snapshot a bounded ordered prefix without reserving or dispatching it.

    Epoch validation prevents obsolete heads initiating more speculative I/O.
    Preparation grants no execution authority; claim_next must still select
    its head transactionally after the active job finishes.
    """
    _require_production()
    width = preparation_width()
    if width <= 1:
        return []
    client = firestore_client or get_firestore_client()

    @firestore.transactional
    def read(transaction: Any) -> list[dict[str, Any]]:
        owner = _data(_root(client, uid).get(transaction=transaction))
        if (
            owner.get('active_job_id') != job_id
            or owner.get('active_epoch') != epoch
            or owner.get('active_state') != 'running'
        ):
            return []
        query = _pending_for_uid(client, uid)
        query = (
            query.order_by('sort_at', direction=firestore.Query.DESCENDING)
            if newest_first(uid)
            else query.order_by('sort_at')
        )
        threshold = backlog_threshold()
        docs = list(query.limit(threshold).stream(transaction=transaction))
        if len(docs) < threshold:
            return []
        return [_data(doc) for doc in docs[: width - 1]]

    return read(client.transaction(read_only=True))


def retire_expired(
    uid: str,
    job_id: str,
    *,
    epoch: Optional[int] = None,
    allow_active_owner: bool = False,
    firestore_client: Any = None,
    now: Optional[datetime] = None,
) -> bool:
    """Retire exact unbound work while caller holds its Redis lock and proves absence.

    An epoch selects an already-dispatching owner. A worker that began running
    wins the transaction race. Waiting retirement can repair a missing idle
    owner but never releases an active reservation.
    """
    _require_production()
    client = firestore_client or get_firestore_client()
    root = _root(client, uid)
    pending = _pending_ref(client, uid, job_id)
    current = now or _now()

    @firestore.transactional
    def commit(transaction: Any) -> bool:
        owner = _data(root.get(transaction=transaction))
        if epoch is None:
            if (owner.get('active_job_id') and not allow_active_owner) or _repair_waiting(owner, current):
                return False
            if owner.get('active_job_id') == job_id:
                return False
            job = _data(pending.get(transaction=transaction))
            payload = job.get('payload') or {}
            accepted = job.get('accepted_at', current)
            if job.get('uid') != uid or job.get('job_id') != job_id:
                return False
        else:
            if (
                owner.get('active_job_id') != job_id
                or owner.get('active_epoch') != epoch
                or owner.get('active_state') != 'dispatching'
            ):
                return False
            payload = owner.get('active_payload') or {}
            accepted = owner.get('active_accepted_at', current)
        content_id = payload.get('content_id')
        ledger = None
        claim = {}
        if isinstance(content_id, str) and content_id and '/' not in content_id:
            ledger = client.collection('users').document(uid).collection('sync_content_ledger').document(content_id)
            claim = _data(ledger.get(transaction=transaction))
        elif content_id is not None:
            return False
        preserve_owner = epoch is None and bool(owner.get('active_job_id'))
        has_pending = (
            False
            if preserve_owner
            else _has_pending(client, uid, transaction=transaction, excluding_job_id=job_id if epoch is None else None)
        )
        durable_completed = (
            sync_redrive.enabled()
            and claim.get('status') == 'completed'
            and is_valid_completed_sync_content_result(claim.get('result'))
        )
        guarded = sync_redrive.enabled() and not durable_completed
        prepared = None
        if guarded:
            # Never transfer a bound run or another job's content ownership.
            if (
                claim.get('job_id') not in (None, job_id)
                or claim.get('ledger_run_token') is not None
                or claim.get('ledger_run_epoch') is not None
            ):
                return False
            prepared = sync_redrive.prepare(transaction, client, uid, job_id, payload, accepted)
        if claim.get('job_id') == job_id and not durable_completed:
            if (
                claim.get('status') != 'processing'
                or claim.get('ledger_run_token') is not None
                or claim.get('ledger_run_epoch') is not None
            ):
                return False
            transaction.update(
                ledger,
                {
                    'status': 'retryable',
                    'job_id': firestore.DELETE_FIELD,
                    'updated_at': current,
                },
            )
        if prepared is not None:
            sync_redrive.retain(transaction, prepared)
        if not preserve_owner:
            _release_owner(transaction, root, owner, current, has_pending=has_pending)
        if epoch is None:
            transaction.delete(pending)
        return True

    return commit(client.transaction())


def claim_next(
    uid: str, *, expected_job_id: Optional[str] = None, firestore_client: Any = None, now: Optional[datetime] = None
) -> Optional[dict[str, Any]]:
    """Promote the configured waiting capture into a fenced dispatch reservation."""
    _require_production()
    client = firestore_client or get_firestore_client()
    root = _root(client, uid)
    current = now or _now()

    @firestore.transactional
    def commit(transaction: Any) -> Optional[dict[str, Any]]:
        owner = _data(root.get(transaction=transaction))
        if owner.get('active_job_id') or _repair_waiting(owner, current):
            return None
        # Read the ordered query inside the same transaction as the owner
        # claim. A separate preselection can miss an earlier capture admitted
        # just before the claim commits.
        candidate = _first_pending(client, uid, transaction=transaction)
        if candidate is None:
            if owner:
                _release_owner(transaction, root, owner, current, has_pending=False)
            return None
        if expected_job_id is not None and candidate.get('job_id') != expected_job_id:
            # The Redis proof belongs to a different head. Let the next kick
            # inspect the new oldest entry before reserving any dispatch.
            return None
        pending = _pending_ref(client, uid, candidate['id'])
        job = _data(pending.get(transaction=transaction))
        if not job:
            return None
        epoch = max(int(owner.get('epoch') or 0), int(owner.get('active_epoch') or 0)) + 1
        active = {
            'epoch': epoch,
            'repair_not_before': firestore.DELETE_FIELD,
            'active_job_id': job['job_id'],
            'active_payload': job['payload'],
            'active_epoch': epoch,
            'dispatch_attempt': 0,
            'active_state': 'dispatching',
            'active_accepted_at': job['accepted_at'],
            'active_since': current,
            'lease_expires_at': current + timedelta(seconds=LEASE_SECONDS),
            'dispatch_retry_at': current + timedelta(seconds=DISPATCH_RETRY_SECONDS),
            'reconcile_at': current + timedelta(seconds=HEARTBEAT_SECONDS),
            'updated_at': current,
        }
        transaction.set(root, active, merge=True)
        transaction.delete(pending)
        return {
            'uid': uid,
            'job_id': job['job_id'],
            'payload': job['payload'],
            'epoch': epoch,
            'accepted_at': job['accepted_at'],
        }

    return commit(client.transaction())


def begin_job(
    uid: str, job_id: str, epoch: int, *, firestore_client: Any = None, now: Optional[datetime] = None
) -> bool:
    """A stale Cloud Task epoch can never enter the transcription pipeline."""
    _require_production()
    client = firestore_client or get_firestore_client()
    root = _root(client, uid)
    current = now or _now()

    @firestore.transactional
    def commit(transaction: Any) -> bool:
        owner = _data(root.get(transaction=transaction))
        if owner.get('active_job_id') != job_id or owner.get('active_epoch') != epoch:
            return False
        transaction.update(
            root,
            {
                'active_state': 'running',
                'lease_expires_at': current + timedelta(seconds=LEASE_SECONDS),
                'reconcile_at': current + timedelta(seconds=HEARTBEAT_SECONDS),
                'updated_at': current,
            },
        )
        return True

    try:
        return commit(client.transaction())
    except NotFound:
        return False


def renew_job(
    uid: str, job_id: str, epoch: int, *, firestore_client: Any = None, now: Optional[datetime] = None
) -> bool:
    _require_production()
    client = firestore_client or get_firestore_client()
    root = _root(client, uid)
    current = now or _now()

    @firestore.transactional
    def commit(transaction: Any) -> bool:
        owner = _data(root.get(transaction=transaction))
        if owner.get('active_job_id') != job_id or owner.get('active_epoch') != epoch:
            return False
        transaction.update(
            root,
            {
                'lease_expires_at': current + timedelta(seconds=LEASE_SECONDS),
                'reconcile_at': current + timedelta(seconds=HEARTBEAT_SECONDS),
                'updated_at': current,
            },
        )
        return True

    try:
        return commit(client.transaction())
    except NotFound:
        return False


def finish_job(
    uid: str, job_id: str, epoch: int, outcome: str, *, firestore_client: Any = None, now: Optional[datetime] = None
) -> bool:
    """Only the current epoch releases the UID; duplicate completion is inert."""
    _require_production()
    client = firestore_client or get_firestore_client()
    root = _root(client, uid)
    current = now or _now()

    @firestore.transactional
    def commit(transaction: Any) -> bool:
        owner = _data(root.get(transaction=transaction))
        if owner.get('active_job_id') != job_id or owner.get('active_epoch') != epoch:
            return False
        has_pending = _has_pending(client, uid, transaction=transaction)
        _release_owner(transaction, root, owner, current, has_pending=has_pending)
        return True

    released = commit(client.transaction())
    if released:
        logger.info('event=sync_uid_sequencer action=finished outcome=%s', outcome)
    return released


def get_owner(uid: str, *, firestore_client: Any = None) -> dict[str, Any]:
    _require_production()
    client = firestore_client or get_firestore_client()
    return _data(_root(client, uid).get())


def due_owners(
    *, limit: int = 100, firestore_client: Any = None, now: Optional[datetime] = None
) -> list[dict[str, Any]]:
    _require_production()
    client = firestore_client or get_firestore_client()
    docs = (
        client.collection(COLLECTION).where('reconcile_at', '<=', now or _now()).limit(max(1, min(limit, 500))).stream()
    )
    return [{'uid': doc.id, **_data(doc)} for doc in docs]


def defer_owner(uid: str, seconds: int, *, firestore_client: Any = None, now: Optional[datetime] = None) -> None:
    _require_production()
    client = firestore_client or get_firestore_client()
    root = _root(client, uid)
    current = now or _now()

    @firestore.transactional
    def commit(transaction: Any) -> None:
        owner = _data(root.get(transaction=transaction))
        if not owner:
            return
        if not owner.get('active_job_id') and not _has_pending(client, uid, transaction=transaction):
            _release_owner(transaction, root, owner, current, has_pending=False)
            return
        reconcile_at = current + timedelta(seconds=seconds)
        if _repair_waiting(owner, reconcile_at):
            reconcile_at = owner['repair_not_before']
        transaction.update(root, {'reconcile_at': reconcile_at, 'updated_at': current})

    try:
        commit(client.transaction())
    except NotFound:
        pass


def note_budget_deferral(
    uid: str, job_id: str, epoch: int, deferrals: int, *, firestore_client: Any = None, now: Optional[datetime] = None
) -> bool:
    """Persist the handler-budget chain count on the running owner.

    The count rides task payloads, but ``redrive_job`` re-dispatches the
    owner's original ``active_payload``; without this copy, a lease that
    expires before the delayed replacement begins would restart the chain at
    zero and an over-budget job could defer forever.

    Returns ``True`` when the count was written and ``False`` when the owner
    no longer names this job/epoch (completed or released elsewhere) — the
    caller must treat ``False`` as "nothing left to protect", not as a
    failure. Transient Firestore failures raise: the write precedes the
    replacement enqueue precisely so a lost count can abort the deferral
    before any replacement exists.
    """
    _require_production()
    client = firestore_client or get_firestore_client()
    root = _root(client, uid)
    current = now or _now()

    @firestore.transactional
    def commit(transaction: Any) -> bool:
        owner = _data(root.get(transaction=transaction))
        if owner.get('active_job_id') != job_id or owner.get('active_epoch') != epoch:
            return False
        transaction.update(root, {'active_budget_deferrals': deferrals, 'updated_at': current})
        return True

    try:
        return commit(client.transaction())
    except NotFound:
        return False


def finish_expired_job(
    uid: str,
    job_id: str,
    epoch: int,
    outcome: str,
    *,
    firestore_client: Any = None,
    now: Optional[datetime] = None,
) -> bool:
    """Release an owner whose lease expired, fenced exactly like redrive_job.

    The deadline is re-checked inside the transaction: a delivery that began
    and renewed between the sweeper's read and this write must never be
    released out from under its running worker.
    """
    _require_production()
    client = firestore_client or get_firestore_client()
    root = _root(client, uid)
    current = now or _now()

    @firestore.transactional
    def commit(transaction: Any) -> bool:
        owner = _data(root.get(transaction=transaction))
        if owner.get('active_job_id') != job_id or owner.get('active_epoch') != epoch:
            return False
        dispatching = owner.get('active_state') == 'dispatching'
        deadline = owner.get('dispatch_retry_at' if dispatching else 'lease_expires_at')
        if not isinstance(deadline, datetime) or deadline > current:
            return False
        has_pending = _has_pending(client, uid, transaction=transaction)
        _release_owner(transaction, root, owner, current, has_pending=has_pending)
        return True

    released = False
    try:
        released = commit(client.transaction())
    except NotFound:
        return False
    if released:
        logger.info('event=sync_uid_sequencer action=finished outcome=%s', outcome)
    return released


def owner_release_due(
    uid: str,
    job_id: str,
    epoch: int,
    *,
    firestore_client: Any = None,
    now: Optional[datetime] = None,
) -> bool:
    """Read-only form of :func:`finish_expired_job`'s release fence.

    Returns whether the owner still names this job/epoch and its deadline
    (dispatch retry while dispatching, else the lease) has passed — the
    exact preconditions under which ``finish_expired_job`` would release.
    The budget-chain finalizer uses it after acquiring the finalization run
    lock to prove no delivery renewed the lease after the sweeper's
    expired-owner read, without mutating the owner.
    """
    _require_production()
    client = firestore_client or get_firestore_client()
    root = _root(client, uid)
    current = now or _now()

    @firestore.transactional
    def check(transaction: Any) -> bool:
        owner = _data(root.get(transaction=transaction))
        if owner.get('active_job_id') != job_id or owner.get('active_epoch') != epoch:
            return False
        dispatching = owner.get('active_state') == 'dispatching'
        deadline = owner.get('dispatch_retry_at' if dispatching else 'lease_expires_at')
        if not isinstance(deadline, datetime) or deadline > current:
            return False
        return True

    try:
        return check(client.transaction())
    except NotFound:
        return False


def redrive_job(
    uid: str, job_id: str, epoch: int, *, firestore_client: Any = None, now: Optional[datetime] = None
) -> Optional[dict[str, Any]]:
    """Retry queued dispatch within its cap; fence expired running work."""
    _require_production()
    client = firestore_client or get_firestore_client()
    root = _root(client, uid)
    current = now or _now()

    @firestore.transactional
    def commit(transaction: Any) -> Optional[dict[str, Any]]:
        owner = _data(root.get(transaction=transaction))
        if owner.get('active_job_id') != job_id or owner.get('active_epoch') != epoch:
            return None
        dispatching = owner.get('active_state') == 'dispatching'
        deadline_field = 'dispatch_retry_at' if dispatching else 'lease_expires_at'
        deadline = owner.get(deadline_field)
        if not isinstance(deadline, datetime) or deadline > current:
            return None
        cap = dispatch_cap(uid, owner) if dispatching else None
        if cap is not None and cap.reached and cap.serving:
            return None  # The reconciler owns the fenced terminal handoff.
        # refactor: superseded by retry_hygiene when CAPTURE_COVERAGE_MODE=serve
        # Preserve epochs across uncertain enqueues: queue latency is not lost ownership.
        next_epoch = epoch if dispatching else epoch + 1
        dispatch_attempt = int(owner.get('dispatch_attempt') or 0) + 1 if dispatching else 0
        # Restore the persisted budget chain count across lease expiry.
        payload = dict(owner['active_payload'])
        deferrals = owner.get('active_budget_deferrals')
        if isinstance(deferrals, int) and not isinstance(deferrals, bool) and deferrals > 0:
            payload[BUDGET_DEFERRALS_PAYLOAD_KEY] = deferrals
        transaction.update(
            root,
            {
                'epoch': next_epoch,
                'active_epoch': next_epoch,
                'dispatch_attempt': dispatch_attempt,
                'active_state': 'dispatching',
                'lease_expires_at': current + timedelta(seconds=LEASE_SECONDS),
                'dispatch_retry_at': current + timedelta(seconds=DISPATCH_RETRY_SECONDS),
                'reconcile_at': current + timedelta(seconds=HEARTBEAT_SECONDS),
                'updated_at': current,
            },
        )
        return {
            'uid': uid,
            'job_id': job_id,
            'payload': payload,
            'epoch': next_epoch,
            'dispatch_attempt': dispatch_attempt,
            'accepted_at': owner['active_accepted_at'],
        }

    try:
        replacement = commit(client.transaction())
    except NotFound:
        return None
    if replacement:
        logger.warning('event=sync_uid_sequencer action=redrive outcome=lease_expired')
    return replacement
