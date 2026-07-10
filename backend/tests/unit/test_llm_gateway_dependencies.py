from __future__ import annotations

import pytest

from llm_gateway.gateway.executor import ProviderRegistry
from llm_gateway.routers.dependencies import close_provider_registry, get_provider_registry


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
