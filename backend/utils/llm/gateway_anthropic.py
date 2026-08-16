"""Gateway-only Anthropic Messages client."""

from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from collections.abc import Mapping
from typing import Any, cast

import anthropic
import httpx
from cachetools import TTLCache

from utils.llm.gateway_byok import byok_gateway_default_headers
from utils.llm.gateway_client import (
    CHAT_AGENT_AUTO_LANE_ID,
    feature_auto_lane_id,
    get_llm_gateway_base_url,
    get_llm_gateway_service_token,
    llm_gateway_headers,
)
from utils.llm.gateway_observability import record_gateway_request_result
from utils.llm.gateway_resilience import gateway_circuit, gateway_transport_timeout, observe_gateway_first_byte
from utils.llm.gateway_serving import is_gateway_transport_failure

_CHAT_AGENT_FEATURE = 'chat_agent'
_GATEWAY_CLIENT_CACHE_MAX_SIZE = 256
_GATEWAY_CLIENT_CACHE_TTL_SECONDS = 3600
_GATEWAY_CLIENT_CACHE: TTLCache[str, anthropic.AsyncAnthropic] = TTLCache(
    maxsize=_GATEWAY_CLIENT_CACHE_MAX_SIZE,
    ttl=_GATEWAY_CLIENT_CACHE_TTL_SECONDS,
)
_REQUEST_ID_HEADER = 'X-Omi-Request-ID'


class LlmGatewayUnavailableError(RuntimeError):
    """The gateway could not accept or complete an Anthropic Messages request."""


def _gateway_request_headers(existing: object) -> dict[str, str]:
    headers = dict(existing) if isinstance(existing, Mapping) else {}
    headers.update(llm_gateway_headers(feature=_CHAT_AGENT_FEATURE))
    return headers


def get_gateway_anthropic_client(
    *,
    byok_api_key: str | None = None,
) -> '_GatewayAnthropicClient':
    gateway_client = _get_or_create_gateway_anthropic_client(byok_api_key=byok_api_key)
    return _GatewayAnthropicClient(
        gateway_client=gateway_client,
        credential_source='service_forwarded_byok' if byok_api_key else 'omi_managed',
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
        timeout=gateway_transport_timeout(),
        max_retries=0,
        default_headers=default_headers,
    )
    _GATEWAY_CLIENT_CACHE[cache_key] = client
    return client


class _GatewayAnthropicClient:
    """Proxy AsyncAnthropic that routes messages.* through the gateway and fails closed."""

    def __init__(
        self,
        *,
        gateway_client: anthropic.AsyncAnthropic,
        credential_source: str,
    ) -> None:
        self._gateway_client = gateway_client
        self.messages = _GatewayAnthropicMessages(
            gateway_messages=gateway_client.messages,
            credential_source=credential_source,
        )

    def __getattr__(self, name: str):
        raise AttributeError(f'gateway-only Anthropic client does not expose direct method {name!r}')


class _GatewayAnthropicMessages:
    def __init__(
        self,
        *,
        gateway_messages: Any,
        credential_source: str,
    ) -> None:
        self._gateway_messages = gateway_messages
        self._credential_source = credential_source

    def stream(self, **kwargs: Any) -> '_GatewayAnthropicStream':
        gateway_kwargs = dict(kwargs)
        gateway_kwargs['model'] = CHAT_AGENT_AUTO_LANE_ID
        gateway_kwargs['extra_headers'] = _gateway_request_headers(gateway_kwargs.get('extra_headers'))
        return _GatewayAnthropicStream(
            gateway_messages=self._gateway_messages,
            gateway_kwargs=gateway_kwargs,
            credential_source=self._credential_source,
        )

    async def create(self, **kwargs: Any) -> Any:
        gateway_kwargs = dict(kwargs)
        gateway_kwargs['model'] = CHAT_AGENT_AUTO_LANE_ID
        gateway_kwargs['extra_headers'] = _gateway_request_headers(gateway_kwargs.get('extra_headers'))
        request_id = _set_request_id(gateway_kwargs)
        if not gateway_circuit.allow_request():
            _record_gateway_unavailable(
                request_id=request_id, reason='circuit_open', credential_source=self._credential_source
            )
            raise LlmGatewayUnavailableError('LLM gateway circuit is open')
        gateway_started_at = time.monotonic()
        try:
            result = await self._gateway_messages.create(**gateway_kwargs)
        except asyncio.CancelledError:
            record_gateway_request_result(
                feature=_CHAT_AGENT_FEATURE,
                outcome='cancelled',
                reason='client_cancelled',
                route=feature_auto_lane_id(_CHAT_AGENT_FEATURE),
                mode='serving',
                request_id=request_id,
                credential_source=self._credential_source,
            )
            raise
        except Exception as exc:
            if not is_gateway_transport_failure(exc):
                record_gateway_request_result(
                    feature=_CHAT_AGENT_FEATURE,
                    outcome='error',
                    reason=_gateway_error_reason(exc),
                    route=feature_auto_lane_id(_CHAT_AGENT_FEATURE),
                    mode='serving',
                    request_id=request_id,
                    credential_source=self._credential_source,
                )
                raise
            gateway_circuit.record_transport_failure()
            observe_gateway_first_byte(
                feature=_CHAT_AGENT_FEATURE, started_at=gateway_started_at, outcome='transport_failure'
            )
            reason = _fallback_reason(exc)
            _record_gateway_unavailable(request_id=request_id, reason=reason, credential_source=self._credential_source)
            raise LlmGatewayUnavailableError('LLM gateway unavailable') from exc
        gateway_circuit.record_transport_success()
        observe_gateway_first_byte(feature=_CHAT_AGENT_FEATURE, started_at=gateway_started_at, outcome='success')
        record_gateway_request_result(
            feature=_CHAT_AGENT_FEATURE,
            outcome='success',
            reason='ok',
            route=feature_auto_lane_id(_CHAT_AGENT_FEATURE),
            mode='serving',
            request_id=request_id,
            credential_source=self._credential_source,
        )
        return result


