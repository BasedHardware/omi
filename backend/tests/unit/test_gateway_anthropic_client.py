from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from utils.llm import gateway_anthropic
from utils.llm.gateway_client import CHAT_AGENT_AUTO_LANE_ID, LLM_GATEWAY_FEATURE_MODE_ENV_VAR
from utils.llm.gateway_resilience import GatewayCircuitBreaker


@pytest.fixture(autouse=True)
def _reset_gateway_circuit_between_tests():
    gateway_anthropic.gateway_circuit.reset()
    yield
    gateway_anthropic.gateway_circuit.reset()


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


def _message_stop_stream() -> _MessageStream:
    return _MessageStream([SimpleNamespace(type='content_block_delta'), SimpleNamespace(type='message_stop')])


def _gateway_client(monkeypatch, *, gateway_messages, recorded):
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
    return gateway_anthropic.get_gateway_anthropic_client()


@pytest.mark.asyncio
async def test_gateway_anthropic_stream_uses_fixed_lane_and_records_success(monkeypatch):
    recorded: list[dict] = []
    gateway_messages = MagicMock()
    gateway_messages.stream.return_value = _message_stop_stream()
    client = _gateway_client(
        monkeypatch,
        gateway_messages=gateway_messages,
        recorded=recorded,
    )

    async with client.messages.stream(model='caller-selected-model', max_tokens=10) as stream:
        events = [event async for event in stream]

    assert [event.type for event in events] == ['content_block_delta', 'message_stop']
    assert gateway_messages.stream.call_args.kwargs['model'] == CHAT_AGENT_AUTO_LANE_ID
    assert gateway_messages.stream.call_args.kwargs['extra_headers']['X-Omi-Request-ID']
    assert recorded[0]['mode'] == 'serving'
    assert recorded[0]['outcome'] == 'success'


@pytest.mark.asyncio
async def test_gateway_anthropic_stream_transport_failure_fails_closed(monkeypatch):
    recorded: list[dict] = []
    gateway_messages = MagicMock()
    gateway_messages.stream.return_value = _MessageStream([], error=httpx.ReadTimeout('first byte timed out'))
    client = _gateway_client(
        monkeypatch,
        gateway_messages=gateway_messages,
        recorded=recorded,
    )

    with pytest.raises(gateway_anthropic.LlmGatewayUnavailableError):
        async with client.messages.stream(model='claude-sonnet-4-6', max_tokens=10) as stream:
            _ = [event async for event in stream]

    assert recorded[0]['outcome'] == 'error'
    assert recorded[0]['reason'] == 'timeout'


@pytest.mark.asyncio
async def test_gateway_anthropic_nonstream_transport_failure_fails_closed(monkeypatch):
    recorded: list[dict] = []
    gateway_messages = MagicMock()
    gateway_messages.create = AsyncMock(side_effect=httpx.ConnectError('connection refused'))
    client = _gateway_client(
        monkeypatch,
        gateway_messages=gateway_messages,
        recorded=recorded,
    )

    with pytest.raises(gateway_anthropic.LlmGatewayUnavailableError):
        await client.messages.create(model='claude-sonnet-4-6', max_tokens=10)

    assert recorded[0]['outcome'] == 'error'
    assert recorded[0]['reason'] == 'request_error'


@pytest.mark.asyncio
async def test_gateway_anthropic_open_circuit_fails_closed(monkeypatch):
    circuit = GatewayCircuitBreaker(failure_threshold=1, cooldown_seconds=30.0)
    circuit.record_transport_failure()
    monkeypatch.setattr(gateway_anthropic, 'gateway_circuit', circuit)
    recorded: list[dict] = []
    gateway_messages = MagicMock()
    gateway_messages.create = AsyncMock()
    client = _gateway_client(
        monkeypatch,
        gateway_messages=gateway_messages,
        recorded=recorded,
    )

    with pytest.raises(gateway_anthropic.LlmGatewayUnavailableError, match='circuit is open'):
        await client.messages.create(model='claude-sonnet-4-6', max_tokens=10)

    gateway_messages.create.assert_not_awaited()
    assert recorded[0]['reason'] == 'circuit_open'


@pytest.mark.asyncio
async def test_gateway_anthropic_nontransport_failure_propagates(monkeypatch):
    recorded: list[dict] = []
    request = httpx.Request('POST', 'http://gateway/v1/messages')
    gateway_messages = MagicMock()
    gateway_messages.create = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            'unauthorized',
            request=request,
            response=httpx.Response(401, request=request),
        )
    )
    client = _gateway_client(
        monkeypatch,
        gateway_messages=gateway_messages,
        recorded=recorded,
    )

    with pytest.raises(httpx.HTTPStatusError):
        await client.messages.create(model='claude-sonnet-4-6', max_tokens=10)

    assert recorded[0]['outcome'] == 'error'
    assert recorded[0]['reason'] == 'auth'
