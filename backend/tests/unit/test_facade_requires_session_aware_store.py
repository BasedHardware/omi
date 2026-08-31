"""The facade states what it needs from a store, and refuses one that cannot provide it (L31).

``NeutralFirestoreClient`` needs more than the domain-facing ``DocumentStore``: upstream's
``@transactional`` bodies interleave reads and writes on one handle, so every op has to run inside a
specific session. That requirement was an unwritten convention — the facade reached for
``store._get(..., session=...)`` and friends, which only ``MongoDocumentStore`` and the in-memory fake
implement — and ``_begin`` inferred "session-less" from a missing ``_mongo_client``.

The dangerous half was the inference, not the missing method. An adapter implementing the documented
port in full got a loud ``AttributeError`` from the first transactional read, which invites a fix;
behind it, ``_begin`` would have quietly handed out ``session=None``, so every transaction in the
product ran **without atomicity and without an error**. Fixing the loud half while shipping the silent
half is the failure this suite exists to prevent.
"""

from __future__ import annotations

from typing import Any, Dict

import pytest

from database.store.firestore_facade import NeutralFirestoreClient
from database.store.ports import (
    FACADE_SESSION_OPS,
    STORE_SESSION_OPS,
    missing_facade_session_ops,
    missing_store_session_ops,
)
from database.store.records import StoredDocument
from tests.store_fakes import FakeDocumentStore


class _DocumentedPortOnly:
    """A store that implements the neutral DocumentStore and nothing more.

    This is the shape of an adapter written from ``ports.py`` alone — e.g. the ArcadeDB adapter
    ADR-0012 accepts — and of the existing ``FirestoreDocumentStore``.
    """

    def get(self, path: str, *, fields: Any = None, timeout: Any = None) -> StoredDocument:
        return StoredDocument.missing(path)

    def set(self, path: str, data: Dict[str, Any], *, merge: bool = False) -> None: ...
    def update(self, path: str, data: Dict[str, Any], *, if_updated_at: Any = None) -> None: ...
    def create(self, path: str, data: Dict[str, Any]) -> None: ...
    def delete(self, path: str, *, if_updated_at: Any = None) -> None: ...
    def run_transaction(self, fn: Any, *, attempts: int = 3) -> Any:
        raise NotImplementedError

    def batch(self) -> Any:
        raise NotImplementedError


def test_a_store_with_only_the_documented_port_is_refused_at_construction():
    with pytest.raises(TypeError) as excinfo:
        NeutralFirestoreClient(_DocumentedPortOnly())
    message = str(excinfo.value)
    assert "_DocumentedPortOnly" in message
    # Every missing op is named — the whole point is not to surface whichever attribute a transaction
    # three layers down happened to touch first.
    for op in FACADE_SESSION_OPS:
        assert op in message, f"{op} missing from the error message"
    assert "FacadeSessionStore" in message
    assert "without atomicity" in message


def test_the_real_firestore_adapter_is_refused_too():
    """Concrete instance of the same gap: this is the wiring the contract suites used to use."""
    from database.store.adapters.firestore import FirestoreDocumentStore

    assert missing_facade_session_ops(FirestoreDocumentStore(client=object())) == FACADE_SESSION_OPS
    with pytest.raises(TypeError, match="FirestoreDocumentStore cannot back NeutralFirestoreClient"):
        NeutralFirestoreClient(FirestoreDocumentStore(client=object()))


def test_forgetting_only_the_session_opener_is_still_refused():
    """The silent half at the store level: everything a store can do, and no way to open a session.

    Before this gate that store would have been accepted and run every transaction session-less.
    ``begin_session`` is now the ONLY thing the store owes the facade, so a store missing it is a
    store that never declared whether its transactions are atomic.
    """

    store = _DocumentedPortOnly()  # the documented port in full, no opener
    assert missing_facade_session_ops(store) == ("begin_session",)
    with pytest.raises(TypeError, match="begin_session"):
        NeutralFirestoreClient(store)


