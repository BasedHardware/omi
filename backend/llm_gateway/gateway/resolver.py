from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from llm_gateway.gateway.config_loader import GatewayConfig
from llm_gateway.gateway.credentials import is_byok_failure_class
from llm_gateway.gateway.errors import (
    GatewayCapabilityMismatchError,
    GatewayInvalidRequestError,
    GatewayInvalidRouteConfigError,
    GatewayModelNotFoundError,
    GatewayUnsupportedModelError,
)
from llm_gateway.gateway.schemas import FailureClass, LaneConfig, RouteArtifact, Surface
from llm_gateway.gateway.validator import ValidatedChatCompletionRequest, validate_chat_completion_request

AUTO_LANE_PREFIX = 'omi:auto:'
NEVER_LKG_FAILURE_CLASSES = frozenset(
    {
        FailureClass.CAPABILITY_MISMATCH,
        FailureClass.PROVIDER_INVALID_REQUEST,
        FailureClass.INVALID_CONFIG,
        FailureClass.BYOK_AUTH,
        FailureClass.BYOK_QUOTA,
        FailureClass.BYOK_RATE_LIMIT,
        FailureClass.BYOK_UNSUPPORTED_PROVIDER,
        FailureClass.MISSING_BYOK_KEY,
    }
)


@dataclass(frozen=True)
class ResolvedRoute:
    lane: LaneConfig
    active_route: RouteArtifact
    last_known_good_route: RouteArtifact
    validated_request: ValidatedChatCompletionRequest


def is_auto_lane_id(model: str) -> bool:
    return model.startswith(AUTO_LANE_PREFIX)


def resolve_chat_completion_route(
    config: GatewayConfig,
    request: Mapping[str, Any],
) -> ResolvedRoute:
    model = request.get('model')
    if not isinstance(model, str) or not model.strip():
        raise GatewayInvalidRequestError('model is required', param='model')

    lane = resolve_lane(config, model.strip())
    validated_request = validate_chat_completion_request(request, lane)
    active_route = _route_by_id(config, lane.active_route, pointer_name='active_route')
    lkg_route = _route_by_id(config, lane.last_known_good, pointer_name='last_known_good')

    _validate_route_matches_lane(lane, active_route, pointer_name='active_route')
    _validate_route_matches_lane(lane, lkg_route, pointer_name='last_known_good')

    return ResolvedRoute(
        lane=lane,
        active_route=active_route,
        last_known_good_route=lkg_route,
        validated_request=validated_request,
    )


def resolve_lane(config: GatewayConfig, model: str) -> LaneConfig:
    if not is_auto_lane_id(model):
        raise GatewayUnsupportedModelError(
            f'provider model names are not direct routes in gateway v1: {model}',
        )

    lane = config.lanes.get(model)
    if lane is None:
        raise GatewayModelNotFoundError(f'auto lane not found: {model}')
    if lane.surface != Surface.OPENAI_CHAT_COMPLETIONS:
        raise GatewayCapabilityMismatchError(f'unsupported lane surface: {lane.surface.value}', param='model')
    return lane


def select_lkg_route_for_failure(
    resolved_route: ResolvedRoute, failure_class: FailureClass | str
) -> RouteArtifact | None:
    if is_lkg_eligible(resolved_route.active_route, failure_class):
        return resolved_route.last_known_good_route
    return None


def is_lkg_eligible(active_route: RouteArtifact, failure_class: FailureClass | str) -> bool:
    normalized_failure_class = _normalize_failure_class(failure_class)
    if normalized_failure_class in NEVER_LKG_FAILURE_CLASSES or is_byok_failure_class(normalized_failure_class):
        return False
    if normalized_failure_class in set(active_route.fallback_policy.never_fallback_on):
        return False
    return normalized_failure_class in set(active_route.fallback_policy.fallback_on)


def _route_by_id(config: GatewayConfig, route_artifact_id: str, *, pointer_name: str) -> RouteArtifact:
    route = config.route_artifacts.get(route_artifact_id)
    if route is None:
        raise GatewayInvalidRouteConfigError(f'{pointer_name} route not configured: {route_artifact_id}')
    return route


def _validate_route_matches_lane(lane: LaneConfig, route: RouteArtifact, *, pointer_name: str) -> None:
    prefix = f'{pointer_name} {route.route_artifact_id}'
    if route.lane_id != lane.lane_id:
        raise GatewayInvalidRouteConfigError(f'{prefix} lane_id mismatch: {route.lane_id}')
    if route.surface != lane.surface:
        raise GatewayInvalidRouteConfigError(f'{prefix} surface mismatch: {route.surface.value}')
    if route.capabilities != lane.capabilities:
        raise GatewayInvalidRouteConfigError(f'{prefix} capabilities mismatch')
    if route.credential_policy.mode != lane.credential_policy.mode:
        raise GatewayInvalidRouteConfigError(f'{prefix} credential mode mismatch: {route.credential_policy.mode.value}')


def _normalize_failure_class(failure_class: FailureClass | str) -> FailureClass:
    if isinstance(failure_class, FailureClass):
        return failure_class
    try:
        return FailureClass(failure_class)
    except ValueError as exc:
        raise GatewayInvalidRouteConfigError(f'unknown failure class: {failure_class}') from exc
