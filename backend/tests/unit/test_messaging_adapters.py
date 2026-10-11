"""Provider fixtures and Stage A contracts; all network IO is replayed."""

import asyncio
import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from testing.messaging.adapter_contract import AdapterContract
from testing.messaging.adapter_fakes import FixtureTransport, FixtureLedger, no_sleep
from testing.messaging.store import MemoryStore
from utils.messaging.adapters.telegram import TelegramAdapter
from utils.messaging.adapters.linq import LinqProvider, IMessageAdapter
from utils.messaging.adapters.rendering import source_phrases, split_text
from utils.messaging.adapters.transport import Transport, DeliveryUncertain, ProviderError
from utils.messaging.contracts import Artifact, Principal
from utils.messaging.gateway import Gateway
from utils.messaging.outbound import ChannelReplySink
from utils.messaging.projection import SurfaceRuntime, surface_runtime, ToolProjection

FIXTURES = Path(__file__).parents[1] / 'fixtures' / 'messaging' / 'adapters'
SECRET = b'synthetic-test-signing-secret-32'


def fixture(provider, kind='text'):
    return (FIXTURES / f'{provider}-{kind}.json').read_bytes()


def signed(adapter, body, *, timestamp=None):
    if adapter.channel == 'telegram':
        return body, {'X-Telegram-Bot-Api-Secret-Token': 'fixture_secret'}
    stamp = str(int(time.time()) if timestamp is None else timestamp)
    value = base64.b64encode(
        hmac.new(SECRET, b'fixture-id.' + stamp.encode() + b'.' + body, hashlib.sha256).digest()
    ).decode()
    return body, {'webhook-id': 'fixture-id', 'webhook-timestamp': stamp, 'webhook-signature': 'v1,' + value}


@pytest.fixture(params=['telegram', 'linq'])
def adapter(request, monkeypatch):
    transport, ledger = FixtureTransport(), FixtureLedger()
    if request.param == 'telegram':
        result = TelegramAdapter(
            '000:fixture-token', 'fixture_secret', transport=transport, ledger=ledger, sleep=no_sleep
        )
    else:
        provider = LinqProvider(
            'fixture-api-key',
            'whsec_' + base64.b64encode(SECRET).decode(),
            transport=transport,
            sleep=no_sleep,
            upload_hosts={'uploads.linqapp.com'},
        )
        result = IMessageAdapter(provider, transport=transport, ledger=ledger, sleep=no_sleep)
    result.sent = []
    send = result.send

    async def record(message, *, text=None, artifact=None, draft=False):
        result.sent.append(dict(message=message, text=text, artifact=artifact, draft=draft))
        await send(message, text=text, artifact=artifact, draft=draft)

    async def owned_bytes(artifact):
        return b'abc'

    # Artifact ownership is exercised independently; the contract's artifact is synthetic.
    monkeypatch.setattr(result, 'owned_bytes', owned_bytes)
    monkeypatch.setattr(result, 'send', record)
    return result


@pytest.fixture
def signed_message(adapter):
    provider = 'telegram' if adapter.channel == 'telegram' else 'linq'

    def create():
        body = fixture(provider)
        # A direct contract sink does not enqueue an inbound job. Pre-credit its
        # synthetic initiating message, as the worker would do before any send.
        message = adapter.parse(body)[0]
        adapter.ledger.received.add((message.external_chat_id, message.provider_message_id))
        return signed(adapter, body)

    return create


class TestProviderContracts(AdapterContract):
    pass


