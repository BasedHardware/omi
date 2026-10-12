"""Execute the real gateway, sinks and provider payloads with hermetic IO."""

import asyncio
import base64
import json
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from testing.messaging.adapter_fakes import FixtureLedger, FixtureTransport, no_sleep
from testing.messaging.store import MemoryStore
from utils.messaging import gateway as gateway_module
from utils.messaging.adapters.linq import IMessageAdapter, LinqProvider
from utils.messaging.adapters.telegram import TelegramAdapter
from utils.messaging.adapters.transport import DeliveryUncertain
from utils.messaging.contracts import ChannelMessage
from utils.messaging.gateway import Gateway
from utils.messaging.outbound import ChannelReplySink


@pytest.fixture(params=['telegram', 'imessage'])
def adapter(request):
    transport, ledger = FixtureTransport(), FixtureLedger()
    if request.param == 'telegram':
        return TelegramAdapter('000:fixture', 'fixture', transport=transport, ledger=ledger, sleep=no_sleep)
    provider = LinqProvider(
        'fixture',
        'whsec_' + base64.b64encode(b'fixture-secret-long-enough').decode(),
        transport=transport,
        sleep=no_sleep,
    )
    return IMessageAdapter(provider, transport=transport, ledger=ledger, sleep=no_sleep)


def incoming(adapter, message_id='10', text='Question one'):
    return ChannelMessage(
        adapter.channel,
        adapter.provider,
        'synthetic',
        'chat',
        message_id,
        text,
        datetime.now(timezone.utc),
        reply_to=message_id,
    )


def sends(adapter):
    return [
        call[2]['json']
        for call in adapter.transport.calls
        if call[1].endswith('/sendMessage') or call[1].endswith('/messages')
    ]


def target(adapter, payload):
    if adapter.channel == 'telegram':
        return payload.get('reply_parameters')
    return payload['message'].get('reply_to')


def expected_target(adapter):
    return (
        {'message_id': 10, 'allow_sending_without_reply': True}
        if adapter.channel == 'telegram'
        else {'message_id': '10'}
    )


@pytest.mark.parametrize('stacked', [False, True])
def test_gateway_one_answer_per_message_and_only_stacked_earlier_answer_is_threaded(adapter, monkeypatch, stacked):
    store, first = MemoryStore(), incoming(adapter)
    proof = store.mint('test', adapter.channel, adapter.provider, 'token')['proof']
    store.consume(proof, first)
    requests = []

    async def digest(*args):
        pass

    def turn(uid, surface, session, request, sink, **kwargs):
        requests.append(request.text)

        async def stream():
            yield 'done: ' + base64.b64encode(
                json.dumps({'text': 'Answer to ' + request.text}).encode()
            ).decode() + '\n\n'

        return stream()

    monkeypatch.setattr(gateway_module, 'append_digest', digest)
    gateway = Gateway(adapter, store=store, turn=turn, admission=lambda uid: None)
    path = store.enqueue(first)
    if stacked:
        path = store.enqueue(replace(first, provider_message_id='11', text='Question two'))
    assert asyncio.run(gateway.process(path))
    bodies = sends(adapter)
    assert requests == (['Question one', 'Question two'] if stacked else ['Question one'])
    assert target(adapter, bodies[0]) == (expected_target(adapter) if stacked else None)
    if stacked:
        assert target(adapter, bodies[1]) is None
    if adapter.channel == 'imessage':
        assert all(
            call[1].endswith('/chats/chat/messages')
            for call in adapter.transport.calls
            if call[1].endswith('/messages')
        )


def test_split_reply_threads_only_first_chunk_and_resolves_after_pacing(adapter):
    first, store = incoming(adapter), MemoryStore()
    store.enqueue(first)

    # Stack while pacing, after the sink has already started sending.
    async def stack(_):
        store.enqueue(replace(first, provider_message_id='11'))

    async def resolver():
        return store.reply_target(first)

    async def run():
        await adapter.admitted(first)
        adapter.capabilities = replace(adapter.capabilities, max_text_len=70)
        await adapter.pace(first.external_chat_id)
        adapter.sleep = stack
        await ChannelReplySink(adapter, first, reply_target=resolver).finish('word ' * 30)

    asyncio.run(run())
    bodies = sends(adapter)
    assert 1 < len(bodies) <= 3
    assert target(adapter, bodies[0]) == expected_target(adapter)
    assert all(target(adapter, body) is None for body in bodies[1:])


