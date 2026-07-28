"""Round-trip tests for Redis cache serialization helpers in database/redis_db.py."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

import database.redis_db as redis_db


class _FakeRedis:
    def __init__(self) -> None:
        self._store: Dict[str, Any] = {}

    def set(self, key: str, value: Any, ex: Optional[int] = None, nx: bool = False) -> Optional[bool]:
        if nx and key in self._store:
            return None
        self._store[key] = value
        return True

    def get(self, key: str) -> Optional[Any]:
        return self._store.get(key)

    def expire(self, key: str, ttl: int) -> None:
        return None

    def mget(self, keys: List[str]) -> List[Optional[Any]]:
        return [self._store.get(key) for key in keys]

    def eval(self, script: str, _numkeys: int, key: str, expected: str, *args: Any) -> int:
        if self._store.get(key) != expected:
            return 0
        if "redis.call('DEL'" in script:
            del self._store[key]
        else:
            self._store[key] = 'done'
        return 1


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


def test_pusher_delivery_lease_reaches_done_with_a_bounded_key(fake_redis: _FakeRedis) -> None:
    delivery_id = f"delivery-{'x' * 512}"

    state, lease_token = redis_db.begin_pusher_delivery("uid-1", delivery_id, redis_client=fake_redis)
    assert state == 'claimed'
    assert lease_token
    assert redis_db.begin_pusher_delivery("uid-1", delivery_id, redis_client=fake_redis) == ('busy', None)
    assert (
        redis_db.complete_pusher_delivery(
            "uid-1",
            delivery_id,
            lease_token,
            redis_client=fake_redis,
        )
        is True
    )
    assert redis_db.begin_pusher_delivery("uid-1", delivery_id, redis_client=fake_redis) == ('done', None)
    assert redis_db.begin_pusher_delivery("uid-2", delivery_id, redis_client=fake_redis)[0] == 'claimed'
    assert all(delivery_id not in key for key in fake_redis._store)
    assert all(len(key) < 128 for key in fake_redis._store)


def test_pusher_failed_effect_releases_only_its_own_lease(fake_redis: _FakeRedis) -> None:
    state, lease_token = redis_db.begin_pusher_delivery("uid-1", "delivery-1", redis_client=fake_redis)
    assert state == 'claimed'
    assert lease_token
    assert (
        redis_db.abandon_pusher_delivery(
            "uid-1",
            "delivery-1",
            "wrong-token",
            redis_client=fake_redis,
        )
        is False
    )
    assert (
        redis_db.abandon_pusher_delivery(
            "uid-1",
            "delivery-1",
            lease_token,
            redis_client=fake_redis,
        )
        is True
    )
    assert redis_db.begin_pusher_delivery("uid-1", "delivery-1", redis_client=fake_redis)[0] == 'claimed'


def test_pusher_delivery_lease_fails_open_when_redis_is_unavailable() -> None:
    class _UnavailableRedis:
        def set(self, *args: Any, **kwargs: Any) -> None:
            raise ConnectionError("redis unavailable")

    client = _UnavailableRedis()

    assert redis_db.begin_pusher_delivery("uid-1", "delivery-1", redis_client=client) == ('unavailable', None)
    assert redis_db.complete_pusher_delivery("uid-1", "delivery-1", "lease-1", redis_client=client) is False
    assert redis_db.abandon_pusher_delivery("uid-1", "delivery-1", "lease-1", redis_client=client) is False


def test_pusher_delivery_client_has_bounded_network_timeouts(monkeypatch: pytest.MonkeyPatch) -> None:
    constructor = MagicMock(return_value=object())
    monkeypatch.setattr(redis_db.redis, 'Redis', constructor)
    monkeypatch.setattr(redis_db, '_pusher_delivery_r', None)

    assert redis_db._get_pusher_delivery_redis() is constructor.return_value
    assert constructor.call_args.kwargs['socket_connect_timeout'] == 0.5
    assert constructor.call_args.kwargs['socket_timeout'] == 0.5
    assert constructor.call_args.kwargs['retry_on_timeout'] is False
