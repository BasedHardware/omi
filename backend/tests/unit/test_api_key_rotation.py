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

    def read_cached_dev_api_key_data(self, hashed_key):
        return self.read_cached_mcp_api_key_auth_context(hashed_key)

    def cache_dev_api_key(self, hashed_key, user_id, scopes, key_id=None, app_id=None, auth_context_version=1):
        self.auth_context = {
            "user_id": user_id,
            "scopes": scopes,
            "key_id": key_id,
            "app_id": app_id,
            "auth_context_version": auth_context_version,
        }
        self.cached.append({"hashed_key": hashed_key, **self.auth_context})
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


def test_rotation_fences_an_authentication_that_races_the_secret_swap(monkeypatch):
    """A retired MCP secret cannot be re-cached into validity by an in-flight auth.

    Reproduces the interleaving directly: the racing authentication has already
    read the pre-swap Firestore document when rotation commits, so its cache write
    lands *after* rotation deleted the entry. Without the retirement fence that
    write keeps the retired secret authorizing for the remainder of the cache TTL.
    """
    db = _DB()
    redis = _Redis()
    db.collection("mcp_api_keys").document("key-1").set(
        {
            "id": "key-1",
            "user_id": "user-1",
            "name": "Agent",
            "hashed_key": _VALID_HASH,
            "key_prefix": "omi_mcp",
            "app_id": mcp_api_key_db.MCP_DEFAULT_APP_ID,
            "scopes": ["memories.read"],
        }
    )
    _install(monkeypatch, mcp_api_key_db, db, redis)
    monkeypatch.setattr(mcp_api_key_db, "generate_api_key", lambda: ("omi_mcp_new", "b" * 64, "omi_mcp"))
    monkeypatch.setattr(mcp_api_key_db, "hash_api_key", lambda secret: {"old": _VALID_HASH, "new": "b" * 64}[secret])

    # The grant check runs after the Firestore read and before the cache write —
    # exactly the window a concurrent rotation commits in.
    rotated = {}
    real_ensure = mcp_api_key_db._ensure_mcp_memory_grant

    def _rotate_mid_authentication(*args, **kwargs):
        if not rotated:
            rotated["raw"] = mcp_api_key_db.rotate_mcp_key("user-1", "key-1")
        return real_ensure(*args, **kwargs)

    monkeypatch.setattr(mcp_api_key_db, "_ensure_mcp_memory_grant", _rotate_mid_authentication)

    mcp_api_key_db.get_api_key_auth_result("omi_mcp_old")

    assert rotated, "the rotation must have committed inside the authentication window"
    # The racing authentication is free to have written a cache entry; what matters
    # is that no later request can authorize the retired secret from it.
    monkeypatch.setattr(mcp_api_key_db, "_ensure_mcp_memory_grant", real_ensure)
    assert mcp_api_key_db.get_api_key_auth_result("omi_mcp_old").context is None
    assert mcp_api_key_db.get_api_key_auth_result("omi_mcp_new").context is not None


def test_dev_rotation_fences_an_authentication_that_races_the_secret_swap(monkeypatch):
    """The same interleaving on Developer keys, which share the rotation contract."""
    db = _DB()
    redis = _DevRedis()
    db.collection("dev_api_keys").document("key-1").set(
        {
            "id": "key-1",
            "user_id": "user-1",
            "name": "Server",
            "hashed_key": _VALID_HASH,
            "key_prefix": "sk_omi_test",
            "app_id": dev_api_key_db.DEV_API_KEY_APP_ID,
            "scopes": ["memories:read"],
        }
    )
    _install(monkeypatch, dev_api_key_db, db, redis)
    monkeypatch.setattr(dev_api_key_db, "generate_dev_api_key", lambda: ("sk_omi_new", "c" * 64, "sk_omi_new_"))
    monkeypatch.setattr(
        dev_api_key_db, "hash_dev_api_key", lambda secret: {"old": _VALID_HASH, "new": "c" * 64}[secret]
    )

    # Retire the secret exactly as a concurrent rotation would, then let the
    # in-flight authentication write its pre-swap context back into the cache.
    dev_api_key_db.rotate_dev_key("user-1", "key-1")
    redis.cache_dev_api_key(_VALID_HASH, "user-1", ["memories:read"], key_id="key-1", app_id="developer_api")

    assert dev_api_key_db.get_api_key_auth_result("omi_dev_old").context is None


def test_mcp_auth_cache_written_under_the_old_scope_semantics_is_rejected(monkeypatch):
    """A rolling deploy must not let an old revision's full-access cache widen a scoped key.

    An old revision's normalize_mcp_scopes() ignored the recorded list and cached
    full access. Bumping the auth-context version is what stops a new revision from
    honoring that entry for a key it recorded as read-only.
    """
    db = _DB()
    redis = _Redis()
    db.collection("mcp_api_keys").document("key-1").set(
        {
            "id": "key-1",
            "user_id": "user-1",
            "name": "Agent",
            "hashed_key": _VALID_HASH,
            "key_prefix": "omi_mcp",
            "app_id": mcp_api_key_db.MCP_DEFAULT_APP_ID,
            "scopes": ["memories.read"],
        }
    )
    _install(monkeypatch, mcp_api_key_db, db, redis)
    monkeypatch.setattr(mcp_api_key_db, "hash_api_key", lambda _secret: _VALID_HASH)
    redis.auth_context = {
        "user_id": "user-1",
        "scopes": list(mcp_api_key_db.MCP_FULL_ACCESS_SCOPES),
        "key_id": "key-1",
        "app_id": mcp_api_key_db.MCP_DEFAULT_APP_ID,
        "auth_context_version": 3,
    }

    context = mcp_api_key_db.get_api_key_auth_result("omi_mcp_old").context

    assert context is not None
    assert context["scopes"] == ["memories.read"]
