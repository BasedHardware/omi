from __future__ import annotations

import os
from functools import lru_cache

from llm_gateway.gateway.config_loader import GatewayConfig, load_gateway_config
from llm_gateway.gateway.executor import ProviderRegistry
from llm_gateway.gateway.providers import OpenAICompatibleChatCompletionProvider

# Production-by-default: a missing env var is treated as production (fail-safe).
# Dev environments must explicitly set OMI_LLM_GATEWAY_PROD to '0' / 'false' / 'no'
# to opt out of production validation.
_DEV_ENV_VALUES = frozenset({'0', 'false', 'no', 'dev', 'development'})


def _resolve_prod_mode() -> bool:
    """True unless OMI_LLM_GATEWAY_PROD is explicitly set to a dev-mode value."""
    raw = os.getenv('OMI_LLM_GATEWAY_PROD', '').strip().lower()
    return raw not in _DEV_ENV_VALUES


@lru_cache(maxsize=1)
def get_gateway_config() -> GatewayConfig:
    # Fail-safe default: production mode. The OMI_LLM_GATEWAY_PROD env var
    # opts INTO dev mode (set to '0', 'false', 'no', 'dev', or 'development'
    # to disable production validation). A missing or unrecognized env
    # var defaults to production mode, so a misconfigured deployment
    # rejects dev-only artifacts rather than silently accepting them.
    # Per cubic-dev-ai review on PR #8746.
    return load_gateway_config(prod_mode=_resolve_prod_mode())


@lru_cache(maxsize=1)
def get_provider_registry() -> ProviderRegistry:
    return ProviderRegistry({'openai': OpenAICompatibleChatCompletionProvider()})


async def close_provider_registry() -> None:
    await get_provider_registry().aclose()
    get_provider_registry.cache_clear()
