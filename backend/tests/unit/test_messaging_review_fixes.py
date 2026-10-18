"""Review regressions: optional context never gates answers, bounded reads and safe pacing."""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import FailedPrecondition
from utils.messaging import context, history, pacing
from utils.llm import prompt_cache


@pytest.fixture(scope='module')
def shaped():
    from utils.retrieval import agentic
    from utils.retrieval import shaped_chat

    return agentic, shaped_chat


@pytest.mark.parametrize('failure', [FailedPrecondition('index'), RuntimeError('revision'), ValueError('ciphertext')])
def test_optional_load_failure_returns_plain_window(monkeypatch, failure):
    store = MagicMock()
    store.load_for_turn = store.load
    store.assert_access = MagicMock()
    store.load.side_effect = failure
    # Preparation now starts digest IO concurrently; keep this regression hermetic
    # while testing only the continuity-load failure.
    monkeypatch.setattr(context, 'recent_activity', lambda *args: [])
    notices = []
    monkeypatch.setattr(context, 'record_fallback', lambda **kw: notices.append(kw))
    assert asyncio.run(context.prepare('u', 's', ['m'], store=store)) == {'summary': '', 'digest': ''}
    store.source_page.assert_not_called()
    assert len(notices) == 1 and notices[0]['outcome'] == 'degraded'


def test_slow_context_read_has_hard_budget(monkeypatch):
    deadlines = []
    measured = context.measured

    async def observe(phase, operation, *, timeout=None):
        deadlines.append(timeout)
        return await measured(phase, operation, timeout=timeout)

    async def stalled(*args):
        await asyncio.Event().wait()

    monkeypatch.setattr(context, 'run_blocking', stalled)
    monkeypatch.setattr(context, 'PREPARE_SECONDS', 0.01)
    monkeypatch.setattr(context, 'measured', observe)

    async def run():
        # Allow scheduler jitter while proving both reads receive the 10ms cap.
        result = await asyncio.wait_for(context.prepare('u', 's', ['m']), 1)
        assert result == {'summary': '', 'digest': ''}
        assert deadlines == [0.01, 0.01]

    asyncio.run(run())


@pytest.mark.parametrize('failure', ['index', 'slow', 'model'])
def test_real_turn_streams_before_background_summary_even_on_failures(monkeypatch, shaped, failure):
    agentic, runner = shaped
    store = MagicMock()
    store.load_for_turn = store.load
    store.assert_access = MagicMock()
    store.load.return_value = {'generation': 0, 'revision': 0}
    store.source_page.return_value = ([{'role': 'user', 'content': 'Dropped fact'}], None, False)
    if failure == 'index':
        store.source_page.side_effect = FailedPrecondition('synthetic missing index')
    tasks, captures, fallback = [], [], []
    summary_called = []

    async def fake_database(executor, function, *args):
        # These are in-memory fakes. Do not make the 10ms refresh test depend
        # on cold db_executor startup; real worker isolation is tested separately.
        return function(*args)

    async def summary(*args):
        summary_called.append(True)
        if failure == 'slow':
            await asyncio.Event().wait()
        raise ValueError('synthetic summary failure')

    class Model:
        model_name = 'gpt-5.6'

        def bind(self, **kwargs):
            return self

        async def astream(self, messages):
            assert not summary_called and not store.source_page.called
            captures.append(messages)
            yield SimpleNamespace(content='Safe answer', tool_calls=[], tool_call_chunks=[], additional_kwargs={})

    from utils.executors import start_background_task

    def tracked(coro, *, name):
        task = start_background_task(coro, name=name)
        tasks.append(task)
        return task

    monkeypatch.setattr(context, 'ChatContextStore', lambda: store)
    monkeypatch.setattr(context, 'run_blocking', fake_database)
    monkeypatch.setattr(context, 'summarize', summary)
    monkeypatch.setattr(context, 'recent_activity', lambda *args: [])
    monkeypatch.setattr(context, 'REFRESH_SECONDS', 0.01)
    monkeypatch.setattr(context, 'start_background_task', tracked)
    monkeypatch.setattr(context, 'record_fallback', lambda **kw: fallback.append(kw))
    monkeypatch.setattr(agentic, 'get_llm', lambda *args, **kw: Model())
    monkeypatch.setattr(agentic, 'gpt56_explicit_cache_enabled', lambda: False)

    async def run():
        output = []
        await runner.run_shaped_chat_stream(
            '',
            [{'role': 'user', 'content': 'Current request'}],
            [],
            {},
            agentic.AsyncStreamingCallback(),
            output,
            agentic.AgentSafetyGuard(),
            {'user_id': 'u', 'chat_session_id': 's', 'context_message_ids': ['m']},
        )
        assert output == ['Safe answer'] and 'Earlier in this chat' not in str(captures)
        assert sum(task.get_name() == 'shaped-context-refresh' for task in tasks) == 1
        assert all(task.done() for task in tasks if task.get_name() != 'shaped-context-refresh')
        await asyncio.gather(*tasks)
        assert fallback
        # The completed/failed refresh must release the session concurrency slot.
        context.schedule_refresh('u', 's', ['m'])
        assert sum(task.get_name() == 'shaped-context-refresh' for task in tasks) == 2
        await asyncio.gather(*tasks)
        assert bool(summary_called) == (failure != 'index')
        store.save.assert_not_called()

    asyncio.run(run())


