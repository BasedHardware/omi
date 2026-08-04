import asyncio
import json
import os
import re
import sys
import time
from collections.abc import AsyncIterator, Awaitable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, TypeVar, cast
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from database import redis_db
from llm_gateway.gateway.providers import VertexAccessTokenSupplier
from utils.byok import get_byok_key
from utils.executors import critical_executor, db_executor, run_blocking
from utils.http_client import (
    get_desktop_gemini_client,
    get_desktop_gemini_semaphore,
    get_desktop_gemini_stream_client,
)
from utils.llm.desktop_llm_stub import (
    llm_stub_enabled,
    stub_gemini_proxy_json,
    stub_gemini_proxy_stream_chunks,
)
from utils.observability.fallback import record_fallback
from utils.other.endpoints import get_current_user_uid
from utils.subscription import is_trial_paywalled

router = APIRouter()

_ALLOWED_ACTIONS = frozenset({'generateContent', 'streamGenerateContent', 'embedContent', 'batchEmbedContents'})
_ALLOWED_MODELS = frozenset({'gemini-2.5-flash', 'gemini-2.5-flash-lite', 'gemini-2.5-pro', 'gemini-embedding-001'})
_VERTEX_MODELS = frozenset({'gemini-2.5-flash', 'gemini-2.5-flash-lite', 'gemini-2.5-pro', 'gemini-embedding-001'})
# Vertex batch embedding is not wire-compatible with the AI Studio batch method.
# Keep the provider decision explicit instead of silently trying one API shape on
# another provider.
_VERTEX_ACTIONS = frozenset({'generateContent', 'streamGenerateContent', 'embedContent'})
_MAX_BODY_BYTES = 5 * 1024 * 1024
_MAX_OUTPUT_TOKENS = 8192
_DEFAULT_THINKING_BUDGET = 1024
_MAX_CONTENT_ITEMS = 128
_MAX_CONTENT_PARTS = 512
_MAX_INLINE_MEDIA_PARTS = 16
_BURST_LIMIT = 30
_DAILY_HARD_LIMIT = 1500

# The deployed Rust proxy originally used a 70/75-second attempt/logical
# contract. A later blind expansion to 235/240 seconds exactly matches the
# incident tail. Restore the bounded non-stream contract while adding the phase
# evidence that was missing. Streaming uses an idle-gap timeout in the shared
# client because a healthy SSE response may legitimately last longer.
_TOTAL_TIMEOUT_SECONDS = 75.0
_CREDENTIAL_TIMEOUT_SECONDS = 5.0
_POOL_WAIT_SECONDS = 5.0
_DISCONNECT_POLL_SECONDS = 0.1

_REQUEST_ID_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:-]{7,63}$')
_REVISION_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,126}$')
_TRACE_PATTERN = re.compile(r'^([0-9a-fA-F]{32})(?:/[^;]+)?(?:;o=[01])?$')
_vertex_tokens = VertexAccessTokenSupplier()

T = TypeVar('T')


@dataclass(frozen=True)
class UpstreamRoute:
    url: str
    headers: dict[str, str]
    params: dict[str, str]
    provider: str
    credential_source: str
    region: str


@dataclass(frozen=True)
class PayloadShape:
    size_bucket: str
    content_parts_bucket: str
    inline_media_bucket: str


class RoutingFailure(Exception):
    def __init__(self, *, code: str, message: str, phase: str = 'credential') -> None:
        super().__init__(code)
        self.code = code
        self.message = message
        self.phase = phase


class ClientDisconnected(Exception):
    pass


