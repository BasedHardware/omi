"""Shared provider result/failure types (dependency-free: schemas + accounting only)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from llm_gateway.gateway.accounting import ProviderResponseMetadata, ProviderUsage
from llm_gateway.gateway.schemas import FailureClass, ProviderRejection

GENERIC_PROVIDER_FAILURE_MESSAGE = 'provider request failed'


@dataclass
class _VertexHttpError(Exception):
    """A Vertex response the PT ladder may route around (429/404/5xx)."""

    status_code: int
    preview: bytes


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


def _openai_usage_payload(usage: ProviderUsage) -> dict[str, Any]:
    return {
        'prompt_tokens': usage.prompt_tokens,
        'completion_tokens': usage.output_tokens + usage.reasoning_tokens,
        'total_tokens': usage.total_tokens,
        'prompt_tokens_details': {'cached_tokens': usage.cached_input_tokens},
        'completion_tokens_details': {'reasoning_tokens': usage.reasoning_tokens},
    }


__all__ = [
    "GENERIC_PROVIDER_FAILURE_MESSAGE",
    "ProviderFailure",
    "ProviderResponse",
    "_VertexHttpError",
    "_openai_usage_payload",
]
