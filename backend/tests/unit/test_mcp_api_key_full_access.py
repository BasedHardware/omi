from datetime import datetime

from google.cloud import firestore
import pytest

import database.mcp_api_key as mcp_api_key_db
import database.api_key_cache as api_key_cache
from database.api_key_metadata import ApiKeyCacheReadMode, ApiKeyCacheReadResult, ApiKeyValidationError
from tests.unit.fixtures.api_key_revocation_fakes import AtomicKeyBatch, RedisStore
import scripts.backfill_mcp_key_full_access as backfill_mcp_keys


@pytest.fixture(autouse=True)
def _local_revocation_store(monkeypatch):
    store = RedisStore()
    monkeypatch.setattr(api_key_cache, "_redis", lambda: store)
    return store


class _DocSnapshot:
    def __init__(self, reference, data=None):
        self.reference = reference
        self.id = reference.id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data or {})


def _deep_merge(target, patch):
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = value


class _DocReference:
    def __init__(self, collection, doc_id):
        self._collection = collection
        self.id = doc_id

    def collection(self, name):
        return self._collection._db.collection(f"{self._collection.name}/{self.id}/{name}")

    # ``**_read_options`` mirrors the real Firestore signature: reads on the MCP
    # auth path pass retry/timeout to bound their deadline (database/mcp_auth_read.py).
    def get(self, **_read_options):
        return _DocSnapshot(self, self._collection._docs.get(self.id))

    def set(self, data, merge=False):
        self._collection.set_count += 1
        if merge:
            existing = self._collection._docs.setdefault(self.id, {})
            _deep_merge(existing, dict(data))
            return
        self._collection._docs[self.id] = dict(data)

    def update(self, data):
        self._collection.update_count += 1
        doc = self._collection._docs.setdefault(self.id, {})
        for key, value in data.items():
            if "." in key:
                parts = key.split(".")
                target = doc
                for part in parts[:-1]:
                    target = target.setdefault(part, {})
                if value is firestore.DELETE_FIELD:
                    target.pop(parts[-1], None)
                else:
                    target[parts[-1]] = value
            elif value is firestore.DELETE_FIELD:
                doc.pop(key, None)
            else:
                doc[key] = value

    def delete(self):
        self._collection._docs.pop(self.id, None)


class _Query:
    def __init__(self, collection, field, expected):
        self._collection = collection
        self._field = field
        self._expected = expected
        self._limit = None

    def limit(self, limit):
        self._limit = limit
        return self

    def stream(self, **_read_options):
        matches = [
            _DocSnapshot(_DocReference(self._collection, doc_id), data)
            for doc_id, data in self._collection._docs.items()
            if data.get(self._field) == self._expected
        ]
        return matches[: self._limit] if self._limit is not None else matches


class _Collection:
    def __init__(self, db, name):
        self._db = db
        self.name = name
        self._docs = {}
        self.set_count = 0
        self.update_count = 0

    def document(self, doc_id):
        return _DocReference(self, doc_id)

    def where(self, field, op, expected):
        assert op == "=="
        return _Query(self, field, expected)


class _DB:
    def batch(self):
        return AtomicKeyBatch()

    def __init__(self):
        self._collections = {}

    def collection(self, name):
        self._collections.setdefault(name, _Collection(self, name))
        return self._collections[name]


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


def _grant_for(db, uid, key_id, app_id=mcp_api_key_db.MCP_DEFAULT_APP_ID):
    doc = (
        db.collection("users")
        .document(uid)
        .collection(mcp_api_key_db.MCP_MEMORY_CONTROL_COLLECTION)
        .document(mcp_api_key_db.MCP_APP_KEY_MEMORY_GRANTS_DOC_ID)
        .get()
        .to_dict()
    )
    return doc["grants"]["mcp"]["apps"][app_id]["keys"][key_id]


