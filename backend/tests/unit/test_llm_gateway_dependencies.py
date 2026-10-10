from __future__ import annotations

import pytest
from unittest.mock import patch

from llm_gateway.gateway.executor import ProviderRegistry
from llm_gateway.routers.dependencies import close_provider_registry, get_provider_registry, get_gateway_config


@pytest.mark.asyncio
async def test_provider_registry_is_cached_and_closed():
    get_provider_registry.cache_clear()
    first = get_provider_registry()
    second = get_provider_registry()

    assert first is second

    await close_provider_registry()

    assert get_provider_registry() is not first
    await close_provider_registry()


@pytest.mark.asyncio
async def test_provider_registry_closes_all_providers_when_one_close_fails():
    calls = []

    class Provider:
        def __init__(self, name: str, should_fail: bool = False):
            self.name = name
            self.should_fail = should_fail

        async def aclose(self):
            calls.append(self.name)
            if self.should_fail:
                raise RuntimeError(f'{self.name} failed')

    registry = ProviderRegistry(
        {
            'first': Provider('first', should_fail=True),
            'second': Provider('second'),
        }
    )

    await registry.aclose()

    assert sorted(calls) == ['first', 'second']


def test_get_gateway_config():
    with patch('llm_gateway.routers.dependencies.load_gateway_config') as mock_load:
        get_gateway_config.cache_clear()

        mock_load.return_value = "mock_config"

        result1 = get_gateway_config()
        result2 = get_gateway_config()

        assert result1 == "mock_config"
        assert result2 == "mock_config"

        # Ensure load_gateway_config is called only once due to cache
        mock_load.assert_called_once_with(prod_mode=True)


def test_get_provider_registry_initialization():
    get_provider_registry.cache_clear()

    registry = get_provider_registry()

    assert isinstance(registry, ProviderRegistry)

    # Verify the registry returns the expected providers
    assert registry.provider_for('openai') is not None
    assert registry.provider_for('openrouter') is not None
    assert registry.provider_for('perplexity') is not None
    assert registry.provider_for('gemini') is not None
    assert registry.provider_for('anthropic') is not None

    # Provider configuration args checking isn't easily done since they are mostly initialized
    # as private fields inside the provider classes or the classes might not have them as fields.
    # What's important is that the dependencies file correctly initialized and added them.
