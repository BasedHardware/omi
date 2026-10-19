"""Regressions from first channel QA, using synthetic identities/content only."""

import asyncio
import base64
import json
import time
from datetime import datetime, timedelta, timezone

from testing.messaging.adapter_fakes import FixtureLedger, FixtureTransport, no_sleep
from testing.messaging.store import MemoryStore
from utils.messaging.adapters.telegram import TelegramAdapter
from utils.messaging.contracts import ChannelMessage
from utils.messaging.gateway import Gateway
from utils.messaging import gateway as gateway_module


def setup_turn():
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
        'Synthetic request',
        datetime.now(timezone.utc),
        reply_to='1',
    )
    store.identities[('telegram', 'telegram', 'fixture-user')] = dict(uid='test', active=True, generation='gen')
    return adapter, store, message


def terminal(text='Synthetic answer'):
    return 'done: ' + base64.b64encode(json.dumps({'text': text}).encode()).decode() + '\n\n'


def test_typing_precedes_cold_session_completion(monkeypatch):
    from threading import Event

    adapter, store, message = setup_turn()
    feedback = Event()
    order = []
    original = store.session

    def cold_session(*args):
        assert feedback.wait(timeout=2), 'Feedback must arrive while context preparation is blocked'
        order.append('context_ready')
        return original(*args)

    async def typing(*args):
        order.append('typing')
        feedback.set()

    def turn(*args, **kwargs):
        async def stream():
            yield terminal()

        return stream()

    monkeypatch.setattr(store, 'session', cold_session)
    monkeypatch.setattr(adapter, 'typing', typing)
    gateway = Gateway(adapter, store=store, turn=turn, admission=lambda uid, channel: None, rate_limit=lambda uid: None)
    assert asyncio.run(gateway.process(store.enqueue(message)))
    assert order.index('typing') < order.index('context_ready')


def test_no_write_callback_then_messages_and_provider_failure_release(monkeypatch):
    from dataclasses import replace
    from utils.messaging.adapters.transport import ProviderError

    adapter, store, message = setup_turn()
    turns = []

    async def digest(*args):
        pass

    def turn(uid, surface, session, request, sink, **kwargs):
        turns.append(request.text)

        async def stream():
            if request.text == 'fail':
                raise ProviderError('Synthetic provider failure')
            yield terminal()

        return stream()

    gateway = Gateway(adapter, store=store, turn=turn, admission=lambda uid, channel: None, rate_limit=lambda uid: None)

    async def run():
        for index, text in enumerate(['message', 'undo', 'after undo', 'fail', 'after failure', 'reminder request']):
            item = replace(
                message, provider_message_id=str(index), text=text, command='undo' if text == 'undo' else None
            )
            assert await gateway.process(store.enqueue(item)) is (text != 'fail')
            assert not store.leases

    asyncio.run(run())
    assert turns == ['message', 'after undo', 'fail', 'after failure', 'reminder request']
    assert [job['status'] for job in store.jobs.values()] == ['done', 'done', 'done', 'running', 'done', 'done']
    assert list(store.jobs.values())[3]['fifo_settled_at']
    texts = [call[2].get('json', {}).get('text', '') for call in adapter.transport.calls]
    assert any('could not finish' in text for text in texts)
    assert not any('Undo last write' in text for text in texts)


