from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
import os
from typing import Any, Protocol

import httpx

from llm_gateway.gateway.credentials import CredentialContext
from llm_gateway.gateway.schemas import CredentialMode, FailureClass, ProviderRef

OPENAI_API_KEY_ENV_VAR = 'OPENAI_API_KEY'
OPENAI_BASE_URL_ENV_VAR = 'OPENAI_BASE_URL'
DEFAULT_OPENAI_BASE_URL = 'https://api.openai.com/v1'


class ChatCompletionProvider(Protocol):
    async def create_chat_completion(
        self,
        request: Mapping[str, Any],
        *,
        provider_ref: ProviderRef,
        credentials: CredentialContext,
        timeout_ms: int,
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class ProviderFailure(Exception):
    failure_class: FailureClass
    safe_message: str = 'provider request failed'

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
            response = await self._http_client.post(
                f'{self._base_url}/chat/completions',
                json=dict(request),
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                },
                timeout=timeout_ms / 1000.0,
            )
        except httpx.TimeoutException as exc:
            raise ProviderFailure(FailureClass.TIMEOUT_BEFORE_OUTPUT) from exc
        except httpx.HTTPError as exc:
            raise ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID) from exc

        if response.status_code in {401, 403}:
            raise ProviderFailure(FailureClass.INVALID_CONFIG)
        if response.status_code == 429:
            raise ProviderFailure(FailureClass.PROVIDER_429_OMI_PAID)
        if response.status_code >= 500:
            raise ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID)
        if response.status_code >= 400:
            raise ProviderFailure(FailureClass.CAPABILITY_MISMATCH)

        try:
            parsed = response.json()
        except ValueError as exc:
            raise ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID) from exc
        if not isinstance(parsed, Mapping):
            raise ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID)
        return parsed


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
