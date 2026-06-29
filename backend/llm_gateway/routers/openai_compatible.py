from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from llm_gateway.gateway.auth import ServiceAuthDependency
from llm_gateway.gateway.config_loader import GatewayConfig
from llm_gateway.gateway.credentials import build_omi_managed_credential_context
from llm_gateway.gateway.errors import (
    GatewayError,
    GatewayErrorCode,
    GatewayInvalidRequestError,
)
from llm_gateway.gateway.executor import ProviderRegistry, execute_chat_completion, selected_serving_route_artifact_id
from llm_gateway.gateway.metrics import observe_error, observe_success, time_request
from llm_gateway.gateway.resolver import resolve_chat_completion_route
from llm_gateway.routers.dependencies import get_gateway_config, get_provider_registry

router = APIRouter()


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
