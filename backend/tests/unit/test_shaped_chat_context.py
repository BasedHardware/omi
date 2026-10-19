"""Context ordering, epoch continuity, explicit boundaries and provider usage contracts."""

import asyncio
import copy
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from database.chat_history_window import cache_aligned_history_limit
from utils.messaging.context import assemble, prepare, refresh, DIGEST_CHARS
from utils.messaging.projection import SurfaceRuntime
from utils.messaging.contracts import Principal
from utils.messaging import context as context_module
from utils.llm import usage_tracker
from utils.llm.prompt_cache import chat_cache_options


def rows(total):
    return [{'role': 'user' if i % 2 == 0 else 'assistant', 'content': 'message ' + str(i)} for i in range(total)]


@pytest.mark.parametrize('surface', ['app', 'telegram', 'imessage'])
def test_same_epoch_prefix_is_byte_identical_with_clock_digest_scope_changes(surface):
    full = rows(15)
    runtime = (
        None
        if surface == 'app'
        else SurfaceRuntime(
            'channel:test',
            '',
            Principal('u'),
            evidence=({'role': 'user', 'content': 'current one'},),
            request_at=datetime(2026, 10, 14, tzinfo=timezone.utc),
        )
    )
    one = assemble(
        full[:13],
        runtime=runtime,
        summary='Earlier facts',
        digest='Activity elsewhere: first',
        request_context={'chat_scope': 'page1'},
        explicit_cache=True,
        stable_prefix='x' * 5000,
    )
    runtime2 = (
        None
        if runtime is None
        else SurfaceRuntime(
            'channel:test',
            '',
            Principal('u'),
            evidence=({'role': 'user', 'content': 'current two'},),
            request_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
        )
    )
    two = assemble(
        full[:15],
        runtime=runtime2,
        summary='Earlier facts',
        digest='Activity elsewhere: second',
        request_context={'chat_scope': 'page2'},
        explicit_cache=True,
        stable_prefix='x' * 5000,
    )
    assert json.dumps(one[:-1], sort_keys=True).encode() == json.dumps(two[: len(one) - 1], sort_keys=True).encode()
    assert 'Earlier in this chat' in str(one[0])
    assert str(one).count('prompt_cache_breakpoint') == 1
    assert str(two).count('prompt_cache_breakpoint') == 1
    for part in one[:-1]:
        assert (
            'Request context' not in str(part)
            and 'request clock' not in str(part)
            and 'Activity elsewhere' not in str(part)
        )
    assert 'Activity elsewhere: first' in str(one[-1]) and 'page1' in str(one[-1])
    assert ('Server-verified request clock' in str(one[-1])) == (surface != 'app')
    assert 'prompt_cache_breakpoint' not in str(one[-1])


@pytest.mark.parametrize('count', [1, 9, 10, 13, 17, 18, 31, 399])
def test_window_is_bounded_and_has_current_user_last(count):
    result = assemble(rows(count))
    assert len(result) <= 18  # synthetic even count adds a new empty user turn
    assert result[-1]['role'] == 'user'
    assert len(result) <= cache_aligned_history_limit(count) + 1


class StateStore:
    def __init__(self, total=30):
        self.all = rows(total)
        self.state: dict[str, Any] = {'generation': 0, 'revision': 0}
        self.saves = []

    def assert_access(self, *args):
        pass

    def load(self, *args):
        return copy.deepcopy(self.state)

    def load_for_turn(self, *args):
        return self.load(*args)

    def source_page(self, uid, session, before, cursor=None) -> tuple[list, dict | None, bool]:
        start = int(cursor['id']) + 1 if cursor else 0
        stop = int(before)
        result = self.all[start:stop]
        return result, {'id': str(stop - 1)} if result else cursor, False

    def save(self, uid, session, state, revision):
        assert revision == self.state['revision']
        self.state = dict(state, revision=revision + 1)
        self.saves.append(copy.deepcopy(state))