class ProxyTelemetry:
    def __init__(self, request: Request, *, streaming: bool) -> None:
        supplied_request_id = request.headers.get('x-omi-request-id') or request.headers.get('x-request-id') or ''
        self.request_id = supplied_request_id if _REQUEST_ID_PATTERN.fullmatch(supplied_request_id) else str(uuid4())
        trace_header = request.headers.get('x-cloud-trace-context', '')
        trace_match = _TRACE_PATTERN.fullmatch(trace_header)
        self.trace_id = trace_match.group(1).lower() if trace_match else ''
        self.route = 'stream' if streaming else 'nonstream'
        self.provider = 'unselected'
        self.credential_source = 'none'
        self.region = 'none'
        self.model = 'unknown'
        self.action = 'unknown'
        self.phase = 'validation'
        self.shape = PayloadShape('unknown', 'unknown', 'unknown')
        self.started = time.monotonic()
        self.completed = False

    def set_route(self, route: UpstreamRoute) -> None:
        self.provider = route.provider
        self.credential_source = route.credential_source
        self.region = route.region

    def complete(
        self,
        *,
        outcome: str,
        status_code: int,
        retryable: bool,
        upstream_status: int | None = None,
        phase: str | None = None,
    ) -> None:
        if self.completed:
            return
        self.completed = True
        phase = phase or self.phase
        event: dict[str, object] = {
            'severity': 'INFO' if 200 <= status_code < 400 else 'WARNING',
            'message': 'desktop_gemini_proxy_terminal',
            'event': 'desktop_gemini_proxy_terminal',
            'service': 'desktop-backend',
            'runtime_implementation': 'python',
            'revision': _safe_revision(os.getenv('K_REVISION')),
            'release_sha': _safe_revision(os.getenv('OMI_DESKTOP_BACKEND_RELEASE_SHA')),
            'request_id': self.request_id,
            'route': self.route,
            'provider_route': self.provider,
            'credential_source': self.credential_source,
            'model': self.model if self.model in _ALLOWED_MODELS else 'unknown',
            'region': _safe_region(self.region),
            'action': self.action if self.action in _ALLOWED_ACTIONS else 'unknown',
            'attempt': 1,
            'phase': phase,
            'outcome': outcome,
            'status_code': status_code,
            'upstream_status': upstream_status or 0,
            'upstream_status_class': _status_class(upstream_status),
            'retryable': retryable,
            'payload_size_bucket': self.shape.size_bucket,
            'content_parts_bucket': self.shape.content_parts_bucket,
            'inline_media_parts_bucket': self.shape.inline_media_bucket,
            'elapsed_ms': round((time.monotonic() - self.started) * 1000),
        }
        project = os.getenv('GOOGLE_CLOUD_PROJECT', '').strip()
        if self.trace_id and project:
            event['logging.googleapis.com/trace'] = f'projects/{project}/traces/{self.trace_id}'
        # One exact JSON object is ingested as jsonPayload in Cloud Logging.
        # The fixed allowlist above intentionally excludes UIDs, prompts, media,
        # URLs, headers, tokens, raw exceptions, and upstream response bodies.
        sys.stdout.write(json.dumps(event, separators=(',', ':'), sort_keys=True) + '\n')
        sys.stdout.flush()


def _safe_revision(value: object) -> str:
    text = str(value or '').strip()
    return text if _REVISION_PATTERN.fullmatch(text) else 'unknown'


def _safe_region(value: object) -> str:
    text = str(value or '').strip().lower()
    return text if text == 'global' or re.fullmatch(r'[a-z]+(?:-[a-z0-9]+)+', text) else 'none'


def _status_class(status: int | None) -> str:
    if status is None:
        return 'none'
    if status == 429:
        return '429'
    if 100 <= status <= 599:
        return f'{status // 100}xx'
    return 'unknown'


def _bucket(value: int, thresholds: tuple[tuple[int, str], ...], overflow: str) -> str:
    for maximum, label in thresholds:
        if value <= maximum:
            return label
    return overflow


