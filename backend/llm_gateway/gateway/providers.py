from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
import json
import os
import time
import logging
from typing import Any, Protocol, cast

import google.auth
from google.auth.transport.requests import Request as GoogleAuthRequest
import httpx

from llm_gateway.gateway.accounting import (
    ProviderResponseMetadata,
    ProviderUsage,
    anthropic_usage_from_response,
    cache_requested_for_anthropic_request,
    cache_write_ttl_for_anthropic_request,
    cache_requested_for_openai_request,
    openai_usage_from_response,
    vertex_usage_from_response,
)
from llm_gateway.gateway.credentials import CredentialContext
from llm_gateway.gateway.schemas import CredentialMode, FailureClass, ProviderRef, ProviderRejection
from llm_gateway.gateway.provider_types import (  # noqa: F401 — re-exported provider contract
    GENERIC_PROVIDER_FAILURE_MESSAGE,
    ProviderFailure,
    ProviderResponse,
    _VertexHttpError,  # pyright: ignore[reportPrivateUsage]
    _openai_usage_payload,  # pyright: ignore[reportPrivateUsage]
)
from llm_gateway.gateway.vertex_pt_policy import (  # noqa: F401 — re-exported vertex policy
    VertexPTPolicyMixin,
)
from llm_gateway.gateway.vertex_wire import (  # noqa: F401 — re-exported wire contract
    _nonnegative_int_or_zero,  # pyright: ignore[reportPrivateUsage]
    _openai_sse_done,  # pyright: ignore[reportPrivateUsage, reportUnusedImport]
    _text_content,  # pyright: ignore[reportPrivateUsage, reportUnusedImport]
    _validate_embeddings_response_shape,  # pyright: ignore[reportPrivateUsage]
    _vertex_embedding_predict_request,  # pyright: ignore[reportPrivateUsage]
    _vertex_headers,  # pyright: ignore[reportPrivateUsage]
    _vertex_predict_to_openai_embeddings,  # pyright: ignore[reportPrivateUsage]
    _vertex_request,  # pyright: ignore[reportPrivateUsage]
    _vertex_to_openai_response,  # pyright: ignore[reportPrivateUsage]
    _vertex_to_openai_stream_chunk,  # pyright: ignore[reportPrivateUsage]
)
from llm_gateway.gateway.sse import SSEEventDecoder
from utils.executors import critical_executor, run_blocking
from utils.llm import vertex_pt_routing as ptr
from utils.log_sanitizer import sanitize

logger = logging.getLogger(__name__)

OPENAI_API_KEY_ENV_VAR = 'OPENAI_API_KEY'
OPENAI_BASE_URL_ENV_VAR = 'OPENAI_BASE_URL'
DEFAULT_OPENAI_BASE_URL = 'https://api.openai.com/v1'
DEFAULT_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_RESPONSE_BYTES_ENV_VAR = 'OPENAI_MAX_RESPONSE_BYTES'
PROVIDER_ERROR_DETAIL_BYTES = 1000
EXPOSE_PROVIDER_ERROR_DETAILS_ENV_VAR = 'LLM_GATEWAY_EXPOSE_PROVIDER_ERROR_DETAILS'
GOOGLE_CLOUD_PROJECT_ENV_VAR = 'GOOGLE_CLOUD_PROJECT'
GOOGLE_CLOUD_PLATFORM_SCOPE = 'https://www.googleapis.com/auth/cloud-platform'


class ChatCompletionProvider(Protocol):
    async def create_chat_completion(
        self,
        request: Mapping[str, Any],
        *,
        provider_ref: ProviderRef,
        credentials: CredentialContext,
        timeout_ms: int,
    ) -> 'ProviderResponse': ...


class EmbeddingProvider(Protocol):
    async def create_embedding(
        self,
        request: Mapping[str, Any],
        *,
        provider_ref: ProviderRef,
        credentials: CredentialContext,
        timeout_ms: int,
    ) -> 'ProviderResponse': ...


