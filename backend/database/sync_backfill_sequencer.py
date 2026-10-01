"""Durable per-UID dispatch ownership for accepted backfill sync jobs.

Pending jobs are separate documents so a large account never grows a single
Firestore document without bound. Only one payload per UID is active; Cloud
Tasks sees that job only after its owner/epoch has committed.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from google.cloud import firestore
from google.api_core.exceptions import NotFound

from database._client import get_firestore_client
from utils.sync import stage as sync_stage

logger = logging.getLogger(__name__)

COLLECTION = 'sync_backfill_sequencer'
PENDING_COLLECTION = 'sync_backfill_pending'
LEASE_SECONDS = 30 * 60  # Longer than a Cloud Task dispatch deadline (25 minutes).
HEARTBEAT_SECONDS = 120
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
    if not isinstance(uid, str) or not uid.strip() or '/' in uid:
        raise ValueError('uid must be a non-empty string without slashes')
    return client.collection(COLLECTION).document(uid.strip())


def _pending_ref(client: Any, uid: str, job_id: str) -> Any:
    if not isinstance(job_id, str) or not job_id.strip() or '/' in job_id:
        raise ValueError('job_id must be a non-empty string without slashes')
    return client.collection(PENDING_COLLECTION).document(job_id.strip())


def _pending_for_uid(client: Any, uid: str) -> Any:
    if not isinstance(uid, str) or not uid.strip() or '/' in uid:
        raise ValueError('uid must be a non-empty string without slashes')
    return client.collection(PENDING_COLLECTION).where('uid', '==', uid.strip())


def _data(snapshot: Any) -> dict[str, Any]:
    return snapshot.to_dict() or {} if getattr(snapshot, 'exists', False) else {}


def is_registered(uid: str, job_id: str, *, firestore_client: Any = None) -> bool:
    """Resolve an uncertain admission acknowledgement without dropping durable work."""
    _require_production()
    if not isinstance(uid, str) or not uid.strip() or '/' in uid:
        raise ValueError('uid must be a non-empty string without slashes')
    if not isinstance(job_id, str) or not job_id.strip() or '/' in job_id:
        raise ValueError('job_id must be a non-empty string without slashes')
    client = firestore_client or get_firestore_client()
    if _data(_pending_ref(client, uid, job_id).get()):
        return True
    return _data(_root(client, uid).get()).get('active_job_id') == job_id.strip()


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
    if not isinstance(uid, str) or not uid.strip() or '/' in uid:
        raise ValueError('uid must be a non-empty string without slashes')
    if not isinstance(job_id, str) or not job_id.strip() or '/' in job_id:
        raise ValueError('job_id must be a non-empty string without slashes')
    if not isinstance(payload, dict):
        raise ValueError('payload must be a dictionary')

    uid = uid.strip()
    job_id = job_id.strip()
    client = firestore_client or get_firestore_client()
    root = _root(client, uid)
    pending = _pending_ref(client, uid, job_id)
    accepted_at = now or _now()
    if accepted_at.tzinfo is None:
        accepted_at = accepted_at.replace(tzinfo=timezone.utc)
    try:
        sort_at = (
            datetime.fromtimestamp(oldest_capture_at, timezone.utc) if oldest_capture_at is not None else accepted_at
        )
    except (OverflowError, OSError, ValueError):
        sort_at = accepted_at

    @firestore.transactional
    def commit(transaction: Any) -> bool:
        existing = _data(pending.get(transaction=transaction))
        owner = _data(root.get(transaction=transaction))
        if existing or owner.get('active_job_id') == job_id:
            return False
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
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError('limit must be a positive integer')
    clamped_limit = max(1, min(limit, 500))
    client = firestore_client or get_firestore_client()
    docs = (
        client.collection(PENDING_COLLECTION)
        .where('reconcile_at', '<=', now or _now())
        .limit(clamped_limit)
        .stream()
    )
    return [{'id': doc.id, **_data(doc)} for doc in docs]


def defer_pending(job_id: str, *, firestore_client: Any = None, now: Optional[datetime] = None) -> None:
    _require_production()
    if not isinstance(job_id, str) or not job_id.strip() or '/' in job_id:
        raise ValueError('job_id must be a non-empty string without slashes')
    job_id = job_id.strip()
    client = firestore_client or get_firestore_client()
    try:
        client.collection(PENDING_COLLECTION).document(job_id).update(
            {'reconcile_at': (now or _now()) + timedelta(minutes=5)}
        )
    except NotFound:
        pass  # Another dispatcher already claimed this pending document.


def claim_next(uid: str, *, firestore_client: Any = None, now: Optional[datetime] = None) -> Optional[dict[str, Any]]:
    """Promote the oldest waiting capture into a fenced dispatch reservation."""
    _require_production()
    if not isinstance(uid, str) or not uid.strip() or '/' in uid:
        raise ValueError('uid must be a non-empty string without slashes')
    uid = uid.strip()
    client = firestore_client or get_firestore_client()
    root = _root(client, uid)
    current = now or _now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)

    @firestore.transactional
    def commit(transaction: Any) -> Optional[dict[str, Any]]:
        owner = _data(root.get(transaction=transaction))
        if owner.get('active_job_id'):
            return None
        # Read the ordered query inside the same transaction as the owner
        # claim. A separate preselection can miss an earlier capture admitted
        # just before the claim commits.
        candidate = _first_pending(client, uid, transaction=transaction)
        if candidate is None:
            return None
        pending = _pending_ref(client, uid, candidate['id'])
        job = _data(pending.get(transaction=transaction))
        if not job:
            return None
        epoch = int(owner.get('epoch') or 0) + 1
        active = {
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
    if not isinstance(uid, str) or not uid.strip() or '/' in uid:
        raise ValueError('uid must be a non-empty string without slashes')
    if not isinstance(job_id, str) or not job_id.strip() or '/' in job_id:
        raise ValueError('job_id must be a non-empty string without slashes')
    if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 0:
        raise ValueError('epoch must be a non-negative integer')

    uid = uid.strip()
    job_id = job_id.strip()
    client = firestore_client or get_firestore_client()
    root = _root(client, uid)
    current = now or _now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)

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
    if not isinstance(uid, str) or not uid.strip() or '/' in uid:
        raise ValueError('uid must be a non-empty string without slashes')
    if not isinstance(job_id, str) or not job_id.strip() or '/' in job_id:
        raise ValueError('job_id must be a non-empty string without slashes')
    if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 0:
        raise ValueError('epoch must be a non-negative integer')

    uid = uid.strip()
    job_id = job_id.strip()
    client = firestore_client or get_firestore_client()
    root = _root(client, uid)
    current = now or _now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)

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
    if not isinstance(uid, str) or not uid.strip() or '/' in uid:
        raise ValueError('uid must be a non-empty string without slashes')
    if not isinstance(job_id, str) or not job_id.strip() or '/' in job_id:
        raise ValueError('job_id must be a non-empty string without slashes')
    if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 0:
        raise ValueError('epoch must be a non-negative integer')

    uid = uid.strip()
    job_id = job_id.strip()
    client = firestore_client or get_firestore_client()
    root = _root(client, uid)

    @firestore.transactional
    def commit(transaction: Any) -> bool:
        owner = _data(root.get(transaction=transaction))
        if owner.get('active_job_id') != job_id or owner.get('active_epoch') != epoch:
            return False
        transaction.delete(root)
        return True

    released = commit(client.transaction())
    if released:
        logger.info('event=sync_uid_sequencer action=finished outcome=%s', outcome)
    return released


def get_owner(uid: str, *, firestore_client: Any = None) -> dict[str, Any]:
    _require_production()
    if not isinstance(uid, str) or not uid.strip() or '/' in uid:
        raise ValueError('uid must be a non-empty string without slashes')
    client = firestore_client or get_firestore_client()
    return _data(_root(client, uid.strip()).get())


def due_owners(
    *, limit: int = 100, firestore_client: Any = None, now: Optional[datetime] = None
) -> list[dict[str, Any]]:
    _require_production()
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError('limit must be a positive integer')
    clamped_limit = max(1, min(limit, 500))
    client = firestore_client or get_firestore_client()
    docs = (
        client.collection(COLLECTION).where('reconcile_at', '<=', now or _now()).limit(clamped_limit).stream()
    )
    return [{'uid': doc.id, **_data(doc)} for doc in docs]


def defer_owner(uid: str, seconds: int, *, firestore_client: Any = None, now: Optional[datetime] = None) -> None:
    _require_production()
    client = firestore_client or get_firestore_client()
    root = _root(client, uid)
    current = now or _now()
    root.update({'reconcile_at': current + timedelta(seconds=seconds), 'updated_at': current})


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
