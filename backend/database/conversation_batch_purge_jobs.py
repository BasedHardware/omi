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

A delete accepted while a same-account delete held the account gate owes its
whole cascade erasure instead: one ``conversation_erasure_jobs`` obligation,
written with the tombstone, dispatched and leased the same way (so an older
consumer that cannot run it answers ``missing`` and it is redriven, never
dropped), and run serially under the account gate by ``run_erasure_job``.

Every delete that erases audio (both cascade modes) owes it through one
``conversation_audio_erasure_jobs`` obligation, armed before the primary row is
deleted and dispatched, leased and redriven the same way. ``run_audio_erasure_job``
needs only the tombstone, so a retry after the row is gone still finishes the
audio; storage holds, staging still in use and ledger-read failures are
recorded on the obligation and retried. It is its own collection so a consumer
that predates it can never mistake it for a cascade erasure.
"""

from __future__ import annotations

import hashlib
import logging
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Iterator
from uuid import uuid4

from google.cloud import firestore

from database._client import get_firestore_client
from database import rpc_deadline
from database import legal_holds
from database.legal_holds import LegalHoldActive, assert_account_deletion_permitted

logger = logging.getLogger(__name__)

COLLECTION = 'conversation_batch_purge_jobs'
# Accepted deletes owing their cascade erasure (a collection older code never reads).
ERASURE_COLLECTION = 'conversation_erasure_jobs'
# Deletes owing their audio erasure (canonical, conversation/donor prefixes, sync staging).
AUDIO_COLLECTION = 'conversation_audio_erasure_jobs'
# Staging still read by an unfinished upload is rechecked hourly for this long after the delete; after
# that it stays owed as ``staging_unsettled`` (escalated on every pass) and is rechecked daily.
AUDIO_STAGING_PENDING_MAX_SECONDS = 14 * 24 * 60 * 60
AUDIO_STAGING_UNSETTLED_RECHECK_SECONDS = 24 * 60 * 60
# A tombstoned conversation whose row is still visible (a delete that failed after arming) is rechecked this soon.
AUDIO_ROW_LIVE_RETRY_SECONDS = 300
# Staging kept for a live sibling stays owed (the ledger that links them expires) and is rechecked daily.
AUDIO_SHARED_LIVE_RECHECK_SECONDS = 24 * 60 * 60
AUDIO_GATE_KIND = 'audio_conversation_deletion'
# Fields an audio run's outcome records; a later outcome that does not set one clears it.
AUDIO_DETAIL_FIELDS = (
    'last_reason',
    'blocked_objects',
    'unverified',
    'in_flight_uploads',
    'shared_live',
    'row_live_since',
    'row_live_passes',
)
# A visible row is rechecked after 5 min, doubling to hourly; after a day it is rechecked daily and counts
# toward the stuck-obligation alert (a delete that failed after arming and was never retried).
AUDIO_ROW_LIVE_MAX_RETRY_SECONDS = 60 * 60
AUDIO_ROW_LIVE_ALERT_AFTER_SECONDS = 24 * 60 * 60
SEGMENTS = 'segments'
TOMBSTONES = 'deleted_conversations'
# Renewed by every checkpoint/unit; a dead or wedged worker loses ownership after this.
LEASE_SECONDS = 300
# No unit or read batch starts past this; with bounded units and checkpointing that
# leaves minutes inside the 1500 s Cloud Tasks dispatch deadline / handler timeout.
RUN_BUDGET_SECONDS = 1200
# Every RPC of the run, inside or outside units, is bounded by budget + this margin (< 1500 s).
RUN_FINALIZE_SECONDS = 120
# A dispatched generation that never ran (lost task, old consumer, exhausted
# retries) is redriven after this, doubling per attempt up to the cap. A task
# still in its queue is re-checked after this instead of redriven.
REDRIVE_SECONDS = 600
MAX_REDRIVE_SECONDS = 6 * 60 * 60
HOLD_RECHECK_SECONDS = 60 * 60
# Each unit waits this long behind a same-kind holder (a user delete), and
# after releasing it sleeps past the foreground waiter's longest backoff (0.5 s).
UNIT_GATE_WAIT_SECONDS = 30.0
UNIT_YIELD_SECONDS = 0.6
GATE_KIND = 'explicit_memory_deletion'
# An accepted delete's erasure lost the account gate to a same-account erasure: retry soon.
BUSY_RETRY_SECONDS = 30
ARTIFACT_RETRY_SECONDS = 240


class RunSuperseded(Exception):
    """This execution no longer owns the obligation; it must stop without writing."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def job_id(uid: str, conversation_id: str) -> str:
    return hashlib.sha256(f'{uid}\x00{conversation_id}'.encode()).hexdigest()[:40]


