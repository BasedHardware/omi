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
from llm_gateway.gateway.executor import ProviderRegistry, execute_chat_completion
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
    try:
        request_body = await _request_json(request)
        resolved_route = resolve_chat_completion_route(config, request_body)
        credentials = build_omi_managed_credential_context(caller)
        result = await execute_chat_completion(resolved_route, credentials, provider_registry)
        return JSONResponse(content=result.response)
    except GatewayError as exc:
        return _error_response(exc)


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
                'type': exc.code.value,
                'param': exc.param,
                'code': exc.code.value,
            }
        },
    )


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