def test_summary_only_changes_when_window_start_jumps_and_preserves_dropped_span(monkeypatch):
    monkeypatch.setattr(context_module, 'recent_activity', lambda *args: [])
    store = StateStore()
    requests = []

    async def summary(uid, text):
        requests.append(text)
        return 'Compact continuity'

    async def run():
        first = await refresh('u', 's', [str(i) for i in range(13)], store=store, summary=summary)
        second = await refresh('u', 's', [str(i) for i in range(15)], store=store, summary=summary)
        assert first == second and not requests
        await refresh('u', 's', [str(i) for i in range(8, 19)], store=store, summary=summary)
        assert store.state['summary'] == 'Compact continuity'
        assert len(requests) == 1
        assert all('message ' + str(i) in requests[0] for i in range(8))
        await refresh('u', 's', [str(i) for i in range(8, 21)], store=store, summary=summary)
        assert len(requests) == 1

    asyncio.run(run())


def test_summary_failure_does_not_advance_cursor(monkeypatch):
    monkeypatch.setattr(context_module, 'recent_activity', lambda *args: [])
    store = StateStore()

    async def invalid(*args):
        return ''

    with pytest.raises(ValueError):
        asyncio.run(refresh('u', 's', ['8'], store=store, summary=invalid))
    assert store.state == {'generation': 0, 'revision': 0} and not store.saves


def test_long_bootstrap_retries_after_last_completed_page(monkeypatch):
    monkeypatch.setattr(context_module, 'recent_activity', lambda *args: [])

    class Pages(StateStore):
        def source_page(self, uid, session, before, cursor=None):
            if cursor is None:
                return self.all[:4], {'id': '3'}, True
            return self.all[4:8], {'id': '7'}, False

    store = Pages()
    calls = []

    async def failing(uid, text):
        calls.append(text)
        if len(calls) == 2:
            raise TimeoutError('Turn deadline')
        return 'First page continuity'

    with pytest.raises(TimeoutError):
        asyncio.run(refresh('u', 's', ['8'], store=store, summary=failing))
    assert store.state['cursor'] == {'id': '3'} and 'anchor' not in store.state
    assert len(store.saves) == 1

    async def retry(uid, text):
        assert 'First page continuity' in text and 'message 4' in text
        assert 'message 0' not in text
        return 'All earlier continuity'

    asyncio.run(refresh('u', 's', ['8'], store=store, summary=retry))
    assert store.state['summary'] == 'All earlier continuity'
    assert store.state['anchor'] == '8' and store.state['cursor'] == {'id': '7'}


def test_activity_is_bounded_and_not_an_event_log_append(monkeypatch):
    activity = [{'created_at': datetime.now(timezone.utc), 'sender': 'human', 'text': 'a' * 12000}]
    monkeypatch.setattr(context_module, 'recent_activity', lambda *args: activity)
    store = StateStore()
    result = asyncio.run(prepare('u', 's', ['0'], store=store))
    assert len(result['digest']) <= DIGEST_CHARS
    assert store.state == {'generation': 0, 'revision': 0}
    assert not hasattr(store, 'append_event')


def test_chat_usage_extracts_stream_metadata_read_write_and_surface():
    calls = []
    callback = usage_tracker.LLMUsageCallback(flush_fn=lambda *a, **kw: calls.append((a, kw)))
    message = AIMessage(
        content='',
        usage_metadata={'input_tokens': 1200, 'output_tokens': 30, 'total_tokens': 1230},
        response_metadata={
            'omi_token_usage': {
                'prompt_tokens': 1200,
                'completion_tokens': 30,
                'prompt_tokens_details': {'cached_tokens': 800, 'cache_write_tokens': 100},
            }
        },
    )
    token = usage_tracker.set_usage_context('u', 'chat_agent', surface='telegram', turn_id='turn')
    try:
        callback.on_llm_end(LLMResult(generations=[[ChatGeneration(message=message)]], llm_output=None))
    finally:
        usage_tracker.reset_usage_context(token)
    assert calls[0][0][:2] == ('u', 'chat_agent') and calls[0][0][-2:] == (1200, 30)
    assert calls[0][1] == {
        'cache_read_tokens': 800,
        'cache_write_tokens': 100,
        'surface': 'telegram',
        'turn_id': 'turn',
    }


