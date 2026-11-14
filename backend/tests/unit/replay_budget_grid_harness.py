"""Shared cell harness for the finalization replay lane contention grids.

Failure-Class: FC-replay-sweep-cursor-and-backoff-run-outside-the-shared-contention-budget

Each grid cell drives one real replay-lane boundary —
``database.conversation_finalization_jobs.defer_finalization_replay`` (the
sweep backoff write) or the replay cursor CAS advance inside
``get_finalization_replay_candidates`` — against a fresh in-memory store whose
decorated transactional body raises the cell's fault program, and returns the
observables the grid tests freeze as literals. The engine under test is the
production one — ``run_with_transaction_contention_retry`` — with only the
wall-clock edges patched (sleep is recorded, never slept; the jitter draw is
pinned to 0.5; deadline cells script the monotonic clock and the per-attempt
duration).

``model_defer_cell`` / ``model_cursor_cell`` are the independent
hand-transcribed expectation walks: they predict every observable from the
source predicates and the retry engine's documented accounting (a fresh
transaction per outer attempt; equal-jitter rungs at the pinned draw; the
expired-chain ceiling of three without a deadline; the attempt cap of five
raises the typed exhaustion without a final sleep; the reserve gate refuses
attempt 2+ before it starts; the never-past-deadline check refuses a sleep
that would overrun; a non-contention failure is never retried; faults inject
before the transactional body, so a faulting attempt never writes). The
emitter that generated the grid files aborted unless the model and the real
boundary agreed on every cell, so each frozen literal was cross-verified at
emit time.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

from google.api_core.exceptions import Aborted, InvalidArgument

from database import conversation_finalization_jobs as jobs
from database import firestore_transaction_retry as retry_mod
from database.firestore_transaction_retry import (
    equal_jitter_delay,
    run_with_transaction_contention_retry as _REAL_BUDGET,
)

RNG_PIN = 0.5
NOW = datetime(2026, 11, 12, tzinfo=timezone.utc)
OVERDUE = NOW - timedelta(hours=1)
JOB_ID = 'grid-job'
STATE_PATH = ('conversation_recovery_state', 'finalization_replay')
JOB_PATH = (jobs.FINALIZATION_JOBS_COLLECTION, JOB_ID)

# Row alphabet: <status:2><generation:1><reconcile_after_at:1><kind:1>.
STATUS_CODES = {
    'wq': 'waiting_quiet',
    'qd': 'quiet_done',
    'qu': 'queued',
    'le': 'leased',
    'bb': 'blocked_byok',
    'co': 'completed',
    'dl': 'dead_letter',
    'di': 'dispatched',
}
GEN_CODES = {'m': 1, 'x': 2, 'n': None}  # m: candidate matches; x: mismatch; n: field absent
RAT_CODES = {'o': 'match', 'r': 'mismatch', 'f': 'future', 'n': 'none'}
KIND_CODES = {'q': 'listen_quiet_check', 'f': 'listen_finalization'}
RAT_DELETED = 'deleted'


def decode_row(code: str) -> dict[str, Any] | None:
    """Expand a row code into the stored job document (``zz`` = row absent)."""
    if code == 'zz':
        return None
    status, gen, rat, kind = code[0:2], code[2], code[3], code[4]
    row: dict[str, Any] = {'kind': KIND_CODES[kind], 'status': STATUS_CODES[status]}
    if GEN_CODES[gen] is not None:
        row['dispatch_generation'] = GEN_CODES[gen]
    rat_mode = RAT_CODES[rat]
    if rat_mode == 'match':
        row['reconcile_after_at'] = OVERDUE
    elif rat_mode == 'mismatch':
        row['reconcile_after_at'] = OVERDUE - timedelta(seconds=1)
    elif rat_mode == 'future':
        row['reconcile_after_at'] = NOW + timedelta(hours=1)
    return row


def defer_candidate(
    row_code: str, *, status_variant: str = 'match', gen_variant: str = 'row', rat_variant: str = 'row'
) -> dict[str, Any]:
    """Build the overdue snapshot the sweep would defer for ``row_code``.

    The candidate is the page-time snapshot; the stored row may have moved on
    since (another writer updated it), which is exactly the gen ``x`` code:
    the candidate carries the stale pre-update generation. Rat ``r`` carries
    the page-time due against a since-moved stored due.
    """
    row = decode_row(row_code) or {}
    gen_code = row_code[2] if len(row_code) >= 5 else ''
    rat_code = row_code[3] if len(row_code) >= 5 else ''
    if status_variant == 'match':
        status = row.get('status') or 'queued'
    else:
        status = 'queued'
    if gen_variant == 'row':
        generation = row.get('dispatch_generation', 1)
        if gen_code == 'x':
            generation = generation + 1
    elif gen_variant == 'other':
        generation = 9
    else:
        generation = int(gen_variant)
    if rat_variant == 'row':
        due = row.get('reconcile_after_at', OVERDUE)
        if rat_code == 'r':
            due = OVERDUE
    elif rat_variant == 'match':
        due = OVERDUE
    else:
        due = NOW - timedelta(hours=2)
    return {
        'job_id': JOB_ID,
        'kind': row.get('kind', 'listen_quiet_check'),
        'status': status,
        'dispatch_generation': generation,
        'reconcile_after_at': due,
    }


def _abort() -> Aborted:
    return Aborted('409 replay sweep contention')


def _expired() -> InvalidArgument:
    return InvalidArgument('The referenced transaction has expired or is no longer valid')


def _real_failure() -> RuntimeError:
    return RuntimeError('synthetic replay sweep dependency failure')


PROGRAMS: dict[str, list[Any]] = {
    'clean': [],
    'ab1': [_abort],
    'ab2': [_abort, _abort],
    'ab3': [_abort, _abort, _abort],
    'ab4': [_abort, _abort, _abort, _abort],
    'ex5': [_abort] * 50,
    'exp1': [_expired],
    'exp2': [_expired, _expired],
    'exp3': [_expired, _expired, _expired],
    'fail1': [_real_failure],
    'aaf': [_abort, _abort, _real_failure],
    'aec': [_abort, _expired],
    # Aborts-then-clean chains: exactly k fresh aborts, then a clean attempt.
    'k1': [_abort],
    'k2': [_abort, _abort],
    'k3': [_abort, _abort, _abort],
    'k4': [_abort, _abort, _abort, _abort],
    'k5': [_abort, _abort, _abort, _abort, _abort],
}


def expected_delay(attempt: int) -> float:
    """Hand-transcribed equal-jitter rung at the pinned draw (rung midpoint)."""
    high = min(0.2 * (2 ** (attempt - 1)), 4.0)
    low = high / 2
    return low + ((high - low) * RNG_PIN)


for _attempt in range(1, 13):
    assert abs(expected_delay(_attempt) - equal_jitter_delay(_attempt, lambda: RNG_PIN)) < 1e-12, _attempt


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


@dataclass
class _DueQuery:
    store: '_GridStore'
    cutoff: datetime | None = None
    after: tuple[datetime, str] | None = None
    bound: int = 100

    def where(self, field_path: str, op: str, cutoff: datetime) -> '_DueQuery':
        assert (field_path, op) == ('reconcile_after_at', '<=')
        self.cutoff = cutoff
        return self

    def order_by(self, field_path: str) -> '_DueQuery':
        assert field_path in {'reconcile_after_at', '__name__'}
        return self

    def start_after(self, cursor: dict[str, Any]) -> '_DueQuery':
        self.after = (cursor['reconcile_after_at'], cursor['__name__'].id)
        return self

    def limit(self, bound: int) -> '_DueQuery':
        self.bound = bound
        return self

    def stream(self):
        ordered = sorted(
            (row['reconcile_after_at'], path[-1], row)
            for path, row in self.store.documents.items()
            if path[0] == jobs.FINALIZATION_JOBS_COLLECTION
            and isinstance(row.get('reconcile_after_at'), datetime)
            and row['reconcile_after_at'] <= self.cutoff
        )
        rows = [entry for entry in ordered if self.after is None or entry[:2] > self.after]
        return iter(SimpleNamespace(id=key, to_dict=(lambda row=dict(row): row)) for _, key, row in rows[: self.bound])


@dataclass
class _CollectionRef:
    store: '_GridStore'
    path: tuple[str, ...]

    def document(self, document_id: str) -> _DocumentRef:
        return _DocumentRef(self.store, self.path + (document_id,))

    def where(self, *args: Any) -> _DueQuery:
        return _DueQuery(self.store).where(*args)


@dataclass
class _Transaction:
    store: '_GridStore'

    def update(self, document: _DocumentRef, updates: dict[str, Any]) -> None:
        self.store.writes += 1
        target = self.store.documents.setdefault(document.path, {})
        for key, value in updates.items():
            if value is jobs.firestore.DELETE_FIELD:
                target.pop(key, None)
            else:
                target[key] = copy.deepcopy(value)

    def set(self, document: _DocumentRef, data: dict[str, Any]) -> None:
        self.store.writes += 1
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


class _CellPatch:
    """Patches the jobs module's wall-clock edges for one cell, then restores.

    All knobs (``max_attempts``, ``deadline``, ``clock``, ``per_attempt``) live
    on the patch instance and are read at call time, so a cell may adjust them
    after entering the patch.
    """

    def __init__(self, store: _GridStore):
        self.store = store
        self.max_attempts: int = 5
        self.deadline: float | None = None
        self.clock: dict[str, float] | None = None
        self.per_attempt: float = 1.0
        self.sleeps: list[float] = []
        self._originals: list[tuple[str, Any]] = []

    def __enter__(self) -> '_CellPatch':
        store = self.store

        def transactional(func):
            def locked(transaction, *args, **kwargs):
                if store.faults:
                    if self.clock is not None:
                        self.clock['now'] += self.per_attempt
                    raise store.faults.pop(0)()
                result = func(transaction, *args, **kwargs)
                if self.clock is not None:
                    self.clock['now'] += self.per_attempt
                return result

            return locked

        def record_sleep(delay: float) -> None:
            self.sleeps.append(delay)
            if self.clock is not None:
                self.clock['now'] += delay

        def budget_retry(*args, **kwargs):
            kwargs.setdefault('sleep', record_sleep)
            kwargs.setdefault('random_value', lambda: RNG_PIN)
            kwargs['max_attempts'] = self.max_attempts
            # Override: the joined lane runner always passes its own default-5
            # max_attempts kwarg, and this knob IS the chain's attempt budget.
            if self.deadline is not None:
                kwargs.setdefault('deadline', self.deadline)
                kwargs.setdefault('monotonic', lambda: self.clock['now'])
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
        ]
        jobs.firestore = _Shim(self._originals[0][1])
        # The joined lanes import the engine at call time from the retry
        # module, so the budget wrapper patches the engine attr and keeps
        # intercepting every lane chain.
        retry_mod.run_with_transaction_contention_retry = budget_retry
        jobs._now = lambda: NOW
        return self

    def __exit__(self, *exc: Any) -> None:
        for name, original in reversed(self._originals):
            setattr(jobs, name, original)


def _seed_defer_store(row: dict[str, Any] | None) -> _GridStore:
    store = _GridStore()
    if row is not None:
        store.documents[JOB_PATH] = copy.deepcopy(row)
    return store


def run_defer_cell(
    row_code: str,
    program: str,
    *,
    status_variant: str = 'match',
    gen_variant: str = 'row',
    rat_variant: str = 'row',
    max_attempts: int = 5,
    deadline: float | None = None,
    per_attempt: float = 1.0,
) -> dict[str, Any]:
    """Drive one backoff cell and freeze the real boundary's observables."""
    row = decode_row(row_code)
    seeded_has_rat = row is not None and 'reconcile_after_at' in row
    store = _seed_defer_store(row)
    store.faults = list(PROGRAMS[program])
    candidate = defer_candidate(
        row_code, status_variant=status_variant, gen_variant=gen_variant, rat_variant=rat_variant
    )
    patch = _CellPatch(store)
    patch.max_attempts = max_attempts
    if deadline is not None:
        patch.deadline = deadline
        patch.clock = {'now': 0.0}
        patch.per_attempt = per_attempt
    with patch:
        try:
            result = jobs.defer_finalization_replay(candidate, firestore_client=store)
            raised = None
        except Exception as error:  # the boundary's own typed surfaces
            result = None
            raised = type(error).__name__
    row_after = store.documents.get(JOB_PATH)
    if row_after is None:
        rat_after = 'missing'
    elif 'reconcile_after_at' not in row_after:
        rat_after = RAT_DELETED if seeded_has_rat else 'missing'
    elif row_after['reconcile_after_at'] == NOW + timedelta(seconds=60):
        rat_after = 'advanced'
    else:
        rat_after = 'unchanged'
    return {
        'result': result,
        'raised': raised,
        'rat_after': rat_after,
        'transactions': len(store.transactions),
        'sleeps': list(patch.sleeps),
        'writes': store.writes,
    }


