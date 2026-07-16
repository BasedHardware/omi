from __future__ import annotations

import os
import random
from typing import Any

try:
    from langchain_core.callbacks.manager import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
except ImportError:
    try:
        from langchain_core.callbacks import BaseCallbackHandler as CallbackManagerForLLMRun
    except ImportError:
        CallbackManagerForLLMRun = Any

    AsyncCallbackManagerForLLMRun = CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel

try:
    from langchain_core.messages import BaseMessage
except ImportError:
    BaseMessage = None
try:
    from langchain_core.outputs import ChatResult
except ImportError:
    ChatResult = Any
try:
    from langchain_core.runnables import Runnable
except ImportError:

    class Runnable:
        pass


from pydantic import ConfigDict

try:
    from utils.byok import has_byok_keys
except ImportError:

    def has_byok_keys() -> bool:
        return False


from utils.executors import llm_executor, start_background_task, submit_with_context
from utils.llm.gateway_client import BACKGROUND_CHAT_EXTRACTION_TIMEOUT_SECONDS, CHAT_STRUCTURED_AUTO_LANE_ID
from utils.llm.gateway_observability import record_gateway_request_result, record_gateway_shadow_comparison
from utils.llm.providers import get_or_create_omi_gateway_llm

DEV_SHADOW_ALL_ENABLED_ENV = 'OMI_LLM_GATEWAY_DEV_SHADOW_ALL_ENABLED'
DEV_SHADOW_ALL_SAMPLE_RATE_ENV = 'OMI_LLM_GATEWAY_DEV_SHADOW_ALL_SAMPLE_RATE'

_PROD_STAGE_VALUES = {'prod', 'production'}


def maybe_wrap_dev_gateway_shadow(
    *,
    feature: str,
    model: str,
    provider: str,
    streaming: bool,
    legacy_model: BaseChatModel,
) -> BaseChatModel:
    if not _dev_shadow_enabled(provider=provider, streaming=streaming):
        return legacy_model

    gateway_model = get_or_create_omi_gateway_llm(
        CHAT_STRUCTURED_AUTO_LANE_ID,
        streaming=False,
        options={'request_timeout': BACKGROUND_CHAT_EXTRACTION_TIMEOUT_SECONDS},
        feature=feature,
    )
    return GatewayShadowChatModel(
        feature=feature,
        model_name=model,
        provider=provider,
        legacy_model=legacy_model,
        gateway_model=gateway_model,
    )


def _dev_shadow_enabled(*, provider: str, streaming: bool) -> bool:
    if streaming:
        return False
    if has_byok_keys():
        return False
    if _is_prod_like_runtime():
        return False
    if provider in {'anthropic', 'perplexity'}:
        return False
    if os.getenv(DEV_SHADOW_ALL_ENABLED_ENV, '').strip().casefold() not in {'1', 'true', 'yes', 'on'}:
        return False
    sample_rate = _sample_rate()
    return sample_rate >= 1.0 or random.random() < sample_rate


def _sample_rate() -> float:
    value = os.getenv(DEV_SHADOW_ALL_SAMPLE_RATE_ENV, '1.0')
    try:
        return max(0.0, min(1.0, float(value)))
    except ValueError:
        return 0.0


def _is_prod_like_runtime() -> bool:
    stage = os.getenv('OMI_ENV_STAGE', '').strip().casefold()
    if stage in _PROD_STAGE_VALUES:
        return True
    service = (os.getenv('K_SERVICE') or os.getenv('APP_NAME') or '').strip().casefold()
    return service.startswith('prod-') or service.startswith('prod_') or service in _PROD_STAGE_VALUES


