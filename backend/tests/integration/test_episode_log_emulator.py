"""Real atomic rollback and concurrent leases. Loopback emulator only, never cloud."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from database import episode_log as store

pytestmark = pytest.mark.integration
NOW = datetime(2026, 11, 4, tzinfo=timezone.utc)


@pytest.fixture
def db(monkeypatch):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('Requires a loopback Firestore emulator; no cloud fallback')
    monkeypatch.setenv('EPISODES_LOG_ENABLED', 'on')
    monkeypatch.setenv('EPISODES_PERCENT', '100')
    client = firestore.Client(project='demo-episode-log', credentials=AnonymousCredentials())
    return client, 'episode-log-' + uuid4().hex


def test_abort_after_staging_publishes_neither_fact_nor_legacy_mutation(db):
    client, uid = db
    legacy = store.root(client, uid).collection('episodes').document('e')
    legacy.set({'title': 'before'})

    @firestore.transactional
    def doomed(transaction):
        capture = store.prepare(transaction, client, uid)
        legacy.get(transaction=transaction)
        transaction.update(legacy, {'title': 'after'})
        capture.stage([{'kind': 'member_refresh', 'cid': 'c', 'payload': {}}], now=NOW)
        raise RuntimeError('synthetic process death before commit')

    with pytest.raises(RuntimeError, match='synthetic process death'):
        doomed(client.transaction())
    assert legacy.get().to_dict() == {'title': 'before'}
    assert list(store.root(client, uid).collection('episode_facts').stream()) == []
    assert store.state(uid, firestore_client=client) == {}


def test_competing_claims_one_epoch_and_stale_publication_is_atomic(db):
    client, uid = db
    store.append(uid, 'key', [{'kind': 'member_refresh', 'cid': 'c', 'payload': {}}], firestore_client=client, now=NOW)

    def take(_):
        return store.claim(uid, firestore_client=client, now=NOW + timedelta(minutes=3))

    with ThreadPoolExecutor(max_workers=4) as pool:
        claims = list(pool.map(take, range(4)))
    winners = [claim for claim in claims if claim]
    assert len(winners) == 1
    stale = winners[0]
    current = store.claim(uid, firestore_client=client, now=NOW + timedelta(minutes=14))
    assert current['epoch'] == stale['epoch'] + 1
    with pytest.raises(store.LostLease):
        store.publish(
            uid, stale, 1, {}, {'e': {'title': 'stale'}}, {}, firestore_client=client, now=NOW + timedelta(minutes=14)
        )
    assert not store.root(client, uid).collection('episode_views').document('e').get().exists
    assert store.state(uid, firestore_client=client).get('cursor', 0) == 0


def test_bounded_fact_page_has_contiguous_arrival_order_and_dedupes(db):
    client, uid = db
    for key in ('z', 'a', 'm'):
        store.append(
            uid, key, [{'kind': 'member_refresh', 'cid': key, 'payload': {}}], firestore_client=client, now=NOW
        )
    assert store.append(uid, 'a', [], firestore_client=client, now=NOW) is None
    page = store.fact_page(uid, 0, 3, limit=2, firestore_client=client)
    assert [row['key'] for row in page] == ['z', 'a']
    events, cursor = store.read_batch(
        uid, {'state': store.state(uid, firestore_client=client)}, firestore_client=client
    )
    assert [event['cid'] for event in events] == ['z', 'a', 'm'] and cursor == 3
