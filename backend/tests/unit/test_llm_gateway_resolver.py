from __future__ import annotations

import pytest

from llm_gateway.gateway.config_loader import GatewayConfig, load_gateway_config
from llm_gateway.gateway.errors import (
    GatewayCapabilityMismatchError,
    GatewayInvalidRequestError,
    GatewayInvalidRouteConfigError,
    GatewayModelNotFoundError,
    GatewayUnsupportedModelError,
)
from llm_gateway.gateway.resolver import (
    is_auto_lane_id,
    is_lkg_eligible,
    resolve_chat_completion_route,
    select_lkg_route_for_failure,
)
from llm_gateway.gateway.schemas import FailureClass, StructuredOutputMode

LANE_ID = 'omi:auto:chat-structured'
ACTIVE_ROUTE = 'route.chat_structured.2026_06_27.001'
LKG_ROUTE = 'route.chat_structured.2026_06_20.001'


def test_is_auto_lane_id_only_matches_omi_auto_namespace():
    assert is_auto_lane_id(LANE_ID)
    assert not is_auto_lane_id('gpt-4o-mini')
    assert not is_auto_lane_id('openai:gpt-4o-mini')


def test_resolves_supported_auto_lane_to_active_artifact():
    resolved = resolve_chat_completion_route(load_gateway_config(prod_mode=True), valid_request())

    assert resolved.lane.lane_id == LANE_ID
    assert resolved.active_route.route_artifact_id == ACTIVE_ROUTE
    assert resolved.last_known_good_route.route_artifact_id == LKG_ROUTE
    assert resolved.active_route.primary.provider == 'openai'
    assert resolved.validated_request.model == LANE_ID


def test_unknown_auto_lane_is_model_not_found():
    request = valid_request(model='omi:auto:unknown')

    with pytest.raises(GatewayModelNotFoundError, match='auto lane not found'):
        resolve_chat_completion_route(load_gateway_config(prod_mode=True), request)


def test_missing_model_is_invalid_request_not_model_not_found():
    request = valid_request(model='')

    with pytest.raises(GatewayInvalidRequestError, match='model is required'):
        resolve_chat_completion_route(load_gateway_config(prod_mode=True), request)


def test_bare_provider_model_is_rejected():
    request = valid_request(model='gpt-4o-mini')

    with pytest.raises(GatewayUnsupportedModelError, match='provider model names'):
        resolve_chat_completion_route(load_gateway_config(prod_mode=True), request)


def test_request_capability_mismatch_is_not_lkg_eligible():
    request = valid_request(stream=True)

    with pytest.raises(GatewayCapabilityMismatchError) as exc_info:
        resolve_chat_completion_route(load_gateway_config(prod_mode=True), request)

    assert getattr(exc_info.value, 'failure_class', None) == FailureClass.CAPABILITY_MISMATCH
    route = load_gateway_config(prod_mode=True).route_artifacts[ACTIVE_ROUTE]
    assert not is_lkg_eligible(route, FailureClass.CAPABILITY_MISMATCH)


def test_active_artifact_capability_mismatch_is_invalid_config():
    base = load_gateway_config(prod_mode=True)
    config = config_with_active_route(
        base.route_artifacts[ACTIVE_ROUTE].model_copy(
            update={
                'capabilities': base.route_artifacts[ACTIVE_ROUTE].capabilities.model_copy(
                    update={'structured_output': StructuredOutputMode.JSON_OBJECT}
                )
            }
        )
    )

    with pytest.raises(GatewayInvalidRouteConfigError, match='capabilities mismatch') as exc_info:
        resolve_chat_completion_route(config, valid_request())

    assert exc_info.value.failure_class == FailureClass.INVALID_CONFIG


def test_lkg_is_selected_only_for_active_route_policy_allowed_failure():
    resolved = resolve_chat_completion_route(load_gateway_config(prod_mode=True), valid_request())

    selected = select_lkg_route_for_failure(resolved, FailureClass.TIMEOUT_BEFORE_OUTPUT)

    assert selected is not None
    assert selected.route_artifact_id == LKG_ROUTE


@pytest.mark.parametrize(
    'failure_class',
    [
        FailureClass.BYOK_AUTH,
        FailureClass.BYOK_QUOTA,
        FailureClass.BYOK_RATE_LIMIT,
        FailureClass.BYOK_UNSUPPORTED_PROVIDER,
        FailureClass.MISSING_BYOK_KEY,
        FailureClass.CAPABILITY_MISMATCH,
        FailureClass.INVALID_CONFIG,
    ],
)
def test_lkg_rejected_for_byok_capability_and_config_failure_classes(failure_class):
    resolved = resolve_chat_completion_route(load_gateway_config(prod_mode=True), valid_request())

    assert not is_lkg_eligible(resolved.active_route, failure_class)
    assert select_lkg_route_for_failure(resolved, failure_class) is None


def test_lkg_rejected_when_failure_not_in_active_route_fallback_policy():
    base = load_gateway_config(prod_mode=True)
    active_route = base.route_artifacts[ACTIVE_ROUTE]
    config = config_with_active_route(
        active_route.model_copy(
            update={
                'fallback_policy': active_route.fallback_policy.model_copy(
                    update={
                        'fallback_on': [FailureClass.TIMEOUT_BEFORE_OUTPUT],
                        'never_fallback_on': active_route.fallback_policy.never_fallback_on,
                    }
                )
            }
        )
    )
    resolved = resolve_chat_completion_route(config, valid_request())

    assert not is_lkg_eligible(resolved.active_route, FailureClass.PROVIDER_429_OMI_PAID)
    assert select_lkg_route_for_failure(resolved, FailureClass.PROVIDER_429_OMI_PAID) is None


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


def config_with_active_route(active_route):
    base = load_gateway_config(prod_mode=True)
    route_artifacts = dict(base.route_artifacts)
    route_artifacts[ACTIVE_ROUTE] = active_route
    return GatewayConfig(
        lanes=base.lanes,
        route_artifacts=route_artifacts,
        feature_bundles=base.feature_bundles,
    )
