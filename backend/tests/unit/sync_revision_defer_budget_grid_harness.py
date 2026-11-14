"""Shared cell harness for the sync-revision defer contention grids.

Failure-Class: FC-sync-revision-yield-commit-runs-outside-the-shared-contention-budget

Each grid cell drives one real boundary —
``database.conversation_finalization_jobs.defer_sync_revision_fence``, the
CAS-loss yield that returns a losing processor's lease to the durable
sync-revision replay queue — against a fresh in-memory store whose decorated
transactional body raises the cell's fault program, and freezes the
observables the grid tests compare as literals. The engine under test is the
production one — ``run_with_transaction_contention_retry`` — with only the
wall-clock edges patched (sleep is recorded, never slept; the jitter draw is
pinned to 0.5; deadline cells script the monotonic clock and the per-attempt
duration).

``model_cell`` is the independent hand-transcribed expectation walk: it
predicts every observable from the source predicates and the retry engine's
documented accounting (one fresh transaction per outer attempt; equal-jitter
rungs at the pinned draw; the expired-chain ceiling of three without a
deadline; the attempt cap raises the typed exhaustion; the reserve gate
refuses attempt 2+ before it starts; the never-past-deadline check refuses a
sleep that would overrun; a non-contention failure is never retried; faults
inject before the transactional body, so a faulting attempt never runs the
gates and never writes). The emitter that generated the grid files aborted
unless the model and the real boundary agreed on every cell, so each frozen
literal was cross-verified at emit time.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from google.api_core.exceptions import Aborted, InvalidArgument
from google.cloud.firestore_v1.transforms import Increment

from database import conversation_finalization_jobs as jobs
from database import firestore_transaction_retry as retry_mod
from database.firestore_transaction_retry import (
    equal_jitter_delay,
    run_with_transaction_contention_retry as _REAL_BUDGET,
)

RNG_PIN = 0.5
NOW = datetime(2026, 11, 13, tzinfo=timezone.utc)
JOB_ID = 'grid-sync-job'
UID = 'u'
CID = 'c'
CALL_GENERATION = 1
CALL_EPOCH = 2
JOB_REVISION = 5
EXPECTED_REVISION = 18
ADVANCED_REVISION = 19
PROJ_SHARD = 3
PROJ_GENERATION = jobs.FINALIZATION_PROJECTION_GENERATION
PROJ_PATH = (jobs.FINALIZATION_PROJECTION_COLLECTION, f'{PROJ_GENERATION}-{PROJ_SHARD:02d}')
JOB_PATH = (jobs.FINALIZATION_JOBS_COLLECTION, JOB_ID)
CONV_PATH = ('users', UID, jobs.CONVERSATIONS_COLLECTION, CID)
QUIET_DEFAULT = jobs.SYNC_REVISION_QUIET_SECONDS
SYNC_DEFER_QUIET_DEFAULT = QUIET_DEFAULT
STALE_DEFAULT = 300
WAIT_PRESERVED = NOW - timedelta(hours=2)
MAX_REDISPATCH = jobs.SYNC_REVISION_MAX_REDISPATCHES

# Job-row code alphabet <lease><fanout><redispatch><claim><wait>:
# lease: m current generation+epoch, g stale generation, e stale epoch,
#        s queued status, z job row absent
# fanout: n absent, p pending, d delivered
# redispatch: 0 none, 2 one below the cap, 3 at the cap
# claim: n no claim fields, 1 count 1 + counts-attempt, 3 count 3 + counts,
#        f count 1 without the flag, z count 0 with the flag
# wait: n wait-start absent, p prior wait-start present
LEASE_CODES = 'mgesz'
FANOUT_CODES = 'npd'
REDISPATCH_CODES = {'0': 0, '2': MAX_REDISPATCH - 1, '3': MAX_REDISPATCH, '1': 1, '4': MAX_REDISPATCH + 1}
CLAIM_CODES = 'n13fz'
WAIT_CODES = 'np'


def decode_job(code: str) -> dict[str, Any] | None:
    """Expand a job-row code into the stored job document (``z`` lease = absent)."""
    if code[0] == 'z':
        return None
    row: dict[str, Any] = {
        'uid': UID,
        'conversation_id': CID,
        'status': 'leased',
        'dispatch_generation': CALL_GENERATION,
        'lease_epoch': CALL_EPOCH,
        'finalization_revision': JOB_REVISION,
    }
    if code[0] == 'g':
        row['dispatch_generation'] = CALL_GENERATION + 1
    elif code[0] == 'e':
        row['lease_epoch'] = CALL_EPOCH + 1
    elif code[0] == 's':
        row['status'] = 'queued'
    fanout = code[1]
    if fanout == 'p':
        row['fanout_status'] = 'pending'
    elif fanout == 'd':
        row['fanout_status'] = 'delivered'
    row['sync_revision_redispatch_count'] = REDISPATCH_CODES[code[2]]
    claim = code[3]
    if claim == '1':
        row['worker_claim_count'] = 1
        row['lease_counts_worker_attempt'] = True
    elif claim == '3':
        row['worker_claim_count'] = 3
        row['lease_counts_worker_attempt'] = True
    elif claim == 'f':
        row['worker_claim_count'] = 1
    elif claim == 'z':
        row['worker_claim_count'] = 0
        row['lease_counts_worker_attempt'] = True
    if code[4] == 'p':
        row['sync_revision_wait_started_at'] = WAIT_PRESERVED
    return row


# Conversation-row code alphabet <status><revision><spoiler><jobid><rev>:
# status: p processing, q queued, c completed
# revision: u advanced (+1 past expected), e equal, b behind, n absent
# spoiler: c clean, d deleted, x discarded, m sync-merged-into
# jobid: j bound to this job, o bound to another job
# rev: m matches the job revision, x mismatched, a field absent
STATUS_CODES = {'p': 'processing', 'q': 'queued', 'c': 'completed'}
REVISION_CODES = {'u': ADVANCED_REVISION, 'e': EXPECTED_REVISION, 'b': EXPECTED_REVISION - 1}
SPOILER_CODES = {'c': None, 'd': ('deleted', True), 'x': ('discarded', True), 'm': ('sync_merged_into', 'conv-999')}
JOBID_CODES = {'j': JOB_ID, 'o': 'other-job'}
REV_CODES = {'m': JOB_REVISION, 'x': JOB_REVISION + 1}


def decode_conv(code: str) -> dict[str, Any]:
    """Expand a conversation-row code into the stored conversation document."""
    row: dict[str, Any] = {
        'id': CID,
        'status': STATUS_CODES[code[0]],
        'finalization_job_id': JOBID_CODES[code[3]],
    }
    if code[1] in REVISION_CODES:
        row['sync_content_revision'] = REVISION_CODES[code[1]]
    spoiler = SPOILER_CODES[code[2]]
    if spoiler is not None:
        row[spoiler[0]] = spoiler[1]
    if code[4] in REV_CODES:
        row['finalization_revision'] = REV_CODES[code[4]]
    return row


# Projection seeding for the exact-shape family: fresh has no shard row,
# leased5 carries a prior counter the delta must increment.
PROJECTION_SEEDS = {
    'fresh': None,
    'leased5': {'generation': PROJ_GENERATION, 'shard': PROJ_SHARD, 'leased': 5},
}


def apply_projection_shape(job: dict[str, Any], shape: str) -> dict[str, Any]:
    """Stamp the job's projection tuple per the cell's projection shape."""
    row = dict(job)
    row.pop('projection_generation', None)
    row.pop('projection_shard', None)
    if shape == 'valid':
        row['projection_generation'] = PROJ_GENERATION
        row['projection_shard'] = PROJ_SHARD
    elif shape == 'badgen':
        row['projection_generation'] = 'legacy-v0'
        row['projection_shard'] = PROJ_SHARD
    elif shape == 'badshard':
        row['projection_generation'] = PROJ_GENERATION
        row['projection_shard'] = 99
    return row


def _abort() -> Aborted:
    return Aborted('409 sync revision defer contention')


def _expired() -> InvalidArgument:
    return InvalidArgument('400 The referenced transaction has expired or is no longer valid')


def _expa() -> Aborted:
    return Aborted('409 the transaction has expired and is no longer valid')


def _plain_invalid() -> InvalidArgument:
    return InvalidArgument('400 plain invalid request')


def _real_failure() -> RuntimeError:
    return RuntimeError('synthetic sync-revision dependency failure')


# Hand-transcribed fault kinds: (raised class name, counts-as-expired, counts-as-contention).
_ABORT_KIND = ('Aborted', False, True)
_EXPIRED_KIND = ('InvalidArgument', True, True)
_EXPA_KIND = ('Aborted', True, True)
_PLAIN_KIND = ('InvalidArgument', False, False)
_REAL_KIND = ('RuntimeError', False, False)
FAULT_KINDS = {
    '_abort': _ABORT_KIND,
    '_expired': _EXPIRED_KIND,
    '_expa': _EXPA_KIND,
    '_plain_invalid': _PLAIN_KIND,
    '_real_failure': _REAL_KIND,
}

PROGRAMS: dict[str, list[Any]] = {
    'clean': [],
    'ab1': [_abort],
    'ab2': [_abort, _abort],
    'ab3': [_abort, _abort, _abort],
    'ab4': [_abort, _abort, _abort, _abort],
    'ab8': [_abort] * 8,
    'ex5': [_abort] * 50,
    'exp1': [_expired],
    'exp2': [_expired, _expired],
    'exp3': [_expired, _expired, _expired],
    'exp4': [_expired] * 4,
    'exp5': [_expired] * 5,
    'expa1': [_expa],
    'inv1': [_plain_invalid],
    'rte1': [_real_failure],
    'aaf': [_abort, _abort, _real_failure],
    'aec': [_abort, _expired],
    'aia': [_abort, _plain_invalid],
    'eab': [_expired, _abort],
    'eexp': [_expired, _expa],
}


def rung_delay(attempt: int) -> float:
    """Hand-transcribed equal-jitter rung at the pinned draw (rung midpoint)."""
    high = min(0.2 * (2 ** (attempt - 1)), 4.0)
    low = high / 2
    return round(low + ((high - low) * RNG_PIN), 6)


for _attempt in range(1, 13):
    _hand = rung_delay(_attempt)
    _real = round(equal_jitter_delay(_attempt, lambda: RNG_PIN), 6)
    assert _hand == _real, (_attempt, _hand, _real)


@dataclass
class _Snapshot:
    data: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any] | None:
        return copy.deepcopy(self.data)


@dataclass
class _DocumentRef:
    store: '_GridStore'
    path: tuple[str, ...]

    def get(self, transaction: object = None) -> _Snapshot:
        del transaction
        return _Snapshot(self.store.documents.get(self.path))

    @property
    def id(self) -> str:
        return self.path[-1]

    def collection(self, name: str) -> '_CollectionRef':
        return _CollectionRef(self.store, self.path + (name,))


@dataclass
class _CollectionRef:
    store: '_GridStore'
    path: tuple[str, ...]

    def document(self, document_id: str) -> _DocumentRef:
        return _DocumentRef(self.store, self.path + (document_id,))


@dataclass
class _Transaction:
    store: '_GridStore'

    def update(self, document: _DocumentRef, updates: dict[str, Any]) -> None:
        self.store.writes += 1
        target = self.store.documents.setdefault(document.path, {})
        for key, value in updates.items():
            if isinstance(value, Increment):
                target[key] = int(target.get(key) or 0) + value._value
            else:
                target[key] = copy.deepcopy(value)

    def set(self, document: _DocumentRef, data: dict[str, Any], merge: bool = False) -> None:
        self.store.writes += 1
        if merge:
            target = self.store.documents.setdefault(document.path, {})
            for key, value in data.items():
                if isinstance(value, Increment):
                    target[key] = int(target.get(key) or 0) + value._value
                else:
                    target[key] = copy.deepcopy(value)
        else:
            self.store.documents[document.path] = copy.deepcopy(data)


@dataclass
class _GridStore:
    documents: dict[tuple[str, ...], dict[str, Any]] = field(default_factory=dict)
    faults: list[Any] = field(default_factory=list)
    transactions: list[_Transaction] = field(default_factory=list)
    writes: int = 0

    def collection(self, name: str) -> _CollectionRef:
        return _CollectionRef(self, (name,))

    def transaction(self, max_attempts=None) -> _Transaction:
        transaction = _Transaction(self)
        self.transactions.append(transaction)
        return transaction


def build_store(
    job_code: str,
    conv_code: str,
    *,
    projection: str = 'valid',
    projection_seed: str = 'fresh',
) -> _GridStore:
    """Seed a fresh store with the cell's job row, conversation row and shard row."""
    store = _GridStore()
    job = decode_job(job_code)
    if job is not None:
        job = apply_projection_shape(job, projection)
        store.documents[JOB_PATH] = job
    store.documents[CONV_PATH] = decode_conv(conv_code)
    seeded_projection = copy.deepcopy(PROJECTION_SEEDS[projection_seed])
    if seeded_projection is not None:
        store.documents[PROJ_PATH] = seeded_projection
    return store