def _payload_shape(body: bytes) -> PayloadShape:
    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        return PayloadShape(_size_bucket(len(body)), 'unknown', 'unknown')
    if not isinstance(payload, dict):
        return PayloadShape(_size_bucket(len(body)), 'unknown', 'unknown')
    contents = payload.get('contents')
    content_count = len(contents) if isinstance(contents, list) else 0
    part_count = 0
    inline_media_count = 0
    if isinstance(contents, list):
        for content in contents:
            if not isinstance(content, dict) or not isinstance(content.get('parts'), list):
                continue
            parts = content['parts']
            part_count += len(parts)
            for part in parts:
                if isinstance(part, dict) and ('inlineData' in part or 'inline_data' in part):
                    inline_media_count += 1
    if content_count > _MAX_CONTENT_ITEMS:
        raise HTTPException(status_code=413, detail='Gemini request has too many content items')
    if part_count > _MAX_CONTENT_PARTS:
        raise HTTPException(status_code=413, detail='Gemini request has too many content parts')
    if inline_media_count > _MAX_INLINE_MEDIA_PARTS:
        raise HTTPException(status_code=413, detail='Gemini request has too many inline media parts')
    return PayloadShape(
        _size_bucket(len(body)),
        _bucket(part_count, ((2, '0-2'), (8, '3-8'), (32, '9-32'), (128, '33-128')), '129+'),
        _bucket(inline_media_count, ((0, '0'), (1, '1'), (4, '2-4')), '5+'),
    )


def _size_bucket(size: int) -> str:
    return _bucket(
        size,
        ((16_384, '0-16kb'), (131_072, '16-128kb'), (524_288, '128-512kb'), (1_048_576, '512kb-1mb')),
        '1mb+',
    )


def _path_parts(path: str) -> tuple[str, str, str]:
    path = path.replace('gemini-3-flash-preview', 'gemini-2.5-flash')
    prefix, separator, action = path.partition(':')
    model = prefix.removeprefix('models/') if separator and prefix.startswith('models/') else ''
    if action not in _ALLOWED_ACTIONS or model not in _ALLOWED_MODELS:
        raise HTTPException(status_code=403, detail='Gemini model or action is not allowed')
    return path, model, action


def _as_nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, float) and value >= 0 and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _sanitize(body: bytes, action: str) -> bytes:
    try:
        payload = json.loads(body)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail='Request body must be valid JSON') from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail='Request body must be a JSON object')
    for key in ('safety_settings', 'safetySettings', 'cached_content', 'cachedContent'):
        payload.pop(key, None)
    contents = payload.get('contents')
    if isinstance(contents, list):
        system_parts: list[Any] = []
        remaining = []
        for content in contents:
            if not isinstance(content, dict):
                remaining.append(content)
                continue
            role = content.setdefault('role', 'user')
            if role == 'system':
                if isinstance(content.get('parts'), list):
                    system_parts.extend(content['parts'])
            else:
                remaining.append(content)
        payload['contents'] = remaining
        if system_parts:
            key = 'system_instruction' if 'system_instruction' in payload else 'systemInstruction'
            instruction = payload.get(key)
            if isinstance(instruction, dict) and isinstance(instruction.get('parts'), list):
                instruction['parts'].extend(system_parts)
            else:
                payload['systemInstruction'] = {'parts': system_parts}
    if action not in {'embedContent', 'batchEmbedContents'}:
        for key in ('candidate_count', 'candidateCount'):
            value = _as_nonnegative_int(payload.get(key))
            if value is not None and value > 1:
                raise HTTPException(status_code=400, detail='candidate_count must be 1 or absent')
        generation_configs = [
            payload[key] for key in ('generation_config', 'generationConfig') if isinstance(payload.get(key), dict)
        ]
        if not generation_configs:
            payload['generationConfig'] = {
                'maxOutputTokens': _MAX_OUTPUT_TOKENS,
                'thinkingConfig': {'thinkingBudget': _DEFAULT_THINKING_BUDGET},
            }
        for config in generation_configs:
            for key in ('candidate_count', 'candidateCount'):
                value = _as_nonnegative_int(config.get(key))
                if value is not None and value > 1:
                    raise HTTPException(status_code=400, detail='candidate_count must be 1 or absent')
            output_key_present = False
            for key in ('max_output_tokens', 'maxOutputTokens'):
                value = _as_nonnegative_int(config.get(key))
                if value is not None:
                    output_key_present = True
                    if value > _MAX_OUTPUT_TOKENS:
                        config[key] = _MAX_OUTPUT_TOKENS
            if not output_key_present:
                config['maxOutputTokens'] = _MAX_OUTPUT_TOKENS
            if 'thinking_config' not in config and 'thinkingConfig' not in config:
                config['thinkingConfig'] = {'thinkingBudget': _DEFAULT_THINKING_BUDGET}
    return json.dumps(payload, separators=(',', ':')).encode()


