from __future__ import annotations

import pytest

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