def test_rejected_thread_falls_back_to_plain_without_spending_another_ratio_credit(adapter):
    message = incoming(adapter)
    adapter.transport.responses = [(400, {'description': 'reply target missing', 'error': 'invalid_reply_to'}, {})]

    async def resolver():
        return message.provider_message_id

    async def run():
        await adapter.admitted(message)
        await ChannelReplySink(adapter, message, reply_target=resolver).finish('Answer')

    asyncio.run(run())
    bodies = sends(adapter)
    assert len(bodies) == 2
    assert target(adapter, bodies[0]) == expected_target(adapter)
    assert target(adapter, bodies[1]) is None
    assert adapter.ledger.sent == 1
    if adapter.channel == 'imessage':
        assert bodies[1]['message']['idempotency_key'] == bodies[0]['message']['idempotency_key'] + ':unthreaded'


def test_ambiguous_thread_outcome_never_changes_to_a_plain_send(adapter):
    message = incoming(adapter)
    adapter.transport.responses = [DeliveryUncertain('synthetic timeout')] * 4

    async def resolver():
        return message.provider_message_id

    async def run():
        await adapter.admitted(message)
        with pytest.raises(DeliveryUncertain):
            await ChannelReplySink(adapter, message, reply_target=resolver).finish('Answer')

    asyncio.run(run())
    assert all(target(adapter, body) == expected_target(adapter) for body in sends(adapter))


@pytest.mark.parametrize(
    'count,prior', [(0, False), (0, True), (1, False), (1, True), (2, False), (2, True), (3, True), (11, True)]
)
def test_imessage_zero_single_and_many_item_navigation(adapter, count, prior):
    if adapter.channel != 'imessage':
        return
    message = incoming(adapter)
    sources = [dict(kind='task', id=str(i), title=f'Do task {i}') for i in range(count)]
    text = '\n'.join('• ' + item['title'] for item in sources) or 'No matching items.'
    if prior:
        adapter.ledger.accepted_chats.add(message.external_chat_id)

    async def run():
        await adapter.admitted(message)
        await ChannelReplySink(adapter, message).finish_payload({'text': text, 'conversations': sources})

    asyncio.run(run())
    bodies = sends(adapter)
    assert bodies[0]['message']['parts'] == [{'type': 'text', 'value': text}]
    if count and prior:
        assert len(bodies) == 2
        url = (
            'https://h.omi.me/task/0'
            if count == 1
            else ('https://h.omi.me/items?' + '&'.join(f'task={i}' for i in range(min(count, 10))))
        )
        assert bodies[1]['message']['parts'] == [{'type': 'link', 'value': url}]
        assert 'reply_to' not in bodies[1]['message']
    else:
        assert len(bodies) == 1


def test_imessage_omits_unmentioned_items_and_bare_domain(adapter):
    if adapter.channel != 'imessage':
        return
    assert 'https://h.omi.me' not in ''.join(adapter.render('Open https://h.omi.me.'))
    message = incoming(adapter)
    adapter.ledger.accepted_chats.add(message.external_chat_id)

    async def run():
        await adapter.admitted(message)
        await ChannelReplySink(adapter, message).finish_payload(
            {'text': 'No suggestions.', 'conversations': [dict(kind='task', id='secret', title='Private task')]}
        )

    asyncio.run(run())
    assert len(sends(adapter)) == 1 and 'h.omi.me' not in str(sends(adapter))


def test_optional_card_rejection_preserves_accepted_text(adapter, caplog):
    if adapter.channel != 'imessage':
        return
    message = incoming(adapter)
    adapter.ledger.accepted_chats.add(message.external_chat_id)
    adapter.transport.responses = [(200, {'message': {'id': 'text-ok'}}, {}), (400, {'error': 'link rejected'}, {})]
    sink = ChannelReplySink(adapter, message)

    async def run():
        await adapter.admitted(message)
        await sink.finish_payload(
            {'text': 'Do task 0', 'conversations': [dict(kind='task', id='0', title='Do task 0')]}
        )

    asyncio.run(run())
    assert sink.finished and len(sends(adapter)) == 2
    assert 'Messaging link card skipped' in caplog.text


