"""Gateway-first Anthropic Messages client with direct transport fallback."""

from __future__ import annotations

import anthropic
import httpx

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
_GATEWAY_CLIENT_CACHE: dict[str, anthropic.AsyncAnthropic] = {}


def get_gateway_first_anthropic_client(
    *,
    legacy_client: anthropic.AsyncAnthropic,
    agent_model: str,
) -> anthropic.AsyncAnthropic | _GatewayFirstAnthropicClient:
    if not should_route_features_through_gateway():
        return legacy_client
    gateway_client = _get_or_create_gateway_anthropic_client()
    return _GatewayFirstAnthropicClient(
        gateway_client=gateway_client,
        legacy_client=legacy_client,
        agent_model=agent_model,
    )


def _get_or_create_gateway_anthropic_client() -> anthropic.AsyncAnthropic:
    token = get_llm_gateway_service_token() or 'gateway-dev'
    cached = _GATEWAY_CLIENT_CACHE.get(token)
    if cached is not None:
        return cached
    client = anthropic.AsyncAnthropic(
        api_key='gateway-managed',
        base_url=get_llm_gateway_base_url(),
        timeout=120.0,
        max_retries=0,
        default_headers={
            'Authorization': f'Bearer {token}',
            'X-Omi-Service-Caller': 'backend',
        },
    )
    _GATEWAY_CLIENT_CACHE[token] = client
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
        gateway_messages: anthropic.resources.messages.AsyncMessages,
        legacy_messages: anthropic.resources.messages.AsyncMessages,
        agent_model: str,
    ) -> None:
        self._gateway_messages = gateway_messages
        self._legacy_messages = legacy_messages
        self._agent_model = agent_model

    def stream(self, **kwargs):
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

    async def create(self, **kwargs):
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
        gateway_messages: anthropic.resources.messages.AsyncMessages,
        legacy_messages: anthropic.resources.messages.AsyncMessages,
        gateway_kwargs: dict,
        legacy_kwargs: dict,
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

    async def __aexit__(self, exc_type, exc, tb):
        if self._active is None:
            return None
        return await self._active.__aexit__(exc_type, exc, tb)

    def __aiter__(self):
        if self._active is None:
            raise RuntimeError('stream context is not active')
        return self._active.__aiter__()

    async def get_final_message(self):
        if self._active is None:
            raise RuntimeError('stream context is not active')
        return await self._active.get_final_message()

    async def __anext__(self):
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
