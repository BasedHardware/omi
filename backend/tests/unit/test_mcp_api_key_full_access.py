from datetime import datetime

import pytest

import database.mcp_api_key as mcp_api_key_db
from database.api_key_metadata import ApiKeyCacheReadMode, ApiKeyCacheReadResult, ApiKeyValidationError
from tests.store_fakes import FakeDocumentStore
import scripts.backfill_mcp_key_full_access as backfill_mcp_keys


def _grant_path(uid: str) -> str:
    return (
        f"users/{uid}/{mcp_api_key_db.MCP_MEMORY_CONTROL_COLLECTION}"
        f"/{mcp_api_key_db.MCP_APP_KEY_MEMORY_GRANTS_DOC_ID}"
    )


class _Redis:
    def __init__(self):
        self.auth_context = None
        self.cached = []

    def read_cached_mcp_api_key_auth_context(self, _hashed_key):
        if self.auth_context is None:
            return ApiKeyCacheReadResult(mode=ApiKeyCacheReadMode.MISS)
        return ApiKeyCacheReadResult(mode=ApiKeyCacheReadMode.HIT, data=self.auth_context)

    def cache_mcp_api_key_auth_context(
        self,
        hashed_key,
        user_id,
        scopes,
        key_id=None,
        app_id=None,
        memory_grant_seeded=True,
        auth_context_version=mcp_api_key_db.MCP_API_KEY_AUTH_CONTEXT_VERSION,
    ):
        self.auth_context = {
            "user_id": user_id,
            "scopes": scopes,
            "key_id": key_id,
            "app_id": app_id,
            "memory_grant_seeded": memory_grant_seeded,
            "auth_context_version": auth_context_version,
        }
        self.cached.append({"hashed_key": hashed_key, **self.auth_context})
        return True

    def delete_cached_mcp_api_key_strict(self, _hashed_key):
        self.auth_context = None
        return True


def _grant_for(store, uid, key_id, app_id=mcp_api_key_db.MCP_DEFAULT_APP_ID):
    doc = store.get(_grant_path(uid)).to_dict()
    return doc["grants"]["mcp"]["apps"][app_id]["keys"][key_id]


def test_create_mcp_key_persists_full_access_identity_and_memory_grant(monkeypatch):
    store = FakeDocumentStore()
    monkeypatch.setattr(mcp_api_key_db, "_store", lambda: store)
    monkeypatch.setattr(mcp_api_key_db, "generate_api_key", lambda: ("omi_mcp_secret", "hashed", "omi_mcp"))
    monkeypatch.setattr(mcp_api_key_db.uuid, "uuid4", lambda: "key-1")

    with pytest.raises(ApiKeyValidationError, match="Invalid MCP API key app_id"):
        mcp_api_key_db.create_mcp_key("user-1", "Agent", app_id="../invalid app")
    assert store.query("mcp_api_keys") == []

    raw_key, key = mcp_api_key_db.create_mcp_key("user-1", "Agent")

    key_doc = store.get("mcp_api_keys/key-1").to_dict()
    assert raw_key == "omi_mcp_secret"
    assert key.app_id == mcp_api_key_db.MCP_DEFAULT_APP_ID
    assert "memories.write" in key.scopes
    assert key_doc["app_id"] == mcp_api_key_db.MCP_DEFAULT_APP_ID
    assert "memories.write" in key_doc["scopes"]

    grant = _grant_for(store, "user-1", "key-1")
    assert grant == {
        "enabled": True,
        "scopes": ["memories.read", "memories.write"],
        "default_read": True,
        "archive_read": False,
        "write": True,
    }


def test_legacy_mcp_key_auth_repairs_identity_scopes_and_memory_grant(monkeypatch):
    store = FakeDocumentStore()
    store.set(
        "mcp_api_keys/legacy-key",
        {
            "id": "legacy-key",
            "user_id": "user-1",
            "name": "Legacy",
            "hashed_key": "hashed",
            "key_prefix": "omi_mcp",
            "created_at": datetime.utcnow(),
            "last_used_at": None,
            "scopes": ["memories.read"],
        },
    )
    redis = _Redis()
    monkeypatch.setattr(mcp_api_key_db, "_store", lambda: store)
    monkeypatch.setattr(mcp_api_key_db, "redis_db", redis)
    monkeypatch.setattr(mcp_api_key_db, "hash_api_key", lambda _secret: "hashed")

    auth = mcp_api_key_db.get_user_and_scopes_by_api_key("omi_mcp_secret")

    assert auth["user_id"] == "user-1"
    assert auth["key_id"] == "legacy-key"
    assert auth["app_id"] == mcp_api_key_db.MCP_DEFAULT_APP_ID
    assert "memories.write" in auth["scopes"]

    repaired = store.get("mcp_api_keys/legacy-key").to_dict()
    assert repaired["app_id"] == mcp_api_key_db.MCP_DEFAULT_APP_ID
    assert "memories.write" in repaired["scopes"]
    assert repaired["last_used_at"] is not None

    grant = _grant_for(store, "user-1", "legacy-key")
    assert grant["default_read"] is True
    assert grant["write"] is True
    assert "memories.write" in grant["scopes"]
    assert redis.cached[0]["app_id"] == mcp_api_key_db.MCP_DEFAULT_APP_ID


