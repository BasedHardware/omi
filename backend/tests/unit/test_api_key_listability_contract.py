import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from unittest.mock import MagicMock

from google.cloud import firestore
import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import database.dev_api_key as dev_api_key_db
import database.mcp_api_key as mcp_api_key_db
import database.redis_db as redis_db
from database.api_key_metadata import (
    ApiKeyAuthRepair,
    ApiKeyCacheReadMode,
    ApiKeyCacheReadResult,
    ApiKeyMetadataRepair,
    ApiKeyRevocationUnavailableError,
    ApiKeyValidationError,
)


def _deep_merge(target: dict[str, Any], patch: dict[str, Any]) -> None:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = value


class _DocumentSnapshot:
    def __init__(self, reference: "_DocumentReference", data: Optional[dict[str, Any]], create_time: object = None):
        self.reference = reference
        self.id = reference.id
        self._data = data
        self.exists = data is not None
        self.create_time = create_time

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data or {})


class _DocumentReference:
    def __init__(self, collection: "_Collection", doc_id: str):
        self._collection = collection
        self.id = doc_id

    def collection(self, name: str) -> "_Collection":
        return self._collection._db.collection(f"{self._collection.name}/{self.id}/{name}")

    def get(self) -> _DocumentSnapshot:
        record = self._collection._records.get(self.id)
        return _DocumentSnapshot(
            self,
            dict(record["data"]) if record else None,
            record.get("create_time") if record else None,
        )

    def set(self, data: dict[str, Any], merge: bool = False) -> None:
        record = self._collection._records.get(self.id)
        if merge and record:
            _deep_merge(record["data"], dict(data))
            return
        self._collection._records[self.id] = {"data": dict(data), "create_time": None}

    def update(self, data: dict[str, Any]) -> None:
        record = self._collection._records.setdefault(self.id, {"data": {}, "create_time": None})
        target = record["data"]
        for path, value in data.items():
            parts = path.split(".")
            parent = target
            for part in parts[:-1]:
                parent = parent.setdefault(part, {})
            if value is firestore.DELETE_FIELD:
                parent.pop(parts[-1], None)
            else:
                parent[parts[-1]] = value

    def delete(self) -> None:
        self._collection._records.pop(self.id, None)


class _Query:
    def __init__(self, collection: "_Collection", conditions: tuple[tuple[str, object], ...] = (), limit: int = 0):
        self._collection = collection
        self._conditions = conditions
        self._limit = limit

    def where(self, field: str, operator: str, expected: object) -> "_Query":
        assert operator == "=="
        return _Query(self._collection, (*self._conditions, (field, expected)), self._limit)

    def limit(self, limit: int) -> "_Query":
        return _Query(self._collection, self._conditions, limit)

    def stream(self) -> list[_DocumentSnapshot]:
        docs = []
        for doc_id, record in self._collection._records.items():
            data = record["data"]
            if all(data.get(field) == expected for field, expected in self._conditions):
                reference = _DocumentReference(self._collection, doc_id)
                docs.append(_DocumentSnapshot(reference, dict(data), record.get("create_time")))
        return docs[: self._limit] if self._limit else docs


class _Collection:
    def __init__(self, db: "_Firestore", name: str):
        self._db = db
        self.name = name
        self._records: dict[str, dict[str, Any]] = {}

    def document(self, doc_id: str) -> _DocumentReference:
        return _DocumentReference(self, doc_id)

    def where(self, field: str, operator: str, expected: object) -> _Query:
        return _Query(self).where(field, operator, expected)


class _Firestore:
    def __init__(self):
        self._collections: dict[str, _Collection] = {}

    def collection(self, name: str) -> _Collection:
        self._collections.setdefault(name, _Collection(self, name))
        return self._collections[name]

    def seed(
        self,
        collection: str,
        doc_id: str,
        data: dict[str, Any],
        *,
        create_time: object = None,
    ) -> None:
        self.collection(collection)._records[doc_id] = {
            "data": dict(data),
            "create_time": create_time,
        }