def test_ttl_only_accepts_verified_supported_contract(monkeypatch):
    monkeypatch.delenv('OMI_CHAT_PROMPT_CACHE_TTL', raising=False)
    assert chat_cache_options() == {'mode': 'explicit', 'ttl': '30m'}
    monkeypatch.setenv('OMI_CHAT_PROMPT_CACHE_TTL', '24h')
    assert chat_cache_options() is None


@pytest.fixture(scope='module')
def sdk_client():
    from utils.llm.gateway_client import GatewayContextChatOpenAI

    return GatewayContextChatOpenAI(model='gpt-5.6', api_key='synthetic-test-key')


def test_gateway_sdk_retains_cache_write_tokens_before_langchain_drops_them(sdk_client):
    from langchain_core.messages import AIMessageChunk

    client = sdk_client
    generation = client._convert_chunk_to_generation_chunk(
        {
            'choices': [],
            'usage': {
                'prompt_tokens': 1200,
                'completion_tokens': 40,
                'prompt_tokens_details': {'cached_tokens': 500, 'cache_write_tokens': 200},
            },
        },
        AIMessageChunk,
        {},
    )
    assert generation.message.response_metadata['omi_token_usage']['prompt_tokens_details'] == {
        'cached_tokens': 500,
        'cache_write_tokens': 200,
    }
    calls = []
    token = usage_tracker.set_usage_context('u', 'chat_agent', surface='imessage', turn_id='sdk-turn')
    try:
        usage_tracker.LLMUsageCallback(flush_fn=lambda *a, **kw: calls.append(kw)).on_llm_end(
            LLMResult(generations=[[ChatGeneration(message=generation.message)]], llm_output=None)
        )
    finally:
        usage_tracker.reset_usage_context(token)
    assert calls == [
        {'cache_read_tokens': 500, 'cache_write_tokens': 200, 'surface': 'imessage', 'turn_id': 'sdk-turn'}
    ]


@pytest.fixture(scope='module')
def shaped_agentic():
    from utils.retrieval import agentic

    return agentic


@pytest.mark.parametrize('channel', [None, 'telegram', 'imessage'])
def test_real_shaped_runner_preserves_system_and_stable_history(monkeypatch, channel, shaped_agentic):
    agentic = shaped_agentic
    from utils.messaging.projection import surface_runtime

    captures = []

    class Model:
        model_name = 'gpt-5.6'

        def bind(self, **kw):
            assert kw['extra_body']['prompt_cache_options'] == {'mode': 'explicit', 'ttl': '30m'}
            return self

        async def astream(self, messages):
            captures.append(copy.deepcopy(messages))
            yield SimpleNamespace(content='Answer', tool_calls=[], tool_call_chunks=[], additional_kwargs={})

    monkeypatch.setattr(agentic, 'get_llm', lambda *a, **kw: Model())
    monkeypatch.setattr(agentic, 'gpt56_explicit_cache_enabled', lambda: True)

    async def run():
        for count, day in [(13, 14), (15, 15)]:
            runtime = (
                None
                if channel is None
                else SurfaceRuntime(
                    'channel:test',
                    '',
                    Principal('u'),
                    evidence=({'role': 'user', 'content': 'current ' + str(count)},),
                    request_at=datetime(2026, 10, day, tzinfo=timezone.utc),
                    channel=channel,
                )
            )
            token = surface_runtime.set(runtime)
            try:
                messages = rows(count)
                if channel is None:
                    messages[-1]['content'] = 'Current datetime: ' + str(day) + '\n' + messages[-1]['content']
                await agentic._run_shaped_chat_stream(
                    'old',
                    messages,
                    [
                        {
                            'type': 'function',
                            'function': {
                                'name': 'history',
                                'description': 'Stable tool contract. ' * 240,
                                'parameters': {'type': 'object'},
                            },
                        }
                    ],
                    {},
                    agentic.AsyncStreamingCallback(),
                    [],
                    agentic.AgentSafetyGuard(),
                    {'user_id': 'u', 'chat_scope': {'page': day}},
                )
            finally:
                surface_runtime.reset(token)

    asyncio.run(run())
    assert json.dumps(captures[0][:-1], sort_keys=True) == json.dumps(
        captures[1][: len(captures[0]) - 1], sort_keys=True
    )
    assert 'Request context' not in str(captures[0][:-1])
    assert 'Request context' in str(captures[0][-1])
    assert 'prompt_cache_breakpoint' in str(captures[0][1:-1])
    assert str(captures[0]).count('prompt_cache_breakpoint') == 2
    assert str(captures[1]).count('prompt_cache_breakpoint') == 2


