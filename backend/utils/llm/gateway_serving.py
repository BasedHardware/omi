"""Gateway-first serving with legacy provider fallback on hard transport failures."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, AsyncIterator, Iterator, TypeVar

try:
    from langchain_core.callbacks.manager import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
except ImportError:
    try:
        from langchain_core.callbacks import BaseCallbackHandler as CallbackManagerForLLMRun
    except ImportError:
        CallbackManagerForLLMRun = Any  # type: ignore[misc,assignment]

    AsyncCallbackManagerForLLMRun = CallbackManagerForLLMRun  # type: ignore[misc,assignment]
try:
    from langchain_core.language_models import BaseChatModel
except ImportError:

    class BaseChatModel:  # type: ignore[no-redef]
        pass


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


try:
    import httpx
except ImportError:  # pragma: no cover - stubbed test environments
    httpx = None  # type: ignore[assignment]

try:
    from pydantic import ConfigDict
except ImportError:  # pragma: no cover - stubbed test environments

    def ConfigDict(**_kwargs):  # type: ignore[misc]
        return {}


from utils.llm.gateway_client import GATEWAY_TRANSPORT_STATUS_CODES, feature_auto_lane_id
from utils.llm.gateway_observability import record_gateway_request_result
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)

# A gateway configuration or credential failure is a controlled 503 and must
# remain visible. Only hard proxy failures may use the temporary legacy path.
_REQUEST_ID_HEADER = 'X-Omi-Request-ID'
_T = TypeVar('_T')


def wrap_gateway_with_legacy_fallback(
    *,
    feature: str,
    gateway_model: BaseChatModel,
    legacy_model: BaseChatModel,
    credential_source: str = 'unknown',
) -> BaseChatModel:
    return GatewayWithLegacyFallbackChatModel(
        feature=feature,
        gateway_model=gateway_model,
        legacy_model=legacy_model,
        credential_source=credential_source,
    )


def is_gateway_transport_failure(exc: BaseException) -> bool:
    """Return True for gateway unreachable / hard HTTP failures that should fall back."""
    if httpx is not None:
        if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)):
            return True
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response is not None and exc.response.status_code in GATEWAY_TRANSPORT_STATUS_CODES

    status_code = getattr(exc, 'status_code', None)
    if isinstance(status_code, int) and status_code in GATEWAY_TRANSPORT_STATUS_CODES:
        return True

    response = getattr(exc, 'response', None)
    response_status = getattr(response, 'status_code', None)
    if isinstance(response_status, int) and response_status in GATEWAY_TRANSPORT_STATUS_CODES:
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
        'gateway timeout',
        '502',
        '504',
    )
    return any(marker in message for marker in transport_markers)


def _fallback_reason(exc: BaseException) -> str:
    if 'timeout' in str(exc).casefold() or 'timed out' in str(exc).casefold():
        return 'timeout'
    if httpx is not None and isinstance(exc, httpx.TimeoutException):
        return 'timeout'
    if httpx is not None and isinstance(exc, (httpx.NetworkError, httpx.RemoteProtocolError)):
        return 'request_error'
    status_code = getattr(exc, 'status_code', None)
    if not isinstance(status_code, int):
        response = getattr(exc, 'response', None)
        status_code = getattr(response, 'status_code', None)
    if isinstance(status_code, int) and status_code in GATEWAY_TRANSPORT_STATUS_CODES:
        return 'request_error'
    return 'unexpected_error'


def _record_gateway_terminal(
    *,
    feature: str,
    outcome: str,
    reason: str,
    mode: str,
    request_id: str = 'unknown',
    credential_source: str = 'unknown',
) -> None:
    observability_context = {}
    if request_id != 'unknown':
        observability_context['request_id'] = request_id
    if credential_source != 'unknown':
        observability_context['credential_source'] = credential_source
    record_gateway_request_result(
        feature=feature,
        outcome=outcome,
        reason=reason,
        route=feature_auto_lane_id(feature),
        mode=mode,
        **observability_context,
    )


def record_gateway_fallback_terminal(
    *,
    feature: str,
    gateway_reason: str,
    outcome: str,
    request_id: str = 'unknown',
    credential_source: str = 'unknown',
    request_outcome: str | None = None,
    request_reason: str | None = None,
) -> None:
    recovered = outcome == 'recovered'
    _record_gateway_terminal(
        feature=feature,
        outcome=request_outcome or ('fallback' if recovered else 'error'),
        reason=request_reason or (gateway_reason if recovered else f'fallback_exhausted_{gateway_reason}'),
        mode='fallback',
        request_id=request_id,
        credential_source=credential_source,
    )
    # Consumer/client cancellation terminates the request, but it does not prove
    # whether the fallback path was recovered, degraded, or exhausted. The shared
    # fallback contract has no cancellation outcome, so emitting one would inflate
    # an operational failure bucket with user-driven lifecycle events.
    if request_outcome == 'cancelled':
        return
    record_fallback(
        component='llm_gateway',
        from_mode='gateway',
        to_mode='legacy_provider',
        reason=_shared_fallback_reason(gateway_reason),
        outcome=outcome,
        log=logger,
    )


def _shared_fallback_reason(gateway_reason: str) -> str:
    if gateway_reason == 'timeout':
        return 'timeout'
    if gateway_reason == 'request_error':
        return 'provider_5xx'
    return 'other'


def _run_legacy_fallback(
    *,
    feature: str,
    gateway_reason: str,
    call: Callable[[], _T],
    request_id: str = 'unknown',
    credential_source: str = 'unknown',
) -> _T:
    try:
        result = call()
    except Exception:
        record_gateway_fallback_terminal(
            feature=feature,
            gateway_reason=gateway_reason,
            outcome='exhausted',
            request_id=request_id,
            credential_source=credential_source,
        )
        raise
    record_gateway_fallback_terminal(
        feature=feature,
        gateway_reason=gateway_reason,
        outcome='recovered',
        request_id=request_id,
        credential_source=credential_source,
    )
    return result


def _close_iterator(stream: object | None) -> None:
    close = getattr(stream, 'close', None)
    if close is None:
        return
    try:
        close()
    except Exception:
        try:
            logger.warning('llm_gateway_stream_cleanup_failed kind=sync')
        except Exception:
            return


async def _close_async_iterator(stream: object | None) -> None:
    close = getattr(stream, 'aclose', None)
    if close is None:
        return
    try:
        await close()
    except Exception:
        try:
            logger.warning('llm_gateway_stream_cleanup_failed kind=async')
        except Exception:
            return


async def _run_legacy_fallback_async(
    *,
    feature: str,
    gateway_reason: str,
    call: Callable[[], Awaitable[_T]],
    request_id: str = 'unknown',
    credential_source: str = 'unknown',
) -> _T:
    try:
        result = await call()
    except asyncio.CancelledError:
        record_gateway_fallback_terminal(
            feature=feature,
            gateway_reason=gateway_reason,
            outcome='exhausted',
            request_id=request_id,
            credential_source=credential_source,
            request_outcome='cancelled',
            request_reason='client_cancelled',
        )
        raise
    except Exception:
        record_gateway_fallback_terminal(
            feature=feature,
            gateway_reason=gateway_reason,
            outcome='exhausted',
            request_id=request_id,
            credential_source=credential_source,
        )
        raise
    record_gateway_fallback_terminal(
        feature=feature,
        gateway_reason=gateway_reason,
        outcome='recovered',
        request_id=request_id,
        credential_source=credential_source,
    )
    return result


def _iter_legacy_fallback(
    *,
    feature: str,
    gateway_reason: str,
    stream: Iterator[Any],
    request_id: str = 'unknown',
    credential_source: str = 'unknown',
) -> Iterator[Any]:
    yielded = False
    terminal_recorded = False
    try:
        for chunk in stream:
            yielded = True
            yield chunk
    except GeneratorExit:
        record_gateway_fallback_terminal(
            feature=feature,
            gateway_reason=gateway_reason,
            outcome='exhausted',
            request_id=request_id,
            credential_source=credential_source,
            request_outcome='cancelled',
            request_reason='consumer_abandoned_stream',
        )
        terminal_recorded = True
        raise
    except Exception:
        record_gateway_fallback_terminal(
            feature=feature,
            gateway_reason=gateway_reason,
            outcome='exhausted',
            request_id=request_id,
            credential_source=credential_source,
        )
        terminal_recorded = True
        raise
    else:
        record_gateway_fallback_terminal(
            feature=feature,
            gateway_reason=gateway_reason,
            outcome='recovered' if yielded else 'exhausted',
            request_id=request_id,
            credential_source=credential_source,
        )
        terminal_recorded = True
    finally:
        try:
            if not terminal_recorded:
                record_gateway_fallback_terminal(
                    feature=feature,
                    gateway_reason=gateway_reason,
                    outcome='exhausted',
                    request_id=request_id,
                    credential_source=credential_source,
                )
        finally:
            _close_iterator(stream)


async def _aiter_legacy_fallback(
    *,
    feature: str,
    gateway_reason: str,
    stream: AsyncIterator[Any],
    request_id: str = 'unknown',
    credential_source: str = 'unknown',
) -> AsyncIterator[Any]:
    yielded = False
    terminal_recorded = False
    try:
        async for chunk in stream:
            yielded = True
            yield chunk
    except (GeneratorExit, asyncio.CancelledError):
        record_gateway_fallback_terminal(
            feature=feature,
            gateway_reason=gateway_reason,
            outcome='exhausted',
            request_id=request_id,
            credential_source=credential_source,
            request_outcome='cancelled',
            request_reason='consumer_abandoned_stream',
        )
        terminal_recorded = True
        raise
    except Exception:
        record_gateway_fallback_terminal(
            feature=feature,
            gateway_reason=gateway_reason,
            outcome='exhausted',
            request_id=request_id,
            credential_source=credential_source,
        )
        terminal_recorded = True
        raise
    else:
        record_gateway_fallback_terminal(
            feature=feature,
            gateway_reason=gateway_reason,
            outcome='recovered' if yielded else 'exhausted',
            request_id=request_id,
            credential_source=credential_source,
        )
        terminal_recorded = True
    finally:
        try:
            if not terminal_recorded:
                record_gateway_fallback_terminal(
                    feature=feature,
                    gateway_reason=gateway_reason,
                    outcome='exhausted',
                    request_id=request_id,
                    credential_source=credential_source,
                )
        finally:
            await _close_async_iterator(stream)


def _gateway_call_kwargs(kwargs: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    gateway_kwargs = dict(kwargs)
    raw_headers = gateway_kwargs.get('extra_headers')
    headers = dict(raw_headers) if isinstance(raw_headers, Mapping) else {}
    request_id_value = next(
        (value for key, value in headers.items() if str(key).casefold() == _REQUEST_ID_HEADER.casefold()),
        None,
    )
    request_id = _canonical_request_id(request_id_value)
    headers = {key: value for key, value in headers.items() if str(key).casefold() != _REQUEST_ID_HEADER.casefold()}
    headers[_REQUEST_ID_HEADER] = request_id
    gateway_kwargs['extra_headers'] = headers
    return gateway_kwargs, request_id


def _canonical_request_id(value: object) -> str:
    if isinstance(value, str):
        try:
            return str(uuid.UUID(value))
        except ValueError:
            pass
    return str(uuid.uuid4())


class GatewayWithLegacyFallbackChatModel(BaseChatModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    feature: str
    gateway_model: BaseChatModel
    legacy_model: BaseChatModel
    credential_source: str = 'unknown'

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
        gateway_kwargs, request_id = _gateway_call_kwargs(kwargs)
        try:
            result = self.gateway_model._generate(messages, stop=stop, run_manager=run_manager, **gateway_kwargs)
        except Exception as exc:
            if not is_gateway_transport_failure(exc):
                _record_gateway_terminal(
                    feature=self.feature,
                    outcome='error',
                    reason=_fallback_reason(exc),
                    mode='serving',
                    request_id=request_id,
                    credential_source=self.credential_source,
                )
                raise
            return _run_legacy_fallback(
                feature=self.feature,
                gateway_reason=_fallback_reason(exc),
                call=lambda: self.legacy_model._generate(messages, stop=stop, run_manager=run_manager, **kwargs),
                request_id=request_id,
                credential_source=self.credential_source,
            )

        _record_gateway_terminal(
            feature=self.feature,
            outcome='success',
            reason='ok',
            mode='serving',
            request_id=request_id,
            credential_source=self.credential_source,
        )
        return result

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        gateway_kwargs, request_id = _gateway_call_kwargs(kwargs)
        try:
            result = await self.gateway_model._agenerate(messages, stop=stop, run_manager=run_manager, **gateway_kwargs)
        except asyncio.CancelledError:
            _record_gateway_terminal(
                feature=self.feature,
                outcome='cancelled',
                reason='client_cancelled',
                mode='serving',
                request_id=request_id,
                credential_source=self.credential_source,
            )
            raise
        except Exception as exc:
            if not is_gateway_transport_failure(exc):
                _record_gateway_terminal(
                    feature=self.feature,
                    outcome='error',
                    reason=_fallback_reason(exc),
                    mode='serving',
                    request_id=request_id,
                    credential_source=self.credential_source,
                )
                raise
            return await _run_legacy_fallback_async(
                feature=self.feature,
                gateway_reason=_fallback_reason(exc),
                call=lambda: self.legacy_model._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs),
                request_id=request_id,
                credential_source=self.credential_source,
            )

        _record_gateway_terminal(
            feature=self.feature,
            outcome='success',
            reason='ok',
            mode='serving',
            request_id=request_id,
            credential_source=self.credential_source,
        )
        return result

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[Any]:
        yielded = False
        stream = None
        gateway_kwargs, request_id = _gateway_call_kwargs(kwargs)
        try:
            stream = self.gateway_model._stream(messages, stop=stop, run_manager=run_manager, **gateway_kwargs)
            for chunk in stream:
                yielded = True
                yield chunk
        except GeneratorExit:
            _record_gateway_terminal(
                feature=self.feature,
                outcome='cancelled',
                reason='consumer_abandoned_stream',
                mode='serving',
                request_id=request_id,
                credential_source=self.credential_source,
            )
            raise
        except Exception as exc:
            if yielded:
                _record_gateway_terminal(
                    feature=self.feature,
                    outcome='error',
                    reason=f'midstream_{_fallback_reason(exc)}',
                    mode='serving',
                    request_id=request_id,
                    credential_source=self.credential_source,
                )
                raise
            if not is_gateway_transport_failure(exc):
                _record_gateway_terminal(
                    feature=self.feature,
                    outcome='error',
                    reason=_fallback_reason(exc),
                    mode='serving',
                    request_id=request_id,
                    credential_source=self.credential_source,
                )
                raise
            gateway_reason = _fallback_reason(exc)
        else:
            if yielded:
                _record_gateway_terminal(
                    feature=self.feature,
                    outcome='success',
                    reason='ok',
                    mode='serving',
                    request_id=request_id,
                    credential_source=self.credential_source,
                )
                return
            gateway_reason = 'empty_stream_before_output'
        finally:
            _close_iterator(stream)

        yield from _iter_legacy_fallback(
            feature=self.feature,
            gateway_reason=gateway_reason,
            stream=self.legacy_model._stream(messages, stop=stop, run_manager=run_manager, **kwargs),
            request_id=request_id,
            credential_source=self.credential_source,
        )

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[Any]:
        yielded = False
        stream = None
        gateway_kwargs, request_id = _gateway_call_kwargs(kwargs)
        try:
            stream = self.gateway_model._astream(messages, stop=stop, run_manager=run_manager, **gateway_kwargs)
            async for chunk in stream:
                yielded = True
                yield chunk
        except (GeneratorExit, asyncio.CancelledError):
            _record_gateway_terminal(
                feature=self.feature,
                outcome='cancelled',
                reason='consumer_abandoned_stream',
                mode='serving',
                request_id=request_id,
                credential_source=self.credential_source,
            )
            raise
        except Exception as exc:
            if yielded:
                _record_gateway_terminal(
                    feature=self.feature,
                    outcome='error',
                    reason=f'midstream_{_fallback_reason(exc)}',
                    mode='serving',
                    request_id=request_id,
                    credential_source=self.credential_source,
                )
                raise
            if not is_gateway_transport_failure(exc):
                _record_gateway_terminal(
                    feature=self.feature,
                    outcome='error',
                    reason=_fallback_reason(exc),
                    mode='serving',
                    request_id=request_id,
                    credential_source=self.credential_source,
                )
                raise
            gateway_reason = _fallback_reason(exc)
        else:
            if yielded:
                _record_gateway_terminal(
                    feature=self.feature,
                    outcome='success',
                    reason='ok',
                    mode='serving',
                    request_id=request_id,
                    credential_source=self.credential_source,
                )
                return
            gateway_reason = 'empty_stream_before_output'
        finally:
            await _close_async_iterator(stream)

        legacy_stream = _aiter_legacy_fallback(
            feature=self.feature,
            gateway_reason=gateway_reason,
            stream=self.legacy_model._astream(messages, stop=stop, run_manager=run_manager, **kwargs),
            request_id=request_id,
            credential_source=self.credential_source,
        )
        try:
            async for chunk in legacy_stream:
                yield chunk
        finally:
            await _close_async_iterator(legacy_stream)

    def with_structured_output(self, schema: dict[str, Any] | type, *, include_raw: bool = False, **kwargs: Any):
        gateway = self.gateway_model.with_structured_output(schema, include_raw=include_raw, **kwargs)
        legacy = self.legacy_model.with_structured_output(schema, include_raw=include_raw, **kwargs)
        return GatewayWithLegacyFallbackRunnable(
            feature=self.feature,
            gateway=gateway,
            legacy=legacy,
            credential_source=self.credential_source,
        )


class GatewayWithLegacyFallbackRunnable(Runnable):
    def __init__(self, *, feature: str, gateway: Runnable, legacy: Runnable, credential_source: str = 'unknown'):
        self._feature = feature
        self._gateway = gateway
        self._legacy = legacy
        self._credential_source = credential_source

    def invoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        gateway_kwargs, request_id = _gateway_call_kwargs(kwargs)
        try:
            result = self._gateway.invoke(input, config=config, **gateway_kwargs)
        except Exception as exc:
            if not is_gateway_transport_failure(exc):
                _record_gateway_terminal(
                    feature=self._feature,
                    outcome='error',
                    reason=_fallback_reason(exc),
                    mode='serving',
                    request_id=request_id,
                    credential_source=self._credential_source,
                )
                raise
            return _run_legacy_fallback(
                feature=self._feature,
                gateway_reason=_fallback_reason(exc),
                call=lambda: self._legacy.invoke(input, config=config, **kwargs),
                request_id=request_id,
                credential_source=self._credential_source,
            )

        _record_gateway_terminal(
            feature=self._feature,
            outcome='success',
            reason='ok',
            mode='serving',
            request_id=request_id,
            credential_source=self._credential_source,
        )
        return result

    async def ainvoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        gateway_kwargs, request_id = _gateway_call_kwargs(kwargs)
        try:
            result = await self._gateway.ainvoke(input, config=config, **gateway_kwargs)
        except asyncio.CancelledError:
            _record_gateway_terminal(
                feature=self._feature,
                outcome='cancelled',
                reason='client_cancelled',
                mode='serving',
                request_id=request_id,
                credential_source=self._credential_source,
            )
            raise
        except Exception as exc:
            if not is_gateway_transport_failure(exc):
                _record_gateway_terminal(
                    feature=self._feature,
                    outcome='error',
                    reason=_fallback_reason(exc),
                    mode='serving',
                    request_id=request_id,
                    credential_source=self._credential_source,
                )
                raise
            return await _run_legacy_fallback_async(
                feature=self._feature,
                gateway_reason=_fallback_reason(exc),
                call=lambda: self._legacy.ainvoke(input, config=config, **kwargs),
                request_id=request_id,
                credential_source=self._credential_source,
            )

        _record_gateway_terminal(
            feature=self._feature,
            outcome='success',
            reason='ok',
            mode='serving',
            request_id=request_id,
            credential_source=self._credential_source,
        )
        return result
