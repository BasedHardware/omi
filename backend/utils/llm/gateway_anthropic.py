"""Gateway-first Anthropic Messages client with direct transport fallback."""

from __future__ import annotations

import hashlib
from typing import Any

import anthropic
import httpx
from cachetools import TTLCache

from utils.llm.gateway_byok import byok_gateway_default_headers
from utils.llm.gateway_client import (
    CHAT_AGENT_AUTO_LANE_ID,
    feature_auto_lane_id,
    get_llm_gateway_base_url,
    get_llm_gateway_service_token,
    should_route_features_through_gateway,
)
from utils.llm.gateway_observability import record_gateway_request_result
from utils.llm.gateway_serving import is_gateway_transport_failure

_CHAT_AGENT_FEATURE = 'chat_agent'
_GATEWAY_CLIENT_CACHE_MAX_SIZE = 256
_GATEWAY_CLIENT_CACHE_TTL_SECONDS = 3600
_GATEWAY_CLIENT_CACHE: TTLCache[str, anthropic.AsyncAnthropic] = TTLCache(
    maxsize=_GATEWAY_CLIENT_CACHE_MAX_SIZE,
    ttl=_GATEWAY_CLIENT_CACHE_TTL_SECONDS,
)


def get_gateway_first_anthropic_client(
    *,
    legacy_client: anthropic.AsyncAnthropic,
    agent_model: str,
    byok_api_key: str | None = None,
) -> anthropic.AsyncAnthropic | _GatewayFirstAnthropicClient:
    if not should_route_features_through_gateway():
        return legacy_client
    gateway_client = _get_or_create_gateway_anthropic_client(byok_api_key=byok_api_key)
    return _GatewayFirstAnthropicClient(
        gateway_client=gateway_client,
        legacy_client=legacy_client,
        agent_model=agent_model,
    )


def _get_or_create_gateway_anthropic_client(*, byok_api_key: str | None = None) -> anthropic.AsyncAnthropic:
    token = get_llm_gateway_service_token() or 'gateway-dev'
    byok_fingerprint = 'none'
    if byok_api_key:
        byok_fingerprint = hashlib.sha256(byok_api_key.encode()).hexdigest()[:16]
    cache_key = f'{token}:{byok_fingerprint}'
    cached = _GATEWAY_CLIENT_CACHE.get(cache_key)
    if cached is not None:
        return cached
    default_headers = {
        'Authorization': f'Bearer {token}',
        'X-Omi-Service-Caller': 'backend',
    }
    if byok_api_key:
        default_headers.update(byok_gateway_default_headers('anthropic', byok_api_key))
    client = anthropic.AsyncAnthropic(
        api_key='gateway-managed',
        base_url=get_llm_gateway_base_url(),
        timeout=120.0,
        max_retries=0,
        default_headers=default_headers,
    )
    _GATEWAY_CLIENT_CACHE[cache_key] = client
    return client


class _GatewayFirstAnthropicClient:
    """Proxy AsyncAnthropic that routes messages.* through gateway with transport fallback."""

    def __init__(
        self,
        *,
        gateway_client: anthropic.AsyncAnthropic,
        legacy_client: anthropic.AsyncAnthropic,
        agent_model: str,
    ) -> None:
        self._gateway_client = gateway_client
        self._legacy_client = legacy_client
        self._agent_model = agent_model
        self.messages = _GatewayFirstAnthropicMessages(
            gateway_messages=gateway_client.messages,
            legacy_messages=legacy_client.messages,
            agent_model=agent_model,
        )

    def __getattr__(self, name: str):
        return getattr(self._legacy_client, name)


