"""Regression: publishing a private app must not orphan its keyed data.

`update_app_visibility_in_db` used to delete the app document and recreate it
under a new ULID when a '-private' id went public. Firestore has no cascades, so
`apps/{id}/reviews`, `apps/{id}/api_keys`, usage history, per-user installed
entries, and the Redis reviews mirror stayed keyed to the dead id — every
integration 401'd and ratings reset.

The fix updates `private` in place: the document id never changes, so every
subcollection and mirror keeps resolving.
"""

import types
from unittest.mock import MagicMock

import database.apps as apps_db


class _Doc:
    def __init__(self, store, doc_id):
        self._store = store
        self.id = doc_id
        self.calls = []

    def get(self, *a, **k):
        snap = MagicMock()
        payload = self._store.get(self.id)
        snap.exists = payload is not None
        snap.to_dict = lambda: dict(payload or {})
        return snap

    def update(self, fields):
        self.calls.append(("update", fields))
        self._store.setdefault(self.id, {}).update(fields)

    def set(self, payload):
        self.calls.append(("set", payload))
        self._store[self.id] = dict(payload)

    def delete(self):
        self.calls.append(("delete",))
        self._store.pop(self.id, None)


class _Collection:
    def __init__(self, store):
        self._store = store
        self.requested = []

    def document(self, doc_id):
        self.requested.append(doc_id)
        return _Doc(self._store, doc_id)


def _install(monkeypatch):
    store = {"myapp-private-01K": {"id": "myapp-private-01K", "private": True, "uid": "dev-1"}}
    coll = _Collection(store)
    monkeypatch.setattr(apps_db, "db", types.SimpleNamespace(collection=lambda _name: coll))
    return store, coll


def test_private_to_public_updates_in_place(monkeypatch):
    store, coll = _install(monkeypatch)
    apps_db.update_app_visibility_in_db("myapp-private-01K", private=False)

    # Same document id — nothing was deleted or re-created under a new id
    assert coll.requested == ["myapp-private-01K"]
    assert store["myapp-private-01K"]["private"] is False
    doc_ops = store["myapp-private-01K"]  # data preserved, id intact
    assert doc_ops["uid"] == "dev-1"


def test_private_to_public_never_deletes_or_sets(monkeypatch):
    _store, coll = _install(monkeypatch)
    # reach inside via a second call to inspect call log
    doc = coll.document("myapp-private-01K")
    apps_db.update_app_visibility_in_db("myapp-private-01K", private=False)
    assert all(op == ("update", {"private": False}) for op in doc.calls)


def test_public_to_private_updates_in_place(monkeypatch):
    store, coll = _install(monkeypatch)
    store["pub-01K"] = {"id": "pub-01K", "private": False, "uid": "dev-1"}
    apps_db.update_app_visibility_in_db("pub-01K", private=True)
    assert coll.requested == ["pub-01K"]
    assert store["pub-01K"]["private"] is True
