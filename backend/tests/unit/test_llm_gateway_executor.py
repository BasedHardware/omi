from __future__ import annotations

from functools import cache

import pytest

import llm_gateway.gateway.executor as executor
from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.config_loader import GatewayConfig, load_gateway_config
from llm_gateway.gateway.credentials import build_byok_credential_context, build_omi_managed_credential_context
from llm_gateway.gateway.errors import (
    GatewayCapabilityMismatchError,
    GatewayCredentialFailureError,
    GatewayInvalidRequestError,
    GatewayInvalidRouteConfigError,
    GatewayProviderFailureError,
    GatewayProviderRequestRejectedError,
)
from llm_gateway.gateway.accounting import AttemptTrace
from llm_gateway.gateway.executor import (
    ProviderRegistry,
    execute_chat_completion,
    provider_request_for,
    selected_serving_route_artifact_id,
)
from llm_gateway.gateway.providers import FakeChatCompletionProvider, ProviderFailure, fake_success_response
from llm_gateway.gateway.resolver import resolve_chat_completion_route
from llm_gateway.gateway.schemas import (
    CredentialMode,
    FailureClass,
    ProviderRef,
    RolloutPolicy,
    RolloutStage,
    RouteServingClass,
)

LANE_ID = 'omi:auto:chat-structured'
CHAT_AGENT_LANE_ID = 'omi:auto:chat-agent'
ACTIVE_ROUTE = 'route.chat_structured.2026_06_27.001'
LKG_ROUTE = 'route.chat_structured.2026_06_20.001'


@pytest.mark.asyncio
async def test_jit_budget_reserve_and_settle_use_db_executor(monkeypatch):
    reservation = object()
    calls: list[tuple[object, object, tuple[object, ...], dict[str, object]]] = []

    async def fake_run_blocking(pool, function, *args, **kwargs):
        calls.append((pool, function, args, kwargs))
        if function is executor.reserve_jit_provider_attempt:
            return reservation
        return True

    monkeypatch.setattr(executor, 'run_blocking', fake_run_blocking)

    assert (
        await executor.reserve_jit_attempt(
            owner_uid='user-123',
            run_id='jit-run',
            contract_version='jit-cloud-qa-v1',
            max_attempts=3,
            max_spend_micro_usd=50_000,
            provider='openai',
            model='gpt-5.6-luna',
            input_tokens=10,
            cached_input_tokens=0,
            output_tokens=20,
            cache_write_tokens=0,
            cache_ttl=None,
        )
        is reservation
    )
    assert await executor.settle_jit_attempt(
        reservation,
        provider='openai',
        model='gpt-5.6-luna',
        metadata=None,
        status='failed',
    )

    assert [call[0] for call in calls] == [executor.db_executor, executor.db_executor]
    assert calls[0][1] is executor.reserve_jit_provider_attempt
    assert calls[1][1] is executor.settle_jit_provider_attempt
    assert calls[0][3]['owner_uid'] == 'user-123'
    assert calls[0][3]['run_id'] == 'jit-run'
    assert calls[1][3]['reservation'] is reservation


@pytest.mark.asyncio
async def test_executor_success_uses_active_primary_and_exposes_lane_model():
    config = config_with_active_route(active_route_with_fallbacks([]))
    resolved = resolve_chat_completion_route(config, valid_request())
    active_primary = resolved.active_route.primary
    provider = FakeChatCompletionProvider([fake_success_response(active_primary, content='{"answer":"primary"}')])

    result = await execute_chat_completion(
        resolved,
        omi_credentials(),
        ProviderRegistry({'openai': provider}),
    )

    assert result.response['model'] == LANE_ID
    assert result.response['choices'][0]['message']['content'] == '{"answer":"primary"}'
    assert result.selected_route_artifact_id == ACTIVE_ROUTE
    assert result.selected_provider == 'openai'
    assert result.selected_model == 'gpt-5.6-luna'
    assert not result.fallback_used
    assert result.fallback_reason is None
    assert result.fallback_from_route_artifact_id is None
    assert result.fallback_to_route_artifact_id is None
    assert not result.used_lkg
    assert result.route_serving_class == RouteServingClass.ACTIVE
    assert provider.calls[0].request['model'] == 'gpt-5.6-luna'
    assert provider.calls[0].request['stream'] is False


@pytest.mark.asyncio
async def test_executor_forwards_prompt_parser_request_without_response_format():
    config = config_with_active_route(active_route_with_fallbacks([]))
    request = valid_request()
    request.pop('response_format')
    resolved = resolve_chat_completion_route(config, request)
    active_primary = resolved.active_route.primary
    provider = FakeChatCompletionProvider([fake_success_response(active_primary, content='{"answer":"primary"}')])

    await execute_chat_completion(
        resolved,
        omi_credentials(),
        ProviderRegistry({'openai': provider}),
    )

    assert provider.calls[0].request['model'] == 'gpt-5.6-luna'
    assert 'response_format' not in provider.calls[0].request