def test_overlong_summary_is_truncated_and_checkpointed(monkeypatch, caplog):
    store = MagicMock()
    store.load_for_turn = store.load
    store.assert_access = MagicMock()
    store.load.return_value = {'generation': 0, 'revision': 0}
    store.source_page.return_value = ([{'role': 'user', 'content': 'fact'}], None, False)

    async def summary(*args):
        return 'a' * 5000

    notices = []
    monkeypatch.setattr(context, 'record_fallback', lambda **kw: notices.append(kw))
    with caplog.at_level('INFO', logger=context.__name__):
        asyncio.run(context.refresh('u', 's', ['m'], store=store, summary=summary))
    assert len(store.save.call_args.args[2]['summary']) == context.SUMMARY_CHARS
    assert not notices and 'summary capped' in caplog.text
    assert 'Optional shaped context unavailable' not in caplog.text
    assert 'a' * 100 not in caplog.text


def test_activity_reads_twenty_candidates_without_decrypting_active_session(monkeypatch):
    client = MagicMock()
    query = client.collection.return_value.document.return_value.collection.return_value.order_by.return_value
    query.limit.return_value.stream.return_value = [
        SimpleNamespace(to_dict=lambda: {'chat_session_id': 'active'}) for _ in range(20)
    ]
    decrypt = MagicMock()
    monkeypatch.setattr(history.chat_db, 'db', client)
    monkeypatch.setattr(history.chat_db, 'decrypt_message_payload', decrypt)
    monkeypatch.setattr(history.chat_db, 'iter_all_messages', lambda *a, **kw: pytest.fail('unbounded scan'))
    assert history.recent_activity('u', exclude_session='active') == []
    query.limit.assert_called_once_with(20)
    from database.chat_context_prefetch import no_retry

    query.limit.return_value.stream.assert_called_once_with(timeout=1.0, retry=no_retry())
    decrypt.assert_not_called()


def test_redis_outage_uses_local_global_and_chat_pacing_then_sends(monkeypatch):
    from utils.messaging.adapters.telegram import TelegramAdapter

    monkeypatch.setattr(pacing, 'reserve', lambda *args: (_ for _ in ()).throw(ConnectionError('synthetic outage')))
    notices = []
    from utils.observability import fallback

    monkeypatch.setattr(fallback, 'record_fallback', lambda **kw: notices.append(kw))
    transport = MagicMock()

    async def request(*args, **kw):
        return SimpleNamespace(
            status_code=200, content=b'ok', headers={}, json=lambda: {'ok': True, 'result': {'message_id': 1}}
        )

    transport.request = request
    adapter = TelegramAdapter('synthetic-token', 'synthetic-secret', shared_pacing=True, transport=transport)
    local = []

    async def local_pace(chat, interval=1.05):
        local.append((chat, interval))

    monkeypatch.setattr(adapter, 'pace', local_pace)
    result = asyncio.run(adapter.api('sendMessage', {'chat_id': '42', 'text': 'Answer'}))
    assert result['ok'] and local == [('__global__', 1 / 30), ('42', 1.05)]
    assert len(notices) == 1 and notices[0]['outcome'] == 'degraded'


def test_bad_ttl_omits_all_explicit_options_and_breakpoints(monkeypatch, shaped):
    agentic, runner = shaped
    monkeypatch.setenv('OMI_CHAT_PROMPT_CACHE_TTL', '24h')
    assert prompt_cache.chat_cache_options() is None
    captures = []

    class Model:
        model_name = 'gpt-5.6'

        def bind(self, **kw):
            assert 'extra_body' not in kw
            return self

        async def astream(self, messages):
            captures.append(messages)
            yield SimpleNamespace(content='Answer', tool_calls=[], tool_call_chunks=[], additional_kwargs={})

    monkeypatch.setattr(agentic, 'get_llm', lambda *a, **kw: Model())
    monkeypatch.setattr(agentic, 'gpt56_explicit_cache_enabled', lambda: True)

    async def run():
        await runner.run_shaped_chat_stream(
            '',
            [{'role': 'user', 'content': 'Question'}],
            [],
            {},
            agentic.AsyncStreamingCallback(),
            [],
            agentic.AgentSafetyGuard(),
            {'user_id': 'u'},
        )

    asyncio.run(run())
    assert 'prompt_cache_breakpoint' not in str(captures)