class OpenAICompatibleChatCompletionProvider:
    def __init__(
        self,
        *,
        api_key_env: str = OPENAI_API_KEY_ENV_VAR,
        base_url: str | None = None,
        default_headers: Mapping[str, str] | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key_env = api_key_env
        self._base_url = (base_url or os.getenv(OPENAI_BASE_URL_ENV_VAR, DEFAULT_OPENAI_BASE_URL)).rstrip('/')
        self._default_headers = dict(default_headers or {})
        self._http_client = http_client or httpx.AsyncClient()
        self._owns_http_client = http_client is None

    async def create_chat_completion(
        self,
        request: Mapping[str, Any],
        *,
        provider_ref: ProviderRef,
        credentials: CredentialContext,
        timeout_ms: int,
    ) -> ProviderResponse:
        api_key = _resolve_provider_api_key(
            credentials=credentials,
            provider_ref=provider_ref,
            api_key_env=self._api_key_env,
        )

        try:
            async with self._http_client.stream(
                'POST',
                f'{self._base_url}/chat/completions',
                json=dict(request),
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                    **self._default_headers,
                },
                timeout=timeout_ms / 1000.0,
            ) as response:
                status_code = response.status_code
                if status_code >= 400:
                    # On error responses, read only a small bounded preview so
                    # that a large/invalid-content-length body cannot reclassify
                    # the status-specific failure class (e.g. 401 -> 5XX). The
                    # body is never surfaced unless LLM_GATEWAY_EXPOSE_PROVIDER_ERROR_DETAILS
                    # is explicitly enabled.
                    error_preview = await _read_bounded_preview(response, max_bytes=PROVIDER_ERROR_DETAIL_BYTES)
                    _raise_for_status(status_code, error_preview, credential_mode=credentials.mode)
                body = await _read_limited_response(response, max_bytes=_configured_max_response_bytes())
                parsed = _parse_limited_json_response(body)
        except httpx.TimeoutException as exc:
            raise ProviderFailure(FailureClass.TIMEOUT_BEFORE_OUTPUT) from exc
        except httpx.HTTPError as exc:
            raise ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID) from exc

        _validate_chat_completion_response_shape(parsed)
        return ProviderResponse(
            response=parsed,
            accounting=openai_usage_from_response(parsed, cache_requested=cache_requested_for_openai_request(request)),
        )

    async def stream_chat_completion(
        self,
        request: Mapping[str, Any],
        *,
        provider_ref: ProviderRef,
        credentials: CredentialContext,
        timeout_ms: int,
    ):
        api_key = _resolve_provider_api_key(
            credentials=credentials,
            provider_ref=provider_ref,
            api_key_env=self._api_key_env,
        )

        try:
            async with self._http_client.stream(
                'POST',
                f'{self._base_url}/chat/completions',
                json=dict(request),
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                    **self._default_headers,
                },
                timeout=timeout_ms / 1000.0,
            ) as response:
                if response.status_code >= 400:
                    error_preview = await _read_bounded_preview(response, max_bytes=PROVIDER_ERROR_DETAIL_BYTES)
                    _raise_for_status(response.status_code, error_preview, credential_mode=credentials.mode)
                async for chunk in response.aiter_bytes():
                    if chunk:
                        yield chunk
        except httpx.TimeoutException as exc:
            raise ProviderFailure(FailureClass.TIMEOUT_BEFORE_OUTPUT) from exc
        except httpx.HTTPError as exc:
            raise ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID) from exc

    async def create_embedding(
        self,
        request: Mapping[str, Any],
        *,
        provider_ref: ProviderRef,
        credentials: CredentialContext,
        timeout_ms: int,
    ) -> ProviderResponse:
        api_key = _resolve_provider_api_key(
            credentials=credentials,
            provider_ref=provider_ref,
            api_key_env=self._api_key_env,
        )
        payload = {'model': provider_ref.model, 'input': list(request['input'])}
        try:
            async with self._http_client.stream(
                'POST',
                f'{self._base_url}/embeddings',
                json=payload,
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                    **self._default_headers,
                },
                timeout=timeout_ms / 1000.0,
            ) as response:
                if response.status_code >= 400:
                    error_preview = await _read_bounded_preview(response, max_bytes=PROVIDER_ERROR_DETAIL_BYTES)
                    _raise_for_status(response.status_code, error_preview, credential_mode=credentials.mode)
                parsed = _parse_limited_json_response(
                    await _read_limited_response(response, max_bytes=_configured_max_response_bytes())
                )
        except ProviderFailure:
            raise
        except httpx.TimeoutException as exc:
            raise ProviderFailure(FailureClass.TIMEOUT_BEFORE_OUTPUT) from exc
        except httpx.HTTPError as exc:
            raise ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID) from exc

        _validate_embeddings_response_shape(parsed)
        raw_usage = parsed.get('usage')
        usage_raw = raw_usage if isinstance(raw_usage, Mapping) else {}
        prompt_tokens = _nonnegative_int_or_zero(usage_raw.get('prompt_tokens'))
        total_tokens = _nonnegative_int_or_zero(usage_raw.get('total_tokens'))
        return ProviderResponse(
            response=parsed,
            accounting=ProviderResponseMetadata(
                usage=ProviderUsage(
                    prompt_tokens=prompt_tokens,
                    uncached_input_tokens=prompt_tokens,
                    total_tokens=total_tokens,
                )
            ),
        )

    async def aclose(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()


class VertexAccessTokenSupplier:
    """Cache ADC access tokens while refreshing blocking Google auth off-loop."""

    def __init__(
        self,
        *,
        credentials_factory: Callable[..., tuple[Any, str | None]] = google.auth.default,
        auth_request_factory: Callable[[], Any] = GoogleAuthRequest,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._credentials_factory = credentials_factory
        self._auth_request_factory = auth_request_factory
        self._now = now
        self._credentials: Any | None = None
        self._access_token: str | None = None
        self._expires_at = 0.0
        self._refresh_lock = asyncio.Lock()

    async def get_access_token(self) -> str:
        if self._access_token and self._now() < self._expires_at - 60:
            return self._access_token
        async with self._refresh_lock:
            if self._access_token and self._now() < self._expires_at - 60:
                return self._access_token
            try:
                token, expires_at = await run_blocking(critical_executor, self._refresh)
            except Exception as exc:
                raise ProviderFailure(FailureClass.INVALID_CONFIG) from exc
            if not token:
                raise ProviderFailure(FailureClass.INVALID_CONFIG)
            self._access_token = token
            self._expires_at = expires_at
            return token

    def _refresh(self) -> tuple[str, float]:
        credentials = self._credentials
        if credentials is None:
            credentials, _ = self._credentials_factory(scopes=[GOOGLE_CLOUD_PLATFORM_SCOPE])
            self._credentials = credentials
        credentials.refresh(self._auth_request_factory())
        token = str(getattr(credentials, 'token', '') or '')
        expiry = getattr(credentials, 'expiry', None)
        expires_at = expiry.timestamp() if expiry is not None else self._now() + 300
        return token, expires_at


class VertexGeminiProvider(VertexPTPolicyMixin):
    """Native Gemini-on-Vertex adapter behind the gateway's OpenAI contract.

    Also owns the company-paid desktop PT policy — pin, overflow ladder,
    reachability, regional vs multi-region host, and the capacity header —
    through ``utils.llm.vertex_pt_routing``, the single policy module the
    desktop BFF mirrors on its kill-switch (direct) path.
    """

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient | None = None,
        access_token_supplier: Callable[[], Awaitable[str]] | None = None,
        project_env: str = GOOGLE_CLOUD_PROJECT_ENV_VAR,
        location_env: str = ptr.REGIONAL_LOCATION_ENV,
        multi_region_location_env: str = ptr.MULTI_REGION_LOCATION_ENV,
        pt_model_override_env: str = ptr.PT_MODEL_OVERRIDE_ENV,
        overflow_model_override_env: str = ptr.OVERFLOW_MODEL_OVERRIDE_ENV,
        overflow_enabled_env: str = ptr.OVERFLOW_ENABLED_ENV,
        probe_ttl_seconds: float = 600.0,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._http_client = http_client or httpx.AsyncClient()
        self._owns_http_client = http_client is None
        self._project_env = project_env
        self._location_env = location_env
        self._multi_region_location_env = multi_region_location_env
        self._pt_model_override_env = pt_model_override_env
        self._overflow_model_override_env = overflow_model_override_env
        self._overflow_enabled_env = overflow_enabled_env
        self._probe_ttl_seconds = probe_ttl_seconds
        self._now = now
        # PT probe TTL is monotonic; ADC expiry is wall-clock. Do not share
        # the PT clock with the token supplier or tokens never refresh
        # (`monotonic() < expiry.timestamp()` stays true forever).
        token_supplier = VertexAccessTokenSupplier()
        self._access_token_supplier = access_token_supplier or token_supplier.get_access_token
        # PT promotion latch and learned reachability, moved from the desktop
        # proxy: positive observations latch for the process, negative ones
        # expire on the probe TTL, and nothing is probed at startup — traffic
        # teaches both tables (see backend/docs/vertex-pt-flash.md).
        self._pt_target_ready = False
        self._pt_target_probed_at: float | None = None
        self._model_unavailable_at: dict[str, float] = {}

    async def create_chat_completion(
        self,
        request: Mapping[str, Any],
        *,
        provider_ref: ProviderRef,
        credentials: CredentialContext,
        timeout_ms: int,
    ) -> ProviderResponse:
        self._reject_byok(credentials)
        payload = _vertex_request(request)
        parsed = await self._generate_content(
            payload,
            anchor=provider_ref.model,
            credentials=credentials,
            timeout_ms=timeout_ms,
        )
        accounting = vertex_usage_from_response(parsed)
        normalized = _vertex_to_openai_response(
            parsed,
            requested_model=provider_ref.model,
            usage=accounting.usage,
        )
        _validate_chat_completion_response_shape(normalized)
        return ProviderResponse(response=normalized, accounting=accounting)

    async def stream_chat_completion(
        self,
        request: Mapping[str, Any],
        *,
        provider_ref: ProviderRef,
        credentials: CredentialContext,
        timeout_ms: int,
    ):
        self._reject_byok(credentials)
        payload = _vertex_request(request)
        deadline = self._now() + max(timeout_ms, 0) / 1000.0
        attempts = self._attempt_plan(provider_ref.model)
        decoder = SSEEventDecoder()
        while attempts:
            model, capacity = attempts.pop(0)
            remaining_ms = int((deadline - self._now()) * 1000)
            if remaining_ms <= 0:
                raise ProviderFailure(FailureClass.TIMEOUT_BEFORE_OUTPUT)
            try:
                endpoint = self._endpoint(model, method='streamGenerateContent')
                headers = _vertex_headers(await self._vertex_access_token(), capacity)
                async with self._http_client.stream(
                    'POST',
                    endpoint,
                    params={'alt': 'sse'},
                    json=payload,
                    headers=headers,
                    timeout=remaining_ms / 1000.0,
                ) as response:
                    if response.status_code >= 400:
                        error_preview = await _read_bounded_preview(response, max_bytes=PROVIDER_ERROR_DETAIL_BYTES)
                        self._observe_attempt(model, capacity, response.status_code, error_preview)
                        recovery = self._recovery_attempts(model, response.status_code, error_preview)
                        if recovery:
                            attempts = recovery
                            continue
                        _raise_for_status(response.status_code, error_preview, credential_mode=credentials.mode)
                    self._record_model_available(model)
                    async for chunk in response.aiter_bytes():
                        for event in decoder.feed(chunk):
                            event_data = event.data.strip()
                            if not event_data or event_data == '[DONE]':
                                continue
                            event_parsed = _parse_limited_json_response(event_data.encode('utf-8'))
                            translated, _ = _vertex_to_openai_stream_chunk(
                                event_parsed,
                                requested_model=provider_ref.model,
                                usage=vertex_usage_from_response(event_parsed).usage,
                            )
                            if translated is not None:
                                yield translated
                    yield _openai_sse_done()
                    return
            except ProviderFailure:
                raise
            except httpx.TimeoutException as exc:
                raise ProviderFailure(FailureClass.TIMEOUT_BEFORE_OUTPUT) from exc
            except httpx.HTTPError as exc:
                raise ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID) from exc

    async def create_embedding(
        self,
        request: Mapping[str, Any],
        *,
        provider_ref: ProviderRef,
        credentials: CredentialContext,
        timeout_ms: int,
    ) -> ProviderResponse:
        self._reject_byok(credentials)
        endpoint = self._endpoint(provider_ref.model, method='predict')
        payload = _vertex_embedding_predict_request(request)
        parsed: Mapping[str, Any] | None = None
        try:
            headers = _vertex_headers(await self._vertex_access_token(), self._capacity_for(provider_ref.model))
            async with self._http_client.stream(
                'POST',
                endpoint,
                json=payload,
                headers=headers,
                timeout=timeout_ms / 1000.0,
            ) as response:
                if response.status_code >= 400:
                    error_preview = await _read_bounded_preview(response, max_bytes=PROVIDER_ERROR_DETAIL_BYTES)
                    _raise_for_status(response.status_code, error_preview, credential_mode=credentials.mode)
                parsed = _parse_limited_json_response(
                    await _read_limited_response(response, max_bytes=_configured_max_response_bytes())
                )
        except ProviderFailure:
            raise
        except httpx.TimeoutException as exc:
            raise ProviderFailure(FailureClass.TIMEOUT_BEFORE_OUTPUT) from exc
        except httpx.HTTPError as exc:
            raise ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID) from exc

        normalized = _vertex_predict_to_openai_embeddings(parsed or {}, model=provider_ref.model)
        _validate_embeddings_response_shape(normalized)
        # Vertex :predict reports billable characters, not tokens; the ledger
        # row records the request while usage stays NOT_REPORTED rather than
        # fabricating token counts.
        return ProviderResponse(response=normalized, accounting=ProviderResponseMetadata(usage=None))

    async def aclose(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()

    async def _generate_content(
        self,
        payload: Mapping[str, Any],
        *,
        anchor: str,
        credentials: CredentialContext,
        timeout_ms: int,
    ) -> Mapping[str, Any]:
        """Run generateContent through the PT ladder: pin, overflow, fallback."""
        deadline = self._now() + max(timeout_ms, 0) / 1000.0
        attempts = self._attempt_plan(anchor)
        last_error: _VertexHttpError | None = None
        parsed: Mapping[str, Any] | None = None
        while attempts:
            model, capacity = attempts.pop(0)
            remaining_ms = int((deadline - self._now()) * 1000)
            if remaining_ms <= 0:
                raise ProviderFailure(FailureClass.TIMEOUT_BEFORE_OUTPUT)
            try:
                parsed = await self._generate_content_once(
                    model=model,
                    capacity=capacity,
                    payload=payload,
                    credentials=credentials,
                    timeout_ms=remaining_ms,
                )
            except _VertexHttpError as error:
                last_error = error
                self._observe_attempt(model, capacity, error.status_code, error.preview)
                recovery = self._recovery_attempts(model, error.status_code, error.preview)
                if recovery:
                    attempts = recovery
                    continue
                _raise_for_status(error.status_code, error.preview, credential_mode=credentials.mode)
            self._record_model_available(model)
            assert parsed is not None
            return parsed
        assert last_error is not None
        _raise_for_status(last_error.status_code, last_error.preview, credential_mode=credentials.mode)
        raise AssertionError('unreachable: _raise_for_status always raises')

    async def _generate_content_once(
        self,
        *,
        model: str,
        capacity: str,
        payload: Mapping[str, Any],
        credentials: CredentialContext,
        timeout_ms: int,
    ) -> Mapping[str, Any]:
        endpoint = self._endpoint(model, method='generateContent')
        try:
            headers = _vertex_headers(await self._vertex_access_token(), capacity)
            async with self._http_client.stream(
                'POST',
                endpoint,
                json=payload,
                headers=headers,
                timeout=timeout_ms / 1000.0,
            ) as response:
                if response.status_code >= 400:
                    error_preview = await _read_bounded_preview(response, max_bytes=PROVIDER_ERROR_DETAIL_BYTES)
                    raise _VertexHttpError(response.status_code, error_preview)
                return _parse_limited_json_response(
                    await _read_limited_response(response, max_bytes=_configured_max_response_bytes())
                )
        except _VertexHttpError:
            raise
        except ProviderFailure:
            raise
        except httpx.TimeoutException as exc:
            raise ProviderFailure(FailureClass.TIMEOUT_BEFORE_OUTPUT) from exc
        except httpx.HTTPError as exc:
            raise ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID) from exc

    async def _vertex_access_token(self) -> str:
        try:
            return await self._access_token_supplier()
        except ProviderFailure:
            raise
        except Exception as exc:
            raise ProviderFailure(FailureClass.INVALID_CONFIG) from exc

    @staticmethod
    def _reject_byok(credentials: CredentialContext) -> None:
        if credentials.mode == CredentialMode.BYOK:
            raise ProviderFailure(FailureClass.BYOK_UNSUPPORTED_PROVIDER)