def test_telegram_tied_provider_clock_uses_message_id_not_late_arrival(adapter):
    if adapter.channel != 'telegram':
        return
    store = MemoryStore()
    older = incoming(adapter, message_id='10')
    newer = replace(older, provider_message_id='11', reply_to='11')
    store.enqueue(newer)
    store.enqueue(older)
    assert store.reply_target(newer) is None
    assert store.reply_target(older) == '10'


@pytest.mark.parametrize('uncertain', [False, True])
def test_stacking_during_retry_rechecks_only_when_previous_attempt_was_rejected(adapter, uncertain):
    first, store = incoming(adapter), MemoryStore()
    store.enqueue(first)
    if uncertain:
        adapter.transport.responses = [DeliveryUncertain('synthetic timeout')] * 4
    else:
        adapter.transport.responses = [(429, {'error_code': 429, 'parameters': {'retry_after': 1}}, {})]

    async def resolver():
        return store.reply_target(first)

    async def stack(_):
        store.enqueue(replace(first, provider_message_id='11', reply_to='11'))

    async def run():
        await adapter.admitted(first)
        adapter.sleep = stack
        if adapter.channel == 'imessage':
            adapter.client.sleep = stack
        sink = ChannelReplySink(adapter, first, reply_target=resolver)
        if uncertain:
            with pytest.raises(DeliveryUncertain):
                await sink.finish('Answer')
        else:
            await sink.finish('Answer')

    asyncio.run(run())
    bodies = sends(adapter)
    assert target(adapter, bodies[0]) is None
    if uncertain:
        assert all(target(adapter, body) is None for body in bodies)
    else:
        assert len(bodies) == 2 and target(adapter, bodies[1]) == expected_target(adapter)


def test_imessage_list_card_uses_reply_order_and_configured_base(adapter, monkeypatch):
    if adapter.channel != 'imessage':
        return
    monkeypatch.setenv('OMI_SHARE_BASE_URL', 'https://share.example.com/omi')
    message = incoming(adapter)
    adapter.ledger.accepted_chats.add(message.external_chat_id)
    sources = [
        {'kind': 'task', 'id': 'a/b &=雪', 'title': 'Send the documents'},
        {'kind': 'memory', 'id': 'second', 'title': 'Plan the session'},
        {'kind': 'task', 'id': 'unused', 'title': 'Unrelated task'},
    ]
    text = 'Plan the session. Then [send the documents](https://share.example.com/omi/task/a%2Fb%20%26%3D%E9%9B%AA).'

    async def run():
        await adapter.admitted(message)
        await ChannelReplySink(adapter, message).finish_payload({'text': text, 'conversations': sources})

    asyncio.run(run())
    bodies = sends(adapter)
    assert bodies[0]['message']['parts'] == [{'type': 'text', 'value': 'Plan the session. Then send the documents.'}]
    assert bodies[1]['message']['parts'] == [
        {'type': 'link', 'value': 'https://share.example.com/omi/items?memory=second&task=a%2Fb%20%26%3D%E9%9B%AA'}
    ]
    assert 'share.example.com' not in ''.join(adapter.render('Open https://share.example.com/omi.'))


def test_imessage_multi_item_text_does_not_eat_longer_urls(adapter):
    if adapter.channel != 'imessage':
        return
    message = incoming(adapter)
    adapter.ledger.accepted_chats.add(message.external_chat_id)
    sources = [
        {'kind': 'task', 'id': 'ab', 'title': 'Short task'},
        {'kind': 'task', 'id': 'abc', 'title': 'Longer task'},
        {'kind': 'task', 'id': '1', 'title': 'One'},
        {'kind': 'task', 'id': '10', 'title': 'Ten'},
    ]
    text = (
        '[Longer task](https://h.omi.me/task/abc) and [Short task](https://h.omi.me/task/ab). '
        '[Ten](https://h.omi.me/task/10) and [One](https://h.omi.me/task/1).'
    )

    async def run():
        await adapter.admitted(message)
        await ChannelReplySink(adapter, message).finish_payload({'text': text, 'conversations': sources})

    asyncio.run(run())
    bodies = sends(adapter)
    assert bodies[0]['message']['parts'] == [{'type': 'text', 'value': 'Longer task and Short task. Ten and One.'}]
    assert 'h.omi.me' not in bodies[0]['message']['parts'][0]['value']
