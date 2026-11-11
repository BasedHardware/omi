"""Durable per-conversation batch-purge obligations and their runner.

A conversation delete arms one obligation in the same write as its tombstone.
Only the reconciler dispatches obligations, each dispatch as a new generation
(a new task name, so a spent or reserved name never swallows the work). A run
holds a lease, erases in bounded units under the account destructive-operation
gate, and removes the obligation only when the generation it ran is still the
current one. A legal hold, a failed run, or a lost task leaves the obligation
due again later; nothing acknowledges it except a completed purge.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from google.cloud import firestore

from database._client import get_firestore_client
from database.legal_holds import LegalHoldActive, assert_account_deletion_permitted, destructive_operation_gate

COLLECTION = 'conversation_batch_purge_jobs'
TOMBSTONES = 'deleted_conversations'
# Above the Cloud Tasks dispatch deadline (1500 s): a run that may still be
# executing is never overlapped by a redrive.
LEASE_SECONDS = 1600
# A dispatched generation that never ran (lost task, old consumer, exhausted
# retries) is redriven after this, doubling per attempt up to the cap.
REDRIVE_SECONDS = 600
MAX_REDRIVE_SECONDS = 6 * 60 * 60
HOLD_RECHECK_SECONDS = 60 * 60
# Each erasure unit waits this long behind a same-kind holder (a user delete).
UNIT_GATE_WAIT_SECONDS = 30.0
GATE_KIND = 'explicit_memory_deletion'


def _now() -> datetime:
    return datetime.now(timezone.utc)


def job_id(uid: str, conversation_id: str) -> str:
    return hashlib.sha256(f'{uid}\x00{conversation_id}'.encode()).hexdigest()[:40]


def job_ref(client: Any, uid: str, conversation_id: str) -> Any:
    return client.collection(COLLECTION).document(job_id(uid, conversation_id))


def arm_fields(uid: str, conversation_id: str, now: datetime | None = None) -> dict[str, Any]:
    """Fields a delete writes (merge) next to its tombstone; generation/attempts survive re-arms."""
    current = now or _now()
    return {'uid': uid, 'conversation_id': conversation_id, 'due_at': current, 'armed_at': current}


def _in_transaction(client: Any, body: Callable[[Any], Any]) -> Any:
    @firestore.transactional
    def run(transaction):
        return body(transaction)

    return run(client.transaction())


def due_jobs(*, now: datetime | None = None, limit: int = 50, firestore_client: Any = None) -> list[Any]:
    """Obligations whose next dispatch is due, oldest first (single-field ``due_at`` index)."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    query = (
        client.collection(COLLECTION)
        .where(filter=firestore.FieldFilter('due_at', '<=', now or _now()))
        .order_by('due_at')
        .limit(limit)
    )
    return list(query.stream())


def claim_dispatch(job: str, *, now: datetime | None = None, firestore_client: Any = None) -> int | None:
    """Advance to a new generation and schedule its redrive; None when not due or running."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    current = now or _now()
    ref = client.collection(COLLECTION).document(job)

    def body(transaction):
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            return None
        row = snapshot.to_dict() or {}
        due = row.get('due_at')
        lease_until = row.get('lease_until')
        if due is None or due > current or (lease_until is not None and lease_until > current):
            return None
        generation = int(row.get('generation') or 0) + 1
        attempts = int(row.get('attempts') or 0) + 1
        delay = min(REDRIVE_SECONDS * 2 ** min(attempts - 1, 16), MAX_REDRIVE_SECONDS)
        transaction.update(
            ref,
            {
                'generation': generation,
                'attempts': attempts,
                'due_at': current + timedelta(seconds=delay),
                'dispatched_at': current,
            },
        )
        return generation

    return _in_transaction(client, body)


def defer(job: str, seconds: float, *, now: datetime | None = None, firestore_client: Any = None) -> None:
    """Make an obligation due again soon (e.g. its dispatch could not be enqueued)."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection(COLLECTION).document(job)

    def body(transaction):
        if ref.get(transaction=transaction).exists:
            transaction.update(ref, {'due_at': (now or _now()) + timedelta(seconds=seconds)})

    _in_transaction(client, body)


