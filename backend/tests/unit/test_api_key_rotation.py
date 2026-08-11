"""Secret rotation for MCP and Developer API keys."""

from datetime import datetime, timezone

import pytest

import database.dev_api_key as dev_api_key_db
import database.mcp_api_key as mcp_api_key_db
from database.api_key_metadata import ApiKeyNotFoundError, ApiKeyRevocationUnavailableError
from tests.unit.test_mcp_api_key_full_access import _DB, _Redis

_VALID_HASH = "a" * 64


class _DevRedis(_Redis):
    def delete_cached_dev_api_key_strict(self, _hashed_key):
        self.auth_context = None
        return True


def _install(monkeypatch, module, db, redis):
    monkeypatch.setattr(module, "get_firestore_client", lambda: db)
    monkeypatch.setattr(module, "redis_db", redis)


def test_rotate_mcp_key_preserves_identity_and_retires_the_previous_secret(monkeypatch):
    db = _DB()
    redis = _Redis()
    created_at = datetime.now(timezone.utc)
    db.collection("mcp_api_keys").document("key-1").set(
        {
            "id": "key-1",
            "user_id": "user-1",
            "name": "Agent",
            "hashed_key": _VALID_HASH,
            "key_prefix": "omi_mcp",
            "created_at": created_at,
            "last_used_at": created_at,
            "app_id": mcp_api_key_db.MCP_DEFAULT_APP_ID,
            "scopes": ["memories.read"],
        }
    )
    redis.auth_context = {"user_id": "user-1", "scopes": ["memories.read"], "key_id": "key-1", "app_id": "mcp-api"}
    _install(monkeypatch, mcp_api_key_db, db, redis)
    monkeypatch.setattr(mcp_api_key_db, "generate_api_key", lambda: ("omi_mcp_new", "b" * 64, "omi_mcp"))

    raw_key, key = mcp_api_key_db.rotate_mcp_key("user-1", "key-1")

    assert raw_key == "omi_mcp_new"
    assert key.id == "key-1"
    assert key.name == "Agent"
    assert key.scopes == ["memories.read"]
    assert key.app_id == mcp_api_key_db.MCP_DEFAULT_APP_ID
    assert key.last_used_at is None

    stored = db.collection("mcp_api_keys").document("key-1").get().to_dict()
    assert stored["hashed_key"] == "b" * 64
    assert stored["created_at"] == created_at
    assert stored["scopes"] == ["memories.read"]
    assert stored["rotated_at"] is not None
    # The retired secret must not survive in the auth cache.
    assert redis.auth_context is None
    # No raw secret is ever persisted.
    assert "omi_mcp_new" not in str(stored)


def test_rotate_mcp_key_rejects_a_key_owned_by_another_user(monkeypatch):
    db = _DB()
    redis = _Redis()
    db.collection("mcp_api_keys").document("key-1").set(
        {"id": "key-1", "user_id": "owner", "name": "Agent", "hashed_key": _VALID_HASH}
    )
    _install(monkeypatch, mcp_api_key_db, db, redis)

    with pytest.raises(ApiKeyNotFoundError):
        mcp_api_key_db.rotate_mcp_key("intruder", "key-1")
    with pytest.raises(ApiKeyNotFoundError):
        mcp_api_key_db.rotate_mcp_key("owner", "missing-key")
    assert db.collection("mcp_api_keys").document("key-1").get().to_dict()["hashed_key"] == _VALID_HASH


def test_rotate_mcp_key_refuses_when_the_previous_secret_cannot_be_uncached(monkeypatch):
    db = _DB()
    redis = _Redis()
    db.collection("mcp_api_keys").document("key-1").set(
        {"id": "key-1", "user_id": "user-1", "name": "Agent", "hashed_key": _VALID_HASH}
    )
    _install(monkeypatch, mcp_api_key_db, db, redis)
    monkeypatch.setattr(redis, "delete_cached_mcp_api_key_strict", lambda _hash: False)

    with pytest.raises(ApiKeyRevocationUnavailableError):
        mcp_api_key_db.rotate_mcp_key("user-1", "key-1")
    assert db.collection("mcp_api_keys").document("key-1").get().to_dict()["hashed_key"] == _VALID_HASH


def test_rotate_dev_key_preserves_name_and_scopes_and_issues_a_new_secret(monkeypatch):
    db = _DB()
    redis = _DevRedis()
    created_at = datetime.now(timezone.utc)
    db.collection("dev_api_keys").document("key-1").set(
        {
            "id": "key-1",
            "user_id": "user-1",
            "name": "Server",
            "hashed_key": _VALID_HASH,
            "key_prefix": "sk_omi_test",
            "created_at": created_at,
            "last_used_at": created_at,
            "app_id": dev_api_key_db.DEV_API_KEY_APP_ID,
            "scopes": ["memories:read"],
        }
    )
    _install(monkeypatch, dev_api_key_db, db, redis)
    monkeypatch.setattr(dev_api_key_db, "generate_dev_api_key", lambda: ("sk_omi_new", "c" * 64, "sk_omi_new_"))

    raw_key, key = dev_api_key_db.rotate_dev_key("user-1", "key-1")

    assert raw_key == "sk_omi_new"
    assert key.id == "key-1"
    assert key.name == "Server"
    assert key.scopes == ["memories:read"]
    assert key.last_used_at is None

    stored = db.collection("dev_api_keys").document("key-1").get().to_dict()
    assert stored["hashed_key"] == "c" * 64
    assert stored["created_at"] == created_at
    assert "sk_omi_new" not in str(stored.get("hashed_key"))


def test_rotate_dev_key_rejects_a_key_owned_by_another_user(monkeypatch):
    db = _DB()
    redis = _DevRedis()
    db.collection("dev_api_keys").document("key-1").set(
        {"id": "key-1", "user_id": "owner", "name": "Server", "hashed_key": _VALID_HASH}
    )
    _install(monkeypatch, dev_api_key_db, db, redis)

    with pytest.raises(ApiKeyNotFoundError):
        dev_api_key_db.rotate_dev_key("intruder", "key-1")
