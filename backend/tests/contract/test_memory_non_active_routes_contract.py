"""Dual-backend contract for non-active memory routes (ADR-0044 facade + ADR-0002 store port).

`database/memory_non_active_routes.py` records what the memory pipeline decided to do with a piece of
extracted memory that is NOT going into the user's active set: review it, archive it, keep it only as
context, reject it, hide it, skip it. One document per decision, under
`users/{uid}/non_active_memory_routes/nar_<sha256(uid:idempotency_key)>`, and the id is derived so a
re-run of the same pipeline step lands on the same document instead of a second one.

    transaction  `persist_non_active_route_outcome` opens a transaction, reads that document, and
                 branches on what it finds. Existing with the same `payload_fingerprint` -> return
                 the STORED record and write nothing. Existing with a different fingerprint -> raise
                 `NonActiveRouteStoreConflict` and write nothing. Absent -> write.

                 The read is what makes the id derivation worth anything, and dropping it fails
                 quietly in two directions. A retry of a pipeline step would overwrite the recorded
                 decision instead of replaying it: the audit fields (`reason`, `run_id`,
                 `source_ids`, `created_at`) silently become the retry's, so the record of WHY a
                 memory was rejected stops describing the run that rejected it. Worse, two different
                 decisions colliding on one idempotency key would stop being an error and become a
                 last-writer-wins overwrite — a memory the user's run archived can end up recorded as
                 `reject`, and the conflict that should have stopped the pipeline is never raised.
                 The tests below therefore assert on what came BACK and on what is still stored,
                 never merely that "one document exists under one id": a write that never reads
                 satisfies that.

    (`default_long_term_visible` is pinned to False on the way in. It is a product invariant riding
    the same write — a non-active route must not be able to make a memory long-term visible — so it
    is asserted where it is persisted.)

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import threading
import uuid

import pytest


@pytest.fixture
def routes(bind_store):
    run = uuid.uuid4().hex[:8]
    uid = f'nar-{run}'

    yield {'uid': uid, 'run': run, 'store': bind_store, 'collection': f'users/{uid}/non_active_memory_routes'}

    for document in bind_store.query(f'users/{uid}/non_active_memory_routes'):
        bind_store.delete(document.path)


def _outcome(routes, **overrides):
    """A route decision the way the pipeline hands one over."""
    from database.memory_non_active_routes import NonActiveRoute, NonActiveRouteOutcome

    fields = {
        'uid': routes['uid'],
        'route': NonActiveRoute.review,
        'idempotency_key': f"key-{routes['run']}",
        'source_ids': ['src-b', 'src-a'],
        'reason': 'low confidence',
        'run_id': f"run-{routes['run']}",
    }
    fields.update(overrides)
    return NonActiveRouteOutcome(**fields)


def _stored(routes):
    return {document.id: document.data for document in routes['store'].query(routes['collection'])}


class _GatedTransaction:
    """The production transaction, paused once between the body's read and its write.

    ``set`` is the first thing the body does after the read, so gating there is the only interleaving
    point available without editing ``database/memory_non_active_routes.py``. Every other attribute
    the SDK's ``@transactional`` driver touches (``_begin`` / ``_commit`` / ``_rollback`` /
    ``_clean_up`` / ``_max_attempts`` / ``_read_only`` / ``_id`` / ``in_progress``) is delegated to
    the real object, so what runs is the real transaction, only late.
    """

    def __init__(self, inner, gate):
        self._inner = inner
        self._gate = gate

    def __getattr__(self, name):
        return getattr(self.__dict__['_inner'], name)

    def set(self, *args, **kwargs):
        self._gate()
        return self._inner.set(*args, **kwargs)


class _GatedClient:
    """The production ``db_client``, handing out gated transactions. Everything else passes through."""

    def __init__(self, inner, gate):
        self._inner = inner
        self._gate = gate

    def __getattr__(self, name):
        return getattr(self.__dict__['_inner'], name)

    def transaction(self, *args, **kwargs):
        return _GatedTransaction(self._inner.transaction(*args, **kwargs), self._gate)


def _rendezvous(parties: int = 2, timeout: float = 1.5):
    """A one-shot barrier: hold each writer between its read and its write.

    Bounded and forgiving, because the two backends serialise contention at different moments — Mongo
    conflicts on the write, Firestore may hold a read lock and block the second reader — and the
    assertion is written to hold for either ordering. Retried attempts run straight through instead
    of waiting for a partner that has already finished.
    """
    barrier = threading.Barrier(parties)
    passed = threading.Event()

    def gate() -> None:
        if passed.is_set():
            return
        try:
            barrier.wait(timeout=timeout)
        except threading.BrokenBarrierError:
            pass
        passed.set()

    return gate


# --- transaction: the derived id plus the read that gives it meaning --------------------------------


def test_a_route_decision_is_persisted_under_its_derived_id(routes):
    import database.memory_non_active_routes as routes_db
    from database.memory_non_active_routes import NonActiveRoute

    persisted = routes_db.persist_non_active_route_outcome(_outcome(routes, route=NonActiveRoute.archive))

    stored = _stored(routes)
    assert list(stored) == [persisted.outcome_id]
    assert persisted.outcome_id.startswith('nar_')
    assert stored[persisted.outcome_id]['route'] == 'archive'
    assert stored[persisted.outcome_id]['reason'] == 'low confidence'
    assert stored[persisted.outcome_id]['payload_fingerprint'] == persisted.payload_fingerprint


def test_source_ids_are_normalised_before_they_are_stored(routes):
    """Sorted and de-duplicated, because they are part of the fingerprint: if the backend round-trips
    them in a different order the same decision would fingerprint differently on a replay and a
    harmless retry would surface as a conflict."""
    import database.memory_non_active_routes as routes_db

    persisted = routes_db.persist_non_active_route_outcome(
        _outcome(routes, source_ids=['src-b', 'src-a', 'src-b', '  '])
    )

    assert persisted.source_ids == ['src-a', 'src-b']
    assert _stored(routes)[persisted.outcome_id]['source_ids'] == ['src-a', 'src-b']


def test_a_non_active_route_never_stores_itself_as_long_term_visible(routes):
    """The invariant the route type exists to enforce, asserted where it is persisted: a decision NOT
    to put a memory in the active set must not be able to write a document that says otherwise."""
    import database.memory_non_active_routes as routes_db

    persisted = routes_db.persist_non_active_route_outcome(
        _outcome(routes, audit_metadata={'default_long_term_visible': True})
    )

    assert persisted.default_long_term_visible is False
    assert _stored(routes)[persisted.outcome_id]['default_long_term_visible'] is False


def test_replaying_the_same_decision_returns_the_stored_one_instead_of_rewriting_it(routes):
    """The assertion that a write-that-never-reads cannot pass.

    Not "one document exists" — a blind overwrite leaves exactly one document too. What proves the
    read happened is that the SECOND call hands back the FIRST call's record: same `created_at`,
    same audit metadata, none of the replay's. `created_at` defaults to "now" on every constructed
    outcome and is excluded from the fingerprint precisely so a replay is not a conflict, which makes
    it the field that tells the two apart.
    """
    import database.memory_non_active_routes as routes_db

    first = routes_db.persist_non_active_route_outcome(_outcome(routes, audit_metadata={'attempt': 1}))
    replay = routes_db.persist_non_active_route_outcome(_outcome(routes, audit_metadata={'attempt': 1}))

    assert replay.created_at == first.created_at, 'the replay must return the record already stored'
    assert replay.audit_metadata == {'attempt': 1}
    assert replay.outcome_id == first.outcome_id
    assert len(_stored(routes)) == 1


def test_a_replay_whose_source_ids_arrive_in_another_order_is_still_a_replay(routes):
    """Normalisation happens before the fingerprint, so the pipeline handing the same sources in a
    different order is the same decision — on both backends. If it were not, an ordinary retry would
    raise a conflict and stall the run."""
    import database.memory_non_active_routes as routes_db

    first = routes_db.persist_non_active_route_outcome(_outcome(routes, source_ids=['src-a', 'src-b']))
    replay = routes_db.persist_non_active_route_outcome(_outcome(routes, source_ids=['src-b', 'src-a']))

    assert replay.created_at == first.created_at
    assert len(_stored(routes)) == 1


def test_a_different_decision_under_the_same_key_is_refused_and_the_recorded_one_survives(routes):
    """The refusal the transaction exists for. Two different decisions colliding on one idempotency
    key is a pipeline bug, and it has to STOP — silently keeping the last writer would rewrite the
    user's recorded outcome (a memory they had archived, recorded as rejected) and destroy the reason
    the first decision was made."""
    import database.memory_non_active_routes as routes_db
    from database.memory_non_active_routes import NonActiveRoute

    first = routes_db.persist_non_active_route_outcome(_outcome(routes, route=NonActiveRoute.archive))

    with pytest.raises(routes_db.NonActiveRouteStoreConflict):
        routes_db.persist_non_active_route_outcome(
            _outcome(routes, route=NonActiveRoute.reject, reason='contradicted by a later source')
        )

    stored = _stored(routes)
    assert list(stored) == [first.outcome_id]
    assert stored[first.outcome_id]['route'] == 'archive', 'the recorded decision must survive the collision'
    assert stored[first.outcome_id]['reason'] == 'low confidence'


def test_a_different_idempotency_key_is_a_different_decision(routes):
    """The other half of the derivation: distinct keys must not collide into one document, or the
    second decision is never recorded at all."""
    import database.memory_non_active_routes as routes_db
    from database.memory_non_active_routes import NonActiveRoute

    first = routes_db.persist_non_active_route_outcome(_outcome(routes))
    second = routes_db.persist_non_active_route_outcome(
        _outcome(routes, idempotency_key=f"key2-{routes['run']}", route=NonActiveRoute.hidden)
    )

    stored = _stored(routes)
    assert first.outcome_id != second.outcome_id
    assert set(stored) == {first.outcome_id, second.outcome_id}
    assert stored[second.outcome_id]['route'] == 'hidden'


def test_a_stored_record_that_does_not_parse_is_not_silently_replaced(routes):
    """The existing document is read through the strict boundary. A corrupt record must fail closed:
    overwriting it would erase the only evidence of a decision already taken, and returning it as if
    it parsed would feed a malformed outcome back into the pipeline."""
    import database.memory_non_active_routes as routes_db
    from database.read_boundary import MalformedDocError

    outcome_id = routes_db._stable_outcome_id(routes['uid'], f"key-{routes['run']}")
    routes['store'].set(f"{routes['collection']}/{outcome_id}", {'uid': routes['uid'], 'route': 'not_a_route'})

    with pytest.raises(MalformedDocError):
        routes_db.persist_non_active_route_outcome(_outcome(routes))

    assert _stored(routes)[outcome_id] == {'uid': routes['uid'], 'route': 'not_a_route'}


def test_two_concurrent_decisions_on_one_key_cannot_both_be_recorded(routes, monkeypatch):
    """Both writers read "nothing recorded yet" before either writes; only one may end up stored.

    This is the concurrent form of the collision above, and the one that needs the transaction rather
    than the derived id: the id makes both writers aim at the same document, and only the transaction
    stops the second from landing on top of the first. Whichever one wins, the stored record must be
    entirely that one's — route AND reason — and the loser must not have been told it succeeded.

    How the loser is refused differs by backend and is deliberately not pinned: on Firestore the SDK
    retries the aborted body, the retry reads the winner's record and raises the module's own
    `NonActiveRouteStoreConflict`; on Mongo the conflict surfaces on the write inside the body, where
    `firestore_facade._txn_write_errors` maps it to `google.api_core.Aborted` — which the SDK
    decorator only retries around `transaction._commit()`, never around the body — so the raw
    `Aborted` reaches the caller. Both refuse the losing write; the exception a caller has to catch
    is not yet the same, and that divergence belongs to the facade, not to this suite.
    """
    from google.api_core.exceptions import Aborted

    import database.memory_non_active_routes as routes_db
    from database.memory_non_active_routes import NonActiveRoute

    gate = _rendezvous(parties=2)
    client = _GatedClient(routes_db.db, gate)
    outcomes: dict[str, object] = {}

    def decide(name: str, route, reason: str) -> None:
        try:
            routes_db.persist_non_active_route_outcome(_outcome(routes, route=route, reason=reason), db_client=client)
            outcomes[name] = 'recorded'
        except routes_db.NonActiveRouteStoreConflict:
            outcomes[name] = 'conflict'
        except Exception as error:  # reported through the outcome map, never swallowed
            outcomes[name] = error

    threads = [
        threading.Thread(target=decide, args=('archive', NonActiveRoute.archive, 'superseded')),
        threading.Thread(target=decide, args=('reject', NonActiveRoute.reject, 'contradicted')),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
        assert not thread.is_alive(), 'a route decision never finished'

    recorded = sorted(name for name, outcome in outcomes.items() if outcome == 'recorded')
    assert len(recorded) == 1, f'exactly one decision may be recorded, got {outcomes}'
    refused = outcomes['reject' if recorded == ['archive'] else 'archive']
    assert refused == 'conflict' or isinstance(refused, Aborted), f'the loser must be refused, got {refused!r}'

    stored = list(_stored(routes).values())
    assert len(stored) == 1, f'one key, one document, got {stored}'
    assert stored[0]['route'] == recorded[0]
    assert stored[0]['reason'] == (
        'superseded' if recorded == ['archive'] else 'contradicted'
    ), "the stored record must be entirely the winner's, not a mixture of the two"