def _vertex_url(model: str, action: str) -> str | None:
    project = os.getenv('GOOGLE_CLOUD_PROJECT', '').strip()
    if model not in _VERTEX_MODELS or action not in _VERTEX_ACTIONS or not project:
        return None
    location = os.getenv('GCP_LOCATION', 'us-central1').strip()
    return f'https://{location}-aiplatform.googleapis.com/v1/projects/{project}/locations/{location}/publishers/google/models/{model}:{action}'


def _studio_url(path: str) -> str:
    return f'https://generativelanguage.googleapis.com/v1beta/{path}'


def _safe_provider_query(query: dict[str, str]) -> dict[str, str]:
    forbidden = {'key', 'access_token', 'oauth_token'}
    if any(key.casefold() in forbidden for key in query):
        raise HTTPException(status_code=400, detail='Provider credential query parameters are not allowed')
    return query


async def _upstream(path: str, model: str, action: str, query: dict[str, str]) -> UpstreamRoute:
    query = _safe_provider_query(query)
    byok_key = get_byok_key('gemini')
    if byok_key:
        return UpstreamRoute(_studio_url(path), {}, {**query, 'key': byok_key}, 'ai_studio_byok', 'byok', 'global')
    vertex_url = _vertex_url(model, action)
    if vertex_url:
        try:
            async with asyncio.timeout(_CREDENTIAL_TIMEOUT_SECONDS):
                token = await _vertex_tokens.get_access_token()
        except TimeoutError as exc:
            raise RoutingFailure(
                code='routing_credential_timeout',
                message='Gemini routing credentials timed out before provider dispatch',
            ) from exc
        except Exception as exc:
            # A configured Vertex route is an operator/security boundary. Never
            # hide a broken identity by silently moving the request to AI Studio.
            raise RoutingFailure(
                code='routing_credentials_unavailable',
                message='Gemini routing credentials are unavailable',
            ) from exc
        url = vertex_url.rsplit(':', 1)[0] + ':predict' if action == 'embedContent' else vertex_url
        return UpstreamRoute(
            url,
            {'Authorization': f'Bearer {token}'},
            query,
            'vertex_ai',
            'application_default_credentials',
            os.getenv('GCP_LOCATION', 'us-central1').strip(),
        )
    server_key = os.getenv('GEMINI_API_KEY', '').strip()
    if not server_key:
        raise RoutingFailure(
            code='routing_not_configured', message='Gemini provider route is not configured', phase='routing'
        )
    return UpstreamRoute(_studio_url(path), {}, {**query, 'key': server_key}, 'ai_studio', 'server_key', 'global')


async def _meter_server_request(uid: str, path: str, model: str, action: str) -> str:
    if get_byok_key('gemini'):
        return path
    try:
        burst_allowed, _, _ = await run_blocking(
            critical_executor, redis_db.check_rate_limit, uid, 'desktop_gemini_burst', _BURST_LIMIT, 60
        )
        if not burst_allowed:
            raise HTTPException(status_code=429, detail='Gemini request rate limit exceeded')
        _, current, _ = await run_blocking(
            critical_executor,
            redis_db.check_rate_limit,
            uid,
            'desktop_gemini_daily',
            _DAILY_HARD_LIMIT,
            86_400,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail='Gemini rate limiter is unavailable') from exc
    if int(current) > _DAILY_HARD_LIMIT:
        raise HTTPException(status_code=429, detail='Gemini daily request limit exceeded')
    soft_limit = 300 if os.getenv('OMI_MODEL_TIER', '').strip().lower() == 'max' else 30
    if int(current) > soft_limit and action not in {'embedContent', 'batchEmbedContents'} and model == 'gemini-2.5-pro':
        record_fallback(
            component='gemini_model',
            from_mode='pro',
            to_mode='flash',
            reason='quota',
            outcome='degraded',
        )
        return f'models/gemini-2.5-flash:{action}'
    return path


