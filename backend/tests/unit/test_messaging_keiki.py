"""Keiki external-harness adapter: signed turns in, turn-scoped replies out. Network replayed."""

import asyncio
import base64
import hashlib
import hmac
import json
import time
from typing import Any

import pytest
from testing.messaging.adapter_contract import AdapterContract
from testing.messaging.adapter_fakes import FixtureLedger, FixtureTransport, no_sleep
from testing.messaging.store import MemoryStore
from utils.messaging.adapters.keiki import KeikiAdapter, KeikiClient, turn_auth
from utils.messaging.adapters.transport import ProviderError
from utils.messaging.gateway import Gateway

AGENT = 'agent-omi-imessage'
SECRET = 'whsec_synthetic-keiki-signing-secret'
BASE = 'https://onkeiki.com/api/v1'


def turn(turn_id='turn-1', text='What are my tasks today?', **overrides):
    value: dict[str, Any] = {
        'type': 'keiki.turn',
        'version': 1,
        'turnId': turn_id,
        'agentId': AGENT,
        'conversationId': '+15555550123',
        'heldBack': False,
        'silent': False,
        'quietLoop': False,
        'channel': {'channel': 'imessage'},
        'messages': [{'text': text, 'content': text, 'messageId': 'msg-' + turn_id}],
        'history': [],
        'context': {},
        'instructions': '',
        'keiki': {'apiBase': BASE, 'turnUrl': BASE + '/turns/' + turn_id, 'mcpUrl': BASE + '/harness/mcp'},
        'deadline': '2026-10-30T12:10:00.000Z',
    }
    value.update(overrides)
    return value


def signed(value, *, secret=SECRET, timestamp=None, raw=None):
    body = raw if raw is not None else json.dumps(value).encode()
    stamp = str(int(time.time()) if timestamp is None else timestamp)
    digest = hmac.new(secret.encode(), stamp.encode() + b'.' + body, hashlib.sha256).hexdigest()
    return body, {'Keiki-Signature': f't={stamp},v1={digest}', 'Keiki-Turn-Id': value.get('turnId', '')}


def calls(adapter, suffix):
    return [c for c in adapter.transport.calls if c[1].endswith(suffix)]


@pytest.fixture
def adapter(monkeypatch):
    transport, ledger = FixtureTransport(), FixtureLedger()
    client = KeikiClient(AGENT, SECRET, transport=transport, sleep=no_sleep)
    result: Any = KeikiAdapter('imessage', client, transport=transport, ledger=ledger, sleep=no_sleep)
    result.sent = []
    send = result.send

    async def record(message, *, text=None, artifact=None, draft=False, link=None):
        result.sent.append(dict(message=message, text=text, artifact=artifact, draft=draft))
        await send(message, text=text, artifact=artifact, draft=draft, **({'link': link} if link else {}))

    monkeypatch.setattr(result, 'send', record)
    return result


@pytest.fixture
def signed_message(adapter):
    def create():
        value = turn()
        message = adapter.parse(json.dumps(value).encode())[0]
        adapter.ledger.received.add((message.external_chat_id, message.provider_message_id))
        return signed(value)

    return create


class TestKeikiContracts(AdapterContract):
    pass


def test_signature_raw_body_replay_and_rotation(adapter):
    body, headers = signed(turn())
    assert adapter.verify_webhook(body, headers)
    assert not adapter.verify_webhook(body + b' ', headers)
    assert not adapter.verify_webhook(*signed(turn(), secret='whsec_another-secret-entirely'))
    assert not adapter.verify_webhook(*signed(turn(), timestamp=int(time.time()) - 301))
    assert not adapter.verify_webhook(body, {})
    # During secret rotation Keiki sends both signatures.
    stamp = headers['Keiki-Signature'].split(',')[0]
    other = hmac.new(b'old-secret-value-xx', b'x', hashlib.sha256).hexdigest()
    rotated = {'Keiki-Signature': stamp + ',v1=' + other + ',' + headers['Keiki-Signature'].split(',')[1]}
    assert adapter.verify_webhook(body, rotated)
    assert not adapter.verify_webhook(body, {'Keiki-Signature': stamp + ',v1=nothex'})


