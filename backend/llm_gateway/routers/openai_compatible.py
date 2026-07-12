from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any, cast

from fastapi import APIRouter, Depends, Request
import httpx
import os
from fastapi.responses import JSONResponse, StreamingResponse

from llm_gateway.gateway.auth import ServiceAuthDependency
from llm_gateway.gateway.config_loader import GatewayConfig
from llm_gateway.gateway.credentials import (
    CredentialContext,
    build_byok_credential_context,
    build_omi_managed_credential_context,
    parse_forwarded_byok_headers,
)
from llm_gateway.gateway.errors import (
    GatewayError,
    GatewayErrorCode,
    GatewayInvalidRouteConfigError,
    GatewayInvalidRequestError,
)
from llm_gateway.gateway.executor import (
    ProviderRegistry,
    execute_chat_completion,
    _map_provider_failure,  # type: ignore[reportPrivateUsage]  # shared gateway failure mapper
    provider_request_for,
    selected_serving_route,
    selected_serving_route_artifact_id,
)
from llm_gateway.gateway.metrics import (
    observe_error,
    observe_request_rejection,
    observe_route_result,
    observe_success,
    report_observation_failure,
    time_request,
)
from llm_gateway.gateway.providers import ProviderFailure
from llm_gateway.gateway.request_context import request_id_for
from llm_gateway.gateway.resolver import ResolvedRoute, is_lkg_eligible, resolve_chat_completion_route
from llm_gateway.gateway.schemas import RouteArtifact
from llm_gateway.gateway.sse import SSEEventDecoder
from llm_gateway.routers.dependencies import get_gateway_config, get_provider_registry

router = APIRouter()
_image_generation_client: httpx.AsyncClient | None = None


@router.post('/v1/chat/completions', response_model=None)
async def create_chat_completion(
    request: Request,
    caller: ServiceAuthDependency,
    config: GatewayConfig = Depends(get_gateway_config),
    provider_registry: ProviderRegistry = Depends(get_provider_registry),
) -> JSONResponse | StreamingResponse:
    started_at = time_request()
    resolved_route = None
    credential_source = 'unknown'
    is_streaming = False
    request_id = request_id_for(request)
    try:
        request_body = await _request_json(request)
        resolved_route = resolve_chat_completion_route(config, request_body)
        credentials = _resolve_credentials(request, caller)
        credential_source = credentials.source.value
        is_streaming = resolved_route.validated_request.forwarded_params.get('stream') is True
        if is_streaming:
            return await _streaming_response(
                resolved_route,
                credentials,
                provider_registry,
                started_at=started_at,
                request_id=request_id,
            )
        result = await execute_chat_completion(resolved_route, credentials, provider_registry)
        _safe_observe(
            lambda: observe_success(
                started_at,
                result,
                credential_source=credential_source,
                request_id=request_id,
            ),
            request_id=request_id,
            api_surface='openai_chat_completions',
        )
        return JSONResponse(content=result.response)
    except asyncio.CancelledError:
        if resolved_route is not None:
            route = selected_serving_route(resolved_route)
            _safe_observe(
                lambda: observe_route_result(
                    started_at,
                    lane_id=resolved_route.lane.lane_id,
                    route_artifact_id=route.route_artifact_id,
                    provider='none',
                    model='none',
                    credential_source=credential_source,
                    used_lkg=route is resolved_route.last_known_good_route,
                    fallback_used=route is resolved_route.last_known_good_route,
                    fallback_reason=None,
                    outcome='cancelled',
                    error_class='client_cancelled',
                    request_id=request_id,
                    api_surface='openai_chat_completions',
                    streaming=is_streaming,
                    phase='before_output',
                ),
                request_id=request_id,
                api_surface='openai_chat_completions',
            )
        raise
    except GatewayError as exc:
        if resolved_route is not None:
            _safe_observe(
                lambda: observe_error(
                    started_at,
                    lane_id=resolved_route.lane.lane_id,
                    route_artifact_id=selected_serving_route_artifact_id(resolved_route),
                    error=exc,
                    credential_source=credential_source,
                    request_id=request_id,
                    streaming=is_streaming,
                ),
                request_id=request_id,
                api_surface='openai_chat_completions',
            )
        else:
            _safe_observe(
                lambda: observe_request_rejection(
                    api_surface='openai_chat_completions',
                    error_class=exc.code.value,
                    request_id=request_id,
                ),
                request_id=request_id,
                api_surface='openai_chat_completions',
            )
        return _error_response(exc)
    except Exception:
        if resolved_route is not None:
            route = selected_serving_route(resolved_route)
            _safe_observe(
                lambda: observe_route_result(
                    started_at,
                    lane_id=resolved_route.lane.lane_id,
                    route_artifact_id=route.route_artifact_id,
                    provider='none',
                    model='none',
                    credential_source=credential_source,
                    used_lkg=route is resolved_route.last_known_good_route,
                    fallback_used=route is resolved_route.last_known_good_route,
                    fallback_reason=None,
                    outcome='error',
                    error_class='unexpected_internal',
                    request_id=request_id,
                    api_surface='openai_chat_completions',
                    streaming=is_streaming,
                    phase='before_output',
                ),
                request_id=request_id,
                api_surface='openai_chat_completions',
            )
        else:
            _safe_observe(
                lambda: observe_request_rejection(
                    api_surface='openai_chat_completions',
                    error_class='unexpected_internal',
                    request_id=request_id,
                ),
                request_id=request_id,
                api_surface='openai_chat_completions',
            )
        raise