def test_create_mcp_key_persists_full_access_identity_and_memory_grant(monkeypatch):
    db = _DB()
    monkeypatch.setattr(mcp_api_key_db, "get_firestore_client", lambda: db)
    monkeypatch.setattr(
        mcp_api_key_db, "generate_api_key", lambda: ("omi_mcp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "hashed", "omi_mcp")
    )
    monkeypatch.setattr(mcp_api_key_db.uuid, "uuid4", lambda: "key-1")

    with pytest.raises(ApiKeyValidationError, match="Invalid MCP API key app_id"):
        mcp_api_key_db.create_mcp_key("user-1", "Agent", app_id="../invalid app")
    assert db.collection("mcp_api_keys")._docs == {}

    raw_key, key = mcp_api_key_db.create_mcp_key("user-1", "Agent")

    key_doc = db.collection("mcp_api_keys").document("key-1").get().to_dict()
    assert raw_key == "omi_mcp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert key.app_id == mcp_api_key_db.MCP_DEFAULT_APP_ID
    assert "memories.write" in key.scopes
    assert key_doc["app_id"] == mcp_api_key_db.MCP_DEFAULT_APP_ID
    assert "memories.write" in key_doc["scopes"]

    grant = _grant_for(db, "user-1", "key-1")
    assert grant == {
        "enabled": True,
        "scopes": ["memories.read", "memories.write"],
        "default_read": True,
        "archive_read": False,
        "write": True,
    }


def test_legacy_mcp_key_auth_repairs_identity_scopes_and_memory_grant(monkeypatch):
    db = _DB()
    db.collection("mcp_api_keys").document("legacy-key").set(
        {
            "id": "legacy-key",
            "user_id": "user-1",
            "name": "Legacy",
            "hashed_key": "hashed",
            "key_prefix": "omi_mcp",
            "created_at": datetime.utcnow(),
            "last_used_at": None,
            "scopes": ["memories.read"],
        }
    )
    redis = _Redis()
    monkeypatch.setattr(mcp_api_key_db, "get_firestore_client", lambda: db)
    monkeypatch.setattr(mcp_api_key_db, "redis_db", redis)
    monkeypatch.setattr(mcp_api_key_db, "hash_api_key", lambda _secret: "hashed")

    auth = mcp_api_key_db.get_user_and_scopes_by_api_key("omi_mcp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")

    assert auth["user_id"] == "user-1"
    assert auth["key_id"] == "legacy-key"
    assert auth["app_id"] == mcp_api_key_db.MCP_DEFAULT_APP_ID
    assert "memories.write" in auth["scopes"]

    repaired = db.collection("mcp_api_keys").document("legacy-key").get().to_dict()
    assert repaired["app_id"] == mcp_api_key_db.MCP_DEFAULT_APP_ID
    assert "memories.write" in repaired["scopes"]
    assert repaired["last_used_at"] is not None

    grant = _grant_for(db, "user-1", "legacy-key")
    assert grant["default_read"] is True
    assert grant["write"] is True
    assert "memories.write" in grant["scopes"]
    assert redis.cached[0]["app_id"] == mcp_api_key_db.MCP_DEFAULT_APP_ID


def test_stale_cached_mcp_key_auth_repairs_once_and_rewrites_cache(monkeypatch):
    db = _DB()
    db.collection("mcp_api_keys").document("cached-key").set(
        {
            "id": "cached-key",
            "user_id": "user-1",
            "hashed_key": "hashed",
            "scopes": ["memories.read"],
        }
    )
    redis = _Redis()
    redis.auth_context = {
        "user_id": "user-1",
        "scopes": ["memories.read"],
        "key_id": "cached-key",
        "app_id": None,
    }
    monkeypatch.setattr(mcp_api_key_db, "get_firestore_client", lambda: db)
    monkeypatch.setattr(mcp_api_key_db, "redis_db", redis)
    monkeypatch.setattr(mcp_api_key_db, "hash_api_key", lambda _secret: "hashed")

    auth = mcp_api_key_db.get_user_and_scopes_by_api_key("omi_mcp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")

    assert auth["app_id"] == mcp_api_key_db.MCP_DEFAULT_APP_ID
    assert "memories.write" in auth["scopes"]
    grant = _grant_for(db, "user-1", "cached-key")
    assert grant["write"] is True
    assert redis.cached[0]["scopes"] == auth["scopes"]
    assert redis.cached[0]["auth_context_version"] == mcp_api_key_db.MCP_API_KEY_AUTH_CONTEXT_VERSION


def test_fresh_cached_mcp_key_auth_does_not_write_firestore(monkeypatch):
    db = _DB()
    redis = _Redis()
    redis.auth_context = {
        "user_id": "user-1",
        "scopes": mcp_api_key_db.MCP_FULL_ACCESS_SCOPES,
        "key_id": "cached-key",
        "app_id": mcp_api_key_db.MCP_DEFAULT_APP_ID,
        "memory_grant_seeded": True,
        "auth_context_version": mcp_api_key_db.MCP_API_KEY_AUTH_CONTEXT_VERSION,
    }
    monkeypatch.setattr(mcp_api_key_db, "get_firestore_client", lambda: db)
    monkeypatch.setattr(mcp_api_key_db, "redis_db", redis)
    monkeypatch.setattr(mcp_api_key_db, "hash_api_key", lambda _secret: "hashed")

    auth = mcp_api_key_db.get_user_and_scopes_by_api_key("omi_mcp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")

    assert auth["user_id"] == "user-1"
    assert db.collection("mcp_api_keys").update_count == 0
    grant_collection = db.collection(f"users/user-1/{mcp_api_key_db.MCP_MEMORY_CONTROL_COLLECTION}")
    assert grant_collection.set_count == 0


def test_delete_mcp_key_removes_memory_grant(monkeypatch):
    db = _DB()
    db.collection("mcp_api_keys").document("key-1").set(
        {
            "id": "key-1",
            "user_id": "user-1",
            "hashed_key": "a" * 64,
            "app_id": mcp_api_key_db.MCP_DEFAULT_APP_ID,
        }
    )
    mcp_api_key_db._seed_mcp_memory_grant("user-1", "key-1", firestore_client=db)
    redis = _Redis()
    monkeypatch.setattr(mcp_api_key_db, "get_firestore_client", lambda: db)
    monkeypatch.setattr(mcp_api_key_db, "redis_db", redis)

    mcp_api_key_db.delete_mcp_key("user-1", "key-1")

    assert db.collection("mcp_api_keys").document("key-1").get().exists is False
    grants_doc = (
        db.collection("users")
        .document("user-1")
        .collection(mcp_api_key_db.MCP_MEMORY_CONTROL_COLLECTION)
        .document(mcp_api_key_db.MCP_APP_KEY_MEMORY_GRANTS_DOC_ID)
        .get()
        .to_dict()
    )
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


def test_create_mcp_key_with_explicit_readonly_scopes_stays_narrowed_through_create_and_auth(monkeypatch):
    db = _DB()
    redis = _Redis()
    monkeypatch.setattr(mcp_api_key_db, "get_firestore_client", lambda: db)
    monkeypatch.setattr(mcp_api_key_db, "redis_db", redis)
    monkeypatch.setattr(
        mcp_api_key_db, "generate_api_key", lambda: ("omi_mcp_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "hashed-ro", "omi_mcp")
    )
    monkeypatch.setattr(mcp_api_key_db, "hash_api_key", lambda _secret: "hashed-ro")
    monkeypatch.setattr(mcp_api_key_db.uuid, "uuid4", lambda: "readonly-key")

    requested = ["memories.read", "conversations.read", "action_items.read", "goals.read"]
    raw_key, key = mcp_api_key_db.create_mcp_key("user-1", "Muse (Omi app)", scopes=requested)

    expected_scopes = ["action_items.read", "conversations.read", "goals.read", "memories.read"]
    assert raw_key == "omi_mcp_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    assert key.scopes == expected_scopes
    for forbidden in ("memories.write", "action_items.write", "screen_activity.read", "people.read", "people.rename"):
        assert forbidden not in key.scopes

    key_doc = db.collection("mcp_api_keys").document("readonly-key").get().to_dict()
    assert key_doc["scopes"] == expected_scopes
    assert key_doc.get("explicit_scopes") is True

    grant = _grant_for(db, "user-1", "readonly-key")
    assert grant == {
        "enabled": True,
        "scopes": ["memories.read"],
        "default_read": True,
        "archive_read": False,
        "write": False,
    }

    # First auth (cache miss -> Firestore lookup + repair check) must keep narrowed scopes and read-only grant.
    auth_miss = mcp_api_key_db.get_user_and_scopes_by_api_key(raw_key)
    assert auth_miss is not None
    assert auth_miss["scopes"] == expected_scopes
    assert db.collection("mcp_api_keys").document("readonly-key").get().to_dict()["scopes"] == expected_scopes
    assert _grant_for(db, "user-1", "readonly-key")["write"] is False
    assert _grant_for(db, "user-1", "readonly-key")["scopes"] == ["memories.read"]

    # Second auth (Redis cache hit) must also keep narrowed scopes without widening or falling back.
    updates_before_cache_hit = db.collection("mcp_api_keys").update_count
    auth_hit = mcp_api_key_db.get_user_and_scopes_by_api_key(raw_key)
    assert auth_hit is not None
    assert auth_hit["scopes"] == expected_scopes
    assert db.collection("mcp_api_keys").update_count == updates_before_cache_hit

    # Listing keys for user must also project the narrowed scope set without reporting a repair.
    listed, repairs = mcp_api_key_db.get_mcp_keys_for_user_with_repair_info("user-1")
    assert len(listed) == 1
    assert listed[0].scopes == expected_scopes
    assert mcp_api_key_db.ApiKeyMetadataRepair.SCOPES not in repairs


def test_create_mcp_key_rejects_empty_or_unknown_explicit_scopes(monkeypatch):
    db = _DB()
    monkeypatch.setattr(mcp_api_key_db, "get_firestore_client", lambda: db)
    for invalid_scopes in ([], ["unknown.scope"], ["memories.read", "people.delete"]):
        with pytest.raises(ApiKeyValidationError, match="Invalid MCP API key scopes"):
            mcp_api_key_db.create_mcp_key("user-1", "Agent", scopes=invalid_scopes)
    assert db.collection("mcp_api_keys")._docs == {}


def test_explicit_narrowed_key_repairs_memory_grant_without_widening_to_write(monkeypatch):
    db = _DB()
    redis = _Redis()
    monkeypatch.setattr(mcp_api_key_db, "get_firestore_client", lambda: db)
    monkeypatch.setattr(mcp_api_key_db, "redis_db", redis)
    monkeypatch.setattr(mcp_api_key_db, "hash_api_key", lambda _secret: "hashed-narrow")

    db.collection("mcp_api_keys").document("narrow-key").set(
        {
            "id": "narrow-key",
            "user_id": "user-1",
            "name": "Narrow",
            "hashed_key": "hashed-narrow",
            "key_prefix": "omi_mcp_1234...5678",
            "created_at": datetime.utcnow(),
            "last_used_at": None,
            "app_id": mcp_api_key_db.MCP_DEFAULT_APP_ID,
            "scopes": ["memories.read", "conversations.read"],
            "explicit_scopes": True,
        }
    )

    auth_result = mcp_api_key_db.get_api_key_auth_result("omi_mcp_cccccccccccccccccccccccccccccccc")
    assert auth_result.context is not None
    assert auth_result.context["scopes"] == ["conversations.read", "memories.read"]
    assert mcp_api_key_db.ApiKeyAuthRepair.SCOPES not in auth_result.repairs
    assert mcp_api_key_db.ApiKeyAuthRepair.MEMORY_GRANT in auth_result.repairs

    grant = _grant_for(db, "user-1", "narrow-key")
    assert grant == {
        "enabled": True,
        "scopes": ["memories.read"],
        "default_read": True,
        "archive_read": False,
        "write": False,
    }


def test_explicit_key_without_memory_scopes_does_not_seed_memory_grant(monkeypatch):
    db = _DB()
    redis = _Redis()
    monkeypatch.setattr(mcp_api_key_db, "get_firestore_client", lambda: db)
    monkeypatch.setattr(mcp_api_key_db, "redis_db", redis)
    monkeypatch.setattr(
        mcp_api_key_db,
        "generate_api_key",
        lambda: ("omi_mcp_dddddddddddddddddddddddddddddddd", "hashed-conv", "omi_mcp"),
    )
    monkeypatch.setattr(mcp_api_key_db, "hash_api_key", lambda _secret: "hashed-conv")
    monkeypatch.setattr(mcp_api_key_db.uuid, "uuid4", lambda: "conv-only-key")

    raw_key, key = mcp_api_key_db.create_mcp_key("user-1", "Conv only", scopes=["conversations.read"])
    assert key.scopes == ["conversations.read"]
    grant_collection = db.collection(f"users/user-1/{mcp_api_key_db.MCP_MEMORY_CONTROL_COLLECTION}")
    assert grant_collection.set_count == 0

    auth_result = mcp_api_key_db.get_api_key_auth_result(raw_key)
    assert auth_result.context is not None
    assert auth_result.context["scopes"] == ["conversations.read"]
    assert grant_collection.set_count == 0
