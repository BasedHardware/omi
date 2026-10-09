"""Dispatch contract: company-paid Gemini is dedicated-only; overflow is Luna."""

import json
from unittest.mock import AsyncMock

import httpx
import pytest
import yaml

from config.vertex_reservations import State
from llm_gateway.gateway.accounting import AttemptTrace
from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.config_loader import DEFAULT_CONFIG_DIR, ConfigValidationError, load_gateway_config
from llm_gateway.gateway.credentials import build_omi_managed_credential_context
from llm_gateway.gateway.errors import GatewayProviderFailureError
from llm_gateway.gateway.executor import (
    ProviderRegistry,
    _gemini_thinking_effort_for_luna,
    execute_chat_completion,
)
from llm_gateway.gateway.metrics import LUNA_UNSUPPORTED_PARAMS_DROPPED_TOTAL
from utils.llm import desktop_gemini_gateway as dgg
from llm_gateway.gateway.providers import OpenAICompatibleChatCompletionProvider, VertexGeminiProvider
from llm_gateway.gateway.resolver import resolve_chat_completion_route
from llm_gateway.routers.openai_compatible import _prepared_streaming_iterator
from utils.llm import vertex_pt_routing as ptr


def success():
    return {
        'object': 'chat.completion',
        'id': 'synthetic',
        'model': 'gpt-6-luna',
        'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'ok'}, 'finish_reason': 'stop'}],
        'usage': {'prompt_tokens': 2, 'completion_tokens': 1, 'total_tokens': 3},
    }


@pytest.mark.parametrize('anchor', list(ptr.DESKTOP_TEXT_LANES))
@pytest.mark.parametrize('state', [State.INACTIVE, State.UNKNOWN, State.ACTIVE])
@pytest.mark.parametrize('streaming', [False, True])
@pytest.mark.asyncio
async def test_paid_dispatch_never_reaches_shared_gemini(monkeypatch, anchor, state, streaming):
    monkeypatch.delenv('OMI_VERTEX_PT_MODEL', raising=False)
    monkeypatch.delenv('OMI_VERTEX_RESERVATION_STATES', raising=False)
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.host == 'us-central1-aiplatform.googleapis.com':
            assert request.headers[ptr.REQUEST_TYPE_HEADER] == 'dedicated'
            assert ptr.PT_MODEL_CURRENT + ':' in request.url.path
            return httpx.Response(429, json={'error': {'message': 'Provisioned throughput exhausted'}})
        assert request.url.path == '/v1/chat/completions'
        body = json.loads(request.content)
        assert body['model'] == 'gpt-6-luna'
        assert not {'google', 'reserved_capacity_only', 'pt_overflow_origin', 'top_p', 'stop'} & body.keys()
        if streaming:
            return httpx.Response(
                200,
                content=b'data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n',
                headers={'content-type': 'text/event-stream'},
            )
        return httpx.Response(200, json=success())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        vertex = VertexGeminiProvider(http_client=client, access_token_supplier=AsyncMock(return_value='synthetic'))
        monkeypatch.setattr(vertex._reservations, 'refresh', AsyncMock(return_value={ptr.PT_MODEL_CURRENT: state}))
        registry = ProviderRegistry(
            {'gemini': vertex, 'openai': OpenAICompatibleChatCompletionProvider(http_client=client)}
        )
        request = {'model': ptr.desktop_text_lane_id(anchor), 'messages': [{'role': 'user', 'content': 'synthetic'}]}
        resolved = resolve_chat_completion_route(load_gateway_config(), request)
        credentials = build_omi_managed_credential_context(ServiceCaller(name='backend'))
        if streaming:
            prepared = await _prepared_streaming_iterator(
                resolved, credentials, registry, resolved.active_route, attempt_trace=AttemptTrace()
            )
            assert prepared.provider == 'openai' and prepared.model == 'gpt-6-luna'
            output = (prepared.first_chunk or b'') + b''.join([chunk async for chunk in prepared.stream])
            assert b'ok' in output
        else:
            result = await execute_chat_completion(resolved, credentials, registry)
            assert result.selected_provider == 'openai' and result.selected_model == 'gpt-6-luna'
            assert result.response['choices'][0]['message']['content'] == 'ok'
            assert result.provider_accounting.usage.total_tokens == 3
        assert len(seen) == (2 if state == State.ACTIVE else 1)


