"""Quiet-check retirement runs on the shared bounded contention budget.

Failure-Class: FC-quiet-retirement-defers-a-replayable-abort-to-the-durable-backstop

The retirement boundary used to run a bare ``firestore.transactional`` call:
the SDK replays a commit abort on the same — often retired — transaction id
and never retries an abort raised by the body's read, so a mid-burst transient
abort deferred the retirement to the durable replay backstop (conversation
lane, ``outcome=deferred`` traceback family in prod backend-listen) or failed
a delivered worker's whole run (generation lane, raw ``Aborted``). Both stop
lanes now compose ``run_transactional`` (expired-id restart on a brand-new
id) inside ``run_with_transaction_contention_retry`` (bounded equal-jitter
replay on fresh transactions) — the same budget every recording-session
writer on these documents already uses.

Guards:
- a read-time abort replays on a fresh transaction and commits exactly once;
- an expired-transaction rejection restarts instead of surfacing;
- budget exhaustion keeps the conversation lane's fail-open defer (indexed
  obligation intact, ``outcome=deferred`` telemetry) after the full budget,
  and raises the typed exhaustion in the generation lane;
- a real (non-contention) failure is never retried into a delay;
- clean-path retirement decisions are byte-identical under replay.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

import pytest
from google.api_core.exceptions import Aborted, InvalidArgument
from prometheus_client import REGISTRY

from database import quiet_check_retirement as retirement
from database.firestore_transaction_retry import (
    DEFAULT_MAX_ATTEMPTS,
    FirestoreContentionExhausted,
    is_transaction_contention,
    run_with_transaction_contention_retry as _REAL_BUDGET,
)

UID = 'synthetic'
CID = 'capture'
NOW_STAMP = '2026-11-12T00:00:00+00:00'


def _job_path() -> tuple[str, ...]:
    return ('conversation_finalization_jobs', retirement.quiet_check_id(UID, CID))


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
    firestore: '_RetirementFirestore'
    path: tuple[str, ...]

    def get(self, transaction: object = None) -> _Snapshot:
        del transaction  # the fixture's transactional reads are order-free; StrictFirestore covers ordering
        return _Snapshot(self.firestore.documents.get(self.path))

    def collection(self, name: str) -> '_CollectionRef':
        return _CollectionRef(self.firestore, self.path + (name,))


@dataclass
class _CollectionRef:
    firestore: '_RetirementFirestore'
    path: tuple[str, ...]

    def document(self, document_id: str) -> _DocumentRef:
        return _DocumentRef(self.firestore, self.path + (document_id,))


@dataclass
class _Transaction:
    firestore: '_RetirementFirestore'

    def update(self, document: _DocumentRef, updates: dict[str, Any]) -> None:
        self.firestore.writes.append((self.firestore.attempt_index, document.path, copy.deepcopy(updates)))
        self.firestore.documents.setdefault(document.path, {}).update(copy.deepcopy(updates))


@dataclass
class _RetirementFirestore:
    """Fake Firestore whose decorated transactional bodies abort until the queue empties.

    Mirrors the production hole the SDK cannot model in a unit fake: the abort
    fires from the decorated body's read, before any write — the exact shape
    ``run_with_transaction_contention_retry`` exists to replay on fresh
    transactions.
    """

    documents: dict[tuple[str, ...], dict[str, Any]] = field(default_factory=dict)
    read_errors: list[BaseException] = field(default_factory=list)
    writes: list[tuple[int, tuple[str, ...], dict[str, Any]]] = field(default_factory=list)
    transactions: list[_Transaction] = field(default_factory=list)
    commits: list[_Transaction] = field(default_factory=list)
    attempt_index: int = 0
    sleeps: list[float] = field(default_factory=list)
    budget_calls: list[dict[str, Any]] = field(default_factory=list)

    def collection(self, name: str) -> _CollectionRef:
        return _CollectionRef(self, (name,))

    def transaction(self) -> _Transaction:
        transaction = _Transaction(self)
        self.transactions.append(transaction)
        return transaction

    def seed_job(self, **overrides: Any) -> tuple[str, ...]:
        path = _job_path()
        self.documents[path] = {
            'kind': 'listen_quiet_check',
            'status': 'waiting_quiet',
            'dispatch_generation': 7,
            'reconcile_after_at': NOW_STAMP,
            'due_at': NOW_STAMP,
            **overrides,
        }
        return path

    def seed_row(self, **overrides: Any) -> tuple[str, ...]:
        path = ('users', UID, 'conversations', CID)
        self.documents[path] = {'status': 'processing', **overrides}
        return path


@pytest.fixture
def store(monkeypatch):
    repo = _RetirementFirestore()

    def transactional(func):
        def locked(transaction, *args, **kwargs):
            repo.attempt_index += 1
            if repo.read_errors:
                raise repo.read_errors.pop(0)
            result = func(transaction, *args, **kwargs)
            repo.commits.append(transaction)
            return result

        return locked

    monkeypatch.setattr(retirement.firestore, 'transactional', transactional)

    def budget_retry(*args, **kwargs):
        repo.budget_calls.append({'operation_name': kwargs.get('operation_name')})
        kwargs.setdefault('sleep', repo.sleeps.append)
        kwargs.setdefault('random_value', lambda: 0.5)
        return _REAL_BUDGET(*args, **kwargs)

    monkeypatch.setattr(retirement, 'run_with_transaction_contention_retry', budget_retry)
    return repo


def _seed_retirable(store: _RetirementFirestore) -> tuple[str, ...]:
    store.seed_job()
    store.seed_row(status='processing')
    return _job_path()


def test_conversation_lane_replays_read_abort_on_fresh_transactions_and_commits_once(store):
    path = _seed_retirable(store)
    store.read_errors = [Aborted('contention'), Aborted('contention')]

    assert retirement.stop_quiet_check_for_conversation(UID, CID, firestore_client=store) is True

    assert store.documents[path]['status'] == 'quiet_done'
    assert len(store.commits) == 1
    assert len(store.transactions) == 3
    assert len(store.sleeps) == 2


def test_conversation_lane_restarts_on_expired_transaction_id(store):
    path = _seed_retirable(store)
    store.read_errors = [InvalidArgument('The referenced transaction has expired or is no longer valid')]

    assert retirement.stop_quiet_check_for_conversation(UID, CID, firestore_client=store) is True

    assert store.documents[path]['status'] == 'quiet_done'
    assert len(store.transactions) == 2


def test_conversation_lane_exhaustion_defers_after_the_full_budget(store, caplog):
    path = _seed_retirable(store)
    store.read_errors = [Aborted('contention')] * 50

    assert retirement.stop_quiet_check_for_conversation(UID, CID, firestore_client=store) is False

    assert store.documents[path]['status'] == 'waiting_quiet'
    assert len(store.transactions) == DEFAULT_MAX_ATTEMPTS
    assert len(store.sleeps) == DEFAULT_MAX_ATTEMPTS - 1
    assert 'event=quiet_check_retirement outcome=deferred operation=stop_quiet_check_for_conversation' in caplog.text


def test_conversation_lane_exhaustion_records_the_durable_backstop_fallback(store):
    _seed_retirable(store)
    store.read_errors = [Aborted('contention')] * 50
    metric = REGISTRY.get_sample_value(
        'omi_fallback_total',
        {
            'component': 'conversation_finalization',
            'from_mode': 'inline',
            'to_mode': 'durable_queued',
            'reason': 'unavailable',
            'outcome': 'degraded',
        },
    )
    before = metric or 0.0

    assert retirement.stop_quiet_check_for_conversation(UID, CID, firestore_client=store) is False

    assert (
        REGISTRY.get_sample_value(
            'omi_fallback_total',
            {
                'component': 'conversation_finalization',
                'from_mode': 'inline',
                'to_mode': 'durable_queued',
                'reason': 'unavailable',
                'outcome': 'degraded',
            },
        )
        or 0.0
    ) == before + 1


def test_conversation_lane_real_failure_is_never_retried_into_a_delay(store, caplog):
    path = _seed_retirable(store)
    store.read_errors = [RuntimeError('real dependency failure')]

    assert retirement.stop_quiet_check_for_conversation(UID, CID, firestore_client=store) is False

    assert len(store.transactions) == 1
    assert store.sleeps == []
    assert 'event=quiet_check_retirement outcome=deferred' in caplog.text
    assert store.documents[path]['status'] == 'waiting_quiet'


def test_conversation_lane_abort_then_real_failure_burns_exactly_one_rung(store):
    _seed_retirable(store)
    store.read_errors = [Aborted('contention'), RuntimeError('real dependency failure')]

    assert retirement.stop_quiet_check_for_conversation(UID, CID, firestore_client=store) is False

    assert len(store.transactions) == 2
    assert len(store.sleeps) == 1


def test_generation_lane_replays_read_abort_and_retires_its_own_generation(store):
    path = _seed_retirable(store)
    store.read_errors = [Aborted('contention'), Aborted('contention')]

    retirement.stop_quiet_check(path[-1], 7, firestore_client=store)

    assert store.documents[path]['status'] == 'quiet_done'
    assert len(store.commits) == 1
    assert len(store.transactions) == 3


def test_generation_lane_exhaustion_raises_the_typed_contention_error(store):
    path = _seed_retirable(store)
    store.read_errors = [Aborted('contention')] * 50

    with pytest.raises(FirestoreContentionExhausted):
        retirement.stop_quiet_check(path[-1], 7, firestore_client=store)

    assert store.documents[path]['status'] == 'waiting_quiet'
    assert len(store.transactions) == DEFAULT_MAX_ATTEMPTS


def test_generation_lane_real_failure_keeps_raising_the_dependency_error(store):
    path = _seed_retirable(store)
    store.read_errors = [RuntimeError('real dependency failure')]

    with pytest.raises(RuntimeError, match='real dependency failure'):
        retirement.stop_quiet_check(path[-1], 7, firestore_client=store)

    assert store.sleeps == []
    assert len(store.transactions) == 1
    assert store.documents[path]['status'] == 'waiting_quiet'


def test_generation_lane_expired_transaction_id_restarts(store):
    path = _seed_retirable(store)
    store.read_errors = [InvalidArgument('The referenced transaction has expired or is no longer valid')]

    retirement.stop_quiet_check(path[-1], 7, firestore_client=store)

    assert store.documents[path]['status'] == 'quiet_done'
    assert len(store.transactions) == 2


def test_both_lanes_name_their_own_budget_operation(store):
    path = _seed_retirable(store)
    store.read_errors = [Aborted('contention')]

    retirement.stop_quiet_check_for_conversation(UID, CID, firestore_client=store)
    retirement.stop_quiet_check(path[-1], 7, firestore_client=store)

    assert store.budget_calls[0]['operation_name'] == 'quiet_check_retirement'
    assert store.budget_calls[1]['operation_name'] == 'quiet_check_generation_stop'


def test_deadline_scoped_budget_refuses_the_second_rung_when_the_reserve_does_not_fit(store, monkeypatch):
    """A 5s deadline after a 1s first attempt cannot cover the 30s reserve floor."""
    from database.firestore_transaction_retry import transaction_retry_deadline_scope

    path = _seed_retirable(store)
    store.read_errors = [Aborted('contention')] * 50

    clock = {'now': 0.0}

    def monotonic() -> float:
        return clock['now']

    def budget_retry(*args, **kwargs):
        kwargs.setdefault('sleep', lambda delay: clock.__setitem__('now', clock['now'] + delay))
        kwargs.setdefault('random_value', lambda: 0.5)
        kwargs.setdefault('monotonic', monotonic)
        return _REAL_BUDGET(*args, **kwargs)

    monkeypatch.setattr(retirement, 'run_with_transaction_contention_retry', budget_retry)
    with transaction_retry_deadline_scope(5.0):
        assert retirement.stop_quiet_check_for_conversation(UID, CID, firestore_client=store) is False

    assert len(store.transactions) == 1
    assert store.sleeps == []
    assert store.documents[path]['status'] == 'waiting_quiet'


def test_contention_classifier_covers_the_exhaustion_error():
    error = FirestoreContentionExhausted('exhausted')
    assert is_transaction_contention(error) is False


def test_clean_path_retirement_decisions_are_unchanged_under_replay(store):
    """An abort followed by a clean replay lands on the same decision as no contention."""
    store.seed_job()
    store.seed_row(status='in_progress')

    assert retirement.stop_quiet_check_for_conversation(UID, CID, firestore_client=store) is False

    path = _job_path()
    assert store.documents[path]['status'] == 'waiting_quiet'

    store.seed_row(status='processing')
    store.read_errors = [Aborted('contention')]
    assert retirement.stop_quiet_check_for_conversation(UID, CID, firestore_client=store) is True
    assert store.documents[path]['status'] == 'quiet_done'


def test_quiet_done_clean_job_stays_a_no_op_under_replay(store):
    path = _seed_retirable(store)
    store.documents[path].update({'status': 'quiet_done'})
    store.documents[path].pop('reconcile_after_at', None)
    store.read_errors = [Aborted('contention')]

    assert retirement.stop_quiet_check_for_conversation(UID, CID, firestore_client=store) is False

    assert len(store.writes) == 0
    assert len(store.transactions) == 2