def test_slow_memory_undo_does_not_block_next_turn_and_second_tap_noop(monkeypatch):
    from dataclasses import replace
    from threading import Event
    from utils.messaging import undo
    from utils.messaging.contracts import UndoResult

    adapter, store, message = setup_turn()
    began, finish = Event(), Event()
    performed = []
    receipt_id = 'a' * 32

    async def digest(*args):
        pass

    def inverse(manager, uid, session, receipt_id=None):
        if performed:
            return UndoResult('already_undone', 'Already undone.')
        performed.append(receipt_id)
        began.set()
        assert finish.wait(3)
        return UndoResult('undone', 'Undone.', '71', 'New memory: Synthetic fact — Undone')

    def turn(uid, surface, session, request, sink, **kwargs):
        async def stream():
            if request.text == 'Synthetic request':
                undo.record_write(uid, 'memory', 'memory-id', None, 'Synthetic fact')
            yield terminal()

        return stream()

    monkeypatch.setattr(undo.UndoStore, 'undo', inverse)
    monkeypatch.setattr(undo.UndoStore, 'mark_edited', lambda *args: None)
    monkeypatch.setattr(
        undo.UndoStore,
        'record',
        lambda *args: undo.action_receipt(receipt_id, 'memory', 'memory-id', None, 'Synthetic fact'),
    )
    monkeypatch.setattr(undo.UndoStore, 'bind_bubble', lambda *args: None)
    gateway = Gateway(adapter, store=store, turn=turn, admission=lambda uid, channel: None, rate_limit=lambda uid: None)

    async def run():
        # Write turn, then action callback, then another message while inverse runs.
        await gateway.process(store.enqueue(message))
        item = replace(
            message, provider_message_id='callback:one', command='undo', callback_id='one', undo_receipt_id=receipt_id
        )
        await gateway.process(store.enqueue(item))
        for _ in range(100):
            if began.is_set():
                break
            await asyncio.sleep(0.005)
        assert began.is_set()
        assert not store.leases
        await gateway.process(store.enqueue(replace(message, provider_message_id='after', text='After undo')))
        assert not store.leases
        finish.set()
        for _ in range(100):
            if any(call[1].endswith('/editMessageText') for call in adapter.transport.calls):
                break
            await asyncio.sleep(0.005)
        assert any(call[1].endswith('/editMessageText') for call in adapter.transport.calls)
        await gateway.process(store.enqueue(replace(item, provider_message_id='callback:two', callback_id='two')))
        await asyncio.sleep(0.03)

    try:
        asyncio.run(run())
    finally:
        finish.set()
    assert performed == [receipt_id]
    edits = [c[2]['json'] for c in adapter.transport.calls if c[1].endswith('/editMessageText')]
    assert len(edits) == 1 and edits[0]['reply_markup'] == {'inline_keyboard': []}
    assert 'Undone' in edits[0]['text']
    assert sum(c[1].endswith('/answerCallbackQuery') for c in adapter.transport.calls) == 2


def test_action_bubbles_only_have_scoped_undo_and_shared_block_data():
    from utils.messaging.undo import action_receipt
    from utils.messaging.outbound import ChannelReplySink

    adapter, store, message = setup_turn()
    memory = action_receipt('a' * 32, 'memory', 'memory-id', None, 'Synthetic fact')
    task = action_receipt('b' * 32, 'task', 'task-id', None, {'description': 'Synthetic task'})

    async def run():
        sink = ChannelReplySink(adapter, message)
        await sink.finish_payload({'text': 'Ordinary answer'})
        await sink.receipt(memory)
        await sink.receipt(task)

    asyncio.run(run())
    calls = [c[2]['json'] for c in adapter.transport.calls if c[1].endswith('/sendMessage')]
    assert 'reply_markup' not in calls[0]
    assert calls[1]['reply_markup']['inline_keyboard'] == [[{'text': 'Undo', 'callback_data': 'undo:' + memory.id}]]
    assert calls[2]['reply_markup']['inline_keyboard'][0][0]['callback_data'] == 'undo:' + task.id
    assert memory.content_block['type'] == 'memoryLink' and memory.content_block['memory_id'] == 'memory-id'
    assert task.content_block['type'] == 'taskCard' and task.content_block['task_id'] == 'task-id'


def test_first_digest_reads_at_most_twenty_rows(monkeypatch):
    from utils.messaging import history

    from unittest.mock import MagicMock
    from types import SimpleNamespace

    client = MagicMock()
    query = client.collection.return_value.document.return_value.collection.return_value.order_by.return_value
    query.limit.return_value.stream.return_value = [
        SimpleNamespace(
            to_dict=lambda i=i: {
                'id': str(i),
                'created_at': datetime.now(timezone.utc),
                'sender': 'human',
                'text': 'recent',
            }
        )
        for i in range(20)
    ]
    monkeypatch.setattr(history.chat_db, 'db', client)
    assert len(history.recent_activity('test')) == 20
    query.limit.assert_called_once_with(20)


