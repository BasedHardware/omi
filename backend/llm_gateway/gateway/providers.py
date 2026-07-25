from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
import json
import os
import time
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
from llm_gateway.gateway.sse import SSEEventDecoder
from utils.executors import critical_executor, run_blocking
from utils.log_sanitizer import sanitize

OPENAI_API_KEY_ENV_VAR = 'OPENAI_API_KEY'
OPENAI_BASE_URL_ENV_VAR = 'OPENAI_BASE_URL'
DEFAULT_OPENAI_BASE_URL = 'https://api.openai.com/v1'
DEFAULT_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_RESPONSE_BYTES_ENV_VAR = 'OPENAI_MAX_RESPONSE_BYTES'
PROVIDER_ERROR_DETAIL_BYTES = 1000
EXPOSE_PROVIDER_ERROR_DETAILS_ENV_VAR = 'LLM_GATEWAY_EXPOSE_PROVIDER_ERROR_DETAILS'
GENERIC_PROVIDER_FAILURE_MESSAGE = 'provider request failed'
GOOGLE_CLOUD_PROJECT_ENV_VAR = 'GOOGLE_CLOUD_PROJECT'
GCP_LOCATION_ENV_VAR = 'GCP_LOCATION'
DEFAULT_GCP_LOCATION = 'us-central1'
GOOGLE_CLOUD_PLATFORM_SCOPE = 'https://www.googleapis.com/auth/cloud-platform'
VERTEX_API_VERSION = 'v1'


class ChatCompletionProvider(Protocol):
    async def create_chat_completion(
        self,
        request: Mapping[str, Any],
        *,
        provider_ref: ProviderRef,
        credentials: CredentialContext,
        timeout_ms: int,
    ) -> 'ProviderResponse': ...


@dataclass
class ProviderFailure(Exception):
    failure_class: FailureClass
    safe_message: str = GENERIC_PROVIDER_FAILURE_MESSAGE
    provider_rejection: ProviderRejection = ProviderRejection.NONE

    def __str__(self) -> str:
        return self.safe_message


@dataclass(frozen=True)
class ProviderResponse(Mapping[str, Any]):
    """OpenAI-compatible response plus provider-native accounting metadata."""

    response: Mapping[str, Any]
    accounting: ProviderResponseMetadata = ProviderResponseMetadata()

    def __getitem__(self, key: str) -> Any:
        return self.response[key]

    def __iter__(self):
        return iter(self.response)

    def __len__(self) -> int:
        return len(self.response)


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


