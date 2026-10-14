"""Launch contracts: hermetic gateway/provider checks and loopback-only Firestore races."""

import asyncio
import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from config.messaging import channel_policy, cohort_enabled
from database.messaging import MessagingStore, PENDING_MAX_SECONDS
from testing.messaging.loopback import LoopbackAdapter
from testing.messaging.store import MemoryStore
from utils.messaging import access, gateway as gateway_module
from utils.messaging.access import AccessDenied, SeatFull
from utils.messaging.adapters.telegram import TelegramAdapter
from utils.messaging.adapters.transport import ProviderError, request_json
from utils.messaging.contracts import ChannelCapabilities
from utils.messaging.gateway import Gateway, inbound_evidence
from utils.messaging.outbound import ChannelReplySink


@pytest.fixture
def policy(monkeypatch):
    value = {'telegram': {'enabled': True, 'cohort': '*'}, 'imessage': {'enabled': True, 'cohort': '*', 'seat_cap': 1}}
    monkeypatch.setenv('OMI_MESSAGING_CHANNEL_POLICY', json.dumps(value))
    monkeypatch.delenv('OMI_MESSAGING_KILL_SWITCH_DOC', raising=False)
    return value


@pytest.mark.parametrize(
    'plan,telegram,imessage',
    [
        ('basic', False, False),
        ('plus', True, False),
        ('unlimited', True, False),
        ('operator', True, True),
        ('architect', True, True),
    ],
)
def test_channel_plan_admission(policy, monkeypatch, plan, telegram, imessage):
    monkeypatch.setattr(access, 'get_user_deletion_wipe_status', lambda uid: None)
    monkeypatch.setattr(access, 'get_user_valid_subscription', lambda uid, **kw: SimpleNamespace(plan=plan))
    for channel, allowed in [('telegram', telegram), ('imessage', imessage)]:
        if allowed:
            access.require_access('any-paid-user', channel)
        else:
            with pytest.raises(PermissionError):
                access.require_access('any-paid-user', channel)


@pytest.mark.parametrize(
    'raw',
    [
        '{',
        '[]',
        '{"telegram":{"enabled":true,"cohort":true}}',
        '{"imessage":{"enabled":true,"cohort":"*","seat_cap":true}}',
        '{"imessage":{"enabled":true,"cohort":"*","seat_cap":null}}',
        '{"imessage":{"enabled":true,"cohort":"*","plans":null}}',
    ],
)
def test_malformed_policy_fails_closed(monkeypatch, raw):
    monkeypatch.setenv('OMI_MESSAGING_CHANNEL_POLICY', raw)
    assert not cohort_enabled('u', 'telegram')
    assert not cohort_enabled('u', 'imessage')


def test_legacy_and_configurable_policy(monkeypatch):
    monkeypatch.delenv('OMI_MESSAGING_CHANNEL_POLICY', raising=False)
    monkeypatch.setenv('OMI_MESSAGING_CHANNELS', 'on')
    monkeypatch.setenv('OMI_MESSAGING_CHANNELS_UIDS', 'u')
    assert cohort_enabled('u', 'imessage') and not cohort_enabled('v', 'telegram')
    assert channel_policy('imessage').get('seat_cap') is None
    monkeypatch.setenv(
        'OMI_MESSAGING_CHANNEL_POLICY',
        json.dumps(
            {
                'imessage': {
                    'enabled': True,
                    'cohort': ['v'],
                    'plans': ['operator', 'architect', 'unlimited'],
                    'seat_cap': 7,
                }
            }
        ),
    )
    assert channel_policy('imessage')['plans'][-1] == 'unlimited'
    assert cohort_enabled('v', 'imessage') and not cohort_enabled('u', 'imessage')
    assert not cohort_enabled('v', 'telegram')


