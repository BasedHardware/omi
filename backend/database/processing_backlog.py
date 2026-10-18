"""Metadata-only backlog totals, intent and transaction hooks. No transcript scans."""

from datetime import datetime
from typing import Any
from uuid import uuid4
import time
import hashlib

from google.cloud import firestore

COLLECTION = 'processing_backlog_items'
SUMMARY = 'processing_backlog'


def get_firestore_client():
    # Deferring this dependency keeps unflagged conversation imports inert.
    from database._client import get_firestore_client as client_factory

    return client_factory()


def external_write_fence(uid: str, *, firestore_client):
    from database.legal_holds import external_write_fence as open_fence

    return open_fence(uid, firestore_client=firestore_client)


def summary_ref(uid: str, *, firestore_client=None):
    return (
        (firestore_client or get_firestore_client())
        .collection('users')
        .document(uid)
        .collection(SUMMARY)
        .document('current')
    )


def items(uid: str, *, firestore_client=None):
    return (firestore_client or get_firestore_client()).collection('users').document(uid).collection(COLLECTION)


def read_processing_backlog_summary(uid: str) -> dict:
    """Deferred-processing summary document.

    Module-level so the Firestore read probe attributes the get to this
    function rather than a lambda or the request-memo wrapper.
    """
    return summary_ref(uid).get().to_dict() or {}


def _request_memo():
    """Load the request memo only when a backlog read or committed write needs it.

    Importing it registers Prometheus series. A fresh import of this module,
    such as the archive-filter seam, must not register those series again.
    """
    from database import fsr_read_cache

    return fsr_read_cache


def read(uid: str) -> dict:
    return _request_memo().memo(uid, 'processing_backlog_summary', lambda: read_processing_backlog_summary(uid))


def stage_transition(
    tx: Any, uid: str, conversation_id: str, existing: dict, incoming: dict, *, firestore_client=None
) -> bool:
    """Stage a summary mutation in the caller's transaction.

    Returns whether this attempt changed the summary. The caller drops the
    request memo only after that transaction commits. Clearing it here would
    let a concurrent reader refill the memo with the pre-commit document.
    """
    if 'processing_deferred' not in incoming:
        return False
    ref = items(uid, firestore_client=firestore_client).document(conversation_id)
    prior = ref.get(transaction=tx).to_dict() or {}
    row = None
    if incoming.get('processing_deferred') and not incoming.get('deleted'):
        estimate = (incoming.get('external_data') or {}).get('processing_backlog_estimate') or {}
        started = incoming.get('started_at') or incoming.get('created_at')
        row = {
            **{key: value for key, value in prior.items() if key.startswith('run_lease')},
            'started_at': started.timestamp() if isinstance(started, datetime) else 0,
            'seconds': float(estimate.get('seconds', 0)),
            'units': float(estimate.get('units', 0)),
            'queued_at': prior.get('queued_at', time.time()),
        }
    if row == prior or not row and not prior:
        return False
    tx.set(
        summary_ref(uid, firestore_client=firestore_client),
        {
            'count': firestore.Increment(int(bool(row)) - int(bool(prior))),
            'seconds': firestore.Increment((row or {}).get('seconds', 0) - prior.get('seconds', 0)),
            'units': firestore.Increment((row or {}).get('units', 0) - prior.get('units', 0)),
        },
        merge=True,
    )
    if row:
        tx.set(ref, row)
    else:
        tx.delete(ref)
    return True


def start(
    uid: str,
    *,
    period: str,
    remaining: float | None,
    cutoff: float,
    request_key: str,
    automatic: bool = False,
    begin: bool = True
) -> dict:
    """Idempotent while active; every run is fenced to its chosen month and cutoff."""
    client = get_firestore_client()
    ref = summary_ref(uid)

    receipt = ref.parent.parent.collection('processing_backlog_requests').document(
        hashlib.sha256(request_key.encode()).hexdigest()
    )

    @firestore.transactional
    def commit(tx):
        current = ref.get(transaction=tx).to_dict() or {}
        seen = receipt.get(transaction=tx)
        if seen.exists:
            return current
        tx.create(receipt, {'period': period, 'created_at': time.time(), 'accepted': begin})
        if not begin:
            return current
        if current.get('state') == 'processing' and current.get('period') == period:
            if automatic:
                # Upgrade intent may extend an earlier partial choice, without
                # replacing the lease/cursors of work already in progress.
                pending = {'period': period, 'remaining': remaining, 'cutoff': cutoff}
                tx.update(ref, {'pending_upgrade': pending})
                return {**current, 'pending_upgrade': pending}
            return current
        updates = {
            'state': 'processing',
            'period': period,
            'token': uuid4().hex,
            'cutoff': cutoff,
            'remaining': remaining,
            'lease_until': 0,
            'automatic': automatic,
            'pending_upgrade': {},
            'reserved': {},
            'cursor_audio': None,
            'cursor_text': None,
        }
        tx.set(ref, updates, merge=True)
        return {**current, **updates}

    with external_write_fence(uid, firestore_client=client):
        result = commit(client.transaction())
    _request_memo().forget_request_reads(uid)
    return result


