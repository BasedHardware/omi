"""Repair pins projected members; disabled capture has no customer side effects."""

from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from google.cloud import firestore

from config import episode_log as config
from database import episode_log as store
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils import omi_flags
from utils.episodes import home_read
from utils.episodes.log import capture, reconcile, worker


@pytest.mark.parametrize('remote', [None, False])
@pytest.mark.parametrize('failure', ['saturated', 'submit_failed'])
def test_capture_off_never_sets_up_submits_or_writes(monkeypatch, remote, failure):
    monkeypatch.setenv('EPISODES_ENABLED', 'on')
    monkeypatch.setenv('EPISODES_PERCENT', '100')
    monkeypatch.setenv('EPISODES_LOG_ENABLED', 'on' if remote is False else 'off')
    rules = {} if remote is None else {'EPISODES_LOG_ENABLED': SimpleNamespace(active=False)}
    monkeypatch.setattr(omi_flags, 'snapshot', lambda: SimpleNamespace(rules=rules))
    submit = Mock(side_effect=RuntimeError(failure))
    invalidate, append, job = Mock(), Mock(), Mock()
    monkeypatch.setattr(capture, 'submit', submit)
    monkeypatch.setattr(store, 'invalidate', invalidate)
    monkeypatch.setattr(store, 'append', append)
    client = StrictFirestore()
    ref = store.root(client, 'synthetic').collection('conversations').document('c')

    @firestore.transactional
    def edit(transaction):
        original = transaction._commit
        assert store.prepare(transaction, client, 'synthetic') is None
        assert transaction._commit == original
        assert not hasattr(transaction, '_episode_capture_commit')
        transaction.set(ref, {'status': 'completed'})

    edit(client.transaction())
    # Direct dispatch, cancellation/drop, and an intent queued before the kill
    # must all respect the same gate, including errors compacting the intent.
    capture.dispatch(job, uid='synthetic', client=client)
    worker.note_dirty('synthetic', 'c', {'status': 'completed'})
    capture.dropped(RuntimeError(failure), uid='synthetic', client=client)
    intent = capture.DeferredCapture(client, 'synthetic')
    intent.stage_error = RuntimeError('staged before kill')
    intent.flush()
    assert client.rows == {ref.path: {'status': 'completed'}}
    assert len(client.transactions) == 1
    for mock in (submit, invalidate, append, job):
        mock.assert_not_called()


def test_capture_kill_after_setup_or_submission_is_inert(monkeypatch):
    enabled = True
    monkeypatch.setattr(config, 'capture_possible', lambda: enabled)
    monkeypatch.setattr(config, 'episodes_enabled_for', lambda uid: True)
    queued, future = [], Future()
    monkeypatch.setattr(capture, 'submit', lambda fn: queued.append(fn) or future)
    invalidate, job = Mock(), Mock()
    monkeypatch.setattr(store, 'invalidate', invalidate)
    client = StrictFirestore()
    transaction = client.transaction()
    intent = store.prepare(transaction, client, 'synthetic')
    intent.stage([{'kind': 'member_refresh', 'cid': 'c', 'payload': {}}])
    enabled = False
    transaction._commit()  # Already installed commit observer must not submit.
    assert not queued
    enabled = True
    capture.dispatch(job, uid='synthetic', client=client)
    enabled = False
    queued.pop()()  # Accepted before kill, run after kill.
    future.cancel()  # Cancellation callback must not write a dirty marker.
    job.assert_not_called()
    invalidate.assert_not_called()
    assert client.rows == {}


