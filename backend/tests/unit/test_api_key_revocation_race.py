"""Deterministic revocation interleavings: no sleeps, services, or network."""

from unittest.mock import MagicMock

import pytest
from google.cloud.firestore_v1.batch import WriteBatch

import database.api_key_cache as fences
import database.dev_api_key as dev
import database.mcp_api_key as mcp
import database.redis_db as redis_db
from database.api_key_metadata import ApiKeyAuthRepair, ApiKeyRevocationUnavailableError
from tests.unit.test_api_key_listability_contract import _Firestore, _Query, _mcp_grant_keys
from tests.unit.test_api_key_revocation_race_fakes import AtomicKeyBatch, RedisStore


@pytest.fixture(params=["dev", "mcp"])
def key(request, monkeypatch):
    kind = request.param
    module = dev if kind == "dev" else mcp
    raw = f"omi_{kind}_" + "a" * 32
    hashed = dev.hash_dev_api_key("a" * 32) if kind == "dev" else mcp.hash_api_key("a" * 32)
    db, store = _Firestore(), RedisStore()
    db.seed(
        f"{kind}_api_keys",
        "key-1",
        {
            "id": "key-1",
            "user_id": "user-1",
            "hashed_key": hashed,
            "app_id": "developer_api" if kind == "dev" else mcp.MCP_DEFAULT_APP_ID,
            "scopes": ["conversations:read"] if kind == "dev" else mcp.MCP_FULL_ACCESS_SCOPES,
        },
    )
    monkeypatch.setattr(module, "get_firestore_client", lambda: db)
    monkeypatch.setattr(redis_db, "r", store)
    monkeypatch.setattr(fences, "_redis", lambda: store)
    monkeypatch.setattr(dev, "remove_developer_api_key_memory_grant", MagicMock())
    if kind == "mcp":
        mcp._seed_mcp_memory_grant("user-1", "key-1", firestore_client=db)
    revoke = lambda: getattr(module, f"delete_{kind}_key")("user-1", "key-1")
    return kind, module, raw, hashed, db, store, revoke


def test_revoke_between_firestore_read_and_fill(key, monkeypatch):
    kind, module, raw, hashed, db, store, revoke = key
    original = _Query.stream

    def read_then_revoke(query, **options):
        snapshots = original(query, **options)
        revoke()
        return snapshots

    monkeypatch.setattr(_Query, "stream", read_then_revoke)
    assert module.get_api_key_auth_result(raw).context is None
    assert fences.is_revoked(kind, hashed)
    assert not db.collection(f"{kind}_api_keys").document("key-1").get().exists
    assert not any(name.startswith(("dev_api_key:", "mcp_api_key")) for name in store.values)


def test_fill_from_read_predating_delete_cannot_resurrect_key(key, monkeypatch):
    kind, module, raw, hashed, _db, store, revoke = key
    name = "cache_dev_api_key" if kind == "dev" else "cache_mcp_api_key_auth_context"
    fill = getattr(redis_db, name)
    outcomes = []

    def revoke_then_fill(*args, **kwargs):
        revoke()
        result = fill(*args, **kwargs)
        outcomes.append(result)
        return result

    monkeypatch.setattr(redis_db, name, revoke_then_fill)
    assert module.get_api_key_auth_result(raw).context is None
    assert outcomes == [False]
    assert module.get_user_id_by_api_key(raw) is None
    assert store.values == {f"api_key:revoked:{kind}:{hashed}": "1"}
    if kind == "mcp":
        assert _mcp_grant_keys(_db, "user-1") == {}


def test_revoke_at_atomic_fill_boundary(key, monkeypatch):
    kind, module, raw, _hashed, _db, store, revoke = key
    evaluate = store.eval

    def revoke_then_eval(*args):
        revoke()
        return evaluate(*args)

    monkeypatch.setattr(store, "eval", revoke_then_eval)
    assert module.get_api_key_auth_result(raw).context is None
    assert module.get_user_id_by_api_key(raw) is None


def test_revoke_during_cache_hit_denies_the_inflight_hit(key, monkeypatch):
    kind, module, raw, _hashed, _db, _store, revoke = key
    assert module.get_user_id_by_api_key(raw) == "user-1"
    name = "read_cached_dev_api_key_data" if kind == "dev" else "read_cached_mcp_api_key_auth_context"
    read = getattr(redis_db, name)

    def cached_then_revoke(*args):
        cached = read(*args)
        revoke()
        return cached

    monkeypatch.setattr(redis_db, name, cached_then_revoke)
    assert module.get_api_key_auth_result(raw).context is None