@pytest.mark.asyncio
async def test_generic_rate_limit_does_not_trigger_capacity_fallback(monkeypatch):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    monkeypatch.setenv('OMI_VERTEX_RESERVATION_STATES', '{"gemini-2.5-flash":"active","gemini-3.8-flash":"inactive"}')
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(429, json={'error': {'message': 'Ordinary project rate limit'}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        vertex = VertexGeminiProvider(http_client=client, access_token_supplier=AsyncMock(return_value='synthetic'))
        resolved = resolve_chat_completion_route(
            load_gateway_config(),
            {
                'model': ptr.desktop_text_lane_id(ptr.PT_MODEL_CURRENT),
                'messages': [{'role': 'user', 'content': 'synthetic'}],
            },
        )
        with pytest.raises(Exception) as error:
            await execute_chat_completion(
                resolved,
                build_omi_managed_credential_context(ServiceCaller(name='backend')),
                ProviderRegistry({'gemini': vertex}),
            )
        assert error.value.failure_class.value == 'provider_429_omi_paid'
        assert len(seen) == 1


@pytest.mark.parametrize('mutation', ['shared_primary', 'shared_fallback', 'openrouter_gemini', 'missing_luna'])
def test_config_load_rejects_paygo_gemini(tmp_path, mutation):
    for name in ['lanes.yaml', 'route_artifacts.yaml', 'feature_bundles.yaml', 'generated_route_overrides.yaml']:
        (tmp_path / name).write_bytes((DEFAULT_CONFIG_DIR / name).read_bytes())
    path = tmp_path / 'route_artifacts.yaml'
    contents = yaml.safe_load(path.read_text())
    route = contents['route_artifacts'][0]
    route.pop('artifact_digest', None)
    if mutation == 'shared_primary':
        route['primary'] = {'provider': 'gemini', 'model': ptr.PT_MODEL_CURRENT}
    elif mutation == 'shared_fallback':
        route['fallbacks'] = [{'provider': 'gemini', 'model': 'gemini-2.5-flash-lite'}]
    elif mutation == 'openrouter_gemini':
        route['primary'] = {'provider': 'openrouter', 'model': 'google/gemini-2.5-flash'}
    else:
        route['primary'] = {'provider': 'gemini', 'model': ptr.PT_MODEL_CURRENT}
        route['provider_options'] = {ptr.RESERVED_CAPACITY_OPTION: True}
        route['fallbacks'] = []
    path.write_text(yaml.safe_dump(contents))
    with pytest.raises(ConfigValidationError, match='company-paid Gemini|requires Luna'):
        load_gateway_config(tmp_path)


@pytest.mark.parametrize('anchor', list(ptr.DESKTOP_TEXT_LANES))
def test_all_desktop_aliases_follow_the_moved_order(anchor):
    assert (
        ptr.reserved_generation_model(anchor, {ptr.PT_MODEL_CURRENT: State.INACTIVE, ptr.PT_MODEL_TARGET: State.ACTIVE})
        == ptr.PT_MODEL_TARGET
    )
    assert ptr.reserved_generation_model(anchor, {}) is None
    assert (
        ptr.reserved_generation_model(anchor, {ptr.PT_MODEL_CURRENT: State.ACTIVE, ptr.PT_MODEL_TARGET: State.ACTIVE})
        is None
    )


@pytest.mark.asyncio
async def test_provider_dispatch_uses_moved_reservation_with_dedicated_header(monkeypatch):
    monkeypatch.delenv('OMI_VERTEX_PT_MODEL', raising=False)
    monkeypatch.delenv('OMI_VERTEX_RESERVATION_STATES', raising=False)
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    seen = []

    def handler(request):
        seen.append(request)
        assert request.headers[ptr.REQUEST_TYPE_HEADER] == 'dedicated'
        assert f'/models/{ptr.PT_MODEL_TARGET}:generateContent' in request.url.path
        return httpx.Response(200, json={'candidates': [{'content': {'parts': [{'text': 'ok'}]}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        vertex = VertexGeminiProvider(http_client=client, access_token_supplier=AsyncMock(return_value='synthetic'))
        monkeypatch.setattr(
            vertex._reservations,
            'refresh',
            AsyncMock(return_value={ptr.PT_MODEL_CURRENT: State.INACTIVE, ptr.PT_MODEL_TARGET: State.ACTIVE}),
        )
        resolved = resolve_chat_completion_route(
            load_gateway_config(),
            {
                'model': ptr.desktop_text_lane_id(ptr.PT_MODEL_CURRENT),
                'messages': [{'role': 'user', 'content': 'synthetic'}],
            },
        )
        result = await execute_chat_completion(
            resolved,
            build_omi_managed_credential_context(ServiceCaller(name='backend')),
            ProviderRegistry({'gemini': vertex}),
        )

    assert result.selected_provider == 'gemini'
    assert len(seen) == 1
    assert f'/models/{ptr.PT_MODEL_TARGET}:generateContent' in seen[0].url.path


@pytest.mark.parametrize(
    ('thinking', 'expected'),
    [
        ({}, 'none'),
        ({'thinking_budget': 0}, 'none'),
        ({'thinking_budget': 1}, 'low'),
        ({'thinking_budget': 1024}, 'low'),
        ({'thinking_budget': 1025}, 'medium'),
        ({'thinking_level': 'minimal'}, 'none'),
        ({'thinking_level': 'low'}, 'low'),
        ({'thinking_level': 'medium'}, 'medium'),
        ({'thinking_level': 'high'}, 'medium'),
    ],
)
def test_gemini_thinking_controls_map_to_luna_effort(thinking, expected):
    assert _gemini_thinking_effort_for_luna(thinking) == expected


@pytest.mark.asyncio
async def test_macos_task_extraction_payload_maps_budget_and_counts_dropped_controls(monkeypatch):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    monkeypatch.setenv('OMI_VERTEX_RESERVATION_STATES', '{"gemini-2.5-flash":"inactive"}')
    seen = []
    before_top_p = LUNA_UNSUPPORTED_PARAMS_DROPPED_TOTAL.labels(param='top_p')._value.get()
    before_stop = LUNA_UNSUPPORTED_PARAMS_DROPPED_TOTAL.labels(param='stop')._value.get()

    def handler(request):
        seen.append(request)
        assert request.url.path == '/v1/chat/completions'
        body = json.loads(request.content)
        assert body['model'] == 'gpt-6-luna'
        assert body['reasoning_effort'] == 'low'
        assert body['tools'][0]['function']['name'] == 'extract_task'
        assert not {'google', 'top_p', 'stop'} & body.keys()
        assert request.headers.get(ptr.REQUEST_TYPE_HEADER) is None
        return httpx.Response(200, json=success())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        vertex = VertexGeminiProvider(http_client=client, access_token_supplier=AsyncMock(return_value='synthetic'))
        monkeypatch.setattr(
            vertex._reservations, 'refresh', AsyncMock(return_value={ptr.PT_MODEL_CURRENT: State.INACTIVE})
        )
        payload = {
            'contents': [
                {
                    'role': 'user',
                    'parts': [
                        {'text': 'Extract tasks visible on this screen.'},
                        {'inlineData': {'mimeType': 'image/jpeg', 'data': 'AA=='}},
                    ],
                },
            ],
            'generationConfig': {
                'thinkingConfig': {'thinkingBudget': 1024},
                'topP': 0.4,
                'stopSequences': ['STOP'],
            },
            'tools': [
                {
                    'functionDeclarations': [
                        {
                            'name': 'extract_task',
                            'description': 'Stage a task suggestion from the screen.',
                            'parameters': {
                                'type': 'object',
                                'properties': {'title': {'type': 'string'}},
                                'required': ['title'],
                            },
                        }
                    ]
                }
            ],
            'toolConfig': {'functionCallingConfig': {'mode': 'ANY'}},
        }
        request = dgg.gemini_body_to_openai_chat(
            payload,
            lane_id=ptr.desktop_text_lane_id(ptr.PT_MODEL_CURRENT),
            stream=False,
        )
        resolved = resolve_chat_completion_route(load_gateway_config(), request)
        result = await execute_chat_completion(
            resolved,
            build_omi_managed_credential_context(ServiceCaller(name='backend')),
            ProviderRegistry({'gemini': vertex, 'openai': OpenAICompatibleChatCompletionProvider(http_client=client)}),
        )

    assert result.selected_provider == 'openai' and result.selected_model == 'gpt-6-luna'
    assert len(seen) == 1
    assert LUNA_UNSUPPORTED_PARAMS_DROPPED_TOTAL.labels(param='top_p')._value.get() == before_top_p + 1
    assert LUNA_UNSUPPORTED_PARAMS_DROPPED_TOTAL.labels(param='stop')._value.get() == before_stop + 1


@pytest.mark.parametrize(
    'lane,streaming',
    [
        ('omi:auto:dream-reasoning', False),
        (ptr.desktop_text_lane_id(ptr.PT_MODEL_CURRENT), False),
        (ptr.desktop_text_lane_id(ptr.PT_MODEL_CURRENT), True),
    ],
)
@pytest.mark.asyncio
async def test_reserved_invalid_request_recovers_through_luna(monkeypatch, lane, streaming):
    from llm_gateway.gateway.schemas import FailureClass
    from llm_gateway.routers.openai_compatible import _stream_with_terminal_metrics
    from models.dream_agent import Plan
    import llm_gateway.gateway.reserved_fallback as telemetry

    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    seen, events = [], []
    monkeypatch.setattr(telemetry, 'record_fallback', lambda **event: events.append(event))
    original_schema = Plan.model_json_schema()

    def handler(request):
        seen.append(request)
        body = json.loads(request.content)
        if request.url.host == 'us-central1-aiplatform.googleapis.com':
            assert request.headers[ptr.REQUEST_TYPE_HEADER] == 'dedicated'
            assert 'responseJsonSchema' in body['generationConfig']
            return httpx.Response(400, json={'error': {'message': 'Response schema too complex synthetic'}})
        assert body['model'] == 'gpt-6-luna'
        assert body['response_format']['json_schema']['schema'] == original_schema
        assert 'reserved_capacity_only' not in body
        if streaming:
            return httpx.Response(200, content=b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n')
        return httpx.Response(200, json=success())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        vertex = VertexGeminiProvider(http_client=client, access_token_supplier=AsyncMock(return_value='synthetic'))
        monkeypatch.setattr(
            vertex._reservations, 'refresh', AsyncMock(return_value={ptr.PT_MODEL_CURRENT: State.ACTIVE})
        )
        registry = ProviderRegistry(
            {'gemini': vertex, 'openai': OpenAICompatibleChatCompletionProvider(http_client=client)}
        )
        request = {
            'model': lane,
            'messages': [{'role': 'user', 'content': 'synthetic'}],
            'stream': streaming,
            'response_format': {'type': 'json_schema', 'json_schema': {'name': 'Plan', 'schema': original_schema}},
        }
        resolved = resolve_chat_completion_route(load_gateway_config(), request)
        credentials = build_omi_managed_credential_context(ServiceCaller(name='backend'))
        trace = AttemptTrace()
        if streaming:
            import time

            prepared = await _prepared_streaming_iterator(
                resolved, credentials, registry, resolved.active_route, attempt_trace=trace
            )
            assert prepared.fallback_reason == 'provider_invalid_request'
            output = b''.join(
                [
                    chunk
                    async for chunk in _stream_with_terminal_metrics(
                        prepared,
                        resolved_route=resolved,
                        credentials=credentials,
                        route=resolved.active_route,
                        started_at=time.monotonic(),
                        request_id='synthetic',
                        attempt_trace=trace,
                    )
                ]
            )
            assert b'ok' in output and b'[DONE]' in output
        else:
            result = await execute_chat_completion(resolved, credentials, registry, attempt_trace=trace)
            assert result.fallback_used and result.fallback_reason == FailureClass.PROVIDER_INVALID_REQUEST
            assert result.selected_model == 'gpt-6-luna'
        assert len(seen) == 2
        assert events == [
            dict(component='llm_gateway', from_mode='gemini', to_mode='openai', reason='other', outcome='recovered')
        ]
        assert trace.attempts[0].error_class == 'provider_invalid_request'
        assert trace.attempts[-1].fallback_reason == 'provider_invalid_request'


@pytest.mark.parametrize(
    'mutation', ['byok', 'shared', 'wrong_fallback', 'luna_primary', 'luna_failure', 'credential_denied']
)
def test_invalid_request_exception_is_only_reserved_paid_primary_to_luna(mutation):
    from llm_gateway.gateway.reserved_fallback import can_try_next_provider
    from llm_gateway.gateway.resolver import is_lkg_eligible
    from llm_gateway.gateway.schemas import CredentialMode, FailureClass, ProviderRef

    config = load_gateway_config()
    route = config.route_artifacts[config.lanes['omi:auto:dream-reasoning'].active_route]
    failed = route.primary
    assert can_try_next_provider(route, failed, FailureClass.PROVIDER_INVALID_REQUEST)
    assert not is_lkg_eligible(route, FailureClass.PROVIDER_INVALID_REQUEST)
    if mutation == 'byok':
        route = route.model_copy(
            update={'credential_policy': route.credential_policy.model_copy(update={'mode': CredentialMode.BYOK})}
        )
    elif mutation == 'shared':
        route = route.model_copy(update={'provider_options': {}})
    elif mutation == 'wrong_fallback':
        route = route.model_copy(update={'fallbacks': [ProviderRef(provider='openai', model='wrong')]})
    elif mutation == 'luna_primary':
        route = route.model_copy(update={'primary': route.fallbacks[0]})
        failed = route.primary
    elif mutation == 'luna_failure':
        failed = route.fallbacks[0]
    else:
        route = route.model_copy(
            update={
                'credential_policy': route.credential_policy.model_copy(
                    update={'fallback_eligible_failure_classes': []}
                )
            }
        )
    assert not can_try_next_provider(route, failed, FailureClass.PROVIDER_INVALID_REQUEST)


@pytest.mark.asyncio
async def test_reserved_schema_translation_runs_through_local_http_endpoint(monkeypatch):
    from llm_gateway.main import app
    from llm_gateway.routers import dependencies
    from models.dream_agent import Plan

    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'synthetic-token')
    seen = []

    def handler(request):
        seen.append(request)
        assert request.headers[ptr.REQUEST_TYPE_HEADER] == 'dedicated'
        schema = json.loads(request.content)['generationConfig']['responseJsonSchema']
        assert schema['properties']['questions']['items'] == {'$ref': '#/$defs/ReviewItem'}
        assert '$defs' in schema
        return httpx.Response(
            200, json={'candidates': [{'content': {'parts': [{'text': '{}'}]}, 'finishReason': 'STOP'}]}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as upstream:
        vertex = VertexGeminiProvider(http_client=upstream, access_token_supplier=AsyncMock(return_value='synthetic'))
        monkeypatch.setattr(
            vertex._reservations, 'refresh', AsyncMock(return_value={ptr.PT_MODEL_CURRENT: State.ACTIVE})
        )
        app.dependency_overrides[dependencies.get_provider_registry] = lambda: ProviderRegistry({'gemini': vertex})
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://synthetic') as local:
                response = await local.post(
                    '/v1/chat/completions',
                    headers={'Authorization': 'Bearer synthetic-token', 'x-omi-service-caller': 'backend'},
                    json={
                        'model': 'omi:auto:dream-reasoning',
                        'messages': [{'role': 'user', 'content': 'synthetic'}],
                        'response_format': {
                            'type': 'json_schema',
                            'json_schema': {'name': 'Plan', 'schema': Plan.model_json_schema()},
                        },
                    },
                )
        finally:
            app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()['model'] == 'omi:auto:dream-reasoning'
    assert Plan.model_validate_json(response.json()['choices'][0]['message']['content']) == Plan()
    assert len(seen) == 1


@pytest.mark.parametrize('streaming', [False, True])
@pytest.mark.asyncio
async def test_luna_rejection_exhausts_reserved_fallback_once(monkeypatch, streaming):
    import llm_gateway.gateway.reserved_fallback as telemetry
    from llm_gateway.gateway.errors import GatewayProviderRequestRejectedError

    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    seen, events = [], []
    monkeypatch.setattr(telemetry, 'record_fallback', lambda **event: events.append(event))

    def handler(request):
        seen.append(request)
        return httpx.Response(400, json={'error': {'message': 'Invalid response schema synthetic'}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        vertex = VertexGeminiProvider(http_client=client, access_token_supplier=AsyncMock(return_value='synthetic'))
        monkeypatch.setattr(
            vertex._reservations, 'refresh', AsyncMock(return_value={ptr.PT_MODEL_CURRENT: State.ACTIVE})
        )
        registry = ProviderRegistry(
            {'gemini': vertex, 'openai': OpenAICompatibleChatCompletionProvider(http_client=client)}
        )
        resolved = resolve_chat_completion_route(
            load_gateway_config(),
            {
                'model': ptr.desktop_text_lane_id(ptr.PT_MODEL_CURRENT),
                'stream': streaming,
                'messages': [{'role': 'user', 'content': 'synthetic'}],
            },
        )
        credentials = build_omi_managed_credential_context(ServiceCaller(name='backend'))
        with pytest.raises(GatewayProviderRequestRejectedError):
            if streaming:
                await _prepared_streaming_iterator(
                    resolved, credentials, registry, resolved.active_route, attempt_trace=AttemptTrace()
                )
            else:
                await execute_chat_completion(resolved, credentials, registry)
        assert len(seen) == 2
        assert events[0]['outcome'] == 'exhausted' and len(events) == 1


@pytest.mark.asyncio
async def test_invalid_request_after_first_stream_chunk_never_calls_luna(monkeypatch):
    from llm_gateway.gateway.providers import FakeChatCompletionProvider, ProviderFailure
    from llm_gateway.gateway.schemas import FailureClass
    from llm_gateway.routers.openai_compatible import _stream_with_terminal_metrics
    import time

    async def stream(*args, **kwargs):
        yield b'data: {"choices":[{"delta":{"content":"synthetic"}}]}\n\n'
        raise ProviderFailure(FailureClass.PROVIDER_INVALID_REQUEST)

    vertex = VertexGeminiProvider()
    monkeypatch.setattr(vertex, 'stream_chat_completion', stream)
    luna = FakeChatCompletionProvider()
    resolved = resolve_chat_completion_route(
        load_gateway_config(),
        {
            'model': ptr.desktop_text_lane_id(ptr.PT_MODEL_CURRENT),
            'stream': True,
            'messages': [{'role': 'user', 'content': 'synthetic'}],
        },
    )
    credentials = build_omi_managed_credential_context(ServiceCaller(name='backend'))
    registry = ProviderRegistry({'gemini': vertex, 'openai': luna})
    try:
        prepared = await _prepared_streaming_iterator(
            resolved, credentials, registry, resolved.active_route, attempt_trace=AttemptTrace()
        )
        output = _stream_with_terminal_metrics(
            prepared,
            resolved_route=resolved,
            credentials=credentials,
            route=resolved.active_route,
            started_at=time.monotonic(),
            request_id='synthetic',
        )
        assert b'synthetic' in await anext(output)
        with pytest.raises(ProviderFailure) as failure:
            await anext(output)
        assert failure.value.failure_class == FailureClass.PROVIDER_INVALID_REQUEST
        assert not luna.calls
    finally:
        await vertex.aclose()