def test_chat_agent_provider_request_includes_omi_luna_personality():
    config = gateway_config()
    request = {
        'model': CHAT_AGENT_LANE_ID,
        'messages': [
            {'role': 'system', 'content': 'Use the user context.'},
            {'role': 'user', 'content': 'Hello.'},
        ],
    }
    resolved = resolve_chat_completion_route(config, request)

    provider_request = provider_request_for(resolved, resolved.active_route.primary)

    system_message = provider_request['messages'][0]
    assert system_message['role'] == 'system'
    assert system_message['content'].startswith('You are Omi, a warm and perceptive personal assistant.')
    assert system_message['content'].endswith('Use the user context.')
    assert provider_request['messages'][1] == {'role': 'user', 'content': 'Hello.'}


def test_chat_agent_personality_preserves_array_system_text():
    config = gateway_config()
    request = {
        'model': CHAT_AGENT_LANE_ID,
        'messages': [
            {'role': 'system', 'content': [{'type': 'text', 'text': 'Use the user context.'}]},
            {'role': 'user', 'content': 'Hello.'},
        ],
    }
    resolved = resolve_chat_completion_route(config, request)

    provider_request = provider_request_for(resolved, resolved.active_route.primary)

    system_message = provider_request['messages'][0]
    assert system_message['role'] == 'system'
    assert system_message['content'][0]['type'] == 'text'
    assert system_message['content'][0]['text'].startswith('You are Omi, a warm and perceptive personal assistant.')
    assert system_message['content'][1:] == [{'type': 'text', 'text': 'Use the user context.'}]


def test_chat_agent_tools_force_reasoning_effort_none_for_luna_chat_completions():
    """gpt-5.6-luna rejects function tools when reasoning_effort != none on chat/completions."""
    config = gateway_config()
    # Mutate the serving route the way a bad override would: medium effort + tools.
    route = config.route_artifacts['route.chat_agent.model_config.001']
    config.route_artifacts['route.chat_agent.model_config.001'] = route.model_copy(
        update={'provider_options': {**dict(route.provider_options), 'reasoning_effort': 'medium', 'temperature': 0.7}}
    )
    request = {
        'model': CHAT_AGENT_LANE_ID,
        'messages': [
            {'role': 'system', 'content': 'Use tools when needed.'},
            {'role': 'user', 'content': 'What did I say about coffee?'},
        ],
        'tools': [
            {
                'type': 'function',
                'function': {
                    'name': 'get_memories_tool',
                    'description': 'Get memories',
                    'parameters': {'type': 'object', 'properties': {'query': {'type': 'string'}}},
                },
            }
        ],
        'tool_choice': 'auto',
    }
    resolved = resolve_chat_completion_route(config, request)

    provider_request = provider_request_for(resolved, resolved.active_route.primary)

    assert provider_request['model'] == 'gpt-5.6-luna'
    assert provider_request['tools']
    assert provider_request.get('reasoning_effort') == 'none'
    assert 'temperature' not in provider_request


def test_chat_agent_default_route_reasoning_effort_is_none():
    config = gateway_config()
    request = {
        'model': CHAT_AGENT_LANE_ID,
        'messages': [{'role': 'user', 'content': 'Hello.'}],
        'tools': [
            {
                'type': 'function',
                'function': {
                    'name': 'get_memories_tool',
                    'description': 'Get memories',
                    'parameters': {'type': 'object', 'properties': {}},
                },
            }
        ],
    }
    resolved = resolve_chat_completion_route(config, request)
    provider_request = provider_request_for(resolved, resolved.active_route.primary)
    assert provider_request.get('reasoning_effort') == 'none'


def test_gpt56_tools_strip_bool_temperature():
    """True==1 must not bypass the temperature sanitize (OpenAI rejects non-default)."""
    config = gateway_config()
    route = config.route_artifacts['route.chat_agent.model_config.001']
    config.route_artifacts['route.chat_agent.model_config.001'] = route.model_copy(
        update={'provider_options': {**dict(route.provider_options), 'temperature': True}}
    )
    request = {
        'model': CHAT_AGENT_LANE_ID,
        'messages': [{'role': 'user', 'content': 'hi'}],
        'tools': [
            {
                'type': 'function',
                'function': {
                    'name': 'get_memories_tool',
                    'description': 'Get memories',
                    'parameters': {'type': 'object', 'properties': {}},
                },
            }
        ],
    }
    resolved = resolve_chat_completion_route(config, request)
    provider_request = provider_request_for(resolved, resolved.active_route.primary)
    assert 'temperature' not in provider_request


@pytest.mark.asyncio
async def test_executor_uses_lkg_route_provider_options_when_active_is_shadow():
    active_route = active_route_with_fallbacks([]).model_copy(
        update={
            'provider_options': {'temperature': 0.9},
            'rollout': RolloutPolicy(stage=RolloutStage.SHADOW, percent=0),
        }
    )
    # Use a non-gpt-5.6 LKG primary so temperature is a meaningful provider option
    # (gpt-5.6* only accepts the default temperature and strips other values).
    lkg_base = gateway_config().route_artifacts[LKG_ROUTE]
    lkg_route = lkg_base.model_copy(
        update={
            'primary': ProviderRef(provider='openai', model='gpt-4.1-mini'),
            'provider_options': {'temperature': 0.1},
        }
    )
    config = config_with_routes(active_route, lkg_route)
    resolved = resolve_chat_completion_route(config, valid_request())
    provider = FakeChatCompletionProvider([fake_success_response(resolved.last_known_good_route.primary)])

    await execute_chat_completion(
        resolved,
        omi_credentials(),
        ProviderRegistry({'openai': provider}),
    )

    assert provider.calls[0].request['temperature'] == 0.1


