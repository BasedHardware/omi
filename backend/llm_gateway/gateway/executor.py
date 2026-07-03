from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from llm_gateway.gateway.credentials import CredentialContext, is_byok_failure_class
from llm_gateway.gateway.errors import (
    GatewayCapabilityMismatchError,
    GatewayCredentialFailureError,
    GatewayError,
    GatewayInvalidRouteConfigError,
    GatewayProviderFailureError,
)
from llm_gateway.gateway.providers import (
    ChatCompletionProvider,
    EXPOSE_PROVIDER_ERROR_DETAILS_ENV_VAR,
    GENERIC_PROVIDER_FAILURE_MESSAGE,
    ProviderFailure,
)
from llm_gateway.gateway.resolver import ResolvedRoute, is_lkg_eligible, select_lkg_route_for_failure
from llm_gateway.gateway.schemas import CredentialMode, FailureClass, ProviderRef, RolloutStage, RouteArtifact
from llm_gateway.gateway.validator import ValidatedChatCompletionRequest
from utils.log_sanitizer import sanitize

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExecutorResult:
    response: dict[str, Any]
    lane_id: str
    selected_route_artifact_id: str
    selected_provider: str
    selected_model: str
    fallback_used: bool
    fallback_reason: FailureClass | None
    used_lkg: bool


class ProviderRegistry:
    def __init__(self, providers: Mapping[str, ChatCompletionProvider] | None = None) -> None:
        self._providers = {provider.strip().lower(): client for provider, client in (providers or {}).items()}

    def provider_for(self, provider: str) -> ChatCompletionProvider | None:
        return self._providers.get(provider.strip().lower())

    async def aclose(self) -> None:
        cleanup_tasks = [
            _close_provider(provider_name, provider)
            for provider_name, provider in self._providers.items()
            if getattr(provider, 'aclose', None) is not None
        ]
        if cleanup_tasks:
            await asyncio.gather(*cleanup_tasks)


async def _close_provider(provider_name: str, provider: ChatCompletionProvider) -> None:
    close = getattr(provider, 'aclose', None)
    if close is None:
        return
    try:
        await close()
    except Exception:
        logger.exception('LLM gateway provider cleanup failed: %s', provider_name)


async def execute_chat_completion(
    resolved_route: ResolvedRoute,
    credential_context: CredentialContext,
    provider_registry: ProviderRegistry,
) -> ExecutorResult:
    serving_route = _select_serving_route(resolved_route)
    serving_is_lkg = serving_route is resolved_route.last_known_good_route
    _validate_credential_mode(serving_route, credential_context)

    first_failure: FailureClass | None = None
    last_error: GatewayError | None = None
    try:
        return await _execute_route(
            resolved_route,
            serving_route,
            credential_context,
            provider_registry,
            is_lkg=serving_is_lkg,
            fallback_reason=None,
        )
    except GatewayError as exc:
        first_failure = exc.failure_class
        last_error = exc

    # When the active route is in shadow/disabled rollout the LKG is already
    # the serving route — there is no separate LKG fallback to try.
    if serving_is_lkg:
        if last_error is not None:
            raise last_error
        raise GatewayProviderFailureError(
            'provider request failed',
            failure_class=FailureClass.INVALID_CONFIG,
        )

    if first_failure is not None and select_lkg_route_for_failure(resolved_route, first_failure) is not None:
        try:
            return await _execute_route(
                resolved_route,
                resolved_route.last_known_good_route,
                credential_context,
                provider_registry,
                is_lkg=True,
                fallback_reason=first_failure,
            )
        except GatewayError as exc:
            last_error = exc

    if last_error is not None:
        raise last_error
    raise GatewayProviderFailureError(
        'provider request failed',
        failure_class=FailureClass.INVALID_CONFIG,
    )


def _select_serving_route(resolved_route: ResolvedRoute) -> RouteArtifact:
    """Return the route that should receive live traffic.

    When the active route is in shadow or disabled rollout, traffic falls
    back to the last-known-good route until the active route is promoted.

    For canary (partial) rollouts the active route only receives the
    configured percentage of traffic via deterministic per-request
    sampling; the remainder is served by the last-known-good route.
    """
    if _is_route_eligible_to_serve(resolved_route.active_route, resolved_route.validated_request):
        return resolved_route.active_route
    return resolved_route.last_known_good_route


def selected_serving_route_artifact_id(resolved_route: ResolvedRoute) -> str:
    return _select_serving_route(resolved_route).route_artifact_id


