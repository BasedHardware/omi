"""Gateway-first serving with legacy provider fallback on hard transport failures."""

from __future__ import annotations

from typing import Any, Iterator

try:
    from langchain_core.callbacks.manager import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
except ImportError:
    try:
        from langchain_core.callbacks import BaseCallbackHandler as CallbackManagerForLLMRun
    except ImportError:
        CallbackManagerForLLMRun = Any  # type: ignore[misc,assignment]

    AsyncCallbackManagerForLLMRun = CallbackManagerForLLMRun  # type: ignore[misc,assignment]
from langchain_core.language_models import BaseChatModel

try:
    from langchain_core.messages import BaseMessage
except ImportError:
    BaseMessage = None  # type: ignore[assignment,misc]
try:
    from langchain_core.outputs import ChatResult
except ImportError:
    ChatResult = Any  # type: ignore[misc,assignment]
try:
    from langchain_core.runnables import Runnable
except ImportError:

    class Runnable:  # type: ignore[no-redef]
        pass


import httpx
from pydantic import ConfigDict

from utils.llm.gateway_client import feature_auto_lane_id
from utils.llm.gateway_observability import record_gateway_request_result

_TRANSPORT_STATUS_CODES = frozenset({502, 503, 504})


def wrap_gateway_with_legacy_fallback(
    *,
    feature: str,
    gateway_model: BaseChatModel,
    legacy_model: BaseChatModel,
) -> BaseChatModel:
    return GatewayWithLegacyFallbackChatModel(
        feature=feature,
        gateway_model=gateway_model,
        legacy_model=legacy_model,
    )


def is_gateway_transport_failure(exc: BaseException) -> bool:
    """Return True for gateway unreachable / hard HTTP failures that should fall back."""
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response is not None and exc.response.status_code in _TRANSPORT_STATUS_CODES

    status_code = getattr(exc, 'status_code', None)
    if isinstance(status_code, int) and status_code in _TRANSPORT_STATUS_CODES:
        return True

    response = getattr(exc, 'response', None)
    response_status = getattr(response, 'status_code', None)
    if isinstance(response_status, int) and response_status in _TRANSPORT_STATUS_CODES:
        return True

    message = str(exc).casefold()
    transport_markers = (
        'timeout',
        'timed out',
        'connection refused',
        'connection reset',
        'connecterror',
        'network error',
        'bad gateway',
        'service unavailable',
        'gateway timeout',
        '502',
        '503',
        '504',
    )
    return any(marker in message for marker in transport_markers)


def _fallback_reason(exc: BaseException) -> str:
    if (
        isinstance(exc, httpx.TimeoutException)
        or 'timeout' in str(exc).casefold()
        or 'timed out' in str(exc).casefold()
    ):
        return 'timeout'
    if isinstance(exc, (httpx.NetworkError, httpx.RemoteProtocolError)):
        return 'request_error'
    status_code = getattr(exc, 'status_code', None)
    if not isinstance(status_code, int):
        response = getattr(exc, 'response', None)
        status_code = getattr(response, 'status_code', None)
    if isinstance(status_code, int) and status_code in _TRANSPORT_STATUS_CODES:
        return 'request_error'
    return 'unexpected_error'


class GatewayWithLegacyFallbackChatModel(BaseChatModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    feature: str
    gateway_model: BaseChatModel
    legacy_model: BaseChatModel

    @property
    def _llm_type(self) -> str:
        return f'{getattr(self.gateway_model, "_llm_type", "chat")}-omi-gateway-fallback'

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        try:
            result = self.gateway_model._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        except Exception as exc:
            if not is_gateway_transport_failure(exc):
                raise
            record_gateway_request_result(
                feature=self.feature,
                outcome='fallback',
                reason=_fallback_reason(exc),
                route=feature_auto_lane_id(self.feature),
            )
            return self.legacy_model._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

        record_gateway_request_result(
            feature=self.feature,
            outcome='success',
            reason='ok',
            route=feature_auto_lane_id(self.feature),
        )
        return result

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        try:
            result = await self.gateway_model._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)
        except Exception as exc:
            if not is_gateway_transport_failure(exc):
                raise
            record_gateway_request_result(
                feature=self.feature,
                outcome='fallback',
                reason=_fallback_reason(exc),
                route=feature_auto_lane_id(self.feature),
            )
            return await self.legacy_model._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)

        record_gateway_request_result(
            feature=self.feature,
            outcome='success',
            reason='ok',
            route=feature_auto_lane_id(self.feature),
        )
        return result

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[Any]:
        try:
            stream = self.gateway_model._stream(messages, stop=stop, run_manager=run_manager, **kwargs)
            yielded = False
            for chunk in stream:
                yielded = True
                yield chunk
            if yielded:
                record_gateway_request_result(
                    feature=self.feature,
                    outcome='success',
                    reason='ok',
                    route=feature_auto_lane_id(self.feature),
                )
            return
        except Exception as exc:
            if not is_gateway_transport_failure(exc):
                raise
            record_gateway_request_result(
                feature=self.feature,
                outcome='fallback',
                reason=_fallback_reason(exc),
                route=feature_auto_lane_id(self.feature),
            )
            yield from self.legacy_model._stream(messages, stop=stop, run_manager=run_manager, **kwargs)

    def with_structured_output(self, schema: dict[str, Any] | type, *, include_raw: bool = False, **kwargs: Any):
        gateway = self.gateway_model.with_structured_output(schema, include_raw=include_raw, **kwargs)
        legacy = self.legacy_model.with_structured_output(schema, include_raw=include_raw, **kwargs)
        return GatewayWithLegacyFallbackRunnable(feature=self.feature, gateway=gateway, legacy=legacy)


class GatewayWithLegacyFallbackRunnable(Runnable):
    def __init__(self, *, feature: str, gateway: Runnable, legacy: Runnable):
        self._feature = feature
        self._gateway = gateway
        self._legacy = legacy

    def invoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        try:
            result = self._gateway.invoke(input, config=config, **kwargs)
        except Exception as exc:
            if not is_gateway_transport_failure(exc):
                raise
            record_gateway_request_result(
                feature=self._feature,
                outcome='fallback',
                reason=_fallback_reason(exc),
                route=feature_auto_lane_id(self._feature),
            )
            return self._legacy.invoke(input, config=config, **kwargs)

        record_gateway_request_result(
            feature=self._feature,
            outcome='success',
            reason='ok',
            route=feature_auto_lane_id(self._feature),
        )
        return result

    async def ainvoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        try:
            result = await self._gateway.ainvoke(input, config=config, **kwargs)
        except Exception as exc:
            if not is_gateway_transport_failure(exc):
                raise
            record_gateway_request_result(
                feature=self._feature,
                outcome='fallback',
                reason=_fallback_reason(exc),
                route=feature_auto_lane_id(self._feature),
            )
            return await self._legacy.ainvoke(input, config=config, **kwargs)

        record_gateway_request_result(
            feature=self._feature,
            outcome='success',
            reason='ok',
            route=feature_auto_lane_id(self._feature),
        )
        return result