@pytest.mark.parametrize(
    'failure',
    [
        None,
        'rejected',
        'failure_rejected',
        'error_frame',
        'error_fallback',
        'empty',
        'cancelled',
        'tool',
        'timeout',
        'unavailable',
        'completion',
        'history',
    ],
)
def test_linq_link_then_reply_and_next_turn_after_failure(adapter, monkeypatch, failure, caplog):
    if adapter.channel != 'imessage':
        return
    from contextvars import ContextVar
    from utils.messaging import history
    from utils.observability.journeys import ClientJourneyAttempt

    monkeypatch.setattr(history, 'recent_activity', lambda *a: [])
    store = MemoryStore()
    fallback_outcomes = []
    from utils.messaging import gateway as gateway_module

    monkeypatch.setattr(gateway_module, 'record_fallback', lambda **values: fallback_outcomes.append(values['outcome']))
    complete = store.complete

    def complete_job(path):
        if failure == 'completion' and store.jobs[path].get('payload', {}).get('provider_message_id') == 'first':
            raise RuntimeError('Synthetic completion failure')
        complete(path)

    monkeypatch.setattr(store, 'complete', complete_job)
    code = '0123456789ABCDEF0123456789ABCDEF'
    proof = store.mint('user', 'imessage', 'linq', 'code')['proof']
    store.proofs[code] = store.proofs.pop(proof)
    append_event = store.append_event
    history_failed = False

    def append_history(uid, session_id, event):
        nonlocal history_failed
        if failure == 'history' and event['role'] == 'assistant' and not history_failed:
            history_failed = True
            raise RuntimeError('Synthetic history persistence failure')
        append_event(uid, session_id, event)

    monkeypatch.setattr(store, 'append_event', append_history)
    cleaned = []
    usage = ContextVar('fixture_usage', default=None)
    turns = []

    def turn(*args, **kwargs):
        turns.append(args)

        async def source():
            token = usage.set('user')
            try:
                if failure == 'cancelled' and len(turns) == 1:
                    raise asyncio.CancelledError
                if failure == 'tool' and len(turns) == 1:
                    raise RuntimeError('Synthetic tool failure')
                if failure == 'empty' and len(turns) == 1:
                    return
                if failure in ('error_frame', 'error_fallback') and len(turns) == 1:
                    yield 'error: {}\n\n'
                    if failure == 'error_frame':
                        return
                yield 'done: ' + base64.b64encode(json.dumps({'text': 'Synthetic answer'}).encode()).decode() + '\n\n'
            finally:
                usage.reset(token)
                cleaned.append(True)

        return ClientJourneyAttempt('chat_first_answer', 'unknown').observe_stream(
            source(),
            success_when=lambda frame: frame.startswith('done: '),
            failure_when=lambda frame: frame.startswith('error: '),
        )

    gateway = Gateway(adapter, store=store, turn=turn, admission=lambda uid: None)

    async def deliver(kind, message_id, text=None):
        value = json.loads(fixture('linq', kind))
        value['data']['id'] = message_id
        if text:
            value['data']['parts'][0]['value'] = text
        jobs = (await gateway.webhook(*signed(adapter, json.dumps(value).encode())))['jobs']
        return jobs[0]

    async def run():
        link_job = await deliver('start', 'link', f'Hi Omi, link code {code}')
        assert await gateway.process(link_job)
        assert store.jobs[link_job]['status'] == 'done'
        assert next(iter(store.identities.values()))['active']
        first = await deliver('text', 'first')
        if failure in ('rejected', 'failure_rejected'):
            # Typing succeeds, final text is rejected, typing stops, failure reply succeeds.
            adapter.transport.responses = [(200, {}, {}), (400, {'error': 'synthetic'}, {}), (200, {}, {})]
            if failure == 'failure_rejected':
                adapter.transport.responses.append((400, {'error': 'synthetic'}, {}))
        elif failure == 'timeout':
            adapter.transport.responses = (
                [(200, {}, {})] + [DeliveryUncertain('Provider transport outcome unknown')] * 4 + [(200, {}, {})]
            )
        elif failure == 'unavailable':
            adapter.transport.responses = [(200, {}, {})] + [(503, {'error': 'synthetic'}, {})] * 4 + [(200, {}, {})]
        if failure not in (None, 'error_fallback'):
            assert not await gateway.process(first)
            assert store.jobs[first]['status'] == 'running'  # no replay of ambiguous effects
            if failure in ('completion', 'history'):
                assert adapter.sent[-1]['text'] == 'Synthetic answer'
                assert fallback_outcomes == []
            else:
                assert 'could not finish' in adapter.sent[-1]['text']
                assert fallback_outcomes == ['exhausted' if failure == 'failure_rejected' else 'degraded']
                session = next(iter(store.sessions.values()))
                assert not any(e['role'] == 'assistant' for e in store.events('user', session['id']))
            assert not store.leases
            assert not await gateway.process(first)
        else:
            assert await gateway.process(first)
        assert cleaned == [True]
        assert usage.get() is None
        second = await deliver('text', 'second')
        assert await gateway.process(second)
        assert store.jobs[second]['status'] == 'done'
        assert not store.leases
        assert adapter.sent[-1]['text'] == 'Synthetic answer'

    asyncio.run(run())
    sends = [call[2]['json'] for call in adapter.transport.calls if call[1].endswith('/messages')]
    assert sends[0]['message']['parts'][0]['value'].startswith('Account linked.')
    assert all('parts' not in body and body['message']['idempotency_key'] for body in sends)
    keys = [body['message']['idempotency_key'] for body in sends]
    assert all(isinstance(item, str) and 1 <= len(item) <= 255 for item in keys)
    if failure in ('timeout', 'unavailable'):
        assert keys[1] == keys[2] == keys[3] == keys[4]
        assert len({keys[0], keys[1], keys[5], keys[6]}) == 4
    else:
        assert len(keys) == len(set(keys))
    assert 'Synthetic answer' not in caplog.text
    assert 'Synthetic tool failure' not in caplog.text
    assert code not in caplog.text
    typing = [call[0] for call in adapter.transport.calls if call[1].endswith('/typing')]
    assert typing == ['POST', 'DELETE', 'POST', 'DELETE']
    if failure not in (None, 'error_fallback'):
        reason = {
            'rejected': 'worker_error',
            'failure_rejected': 'worker_error',
            'completion': 'worker_error',
            'history': 'worker_error',
            'error_frame': 'turn_error_frame',
            'empty': 'missing_terminal_reply',
            'tool': 'worker_error',
            'timeout': 'delivery_uncertain',
            'unavailable': 'worker_error',
            'cancelled': 'turn_cancelled',
        }[failure]
        assert 'reason=' + reason in caplog.text
    if failure == 'rejected':
        assert 'status_code=400' in caplog.text
    if failure == 'unavailable':
        assert 'status_code=503' in caplog.text