def begin_run(
    job: str, generation: int, *, now: datetime | None = None, firestore_client: Any = None
) -> tuple[str, dict[str, Any] | None]:
    """Take the run lease for ``generation``: run, missing, superseded or in_progress."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    current = now or _now()
    ref = client.collection(COLLECTION).document(job)

    def body(transaction):
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            return 'missing', None
        row = snapshot.to_dict() or {}
        if int(row.get('generation') or 0) != generation:
            return 'superseded', row
        lease_until = row.get('lease_until')
        if lease_until is not None and lease_until > current:
            return 'in_progress', row
        lease_until = current + timedelta(seconds=LEASE_SECONDS)
        due = row.get('due_at')
        transaction.update(
            ref,
            {
                'lease_generation': generation,
                'lease_until': lease_until,
                'due_at': lease_until if due is None or due < lease_until else due,
            },
        )
        return 'run', row

    return _in_transaction(client, body)


def finish_run(
    job: str, generation: int, outcome: str, *, now: datetime | None = None, firestore_client: Any = None
) -> bool:
    """Record a run's outcome; only a matching generation's ``completed`` removes the obligation."""
    if outcome not in {'completed', 'held', 'failed'}:
        raise ValueError('outcome must be completed, held or failed')
    client = firestore_client if firestore_client is not None else get_firestore_client()
    current = now or _now()
    ref = client.collection(COLLECTION).document(job)

    def body(transaction):
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            return False
        row = snapshot.to_dict() or {}
        release = {'lease_generation': None, 'lease_until': None, 'last_outcome': outcome}
        if int(row.get('generation') or 0) != generation:
            # A newer generation owns the obligation; only drop our own lease.
            if row.get('lease_generation') == generation:
                transaction.update(ref, release)
            return False
        if outcome == 'completed':
            transaction.delete(ref)
            return True
        wait = HOLD_RECHECK_SECONDS if outcome == 'held' else REDRIVE_SECONDS
        transaction.update(ref, {**release, 'due_at': current + timedelta(seconds=wait)})
        return False

    return _in_transaction(client, body)


def run_job(job: str, generation: int, *, firestore_client: Any = None) -> str:
    """Execute one dispatched generation. Raises on a retryable failure."""
    from database.batch_pipeline_purge import purge_batch_owner

    client = firestore_client if firestore_client is not None else get_firestore_client()
    claim, row = begin_run(job, generation, firestore_client=client)
    if claim != 'run' or row is None:
        return claim
    uid, conversation_id = str(row['uid']), str(row['conversation_id'])
    try:
        tombstone = client.collection('users').document(uid).collection(TOMBSTONES).document(conversation_id)
        if not tombstone.get().exists:
            # Account wipe removed the subtree after erasing every batch row it owned.
            finish_run(job, generation, 'completed', firestore_client=client)
            return 'no_tombstone'
        # Cheap preflight so a held obligation does not rescan; the per-unit gate is the authority.
        assert_account_deletion_permitted(uid)
        purge_batch_owner(
            uid,
            conversation_id=conversation_id,
            unit_guard=lambda: destructive_operation_gate(uid, kind=GATE_KIND, wait_seconds=UNIT_GATE_WAIT_SECONDS),
        )
    except LegalHoldActive:
        finish_run(job, generation, 'held', firestore_client=client)
        return 'held'
    except BaseException:
        try:
            finish_run(job, generation, 'failed', firestore_client=client)
        except Exception:
            pass  # The lease expires; the original failure is what the queue must see.
        raise
    finish_run(job, generation, 'completed', firestore_client=client)
    return 'purged'


__all__ = [
    'COLLECTION',
    'arm_fields',
    'begin_run',
    'claim_dispatch',
    'defer',
    'due_jobs',
    'finish_run',
    'job_id',
    'job_ref',
    'run_job',
]