class _Redis:
    def __init__(self):
        self.mcp_context: Optional[dict[str, Any]] = None
        self.dev_context: Optional[dict[str, Any]] = None

    def read_cached_mcp_api_key_auth_context(self, _hashed_key: str) -> ApiKeyCacheReadResult:
        if self.mcp_context is None:
            return ApiKeyCacheReadResult(mode=ApiKeyCacheReadMode.MISS)
        return ApiKeyCacheReadResult(mode=ApiKeyCacheReadMode.HIT, data=dict(self.mcp_context))

    def cache_mcp_api_key_auth_context(
        self,
        _hashed_key: str,
        user_id: str,
        scopes: Optional[list[str]] = None,
        key_id: Optional[str] = None,
        app_id: Optional[str] = None,
        memory_grant_seeded: bool = True,
        auth_context_version: int = mcp_api_key_db.MCP_API_KEY_AUTH_CONTEXT_VERSION,
    ) -> bool:
        self.mcp_context = {
            "user_id": user_id,
            "scopes": scopes,
            "key_id": key_id,
            "app_id": app_id,
            "memory_grant_seeded": memory_grant_seeded,
            "auth_context_version": auth_context_version,
        }
        return True

    def delete_cached_mcp_api_key_strict(self, _hashed_key: str) -> bool:
        self.mcp_context = None
        return True

    def read_cached_dev_api_key_data(self, _hashed_key: str) -> ApiKeyCacheReadResult:
        if self.dev_context is None:
            return ApiKeyCacheReadResult(mode=ApiKeyCacheReadMode.MISS)
        return ApiKeyCacheReadResult(mode=ApiKeyCacheReadMode.HIT, data=dict(self.dev_context))

    def cache_dev_api_key(
        self,
        _hashed_key: str,
        user_id: str,
        scopes: Optional[list[str]] = None,
        ttl: int = 3600,
        key_id: Optional[str] = None,
        app_id: Optional[str] = None,
        auth_context_version: int = dev_api_key_db.DEV_API_KEY_AUTH_CONTEXT_VERSION,
    ) -> bool:
        del ttl
        self.dev_context = {
            "user_id": user_id,
            "scopes": scopes,
            "key_id": key_id,
            "app_id": app_id,
            "auth_context_version": auth_context_version,
        }
        return True

    def delete_cached_dev_api_key_strict(self, _hashed_key: str) -> bool:
        self.dev_context = None
        return True


class _RedisKeyValueStore:
    def __init__(self):
        self.values: dict[str, object] = {}

    def set(self, key: str, value: object, ex: Optional[int] = None) -> None:
        del ex
        self.values[key] = value

    def get(self, key: str) -> object:
        value = self.values.get(key)
        return value.encode() if isinstance(value, str) else value

    def delete(self, *keys: str) -> None:
        for key in keys:
            self.values.pop(key, None)


class _FailingRedisKeyValueStore(_RedisKeyValueStore):
    def set(self, key: str, value: object, ex: Optional[int] = None) -> None:
        del key, value, ex
        raise RuntimeError("redis unavailable")


class _ReadFailingRedisKeyValueStore(_RedisKeyValueStore):
    def get(self, key: str) -> object:
        del key
        raise RuntimeError("redis read unavailable")


class _DeleteFailingRedisKeyValueStore(_RedisKeyValueStore):
    def __init__(self):
        super().__init__()
        self.delete_calls: list[tuple[str, ...]] = []

    def delete(self, *keys: str) -> None:
        self.delete_calls.append(keys)
        raise RuntimeError("redis delete unavailable")


def _mcp_grant_keys(db: _Firestore, user_id: str) -> dict[str, Any]:
    grant = (
        db.collection("users")
        .document(user_id)
        .collection(mcp_api_key_db.MCP_MEMORY_CONTROL_COLLECTION)
        .document(mcp_api_key_db.MCP_APP_KEY_MEMORY_GRANTS_DOC_ID)
        .get()
        .to_dict()
    )
    return grant["grants"]["mcp"]["apps"][mcp_api_key_db.MCP_DEFAULT_APP_ID]["keys"]