def test_failed_deferred_reply_remains_fenced(adapter, monkeypatch):
    if adapter.channel != 'imessage':
        return
    from datetime import timedelta
    from utils.messaging import history
    from utils.messaging.contracts import ReentryEvent

    monkeypatch.setattr(history, 'recent_activity', lambda *a: [])
    store = MemoryStore()
    message = adapter.parse(fixture('linq'))[0]
    store.consume(store.mint('user', 'imessage', 'linq', 'code')['proof'], message)

    def turn(*args, **kwargs):
        async def stream():
            yield 'done: ' + base64.b64encode(json.dumps({'text': 'Deferred answer'}).encode()).decode() + '\n\n'

        return stream()

    gateway = Gateway(adapter, store=store, turn=turn, admission=lambda uid: None)
    principal = Principal('user', frozenset(), datetime.now(timezone.utc) + timedelta(minutes=5), 'task')
    event = ReentryEvent('event', 'Synthetic result', 'task')

    async def run():
        await adapter.admitted(message)
        adapter.transport.responses = [(200, {}, {}), (400, {}, {}), (200, {}, {})]
        with pytest.raises(ProviderError):
            await gateway.reenter(message, event, principal=principal)
        assert not store.leases
        session = next(iter(store.sessions.values()))
        events = store.events('user', session['id'])
        assert not any(e['id'] == 'reply:event' for e in events)
        assert any(e['id'] == 'failed:event' for e in events)
        assert 'could not finish' in adapter.sent[-1]['text']
        sent = len(adapter.sent)
        await gateway.reenter(message, event, principal=principal)
        assert len(adapter.sent) == sent
        assert not store.leases

    asyncio.run(run())