def test_turn_auth_is_the_documented_kts1_credential():
    token = turn_auth(SECRET, AGENT, 'turn-9', now=1789600000)
    prefix, payload, signature = token.split('.')
    assert prefix == 'kts1'
    decoded = base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4))
    assert decoded == b'{"a":"agent-omi-imessage","t":"turn-9","ts":1789600000}'
    expected = hmac.new(SECRET.encode(), b'keiki-turn-auth.v1.' + payload.encode(), hashlib.sha256).hexdigest()
    assert signature == expected


def test_parse_maps_one_turn_to_one_inbox_message(adapter):
    value = turn(
        messages=[
            {'text': 'first part', 'messageId': 'm1'},
            {'text': 'note from server', 'messageId': 'm2', 'silent': True},
            {'text': 'second part', 'messageId': 'm3', 'replyTo': {'messageId': 'm0', 'text': 'earlier'}},
        ]
    )
    (message,) = adapter.parse(json.dumps(value).encode())
    assert (message.channel, message.provider) == ('imessage', 'keiki')
    assert message.provider_message_id == 'turn-1'
    assert message.external_user_id == message.external_chat_id == '+15555550123'
    assert message.text == 'first part\nsecond part'
    assert message.reply_to == 'm3'
    assert (message.quoted_text, message.quoted_message_id) == ('earlier', 'm0')


def test_link_code_and_commands(adapter):
    code = '0123456789ABCDEF0123456789ABCDEF'
    (linked,) = adapter.parse(json.dumps(turn(text='link ' + code.lower())).encode())
    assert linked.link_proof == code
    for text, command in (('help', 'help'), ('new chat', 'new'), ('undo', 'undo'), ('👍', 'ack')):
        assert adapter.parse(json.dumps(turn(text=text)).encode())[0].command == command
    assert adapter.parse(json.dumps(turn(text='unlink')).encode())[0].unlink
    attachment = turn(text='', messages=[{'text': '', 'content': '[Photo; attachment_id=a1]', 'messageId': 'm'}])
    assert adapter.parse(json.dumps(attachment).encode())[0].command == 'unsupported'


@pytest.mark.parametrize('service', ['imessage', 'sms', 'SMS', 'photon'])
def test_phone_line_services_reach_the_imessage_channel(adapter, service):
    (message,) = adapter.parse(json.dumps(turn(channel={'channel': service, 'isDm': True})).encode())
    assert (message.channel, message.external_chat_id) == ('imessage', '+15555550123')


@pytest.mark.parametrize(
    'overrides',
    [
        {'heldBack': True},
        {'silent': True},
        {'quietLoop': True},
        {'channel': {'channel': 'imessage', 'isGroup': True}},
        {'channel': {'channel': 'slack'}},
        {'channel': {'channel': 'whatsapp'}},
        {'messages': [{'text': 'platform notice', 'silent': True}]},
    ],
)
def test_unanswered_turns_settle_without_a_reply(adapter, overrides):
    gateway = Gateway(adapter, store=MemoryStore(), turn=lambda *a, **k: pytest.fail('turn ran'))

    async def run():
        result = await gateway.webhook(*signed(turn(**overrides)))
        # The acknowledgement does not wait for Keiki; the settle runs right after it.
        assert not calls(adapter, '/complete')
        await asyncio.sleep(0.05)
        return result

    result = asyncio.run(run())
    assert not result['jobs'] and not adapter.sent
    (complete,) = calls(adapter, '/turns/turn-1/complete')
    assert complete[2]['json'] == {'status': 'completed'}


@pytest.mark.parametrize(
    'event',
    [
        {'type': 'keiki.turn.cancelled', 'turnId': 'turn-1', 'agentId': AGENT, 'conversationId': '+1555'},
        {'type': 'keiki.reaction', 'version': 1, 'eventId': 'e', 'agentId': AGENT, 'conversationId': '+1555'},
    ],
)
def test_non_turn_events_are_acknowledged_without_calls(adapter, event):
    gateway = Gateway(adapter, store=MemoryStore())
    assert not asyncio.run(gateway.webhook(*signed(event)))['jobs']
    assert not adapter.transport.calls


def test_event_for_another_agent_is_rejected(adapter):
    with pytest.raises(PermissionError):
        asyncio.run(Gateway(adapter, store=MemoryStore()).webhook(*signed(turn(agentId='someone-else'))))


