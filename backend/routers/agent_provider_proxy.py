import hmac
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from database._client import get_firestore_client
from utils.executors import db_executor, run_blocking
from utils.llm.gateway_client import get_llm_gateway_base_url, get_llm_gateway_service_token, llm_gateway_headers
from utils.subscription import is_trial_paywalled

router = APIRouter()

_MAX_BODY_BYTES = 5 * 1024 * 1024
_CHAT_AGENT_LANE = "omi:auto:chat-agent"
_ANTHROPIC_VERSION = "anthropic-version"
_ANTHROPIC_BETA = "anthropic-beta"


def _find_agent_uid(token: str) -> str | None:
    if not token or len(token) > 512:
        return None
    query = get_firestore_client().collection("users").where("agentVm.authToken", "==", token).limit(2)
    matches = []
    for document in query.stream():
        data = document.to_dict() or {}
        agent_vm = data.get("agentVm") if isinstance(data, dict) else None
        stored_token = agent_vm.get("authToken") if isinstance(agent_vm, dict) else None
        if isinstance(stored_token, str) and hmac.compare_digest(stored_token, token):
            matches.append(document.id)
    return matches[0] if len(matches) == 1 else None


async def _authorize_agent(request: Request) -> str:
    token = request.headers.get("x-api-key", "").strip()
    try:
        uid = await run_blocking(db_executor, _find_agent_uid, token)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Agent authorization is unavailable") from exc
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid agent authentication")
    if await run_blocking(db_executor, is_trial_paywalled, uid, "desktop"):
        raise HTTPException(status_code=402, detail="trial_expired")
    return uid


def _gateway_request_headers(request: Request, uid: str) -> dict[str, str]:
    if not get_llm_gateway_service_token():
        raise HTTPException(status_code=503, detail="LLM gateway is not configured")
    headers = llm_gateway_headers(feature="chat_agent")
    headers["X-Omi-User-Uid"] = uid
    headers[_ANTHROPIC_VERSION] = request.headers.get(_ANTHROPIC_VERSION, "2023-06-01")
    beta = request.headers.get(_ANTHROPIC_BETA)
    if beta:
        headers[_ANTHROPIC_BETA] = beta
    return headers


async def _read_limited_body(request: Request) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_length = int(content_length)
            if declared_length < 0:
                raise HTTPException(status_code=400, detail="Invalid Content-Length")
            if declared_length > _MAX_BODY_BYTES:
                raise HTTPException(status_code=413, detail="Request body is too large")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid Content-Length") from exc
    chunks = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > _MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Request body is too large")
        chunks.append(chunk)
    return b"".join(chunks)


async def _stream_response(client: httpx.AsyncClient, context: Any, upstream: httpx.Response) -> AsyncIterator[bytes]:
    try:
        async for chunk in upstream.aiter_raw():
            yield chunk
    finally:
        await context.__aexit__(None, None, None)
        await client.aclose()


@router.post("/v1/agent/anthropic/v1/messages")
async def agent_anthropic_messages(request: Request) -> Response:
    uid = await _authorize_agent(request)
    body = await _read_limited_body(request)
    try:
        payload = json.loads(body)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Request body must be a JSON object")
    payload["model"] = _CHAT_AGENT_LANE
    body = json.dumps(payload, separators=(",", ":")).encode()
    headers = _gateway_request_headers(request, uid)
    gateway_url = f"{get_llm_gateway_base_url()}/v1/messages"
    if payload.get("stream") is True:
        client = httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=None, write=240, pool=10))
        context = client.stream("POST", gateway_url, content=body, headers=headers)
        try:
            upstream = await context.__aenter__()
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            await client.aclose()
            raise HTTPException(status_code=502, detail="LLM gateway request failed") from exc
        if upstream.status_code >= 400:
            content = await upstream.aread()
            await context.__aexit__(None, None, None)
            await client.aclose()
            return Response(content, status_code=upstream.status_code, media_type="application/json")
        return StreamingResponse(
            _stream_response(client, context, upstream),
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type", "text/event-stream"),
        )
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(240, connect=10)) as client:
            upstream = await client.post(gateway_url, content=body, headers=headers)
    except (httpx.TimeoutException, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail="LLM gateway request failed") from exc
    return Response(
        upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", "application/json"),
    )
