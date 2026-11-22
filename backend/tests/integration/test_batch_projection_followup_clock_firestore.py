"""Durable stamping/checkpoint boundaries against the loopback emulator only."""

import os
from uuid import uuid4
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from database.batch_pipeline_projection_followup_clock import DUE_FIELD as DUE, defer_unchanged
from database.batch_pipeline_projection_followup_backfill import backfill_ref, stamp_page
from database.batch_pipeline_store import FirestoreStore
from database.batch_pipeline_projection_finish import projection_finish_state_fields

pytestmark = pytest.mark.integration


@pytest.fixture
def store():
    host = os.getenv('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('loopback emulator required; no cloud fallback')
    client = firestore.Client(project='demo-followup-clock', credentials=AnonymousCredentials())
    return FirestoreStore(f'batch_pipeline_test_{uuid4().hex}', firestore_client=client)


def seed(store):
    collection = store.client.collection(f'{store.namespace}_results')
    for index, state in enumerate(('persisted', 'ready', 'ready', 'pending', 'completed')):
        collection.document(str(index)).set({'projection_state': state, 'committed_at': float(index)})
    collection.document('1').update({DUE: 9999.0, 'projection_finish_backoff_step': 2})
    return collection


def test_dry_run_resume_preserves_clocks_and_filters_immediately(store):
    rows = seed(store)
    marker = backfill_ref(store.client, store.namespace)
    assert stamp_page(store, 100.0, size=2) == {
        'complete': False,
        'scanned': 2,
        'missing': 1,
        'stamped': 0,
    }
    assert not marker.get().exists
    assert DUE not in rows.document('0').get().to_dict()
    assert stamp_page(store, 100.0, size=2, apply=True)['stamped'] == 1
    assert not store.projection_followup_backfill_complete()
    # A fresh operator resumes shared progress without rescanning the first page.
    fresh = FirestoreStore(store.namespace, firestore_client=store.client)
    assert stamp_page(fresh, 101.0, size=2, apply=True) == {
        'complete': True,
        'scanned': 1,
        'missing': 1,
        'stamped': 1,
    }
    assert fresh.projection_followup_backfill_complete()
    assert rows.document('1').get().to_dict()[DUE] == 9999.0
    assert rows.document('1').get().to_dict()['projection_finish_backoff_step'] == 2
    assert fresh.projection_page(states=('persisted', 'ready'), followup_due_before=200.0)[0] == ['0', '2']
    assert DUE not in rows.document('3').get().to_dict()
    assert DUE not in rows.document('4').get().to_dict()
    assert stamp_page(fresh, 200.0, apply=True)['scanned'] == 0


def test_failure_does_not_advance_checkpoint_and_state_moves_are_fenced(store, monkeypatch):
    rows = seed(store)
    original = store.projection_page

    def moved(*args, **kwargs):
        page = original(*args, **kwargs)
        rows.document('0').update({'projection_state': 'completed'})
        return page

    monkeypatch.setattr(store, 'projection_page', moved)
    assert stamp_page(store, 100.0, size=2, apply=True)['stamped'] == 0
    assert DUE not in rows.document('0').get().to_dict()
    marker = backfill_ref(store.client, store.namespace)
    before = marker.get().to_dict()
    real_transaction = store.client.transaction

    def failed_transaction(*args, **kwargs):
        raise RuntimeError('synthetic transaction failure')

    monkeypatch.setattr(store.client, 'transaction', failed_transaction)
    with pytest.raises(RuntimeError, match='synthetic transaction failure'):
        stamp_page(store, 101.0, size=2, apply=True)
    assert marker.get().to_dict() == before
    monkeypatch.setattr(store.client, 'transaction', real_transaction)
    assert stamp_page(store, 102.0, size=2, apply=True)['complete']
    assert rows.document('2').get().to_dict()[DUE] == 102.0


def test_competing_operator_cannot_commit_stale_checkpoint(store, monkeypatch):
    seed(store)
    original = store.projection_page

    def concurrent(*args, **kwargs):
        page = original(*args, **kwargs)
        backfill_ref(store.client, store.namespace).set({'other_operator': True})
        return page

    monkeypatch.setattr(store, 'projection_page', concurrent)
    with pytest.raises(RuntimeError, match='checkpoint changed'):
        stamp_page(store, 100.0, apply=True)
    assert not store.projection_followup_backfill_complete()


def test_due_ordering_equal_clocks_and_restart_never_drop_a_result(store):
    rows = store.client.collection(f'{store.namespace}_results')
    for key in ('a', 'b', 'c'):
        rows.document(key).set({'projection_state': 'ready', 'committed_at': 10.0, DUE: 20.0})
    rows.document('future').set({'projection_state': 'ready', 'committed_at': 1.0, DUE: 200.0})
    ids, cursor = store.projection_page(limit=2, states=('ready',), followup_due_before=100.0)
    assert ids == ['a', 'b']
    fresh = FirestoreStore(store.namespace, firestore_client=store.client)
    assert fresh.projection_page(limit=2, states=('ready',), after=cursor, followup_due_before=100.0)[0] == ['c']
    assert fresh.projection_page(states=('ready',), followup_due_before=200.0)[0] == ['a', 'b', 'c', 'future']


def test_concurrent_incomplete_attempts_write_one_bounded_deadline_and_state_move_wakes(store):
    ref = store.client.collection(f'{store.namespace}_results').document('same')
    before = {'projection_state': 'ready', 'projection': {'state': 'ready'}, 'committed_at': 10.0, DUE: 1.0}
    ref.set(before)
    projection = SimpleNamespace(client=store.client, store=store, ref=lambda *_: ref)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: defer_unchanged(projection, 'same', before, 100.0, 900.0), range(2)))
    assert sorted(outcomes) == [False, True]
    assert ref.get().to_dict()[DUE] == 160.0
    ref.update(
        {
            'projection': {'state': 'ready', 'conversation_id': 'changed'},
            **projection_finish_state_fields('ready', 101.0),
        }
    )
    assert not defer_unchanged(projection, 'same', before, 102.0, 900.0)
    assert ref.get().to_dict()[DUE] == 101.0
