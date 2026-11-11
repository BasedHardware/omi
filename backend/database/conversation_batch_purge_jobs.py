"""Durable per-conversation batch-purge obligations and their runner.

A conversation delete arms one obligation in the same write as its tombstone.
Only the reconciler dispatches obligations, each dispatch as a new generation
(a new task name, so a spent or reserved name never swallows the work).

A run owns the obligation through a unique ``run_token`` and a lease that every
checkpoint and every destructive unit renews in a transaction that also proves
ownership, so an expired, superseded or duplicate execution stops before its
next erasure. Progress (scan position plus the content-free segment ids found
before any erasure) is checkpointed under that same check; a run hands off
well before the Cloud Tasks deadline and the next generation resumes from it.
The obligation is removed only by its owning run after the last phase.
"""

from __future__ import annotations

import hashlib
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Iterator
from uuid import uuid4

from google.cloud import firestore

from database._client import get_firestore_client
from database.legal_holds import LegalHoldActive, assert_account_deletion_permitted, destructive_operation_gate

COLLECTION = 'conversation_batch_purge_jobs'
SEGMENTS = 'segments'
TOMBSTONES = 'deleted_conversations'
# Renewed by every checkpoint/unit; a dead or wedged worker loses ownership after this.
LEASE_SECONDS = 300
# Hand off well inside the 1500 s Cloud Tasks dispatch deadline / handler timeout.
RUN_BUDGET_SECONDS = 1200
# A dispatched generation that never ran (lost task, old consumer, exhausted
# retries) is redriven after this, doubling per attempt up to the cap.
REDRIVE_SECONDS = 600
MAX_REDRIVE_SECONDS = 6 * 60 * 60
HOLD_RECHECK_SECONDS = 60 * 60
# Each unit waits this long behind a same-kind holder (a user delete), and
# after releasing it sleeps past the foreground waiter's longest backoff (0.5 s).
UNIT_GATE_WAIT_SECONDS = 30.0
UNIT_YIELD_SECONDS = 0.6
GATE_KIND = 'explicit_memory_deletion'


class RunSuperseded(Exception):
    """This execution no longer owns the obligation; it must stop without writing."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def job_id(uid: str, conversation_id: str) -> str:
    return hashlib.sha256(f'{uid}\x00{conversation_id}'.encode()).hexdigest()[:40]


def job_ref(client: Any, uid: str, conversation_id: str) -> Any:
    return client.collection(COLLECTION).document(job_id(uid, conversation_id))


def arm_fields(uid: str, conversation_id: str, now: datetime | None = None) -> dict[str, Any]:
    """Fields a delete writes (merge) next to its tombstone; generation/attempts/progress survive re-arms."""
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


def segment_records(
    job: str, namespace: str, *, limit: int | None = None, firestore_client: Any = None
) -> list[dict[str, Any]]:
    """Persisted (content-free) segment ids still owed erasure for one namespace."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    query = (
        client.collection(COLLECTION)
        .document(job)
        .collection(SEGMENTS)
        .where(filter=firestore.FieldFilter('namespace', '==', namespace))
    )
    if limit is not None:
        query = query.limit(limit)
    return [snapshot.to_dict() or {} for snapshot in query.stream()]


def _segment_ref(client: Any, job: str, namespace: str, segment_id: str) -> Any:
    digest = hashlib.sha256(f'{namespace}\x00{segment_id}'.encode()).hexdigest()[:40]
    return client.collection(COLLECTION).document(job).collection(SEGMENTS).document(digest)