def test_reminder_tool_runs_from_channel_projection_and_emits_task_receipt(monkeypatch):
    from datetime import timedelta
    from utils.retrieval import agentic
    from utils.retrieval.tools import action_item_tools
    from utils.messaging import undo
    from utils.messaging.contracts import Principal
    from utils.messaging.projection import surface_runtime, project_runtime_tools

    adapter, store, message = setup_turn()
    due = datetime.now(timezone.utc) + timedelta(minutes=10)
    tasks, notifications = {}, []

    def create(uid, data):
        assert uid == 'test'
        tasks['task-id'] = dict(data, id='task-id')
        return 'task-id'

    def record(manager, uid, session, kind, object_id, before, after):
        return undo.action_receipt('c' * 32, kind, object_id, before, after)

    monkeypatch.setattr(action_item_tools.action_items_db, 'create_action_item', create)
    monkeypatch.setattr(action_item_tools.action_items_db, 'get_action_item', lambda uid, task_id: tasks[task_id])
    monkeypatch.setattr(
        action_item_tools, 'send_action_item_data_message', lambda **kwargs: notifications.append(kwargs)
    )
    monkeypatch.setattr(action_item_tools, 'send_action_item_created_notification', lambda *args: None)
    monkeypatch.setattr(undo.UndoStore, 'record', record)
    monkeypatch.setattr(undo.UndoStore, 'reserve_selection', lambda *args: None)
    monkeypatch.setattr(undo.UndoStore, 'bind_bubble', lambda *args: None)

    async def digest(*args):
        pass

    def turn(*args, **kwargs):
        async def stream():
            runtime = surface_runtime.get()
            projection = project_runtime_tools(runtime, agentic.CORE_TOOLS, (), (), ())
            result = await agentic._execute_tool(
                'create_action_item_tool',
                {'description': 'Synthetic dinner task', 'due_at': due.isoformat()},
                dict(projection.registry),
                {'user_id': 'test', 'tool_projection': projection},
            )
            assert 'Added:' in result and 'undo' not in result.lower()
            yield terminal('Scheduled your reminder.')

        return stream()

    asyncio.run(
        Gateway(
            adapter, store=store, turn=turn, admission=lambda uid, channel: None, rate_limit=lambda uid: None
        ).process(store.enqueue(message))
    )
    assert tasks['task-id']['due_at'] == due
    assert notifications[0]['due_at'] == due.isoformat()
    assert not store.leases
    final = [c[2]['json'] for c in adapter.transport.calls if c[1].endswith('/sendMessage')]
    assert 'reply_markup' not in final[0]
    assert 'Synthetic dinner task' in final[1]['text'] and 'due' in final[1]['text']
    assert final[1]['reply_markup']['inline_keyboard'][0][0]['callback_data'] == 'undo:' + 'c' * 32


def test_undo_failure_sends_error_and_next_message_runs(monkeypatch):
    from dataclasses import replace
    from utils.messaging import undo

    adapter, store, message = setup_turn()

    def fail(*args):
        raise RuntimeError('Synthetic inverse cleanup failure')

    monkeypatch.setattr(undo.UndoStore, 'undo', fail)

    async def digest(*args):
        pass

    def turn(*args, **kwargs):
        async def stream():
            yield terminal()

        return stream()

    gateway = Gateway(adapter, store=store, turn=turn, admission=lambda uid, channel: None, rate_limit=lambda uid: None)

    async def run():
        callback = replace(
            message,
            provider_message_id='callback:failure',
            callback_id='failure',
            command='undo',
            undo_receipt_id='d' * 32,
        )
        await gateway.process(store.enqueue(callback))
        for _ in range(100):
            if any('couldn’t finish undoing' in c[2].get('json', {}).get('text', '') for c in adapter.transport.calls):
                break
            await asyncio.sleep(0.005)
        assert not store.leases
        await gateway.process(store.enqueue(message))

    asyncio.run(run())
    assert any('couldn’t finish undoing' in c[2].get('json', {}).get('text', '') for c in adapter.transport.calls)
    assert not store.leases


def test_channel_skips_discarded_legacy_prompt_but_keeps_tool_projection(monkeypatch, capsys):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from utils.retrieval import agentic
    from utils.messaging.contracts import Principal
    from utils.messaging.projection import SurfaceRuntime, surface_runtime

    prompt_reads = []

    def cold_prompt(*args, **kwargs):
        prompt_reads.append(True)
        time.sleep(0.08)
        return 'Discarded legacy prompt'

    monkeypatch.setattr(agentic, '_get_agentic_qa_prompt', cold_prompt)
    monkeypatch.setattr(agentic, 'load_app_tools', lambda *args: [])

    async def runner(*args):
        assert 'create_action_item_tool' in args[3]
        assert args[7]['user_id'] == 'test'
        args[5].append('Synthetic answer')
        await args[4].put_data('Synthetic answer')
        await args[4].end()

    monkeypatch.setattr(agentic, '_run_shaped_chat_stream', runner)

    async def run():
        token = surface_runtime.set(SurfaceRuntime('channel:fixture', '', Principal('test')))
        try:
            callback = {}
            chunks = [
                chunk
                async for chunk in agentic.execute_agentic_chat_stream(
                    'test',
                    [SimpleNamespace(text='Synthetic request', sender='human', files_id=[])],
                    callback_data=callback,
                    tz='UTC',
                    current_datetime_block='Today',
                )
            ]
            assert callback['answer'] == 'Synthetic answer'
            assert chunks[-1] is None
        finally:
            surface_runtime.reset(token)

    started = time.monotonic()
    asyncio.run(run())
    with capsys.disabled():
        print(f'QA setup elapsed_ms={(time.monotonic()-started)*1000:.1f} legacy_prompt_reads={len(prompt_reads)}')
    assert prompt_reads == []