# Cursor shape alphabet (the state document's persisted cursor):
# none: no persisted cursor; full: prior full-page cursor; minimal: no cutoff;
# cstr: cutoff not a datetime; njid: cursor without a job id.
CURSOR_SHAPES = {
    'none': None,
    'full': {
        'reconcile_after_at': OVERDUE - timedelta(minutes=30),
        'job_id': 'quiet-000',
        'cutoff': NOW - timedelta(minutes=1),
    },
    'minimal': {'reconcile_after_at': OVERDUE - timedelta(minutes=30), 'job_id': 'quiet-000'},
    'cstr': {'reconcile_after_at': OVERDUE - timedelta(minutes=30), 'job_id': 'quiet-000', 'cutoff': 'not-a-datetime'},
    'njid': {'reconcile_after_at': OVERDUE - timedelta(minutes=30), 'cutoff': NOW - timedelta(minutes=1)},
}

# Page scenarios (what the due-window query selects at limit 3):
# full: 3 due rows -> next cursor; partial: 2 due rows -> cursor rewinds;
# empty: 3 future rows -> nothing due; mixed: 1 due + 2 future rows.
PAGE_SCENARIOS = {'full': 3, 'partial': 2, 'empty': 0, 'mixed': 1}


def _seed_cursor_store(shape: str, scenario: str) -> tuple[_GridStore, Any]:
    store = _GridStore()
    state = {'generation': 7, 'cursor': copy.deepcopy(CURSOR_SHAPES[shape])}
    store.documents[STATE_PATH] = state
    due_rows = PAGE_SCENARIOS[scenario]
    for index in range(3):
        due = index < due_rows
        store.documents[(jobs.FINALIZATION_JOBS_COLLECTION, f'quiet-{index:03}')] = {
            'kind': 'listen_quiet_check',
            'status': 'waiting_quiet',
            'dispatch_generation': 1,
            'reconcile_after_at': OVERDUE if due else NOW + timedelta(hours=1),
            'due_at': OVERDUE,
        }
    return store, state.get('cursor')