def _safe_observe(fn: Callable[[], None], *, request_id: str, api_surface: str) -> None:
    """Emit metrics without risking request-handling failures."""
    try:
        fn()
    except Exception:
        report_observation_failure(api_surface=api_surface, request_id=request_id)


async def _request_json(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except ValueError as exc:
        raise GatewayInvalidRequestError('request body must be valid JSON') from exc
    if not isinstance(body, dict):
        raise GatewayInvalidRequestError('request body must be an object')
    return cast(dict[str, Any], body)


def _resolve_credentials(request: Request, caller: ServiceAuthDependency) -> CredentialContext:
    forwarded = parse_forwarded_byok_headers(request.headers)
    if forwarded:
        return build_byok_credential_context(caller, forwarded)
    return build_omi_managed_credential_context(caller)


def _error_response(exc: GatewayError) -> JSONResponse:
    content: dict[str, object] = {
        'error': {
            'message': exc.message,
            'type': _error_type_for_code(exc.code),
            'param': exc.param,
            'code': exc.code.value,
        }
    }
    return JSONResponse(
        status_code=_status_code_for_error(exc),
        content=content,
    )


def _error_type_for_code(code: GatewayErrorCode) -> str:
    """Map an internal error code to an OpenAI API error category.

    OpenAI distinguishes ``type`` (a broad error category) from ``code`` (the
    specific identifier). Without this distinction clients that categorize
    errors by ``type`` cannot classify them correctly.
    """
    if code == GatewayErrorCode.CREDENTIAL_FAILURE:
        return 'authentication_error'
    if code in {
        GatewayErrorCode.INVALID_REQUEST,
        GatewayErrorCode.INVALID_ROUTE_CONFIG,
        GatewayErrorCode.UNSUPPORTED_MODEL,
        GatewayErrorCode.CAPABILITY_NOT_SUPPORTED,
    }:
        return 'invalid_request_error'
    return 'api_error'


def _status_code_for_error(exc: GatewayError) -> int:
    if exc.code == GatewayErrorCode.MODEL_NOT_FOUND:
        return 404
    if exc.code in {
        GatewayErrorCode.INVALID_REQUEST,
        GatewayErrorCode.UNSUPPORTED_MODEL,
        GatewayErrorCode.CAPABILITY_NOT_SUPPORTED,
    }:
        return 400
    if exc.code == GatewayErrorCode.CREDENTIAL_FAILURE:
        return 401
    if exc.code == GatewayErrorCode.INVALID_ROUTE_CONFIG:
        return 503
    if exc.code == GatewayErrorCode.PROVIDER_FAILURE:
        return 502
    return 500


@router.post('/v1/images/generations')
async def create_image_generation(request: Request, caller: ServiceAuthDependency):
    request_body = await _request_json(request)
    api_key = os.getenv('OPENAI_API_KEY', '').strip()
    if not api_key:
        return JSONResponse(
            status_code=503,
            content={'error': {'message': 'provider request failed: invalid_config', 'type': 'api_error'}},
        )
    try:
        response = await _get_image_generation_client().post(
            'https://api.openai.com/v1/images/generations',
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            json=request_body,
        )
        return JSONResponse(status_code=response.status_code, content=response.json())
    except (httpx.HTTPError, ValueError):
        return JSONResponse(
            status_code=502,
            content={'error': {'message': 'provider request failed', 'type': 'api_error'}},
        )


def _get_image_generation_client() -> httpx.AsyncClient:
    global _image_generation_client
    if _image_generation_client is None:
        _image_generation_client = httpx.AsyncClient(timeout=120.0)
    return _image_generation_client


async def close_image_generation_client() -> None:
    global _image_generation_client
    if _image_generation_client is not None:
        await _image_generation_client.aclose()
        _image_generation_client = None


async def _streaming_response(
    resolved_route: ResolvedRoute,
    credentials: CredentialContext,
    provider_registry: ProviderRegistry,
    *,
    started_at: float,
    request_id: str,
) -> StreamingResponse:
    route = selected_serving_route(resolved_route)

    prepared = await _prepared_streaming_iterator(resolved_route, credentials, provider_registry, route)
    async_iterator = _stream_with_terminal_metrics(
        prepared,
        resolved_route=resolved_route,
        credentials=credentials,
        route=route,
        started_at=started_at,
        request_id=request_id,
    )

    return StreamingResponse(async_iterator, media_type='text/event-stream')


@dataclass(frozen=True)
class _PreparedStream:
    first_chunk: bytes | None
    stream: AsyncIterator[bytes]
    provider: str
    model: str
    fallback_used: bool
    fallback_reason: str | None


async def _prepared_streaming_iterator(
    resolved_route: ResolvedRoute,
    credentials: CredentialContext,
    provider_registry: ProviderRegistry,
    route: RouteArtifact,
) -> _PreparedStream:
    last_error: GatewayError | None = None
    first_failure: str | None = None
    for index, provider_ref in enumerate([route.primary, *route.fallbacks]):
        provider = provider_registry.provider_for(provider_ref.provider)
        if provider is None:
            raise GatewayInvalidRouteConfigError(f'provider is not supported for this route: {provider_ref.provider}')
        stream_chat_completion = getattr(provider, 'stream_chat_completion', None)
        if stream_chat_completion is None:
            continue
        stream = stream_chat_completion(
            provider_request_for(resolved_route, provider_ref),
            provider_ref=provider_ref,
            credentials=credentials,
            timeout_ms=route.timeouts.request_ms,
        )
        try:
            while True:
                first_chunk = await anext(stream)
                if first_chunk:
                    break
        except StopAsyncIteration:
            return _PreparedStream(
                first_chunk=None,
                stream=stream,
                provider=provider_ref.provider,
                model=provider_ref.model,
                fallback_used=index > 0 or route is resolved_route.last_known_good_route,
                fallback_reason=first_failure,
            )
        except ProviderFailure as exc:
            last_error = _map_provider_failure(exc, credentials)
            first_failure = first_failure or exc.failure_class.value
            if not is_lkg_eligible(route, exc.failure_class):
                raise last_error
            continue
        return _PreparedStream(
            first_chunk=first_chunk,
            stream=stream,
            provider=provider_ref.provider,
            model=provider_ref.model,
            fallback_used=index > 0 or route is resolved_route.last_known_good_route,
            fallback_reason=first_failure,
        )
    if last_error is not None:
        raise last_error
    raise GatewayInvalidRequestError('streaming provider adapter is not configured', param='stream')


async def _stream_with_terminal_metrics(
    prepared: _PreparedStream,
    *,
    resolved_route: ResolvedRoute,
    credentials: CredentialContext,
    route: RouteArtifact,
    started_at: float,
    request_id: str,
) -> AsyncIterator[bytes]:
    terminal_observed = False
    saw_output = prepared.first_chunk is not None
    terminal_marker_seen = False
    decoder = SSEEventDecoder()
    ttfb_seconds = time_request() - started_at if saw_output else None

    def observe_terminal(*, outcome: str, error_class: str, phase: str) -> None:
        nonlocal terminal_observed
        if terminal_observed:
            return
        terminal_observed = True
        _safe_observe(
            lambda: observe_route_result(
                started_at,
                lane_id=resolved_route.lane.lane_id,
                route_artifact_id=route.route_artifact_id,
                provider=prepared.provider,
                model=prepared.model,
                credential_source=credentials.source.value,
                used_lkg=route is resolved_route.last_known_good_route,
                fallback_used=prepared.fallback_used,
                fallback_reason=prepared.fallback_reason,
                outcome=outcome,
                error_class=error_class,
                request_id=request_id,
                api_surface='openai_chat_completions',
                streaming=True,
                phase=phase,
                ttfb_seconds=ttfb_seconds,
            ),
            request_id=request_id,
            api_surface='openai_chat_completions',
        )

    def inspect_chunk(chunk: bytes) -> None:
        nonlocal terminal_marker_seen
        for event in decoder.feed(chunk):
            if event.data.strip() == '[DONE]':
                terminal_marker_seen = True
                observe_terminal(outcome='success', error_class='none', phase='terminal_marker')

    if prepared.first_chunk is None:
        observe_terminal(outcome='error', error_class='empty_stream_before_output', phase='before_output')
        return

    try:
        inspect_chunk(prepared.first_chunk)
        yield prepared.first_chunk
        async for chunk in prepared.stream:
            if chunk:
                inspect_chunk(chunk)
                yield chunk
    except asyncio.CancelledError:
        observe_terminal(
            outcome='cancelled',
            error_class='client_cancelled',
            phase='midstream' if saw_output else 'before_output',
        )
        raise
    except ProviderFailure as exc:
        observe_terminal(
            outcome='error',
            error_class=f'{exc.failure_class.value}_midstream',
            phase='midstream',
        )
        raise
    except ValueError:
        observe_terminal(outcome='error', error_class='invalid_sse_frame', phase='midstream')
        raise
    except Exception:
        observe_terminal(outcome='error', error_class='transport_midstream', phase='midstream')
        raise
    else:
        if not terminal_marker_seen:
            observe_terminal(outcome='error', error_class='eof_before_terminal_marker', phase='midstream')
    finally:
        if not terminal_observed:
            observe_terminal(
                outcome='cancelled',
                error_class='consumer_abandoned_stream',
                phase='midstream' if saw_output else 'before_output',
            )
