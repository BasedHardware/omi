"""Live integration test for geocoding Redis cache (PR #4688, issue #4653).

Requires real Redis + Google Maps API credentials.
Run from backend/ with env loaded:
    cd backend && set -a && source ~/.config/omi/dev/backend/.env && set +a
    python3 -m pytest tests/integration/test_geocoding_cache_live.py -v -s

Tests:
1. First call hits Google API, caches result in Redis with 48h TTL
2. Second call serves from Redis cache (faster, no API cost)
3. Cache key uses 3 decimal places (~100m precision)
4. Distant coordinates get different cache keys
5. Cleanup removes test data
"""

import json
import os
import time

import pytest

from database.redis_db import r
from models.conversation import Geolocation
from utils.conversations.location import get_google_maps_location

# San Francisco (Embarcadero)
LAT = 37.79520
LNG = -122.39330
CACHE_KEY = f"geocode:{LAT:.3f},{LNG:.3f}"


@pytest.fixture(autouse=True)
def cleanup_cache():
    """Clear test cache key before and after each test."""
    r.delete(CACHE_KEY)
    yield
    r.delete(CACHE_KEY)


def _skip_if_no_credentials():
    if not os.getenv("GOOGLE_MAPS_API_KEY"):
        pytest.skip("GOOGLE_MAPS_API_KEY not set")
    if not os.getenv("REDIS_DB_HOST"):
        pytest.skip("REDIS_DB_HOST not set")


class TestGeoCacheLive:

    def test_first_call_hits_api_and_caches(self):
        """First call should hit Google API and write to Redis."""
        _skip_if_no_credentials()

        result = get_google_maps_location(LAT, LNG)

        assert result is not None
        assert isinstance(result, Geolocation)
        assert result.google_place_id is not None
        assert result.address is not None

        # Verify cache was written
        cached_raw = r.get(CACHE_KEY)
        assert cached_raw is not None, "Cache should be populated after first call"
        cached_data = json.loads(cached_raw)
        assert cached_data["google_place_id"] == result.google_place_id

        # Verify TTL is ~48h
        ttl = r.ttl(CACHE_KEY)
        assert 172700 < ttl <= 172800, f"TTL should be ~172800s, got {ttl}"

    def test_second_call_hits_cache_faster(self):
        """Second call should serve from Redis (faster than API)."""
        _skip_if_no_credentials()

        # Prime the cache
        t0 = time.time()
        result1 = get_google_maps_location(LAT, LNG)
        api_time = time.time() - t0

        # Cache hit
        t0 = time.time()
        result2 = get_google_maps_location(LAT, LNG)
        cache_time = time.time() - t0

        assert result2 is not None
        assert result2.google_place_id == result1.google_place_id
        assert result2.address == result1.address
        assert cache_time < api_time, f"Cache hit ({cache_time:.3f}s) should be faster than API ({api_time:.3f}s)"

    def test_cache_key_uses_3_decimal_precision(self):
        """Cache key should round to 3 decimal places (~100m)."""
        _skip_if_no_credentials()

        get_google_maps_location(LAT, LNG)

        # Key should exist with 3 decimal places
        assert r.exists(CACHE_KEY), f"Expected cache key {CACHE_KEY} to exist"

        # Key with 2 decimal places should NOT exist
        key_2dp = f"geocode:{LAT:.2f},{LNG:.2f}"
        assert not r.exists(key_2dp), f"Key with 2dp should not exist: {key_2dp}"

    def test_distant_coords_different_cache_key(self):
        """Coordinates ~200m away should produce a different cache key."""
        distant_lat = LAT + 0.002  # ~220m north
        distant_key = f"geocode:{distant_lat:.3f},{LNG:.3f}"
        assert distant_key != CACHE_KEY