def claim_dispatch(job: str, *, now: datetime | None = None, firestore_client: Any = None) -> tuple[int, int] | None:
    """Advance to a new generation and schedule its redrive: (generation, attempts) or None."""
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
        return generation, attempts

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
) -> tuple[str, dict[str, Any] | None, str | None]:
    """Take ownership of ``generation``: (run|missing|superseded|in_progress, row, run_token)."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    current = now or _now()
    ref = client.collection(COLLECTION).document(job)
    token = uuid4().hex

    def body(transaction):
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            return 'missing', None, None
        row = snapshot.to_dict() or {}
        if int(row.get('generation') or 0) != generation:
            return 'superseded', row, None
        lease_until = row.get('lease_until')
        if lease_until is not None and lease_until > current:
            return 'in_progress', row, None
        lease_until = current + timedelta(seconds=LEASE_SECONDS)
        due = row.get('due_at')
        transaction.update(
            ref,
            {
                'run_token': token,
                'lease_generation': generation,
                'lease_until': lease_until,
                'due_at': lease_until if due is None or due < lease_until else due,
            },
        )
        return 'run', row, token

    return _in_transaction(client, body)


def finish_run(
    job: str,
    generation: int,
    token: str,
    outcome: str,
    *,
    now: datetime | None = None,
    firestore_client: Any = None,
) -> bool:
    """Record the owning run's outcome; only ``completed`` removes the obligation. False if not owner."""
    if outcome not in {'completed', 'held', 'failed', 'checkpointed'}:
        raise ValueError('outcome must be completed, held, failed or checkpointed')
    client = firestore_client if firestore_client is not None else get_firestore_client()
    current = now or _now()
    ref = client.collection(COLLECTION).document(job)

    def body(transaction):
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            return False
        row = snapshot.to_dict() or {}
        if int(row.get('generation') or 0) != generation or row.get('run_token') != token:
            return False
        if outcome == 'completed':
            transaction.delete(ref)
            return True
        release = {'run_token': None, 'lease_generation': None, 'lease_until': None, 'last_outcome': outcome}
        if outcome == 'checkpointed':
            # Progress was made: hand off at once and restart the lost-task backoff.
            transaction.update(ref, {**release, 'due_at': current, 'attempts': 0})
            return False
        wait = HOLD_RECHECK_SECONDS if outcome == 'held' else REDRIVE_SECONDS
        transaction.update(ref, {**release, 'due_at': current + timedelta(seconds=wait)})
        return False

    return _in_transaction(client, body)


class RunProgress:
    """The purge's view of one owned run: fenced checkpoints, segment records, units."""

    def __init__(
        self,
        client: Any,
        job: str,
        generation: int,
        token: str,
        uid: str,
        position: dict[str, Any] | None,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        budget_seconds: float = RUN_BUDGET_SECONDS,
    ):
        self.client, self.job, self.generation, self.token, self.uid = client, job, generation, token, uid
        self.position = dict(position or {})
        self._clock, self._sleep = clock, sleep
        self._started = clock()
        self._budget = budget_seconds

    def _ref(self) -> Any:
        return self.client.collection(COLLECTION).document(self.job)

    def _owned(self, transaction: Any) -> None:
        snapshot = self._ref().get(transaction=transaction)
        row = (snapshot.to_dict() or {}) if snapshot.exists else {}
        if int(row.get('generation') or 0) != self.generation or row.get('run_token') != self.token:
            raise RunSuperseded()

    @staticmethod
    def _renewal() -> dict[str, Any]:
        return {'lease_until': _now() + timedelta(seconds=LEASE_SECONDS)}

    def checkpoint(self, position: dict[str, Any], *, add_segments: tuple[str, Iterable[str]] | None = None) -> None:
        namespace, found = add_segments or ('', ())
        segment_ids = list(dict.fromkeys(found))

        def body(transaction):
            self._owned(transaction)
            for segment_id in segment_ids:
                transaction.set(
                    _segment_ref(self.client, self.job, namespace, segment_id),
                    {'namespace': namespace, 'segment_id': segment_id},
                )
            transaction.update(self._ref(), {**self._renewal(), 'progress': position})

        _in_transaction(self.client, body)
        self.position = dict(position)

    def segments(self, namespace: str) -> set[str]:
        records = segment_records(self.job, namespace, firestore_client=self.client)
        return {str(record['segment_id']) for record in records if record.get('segment_id')}

    def pending_segments(self, namespace: str, limit: int) -> list[str]:
        records = segment_records(self.job, namespace, limit=limit, firestore_client=self.client)
        return [str(record['segment_id']) for record in records if record.get('segment_id')]

    def segments_done(self, namespace: str, segment_ids: Iterable[str]) -> None:
        done = list(segment_ids)

        def body(transaction):
            self._owned(transaction)
            for segment_id in done:
                transaction.delete(_segment_ref(self.client, self.job, namespace, segment_id))
            transaction.update(self._ref(), self._renewal())

        _in_transaction(self.client, body)

    @contextmanager
    def unit(self) -> Iterator[None]:
        with destructive_operation_gate(self.uid, kind=GATE_KIND, wait_seconds=UNIT_GATE_WAIT_SECONDS):

            def renew(transaction):
                self._owned(transaction)
                transaction.update(self._ref(), self._renewal())

            _in_transaction(self.client, renew)
            yield
        self._sleep(UNIT_YIELD_SECONDS)

    def expired(self) -> bool:
        return self._clock() - self._started >= self._budget