def _vertex_embedding_request(body: bytes) -> bytes:
    payload = json.loads(body)
    try:
        text = payload['content']['parts'][0]['text']
    except (KeyError, IndexError, TypeError) as exc:
        raise HTTPException(status_code=400, detail='embedContent requires content.parts[0].text') from exc
    instance = {'content': text}
    for source, destination in (('taskType', 'task_type'), ('title', 'title')):
        if source in payload:
            instance[destination] = payload[source]
    return json.dumps({'instances': [instance]}, separators=(',', ':')).encode()


def _vertex_embedding_response(body: bytes) -> bytes:
    try:
        values = json.loads(body)['predictions'][0]['embeddings']['values']
    except (KeyError, IndexError, TypeError, ValueError):
        return body
    return json.dumps({'embedding': {'values': values}}, separators=(',', ':')).encode()


async def _wait_for_disconnect(request: Request) -> None:
    while not await request.is_disconnected():
        await asyncio.sleep(_DISCONNECT_POLL_SECONDS)


async def _await_value(awaitable: Awaitable[T]) -> T:
    return await awaitable


async def _cancel_on_disconnect(request: Request, awaitable: Awaitable[T]) -> T:
    upstream_task = asyncio.create_task(_await_value(awaitable), name='desktop-gemini-upstream')
    disconnect_task = asyncio.create_task(_wait_for_disconnect(request), name='desktop-gemini-disconnect')
    try:
        done, _ = await asyncio.wait((upstream_task, disconnect_task), return_when=asyncio.FIRST_COMPLETED)
        if upstream_task in done:
            return await upstream_task
        raise ClientDisconnected
    finally:
        upstream_task.cancel()
        with suppress(asyncio.CancelledError):
            await upstream_task
        disconnect_task.cancel()
        with suppress(asyncio.CancelledError):
            await disconnect_task


async def _read_request_body(request: Request) -> bytes:
    content_length = request.headers.get('content-length')
    if content_length is not None:
        if not content_length.isascii() or not content_length.isdigit():
            raise HTTPException(status_code=400, detail='Content-Length must be a non-negative integer')
        declared_length = int(content_length)
        if declared_length > _MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail='Request body is too large')

    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > _MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail='Request body is too large')
        body.extend(chunk)
    return bytes(body)


def _response_headers(
    telemetry: ProxyTelemetry,
    *,
    provider: str | None = None,
    error_class: str | None = None,
    phase: str | None = None,
    retryable: bool | None = None,
    upstream_status: int | None = None,
) -> dict[str, str]:
    headers = {
        'X-Request-Id': telemetry.request_id,
        'X-Omi-Request-Id': telemetry.request_id,
        'X-Omi-Provider': provider or telemetry.provider,
    }
    if error_class:
        headers['X-Omi-Error-Class'] = error_class
    if phase:
        headers['X-Omi-Failure-Phase'] = phase
    if retryable is not None:
        headers['X-Omi-Retryable'] = 'true' if retryable else 'false'
    if upstream_status is not None:
        headers['X-Omi-Upstream-Status'] = str(upstream_status)
    return headers


def _error_response(
    telemetry: ProxyTelemetry,
    *,
    status_code: int,
    code: str,
    message: str,
    phase: str,
    retryable: bool,
    upstream_status: int | None = None,
    retry_after: int | None = None,
) -> JSONResponse:
    headers = _response_headers(
        telemetry,
        error_class=code,
        phase=phase,
        retryable=retryable,
        upstream_status=upstream_status,
    )
    if retry_after is not None:
        headers['Retry-After'] = str(retry_after)
    return JSONResponse(
        status_code=status_code,
        headers=headers,
        content={'error': code, 'message': message, 'request_id': telemetry.request_id, 'retryable': retryable},
    )