class _CellPatch:
    """Patches the jobs module's wall-clock edges for one cell, then restores.

    All knobs (``max_attempts``, ``deadline``, ``clock``, ``per_attempt``,
    ``quiet_seconds``, ``stale_seconds``) live on the patch instance and are
    read at call time, so a cell may adjust them after entering the patch.
    With ``clock`` active the monotonic read is scripted even when no
    ``deadline`` kwarg is injected, so an ambient
    ``transaction_retry_deadline_scope`` still walks the scripted clock.
    """

    def __init__(self, store: _GridStore):
        self.store = store
        self.max_attempts: int = 5
        self.deadline: float | None = None
        self.clock: dict[str, float] | None = None
        self.per_attempt: float = 1.0
        self.quiet_seconds: int = QUIET_DEFAULT
        self.stale_seconds: int = STALE_DEFAULT
        self.sleeps: list[float] = []
        self._originals: list[tuple[str, Any]] = []

    def __enter__(self) -> '_CellPatch':
        store, patch = self.store, self

        def transactional(func):
            def locked(transaction, *args, **kwargs):
                if store.faults:
                    if patch.clock is not None:
                        patch.clock['now'] += patch.per_attempt
                    raise store.faults.pop(0)()
                result = func(transaction, *args, **kwargs)
                if patch.clock is not None:
                    patch.clock['now'] += patch.per_attempt
                return result

            return locked

        def record_sleep(delay: float) -> None:
            patch.sleeps.append(round(delay, 6))
            if patch.clock is not None:
                patch.clock['now'] += delay

        def budget_retry(*args, **kwargs):
            kwargs.setdefault('sleep', record_sleep)
            kwargs.setdefault('random_value', lambda: RNG_PIN)
            kwargs['max_attempts'] = patch.max_attempts
            # Override: the joined lane runner always passes its own default-5
            # max_attempts kwarg, and this knob IS the chain's attempt budget.
            if patch.deadline is not None:
                kwargs.setdefault('deadline', patch.deadline)
            if patch.clock is not None:
                kwargs.setdefault('monotonic', lambda: patch.clock['now'])
            return _REAL_BUDGET(*args, **kwargs)

        class _Shim:
            def __init__(self, real):
                self._real = real

            def __getattr__(self, name):
                if name == 'transactional':
                    return transactional
                return getattr(self._real, name)

        self._originals = [
            ('firestore', jobs.firestore),
            ('run_with_transaction_contention_retry', retry_mod.run_with_transaction_contention_retry),
            ('_now', jobs._now),
            ('get_finalization_reconcile_stale_after', jobs.get_finalization_reconcile_stale_after),
            ('SYNC_REVISION_QUIET_SECONDS', jobs.SYNC_REVISION_QUIET_SECONDS),
        ]
        jobs.firestore = _Shim(self._originals[0][1])
        # The joined lanes import the engine at call time from the retry
        # module, so the budget wrapper patches the engine attr.
        retry_mod.run_with_transaction_contention_retry = budget_retry
        jobs._now = lambda: NOW
        jobs.get_finalization_reconcile_stale_after = lambda: timedelta(seconds=patch.stale_seconds)
        jobs.SYNC_REVISION_QUIET_SECONDS = patch.quiet_seconds
        return self

    def __exit__(self, *exc: Any) -> None:
        for name, original in reversed(self._originals):
            setattr(jobs, name, original)