def test_remote_kill_cache_and_failure(monkeypatch):
    from database import _client

    access._kill_cache.clear()
    monkeypatch.setenv('OMI_MESSAGING_KILL_SWITCH_DOC', 'messaging_config/switch')
    clock = [0]
    row = {'telegram': True, 'imessage': False}
    calls = []

    def get():
        calls.append(True)
        return SimpleNamespace(to_dict=lambda: dict(row))

    monkeypatch.setattr(
        _client, 'get_firestore_client', lambda: SimpleNamespace(document=lambda path: SimpleNamespace(get=get))
    )
    monkeypatch.setattr(access.time, 'monotonic', lambda: clock[0])
    assert access.remote_enabled('telegram') and not access.remote_enabled('imessage')
    row['telegram'] = False
    assert access.remote_enabled('telegram') and len(calls) == 1
    clock[0] = 61
    assert not access.remote_enabled('telegram') and len(calls) == 2
    clock[0] = 122
    monkeypatch.setattr(_client, 'get_firestore_client', lambda: (_ for _ in ()).throw(RuntimeError()))
    assert not access.remote_enabled('telegram')
    access._kill_cache.clear()


def message(adapter, **kw):
    return adapter.parse(adapter.signed(**kw)[0])[0]


def test_unknown_sender_gets_one_reply_per_window():
    adapter, store = LoopbackAdapter(), MemoryStore()
    gateway = Gateway(adapter, store=store, admission=lambda uid, channel: None, rate_limit=lambda uid: None)

    async def run():
        for i in range(3):
            assert await gateway.process(store.enqueue(message(adapter, provider_message_id=str(i))))

    asyncio.run(run())
    assert len(adapter.sent) == 1
    assert all(row['status'] == 'done' for row in store.jobs.values())


@pytest.mark.parametrize('reason', ['paid_plan', 'channel_plan', 'channel_disabled'])
def test_lost_access_replies_once_without_model(reason):
    adapter, store = LoopbackAdapter(), MemoryStore()
    incoming = message(adapter)
    store.consume(store.mint('u', adapter.channel, adapter.provider, 'token')['proof'], incoming)

    def deny(uid, channel):
        raise AccessDenied(reason, 'denied')

    gateway = Gateway(
        adapter,
        store=store,
        admission=deny,
        rate_limit=lambda uid: None,
        turn=lambda *a, **kw: pytest.fail('No model on admission denial'),
    )

    async def run():
        for i in range(2):
            assert await gateway.process(store.enqueue(replace(incoming, provider_message_id=str(i))))

    asyncio.run(run())
    assert len(adapter.sent) == 1
    assert not store.leases


def test_linked_channel_uses_chat_send_limit(monkeypatch):
    adapter, store = LoopbackAdapter(), MemoryStore()
    incoming = message(adapter)
    store.consume(store.mint('u', adapter.channel, adapter.provider, 'token')['proof'], incoming)
    called = []
    from utils.messaging.metrics import TURNS

    before = TURNS.labels(adapter.channel, 'completed')._value.get()

    def limit(uid):
        called.append(uid)
        raise HTTPException(status_code=429)

    gateway = Gateway(
        adapter,
        store=store,
        admission=lambda uid, channel: None,
        rate_limit=limit,
        turn=lambda *a, **kw: pytest.fail('No model when throttled'),
    )
    assert asyncio.run(gateway.process(store.enqueue(incoming)))
    assert called == ['u'] and 'wait' in adapter.sent[0]['text']
    assert TURNS.labels(adapter.channel, 'completed')._value.get() == before + 1
    assert not store.leases


def test_chat_limit_uses_same_uid_and_policy(monkeypatch):
    from utils.other import endpoints

    calls = []
    monkeypatch.setattr(endpoints, 'check_rate_limit_inline', lambda *args: calls.append(args))
    gateway_module._chat_rate_limit('u')
    assert calls == [('u', 'chat:send_message')]


