"""The Mongo adapter must turn a neutral ``get(timeout=)`` into a real server-side ``maxTimeMS``
deadline, so a slow read aborts at the deadline instead of holding a request worker until the
(much larger) socket timeout. Regression for cubic review 4909186286 #2: default-read rollout's
2s deadline was disabled on the Mongo backend because the facade dropped the timeout and the
adapter had no way to receive one. A deterministic spy client records the ``find_one`` kwargs.
"""

from database.store.adapters.mongo import MongoDocumentStore


class _SpyCollection:
    def __init__(self) -> None:
        self.calls = []

    def find_one(self, query, projection=None, *, session=None, **kw):
        self.calls.append(kw)
        return None  # a missing doc is fine; we only assert the read-deadline kwargs


class _SpyDb:
    def __init__(self, coll: _SpyCollection) -> None:
        self._coll = coll

    def __getitem__(self, _name: str) -> _SpyCollection:
        return self._coll


class _SpyClient:
    def __init__(self, db: _SpyDb) -> None:
        self._db = db

    def __getitem__(self, _name: str) -> _SpyDb:
        return self._db

    def close(self) -> None:  # pragma: no cover - parity with MongoClient
        pass


def _store_with_spy():
    coll = _SpyCollection()
    store = MongoDocumentStore(client=_SpyClient(_SpyDb(coll)), db_name="t")
    return store, coll


def test_get_timeout_maps_to_max_time_ms():
    store, coll = _store_with_spy()
    store.get("users/u1", timeout=2)
    assert coll.calls == [{"max_time_ms": 2000}]


def test_get_without_timeout_passes_no_deadline():
    store, coll = _store_with_spy()
    store.get("users/u1")
    assert coll.calls == [{}]


def test_mongo_client_bounds_server_selection_and_connect(monkeypatch):
    # The MongoClient had no timeouts, so an unreachable/degraded server hung request workers on
    # PyMongo's 30s default server-selection (root cause behind "slow Mongo reads"). Bound server
    # selection + connect so it fails fast; socketTimeoutMS stays unset (per-read maxTimeMS bounds reads).
    import database.store.adapters.mongo as mongo_mod

    captured = {}

    class _SpyMongoClient:
        def __init__(self, uri, **kw):
            captured["uri"] = uri
            captured.update(kw)

        def __getitem__(self, _name):
            return object()

    monkeypatch.setattr(mongo_mod, "MongoClient", _SpyMongoClient)
    mongo_mod.MongoDocumentStore(uri="mongodb://mongo:27017/?replicaSet=rs0", db_name="t")

    assert captured["tz_aware"] is True
    assert captured["serverSelectionTimeoutMS"] == 5000
    assert captured["connectTimeoutMS"] == 5000
    assert "socketTimeoutMS" not in captured  # long ops must not be killed mid-flight