@pytest.mark.asyncio
async def test_executor_maps_gemini_thinking_budget_before_provider_call():
    active_route = active_route_with_fallbacks([]).model_copy(update={'provider_options': {'thinking_budget': 0}})
    config = config_with_active_route(active_route)
    resolved = resolve_chat_completion_route(config, valid_request())
    provider = FakeChatCompletionProvider([fake_success_response(resolved.active_route.primary)])

    await execute_chat_completion(
        resolved,
        omi_credentials(),
        ProviderRegistry({'openai': provider}),
    )

    assert provider.calls[0].request['reasoning_effort'] == 'none'
    assert 'thinking_budget' not in provider.calls[0].request


@pytest.mark.asyncio
async def test_executor_retries_provider_up_to_max_attempts_before_fallback():
    fallback_ref = ProviderRef(provider='openai', model='gpt-4o-mini')
    config = config_with_active_route(active_route_with_fallbacks([fallback_ref]))
    # Override retry to 3 attempts on the active route
    active_route = config.route_artifacts[ACTIVE_ROUTE].model_copy(
        update={'retry': type(config.route_artifacts[ACTIVE_ROUTE].retry)(max_attempts=3)}
    )
    config = config_with_active_route(active_route.model_copy(update={'fallbacks': [fallback_ref]}))
    resolved = resolve_chat_completion_route(config, valid_request())
    # 3 transient failures then fallback succeeds
    provider = FakeChatCompletionProvider(
        [
            ProviderFailure(FailureClass.TIMEOUT_BEFORE_OUTPUT),
            ProviderFailure(FailureClass.TIMEOUT_BEFORE_OUTPUT),
            ProviderFailure(FailureClass.TIMEOUT_BEFORE_OUTPUT),
            fake_success_response(fallback_ref, content='{"answer":"fallback"}'),
        ]
    )

    result = await execute_chat_completion(
        resolved,
        omi_credentials(),
        ProviderRegistry({'openai': provider}),
    )

    # Primary tried 3 times (max_attempts), then fallback once
    assert [call.model for call in provider.calls] == ['gpt-5.6-luna', 'gpt-5.6-luna', 'gpt-5.6-luna', 'gpt-4o-mini']
    assert result.response['choices'][0]['message']['content'] == '{"answer":"fallback"}'


@pytest.mark.asyncio
async def test_executor_stops_jit_attempts_at_qualification_ceiling():
    route = active_route_with_fallbacks([]).model_copy(
        update={'retry': type(gateway_config().route_artifacts[ACTIVE_ROUTE].retry)(max_attempts=3)}
    )
    resolved = resolve_chat_completion_route(config_with_active_route(route), valid_request())
    provider = FakeChatCompletionProvider(
        [
            ProviderFailure(FailureClass.TIMEOUT_BEFORE_OUTPUT),
            ProviderFailure(FailureClass.TIMEOUT_BEFORE_OUTPUT),
            fake_success_response(route.primary),
        ]
    )
    trace = AttemptTrace()

    with pytest.raises(GatewayInvalidRequestError, match='JIT provider attempt budget exhausted'):
        await execute_chat_completion(
            resolved,
            omi_credentials(),
            ProviderRegistry({'openai': provider}),
            attempt_trace=trace,
            max_provider_attempts=2,
        )

    assert len(provider.calls) == 2
    assert len(trace.attempts) == 2


@pytest.mark.asyncio
async def test_executor_retries_with_only_the_remaining_request_deadline(monkeypatch):
    active_route = active_route_with_fallbacks([])
    active_route = active_route.model_copy(
        update={
            'retry': type(active_route.retry)(max_attempts=2),
            'timeouts': active_route.timeouts.model_copy(update={'request_ms': 100}),
        }
    )
    resolved = resolve_chat_completion_route(config_with_active_route(active_route), valid_request())
    clock = iter([0.0, 0.0, 0.075])
    monkeypatch.setattr(executor, 'monotonic', lambda: next(clock), raising=False)
    provider = FakeChatCompletionProvider(
        [
            ProviderFailure(FailureClass.TIMEOUT_BEFORE_OUTPUT),
            fake_success_response(active_route.primary),
        ]
    )

    await execute_chat_completion(resolved, omi_credentials(), ProviderRegistry({'openai': provider}))

    assert [call.timeout_ms for call in provider.calls] == [100, 25]