@pytest.mark.parametrize('command', ['new', 'link_help'])
def test_new_and_malformed_start_do_not_run_model(command):
    adapter, store = LoopbackAdapter(), MemoryStore()
    incoming = message(adapter, command=command)
    store.consume(store.mint('u', adapter.channel, adapter.provider, 'token')['proof'], incoming)
    before = store.session('u', incoming, store.lookup(incoming))['id']
    gateway = Gateway(
        adapter,
        store=store,
        admission=lambda uid, channel: None,
        rate_limit=lambda uid: None,
        turn=lambda *a, **kw: pytest.fail('Command is not a model request'),
    )
    assert asyncio.run(gateway.process(store.enqueue(incoming)))
    after = store.session('u', incoming, store.lookup(incoming))['id']
    assert (before != after) == (command == 'new')
    assert len(adapter.sent) == 1


def test_telegram_malformed_start_forward_and_new_parser():
    adapter = TelegramAdapter('synthetic-token', 'synthetic-secret')
    item = {
        'message_id': 1,
        'chat': {'id': 1, 'type': 'private'},
        'from': {'id': 1},
        'text': '/start bad!',
        'forward_origin': {'type': 'hidden_user'},
    }
    incoming = adapter.parse(json.dumps({'update_id': 1, 'message': item}).encode())[0]
    assert incoming.command == 'link_help' and incoming.link_proof is None and incoming.forwarded
    assert 'Forwarded content (untrusted' in inbound_evidence(incoming)
    item['text'] = '/new'
    assert adapter.parse(json.dumps({'update_id': 2, 'message': item}).encode())[0].command == 'new'


def test_failed_draft_preserves_final_reply():
    adapter = LoopbackAdapter(capabilities=ChannelCapabilities(streaming='draft'))
    incoming = message(adapter)
    send = adapter.send

    async def broken_preview(msg, **kw):
        if kw.get('draft'):
            raise ProviderError('preview unavailable', status_code=400)
        return await send(msg, **kw)

    adapter.send = broken_preview

    async def run():
        sink = ChannelReplySink(adapter, incoming)
        await sink.text('partial')
        await sink.text(' more')
        await sink.finish('final')
        assert sink.drafts_disabled

    asyncio.run(run())
    assert [row['text'] for row in adapter.sent] == ['final']


def test_429_wait_and_pacing_each_attempt():
    import httpx

    calls, sleeps = [], []
    from utils.messaging.metrics import HTTP

    before_429 = HTTP.labels('telegram', '429')._value.get()
    before_200 = HTTP.labels('telegram', '200')._value.get()

    class Transport:
        async def request(self, *a, **kw):
            calls.append('request')
            return httpx.Response(
                429 if calls.count('request') == 1 else 200,
                json={'parameters': {'retry_after': 7}} if calls.count('request') == 1 else {'ok': True},
            )

    async def pace():
        calls.append('pace')

    async def wait(delay):
        sleeps.append(delay)

    asyncio.run(request_json(Transport(), 'POST', 'https://api.telegram.org/test', sleep=wait, before_attempt=pace))
    assert calls == ['pace', 'request', 'pace', 'request'] and sleeps == [7]
    assert HTTP.labels('telegram', '429')._value.get() == before_429 + 1
    assert HTTP.labels('telegram', '200')._value.get() == before_200 + 1


@pytest.fixture
def store():
    host = os.getenv('MESSAGING_TEST_FIRESTORE_HOST')
    if not host:
        pytest.skip('Loopback emulator not requested')
    assert host.startswith('127.0.0.1:')
    from google.auth.credentials import AnonymousCredentials
    from google.cloud import firestore

    os.environ['FIRESTORE_EMULATOR_HOST'] = host
    client = firestore.Client(project='demo-q-' + uuid4().hex[:10], credentials=AnonymousCredentials())
    client.collection('users').document('u').set({'name': 'synthetic'})
    client.collection('users').document('v').set({'name': 'synthetic'})
    yield MessagingStore(firestore_client=client)
    client.close()


def imessage(adapter, sender='one'):
    return replace(message(adapter), channel='imessage', provider='linq', external_user_id=sender)


