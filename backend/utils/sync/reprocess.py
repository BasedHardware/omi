"""Durable, trailing-edge sync enrichment outbox.

Only IDs and scheduling metadata live here. A deterministic task name survives a
lost enqueue acknowledgement. The existing sequencer sweep repairs missing or
exhausted tasks in bounded batches, including a crash between mark and enqueue.
"""

from __future__ import annotations

import hashlib
import math
import logging
import os
import random
import time
import uuid
from typing import Any, Callable, TypeVar, TypeAlias, TypeGuard
from urllib.parse import urlsplit

from google.cloud import firestore
from google.api_core.exceptions import AlreadyExists, FailedPrecondition, NotFound
from prometheus_client import Counter

from config.sync_reprocess import settle_seconds
from config.repeat_work import revision_reuse
from database._client import get_firestore_client

Row: TypeAlias = dict[str, Any]
ResultT = TypeVar('ResultT')

logger = logging.getLogger(__name__)

COLLECTION = 'sync_reprocess_outbox'
LEASE_SECONDS = 1800  # Greater than the Cloud Tasks dispatch deadline.
REPAIR_SECONDS = 1800
COALESCED = Counter('sync_reprocess_coalesced_total', 'Sync updates folded into an existing enrichment obligation')
UNBOUND = Counter('sync_reprocess_unbound_total', 'Sync obligations awaiting a complete worker binding', ['action'])


def key(uid: str, conversation_id: str) -> str:
    return hashlib.sha256(f'{uid}\0{conversation_id}'.encode()).hexdigest()


def owns_runtime() -> bool:
    from utils.sync.stage import production_stage

    return bool(os.getenv('FIRESTORE_EMULATOR_HOST')) or production_stage()


def _mutate(document_id: str, operation: Callable[[Row | None], tuple[Row | None, ResultT]]) -> ResultT:
    if not owns_runtime():
        raise RuntimeError('sync reprocess outbox requires production or a Firestore emulator')
    client = get_firestore_client()
    ref = client.collection(COLLECTION).document(document_id)

    # All state for one obligation is in one document. Optimistic conditional
    # writes avoid read-lock upgrade deadlocks under simultaneous appends while
    # fencing claims, extension and completion against the exact read revision.
    for attempt in range(10):
        snapshot = ref.get()
        old = snapshot.to_dict() if snapshot.exists else None
        new, result = operation(old)
        if new == old:
            return result
        try:
            if old is None:
                ref.create(new)
            else:
                fence = firestore.LastUpdateOption(snapshot.update_time)
                if new is None:
                    ref.delete(option=fence)
                else:
                    ref.update(new, option=fence)
            return result
        except (AlreadyExists, FailedPrecondition, NotFound):
            if attempt == 9:
                raise
            time.sleep(random.uniform(0.005, min(0.2, 0.01 * 2**attempt)))
    raise AssertionError('outbox CAS loop must return or raise within its retry budget')


def valid_dispatch_binding(dispatch: object) -> TypeGuard[dict[str, str]]:
    """A binding belongs to the receiving sync handler, including its audience."""
    if not isinstance(dispatch, dict):
        return False
    for field in ('queue', 'handler', 'audience', 'invoker_sa'):
        value = dispatch.get(field)
        if not isinstance(value, str) or not value or value != value.strip():
            return False
    try:
        url = urlsplit(dispatch['handler'])
    except ValueError:
        return False
    return (
        url.scheme == 'https'
        and bool(url.netloc)
        and url.path.endswith('/v2/sync-jobs/run')
        and not url.query
        and not url.fragment
        and dispatch['audience'] == dispatch['handler']
    )


def _dispatch_binding() -> dict[str, str] | None:
    handler = os.getenv('SYNC_TASKS_HANDLER_URL', '')
    binding = {
        'queue': os.getenv('SYNC_TASKS_QUEUE', ''),
        'handler': handler,
        'audience': os.getenv('SYNC_TASKS_OIDC_AUDIENCE') or handler,
        'invoker_sa': os.getenv('SYNC_TASKS_INVOKER_SA', ''),
    }
    return binding if valid_dispatch_binding(binding) else None


def _enqueue(row: dict[str, Any]) -> None:
    from utils.cloud_tasks import enqueue_named_task

    # A backfill obligation is repaired by the fresh service's sweep. Retain
    # the originating queue/worker/identity rather than borrowing that sweep's
    # fresh capacity or audience. These bindings contain no credentials.
    dispatch = row.get('dispatch')
    if not valid_dispatch_binding(dispatch):
        raise RuntimeError('sync reprocessing requires a complete sync worker binding')
    handler = dispatch['handler']
    enqueue_named_task(
        dispatch['queue'],
        handler,
        f"sr-{key(row['uid'], row['conversation_id'])}-{row['task_token']}",
        {'kind': 'sync_reprocess', 'key': key(row['uid'], row['conversation_id']), 'task_token': row['task_token']},
        audience=dispatch['audience'],
        invoker_sa=dispatch['invoker_sa'],
        schedule_at=math.ceil(row['due_at']),
    )


