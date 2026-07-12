from __future__ import annotations

from typing import Any, AsyncIterator, Iterator

import httpx
import pytest
from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from utils.llm import gateway_serving
from utils.llm.gateway_client import feature_auto_lane_id


class _StreamChatModel(BaseChatModel):
    name: str
    chunks: list[str]
    fail_before_yield: bool = False

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
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content='sync'))])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[Any]:
        if self.fail_before_yield:
            raise httpx.ConnectError('connection refused')
        for chunk in self.chunks:
            yield ChatGeneration(message=AIMessage(content=chunk))

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> AsyncIterator[Any]:
        if self.fail_before_yield:
            raise httpx.ConnectError('connection refused')
        for chunk in self.chunks:
            yield ChatGeneration(message=AIMessage(content=chunk))


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
    assert recorded == [
        {
            'feature': 'chat_responses',
            'outcome': 'success',
            'reason': 'ok',
            'route': feature_auto_lane_id('chat_responses'),
            'mode': 'serving',
        }
    ]


def test_gateway_serving_stream_falls_back_before_first_chunk(monkeypatch):
    recorded: list[dict[str, Any]] = []
    monkeypatch.setattr(
        gateway_serving,
        'record_gateway_request_result',
        lambda **kwargs: recorded.append(kwargs),
    )

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