def test_reply_uses_turn_scoped_api_and_settles(adapter, monkeypatch):
    from utils.messaging import history
    from utils.observability.journeys import ClientJourneyAttempt

    monkeypatch.setattr(history, 'recent_activity', lambda *a: [])
    store = MemoryStore()
    code = '0123456789ABCDEF0123456789ABCDEF'
    proof = store.mint('user', 'imessage', 'keiki', 'code')['proof']
    store.proofs[code] = store.proofs.pop(proof)
    outcome = {'fail': False}

    def run_turn(*args, **kwargs):
        async def source():
            if outcome['fail']:
                raise RuntimeError('Synthetic tool failure')
            yield 'done: ' + base64.b64encode(json.dumps({'text': 'Synthetic answer'}).encode()).decode() + '\n\n'

        return ClientJourneyAttempt('mobile_chat', 'unknown').observe_stream(
            source(),
            success_when=lambda frame: frame.startswith('done: '),
            failure_when=lambda frame: frame.startswith('error: '),
        )

    gateway = Gateway(adapter, store=store, turn=run_turn, admission=lambda u, c: None, rate_limit=lambda u: None)

    async def deliver(turn_id, text):
        return (await gateway.webhook(*signed(turn(turn_id, text))))['jobs'][0]

    async def run():
        assert await gateway.process(await deliver('turn-link', 'link ' + code))
        assert adapter.sent[-1]['text'] == 'Account linked. You can chat with Omi here.'
        assert calls(adapter, '/turns/turn-link/complete')[-1][2]['json'] == {'status': 'completed'}

        assert await gateway.process(await deliver('turn-2', 'What are my tasks today?'))
        (message,) = calls(adapter, '/turns/turn-2/messages')
        method, url, kwargs = message
        assert (method, url) == ('POST', BASE + '/turns/turn-2/messages')
        assert kwargs['headers']['Authorization'].startswith('Bearer kts1.')
        assert kwargs['json']['text'] == 'Synthetic answer' and kwargs['json']['idempotencyKey']
        assert calls(adapter, '/turns/turn-2/typing')
        assert calls(adapter, '/turns/turn-2/complete')[-1][2]['json'] == {'status': 'completed'}

        outcome['fail'] = True
        await gateway.process(await deliver('turn-3', 'and tomorrow?'))
        assert calls(adapter, '/turns/turn-3/complete')[-1][2]['json'] == {'status': 'failed'}

    asyncio.run(run())


def test_unsupported_thread_falls_back_before_send(adapter):
    message = adapter.parse(json.dumps(turn()).encode())[0]
    adapter.ledger.received.add((message.external_chat_id, message.provider_message_id))
    from utils.messaging.delivery_context import send_first_chunk

    adapter.transport.responses = [(400, {'error': 'unsupported'}, {}), (200, {'ok': True, 'messageId': 'k1'}, {})]

    async def run():
        token = send_first_chunk.set(True)
        try:
            from dataclasses import replace

            await adapter.send(replace(message, callback_id='tap'), text='hi')
        finally:
            send_first_chunk.reset(token)

    asyncio.run(run())
    first, second = calls(adapter, '/messages')
    assert first[2]['json']['replyToMessageId'] == 'msg-turn-1'
    assert 'replyToMessageId' not in second[2]['json']
    assert first[2]['json']['idempotencyKey'] == second[2]['json']['idempotencyKey']


def test_closed_turn_and_ambiguous_send_fail_closed(adapter):
    message = adapter.parse(json.dumps(turn()).encode())[0]
    adapter.ledger.received.add((message.external_chat_id, message.provider_message_id))
    adapter.transport.responses = [(409, {'error': 'turn_closed'}, {})]
    with pytest.raises(ProviderError):
        asyncio.run(adapter.send(message, text='late'))
    adapter.transport.responses = [(502, {'error': 'delivery_failed', 'retryable': False}, {})]
    with pytest.raises(ProviderError):
        asyncio.run(adapter.send(message, text='maybe sent'))
    assert len(calls(adapter, '/messages')) == 2  # the ambiguous send is never replayed


def test_settle_tolerates_a_turn_keiki_already_closed(adapter):
    adapter.transport.responses = [(409, {'error': 'turn_closed'}, {})]
    message = adapter.parse(json.dumps(turn()).encode())[0]
    asyncio.run(adapter.settled(message, True))