@pytest.mark.asyncio
async def test_executor_attempt_trace_retains_each_retry_and_fallback() -> None:
    fallback_ref = ProviderRef(provider='openai', model='gpt-4o-mini')
    route = active_route_with_fallbacks([fallback_ref])
    route = route.model_copy(update={'retry': type(route.retry)(max_attempts=2)})
    resolved = resolve_chat_completion_route(config_with_active_route(route), valid_request())
    provider = FakeChatCompletionProvider(
        [
            ProviderFailure(FailureClass.TIMEOUT_BEFORE_OUTPUT),
            ProviderFailure(FailureClass.TIMEOUT_BEFORE_OUTPUT),
            fake_success_response(fallback_ref),
        ]
    )
    trace = AttemptTrace()

    await execute_chat_completion(
        resolved, omi_credentials(), ProviderRegistry({'openai': provider}), attempt_trace=trace
    )

    assert [attempt.outcome for attempt in trace.attempts] == ['error', 'error', 'success']
    assert [attempt.retry_ordinal for attempt in trace.attempts] == [1, 2, 1]
    assert trace.attempts[-1].configured_model == 'gpt-4o-mini'
    assert trace.attempts[-1].fallback_reason == FailureClass.TIMEOUT_BEFORE_OUTPUT.value


@pytest.mark.asyncio
async def test_jit_unknown_provider_failure_is_returned_without_retry_or_fallback(monkeypatch):
    fallback_ref = ProviderRef(provider='openai', model='gpt-4o-mini')
    route = active_route_with_fallbacks([fallback_ref]).model_copy(
        update={'retry': type(active_route_with_fallbacks([]).retry)(max_attempts=3)}
    )
    resolved = resolve_chat_completion_route(config_with_active_route(route), valid_request())
    provider = FakeChatCompletionProvider([ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID)])
    settlements: list[dict[str, object]] = []

    async def reserve(**_kwargs):
        return object()

    async def settle(_reservation, **kwargs):
        settlements.append(kwargs)
        return True

    monkeypatch.setattr(executor, 'reserve_jit_attempt', reserve)
    monkeypatch.setattr(executor, 'settle_jit_attempt', settle)

    with pytest.raises(GatewayProviderFailureError) as raised:
        await execute_chat_completion(
            resolved,
            omi_credentials(),
            ProviderRegistry({'openai': provider}),
            attempt_trace=AttemptTrace(),
            max_provider_attempts=3,
            jit_max_spend_micro_usd=50_000,
            jit_owner_uid='user-123',
            jit_run_id='jit-unknown-cost',
            jit_contract_version='jit-cloud-qa-v1',
        )

    assert raised.value.failure_class == FailureClass.PROVIDER_5XX_OMI_PAID
    assert len(provider.calls) == 1
    assert len(settlements) == 1
    assert settlements[0]['status'] == 'failed'


@pytest.mark.asyncio
async def test_jit_reservation_that_outlives_deadline_is_released_without_provider_call(monkeypatch):
    route = active_route_with_fallbacks([])
    config = config_with_active_route(route)
    resolved = resolve_chat_completion_route(config, valid_request())
    provider = FakeChatCompletionProvider()
    reservation = object()
    settlements: list[dict[str, object]] = []
    clock = iter([0.0, 2.0])
    monkeypatch.setattr(executor, 'monotonic', lambda: next(clock), raising=False)

    async def reserve(**_kwargs):
        return reservation

    async def settle(_reservation, **kwargs):
        settlements.append(kwargs)
        return True

    monkeypatch.setattr(executor, 'reserve_jit_attempt', reserve)
    monkeypatch.setattr(executor, 'settle_jit_attempt', settle)

    response, error = await executor._attempt_provider(
        resolved,
        route,
        provider,
        route.primary,
        omi_credentials(),
        attempt_trace=AttemptTrace(),
        max_provider_attempts=3,
        jit_max_spend_micro_usd=50_000,
        jit_owner_uid='user-123',
        jit_run_id='jit-deadline-release',
        jit_contract_version='jit-cloud-qa-v1',
        fallback_reason=None,
        deadline_monotonic=1.0,
    )

    assert response is None
    assert error is not None and error.failure_class == FailureClass.TIMEOUT_BEFORE_OUTPUT
    assert provider.calls == []
    assert settlements == [
        {
            'provider': route.primary.provider,
            'model': route.primary.model,
            'metadata': None,
            'status': 'released',
            'release_without_provider': True,
        }
    ]


