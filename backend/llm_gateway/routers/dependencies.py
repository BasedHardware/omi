from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from llm_gateway.gateway.config_loader import DEFAULT_CONFIG_DIR, GatewayConfig
from llm_gateway.gateway.config_reload import GatewayConfigReloader
from llm_gateway.gateway.executor import ProviderRegistry
from llm_gateway.gateway.providers import (
    AnthropicMessagesProvider,
    OpenAICompatibleChatCompletionProvider,
    VertexGeminiProvider,
)

# Production-by-default: missing env is production (fail-safe).
# Dev must set OMI_LLM_GATEWAY_PROD to a dev-mode value to opt out.
_DEV_ENV_VALUES = frozenset({'0', 'false', 'no', 'dev', 'development'})


def _resolve_prod_mode() -> bool:
    raw = os.getenv('OMI_LLM_GATEWAY_PROD', '').strip().lower()
    return raw not in _DEV_ENV_VALUES


_config_reloader = GatewayConfigReloader(Path(DEFAULT_CONFIG_DIR), prod_mode_fn=_resolve_prod_mode)


async def get_gateway_config() -> GatewayConfig:
    """Return current gateway config, hot-reloading on YAML mtime change."""
    return await _config_reloader.get()


def reset_gateway_config_reloader() -> None:
    """Test helper: force next get() to reload from disk."""
    _config_reloader.invalidate()


@lru_cache(maxsize=1)
def get_provider_registry() -> ProviderRegistry:
    return ProviderRegistry(
        {
            'openai': OpenAICompatibleChatCompletionProvider(),
            'openrouter': OpenAICompatibleChatCompletionProvider(
                api_key_env='OPENROUTER_API_KEY',
                base_url='https://openrouter.ai/api/v1',
                default_headers={'X-Title': 'Omi Chat'},
            ),
            'perplexity': OpenAICompatibleChatCompletionProvider(
                api_key_env='PERPLEXITY_API_KEY',
                base_url='https://api.perplexity.ai',
            ),
            'gemini': VertexGeminiProvider(),
            'anthropic': AnthropicMessagesProvider(),
        }
    )


async def close_provider_registry() -> None:
    await get_provider_registry().aclose()
    get_provider_registry.cache_clear()
