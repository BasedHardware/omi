"""Hermetic unit tests for action_items_cache resilience, security, and fail-open guarantees."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
import pytest
import redis as redis_pkg

from database.action_items_cache import (
    MAX_KEY_LENGTH,
    MAX_UID_LENGTH,
    _clean_key,
    _clean_uid,
    _version_key,
    bump_action_items_list_version,
    compute_etag,
    get_action_items_list_version,
    if_none_match_matches,
    list_cache_key,
    list_cache_ttl_seconds,
    read_cached_list,
    write_cached_list,
)


def test_clean_uid_validation():
    assert _clean_uid(None) == ""
    assert _clean_uid(12345) == ""
    assert _clean_uid("") == ""
    assert _clean_uid("   ") == ""
    assert _clean_uid("u" * (MAX_UID_LENGTH + 1)) == ""
    assert _clean_uid("user\rname") == ""
    assert _clean_uid("user\nname") == ""
    assert _clean_uid("user\x00name") == ""
    assert _clean_uid("user..traversal") == ""

    assert _clean_uid("user_123") == "user_123"
    assert _clean_uid("  user_456  ") == "user_456"
    assert _clean_uid("u" * MAX_UID_LENGTH) == "u" * MAX_UID_LENGTH


def test_clean_key_validation():
    assert _clean_key(None) == ""
    assert _clean_key(123) == ""
    assert _clean_key("") == ""
    assert _clean_key("   ") == ""
    assert _clean_key("k" * (MAX_KEY_LENGTH + 1)) == ""
    assert _clean_key("key\r1") == ""
    assert _clean_key("key\n1") == ""
    assert _clean_key("key\x001") == ""

    assert _clean_key("ail:u1:1:abcd") == "ail:u1:1:abcd"
    assert _clean_key("  ail:u1:1:abcd  ") == "ail:u1:1:abcd"


def test_list_cache_ttl_seconds_env_parsing(monkeypatch):
    monkeypatch.delenv("ACTION_ITEMS_LIST_CACHE_TTL_SECONDS", raising=False)
    assert list_cache_ttl_seconds() == 30

    monkeypatch.setenv("ACTION_ITEMS_LIST_CACHE_TTL_SECONDS", "invalid_number")
    assert list_cache_ttl_seconds() == 30

    monkeypatch.setenv("ACTION_ITEMS_LIST_CACHE_TTL_SECONDS", "0")
    assert list_cache_ttl_seconds() == 0

    monkeypatch.setenv("ACTION_ITEMS_LIST_CACHE_TTL_SECONDS", "-10")
    assert list_cache_ttl_seconds() == 0

    monkeypatch.setenv("ACTION_ITEMS_LIST_CACHE_TTL_SECONDS", "500")
    assert list_cache_ttl_seconds() == 300  # Capped at _TTL_MAX_SECONDS

    monkeypatch.setenv("ACTION_ITEMS_LIST_CACHE_TTL_SECONDS", "45")
    assert list_cache_ttl_seconds() == 45


def test_version_key_generation():
    assert _version_key("user123") == "ail:ver:user123"
    assert _version_key("") == ""
    assert _version_key("   ") == ""
    assert _version_key("bad\nuser") == ""


def test_bump_action_items_list_version_happy_path():
    fake_client = MagicMock()
    fake_pipe = MagicMock()
    fake_client.pipeline.return_value = fake_pipe

    with patch("database.action_items_cache.redis_db.r", fake_client):
        bump_action_items_list_version("user123")

    fake_client.pipeline.assert_called_once()
    fake_pipe.incr.assert_called_once_with("ail:ver:user123")
    fake_pipe.expire.assert_called_once_with("ail:ver:user123", 7 * 24 * 3600)
    fake_pipe.execute.assert_called_once()


def test_bump_action_items_list_version_fail_open_redis_error():
    fake_client = MagicMock()
    fake_client.pipeline.side_effect = redis_pkg.exceptions.ConnectionError("Redis down")

    with patch("database.action_items_cache.redis_db.r", fake_client):
        # Must swallow RedisError and fail open
        bump_action_items_list_version("user123")


def test_bump_action_items_list_version_client_none_fail_open():
    with patch("database.action_items_cache.redis_db.r", None):
        # Must not raise AttributeError
        bump_action_items_list_version("user123")


def test_get_action_items_list_version_happy_path():
    fake_client = MagicMock()
    fake_client.get.return_value = b"42"

    with patch("database.action_items_cache.redis_db.r", fake_client):
        assert get_action_items_list_version("user123") == 42

    # Key does not exist in Redis -> version 0
    fake_client.get.return_value = None
    with patch("database.action_items_cache.redis_db.r", fake_client):
        assert get_action_items_list_version("user123") == 0

    # Malformed non-integer in Redis -> version 0
    fake_client.get.return_value = b"corrupted"
    with patch("database.action_items_cache.redis_db.r", fake_client):
        assert get_action_items_list_version("user123") == 0


def test_get_action_items_list_version_fail_open_redis_error():
    fake_client = MagicMock()
    fake_client.get.side_effect = redis_pkg.exceptions.TimeoutError("Redis timeout")

    with patch("database.action_items_cache.redis_db.r", fake_client):
        assert get_action_items_list_version("user123") is None


def test_get_action_items_list_version_client_none():
    with patch("database.action_items_cache.redis_db.r", None):
        assert get_action_items_list_version("user123") is None


def test_list_cache_key_generation():
    params = {"limit": 50, "offset": 0, "completed": False}
    key1 = list_cache_key("u1", 2, params)
    assert key1.startswith("ail:u1:2:")

    # Deterministic hashing regardless of dict key order
    params_reversed = {"completed": False, "offset": 0, "limit": 50}
    key2 = list_cache_key("u1", 2, params_reversed)
    assert key1 == key2

    # Malformed version or uid handled gracefully
    key3 = list_cache_key("", -5, None)  # type: ignore[arg-type]
    assert key3.startswith("ail:anonymous:0:")


def test_compute_etag():
    body = {"items": [{"id": 1, "text": "test"}], "total": 1}
    etag1 = compute_etag(body)
    assert etag1.startswith('W/"')
    assert etag1.endswith('"')

    # Identical content yields identical ETag
    etag2 = compute_etag({"total": 1, "items": [{"id": 1, "text": "test"}]})
    assert etag1 == etag2

    # Non-dict body fallback
    etag3 = compute_etag(None)  # type: ignore[arg-type]
    assert etag3.startswith('W/"')


def test_read_cached_list_happy_path():
    fake_client = MagicMock()
    payload = {"etag": 'W/"123"', "body": {"items": [1, 2]}}
    fake_client.get.return_value = json.dumps(payload).encode("utf-8")

    with patch("database.action_items_cache.redis_db.r", fake_client):
        res = read_cached_list("ail:u1:1:abc")
        assert res == payload


def test_read_cached_list_corrupted_payload():
    fake_client = MagicMock()

    with patch("database.action_items_cache.redis_db.r", fake_client):
        # Empty string
        fake_client.get.return_value = b""
        assert read_cached_list("ail:u1:1:abc") is None

        # Invalid JSON
        fake_client.get.return_value = b"invalid json"
        assert read_cached_list("ail:u1:1:abc") is None

        # JSON is a list, not dict
        fake_client.get.return_value = json.dumps([1, 2, 3]).encode("utf-8")
        assert read_cached_list("ail:u1:1:abc") is None

        # Missing 'body'
        fake_client.get.return_value = json.dumps({"etag": 'W/"123"'}).encode("utf-8")
        assert read_cached_list("ail:u1:1:abc") is None

        # 'body' is not a dict
        fake_client.get.return_value = json.dumps({"etag": 'W/"123"', "body": "not_dict"}).encode("utf-8")
        assert read_cached_list("ail:u1:1:abc") is None

        # 'etag' is not a str
        fake_client.get.return_value = json.dumps({"etag": 12345, "body": {}}).encode("utf-8")
        assert read_cached_list("ail:u1:1:abc") is None


def test_read_cached_list_fail_open():
    fake_client = MagicMock()
    fake_client.get.side_effect = redis_pkg.exceptions.RedisError("Err")

    with patch("database.action_items_cache.redis_db.r", fake_client):
        assert read_cached_list("ail:u1:1:abc") is None

    with patch("database.action_items_cache.redis_db.r", None):
        assert read_cached_list("ail:u1:1:abc") is None


def test_write_cached_list_happy_path_and_ttl_clamping():
    fake_client = MagicMock()

    with patch("database.action_items_cache.redis_db.r", fake_client):
        # Normal write
        write_cached_list("ail:u1:1:abc", body={"items": []}, etag='W/"etag1"', ttl=30)
        fake_client.set.assert_called_once()
        args, kwargs = fake_client.set.call_args
        assert args[0] == "ail:u1:1:abc"
        assert kwargs["ex"] == 30
        written = json.loads(args[1])
        assert written == {"etag": 'W/"etag1"', "body": {"items": []}}

        fake_client.reset_mock()

        # TTL clamping: ttl 1000 clamped to 300
        write_cached_list("ail:u1:1:abc", body={"items": []}, etag='W/"etag1"', ttl=1000)
        _, kwargs = fake_client.set.call_args
        assert kwargs["ex"] == 300

        fake_client.reset_mock()

        # Non-positive TTL: should not write
        write_cached_list("ail:u1:1:abc", body={"items": []}, etag='W/"etag1"', ttl=0)
        fake_client.set.assert_not_called()

        write_cached_list("ail:u1:1:abc", body={"items": []}, etag='W/"etag1"', ttl=-5)
        fake_client.set.assert_not_called()


def test_write_cached_list_fail_open():
    fake_client = MagicMock()
    fake_client.set.side_effect = redis_pkg.exceptions.RedisError("Err")

    with patch("database.action_items_cache.redis_db.r", fake_client):
        # Must not raise
        write_cached_list("ail:u1:1:abc", body={"items": []}, etag='W/"etag1"', ttl=30)

    with patch("database.action_items_cache.redis_db.r", None):
        # Must not raise when client is None
        write_cached_list("ail:u1:1:abc", body={"items": []}, etag='W/"etag1"', ttl=30)


def test_if_none_match_matches():
    # Empty inputs
    assert if_none_match_matches(None, 'W/"123"') is False
    assert if_none_match_matches("", 'W/"123"') is False
    assert if_none_match_matches('W/"123"', "") is False

    # Wildcard
    assert if_none_match_matches("*", 'W/"123"') is True
    assert if_none_match_matches('"other", *', 'W/"123"') is True

    # Exact and normalized weak / strong comparisons
    assert if_none_match_matches('W/"123"', 'W/"123"') is True
    assert if_none_match_matches('"123"', 'W/"123"') is True
    assert if_none_match_matches('123', 'W/"123"') is True
    assert if_none_match_matches('W/"123"', '"123"') is True
    assert if_none_match_matches('  W/"123"  ', 'W/"123"') is True

    # List of candidate tags
    assert if_none_match_matches('"old1", "123", "old2"', 'W/"123"') is True
    assert if_none_match_matches('"old1", "old2"', 'W/"123"') is False