def test_a_session_that_cannot_be_used_is_refused_loudly():
    """The silent half at the SESSION level — the one moving the ops onto the handle created.

    A store can now satisfy ``FacadeSessionStore`` (it has ``begin_session``) and still hand back a
    handle that cannot read or write. Left unchecked that is an ``AttributeError`` from whichever op
    the transactional body reached first, three frames from the reason — the same shape as the
    original L31 defect. It is refused at ``_begin``, naming every missing op.
    """

    class _HalfBuiltSession:
        """Can read, cannot write: exactly the shape that would survive a partial implementation."""

        def get(self, path: str, *, fields: Any = None) -> StoredDocument:
            return StoredDocument.missing(path)

        def query(self, collection: str, **kw: Any) -> list:
            return []

    class _OpensAnUnusableSession(FakeDocumentStore):
        def begin_session(self) -> Any:
            return _HalfBuiltSession()

    store = _OpensAnUnusableSession()
    assert missing_store_session_ops(_HalfBuiltSession()) == ("set", "update", "create", "delete")
    # The store itself passes: the gap is one level down, which is why it needs its own check.
    assert missing_facade_session_ops(store) == ()

    transaction = NeutralFirestoreClient(store).transaction()
    with pytest.raises(TypeError) as excinfo:
        transaction._begin()
    message = str(excinfo.value)
    assert "_HalfBuiltSession" in message
    for op in ("set", "update", "create", "delete"):
        assert op in message, f"{op} missing from the error message"
    assert "StoreSession" in message


def test_a_usable_session_names_every_op_the_facade_runs():
    """``STORE_SESSION_OPS`` is the list the error message is built from; keep it honest."""
    assert missing_store_session_ops(FakeDocumentStore()) == ()
    assert set(STORE_SESSION_OPS) == {"get", "set", "update", "create", "delete", "query"}


# --- the legacy principals: everything already behind the facade must keep working ---------------


def test_the_in_memory_fake_still_satisfies_the_requirement():
    """It declares session-less on purpose, which is a legitimate answer — not an omission."""
    store = FakeDocumentStore()
    assert missing_facade_session_ops(store) == ()
    client = NeutralFirestoreClient(store)
    transaction = client.transaction()
    transaction._begin()
    assert transaction._session is None, "the fake declares session-less: writes apply directly"


def test_the_mongo_adapter_still_satisfies_the_requirement():
    """Structural check, so it runs without a live replica set (the contract lane covers behavior)."""
    from database.store.adapters.mongo import MongoDocumentStore

    assert missing_facade_session_ops(MongoDocumentStore) == ()


def test_begin_takes_the_session_from_the_store_not_from_a_sniffed_attribute():
    """The regression guard: a sniffed ``_mongo_client`` must no longer decide anything.

    A store that carries a ``_mongo_client`` AND declares its own opener must get the declared
    session. Under the old inference the sniffed client won and started its own transaction.
    """

    class _Sentinel(FakeDocumentStore):
        """A usable session (the fake's own six ops) whose IDENTITY is what the test follows."""

    sentinel = _Sentinel()

    class _DeclaresItsOwnSession(FakeDocumentStore):
        def __init__(self) -> None:
            super().__init__()
            self.opened = 0
            # A decoy: the attribute the old code inferred from. Touching it would blow up.
            self._mongo_client = _ExplodingClient()

        def begin_session(self) -> Any:
            self.opened += 1
            return sentinel

    class _ExplodingClient:
        def start_session(self) -> Any:  # pragma: no cover - reaching this IS the failure
            raise AssertionError("_begin must ask the store, not sniff _mongo_client")

    store = _DeclaresItsOwnSession()
    transaction = NeutralFirestoreClient(store).transaction()
    transaction._begin()
    assert transaction._session is sentinel
    assert store.opened == 1


def test_a_fake_backed_transaction_still_reads_and_writes_through_the_facade():
    """End-to-end sanity on the session-less path every hermetic unit suite depends on."""
    store = FakeDocumentStore()
    store.set("users/u1", {"name": "before"})
    client = NeutralFirestoreClient(store)
    transaction = client.transaction()
    transaction._begin()
    reference = client.document("users/u1")
    assert transaction.get(reference).to_dict() == {"name": "before"}
    transaction.update(reference, {"name": "after"})
    transaction._commit()
    assert store.get("users/u1").data["name"] == "after"