def run_cursor_cell(
    shape: str,
    scenario: str,
    program: str,
    *,
    max_attempts: int = 5,
    deadline: float | None = None,
    per_attempt: float = 1.0,
) -> dict[str, Any]:
    """Drive one replay-page cell (cursor CAS advance under the budget).

    ``shape`` is the persisted cursor shape; ``scenario`` is what the due
    window selects (full/partial/empty/mixed at limit 3).
    """
    store, pre_cursor = _seed_cursor_store(shape, scenario)
    store.faults = list(PROGRAMS[program])
    patch = _CellPatch(store)
    patch.max_attempts = max_attempts
    if deadline is not None:
        patch.deadline = deadline
        patch.clock = {'now': 0.0}
        patch.per_attempt = per_attempt
    with patch:
        try:
            result = jobs.get_finalization_replay_candidates(limit=3, firestore_client=store)
            raised = None
        except Exception as error:
            result = None
            raised = type(error).__name__
    state_after = store.documents.get(STATE_PATH) or {}
    post_cursor = state_after.get('cursor')
    if post_cursor == pre_cursor:
        cursor_after = 'unchanged'
    elif isinstance(post_cursor, dict):
        cursor_after = 'set'
    else:
        cursor_after = 'wrapped'
    return {
        'page': len(result or []),
        'raised': raised,
        'generation_after': state_after.get('generation'),
        'cursor_after': cursor_after,
        'transactions': len(store.transactions),
        'sleeps': list(patch.sleeps),
        'writes': store.writes,
    }