def _owes_segments(client: Any, job: str) -> bool:
    from database.batch_pipeline_purge import NAMESPACES

    return any(segment_records(job, namespace, limit=1, firestore_client=client) for namespace in NAMESPACES)


def _drop_segment_records(client: Any, job: str) -> None:
    from database.batch_pipeline_purge import NAMESPACES

    for namespace in NAMESPACES:
        while True:
            records = segment_records(job, namespace, limit=200, firestore_client=client)
            if not records:
                break
            batch = client.batch()
            for record in records:
                batch.delete(_segment_ref(client, job, namespace, str(record.get('segment_id'))))
            batch.commit()


def run_job(
    job: str,
    generation: int,
    *,
    firestore_client: Any = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    budget_seconds: float = RUN_BUDGET_SECONDS,
) -> str:
    """Execute (or resume) one dispatched generation. Raises on a retryable failure."""
    from database.batch_pipeline_conversation_purge import PurgeCheckpointed, purge_conversation

    client = firestore_client if firestore_client is not None else get_firestore_client()
    claim, row, token = begin_run(job, generation, firestore_client=client)
    if claim != 'run' or row is None or token is None:
        return claim
    uid, conversation_id = str(row['uid']), str(row['conversation_id'])
    progress = RunProgress(
        client,
        job,
        generation,
        token,
        uid,
        row.get('progress'),
        clock=clock,
        sleep=sleep,
        budget_seconds=budget_seconds,
    )

    def finish(outcome: str) -> bool:
        return finish_run(job, generation, token, outcome, firestore_client=client)

    try:
        tombstone = client.collection('users').document(uid).collection(TOMBSTONES).document(conversation_id)
        if not tombstone.get().exists:
            # Account wipe removed the subtree after erasing every batch row it owned.
            _drop_segment_records(client, job)
            return 'no_tombstone' if finish('completed') else 'superseded'
        # Cheap preflight so a held obligation does not rescan; every unit re-checks under the gate.
        assert_account_deletion_permitted(uid)
        purge_conversation(uid, conversation_id, progress, clock=clock)
        if _owes_segments(client, job):
            raise RuntimeError('batch purge finished with segment erasure still recorded')
    except RunSuperseded:
        return 'superseded'
    except LegalHoldActive:
        finish('held')
        return 'held'
    except PurgeCheckpointed:
        finish('checkpointed')
        return 'checkpointed'
    except BaseException:
        try:
            finish('failed')
        except Exception:
            pass  # The lease expires; the original failure is what the queue must see.
        raise
    return 'purged' if finish('completed') else 'superseded'


__all__ = [
    'COLLECTION',
    'RunProgress',
    'RunSuperseded',
    'arm_fields',
    'begin_run',
    'claim_dispatch',
    'defer',
    'due_jobs',
    'finish_run',
    'job_id',
    'job_ref',
    'run_job',
    'segment_records',
]
