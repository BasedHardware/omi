from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from utils.llm import gateway_anthropic
from utils.llm.gateway_client import CHAT_AGENT_AUTO_LANE_ID, LLM_GATEWAY_FEATURE_MODE_ENV_VAR


@pytest.mark.asyncio
async def test_gateway_anthropic_stream_uses_auto_lane_on_success(monkeypatch):
    recorded: list[dict] = []
    gateway_stream = AsyncMock()
    gateway_stream.__aenter__ = AsyncMock(return_value=gateway_stream)
    gateway_stream.__aexit__ = AsyncMock(return_value=None)
    gateway_stream.__aiter__ = MagicMock(return_value=iter([]))
    gateway_stream.get_final_message = AsyncMock(return_value=MagicMock())

    gateway_messages = MagicMock()
    gateway_messages.stream.return_value = gateway_stream
    gateway_client = MagicMock(messages=gateway_messages)

    legacy_messages = MagicMock()
    legacy_client = MagicMock(messages=legacy_messages)

    monkeypatch.setenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, 'gateway')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setattr(gateway_anthropic, '_get_or_create_gateway_anthropic_client', lambda **kwargs: gateway_client)
    monkeypatch.setattr(
        gateway_anthropic,
        'record_gateway_request_result',
        lambda **kwargs: recorded.append(kwargs),
    )

    client = gateway_anthropic.get_gateway_first_anthropic_client(
        legacy_client=legacy_client,
        agent_model='claude-sonnet-4-6',
    )

    async with client.messages.stream(model='claude-sonnet-4-6', max_tokens=10):
        pass

    gateway_messages.stream.assert_called_once()
    assert gateway_messages.stream.call_args.kwargs['model'] == CHAT_AGENT_AUTO_LANE_ID
    legacy_messages.stream.assert_not_called()
    assert recorded[0]['mode'] == 'serving'
    assert recorded[0]['feature'] == 'chat_agent'


@pytest.mark.asyncio
async def test_gateway_anthropic_stream_falls_back_on_transport_failure(monkeypatch):
    recorded: list[dict] = []
    legacy_stream = AsyncMock()
    legacy_stream.__aenter__ = AsyncMock(return_value=legacy_stream)
    legacy_stream.__aexit__ = AsyncMock(return_value=None)
    legacy_stream.__aiter__ = MagicMock(return_value=iter([]))

    gateway_messages = MagicMock()
    gateway_messages.stream.side_effect = httpx.ConnectError('connection refused')

    legacy_messages = MagicMock()
    legacy_messages.stream.return_value = legacy_stream
    gateway_client = MagicMock(messages=gateway_messages)
    legacy_client = MagicMock(messages=legacy_messages)

    monkeypatch.setenv(LLM_GATEWAY_FEATURE_MODE_ENV_VAR, 'gateway')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setattr(gateway_anthropic, '_get_or_create_gateway_anthropic_client', lambda **kwargs: gateway_client)
    monkeypatch.setattr(
        gateway_anthropic,
        'record_gateway_request_result',
        lambda **kwargs: recorded.append(kwargs),
    )

    client = gateway_anthropic.get_gateway_first_anthropic_client(
        legacy_client=legacy_client,
        agent_model='claude-sonnet-4-6',
    )

    async with client.messages.stream(model='claude-sonnet-4-6', max_tokens=10):
        pass

    legacy_messages.stream.assert_called_once()
    assert legacy_messages.stream.call_args.kwargs['model'] == 'claude-sonnet-4-6'
    assert recorded[0]['mode'] == 'fallback'