def test_seat_cap_atomic_waitlist_unlink_and_deletion(store, policy):
    adapter = LoopbackAdapter()
    store.capacity('imessage').set({'initialized': True, 'count': 0})
    proofs = [store.mint(uid, 'imessage', 'linq', 'code')['proof'] for uid in ['u', 'v']]

    def consume(index):
        try:
            return store.consume(proofs[index], imessage(adapter, str(index)))
        except SeatFull:
            return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(consume, [0, 1]))
    assert sum(row is not None for row in results) == 1
    assert store.capacity('imessage').get().to_dict()['count'] == 1
    winner = 'u' if results[0] else 'v'
    loser = 'v' if results[0] else 'u'
    with pytest.raises(SeatFull):
        store.mint(loser, 'imessage', 'linq', 'code')
    assert store.user(loser).collection('channel_waitlist').document('imessage').get().exists
    # Re-link and a second identity for the same user never consume a second seat.
    proof = store.mint(winner, 'imessage', 'linq', 'code')['proof']
    store.consume(proof, imessage(adapter, 'extra'))
    assert store.capacity('imessage').get().to_dict()['count'] == 1
    links = store.links(winner)
    store.unlink(winner, links[0]['id'])
    assert store.capacity('imessage').get().to_dict()['count'] == 1
    store.delete_account(winner)
    assert store.capacity('imessage').get().to_dict()['count'] == 0
    proof = store.mint(loser, 'imessage', 'linq', 'code')['proof']
    store.consume(proof, imessage(adapter, 'returning'))
    assert not store.user(loser).collection('channel_waitlist').document('imessage').get().exists


def test_uninitialized_seats_fail_closed(store, policy):
    with pytest.raises(PermissionError, match='reconciliation'):
        store.mint('u', 'imessage', 'linq', 'code')


def test_event_tail_fences_survive_pruning_and_new_session(store):
    adapter = LoopbackAdapter()
    incoming = message(adapter)
    link = store.consume(store.mint('u', 'loopback', 'fake', 'token')['proof'], incoming)
    session = store.session('u', incoming, link)
    from utils import encryption

    ref = store.user('u').collection('chat_sessions').document(session['id'])
    store.append_event('u', session['id'], {'id': '0', 'at': '0', 'content': 'first'})
    batch = store.db.batch()
    for i in range(1, 40):
        batch.set(
            ref.collection('channel_events').document(f'z{i+1:012d}'),
            {'sequence': i + 1, 'payload': encryption.encrypt(json.dumps({'id': str(i), 'content': 'old'}), 'u')},
        )
    batch.update(ref, {'channel_event_sequence': 40})
    batch.commit()
    for i in range(40, 45):
        store.append_event('u', session['id'], {'id': str(i), 'at': str(i), 'content': 'x' * 13000})
    events = store.events('u', session['id'])
    assert len(events) == 40 and events[0]['id'] == '5'
    assert store.has_event('u', session['id'], {'0'})
    store.append_event('u', session['id'], {'id': '0', 'content': 'duplicate'})
    assert len(store.events('u', session['id'])) == 40
    fresh = store.reset_session('u', incoming, link)
    assert store.session('u', incoming, link)['id'] == fresh['id'] != session['id']
    assert not store.events('u', fresh['id'])


def test_legacy_event_fences_are_migrated_before_compaction(store):
    from utils import encryption

    adapter = LoopbackAdapter()
    incoming = message(adapter)
    link = store.consume(store.mint('u', 'loopback', 'fake', 'token')['proof'], incoming)
    session = store.session('u', incoming, link)
    ref = store.user('u').collection('chat_sessions').document(session['id'])
    ref.update({'channel_events_migrated': False})
    for i in range(41):
        ref.collection('channel_events').document(f'{i:012d}').set(
            {'payload': encryption.encrypt(json.dumps({'id': 'legacy' + str(i), 'content': 'old'}), 'u')}
        )
    store.append_event('u', session['id'], {'id': 'new', 'content': 'new'})
    assert store.has_event('u', session['id'], {'legacy0'})
    assert len(store.events('u', session['id'])) == 40


