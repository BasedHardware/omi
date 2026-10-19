"""Local integration: real Firestore emulator transactions; never connects to cloud."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from database.messaging import MessagingStore
from utils.messaging.identity import key
from testing.messaging.loopback import LoopbackAdapter


@pytest.fixture
def store():
    host = os.getenv('MESSAGING_TEST_FIRESTORE_HOST')
    if not host:
        pytest.skip('Local Firestore emulator not requested')
    assert host.startswith('127.0.0.1:')
    os.environ['FIRESTORE_EMULATOR_HOST'] = host
    client = firestore.Client(project='demo-messaging-' + uuid4().hex[:10], credentials=AnonymousCredentials())
    client.collection('users').document('u').set({'name': 'Synthetic contract user'})
    yield MessagingStore(firestore_client=client)
    client.close()


@pytest.mark.parametrize('kind', ['token', 'code'])
def test_link_proof_race_expiry_audience_and_unlink(store, kind):
    adapter = LoopbackAdapter()
    message = adapter.parse(adapter.signed()[0])[0]
    proof = store.mint('u', message.channel, message.provider, kind)['proof']

    def consume():
        try:
            return store.consume(proof, message)
        except PermissionError:
            return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: consume(), range(2)))
    assert sum(r is not None for r in results) == 1
    assert len(store.links('u')) == 1
    old = store.mint('u', message.channel, message.provider, kind, now=datetime.now(timezone.utc) - timedelta(hours=1))[
        'proof'
    ]
    with pytest.raises(PermissionError):
        store.consume(old, message)
    session = store.session('u', message, results[0] or results[1])
    store.append_event('u', session['id'], {'id': 'event', 'content': 'private content'})
    assert store.events('u', session['id'])[0]['content'] == 'private content'
    link_id = key(message.channel, message.provider, message.external_user_id)
    store.user('u').collection('messages').document('msg').set({'channel_link_id': link_id, 'text': 'private'})
    store.unlink('u', link_id)
    assert not store.lookup(message) and not store.links('u')
    assert not store.user('u').collection('chat_sessions').document(session['id']).get().exists
    assert not store.user('u').collection('messages').document('msg').get().exists


def test_dedup_claim_lease_and_content_erasure(store):
    adapter = LoopbackAdapter()
    message = adapter.parse(adapter.signed()[0])[0]
    path = store.enqueue(message)
    assert store.enqueue(message) is None
    assert store.claim(path)['text'] == 'hello'
    assert store.claim(path) is None
    token = store.acquire('u', 's')
    assert token and store.acquire('u', 's') is None
    with pytest.raises(PermissionError):
        store.release('u', 's', 'foreign-token')
    store.release('u', 's', token)
    assert store.acquire('u', 's')
    store.complete(path)
    assert 'payload' not in store.db.document(path).get().to_dict()
    assert store.enqueue(message) is None


@pytest.fixture
def local_api(store, monkeypatch):
    from fastapi import FastAPI
    from fastapi.routing import APIRoute
    from fastapi.testclient import TestClient
    from routers import messaging
    from utils.messaging.gateway import Gateway

    adapter = LoopbackAdapter()
    gateway = Gateway(adapter, store=store, admission=lambda uid, channel: None, rate_limit=lambda uid: None)
    monkeypatch.setattr(messaging, 'MessagingStore', lambda: store)
    monkeypatch.setattr(messaging, '_admit', lambda uid, channel: None)
    monkeypatch.setattr(messaging, '_gateways', {'loopback': gateway})
    app = FastAPI()
    app.include_router(messaging.router)
    app.dependency_overrides[messaging.get_current_user_uid] = lambda: 'u'
    # The mint dependency has a rate-limit wrapper; override that exact route dependency.
    mint = next(r for r in app.routes if isinstance(r, APIRoute) and r.path == '/v1/messaging/link-proofs')
    mint_dependency = mint.dependant.dependencies[0].call
    assert mint_dependency is not None
    app.dependency_overrides[mint_dependency] = lambda: 'u'
    with TestClient(app) as client:
        yield client, gateway, adapter


def test_app_routes_and_signature_webhook_with_real_local_store(local_api):
    client, gateway, adapter = local_api
    response = client.post(
        '/v1/messaging/link-proofs', json={'channel': 'loopback', 'provider': 'fake', 'kind': 'code'}
    )
    assert response.status_code == 200
    body, headers = adapter.signed(link_proof=response.json()['proof'])
    assert (
        client.post('/v1/messaging/webhooks/loopback', content=body, headers={'signature': 'invalid'}).status_code
        == 401
    )
    assert client.post('/v1/messaging/webhooks/loopback', content=body, headers=headers).status_code == 202
    assert not adapter.sent
    import asyncio

    asyncio.run(gateway.drain())
    links = client.get('/v1/messaging/links').json()['links']
    assert len(links) == 1
    assert client.patch('/v1/messaging/links/' + links[0]['id'], json={'visible_in_app': True}).status_code == 200
    assert client.get('/v1/messaging/links').json()['links'][0]['visible_in_app']
    assert client.delete('/v1/messaging/links/' + links[0]['id']).status_code == 200
    assert client.get('/v1/messaging/links').json()['links'] == []


def test_album_atomic_coalescing_dedup_fifo_and_late_part(store):
    from dataclasses import replace
    from utils.messaging.contracts import InboundAttachment

    adapter = LoopbackAdapter()
    message = replace(
        adapter.parse(adapter.signed()[0])[0],
        channel='telegram',
        provider='telegram',
        media_group_id='group',
        attachments=(InboundAttachment('file', 'photo.jpg', 'image/jpeg'),),
    )
    second = replace(message, provider_message_id='second', text='Second caption')
    first_path = store.enqueue(message)
    assert store.enqueue(second) == first_path
    assert store.enqueue(message) is None
    assert store.claim_next(first_path) is None
    now = datetime.now(timezone.utc) + timedelta(seconds=4)
    first_claim = store.claim_next(first_path, now=now)
    assert first_claim is not None
    path, payload = first_claim
    assert path == first_path and len(payload['attachments']) == 2
    assert 'Second caption' in payload['text']
    assert store.claim_next(path, now=now) is None
    late = replace(message, provider_message_id='late')
    assert store.enqueue(late) == path
    refreshed = store.seal_album(path, 2)
    assert refreshed is not None and len(refreshed['attachments']) == 3
    assert store.seal_album(path, 3) is None
    latest = replace(message, provider_message_id='after-generation')
    late_path = store.enqueue(latest)
    assert store.enqueue(replace(message, provider_message_id='out-of-order')) == late_path
    assert late_path != path and store.claim_next(late_path, now=now) is None
    store.complete(path)
    assert store.enqueue(second) is None
    late_claim = store.claim_next(late_path, now=now)
    assert late_claim is not None and len(late_claim[1]['attachments']) == 2
    store.complete(late_path)
    assert not store.pending(message)


def test_no_cap_imessage_redemption_never_reads_capacity(store, monkeypatch):
    from dataclasses import replace

    monkeypatch.setenv('OMI_MESSAGING_CHANNEL_POLICY', '{"imessage":{"enabled":true,"cohort":["u"],"seat_cap":"off"}}')

    def capacity(*args):
        raise AssertionError('No seat counter read permitted')

    monkeypatch.setattr(store, 'capacity', capacity)
    message = replace(LoopbackAdapter().parse(LoopbackAdapter().signed()[0])[0], channel='imessage', provider='linq')
    proof = store.mint('u', 'imessage', 'linq', 'code')['proof']
    link = store.consume(proof, message)
    store.assert_link_capacity(message, link)
    store.unlink('u', key(message.channel, message.provider, message.external_user_id))
    assert store.lookup(message) is None


def test_album_seal_races_late_admission_without_losing_a_part(store):
    from dataclasses import replace
    from utils.messaging.contracts import InboundAttachment

    adapter = LoopbackAdapter()
    first = replace(
        adapter.parse(adapter.signed()[0])[0],
        media_group_id='race',
        attachments=(InboundAttachment('first', 'first.jpg', 'image/jpeg'),),
    )
    path = store.enqueue(first)
    assert store.claim_next(path, now=datetime.now(timezone.utc) + timedelta(seconds=4))
    late = replace(
        first, provider_message_id='racing', attachments=(InboundAttachment('late', 'late.jpg', 'image/jpeg'),)
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        seal = executor.submit(store.seal_album, path, 1)
        append = executor.submit(store.enqueue, late)
        updated, admitted_path = seal.result(), append.result()
    if updated is None:
        # Sealing won; admission must durably create the shared follow-up.
        assert admitted_path != path
        assert len(store.db.document(admitted_path).get().to_dict()['payload']) > 0
    else:
        assert admitted_path == path and len(updated['attachments']) == 2
        assert store.seal_album(path, 2) is None
    assert store.enqueue(late) is None


def test_album_claimed_by_old_worker_is_never_appendable(store):
    from dataclasses import replace
    from utils.messaging.contracts import InboundAttachment

    adapter = LoopbackAdapter()
    message = replace(
        adapter.parse(adapter.signed()[0])[0],
        media_group_id='rolling-deploy',
        attachments=(InboundAttachment('file', 'p.jpg', 'image/jpeg'),),
    )
    path = store.enqueue(message)
    # Old workers only stamp status/started_at, even if a new instance admitted the row.
    store.db.document(path).update({'status': 'running', 'started_at': datetime.now(timezone.utc)})
    late_path = store.enqueue(replace(message, provider_message_id='late'))
    assert late_path != path


def test_cleanup_preserves_unknown_running_reconciliation(store):
    adapter = LoopbackAdapter()
    message = adapter.parse(adapter.signed()[0])[0]
    path = store.enqueue(message)
    assert store.claim(path) is not None
    identity = store.identity(message.channel, message.provider, message.external_user_id)
    old = datetime.now(timezone.utc) - timedelta(days=40)
    identity.update({'last_inbound_at': old})
    store.db.document(path).update({'started_at': old, 'fifo_settled_at': old})
    # Even a settled ambiguous send retains running status until reconciliation.
    assert store.cleanup()['identities'] == 0
    assert identity.get().exists and store.db.document(path).get().to_dict()['payload']
    store.complete(path)
    assert store.cleanup()['identities'] == 1
    assert not identity.get().exists
