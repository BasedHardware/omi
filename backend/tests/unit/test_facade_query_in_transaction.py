"""`query.stream(transaction=tx)` must run inside the transaction, not merely be accepted (BACKLOG L24).

Upstream reads COLLECTIONS inside `@firestore.transactional` bodies, not just documents:

  * `database/action_items.py` — the idempotency-key de-dup that decides whether to create a task at all;
  * `database/goals.py` — the relationship detach;
  * `database/conversation_finalization_jobs.py` — the photo-existence probe, whose own docstring says
    "without moving the read outside the authoritative snapshot".

The facade's `_Query.stream(transaction=...)` accepted that argument and dropped it, so on Mongo every one
of those reads ran outside the session — including the last one, whose docstring promised the opposite.

This is the tripwire discipline the project settled on: assert that the SESSION reached the store, not that
"a query happened". A test that only checked the returned rows would pass just as well with the transaction
ignored, which is exactly how the defect survived.

What the fix does NOT give is measured and written down in ADR-0070: Mongo takes no lock on what a
transaction reads, so a concurrent write to a row this query returned still does not stop the commit. The
read now runs in the transaction's own view; read-set conflict detection is a separate problem (L46).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from database.store.firestore_facade import NeutralFirestoreClient
from database.store.records import StoredDocument
from tests.store_fakes import FakeDocumentStore


class _SessionRecordingStore(FakeDocumentStore):
    """The fake, plus a note of which session each read was given."""

    def __init__(self) -> None:
        super().__init__()
        self.query_sessions: List[Any] = []
        self.get_sessions: List[Any] = []

    def _begin_session(self) -> Any:
        # A stand-in handle with the Mongo session lifecycle the facade drives. Returning a real object
        # (instead of the fake's `None`) is what makes "was the session threaded through?" observable.
        return _FakeSession()

    def _query(self, collection: str, *, session: Any = None, **kw: Any) -> List[StoredDocument]:
        self.query_sessions.append(session)
        return self.query(collection, **kw)

    def _get(self, path: str, *, fields: Optional[Sequence[str]] = None, session: Any = None) -> StoredDocument:
        self.get_sessions.append(session)
        return super()._get(path, fields=fields, session=session)


class _FakeSession:
    """Only the lifecycle the facade's `_FacadeTransaction` calls."""

    def __init__(self) -> None:
        self.committed = False

    def commit_transaction(self) -> None:
        self.committed = True

    def abort_transaction(self) -> None:  # pragma: no cover - only on failure paths
        pass

    def end_session(self) -> None:
        pass


def _seed(store: FakeDocumentStore) -> None:
    store.set('users/u1/action_items/a1', {'idempotency_key': 'k1', 'completed': False})
    store.set('users/u1/action_items/a2', {'idempotency_key': 'k2', 'completed': False})


def test_the_transaction_reaches_the_store_on_a_collection_read():
    store = _SessionRecordingStore()
    _seed(store)
    client = NeutralFirestoreClient(store)
    transaction = client.transaction()
    transaction._begin()

    query = client.collection('users/u1/action_items').where('idempotency_key', '==', 'k1')
    rows = [snapshot.id for snapshot in query.stream(transaction=transaction)]

    assert rows == ['a1']
    assert store.query_sessions == [transaction._session], 'the read ran outside the transaction'
    assert store.query_sessions[0] is not None


def test_without_a_transaction_the_read_stays_session_less():
    """The common path must not silently acquire a session it was not given."""
    store = _SessionRecordingStore()
    _seed(store)
    client = NeutralFirestoreClient(store)

    rows = [snapshot.id for snapshot in client.collection('users/u1/action_items').stream()]

    assert sorted(rows) == ['a1', 'a2']
    assert store.query_sessions == [], 'a session-less read must not go through the session path'


def test_get_forwards_the_transaction_too():
    """`get()` is `stream()` materialised; upstream calls both shapes."""
    store = _SessionRecordingStore()
    _seed(store)
    client = NeutralFirestoreClient(store)
    transaction = client.transaction()
    transaction._begin()

    rows = client.collection('users/u1/action_items').where('completed', '==', False).get(transaction)

    assert sorted(snapshot.id for snapshot in rows) == ['a1', 'a2']
    assert store.query_sessions == [transaction._session]


def test_the_dedup_shape_from_action_items_runs_in_the_transaction():
    """The real call shape: two filters, a limit, streamed with the transaction — the read whose result
    decides whether a duplicate action item gets created."""
    store = _SessionRecordingStore()
    _seed(store)
    client = NeutralFirestoreClient(store)
    transaction = client.transaction()
    transaction._begin()

    query = (
        client.collection('users/u1/action_items')
        .where('idempotency_key', '==', 'k2')
        .where('completed', '==', False)
        .limit(5)
    )
    found = [snapshot.id for snapshot in query.stream(transaction=transaction)]

    assert found == ['a2']
    assert store.query_sessions == [transaction._session]


def test_a_transactional_group_query_is_refused_not_ignored():
    """The other half of L24: `collection_group().stream(transaction=...)` also accepted and dropped it.

    `query_group` has no session-aware twin in the neutral port and no caller asks for one (the on-prem
    group queries are background sweeps — memory vector repair, projection sync — which run outside any
    transaction). Saying so beats repeating the defect quietly.
    """
    import pytest

    store = _SessionRecordingStore()
    _seed(store)
    client = NeutralFirestoreClient(store)
    transaction = client.transaction()
    transaction._begin()

    with pytest.raises(NotImplementedError, match='query_group has no'):
        list(client.collection_group('action_items').stream(transaction=transaction))

    # Without a transaction it is the ordinary sweep, untouched.
    assert isinstance(list(client.collection_group('action_items').stream()), list)


def test_a_transactional_count_is_refused_not_ignored():
    """Third instance of the same shape, found while fixing the first two: `_AggregationQuery.get` also
    took a `transaction` and ignored it — and there the lie is starker, because the count has already run
    by the time `.get()` is called. No caller counts inside a transaction, so the boundary is documented
    rather than pretended.
    """
    import pytest

    store = _SessionRecordingStore()
    _seed(store)
    client = NeutralFirestoreClient(store)
    transaction = client.transaction()
    transaction._begin()

    aggregation = client.collection('users/u1/action_items').count()
    with pytest.raises(NotImplementedError, match='no transactional count'):
        aggregation.get(transaction)

    assert aggregation.get()[0][0].value == 2