def test_private_memories_empty_result_is_not_a_claim_no_facts_exist(monkeypatch):
    from types import SimpleNamespace
    from utils.retrieval.tools import memory_tools
    from utils.messaging.contracts import Principal
    from utils.messaging.projection import SurfaceRuntime, surface_runtime

    now = datetime.now(timezone.utc)
    private = SimpleNamespace(
        is_locked=False, user_review=True, created_at=now, visibility='private', sensitivity_labels=[]
    )

    class Service:
        def __init__(self, **kwargs):
            pass

        def read(self, uid, **kwargs):
            assert uid == 'test'
            return [private]

    monkeypatch.setattr(memory_tools, 'MemoryService', Service)
    token = surface_runtime.set(
        SurfaceRuntime('channel:fixture', '', Principal('test'), withhold_private_memories=True)
    )
    try:
        result = memory_tools.get_memories_tool.func(config={'configurable': {'user_id': 'test'}})
    finally:
        surface_runtime.reset(token)
    assert 'does not prove' in result and 'Privacy' in result
    assert 'may not have any recorded facts' not in result


def test_typing_outage_and_stream_without_terminal_do_not_silence_chat(monkeypatch):
    from dataclasses import replace
    from utils.messaging.adapters.transport import ProviderError

    adapter, store, message = setup_turn()

    async def typing(*args):
        raise ProviderError('Synthetic typing outage')

    async def digest(*args):
        pass

    def turn(*args, **kwargs):
        async def stream():
            yield 'think: Synthetic incomplete turn'

        return stream()

    monkeypatch.setattr(adapter, 'typing', typing)
    gateway = Gateway(adapter, store=store, turn=turn, admission=lambda uid, channel: None, rate_limit=lambda uid: None)

    async def run():
        for index in range(2):
            await gateway.process(store.enqueue(replace(message, provider_message_id=str(index))))
            assert not store.leases

    asyncio.run(run())
    replies = [c[2]['json']['text'] for c in adapter.transport.calls if c[1].endswith('/sendMessage')]
    assert len(replies) == 2 and all('could not finish' in text for text in replies)


def test_authenticated_receipt_callback_recovers_interrupted_bubble_binding(monkeypatch):
    from dataclasses import replace
    from utils.messaging import undo
    from utils.messaging.contracts import UndoResult

    adapter, store, message = setup_turn()
    monkeypatch.setattr(
        undo.UndoStore, 'undo', lambda *args: UndoResult('undone', 'Undone.', bubble_text='Synthetic fact — Undone')
    )
    monkeypatch.setattr(undo.UndoStore, 'mark_edited', lambda *args: None)
    gateway = Gateway(adapter, store=store, admission=lambda uid, channel: None, rate_limit=lambda uid: None)

    async def run():
        item = replace(message, command='undo', callback_id='callback', undo_receipt_id='e' * 32, reply_to='71')
        await gateway.process(store.enqueue(item))
        for _ in range(100):
            if any(c[1].endswith('/editMessageText') for c in adapter.transport.calls):
                break
            await asyncio.sleep(0.005)

    asyncio.run(run())
    edits = [c[2]['json'] for c in adapter.transport.calls if c[1].endswith('/editMessageText')]
    assert edits[0]['message_id'] == 71 and edits[0]['reply_markup'] == {'inline_keyboard': []}


