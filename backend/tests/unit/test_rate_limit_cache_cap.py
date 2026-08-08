"""Regression: the in-process custom rate-limit cache must stay bounded.

utils.other.endpoints.rate_limit_custom stores per-request state in the module-level `cached` dict
keyed by "{endpoint}:{ip}". It was get/set only with no eviction, so a stream of distinct client IPs
(ordinary traffic, or an attacker rotating IPs) grew the map without bound. _store_rate_limit caps it.
"""

import pytest

import utils.other.endpoints as endpoints


@pytest.fixture(autouse=True)
def _clear():
    endpoints.cached.clear()
    yield
    endpoints.cached.clear()


def test_rate_limit_cache_is_bounded_and_keeps_newest(monkeypatch):
    monkeypatch.setattr(endpoints, "_MAX_RATE_LIMIT_ENTRIES", 10)
    for i in range(40):
        endpoints._store_rate_limit(f"rate_limit:ep:{i}", "{}")

    assert len(endpoints.cached) <= 10
    assert "rate_limit:ep:39" in endpoints.cached  # newest retained
    assert "rate_limit:ep:0" not in endpoints.cached  # oldest evicted


def test_updating_an_existing_key_does_not_grow(monkeypatch):
    monkeypatch.setattr(endpoints, "_MAX_RATE_LIMIT_ENTRIES", 10)
    endpoints._store_rate_limit("k", "v1")
    endpoints._store_rate_limit("k", "v2")

    assert len(endpoints.cached) == 1
    assert endpoints.cached["k"] == "v2"
