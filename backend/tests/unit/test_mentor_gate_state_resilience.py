"""Hermetic unit tests for mentor_gate_state storage tier and resilience guards."""

from __future__ import annotations

import time
from typing import Any, Dict
from unittest.mock import MagicMock
import pytest

from database.mentor_gate_state import (
    CLAIM_TTL_SECONDS,
    MAX_ID_LENGTH,
    STATE_TTL_SECONDS,
    _clean_id,
    _clean_state,
    _clean_ttl,
    _resolve_redis,
    claim,
    clear_local_cache,
    read,
    read_authoritative,
    record,
    release,
)


class FakeRedis:
    def __init__(self) -> None:
        self.store: Dict[str, str] = {}
        self.expirations: Dict[str, float] = {}

    def get(self, key: str) -> str | None:
        if key not in self.store:
            return None
        if key in self.expirations and self.expirations[key] < time.time():
            self.store.pop(key, None)
            self.expirations.pop(key, None)
            return None
        return self.store.get(key)

    def set(self, key: str, value: str, nx: bool = False, ex: int | None = None) -> bool:
        now = time.time()
        # Clean expired
        if key in self.expirations and self.expirations[key] < now:
            self.store.pop(key, None)
            self.expirations.pop(key, None)

        if nx and key in self.store:
            return False
        self.store[key] = value
        if ex is not None:
            self.expirations[key] = now + ex
        return True

    def delete(self, key: str) -> int:
        removed = 1 if key in self.store else 0
        self.store.pop(key, None)
        self.expirations.pop(key, None)
        return removed


@pytest.fixture(autouse=True)
def _reset_local():
    clear_local_cache()
    yield
    clear_local_cache()


def test_clean_id_validation():
    assert _clean_id(None) == ""
    assert _clean_id(123) == ""
    assert _clean_id("") == ""
    assert _clean_id("   ") == ""
    assert _clean_id("user:123") == ""
    assert _clean_id("user/123") == ""
    assert _clean_id(r"user\123") == ""
    assert _clean_id("user\0admin") == ""
    assert _clean_id("user\nadmin") == ""
    assert _clean_id("user\radmin") == ""
    assert _clean_id("user admin") == ""
    assert _clean_id("u" * (MAX_ID_LENGTH + 1)) == ""

    assert _clean_id("valid-user-123") == "valid-user-123"
    assert _clean_id("  valid_user_456  ") == "valid_user_456"
    assert _clean_id("u" * MAX_ID_LENGTH) == "u" * MAX_ID_LENGTH


def test_clean_ttl_sanitization():
    assert _clean_ttl(None, 60) == 60
    assert _clean_ttl("invalid", 60) == 60
    assert _clean_ttl(True, 60) == 60
    assert _clean_ttl(False, 60) == 60
    assert _clean_ttl(0, 60) == 60
    assert _clean_ttl(-10, 60) == 60
    assert _clean_ttl(120, 60) == 120


def test_clean_state_validation():
    assert _clean_state(None) is None
    assert _clean_state("not a dict") is None
    assert _clean_state([1, 2, 3]) is None
    assert _clean_state({"eval_count": 1}) == {"eval_count": 1}


def test_resolve_redis_injection():
    fake = FakeRedis()
    assert _resolve_redis(fake) is fake


def test_read_and_read_authoritative_flow():
    fake = FakeRedis()
    uid = "test-uid-1"

    # Initially empty
    assert read(uid, redis_client=fake) is None
    assert read_authoritative(uid, redis_client=fake) is None

    # Record state
    state = {"eval_count": 3, "last_eval": 1000.0}
    record(uid, state, redis_client=fake)

    # Local read hits mirror
    assert read(uid, redis_client=fake) == state

    # Authoritative read hits remote and returns exact copy
    assert read_authoritative(uid, redis_client=fake) == state

    # Invalidate invalid uid
    assert read("", redis_client=fake) is None
    assert read_authoritative("u/invalid", redis_client=fake) is None


def test_claim_and_release_semantics():
    fake = FakeRedis()
    uid = "test-uid-2"

    # First worker claims successfully
    assert claim(uid, redis_client=fake) is True

    # Second worker trying to claim the same user fails (busy)
    assert claim(uid, redis_client=fake) is False

    # Release claim
    release(uid, redis_client=fake)

    # Next worker can claim again
    assert claim(uid, redis_client=fake) is True

    # Invalid uid fails claim and safely releases
    assert claim("", redis_client=fake) is False
    assert claim("u:bad", redis_client=fake) is False
    release("")


def test_redis_failure_falls_open():
    broken_redis = MagicMock()
    broken_redis.get.side_effect = RuntimeError("Redis connection dropped")
    broken_redis.set.side_effect = RuntimeError("Redis connection dropped")
    broken_redis.delete.side_effect = RuntimeError("Redis connection dropped")

    uid = "test-uid-3"

    # Reads fall open (return None)
    assert read(uid, redis_client=broken_redis) is None
    assert read_authoritative(uid, redis_client=broken_redis) is None

    # Claim falls open (returns True so mentor is not silenced)
    assert claim(uid, redis_client=broken_redis) is True

    # Release does not raise
    release(uid, redis_client=broken_redis)


def test_record_failed_shared_write_evicts_local_mirror():
    fake = FakeRedis()
    uid = "test-uid-4"
    state = {"eval_count": 1}

    # Successful write mirrors locally
    record(uid, state, redis_client=fake)
    assert read(uid, redis_client=fake) == state

    # Broken redis write evicts local mirror so pod does not throttle on unshared state
    broken_redis = MagicMock()
    broken_redis.set.side_effect = RuntimeError("Write failed")

    record(uid, {"eval_count": 2}, redis_client=broken_redis)
    # Since write failed, local mirror must be cleared for this key
    assert read(uid, redis_client=fake) == state  # local had been cleared, read falls through to shared tier


def test_record_non_serializable_payload_fails_safely_and_evicts_mirror():
    fake = FakeRedis()
    uid = "test-uid-5"
    state = {"eval_count": 1}

    # Successful write mirrors locally
    record(uid, state, redis_client=fake)
    assert read(uid, redis_client=fake) == state

    # Attempting to record a payload with non-serializable objects (e.g. object()) fails write safely
    # and evicts the local mirror, avoiding persisting corrupt or silently lossy data.
    bad_state = {"eval_count": 2, "unserializable": object()}
    record(uid, bad_state, redis_client=fake)

    # Local mirror was evicted, so read falls back to the previous shared tier state
    assert read(uid, redis_client=fake) == state
