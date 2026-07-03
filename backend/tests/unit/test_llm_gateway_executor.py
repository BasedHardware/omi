from __future__ import annotations

import pytest

from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.config_loader import GatewayConfig, load_gateway_config
from llm_gateway.gateway.credentials import build_byok_credential_context, build_omi_managed_credential_context
from llm_gateway.gateway.errors import (
    GatewayCapabilityMismatchError,
    GatewayCredentialFailureError,
    GatewayInvalidRouteConfigError,
    GatewayProviderFailureError,
)
from llm_gateway.gateway.executor import ProviderRegistry, execute_chat_completion, selected_serving_route_artifact_id
from llm_gateway.gateway.providers import FakeChatCompletionProvider, ProviderFailure, fake_success_response
from llm_gateway.gateway.resolver import resolve_chat_completion_route
from llm_gateway.gateway.schemas import CredentialMode, FailureClass, ProviderRef, RolloutPolicy, RolloutStage

LANE_ID = 'omi:auto:chat-structured'
ACTIVE_ROUTE = 'route.chat_structured.2026_06_27.001'
LKG_ROUTE = 'route.chat_structured.2026_06_20.001'


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
    assert result.selected_model == 'gpt-4.1-mini'
    assert not result.fallback_used
    assert not result.used_lkg
    assert provider.calls[0].request['model'] == 'gpt-4.1-mini'
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

    assert provider.calls[0].request['model'] == 'gpt-4.1-mini'
    assert 'response_format' not in provider.calls[0].request


@pytest.mark.asyncio
async def test_executor_uses_executing_route_provider_options_for_lkg_fallback():
    active_route = active_route_with_fallbacks([]).model_copy(
        update={
            'provider_options': {'temperature': 0.9},
            'rollout': RolloutPolicy(stage=RolloutStage.SHADOW, percent=0),
        }
    )
    lkg_route = (
        load_gateway_config(prod_mode=True)
        .route_artifacts[LKG_ROUTE]
        .model_copy(update={'provider_options': {'temperature': 0.1}})
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
    assert [call.model for call in provider.calls] == ['gpt-4.1-mini', 'gpt-4.1-mini', 'gpt-4.1-mini', 'gpt-4o-mini']
    assert result.response['choices'][0]['message']['content'] == '{"answer":"fallback"}'


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'failure_class,error_type',
    [
        (FailureClass.INVALID_CONFIG, GatewayInvalidRouteConfigError),
        (FailureClass.CAPABILITY_MISMATCH, GatewayCapabilityMismatchError),
        (FailureClass.BYOK_AUTH, GatewayCredentialFailureError),
        (FailureClass.BYOK_QUOTA, GatewayCredentialFailureError),
        (FailureClass.BYOK_RATE_LIMIT, GatewayCredentialFailureError),
    ],
)
async def test_executor_does_not_retry_terminal_provider_failures(failure_class, error_type):
    config = config_with_active_route(
        active_route_with_fallbacks([]).model_copy(
            update={'retry': type(load_gateway_config().route_artifacts[ACTIVE_ROUTE].retry)(max_attempts=3)}
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
    assert not result.used_lkg
    assert [call.model for call in provider.calls] == ['gpt-4.1-mini', 'gpt-4o-mini']


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'failure_class,error_type',
    [
        (FailureClass.INVALID_CONFIG, GatewayInvalidRouteConfigError),
        (FailureClass.CAPABILITY_MISMATCH, GatewayCapabilityMismatchError),
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
    assert result.selected_model == 'gpt-4.1-mini'
    assert result.fallback_used
    assert result.fallback_reason == FailureClass.TIMEOUT_BEFORE_OUTPUT
    assert result.used_lkg
    assert [call.model for call in provider.calls] == ['gpt-4.1-mini', 'gpt-4.1-mini']


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
    lkg_route = (
        load_gateway_config(prod_mode=True)
        .route_artifacts[LKG_ROUTE]
        .model_copy(update={'credential_policy': byok_policy()})
    )
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
    lkg_route = (
        load_gateway_config(prod_mode=True)
        .route_artifacts[LKG_ROUTE]
        .model_copy(update={'credential_policy': byok_policy()})
    )
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

    # Provider should be called with the LKG model (gpt-4.1-mini, which now
    # matches the legacy chat_extraction model). The LKG is aligned with the
    # legacy route by design so the shadow pilot is a no-user-visible match.
    provider = FakeChatCompletionProvider(
        [fake_success_response(resolved.last_known_good_route.primary, content='{"answer":"lkg"}')]
    )

    result = await execute_chat_completion(
        resolved,
        omi_credentials(),
        ProviderRegistry({'openai': provider}),
    )

    assert result.selected_route_artifact_id == LKG_ROUTE
    assert result.selected_model == 'gpt-4.1-mini'
    assert result.used_lkg
    assert provider.calls[0].request['model'] == 'gpt-4.1-mini'
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
    assert result.selected_model == 'gpt-4.1-mini'
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
    """A canary route at <100% should send only a proportional fraction of
    requests to the active route, with the rest falling back to LKG.

    Deterministic hashing means the distribution is stable per-request, but
    over many distinct requests the percentage is honored within a tolerance.
    """
    from llm_gateway.gateway.executor import _is_route_eligible_to_serve

    canary_route = active_route_with_fallbacks([]).model_copy(
        update={'rollout': RolloutPolicy(stage=RolloutStage.CANARY, percent=30)}
    )
    config = config_with_active_route(canary_route)

    active_count = 0
    total = 500
    from llm_gateway.gateway.resolver import resolve_chat_completion_route as _resolve

    for i in range(total):
        resolved = _resolve(config, valid_request(messages=[{'role': 'user', 'content': f'msg {i}'}]))
        if _is_route_eligible_to_serve(resolved.active_route, resolved.validated_request):
            active_count += 1

    # With 30% canary, expect ~150 ± 30 (generous tolerance for deterministic hash)
    assert 100 <= active_count <= 200, f'canary distribution off: {active_count}/{total}'


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


def active_route_with_fallbacks(fallbacks: list[ProviderRef]):
    active_route = load_gateway_config(prod_mode=True).route_artifacts[ACTIVE_ROUTE]
    return active_route.model_copy(update={'fallbacks': fallbacks, **_active_rollout_kwargs(active_route)})


def _active_rollout_kwargs(active_route):
    """Return model_copy update dict to promote a route to serving rollout."""
    return {'rollout': RolloutPolicy(stage=RolloutStage.ACTIVE, percent=100)}


def config_with_active_route(active_route):
    base = load_gateway_config(prod_mode=True)
    return config_with_routes(active_route, base.route_artifacts[LKG_ROUTE])


def config_with_routes(active_route, lkg_route):
    base = load_gateway_config(prod_mode=True)
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
    return (
        load_gateway_config(prod_mode=True)
        .lanes[LANE_ID]
        .credential_policy.model_copy(update={'mode': CredentialMode.BYOK})
    )