def instant_token(value: Any) -> Any:
    """Freeze a stored instant as a stable token relative to ``NOW``."""
    if value is None:
        return 'absent'
    if not isinstance(value, datetime):
        return value
    total = (value - NOW).total_seconds()
    if total == 0:
        return 'now'
    return f'now+{total:g}s' if total > 0 else f'now-{abs(total):g}s'


def _facets(
    job_row: dict[str, Any] | None,
    conv_row: dict[str, Any] | None,
    proj_row: dict[str, Any] | None,
    *,
    result: Any,
    raised: str | None,
    reason: str | None,
    attempts: int,
    sleeps: list[float],
    writes: int,
    exact: bool,
) -> dict[str, Any]:
    """Freeze one cell's observables from the post-state rows."""
    job_view: dict[str, Any] = {
        'status': instant_token((job_row or {}).get('status')),
        'redispatches': instant_token((job_row or {}).get('sync_revision_redispatch_count')),
        'claim': instant_token((job_row or {}).get('worker_claim_count')),
        'reconcile_after': instant_token((job_row or {}).get('reconcile_after_at')),
        'not_before': instant_token((job_row or {}).get('sync_revision_not_before')),
        'dispatch_requested': instant_token((job_row or {}).get('dispatch_requested_at')),
        'wait_started': instant_token((job_row or {}).get('sync_revision_wait_started_at')),
        'waiting': instant_token((job_row or {}).get('sync_revision_waiting')),
        'failure_code': instant_token((job_row or {}).get('last_failure_code')),
        'observed': instant_token((job_row or {}).get('sync_revision_observed')),
    }
    cell: dict[str, Any] = {
        'result': result,
        'raised': raised,
        'reason': reason,
        'transactions': attempts,
        'sleeps': list(sleeps),
        'writes': writes,
        'job': job_view,
        'proj': (
            None
            if proj_row is None
            else {
                'generation': proj_row.get('generation'),
                'shard': proj_row.get('shard'),
                'leased': proj_row.get('leased'),
                'queued': proj_row.get('queued'),
            }
        ),
        'conv': (
            None
            if conv_row is None
            else {
                'status': conv_row.get('status'),
                'sync_content_revision': conv_row.get('sync_content_revision'),
                'deleted': conv_row.get('deleted'),
                'discarded': conv_row.get('discarded'),
                'sync_merged_into': conv_row.get('sync_merged_into'),
                'finalization_job_id': conv_row.get('finalization_job_id'),
                'finalization_revision': conv_row.get('finalization_revision'),
            }
        ),
    }
    if exact:
        cell['job_after'] = (
            None if job_row is None else {key: instant_token(value) for key, value in sorted(job_row.items())}
        )
    return cell