def test_mcp_key_authentication_metadata_projection_and_revocation_share_document_identity(monkeypatch):
    raw_token = "omi_mcp_0123456789abcdef0123456789abcdef"
    db = _Firestore()
    db.seed(
        "mcp_api_keys",
        "canonical-mcp-id",
        {
            "id": "embedded-wrong-id",
            "user_id": "user-1",
            "hashed_key": mcp_api_key_db.hash_api_key(raw_token.removeprefix("omi_mcp_")),
            "name": raw_token,
            "key_prefix": raw_token,
            "created_at": "not-a-time",
            "last_used_at": "not-a-time",
            "scopes": "memories.read",
        },
        create_time=datetime(2024, 1, 2),
    )
    redis = _Redis()
    redis.mcp_context = {
        "user_id": "user-1",
        "key_id": "embedded-wrong-id",
        "app_id": mcp_api_key_db.MCP_DEFAULT_APP_ID,
        "scopes": mcp_api_key_db.MCP_FULL_ACCESS_SCOPES,
    }
    monkeypatch.setattr(mcp_api_key_db, "get_firestore_client", lambda: db)
    monkeypatch.setattr(mcp_api_key_db, "redis_db", redis)

    auth_result = mcp_api_key_db.get_api_key_auth_result(raw_token)
    auth = auth_result.context

    assert auth == {
        "user_id": "user-1",
        "scopes": sorted(mcp_api_key_db.MCP_FULL_ACCESS_SCOPES),
        "key_id": "canonical-mcp-id",
        "app_id": mcp_api_key_db.MCP_DEFAULT_APP_ID,
    }
    assert auth_result.repairs == {
        ApiKeyAuthRepair.DOCUMENT_ID,
        ApiKeyAuthRepair.APP_ID,
        ApiKeyAuthRepair.SCOPES,
        ApiKeyAuthRepair.MEMORY_GRANT,
    }
    assert redis.mcp_context["auth_context_version"] == mcp_api_key_db.MCP_API_KEY_AUTH_CONTEXT_VERSION
    assert redis.mcp_context["key_id"] == "canonical-mcp-id"
    assert set(_mcp_grant_keys(db, "user-1")) == {"canonical-mcp-id"}

    listed, repairs = mcp_api_key_db.get_mcp_keys_for_user_with_repair_info("user-1")

    assert [key.id for key in listed] == ["canonical-mcp-id"]
    assert listed[0].name == "Legacy MCP API key"
    assert listed[0].key_prefix == "omi_mcp_legacy"
    assert listed[0].created_at == datetime(2024, 1, 2, tzinfo=timezone.utc)
    assert raw_token not in json.dumps([key.model_dump(mode="json") for key in listed])
    assert repairs == {
        ApiKeyMetadataRepair.NAME,
        ApiKeyMetadataRepair.KEY_PREFIX,
        ApiKeyMetadataRepair.CREATED_AT,
    }

    mcp_api_key_db.delete_mcp_key("user-1", listed[0].id)

    assert _mcp_grant_keys(db, "user-1") == {}
    assert mcp_api_key_db.get_user_and_scopes_by_api_key(raw_token) is None


def test_developer_key_authentication_metadata_projection_and_revocation_share_document_identity(monkeypatch):
    raw_token = "omi_dev_0123456789abcdef0123456789abcdef"
    db = _Firestore()
    db.seed(
        "dev_api_keys",
        "canonical-dev-id",
        {
            "id": "embedded-wrong-id",
            "user_id": "user-1",
            "hashed_key": dev_api_key_db.hash_dev_api_key(raw_token.removeprefix("omi_dev_")),
            "name": raw_token,
            "key_prefix": raw_token,
            "created_at": None,
            "last_used_at": {"invalid": True},
            "app_id": raw_token,
            "scopes": ["memories:read", "unknown", 7],
        },
        create_time=datetime(2024, 2, 3, tzinfo=timezone.utc),
    )
    redis = _Redis()
    redis.dev_context = {
        "user_id": "user-1",
        "key_id": "embedded-wrong-id",
        "app_id": "developer_api",
        "scopes": ["memories:write"],
    }
    removed_grants: list[tuple[str, str]] = []
    monkeypatch.setattr(dev_api_key_db, "get_firestore_client", lambda: db)
    monkeypatch.setattr(dev_api_key_db, "redis_db", redis)
    monkeypatch.setattr(
        dev_api_key_db,
        "remove_developer_api_key_memory_grant",
        lambda user_id, key_id, **_kwargs: removed_grants.append((user_id, key_id)),
    )

    initial_list, initial_repairs = dev_api_key_db.get_dev_keys_for_user_with_repair_info("user-1")

    assert initial_repairs == set(ApiKeyMetadataRepair)
    assert raw_token not in json.dumps([key.model_dump(mode="json") for key in initial_list])

    auth_result = dev_api_key_db.get_api_key_auth_result(raw_token)
    auth = auth_result.context

    assert auth == {
        "user_id": "user-1",
        "scopes": ["memories:read"],
        "key_id": "canonical-dev-id",
        "app_id": "developer_api",
    }
    assert auth_result.repairs == {
        ApiKeyAuthRepair.DOCUMENT_ID,
        ApiKeyAuthRepair.APP_ID,
        ApiKeyAuthRepair.SCOPES,
    }
    assert redis.dev_context["auth_context_version"] == dev_api_key_db.DEV_API_KEY_AUTH_CONTEXT_VERSION
    assert redis.dev_context["key_id"] == "canonical-dev-id"

    listed = dev_api_key_db.get_dev_keys_for_user("user-1")

    assert [key.id for key in listed] == ["canonical-dev-id"]
    assert listed[0].name == "Legacy Developer API key"
    assert listed[0].key_prefix == "omi_dev_legacy"
    assert listed[0].created_at == datetime(2024, 2, 3, tzinfo=timezone.utc)
    assert listed[0].scopes == ["memories:read"]
    assert raw_token not in json.dumps([key.model_dump(mode="json") for key in listed])

    dev_api_key_db.delete_dev_key("user-1", listed[0].id)

    assert removed_grants == [("user-1", "canonical-dev-id")]
    assert dev_api_key_db.get_user_and_scopes_by_api_key(raw_token) is None


