"""Round-trip tests for Redis cache serialization helpers in database/redis_db.py."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

import database.redis_db as redis_db


class _FakeRedis:
    def __init__(self) -> None:
        self._store: Dict[str, Any] = {}
        self.set_calls: List[Dict[str, Any]] = []
        self.expire_calls: List[tuple[str, int]] = []

    def set(self, key: str, value: Any, ex: Optional[int] = None) -> None:
        self._store[key] = value
        self.set_calls.append({'key': key, 'value': value, 'ex': ex})

    def get(self, key: str) -> Optional[Any]:
        return self._store.get(key)

    def expire(self, key: str, ttl: int) -> None:
        self.expire_calls.append((key, ttl))

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


def test_geolocation_omits_unset_optional_fields(fake_redis: _FakeRedis) -> None:
    """A cached geolocation must stay parseable by a reader still using ``eval()``.

    ``Geolocation.model_dump()`` carries ``None`` for google_place_id/address/
    location_type. Serialized as JSON ``null`` those crashed pusher's legacy
    reader with ``NameError: name 'null' is not defined``, and the failing
    conversation was then marked discarded.
    """
    redis_db.cache_user_geolocation(
        "uid-1",
        {
            "google_place_id": None,
            "latitude": 37.77,
            "longitude": -122.42,
            "address": None,
            "location_type": None,
        },
    )

    raw = fake_redis._store["users:uid-1:geolocation"]
    assert "null" not in raw
    assert eval(raw) == {"latitude": 37.77, "longitude": -122.42}  # noqa: S307 — legacy reader
    assert redis_db.get_cached_user_geolocation("uid-1") == {"latitude": 37.77, "longitude": -122.42}


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


def test_set_generic_cache_uses_atomic_ex(fake_redis: _FakeRedis) -> None:
    redis_db.set_generic_cache("apps:marketplace", {"ok": True}, ttl=120)
    assert fake_redis.expire_calls == []
    assert len(fake_redis.set_calls) == 1
    assert fake_redis.set_calls[0]['ex'] == 120
    assert redis_db.get_generic_cache("apps:marketplace") == {"ok": True}


def test_set_generic_cache_without_ttl_omits_ex(fake_redis: _FakeRedis) -> None:
    redis_db.set_generic_cache("apps:no-ttl", {"ok": True})
    assert fake_redis.set_calls[0]['ex'] is None
    assert fake_redis.expire_calls == []


def test_cache_user_name_uses_atomic_ex(fake_redis: _FakeRedis) -> None:
    redis_db.cache_user_name("uid-1", "Ada", ttl=3600)
    assert fake_redis.expire_calls == []
    assert fake_redis.set_calls == [{'key': 'users:uid-1:name', 'value': 'Ada', 'ex': 3600}]


def test_cache_signed_url_uses_atomic_ex(fake_redis: _FakeRedis) -> None:
    redis_db.cache_signed_url("path/a.wav", "https://example.test/a", ttl=60)
    assert fake_redis.expire_calls == []
    assert fake_redis.set_calls == [{'key': 'urls:path/a.wav', 'value': 'https://example.test/a', 'ex': 59}]