def claim(uid: str, token: str, period: str) -> str | None:
    client = get_firestore_client()
    ref = summary_ref(uid)

    @firestore.transactional
    def commit(tx):
        row = ref.get(transaction=tx).to_dict() or {}
        if row.get('state') != 'processing' or row.get('token') != token or row.get('period') != period:
            return None
        if row.get('lease_until', 0) > time.time():
            return None
        lease = uuid4().hex
        tx.update(ref, {'lease': lease, 'lease_until': time.time() + 1800})
        return lease

    with external_write_fence(uid, firestore_client=client):
        result = commit(client.transaction())
    _request_memo().forget_request_reads(uid)
    return result


def checkpoint(uid: str, token: str, lease: str, updates: dict) -> bool:
    client = get_firestore_client()
    ref = summary_ref(uid)

    @firestore.transactional
    def commit(tx):
        row = ref.get(transaction=tx).to_dict() or {}
        if row.get('token') != token or row.get('lease') != lease or row.get('lease_until', 0) <= time.time():
            return False
        tx.update(ref, updates)
        return True

    with external_write_fence(uid, firestore_client=client):
        result = commit(client.transaction())
    _request_memo().forget_request_reads(uid)
    return result


def finish(uid: str, token: str, lease: str, period: str) -> bool:
    """Finish one choice and consume an already-authorized same-month upgrade.

    Returns true only when a new fenced run needs scheduling. This transaction
    serializes with upgrade arrival; the old worker can never overwrite its job.
    Query/allowance failures use this same authority only when unreserved.
    """
    client = get_firestore_client()
    ref = summary_ref(uid)

    @firestore.transactional
    def commit(tx):
        row = ref.get(transaction=tx).to_dict() or {}
        if row.get('token') != token or row.get('lease') != lease or row.get('lease_until', 0) <= time.time():
            return False
        # A reservation may have committed even when its checkpoint response
        # was lost. Only a known completed attempt may clear it before finish.
        if row.get('reserved'):
            return False
        pending = row.get('pending_upgrade') or {}
        if pending.get('period') == period == row.get('period'):
            tx.update(
                ref,
                {
                    'state': 'processing',
                    'token': uuid4().hex,
                    'cutoff': pending['cutoff'],
                    'remaining': pending['remaining'],
                    'automatic': True,
                    'pending_upgrade': {},
                    'reserved': {},
                    'cursor_audio': None,
                    'cursor_text': None,
                    'lease_until': 0,
                },
            )
            return True
        tx.update(ref, {'state': 'waiting_choice', 'pending_upgrade': {}, 'lease_until': 0})
        return False

    with external_write_fence(uid, firestore_client=client):
        result = commit(client.transaction())
    _request_memo().forget_request_reads(uid)
    return result


def remove(uid: str, identity: str) -> None:
    client = get_firestore_client()
    staged = False

    @firestore.transactional
    def commit(tx):
        nonlocal staged
        staged = stage_transition(tx, uid, identity, {}, {'processing_deferred': False})

    with external_write_fence(uid, firestore_client=client):
        commit(client.transaction())
    if staged:
        _request_memo().forget_request_reads(uid)


def claim_item(uid: str, identity: str) -> str | None:
    client = get_firestore_client()
    ref = items(uid).document(identity)

    @firestore.transactional
    def commit(tx):
        row = ref.get(transaction=tx).to_dict() or {}
        if not row or row.get('run_lease_until', 0) > time.time():
            return None
        lease = uuid4().hex
        tx.update(ref, {'run_lease': lease, 'run_lease_until': time.time() + 1800})
        return lease

    with external_write_fence(uid, firestore_client=client):
        return commit(client.transaction())


def release_item(uid: str, identity: str, lease: str) -> None:
    client = get_firestore_client()
    ref = items(uid).document(identity)

    @firestore.transactional
    def commit(tx):
        row = ref.get(transaction=tx).to_dict() or {}
        if row.get('run_lease') == lease:
            tx.update(ref, {'run_lease_until': 0})

    with external_write_fence(uid, firestore_client=client):
        commit(client.transaction())