def selected_serving_route(resolved_route: ResolvedRoute) -> RouteArtifact:
    return _select_serving_route(resolved_route)


def provider_request_for(resolved_route: ResolvedRoute, provider_ref: ProviderRef) -> dict[str, Any]:
    return _provider_request(resolved_route, provider_ref)


def _is_route_eligible_to_serve(route: RouteArtifact, validated_request: ValidatedChatCompletionRequest) -> bool:
    """Whether a route should receive live traffic based on rollout stage and percent."""
    if route.rollout.stage in (RolloutStage.SHADOW, RolloutStage.DISABLED):
        return False
    if route.rollout.stage == RolloutStage.CANARY and route.rollout.percent < 100.0:
        return _canary_sample(route, validated_request)
    return route.rollout.percent > 0


def _canary_sample(route: RouteArtifact, validated_request: ValidatedChatCompletionRequest) -> bool:
    """Deterministically decide whether a single request is served by a canary route.

    A stable hash of the request messages (plus the route artifact id so
    different canary routes in the same lane diverge) is mapped into the
    [0, 100) range and compared against the configured rollout percentage.
    This keeps the same request consistently on the same lane across
    retries, while distributing traffic proportionally over many requests.
    """
    payload = json.dumps(
        {
            'route_artifact_id': route.route_artifact_id,
            'messages': list(validated_request.messages),
        },
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=True,
    )
    digest = hashlib.sha256(payload.encode('utf-8')).hexdigest()
    bucket = int(digest[:8], 16) % 10000 / 100.0
    return bucket < route.rollout.percent


RETRYABLE_PROVIDER_FAILURE_CLASSES = frozenset(
    {
        FailureClass.TIMEOUT_BEFORE_OUTPUT,
        FailureClass.PROVIDER_429_OMI_PAID,
        FailureClass.PROVIDER_5XX_OMI_PAID,
    }
)


async def _execute_route(
    resolved_route: ResolvedRoute,
    route: RouteArtifact,
    credential_context: CredentialContext,
    provider_registry: ProviderRegistry,
    *,
    is_lkg: bool,
    fallback_reason: FailureClass | None,
) -> ExecutorResult:
    refs = [route.primary, *route.fallbacks]
    last_error: GatewayError | None = None
    current_fallback_reason = fallback_reason

    for index, provider_ref in enumerate(refs):
        provider = provider_registry.provider_for(provider_ref.provider)
        if provider is None:
            error = _unsupported_provider_error(provider_ref, credential_context)
        elif route.credential_policy.mode == CredentialMode.BYOK and not credential_context.has_provider_key(
            provider_ref.provider
        ):
            error = GatewayCredentialFailureError(
                f'BYOK key is required for provider {provider_ref.provider}',
                failure_class=FailureClass.MISSING_BYOK_KEY,
                param='credentials',
            )
        else:
            response, error = await _attempt_provider(
                resolved_route,
                route,
                provider,
                provider_ref,
                credential_context,
            )
            if error is None:
                return _executor_result(
                    response,  # type: ignore[arg-type]
                    resolved_route=resolved_route,
                    route=route,
                    provider_ref=provider_ref,
                    fallback_used=index > 0 or is_lkg,
                    fallback_reason=current_fallback_reason,
                    used_lkg=is_lkg,
                )

        last_error = error
        if index == len(refs) - 1 or not _can_try_next_provider(route, error.failure_class):
            raise error
        current_fallback_reason = error.failure_class

    if last_error is not None:
        raise last_error
    raise GatewayInvalidRouteConfigError(f'route {route.route_artifact_id} has no provider refs')


async def _attempt_provider(
    resolved_route: ResolvedRoute,
    route: RouteArtifact,
    provider: ChatCompletionProvider,
    provider_ref: ProviderRef,
    credential_context: CredentialContext,
) -> tuple[Mapping[str, Any] | None, GatewayError | None]:
    """Try a single provider up to ``route.retry.max_attempts`` times.

    Returns ``(response, None)`` on success, or ``(None, error)`` if all
    attempts fail.
    """
    max_attempts = max(route.retry.max_attempts, 1)
    error: GatewayError | None = None
    for _attempt in range(max_attempts):
        try:
            response = await provider.create_chat_completion(
                _provider_request(resolved_route, provider_ref, route=route),
                provider_ref=provider_ref,
                credentials=credential_context,
                timeout_ms=route.timeouts.request_ms,
            )
            return response, None
        except ProviderFailure as exc:
            error = _map_provider_failure(exc, credential_context)
            if error.failure_class not in RETRYABLE_PROVIDER_FAILURE_CLASSES:
                return None, error
    return None, error


