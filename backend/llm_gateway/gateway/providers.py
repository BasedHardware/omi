from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from llm_gateway.gateway.credentials import CredentialContext
from llm_gateway.gateway.schemas import FailureClass, ProviderRef


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