def test_pending_queries_expired_notice_claim_and_cleanup(store):
    adapter = LoopbackAdapter()
    incoming = message(adapter)
    link = store.consume(store.mint('u', 'loopback', 'fake', 'token')['proof'], incoming)
    path = store.enqueue(incoming)
    assert store.pending_jobs('loopback', 'fake') == [path]
    assert store.pending_jobs('telegram', 'telegram') == []
    store.claim_next(path, now=datetime.now(timezone.utc) + timedelta(seconds=PENDING_MAX_SECONDS + 1))
    assert store.db.document(path).get().to_dict()['status'] == 'expired'
    assert len(store.claim_expired('loopback', 'fake')) == 1
    assert store.claim_expired('loopback', 'fake') == []
    assert 'payload' not in store.db.document(path).get().to_dict()
    old = datetime.now(timezone.utc) - timedelta(days=40)
    store.db.document(path).update({'done_at': old})
    store.mint('u', 'loopback', 'fake', 'token', now=old)
    store.waitlist('v', 'imessage', now=old)
    unknown = replace(incoming, external_user_id='unknown', provider_message_id='unknown')
    store.enqueue(unknown)
    store.identity('loopback', 'fake', 'unknown').update({'last_inbound_at': old})
    result = store.cleanup()
    assert result == {'proofs': 1, 'identities': 1, 'inbox': 1, 'waitlist': 1}
    assert store.lookup(incoming)['active']
    assert not store.lookup(unknown)
    assert len(store.links('u')) == 1


def test_prepare_launch_backfills_legacy_metadata_and_seats(store, monkeypatch):
    monkeypatch.delenv('OMI_MESSAGING_CHANNEL_POLICY', raising=False)
    monkeypatch.setenv('OMI_MESSAGING_CHANNELS', 'off')
    incoming = imessage(LoopbackAdapter())
    store.consume(store.mint('u', 'imessage', 'linq', 'code')['proof'], incoming)
    path = store.enqueue(incoming)
    from google.cloud import firestore

    store.db.document(path).update({'channel': firestore.DELETE_FIELD, 'provider': firestore.DELETE_FIELD})
    assert store.pending_jobs('imessage', 'linq') == []
    assert store.prepare_launch() == {'seats': 1, 'inbox_metadata': 1}
    assert store.pending_jobs('imessage', 'linq') == [path]
    assert store.capacity('imessage').get().to_dict()['count'] == 1
    monkeypatch.setenv('OMI_MESSAGING_CHANNELS', 'on')
    with pytest.raises(ValueError, match='Disable'):
        store.prepare_launch()


def test_redis_pacing_is_shared_between_instances(monkeypatch):
    host = os.getenv('MESSAGING_TEST_REDIS_HOST')
    if not host:
        pytest.skip('Loopback Redis not requested')
    assert host.startswith('127.0.0.1:')
    import redis
    import time
    from database import redis_db
    from utils.messaging.pacing import reserve

    hostname, port = host.split(':')
    clients = [redis.Redis(host=hostname, port=int(port)), redis.Redis(host=hostname, port=int(port))]
    bot = 'synthetic-' + uuid4().hex
    deadlines = []
    for i in range(12):
        monkeypatch.setattr(redis_db, 'r', clients[i % 2])
        delay = reserve(bot, 'chat-' + str(i))
        deadlines.append(time.monotonic() + delay)
    assert all(b - a >= 0.025 for a, b in zip(deadlines, deadlines[1:]))
    delay = reserve(bot, 'chat-11')
    assert delay > 1
    for client in clients:
        client.close()