def test_verified_http_message_callback_message_sequence(monkeypatch):
    import httpx
    from fastapi import FastAPI
    from routers import messaging

    adapter, store, message = setup_turn()
    store.identities[('telegram', 'telegram', '42')] = dict(uid='test', active=True, generation='gen')
    turns = []

    async def digest(*args):
        pass

    def turn(uid, surface, session, request, sink, **kwargs):
        turns.append(request.text)

        async def stream():
            yield terminal()

        return stream()

    gateway = Gateway(adapter, store=store, turn=turn, admission=lambda uid, channel: None, rate_limit=lambda uid: None)

    completed = asyncio.Event()

    async def dispatch(paths):
        try:
            for path in paths:
                await gateway.process(path)
        finally:
            completed.set()

    gateway.wake = dispatch
    monkeypatch.setattr(messaging, '_gateways', {'telegram': gateway})
    app = FastAPI()
    app.include_router(messaging.router)
    headers = {'X-Telegram-Bot-Api-Secret-Token': 'fixture_secret'}
    chat = {'id': 42, 'type': 'private'}
    sender = {'id': 42, 'is_bot': False}

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://fixture') as client:
            for i, text in enumerate(['Synthetic message', 'undo', 'Synthetic follow-up']):
                item = {'message_id': i + 1, 'chat': chat, 'from': sender, 'text': text}
                body = {'update_id': i + 1, 'message': item}
                if text == 'undo':
                    body = {
                        'update_id': i + 1,
                        'callback_query': {'id': 'fixture-callback', 'from': sender, 'message': item, 'data': 'undo'},
                    }
                completed.clear()
                response = await client.post('/v1/messaging/webhooks/telegram', headers=headers, json=body)
                assert response.status_code == 202
                await asyncio.wait_for(completed.wait(), 5)
                assert all(job['status'] == 'done' for job in store.jobs.values())
                assert not store.leases
            bad = await client.post('/v1/messaging/webhooks/telegram', json=body)
            assert bad.status_code == 401
        specific = {
            'update_id': 9,
            'callback_query': {'id': 'specific', 'from': sender, 'message': item, 'data': 'undo:' + 'a' * 32},
        }
        parsed = adapter.parse(json.dumps(specific).encode())[0]
        assert parsed.command == 'undo' and parsed.undo_receipt_id == 'a' * 32
        assert parsed.callback_id == 'specific' and parsed.provider_message_id == 'callback:specific'

    asyncio.run(run())
    assert turns == ['Synthetic message', 'Synthetic follow-up']
    assert sum(c[1].endswith('/answerCallbackQuery') for c in adapter.transport.calls) == 1


def test_revocation_detected_by_early_typing_never_loads_session_or_model(monkeypatch):
    adapter, store, message = setup_turn()

    async def revoked(*args):
        raise PermissionError('Synthetic revoked generation')

    def forbidden(*args, **kwargs):
        raise AssertionError('Private session/model work after revocation')

    monkeypatch.setattr(adapter, 'typing', revoked)
    monkeypatch.setattr(store, 'session', forbidden)
    gateway = Gateway(
        adapter, store=store, turn=forbidden, admission=lambda uid, channel: None, rate_limit=lambda uid: None
    )
    asyncio.run(gateway.process(store.enqueue(message)))


def test_repeated_linq_text_undo_gets_acknowledgement(monkeypatch):
    from dataclasses import replace
    from utils.messaging.contracts import UndoResult
    from utils.messaging.undo import UndoStore

    adapter, store, message = setup_turn()
    monkeypatch.setattr(UndoStore, 'undo', lambda *args: UndoResult('already_undone', 'Already undone.'))
    replies = []

    class Sink:
        async def finish(self, text):
            replies.append(text)

    gateway = Gateway(adapter, store=store, admission=lambda uid, channel: None, rate_limit=lambda uid: None)
    asyncio.run(gateway._undo_action('test', {'id': 'session'}, replace(message, command='undo'), Sink()))
    assert replies == ['Already undone.']


def test_digest_does_not_scan_past_twenty_current_session_candidates(monkeypatch):
    from utils.messaging import history
    from unittest.mock import MagicMock
    from types import SimpleNamespace

    client = MagicMock()
    query = client.collection.return_value.document.return_value.collection.return_value.order_by.return_value
    query.limit.return_value.stream.return_value = [
        SimpleNamespace(to_dict=lambda: {'chat_session_id': 'current'}) for _ in range(20)
    ]
    monkeypatch.setattr(history.chat_db, 'db', client)
    assert history.recent_activity('test', exclude_session='current') == []
    query.limit.assert_called_once_with(20)


def test_backlog_release_preserves_fifo_and_original_message_clock(monkeypatch):
    from dataclasses import replace
    from utils.messaging.projection import surface_runtime

    adapter, store, message = setup_turn()
    times = [datetime(2026, 10, 11, 9, minute, tzinfo=timezone.utc) for minute in (19, 22, 23)]
    seen, contexts = [], []

    async def digest(*args):
        pass

    def turn(uid, surface, session, request, sink, **kwargs):
        runtime = surface_runtime.get()
        seen.append((request.text, runtime.request_at))
        contexts.append(runtime.evidence)

        async def stream():
            yield terminal('Confirmed ' + request.text)

        return stream()

    gateway = Gateway(adapter, store=store, turn=turn, admission=lambda uid, channel: None, rate_limit=lambda uid: None)
    paths = [
        store.enqueue(replace(message, provider_message_id=str(i), text=str(i), received_at=at))
        for i, at in enumerate(times)
    ]
    session = store.session('test', message, store.lookup(message))
    held = store.acquire('test', session['surface'])

    async def run():
        # A busy lease and reverse worker wake order must not admit a later turn.
        for path in reversed(paths):
            assert not await gateway.process(path)
        assert not seen
        # A fresh lease stays exclusive until its holder releases it.
        assert store.leases
        store.release('test', session['surface'], held)
        assert await gateway.process(paths[2])
        assert all(store.jobs[path]['status'] == 'done' for path in paths)

    asyncio.run(run())
    assert seen == list(zip(['0', '1', '2'], times))
    assert contexts[1] == ({'role': 'user', 'content': '1'},)
    assert contexts[2] == ({'role': 'user', 'content': '2'},)
    assert 'Confirmed 0' in str(store.logs) and 'Confirmed 1' in str(store.logs)
    replies = [call[2]['json']['text'] for call in adapter.transport.calls if call[1].endswith('/sendMessage')]
    assert replies == ['Confirmed 0', 'Confirmed 1', 'Confirmed 2']