def run_defer_cell(
    job_code: str,
    conv_code: str,
    program: str,
    *,
    max_attempts: int = 5,
    deadline: float | None = None,
    per_attempt: float = 1.0,
    quiet_seconds: int = QUIET_DEFAULT,
    stale_seconds: int = STALE_DEFAULT,
    projection: str = 'valid',
    projection_seed: str = 'fresh',
    exact: bool = False,
) -> dict[str, Any]:
    """Drive one cell through the real boundary and freeze its observables."""
    store = build_store(job_code, conv_code, projection=projection, projection_seed=projection_seed)
    store.faults = list(PROGRAMS[program])
    patch = _CellPatch(store)
    patch.max_attempts = max_attempts
    patch.quiet_seconds = quiet_seconds
    patch.stale_seconds = stale_seconds
    if deadline is not None:
        patch.deadline = deadline
        patch.clock = {'now': 0.0}
        patch.per_attempt = per_attempt
    with patch:
        try:
            result = jobs.defer_sync_revision_fence(
                JOB_ID, CALL_GENERATION, CALL_EPOCH, EXPECTED_REVISION, firestore_client=store
            )
            raised = None
            reason = None
        except Exception as error:  # the boundary's own typed surfaces
            result = None
            raised = type(error).__name__
            reason = getattr(error, 'reason', None)
    return _facets(
        store.documents.get(JOB_PATH),
        store.documents.get(CONV_PATH),
        store.documents.get(PROJ_PATH),
        result=result,
        raised=raised,
        reason=reason,
        attempts=len(store.transactions),
        sleeps=list(patch.sleeps),
        writes=store.writes,
        exact=exact,
    )