class VertexGeminiProvider:
    """Native Gemini-on-Vertex adapter behind the gateway's OpenAI contract."""

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient | None = None,
        access_token_supplier: Callable[[], Awaitable[str]] | None = None,
        project_env: str = GOOGLE_CLOUD_PROJECT_ENV_VAR,
        location_env: str = GCP_LOCATION_ENV_VAR,
    ) -> None:
        self._http_client = http_client or httpx.AsyncClient()
        self._owns_http_client = http_client is None
        self._project_env = project_env
        self._location_env = location_env
        token_supplier = VertexAccessTokenSupplier()
        self._access_token_supplier = access_token_supplier or token_supplier.get_access_token

    async def create_chat_completion(
        self,
        request: Mapping[str, Any],
        *,
        provider_ref: ProviderRef,
        credentials: CredentialContext,
        timeout_ms: int,
    ) -> ProviderResponse:
        self._reject_byok(credentials)
        endpoint = self._endpoint(provider_ref.model, method='generateContent')
        payload = _vertex_request(request)
        try:
            access_token = await self._vertex_access_token()
            async with self._http_client.stream(
                'POST',
                endpoint,
                json=payload,
                headers=_vertex_headers(access_token),
                timeout=timeout_ms / 1000.0,
            ) as response:
                if response.status_code >= 400:
                    error_preview = await _read_bounded_preview(response, max_bytes=PROVIDER_ERROR_DETAIL_BYTES)
                    _raise_for_status(response.status_code, error_preview)
                parsed = _parse_limited_json_response(
                    await _read_limited_response(response, max_bytes=_configured_max_response_bytes())
                )
        except ProviderFailure:
            raise
        except httpx.TimeoutException as exc:
            raise ProviderFailure(FailureClass.TIMEOUT_BEFORE_OUTPUT) from exc
        except httpx.HTTPError as exc:
            raise ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID) from exc

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
        endpoint = self._endpoint(provider_ref.model, method='streamGenerateContent')
        payload = _vertex_request(request)
        decoder = SSEEventDecoder()
        try:
            access_token = await self._vertex_access_token()
            async with self._http_client.stream(
                'POST',
                endpoint,
                params={'alt': 'sse'},
                json=payload,
                headers=_vertex_headers(access_token),
                timeout=timeout_ms / 1000.0,
            ) as response:
                if response.status_code >= 400:
                    error_preview = await _read_bounded_preview(response, max_bytes=PROVIDER_ERROR_DETAIL_BYTES)
                    _raise_for_status(response.status_code, error_preview)
                async for chunk in response.aiter_bytes():
                    for event in decoder.feed(chunk):
                        event_data = event.data.strip()
                        if not event_data or event_data == '[DONE]':
                            continue
                        parsed = _parse_limited_json_response(event_data.encode('utf-8'))
                        translated, _ = _vertex_to_openai_stream_chunk(
                            parsed,
                            requested_model=provider_ref.model,
                            usage=vertex_usage_from_response(parsed).usage,
                        )
                        if translated is not None:
                            yield translated
                yield _openai_sse_done()
        except ProviderFailure:
            raise
        except httpx.TimeoutException as exc:
            raise ProviderFailure(FailureClass.TIMEOUT_BEFORE_OUTPUT) from exc
        except httpx.HTTPError as exc:
            raise ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID) from exc

    async def aclose(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()

    def _endpoint(self, model: str, *, method: str) -> str:
        project = os.getenv(self._project_env, '').strip()
        location = os.getenv(self._location_env, DEFAULT_GCP_LOCATION).strip()
        if not project or not location:
            raise ProviderFailure(FailureClass.INVALID_CONFIG)
        return (
            f'https://{location}-aiplatform.googleapis.com/{VERTEX_API_VERSION}/projects/{project}'
            f'/locations/{location}/publishers/google/models/{model}:{method}'
        )

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


def _vertex_headers(access_token: str) -> dict[str, str]:
    if not access_token.strip():
        raise ProviderFailure(FailureClass.INVALID_CONFIG)
    return {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
    }


def _vertex_request(request: Mapping[str, Any]) -> dict[str, Any]:
    unsupported_params = sorted(
        key
        for key in (
            'frequency_penalty',
            'logit_bias',
            'logprobs',
            'n',
            'presence_penalty',
            'prompt_cache_key',
            'seed',
            'top_logprobs',
            'user',
        )
        if key in request
    )
    if unsupported_params:
        raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)

    system_parts: list[dict[str, str]] = []
    contents: list[dict[str, Any]] = []
    raw_messages = request.get('messages')
    if not isinstance(raw_messages, list):
        raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
    for message in raw_messages:
        if not isinstance(message, Mapping):
            raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
        role = message.get('role')
        text = _text_content(message.get('content'))
        if role == 'system':
            system_parts.append({'text': text})
            continue
        if role not in {'user', 'assistant'}:
            raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
        contents.append(
            {
                'role': 'model' if role == 'assistant' else 'user',
                'parts': [{'text': text}],
            }
        )

    generation_config: dict[str, Any] = {}
    for request_key, vertex_key in (('temperature', 'temperature'), ('top_p', 'topP')):
        if request_key in request:
            generation_config[vertex_key] = request[request_key]
    if 'stop' in request:
        stop = request['stop']
        if isinstance(stop, str):
            generation_config['stopSequences'] = [stop]
        elif isinstance(stop, list) and all(isinstance(item, str) for item in stop):
            generation_config['stopSequences'] = stop
        else:
            raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
    output_limit = _output_limit(request)
    if output_limit is not None:
        generation_config['maxOutputTokens'] = output_limit
    thinking_budget = _thinking_budget(request)
    if thinking_budget is not None:
        generation_config['thinkingConfig'] = {'thinkingBudget': thinking_budget}
    response_format = request.get('response_format')
    if isinstance(response_format, Mapping):
        json_schema = response_format.get('json_schema')
        if not isinstance(json_schema, Mapping) or not isinstance(json_schema.get('schema'), Mapping):
            raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
        generation_config['responseMimeType'] = 'application/json'
        generation_config['responseSchema'] = dict(cast(Mapping[str, Any], json_schema['schema']))

    payload: dict[str, Any] = {'contents': contents}
    if system_parts:
        payload['systemInstruction'] = {'parts': system_parts}
    if generation_config:
        payload['generationConfig'] = generation_config
    return payload


def _output_limit(request: Mapping[str, Any]) -> int | None:
    max_completion_tokens = request.get('max_completion_tokens')
    max_tokens = request.get('max_tokens')
    value = max_completion_tokens if max_completion_tokens is not None else max_tokens
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
    return value