class AnthropicMessagesProvider:
    """Minimal Anthropic Messages adapter behind the gateway route boundary."""

    def __init__(
        self,
        *,
        api_key_env: str = 'ANTHROPIC_API_KEY',
        base_url: str = 'https://api.anthropic.com/v1',
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key_env = api_key_env
        self._base_url = base_url.rstrip('/')
        self._http_client = http_client or httpx.AsyncClient()
        self._owns_http_client = http_client is None

    async def create_chat_completion(
        self,
        request: Mapping[str, Any],
        *,
        provider_ref: ProviderRef,
        credentials: CredentialContext,
        timeout_ms: int,
    ) -> ProviderResponse:
        if credentials.mode == CredentialMode.BYOK:
            raise ProviderFailure(FailureClass.BYOK_UNSUPPORTED_PROVIDER)

        api_key = os.getenv(self._api_key_env, '').strip()
        if not api_key:
            raise ProviderFailure(FailureClass.INVALID_CONFIG)

        anthropic_request = _anthropic_request(request, provider_ref)
        try:
            response = await self._http_client.post(
                f'{self._base_url}/messages',
                json=anthropic_request,
                headers={
                    'x-api-key': api_key,
                    'anthropic-version': '2023-06-01',
                    'anthropic-beta': 'token-efficient-tools-2025-02-19',
                    'Content-Type': 'application/json',
                },
                timeout=timeout_ms / 1000.0,
            )
            if response.status_code >= 400:
                _raise_for_status(
                    response.status_code,
                    response.content[:PROVIDER_ERROR_DETAIL_BYTES],
                    credential_mode=credentials.mode,
                )
            parsed = response.json()
        except httpx.TimeoutException as exc:
            raise ProviderFailure(FailureClass.TIMEOUT_BEFORE_OUTPUT) from exc
        except httpx.HTTPError as exc:
            raise ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID) from exc
        except ValueError as exc:
            raise ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID) from exc

        accounting = anthropic_usage_from_response(
            parsed,
            cache_requested=cache_requested_for_anthropic_request(anthropic_request),
            cache_write_ttl=cache_write_ttl_for_anthropic_request(anthropic_request),
        )
        normalized = _anthropic_to_openai_response(
            parsed,
            requested_model=str(request.get('model') or provider_ref.model),
            usage=accounting.usage,
        )
        return ProviderResponse(response=normalized, accounting=accounting)

    async def aclose(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()


def _anthropic_request(request: Mapping[str, Any], provider_ref: ProviderRef) -> dict[str, Any]:
    system_blocks: list[Any] = []
    messages: list[Mapping[str, Any]] = []
    for message in cast(list[object], request.get('messages') or []):
        if not isinstance(message, Mapping):
            continue
        typed_message = cast(Mapping[str, Any], message)
        if typed_message.get('role') == 'system':
            system_text = _text_content(typed_message.get('content'))
            if system_text:
                system_blocks.append(system_text)
        else:
            messages.append(typed_message)

    payload: dict[str, Any] = {
        'model': provider_ref.model,
        'messages': messages,
        'max_tokens': int(request.get('max_tokens') or request.get('max_completion_tokens') or 4096),
    }
    if system_blocks:
        payload['system'] = '\n\n'.join(str(block) for block in system_blocks if block is not None)
    if 'temperature' in request:
        payload['temperature'] = request['temperature']
    if 'tools' in request:
        payload['tools'] = request['tools']
    if 'tool_choice' in request and request.get('tool_choice') not in (None, 'none'):
        payload['tool_choice'] = request['tool_choice']
    return payload


def _anthropic_to_openai_response(
    response: Mapping[str, Any],
    *,
    requested_model: str,
    usage: ProviderUsage | None = None,
) -> dict[str, Any]:
    content_blocks = response.get('content')
    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    if isinstance(content_blocks, list):
        for block in cast(list[object], content_blocks):
            if not isinstance(block, Mapping):
                continue
            typed_block = cast(Mapping[str, Any], block)
            if typed_block.get('type') == 'text' and isinstance(typed_block.get('text'), str):
                text_parts.append(typed_block['text'])
            elif typed_block.get('type') == 'tool_use':
                tool_calls.append(
                    {
                        'id': typed_block.get('id') or '',
                        'type': 'function',
                        'function': {
                            'name': typed_block.get('name') or '',
                            'arguments': json.dumps(typed_block.get('input') or {}, separators=(',', ':')),
                        },
                    }
                )

    message: dict[str, Any] = {'role': 'assistant', 'content': ''.join(text_parts)}
    if tool_calls:
        message['tool_calls'] = tool_calls
    normalized: dict[str, Any] = {
        'id': str(response.get('id') or 'anthropic_gateway'),
        'object': 'chat.completion',
        'created': int(time.time()),
        'model': requested_model,
        'choices': [
            {
                'index': 0,
                'message': message,
                'finish_reason': 'tool_calls' if tool_calls else _openai_finish_reason(response.get('stop_reason')),
            }
        ],
    }
    if usage is not None:
        normalized['usage'] = _openai_usage_payload(usage)
    return normalized


def _openai_finish_reason(stop_reason: Any) -> str:
    if stop_reason in {'end_turn', 'stop_sequence'}:
        return 'stop'
    if stop_reason == 'max_tokens':
        return 'length'
    if stop_reason == 'tool_use':
        return 'tool_calls'
    return 'stop'


def _resolve_provider_api_key(
    *,
    credentials: CredentialContext,
    provider_ref: ProviderRef,
    api_key_env: str,
) -> str:
    if credentials.mode == CredentialMode.BYOK:
        forwarded = credentials.forwarded_key_for(provider_ref.provider)
        if not forwarded:
            raise ProviderFailure(FailureClass.MISSING_BYOK_KEY)
        return forwarded
    api_key = os.getenv(api_key_env, '').strip()
    if not api_key:
        raise ProviderFailure(FailureClass.INVALID_CONFIG)
    return api_key


class FakeChatCompletionProvider:
    def __init__(self, outcomes: list[Mapping[str, Any] | ProviderFailure] | None = None) -> None:
        self._outcomes: deque[Mapping[str, Any] | ProviderFailure] = deque(outcomes or [])
        self.calls: list[FakeProviderCall] = []

    async def create_chat_completion(
        self,
        request: Mapping[str, Any],
        *,
        provider_ref: ProviderRef,
        credentials: CredentialContext,
        timeout_ms: int,
    ) -> ProviderResponse:
        self.calls.append(
            FakeProviderCall(
                provider=provider_ref.provider,
                model=provider_ref.model,
                request=dict(request),
                credential_mode=credentials.mode.value,
                timeout_ms=timeout_ms,
            )
        )
        if not self._outcomes:
            response = _default_fake_response(provider_ref)
            return ProviderResponse(response=response, accounting=openai_usage_from_response(response))

        outcome = self._outcomes.popleft()
        if isinstance(outcome, ProviderFailure):
            raise outcome
        response = dict(outcome)
        return ProviderResponse(response=response, accounting=openai_usage_from_response(response))


@dataclass(frozen=True)
class FakeProviderCall:
    provider: str
    model: str
    request: dict[str, Any]
    credential_mode: str
    timeout_ms: int


def fake_success_response(provider_ref: ProviderRef, *, content: str = '{"answer":"ok"}') -> dict[str, Any]:
    return {
        'id': 'chatcmpl_fake',
        'object': 'chat.completion',
        'created': 1782522000,
        'model': provider_ref.model,
        'choices': [
            {
                'index': 0,
                'message': {'role': 'assistant', 'content': content},
                'finish_reason': 'stop',
            }
        ],
    }


def _default_fake_response(provider_ref: ProviderRef) -> dict[str, Any]:
    return fake_success_response(provider_ref)


def _raise_for_status(
    status_code: int,
    body: bytes = b'',
    *,
    credential_mode: CredentialMode = CredentialMode.OMI_PAID,
) -> None:
    byok = credential_mode == CredentialMode.BYOK
    if status_code in {401, 403}:
        raise ProviderFailure(
            FailureClass.BYOK_AUTH if byok else FailureClass.INVALID_CONFIG,
            safe_message=_provider_error_message(status_code, body),
        )
    if status_code == 408:
        raise ProviderFailure(
            FailureClass.TIMEOUT_BEFORE_OUTPUT, safe_message=_provider_error_message(status_code, body)
        )
    if status_code == 429:
        raise ProviderFailure(
            FailureClass.BYOK_RATE_LIMIT if byok else FailureClass.PROVIDER_429_OMI_PAID,
            safe_message=_provider_error_message(status_code, body),
        )
    if status_code >= 500:
        raise ProviderFailure(
            FailureClass.PROVIDER_5XX_OMI_PAID, safe_message=_provider_error_message(status_code, body)
        )
    if status_code >= 400:
        provider_rejection = _provider_rejection(body)
        failure_class = (
            FailureClass.CAPABILITY_MISMATCH
            if provider_rejection.value.startswith('unsupported_')
            else FailureClass.PROVIDER_INVALID_REQUEST
        )
        raise ProviderFailure(
            failure_class,
            safe_message=_provider_error_message(status_code, body),
            provider_rejection=provider_rejection,
        )


_PROVIDER_REJECTION_PARAMS = {
    'model': 'model',
    'messages': 'messages',
    'response_format': 'response_format',
    'reasoning_effort': 'reasoning_effort',
    'temperature': 'temperature',
    'max_tokens': 'output_limit',
    'max_completion_tokens': 'output_limit',
    'prompt_cache_key': 'prompt_cache',
    'prompt_cache_options': 'prompt_cache',
    'tools': 'tools',
    'tool_choice': 'tools',
    'stream': 'stream',
    'stream_options': 'stream',
}


def _provider_rejection(body: bytes) -> ProviderRejection:
    """Extract only allowlisted provider error semantics from a bounded body preview."""
    try:
        parsed = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ProviderRejection.OTHER_4XX
    if not isinstance(parsed, Mapping):
        return ProviderRejection.OTHER_4XX
    error = parsed.get('error')
    if not isinstance(error, Mapping):
        return ProviderRejection.OTHER_4XX

    code = error.get('code')
    if code == 'context_length_exceeded':
        return ProviderRejection.CONTEXT_LENGTH_EXCEEDED
    if code == 'model_not_found':
        return ProviderRejection.MODEL_NOT_FOUND

    prefix = 'unsupported' if code == 'unsupported_parameter' else None
    if code in {'invalid_parameter', 'invalid_value', 'invalid_type'}:
        prefix = 'invalid'
    if prefix is not None:
        raw_param = error.get('param')
        root_param = raw_param.split('[', 1)[0].split('.', 1)[0] if isinstance(raw_param, str) else ''
        bounded_param = _PROVIDER_REJECTION_PARAMS.get(root_param, 'other')
        return ProviderRejection(f'{prefix}_{bounded_param}')

    if error.get('type') == 'invalid_request_error':
        return ProviderRejection.INVALID_REQUEST
    return ProviderRejection.OTHER_4XX


def _provider_error_message(status_code: int, body: bytes) -> str:
    if not _expose_provider_error_details():
        return GENERIC_PROVIDER_FAILURE_MESSAGE
    preview = body.decode('utf-8', errors='replace')[:PROVIDER_ERROR_DETAIL_BYTES]
    return f'provider request failed: status={status_code} body={sanitize(preview)}'


def _expose_provider_error_details() -> bool:
    return os.getenv(EXPOSE_PROVIDER_ERROR_DETAILS_ENV_VAR, '').strip().lower() == 'true'


async def _read_limited_response(response: httpx.Response, *, max_bytes: int) -> bytes:
    content_length = response.headers.get('content-length')
    if content_length is not None:
        try:
            if int(content_length) > max_bytes:
                raise ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID)
        except ValueError as exc:
            raise ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID) from exc

    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > max_bytes:
            raise ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID)
        chunks.append(chunk)
    return b''.join(chunks)