class _GatewayFirstAnthropicMessages:
    def __init__(
        self,
        *,
        gateway_messages: Any,
        legacy_messages: Any,
        agent_model: str,
    ) -> None:
        self._gateway_messages = gateway_messages
        self._legacy_messages = legacy_messages
        self._agent_model = agent_model

    def stream(self, **kwargs: Any) -> '_GatewayAnthropicStreamWithFallback':
        gateway_kwargs = dict(kwargs)
        gateway_kwargs['model'] = CHAT_AGENT_AUTO_LANE_ID
        legacy_kwargs = dict(kwargs)
        legacy_kwargs['model'] = self._agent_model
        return _GatewayAnthropicStreamWithFallback(
            gateway_messages=self._gateway_messages,
            legacy_messages=self._legacy_messages,
            gateway_kwargs=gateway_kwargs,
            legacy_kwargs=legacy_kwargs,
        )

    async def create(self, **kwargs: Any) -> Any:
        gateway_kwargs = dict(kwargs)
        gateway_kwargs['model'] = CHAT_AGENT_AUTO_LANE_ID
        try:
            result = await self._gateway_messages.create(**gateway_kwargs)
        except Exception as exc:
            if not is_gateway_transport_failure(exc):
                raise
            record_gateway_request_result(
                feature=_CHAT_AGENT_FEATURE,
                outcome='fallback',
                reason=_fallback_reason(exc),
                route=feature_auto_lane_id(_CHAT_AGENT_FEATURE),
                mode='fallback',
            )
            return await self._legacy_messages.create(**kwargs)
        record_gateway_request_result(
            feature=_CHAT_AGENT_FEATURE,
            outcome='success',
            reason='ok',
            route=feature_auto_lane_id(_CHAT_AGENT_FEATURE),
            mode='serving',
        )
        return result


class _GatewayAnthropicStreamWithFallback:
    def __init__(
        self,
        *,
        gateway_messages: Any,
        legacy_messages: Any,
        gateway_kwargs: dict[str, Any],
        legacy_kwargs: dict[str, Any],
    ) -> None:
        self._gateway_messages = gateway_messages
        self._legacy_messages = legacy_messages
        self._gateway_kwargs = gateway_kwargs
        self._legacy_kwargs = legacy_kwargs
        self._active = None
        self._started = False

    async def __aenter__(self):
        try:
            self._active = await self._gateway_messages.stream(**self._gateway_kwargs).__aenter__()
        except Exception as exc:
            if not is_gateway_transport_failure(exc):
                raise
            record_gateway_request_result(
                feature=_CHAT_AGENT_FEATURE,
                outcome='fallback',
                reason=_fallback_reason(exc),
                route=feature_auto_lane_id(_CHAT_AGENT_FEATURE),
                mode='fallback',
            )
            self._active = await self._legacy_messages.stream(**self._legacy_kwargs).__aenter__()
            return self
        self._started = True
        record_gateway_request_result(
            feature=_CHAT_AGENT_FEATURE,
            outcome='success',
            reason='ok',
            route=feature_auto_lane_id(_CHAT_AGENT_FEATURE),
            mode='serving',
        )
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> Any:
        if self._active is None:
            return None
        return await self._active.__aexit__(exc_type, exc, tb)

    def __aiter__(self) -> Any:
        if self._active is None:
            raise RuntimeError('stream context is not active')
        return self._active.__aiter__()

    async def get_final_message(self) -> Any:
        if self._active is None:
            raise RuntimeError('stream context is not active')
        return await self._active.get_final_message()

    async def __anext__(self) -> Any:
        if self._active is None:
            raise RuntimeError('stream context is not active')
        return await self._active.__anext__()


def _fallback_reason(exc: BaseException) -> str:
    if 'timeout' in str(exc).casefold():
        return 'timeout'
    if isinstance(exc, httpx.TimeoutException):
        return 'timeout'
    if isinstance(exc, (httpx.NetworkError, httpx.RemoteProtocolError, httpx.ConnectError)):
        return 'request_error'
    status_code = getattr(exc, 'status_code', None)
    if isinstance(status_code, int) and status_code in {502, 503, 504}:
        return 'request_error'
    return 'unexpected_error'
