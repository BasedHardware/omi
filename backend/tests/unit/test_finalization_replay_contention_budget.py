"""The finalization replay sweep's cursor advance and backoff ride the shared budget.

The sweep's five sibling writers (BYOK reclaim, in-progress content, stale
processing, meeting-receipt, BYOK abandonment cursor advances and every custody
writer) ride ``run_with_transaction_contention_retry``; the replay cursor CAS
advance and ``defer_finalization_replay`` ran the decorated transaction bare, so
one transient read abort escaped as a raw SDK error: the cursor advance aborted
the whole reconcile pass (the sweep lost its page position and rescanned the
window on the next pass) and the quiet backoff never landed (the hot head stayed
at the window front and was re-claimed by the very next sweep). These tests pin
the budgeted behavior: a replayable abort replays on a fresh transaction, the
chain cap surfaces as the typed exhaustion the callers already catch, and a
non-contention failure still propagates unretried.

Failure-Class: FC-replay-sweep-cursor-and-backoff-run-outside-the-shared-contention-budget
"""

from datetime import datetime, timedelta, timezone

import pytest
from google.api_core.exceptions import Aborted

from database import conversation_finalization_jobs as jobs
from database import firestore_transaction_retry
from database.firestore_transaction_retry import (
    FirestoreContentionExhausted,
    run_with_transaction_contention_retry as _REAL_BUDGET,
)
from services import conversation_finalization as service
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

NOW = datetime(2026, 11, 12, tzinfo=timezone.utc)
OVERDUE = NOW - timedelta(hours=1)


def _abort():
    return Aborted('409 replay sweep contention')


def _aborts(count):
    return [_abort] * count


def _fail():
    return RuntimeError('synthetic replay sweep dependency failure')


CANDIDATE = {
    'job_id': 'quiet-000',
    'kind': 'listen_quiet_check',
    'status': 'waiting_quiet',
    'dispatch_generation': 1,
    'reconcile_after_at': OVERDUE,
}


class _FaultedTransactional:
    """Patches ``jobs.firestore`` so each transactional body call may raise once."""

    def __init__(self, faults):
        self._real = jobs.firestore
        self._faults = list(faults)

    def _transactional(self, func):
        def locked(transaction, *args, **kwargs):
            if self._faults:
                raise self._faults.pop(0)()
            return func(transaction, *args, **kwargs)

        return locked

    def __getattr__(self, name):
        if name == 'transactional':
            return self._transactional
        return getattr(self._real, name)


class _BudgetProbe:
    """Wraps the real budget engine with recorded sleeps and a pinned jitter draw."""

    def __init__(self):
        self.sleeps = []
        self.calls = []

    def __call__(self, transaction_factory, operation, **kwargs):
        self.calls.append(kwargs.get('operation_name'))

        def record_sleep(delay):
            self.sleeps.append(delay)

        kwargs.setdefault('sleep', record_sleep)
        kwargs.setdefault('random_value', lambda: 0.5)
        return _REAL_BUDGET(transaction_factory, operation, **kwargs)


class _DueQuery:
    """Narrow query seam for the replay page (real-store ordering is emulator-qualified)."""

    def __init__(self, store):
        self.store = store
        self.after = None
        self.bound = 100
        self.orders = []
        self.cutoff = None

    def where(self, field, op, cutoff):
        assert (field, op) == ('reconcile_after_at', '<=')
        self.cutoff = cutoff
        return self

    def order_by(self, field):
        assert field in {'reconcile_after_at', '__name__'}
        self.orders.append(field)
        return self

    def start_after(self, cursor):
        assert self.orders == ['reconcile_after_at', '__name__']
        self.after = (cursor['reconcile_after_at'], cursor['__name__'].id)
        return self

    def limit(self, bound):
        self.bound = bound
        return self

    def stream(self):
        from types import SimpleNamespace

        ordered = sorted(
            (row['reconcile_after_at'], path[-1], row)
            for path, row in self.store.rows.items()
            if path[0] == jobs.FINALIZATION_JOBS_COLLECTION
            and isinstance(row.get('reconcile_after_at'), datetime)
            and row['reconcile_after_at'] <= self.cutoff
        )
        rows = [entry for entry in ordered if self.after is None or entry[:2] > self.after]
        return iter(SimpleNamespace(id=key, to_dict=lambda row=dict(row): row) for _, key, row in rows[: self.bound])


class _ReplayStore(StrictFirestore):
    def collection(self, name):
        col = super().collection(name)
        if name != jobs.FINALIZATION_JOBS_COLLECTION:
            return col
        from types import SimpleNamespace

        return SimpleNamespace(document=col.document, where=lambda *args: _DueQuery(self).where(*args))


def _seed(row_overrides=None, *, page_rows=3):
    rows = {
        ('conversation_recovery_state', 'finalization_replay'): {'generation': 7, 'cursor': None},
    }
    for index in range(page_rows):
        rows[(jobs.FINALIZATION_JOBS_COLLECTION, f'quiet-{index:03}')] = {
            'kind': 'listen_quiet_check',
            'status': 'waiting_quiet',
            'dispatch_generation': 1,
            'reconcile_after_at': OVERDUE,
            'due_at': OVERDUE,
        }
    if row_overrides is not None:
        rows[(jobs.FINALIZATION_JOBS_COLLECTION, 'quiet-000')] = row_overrides
    return _ReplayStore(rows)


@pytest.fixture()
def budget(monkeypatch):
    probe = _BudgetProbe()
    # The joined lane imports the engine at call time from the retry module.
    monkeypatch.setattr(firestore_transaction_retry, 'run_with_transaction_contention_retry', probe)
    return probe


def _fault(monkeypatch, faults):
    monkeypatch.setattr(jobs, 'firestore', _FaultedTransactional(faults))