def test_non_memory_and_uid_only_access_denied_even_with_stale_cache(key):
    kind, module, raw, hashed, _db, store, revoke = key
    auth = module.get_api_key_auth_result(raw).context
    assert auth is not None
    assert "conversations:read" in auth["scopes"] if kind == "dev" else "conversations.read" in auth["scopes"]
    cached_before = dict(store.values)
    revoke()
    # Simulate an older writer or legacy worker leaving stale positive entries.
    store.values.update(cached_before)
    assert module.get_api_key_auth_result(raw).context is None
    assert module.get_user_id_by_api_key(raw) is None
    assert fences.is_revoked(kind, hashed)
    assert not getattr(redis_db, "cache_dev_api_key" if kind == "dev" else "cache_mcp_api_key_auth_context")(
        hashed, "user-1", auth["scopes"], key_id="key-1", app_id=auth["app_id"]
    )


def test_cache_purge_failure_keeps_fence_and_retry_completes_revoke(key, monkeypatch):
    kind, module, raw, hashed, db, store, revoke = key
    assert module.get_user_id_by_api_key(raw) == "user-1"
    delete = store.delete
    monkeypatch.setattr(store, "delete", MagicMock(side_effect=RuntimeError("purge unavailable")))
    with pytest.raises(ApiKeyRevocationUnavailableError):
        revoke()
    assert db.collection(f"{kind}_api_keys").document("key-1").get().exists
    if kind == "mcp":
        assert "key-1" in _mcp_grant_keys(db, "user-1")
    assert module.get_user_id_by_api_key(raw) is None
    assert fences.is_revoked(kind, hashed)
    monkeypatch.setattr(store, "delete", delete)
    revoke()
    assert not db.collection(f"{kind}_api_keys").document("key-1").get().exists


@pytest.mark.parametrize("failure", [False, RuntimeError("marker unavailable")])
def test_unconfirmed_marker_never_purges_cache_or_deletes_key(key, monkeypatch, failure):
    kind, module, raw, hashed, db, store, revoke = key
    assert module.get_user_id_by_api_key(raw) == "user-1"
    before = dict(store.values)
    set_value = store.set
    delete = MagicMock(wraps=store.delete)
    monkeypatch.setattr(store, "delete", delete)

    def marker_failure(name, value, ex=None):
        if name.startswith("api_key:revoked:"):
            if isinstance(failure, Exception):
                raise failure
            return failure
        return set_value(name, value, ex)

    monkeypatch.setattr(store, "set", marker_failure)
    with pytest.raises(ApiKeyRevocationUnavailableError):
        revoke()
    delete.assert_not_called()
    assert store.values == before
    assert db.collection(f"{kind}_api_keys").document("key-1").get().exists
    assert not fences.is_revoked(kind, hashed)
    assert module.get_user_id_by_api_key(raw) == "user-1"


@pytest.mark.parametrize("deleted", [False, True])
@pytest.mark.parametrize("failure", [RuntimeError("read unavailable"), False, b""])
def test_marker_read_failure_uses_authoritative_record_without_cache(key, monkeypatch, deleted, failure):
    kind, module, raw, _hashed, db, store, _revoke = key
    assert module.get_user_id_by_api_key(raw) == "user-1"
    if deleted:
        db.collection(f"{kind}_api_keys").document("key-1").delete()
    before = dict(store.values)
    get_value = store.get

    def unavailable_marker(name):
        if name.startswith("api_key:revoked:"):
            if isinstance(failure, Exception):
                raise failure
            return failure
        return get_value(name)

    monkeypatch.setattr(store, "get", unavailable_marker)
    evaluate = MagicMock(wraps=store.eval)
    monkeypatch.setattr(store, "eval", evaluate)
    read_name = "read_cached_dev_api_key_data" if kind == "dev" else "read_cached_mcp_api_key_auth_context"
    read = MagicMock(wraps=getattr(redis_db, read_name))
    monkeypatch.setattr(redis_db, read_name, read)
    result = module.get_api_key_auth_result(raw)
    assert (result.context is None) is deleted
    if not deleted:
        assert result.context["user_id"] == "user-1"
    assert ApiKeyAuthRepair.CACHE_READ in result.repairs
    assert ApiKeyAuthRepair.CACHE_WRITE not in result.repairs
    assert store.values == before
    evaluate.assert_not_called()
    read.assert_not_called()