@pytest.mark.asyncio
async def test_jit_success_with_rejected_settlement_is_recorded_as_accounting_error(monkeypatch):
    route = active_route_with_fallbacks([])
    resolved = resolve_chat_completion_route(config_with_active_route(route), valid_request())
    provider = FakeChatCompletionProvider([fake_success_response(route.primary)])
    trace = AttemptTrace()

    async def reserve(**_kwargs):
        return object()

    async def reject_settlement(_reservation, **_kwargs):
        return False

    monkeypatch.setattr(executor, 'reserve_jit_attempt', reserve)
    monkeypatch.setattr(executor, 'settle_jit_attempt', reject_settlement)

    response, error = await executor._attempt_provider(
        resolved,
        route,
        provider,
        route.primary,
        omi_credentials(),
        attempt_trace=trace,
        max_provider_attempts=3,
        jit_max_spend_micro_usd=50_000,
        jit_owner_uid='user-123',
        jit_run_id='jit-settlement-failure',
        jit_contract_version='jit-cloud-qa-v1',
        fallback_reason=None,
        deadline_monotonic=executor.monotonic() + 10_000.0,
    )

    assert response is None
    assert isinstance(error, GatewayInvalidRequestError)
    assert len(provider.calls) == 1
    assert len(trace.attempts) == 1
    assert trace.attempts[0].outcome == 'error'
    assert trace.attempts[0].error_class == 'jit_budget_settlement_failed'


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'failure_class,error_type',
    [
        (FailureClass.INVALID_CONFIG, GatewayInvalidRouteConfigError),
        (FailureClass.CAPABILITY_MISMATCH, GatewayCapabilityMismatchError),
        (FailureClass.PROVIDER_INVALID_REQUEST, GatewayProviderRequestRejectedError),
        (FailureClass.BYOK_AUTH, GatewayCredentialFailureError),
        (FailureClass.BYOK_QUOTA, GatewayCredentialFailureError),
        (FailureClass.BYOK_RATE_LIMIT, GatewayCredentialFailureError),
    ],
)
async def test_executor_does_not_retry_terminal_provider_failures(failure_class, error_type):
    config = config_with_active_route(
        active_route_with_fallbacks([]).model_copy(
            update={'retry': type(gateway_config().route_artifacts[ACTIVE_ROUTE].retry)(max_attempts=3)}
        )
    )
    resolved = resolve_chat_completion_route(config, valid_request())
    provider = FakeChatCompletionProvider([ProviderFailure(failure_class)])

    with pytest.raises(error_type):
        await execute_chat_completion(
            resolved,
            omi_credentials(),
            ProviderRegistry({'openai': provider}),
        )

    assert len(provider.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'failure_class',
    [
        FailureClass.TIMEOUT_BEFORE_OUTPUT,
        FailureClass.PROVIDER_429_OMI_PAID,
        FailureClass.PROVIDER_5XX_OMI_PAID,
    ],
)
async def test_executor_uses_active_route_fallback_for_policy_allowed_failures(failure_class):
    fallback_ref = ProviderRef(provider='openai', model='gpt-4o-mini')
    config = config_with_active_route(active_route_with_fallbacks([fallback_ref]))
    resolved = resolve_chat_completion_route(config, valid_request())
    provider = FakeChatCompletionProvider(
        [
            ProviderFailure(failure_class, safe_message='raw provider detail should not leak'),
            fake_success_response(fallback_ref, content='{"answer":"fallback"}'),
        ]
    )

    result = await execute_chat_completion(
        resolved,
        omi_credentials(),
        ProviderRegistry({'openai': provider}),
    )

    assert result.response['model'] == LANE_ID
    assert result.response['choices'][0]['message']['content'] == '{"answer":"fallback"}'
    assert result.selected_route_artifact_id == ACTIVE_ROUTE
    assert result.selected_model == 'gpt-4o-mini'
    assert result.fallback_used
    assert result.fallback_reason == failure_class
    assert result.fallback_from_route_artifact_id == ACTIVE_ROUTE
    assert result.fallback_to_route_artifact_id == ACTIVE_ROUTE
    assert not result.used_lkg
    assert result.route_serving_class == RouteServingClass.ACTUAL_FALLBACK
    assert [call.model for call in provider.calls] == ['gpt-5.6-luna', 'gpt-4o-mini']