# ---------------------------------------------------------------------------
# Hand-transcribed model (independent expectation walk; the emitter aborts
# unless the model and the real boundary agree cell by cell).
# ---------------------------------------------------------------------------

_EXPIRED_CEILING = 3


def _engine_walk(program: str, *, max_attempts: int, deadline: float | None, per_attempt: float) -> dict[str, Any]:
    """The retry engine's accounting: attempts, sleeps, raised class and reason."""
    faults = PROGRAMS[program]
    clock_active = deadline is not None
    now = 0.0
    sleeps: list[float] = []
    expired = 0
    raised = None
    reason = None
    attempts = 0
    body_ran = False
    last = 0.0
    for attempt in range(1, max_attempts + 1):
        if attempt > 1 and deadline is not None:
            remaining = deadline - now
            reserve = max(last * 1.5, 30.0)
            if remaining < reserve:
                raised = 'FirestoreContentionExhausted'
                reason = 'deadline_exhausted'
                break
        attempts = attempt
        start = now
        fault = faults[attempt - 1] if attempt - 1 < len(faults) else None
        if fault is not None:
            if clock_active:
                now += per_attempt
            last = now - start
            name, counts_expired, counts_contention = FAULT_KINDS[fault.__name__]
            if not counts_contention:
                raised = name
                break
            if counts_expired:
                expired += 1
            if attempt >= max_attempts or (deadline is None and expired >= _EXPIRED_CEILING):
                raised = 'FirestoreContentionExhausted'
                reason = 'attempts_exhausted'
                break
            delay = rung_delay(attempt)
            if deadline is not None and deadline - now < delay:
                raised = 'FirestoreContentionExhausted'
                reason = 'deadline_exhausted'
                break
            sleeps.append(round(delay, 6))
            if clock_active:
                now += delay
        else:
            if clock_active:
                now += per_attempt
            body_ran = True
            break
    return {
        'attempts': attempts,
        'sleeps': sleeps,
        'raised': raised,
        'reason': reason,
        'body_ran': body_ran,
    }


