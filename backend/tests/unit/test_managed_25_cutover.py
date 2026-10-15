"""Automatic evidence-driven 2.5 retirement with one-row destination selection."""

import json
from dataclasses import replace
from unittest.mock import AsyncMock

import httpx
import pytest

from config import vertex_reservations as vr
from llm_gateway.gateway.accounting import AttemptTrace
from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.config_loader import load_gateway_config
from llm_gateway.gateway.credentials import build_omi_managed_credential_context
from llm_gateway.gateway.executor import ProviderRegistry, execute_chat_completion
from llm_gateway.gateway.providers import OpenAICompatibleChatCompletionProvider, VertexGeminiProvider
from llm_gateway.gateway.resolver import resolve_chat_completion_route
from llm_gateway.routers.openai_compatible import _prepared_streaming_iterator
from utils.llm import vertex_pt_routing as ptr
from utils.llm.vertex_policy_metrics import MANAGED_25_ATTEMPTS, POLICY_DECISIONS

OLD, NEW = 'gemini-2.5-flash', 'gemini-3.8-flash'


def observed_move():
    evidence = {OLD: vr.observe(vr.Evidence(), now=500, outcome='dedicated_success')}
    for now in (1000, 1600, 2200, 2800):
        evidence[OLD] = vr.observe(evidence[OLD], now=now, outcome='capacity_error')
    # A saturated order cannot prove inactivity; positive service on the same
    # exclusive order's other model completes the evidence sequence.
    assert vr.observed_state(OLD, evidence, now=2801)[0] == vr.State.ACTIVE
    evidence[NEW] = vr.observe(vr.Evidence(), now=2799, outcome='dedicated_success')
    states = {m: vr.observed_state(m, evidence, now=2801)[0] for m in (OLD, NEW)}
    assert states == {OLD: vr.State.INACTIVE, NEW: vr.State.ACTIVE}
    return states


CASES = (
    [('macos', tag, f'macos_{suffix}') for tag, suffix in vr.PRODUCT_POLICY_TAGS.items()]
    + [('windows', tag, f'windows_{suffix}') for tag, suffix in vr.PRODUCT_POLICY_TAGS.items()]
    + [
        ('', 'unknown', 'desktop_other'),
        ('windows', 'unrecognized', 'desktop_other'),
        ('', 'proactive_notification', 'proactive_nudges'),
        ('', '__backend__', 'backend_other'),
    ]
)