@pytest.mark.asyncio
async def test_executor_identical_provider_model_retry_is_not_actual_fallback():
    """A within-route fallback to the same provider+model is a retry, not a
    distinct provider/route failover, and must not be classified as
    ACTUAL_FALLBACK — per the PR behavioral contract that actual fallback
    requires a *subsequent provider/route* success."""
    identical_ref = ProviderRef(provider='openai', model='gpt-5.6-luna')
    config = config_with_active_route(active_route_with_fallbacks([identical_ref]))
    resolved = resolve_chat_completion_route(config, valid_request())
    provider = FakeChatCompletionProvider(
        [
            ProviderFailure(FailureClass.TIMEOUT_BEFORE_OUTPUT),
            fake_success_response(identical_ref, content='{"answer":"retry"}'),
        ]
    )

    result = await execute_chat_completion(
        resolved,
        omi_credentials(),
        ProviderRegistry({'openai': provider}),
    )

    assert result.selected_model == 'gpt-5.6-luna'
    assert not result.fallback_used
    assert result.fallback_reason is None
    assert result.fallback_from_route_artifact_id is None
    assert result.fallback_to_route_artifact_id is None
    assert result.route_serving_class == RouteServingClass.ACTIVE
    assert [call.model for call in provider.calls] == ['gpt-5.6-luna', 'gpt-5.6-luna']


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'failure_class,error_type',
    [
        (FailureClass.INVALID_CONFIG, GatewayInvalidRouteConfigError),
        (FailureClass.CAPABILITY_MISMATCH, GatewayCapabilityMismatchError),
        (FailureClass.PROVIDER_INVALID_REQUEST, GatewayProviderRequestRejectedError),
        (FailureClass.BYOK_AUTH, GatewayCredentialFailureError),
        (FailureClass.BYOK_QUOTA, GatewayCredentialFailureError),
        (FailureClass.BYOK_RATE_LIMIT, GatewayCredentialFailureError),
        (FailureClass.MISSING_BYOK_KEY, GatewayCredentialFailureError),
    ],
)
async def test_executor_does_not_fallback_for_non_eligible_failures(failure_class, error_type):
    fallback_ref = ProviderRef(provider='openai', model='gpt-4o-mini')
    config = config_with_active_route(active_route_with_fallbacks([fallback_ref]))
    resolved = resolve_chat_completion_route(config, valid_request())
    provider = FakeChatCompletionProvider([ProviderFailure(failure_class)])

    with pytest.raises(error_type) as exc_info:
        await execute_chat_completion(
            resolved,
            omi_credentials(),
            ProviderRegistry({'openai': provider}),
        )

    assert exc_info.value.failure_class == failure_class
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_executor_uses_lkg_only_when_active_route_policy_allows():
    config = config_with_active_route(active_route_with_fallbacks([]))
    resolved = resolve_chat_completion_route(config, valid_request())
    provider = FakeChatCompletionProvider(
        [
            ProviderFailure(FailureClass.TIMEOUT_BEFORE_OUTPUT),
            fake_success_response(resolved.last_known_good_route.primary, content='{"answer":"lkg"}'),
        ]
    )

    result = await execute_chat_completion(
        resolved,
        omi_credentials(),
        ProviderRegistry({'openai': provider}),
    )

    assert result.response['model'] == LANE_ID
    assert result.selected_route_artifact_id == LKG_ROUTE
    assert result.selected_model == 'gpt-5.6-luna'
    assert result.fallback_used
    assert result.fallback_reason == FailureClass.TIMEOUT_BEFORE_OUTPUT
    assert result.fallback_from_route_artifact_id == ACTIVE_ROUTE
    assert result.fallback_to_route_artifact_id == LKG_ROUTE
    assert result.used_lkg
    assert result.route_serving_class == RouteServingClass.ACTUAL_FALLBACK
    assert [call.model for call in provider.calls] == ['gpt-5.6-luna', 'gpt-5.6-luna']


@pytest.mark.asyncio
async def test_executor_does_not_use_lkg_when_active_route_policy_rejects_failure():
    active_route = active_route_with_fallbacks([])
    config = config_with_active_route(
        active_route.model_copy(
            update={
                'fallback_policy': active_route.fallback_policy.model_copy(
                    update={'fallback_on': [FailureClass.PROVIDER_429_OMI_PAID]}
                )
            }
        )
    )
    resolved = resolve_chat_completion_route(config, valid_request())
    provider = FakeChatCompletionProvider([ProviderFailure(FailureClass.TIMEOUT_BEFORE_OUTPUT)])

    with pytest.raises(GatewayProviderFailureError) as exc_info:
        await execute_chat_completion(
            resolved,
            omi_credentials(),
            ProviderRegistry({'openai': provider}),
        )

    assert exc_info.value.failure_class == FailureClass.TIMEOUT_BEFORE_OUTPUT
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_executor_remains_error_when_active_and_lkg_routes_both_fail():
    config = config_with_active_route(active_route_with_fallbacks([]))
    resolved = resolve_chat_completion_route(config, valid_request())
    provider = FakeChatCompletionProvider(
        [
            ProviderFailure(FailureClass.TIMEOUT_BEFORE_OUTPUT),
            ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID),
        ]
    )

    with pytest.raises(GatewayProviderFailureError) as exc_info:
        await execute_chat_completion(
            resolved,
            omi_credentials(),
            ProviderRegistry({'openai': provider}),
        )

    assert exc_info.value.failure_class == FailureClass.PROVIDER_5XX_OMI_PAID
    assert [call.model for call in provider.calls] == ['gpt-5.6-luna', 'gpt-5.6-luna']


@pytest.mark.asyncio
async def test_unsupported_omi_paid_provider_is_visible_and_does_not_fallback():
    active_route = active_route_with_fallbacks([ProviderRef(provider='openai', model='gpt-4o-mini')]).model_copy(
        update={'primary': ProviderRef(provider='missing-provider', model='missing-model')}
    )
    config = config_with_active_route(active_route)
    resolved = resolve_chat_completion_route(config, valid_request())
    provider = FakeChatCompletionProvider()

    with pytest.raises(GatewayInvalidRouteConfigError) as exc_info:
        await execute_chat_completion(
            resolved,
            omi_credentials(),
            ProviderRegistry({'openai': provider}),
        )

    assert exc_info.value.failure_class == FailureClass.INVALID_CONFIG
    assert provider.calls == []