def test_react_maps_tapbacks_to_the_current_message(adapter):
    message = adapter.parse(json.dumps(turn()).encode())[0]
    adapter.ledger.received.add((message.external_chat_id, message.provider_message_id))
    asyncio.run(adapter.action(message, 'react', 'love'))
    (react,) = calls(adapter, '/actions')
    assert react[2]['json'] == {
        'action': 'react',
        'messageId': 'msg-turn-1',
        'emoji': '❤️',
        'idempotencyKey': react[2]['json']['idempotencyKey'],
    }
    with pytest.raises(ValueError):
        asyncio.run(adapter.action(message, 'react', 'rocket'))
    assert [t.name for t in adapter.tools(None)] == ['imessage_react']


def test_whatsapp_channel_and_runtime_wiring(monkeypatch):
    from utils.messaging.adapters import runtime

    monkeypatch.setenv('OMI_MESSAGING_CHANNEL_POLICY', json.dumps({'whatsapp': {'enabled': True, 'cohort': []}}))
    monkeypatch.setenv('OMI_WHATSAPP_ENABLED', 'on')
    monkeypatch.setenv('KEIKI_WHATSAPP_AGENT_ID', 'agent-omi-whatsapp')
    monkeypatch.setenv('KEIKI_WHATSAPP_SIGNING_SECRET', SECRET)
    (adapter,) = runtime.configured_adapters()
    assert (adapter.channel, adapter.provider) == ('whatsapp', 'keiki')
    assert adapter.capabilities.free_reply_window is not None
    wa = turn(agentId='agent-omi-whatsapp', channel={'channel': 'whatsapp'}, conversationId='wa:+15555550123')
    assert adapter.parse(json.dumps(wa).encode())[0].channel == 'whatsapp'
    assert not adapter.parse(json.dumps(dict(wa, channel={'channel': 'imessage'})).encode())

    monkeypatch.setenv('OMI_WHATSAPP_PROVIDER', 'meta')
    with pytest.raises(ValueError):
        runtime.configured_adapters()


def test_imessage_provider_switch(monkeypatch):
    from utils.messaging.adapters import runtime

    monkeypatch.setenv(
        'OMI_MESSAGING_CHANNEL_POLICY', json.dumps({'imessage': {'enabled': True, 'cohort': [], 'seat_cap': 'off'}})
    )
    monkeypatch.setenv('OMI_IMESSAGE_ENABLED', 'on')
    monkeypatch.setenv('OMI_IMESSAGE_PROVIDER', 'keiki')
    monkeypatch.setenv('KEIKI_IMESSAGE_AGENT_ID', AGENT)
    monkeypatch.setenv('KEIKI_IMESSAGE_SIGNING_SECRET', SECRET)
    (adapter,) = runtime.configured_adapters()
    assert (adapter.channel, adapter.provider) == ('imessage', 'keiki')
    monkeypatch.setenv('OMI_IMESSAGE_PROVIDER', 'sendblue')
    with pytest.raises(ValueError):
        runtime.configured_adapters()


def test_failed_settle_is_counted(adapter):
    from utils.messaging.metrics import FAILURES

    gateway = Gateway(adapter, store=MemoryStore())
    message = adapter.parse(json.dumps(turn()).encode())[0]
    before = FAILURES.labels('imessage', 'settle_failed')._value.get()
    adapter.transport.responses = [(500, {'error': 'x'}, {})] * 4
    asyncio.run(gateway._settle_provider_turn(message, True))
    assert FAILURES.labels('imessage', 'settle_failed')._value.get() == before + 1


def test_expired_rows_settle_their_turn(adapter, monkeypatch):
    store = MemoryStore()
    gateway = Gateway(adapter, store=store)
    message = adapter.parse(json.dumps(turn('turn-old')).encode())[0]
    from dataclasses import asdict

    payload = dict(asdict(message), received_at=message.received_at.isoformat())
    monkeypatch.setattr(store, 'claim_expired', lambda channel, provider: [payload])
    asyncio.run(gateway.expired_notices())
    assert calls(adapter, '/turns/turn-old/complete')[-1][2]['json'] == {'status': 'failed'}


def test_failed_declined_settle_is_counted(adapter):
    from utils.messaging.metrics import FAILURES

    gateway = Gateway(adapter, store=MemoryStore())
    before = FAILURES.labels('imessage', 'settle_failed')._value.get()
    adapter.transport.responses = [(500, {'error': 'x'}, {})] * 4
    with pytest.raises(ProviderError):
        asyncio.run(gateway._settle_unhandled(signed(turn(heldBack=True))[0]))
    assert FAILURES.labels('imessage', 'settle_failed')._value.get() == before + 1