def completion(model):
    return {
        'id': 'synthetic-response',
        'object': 'chat.completion',
        'model': model,
        'choices': [
            {'index': 0, 'message': {'role': 'assistant', 'content': 'invented answer'}, 'finish_reason': 'stop'}
        ],
        'usage': {'prompt_tokens': 10, 'completion_tokens': 2, 'total_tokens': 12},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize('platform,tag,row', CASES)
@pytest.mark.parametrize('stream', [False, True])
@pytest.mark.parametrize('anchor', list(ptr.DESKTOP_TEXT_LANES))
async def test_one_destination_row_controls_real_provider_dispatch(monkeypatch, platform, tag, row, stream, anchor):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    monkeypatch.setenv(ptr.PT_TARGET_LOCATION_ENV, 'us')
    monkeypatch.setenv(ptr.PT_MODEL_OVERRIDE_ENV, OLD)  # Must not reverse a real order move.
    monkeypatch.delenv(vr.STATE_OVERRIDE_ENV, raising=False)
    seen = []

    def handler(request):
        seen.append(request)
        assert request.url.path == '/v1/chat/completions'
        assert json.loads(request.content)['model'] == 'gpt-6-luna'
        return (
            httpx.Response(
                200,
                content=b'data: {"choices":[{"delta":{"content":"invented answer"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n',
            )
            if stream
            else httpx.Response(200, json=completion('gpt-6-luna'))
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        vertex = VertexGeminiProvider(
            http_client=client, access_token_supplier=AsyncMock(return_value='synthetic-token')
        )
        monkeypatch.setattr(vertex._reservations, 'refresh', AsyncMock(return_value=observed_move()))
        monkeypatch.setattr(vertex._reservations, 'record', AsyncMock())
        registry = ProviderRegistry(
            {'gemini': vertex, 'openai': OpenAICompatibleChatCompletionProvider(http_client=client)}
        )
        resolved = resolve_chat_completion_route(
            load_gateway_config(),
            {'model': ptr.DESKTOP_TEXT_LANES[anchor], 'messages': [{'role': 'user', 'content': 'invented request'}]},
        )
        if row == 'backend_other':
            backend_route = resolved.active_route.model_copy(update={'lane_id': 'omi:auto:synthetic-backend'})
            resolved = replace(
                resolved,
                lane=resolved.lane.model_copy(update={'lane_id': 'omi:auto:synthetic-backend'}),
                active_route=backend_route,
                last_known_good_route=backend_route,
            )
        # Older gateway callers may lack a product tag; unknown defaults to desktop_other.
        caller = ServiceCaller(
            name='backend',
            user_uid='synthetic-owner',
            client_platform=platform or None,
            product_lane=tag if tag in vr.PRODUCT_POLICY_TAGS else None,
            usage_feature=tag if tag == 'proactive_notification' else None,
        )
        credentials = build_omi_managed_credential_context(caller)
        before = POLICY_DECISIONS.labels(lane=row, action='luna')._value.get()
        if stream:
            prepared = await _prepared_streaming_iterator(
                resolved, credentials, registry, resolved.active_route, attempt_trace=AttemptTrace()
            )
            output = (prepared.first_chunk or b'') + b''.join([chunk async for chunk in prepared.stream])
            assert b'invented answer' in output
        else:
            result = await execute_chat_completion(resolved, credentials, registry, attempt_trace=AttemptTrace())
            assert result.selected_provider == 'openai'
        assert POLICY_DECISIONS.labels(lane=row, action='luna')._value.get() == before + 1
        assert len(seen) == 1
        assert not any(OLD in str(req.url) for req in seen)


@pytest.mark.asyncio
@pytest.mark.parametrize('state', [vr.State.UNKNOWN, vr.State.INACTIVE])
async def test_unknown_stays_dedicated_and_inactive_without_active_target_uses_luna(monkeypatch, state):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    monkeypatch.delenv(ptr.PT_MODEL_OVERRIDE_ENV, raising=False)
    seen = []

    def handler(request):
        seen.append(request)
        if state == vr.State.UNKNOWN:
            assert f'/models/{OLD}:generateContent' in request.url.path
            assert request.headers[ptr.REQUEST_TYPE_HEADER] == 'dedicated'
            return httpx.Response(
                200,
                json={'candidates': [{'content': {'parts': [{'text': 'invented answer'}]}, 'finishReason': 'STOP'}]},
            )
        assert request.url.path == '/v1/chat/completions'
        return httpx.Response(200, json=completion('gpt-6-luna'))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        vertex = VertexGeminiProvider(
            http_client=client, access_token_supplier=AsyncMock(return_value='synthetic-token')
        )
        monkeypatch.setattr(vertex._reservations, 'refresh', AsyncMock(return_value={OLD: state}))
        monkeypatch.setattr(vertex._reservations, 'record', AsyncMock())
        resolved = resolve_chat_completion_route(
            load_gateway_config(),
            {'model': ptr.DESKTOP_TEXT_LANES[OLD], 'messages': [{'role': 'user', 'content': 'invented'}]},
        )
        before = MANAGED_25_ATTEMPTS.labels(lane='desktop_other', traffic_type='dedicated')._value.get()
        await execute_chat_completion(
            resolved,
            build_omi_managed_credential_context(ServiceCaller(name='backend')),
            ProviderRegistry({'gemini': vertex, 'openai': OpenAICompatibleChatCompletionProvider(http_client=client)}),
        )
        assert len(seen) == 1
        assert MANAGED_25_ATTEMPTS.labels(lane='desktop_other', traffic_type='dedicated')._value.get() == before + (
            state == vr.State.UNKNOWN
        )


@pytest.mark.parametrize('lane', list(vr.INACTIVE_DESTINATIONS) + ['invented_unknown'])
def test_no_managed_inactive_policy_can_emit_25_shared(lane):
    assert vr.policy(OLD, vr.State.INACTIVE, lane=lane).kind in {'refuse', 'luna'}
    assert ptr.request_type_for(model=OLD, pt_model=NEW) == 'dedicated'
    with pytest.raises(ValueError, match='gateway Luna'):
        ptr.reservation_capacity(OLD, {OLD: vr.State.INACTIVE})
    for helper, kwargs in [
        (ptr.resolve_overflow_ladder, {'pt_model': NEW}),
        (ptr.resolve_fallback_chain, {'model': NEW, 'pt_model': NEW}),
    ]:
        with pytest.raises(ValueError):
            helper(**kwargs, override=OLD)


@pytest.mark.asyncio
async def test_lkg_reentry_cannot_restore_retired_25(monkeypatch):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    monkeypatch.delenv(ptr.PT_MODEL_OVERRIDE_ENV, raising=False)
    monkeypatch.delenv(vr.STATE_OVERRIDE_ENV, raising=False)
    seen = []
    luna_calls = []

    def handler(request):
        seen.append(request)
        if '/publishers/google/models/' in request.url.path:
            assert '/models/gemini-3.8-flash:' in request.url.path
            assert request.headers[ptr.REQUEST_TYPE_HEADER] == 'dedicated'
            return httpx.Response(429, json={'error': {'message': 'Dedicated provisioned throughput exhausted'}})
        luna_calls.append(request)
        return (
            httpx.Response(503, json={}) if len(luna_calls) == 1 else httpx.Response(200, json=completion('gpt-6-luna'))
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        vertex = VertexGeminiProvider(
            http_client=client, access_token_supplier=AsyncMock(return_value='synthetic-token')
        )
        monkeypatch.setattr(vertex._reservations, 'refresh', AsyncMock(return_value=observed_move()))
        monkeypatch.setattr(vertex._reservations, 'record', AsyncMock())
        resolved = resolve_chat_completion_route(
            load_gateway_config(),
            {'model': ptr.DESKTOP_TEXT_LANES[OLD], 'messages': [{'role': 'user', 'content': 'invented'}]},
        )
        resolved = replace(
            resolved,
            last_known_good_route=resolved.active_route.model_copy(update={'route_artifact_id': 'synthetic.lkg'}),
        )
        result = await execute_chat_completion(
            resolved,
            build_omi_managed_credential_context(ServiceCaller(name='backend')),
            ProviderRegistry({'gemini': vertex, 'openai': OpenAICompatibleChatCompletionProvider(http_client=client)}),
            attempt_trace=AttemptTrace(),
        )
        assert result.used_lkg and result.selected_provider == 'openai'
        assert len(seen) == 2 and len(luna_calls) == 2
        assert not any('/models/gemini-2.5-flash:' in request.url.path for request in seen)


def test_destination_inventory_covers_all_released_product_tags():
    from config.desktop_gemini_attribution_generated import GEMINI_LANES

    assert set(vr.PRODUCT_POLICY_TAGS) == GEMINI_LANES - {'embedding'}
    assert vr.INACTIVE_DESTINATIONS['macos_legacy_tasks'] == vr.R
    assert all(value == vr.LUNA for lane, value in vr.INACTIVE_DESTINATIONS.items() if lane != 'macos_legacy_tasks')


def test_target_stop_override_survives_legacy_pin_containment():
    from utils.llm.vertex_reservation_state import effective_states

    states = observed_move()
    env = {ptr.PT_MODEL_OVERRIDE_ENV: OLD, vr.STATE_OVERRIDE_ENV: json.dumps({NEW: 'inactive'})}
    effective = ptr.cutover_states(states, effective_states(states, env), env=env)
    assert effective[OLD] == vr.State.INACTIVE and effective[NEW] == vr.State.INACTIVE
    assert ptr.reserved_generation_model(OLD, effective) is None


@pytest.mark.asyncio
@pytest.mark.parametrize('stream', [False, True])
async def test_unexpected_25_on_demand_receipt_is_visible(monkeypatch, stream):
    from utils.llm.vertex_policy_metrics import UNEXPECTED_25_PAYGO

    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    monkeypatch.delenv(ptr.PT_MODEL_OVERRIDE_ENV, raising=False)
    monkeypatch.delenv(vr.STATE_OVERRIDE_ENV, raising=False)

    def handler(request):
        assert request.headers[ptr.REQUEST_TYPE_HEADER] == 'dedicated'
        # Deliberately contradictory synthetic provider receipt; alert must see it.
        body = {
            'candidates': [{'content': {'parts': [{'text': 'invented'}]}, 'finishReason': 'STOP'}],
            'trafficType': 'ON_DEMAND',
            'usageMetadata': {'promptTokenCount': 3, 'candidatesTokenCount': 2},
        }
        return (
            httpx.Response(200, content=f'data: {json.dumps(body)}\n\n'.encode())
            if stream
            else httpx.Response(200, json=body)
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = VertexGeminiProvider(
            http_client=client, access_token_supplier=AsyncMock(return_value='synthetic-token')
        )
        monkeypatch.setattr(provider._reservations, 'refresh', AsyncMock(return_value={}))
        monkeypatch.setattr(provider._reservations, 'record', AsyncMock())
        resolved = resolve_chat_completion_route(
            load_gateway_config(),
            {'model': ptr.DESKTOP_TEXT_LANES[OLD], 'messages': [{'role': 'user', 'content': 'invented'}]},
        )
        credentials = build_omi_managed_credential_context(ServiceCaller(name='backend'))
        before = UNEXPECTED_25_PAYGO.labels(lane='desktop_other')._value.get()
        if stream:
            prepared = await _prepared_streaming_iterator(
                resolved,
                credentials,
                ProviderRegistry({'gemini': provider}),
                resolved.active_route,
                attempt_trace=AttemptTrace(),
            )
            _ = [chunk async for chunk in prepared.stream]
        else:
            await execute_chat_completion(resolved, credentials, ProviderRegistry({'gemini': provider}))
        assert UNEXPECTED_25_PAYGO.labels(lane='desktop_other')._value.get() == before + 1
        assert provider._reservation_states.get(OLD) != vr.State.ACTIVE


@pytest.mark.asyncio
@pytest.mark.parametrize('model', [OLD, NEW, 'gemini-2.5-flash-lite', 'gemini-3.1-flash-lite'])
@pytest.mark.parametrize('capacity', ['dedicated', 'shared'])
@pytest.mark.parametrize('stream', [False, True])
async def test_stale_plan_cannot_dispatch_any_non_dream_flash(monkeypatch, model, capacity, stream):
    from utils.llm.vertex_policy_metrics import NON_DREAM_FLASH_AFTER_CUTOVER

    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    monkeypatch.setenv(ptr.PT_MODEL_OVERRIDE_ENV, OLD)
    calls = []

    def handler(request):
        calls.append(request)
        assert request.url.path == '/v1/chat/completions'
        assert json.loads(request.content)['model'] == 'gpt-6-luna'
        if stream:
            return httpx.Response(
                200,
                content=b'data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n',
            )
        return httpx.Response(200, json=completion('gpt-6-luna'))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        vertex = VertexGeminiProvider(http_client=client, access_token_supplier=AsyncMock(return_value='synthetic'))
        monkeypatch.setattr(vertex._reservations, 'refresh', AsyncMock(return_value=observed_move()))
        # Simulate a stale plan, misconfigured overflow, or LKG code bypassing policy.
        monkeypatch.setattr(vertex, '_attempt_plan', lambda *args, **kwargs: [(model, capacity)])
        resolved = resolve_chat_completion_route(
            load_gateway_config(),
            {'model': ptr.DESKTOP_TEXT_LANES[NEW], 'messages': [{'role': 'user', 'content': 'invented'}]},
        )
        registry = ProviderRegistry(
            {'gemini': vertex, 'openai': OpenAICompatibleChatCompletionProvider(http_client=client)}
        )
        credentials = build_omi_managed_credential_context(ServiceCaller(name='backend'))
        label = model if model in {OLD, NEW} else 'other_flash'
        metric = NON_DREAM_FLASH_AFTER_CUTOVER.labels(lane='desktop_other', model=label, traffic_type=capacity)
        before = metric._value.get()
        if stream:
            prepared = await _prepared_streaming_iterator(
                resolved, credentials, registry, resolved.active_route, attempt_trace=AttemptTrace()
            )
            _ = [chunk async for chunk in prepared.stream]
        else:
            result = await execute_chat_completion(resolved, credentials, registry)
            assert result.selected_provider == 'openai'
        assert metric._value.get() == before + 1
        assert len(calls) == 1


def test_stale_remap_destination_cannot_grant_non_dream_reserved_capacity(monkeypatch):
    monkeypatch.setitem(vr.INACTIVE_DESTINATIONS, 'desktop_other', vr.REMAP)
    assert ptr.managed_generation_action(NEW, observed_move()) == vr.LUNA
