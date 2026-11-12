"""Firestore contention surfaces in the batch projection path (run 23, 2026-10-21).

The sweep logged ``exception_type=ValueError``: google-cloud-firestore's
``@transactional`` wraps its last commit ``Aborted`` in ``ValueError``. The
retention phase logged ``InvalidArgument``: its bare transaction never restarted
an expired transaction. Both are reproduced here with the real SDK wrapper.
"""

from unittest.mock import Mock

from google.api_core.exceptions import Aborted, InvalidArgument
from google.cloud.firestore_v1.transaction import _Transactional
import pytest

from database import batch_pipeline_store
from database import firestore_transaction_retry
from utils.batch_pipeline import retention
from utils.batch_pipeline.projection import error_site_field, error_type

EXPIRED = 'The referenced transaction has expired or is no longer valid.'


class AlwaysAbortedTransaction:
    """Just enough of firestore_v1.Transaction for _Transactional: every commit aborts."""

    _max_attempts = 5
    _read_only = False

    def __init__(self):
        self._id = None
        self.commits = 0

    def _clean_up(self):
        self._id = None

    def _begin(self, retry_id=None):
        self._id = b'synthetic'

    def _commit(self):
        self.commits += 1
        raise Aborted('synthetic commit contention')

    def _rollback(self):
        self._id = None


def sdk_commit_exhausted() -> ValueError:
    transaction = AlwaysAbortedTransaction()
    with pytest.raises(ValueError) as caught:
        _Transactional(lambda tx: None)(transaction)
    assert transaction.commits == 5
    return caught.value


def test_sdk_commit_exhaustion_is_the_valueerror_from_aborted():
    error = sdk_commit_exhausted()
    assert 'Failed to commit transaction' in str(error)
    assert isinstance(error.__cause__, Aborted)


def test_sdk_commit_exhaustion_logs_as_contention_exhausted():
    assert error_type(sdk_commit_exhausted()) == 'FirestoreContentionExhausted'


@pytest.mark.parametrize(
    'error,name',
    [
        (ValueError('completion owner mismatch'), 'ValueError'),
        (Aborted('read contention'), 'Aborted'),
        (InvalidArgument(EXPIRED), 'InvalidArgument'),
    ],
)
def test_other_errors_keep_their_class(error, name):
    assert error_type(error) == name


def test_valueerror_chained_from_non_contention_keeps_its_class():
    try:
        try:
            raise KeyError('x')
        except KeyError as inner:
            raise ValueError('app') from inner
    except ValueError as error:
        assert error_type(error) == 'ValueError'


def test_error_site_names_innermost_backend_frame_without_payload():
    def fails():
        raise ValueError('secret-payload-never-logged')

    try:
        fails()
    except ValueError as error:
        site = error_site_field(error)
    assert site.startswith(' site=test_batch_pipeline_contention_errors.py:')
    assert 'secret' not in site
    assert error_site_field(ValueError('never raised')) == ''


@pytest.fixture
def no_sleep(monkeypatch):
    actual = firestore_transaction_retry.run_with_transaction_contention_retry

    def fast(*args, **kwargs):
        return actual(*args, **kwargs, sleep=lambda _: None)

    monkeypatch.setattr(firestore_transaction_retry, 'run_with_transaction_contention_retry', fast)


@pytest.mark.parametrize(
    'first',
    [
        InvalidArgument(EXPIRED),  # expired transaction on commit (run 23's retention error)
        Aborted('read-time contention'),
        'sdk_exhausted',  # the SDK's ValueError wrapper
    ],
)
def test_retention_transaction_retries_on_a_fresh_transaction(no_sleep, first):
    if first == 'sdk_exhausted':
        first = sdk_commit_exhausted()
    client = Mock()
    client.transaction.side_effect = [object(), object(), object()]
    operation = Mock(side_effect=[first, True])
    assert retention.run_retention_transaction(client, operation) is True
    assert operation.call_count == 2
    assert operation.call_args_list[0].args[0] is not operation.call_args_list[1].args[0]


@pytest.mark.parametrize('error', [ValueError('completion owner mismatch'), InvalidArgument('not expiry')])
def test_retention_transaction_never_replays_other_errors(no_sleep, error):
    client = Mock()
    operation = Mock(side_effect=error)
    with pytest.raises(type(error)):
        retention.run_retention_transaction(client, operation)
    assert operation.call_count == 1


def test_app_valueerror_from_aborted_keeps_its_class():
    try:
        try:
            raise Aborted('contention')
        except Aborted as inner:
            raise ValueError('dream_gate_contention') from inner
    except ValueError as error:
        assert error_type(error) == 'ValueError'


def test_retention_commit_contention_budget_is_five_bodies_not_twenty_five(no_sleep):
    """Real @firestore.transactional body; every commit aborts."""
    from google.cloud import firestore

    transactions = []

    def transaction(max_attempts=5):
        tx = AlwaysAbortedTransaction()
        tx._max_attempts = max_attempts
        transactions.append(tx)
        return tx

    client = Mock()
    client.transaction.side_effect = transaction
    bodies = []

    @firestore.transactional
    def body(tx):
        bodies.append(tx)
        return True

    with pytest.raises(firestore_transaction_retry.FirestoreContentionExhausted):
        retention.run_retention_transaction(client, body)
    assert len(transactions) == 5
    assert sum(tx.commits for tx in transactions) == 5
    assert len(bodies) == 5


def test_expire_completed_segment_runs_through_the_bounded_retry(monkeypatch):
    calls = []

    def run(client, operation):
        calls.append(client)
        return 'ran'

    monkeypatch.setattr(retention, 'run_retention_transaction', run)
    store = Mock(namespace='batch_pipeline_test_contention')
    assert retention.expire_completed_segment(store, 'synthetic-owner', 'segment', 0.0) == 'ran'
    assert calls == [store.client]


