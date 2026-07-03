from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
import httpx
import os
from fastapi.responses import JSONResponse, StreamingResponse

from llm_gateway.gateway.auth import ServiceAuthDependency
from llm_gateway.gateway.config_loader import GatewayConfig
from llm_gateway.gateway.credentials import build_omi_managed_credential_context
from llm_gateway.gateway.errors import (
    GatewayError,
    GatewayErrorCode,
    GatewayInvalidRequestError,
)
from llm_gateway.gateway.executor import (
    ProviderRegistry,
    execute_chat_completion,
    provider_request_for,
    selected_serving_route,
    selected_serving_route_artifact_id,
)
from llm_gateway.gateway.metrics import observe_error, observe_success, time_request
from llm_gateway.gateway.providers import ProviderFailure
from llm_gateway.gateway.resolver import is_lkg_eligible, resolve_chat_completion_route
from llm_gateway.routers.dependencies import get_gateway_config, get_provider_registry

router = APIRouter()
_image_generation_client: httpx.AsyncClient | None = None


@router.post('/v1/chat/completions')
async def create_chat_completion(
    request: Request,
    caller: ServiceAuthDependency,
    config: GatewayConfig = Depends(get_gateway_config),
    provider_registry: ProviderRegistry = Depends(get_provider_registry),
):
    started_at = time_request()
    resolved_route = None
    try:
        request_body = await _request_json(request)
        resolved_route = resolve_chat_completion_route(config, request_body)
        credentials = build_omi_managed_credential_context(caller)
        if resolved_route.validated_request.forwarded_params.get('stream') is True:
            return _streaming_response(resolved_route, credentials, provider_registry)
        result = await execute_chat_completion(resolved_route, credentials, provider_registry)
        _safe_observe(lambda: observe_success(started_at, result))
        return JSONResponse(content=result.response)
    except GatewayError as exc:
        if resolved_route is not None:
            _safe_observe(
                lambda: observe_error(
                    started_at,
                    lane_id=resolved_route.lane.lane_id,
                    route_artifact_id=selected_serving_route_artifact_id(resolved_route),
                    error=exc,
                )
            )
        return _error_response(exc)


def _safe_observe(fn: Any) -> None:
    """Emit metrics without risking request-handling failures."""
    try:
        fn()
    except Exception:
        pass


async def _request_json(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except ValueError as exc:
        raise GatewayInvalidRequestError('request body must be valid JSON') from exc
    if not isinstance(body, dict):
        raise GatewayInvalidRequestError('request body must be an object')
    return body


def _error_response(exc: GatewayError) -> JSONResponse:
    return JSONResponse(
        status_code=_status_code_for_error(exc),
        content={
            'error': {
                'message': exc.message,
                'type': _error_type_for_code(exc.code),
                'param': exc.param,
                'code': exc.code.value,
            }
        },
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


def _streaming_response(resolved_route, credentials, provider_registry: ProviderRegistry) -> StreamingResponse:
    route = selected_serving_route(resolved_route)

    async def event_stream():
        last_error: ProviderFailure | None = None
        for provider_ref in [route.primary, *route.fallbacks]:
            provider = provider_registry.provider_for(provider_ref.provider)
            stream_chat_completion = getattr(provider, 'stream_chat_completion', None)
            if stream_chat_completion is None:
                continue
            try:
                async for chunk in stream_chat_completion(
                    provider_request_for(resolved_route, provider_ref),
                    provider_ref=provider_ref,
                    credentials=credentials,
                    timeout_ms=route.timeouts.request_ms,
                ):
                    yield chunk
                return
            except ProviderFailure as exc:
                last_error = exc
                if not is_lkg_eligible(route, exc.failure_class):
                    raise
        if last_error is not None:
            raise last_error
        raise GatewayInvalidRequestError('streaming provider adapter is not configured', param='stream')

    return StreamingResponse(event_stream(), media_type='text/event-stream')