def test_mcp_present_poisoned_app_identity_fails_auth_but_remains_safely_listable(monkeypatch):
    raw_token = "omi_mcp_fedcba9876543210fedcba9876543210"
    overflowing_datetime = datetime.max.replace(tzinfo=timezone(-timedelta(hours=23)))
    db = _Firestore()
    db.seed(
        "mcp_api_keys",
        "poisoned-mcp-id",
        {
            "user_id": "user-1",
            "hashed_key": mcp_api_key_db.hash_api_key(raw_token.removeprefix("omi_mcp_")),
            "name": f"Unsafe {raw_token}",
            "key_prefix": raw_token,
            "created_at": overflowing_datetime,
            "last_used_at": raw_token,
            "app_id": raw_token,
            "scopes": [raw_token],
        },
    )
    redis = _Redis()
    monkeypatch.setattr(mcp_api_key_db, "get_firestore_client", lambda: db)
    monkeypatch.setattr(mcp_api_key_db, "redis_db", redis)

    listed, repairs = mcp_api_key_db.get_mcp_keys_for_user_with_repair_info("user-1")

    assert repairs == set(ApiKeyMetadataRepair)
    assert listed[0].name == "Legacy MCP API key"
    assert listed[0].key_prefix == "omi_mcp_legacy"
    assert listed[0].app_id == mcp_api_key_db.MCP_DEFAULT_APP_ID
    assert listed[0].created_at == datetime(1970, 1, 1, tzinfo=timezone.utc)
    assert raw_token not in json.dumps([key.model_dump(mode="json") for key in listed])
    assert mcp_api_key_db.get_user_and_scopes_by_api_key(raw_token) is None


def test_missing_created_at_uses_snapshot_time_then_epoch_with_deterministic_ties(monkeypatch):
    db = _Firestore()
    for collection, prefix in (("mcp_api_keys", "mcp"), ("dev_api_keys", "dev")):
        for doc_id, create_time in (
            (f"{prefix}-b-epoch", None),
            (f"{prefix}-newer", datetime(2025, 1, 1, tzinfo=timezone.utc)),
            (f"{prefix}-a-epoch", None),
        ):
            db.seed(
                collection,
                doc_id,
                {"user_id": "user-1", "created_at": "invalid", "key_prefix": f"omi_{prefix}_raw-secret"},
                create_time=create_time,
            )
    monkeypatch.setattr(mcp_api_key_db, "get_firestore_client", lambda: db)
    monkeypatch.setattr(dev_api_key_db, "get_firestore_client", lambda: db)

    mcp_keys = mcp_api_key_db.get_mcp_keys_for_user("user-1")
    dev_keys = dev_api_key_db.get_dev_keys_for_user("user-1")

    assert [key.id for key in mcp_keys] == ["mcp-newer", "mcp-a-epoch", "mcp-b-epoch"]
    assert [key.id for key in dev_keys] == ["dev-newer", "dev-a-epoch", "dev-b-epoch"]
    assert all(key.created_at.tzinfo == timezone.utc for key in [*mcp_keys, *dev_keys])
    assert {key.key_prefix for key in mcp_keys} == {"omi_mcp_legacy"}
    assert {key.key_prefix for key in dev_keys} == {"omi_dev_legacy"}