def test_relative_reminder_anchors_to_received_time_and_reports_phone_or_late(monkeypatch):
    from dataclasses import replace
    from utils.retrieval.tools import action_item_tools
    from utils.messaging.projection import SurfaceRuntime, surface_runtime
    from utils.messaging.contracts import Principal
    from utils.messaging.turn_context import channel_evidence

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 11, 9, 31, tzinfo=timezone.utc)

    tasks, pushes, receipts = {}, [], []
    monkeypatch.setattr(action_item_tools, 'datetime', Clock)
    monkeypatch.setattr(
        action_item_tools.action_items_db,
        'create_action_item',
        lambda uid, data: tasks.setdefault('task', dict(data, id='task')) and 'task',
    )
    monkeypatch.setattr(action_item_tools.action_items_db, 'get_action_item', lambda uid, task: tasks[task])
    monkeypatch.setattr(action_item_tools, 'send_action_item_data_message', lambda **kwargs: pushes.append(kwargs))
    monkeypatch.setattr(action_item_tools, 'send_action_item_created_notification', lambda *args: None)
    monkeypatch.setattr(
        action_item_tools, 'record_write', lambda uid, kind, object_id, before, after: receipts.append(after) or ''
    )
    runtime = SurfaceRuntime(
        'channel:test', '', Principal('test'), request_at=datetime(2026, 10, 11, 9, 19, tzinfo=timezone.utc)
    )
    config = {'configurable': {'user_id': 'test', 'user_timezone': 'Asia/Ho_Chi_Minh'}}
    for received, expected, state in [(19, 29, 'late'), (31, 41, 'requested')]:
        tasks.clear()
        token = surface_runtime.set(
            replace(runtime, request_at=datetime(2026, 10, 11, 9, received, tzinfo=timezone.utc))
        )
        try:
            result = action_item_tools.create_action_item_tool.func(
                description='Synthetic reminder', due_in_minutes=10, config=config
            )
            evidence = channel_evidence(surface_runtime.get(), 'Asia/Ho_Chi_Minh')
            assert '+07:00' in evidence[0]['content'] and 'due_in_minutes=N' in evidence[0]['content']
        finally:
            surface_runtime.reset(token)
        assert tasks['task']['due_at'] == datetime(2026, 10, 11, 9, expected, tzinfo=timezone.utc)
        if state == 'late':
            assert not pushes and 'passed while this request waited' in result
        else:
            assert pushes[0]['due_at'] == tasks['task']['due_at'].isoformat()
            assert "I'll remind you at 4:41 PM" in result and 'on your phone' in result
        assert receipts[-1]['_channel_reminder_confirmation'] in result
    pushes.clear()
    tasks.clear()
    token = surface_runtime.set(replace(runtime, request_at=datetime(2026, 10, 8, 9, 19, tzinfo=timezone.utc)))
    try:
        result = action_item_tools.create_action_item_tool.func(
            description='Synthetic reminder', due_in_minutes=10, config=config
        )
    finally:
        surface_runtime.reset(token)
    assert tasks['task']['due_at'] == datetime(2026, 10, 8, 9, 29, tzinfo=timezone.utc)
    assert not pushes and 'passed while this request waited' in result and 'future date' not in result