class SuccessfulTransaction(AlwaysAbortedTransaction):
    def _commit(self):
        self.commits += 1
        return []


def test_batch_store_retries_with_fresh_single_attempt_transactions(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_CONTENTION_RETRY_ENABLED', raising=False)
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    actual = batch_pipeline_store.run_with_transaction_contention_retry
    monkeypatch.setattr(
        batch_pipeline_store,
        'run_with_transaction_contention_retry',
        lambda *args, **kwargs: actual(*args, **kwargs, sleep=lambda _: None),
    )
    transactions = []

    def new_transaction(max_attempts=5):
        transaction = AlwaysAbortedTransaction() if not transactions else SuccessfulTransaction()
        transaction._max_attempts = max_attempts
        transactions.append(transaction)
        return transaction

    client = Mock()
    client.transaction.side_effect = new_transaction
    store = batch_pipeline_store.FirestoreStore('batch_pipeline_dev', firestore_client=client)
    body_calls = []

    assert store.run(lambda tx: body_calls.append(tx) or True) is True
    assert len(body_calls) == 2
    assert [tx._max_attempts for tx in transactions] == [1, 1]
    assert [tx.commits for tx in transactions] == [1, 1]


def test_batch_store_kill_switch_restores_single_legacy_attempt(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_RETRY_ENABLED', 'false')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    client = Mock()
    transaction = AlwaysAbortedTransaction()
    client.transaction.return_value = transaction
    store = batch_pipeline_store.FirestoreStore('batch_pipeline_dev', firestore_client=client)

    with pytest.raises(ValueError) as caught:
        store.run(lambda _tx: True)

    assert isinstance(caught.value.__cause__, Aborted)
    client.transaction.assert_called_once_with()
    assert transaction.commits == 5


def test_exhausted_batch_store_contention_names_the_tables_never_the_keys(monkeypatch, caplog):
    # The admission drain logged only "FirestoreContentionExhausted": nothing said which
    # shared document (owner scheduler row, conversation, ledger) kept aborting the commit.
    monkeypatch.delenv('BATCH_PIPELINE_CONTENTION_RETRY_ENABLED', raising=False)
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    actual = batch_pipeline_store.run_with_transaction_contention_retry
    monkeypatch.setattr(
        batch_pipeline_store,
        'run_with_transaction_contention_retry',
        lambda *args, **kwargs: actual(*args, **kwargs, sleep=lambda _: None),
    )
    monkeypatch.setattr(batch_pipeline_store.FirestoreTransaction, 'flush', lambda self: None)

    def new_transaction(max_attempts=5):
        transaction = AlwaysAbortedTransaction()
        transaction._max_attempts = max_attempts
        return transaction

    client = Mock()
    client.transaction.side_effect = new_transaction
    store = batch_pipeline_store.FirestoreStore('batch_pipeline_dev', firestore_client=client)

    def body(tx):
        tx.cache[('owners', 'owner-secret')] = {}
        tx.cache[('conversations', 'uid-secret/conv-secret')] = {}
        tx.writes[('jobs', 'segment-secret')] = {}
        tx.patches[('conversations', 'uid-secret/conv-secret')] = {}
        # A scheduler query reads through the raw transaction, never the cache.
        tx.direct_reads.add('jobs_query')
        return True

    with caplog.at_level('WARNING', logger=batch_pipeline_store.logger.name):
        with pytest.raises(firestore_transaction_retry.FirestoreContentionExhausted) as caught:
            store.run(body)

    assert caught.value.store_tables == 'read=conversations,jobs_query,owners wrote=conversations,jobs,privacy_fence'
    line = next(r.getMessage() for r in caplog.records if 'event=batch_store_contention' in r.getMessage())
    assert 'read_tables=conversations,jobs_query,owners' in line
    assert 'write_tables=conversations,jobs,privacy_fence' in line
    assert 'secret' not in line and 'secret' not in caught.value.store_tables


def test_contention_tables_reports_none_and_external_writes_sorted():
    view = batch_pipeline_store.FirestoreTransaction(Mock(), 'batch_pipeline_dev', Mock())
    assert batch_pipeline_store.contention_tables(view) == ('none', 'none')
    view.external[object()] = (object(), {})
    view.writes[('jobs', 'segment')] = {}
    assert batch_pipeline_store.contention_tables(view) == ('none', 'external,jobs')


def test_direct_transaction_reads_are_named(monkeypatch):
    # Queries and privacy checks read through the raw transaction, not the view cache.
    monkeypatch.setattr(batch_pipeline_store, 'first_pending', lambda *a, **k: None)
    monkeypatch.setattr(batch_pipeline_store, 'service_frontier', lambda *a, **k: 0.0)
    monkeypatch.setattr(batch_pipeline_store, 'assert_batch_write_allowed', lambda *a, **k: 1)
    view = batch_pipeline_store.FirestoreTransaction(Mock(), 'batch_pipeline_dev', Mock())
    batch_pipeline_store._note_direct_reads(view)
    assert batch_pipeline_store.contention_tables(view) == ('none', 'none')
    view.first_pending('owner')
    view.service_frontier(0)
    view.check_privacy('uid')
    # Default: the frontier is a hint read outside the transaction, so it is not a contended read.
    assert batch_pipeline_store.contention_tables(view) == ('jobs_query,privacy', 'none')
    # With admission_frontier_hint off, the transactional frontier query is named again.
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"admission_frontier_hint": 0}')
    view.service_frontier(0)
    assert batch_pipeline_store.contention_tables(view) == ('control_query,jobs_query,privacy', 'none')
