from __future__ import annotations

import os
import time
from typing import Any, Dict
import pytest

import database.mcp_cache_integrity as integrity
import database.mcp_token_cache as token_cache


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, Any] = {}
        self.sets: dict[str, set[str]] = {}
        self.ttls: dict[str, int] = {}

    def get(self, key: str) -> Any:
        return self.store.get(key)

    def set(self, key: str, value: Any, ex: int | None = None, nx: bool = False) -> bool:
        if nx and key in self.store:
            return False
        self.store[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    def exists(self, key: str) -> int:
        return 1 if key in self.store else 0

    def delete(self, *keys: str) -> int:
        count = 0
        for k in keys:
            if k in self.store:
                del self.store[k]
                count += 1
            if k in self.sets:
                del self.sets[k]
                count += 1
        return count

    def sadd(self, key: str, *members: str) -> int:
        s = self.sets.setdefault(key, set())
        initial = len(s)
        s.update(members)
        return len(s) - initial

    def smembers(self, key: str) -> set[str]:
        return set(self.sets.get(key, set()))

    def expire(self, key: str, seconds: int) -> bool:
        self.ttls[key] = seconds
        return True


# ==============================================================================
# MCP Cache Integrity Resilience Tests
# ==============================================================================


def test_dumps_signed_handles_unserializable_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENCRYPTION_SECRET", "test_secret_key_12345678901234567890")

    # Custom non-serializable object
    class NonSerializable:
        pass

    assert integrity.dumps_signed(NonSerializable(), "at") is None


def test_dumps_signed_and_loads_verified_whitespace_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENCRYPTION_SECRET", "   ")
    assert not integrity.integrity_available()
    assert integrity.dumps_signed({"test": 1}, "at") is None
    assert integrity.loads_verified('{"v":2,"type":"at","data":{"test":1},"mac":"dummy"}', "at") is None


def test_loads_verified_invalid_and_corrupt_types(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENCRYPTION_SECRET", "test_secret_key_12345678901234567890")

    # Non-string input
    assert integrity.loads_verified(None, "at") is None
    assert integrity.loads_verified(123, "at") is None  # type: ignore[arg-type]

    # Malformed JSON
    assert integrity.loads_verified("invalid json", "at") is None

    # Valid JSON but wrong envelope structure
    assert integrity.loads_verified("{}", "at") is None
    assert integrity.loads_verified('{"v": 1, "type": "at", "data": "foo", "mac": "bar"}', "at") is None
    assert integrity.loads_verified('{"v": 2, "type": "wrong_tag", "data": "foo", "mac": "bar"}', "at") is None
    assert integrity.loads_verified('{"v": 2, "type": "at", "mac": "bar"}', "at") is None

    # Forged MAC
    valid_blob = integrity.dumps_signed({"user": "alice"}, "at")
    assert valid_blob is not None
    tampered_blob = valid_blob.replace("alice", "bob")
    assert integrity.loads_verified(tampered_blob, "at") is None


# ==============================================================================
# MCP Token Cache Resilience Tests
# ==============================================================================


def test_read_access_token_empty_inputs() -> None:
    assert token_cache.read_access_token("", "https://api.example.com") is None
    assert token_cache.read_access_token("   ", "https://api.example.com") is None
    assert token_cache.read_access_token("token_123", "") is None
    assert token_cache.read_access_token("token_123", "   ") is None
    assert token_cache.read_access_token(None, "https://api.example.com") is None  # type: ignore[arg-type]


def test_fill_access_token_malformed_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENCRYPTION_SECRET", "test_secret_key_12345678901234567890")
    fake_redis = _FakeRedis()
    monkeypatch.setattr(token_cache, "_redis", lambda: fake_redis)

    now = time.time()
    valid_expiry = now + 120

    # Non-dict identity
    token_cache.fill_access_token("at_1", None, valid_expiry, index_ttl_seconds=3600)  # type: ignore[arg-type]
    assert len(fake_redis.store) == 0

    # Missing required keys (must not raise KeyError)
    incomplete_identities = [
        {},
        {"uid": "u1"},
        {"uid": "u1", "client_id": "c1"},
        {"uid": "u1", "client_id": "c1", "resource": "r1"},
        {"uid": "u1", "client_id": "c1", "resource": "r1", "scopes": []},  # empty scopes
        {
            "uid": "u1",
            "client_id": "c1",
            "resource": "r1",
            "scopes": ["mcp:full_access"],
            "grant_id": "",
        },  # empty grant
        {"uid": "", "client_id": "c1", "resource": "r1", "scopes": ["mcp:full_access"], "grant_id": "g1"},  # empty uid
    ]

    for identity in incomplete_identities:
        token_cache.fill_access_token("at_1", identity, valid_expiry, index_ttl_seconds=3600)
        assert len(fake_redis.store) == 0


def test_fill_access_token_invalid_expiry_and_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENCRYPTION_SECRET", "test_secret_key_12345678901234567890")
    fake_redis = _FakeRedis()
    monkeypatch.setattr(token_cache, "_redis", lambda: fake_redis)

    identity = {
        "uid": "user_123",
        "client_id": "client_abc",
        "resource": "https://api.example.com/mcp",
        "scopes": ["mcp:full_access"],
        "grant_id": "grant_xyz",
    }

    # Empty token
    token_cache.fill_access_token("   ", identity, time.time() + 100, index_ttl_seconds=3600)
    assert len(fake_redis.store) == 0

    # Past expiry
    token_cache.fill_access_token("at_1", identity, time.time() - 10, index_ttl_seconds=3600)
    assert len(fake_redis.store) == 0

    # NaN / Infinite expiry
    token_cache.fill_access_token("at_1", identity, float("nan"), index_ttl_seconds=3600)
    token_cache.fill_access_token("at_1", identity, float("inf"), index_ttl_seconds=3600)
    assert len(fake_redis.store) == 0


def test_fill_access_token_clamps_index_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENCRYPTION_SECRET", "test_secret_key_12345678901234567890")
    fake_redis = _FakeRedis()
    monkeypatch.setattr(token_cache, "_redis", lambda: fake_redis)

    identity = {
        "uid": "user_123",
        "client_id": "client_abc",
        "resource": "https://api.example.com/mcp",
        "scopes": ["mcp:full_access"],
        "grant_id": "grant_xyz",
    }

    # Zero or negative index TTL must clamp to positive integer to prevent immediate purge
    token_cache.fill_access_token("at_1", identity, time.time() + 50, index_ttl_seconds=-5)
    grant_key = token_cache._grant_tokens_key("grant_xyz")
    assert fake_redis.ttls[grant_key] >= 1


def test_invalidate_grant_empty_and_base_key_protection(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = _FakeRedis()
    monkeypatch.setattr(token_cache, "_redis", lambda: fake_redis)

    # Empty grant_id returns without doing anything
    token_cache.invalidate_grant("", marker_ttl_seconds=3600)
    token_cache.invalidate_grant("   ", marker_ttl_seconds=3600)
    assert len(fake_redis.store) == 0

    # Seed grant index with empty/blank hashes to test base key protection
    index_key = token_cache._grant_tokens_key("grant_123")
    fake_redis.sadd(index_key, "", "   ", "valid_hash_456")
    fake_redis.set("mcp:oauth:at:", "IMPORTANT_BASE_PREFIX_CONTENT")
    fake_redis.set("mcp:oauth:at:valid_hash_456", "token_content")

    token_cache.invalidate_grant("grant_123", marker_ttl_seconds=3600)

    # Base key prefix MUST NOT be deleted
    assert fake_redis.get("mcp:oauth:at:") == "IMPORTANT_BASE_PREFIX_CONTENT"
    # Specific valid hash must be deleted
    assert fake_redis.get("mcp:oauth:at:valid_hash_456") is None


def test_claim_last_used_write_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = _FakeRedis()
    monkeypatch.setattr(token_cache, "_redis", lambda: fake_redis)

    assert token_cache.claim_last_used_write("") is False
    assert token_cache.claim_last_used_write("   ") is False
    assert token_cache.claim_last_used_write(None) is False  # type: ignore[arg-type]

    # Valid token claims successfully once
    assert token_cache.claim_last_used_write("valid_token_123") is True
    # Immediate repeat claim is throttled
    assert token_cache.claim_last_used_write("valid_token_123") is False