def job_ref(client: Any, uid: str, conversation_id: str) -> Any:
    return client.collection(COLLECTION).document(job_id(uid, conversation_id))


def erasure_job_id(uid: str, conversation_id: str) -> str:
    # Distinct from the batch-purge id, so no consumer can mistake one obligation for the other.
    return hashlib.sha256(f'erasure\x00{uid}\x00{conversation_id}'.encode()).hexdigest()[:40]


def erasure_job_ref(client: Any, uid: str, conversation_id: str) -> Any:
    return client.collection(ERASURE_COLLECTION).document(erasure_job_id(uid, conversation_id))


def audio_job_id(uid: str, conversation_id: str) -> str:
    return hashlib.sha256(f'audio\x00{uid}\x00{conversation_id}'.encode()).hexdigest()[:40]


def audio_job_ref(client: Any, uid: str, conversation_id: str) -> Any:
    return client.collection(AUDIO_COLLECTION).document(audio_job_id(uid, conversation_id))


def arm_audio_erasure(
    uid: str,
    conversation_id: str,
    source_ids: Iterable[str] = (),
    *,
    sync_sourced: bool = False,
    firestore_client: Any = None,
    now: datetime | None = None,
) -> None:
    """Owe this deleted conversation's audio durably (merge: a re-arm keeps generation and donors).

    ``sync_sourced`` notes a conversation fed by sync uploads, so a run that finds
    no staging for it can report that the ledger no longer names it.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    current = now or _now()
    ref = audio_job_ref(client, uid, conversation_id)
    donors = [str(source) for source in dict.fromkeys(source_ids) if source and source != conversation_id]

    def body(transaction):
        snapshot = ref.get(transaction=transaction)
        known = list((snapshot.to_dict() or {}).get('audio_source_ids') or []) if snapshot.exists else []
        fields = {
            'uid': uid,
            'conversation_id': conversation_id,
            'due_at': current,
            'armed_at': current,
            'arm_revision': uuid4().hex,
            # A retry after the row lost its merge links keeps the donors an earlier arm recorded.
            'audio_source_ids': known + [source for source in donors if source not in known],
            'sync_sourced': (
                bool(sync_sourced or (snapshot.to_dict() or {}).get('sync_sourced'))
                if snapshot.exists
                else bool(sync_sourced)
            ),
        }
        transaction.set(ref, fields, merge=True)

    _in_transaction(client, body)


def accept_fields(
    uid: str, conversation_id: str, *, audio_source_ids: list[str] | None = None, now: datetime | None = None
) -> dict[str, Any]:
    """Fields an accepted delete writes (merge) next to its tombstone; generation/attempts survive re-accepts."""
    current = now or _now()
    return {
        'uid': uid,
        'conversation_id': conversation_id,
        'due_at': current,
        'accepted_at': current,
        'audio_source_ids': list(audio_source_ids or []),
    }


def arm_fields(uid: str, conversation_id: str, now: datetime | None = None) -> dict[str, Any]:
    """Fields a delete writes (merge) next to its tombstone; generation/attempts/progress survive re-arms."""
    current = now or _now()
    return {
        'uid': uid,
        'conversation_id': conversation_id,
        'due_at': current,
        'armed_at': current,
        'arm_revision': uuid4().hex,
    }


def _arm(row: dict[str, Any]) -> dict[str, Any]:
    # armed_at also detects re-arms from producers predating arm_revision.
    return {'armed_at': row.get('armed_at'), 'arm_revision': row.get('arm_revision')}


def _in_transaction(client: Any, body: Callable[[Any], Any]) -> Any:
    @firestore.transactional
    def run(transaction):
        return body(transaction)

    return run(client.transaction())


def due_jobs(
    *, now: datetime | None = None, limit: int = 50, firestore_client: Any = None, collection: str = COLLECTION
) -> list[Any]:
    """Obligations whose next dispatch is due, oldest first (single-field ``due_at`` index)."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    query = (
        client.collection(collection)
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