@pytest.mark.asyncio
async def test_byok_missing_key_and_unsupported_provider_fail_without_fallback_or_lkg():
    active_route = active_route_with_fallbacks([ProviderRef(provider='openai', model='gpt-4o-mini')]).model_copy(
        update={
            'credential_policy': byok_policy(),
            'primary': ProviderRef(provider='anthropic', model='claude-test'),
        }
    )
    lkg_route = gateway_config().route_artifacts[LKG_ROUTE].model_copy(update={'credential_policy': byok_policy()})
    config = config_with_routes(active_route, lkg_route)
    resolved = resolve_chat_completion_route(config, valid_request())

    with pytest.raises(GatewayCredentialFailureError) as exc_info:
        await execute_chat_completion(
            resolved,
            build_byok_credential_context(ServiceCaller(name='backend'), {'openai': ''}),
            ProviderRegistry({'openai': FakeChatCompletionProvider()}),
        )

    assert exc_info.value.failure_class == FailureClass.BYOK_UNSUPPORTED_PROVIDER

    supported_active = active_route.model_copy(update={'primary': ProviderRef(provider='openai', model='gpt-4.1-mini')})
    resolved = resolve_chat_completion_route(config_with_routes(supported_active, lkg_route), valid_request())
    with pytest.raises(GatewayCredentialFailureError) as missing_key_info:
        await execute_chat_completion(
            resolved,
            build_byok_credential_context(ServiceCaller(name='backend'), {'openai': ''}),
            ProviderRegistry({'openai': FakeChatCompletionProvider()}),
        )

    assert missing_key_info.value.failure_class == FailureClass.MISSING_BYOK_KEY


@pytest.mark.asyncio
async def test_raw_byok_key_is_not_in_provider_error_repr_or_dump():
    raw_key = 'sk-test-secret-should-not-appear'
    active_route = active_route_with_fallbacks([]).model_copy(update={'credential_policy': byok_policy()})
    lkg_route = gateway_config().route_artifacts[LKG_ROUTE].model_copy(update={'credential_policy': byok_policy()})
    config = config_with_routes(active_route, lkg_route)
    resolved = resolve_chat_completion_route(config, valid_request())
    provider = FakeChatCompletionProvider(
        [ProviderFailure(FailureClass.BYOK_AUTH, safe_message=f'provider rejected {raw_key}')]
    )

    with pytest.raises(GatewayCredentialFailureError) as exc_info:
        await execute_chat_completion(
            resolved,
            build_byok_credential_context(ServiceCaller(name='backend'), {'openai': raw_key}),
            ProviderRegistry({'openai': provider}),
        )

    assert raw_key not in repr(exc_info.value)
    assert raw_key not in str(exc_info.value.to_error_dict())
    assert raw_key not in str(provider.calls[0].request)


@pytest.mark.asyncio
async def test_shadow_active_route_serves_lkg_not_active():
    """When the active route is in shadow rollout (percent 0), traffic should
    be served by the last-known-good route, not the shadow candidate."""
    # Keep the checked-in shadow rollout on the active route
    shadow_route = active_route_with_fallbacks([]).model_copy(
        update={'rollout': RolloutPolicy(stage=RolloutStage.SHADOW, percent=0)}
    )
    config = config_with_active_route(shadow_route)
    resolved = resolve_chat_completion_route(config, valid_request())

    # Provider should be called with the gateway LKG model (gpt-5.6-luna).
    # The gateway route is intentionally independent from legacy chat extraction.
    provider = FakeChatCompletionProvider(
        [fake_success_response(resolved.last_known_good_route.primary, content='{"answer":"lkg"}')]
    )

    result = await execute_chat_completion(
        resolved,
        omi_credentials(),
        ProviderRegistry({'openai': provider}),
    )

    assert result.selected_route_artifact_id == LKG_ROUTE
    assert result.selected_model == 'gpt-5.6-luna'
    assert result.used_lkg
    assert not result.fallback_used
    assert result.fallback_reason is None
    assert result.fallback_from_route_artifact_id is None
    assert result.fallback_to_route_artifact_id is None
    assert result.route_serving_class == RouteServingClass.LKG
    assert provider.calls[0].request['model'] == 'gpt-5.6-luna'
    assert selected_serving_route_artifact_id(resolved) == LKG_ROUTE


@pytest.mark.asyncio
async def test_disabled_active_route_serves_lkg_not_active():
    """When the active route is disabled rollout, traffic should fall back to
    the last-known-good route."""
    disabled_route = active_route_with_fallbacks([]).model_copy(
        update={'rollout': RolloutPolicy(stage=RolloutStage.DISABLED, percent=0)}
    )
    config = config_with_active_route(disabled_route)
    resolved = resolve_chat_completion_route(config, valid_request())

    provider = FakeChatCompletionProvider(
        [fake_success_response(resolved.last_known_good_route.primary, content='{"answer":"lkg"}')]
    )

    result = await execute_chat_completion(
        resolved,
        omi_credentials(),
        ProviderRegistry({'openai': provider}),
    )

    assert result.selected_route_artifact_id == LKG_ROUTE
    assert result.selected_model == 'gpt-5.6-luna'
    assert result.used_lkg


@pytest.mark.asyncio
async def test_canary_active_route_with_percent_zero_serves_lkg():
    """A canary route with percent 0 should not serve live traffic."""
    canary_route = active_route_with_fallbacks([]).model_copy(
        update={'rollout': RolloutPolicy(stage=RolloutStage.CANARY, percent=0)}
    )
    config = config_with_active_route(canary_route)
    resolved = resolve_chat_completion_route(config, valid_request())

    provider = FakeChatCompletionProvider(
        [fake_success_response(resolved.last_known_good_route.primary, content='{"answer":"lkg"}')]
    )

    result = await execute_chat_completion(
        resolved,
        omi_credentials(),
        ProviderRegistry({'openai': provider}),
    )

    assert result.selected_route_artifact_id == LKG_ROUTE
    assert result.used_lkg


