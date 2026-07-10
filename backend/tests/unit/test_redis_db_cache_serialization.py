"""Round-trip tests for Redis cache serialization helpers in database/redis_db.py."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

import database.redis_db as redis_db


class _FakeRedis:
    def __init__(self) -> None:
        self._store: Dict[str, Any] = {}

    def set(self, key: str, value: Any, ex: Optional[int] = None) -> None:
        self._store[key] = value

    def get(self, key: str) -> Optional[Any]:
        return self._store.get(key)

    def expire(self, key: str, ttl: int) -> None:
        return None

    def mget(self, keys: List[str]) -> List[Optional[Any]]:
        return [self._store.get(key) for key in keys]


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> _FakeRedis:
    client = _FakeRedis()
    monkeypatch.setattr(redis_db, "r", client)
    return client


def test_usage_count_json_round_trip(fake_redis: _FakeRedis) -> None:
    redis_db.set_app_usage_count_cache("app-1", 42)
    assert redis_db.get_app_usage_count_cache("app-1") == 42


def test_usage_count_legacy_literal_round_trip(fake_redis: _FakeRedis) -> None:
    fake_redis._store["apps:app-legacy:usage_count"] = b"99"
    assert redis_db.get_app_usage_count_cache("app-legacy") == 99


def test_money_made_json_round_trip(fake_redis: _FakeRedis) -> None:
    redis_db.set_app_money_made_amount_cache("app-1", 12.5)
    assert redis_db.get_app_money_made_amount_cache("app-1") == 12.5


def test_reviews_json_round_trip(fake_redis: _FakeRedis) -> None:
    redis_db.set_app_review_cache("app-1", "uid-a", {"rating": 5, "text": "great"})
    assert redis_db.get_specific_user_review("app-1", "uid-a") == {"rating": 5, "text": "great"}
    assert redis_db.get_app_reviews("app-1") == {"uid-a": {"rating": 5, "text": "great"}}


def test_reviews_legacy_literal_round_trip(fake_redis: _FakeRedis) -> None:
    fake_redis._store["plugins:app-legacy:reviews"] = b"{'uid-a': {'rating': 4}}"
    assert redis_db.get_specific_user_review("app-legacy", "uid-a") == {"rating": 4}


def test_geolocation_json_round_trip(fake_redis: _FakeRedis) -> None:
    geo = {"lat": 37.77, "lng": -122.42, "city": "San Francisco"}
    redis_db.cache_user_geolocation("uid-1", geo)
    assert redis_db.get_cached_user_geolocation("uid-1") == geo


def test_geolocation_legacy_literal_round_trip(fake_redis: _FakeRedis) -> None:
    fake_redis._store["users:uid-legacy:geolocation"] = b"{'lat': 1.0, 'lng': 2.0}"
    assert redis_db.get_cached_user_geolocation("uid-legacy") == {"lat": 1.0, "lng": 2.0}


def test_apps_reviews_batch_round_trip(fake_redis: _FakeRedis) -> None:
    redis_db.set_app_review_cache("app-a", "uid-1", {"rating": 3})
    redis_db.set_app_review_cache("app-b", "uid-2", {"rating": 5})
    reviews = redis_db.get_apps_reviews(["app-a", "app-b", "app-missing"])
    assert reviews == {
        "app-a": {"uid-1": {"rating": 3}},
        "app-b": {"uid-2": {"rating": 5}},
        "app-missing": {},
    }
