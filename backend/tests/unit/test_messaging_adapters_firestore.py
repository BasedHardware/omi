"""Durable outbound/undo transactions against a loopback-only Firestore emulator."""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from database import action_items
from database.messaging import MessagingStore
from testing.messaging.loopback import LoopbackAdapter
from utils.messaging.adapters.delivery import DeliveryLedger
from utils.messaging.undo import UndoStore
from utils.messaging import undo
from utils.messaging.projection import SurfaceRuntime, surface_runtime
from utils.messaging.contracts import Principal


@pytest.fixture
def store(monkeypatch):
    host = os.getenv('MESSAGING_TEST_FIRESTORE_HOST')
    if not host:
        pytest.skip('Local Firestore emulator not requested')
    assert host.startswith('127.0.0.1:')
    monkeypatch.setenv('FIRESTORE_EMULATOR_HOST', host)
    client = firestore.Client(project='demo-msg-adapters-' + uuid4().hex[:8], credentials=AnonymousCredentials())
    client.collection('users').document('test').set({'name': 'Synthetic test user'})
    yield MessagingStore(firestore_client=client)
    client.close()


def message():
    adapter = LoopbackAdapter()
    return adapter.parse(adapter.signed()[0])[0]


def test_duplicate_inbound_and_atomic_ratio_content_free_receipts(store):
    ledger, incoming = DeliveryLedger(store), message()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: ledger.inbound(incoming), range(4)))

    def reserve(i):
        try:
            return ledger.reserve(incoming, str(i), ratio=2)
        except PermissionError:
            return False

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(reserve, range(4)))
    assert sum(results) == 2
    assert ledger._chat(incoming).get().to_dict() == {'received': 1, 'sent': 2}
    receipt = list(ledger._chat(incoming).collection('receipts').stream())[0].to_dict()
    assert set(receipt) == {'state', 'at'}


def test_receipt_retry_and_ambiguous_telegram_reconciliation(store):
    ledger, incoming = DeliveryLedger(store), message()
    ledger.inbound(incoming)
    assert ledger.reserve(incoming, 'telegram')
    with pytest.raises(RuntimeError, match='reconciliation'):
        ledger.reserve(incoming, 'telegram')
    assert ledger.reserve(incoming, 'telegram', retry_reserved=True)
    ledger.accepted(incoming, 'telegram', 'receipt-1')
    assert not ledger.reserve(incoming, 'telegram', retry_reserved=True)
    assert ledger._chat(incoming).get().to_dict()['sent'] == 1


def test_undo_encrypted_scoped_expired_once_and_ambiguous_inverse(store, monkeypatch):
    manager = UndoStore(store)
    store.db.collection('channel_identities').document('test-link').set(
        {'active': True, 'uid': 'test', 'generation': 'generation'}
    )
    store.user('test').collection('chat_sessions').document('session').set(
        {'channel_link_id': 'test-link', 'link_generation': 'generation'}
    )
    runtime = SurfaceRuntime('channel:test', '', Principal('test'), session_id='session')
    token = surface_runtime.set(runtime)
    calls = []
    try:
        receipt = manager.record('test', 'session', 'task', 'object', None, {'description': 'synthetic task'})
        assert 'synthetic task' not in str(manager.ref('test', 'session', receipt.id).get().to_dict())
        monkeypatch.setattr(undo, 'apply_inverse', lambda uid, payload: calls.append((uid, payload)))
        assert manager.undo('other', 'session', receipt.id).status == 'unavailable'
        assert manager.undo('test', 'session', receipt.id).status == 'undone'
        assert manager.undo('test', 'session', receipt.id).status == 'already_undone'
        assert len(calls) == 1
        receipt = manager.record('test', 'session', 'task', 'object', None, {})
        manager.ref('test', 'session', receipt.id).update(
            {'expires_at': datetime.now(timezone.utc) - timedelta(seconds=1)}
        )
        assert manager.undo('test', 'session', receipt.id).status == 'unavailable'
        receipt = manager.record('test', 'session', 'task', 'object', None, {})

        def fail(*args):
            raise RuntimeError('ambiguous')

        monkeypatch.setattr(undo, 'apply_inverse', fail)
        with pytest.raises(RuntimeError):
            manager.undo('test', 'session', receipt.id)
        assert manager.ref('test', 'session', receipt.id).get().to_dict()['state'] == 'running'
        assert manager.undo('test', 'session', receipt.id).status == 'unavailable'
    finally:
        surface_runtime.reset(token)


def test_task_inverse_compare_and_restore_and_delete(store, monkeypatch):
    monkeypatch.setattr(action_items, 'db', store.db)
    monkeypatch.setattr(action_items, 'bump_action_items_list_version', lambda uid: None)
    monkeypatch.setattr(action_items, '_purge_proactivity_source', lambda *a: None)
    ref = store.user('test').collection('action_items').document('task')
    prior = {'id': 'task', 'description': 'before', 'completed': False, 'due_at': None}
    ref.set(prior)
    after = {'id': 'task', 'description': 'after', 'completed': True, 'due_at': None}
    ref.set(after)
    expected = action_items.get_action_item('test', 'task')
    ref.update({'description': 'concurrent app change'})
    assert not action_items.restore_channel_write('test', 'task', expected, prior)
    ref.set(after)
    expected = action_items.get_action_item('test', 'task')
    assert action_items.restore_channel_write('test', 'task', expected, prior)
    assert action_items.get_action_item('test', 'task')['description'] == 'before'
    expected = action_items.get_action_item('test', 'task')
    assert action_items.restore_channel_write('test', 'task', expected, None)
    assert not ref.get().exists