def test_task_cancellation_retains_lease_until_worker_stops(adapter, monkeypatch, caplog):
    if adapter.channel != 'imessage':
        return
    import threading
    from utils.messaging import history

    monkeypatch.setattr(history, 'recent_activity', lambda *a: [])
    store = MemoryStore()
    code = '0123456789ABCDEF0123456789ABCDEF'
    proof = store.mint('user', 'imessage', 'linq', 'code')['proof']
    store.proofs[code] = store.proofs.pop(proof)
    release_thread = threading.Event()
    started = threading.Event()

    def turn(*args, **kwargs):
        started.set()
        release_thread.wait(5)

        async def stream():
            yield 'done: ' + base64.b64encode(json.dumps({'text': 'Synthetic answer'}).encode()).decode() + '\n\n'

        return stream()

    gateway = Gateway(adapter, store=store, turn=turn, admission=lambda uid: None)

    async def deliver(kind, message_id, text=None):
        value = json.loads(fixture('linq', kind))
        value['data']['id'] = message_id
        if text:
            value['data']['parts'][0]['value'] = text
        return (await gateway.webhook(*signed(adapter, json.dumps(value).encode())))['jobs'][0]

    async def run():
        link_job = await deliver('start', 'link', f'Hi Omi, link code {code}')
        assert await gateway.process(link_job)
        first = await deliver('text', 'first')
        task = asyncio.create_task(gateway.process(first))
        assert await asyncio.to_thread(started.wait, 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert store.leases
        assert store.jobs[first]['status'] == 'running'
        assert 'reason=worker_cancelled' in caplog.text
        assert all('could not finish' not in (item.get('text') or '') for item in adapter.sent)
        typing = [call[0] for call in adapter.transport.calls if call[1].endswith('/typing')]
        assert typing and typing[0] == 'POST' and 'DELETE' in typing
        second = await deliver('text', 'second')
        assert not await gateway.process(second)
        assert store.jobs[second]['status'] == 'pending'
        assert store.leases
        assert code not in caplog.text

    try:
        asyncio.run(run())
    finally:
        release_thread.set()


@pytest.mark.parametrize('status,body', [(429, {}), (200, {'error_code': 429})])
def test_terminal_rate_limit_preserves_status(status, body):
    from utils.messaging.adapters.transport import request_json

    async def run():
        transport = FixtureTransport([(status, body, {'Retry-After': '61'})])
        with pytest.raises(ProviderError) as error:
            await request_json(transport, 'POST', 'https://api.linqapp.com/synthetic', sleep=no_sleep)
        assert error.value.status_code == 429

    asyncio.run(run())


@pytest.mark.parametrize(
    'kind',
    ['text', 'voice', 'photo', 'document', 'edited', 'start', 'unlink', 'unknown_sender', 'duplicate', 'bad_signature'],
)
def test_golden_payloads(adapter, kind):
    provider = 'telegram' if adapter.channel == 'telegram' else 'linq'
    body = fixture(provider, kind)
    body, headers = signed(adapter, body)
    if kind == 'bad_signature':
        headers = {name: 'invalid' for name in headers}
        assert not adapter.verify_webhook(body, headers)
        return
    assert adapter.verify_webhook(body, headers)
    messages = adapter.parse(body)
    if kind == 'edited':
        assert not messages
        return
    assert len(messages) == 1
    message = messages[0]
    assert (message.channel, message.provider) == (adapter.channel, adapter.provider)
    if kind in ('voice', 'photo', 'document'):
        assert len(message.attachments) == 1
        assert message.attachments[0].voice == (kind == 'voice')
    if kind == 'start':
        assert message.link_proof
    if kind == 'unlink':
        assert message.unlink
    if kind == 'duplicate':
        assert message.provider_message_id == adapter.parse(fixture(provider))[0].provider_message_id


def test_linq_signatures_rotation_raw_body_and_replay(adapter):
    if adapter.channel != 'imessage':
        return
    body, headers = signed(adapter, fixture('linq'))
    assert not adapter.verify_webhook(body + b' ', headers)
    headers['webhook-signature'] = 'v1,invalid ' + headers['webhook-signature']
    assert adapter.verify_webhook(body, headers)
    for age in (-301, 301):
        body, headers = signed(adapter, body, timestamp=int(time.time()) + age)
        assert not adapter.verify_webhook(body, headers)
    assert not adapter.verify_webhook(
        body, {'X-Webhook-Signature': 'fake', 'X-Webhook-Timestamp': str(int(time.time()))}
    )


def test_groups_bots_outbound_edits_are_not_turns(adapter):
    if adapter.channel == 'telegram':
        value = json.loads(fixture('telegram'))
        value['message']['chat']['type'] = 'group'
        assert not adapter.parse(json.dumps(value).encode())
        value['message']['chat']['type'] = 'private'
        value['message']['from']['is_bot'] = True
    else:
        value = json.loads(fixture('linq'))
        value['data']['chat']['is_group'] = True
        assert not adapter.parse(json.dumps(value).encode())
        value['data']['chat']['is_group'] = False
        value['data']['direction'] = 'outbound'
    assert not adapter.parse(json.dumps(value).encode())


def test_linq_link_code_is_extracted_from_surrounding_text(adapter):
    if adapter.channel != 'imessage':
        return
    code = '0123456789ABCDEF0123456789ABCDEF'
    value = json.loads(fixture('linq', 'start'))
    value['data']['parts'][0]['value'] = f'Your Omi code is {code}. Tap to connect.'
    message = adapter.parse(json.dumps(value).encode())[0]
    assert message.link_proof == code
    assert not message.unlink
    value['data']['parts'][0]['value'] = f'{code} and {code}'
    assert adapter.parse(json.dumps(value).encode())[0].link_proof is None
    value['data']['parts'][0]['value'] = code + 'AA'
    assert adapter.parse(json.dumps(value).encode())[0].link_proof is None


def test_telegram_username_is_a_display_handle(adapter):
    if adapter.channel != 'telegram':
        return
    value = json.loads(fixture('telegram'))
    value['message']['from']['username'] = '@OmiFriend'
    assert adapter.parse(json.dumps(value).encode())[0].display_name == '@OmiFriend'
    value['message']['from'].pop('username')
    assert adapter.parse(json.dumps(value).encode())[0].display_name is None


def test_voice_notes_off_does_not_run_a_turn(adapter):
    if adapter.channel != 'telegram':
        return
    from utils.messaging.contracts import ChannelMessage, InboundAttachment

    store = MemoryStore()
    message = ChannelMessage(
        adapter.channel,
        adapter.provider,
        'fixture-user',
        'fixture-chat',
        'voice-1',
        '',
        datetime.now(timezone.utc),
        attachments=(InboundAttachment('file', 'voice.ogg', 'audio/ogg', 12, True),),
    )
    store.identities[(message.channel, message.provider, message.external_user_id)] = dict(
        uid='user', active=True, generation='gen', voice_notes=False
    )
    path = store.enqueue(message)
    turns = []

    async def turn(*args, **kwargs):
        turns.append(args)

    gateway = Gateway(adapter, store=store, turn=turn, admission=lambda uid: None)
    asyncio.run(gateway.process(path))
    assert turns == []
    assert 'Voice notes are turned off' in adapter.sent[-1]['text']


def test_linq_legacy_payload_version(adapter):
    if adapter.channel != 'imessage':
        return
    value = json.loads(fixture('linq'))
    value['webhook_version'] = '2025-01-01'
    value['data'] = dict(
        chat_id='fixture-chat',
        **{'from': '+12025550101'},
        is_group=False,
        is_from_me=False,
        message=dict(id='fixture-message', parts=[dict(type='text', value='legacy')]),
    )
    assert adapter.parse(json.dumps(value).encode())[0].text == 'legacy'


def test_renderers_escape_split_and_citations(adapter):
    text = 'A [1] source. **Hello** _world_! ' + '😀' * 5000
    parts = adapter.render(text)
    assert len(parts) > 1
    assert all(len(p.encode('utf-16-le')) // 2 <= adapter.capabilities.max_text_len for p in parts)
    assert '[1]' not in ''.join(parts)
    assert not any(p.endswith('\\') for p in parts)
    assert source_phrases('See [1]', [{'title': 'Weekly review'}]) == 'See '
    assert ''.join(split_text('a b\n😀' * 10, 8)) == 'a b\n😀' * 10


def test_telegram_stable_draft_and_final_committed(adapter):
    if adapter.channel != 'telegram':
        return
    message = adapter.parse(fixture('telegram'))[0]

    async def run():
        await adapter.admitted(message)
        await adapter.send(message, text='hello', draft=True)
        await adapter.send(message, text='hello again', draft=True)
        await adapter.send(message, text='hello again')

    asyncio.run(run())
    calls = adapter.transport.calls
    assert calls[0][1].endswith('/sendMessageDraft') and calls[1][1].endswith('/sendMessageDraft')
    assert calls[0][2]['json']['draft_id'] == calls[1][2]['json']['draft_id'] != 0
    assert calls[-1][1].endswith('/sendMessage')


def responses(*names):
    data = json.loads((FIXTURES / 'responses.json').read_text())
    return [(data[name]['status'], data[name]['body'], data[name]['headers']) for name in names]


def test_replayed_429_then_success(adapter):
    message = adapter.parse(fixture(adapter.provider))[0]
    adapter.transport.responses = responses('rate_limit', 'telegram_ok' if adapter.channel == 'telegram' else 'linq_ok')
    delays = []

    async def sleep(delay):
        delays.append(delay)

    adapter.sleep = sleep
    if adapter.channel == 'imessage':
        adapter.client.sleep = sleep

    async def run():
        await adapter.admitted(message)
        await adapter.send(message, text='safe')

    asyncio.run(run())
    assert len(adapter.transport.calls) == 2 and 2 in delays
    assert adapter.ledger.sent == 1


def test_ambiguous_5xx_fail_closed_or_idempotent(adapter):
    message = adapter.parse(fixture(adapter.provider))[0]
    adapter.transport.responses = responses('server_error', 'linq_ok')

    async def run():
        await adapter.admitted(message)
        if adapter.channel == 'telegram':
            with pytest.raises(DeliveryUncertain):
                await adapter.send(message, text='safe')
            with pytest.raises(RuntimeError, match='reconciliation'):
                await adapter.send(message, text='safe')
            assert len(adapter.transport.calls) == 1
        else:
            await adapter.send(message, text='safe')
            assert len(adapter.transport.calls) == 2
            assert (
                adapter.transport.calls[0][2]['json']['message']['idempotency_key']
                == adapter.transport.calls[1][2]['json']['message']['idempotency_key']
            )

    asyncio.run(run())


def test_linq_ratio_all_messages_count_typing_does_not(adapter):
    if adapter.channel != 'imessage':
        return
    message = adapter.parse(fixture('linq'))[0]

    async def run():
        with pytest.raises(PermissionError):
            await adapter.send(message, text='no unsolicited sends')
        await adapter.admitted(message)
        await adapter.admitted(message)
        await adapter.typing(message)
        assert adapter.ledger.sent == 0
        for i in range(3):
            await adapter.send(message, text=f'status {i}')
        with pytest.raises(PermissionError):
            await adapter.send(message, text='fourth')
        assert adapter.ledger.sent == 3

    asyncio.run(run())


def test_tools_advertise_and_execute_only_on_guarded_linked_chat(adapter):
    message = adapter.parse(fixture(adapter.provider))[0]
    checks = []

    async def guard():
        checks.append(True)

    sink = ChannelReplySink(adapter, message, guard=guard)
    tools = adapter.tools(sink)
    projection = ToolProjection.build((), tools, (), principal=Principal('test'))
    assert all('chat_id' not in tool.args for tool in tools)

    async def run():
        await adapter.admitted(message)
        reaction = '👍' if adapter.channel == 'telegram' else 'like'
        await projection.authorize('test', adapter.channel + '_react').ainvoke({'emoji': reaction})

    asyncio.run(run())
    assert len(checks) >= 2
    with pytest.raises(PermissionError):
        projection.authorize('other', adapter.channel + '_react')


def test_followups_buttons_and_citation_source_prose(adapter):
    message = adapter.parse(fixture(adapter.provider))[0]

    async def run():
        await adapter.admitted(message)
        await ChannelReplySink(adapter, message).finish_payload(
            {
                'text': 'Found [1].',
                'conversations': [{'id': 'conv-1', 'title': 'Daily standup'}],
                'follow_up_suggestions': ['Explain more', 'x' * 80],
            }
        )

    asyncio.run(run())
    payload = adapter.transport.calls[-1][2]['json']
    if adapter.channel == 'telegram':
        assert payload['reply_markup']['inline_keyboard'][0][0] == {
            'text': 'Daily standup',
            'url': 'https://h.omi.me/conversation/conv-1',
        }
        assert '[1]' not in payload['text']
    else:
        assert 'Open in Omi: https://h.omi.me/conversation/conv-1' in payload['message']['parts'][0]['value']
        assert 'Explain more' not in str(payload)


def test_many_items_are_one_imessage_link_or_bounded_telegram_buttons(adapter):
    message = adapter.parse(fixture(adapter.provider))[0]
    conversations = [{'id': f'id {index}', 'kind': 'task', 'title': f'Task {index}'} for index in range(6)]

    async def run():
        await adapter.admitted(message)
        await ChannelReplySink(adapter, message).finish_payload(
            {'text': 'Tasks [#1][#2].', 'conversations': conversations}
        )

    asyncio.run(run())
    payload = adapter.transport.calls[-1][2]['json']
    if adapter.channel == 'telegram':
        rows = payload['reply_markup']['inline_keyboard']
        assert len(rows) == 6
        assert rows[-1] == [{'text': 'Open in Omi', 'url': 'https://h.omi.me'}]
        assert all(row[0]['url'].startswith('https://h.omi.me/task/id%20') for row in rows[:-1])
        assert '[#1]' not in payload['text']
        assert payload['text'].count('https://') == 0
    else:
        body = payload['message']['parts'][0]['value']
        assert body.count('https://') == 1
        assert 'Open in Omi: https://h.omi.me' in body
        assert '/task/' not in body
        assert '[#1]' not in body


def test_media_fetch_bounds_and_ssrf(monkeypatch):
    # No network occurs: validation happens before the shared client is requested.
    transport = Transport()
    for url in [
        'http://cdn.linqapp.com/x',
        'https://127.0.0.1/x',
        'https://cdn.linqapp.com.evil/x',
        'https://user@cdn.linqapp.com/x',
    ]:
        with pytest.raises(PermissionError):
            asyncio.run(transport.download(url, allowed_hosts={'cdn.linqapp.com'}))


def test_real_followup_wire_block_and_source_title(adapter):
    message = adapter.parse(fixture(adapter.provider))[0]

    async def run():
        await adapter.admitted(message)
        await ChannelReplySink(adapter, message).finish_payload(
            {
                'text': 'See [1].',
                'memories': [{'id': 'conv-1', 'structured': {'title': 'Team meeting'}}],
                'content_blocks': [{'type': 'followUp', 'id': 'synthetic:followup', 'text': 'What changed?'}],
            }
        )

    asyncio.run(run())
    payload = adapter.transport.calls[-1][2]['json']
    if adapter.channel == 'telegram':
        assert '[1]' not in payload['text']
        assert payload['reply_markup']['inline_keyboard'][0][0]['text'] == 'Team meeting'
        assert payload['reply_markup']['inline_keyboard'][0][0]['url'] == 'https://h.omi.me/conversation/conv-1'
    else:
        assert 'What changed?' not in str(payload)
        assert 'Open in Omi: https://h.omi.me/conversation/conv-1' in payload['message']['parts'][0]['value']


def test_revocation_during_429_backoff_blocks_retry(adapter):
    message = adapter.parse(fixture(adapter.provider))[0]
    adapter.transport.responses = responses('rate_limit', 'telegram_ok')
    active = True

    async def guard():
        if not active:
            raise PermissionError('Link revoked')

    async def sleep(delay):
        nonlocal active
        active = False

    adapter.sleep = sleep
    if adapter.channel == 'imessage':
        adapter.client.sleep = sleep

    async def run():
        await adapter.admitted(message)
        with pytest.raises(PermissionError, match='revoked'):
            await ChannelReplySink(adapter, message, guard=guard).finish('hello')

    asyncio.run(run())
    assert len(adapter.transport.calls) == 1


def test_media_prepare_stt_and_searchable_file_ids(adapter, monkeypatch):
    from database import chat
    from utils.messaging.adapters.media import ChatMediaStore
    from utils.stt import pre_recorded

    calls = []
    media = ChatMediaStore()
    monkeypatch.setattr(
        pre_recorded,
        'prerecorded_from_bytes',
        lambda data, **kwargs: [{'word': 'voice'}, {'punctuated_word': 'transcribed.'}],
    )

    def ingest(uid, attachment, data):
        calls.append(('ingest', uid, attachment.mime_type, data))
        return Artifact('owned-file-id', attachment.mime_type, len(data), attachment.name)

    monkeypatch.setattr(media, 'ingest', ingest)
    monkeypatch.setattr(
        chat, 'add_files_to_chat_session', lambda uid, session, ids: calls.append(('session', uid, session, ids))
    )
    adapter.media = media
    checks = []

    async def guard():
        checks.append(True)

    async def run():
        voice = adapter.parse(fixture(adapter.provider, 'voice'))[0]
        result = await adapter.prepare(voice, 'test', {'id': 'surface-session'}, guard)
        assert 'voice transcribed.' in result.text and not result.attachments
        document = adapter.parse(fixture(adapter.provider, 'document'))[0]
        result = await adapter.prepare(document, 'test', {'id': 'surface-session'}, guard)
        assert result.media[0].file_store_ref == 'owned-file-id'

    asyncio.run(run())
    assert ('session', 'test', 'surface-session', ['owned-file-id']) in calls
    assert len(checks) >= 4


def test_owned_artifact_rejects_foreign_ids_metadata_and_oversize(monkeypatch):
    from database import chat
    from utils.messaging.adapters.media import ChatMediaStore
    from utils.other import chat_file

    artifact = Artifact('file', 'text/plain', 3, 'a.txt')
    store = ChatMediaStore()
    queried = []

    def rows(uid, ids):
        queried.append((uid, ids))
        return []

    monkeypatch.setattr(chat, 'get_chat_files', rows)
    with pytest.raises(PermissionError):
        store.resolve('test', artifact)
    assert queried == [('test', ['file'])]
    monkeypatch.setattr(chat, 'get_chat_files', lambda *a: [{'name': 'a.txt', 'mime_type': 'image/jpeg'}])
    with pytest.raises(PermissionError):
        store.resolve('test', artifact)
    monkeypatch.setattr(chat, 'get_chat_files', lambda *a: [{'name': 'a.txt', 'mime_type': 'text/plain'}])
    monkeypatch.setattr(chat_file, 'download_owned_chat_file', lambda *a, **k: b'wrong size')
    with pytest.raises(ValueError):
        store.resolve('test', artifact)


def test_chart_exclusion_uses_same_authority_and_keeps_app():
    from utils.messaging.projection import project_runtime_tools
    from langchain_core.tools import StructuredTool

    def chart(data: str) -> str:
        """Render a chart."""
        return data

    tool = StructuredTool.from_function(name='create_chart_tool', func=chart)
    channel = SurfaceRuntime('channel:test', '', Principal('test'))
    projection = project_runtime_tools(channel, [tool], [], [], [])
    assert not projection.registry
    with pytest.raises(PermissionError):
        projection.authorize('test', 'create_chart_tool')
    app = replace(channel, surface='app')
    assert project_runtime_tools(app, [tool], [], [], []).authorize('test', 'create_chart_tool') is tool


def test_off_by_default_runtime_and_live_config_safety(monkeypatch):
    from utils.messaging.adapters.runtime import configured_adapters
    from testing.messaging.live_adapters import validate_config

    monkeypatch.delenv('OMI_MESSAGING_CHANNELS', raising=False)
    monkeypatch.setenv('OMI_TELEGRAM_ENABLED', 'on')
    assert configured_adapters() == ()
    config = dict(
        test_uid='synthetic-test',
        test_account_verified=True,
        telegram_test_user_id='101',
        linq_test_handle='+12025550101',
        telegram_dev_bot_id='100',
        linq_dev_line='+12025550102',
        webhook_origin='https://qa.example.test',
        secret_project='based-hardware-dev',
    )
    assert validate_config(config) == config
    for field, value in [
        ('test_account_verified', False),
        ('secret_project', 'based-hardware'),
        ('webhook_origin', 'https://api.omi.me'),
    ]:
        with pytest.raises(ValueError):
            validate_config({**config, field: value})


def test_app_writes_do_not_create_undo_or_channel_capture(monkeypatch):
    from utils.messaging import undo
    from utils.retrieval.tools import preference_tools

    called = []
    monkeypatch.setattr(preference_tools, 'capture_memory_write', lambda **kwargs: called.append(kwargs))
    token = surface_runtime.set(SurfaceRuntime('channel:test', '', Principal('test')))
    try:
        preference_tools._capture_app_memory_write(content='synthetic')
        assert not called
    finally:
        surface_runtime.reset(token)
    assert undo.record_write('test', 'task', 'id', None, {}) == ''
    preference_tools._capture_app_memory_write(content='synthetic')
    assert len(called) == 1


def test_adapter_http_routes_authenticate_before_admission(adapter, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import messaging

    gateway = Gateway(adapter, store=MemoryStore(), turn=lambda *a, **k: pytest.fail('Turn before HTTP ACK'))
    monkeypatch.setattr(messaging, '_gateways', {'provider-test': gateway})
    app = FastAPI()
    app.include_router(messaging.router)
    body, headers = signed(adapter, fixture(adapter.provider))
    with TestClient(app) as client:
        assert client.post('/v1/messaging/webhooks/provider-test', content=body, headers=headers).status_code == 202
        assert client.post('/v1/messaging/webhooks/provider-test', content=body, headers=headers).status_code == 202
        assert len(gateway.store.jobs) == 1
        assert not adapter.transport.calls
        assert client.post('/v1/messaging/webhooks/provider-test', content=body, headers={}).status_code == 401
        assert client.post('/v1/messaging/webhooks/missing', content=body, headers=headers).status_code == 404
        assert (
            client.post('/v1/messaging/webhooks/provider-test', content=b'x' * 1_000_001, headers=headers).status_code
            == 413
        )


def test_memory_inverse_uses_universal_service_and_fails_closed(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from database import _client
    from utils.memory import canonical_memory_adapter, memory_service
    from utils.messaging.undo import apply_inverse

    monkeypatch.setattr(_client, 'get_data_plane_firestore_client', lambda: object())
    item = SimpleNamespace(content='after', superseded_by=None, status=SimpleNamespace(value='active'))
    monkeypatch.setattr(canonical_memory_adapter, 'read_canonical_memory_item', lambda *a, **k: item)
    service = MagicMock()
    monkeypatch.setattr(memory_service, 'MemoryService', lambda **kwargs: service)
    payload = {'kind': 'memory', 'object_id': 'owned', 'before': 'before', 'after': 'after'}
    apply_inverse('test', payload)
    assert service.update_external_memory_content.call_args.args == ('test', 'owned', 'before')
    apply_inverse('test', {**payload, 'before': None})
    assert service.delete_external_memory.call_args.args == ('test', 'owned')
    item.content = 'concurrent change'
    with pytest.raises(PermissionError):
        apply_inverse('test', payload)
    assert service.update_external_memory_content.call_count == 1
    apply_inverse('test', {'kind': 'memory_closed', 'object_id': 'owned', 'operation_id': 'synthetic-op'})
    service.reopen_standalone_closed_ledger_fact.assert_called_once_with('test', 'owned', 'synthetic-op')


def test_provider_http_logs_filter_credential_urls():
    import logging
    from utils.messaging.adapters.transport import ProviderLogFilter

    filter_ = ProviderLogFilter()
    record = logging.LogRecord(
        'httpx', logging.INFO, '', 0, 'HTTP POST %s', ('https://api.telegram.org/botSECRET/sendMessage',), None
    )
    assert not filter_.filter(record)
    assert filter_.filter(logging.LogRecord('httpx', logging.INFO, '', 0, 'unrelated request', (), None))


def test_telegram_definite_html_rejection_falls_back_once():
    transport = FixtureTransport([(400, {'ok': False, 'description': "Bad Request: can't parse entities"}, {})])
    adapter = TelegramAdapter('000:fixture-token', 'fixture_secret', transport=transport, sleep=no_sleep)
    asyncio.run(adapter.api('sendMessage', {'chat_id': 'fixture', 'text': '<b>A &amp; B</b>', 'parse_mode': 'HTML'}))
    assert len(transport.calls) == 2
    first, second = [call[2]['json'] for call in transport.calls]
    assert first['parse_mode'] == 'HTML'
    assert second == {'chat_id': 'fixture', 'text': 'A & B'}


@pytest.mark.parametrize('status', [400, 500])
def test_telegram_other_failure_never_replays_send_as_plain(status):
    transport = FixtureTransport([(status, {'ok': False, 'description': 'unrelated rejection'}, {})])
    adapter = TelegramAdapter('000:fixture-token', 'fixture_secret', transport=transport, sleep=no_sleep)
    with pytest.raises(ProviderError):
        asyncio.run(adapter.api('sendMessage', {'chat_id': 'fixture', 'text': '<b>A</b>', 'parse_mode': 'HTML'}))
    assert len(transport.calls) == 1
