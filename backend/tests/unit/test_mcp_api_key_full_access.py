from datetime import datetime

from google.cloud import firestore

import database.mcp_api_key as mcp_api_key_db
import scripts.backfill_mcp_key_full_access as backfill_mcp_keys


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

    def get(self):
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

    def stream(self):
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
    def __init__(self):
        self._collections = {}

    def collection(self, name):
        self._collections.setdefault(name, _Collection(self, name))
        return self._collections[name]


class _Redis:
    def __init__(self):
        self.auth_context = None
        self.cached = []

    def get_cached_mcp_api_key_auth_context(self, _hashed_key):
        return self.auth_context

    def cache_mcp_api_key_auth_context(self, hashed_key, user_id, scopes, key_id=None, app_id=None):
        self.auth_context = {
            "user_id": user_id,
            "scopes": scopes,
            "key_id": key_id,
            "app_id": app_id,
            "memory_grant_seeded": True,
            "auth_context_version": mcp_api_key_db.MCP_API_KEY_AUTH_CONTEXT_VERSION,
        }
        self.cached.append({"hashed_key": hashed_key, **self.auth_context})

    def delete_cached_mcp_api_key(self, _hashed_key):
        self.auth_context = None


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
    monkeypatch.setattr(mcp_api_key_db, "generate_api_key", lambda: ("omi_mcp_secret", "hashed", "omi_mcp"))
    monkeypatch.setattr(mcp_api_key_db.uuid, "uuid4", lambda: "key-1")

    raw_key, key = mcp_api_key_db.create_mcp_key("user-1", "Agent")

    key_doc = db.collection("mcp_api_keys").document("key-1").get().to_dict()
    assert raw_key == "omi_mcp_secret"
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

    auth = mcp_api_key_db.get_user_and_scopes_by_api_key("omi_mcp_secret")

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

    auth = mcp_api_key_db.get_user_and_scopes_by_api_key("omi_mcp_secret")

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

    auth = mcp_api_key_db.get_user_and_scopes_by_api_key("omi_mcp_secret")

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
            "hashed_key": "hashed",
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
