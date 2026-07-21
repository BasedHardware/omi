from __future__ import annotations

from typing import Any, AsyncIterator, Iterator
import uuid

import httpx
import pytest
from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from utils.llm import gateway_serving
from utils.llm.gateway_client import feature_auto_lane_id
from utils.llm.gateway_resilience import GatewayCircuitBreaker


@pytest.fixture(autouse=True)
def _reset_gateway_circuit_between_tests():
    gateway_serving.gateway_circuit.reset()
    yield
    gateway_serving.gateway_circuit.reset()


class _StreamChatModel(BaseChatModel):
    name: str
    chunks: list[str]
    fail_before_yield: bool = False
    fail_after_chunks: bool = False
    calls: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return self.name

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.calls.append(kwargs)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content='sync'))])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[Any]:
        self.calls.append(kwargs)
        if self.fail_before_yield:
            raise httpx.ConnectError('connection refused')
        for chunk in self.chunks:
            yield ChatGeneration(message=AIMessage(content=chunk))
        if self.fail_after_chunks:
            raise httpx.ReadError('stream reset')

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> AsyncIterator[Any]:
        self.calls.append(kwargs)
        if self.fail_before_yield:
            raise httpx.ConnectError('connection refused')
        for chunk in self.chunks:
            yield ChatGeneration(message=AIMessage(content=chunk))
        if self.fail_after_chunks:
            raise httpx.ReadError('stream reset')


def test_gateway_serving_stream_records_serving_mode_on_success(monkeypatch):
    recorded: list[dict[str, Any]] = []
    monkeypatch.setattr(
        gateway_serving,
        'record_gateway_request_result',
        lambda **kwargs: recorded.append(kwargs),
    )

    gateway = _StreamChatModel(name='gateway', chunks=['a', 'b'])
    legacy = _StreamChatModel(name='legacy', chunks=['x'])
    wrapped = gateway_serving.wrap_gateway_with_legacy_fallback(
        feature='chat_responses',
        gateway_model=gateway,
        legacy_model=legacy,
    )

    chunks = list(wrapped._stream([]))

    assert len(chunks) == 2
    assert len(recorded) == 1
    assert recorded[0] == {
        'feature': 'chat_responses',
        'outcome': 'success',
        'reason': 'ok',
        'route': feature_auto_lane_id('chat_responses'),
        'mode': 'serving',
        'request_id': recorded[0]['request_id'],
    }
    assert str(uuid.UUID(recorded[0]['request_id'])) == recorded[0]['request_id']
    assert gateway.calls[0]['extra_headers']['X-Omi-Request-ID'] == recorded[0]['request_id']


def test_gateway_serving_stream_falls_back_before_first_chunk(monkeypatch):
    recorded: list[dict[str, Any]] = []
    fallbacks: list[dict[str, Any]] = []
    monkeypatch.setattr(
        gateway_serving,
        'record_gateway_request_result',
        lambda **kwargs: recorded.append(kwargs),
    )
    monkeypatch.setattr(gateway_serving, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))

    gateway = _StreamChatModel(name='gateway', chunks=[], fail_before_yield=True)
    legacy = _StreamChatModel(name='legacy', chunks=['fallback'])
    wrapped = gateway_serving.wrap_gateway_with_legacy_fallback(
        feature='chat_responses',
        gateway_model=gateway,
        legacy_model=legacy,
    )

    chunks = list(wrapped._stream([]))

    assert len(chunks) == 1
    assert recorded[0]['mode'] == 'fallback'
    assert recorded[0]['outcome'] == 'fallback'
    assert fallbacks[0]['outcome'] == 'recovered'


def test_gateway_serving_open_circuit_bypasses_a_second_transport_attempt(monkeypatch):
    monkeypatch.setattr(
        gateway_serving,
        'gateway_circuit',
        GatewayCircuitBreaker(failure_threshold=1, cooldown_seconds=30.0),
    )
    gateway = _StreamChatModel(name='gateway', chunks=[], fail_before_yield=True)
    legacy = _StreamChatModel(name='legacy', chunks=['fallback'])
    wrapped = gateway_serving.wrap_gateway_with_legacy_fallback(
        feature='chat_responses',
        gateway_model=gateway,
        legacy_model=legacy,
    )

    assert [chunk.message.content for chunk in wrapped._stream([])] == ['fallback']
    assert [chunk.message.content for chunk in wrapped._stream([])] == ['fallback']

    assert len(gateway.calls) == 1
    assert len(legacy.calls) == 2


