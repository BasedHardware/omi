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
    from fastapi.testclient import TestClient
    from routers import messaging
    from utils.messaging.gateway import Gateway

    adapter = LoopbackAdapter()
    gateway = Gateway(adapter, store=store, admission=lambda uid: None)
    monkeypatch.setattr(messaging, 'MessagingStore', lambda: store)
    monkeypatch.setattr(messaging, '_admit', lambda uid: None)
    monkeypatch.setattr(messaging, '_gateways', {'loopback': gateway})
    app = FastAPI()
    app.include_router(messaging.router)
    app.dependency_overrides[messaging.get_current_user_uid] = lambda: 'u'
    # The mint dependency has a rate-limit wrapper; override that exact route dependency.
    mint = next(r for r in app.routes if getattr(r, 'path', '') == '/v1/messaging/link-proofs')
    app.dependency_overrides[mint.dependant.dependencies[0].call] = lambda: 'u'
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