def test_expired_job_notice_respects_reply_window(monkeypatch):
    adapter = LoopbackAdapter(capabilities=ChannelCapabilities(free_reply_window=timedelta(minutes=10)))
    store = MemoryStore()
    incoming = message(adapter, received_at=(datetime.now(timezone.utc) - timedelta(minutes=31)).isoformat())
    store.consume(store.mint('u', adapter.channel, adapter.provider, 'token')['proof'], incoming)
    from dataclasses import asdict

    payload = asdict(incoming)
    payload['received_at'] = incoming.received_at.isoformat()
    monkeypatch.setattr(store, 'claim_expired', lambda *args: [dict(payload)])
    gateway = Gateway(adapter, store=store, admission=lambda uid, channel: None, rate_limit=lambda uid: None)
    asyncio.run(gateway.expired_notices())
    assert not adapter.sent
    adapter.capabilities = ChannelCapabilities()
    asyncio.run(gateway.expired_notices())
    assert len(adapter.sent) == 1 and 'please resend' in adapter.sent[0]['text']


def test_telegram_malformed_start_webhook_returns_202(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import messaging

    adapter = TelegramAdapter('synthetic-token', 'synthetic-secret')
    store = MemoryStore()
    gateway = Gateway(adapter, store=store, admission=lambda uid, channel: None, rate_limit=lambda uid: None)
    monkeypatch.setattr(messaging, '_gateways', {'telegram': gateway})
    app = FastAPI()
    app.include_router(messaging.router)
    body = {
        'update_id': 1,
        'message': {
            'message_id': 1,
            'chat': {'id': 1, 'type': 'private'},
            'from': {'id': 1},
            'text': '/start invalid!',
        },
    }
    with TestClient(app) as client:
        response = client.post(
            '/v1/messaging/webhooks/telegram',
            json=body,
            headers={'X-Telegram-Bot-Api-Secret-Token': 'synthetic-secret'},
        )
    assert response.status_code == 202
    assert next(iter(store.jobs.values()))['payload']['command'] == 'link_help'


def test_mint_capacity_error_is_typed_waitlist(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import messaging

    class Full:
        def mint(self, *args):
            raise SeatFull()

    monkeypatch.setattr(messaging, '_admit', lambda uid, channel: None)
    monkeypatch.setattr(messaging, 'MessagingStore', Full)
    app = FastAPI()
    app.include_router(messaging.router)
    route = next(route for route in app.routes if route.path == '/v1/messaging/link-proofs')
    app.dependency_overrides[route.dependant.dependencies[0].call] = lambda: 'u'
    with TestClient(app) as client:
        response = client.post(
            '/v1/messaging/link-proofs', json={'channel': 'imessage', 'provider': 'linq', 'kind': 'code'}
        )
    assert response.status_code == 409
    assert response.json()['detail'] == {'reason': 'seat_cap', 'message': 'iMessage is full — join the waitlist'}


@pytest.mark.parametrize('prepare', [False, True])
def test_maintenance_entrypoint_runs_without_provider_construction(monkeypatch, prepare):
    import sys
    from utils.messaging import maintenance

    calls = []
    monkeypatch.setattr(sys, 'argv', ['maintenance'] + (['--prepare-launch'] if prepare else []))
    monkeypatch.setenv('OMI_MESSAGING_RETENTION_DAYS', '30')
    monkeypatch.setattr(
        maintenance,
        'MessagingStore',
        lambda: SimpleNamespace(
            cleanup=lambda **kw: calls.append(('cleanup', kw)) or {},
            prepare_launch=lambda: calls.append(('prepare', {})) or {},
        ),
    )
    maintenance.main()
    assert calls == [('prepare', {})] if prepare else calls == [('cleanup', {'retention_days': 30})]


def test_imessage_only_policy_still_admits_app_awareness(monkeypatch):
    monkeypatch.setenv('OMI_MESSAGING_CHANNEL_POLICY', json.dumps({'imessage': {'enabled': True, 'cohort': ['u']}}))
    monkeypatch.delenv('OMI_MESSAGING_KILL_SWITCH_DOC', raising=False)
    monkeypatch.setattr(access, 'get_user_deletion_wipe_status', lambda uid: None)
    monkeypatch.setattr(access, 'get_user_valid_subscription', lambda *a, **kw: SimpleNamespace(plan='operator'))
    assert cohort_enabled('u') and not cohort_enabled('u', 'telegram')
    access.require_app_access('u')
    with pytest.raises(PermissionError):
        access.require_app_access('outside')