class _GatewayAnthropicStream:
    def __init__(
        self,
        *,
        gateway_messages: Any,
        gateway_kwargs: dict[str, Any],
        credential_source: str,
    ) -> None:
        self._gateway_messages = gateway_messages
        self._gateway_kwargs = gateway_kwargs
        self._credential_source = credential_source
        self._request_id = _set_request_id(self._gateway_kwargs)
        self._active = None
        self._iterator = None
        self._using_gateway = False
        self._saw_output = False
        self._terminal_recorded = False
        self._gateway_started_at: float | None = None

    async def __aenter__(self):
        if not gateway_circuit.allow_request():
            _record_gateway_unavailable(
                request_id=self._request_id,
                reason='circuit_open',
                credential_source=self._credential_source,
            )
            self._terminal_recorded = True
            raise LlmGatewayUnavailableError('LLM gateway circuit is open')
        self._gateway_started_at = time.monotonic()
        try:
            self._active = await self._gateway_messages.stream(**self._gateway_kwargs).__aenter__()
        except asyncio.CancelledError:
            record_gateway_request_result(
                feature=_CHAT_AGENT_FEATURE,
                outcome='cancelled',
                reason='client_cancelled',
                route=feature_auto_lane_id(_CHAT_AGENT_FEATURE),
                mode='serving',
                request_id=self._request_id,
                credential_source=self._credential_source,
            )
            self._terminal_recorded = True
            raise
        except Exception as exc:
            if not is_gateway_transport_failure(exc):
                record_gateway_request_result(
                    feature=_CHAT_AGENT_FEATURE,
                    outcome='error',
                    reason=_gateway_error_reason(exc),
                    route=feature_auto_lane_id(_CHAT_AGENT_FEATURE),
                    mode='serving',
                    request_id=self._request_id,
                    credential_source=self._credential_source,
                )
                self._terminal_recorded = True
                raise
            gateway_circuit.record_transport_failure()
            self._observe_gateway_first_byte('transport_failure')
            _record_gateway_unavailable(
                request_id=self._request_id,
                reason=_fallback_reason(exc),
                credential_source=self._credential_source,
            )
            self._terminal_recorded = True
            raise LlmGatewayUnavailableError('LLM gateway unavailable') from exc
        self._using_gateway = True
        return self

    async def _close_failed_gateway_stream(self, *, error: BaseException | None) -> None:
        active = self._active
        self._active = None
        self._iterator = None
        self._using_gateway = False
        if active is not None:
            try:
                if error is None:
                    await active.__aexit__(None, None, None)
                else:
                    await active.__aexit__(type(error), error, error.__traceback__)
            except asyncio.CancelledError:
                raise
            except Exception:
                # The transport failure is already known and remains the request error.
                pass

    def _observe_gateway_first_byte(self, outcome: str) -> None:
        if self._gateway_started_at is None:
            return
        observe_gateway_first_byte(
            feature=_CHAT_AGENT_FEATURE,
            started_at=self._gateway_started_at,
            outcome=outcome,
        )
        self._gateway_started_at = None

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> Any:
        if self._active is None:
            return None
        try:
            return await self._active.__aexit__(exc_type, exc, tb)
        except asyncio.CancelledError:
            if self._should_record_terminal():
                self._record_terminal(outcome='cancelled', reason='client_cancelled')
            raise
        except Exception as exit_error:
            if self._should_record_terminal():
                self._record_terminal(outcome='error', reason=f'stream_exit_{_gateway_error_reason(exit_error)}')
            raise
        finally:
            if self._should_record_terminal():
                if exc_type is None:
                    self._record_terminal(outcome='cancelled', reason='consumer_abandoned_stream')
                elif _is_cancelled_exception_type(exc_type):
                    self._record_terminal(outcome='cancelled', reason='client_cancelled')
                else:
                    self._record_terminal(outcome='error', reason='consumer_stream_exception')

    def __aiter__(self) -> Any:
        if self._active is None:
            raise RuntimeError('stream context is not active')
        if self._iterator is None:
            self._iterator = self._active.__aiter__()
        return self

    async def get_final_message(self) -> Any:
        if self._active is None:
            raise RuntimeError('stream context is not active')
        try:
            message = await self._active.get_final_message()
        except (asyncio.CancelledError, GeneratorExit):
            if self._should_record_terminal():
                self._record_terminal(outcome='cancelled', reason='client_cancelled')
            raise
        except Exception as exc:
            if self._should_record_terminal():
                phase = 'midstream' if self._saw_output else 'before_output'
                self._record_terminal(outcome='error', reason=f'stream_{phase}_{_gateway_error_reason(exc)}')
            raise
        if self._should_record_terminal():
            self._record_terminal(outcome='success', reason='ok')
        return message

    async def __anext__(self) -> Any:
        if self._active is None:
            raise RuntimeError('stream context is not active')
        if self._iterator is None:
            self.__aiter__()
        iterator = self._iterator
        if iterator is None:
            raise RuntimeError('stream iterator is not active')
        try:
            event = await iterator.__anext__()
        except (asyncio.CancelledError, GeneratorExit):
            if self._should_record_terminal():
                self._record_terminal(outcome='cancelled', reason='client_cancelled')
            raise
        except StopAsyncIteration:
            if self._using_gateway and not self._saw_output:
                await self._close_failed_gateway_stream(error=None)
                _record_gateway_unavailable(
                    request_id=self._request_id,
                    reason='empty_stream_before_output',
                    credential_source=self._credential_source,
                )
                self._terminal_recorded = True
                raise LlmGatewayUnavailableError('LLM gateway returned an empty stream')
            if self._should_record_terminal():
                self._record_terminal(outcome='error', reason='stream_eof_before_message_stop')
            raise
        except Exception as exc:
            if self._using_gateway and not self._saw_output and is_gateway_transport_failure(exc):
                gateway_circuit.record_transport_failure()
                self._observe_gateway_first_byte('transport_failure')
                await self._close_failed_gateway_stream(error=exc)
                _record_gateway_unavailable(
                    request_id=self._request_id,
                    reason=_fallback_reason(exc),
                    credential_source=self._credential_source,
                )
                self._terminal_recorded = True
                raise LlmGatewayUnavailableError('LLM gateway unavailable') from exc
            if self._should_record_terminal():
                phase = 'midstream' if self._saw_output else 'before_output'
                self._record_terminal(outcome='error', reason=f'stream_{phase}_{_gateway_error_reason(exc)}')
            raise

        if self._using_gateway and not self._saw_output:
            gateway_circuit.record_transport_success()
            self._observe_gateway_first_byte('success')
        self._saw_output = True
        event_type = getattr(event, 'type', None)
        if event_type == 'message_stop' and self._should_record_terminal():
            self._record_terminal(outcome='success', reason='ok')
        elif event_type == 'error' and self._should_record_terminal():
            self._record_terminal(outcome='error', reason='provider_error_event')
        return event

    def _should_record_terminal(self) -> bool:
        return self._using_gateway and not self._terminal_recorded

    def _record_terminal(self, *, outcome: str, reason: str) -> None:
        if self._terminal_recorded:
            return
        self._terminal_recorded = True
        record_gateway_request_result(
            feature=_CHAT_AGENT_FEATURE,
            outcome=outcome,
            reason=reason,
            route=feature_auto_lane_id(_CHAT_AGENT_FEATURE),
            mode='serving',
            request_id=self._request_id,
            credential_source=self._credential_source,
        )