def _timeout_phase(exc: httpx.TimeoutException) -> str:
    if isinstance(exc, httpx.ConnectTimeout):
        return 'connect'
    if isinstance(exc, httpx.WriteTimeout):
        return 'write'
    if isinstance(exc, httpx.PoolTimeout):
        return 'pool'
    if isinstance(exc, httpx.ReadTimeout):
        return 'read'
    return 'provider'


def _provider_error(response: httpx.Response, telemetry: ProxyTelemetry) -> Response:
    status = response.status_code
    if status == 429:
        code, proxy_status, message, retryable, retry_after = (
            'provider_rate_limited',
            429,
            'Gemini provider rate limited the request',
            True,
            30,
        )
    elif status in {408, 504}:
        code, proxy_status, message, retryable, retry_after = (
            'provider_timeout',
            504,
            'Gemini provider timed out before returning a terminal response',
            False,
            None,
        )
    elif status >= 500:
        code, proxy_status, message, retryable, retry_after = (
            'provider_unavailable',
            502,
            'Gemini provider returned an unavailable response',
            False,
            None,
        )
    else:
        code, proxy_status, message, retryable, retry_after = (
            'provider_rejected',
            status,
            'Gemini provider rejected the request',
            False,
            None,
        )
    telemetry.complete(
        outcome=code,
        status_code=proxy_status,
        retryable=retryable,
        upstream_status=status,
        phase='provider',
    )
    return _error_response(
        telemetry,
        status_code=proxy_status,
        code=code,
        message=message,
        phase='provider',
        retryable=retryable,
        upstream_status=status,
        retry_after=retry_after,
    )


async def _acquire_provider_slot(semaphore: asyncio.Semaphore) -> None:
    try:
        async with asyncio.timeout(_POOL_WAIT_SECONDS):
            await semaphore.acquire()
    except TimeoutError as exc:
        raise httpx.PoolTimeout('Desktop Gemini concurrency pool wait exceeded') from exc


def _stream_error_event(*, code: str, phase: str, telemetry: ProxyTelemetry) -> bytes:
    event = {'error': code, 'phase': phase, 'request_id': telemetry.request_id, 'retryable': False}
    return f'data: {json.dumps(event, separators=(",", ":"))}\n\n'.encode()


async def _stream_provider(
    request: Request,
    route: UpstreamRoute,
    body: bytes,
    telemetry: ProxyTelemetry,
) -> AsyncIterator[bytes]:
    client = get_desktop_gemini_stream_client()
    semaphore = get_desktop_gemini_semaphore()
    context: Any | None = None
    acquired = False
    opened = False
    try:
        async with asyncio.timeout(_TOTAL_TIMEOUT_SECONDS):
            telemetry.phase = 'pool'
            await _acquire_provider_slot(semaphore)
            acquired = True
            telemetry.phase = 'connect'
            context = client.stream(
                'POST',
                route.url,
                params=route.params,
                content=body,
                headers={'Content-Type': 'application/json', **route.headers},
            )
            upstream = cast(httpx.Response, await _cancel_on_disconnect(request, context.__aenter__()))
            opened = True
        telemetry.phase = 'first_byte'
        if upstream.status_code >= 400:
            response = _provider_error(upstream, telemetry)
            event = json.loads(bytes(response.body))
            yield f'data: {json.dumps(event, separators=(",", ":"))}\n\n'.encode()
            return
        async for chunk in upstream.aiter_bytes():
            yield chunk
        telemetry.complete(outcome='success', status_code=upstream.status_code, retryable=False, phase='body')
    except ClientDisconnected:
        telemetry.complete(outcome='client_cancelled', status_code=499, retryable=False, phase='client_disconnect')
        yield _stream_error_event(code='client_cancelled', phase='client_disconnect', telemetry=telemetry)
    except httpx.TimeoutException as exc:
        phase = _timeout_phase(exc)
        telemetry.complete(outcome=f'{phase}_timeout', status_code=504, retryable=False, phase=phase)
        yield _stream_error_event(code='provider_timeout', phase=phase, telemetry=telemetry)
    except TimeoutError:
        phase = telemetry.phase
        telemetry.complete(outcome='provider_deadline_exceeded', status_code=504, retryable=False, phase=phase)
        yield _stream_error_event(code='provider_deadline_exceeded', phase=phase, telemetry=telemetry)
    except asyncio.CancelledError:
        telemetry.complete(outcome='client_cancelled', status_code=499, retryable=False, phase='client_disconnect')
        raise
    except httpx.HTTPError:
        telemetry.complete(outcome='transport_error', status_code=502, retryable=False, phase='body')
        yield _stream_error_event(code='provider_transport_error', phase=telemetry.phase, telemetry=telemetry)
    finally:
        if opened and context is not None:
            with suppress(Exception):
                await context.__aexit__(None, None, None)
        if acquired:
            semaphore.release()