def _body_walk(
    seed_job: dict[str, Any] | None,
    seed_conv: dict[str, Any] | None,
    projection: str,
    *,
    quiet_seconds: int,
    stale_seconds: int,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """The transactional body's gate walk and the exact writes a pass commits."""
    job = seed_job or {}
    conv = seed_conv or {}
    if job.get('status') != 'leased':
        return None, None
    if int(job.get('dispatch_generation') or 1) != CALL_GENERATION:
        return None, None
    if int(job.get('lease_epoch') or 0) != CALL_EPOCH:
        return None, None
    if job.get('fanout_status') not in (None, 'pending'):
        return None, None
    if conv.get('status') != 'processing':
        return None, None
    if conv.get('deleted'):
        return None, None
    if conv.get('discarded'):
        return None, None
    if conv.get('sync_merged_into'):
        return None, None
    if conv.get('finalization_job_id') != JOB_ID:
        return None, None
    if conv.get('finalization_revision') != job.get('finalization_revision'):
        return None, None
    if int(conv.get('sync_content_revision') or 0) <= EXPECTED_REVISION:
        return None, None
    redispatches = int(job.get('sync_revision_redispatch_count') or 0)
    if redispatches >= MAX_REDISPATCH:
        return None, None
    mutations = {
        'status': 'queued',
        'updated_at': NOW,
        'lease_expires_at': NOW,
        'dispatch_requested_at': NOW - timedelta(seconds=stale_seconds),
        'reconcile_after_at': NOW + timedelta(seconds=quiet_seconds),
        'last_failure_code': 'sync_revision_advanced',
        'sync_revision_redispatch_count': redispatches + 1,
        'sync_revision_observed': int(conv.get('sync_content_revision') or 0),
        'sync_revision_waiting': True,
        'sync_revision_not_before': NOW + timedelta(seconds=quiet_seconds),
        'sync_revision_wait_started_at': job.get('sync_revision_wait_started_at') or NOW,
    }
    if job.get('lease_counts_worker_attempt'):
        mutations['worker_claim_count'] = max(0, int(job.get('worker_claim_count') or 0) - 1)
    projection_ok = (
        isinstance(job.get('projection_generation'), str)
        and job.get('projection_generation') == PROJ_GENERATION
        and isinstance(job.get('projection_shard'), int)
        and not isinstance(job.get('projection_shard'), bool)
        and 0 <= job['projection_shard'] < jobs.FINALIZATION_PROJECTION_SHARD_COUNT
    )
    deltas = None
    if projection_ok:
        deltas = {'generation': PROJ_GENERATION, 'shard': job['projection_shard'], 'leased': -1, 'queued': 1}
    return mutations, deltas


def _apply_mutation(row: dict[str, Any] | None, mutations: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        row = {}
    else:
        row = copy.deepcopy(row)
    if mutations is None:
        return row or None
    row.update(copy.deepcopy(mutations))
    return row


def _apply_deltas(seed: dict[str, Any] | None, deltas: dict[str, Any] | None) -> dict[str, Any] | None:
    if deltas is None:
        return copy.deepcopy(seed) if seed is not None else None
    row = copy.deepcopy(seed) if seed is not None else {}
    leased = deltas['leased']
    queued = deltas['queued']
    row['generation'] = deltas['generation']
    row['shard'] = deltas['shard']
    row['leased'] = int(row.get('leased') or 0) + leased
    row['queued'] = int(row.get('queued') or 0) + queued
    return row


def model_cell(
    job_code: str,
    conv_code: str,
    program: str,
    *,
    max_attempts: int = 5,
    deadline: float | None = None,
    per_attempt: float = 1.0,
    quiet_seconds: int = QUIET_DEFAULT,
    stale_seconds: int = STALE_DEFAULT,
    projection: str = 'valid',
    projection_seed: str = 'fresh',
    exact: bool = False,
) -> dict[str, Any]:
    """Predict one cell from the source predicates and the engine's accounting."""
    seed_job = decode_job(job_code)
    seeded_job_with_projection = apply_projection_shape(seed_job, projection) if seed_job is not None else None
    seed_conv = decode_conv(conv_code)
    engine = _engine_walk(program, max_attempts=max_attempts, deadline=deadline, per_attempt=per_attempt)
    writes = 0
    if engine['raised'] is not None or not engine['body_ran']:
        result = None
        job_after = seeded_job_with_projection
        proj_after = copy.deepcopy(PROJECTION_SEEDS[projection_seed])
    else:
        mutations, deltas = _body_walk(
            seeded_job_with_projection,
            seed_conv,
            projection,
            quiet_seconds=quiet_seconds,
            stale_seconds=stale_seconds,
        )
        result = mutations is not None
        job_after = _apply_mutation(seeded_job_with_projection, mutations)
        proj_after = _apply_deltas(PROJECTION_SEEDS[projection_seed], deltas)
        writes = (1 if mutations is not None else 0) + (1 if deltas is not None else 0)
    return _facets(
        job_after,
        copy.deepcopy(seed_conv),
        proj_after,
        result=result,
        raised=engine['raised'],
        reason=engine['reason'],
        attempts=engine['attempts'],
        sleeps=engine['sleeps'],
        writes=writes,
        exact=exact,
    )