class GatewayShadowChatModel(BaseChatModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    feature: str
    model_name: str
    provider: str
    legacy_model: BaseChatModel
    gateway_model: BaseChatModel

    @property
    def _llm_type(self) -> str:
        return f'{getattr(self.legacy_model, "_llm_type", "chat")}-omi-gateway-shadow'

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        result = self.legacy_model._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        _submit_sync_shadow(
            self.gateway_model._generate,
            messages,
            stop=stop,
            feature=_shadow_feature(self.feature),
            **kwargs,
        )
        return result

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        result = await self.legacy_model._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)
        start_background_task(
            _run_async_shadow(
                self.gateway_model._agenerate, messages, stop=stop, feature=_shadow_feature(self.feature), **kwargs
            ),
            name=f'llm-gateway-shadow:{self.feature}',
        )
        return result

    def with_structured_output(self, schema: dict[str, Any] | type, *, include_raw: bool = False, **kwargs: Any):
        legacy = self.legacy_model.with_structured_output(schema, include_raw=include_raw, **kwargs)
        gateway = self.gateway_model.with_structured_output(schema, include_raw=include_raw, **kwargs)
        return GatewayShadowRunnable(feature=_shadow_feature(self.feature), legacy=legacy, gateway=gateway)


class GatewayShadowRunnable(Runnable):
    def __init__(self, *, feature: str, legacy: Runnable, gateway: Runnable):
        self._feature = feature
        self._legacy = legacy
        self._gateway = gateway

    def invoke(self, input: Any, config=None, **kwargs: Any) -> Any:
        result = self._legacy.invoke(input, config=config, **kwargs)
        _submit_sync_shadow(
            self._gateway.invoke, input, config=config, feature=self._feature, legacy_result=result, **kwargs
        )
        return result

    async def ainvoke(self, input: Any, config=None, **kwargs: Any) -> Any:
        result = await self._legacy.ainvoke(input, config=config, **kwargs)
        start_background_task(
            _run_async_shadow(
                self._gateway.ainvoke,
                input,
                config=config,
                feature=self._feature,
                legacy_result=result,
                **kwargs,
            ),
            name=f'llm-gateway-shadow:{self._feature}',
        )
        return result


def _submit_sync_shadow(fn, *args, feature: str, legacy_result: Any = None, **kwargs: Any) -> None:
    try:
        submit_with_context(llm_executor, _run_sync_shadow, fn, args, kwargs, feature, legacy_result)
    except Exception:
        record_gateway_request_result(feature=feature, outcome='fallback', reason='submit_failed', mode='shadow')


def _run_sync_shadow(fn, args: tuple[Any, ...], kwargs: dict[str, Any], feature: str, legacy_result: Any) -> None:
    try:
        gateway_result = fn(*args, **kwargs)
    except Exception:
        record_gateway_request_result(feature=feature, outcome='fallback', reason='unexpected_error', mode='shadow')
        return
    record_gateway_request_result(feature=feature, outcome='success', reason='ok', mode='shadow')
    _record_shadow_result_comparison(feature=feature, legacy_result=legacy_result, gateway_result=gateway_result)


async def _run_async_shadow(fn, *args, feature: str, legacy_result: Any = None, **kwargs: Any) -> None:
    try:
        gateway_result = await fn(*args, **kwargs)
    except Exception:
        record_gateway_request_result(feature=feature, outcome='fallback', reason='unexpected_error', mode='shadow')
        return
    record_gateway_request_result(feature=feature, outcome='success', reason='ok', mode='shadow')
    _record_shadow_result_comparison(feature=feature, legacy_result=legacy_result, gateway_result=gateway_result)


def _record_shadow_result_comparison(*, feature: str, legacy_result: Any, gateway_result: Any) -> None:
    if legacy_result is None:
        return
    record_gateway_shadow_comparison(
        feature=feature,
        field='parsed_result',
        outcome='exact_match' if _comparison_value(legacy_result) == _comparison_value(gateway_result) else 'mismatch',
    )


def _comparison_value(value: Any) -> Any:
    if isinstance(value, dict) and {'raw', 'parsed', 'parsing_error'} <= set(value):
        value = value.get('parsed')
    if hasattr(value, 'model_dump'):
        return value.model_dump(mode='json')
    if BaseMessage is not None and isinstance(value, BaseMessage):
        return {'type': value.type, 'content': value.content}
    return value


def _shadow_feature(feature: str) -> str:
    return f'{feature}.shadow'