def test_equivalent_reordered_scope_lists_keep_canonical_order_without_repairs(monkeypatch):
    db = _Firestore()
    mcp_token = "omi_mcp_11111111111111111111111111111111"
    dev_token = "omi_dev_22222222222222222222222222222222"
    mcp_scopes = sorted(mcp_api_key_db.MCP_FULL_ACCESS_SCOPES)
    dev_scopes = ["conversations:read", "memories:read"]
    db.seed(
        "mcp_api_keys",
        "mcp-key",
        {
            "id": "mcp-key",
            "user_id": "user-1",
            "hashed_key": mcp_api_key_db.hash_api_key(mcp_token.removeprefix("omi_mcp_")),
            "name": "MCP key",
            "key_prefix": "omi_mcp_abcd...1234",
            "created_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
            "app_id": mcp_api_key_db.MCP_DEFAULT_APP_ID,
            "scopes": list(reversed(mcp_scopes)),
        },
    )
    db.seed(
        "dev_api_keys",
        "dev-key",
        {
            "id": "dev-key",
            "user_id": "user-1",
            "hashed_key": dev_api_key_db.hash_dev_api_key(dev_token.removeprefix("omi_dev_")),
            "name": "Developer key",
            "key_prefix": "omi_dev_abcd...1234",
            "created_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
            "app_id": dev_api_key_db.DEV_API_KEY_APP_ID,
            "scopes": list(reversed(dev_scopes)),
        },
    )
    monkeypatch.setattr(mcp_api_key_db, "get_firestore_client", lambda: db)
    monkeypatch.setattr(dev_api_key_db, "get_firestore_client", lambda: db)
    redis = _Redis()
    monkeypatch.setattr(mcp_api_key_db, "redis_db", redis)
    monkeypatch.setattr(dev_api_key_db, "redis_db", redis)

    mcp_keys, mcp_repairs = mcp_api_key_db.get_mcp_keys_for_user_with_repair_info("user-1")
    dev_keys, dev_repairs = dev_api_key_db.get_dev_keys_for_user_with_repair_info("user-1")

    assert mcp_repairs == frozenset()
    assert dev_repairs == frozenset()
    assert mcp_keys[0].scopes == mcp_scopes
    assert dev_keys[0].scopes == dev_scopes

    mcp_auth = mcp_api_key_db.get_api_key_auth_result(mcp_token)
    dev_auth = dev_api_key_db.get_api_key_auth_result(dev_token)

    assert ApiKeyAuthRepair.SCOPES not in mcp_auth.repairs
    assert ApiKeyAuthRepair.SCOPES not in dev_auth.repairs


def test_authentication_fails_when_auth_critical_user_identity_is_whitespace(monkeypatch):
    mcp_token = "omi_mcp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    dev_token = "omi_dev_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    db = _Firestore()
    db.seed(
        "mcp_api_keys",
        "mcp-whitespace-user",
        {
            "hashed_key": mcp_api_key_db.hash_api_key(mcp_token.removeprefix("omi_mcp_")),
            "user_id": "   ",
        },
    )
    db.seed(
        "dev_api_keys",
        "dev-whitespace-user",
        {
            "hashed_key": dev_api_key_db.hash_dev_api_key(dev_token.removeprefix("omi_dev_")),
            "user_id": "\t",
        },
    )
    redis = _Redis()
    monkeypatch.setattr(mcp_api_key_db, "get_firestore_client", lambda: db)
    monkeypatch.setattr(dev_api_key_db, "get_firestore_client", lambda: db)
    monkeypatch.setattr(mcp_api_key_db, "redis_db", redis)
    monkeypatch.setattr(dev_api_key_db, "redis_db", redis)

    assert mcp_api_key_db.get_user_and_scopes_by_api_key(mcp_token) is None
    assert dev_api_key_db.get_user_and_scopes_by_api_key(dev_token) is None


def test_developer_auth_survives_redis_cache_write_failure(monkeypatch):
    raw_token = "omi_dev_cccccccccccccccccccccccccccccccc"
    db = _Firestore()
    db.seed(
        "dev_api_keys",
        "dev-cache-failure",
        {
            "hashed_key": dev_api_key_db.hash_dev_api_key(raw_token.removeprefix("omi_dev_")),
            "user_id": "user-1",
            "scopes": ["memories:read"],
        },
    )
    monkeypatch.setattr(dev_api_key_db, "get_firestore_client", lambda: db)
    monkeypatch.setattr(redis_db, "r", _FailingRedisKeyValueStore())

    auth_result = dev_api_key_db.get_api_key_auth_result(raw_token)
    auth = auth_result.context

    assert auth == {
        "user_id": "user-1",
        "scopes": ["memories:read"],
        "key_id": "dev-cache-failure",
        "app_id": "developer_api",
    }
    assert auth_result.repairs == {
        ApiKeyAuthRepair.DOCUMENT_ID,
        ApiKeyAuthRepair.APP_ID,
        ApiKeyAuthRepair.CACHE_WRITE,
    }
    repaired = db.collection("dev_api_keys").document("dev-cache-failure").get().to_dict()
    assert repaired["last_used_at"] is not None


def test_mcp_auth_reports_redis_cache_write_failure_after_full_recovery(monkeypatch):
    raw_token = "omi_mcp_33333333333333333333333333333333"
    hashed_key = mcp_api_key_db.hash_api_key(raw_token.removeprefix("omi_mcp_"))
    db = _Firestore()
    db.seed(
        "mcp_api_keys",
        "mcp-cache-failure",
        {
            "id": "mcp-cache-failure",
            "user_id": "user-1",
            "hashed_key": hashed_key,
            "app_id": mcp_api_key_db.MCP_DEFAULT_APP_ID,
            "scopes": sorted(mcp_api_key_db.MCP_FULL_ACCESS_SCOPES),
        },
    )
    mcp_api_key_db._seed_mcp_memory_grant("user-1", "mcp-cache-failure", firestore_client=db)
    monkeypatch.setattr(mcp_api_key_db, "get_firestore_client", lambda: db)
    monkeypatch.setattr(redis_db, "r", _FailingRedisKeyValueStore())

    auth_result = mcp_api_key_db.get_api_key_auth_result(raw_token)

    assert auth_result.context is not None
    assert auth_result.context["key_id"] == "mcp-cache-failure"
    assert auth_result.repairs == {ApiKeyAuthRepair.CACHE_WRITE}