def test_inverse_receipt_fences_revocation_and_never_recreates_session(store):
    manager = UndoStore(store)
    incoming = message()
    proof = store.mint('test', incoming.channel, incoming.provider, 'token')['proof']
    link = store.consume(proof, incoming)
    session = store.session('test', incoming, link)
    token = surface_runtime.set(SurfaceRuntime(session['surface'], '', Principal('test'), session_id=session['id']))
    try:
        store.unlink('test', session['channel_link_id'])
        with pytest.raises(PermissionError):
            manager.record('test', session['id'], 'task', 'object', None, {})
        assert not store.user('test').collection('chat_sessions').document(session['id']).get().exists
    finally:
        surface_runtime.reset(token)


def test_specific_receipts_survive_later_writes_and_text_undo_rejects_multiwrite(store, monkeypatch):
    store.db.collection('channel_identities').document('test-link').set(
        {'active': True, 'uid': 'test', 'generation': 'generation'}
    )
    store.user('test').collection('chat_sessions').document('session').set(
        {'channel_link_id': 'test-link', 'link_generation': 'generation'}
    )
    manager = UndoStore(store)
    runtime = SurfaceRuntime('channel:test', '', Principal('test'), session_id='session', turn_id='turn-one')
    token = surface_runtime.set(runtime)
    calls = []
    monkeypatch.setattr(undo, 'apply_inverse', lambda uid, payload: calls.append(payload['object_id']))
    try:
        first = manager.record('test', 'session', 'memory', 'memory-one', None, 'Synthetic fact')
        second = manager.record('test', 'session', 'task', 'task-two', None, {'description': 'Synthetic task'})
        assert manager.undo('test', 'session').status == 'unavailable'
        manager.bind_bubble('test', 'session', first.id, '71')
        result = manager.undo('test', 'session', first.id)
        assert result.status == 'undone' and result.bubble_id == '71'
        assert manager.ref('test', 'session', second.id).get().to_dict()['state'] == 'ready'
        manager.mark_edited('test', 'session', first.id)
        replay = manager.undo('test', 'session', first.id)
        assert replay.status == 'already_undone' and replay.bubble_id is None
        assert calls == ['memory-one']
        assert manager.undo('test', 'session', second.id).status == 'undone'
        assert calls == ['memory-one', 'task-two']
    finally:
        surface_runtime.reset(token)


def test_duplicate_callback_race_claims_inverse_once(store, monkeypatch):
    store.db.collection('channel_identities').document('test-link').set(
        {'active': True, 'uid': 'test', 'generation': 'generation'}
    )
    store.user('test').collection('chat_sessions').document('session').set(
        {'channel_link_id': 'test-link', 'link_generation': 'generation'}
    )
    manager = UndoStore(store)
    token = surface_runtime.set(SurfaceRuntime('channel:test', '', Principal('test'), session_id='session'))
    try:
        receipt = manager.record('test', 'session', 'task', 'task-one', None, {'description': 'Synthetic task'})
    finally:
        surface_runtime.reset(token)
    calls = []
    monkeypatch.setattr(undo, 'apply_inverse', lambda uid, payload: calls.append(payload['object_id']))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: manager.undo('test', 'session', receipt.id), range(4)))
    assert sum(result.status == 'undone' for result in results) == 1
    assert calls == ['task-one']


def test_expired_receipts_cleanup_is_bounded_and_preserves_recent_tombstones(store):
    manager = UndoStore(store)
    now = datetime.now(timezone.utc)
    for i in range(105):
        manager.ref('test', 'session', str(i)).set(
            {'expires_at': now - timedelta(days=2), 'state': 'done', 'presentation': 'encrypted snapshot'}
        )
    manager.ref('test', 'session', 'recent').set({'expires_at': now, 'state': 'done'})
    manager.ref('test', 'session').set({'state': 'ready', 'receipt_id': 'recent'})
    assert manager.prune_expired('test', 'session', now=now) == 100
    assert manager.prune_expired('test', 'session', now=now) == 5
    assert manager.ref('test', 'session', 'recent').get().exists
    assert manager.ref('test', 'session').get().exists


def test_inbox_fifo_fences_running_head_and_sorts_retry_backlog(store):
    from dataclasses import replace

    incoming = message()
    items = [replace(incoming, provider_message_id=str(i)) for i in range(3)]
    paths = [store.enqueue(item) for item in items]
    assert store.claim(paths[2]) is None
    assert store.claim(paths[1]) is None
    assert store.claim(paths[0]) is not None
    assert store.claim(paths[1]) is None
    store.retry(paths[0])
    assert store.pending(incoming) == paths
    assert store.claim(paths[2]) is None
    assert store.claim(paths[0]) is not None
    store.complete(paths[0])
    assert store.claim(paths[2]) is None
    assert store.claim(paths[1]) is not None
    store.complete(paths[1])
    assert store.claim(paths[2]) is not None