async def _proxy(request: Request, path: str, streaming: bool, uid: str) -> Response:
    telemetry = ProxyTelemetry(request, streaming=streaming)
    try:
        body = await _read_request_body(request)
        telemetry.shape = _payload_shape(body)
        path, model, action = _path_parts(path)
        telemetry.model = model
        telemetry.action = action
        if llm_stub_enabled():
            body_text = body.decode('utf-8', errors='replace')
            telemetry.provider = 'offline_stub'
            telemetry.credential_source = 'none'
            if streaming or action == 'streamGenerateContent':
                chunks = stub_gemini_proxy_stream_chunks(body_text)

                async def stub_stream() -> AsyncIterator[bytes]:
                    for chunk in chunks:
                        yield chunk.encode('utf-8')

                telemetry.complete(outcome='success', status_code=200, retryable=False, phase='stub')
                return StreamingResponse(
                    stub_stream(), media_type='text/event-stream', headers=_response_headers(telemetry)
                )
            payload = stub_gemini_proxy_json(body_text)
            telemetry.complete(outcome='success', status_code=200, retryable=False, phase='stub')
            return Response(
                json.dumps(payload, separators=(',', ':')).encode('utf-8'),
                media_type='application/json',
                headers=_response_headers(telemetry),
            )
        telemetry.phase = 'metering'
        path = await _meter_server_request(uid, path, model, action)
        _, model, action = _path_parts(path)
        telemetry.model = model
        telemetry.action = action
        body = _sanitize(body, action)
        telemetry.shape = _payload_shape(body)
    except HTTPException as exc:
        outcome = 'rate_limited' if exc.status_code == 429 else 'validation_rejected'
        phase = telemetry.phase if telemetry.phase == 'metering' else 'validation'
        retryable = exc.status_code == 429
        telemetry.complete(outcome=outcome, status_code=exc.status_code, retryable=retryable, phase=phase)
        exc.headers = {
            **(exc.headers or {}),
            **_response_headers(telemetry, error_class=outcome, phase=phase, retryable=retryable),
        }
        raise

    try:
        async with asyncio.timeout(_TOTAL_TIMEOUT_SECONDS):
            telemetry.phase = 'routing'
            route = await _upstream(path, model, action, dict(request.query_params))
            telemetry.set_route(route)
            if route.provider == 'vertex_ai' and action == 'embedContent':
                body = _vertex_embedding_request(body)
            if streaming:
                return StreamingResponse(
                    _stream_provider(request, route, body, telemetry),
                    media_type='text/event-stream',
                    headers=_response_headers(telemetry),
                )
            client = get_desktop_gemini_client()
            semaphore = get_desktop_gemini_semaphore()

            async def post() -> httpx.Response:
                telemetry.phase = 'pool'
                await _acquire_provider_slot(semaphore)
                try:
                    telemetry.phase = 'connect'
                    return await client.post(
                        route.url,
                        params=route.params,
                        content=body,
                        headers={'Content-Type': 'application/json', **route.headers},
                    )
                finally:
                    semaphore.release()

            response = await _cancel_on_disconnect(request, post())
            telemetry.phase = 'body'
    except HTTPException as exc:
        phase = telemetry.phase if telemetry.phase in {'routing', 'credential'} else 'validation'
        telemetry.complete(outcome='validation_rejected', status_code=exc.status_code, retryable=False, phase=phase)
        exc.headers = {
            **(exc.headers or {}),
            **_response_headers(
                telemetry,
                error_class='validation_rejected',
                phase=phase,
                retryable=False,
            ),
        }
        raise
    except RoutingFailure as exc:
        telemetry.complete(outcome=exc.code, status_code=503, retryable=False, phase=exc.phase)
        return _error_response(
            telemetry,
            status_code=503,
            code=exc.code,
            message=exc.message,
            phase=exc.phase,
            retryable=False,
        )
    except ClientDisconnected:
        telemetry.complete(outcome='client_cancelled', status_code=499, retryable=False, phase='client_disconnect')
        return _error_response(
            telemetry,
            status_code=499,
            code='client_cancelled',
            message='Client disconnected before the Gemini request completed',
            phase='client_disconnect',
            retryable=False,
        )
    except httpx.TimeoutException as exc:
        phase = _timeout_phase(exc)
        telemetry.complete(outcome=f'{phase}_timeout', status_code=504, retryable=False, phase=phase)
        return _error_response(
            telemetry,
            status_code=504,
            code='provider_timeout',
            message=f'Gemini provider timed out during {phase}',
            phase=phase,
            retryable=False,
        )
    except TimeoutError:
        phase = telemetry.phase
        status_code = 503 if phase in {'routing', 'credential'} else 504
        code = 'routing_timeout' if status_code == 503 else 'provider_deadline_exceeded'
        telemetry.complete(outcome=code, status_code=status_code, retryable=False, phase=phase)
        return _error_response(
            telemetry,
            status_code=status_code,
            code=code,
            message='Gemini request exceeded the Omi logical deadline',
            phase=phase,
            retryable=False,
        )
    except asyncio.CancelledError:
        telemetry.complete(outcome='client_cancelled', status_code=499, retryable=False, phase='client_disconnect')
        raise
    except httpx.HTTPError:
        telemetry.complete(outcome='transport_error', status_code=502, retryable=False, phase=telemetry.phase)
        return _error_response(
            telemetry,
            status_code=502,
            code='provider_transport_error',
            message='Gemini provider transport failed',
            phase=telemetry.phase,
            retryable=False,
        )

    if response.status_code >= 400:
        return _provider_error(response, telemetry)
    content = (
        _vertex_embedding_response(response.content)
        if route.provider == 'vertex_ai' and action == 'embedContent'
        else response.content
    )
    telemetry.complete(
        outcome='success',
        status_code=response.status_code,
        retryable=False,
        upstream_status=response.status_code,
        phase='body',
    )
    return Response(
        content,
        status_code=response.status_code,
        media_type=response.headers.get('content-type'),
        headers=_response_headers(telemetry),
    )


async def _authorized_desktop_user(uid: str = Depends(get_current_user_uid)) -> str:
    if await run_blocking(db_executor, is_trial_paywalled, uid, 'desktop'):
        raise HTTPException(status_code=402, detail='trial_expired')
    return uid


@router.post('/v1/proxy/gemini/{path:path}')
async def gemini_proxy(request: Request, path: str, uid: str = Depends(_authorized_desktop_user)) -> Response:
    return await _proxy(request, path, False, uid)


@router.post('/v1/proxy/gemini-stream/{path:path}')
async def gemini_stream_proxy(request: Request, path: str, uid: str = Depends(_authorized_desktop_user)) -> Response:
    return await _proxy(request, path, True, uid)
