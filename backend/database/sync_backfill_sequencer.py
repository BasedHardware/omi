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
from utils.sync import stage as sync_stage

logger = logging.getLogger(__name__)
OWNER_REPAIRED = Counter('sync_backfill_owner_repaired', 'Missing backfill owners recreated')

COLLECTION = 'sync_backfill_sequencer'
PENDING_COLLECTION = 'sync_backfill_pending'
LEASE_SECONDS = 30 * 60  # Longer than a Cloud Task dispatch deadline (25 minutes).
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
    docs = list(_pending_for_uid(client, uid).order_by('sort_at').limit(1).stream(transaction=transaction))
    return {'id': docs[0].id, **_data(docs[0])} if docs else None


def has_pending(uid: str, *, firestore_client: Any = None) -> bool:
    _require_production()
    client = firestore_client or get_firestore_client()
    return _first_pending(client, uid) is not None


def waiting_sample(uid: str, *, firestore_client: Any = None, now: Optional[datetime] = None) -> dict[str, Any]:
    _require_production()
    client = firestore_client or get_firestore_client()
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


def retire_expired(
    uid: str,
    job_id: str,
    *,
    epoch: Optional[int] = None,
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
            if owner.get('active_job_id') or _repair_waiting(owner, current):
                return False
            job = _data(pending.get(transaction=transaction))
            payload = job.get('payload') or {}
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
        content_id = payload.get('content_id')
        ledger = None
        claim = {}
        if isinstance(content_id, str) and content_id and '/' not in content_id:
            ledger = client.collection('users').document(uid).collection('sync_content_ledger').document(content_id)
            claim = _data(ledger.get(transaction=transaction))
        elif content_id is not None:
            return False
        has_pending = _has_pending(
            client, uid, transaction=transaction, excluding_job_id=job_id if epoch is None else None
        )
        if claim.get('job_id') == job_id:
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
        _release_owner(transaction, root, owner, current, has_pending=has_pending)
        if epoch is None:
            transaction.delete(pending)
        return True

    return commit(client.transaction())


def claim_next(
    uid: str, *, expected_job_id: Optional[str] = None, firestore_client: Any = None, now: Optional[datetime] = None
) -> Optional[dict[str, Any]]:
    """Promote the oldest waiting capture into a fenced dispatch reservation."""
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

    return commit(client.transaction())


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

    return commit(client.transaction())


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

    commit(client.transaction())


def redrive_job(
    uid: str, job_id: str, epoch: int, *, firestore_client: Any = None, now: Optional[datetime] = None
) -> Optional[dict[str, Any]]:
    """Replace a lost dispatch epoch, preserving the one active job and payload."""
    _require_production()
    client = firestore_client or get_firestore_client()
    root = _root(client, uid)
    current = now or _now()

    @firestore.transactional
    def commit(transaction: Any) -> Optional[dict[str, Any]]:
        owner = _data(root.get(transaction=transaction))
        if owner.get('active_job_id') != job_id or owner.get('active_epoch') != epoch:
            return None
        deadline_field = 'dispatch_retry_at' if owner.get('active_state') == 'dispatching' else 'lease_expires_at'
        deadline = owner.get(deadline_field)
        if not isinstance(deadline, datetime) or deadline > current:
            return None
        next_epoch = epoch + 1
        transaction.update(
            root,
            {
                'epoch': next_epoch,
                'active_epoch': next_epoch,
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
            'payload': owner['active_payload'],
            'epoch': next_epoch,
            'accepted_at': owner['active_accepted_at'],
        }

    replacement = commit(client.transaction())
    if replacement:
        logger.warning('event=sync_uid_sequencer action=redrive outcome=lease_expired')
    return replacement
