"""Hermetic unit tests for action_items_cache hardening and resilience."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
import redis as redis_pkg

from database import action_items_cache as aic


def test_sanitize_uid() -> None:
    assert aic._sanitize_uid("user_123") == "user_123"
    assert aic._sanitize_uid("  user_abc  ") == "user_abc"
    assert aic._sanitize_uid("") is None
    assert aic._sanitize_uid("   ") is None
    assert aic._sanitize_uid(None) is None
    assert aic._sanitize_uid(12345) is None
    assert aic._sanitize_uid(["user"]) is None
    assert aic._sanitize_uid("user\nnewline") is None
    assert aic._sanitize_uid("user\x00null") is None


def test_list_cache_ttl_clamping(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ACTION_ITEMS_LIST_CACHE_TTL_SECONDS", raising=False)
    assert aic.list_cache_ttl_seconds() == 30

    monkeypatch.setenv("ACTION_ITEMS_LIST_CACHE_TTL_SECONDS", "60")
    assert aic.list_cache_ttl_seconds() == 60

    monkeypatch.setenv("ACTION_ITEMS_LIST_CACHE_TTL_SECONDS", "0")
    assert aic.list_cache_ttl_seconds() == 0

    monkeypatch.setenv("ACTION_ITEMS_LIST_CACHE_TTL_SECONDS", "-10")
    assert aic.list_cache_ttl_seconds() == 0

    monkeypatch.setenv("ACTION_ITEMS_LIST_CACHE_TTL_SECONDS", "1000")
    assert aic.list_cache_ttl_seconds() == aic._TTL_MAX_SECONDS

    monkeypatch.setenv("ACTION_ITEMS_LIST_CACHE_TTL_SECONDS", "not_a_number")
    assert aic.list_cache_ttl_seconds() == 30


def test_bump_action_items_list_version() -> None:
    mock_redis = MagicMock()
    mock_pipe = MagicMock()
    mock_redis.pipeline.return_value = mock_pipe

    with patch.object(aic.redis_db, "r", mock_redis):
        # Empty or invalid uid does nothing
        aic.bump_action_items_list_version("")
        aic.bump_action_items_list_version("   ")
        mock_redis.pipeline.assert_not_called()

        # Valid uid invokes pipeline
        aic.bump_action_items_list_version("user_42")
        mock_pipe.incr.assert_called_once_with("ail:ver:user_42")
        mock_pipe.expire.assert_called_once_with("ail:ver:user_42", aic._VERSION_TTL_SECONDS)
        mock_pipe.execute.assert_called_once()

        # RedisError is swallowed fail-open
        mock_pipe.execute.side_effect = redis_pkg.exceptions.RedisError("Connection reset")
        aic.bump_action_items_list_version("user_42")  # does not raise

        # Generic Exception is swallowed fail-open
        mock_pipe.execute.side_effect = RuntimeError("Pool destroyed")
        aic.bump_action_items_list_version("user_42")  # does not raise


def test_get_action_items_list_version() -> None:
    mock_redis = MagicMock()

    with patch.object(aic.redis_db, "r", mock_redis):
        # Invalid uid returns None
        assert aic.get_action_items_list_version("") is None
        assert aic.get_action_items_list_version(None) is None  # type: ignore[arg-type]

        # Cache miss returns 0
        mock_redis.get.return_value = None
        assert aic.get_action_items_list_version("u1") == 0

        # Valid version
        mock_redis.get.return_value = b"5"
        assert aic.get_action_items_list_version("u1") == 5

        # Negative version treated as unavailable (None) rather than v0
        mock_redis.get.return_value = b"-2"
        assert aic.get_action_items_list_version("u1") is None

        # Corrupted non-integer falls back to 0
        mock_redis.get.return_value = b"corrupted"
        assert aic.get_action_items_list_version("u1") == 0

        # Redis error returns None
        mock_redis.get.side_effect = redis_pkg.exceptions.ConnectionError("Redis down")
        assert aic.get_action_items_list_version("u1") is None


def test_list_cache_key_resilience() -> None:
    key1 = aic.list_cache_key("uid_1", 3, {"limit": 10})
    assert key1.startswith("ail:uid_1:3:")

    # Safe version clamping for negative numbers
    key2 = aic.list_cache_key("uid_1", -5, {"limit": 10})
    assert key2.startswith("ail:uid_1:0:")

    # Non-dict params fallback
    key3 = aic.list_cache_key("uid_1", 1, None)  # type: ignore[arg-type]
    assert key3.startswith("ail:uid_1:1:")

    # Non-string uid fallback
    key4 = aic.list_cache_key(None, 1, {})  # type: ignore[arg-type]
    assert key4.startswith("ail:unknown:1:")


def test_compute_etag() -> None:
    etag1 = aic.compute_etag({"items": [{"id": "1"}]})
    assert etag1.startswith('W/"')
    assert etag1.endswith('"')

    etag2 = aic.compute_etag([{"id": "1"}])
    assert etag2.startswith('W/"')

    # Non-dict / non-list graceful handling
    etag3 = aic.compute_etag("scalar_string")
    assert etag3.startswith('W/"')


def test_read_cached_list() -> None:
    mock_redis = MagicMock()

    with patch.object(aic.redis_db, "r", mock_redis):
        # Invalid key returns None
        assert aic.read_cached_list("") is None
        assert aic.read_cached_list("  ") is None

        # Miss
        mock_redis.get.return_value = None
        assert aic.read_cached_list("ail:key") is None

        # Valid hit
        payload = {"etag": 'W/"123"', "body": {"items": []}}
        mock_redis.get.return_value = json.dumps(payload)
        assert aic.read_cached_list("ail:key") == payload

        # Malformed JSON
        mock_redis.get.return_value = "invalid json"
        assert aic.read_cached_list("ail:key") is None

        # Missing body or etag
        mock_redis.get.return_value = json.dumps({"only_etag": "123"})
        assert aic.read_cached_list("ail:key") is None

        # Non-dict/list body in cached payload rejected
        mock_redis.get.return_value = json.dumps({"etag": 'W/"123"', "body": "garbage_string"})
        assert aic.read_cached_list("ail:key") is None

        # Non-string etag in cached payload rejected
        mock_redis.get.return_value = json.dumps({"etag": 12345, "body": {"items": []}})
        assert aic.read_cached_list("ail:key") is None

        # Redis error swallowed fail-open
        mock_redis.get.side_effect = redis_pkg.exceptions.TimeoutError("timed out")
        assert aic.read_cached_list("ail:key") is None


def test_write_cached_list() -> None:
    mock_redis = MagicMock()

    with patch.object(aic.redis_db, "r", mock_redis):
        # Invalid inputs do not call Redis
        aic.write_cached_list("", body={"items": []}, etag='W/"1"', ttl=30)
        aic.write_cached_list("k", body="not a dict", etag='W/"1"', ttl=30)
        aic.write_cached_list("k", body={"items": []}, etag="", ttl=30)
        aic.write_cached_list("k", body={"items": []}, etag='W/"1"', ttl=0)
        aic.write_cached_list("k", body={"items": []}, etag='W/"1"', ttl=-10)
        aic.write_cached_list("k", body={"items": []}, etag='W/"1"', ttl=float("inf"))  # type: ignore[arg-type]
        mock_redis.set.assert_not_called()

        # Valid write clamps TTL
        aic.write_cached_list("ail:k", body={"items": []}, etag='W/"1"', ttl=500)
        mock_redis.set.assert_called_once()
        _, kwargs = mock_redis.set.call_args
        assert kwargs["ex"] == aic._TTL_MAX_SECONDS

        # RedisError is swallowed fail-open
        mock_redis.set.side_effect = redis_pkg.exceptions.RedisError("Write error")
        aic.write_cached_list("ail:k", body={"items": []}, etag='W/"1"', ttl=30)  # does not raise


def test_if_none_match_matches() -> None:
    etag = 'W/"3b5d20"'

    # Empty inputs return False
    assert not aic.if_none_match_matches(None, etag)
    assert not aic.if_none_match_matches("", etag)
    assert not aic.if_none_match_matches('W/"3b5d20"', "")

    # Wildcard matches everything
    assert aic.if_none_match_matches("*", etag)

    # Identical weak ETag
    assert aic.if_none_match_matches('W/"3b5d20"', etag)

    # Quoted string without W/ matches weak ETag
    assert aic.if_none_match_matches('"3b5d20"', etag)

    # Unquoted string does not match under RFC 9110
    assert not aic.if_none_match_matches("3b5d20", etag)

    # Multiple candidates
    assert aic.if_none_match_matches('"other", "3b5d20", "xyz"', etag)
    assert not aic.if_none_match_matches('"other", "different"', etag)