def _record_gateway_unavailable(*, request_id: str, reason: str, credential_source: str) -> None:
    record_gateway_request_result(
        feature=_CHAT_AGENT_FEATURE,
        outcome='error',
        reason=reason,
        route=feature_auto_lane_id(_CHAT_AGENT_FEATURE),
        mode='serving',
        request_id=request_id,
        credential_source=credential_source,
    )


def _is_cancelled_exception_type(exc_type: Any) -> bool:
    return isinstance(exc_type, type) and issubclass(exc_type, (asyncio.CancelledError, GeneratorExit))


def _set_request_id(kwargs: dict[str, Any]) -> str:
    request_id = str(uuid.uuid4())
    raw_headers = kwargs.get('extra_headers')
    headers: dict[str, str] = dict(cast(Mapping[str, str], raw_headers)) if isinstance(raw_headers, Mapping) else {}
    headers[_REQUEST_ID_HEADER] = request_id
    kwargs['extra_headers'] = headers
    return request_id


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


def _gateway_error_reason(exc: BaseException) -> str:
    reason = _fallback_reason(exc)
    if reason != 'unexpected_error':
        return reason
    status_code = getattr(exc, 'status_code', None)
    if not isinstance(status_code, int):
        response = getattr(exc, 'response', None)
        status_code = getattr(response, 'status_code', None)
    if status_code in {401, 403}:
        return 'auth'
    if status_code == 429:
        return 'rate_limit'
    if isinstance(status_code, int) and 400 <= status_code < 500:
        return 'request_rejected'
    return 'unexpected_error'
