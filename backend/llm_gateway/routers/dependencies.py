from __future__ import annotations

from functools import lru_cache

from llm_gateway.gateway.config_loader import GatewayConfig, load_gateway_config
from llm_gateway.gateway.executor import ProviderRegistry
from llm_gateway.gateway.providers import (
    AnthropicMessagesProvider,
    OpenAICompatibleChatCompletionProvider,
    VertexGeminiProvider,
)


@lru_cache(maxsize=1)
def get_gateway_config() -> GatewayConfig:
    return load_gateway_config(prod_mode=True)


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