def test_mcp_auth_reports_cache_read_error_after_firestore_recovery(monkeypatch):
    raw_token = "omi_mcp_44444444444444444444444444444444"
    hashed_key = mcp_api_key_db.hash_api_key(raw_token.removeprefix("omi_mcp_"))
    db = _Firestore()
    db.seed(
        "mcp_api_keys",
        "mcp-cache-read-failure",
        {
            "id": "mcp-cache-read-failure",
            "user_id": "user-1",
            "hashed_key": hashed_key,
            "app_id": mcp_api_key_db.MCP_DEFAULT_APP_ID,
            "scopes": sorted(mcp_api_key_db.MCP_FULL_ACCESS_SCOPES),
        },
    )
    mcp_api_key_db._seed_mcp_memory_grant("user-1", "mcp-cache-read-failure", firestore_client=db)
    monkeypatch.setattr(mcp_api_key_db, "get_firestore_client", lambda: db)
    monkeypatch.setattr(redis_db, "r", _ReadFailingRedisKeyValueStore())

    auth_result = mcp_api_key_db.get_api_key_auth_result(raw_token)

    assert auth_result.context is not None
    assert auth_result.context["key_id"] == "mcp-cache-read-failure"
    assert auth_result.repairs == {ApiKeyAuthRepair.CACHE_READ}


def test_developer_auth_reports_cache_read_error_after_firestore_recovery(monkeypatch):
    raw_token = "omi_dev_55555555555555555555555555555555"
    hashed_key = dev_api_key_db.hash_dev_api_key(raw_token.removeprefix("omi_dev_"))
    db = _Firestore()
    db.seed(
        "dev_api_keys",
        "dev-cache-read-failure",
        {
            "id": "dev-cache-read-failure",
            "user_id": "user-1",
            "hashed_key": hashed_key,
            "app_id": dev_api_key_db.DEV_API_KEY_APP_ID,
            "scopes": ["memories:read"],
        },
    )
    monkeypatch.setattr(dev_api_key_db, "get_firestore_client", lambda: db)
    monkeypatch.setattr(redis_db, "r", _ReadFailingRedisKeyValueStore())

    auth_result = dev_api_key_db.get_api_key_auth_result(raw_token)

    assert auth_result.context is not None
    assert auth_result.context["key_id"] == "dev-cache-read-failure"
    assert auth_result.repairs == {ApiKeyAuthRepair.CACHE_READ}


def test_cache_delete_failure_preserves_mcp_document_grant_and_current_auth(monkeypatch):
    raw_token = "omi_mcp_dddddddddddddddddddddddddddddddd"
    hashed_key = mcp_api_key_db.hash_api_key(raw_token.removeprefix("omi_mcp_"))
    db = _Firestore()
    db.seed(
        "mcp_api_keys",
        "mcp-revoke-failure",
        {
            "id": "mcp-revoke-failure",
            "user_id": "user-1",
            "hashed_key": hashed_key,
            "app_id": mcp_api_key_db.MCP_DEFAULT_APP_ID,
            "scopes": sorted(mcp_api_key_db.MCP_FULL_ACCESS_SCOPES),
        },
    )
    mcp_api_key_db._seed_mcp_memory_grant(
        "user-1",
        "mcp-revoke-failure",
        firestore_client=db,
    )
    store = _DeleteFailingRedisKeyValueStore()
    monkeypatch.setattr(redis_db, "r", store)
    monkeypatch.setattr(mcp_api_key_db, "get_firestore_client", lambda: db)
    assert redis_db.cache_mcp_api_key_auth_context(
        hashed_key,
        "user-1",
        sorted(mcp_api_key_db.MCP_FULL_ACCESS_SCOPES),
        key_id="mcp-revoke-failure",
        app_id=mcp_api_key_db.MCP_DEFAULT_APP_ID,
    )

    with pytest.raises(ApiKeyRevocationUnavailableError):
        mcp_api_key_db.delete_mcp_key("user-1", "mcp-revoke-failure")

    assert store.delete_calls == [
        (f"mcp_api_key:{hashed_key}", f"mcp_api_key_auth:{hashed_key}"),
    ]
    assert db.collection("mcp_api_keys").document("mcp-revoke-failure").get().exists is True
    assert set(_mcp_grant_keys(db, "user-1")) == {"mcp-revoke-failure"}
    assert mcp_api_key_db.get_user_and_scopes_by_api_key(raw_token)["key_id"] == "mcp-revoke-failure"