def test_provider_clocks_are_bounded_and_linq_uses_sent_at():
    from utils.messaging.adapters.linq import LinqProvider

    adapter, _, _ = setup_turn()
    now = datetime.now(timezone.utc)
    future = int((now + timedelta(hours=2)).timestamp())
    ancient = int((now - timedelta(days=3)).timestamp())
    item = {
        'message_id': 1,
        'chat': {'id': 42, 'type': 'private'},
        'from': {'id': 42, 'is_bot': False},
        'text': 'Synthetic reminder',
    }
    ahead = adapter.parse(json.dumps({'update_id': 1, 'message': dict(item, date=future)}).encode())[0]
    assert ahead.received_at <= datetime.now(timezone.utc) + timedelta(seconds=2)
    old = adapter.parse(json.dumps({'update_id': 2, 'message': dict(item, date=ancient)}).encode())[0]
    age = datetime.now(timezone.utc) - old.received_at
    assert timedelta(hours=23) < age <= timedelta(days=1, seconds=2)
    try:
        adapter.parse(json.dumps({'update_id': 3, 'message': dict(item, date=10**18)}).encode())
    except ValueError as error:
        assert 'time' in str(error)
    else:
        raise AssertionError('Extreme Telegram date must be rejected')

    sent = (now - timedelta(minutes=10)).strftime('%Y-%m-%dT%H:%M:%S.%f') + '123Z'
    provider = LinqProvider(
        'fixture-api-key',
        'whsec_' + base64.b64encode(b'synthetic-test-signing-secret-32').decode(),
        transport=adapter.transport,
        sleep=lambda *_: None,
    )
    body = {
        'webhook_version': '2026-02-03',
        'event_type': 'message.received',
        'data': {
            'id': 'fixture-message',
            'sent_at': sent,
            'chat': {'id': 'fixture-chat', 'is_group': False},
            'direction': 'inbound',
            'sender_handle': {'handle': '+12025550101', 'is_me': False},
            'parts': [{'type': 'text', 'value': 'Synthetic reminder'}],
        },
    }
    parsed = provider.parse(json.dumps(body).encode())[0]
    assert abs((parsed.received_at - (now - timedelta(minutes=10))).total_seconds()) < 1
    body['data']['sent_at'] = (now + timedelta(hours=3)).strftime('%Y-%m-%dT%H:%M:%SZ')
    clamped = provider.parse(json.dumps(body).encode())[0]
    assert clamped.received_at <= datetime.now(timezone.utc) + timedelta(seconds=2)


def test_busy_lease_does_not_wake_its_own_head(monkeypatch):
    from dataclasses import replace

    adapter, store, message = setup_turn()
    wakes = []

    async def wake(paths):
        wakes.extend(paths)

    async def digest(*args):
        pass

    def turn(*args, **kwargs):
        async def stream():
            yield terminal()

        return stream()

    gateway = Gateway(
        adapter, store=store, turn=turn, admission=lambda uid, channel: None, rate_limit=lambda uid: None, wake=wake
    )
    session = store.session('test', message, store.lookup(message))
    held = store.acquire('test', session['surface'])
    path = store.enqueue(message)
    following = store.enqueue(replace(message, provider_message_id='next'))

    async def run():
        assert not await gateway.process(path)
        assert wakes == []
        assert store.jobs[path]['status'] == 'pending'
        store.release('test', session['surface'], held)
        assert await gateway.process(path)

    asyncio.run(run())
    assert wakes == [following]


def test_channel_memory_search_empty_does_not_claim_no_facts(monkeypatch):
    from types import SimpleNamespace
    from utils.retrieval.tools import memory_tools
    from utils.messaging.contracts import Principal
    from utils.messaging.projection import SurfaceRuntime, surface_runtime

    private = SimpleNamespace(
        is_locked=False, visibility='private', sensitivity_labels=[], content='synthetic private fact'
    )

    class Match:
        memory = private
        score = 0.9

    class Service:
        def __init__(self, **kwargs):
            pass

        def search(self, *args, **kwargs):
            return [Match()]

    monkeypatch.setattr(memory_tools, 'MemoryService', Service)
    token = surface_runtime.set(
        SurfaceRuntime('channel:fixture', '', Principal('test'), withhold_private_memories=True)
    )
    try:
        result = memory_tools.search_memories_tool.func(
            query='synthetic query', config={'configurable': {'user_id': 'test', 'user_timezone': 'UTC'}}
        )
    finally:
        surface_runtime.reset(token)
    assert 'does not prove' in result and 'synthetic private fact' not in result and 'synthetic query' not in result


def test_stale_unscoped_callback_cannot_reverse_latest_write(monkeypatch):
    from dataclasses import replace
    from utils.messaging.undo import UndoStore

    adapter, store, message = setup_turn()

    def forbidden(*args):
        raise AssertionError('Stale generic callback must never resolve the last write')

    monkeypatch.setattr(UndoStore, 'undo', forbidden)
    monkeypatch.setattr(UndoStore, 'select_receipt', forbidden)
    gateway = Gateway(adapter, store=store, admission=lambda uid, channel: None, rate_limit=lambda uid: None)
    incoming = replace(message, command='undo', callback_id='stale', reply_to='17')
    asyncio.run(gateway.process(store.enqueue(incoming)))
    assert sum(call[1].endswith('/answerCallbackQuery') for call in adapter.transport.calls) == 1
    assert not any(call[1].endswith('/sendMessage') for call in adapter.transport.calls)
    assert not store.leases