@pytest.mark.asyncio
async def test_digest_latency_does_not_discard_ready_summary(monkeypatch):
    # The old serial path timed out at 150ms and threw away this loaded summary.
    async def blocking(executor, fn, *args):
        await asyncio.sleep(0.11 if fn.__name__ == 'load_for_turn' else 0.065)
        return fn(*args)

    monkeypatch.setattr(context_module, 'run_blocking', blocking)
    monkeypatch.setattr(context_module, 'recent_activity', lambda *a: [])
    store = StateStore()
    store.state['summary'] = 'Continuity survives'
    result = await prepare('u', 's', ['0'], store=store)
    assert result['summary'] == 'Continuity survives'


@pytest.mark.asyncio
async def test_digest_timeout_keeps_summary_and_logs_phase_without_exception_text(monkeypatch, caplog):
    async def blocking(executor, fn, *args):
        if fn.__name__ != 'load_for_turn':
            await asyncio.sleep(1)
        return fn(*args)

    monkeypatch.setattr(context_module, 'run_blocking', blocking)
    monkeypatch.setattr(context_module, 'recent_activity', lambda *a: [])
    store = StateStore()
    store.state['summary'] = 'Stored continuity'
    result = await prepare('private-user', 'private-session', ['0'], store=store)
    assert result == {'summary': 'Stored continuity', 'digest': ''}
    assert 'phase=digest' in caplog.text and 'error_type=TimeoutError' in caplog.text
    assert 'private-user' not in caplog.text and 'private-session' not in caplog.text


@pytest.mark.asyncio
async def test_permission_guard_discards_digest_and_logs_code_site(monkeypatch, caplog):
    class Removed(StateStore):
        def load(self, *args):
            raise PermissionError('private user data must never be logged')

    monkeypatch.setattr(
        context_module,
        'recent_activity',
        lambda *a: [{'created_at': datetime.now(timezone.utc), 'sender': 'human', 'text': 'private activity'}],
    )
    result = await prepare('u', 's', ['0'], store=Removed())
    assert result == {'summary': '', 'digest': ''}
    assert 'phase=summary_load' in caplog.text and 'error_type=PermissionError' in caplog.text
    assert 'private user data' not in caplog.text


def test_context_load_uses_guarded_snapshots_without_rereading(monkeypatch):
    from database.chat_context import ChatContextStore
    from unittest.mock import MagicMock

    messaging = MagicMock()
    store = ChatContextStore(messaging=messaging)
    monkeypatch.setattr(
        store, 'assert_access', lambda *a: ({'shaped_context_revision': 4}, {'chat_context_generation': 2})
    )
    assert store.load('u', 's') == {'generation': 2, 'revision': 4}
    messaging.user.assert_not_called()


@pytest.mark.asyncio
async def test_malformed_digest_does_not_discard_summary(monkeypatch, caplog):
    monkeypatch.setattr(context_module, 'recent_activity', lambda *a: [{'text': 'private malformed row'}])
    store = StateStore()
    store.state['summary'] = 'Stored continuity'
    assert await prepare('u', 's', ['0'], store=store) == {'summary': 'Stored continuity', 'digest': ''}
    assert 'phase=digest' in caplog.text and 'error_type=KeyError' in caplog.text
    assert 'private malformed row' not in caplog.text