def test_stale_cached_mcp_key_auth_repairs_once_and_rewrites_cache(monkeypatch):
    store = FakeDocumentStore()
    store.set(
        "mcp_api_keys/cached-key",
        {
            "id": "cached-key",
            "user_id": "user-1",
            "hashed_key": "hashed",
            "scopes": ["memories.read"],
        },
    )
    redis = _Redis()
    redis.auth_context = {
        "user_id": "user-1",
        "scopes": ["memories.read"],
        "key_id": "cached-key",
        "app_id": None,
    }
    monkeypatch.setattr(mcp_api_key_db, "_store", lambda: store)
    monkeypatch.setattr(mcp_api_key_db, "redis_db", redis)
    monkeypatch.setattr(mcp_api_key_db, "hash_api_key", lambda _secret: "hashed")

    auth = mcp_api_key_db.get_user_and_scopes_by_api_key("omi_mcp_secret")

    assert auth["app_id"] == mcp_api_key_db.MCP_DEFAULT_APP_ID
    assert "memories.write" in auth["scopes"]
    grant = _grant_for(store, "user-1", "cached-key")
    assert grant["write"] is True
    assert redis.cached[0]["scopes"] == auth["scopes"]
    assert redis.cached[0]["auth_context_version"] == mcp_api_key_db.MCP_API_KEY_AUTH_CONTEXT_VERSION


def test_fresh_cached_mcp_key_auth_does_not_write_firestore(monkeypatch):
    store = FakeDocumentStore()
    redis = _Redis()
    redis.auth_context = {
        "user_id": "user-1",
        "scopes": mcp_api_key_db.MCP_FULL_ACCESS_SCOPES,
        "key_id": "cached-key",
        "app_id": mcp_api_key_db.MCP_DEFAULT_APP_ID,
        "memory_grant_seeded": True,
        "auth_context_version": mcp_api_key_db.MCP_API_KEY_AUTH_CONTEXT_VERSION,
    }
    monkeypatch.setattr(mcp_api_key_db, "_store", lambda: store)
    monkeypatch.setattr(mcp_api_key_db, "redis_db", redis)
    monkeypatch.setattr(mcp_api_key_db, "hash_api_key", lambda _secret: "hashed")

    auth = mcp_api_key_db.get_user_and_scopes_by_api_key("omi_mcp_secret")

    assert auth["user_id"] == "user-1"
    # A fresh cache hit must short-circuit before any store read/write.
    assert store.query("mcp_api_keys") == []
    assert store.exists(_grant_path("user-1")) is False


def test_delete_mcp_key_removes_memory_grant(monkeypatch):
    store = FakeDocumentStore()
    monkeypatch.setattr(mcp_api_key_db, "_store", lambda: store)
    store.set(
        "mcp_api_keys/key-1",
        {
            "id": "key-1",
            "user_id": "user-1",
            "hashed_key": "a" * 64,
            "app_id": mcp_api_key_db.MCP_DEFAULT_APP_ID,
        },
    )
    mcp_api_key_db._seed_mcp_memory_grant("user-1", "key-1")
    redis = _Redis()
    monkeypatch.setattr(mcp_api_key_db, "redis_db", redis)

    mcp_api_key_db.delete_mcp_key("user-1", "key-1")

    assert store.exists("mcp_api_keys/key-1") is False
    grants_doc = store.get(_grant_path("user-1")).to_dict()
    keys = grants_doc["grants"]["mcp"]["apps"][mcp_api_key_db.MCP_DEFAULT_APP_ID]["keys"]
    assert "key-1" not in keys


def test_backfill_normalized_scopes_treats_invalid_scope_shape_as_empty():
    scopes = backfill_mcp_keys._normalized_scopes("memories.read")

    assert "m" not in scopes
    assert set(mcp_api_key_db.MCP_FULL_ACCESS_SCOPES).issubset(set(scopes))


def test_backfill_grant_check_requires_all_memory_grant_scopes():
    assert (
        backfill_mcp_keys._grant_ok(
            {
                "enabled": True,
                "write": True,
                "default_read": True,
                "scopes": ["memories.write"],
            }
        )
        is False
    )
    assert (
        backfill_mcp_keys._grant_ok(
            {
                "enabled": True,
                "write": True,
                "default_read": True,
                "scopes": mcp_api_key_db.MCP_MEMORY_GRANT_SCOPES,
            }
        )
        is True
    )
