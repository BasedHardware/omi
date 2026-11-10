"""A newer message replaces a channel reply the user has not seen yet.

On Telegram a user who spots a typo sends a correction while Omi is still working.
If none of the reply has been delivered and no tool changed anything, the running
turn stops quietly (no apology), and the correction is answered next.
"""

import asyncio
import base64
import json
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from database.messaging import can_supersede
from testing.messaging.adapter_fakes import FixtureLedger, FixtureTransport, no_sleep
from testing.messaging.store import MemoryStore
from utils.messaging import gateway as gateway_module
from utils.messaging.adapters.telegram import TelegramAdapter
from utils.messaging.contracts import ChannelMessage
from utils.messaging.gateway import Gateway


def _setup():
    adapter = TelegramAdapter(
        '000:fixture', 'fixture_secret', transport=FixtureTransport(), ledger=FixtureLedger(), sleep=no_sleep
    )
    store = MemoryStore()
    message = ChannelMessage(
        'telegram',
        'telegram',
        'fixture-user',
        'fixture-chat',
        'first',
        'Is this one steel frame?',
        datetime.now(timezone.utc),
        reply_to='1',
    )
    store.identities[('telegram', 'telegram', 'fixture-user')] = dict(uid='test', active=True, generation='gen')
    return adapter, store, message


def _terminal(text):
    return 'done: ' + base64.b64encode(json.dumps({'text': text}).encode()).decode() + '\n\n'


def _sent_texts(adapter):
    return [call[2].get('json', {}).get('text', '') for call in adapter.transport.calls]


def test_newer_message_replaces_a_reply_still_thinking(monkeypatch):
    monkeypatch.setattr(gateway_module, 'SUPERSEDE_POLL_SECONDS', 0.01)
    adapter, store, first = _setup()
    second = replace(first, provider_message_id='second', text='Sorry, I meant still frame')
    requests = []

    def turn(uid, surface, session, request, sink, **kwargs):
        requests.append(request.text)

        async def stream():
            if request.text == first.text:
                for _ in range(200):  # still thinking; the correction arrives meanwhile
                    await asyncio.sleep(0.005)
                    yield 'think: Searching files\n\n'
                yield _terminal('This is the wrong answer')
            else:
                yield _terminal('Here is the progression.')

        return stream()

    gateway = Gateway(adapter, store=store, turn=turn, admission=lambda uid, channel: None, rate_limit=lambda uid: None)

    async def run():
        first_path = store.enqueue(first)
        running = asyncio.create_task(gateway.process(first_path))
        await asyncio.sleep(0.05)
        second_path = store.enqueue(second)
        # The same worker drains the inbox: once the first turn stops, it answers the correction.
        assert await running
        return first_path, second_path

    first_path, second_path = asyncio.run(run())

    assert requests == [first.text, second.text]
    texts = _sent_texts(adapter)
    assert 'Here is the progression.' in texts
    assert 'This is the wrong answer' not in texts
    assert not any('could not finish' in text for text in texts), 'a replaced reply sends no apology'
    assert store.jobs[first_path]['status'] == 'done'
    assert store.jobs[second_path]['status'] == 'done'
    assert not store.leases


def test_a_reply_already_delivered_is_not_replaced(monkeypatch):
    monkeypatch.setattr(gateway_module, 'SUPERSEDE_POLL_SECONDS', 0.01)
    adapter, store, first = _setup()

    def turn(uid, surface, session, request, sink, **kwargs):
        async def stream():
            yield 'think: working\n\n'
            sink.delivered_ids.append('already-sent')  # e.g. a tool sent a message mid-turn
            for _ in range(20):
                await asyncio.sleep(0.005)
                yield 'think: still working\n\n'
            yield _terminal('Finished anyway')

        return stream()

    gateway = Gateway(adapter, store=store, turn=turn, admission=lambda uid, channel: None, rate_limit=lambda uid: None)

    async def run():
        path = store.enqueue(first)
        running = asyncio.create_task(gateway.process(path))
        await asyncio.sleep(0.03)
        store.enqueue(replace(first, provider_message_id='second', text='another'))
        await running

    asyncio.run(run())
    assert 'Finished anyway' in _sent_texts(adapter)


