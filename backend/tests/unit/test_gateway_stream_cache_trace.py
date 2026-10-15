"""Streaming traces preserve cache-operation receipts before and after output."""

import json

import pytest

from llm_gateway.gateway.accounting import AttemptTrace, ProviderResponseMetadata
from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.config_loader import load_gateway_config
from llm_gateway.gateway.credentials import build_omi_managed_credential_context
from llm_gateway.gateway.errors import GatewayError
from llm_gateway.gateway.executor import ProviderRegistry, selected_serving_route
from llm_gateway.gateway.provider_types import ProviderFailure
from llm_gateway.gateway.resolver import resolve_chat_completion_route
from llm_gateway.gateway.schemas import FailureClass
from llm_gateway.routers import openai_compatible as router


def route_and_credentials():
    resolved = resolve_chat_completion_route(
        load_gateway_config(),
        {
            'model': 'omi:auto:chat-agent',
            'messages': [
                {'role': 'system', 'content': 'synthetic stable ' * 500},
                {'role': 'user', 'content': 'invented request'},
            ],
            'stream': True,
        },
    )
    return (
        resolved,
        selected_serving_route(resolved),
        build_omi_managed_credential_context(ServiceCaller(name='backend', user_uid='synthetic-owner')),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize('metadata_present', [False, True])
async def test_pre_output_error_preserves_lane_policy_and_operation_metadata(metadata_present):
    resolved, route, credentials = route_and_credentials()
    metadata = (
        ProviderResponseMetadata(
            cache_mode='explicit',
            cacheable_prefix_tokens=5000,
            cache_write_tokens=5100,
            cache_storage_token_seconds=9180000,
        )
        if metadata_present
        else None
    )

    class FailingProvider:
        async def stream_chat_completion(self, *args, **kwargs):
            raise ProviderFailure(FailureClass.INVALID_CONFIG, accounting=metadata)
            yield b''

    trace = AttemptTrace()
    with pytest.raises(GatewayError):
        await router._prepared_streaming_iterator(
            resolved,
            credentials,
            ProviderRegistry({route.primary.provider: FailingProvider()}),
            route,
            attempt_trace=trace,
        )
    assert len(trace.attempts) == 1
    attempt = trace.attempts[0]
    assert attempt.lane_id == route.lane_id
    assert attempt.cache_mode == 'explicit' and attempt.cacheable_prefix_tokens >= 1024
    assert attempt.usage is None
    assert attempt.cache_write_tokens == (5100 if metadata_present else 0)
    assert attempt.cache_storage_token_seconds == (9180000 if metadata_present else 0)


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', ['success', 'error', 'eof'])
async def test_terminal_stream_trace_retains_lane_and_cache_receipt(outcome):
    resolved, route, credentials = route_and_credentials()
    receipt = {
        'lane': 'unknown',
        'mode': 'explicit',
        'prefix_tokens': 5000,
        'write_tokens': 5100,
        'storage_token_seconds': 9180000,
    }
    initial = f'data: {json.dumps({"choices": [{"delta": {"content": "invented"}}], "_gateway_cache_receipt": receipt})}\n\n'.encode()

    async def remaining():
        if outcome == 'error':
            raise ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID)
        if outcome == 'success':
            yield b'data: {"choices":[],"usage":{"prompt_tokens":5100,"completion_tokens":3,"prompt_tokens_details":{"cached_tokens":5000}}}\n\n'
            yield b'data: [DONE]\n\n'

    trace = AttemptTrace()
    prepared = router._PreparedStream(
        first_chunk=initial,
        stream=remaining(),
        provider=route.primary.provider,
        model=route.primary.model,
        fallback_used=False,
        fallback_reason=None,
    )
    stream = router._stream_with_terminal_metrics(
        prepared,
        resolved_route=resolved,
        credentials=credentials,
        route=route,
        started_at=router.time_request(),
        request_id='synthetic-request',
        attempt_trace=trace,
    )
    if outcome == 'error':
        with pytest.raises(ProviderFailure):
            _ = [chunk async for chunk in stream]
    else:
        _ = [chunk async for chunk in stream]
    assert len(trace.attempts) == 1
    attempt = trace.attempts[0]
    assert attempt.lane_id == route.lane_id
    # A final usage event without receipt metadata must not erase initial charges.
    assert attempt.cache_write_tokens == 5100
    assert attempt.cache_storage_token_seconds == 9180000
    assert attempt.outcome == ('success' if outcome == 'success' else 'error')
