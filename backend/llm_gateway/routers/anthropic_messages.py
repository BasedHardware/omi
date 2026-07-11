"""Raw Anthropic Messages API pass-through for agentic chat."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Mapping
from typing import Any, cast

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from llm_gateway.gateway.auth import ServiceAuthDependency
from llm_gateway.gateway.config_loader import GatewayConfig
from llm_gateway.gateway.schemas import RouteArtifact
from llm_gateway.routers.dependencies import get_gateway_config

router = APIRouter()

ANTHROPIC_MESSAGES_BASE_URL = 'https://api.anthropic.com/v1'
AUTO_LANE_PREFIX = 'omi:auto:'
ANTHROPIC_BETA_HEADER = 'anthropic-beta'
ANTHROPIC_VERSION_HEADER = 'anthropic-version'
DEFAULT_ANTHROPIC_VERSION = '2023-06-01'
DEFAULT_ANTHROPIC_BETA = 'token-efficient-tools-2025-02-19'

_anthropic_http_client: httpx.AsyncClient | None = None


@router.post('/v1/messages', response_model=None)
async def create_anthropic_message(
    request: Request,
    caller: ServiceAuthDependency,
    config: GatewayConfig = Depends(get_gateway_config),
) -> JSONResponse | StreamingResponse:
    try:
        request_body = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='request body must be valid JSON') from exc
    if not isinstance(request_body, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='request body must be an object')

    body = cast(dict[str, Any], request_body)
    route = _resolve_lane_route(config, body.get('model'))
    body['model'] = route.primary.model
    body.update(route.provider_options)

    api_key = _resolve_anthropic_api_key(request)
    if not api_key:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={'error': {'message': 'anthropic provider is not configured', 'type': 'api_error'}},
        )

    headers = _anthropic_forward_headers(request, api_key=api_key)
    if body.get('stream') is True:
        return await _streaming_anthropic_messages_response(body, headers=headers)

    try:
        response = await _get_anthropic_http_client().post(
            f'{ANTHROPIC_MESSAGES_BASE_URL}/messages',
            json=body,
            headers=headers,
        )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail='anthropic request timed out') from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail='anthropic transport failure') from exc

    return JSONResponse(status_code=response.status_code, content=_response_json_or_error(response))


def _resolve_lane_route(config: GatewayConfig, model: object) -> RouteArtifact:
    if not isinstance(model, str) or not model.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='model is required')
    lane_id = model.strip()
    if not lane_id.startswith(AUTO_LANE_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'only auto lanes are supported on /v1/messages: {lane_id}',
        )
    lane = config.lanes.get(lane_id)
    if lane is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'auto lane not found: {lane_id}')
    route = config.route_artifacts.get(lane.active_route)
    if route is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f'active route missing for lane: {lane_id}',
        )
    provider_ref = route.primary
    if provider_ref.provider != 'anthropic':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'lane {lane_id} is not an anthropic messages lane',
        )
    return route


def _resolve_anthropic_api_key(request: Request) -> str | None:
    forwarded = request.headers.get('x-omi-byok-anthropic-key', '').strip()
    if forwarded:
        return forwarded
    configured = os.getenv('ANTHROPIC_API_KEY', '').strip()
    return configured or None


def _anthropic_forward_headers(request: Request, *, api_key: str) -> dict[str, str]:
    headers = {
        'x-api-key': api_key,
        ANTHROPIC_VERSION_HEADER: request.headers.get(ANTHROPIC_VERSION_HEADER, DEFAULT_ANTHROPIC_VERSION),
        'Content-Type': 'application/json',
    }
    beta = request.headers.get(ANTHROPIC_BETA_HEADER, DEFAULT_ANTHROPIC_BETA)
    if beta:
        headers[ANTHROPIC_BETA_HEADER] = beta
    return headers


async def _streaming_anthropic_messages_response(
    body: Mapping[str, Any],
    *,
    headers: Mapping[str, str],
) -> JSONResponse | StreamingResponse:
    """Open the upstream stream before committing HTTP status.

    Upstream 4xx/5xx must be returned as JSON with the real status so gateway
    clients can fall back. Yielding the error body under an already-committed
    HTTP 200 breaks transport-failure detection.
    """
    try:
        stream_cm = _get_anthropic_http_client().stream(
            'POST',
            f'{ANTHROPIC_MESSAGES_BASE_URL}/messages',
            json=dict(body),
            headers=dict(headers),
        )
        response = await stream_cm.__aenter__()
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail='anthropic request timed out') from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail='anthropic transport failure') from exc

    if response.status_code >= 400:
        try:
            error_bytes = await response.aread()
        finally:
            await stream_cm.__aexit__(None, None, None)
        return JSONResponse(status_code=response.status_code, content=_bytes_json_or_error(error_bytes))

    return StreamingResponse(
        _iter_open_anthropic_stream(stream_cm, response),
        media_type='text/event-stream',
    )


async def _iter_open_anthropic_stream(stream_cm: Any, response: Any) -> AsyncIterator[bytes]:
    try:
        async for chunk in response.aiter_bytes():
            yield chunk
    except httpx.TimeoutException:
        yield b'event: error\ndata: {"type":"error","error":{"type":"timeout_error"}}\n\n'
    except httpx.HTTPError:
        yield b'event: error\ndata: {"type":"error","error":{"type":"api_error"}}\n\n'
    finally:
        await stream_cm.__aexit__(None, None, None)


def _response_json_or_error(response: httpx.Response) -> object:
    try:
        return response.json()
    except ValueError:
        return {'error': {'message': 'invalid anthropic response', 'type': 'api_error'}}


def _bytes_json_or_error(body: bytes) -> object:
    if not body:
        return {'error': {'message': 'anthropic request failed', 'type': 'api_error'}}
    try:
        return json.loads(body)
    except ValueError:
        return {'error': {'message': 'invalid anthropic response', 'type': 'api_error'}}


def _get_anthropic_http_client() -> httpx.AsyncClient:
    global _anthropic_http_client
    if _anthropic_http_client is None:
        _anthropic_http_client = httpx.AsyncClient(timeout=120.0)
    return _anthropic_http_client


async def close_anthropic_messages_client() -> None:
    global _anthropic_http_client
    if _anthropic_http_client is not None:
        await _anthropic_http_client.aclose()
        _anthropic_http_client = None