def segment_ref(client: Any, job: str, namespace: str, segment_id: str) -> Any:
    digest = hashlib.sha256(f'{namespace}\x00{segment_id}'.encode()).hexdigest()[:40]
    return client.collection(COLLECTION).document(job).collection(SEGMENTS).document(digest)


def lease_held(row: dict[str, Any], *, now: datetime | None = None) -> bool:
    """Whether a run owns this obligation row right now (renewals move ``lease_until``, never ``due_at``)."""
    lease_until = row.get('lease_until')
    return lease_until is not None and lease_until > (now or _now())


def claim_dispatch(
    job: str, *, now: datetime | None = None, firestore_client: Any = None, collection: str = COLLECTION
) -> tuple[int, int] | None:
    """Advance to a new generation and schedule its redrive: (generation, attempts) or None."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    current = now or _now()
    ref = client.collection(collection).document(job)

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


def defer(
    job: str,
    seconds: float,
    *,
    now: datetime | None = None,
    firestore_client: Any = None,
    collection: str = COLLECTION,
    generation: int | None = None,
) -> None:
    """Make an obligation due after ``seconds`` (e.g. its dispatch could not be enqueued).

    With ``generation``, only while that is still the obligation's generation.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection(collection).document(job)

    def body(transaction):
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            return
        if generation is not None and int((snapshot.to_dict() or {}).get('generation') or 0) != generation:
            return
        transaction.update(ref, {'due_at': (now or _now()) + timedelta(seconds=seconds)})

    _in_transaction(client, body)