def mark(
    uid: str,
    conversation_id: str,
    language: str,
    *,
    now: float | None = None,
    mutate: Callable | None = None,
) -> None:
    """Record one enrichment obligation.

    Projection may inject a transactional mutation to commit its replay receipt
    and privacy fences with this obligation. The default retains the normal
    CAS path; both paths enqueue only after durable persistence.
    """
    if mutate is not None and not owns_runtime():
        raise RuntimeError('sync reprocess projection requires production or a Firestore emulator')
    current = time.time() if now is None else now

    def update(old: Row | None) -> tuple[Row, tuple[Row, bool]]:
        row = dict(old or {})
        row.update(
            uid=uid,
            conversation_id=conversation_id,
            language=language,
            version=row.get('version', 0) + 1,
            due_at=max(row.get('due_at', 0), current + settle_seconds()),
        )
        if revision_reuse():
            # Extend the existing quiet window, but never postpone a dirty
            # obligation indefinitely under a continuous trickle of revisions.
            row['first_pending_at'] = row.get('first_pending_at', current)
            row['due_at'] = min(row['due_at'], row['first_pending_at'] + 3600)
        if old is None:
            row.update(
                task_token=uuid.uuid4().hex, task_due_at=row['due_at'], lease_until=0, dispatch=_dispatch_binding()
            )
        elif not valid_dispatch_binding(row.get('dispatch')):
            row['dispatch'] = None
        return row, (row, old is not None)

    row, coalesced = (mutate or _mutate)(key(uid, conversation_id), update)
    if coalesced:
        COALESCED.inc()
    elif valid_dispatch_binding(row.get('dispatch')):
        _enqueue(row)  # Failure leaves the obligation durable for the sweep.
    else:
        UNBOUND.labels(action='mark').inc()


def run(document_id: str, task_token: str, process: Callable[[str, str, str], Any], *, now: float | None = None) -> str:
    current = time.time() if now is None else now
    owner = uuid.uuid4().hex

    def claim(old: Row | None) -> tuple[Row | None, tuple[str, Row | None]]:
        if old is None or old['task_token'] != task_token:
            return old, ('stale', None)
        if old.get('lease_until', 0) > current:
            return old, ('busy', None)
        row = dict(old)
        if row['due_at'] > current:
            row.update(task_token=uuid.uuid4().hex, task_due_at=row['due_at'])
            return row, ('deferred', row)
        row.update(lease_until=current + LEASE_SECONDS, owner=owner)
        return row, ('claimed', row)

    status, row = _mutate(document_id, claim)
    if status == 'deferred':
        assert row is not None
        _enqueue(row)
        return status
    if status != 'claimed':
        return status
    assert row is not None
    # Exceptions leave a leased, dirty row. Retry/sweep recovers after expiry.
    process(row['uid'], row['conversation_id'], row['language'])

    def finish(old: Row | None) -> tuple[Row | None, Row | None]:
        if old is None or old.get('owner') != owner:
            return old, None
        if old['version'] == row['version']:
            return None, None
        pending = dict(old)
        pending.update(lease_until=0, task_token=uuid.uuid4().hex, task_due_at=pending['due_at'])
        return pending, pending

    pending = _mutate(document_id, finish)
    if pending is not None:
        _enqueue(pending)
    return 'processed'


def sweep(*, now: float | None = None, limit: int = 100) -> dict[str, int]:
    current = time.time() if now is None else now
    counts = {'repaired': 0, 'error': 0}
    if not owns_runtime():
        return counts
    binding = _dispatch_binding()
    limit = max(1, min(100, limit))
    client = get_firestore_client()
    # One range/order field uses the automatic single-field index.
    snapshots = client.collection(COLLECTION).where('due_at', '<=', current).order_by('due_at').limit(limit).stream()
    for snapshot in snapshots:

        def repair(old: Row | None) -> tuple[Row | None, tuple[str, Row | None]]:
            if old is None or old.get('lease_until', 0) > current:
                return old, ('skipped', None)
            row = dict(old)
            if not valid_dispatch_binding(row.get('dispatch')):
                if binding is None:
                    return old, ('unbound', None)
                # Claim and fence the repaired binding in the same CAS. Any old
                # task delivery becomes stale; valid backfill bindings stay put.
                row.update(dispatch=binding, task_token=uuid.uuid4().hex, task_due_at=current)
            if row['task_due_at'] + REPAIR_SECONDS <= current:
                row.update(task_token=uuid.uuid4().hex, task_due_at=current)
            return row, ('ready', row)

        try:
            status, row = _mutate(snapshot.id, repair)
            if status == 'unbound':
                UNBOUND.labels(action='repair').inc()
            if row is not None:
                _enqueue(row)
                counts['repaired'] += 1
        except Exception as error:
            counts['error'] += 1
            logger.error('event=sync_reprocess action=repair outcome=error exception_type=%s', type(error).__name__)
    return counts