def _provider_request(
    resolved_route: ResolvedRoute,
    provider_ref: ProviderRef,
    *,
    route: RouteArtifact | None = None,
) -> dict[str, Any]:
    route = route or selected_serving_route(resolved_route)
    provider_request = {
        'model': provider_ref.model,
        'messages': list(resolved_route.validated_request.messages),
        'stream': False,
    }
    _apply_provider_options(provider_request, route.provider_options)
    if resolved_route.validated_request.response_format is not None:
        provider_request['response_format'] = dict(resolved_route.validated_request.response_format)
    provider_request.update(dict(resolved_route.validated_request.forwarded_params))
    return provider_request


def _apply_provider_options(provider_request: dict[str, Any], provider_options: Mapping[str, Any]) -> None:
    extra_body = provider_options.get('extra_body')
    if isinstance(extra_body, Mapping):
        provider_request.update(dict(extra_body))
    for key, value in provider_options.items():
        if key != 'extra_body':
            provider_request[key] = value


def _executor_result(
    provider_response: Mapping[str, Any],
    *,
    resolved_route: ResolvedRoute,
    route: RouteArtifact,
    provider_ref: ProviderRef,
    fallback_used: bool,
    fallback_reason: FailureClass | None,
    used_lkg: bool,
) -> ExecutorResult:
    response = dict(provider_response)
    response['model'] = resolved_route.validated_request.model
    return ExecutorResult(
        response=response,
        lane_id=resolved_route.lane.lane_id,
        selected_route_artifact_id=route.route_artifact_id,
        selected_provider=provider_ref.provider,
        selected_model=provider_ref.model,
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
        used_lkg=used_lkg,
    )


def _validate_credential_mode(route: RouteArtifact, credential_context: CredentialContext) -> None:
    if route.credential_policy.mode != credential_context.mode:
        raise GatewayInvalidRouteConfigError(
            f'route {route.route_artifact_id} credential mode does not match request context'
        )


def _unsupported_provider_error(
    provider_ref: ProviderRef,
    credential_context: CredentialContext,
) -> GatewayCredentialFailureError | GatewayInvalidRouteConfigError:
    if credential_context.mode == CredentialMode.BYOK:
        return GatewayCredentialFailureError(
            f'BYOK provider is not supported for this route: {provider_ref.provider}',
            failure_class=FailureClass.BYOK_UNSUPPORTED_PROVIDER,
            param='provider',
        )
    return GatewayInvalidRouteConfigError(f'provider is not supported for this route: {provider_ref.provider}')


def _map_provider_failure(exc: ProviderFailure, credential_context: CredentialContext) -> GatewayError:
    failure_class = exc.failure_class
    if failure_class == FailureClass.INVALID_CONFIG:
        return GatewayInvalidRouteConfigError(_safe_failure_message(failure_class, exc.safe_message), param='provider')
    if failure_class == FailureClass.CAPABILITY_MISMATCH:
        return GatewayCapabilityMismatchError(_safe_failure_message(failure_class, exc.safe_message), param='provider')
    if credential_context.mode == CredentialMode.BYOK or is_byok_failure_class(failure_class):
        return GatewayCredentialFailureError(
            _safe_failure_message(failure_class, exc.safe_message),
            failure_class=failure_class,
            param='provider',
        )
    return GatewayProviderFailureError(
        _safe_failure_message(failure_class, exc.safe_message),
        failure_class=failure_class,
        param='provider',
    )


def _safe_failure_message(failure_class: FailureClass, provider_message: str | None = None) -> str:
    if _expose_provider_error_details() and provider_message and provider_message != GENERIC_PROVIDER_FAILURE_MESSAGE:
        return sanitize(provider_message)
    return f'provider request failed: {failure_class.value}'


def _expose_provider_error_details() -> bool:
    return os.getenv(EXPOSE_PROVIDER_ERROR_DETAILS_ENV_VAR, '').strip().lower() == 'true'


def _can_try_next_provider(route: RouteArtifact, failure_class: FailureClass | None) -> bool:
    if failure_class is None:
        return False
    return is_lkg_eligible(route, failure_class)