def test_commands_and_callbacks_never_replace_a_reply():
    _, _, message = _setup()
    assert can_supersede(message)
    assert not can_supersede(replace(message, command='new'))
    assert not can_supersede(replace(message, callback_id='cb-1'))
    assert not can_supersede(replace(message, media_group_id='album-1'))
    assert not can_supersede(replace(message, link_proof='proof'))


def test_superseding_pending_ignores_other_users_and_commands():
    _, store, first = _setup()
    running = store.enqueue(first)
    store.jobs[running]['status'] = 'running'
    other_user = replace(first, external_user_id='someone-else', provider_message_id='x')
    store.identities[('telegram', 'telegram', 'someone-else')] = dict(uid='other', active=True, generation='gen')
    store.enqueue(other_user)
    store.enqueue(replace(first, provider_message_id='cmd', command='help'))
    assert not store.superseding_pending(running)

    store.enqueue(replace(first, provider_message_id='fix', text='correction'))
    assert store.superseding_pending(running)


@pytest.mark.parametrize('replaceable', [True, False])
def test_frame_wrapper_passes_frames_through_when_nothing_replaces(replaceable):
    async def frames():
        yield 'a'
        yield 'b'

    async def never():
        return False

    async def run():
        return [frame async for frame in gateway_module._frames_until_superseded(frames(), never, lambda: replaceable)]

    assert asyncio.run(run()) == ['a', 'b']


def test_a_reply_the_user_is_watching_as_a_draft_is_not_replaced(monkeypatch):
    monkeypatch.setattr(gateway_module, 'SUPERSEDE_POLL_SECONDS', 0.01)
    adapter, store, first = _setup()  # the Telegram adapter streams drafts by default

    def turn(uid, surface, session, request, sink, **kwargs):
        async def stream():
            yield 'data: The camera follows\n\n'  # sent as a visible draft
            for _ in range(20):
                await asyncio.sleep(0.005)
                yield 'think: still working\n\n'
            yield _terminal('The camera follows the runner.')

        return stream()

    gateway = Gateway(adapter, store=store, turn=turn, admission=lambda uid, channel: None, rate_limit=lambda uid: None)

    async def run():
        running = asyncio.create_task(gateway.process(store.enqueue(first)))
        await asyncio.sleep(0.03)
        store.enqueue(replace(first, provider_message_id='second', text='another'))
        await running

    asyncio.run(run())
    assert 'The camera follows the runner.' in _sent_texts(adapter)


def test_terminal_frame_is_delivered_even_when_a_newer_message_waits(monkeypatch):
    async def always():
        return True

    monkeypatch.setattr(gateway_module, 'SUPERSEDE_POLL_SECONDS', 0.0)

    async def run_terminal_only():
        async def only_terminal():
            await asyncio.sleep(0.02)
            yield _terminal('Answer')

        return [frame async for frame in gateway_module._frames_until_superseded(only_terminal(), always, lambda: True)]

    assert asyncio.run(run_terminal_only()) == [_terminal('Answer')]


def test_a_message_in_another_chat_does_not_replace_this_reply():
    _, store, first = _setup()
    running = store.enqueue(first)
    store.jobs[running]['status'] = 'running'
    store.enqueue(replace(first, external_chat_id='group-chat', provider_message_id='g1', text='in another chat'))
    assert not store.superseding_pending(running)


def test_a_row_from_before_the_chat_field_is_never_replaced():
    _, store, first = _setup()
    running = store.enqueue(first)
    store.jobs[running]['status'] = 'running'
    store.jobs[running].pop('chat')
    store.enqueue(replace(first, provider_message_id='fix', text='correction'))
    assert not store.superseding_pending(running)