@pytest.mark.parametrize("deleted", [False, True])
def test_marker_read_failure_after_firestore_read_reloads_without_filling(key, monkeypatch, deleted):
    kind, module, raw, _hashed, db, store, _revoke = key
    original = _Query.stream
    evaluate = MagicMock(wraps=store.eval)
    monkeypatch.setattr(store, "eval", evaluate)

    def read_then_lose_marker(query, **options):
        snapshots = original(query, **options)
        if deleted:
            db.collection(f"{kind}_api_keys").document("key-1").delete()
        monkeypatch.setattr(store, "get", MagicMock(side_effect=RuntimeError("read unavailable")))
        return snapshots

    monkeypatch.setattr(_Query, "stream", read_then_lose_marker)
    result = module.get_api_key_auth_result(raw)
    assert (result.context is None) is deleted
    assert ApiKeyAuthRepair.CACHE_READ in result.repairs
    assert store.values == {}
    evaluate.assert_not_called()


@pytest.mark.parametrize("deleted", [False, True])
def test_marker_read_failure_after_fill_revalidates_without_further_cache_writes(key, monkeypatch, deleted):
    kind, module, raw, _hashed, db, store, _revoke = key
    evaluate = store.eval
    read_marker = fences.is_revoked
    filled = []

    def fill_then_lose_marker(*args):
        result = evaluate(*args)
        filled.append(dict(store.values))
        return result

    def marker_unavailable_after_fill(*args):
        if filled:
            if deleted:
                db.collection(f"{kind}_api_keys").document("key-1").delete()
            return None
        return read_marker(*args)

    evaluate_spy = MagicMock(side_effect=fill_then_lose_marker)
    monkeypatch.setattr(store, "eval", evaluate_spy)
    monkeypatch.setattr(fences, "is_revoked", marker_unavailable_after_fill)
    result = module.get_api_key_auth_result(raw)
    assert (result.context is None) is deleted
    assert ApiKeyAuthRepair.CACHE_READ in result.repairs
    assert evaluate_spy.call_count == 1  # Prior fill only; none on authoritative retry.
    assert store.values == filled[0]


def test_revocation_marker_is_permanent(key):
    kind, _module, _raw, hashed, _db, store, revoke = key
    revoke()
    assert store.set_calls[-1] == (f"api_key:revoked:{kind}:{hashed}", "1", None)


def test_mcp_revoke_after_grant_read_prevents_prepared_batch_commit(key, monkeypatch):
    kind, module, raw, _hashed, db, _store, revoke = key
    if kind != "mcp":
        pytest.skip("MCP-only grant repair")
    mcp._delete_mcp_memory_grant("user-1", "key-1", firestore_client=db)
    monkeypatch.setattr(db, "batch", lambda: AtomicKeyBatch(before_commit=revoke))
    assert module.get_api_key_auth_result(raw).context is None
    assert _mcp_grant_keys(db, "user-1") == {}


def test_mcp_revoke_after_grant_batch_commit_removes_repaired_grant(key, monkeypatch):
    kind, module, raw, _hashed, db, _store, revoke = key
    if kind != "mcp":
        pytest.skip("MCP-only grant repair")
    mcp._delete_mcp_memory_grant("user-1", "key-1", firestore_client=db)
    batch = AtomicKeyBatch()
    commit = batch.commit

    def commit_then_revoke():
        commit()
        assert "key-1" in _mcp_grant_keys(db, "user-1")
        revoke()

    monkeypatch.setattr(batch, "commit", commit_then_revoke)
    monkeypatch.setattr(db, "batch", lambda: batch)
    assert module.get_api_key_auth_result(raw).context is None
    assert _mcp_grant_keys(db, "user-1") == {}


@pytest.mark.parametrize(
    "token",
    [
        None,
        "",
        "omi_mcp_",
        "omi_mcp_secret",
        "omi_mcp_" + "a" * 31,
        "omi_mcp_" + "a" * 33,
        "omi_mcp_" + "A" * 32,
        "omi_mcp_" + "g" * 32,
        "omi_mcp_" + "a" * 32 + "\n",
        " omi_mcp_" + "a" * 32,
        "omi_dev_" + "a" * 32,
    ],
)
def test_mcp_rejects_invalid_format_before_hash_cache_or_database(monkeypatch, token):
    hash_key, fence, db = MagicMock(), MagicMock(), MagicMock()
    monkeypatch.setattr(mcp, "hash_api_key", hash_key)
    monkeypatch.setattr(fences, "is_revoked", fence)
    monkeypatch.setattr(mcp, "_db", db)
    assert mcp.get_api_key_auth_result(token).context is None
    hash_key.assert_not_called()
    fence.assert_not_called()
    db.assert_not_called()


def test_firestore_sdk_batch_update_requires_existing_key():
    """Validate the fake's critical precondition against the installed SDK."""
    key_ref = MagicMock()
    key_ref._document_path = "projects/test/databases/(default)/documents/mcp_api_keys/key-1"
    batch = WriteBatch(MagicMock())
    batch.update(key_ref, {"last_used_at": None})
    assert batch._write_pbs[0].current_document.exists is True