def _thinking_budget(request: Mapping[str, Any]) -> int | None:
    if request.get('reasoning_effort') == 'none':
        return 0
    extra_body = request.get('extra_body')
    if not isinstance(extra_body, Mapping):
        return None
    google_options = extra_body.get('google')
    if not isinstance(google_options, Mapping):
        return None
    thinking_config = google_options.get('thinking_config')
    if not isinstance(thinking_config, Mapping):
        return None
    thinking_budget = thinking_config.get('thinking_budget')
    if not isinstance(thinking_budget, int) or isinstance(thinking_budget, bool) or thinking_budget < 0:
        raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)
    return thinking_budget


def _vertex_to_openai_response(
    response: Mapping[str, Any],
    *,
    requested_model: str,
    usage: ProviderUsage | None = None,
) -> dict[str, Any]:
    candidates = response.get('candidates')
    candidate = (
        candidates[0] if isinstance(candidates, list) and candidates and isinstance(candidates[0], Mapping) else None
    )
    content = _vertex_candidate_text(candidate)
    finish_reason = _vertex_finish_reason(candidate.get('finishReason') if candidate is not None else 'SAFETY')
    normalized: dict[str, Any] = {
        'id': str(response.get('responseId') or 'vertex_gateway'),
        'object': 'chat.completion',
        'created': int(time.time()),
        'model': requested_model,
        'choices': [
            {
                'index': 0,
                'message': {'role': 'assistant', 'content': content},
                'finish_reason': finish_reason,
            }
        ],
    }
    if usage is not None:
        normalized['usage'] = _openai_usage_payload(usage)
    return normalized


def _vertex_to_openai_stream_chunk(
    response: Mapping[str, Any],
    *,
    requested_model: str,
    usage: ProviderUsage | None = None,
) -> tuple[bytes | None, bool]:
    candidates = response.get('candidates')
    candidate = (
        candidates[0] if isinstance(candidates, list) and candidates and isinstance(candidates[0], Mapping) else None
    )
    if candidate is None and usage is None:
        return None, False
    text = _vertex_candidate_text(candidate)
    raw_finish_reason = candidate.get('finishReason') if candidate is not None else None
    finish_reason = _vertex_finish_reason(raw_finish_reason) if raw_finish_reason else None
    if not text and finish_reason is None and usage is None:
        return None, False
    body: dict[str, Any] = {
        'id': str(response.get('responseId') or 'vertex_gateway'),
        'object': 'chat.completion.chunk',
        'created': int(time.time()),
        'model': requested_model,
        'choices': (
            [
                {
                    'index': 0,
                    'delta': {'content': text} if text else {},
                    'finish_reason': finish_reason,
                }
            ]
            if candidate is not None
            else []
        ),
    }
    if usage is not None:
        body['usage'] = _openai_usage_payload(usage)
    return _openai_sse(body), finish_reason is not None


def _vertex_candidate_text(candidate: Mapping[str, Any] | None) -> str:
    if candidate is None:
        return ''
    content = candidate.get('content')
    if not isinstance(content, Mapping):
        return ''
    parts = content.get('parts')
    if not isinstance(parts, list):
        return ''
    text_parts: list[str] = []
    for part in parts:
        if isinstance(part, Mapping) and isinstance(part.get('text'), str):
            text_parts.append(part['text'])
    return ''.join(text_parts)


def _vertex_finish_reason(value: object) -> str:
    normalized = str(value or '').upper()
    if normalized in {'MAX_TOKENS', 'LENGTH'}:
        return 'length'
    if normalized in {'SAFETY', 'BLOCKLIST', 'PROHIBITED_CONTENT', 'SPII', 'RECITATION'}:
        return 'content_filter'
    return 'stop'


def _openai_sse(body: Mapping[str, Any]) -> bytes:
    return f'data: {json.dumps(dict(body), separators=(",", ":"))}\n\n'.encode('utf-8')


def _openai_sse_done() -> bytes:
    return b'data: [DONE]\n\n'


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


def _openai_usage_payload(usage: ProviderUsage) -> dict[str, Any]:
    return {
        'prompt_tokens': usage.prompt_tokens,
        'completion_tokens': usage.output_tokens + usage.reasoning_tokens,
        'total_tokens': usage.total_tokens,
        'prompt_tokens_details': {'cached_tokens': usage.cached_input_tokens},
        'completion_tokens_details': {'reasoning_tokens': usage.reasoning_tokens},
    }


def _text_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in cast(list[object], content):
            if not isinstance(part, Mapping):
                continue
            typed_part = cast(Mapping[str, Any], part)
            if typed_part.get('type') == 'text' and isinstance(typed_part.get('text'), str):
                parts.append(typed_part['text'])
        return '\n'.join(parts)
    return ''


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
