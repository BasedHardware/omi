"""Admission and discovery restart atomic read aborts within a bounded budget."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from google.api_core.exceptions import Aborted

from config.dream_agent import Caps
from database import dream_scheduler, dream_store, firestore_transaction_retry
from tests.support.dream_firestore import DreamFirestore, Document
from utils import dream_metrics

NOW = datetime(2026, 10, 21, 13, tzinfo=timezone.utc)
OWNER = 'synthetic-admission-contention'


@pytest.fixture
def database(monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', 'all')
    monkeypatch.setenv('REVIEW_SURFACE_MODE', 'on')
    monkeypatch.setattr(dream_store, 'mode', lambda: 'on')
    monkeypatch.setattr(dream_store._review_store(), 'encode_doc', lambda uid, value: value)
    return DreamFirestore()


@pytest.fixture
def retry_sleeps(monkeypatch):
    sleeps = []
    retry = firestore_transaction_retry.run_with_transaction_contention_retry

    def fast_retry(*args, **kwargs):
        return retry(*args, **kwargs, sleep=sleeps.append, random_value=lambda: 0)

    monkeypatch.setattr(firestore_transaction_retry, 'run_with_transaction_contention_retry', fast_retry)
    return sleeps


@pytest.mark.parametrize('exhausted', [False, True])
@pytest.mark.parametrize('site', ['count', 'legacy_global_spend'])
def test_acquire_restarts_read_aborts_without_duplicate_admission(database, retry_sleeps, monkeypatch, site, exhausted):
    database.rows[('users', OWNER)] = {}
    when = NOW
    if site == 'legacy_global_spend':
        old = dream_store.acquire(OWNER, Caps(), now=NOW, firestore_client=database)
        database.rows[('dream_users', OWNER)]['lease']['global_spend_scope'] = True
        global_path = ('dream_global_spend', old['day'])
        database.rows[global_path] = {'reserved_usd': 1.0}
        when += timedelta(seconds=1741)
    before = deepcopy(database.rows)
    transactions, reclaimed = [], {}

    def maybe_abort(tx):
        transactions.append(tx)
        if exhausted or len(transactions) == 1:
            raise Aborted('synthetic admission read abort')

    if site == 'count':
        original_count = dream_store.dirty_count

        def count(*args, transaction=None, **kwargs):
            maybe_abort(transaction)
            return original_count(*args, transaction=transaction, **kwargs)

        monkeypatch.setattr(dream_store, 'dirty_count', count)
    else:
        original_get = Document.get

        def get(ref, transaction=None, **kwargs):
            if ref.path == global_path:
                maybe_abort(transaction)
            return original_get(ref, transaction=transaction, **kwargs)

        monkeypatch.setattr(Document, 'get', get)

    def acquire():
        return dream_store.acquire(OWNER, Caps(), now=when, firestore_client=database, reclaim_sink=reclaimed)

    if exhausted:
        with pytest.raises(firestore_transaction_retry.FirestoreContentionExhausted):
            acquire()
        assert database.rows == before and reclaimed == {}
    else:
        lease = acquire()
        assert database.rows[('dream_users', OWNER)]['lease'] == lease
        assert database.rows[('dream_users', OWNER)]['passes'] == (2 if site == 'legacy_global_spend' else 1)
        if site == 'legacy_global_spend':
            assert lease['run_id'] != old['run_id']
            assert reclaimed == {'age_s': 1741, 'size_bucket': 'light'}
            assert database.rows[global_path] == before[global_path]
            assert len([path for path in database.rows if path[:3] == ('users', OWNER, 'dream_runs')]) == 1
    assert len(transactions) == (5 if exhausted else 2)
    assert len({id(tx) for tx in transactions}) == len(transactions)
    assert len(retry_sleeps) == len(transactions) - 1


@pytest.mark.parametrize('exhausted', [False, True])
def test_discover_restarts_read_aborts_and_preserves_existing_due(database, retry_sleeps, monkeypatch, exhausted):
    owners = ['synthetic-discovery-new', 'synthetic-discovery-queued']
    rows = []
    for owner in owners:
        ref = database.collection('users').document(owner)
        ref.set({})
        rows.append(ref.get())
    queued = ('dream_due', owners[1])
    database.rows[queued] = {'due_at': NOW + timedelta(hours=2)}
    monkeypatch.setattr(dream_scheduler, 'candidate_page', lambda **kwargs: rows)
    before = deepcopy(database.rows)
    transactions = []
    original_get_all = database.get_all

    def get_all(refs, *, transaction=None, **kwargs):
        if transaction is not None and refs[0].path[0] == 'dream_due':
            transactions.append(transaction)
            if exhausted or len(transactions) == 1:
                raise Aborted('synthetic discovery read abort')
        return original_get_all(refs, transaction=transaction, **kwargs)

    monkeypatch.setattr(database, 'get_all', get_all)
    if exhausted:
        with pytest.raises(firestore_transaction_retry.FirestoreContentionExhausted):
            dream_scheduler.discover(database, NOW, pages=1)
        assert database.rows == before
    else:
        dream_scheduler.discover(database, NOW, pages=1)
        assert database.rows[queued] == before[queued]
        assert ('dream_due', owners[0]) in database.rows
        assert database.rows[('dream_scheduler', 'discovery')] == {'after': owners[-1]}
    assert len(transactions) == (5 if exhausted else 2)
    assert len({id(tx) for tx in transactions}) == len(transactions)
    assert len(retry_sleeps) == len(transactions) - 1


def test_contention_exhaustion_has_its_own_metric_label(caplog):
    metric = dream_metrics.PASSES.labels('failed', 'FirestoreContentionExhausted')
    before = metric._value.get()
    with caplog.at_level('INFO', logger='utils.dream_metrics'):
        dream_metrics.record_pass({'status': 'failed', 'error_type': 'FirestoreContentionExhausted'})
    assert metric._value.get() == before + 1
    assert 'error_type=FirestoreContentionExhausted' in caplog.text
