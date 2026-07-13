from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from utils.llm import gateway_anthropic
from utils.llm.gateway_client import CHAT_AGENT_AUTO_LANE_ID, LLM_GATEWAY_FEATURE_MODE_ENV_VAR


class _MessageStream:
    def __init__(self, events: list[object], *, error: Exception | None = None) -> None:
        self._events = iter(events)
        self._error = error
        self._error_raised = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._events)
        except StopIteration:
            if self._error is not None and not self._error_raised:
                self._error_raised = True
                raise self._error
            raise StopAsyncIteration

    async def get_final_message(self):
        if self._error is not None:
            raise self._error
        return SimpleNamespace(type='message')


class _ContextWithDistinctIterator:
    def __init__(self, events: list[object]) -> None:
        self._iterator = _MessageStream(events)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def __aiter__(self):
        return self._iterator

    async def get_final_message(self):
        return SimpleNamespace(type='message')


def _message_stop_stream(*, error: Exception | None = None) -> _MessageStream:
    return _MessageStream(
        [SimpleNamespace(type='content_block_delta'), SimpleNamespace(type='message_stop')],
        error=error,
    )


def _gateway_client(monkeypatch, *, gateway_messages, legacy_messages, recorded, fallbacks):
    monkeypatch.setenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, 'gateway')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setattr(
        gateway_anthropic,
        '_get_or_create_gateway_anthropic_client',
        lambda **_kwargs: MagicMock(messages=gateway_messages),
    )
    monkeypatch.setattr(
        gateway_anthropic,
        'record_gateway_request_result',
        lambda **kwargs: recorded.append(kwargs),
    )
    monkeypatch.setattr(
        gateway_anthropic,
        'record_gateway_fallback_terminal',
        lambda **kwargs: fallbacks.append(kwargs),
    )
    return gateway_anthropic.get_gateway_first_anthropic_client(
        legacy_client=MagicMock(messages=legacy_messages),
        agent_model='claude-sonnet-4-6',
    )


@pytest.mark.asyncio
async def test_gateway_anthropic_stream_records_success_only_after_message_stop(monkeypatch):
    recorded: list[dict] = []
    fallbacks: list[dict] = []
    gateway_messages = MagicMock()
    gateway_messages.stream.return_value = _message_stop_stream()
    legacy_messages = MagicMock()
    client = _gateway_client(
        monkeypatch,
        gateway_messages=gateway_messages,
        legacy_messages=legacy_messages,
        recorded=recorded,
        fallbacks=fallbacks,
    )

    async with client.messages.stream(model='claude-sonnet-4-6', max_tokens=10) as stream:
        assert recorded == []
        events = [event async for event in stream]

    assert [event.type for event in events] == ['content_block_delta', 'message_stop']
    assert gateway_messages.stream.call_args.kwargs['model'] == CHAT_AGENT_AUTO_LANE_ID
    assert gateway_messages.stream.call_args.kwargs['extra_headers']['X-Omi-Request-ID']
    legacy_messages.stream.assert_not_called()
    assert recorded[0]['mode'] == 'serving'
    assert recorded[0]['outcome'] == 'success'
    assert recorded[0]['request_id'] == gateway_messages.stream.call_args.kwargs['extra_headers']['X-Omi-Request-ID']
    assert fallbacks == []


@pytest.mark.asyncio
async def test_gateway_anthropic_stream_clean_eof_without_message_stop_is_error(monkeypatch):
    recorded: list[dict] = []
    gateway_messages = MagicMock()
    gateway_messages.stream.return_value = _MessageStream([SimpleNamespace(type='content_block_delta')])
    client = _gateway_client(
        monkeypatch,
        gateway_messages=gateway_messages,
        legacy_messages=MagicMock(),
        recorded=recorded,
        fallbacks=[],
    )

    async with client.messages.stream(model='claude-sonnet-4-6', max_tokens=10) as stream:
        _ = [event async for event in stream]

    assert recorded[0]['outcome'] == 'error'
    assert recorded[0]['reason'] == 'stream_eof_before_message_stop'