@pytest.mark.asyncio
async def test_canary_route_enforces_partial_rollout_percentage():
    """A canary route at <100% should send stable in-bucket requests active and the rest to LKG."""
    from llm_gateway.gateway.executor import _is_route_eligible_to_serve

    canary_route = active_route_with_fallbacks([]).model_copy(
        update={'rollout': RolloutPolicy(stage=RolloutStage.CANARY, percent=30)}
    )
    config = config_with_active_route(canary_route)

    active_messages = ('msg 1', 'msg 3', 'msg 5')
    lkg_messages = ('msg 0', 'msg 2', 'msg 4')

    for content in active_messages:
        resolved = resolve_chat_completion_route(config, valid_request(messages=[{'role': 'user', 'content': content}]))
        assert _is_route_eligible_to_serve(resolved.active_route, resolved.validated_request)

    for content in lkg_messages:
        resolved = resolve_chat_completion_route(config, valid_request(messages=[{'role': 'user', 'content': content}]))
        if _is_route_eligible_to_serve(resolved.active_route, resolved.validated_request):
            pytest.fail(f'{content!r} unexpectedly entered the 30% canary bucket')


@pytest.mark.asyncio
async def test_canary_sampling_is_deterministic_for_same_request():
    """The same request should consistently get the same canary decision."""
    from llm_gateway.gateway.executor import _is_route_eligible_to_serve

    canary_route = active_route_with_fallbacks([]).model_copy(
        update={'rollout': RolloutPolicy(stage=RolloutStage.CANARY, percent=50)}
    )
    config = config_with_active_route(canary_route)

    resolved = resolve_chat_completion_route(config, valid_request())
    decision1 = _is_route_eligible_to_serve(resolved.active_route, resolved.validated_request)
    decision2 = _is_route_eligible_to_serve(resolved.active_route, resolved.validated_request)

    assert decision1 == decision2


@pytest.mark.asyncio
async def test_canary_route_at_100_percent_serves_active():
    """A canary route at 100% should serve all traffic from the active route."""
    canary_route = active_route_with_fallbacks([]).model_copy(
        update={'rollout': RolloutPolicy(stage=RolloutStage.CANARY, percent=100)}
    )
    config = config_with_active_route(canary_route)
    resolved = resolve_chat_completion_route(config, valid_request())

    provider = FakeChatCompletionProvider(
        [fake_success_response(resolved.active_route.primary, content='{"answer":"active"}')]
    )

    result = await execute_chat_completion(
        resolved,
        omi_credentials(),
        ProviderRegistry({'openai': provider}),
    )

    assert result.selected_route_artifact_id == ACTIVE_ROUTE
    assert not result.used_lkg
    assert not result.fallback_used
    assert result.route_serving_class == RouteServingClass.CANARY


def valid_request(**overrides):
    request = {
        'model': LANE_ID,
        'messages': [{'role': 'user', 'content': 'Return JSON.'}],
        'response_format': {
            'type': 'json_schema',
            'json_schema': {
                'name': 'test_schema',
                'schema': {
                    'type': 'object',
                    'properties': {'answer': {'type': 'string'}},
                    'required': ['answer'],
                    'additionalProperties': False,
                },
            },
        },
    }
    request.update(overrides)
    return request


def omi_credentials():
    return build_omi_managed_credential_context(ServiceCaller(name='backend'))


@cache
def gateway_config() -> GatewayConfig:
    """Load the immutable checked-in gateway config once per test module."""
    return load_gateway_config(prod_mode=True)


def active_route_with_fallbacks(fallbacks: list[ProviderRef]):
    active_route = gateway_config().route_artifacts[ACTIVE_ROUTE]
    return active_route.model_copy(update={'fallbacks': fallbacks, **_active_rollout_kwargs(active_route)})


def _active_rollout_kwargs(active_route):
    """Return model_copy update dict to promote a route to serving rollout."""
    return {'rollout': RolloutPolicy(stage=RolloutStage.ACTIVE, percent=100)}


def config_with_active_route(active_route):
    base = gateway_config()
    return config_with_routes(active_route, base.route_artifacts[LKG_ROUTE])


def config_with_routes(active_route, lkg_route):
    base = gateway_config()
    route_artifacts = dict(base.route_artifacts)
    route_artifacts[ACTIVE_ROUTE] = active_route
    route_artifacts[LKG_ROUTE] = lkg_route
    lanes = dict(base.lanes)
    lanes[LANE_ID] = lanes[LANE_ID].model_copy(update={'credential_policy': active_route.credential_policy})
    return GatewayConfig(
        lanes=lanes,
        route_artifacts=route_artifacts,
        feature_bundles=base.feature_bundles,
    )


def byok_policy():
    return gateway_config().lanes[LANE_ID].credential_policy.model_copy(update={'mode': CredentialMode.BYOK})
