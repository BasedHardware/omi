"""Regression: the disabled-app cache size cap must hold on every write path.

database.webhook_health caches disabled-app state in _disabled_cache with a _CACHE_MAX_SIZE safety
cap, but the cap was enforced only on the is_app_webhook_disabled read path; the record/re-enable
write paths set the cache without it. _set_disabled_state centralizes the write so every path stays
within the cap.
"""

import pytest

import database.webhook_health as wh


@pytest.fixture(autouse=True)
def _clear_cache():
    wh._disabled_cache.clear()
    yield
    wh._disabled_cache.clear()


def test_cap_is_enforced_on_the_write_paths(monkeypatch):
    monkeypatch.setattr(wh, "_CACHE_MAX_SIZE", 10)
    for i in range(30):
        wh._set_disabled_state(f"app-{i}", True)

    # Before the fix these write paths never evicted, so the cache would hold all 30 entries.
    assert len(wh._disabled_cache) <= 10
    assert len(wh._disabled_cache) >= 1


def test_rewriting_a_key_increments_generation_without_growth():
    wh._set_disabled_state("a", True)
    gen1 = wh._disabled_cache["a"][2]

    wh._set_disabled_state("a", False)

    value, _ts, gen2 = wh._disabled_cache["a"]
    assert gen2 == gen1 + 1
    assert value is False
    assert len(wh._disabled_cache) == 1  # same key, no growth