def test_member_read_records_exact_versions_including_missing_and_hidden(monkeypatch):
    client = Mock()
    ref = lambda cid: SimpleNamespace(path=f'users/u/conversations/{cid}')
    docs = [
        SimpleNamespace(
            id='visible',
            reference=ref('visible'),
            exists=True,
            update_time=1,
            to_dict=lambda: {'structured': {'title': 'before'}},
        ),
        SimpleNamespace(
            id='hidden', reference=ref('hidden'), exists=True, update_time=2, to_dict=lambda: {'deleted': True}
        ),
        SimpleNamespace(id='missing', reference=ref('missing'), exists=False, update_time=None),
    ]
    client.get_all.return_value = docs
    monkeypatch.setattr(home_read.conversations, 'prepare_conversation_for_read', lambda raw, uid: raw)
    proof = {}
    members = reconcile.read_members('u', [{'conversation_ids': ['visible', 'hidden', 'missing']}], client, proof)
    assert set(members) == {'visible', 'hidden'}
    assert proof == {doc.reference.path: doc.update_time for doc in docs}
    client.get_all.assert_called_once()


def test_member_proof_budget_fails_before_any_reads():
    client = Mock()
    with pytest.raises(store.ProjectionCapacity):
        reconcile.read_members('u', [{'conversation_ids': ['c']}], client, dict.fromkeys(range(store.MAX_PUBLISH_ROWS)))
    assert not client.mock_calls


@pytest.mark.parametrize('version', [None, 1, 2])
def test_member_proof_reads_in_publication_transaction(monkeypatch, version):
    client, transaction = Mock(), object()
    path = 'users/u/conversations/c'
    monkeypatch.setattr(reconcile, 'source_documents', lambda *a, **kw: [])
    client.get_all.return_value = [SimpleNamespace(reference=SimpleNamespace(path=path), update_time=version)]
    if version == 1:
        reconcile.verify('u', client, {path: 1}, transaction)
    else:
        with pytest.raises(store.LostLease, match='source_changed'):
            reconcile.verify('u', client, {path: 1}, transaction)
    client.get_all.assert_called_once_with([client.document.return_value], field_paths=[], transaction=transaction)


def test_policy_release_disabled_after_serving_does_not_invalidate(monkeypatch):
    from utils.episodes.log.policy import home_policy_write

    enabled = True
    monkeypatch.setattr(config, 'capture_possible', lambda: True)
    monkeypatch.setattr(config, 'enabled', lambda uid: enabled)
    monkeypatch.setattr(config, 'home_enabled', lambda: True)
    client, queued = object(), []
    monkeypatch.setattr(store, 'state', lambda *a, **kw: {'cursor': 1})
    barrier, invalidate = Mock(), Mock()
    monkeypatch.setattr(store, 'policy_barrier', barrier)
    monkeypatch.setattr(store, 'invalidate', invalidate)
    monkeypatch.setattr(capture, 'submit', lambda fn: queued.append(fn) or Future())

    @home_policy_write(firestore_client=lambda: client)
    def edit(uid, conversation_id):
        return 'original response'

    assert edit('synthetic', 'c') == 'original response'
    assert barrier.call_count == 1  # Entry occurred while enabled.
    enabled = False
    queued.pop()()
    assert barrier.call_count == 1
    invalidate.assert_not_called()


def test_source_growth_rejects_before_spending_member_read_budget(monkeypatch):
    doc = SimpleNamespace(reference=SimpleNamespace(path='users/u/episodes/new'), update_time=2)
    monkeypatch.setattr(reconcile, 'source_documents', lambda *a, **kw: [doc])
    client = Mock()
    with pytest.raises(store.LostLease, match='source_changed'):
        reconcile.verify('u', client, {'users/u/conversations/c': 1}, object())
    client.get_all.assert_not_called()


def test_disabled_retry_clears_aborted_intent_before_readmission(monkeypatch):
    enabled = True
    monkeypatch.setattr(config, 'capture_possible', lambda: enabled)
    monkeypatch.setattr(config, 'episodes_enabled_for', lambda uid: True)
    submit = Mock()
    monkeypatch.setattr(capture, 'submit', submit)
    client = StrictFirestore()
    transaction = client.transaction()
    aborted = store.prepare(transaction, client, 'synthetic')
    aborted.stage([{'kind': 'member_refresh', 'cid': 'aborted', 'payload': {}}])
    enabled = False
    assert store.prepare(transaction, client, 'synthetic') is None
    enabled = True
    transaction._commit()
    submit.assert_not_called()
    assert client.rows == {}