# ---------------------------------------------------------------------------
# Hand-transcribed models (independent expectation walks; the emitter aborts
# unless model and real boundary agree cell by cell).
# ---------------------------------------------------------------------------

_CONTENTION = ('Aborted', 'InvalidArgument')
_CAP = 5
_EXPIRED_CEILING = 3


def _engine_walk(
    program: list[Any], *, max_attempts: int, deadline: float | None, per_attempt: float
) -> dict[str, Any]:
    """The retry engine's accounting: attempts, sleeps, raised token."""
    now = 0.0
    sleeps: list[float] = []
    expired_chains = 0
    raised = None
    attempts = 0
    for attempt in range(1, max_attempts + 1):
        attempts = attempt
        if attempt > 1 and deadline is not None:
            remaining = deadline - now
            reserve = max(per_attempt * 1.5, 30.0)
            if remaining < reserve:
                raised = 'FirestoreContentionExhausted'
                break
        fault = program[attempt - 1] if attempt - 1 < len(program) else None
        if fault is not None:
            if deadline is not None:
                now += per_attempt
            error = fault()
            name = type(error).__name__
            if name not in _CONTENTION:
                raised = name
                break
            if name == 'InvalidArgument':
                expired_chains += 1
            if attempt >= max_attempts or (deadline is None and expired_chains >= _EXPIRED_CEILING):
                raised = 'FirestoreContentionExhausted'
                break
            delay = expected_delay(attempt)
            if deadline is not None and deadline - now < delay:
                raised = 'FirestoreContentionExhausted'
                break
            sleeps.append(delay)
            now += delay
        else:
            if deadline is not None:
                now += per_attempt
            break
    return {'attempts': attempts, 'sleeps': sleeps, 'raised': raised}