def test_prelease_admission_failure_does_not_poison_fifo_head(monkeypatch):
    from dataclasses import replace
    import pytest

    adapter, store, message = setup_turn()
    denied = [True]

    def admission(uid, channel):
        if denied[0]:
            raise PermissionError('Synthetic entitlement revoked')

    async def digest(*args):
        pass

    def turn(*args, **kwargs):
        async def stream():
            yield terminal()

        return stream()

    gateway = Gateway(adapter, store=store, turn=turn, admission=admission, rate_limit=lambda uid: None)
    first = store.enqueue(message)
    second = store.enqueue(replace(message, provider_message_id='second'))

    async def run():
        assert await gateway.process(first)
        assert store.jobs[first]['status'] == 'done'
        assert store.jobs[second]['status'] == 'done'
        assert sum(url.endswith('/sendMessage') for method, url, kwargs in adapter.transport.calls) == 1
        denied[0] = False
        third = store.enqueue(replace(message, provider_message_id='third'))
        assert await gateway.process(third)

    asyncio.run(run())
    assert not store.leases


def test_telegram_request_clock_uses_message_date_not_late_webhook_time():
    adapter, _, _ = setup_turn()
    # Keep the delayed delivery inside the parser's bounded provider-clock window.
    at = (datetime.now(timezone.utc) - timedelta(minutes=10)).replace(microsecond=0)
    item = {
        'message_id': 1,
        'date': int(at.timestamp()),
        'chat': {'id': 42, 'type': 'private'},
        'from': {'id': 42, 'is_bot': False},
        'text': 'Synthetic reminder',
    }
    parsed = adapter.parse(json.dumps({'update_id': 1, 'message': item}).encode())[0]
    assert parsed.received_at == at
    before = datetime.now(timezone.utc)
    callback = {'id': 'ask', 'from': item['from'], 'message': item, 'data': 'ask:Synthetic follow-up'}
    parsed = adapter.parse(json.dumps({'update_id': 2, 'callback_query': callback}).encode())[0]
    assert parsed.received_at >= before


def test_merged_failed_send_then_undo_callback_then_next_message(monkeypatch):
    from dataclasses import replace
    from utils.messaging.adapters.transport import ProviderError

    adapter, store, message = setup_turn()
    original_send, original_release = adapter.send, store.release
    rejected, releases, typing_stops = [], [], []

    async def send(message, **kwargs):
        if kwargs.get('text') == 'Synthetic answer' and not rejected:
            rejected.append(True)
            raise ProviderError('Synthetic rejected send')
        return await original_send(message, **kwargs)

    def release(uid, surface, token):
        releases.append(token)
        original_release(uid, surface, token)

    async def typing(message, active=True):
        if not active:
            typing_stops.append(message.provider_message_id)

    async def digest(*args):
        pass

    def turn(*args, **kwargs):
        async def stream():
            yield terminal()

        return stream()

    monkeypatch.setattr(adapter, 'send', send)
    monkeypatch.setattr(adapter, 'typing', typing)
    monkeypatch.setattr(store, 'release', release)
    gateway = Gateway(adapter, store=store, turn=turn, admission=lambda uid, channel: None, rate_limit=lambda uid: None)
    failed = store.enqueue(message)
    callback = store.enqueue(replace(message, provider_message_id='undo', command='undo', callback_id='callback'))
    following = store.enqueue(replace(message, provider_message_id='next'))

    async def run():
        assert await gateway.process(failed)  # settled failure drains callback and next message
        assert store.jobs[failed]['status'] == 'running'
        assert store.jobs[failed]['fifo_settled_at']
        assert 'payload' in store.jobs[failed]
        assert not store.leases
        session = next(iter(store.sessions.values()))
        assert not any(
            e['id'] == 'reply:' + gateway_module.key('telegram', 'first') for e in store.events('test', session['id'])
        )
        assert not await gateway.process(failed)  # retained evidence is never replayed
        assert not await gateway.process(callback)
        assert not await gateway.process(following)
        assert store.jobs[callback]['status'] == store.jobs[following]['status'] == 'done'
        assert not store.leases

    asyncio.run(run())
    assert len(releases) == 3 and len(set(releases)) == 3
    assert typing_stops == ['first', 'undo', 'next']
    replies = [call[2].get('json', {}).get('text', '') for call in adapter.transport.calls]
    assert replies.count('Synthetic answer') == 1
    assert sum('could not finish' in text for text in replies) == 1