def test_cache_delete_failure_preserves_developer_document_and_current_auth(monkeypatch):
    raw_token = "omi_dev_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
    hashed_key = dev_api_key_db.hash_dev_api_key(raw_token.removeprefix("omi_dev_"))
    db = _Firestore()
    db.seed(
        "dev_api_keys",
        "dev-revoke-failure",
        {
            "id": "dev-revoke-failure",
            "user_id": "user-1",
            "hashed_key": hashed_key,
            "app_id": dev_api_key_db.DEV_API_KEY_APP_ID,
            "scopes": ["memories:read"],
        },
    )
    store = _DeleteFailingRedisKeyValueStore()
    remove_grant = MagicMock()
    monkeypatch.setattr(redis_db, "r", store)
    monkeypatch.setattr(dev_api_key_db, "get_firestore_client", lambda: db)
    monkeypatch.setattr(dev_api_key_db, "remove_developer_api_key_memory_grant", remove_grant)
    assert redis_db.cache_dev_api_key(
        hashed_key,
        "user-1",
        ["memories:read"],
        key_id="dev-revoke-failure",
        app_id=dev_api_key_db.DEV_API_KEY_APP_ID,
    )

    with pytest.raises(ApiKeyRevocationUnavailableError):
        dev_api_key_db.delete_dev_key("user-1", "dev-revoke-failure")

    assert store.delete_calls == [(f"dev_api_key:{hashed_key}",)]
    assert db.collection("dev_api_keys").document("dev-revoke-failure").get().exists is True
    remove_grant.assert_not_called()
    assert dev_api_key_db.get_user_and_scopes_by_api_key(raw_token)["key_id"] == "dev-revoke-failure"


@pytest.mark.parametrize("corrupt_hash", [None, "", " ", 7, "not-a-hash"])
def test_corrupt_hash_blocks_mcp_revocation_before_document_grant_or_current_cache_mutation(monkeypatch, corrupt_hash):
    raw_token = "omi_mcp_66666666666666666666666666666666"
    hashed_key = mcp_api_key_db.hash_api_key(raw_token.removeprefix("omi_mcp_"))
    db = _Firestore()
    db.seed(
        "mcp_api_keys",
        "mcp-corrupt-hash",
        {
            "id": "mcp-corrupt-hash",
            "user_id": "user-1",
            "hashed_key": corrupt_hash,
            "app_id": mcp_api_key_db.MCP_DEFAULT_APP_ID,
            "scopes": sorted(mcp_api_key_db.MCP_FULL_ACCESS_SCOPES),
        },
    )
    mcp_api_key_db._seed_mcp_memory_grant("user-1", "mcp-corrupt-hash", firestore_client=db)
    store = _RedisKeyValueStore()
    monkeypatch.setattr(redis_db, "r", store)
    monkeypatch.setattr(mcp_api_key_db, "get_firestore_client", lambda: db)
    assert redis_db.cache_mcp_api_key_auth_context(
        hashed_key,
        "user-1",
        sorted(mcp_api_key_db.MCP_FULL_ACCESS_SCOPES),
        key_id="mcp-corrupt-hash",
        app_id=mcp_api_key_db.MCP_DEFAULT_APP_ID,
    )
    cached_before = dict(store.values)

    with pytest.raises(ApiKeyRevocationUnavailableError):
        mcp_api_key_db.delete_mcp_key("user-1", "mcp-corrupt-hash")

    assert store.values == cached_before
    assert db.collection("mcp_api_keys").document("mcp-corrupt-hash").get().exists is True
    assert set(_mcp_grant_keys(db, "user-1")) == {"mcp-corrupt-hash"}
    assert mcp_api_key_db.get_user_and_scopes_by_api_key(raw_token)["key_id"] == "mcp-corrupt-hash"