def model_defer_cell(
    row_code: str,
    program: str,
    *,
    status_variant: str = 'match',
    gen_variant: str = 'row',
    rat_variant: str = 'row',
    max_attempts: int = 5,
    deadline: float | None = None,
    per_attempt: float = 1.0,
) -> dict[str, Any]:
    """Predict one backoff cell from the source predicates and engine accounting."""
    row = decode_row(row_code)
    candidate = defer_candidate(
        row_code, status_variant=status_variant, gen_variant=gen_variant, rat_variant=rat_variant
    )
    faults = PROGRAMS[program]
    engine = _engine_walk(faults, max_attempts=max_attempts, deadline=deadline, per_attempt=per_attempt)

    # Only attempts that pass the fault program reach the transactional body;
    # a faulting or gate-refused attempt never runs it, so it never writes.
    faults_consumed = min(len(faults), engine['attempts'])
    body_runs = engine['attempts'] - faults_consumed
    if engine['raised'] or body_runs == 0:
        result = None
        decided = False
    else:
        current = row or {}
        due = current.get('reconcile_after_at')
        if not isinstance(due, datetime) or due > NOW:
            result = False
            decided = True
        elif any(
            current.get(key) != candidate.get(key) for key in ('status', 'dispatch_generation', 'reconcile_after_at')
        ):
            result = False
            decided = True
        else:
            result = True
            decided = True

    if result is True:
        kind = (row or {}).get('kind')
        status = (row or {}).get('status')
        terminal_delete = kind != 'listen_quiet_check' and (
            status in {'completed', 'dead_letter'} or status == 'blocked_byok'
        )
        rat_after = RAT_DELETED if terminal_delete else 'advanced'
        writes = body_runs
    elif decided:
        rat_after = 'missing' if row is None else ('unchanged' if 'reconcile_after_at' in row else 'missing')
        writes = 0
    else:
        rat_after = 'missing' if row is None else ('unchanged' if 'reconcile_after_at' in row else 'missing')
        writes = 0
    return {
        'result': result,
        'raised': engine['raised'],
        'rat_after': rat_after,
        'transactions': engine['attempts'],
        'sleeps': engine['sleeps'],
        'writes': writes,
    }


def model_cursor_cell(
    shape: str,
    scenario: str,
    program: str,
    *,
    max_attempts: int = 5,
    deadline: float | None = None,
    per_attempt: float = 1.0,
) -> dict[str, Any]:
    """Predict one replay-page cell from the source predicates and engine accounting."""
    persisted_generation = 7
    pre_cursor = copy.deepcopy(CURSOR_SHAPES[shape])
    due_rows = PAGE_SCENARIOS[scenario]
    faults = PROGRAMS[program]
    engine = _engine_walk(faults, max_attempts=max_attempts, deadline=deadline, per_attempt=per_attempt)

    if engine['raised'] is not None:
        # The fault fired before the transactional body: nothing was written.
        return {
            'page': 0,
            'raised': engine['raised'],
            'generation_after': persisted_generation,
            'cursor_after': 'unchanged',
            'transactions': engine['attempts'],
            'sleeps': engine['sleeps'],
            'writes': 0,
        }
    faults_consumed = min(len(faults), engine['attempts'])
    body_runs = engine['attempts'] - faults_consumed

    # Non-transactional page walk: state read, cutoff freeze, query, next cursor.
    cutoff = NOW
    if isinstance(pre_cursor, dict) and isinstance(pre_cursor.get('cutoff'), datetime):
        cutoff = pre_cursor['cutoff']
    page_len = due_rows
    next_cursor = None
    if page_len == 3:
        next_cursor = {'reconcile_after_at': OVERDUE, 'job_id': 'quiet-002', 'cutoff': cutoff}

    # Transactional CAS advance: the request generation is read from the same
    # pre-read state, so the CAS always matches here and writes the cursor.
    generation_after = persisted_generation + 1
    post_cursor = next_cursor
    writes = body_runs
    if post_cursor == pre_cursor:
        cursor_after = 'unchanged'
    elif isinstance(post_cursor, dict):
        cursor_after = 'set'
    else:
        cursor_after = 'wrapped'
    return {
        'page': page_len,
        'raised': None,
        'generation_after': generation_after,
        'cursor_after': cursor_after,
        'transactions': engine['attempts'],
        'sleeps': engine['sleeps'],
        'writes': writes,
    }