def test_gateway_serving_stream_empty_gateway_uses_legacy_and_does_not_claim_gateway_success(monkeypatch):
    recorded: list[dict[str, Any]] = []
    fallbacks: list[dict[str, Any]] = []
    monkeypatch.setattr(gateway_serving, 'record_gateway_request_result', lambda **kwargs: recorded.append(kwargs))
    monkeypatch.setattr(gateway_serving, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))

    wrapped = gateway_serving.wrap_gateway_with_legacy_fallback(
        feature='chat_responses',
        gateway_model=_StreamChatModel(name='gateway', chunks=[]),
        legacy_model=_StreamChatModel(name='legacy', chunks=['fallback']),
    )

    chunks = list(wrapped._stream([]))

    assert len(chunks) == 1
    assert len(recorded) == 1
    assert recorded[0] == {
        'feature': 'chat_responses',
        'outcome': 'fallback',
        'reason': 'empty_stream_before_output',
        'route': feature_auto_lane_id('chat_responses'),
        'mode': 'fallback',
        'request_id': recorded[0]['request_id'],
    }
    assert str(uuid.UUID(recorded[0]['request_id'])) == recorded[0]['request_id']
    assert fallbacks[0]['outcome'] == 'recovered'


def test_fallback_cancellation_does_not_invent_shared_terminal_outcome(monkeypatch):
    recorded: list[dict[str, Any]] = []
    fallbacks: list[dict[str, Any]] = []
    monkeypatch.setattr(gateway_serving, 'record_gateway_request_result', lambda **kwargs: recorded.append(kwargs))
    monkeypatch.setattr(gateway_serving, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))

    gateway_serving.record_gateway_fallback_terminal(
        feature='chat_agent',
        gateway_reason='request_error',
        outcome='exhausted',
        request_id='opaque-request-id',
        credential_source='omi_managed',
        request_outcome='cancelled',
        request_reason='consumer_abandoned_stream',
    )

    assert recorded[0]['outcome'] == 'cancelled'
    assert recorded[0]['reason'] == 'consumer_abandoned_stream'
    assert recorded[0]['mode'] == 'fallback'
    assert fallbacks == []


def test_gateway_serving_stream_records_exhausted_when_legacy_fallback_fails(monkeypatch):
    recorded: list[dict[str, Any]] = []
    fallbacks: list[dict[str, Any]] = []
    monkeypatch.setattr(gateway_serving, 'record_gateway_request_result', lambda **kwargs: recorded.append(kwargs))
    monkeypatch.setattr(gateway_serving, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))

    wrapped = gateway_serving.wrap_gateway_with_legacy_fallback(
        feature='chat_responses',
        gateway_model=_StreamChatModel(name='gateway', chunks=[], fail_before_yield=True),
        legacy_model=_StreamChatModel(name='legacy', chunks=[], fail_before_yield=True),
    )

    with pytest.raises(httpx.ConnectError):
        list(wrapped._stream([]))

    assert recorded[0]['outcome'] == 'error'
    assert recorded[0]['reason'].startswith('fallback_exhausted_')
    assert fallbacks[0]['outcome'] == 'exhausted'


def test_gateway_serving_midstream_failure_is_error_without_legacy_fallback(monkeypatch):
    recorded: list[dict[str, Any]] = []
    fallbacks: list[dict[str, Any]] = []
    legacy = _StreamChatModel(name='legacy', chunks=['must-not-run'])
    monkeypatch.setattr(gateway_serving, 'record_gateway_request_result', lambda **kwargs: recorded.append(kwargs))
    monkeypatch.setattr(gateway_serving, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))

    wrapped = gateway_serving.wrap_gateway_with_legacy_fallback(
        feature='chat_responses',
        gateway_model=_StreamChatModel(name='gateway', chunks=['partial'], fail_after_chunks=True),
        legacy_model=legacy,
    )

    with pytest.raises(httpx.ReadError):
        list(wrapped._stream([]))

    assert recorded[0]['outcome'] == 'error'
    assert recorded[0]['reason'].startswith('midstream_')
    assert fallbacks == []


def test_gateway_serving_stream_close_records_cancelled_exactly_once(monkeypatch):
    recorded: list[dict[str, Any]] = []
    monkeypatch.setattr(gateway_serving, 'record_gateway_request_result', lambda **kwargs: recorded.append(kwargs))
    wrapped = gateway_serving.wrap_gateway_with_legacy_fallback(
        feature='chat_responses',
        gateway_model=_StreamChatModel(name='gateway', chunks=['a', 'b']),
        legacy_model=_StreamChatModel(name='legacy', chunks=[]),
    )

    stream = wrapped._stream([])
    _ = next(stream)
    stream.close()

    assert len(recorded) == 1
    assert recorded[0]['outcome'] == 'cancelled'
    assert recorded[0]['reason'] == 'consumer_abandoned_stream'