def begin_run(
    job: str,
    generation: int,
    *,
    now: datetime | None = None,
    firestore_client: Any = None,
    collection: str = COLLECTION,
) -> tuple[str, dict[str, Any] | None, str | None]:
    """Take ownership of ``generation``: (run|missing|superseded|in_progress, row, run_token)."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    current = now or _now()
    ref = client.collection(collection).document(job)
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
        progress_fields = {}
        if collection == COLLECTION:
            arm = _arm(row)
            # An unversioned legacy cursor cannot prove which arm it covered.
            # Rewind discovery once; segment journals remain owed and untouched.
            if row.get('progress_arm') != arm:
                row['progress'] = {}
            row['progress_arm'] = arm
            progress_fields = {'progress': row.get('progress') or {}, 'progress_arm': arm}
        transaction.update(
            ref,
            {
                'run_token': token,
                'lease_generation': generation,
                'lease_until': lease_until,
                'due_at': lease_until if due is None or due < lease_until else due,
                **progress_fields,
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
    collection: str = COLLECTION,
    detail: dict[str, Any] | None = None,
    arm_revision: Any = None,
    retry_after: float | None = None,
    count_attempt: bool = False,
) -> bool:
    """Record the owning run's outcome; only ``completed`` removes the obligation. False if not owner.

    ``detail`` is recorded on a retained obligation (e.g. why it waits). For an
    audio obligation, ``arm_revision`` is the arm the run erased: a newer arm
    (a retried delete) is redriven instead of completed. ``retry_after``
    overrides a ``held``/``failed`` obligation's recheck delay.
    """
    if outcome not in {'completed', 'held', 'failed', 'checkpointed', 'busy', 'artifact_pending'}:
        raise ValueError('invalid purge outcome')
    client = firestore_client if firestore_client is not None else get_firestore_client()
    current = now or _now()
    ref = client.collection(collection).document(job)

    def body(transaction):
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            return False
        row = snapshot.to_dict() or {}
        if int(row.get('generation') or 0) != generation or row.get('run_token') != token:
            return False
        if collection == COLLECTION and row.get('progress_arm') != _arm(row):
            # The owner still owes the new arm. Never let an obsolete run
            # complete it or publish a cursor beyond newly added rows.
            transaction.update(
                ref,
                {
                    'progress': {},
                    'progress_arm': _arm(row),
                    'run_token': None,
                    'lease_generation': None,
                    'lease_until': None,
                    'due_at': current,
                    'attempts': 0,
                    'last_outcome': 'rearmed',
                },
            )
            return False
        result, extra = outcome, dict(detail or {})
        if result == 'completed' and collection == AUDIO_COLLECTION and row.get('arm_revision') != arm_revision:
            result = 'checkpointed'  # re-armed while running: erase again for the newer arm
            extra['last_reason'] = 'rearmed'
        if result == 'completed':
            transaction.delete(ref)
            return True
        if collection == AUDIO_COLLECTION:
            # A stale reason or count from an earlier outcome must not describe this one.
            extra = {**{field: firestore.DELETE_FIELD for field in AUDIO_DETAIL_FIELDS}, **extra}
        release = {
            'run_token': None,
            'lease_generation': None,
            'lease_until': None,
            'last_outcome': result,
            **extra,
        }
        if result == 'checkpointed':
            # Progress was made: hand off at once and restart the lost-task backoff.
            transaction.update(ref, {**release, 'due_at': current, 'attempts': 0})
            return False
        if result in {'busy', 'artifact_pending'}:
            wait = BUSY_RETRY_SECONDS if result == 'busy' else ARTIFACT_RETRY_SECONDS
            transaction.update(ref, {**release, 'due_at': current + timedelta(seconds=wait), 'attempts': 0})
            return False
        wait = HOLD_RECHECK_SECONDS if result == 'held' else REDRIVE_SECONDS
        if retry_after is not None:
            wait = retry_after
        if result == 'held' and collection == AUDIO_COLLECTION and not count_attempt:
            # A deliberate hold (storage hold, staging waiting, switch off, legal hold) made its
            # decision: it is not a lost task, so it must not trip the stuck-obligation alert.
            release['attempts'] = 0
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
        started: float | None = None,
    ):
        self.client, self.job, self.generation, self.token, self.uid = client, job, generation, token, uid
        self.position = dict(position or {})
        self._clock, self._sleep = clock, sleep
        self._started = clock() if started is None else started  # the run's entry, admission included
        self._budget = budget_seconds
        self._checkpointed = False  # every run saves at least one step before honouring its budget

    def _ref(self) -> Any:
        return self.client.collection(COLLECTION).document(self.job)

    def _owned(self, transaction: Any) -> None:
        snapshot = self._ref().get(transaction=transaction)
        row = (snapshot.to_dict() or {}) if snapshot.exists else {}
        if int(row.get('generation') or 0) != self.generation or row.get('run_token') != self.token:
            raise RunSuperseded()
        if row.get('progress_arm') != _arm(row):
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
                    segment_ref(self.client, self.job, namespace, segment_id),
                    {'namespace': namespace, 'segment_id': segment_id},
                )
            transaction.update(self._ref(), {**self._renewal(), 'progress': position})

        _in_transaction(self.client, body)
        self.position = dict(position)
        self._checkpointed = True

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
                transaction.delete(segment_ref(self.client, self.job, namespace, segment_id))
            transaction.update(self._ref(), self._renewal())

        _in_transaction(self.client, body)

    @contextmanager
    def unit(self) -> Iterator[legal_holds.UnitAuthority]:
        # Erasures under the unit are fenced by its authority; see bounded_destructive_unit.
        with legal_holds.bounded_destructive_unit(
            self.uid, kind=GATE_KIND, wait_seconds=UNIT_GATE_WAIT_SECONDS
        ) as authority:

            def renew(transaction):
                self._owned(transaction)
                transaction.update(self._ref(), self._renewal())

            _in_transaction(self.client, renew)
            yield authority
        self._sleep(UNIT_YIELD_SECONDS)

    def settle_stuck(self, resolve: Callable[[str], bool]) -> None:
        """Settle a unit gate left held by an unknown remote outcome, under that gate's own token."""
        client = legal_holds.account_deletion_firestore_client()
        stuck = legal_holds.stuck_remote_erasure(self.uid, kind=GATE_KIND, firestore_client=client)
        if stuck is None:
            return
        token, target = stuck
        # Re-issuing the same generation-pinned delete: a definitive answer settles the old request too.
        if resolve(target):
            legal_holds.settle_stuck_remote_erasure(self.uid, kind=GATE_KIND, token=token, firestore_client=client)

    def expired(self) -> bool:
        return self._checkpointed and self._clock() - self._started >= self._budget


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
                batch.delete(segment_ref(client, job, namespace, str(record.get('segment_id'))))
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
    from database.batch_pipeline_conversation_purge import ArtifactUploadPending, PurgeCheckpointed, purge_conversation

    # The run's budget and its absolute RPC deadline start at entry: admission is debited too.
    started = clock()
    client = firestore_client if firestore_client is not None else get_firestore_client()
    # Units hold the gate; their ownership checks on this client honour the unit's RPC deadline.
    rpc_deadline.bind_firestore_client(client)
    with rpc_deadline.rpc_deadline(rpc_deadline.now() + budget_seconds + RUN_FINALIZE_SECONDS):
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
            started=started,
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
            finish('checkpointed')  # re-arms rewind and redrive; another owner remains untouched
            return 'superseded'
        except LegalHoldActive:
            finish('held')
            return 'held'
        except ArtifactUploadPending:
            finish('artifact_pending')
            return 'artifact_pending'
        except PurgeCheckpointed:
            finish('checkpointed')
            return 'checkpointed'
        except Exception as error:
            # Units acquire before erasing, so a unit that lost its gate wait erased nothing; progress is saved.
            if lost_gate_to_peer(error, uid):
                logger.info('conversation batch purge waiting for the account gate job=%s', job)
                finish('busy')
                return 'busy'
            _finish_failed(finish)
            raise
        except BaseException:
            _finish_failed(finish)
            raise
        return 'purged' if finish('completed') else 'superseded'