@pytest.mark.asyncio
async def test_gateway_anthropic_stream_early_consumer_exit_is_cancelled(monkeypatch):
    recorded: list[dict] = []
    gateway_messages = MagicMock()
    gateway_messages.stream.return_value = _message_stop_stream()
    client = _gateway_client(
        monkeypatch,
        gateway_messages=gateway_messages,
        legacy_messages=MagicMock(),
        recorded=recorded,
        fallbacks=[],
    )

    async with client.messages.stream(model='claude-sonnet-4-6', max_tokens=10) as stream:
        first = await anext(stream)
        assert first.type == 'content_block_delta'

    assert len(recorded) == 1
    assert recorded[0]['outcome'] == 'cancelled'
    assert recorded[0]['reason'] == 'consumer_abandoned_stream'


@pytest.mark.asyncio
async def test_gateway_anthropic_stream_task_cancellation_is_not_an_error(monkeypatch):
    recorded: list[dict] = []
    gateway_messages = MagicMock()
    gateway_messages.stream.return_value = _message_stop_stream()
    client = _gateway_client(
        monkeypatch,
        gateway_messages=gateway_messages,
        legacy_messages=MagicMock(),
        recorded=recorded,
        fallbacks=[],
    )

    stream = client.messages.stream(model='claude-sonnet-4-6', max_tokens=10)
    await stream.__aenter__()
    await stream.__aexit__(asyncio.CancelledError, asyncio.CancelledError(), None)

    assert len(recorded) == 1
    assert recorded[0]['outcome'] == 'cancelled'
    assert recorded[0]['reason'] == 'client_cancelled'


@pytest.mark.asyncio
async def test_gateway_anthropic_consumer_body_failure_is_not_mislabeled_cancelled(monkeypatch):
    recorded: list[dict] = []
    gateway_messages = MagicMock()
    gateway_messages.stream.return_value = _message_stop_stream()
    client = _gateway_client(
        monkeypatch,
        gateway_messages=gateway_messages,
        legacy_messages=MagicMock(),
        recorded=recorded,
        fallbacks=[],
    )

    with pytest.raises(RuntimeError, match='consumer callback failed'):
        async with client.messages.stream(model='claude-sonnet-4-6', max_tokens=10) as stream:
            _ = await anext(stream)
            raise RuntimeError('consumer callback failed')

    assert len(recorded) == 1
    assert recorded[0]['outcome'] == 'error'
    assert recorded[0]['reason'] == 'consumer_stream_exception'


@pytest.mark.asyncio
async def test_gateway_anthropic_stream_honors_distinct_active_iterator(monkeypatch):
    recorded: list[dict] = []
    gateway_messages = MagicMock()
    gateway_messages.stream.return_value = _ContextWithDistinctIterator(
        [SimpleNamespace(type='content_block_delta'), SimpleNamespace(type='message_stop')]
    )
    client = _gateway_client(
        monkeypatch,
        gateway_messages=gateway_messages,
        legacy_messages=MagicMock(),
        recorded=recorded,
        fallbacks=[],
    )

    async with client.messages.stream(model='claude-sonnet-4-6', max_tokens=10) as stream:
        events = [event async for event in stream]

    assert [event.type for event in events] == ['content_block_delta', 'message_stop']
    assert recorded[0]['outcome'] == 'success'


@pytest.mark.asyncio
async def test_gateway_anthropic_stream_fallback_records_recovered_after_legacy_message_stop(monkeypatch):
    recorded: list[dict] = []
    fallbacks: list[dict] = []
    gateway_messages = MagicMock()
    gateway_messages.stream.side_effect = httpx.ConnectError('connection refused')
    legacy_messages = MagicMock()
    legacy_messages.stream.return_value = _message_stop_stream()
    client = _gateway_client(
        monkeypatch,
        gateway_messages=gateway_messages,
        legacy_messages=legacy_messages,
        recorded=recorded,
        fallbacks=fallbacks,
    )

    async with client.messages.stream(model='claude-sonnet-4-6', max_tokens=10) as stream:
        assert fallbacks == []
        _ = [event async for event in stream]

    assert legacy_messages.stream.call_args.kwargs['model'] == 'claude-sonnet-4-6'
    assert fallbacks[0]['outcome'] == 'recovered'
    assert fallbacks[0]['request_id']
    assert recorded == []