def test_gateway_serving_legacy_fallback_close_records_request_cancellation_only(monkeypatch):
    recorded: list[dict[str, Any]] = []
    fallbacks: list[dict[str, Any]] = []
    monkeypatch.setattr(gateway_serving, 'record_gateway_request_result', lambda **kwargs: recorded.append(kwargs))
    monkeypatch.setattr(gateway_serving, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))
    wrapped = gateway_serving.wrap_gateway_with_legacy_fallback(
        feature='chat_responses',
        gateway_model=_StreamChatModel(name='gateway', chunks=[], fail_before_yield=True),
        legacy_model=_StreamChatModel(name='legacy', chunks=['a', 'b']),
    )

    stream = wrapped._stream([])
    _ = next(stream)
    stream.close()

    assert fallbacks == []
    assert len(recorded) == 1
    assert recorded[0]['outcome'] == 'cancelled'
    assert recorded[0]['reason'] == 'consumer_abandoned_stream'


@pytest.mark.asyncio
async def test_gateway_serving_astream_aclose_records_cancelled_exactly_once(monkeypatch):
    recorded: list[dict[str, Any]] = []
    monkeypatch.setattr(gateway_serving, 'record_gateway_request_result', lambda **kwargs: recorded.append(kwargs))
    wrapped = gateway_serving.wrap_gateway_with_legacy_fallback(
        feature='persona_chat',
        gateway_model=_StreamChatModel(name='gateway', chunks=['a', 'b']),
        legacy_model=_StreamChatModel(name='legacy', chunks=[]),
    )

    stream = wrapped._astream([])
    _ = await anext(stream)
    await stream.aclose()

    assert len(recorded) == 1
    assert recorded[0]['outcome'] == 'cancelled'


@pytest.mark.asyncio
async def test_gateway_serving_async_legacy_fallback_aclose_records_request_cancellation_only(monkeypatch):
    recorded: list[dict[str, Any]] = []
    fallbacks: list[dict[str, Any]] = []
    monkeypatch.setattr(gateway_serving, 'record_gateway_request_result', lambda **kwargs: recorded.append(kwargs))
    monkeypatch.setattr(gateway_serving, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))
    wrapped = gateway_serving.wrap_gateway_with_legacy_fallback(
        feature='persona_chat',
        gateway_model=_StreamChatModel(name='gateway', chunks=[], fail_before_yield=True),
        legacy_model=_StreamChatModel(name='legacy', chunks=['a', 'b']),
    )

    stream = wrapped._astream([])
    _ = await anext(stream)
    await stream.aclose()

    assert fallbacks == []
    assert len(recorded) == 1
    assert recorded[0]['outcome'] == 'cancelled'
    assert recorded[0]['reason'] == 'consumer_abandoned_stream'


@pytest.mark.asyncio
async def test_gateway_serving_astream_records_serving_mode(monkeypatch):
    recorded: list[dict[str, Any]] = []
    monkeypatch.setattr(
        gateway_serving,
        'record_gateway_request_result',
        lambda **kwargs: recorded.append(kwargs),
    )

    gateway = _StreamChatModel(name='gateway', chunks=['tok'])
    legacy = _StreamChatModel(name='legacy', chunks=[])
    wrapped = gateway_serving.wrap_gateway_with_legacy_fallback(
        feature='persona_chat',
        gateway_model=gateway,
        legacy_model=legacy,
    )

    chunks = [chunk async for chunk in wrapped._astream([])]

    assert len(chunks) == 1
    assert recorded[0]['mode'] == 'serving'


def test_gateway_serving_preserves_canonical_request_id(monkeypatch):
    recorded: list[dict[str, Any]] = []
    request_id = '245a4344-4cd3-4939-ac62-e3b7a89e0fe8'
    monkeypatch.setattr(gateway_serving, 'record_gateway_request_result', lambda **kwargs: recorded.append(kwargs))
    gateway = _StreamChatModel(name='gateway', chunks=[])
    wrapped = gateway_serving.wrap_gateway_with_legacy_fallback(
        feature='chat_responses',
        gateway_model=gateway,
        legacy_model=_StreamChatModel(name='legacy', chunks=[]),
    )

    wrapped._generate([], extra_headers={'x-omi-request-id': request_id, 'x-client-header': 'kept'})

    assert recorded[0]['request_id'] == request_id
    assert gateway.calls[0]['extra_headers'] == {
        'X-Omi-Request-ID': request_id,
        'x-client-header': 'kept',
    }
