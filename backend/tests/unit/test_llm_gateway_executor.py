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
from llm_gateway.gateway.executor import ProviderRegistry, execute_chat_completion
from llm_gateway.gateway.providers import FakeChatCompletionProvider, ProviderFailure, fake_success_response
from llm_gateway.gateway.resolver import resolve_chat_completion_route
from llm_gateway.gateway.schemas import CredentialMode, FailureClass, ProviderRef

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
async def test_executor_retries_provider_up_to_max_attempts_before_fallback():
    """retry.max_attempts is honored: transient failures are retried before
    falling through to the next provider."""
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
    assert result.selected_model == 'gpt-4o-mini'
    assert result.fallback_used
    assert result.fallback_reason == FailureClass.TIMEOUT_BEFORE_OUTPUT
    assert result.used_lkg
    assert [call.model for call in provider.calls] == ['gpt-4.1-mini', 'gpt-4o-mini']


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
    return active_route.model_copy(update={'fallbacks': fallbacks})


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
