from __future__ import annotations

from functools import lru_cache

from llm_gateway.gateway.config_loader import GatewayConfig, load_gateway_config
from llm_gateway.gateway.executor import ProviderRegistry
from llm_gateway.gateway.providers import OpenAICompatibleChatCompletionProvider


@lru_cache(maxsize=1)
def get_gateway_config() -> GatewayConfig:
    # Respect OMI_LLM_GATEWAY_PROD env var. In dev/staging (env unset) we accept
    # dev_only placeholders; in prod (env set) we reject them. Hard-coding True
    # here would break /ready and the openai_compatible request path in dev,
    # where R0's day-one placeholders are intentional.
    return load_gateway_config(prod_mode=None)


@lru_cache(maxsize=1)
def get_provider_registry() -> ProviderRegistry:
    return ProviderRegistry({'openai': OpenAICompatibleChatCompletionProvider()})


async def close_provider_registry() -> None:
    await get_provider_registry().aclose()
    get_provider_registry.cache_clear()
