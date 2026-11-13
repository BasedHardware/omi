"""Shared cell harness for the quiet-check retirement contention grids.

Failure-Class: FC-quiet-retirement-defers-a-replayable-abort-to-the-durable-backstop

Each grid cell drives the real retirement boundary
(``database.quiet_check_retirement.stop_quiet_check_for_conversation`` or
``stop_quiet_check``) against a fresh in-memory store whose decorated
transactional body raises the cell's fault program, and returns the
observables the grid tests freeze as literals. The engine under test is the
production one — ``run_with_transaction_contention_retry`` and
``run_transactional`` — with only the wall-clock edges patched (sleep is
recorded, never slept; the jitter draw is pinned to 0.5; deadline cells
script the monotonic clock).

``model_conv_cell`` / ``model_gen_cell`` are the independent hand-transcribed
expectation walk: they predict every observable from the source predicates and
the retry engine's documented accounting (outer budget replays Aborted on
fresh transactions; ``run_transactional`` restarts an expired-id rejection on
a brand-new inner transaction with its own jitter rung; a non-contention
failure is never retried; the attempt cap is 5). The emitter that generated
the grid files aborted unless the model and the real boundary agreed on every
cell, so each frozen literal was cross-verified at emit time.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from typing import Any

from google.api_core.exceptions import Aborted, InvalidArgument

from database import quiet_check_retirement as retirement
from database._client import run_transactional as _REAL_RUN_TRANSACTIONAL
from database.firestore_transaction_retry import (
    equal_jitter_delay,
    run_with_transaction_contention_retry as _REAL_BUDGET,
)

RNG_PIN = 0.5

UID = 'grid-user'
CID = 'grid-capture'
NOW_STAMP = '2026-11-12T00:00:00+00:00'

JOBS: dict[str, dict[str, Any]] = {
    'quiet': {'kind': 'listen_quiet_check'},
    'fin': {'kind': 'listen_finalization'},
    'merge': {'kind': 'conversation_merge', 'conversation_ids': ['a', 'b']},
}

STATUS: dict[str, dict[str, Any]] = {
    'waiting': {'status': 'waiting_quiet', 'dispatch_generation': 7},
    'done_rec': {'status': 'quiet_done', 'reconcile_after_at': NOW_STAMP, 'dispatch_generation': 7},
    'done_clean': {'status': 'quiet_done', 'dispatch_generation': 7},
    'queued': {'status': 'queued', 'dispatch_generation': 8},
    'claimed': {'status': 'claimed', 'dispatch_generation': 7},
    'byok': {'status': 'blocked_byok', 'dispatch_generation': 7},
    'dispatched': {'status': 'dispatched', 'dispatch_generation': 7},
    'failed': {'status': 'failed', 'dispatch_generation': 7},
}

ROWS: dict[str, dict[str, Any] | None] = {
    'missing': None,
    'live': {'status': 'in_progress'},
    'deleted': {'status': 'in_progress', 'deleted': True},
    'discarded': {'status': 'in_progress', 'discarded': True},
    'merged': {'status': 'in_progress', 'sync_merged_into': 'survivor'},
    'finjob': {'status': 'in_progress', 'finalization_job_id': 'owner-job'},
    'processing': {'status': 'processing'},
    'completed': {'status': 'completed'},
    'failed': {'status': 'failed'},
    'merging': {'status': 'merging'},
    'locked': {'status': 'in_progress', 'is_locked': True},
}


def expected_delay(attempt: int) -> float:
    """Hand-transcribed equal-jitter rung at the pinned draw (midpoint of the rung)."""
    high = min(0.2 * (2 ** (attempt - 1)), 4.0)
    low = high / 2
    return low + ((high - low) * RNG_PIN)


for _attempt in range(1, 13):
    assert abs(expected_delay(_attempt) - equal_jitter_delay(_attempt, lambda: RNG_PIN)) < 1e-12, _attempt


def _abort() -> Aborted:
    return Aborted('409 quiet retirement contention')


def _expired() -> InvalidArgument:
    return InvalidArgument('The referenced transaction has expired or is no longer valid')


def _real_failure() -> RuntimeError:
    return RuntimeError('synthetic quiet retirement dependency failure')


PROGRAMS: dict[str, list[Any]] = {
    'clean': [],
    'ab1': [_abort],
    'ab2': [_abort, _abort],
    'ab4': [_abort, _abort, _abort, _abort],
    'exp1': [_expired],
    'exp2': [_expired, _expired],
    'fail1': [_real_failure],
    'aaf': [_abort, _abort, _real_failure],
    'aec': [_abort, _expired],
    'ex5': [_abort] * 50,
}


@dataclass
class _Snapshot:
    data: dict[str, Any] | None

    @property
    def exists(self) -> bool:
        return self.data is not None

    def to_dict(self) -> dict[str, Any] | None:
        return copy.deepcopy(self.data)


@dataclass
class _DocumentRef:
    store: '_GridStore'
    path: tuple[str, ...]

    def get(self, transaction: object = None) -> _Snapshot:
        del transaction
        return _Snapshot(self.store.documents.get(self.path))

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
        self.store.documents.setdefault(document.path, {}).update(copy.deepcopy(updates))


@dataclass
class _GridStore:
    documents: dict[tuple[str, ...], dict[str, Any]] = field(default_factory=dict)
    read_errors: list[Any] = field(default_factory=list)
    transactions: list[_Transaction] = field(default_factory=list)
    writes: int = 0
    job_path: tuple[str, ...] = ('conversation_finalization_jobs', 'unset')

    def collection(self, name: str) -> _CollectionRef:
        return _CollectionRef(self, (name,))

    def transaction(self) -> _Transaction:
        transaction = _Transaction(self)
        self.transactions.append(transaction)
        return transaction


class _DeferCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.deferred = False

    def emit(self, record: logging.LogRecord) -> None:
        if 'outcome=deferred' in record.getMessage():
            self.deferred = True


def _conv_job_path() -> tuple[str, ...]:
    return ('conversation_finalization_jobs', retirement.quiet_check_id(UID, CID))


class _CellPatch:
    """Patches the retirement module's wall-clock edges for one cell, then restores.

    All knob dicts (``budget_kwargs``, ``clock``) are read at call time, so a
    cell may adjust them after entering the patch.
    """

    def __init__(self, store: _GridStore):
        self.store = store
        self.clock: dict[str, float] | None = None
        self.per_attempt: float = 0.0
        self.rng: float = RNG_PIN
        self.budget_kwargs: dict[str, Any] = {}
        self.outer_sleeps: list[float] = []
        self.inner_sleeps: list[float] = []
        self.gate_answers: list[int] = []
        self._originals: list[tuple[str, Any]] = []

    def __enter__(self) -> '_CellPatch':
        def transactional(func):
            def locked(transaction, *args, **kwargs):
                if self.store.read_errors:
                    if self.clock is not None:
                        self.clock['now'] += self.per_attempt
                    raise self.store.read_errors.pop(0)()
                result = func(transaction, *args, **kwargs)
                if self.clock is not None:
                    self.clock['now'] += self.per_attempt
                return result

            return locked

        def record_sleep(delay: float) -> None:
            self.outer_sleeps.append(delay)
            if self.clock is not None:
                self.clock['now'] += delay

        def budget_retry(*args, **kwargs):
            kwargs.setdefault('sleep', record_sleep)
            kwargs.setdefault('random_value', lambda: self.rng)
            for key, value in self.budget_kwargs.items():
                kwargs.setdefault(key, value)
            if self.clock is not None:
                kwargs.setdefault('monotonic', lambda: self.clock['now'])
            return _REAL_BUDGET(*args, **kwargs)

        def grid_run_transactional(*args, **kwargs):
            kwargs.setdefault('sleep', self.inner_sleeps.append)
            kwargs.setdefault('random_value', lambda: RNG_PIN)
            return _REAL_RUN_TRANSACTIONAL(*args, **kwargs)

        self._originals = [
            ('transactional', retirement.firestore.transactional),
            ('run_with_transaction_contention_retry', retirement.run_with_transaction_contention_retry),
            ('run_transactional', retirement.run_transactional),
        ]
        retirement.firestore.transactional = transactional
        retirement.run_with_transaction_contention_retry = budget_retry
        retirement.run_transactional = grid_run_transactional
        return self

    def __exit__(self, *exc: Any) -> None:
        for name, original in reversed(self._originals):
            if name == 'transactional':
                retirement.firestore.transactional = original
            else:
                setattr(retirement, name, original)


def _observables(store: _GridStore, patch: _CellPatch, capture: _DeferCapture, result: Any, raised: str | None):
    job_after = store.documents.get(store.job_path)
    return {
        'result': result,
        'job_status_after': None if job_after is None else job_after.get('status'),
        'transactions': len(store.transactions),
        'outer_sleeps': list(patch.outer_sleeps),
        'inner_sleeps': list(patch.inner_sleeps),
        'writes': store.writes,
        'deferred': capture.deferred,
        'raised': raised,
    }


def _drive(store: _GridStore, call):
    capture = _DeferCapture()
    logger = logging.getLogger('database.quiet_check_retirement')
    logger.addHandler(capture)
    try:
        with _CellPatch(store, *()) as patch:
            patch_kwargs: dict[str, Any] = {}
            try:
                result = call(store, patch, patch_kwargs)
                raised = None
            except Exception as error:  # the boundary's own typed surfaces
                result = None
                raised = type(error).__name__
            return _observables(store, patch, capture, result, raised), patch_kwargs
    finally:
        logger.removeHandler(capture)


def run_conv_cell(
    kind: str,
    status: str,
    row: str,
    program: str,
    *,
    max_attempts: int = 5,
    clock: dict[str, float] | None = None,
    per_attempt: float = 0.0,
    inter_attempt_gate=None,
    deadline: float | None = None,
    rng: float = RNG_PIN,
    aborts_then_clean: int | None = None,
) -> dict[str, Any]:
    """Drive one conversation-lane cell and return its observables.

    ``aborts_then_clean`` replaces the fault program with exactly that many
    fresh aborts followed by a clean attempt (the schedule grid's shapes).
    """
    store = _GridStore()
    store.job_path = _conv_job_path()
    if kind != 'absent':
        store.documents[store.job_path] = {**JOBS[kind], **STATUS[status]}
    row_shape = ROWS[row]
    if row_shape is not None:
        store.documents[('users', UID, 'conversations', CID)] = dict(row_shape)
    if aborts_then_clean is None:
        store.read_errors = list(PROGRAMS[program])
    else:
        store.read_errors = [_abort for _ in range(aborts_then_clean)]
    budget_kwargs: dict[str, Any] = {'max_attempts': max_attempts}
    if inter_attempt_gate is not None:
        budget_kwargs['inter_attempt_gate'] = inter_attempt_gate
    if deadline is not None:
        budget_kwargs['deadline'] = deadline

    def call(target_store: _GridStore, patch: _CellPatch, patch_kwargs: dict[str, Any]):
        patch.budget_kwargs = budget_kwargs
        if clock is not None:
            patch.clock = clock
            patch.per_attempt = per_attempt
        patch.rng = rng
        return retirement.stop_quiet_check_for_conversation(UID, CID, firestore_client=target_store)

    observables, _ = _drive(store, call)
    return observables


def recording_gate(answer):
    """An inter-attempt gate that records the attempt numbers it was asked about."""
    answers: list[int] = []

    def gate(attempt: int):
        answers.append(attempt)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    return gate, answers


def run_gen_cell(
    kind: str,
    status: str,
    proposed_generation: int,
    program: str,
    *,
    max_attempts: int = 5,
) -> dict[str, Any]:
    """Drive one generation-lane cell and return its observables."""
    store = _GridStore()
    store.job_path = ('conversation_finalization_jobs', 'grid-worker-job')
    if kind != 'absent':
        store.documents[store.job_path] = {**JOBS[kind], **STATUS[status]}
    store.read_errors = list(PROGRAMS[program])

    def call(target_store: _GridStore, patch: _CellPatch, patch_kwargs: dict[str, Any]):
        patch.budget_kwargs = {'max_attempts': max_attempts}
        return retirement.stop_quiet_check(store.job_path[-1], proposed_generation, firestore_client=target_store)

    observables, _ = _drive(store, call)
    return observables


# ---------------------------------------------------------------------------
# Independent hand-transcribed expectation model.
# ---------------------------------------------------------------------------

_OUTER_ATTEMPT_CAP = 5


def model_conv_cell(
    kind: str,
    status: str,
    row: str,
    program: str,
    *,
    max_attempts: int = 5,
    clock: dict[str, float] | None = None,
    per_attempt: float = 0.0,
    inter_attempt_gate=None,
    deadline: float | None = None,
) -> dict[str, Any]:
    seeded_status = None if kind == 'absent' else STATUS[status]['status']
    retires = (
        kind == 'quiet'
        and not (status == 'done_clean')
        and (
            row == 'missing'
            or ROWS[row].get('status') != 'in_progress'
            or any(ROWS[row].get(key) for key in ('deleted', 'discarded', 'sync_merged_into', 'finalization_job_id'))
        )
    )
    short_circuit = kind != 'quiet'

    transactions = 0
    outer: list[float] = []
    inner: list[float] = []
    deferred = False
    raised = None
    result = None

    if short_circuit:
        result = False
    else:
        if program == 'clean':
            transactions = 1
        elif program == 'aaf':
            transactions = 3
            outer = [expected_delay(1), expected_delay(2)]
            deferred = True
            result = False
        elif program in ('ab1', 'ab2', 'ab4'):
            aborts = {'ab1': 1, 'ab2': 2, 'ab4': 4}[program]
            transactions = aborts + 1
            if transactions <= max_attempts:
                outer = [expected_delay(a) for a in range(1, aborts + 1)]
            else:
                capped = max_attempts - 1
                transactions = max_attempts
                outer = [expected_delay(a) for a in range(1, capped + 1)]
                deferred = True
                raised = None
                result = False
        elif program in ('exp1', 'exp2'):
            expiries = {'exp1': 1, 'exp2': 2}[program]
            transactions = 1 + expiries
            inner = [expected_delay(a) for a in range(1, expiries + 1)]
        elif program == 'aec':
            transactions = 3
            outer = [expected_delay(1)]
            inner = [expected_delay(1)]
        elif program == 'fail1':
            transactions = 1
            deferred = True
            result = False
        elif program == 'ex5':
            transactions = max_attempts
            outer = [expected_delay(a) for a in range(1, max_attempts)]
            deferred = True
            result = False
        else:  # pragma: no cover - emitter forbids unknown programs
            raise ValueError(program)

        if result is None and raised is None and not deferred:
            result = retires

    if retires and transactions > 0 and not deferred:
        job_status_after = 'quiet_done'
    else:
        job_status_after = seeded_status

    writes = 1 if (retires and transactions > 0 and not deferred) else 0
    if short_circuit:
        writes = 0

    return {
        'result': result,
        'job_status_after': job_status_after,
        'transactions': transactions,
        'outer_sleeps': outer,
        'inner_sleeps': inner,
        'writes': writes,
        'deferred': deferred,
        'raised': raised,
    }


def model_gen_cell(
    kind: str,
    status: str,
    proposed_generation: int,
    program: str,
    *,
    max_attempts: int = 5,
) -> dict[str, Any]:
    seeded_generation = None if kind == 'absent' else STATUS[status]['dispatch_generation']
    seeded_status = None if kind == 'absent' else STATUS[status]['status']
    retires = seeded_generation == proposed_generation and kind == 'quiet'

    transactions = 0
    outer: list[float] = []
    inner: list[float] = []
    raised = None
    if program == 'clean':
        transactions = 1
    elif program in ('ab1', 'ab2', 'ab4'):
        aborts = {'ab1': 1, 'ab2': 2, 'ab4': 4}[program]
        transactions = aborts + 1
        if transactions <= max_attempts:
            outer = [expected_delay(a) for a in range(1, aborts + 1)]
        else:
            transactions = max_attempts
            outer = [expected_delay(a) for a in range(1, max_attempts)]
            raised = 'FirestoreContentionExhausted'
    elif program in ('exp1', 'exp2'):
        expiries = {'exp1': 1, 'exp2': 2}[program]
        transactions = 1 + expiries
        inner = [expected_delay(a) for a in range(1, expiries + 1)]
    elif program == 'aec':
        transactions = 3
        outer = [expected_delay(1)]
        inner = [expected_delay(1)]
    elif program == 'fail1':
        transactions = 1
        raised = 'RuntimeError'
    elif program == 'aaf':
        transactions = 3
        outer = [expected_delay(1), expected_delay(2)]
        raised = 'RuntimeError'
    elif program == 'ex5':
        transactions = max_attempts
        outer = [expected_delay(a) for a in range(1, max_attempts)]
        raised = 'FirestoreContentionExhausted'
    else:  # pragma: no cover - emitter forbids unknown programs
        raise ValueError(program)

    job_status_after = 'quiet_done' if (retires and raised is None) else seeded_status
    return {
        'result': None,
        'job_status_after': job_status_after,
        'transactions': transactions,
        'outer_sleeps': outer,
        'inner_sleeps': inner,
        'writes': 1 if (retires and raised is None) else 0,
        'deferred': False,
        'raised': raised,
    }
