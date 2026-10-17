"""Exercise sync's real SDK decorator at the read-versus-commit retry boundary.

The SDK-surface fake stages writes until commit; StrictFirestore intentionally
cannot model aborts or SDK retry. Shared-document contention is qualified in dev.
"""

from functools import partial

import pytest
from google.api_core.exceptions import Aborted, InvalidArgument, ServiceUnavailable

import database.firestore_transaction_retry as firestore_transaction_retry
from database import conversations as conversations_db
from database.firestore_transaction_retry import (
    FirestoreContentionExhausted,
    run_with_transaction_contention_retry,
)
from tests.unit.test_conversation_persistence_transaction_expiry import _FakeFirestoreClient
from tests.unit.test_sync_cross_job_assignment import chunk
from utils.sync import assignment


@pytest.fixture
def sdk_assignment(monkeypatch):
    monkeypatch.setattr(conversations_db, '_sync_conversation_search_index', lambda *args: None)
    monkeypatch.setattr(conversations_db, 'invalidate_people_stats_cache', lambda *args: None)
    # The retry runner now lives in database.sync_assignment.run_sync_assignment,
    # which resolves run_with_transaction_contention_retry from its source module
    # at call time; patch that module so the seam keeps controlling production.
    monkeypatch.setattr(
        firestore_transaction_retry,
        'run_with_transaction_contention_retry',
        partial(run_with_transaction_contention_retry, sleep=lambda _: None, random_value=lambda: 0),
    )
    monkeypatch.delenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', raising=False)

    def build(*, read_errors=(), commit_errors=()):
        store = _FakeFirestoreClient(None, list(commit_errors))
        errors = list(read_errors)
        read_transactions = []
        original_get = store.doc_ref.get

        def read(transaction=None):
            if transaction is None:
                return original_get(transaction=transaction)
            read_transactions.append(transaction)
            if errors:
                error = errors.pop(0)
                if error is not None:
                    raise error
            return original_get(transaction=transaction)

        monkeypatch.setattr(store.doc_ref, 'get', read)

        def body(transaction, user_ref, incoming, **kwargs):
            # Raise from a real decorated transaction's body, before any write.
            store.doc_ref.get(transaction=transaction)
            transaction.set(store.doc_ref, incoming)
            return incoming, True, incoming['transcript_segments']

        monkeypatch.setattr(assignment, 'assign_in_transaction', body)
        return store, read_transactions

    return build


def persist(store):
    return conversations_db.assign_sync_conversation('synthetic-unit', chunk('canonical', 1000), firestore_client=store)


@pytest.mark.parametrize('flag', [None, 'false'])
def test_default_off_retains_read_abort_without_replay(sdk_assignment, monkeypatch, flag):
    if flag is not None:
        monkeypatch.setenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', flag)
    store, reads = sdk_assignment(read_errors=[Aborted('contention')])
    with pytest.raises(Aborted):
        persist(store)
    assert len(store.transactions) == len(reads) == 1
    assert store.commits == []


def test_enabled_read_abort_uses_fresh_transaction_and_commits_once(sdk_assignment, monkeypatch):
    monkeypatch.setenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', 'true')
    store, reads = sdk_assignment(read_errors=[Aborted('contention')])
    result, created, _ = persist(store)
    assert created and result['id'] == 'canonical'
    assert len(store.transactions) == 2
    assert reads == store.transactions
    assert store.transactions[0].rolled_back
    assert len(store.commits) == 1
    assert len(store.commits[0]['transcript_segments']) == 1


def test_enabled_read_abort_has_finite_outer_budget(sdk_assignment, monkeypatch):
    monkeypatch.setenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', 'true')
    store, reads = sdk_assignment(read_errors=[Aborted('contention') for _ in range(5)])
    with pytest.raises(FirestoreContentionExhausted):
        persist(store)
    assert len(store.transactions) == len(reads) == 5
    assert store.commits == []


def test_commit_abort_keeps_sdk_retry_and_single_durable_write(sdk_assignment, monkeypatch):
    monkeypatch.setenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', 'true')
    store, reads = sdk_assignment(commit_errors=[Aborted('commit contention')])
    persist(store)
    assert len(store.transactions) == 1
    assert len(reads) == 2
    assert len(store.commits) == 1


def test_sdk_exhaustion_cause_is_bounded_by_outer_budget(sdk_assignment, monkeypatch):
    monkeypatch.setenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', 'true')
    store, reads = sdk_assignment(commit_errors=[Aborted('commit contention') for _ in range(25)])
    with pytest.raises(FirestoreContentionExhausted):
        persist(store)
    assert len(store.transactions) == 5
    assert len(reads) == 25
    assert store.commits == []


def test_expiry_restarts_still_work_inside_outer_contention_retry(sdk_assignment, monkeypatch):
    monkeypatch.setenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', 'true')
    store, reads = sdk_assignment(
        read_errors=[None, Aborted('contention')],
        commit_errors=[InvalidArgument('The referenced transaction has expired or is no longer valid.')],
    )
    persist(store)
    assert len(store.transactions) == 3
    assert reads == store.transactions
    assert len(store.commits) == 1


@pytest.mark.parametrize('error', [InvalidArgument('bad payload'), ServiceUnavailable('ambiguous transport failure')])
def test_non_contention_errors_are_not_replayed(sdk_assignment, monkeypatch, error):
    monkeypatch.setenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', 'true')
    store, reads = sdk_assignment(read_errors=[error])
    with pytest.raises(type(error)):
        persist(store)
    assert len(store.transactions) == len(reads) == 1
    assert store.commits == []


def test_batch_opt_in_retries_without_enabling_legacy_assignment(sdk_assignment):
    store, reads = sdk_assignment(read_errors=[Aborted('synthetic contention')])
    result, created, _ = conversations_db.assign_sync_conversation(
        'synthetic-unit', chunk('canonical', 1000), firestore_client=store, retry_contention=True
    )
    assert created and result['id'] == 'canonical'
    assert len(store.transactions) == len(reads) == 2
    assert len(store.commits) == 1