@pytest.mark.parametrize("corrupt_hash", [None, "", " ", 7, "not-a-hash"])
def test_corrupt_hash_blocks_developer_revocation_before_document_grant_or_current_cache_mutation(
    monkeypatch, corrupt_hash
):
    raw_token = "omi_dev_77777777777777777777777777777777"
    hashed_key = dev_api_key_db.hash_dev_api_key(raw_token.removeprefix("omi_dev_"))
    db = _Firestore()
    db.seed(
        "dev_api_keys",
        "dev-corrupt-hash",
        {
            "id": "dev-corrupt-hash",
            "user_id": "user-1",
            "hashed_key": corrupt_hash,
            "app_id": dev_api_key_db.DEV_API_KEY_APP_ID,
            "scopes": ["memories:read"],
        },
    )
    store = _RedisKeyValueStore()
    remove_grant = MagicMock()
    monkeypatch.setattr(redis_db, "r", store)
    monkeypatch.setattr(dev_api_key_db, "get_firestore_client", lambda: db)
    monkeypatch.setattr(dev_api_key_db, "remove_developer_api_key_memory_grant", remove_grant)
    assert redis_db.cache_dev_api_key(
        hashed_key,
        "user-1",
        ["memories:read"],
        key_id="dev-corrupt-hash",
        app_id=dev_api_key_db.DEV_API_KEY_APP_ID,
    )
    cached_before = dict(store.values)

    with pytest.raises(ApiKeyRevocationUnavailableError):
        dev_api_key_db.delete_dev_key("user-1", "dev-corrupt-hash")

    assert store.values == cached_before
    assert db.collection("dev_api_keys").document("dev-corrupt-hash").get().exists is True
    remove_grant.assert_not_called()
    assert dev_api_key_db.get_user_and_scopes_by_api_key(raw_token)["key_id"] == "dev-corrupt-hash"


def test_raw_token_names_are_rejected_before_generation_or_write(monkeypatch):
    db = _Firestore()
    mcp_generate = MagicMock()
    dev_generate = MagicMock()
    monkeypatch.setattr(mcp_api_key_db, "get_firestore_client", lambda: db)
    monkeypatch.setattr(dev_api_key_db, "get_firestore_client", lambda: db)
    monkeypatch.setattr(mcp_api_key_db, "generate_api_key", mcp_generate)
    monkeypatch.setattr(dev_api_key_db, "generate_dev_api_key", dev_generate)

    with pytest.raises(ApiKeyValidationError, match="must not contain a raw API key"):
        mcp_api_key_db.create_mcp_key("user-1", "omi_mcp_ffffffffffffffffffffffffffffffff")
    with pytest.raises(ApiKeyValidationError, match="must not contain a raw API key"):
        dev_api_key_db.create_dev_key("user-1", "omi_dev_ffffffffffffffffffffffffffffffff")

    mcp_generate.assert_not_called()
    dev_generate.assert_not_called()
    assert db.collection("mcp_api_keys")._records == {}
    assert db.collection("dev_api_keys")._records == {}


def test_redis_auth_context_adapters_persist_current_schema_versions(monkeypatch):
    store = _RedisKeyValueStore()
    monkeypatch.setattr(redis_db, "r", store)

    redis_db.cache_mcp_api_key_auth_context(
        "mcp-hash",
        "user-1",
        ["memories.read"],
        key_id="mcp-key",
        app_id="mcp-api",
    )
    redis_db.cache_dev_api_key(
        "dev-hash",
        "user-1",
        ["memories:read"],
        key_id="dev-key",
        app_id="developer_api",
    )

    mcp_context = redis_db.get_cached_mcp_api_key_auth_context("mcp-hash")
    dev_context = redis_db.get_cached_dev_api_key_data("dev-hash")
    assert mcp_context is not None
    assert dev_context is not None
    assert mcp_context["auth_context_version"] == mcp_api_key_db.MCP_API_KEY_AUTH_CONTEXT_VERSION
    assert dev_context["auth_context_version"] == dev_api_key_db.DEV_API_KEY_AUTH_CONTEXT_VERSION


def test_redis_auth_cache_reads_distinguish_hit_miss_error_and_legacy_uid(monkeypatch):
    store = _RedisKeyValueStore()
    monkeypatch.setattr(redis_db, "r", store)

    assert redis_db.read_cached_mcp_api_key_auth_context("mcp-hash").mode == ApiKeyCacheReadMode.MISS
    assert redis_db.read_cached_dev_api_key_data("dev-hash").mode == ApiKeyCacheReadMode.MISS

    store.values["mcp_api_key_auth:mcp-hash"] = "not-json"
    store.values["dev_api_key:dev-hash"] = "not-json"
    assert redis_db.read_cached_mcp_api_key_auth_context("mcp-hash").mode == ApiKeyCacheReadMode.ERROR
    assert redis_db.read_cached_dev_api_key_data("dev-hash").mode == ApiKeyCacheReadMode.ERROR

    store.values.pop("mcp_api_key_auth:mcp-hash")
    store.values["mcp_api_key:mcp-hash"] = "user-1"
    legacy = redis_db.read_cached_mcp_api_key_auth_context("mcp-hash")
    assert legacy.mode == ApiKeyCacheReadMode.HIT
    assert legacy.data == {"user_id": "user-1", "scopes": None, "key_id": None, "app_id": None}
