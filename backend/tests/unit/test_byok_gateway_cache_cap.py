"""Regression: the gateway BYOK LLM-client cache must stay bounded.

utils.llm.gateway_byok caches a ChatOpenAI client per cache key, and the cache key includes a
per-BYOK-key fingerprint, so a long-lived process serving many distinct BYOK credentials accumulated
a client per key for the whole process lifetime (the repo's rule requires module-level dicts to cap
or TTL). _remember_byok_client caps the map and evicts the oldest entry.
"""

import pytest

import utils.llm.gateway_byok as gw


@pytest.fixture(autouse=True)
def _clear_cache():
    gw._byok_gateway_llm_cache.clear()
    yield
    gw._byok_gateway_llm_cache.clear()


def test_cache_is_bounded_and_evicts_oldest():
    cap = gw._MAX_BYOK_GATEWAY_CLIENTS
    for i in range(cap + 25):
        gw._remember_byok_client((f"key-{i}",), f"client-{i}")

    assert len(gw._byok_gateway_llm_cache) == cap
    # oldest evicted, most recent retained
    assert ("key-0",) not in gw._byok_gateway_llm_cache
    assert gw._byok_gateway_llm_cache[(f"key-{cap + 24}",)] == f"client-{cap + 24}"


def test_rewriting_a_key_refreshes_without_growth():
    for i in range(5):
        gw._remember_byok_client((f"k{i}",), f"c{i}")
    before = len(gw._byok_gateway_llm_cache)

    gw._remember_byok_client(("k0",), "c0-new")

    assert len(gw._byok_gateway_llm_cache) == before  # updating an existing key does not grow the map
    assert gw._byok_gateway_llm_cache[("k0",)] == "c0-new"
