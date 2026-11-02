"""Hermetic policy guards; real query ordering/contention is covered by the emulator suite."""

import json
import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from database import messaging
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.messaging.identity import key
from utils.messaging import gateway as gateway_module
from testing.messaging.loopback import LoopbackAdapter
from testing.messaging.store import MemoryStore


@pytest.fixture
def queue(monkeypatch):
    client, tx = MagicMock(), MagicMock()
    client.transaction.return_value = tx
    ref = client.document.return_value
    ref.parent.parent.id = 'synthetic-identity'
    ref.path = 'channel_identities/synthetic/inbox/new'
    snapshots = []

    def stream(**kwargs):
        assert kwargs['transaction'] is tx
        assert not tx.update.called  # all query reads precede writes
        return iter(snapshots)

    ref.parent.where.return_value.order_by.return_value.stream.side_effect = stream
    monkeypatch.setattr(messaging.firestore, 'transactional', lambda fn: fn)
    monkeypatch.setattr(messaging.encryption, 'decrypt', lambda value, uid: value)
    store = messaging.MessagingStore(firestore_client=client)
    return store, tx, snapshots, ref.path


def row(path, status, now, age=0, **extra):
    snapshot = MagicMock()
    snapshot.reference.path = path
    snapshot.to_dict.return_value = dict(
        status=status, created_at=now - timedelta(seconds=age), payload=json.dumps({'text': path}), **extra
    )
    return snapshot


def test_claim_settles_legacy_running_and_retires_pending_without_replay(queue, caplog):
    store, tx, rows, path = queue
    now = datetime.now(timezone.utc)
    rows.extend(
        [
            row('old-pending', 'pending', now, messaging.PENDING_MAX_SECONDS + 1),
            row('old-running', 'running', now, messaging.STALE_SECONDS + 1),
            row(path, 'pending', now),
        ]
    )
    assert store.claim_next(path, now=now) == (path, {'text': path})
    patches = [call.args[1] for call in tx.update.call_args_list]
    assert patches[0]['status'] == 'expired' and 'payload' not in patches[0]
    assert patches[1]['retired_reason'] == 'stale_running' and 'status' not in patches[1]
    assert patches[2] == {'status': 'running', 'started_at': now}
    assert 'reason=stale_running' in caplog.text


def test_fresh_running_head_blocks_every_wake_and_counts_refusal(queue, caplog):
    store, tx, rows, path = queue
    now = datetime.now(timezone.utc)
    rows.extend([row('running-head', 'running', now, 10), row(path, 'pending', now)])
    before = messaging._QUEUE_EVENTS.labels(reason='non_head')._value.get()
    assert store.claim_next(path, now=now) is None
    assert not tx.update.called
    assert messaging._QUEUE_EVENTS.labels(reason='non_head')._value.get() == before + 1
    assert 'reason=non_head' in caplog.text and 'head_age_seconds=10.0' in caplog.text


def test_new_wake_claims_older_pending_and_never_skips_it(queue):
    store, tx, rows, path = queue
    now = datetime.now(timezone.utc)
    rows.extend([row('older', 'pending', now, 10), row(path, 'pending', now)])
    assert store.claim(path, now=now) is None
    assert not tx.update.called
    assert store.claim_next(path, now=now) == ('older', {'text': 'older'})


def test_started_at_allows_a_recent_claim_of_an_older_pending(queue):
    store, tx, rows, path = queue
    now = datetime.now(timezone.utc)
    rows.append(row(path, 'running', now, 1000, started_at=now))
    assert store.claim_next(path, now=now) is None
    assert not tx.update.called


def test_settled_running_row_is_never_replayed(queue):
    store, tx, rows, path = queue
    now = datetime.now(timezone.utc)
    rows.append(row(path, 'running', now, 1000, fifo_settled_at=now))
    assert store.claim_next(path, now=now) is None
    assert not tx.update.called


def test_lease_expiry_is_transactional_and_old_token_is_fenced(caplog):
    now = datetime.now(timezone.utc)
    path = ('users', 'test', 'channel_turn_leases', key('surface'))
    db = StrictFirestore({path: {'token': 'old', 'created_at': now}})
    store = messaging.MessagingStore(firestore_client=db)
    assert store.acquire('test', 'surface', now=now) is None
    token = store.acquire('test', 'surface', now=now + timedelta(seconds=messaging.STALE_SECONDS))
    assert token and db.rows[path]['token'] == token
    with pytest.raises(PermissionError):
        store.assert_lease('test', 'surface', 'old')
    assert 'reason=lease_busy' in caplog.text and 'reason=stale_lease' in caplog.text


def test_worker_deadline_settles_without_replaying_and_continues(monkeypatch):

    adapter, store = LoopbackAdapter(), MemoryStore()
    incoming = adapter.parse(adapter.signed()[0])[0]
    first = store.enqueue(incoming)
    second = store.enqueue(replace(incoming, provider_message_id='second'))
    gateway = gateway_module.Gateway(adapter, store=store)
    seen = []

    async def process_claimed(path, payload):
        seen.append(path)
        if path == first:
            await asyncio.Event().wait()
        store.complete(path)
        return True

    monkeypatch.setattr(gateway_module, 'TURN_TIMEOUT_SECONDS', 0.01)
    monkeypatch.setattr(gateway, '_process_claimed', process_claimed)
    assert asyncio.run(gateway.process(second))
    assert seen == [first, second]
    assert store.jobs[first]['fifo_settled_at']
    assert not asyncio.run(gateway.process(first))
    assert seen == [first, second]
