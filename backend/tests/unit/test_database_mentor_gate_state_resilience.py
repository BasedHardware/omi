"""Unit tests for database.mentor_gate_state resilience and defensive input boundaries."""

import json
from unittest.mock import MagicMock, patch

import pytest

import database.mentor_gate_state as mgs


@pytest.fixture(autouse=True)
def reset_local_cache():
    """Clear in-memory mirror and reset state before and after each test."""
    with mgs._local_lock:
        mgs._local.clear()
    yield
    with mgs._local_lock:
        mgs._local.clear()


class FakeRedis:
    def __init__(self):
        self.store = {}
        self.expirations = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.store:
            return False
        self.store[key] = value
        if ex is not None:
            self.expirations[key] = ex
        return True

    def delete(self, key):
        self.store.pop(key, None)
        self.expirations.pop(key, None)


def test_clean_uid_helper():
    assert mgs._clean_uid("user_123") == "user_123"
    assert mgs._clean_uid("  user_123  ") == "user_123"
    assert mgs._clean_uid("") is None
    assert mgs._clean_uid("   ") is None
    assert mgs._clean_uid(None) is None
    assert mgs._clean_uid(12345) is None


def test_safe_ttl_helper():
    assert mgs._safe_ttl(60, default=30) == 60
    assert mgs._safe_ttl("120", default=30) == 120
    assert mgs._safe_ttl(-10, default=30) == 30
    assert mgs._safe_ttl(0, default=30) == 30
    assert mgs._safe_ttl("invalid", default=30) == 30
    assert mgs._safe_ttl(None, default=30) == 30


def test_read_and_read_authoritative_with_invalid_uid_falls_open():
    assert mgs.read("") is None
    assert mgs.read("   ") is None
    assert mgs.read(None) is None
    assert mgs.read(1234) is None

    assert mgs.read_authoritative("") is None
    assert mgs.read_authoritative("   ") is None
    assert mgs.read_authoritative(None) is None


def test_claim_and_release_with_invalid_uid_fails_open():
    # Claim must fail open (return True) so invalid inputs do not silence the mentor
    assert mgs.claim("") is True
    assert mgs.claim("   ") is True
    assert mgs.claim(None) is True

    # Release with invalid uid should be a safe no-op
    mgs.release("")
    mgs.release("   ")
    mgs.release(None)


def test_record_with_invalid_uid_or_non_dict_state_is_noop():
    fake_redis = FakeRedis()
    with patch("database.redis_db.r", fake_redis):
        mgs.record("", {"eval": 1})
        mgs.record("   ", {"eval": 1})
        mgs.record(None, {"eval": 1})
        mgs.record("user_1", "not-a-dict")
        mgs.record("user_1", None)
        mgs.record("user_1", [1, 2, 3])

    assert len(fake_redis.store) == 0
    with mgs._local_lock:
        assert len(mgs._local) == 0


def test_record_and_read_normalizes_whitespace():
    fake_redis = FakeRedis()
    with patch("database.redis_db.r", fake_redis):
        mgs.record("  user_space_1  ", {"count": 42}, ttl=3600)

        # Stored in redis under trimmed key
        assert "user_space_1:mentor_gate_eval_state" in fake_redis.store

        # Readable with or without whitespace
        result1 = mgs.read("  user_space_1  ")
        assert result1 == {"count": 42}

        result2 = mgs.read_authoritative("user_space_1")
        assert result2 == {"count": 42}


def test_claim_safe_ttl_clamping():
    fake_redis = FakeRedis()
    with patch("database.redis_db.r", fake_redis):
        # Negative ttl clamps to default CLAIM_TTL_SECONDS
        assert mgs.claim("user_ttl", ttl=-50) is True
        assert fake_redis.expirations["user_ttl:mentor_gate_eval_claim"] == mgs.CLAIM_TTL_SECONDS

        # Re-claiming while held returns False
        assert mgs.claim("user_ttl", ttl=10) is False

        # Release frees the claim
        mgs.release("  user_ttl  ")
        assert "user_ttl:mentor_gate_eval_claim" not in fake_redis.store


def test_record_safe_ttl_clamping():
    fake_redis = FakeRedis()
    with patch("database.redis_db.r", fake_redis):
        mgs.record("user_clamp", {"status": "ok"}, ttl=-100)
        assert fake_redis.expirations["user_clamp:mentor_gate_eval_state"] == mgs.STATE_TTL_SECONDS

        mgs.record("user_clamp2", {"status": "ok"}, ttl="invalid")
        assert fake_redis.expirations["user_clamp2:mentor_gate_eval_state"] == mgs.STATE_TTL_SECONDS

        mgs.record("user_clamp3", {"status": "ok"}, ttl=500)
        assert fake_redis.expirations["user_clamp3:mentor_gate_eval_state"] == 500


def test_record_non_json_serializable_fails_safely():
    fake_redis = FakeRedis()
    with patch("database.redis_db.r", fake_redis):
        # Set objects are not JSON serializable by default
        mgs.record("user_unserializable", {"tags": {1, 2, 3}})

    # Should not crash, and should not be stored in redis or local
    assert "user_unserializable:mentor_gate_eval_state" not in fake_redis.store
    with mgs._local_lock:
        assert "user_unserializable" not in mgs._local


def test_corrupted_json_in_redis_falls_open():
    fake_redis = FakeRedis()
    fake_redis.store["user_bad:mentor_gate_eval_state"] = "not-json{{"
    with patch("database.redis_db.r", fake_redis):
        result = mgs.read_authoritative("user_bad")
        assert result is None


def test_redis_connection_error_falls_open():
    mock_redis = MagicMock()
    mock_redis.get.side_effect = ConnectionError("Redis down")
    mock_redis.set.side_effect = ConnectionError("Redis down")

    with patch("database.redis_db.r", mock_redis):
        assert mgs.read_authoritative("user_conn") is None
        assert mgs.claim("user_conn") is True
        # Record does not crash
        mgs.record("user_conn", {"val": 1})
        with mgs._local_lock:
            assert "user_conn" not in mgs._local


def test_local_cache_bounded_eviction():
    with patch.object(mgs, "_MAX_LOCAL_ENTRIES", 3):
        mgs._write_local("u1", {"i": 1}, ttl=100)
        mgs._write_local("u2", {"i": 2}, ttl=100)
        mgs._write_local("u3", {"i": 3}, ttl=100)

        with mgs._local_lock:
            assert len(mgs._local) == 3

        # Adding 4th item triggers bounded eviction
        mgs._write_local("u4", {"i": 4}, ttl=100)

        with mgs._local_lock:
            assert len(mgs._local) <= 3
            assert "u4" in mgs._local
