from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
import json
import os
from typing import Any, Protocol

import httpx

from llm_gateway.gateway.credentials import CredentialContext
from llm_gateway.gateway.schemas import CredentialMode, FailureClass, ProviderRef
from utils.log_sanitizer import sanitize

OPENAI_API_KEY_ENV_VAR = 'OPENAI_API_KEY'
OPENAI_BASE_URL_ENV_VAR = 'OPENAI_BASE_URL'
DEFAULT_OPENAI_BASE_URL = 'https://api.openai.com/v1'
DEFAULT_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_RESPONSE_BYTES_ENV_VAR = 'OPENAI_MAX_RESPONSE_BYTES'
PROVIDER_ERROR_DETAIL_BYTES = 1000
EXPOSE_PROVIDER_ERROR_DETAILS_ENV_VAR = 'LLM_GATEWAY_EXPOSE_PROVIDER_ERROR_DETAILS'
GENERIC_PROVIDER_FAILURE_MESSAGE = 'provider request failed'


class ChatCompletionProvider(Protocol):
    async def create_chat_completion(
        self,
        request: Mapping[str, Any],
        *,
        provider_ref: ProviderRef,
        credentials: CredentialContext,
        timeout_ms: int,
    ) -> Mapping[str, Any]: ...


@dataclass
class ProviderFailure(Exception):
    failure_class: FailureClass
    safe_message: str = GENERIC_PROVIDER_FAILURE_MESSAGE

    def __str__(self) -> str:
        return self.safe_message


class OpenAICompatibleChatCompletionProvider:
    def __init__(
        self,
        *,
        api_key_env: str = OPENAI_API_KEY_ENV_VAR,
        base_url: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key_env = api_key_env
        self._base_url = (base_url or os.getenv(OPENAI_BASE_URL_ENV_VAR, DEFAULT_OPENAI_BASE_URL)).rstrip('/')
        self._http_client = http_client or httpx.AsyncClient()
        self._owns_http_client = http_client is None

    async def create_chat_completion(
        self,
        request: Mapping[str, Any],
        *,
        provider_ref: ProviderRef,
        credentials: CredentialContext,
        timeout_ms: int,
    ) -> Mapping[str, Any]:
        if credentials.mode == CredentialMode.BYOK:
            raise ProviderFailure(FailureClass.BYOK_UNSUPPORTED_PROVIDER)

        api_key = os.getenv(self._api_key_env, '').strip()
        if not api_key:
            raise ProviderFailure(FailureClass.INVALID_CONFIG)

        try:
            async with self._http_client.stream(
                'POST',
                f'{self._base_url}/chat/completions',
                json=dict(request),
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
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
                    _raise_for_status(status_code, error_preview)
                body = await _read_limited_response(response, max_bytes=_configured_max_response_bytes())
                parsed = _parse_limited_json_response(body)
        except httpx.TimeoutException as exc:
            raise ProviderFailure(FailureClass.TIMEOUT_BEFORE_OUTPUT) from exc
        except httpx.HTTPError as exc:
            raise ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID) from exc

        _validate_chat_completion_response_shape(parsed)
        return parsed

    async def aclose(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()


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
    ) -> Mapping[str, Any]:
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
            return _default_fake_response(provider_ref)

        outcome = self._outcomes.popleft()
        if isinstance(outcome, ProviderFailure):
            raise outcome
        return outcome


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


def _raise_for_status(status_code: int, body: bytes = b'') -> None:
    if status_code in {401, 403}:
        raise ProviderFailure(FailureClass.INVALID_CONFIG, safe_message=_provider_error_message(status_code, body))
    if status_code == 408:
        raise ProviderFailure(
            FailureClass.TIMEOUT_BEFORE_OUTPUT, safe_message=_provider_error_message(status_code, body)
        )
    if status_code == 429:
        raise ProviderFailure(
            FailureClass.PROVIDER_429_OMI_PAID, safe_message=_provider_error_message(status_code, body)
        )
    if status_code >= 500:
        raise ProviderFailure(
            FailureClass.PROVIDER_5XX_OMI_PAID, safe_message=_provider_error_message(status_code, body)
        )
    if status_code >= 400:
        raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH, safe_message=_provider_error_message(status_code, body))


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
        parsed = json.loads(body)
    except ValueError as exc:
        raise ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID) from exc
    if not isinstance(parsed, Mapping):
        raise ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID)
    return parsed


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
    for choice in choices:
        if not isinstance(choice, Mapping):
            raise ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID)
        message = choice.get('message')
        if not isinstance(message, Mapping) or message.get('role') != 'assistant':
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