async def _read_bounded_preview(response: httpx.Response, *, max_bytes: int) -> bytes:
    """Read at most ``max_bytes`` of the response body, truncating silently.

    Unlike :func:`_read_limited_response`, an oversized body never raises a
    failure class — the preview is simply truncated. This keeps status-specific
    classification (401/403/429/4xx) intact regardless of body size, so a
    large error response from the provider is not reclassified as a generic 5xx.
    """
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        remaining = max_bytes - total
        if remaining <= 0:
            break
        if len(chunk) > remaining:
            chunks.append(chunk[:remaining])
            break
        chunks.append(chunk)
        total += len(chunk)
    return b''.join(chunks)


def _parse_limited_json_response(body: bytes) -> Mapping[str, Any]:
    try:
        parsed = cast(object, json.loads(body))
    except ValueError as exc:
        raise ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID) from exc
    if not isinstance(parsed, Mapping):
        raise ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID)
    return cast(Mapping[str, Any], parsed)


def _validate_chat_completion_response_shape(response: Mapping[str, Any]) -> None:
    if response.get('object') != 'chat.completion':
        raise ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID)
    if not isinstance(response.get('id'), str) or not response['id']:
        raise ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID)
    if not isinstance(response.get('model'), str) or not response['model']:
        raise ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID)
    choices = response.get('choices')
    if not isinstance(choices, list) or not choices:
        raise ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID)
    typed_choices = cast(list[object], choices)
    for choice in typed_choices:
        if not isinstance(choice, Mapping):
            raise ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID)
        typed_choice = cast(Mapping[str, object], choice)
        message = typed_choice.get('message')
        if not isinstance(message, Mapping):
            raise ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID)
        typed_message = cast(Mapping[str, object], message)
        if typed_message.get('role') != 'assistant':
            raise ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID)


def _configured_max_response_bytes() -> int:
    configured = os.getenv(MAX_RESPONSE_BYTES_ENV_VAR, '').strip()
    if not configured:
        return DEFAULT_MAX_RESPONSE_BYTES
    try:
        value = int(configured)
    except ValueError as exc:
        raise ProviderFailure(FailureClass.INVALID_CONFIG) from exc
    return value if value > 0 else DEFAULT_MAX_RESPONSE_BYTES