def _defer_drive(monkeypatch, budget, faults, candidate=None, row_overrides=None):
    store = _seed(row_overrides)
    monkeypatch.setattr(jobs, '_now', lambda: NOW)
    _fault(monkeypatch, faults)
    return store, jobs.defer_finalization_replay(candidate or CANDIDATE, firestore_client=store)


def test_defer_replays_single_read_abort_on_fresh_transaction(monkeypatch, budget):
    store, result = _defer_drive(monkeypatch, budget, _aborts(1), None)
    assert result is True
    assert budget.sleeps == pytest.approx([0.15])
    row = store.rows[(jobs.FINALIZATION_JOBS_COLLECTION, 'quiet-000')]
    assert row['reconcile_after_at'] == NOW + timedelta(seconds=60)


def test_defer_exhaustion_is_typed_not_raw(monkeypatch, budget):
    with pytest.raises(FirestoreContentionExhausted) as exhausted:
        _defer_drive(monkeypatch, budget, _aborts(5), None)
    assert exhausted.value.reason == 'attempts_exhausted'
    assert budget.sleeps == pytest.approx([0.15, 0.3, 0.6, 1.2])


def test_defer_never_replays_noncontention_failure(monkeypatch, budget):
    with pytest.raises(RuntimeError):
        _defer_drive(monkeypatch, budget, [_fail], None)
    assert budget.sleeps == []
    assert len(budget.calls) == 1


def test_defer_mismatched_backoff_is_single_attempt(monkeypatch, budget):
    store, result = _defer_drive(
        monkeypatch, budget, [], candidate=dict(CANDIDATE, reconcile_after_at=NOW - timedelta(hours=2))
    )
    assert result is False
    assert budget.sleeps == []
    assert len(store.transactions) == 1
    row = store.rows[(jobs.FINALIZATION_JOBS_COLLECTION, 'quiet-000')]
    assert row['reconcile_after_at'] == OVERDUE


def test_defer_budget_engages_on_terminal_delete_shape(monkeypatch, budget):
    store, result = _defer_drive(
        monkeypatch,
        budget,
        [],
        candidate=dict(CANDIDATE, status='completed'),
        row_overrides=dict(CANDIDATE, kind='listen_finalization', status='completed'),
    )
    assert result is True
    assert len(budget.calls) == 1
    row = store.rows[(jobs.FINALIZATION_JOBS_COLLECTION, 'quiet-000')]
    assert row['reconcile_after_at'] is jobs.firestore.DELETE_FIELD


def _candidates_drive(monkeypatch, budget, faults, *, limit=3):
    store = _seed(page_rows=limit)
    monkeypatch.setattr(jobs, '_now', lambda: NOW)
    _fault(monkeypatch, faults)
    page = jobs.get_finalization_replay_candidates(limit=limit, firestore_client=store)
    return store, page


def test_cursor_advance_replays_single_read_abort(monkeypatch, budget):
    store, page = _candidates_drive(monkeypatch, budget, _aborts(1))
    assert [job['job_id'] for job in page] == ['quiet-000', 'quiet-001', 'quiet-002']
    assert budget.sleeps == pytest.approx([0.15])
    state = store.rows[('conversation_recovery_state', 'finalization_replay')]
    assert state['generation'] == 8
    assert state['cursor']['job_id'] == 'quiet-002'


def test_cursor_advance_exhaustion_is_typed_not_raw(monkeypatch, budget):
    with pytest.raises(FirestoreContentionExhausted) as exhausted:
        _candidates_drive(monkeypatch, budget, _aborts(5))
    assert exhausted.value.reason == 'attempts_exhausted'
    assert budget.sleeps == pytest.approx([0.15, 0.3, 0.6, 1.2])


def test_cursor_advance_never_replays_noncontention_failure(monkeypatch, budget):
    with pytest.raises(RuntimeError):
        _candidates_drive(monkeypatch, budget, [_fail])
    assert budget.sleeps == []
    assert len(budget.calls) == 1


def test_sweep_pass_survives_transient_cursor_abort(monkeypatch, budget):
    store = _seed(page_rows=2)
    monkeypatch.setattr(jobs, '_now', lambda: NOW)
    monkeypatch.setattr(jobs, 'recover_stranded_byok_jobs', lambda **kwargs: {'blocked': 0, 'errors': 0})
    monkeypatch.setattr(service, 'is_listen_finalization_dispatch_enabled', lambda: False)
    monkeypatch.setattr(service, 'is_listen_finalization_tasks_configured', lambda: True)
    monkeypatch.setattr(service, '_publish_job_metrics', lambda *args, **kwargs: None)
    monkeypatch.setattr(service, 'replay_enabled', lambda: True)
    _fault(monkeypatch, _aborts(1))
    result = service.reconcile_listen_finalization_jobs(limit=2, firestore_client=store)
    assert result['error'] == 0
    assert result['skipped'] == 2
    state = store.rows[('conversation_recovery_state', 'finalization_replay')]
    assert state['generation'] == 8


def test_quiet_backoff_lands_after_transient_abort(monkeypatch, budget):
    store = _seed()
    monkeypatch.setattr(jobs, '_now', lambda: NOW)
    monkeypatch.setattr(service.quiet_finalization, 'run', lambda *args, **kwargs: 'stale')
    _fault(monkeypatch, _aborts(1))
    outcome = service._reconcile_quiet_candidate(CANDIDATE, firestore_client=store)
    assert outcome == 'stale'
    row = store.rows[(jobs.FINALIZATION_JOBS_COLLECTION, 'quiet-000')]
    assert row['reconcile_after_at'] == NOW + timedelta(seconds=60)
    assert len(budget.calls) == 1