@pytest.mark.asyncio
async def test_gateway_anthropic_stream_fallback_records_exhausted_on_legacy_failure(monkeypatch):
    fallbacks: list[dict] = []
    gateway_messages = MagicMock()
    gateway_messages.stream.side_effect = httpx.ConnectError('connection refused')
    legacy_messages = MagicMock()
    legacy_messages.stream.return_value = _MessageStream([], error=httpx.ReadError('legacy reset'))
    client = _gateway_client(
        monkeypatch,
        gateway_messages=gateway_messages,
        legacy_messages=legacy_messages,
        recorded=[],
        fallbacks=fallbacks,
    )

    with pytest.raises(httpx.ReadError):
        async with client.messages.stream(model='claude-sonnet-4-6', max_tokens=10) as stream:
            _ = [event async for event in stream]

    assert fallbacks[0]['outcome'] == 'exhausted'


@pytest.mark.asyncio
async def test_gateway_anthropic_fallback_consumer_exit_preserves_cancelled_request_outcome(monkeypatch):
    recorded: list[dict] = []
    fallbacks: list[dict] = []
    gateway_messages = MagicMock()
    gateway_messages.stream.side_effect = httpx.ConnectError('connection refused')
    legacy_messages = MagicMock()
    legacy_messages.stream.return_value = _message_stop_stream()
    client = _gateway_client(
        monkeypatch,
        gateway_messages=gateway_messages,
        legacy_messages=legacy_messages,
        recorded=recorded,
        fallbacks=fallbacks,
    )

    async with client.messages.stream(model='claude-sonnet-4-6', max_tokens=10) as stream:
        _ = await anext(stream)

    assert fallbacks == []
    assert len(recorded) == 1
    assert recorded[0]['mode'] == 'fallback'
    assert recorded[0]['outcome'] == 'cancelled'
    assert recorded[0]['reason'] == 'consumer_abandoned_stream'


@pytest.mark.asyncio
async def test_gateway_anthropic_fallback_consumer_body_failure_is_request_error_not_exhausted(monkeypatch):
    recorded: list[dict] = []
    fallbacks: list[dict] = []
    gateway_messages = MagicMock()
    gateway_messages.stream.side_effect = httpx.ConnectError('connection refused')
    legacy_messages = MagicMock()
    legacy_messages.stream.return_value = _message_stop_stream()
    client = _gateway_client(
        monkeypatch,
        gateway_messages=gateway_messages,
        legacy_messages=legacy_messages,
        recorded=recorded,
        fallbacks=fallbacks,
    )

    with pytest.raises(RuntimeError, match='consumer callback failed'):
        async with client.messages.stream(model='claude-sonnet-4-6', max_tokens=10) as stream:
            _ = await anext(stream)
            raise RuntimeError('consumer callback failed')

    assert fallbacks == []
    assert len(recorded) == 1
    assert recorded[0]['mode'] == 'fallback'
    assert recorded[0]['outcome'] == 'error'
    assert recorded[0]['reason'] == 'consumer_stream_exception'


@pytest.mark.asyncio
async def test_gateway_anthropic_nonstream_fallback_waits_for_legacy_success(monkeypatch):
    fallbacks: list[dict] = []
    gateway_messages = MagicMock()
    gateway_messages.create = AsyncMock(side_effect=httpx.ConnectError('connection refused'))
    legacy_messages = MagicMock()
    legacy_messages.create = AsyncMock(return_value=SimpleNamespace(id='legacy-message'))
    client = _gateway_client(
        monkeypatch,
        gateway_messages=gateway_messages,
        legacy_messages=legacy_messages,
        recorded=[],
        fallbacks=fallbacks,
    )

    result = await client.messages.create(model='claude-sonnet-4-6', max_tokens=10)

    assert result.id == 'legacy-message'
    assert fallbacks[0]['outcome'] == 'recovered'


@pytest.mark.asyncio
async def test_gateway_anthropic_nontransport_failure_records_terminal_error_without_fallback(monkeypatch):
    recorded: list[dict] = []
    gateway_messages = MagicMock()
    gateway_messages.create = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            'unauthorized',
            request=httpx.Request('POST', 'http://gateway/v1/messages'),
            response=httpx.Response(401),
        )
    )
    client = _gateway_client(
        monkeypatch,
        gateway_messages=gateway_messages,
        legacy_messages=MagicMock(),
        recorded=recorded,
        fallbacks=[],
    )

    with pytest.raises(httpx.HTTPStatusError):
        await client.messages.create(model='claude-sonnet-4-6', max_tokens=10)

    assert len(recorded) == 1
    assert recorded[0]['outcome'] == 'error'
    assert recorded[0]['reason'] == 'auth'
    assert recorded[0]['request_id']