def _finish_failed(finish: Callable[[str], bool]) -> None:
    try:
        finish('failed')
    except Exception:
        pass  # The lease expires; the original failure is what the queue must see.


def lost_gate_to_peer(error: BaseException, uid: str, kind: str = GATE_KIND) -> bool:
    if type(error).__name__ == 'HTTPException' and getattr(error, 'status_code', None) == 409:
        return True  # the cascade's nested gate mapped a same-account peer to account_gate_busy
    try:
        return legal_holds.gate_busy_with_peer(error, uid, kind=kind) is True
    except Exception:  # noqa: BLE001 - an unreadable gate is a plain failure (redriven)
        return False


def run_erasure_job(
    job: str,
    generation: int,
    *,
    erase: Callable[[str, str, list[str]], None],
    firestore_client: Any = None,
) -> str:
    """Erase one accepted delete: the request's own cascade, serially under the account gate.

    ``erase(uid, conversation_id, audio_source_ids)`` acquires the gate (its
    acquisition re-checks the hold and refuses an account wipe's gate) and raises
    when it cannot. The cascade is idempotent, so a duplicate or superseded run
    only repeats finished steps behind the same gate. Raises on a retryable failure.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    claim, row, token = begin_run(job, generation, firestore_client=client, collection=ERASURE_COLLECTION)
    if claim != 'run' or row is None or token is None:
        return claim
    uid, conversation_id = str(row['uid']), str(row['conversation_id'])

    def finish(outcome: str) -> bool:
        return finish_run(job, generation, token, outcome, firestore_client=client, collection=ERASURE_COLLECTION)

    try:
        tombstone = client.collection('users').document(uid).collection(TOMBSTONES).document(conversation_id)
        if not tombstone.get().exists:
            # Account deletion supersedes: the wipe removed the subtree, tombstone included.
            return 'no_tombstone' if finish('completed') else 'superseded'
        assert_account_deletion_permitted(uid)
        try:
            erase(uid, conversation_id, [str(source) for source in row.get('audio_source_ids') or []])
        except LegalHoldActive:
            raise
        except Exception as error:
            if not lost_gate_to_peer(error, uid):
                raise
            logger.info('conversation erasure waiting for the account gate job=%s', job)
            finish('busy')
            return 'busy'
    except LegalHoldActive:
        # Stays hidden (tombstone + deleted row) and retained; rechecked hourly.
        finish('held')
        return 'held'
    except BaseException:
        try:
            finish('failed')
        except Exception:
            pass  # The lease expires; the original failure is what the queue must see.
        raise
    return 'erased' if finish('completed') else 'superseded'


def _gate_busy(error: BaseException, uid: str) -> bool:
    # The audio gate is account-exclusive: any running destructive operation makes it busy.
    if type(error).__name__ in {'DestructiveOperationInProgress', 'DestructiveGateTakeover'}:
        return True
    return lost_gate_to_peer(error, uid, kind=AUDIO_GATE_KIND)


def _record_staging(
    client: Any, job: str, token: str, sources: dict[str, list[str]], settled: Iterable[str]
) -> tuple[dict[str, list[str]], list[str]]:
    """Merge staging jobs, their fed conversations and settled jobs into the record under run ownership.

    Never shrinks: a sibling or settled state once seen stays recorded. Returns the merged record.
    """
    ref = client.collection(AUDIO_COLLECTION).document(job)

    def body(transaction):
        snapshot = ref.get(transaction=transaction)
        row = (snapshot.to_dict() or {}) if snapshot.exists else {}
        if row.get('run_token') != token:
            raise RunSuperseded()
        merged = {key: list(value) for key, value in (row.get('staging_sources') or {}).items()}
        for key, ids in sources.items():
            merged[key] = sorted(set(merged.get(key, [])) | set(ids))
        done = sorted(set(row.get('staging_settled') or []) | set(settled))
        transaction.update(ref, {'staging_sources': merged, 'staging_settled': done, 'staging_recorded_at': _now()})
        return merged, done

    return _in_transaction(client, body)


def run_audio_erasure_job(
    job: str,
    generation: int,
    *,
    erase: Callable[..., Any],
    enabled: Callable[[], bool] = lambda: True,
    firestore_client: Any = None,
    now: datetime | None = None,
) -> str:
    """Erase one deleted conversation's audio; retried until done, never dropped.

    ``erase(uid, conversation_id, audio_source_ids, staging=recorded)`` acquires
    the account's audio gate (refusing a legal hold) and erases every copy; it
    is idempotent, so a duplicate run repeats finished steps. ``recorded`` is
    the staging jobs (with their fed conversations) this obligation recorded
    from the ledger on its first run, so they stay owed after the ledger rows
    expire. It may return a mapping with ``shared_live`` (staging kept for a
    live sibling): the obligation then stays owed, rechecked daily. Only the
    tombstone is required: the primary row may already be gone, but a row that
    is still visible (the delete failed after arming) waits. With ``enabled``
    false (the kill switch) the obligation is held, not run. Raises on a
    retryable failure.
    """
    from database.account_deletion_operational_holds import StoragePrefixPurgeBlocked
    from database.sync_ledger_sources import StagingInFlight

    client = firestore_client if firestore_client is not None else get_firestore_client()
    claim, row, token = begin_run(job, generation, firestore_client=client, collection=AUDIO_COLLECTION, now=now)
    if claim != 'run' or row is None or token is None:
        return claim
    uid, conversation_id = str(row['uid']), str(row['conversation_id'])
    arm_revision = row.get('arm_revision')

    def finish(outcome: str, retry_after: float | None = None, count_attempt: bool = False, **detail: Any) -> bool:
        return finish_run(
            job,
            generation,
            token,
            outcome,
            firestore_client=client,
            collection=AUDIO_COLLECTION,
            detail={'last_reason': detail.pop('reason', outcome), **detail},
            arm_revision=arm_revision,
            retry_after=retry_after,
            count_attempt=count_attempt,
        )

    donors = [str(source) for source in row.get('audio_source_ids') or []]
    try:
        user = client.collection('users').document(uid)
        if not user.collection(TOMBSTONES).document(conversation_id).get().exists:
            # Account deletion supersedes: the wipe removed the subtree and every owner storage prefix.
            return 'no_tombstone' if finish('completed') else 'superseded'
        recorded = {key: list(value) for key, value in (row.get('staging_sources') or {}).items()}
        settled = list(row.get('staging_settled') or [])
        # Every pass, before any hold, re-reads the ledger (read-only) and merges it into the record:
        # the ledger expires while a held obligation may outlive it, so siblings fed since the last pass
        # and a job's settled state are captured whatever holds this pass.
        from database.sync_ledger_sources import staging_sources

        try:
            found = staging_sources(uid, [conversation_id, *donors], extra_jobs=recorded, firestore_client=client)
            recorded, settled = _record_staging(client, job, token, found.fed, found.settled)
        except RunSuperseded:
            raise
        except Exception:
            if enabled():
                raise
        if not recorded and row.get('sync_sourced'):
            # Accepted retention exception: a sync conversation deleted after its ledger rows expired
            # (45 days) cannot be traced to its staging; account deletion still sweeps syncing/{uid}/.
            logger.info('event=conversation_audio_erasure outcome=staging_undiscoverable_after_ledger_ttl job=%s', job)
        if not enabled():
            # Kill switch off: armed obligations stay owed and resume when it is back on.
            finish('held', reason='switched_off')
            return 'switched_off'
        conversation = user.collection('conversations').document(conversation_id).get()
        if conversation.exists and not (conversation.to_dict() or {}).get('deleted'):
            # The delete failed after arming (it answered 503): never erase audio of a visible conversation.
            current = now or _now()
            since = row.get('row_live_since') if row.get('last_reason') == 'conversation_row_live' else None
            since = since if isinstance(since, datetime) else current
            passes = int(row.get('row_live_passes') or 0) if row.get('last_reason') == 'conversation_row_live' else 0
            stuck = (current - since).total_seconds() >= AUDIO_ROW_LIVE_ALERT_AFTER_SECONDS
            wait = (
                AUDIO_SHARED_LIVE_RECHECK_SECONDS
                if stuck
                else min(AUDIO_ROW_LIVE_RETRY_SECONDS * 2 ** min(passes, 16), AUDIO_ROW_LIVE_MAX_RETRY_SECONDS)
            )
            finish(
                'held',
                retry_after=wait,
                count_attempt=stuck,
                reason='conversation_row_live',
                row_live_since=since,
                row_live_passes=passes + 1,
            )
            return 'conversation_row_live'
        assert_account_deletion_permitted(uid)
        try:
            summary = erase(uid, conversation_id, donors, staging=recorded, settled=settled)
        except LegalHoldActive:
            raise
        except StoragePrefixPurgeBlocked as error:
            # Object holds are reported on the obligation and rechecked; nothing else is skipped.
            logger.warning(
                'event=conversation_audio_erasure outcome=storage_held job=%s objects=%d unverified=%d',
                job,
                len(error.objects),
                error.unverified,
            )
            finish('held', reason='storage_hold', blocked_objects=len(error.objects), unverified=error.unverified)
            return 'storage_held'
        except StagingInFlight as error:
            armed_at = row.get('armed_at')
            if armed_at is not None and (now or _now()) - armed_at >= timedelta(
                seconds=AUDIO_STAGING_PENDING_MAX_SECONDS
            ):
                # Never discharged while staging is kept (its bucket has no lifecycle delete): escalate, recheck daily.
                logger.error(
                    'event=conversation_audio_erasure outcome=staging_unsettled job=%s uploads=%d', job, error.count
                )
                finish(
                    'held',
                    retry_after=AUDIO_STAGING_UNSETTLED_RECHECK_SECONDS,
                    reason='staging_unsettled',
                    in_flight_uploads=error.count,
                )
                return 'staging_unsettled'
            logger.info(
                'event=conversation_audio_erasure outcome=staging_in_flight job=%s uploads=%d', job, error.count
            )
            finish('held', reason='staging_in_flight', in_flight_uploads=error.count)
            return 'staging_in_flight'
        except Exception as error:
            if not _gate_busy(error, uid):
                raise
            logger.info('conversation audio erasure waiting for the account gate job=%s', job)
            finish('busy')
            return 'busy'
    except RunSuperseded:
        return 'superseded'  # another run owns the obligation now; it records and erases
    except LegalHoldActive:
        # Stays hidden and retained; rechecked hourly.
        finish('held', reason='legal_hold')
        return 'held'
    except BaseException as error:
        # Ledger reads, provider errors, an unreadable hold: the obligation stays and is redriven.
        logger.warning(
            'event=conversation_audio_erasure outcome=failed job=%s exception_type=%s', job, type(error).__name__
        )
        try:
            finish('failed', reason=type(error).__name__)
        except Exception:
            pass  # The lease expires; the original failure is what the queue must see.
        raise
    shared_live = int((summary or {}).get('shared_live') or 0) if isinstance(summary, dict) else 0
    if shared_live:
        # Never discharged while a recorded prefix is kept for a live sibling (the ledger linking
        # them expires): rechecked daily, erased once that sibling is deleted.
        logger.info(
            'event=conversation_audio_erasure outcome=held last_reason=staging_kept_for_live_sibling '
            'job=%s shared_live=%d',
            job,
            shared_live,
        )
        finish(
            'held',
            retry_after=AUDIO_SHARED_LIVE_RECHECK_SECONDS,
            reason='staging_kept_for_live_sibling',
            shared_live=shared_live,
        )
        return 'staging_kept_for_live_sibling'
    return 'erased' if finish('completed') else 'superseded'


__all__ = [
    'AUDIO_COLLECTION',
    'COLLECTION',
    'ERASURE_COLLECTION',
    'RunProgress',
    'RunSuperseded',
    'accept_fields',
    'arm_audio_erasure',
    'arm_fields',
    'audio_job_id',
    'audio_job_ref',
    'begin_run',
    'claim_dispatch',
    'defer',
    'due_jobs',
    'erasure_job_id',
    'erasure_job_ref',
    'finish_run',
    'job_id',
    'job_ref',
    'lease_held',
    'run_audio_erasure_job',
    'run_erasure_job',
    'run_job',
    'segment_records',
]
