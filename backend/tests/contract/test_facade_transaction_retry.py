"""A write conflict on the Mongo posture must REPLAY the transaction body (ADR-0091, BACKLOG L53).

**Why this is not a dual-backend contract suite, though it lives beside them.** The first version was
parametrised over both backends and its docstring claimed the two postures now agree. The Firestore leg
then failed four tests and took 79 seconds, which is the measurement that corrected the claim: on
Firestore a transaction holds a lock on what it READ, so an out-of-band write to that row blocks until
the transaction resolves — the interference cannot land, and the two wait for each other until the lock
times out. That is the divergence ADR-0070 already records, and it means contention cannot be forced
portably from a test.

What is ours is the Mongo half. Firestore's retry is google's own SDK behaviour on google's own client;
asserting it here would be asserting something we neither own nor can trigger. So this drives the facade
against a live Mongo replica set and says what changed:

    before   a write conflict surfaced from INSIDE the body (the `update_one` on the session), and
             google's `_pre_commit` sits outside `except retryable_exceptions` — so it propagated as a
             bare `Aborted` and the body ran exactly ONCE. A caller catching only its own domain error
             got an unhandled exception; the MCP token exchange turned it into an HTTP 500 (L56).
    now      the conflict is HELD on the transaction and re-raised from `_commit`, the one place the
             decorator watches. The body replays, re-reads, and commits.

The interference is issued from inside the body on a chosen attempt: deterministic, and exactly the
interleaving contention produces. A threaded version would pass with the retry removed, because nothing
forces the order. Order matters twice over: the competitor must land BEFORE this transaction's first
write, or it waits on the lock until Mongo's 60-second transaction lifetime expires — one early draft of
this file took 70 seconds for that reason.

One mutation survives and is recorded rather than hidden: deleting the re-raise in ``_commit`` still
retries, because committing an already aborted session fails with a TransientTransactionError label that
the existing handler turns into ``Aborted``. It is redundant with pymongo's current reporting. It stays
so the retry is a decision of ours rather than a side effect of a driver's labelling.
"""

from __future__ import annotations

import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get('MONGO_URI'), reason='MONGO_URI not set')


@pytest.fixture
def rig():
    """The pair this posture deploys: the neutral facade over a live Mongo replica set."""
    from database.store.adapters.mongo import MongoDocumentStore
    from database.store.firestore_facade import NeutralFirestoreClient

    store = MongoDocumentStore(uri=os.environ['MONGO_URI'], db_name='omi_contract')
    run = uuid.uuid4().hex[:8]
    path = f'users/contend-{run}'
    store.set(path, {'n': 0, 'note': 'original'})
    try:
        yield {'client': NeutralFirestoreClient(store), 'store': store, 'path': path}
    finally:
        store.delete(path)
        store.close()


def _run(rig, *, interfere_on_attempt=1):
    from google.cloud.firestore import transactional

    attempts: list[int] = []
    seen: list[object] = []

    @transactional
    def body(transaction, ref):
        attempts.append(len(attempts) + 1)
        snapshot = transaction.get(ref)
        seen.append((snapshot.to_dict() or {}).get('n'))
        if len(attempts) == interfere_on_attempt:
            rig['store'].set(rig['path'], {'n': 99, 'note': 'competitor'})
        transaction.set(ref, {'n': len(attempts), 'note': 'winner'})

    body(rig['client'].transaction(), rig['client'].document(rig['path']))
    return attempts, seen


def _stored(rig):
    return rig['store'].get(rig['path']).data


def test_a_contended_transaction_replays_its_body_and_commits(rig):
    """Before this change the same call raised `Aborted` after one attempt."""
    attempts, _seen = _run(rig)

    assert len(attempts) == 2, 'the body must run again after losing the race'
    assert _stored(rig)['note'] == 'winner'


def test_the_replay_re_reads_instead_of_reusing_the_stale_snapshot(rig):
    """A retry that replayed against the snapshot it already had would be a retry in name only: it would
    overwrite the competitor with a decision made before the competitor existed."""
    _attempts, seen = _run(rig)

    assert seen == [0, 99], 'the second attempt must read what beat it'


def test_an_uncontended_transaction_still_runs_exactly_once(rig):
    """The retry must not become a general re-run."""
    attempts, seen = _run(rig, interfere_on_attempt=0)

    assert attempts == [1]
    assert seen == [0]
    assert _stored(rig) == {'n': 1, 'note': 'winner'}


def test_an_error_from_the_body_is_not_retried_and_reaches_the_caller(rig):
    """Only contention is retryable. A domain refusal is the transaction's ANSWER, and replaying it would
    run the caller's decision logic several times for one request."""
    from google.cloud.firestore import transactional

    attempts: list[int] = []

    class Refused(Exception):
        pass

    @transactional
    def body(transaction, ref):
        attempts.append(1)
        transaction.get(ref)
        raise Refused('the body decided no')

    with pytest.raises(Refused):
        body(rig['client'].transaction(), rig['client'].document(rig['path']))

    assert attempts == [1], 'a domain refusal must not be replayed'
    assert _stored(rig)['note'] == 'original', 'and must leave nothing behind'


def test_nothing_from_the_losing_attempt_survives(rig):
    """The losing attempt wrote before it lost, and kept writing after — the transaction goes inert
    rather than raising, so the body can reach the commit. None of it may land."""
    from google.cloud.firestore import transactional

    attempts: list[int] = []

    @transactional
    def body(transaction, ref):
        attempts.append(len(attempts) + 1)
        transaction.get(ref)
        if len(attempts) == 1:
            # The competitor lands BEFORE this transaction's first write. Order matters and it is not
            # cosmetic: writing first takes a lock, and the out-of-band write then waits for it until
            # Mongo's 60-second transaction lifetime expires. Measured — that one test took 70s.
            rig['store'].set(rig['path'], {'n': 99, 'note': 'competitor'})
            transaction.set(ref, {'n': -1, 'note': 'the write that lost', 'ghost': True})
            transaction.set(ref, {'n': -2, 'note': 'written after the conflict'})
        transaction.set(ref, {'n': len(attempts), 'note': f'attempt-{len(attempts)}'})

    body(rig['client'].transaction(), rig['client'].document(rig['path']))

    stored = _stored(rig)
    assert stored['note'] == 'attempt-2', 'the replay decides, alone'
    assert 'ghost' not in stored, 'the losing write must leave no trace'


def test_a_poisoned_read_reports_absent_rather_than_raising(rig):
    """What lets the body finish. Once the session is aborted, asking Mongo anything raises — so a read
    after the conflict reports "not there" instead. The body may then take its create branch; every write
    on that branch is inert, and the replay decides again against real data."""
    from google.cloud.firestore import transactional

    reads: list[bool] = []

    @transactional
    def body(transaction, ref):
        transaction.get(ref)
        if not reads:
            rig['store'].set(rig['path'], {'n': 99, 'note': 'competitor'})
            transaction.set(ref, {'n': -1})
            reads.append(transaction.get(ref).exists)
        transaction.set(ref, {'n': 1, 'note': 'winner'})

    body(rig['client'].transaction(), rig['client'].document(rig['path']))

    assert reads == [False], 'a read after the conflict must report absent, not raise'
    assert _stored(rig)['note'] == 'winner'


def test_a_poisoned_transaction_stops_talking_to_the_dead_session(rig):
    """What the inert short-circuit buys, which correctness alone does not.

    Once Mongo has aborted the session every further operation fails, and the conflict handler would
    simply record the same poison again — so removing the early return leaves the OUTCOME identical, and
    the mutation survives. What changes is traffic: a body that writes many documents after losing the
    race would issue one doomed round-trip per write. This counts them.
    """
    from google.cloud.firestore import transactional

    store = rig['store']
    writes: list[str] = []
    attempts: list[int] = []
    real_set = store._set

    def counting_set(path, data, **kwargs):
        # Only writes issued INSIDE the transaction: the competitor goes through the same store without a
        # session, and counting it would make the number describe the test instead of the mechanism.
        if kwargs.get('session') is not None:
            writes.append(path)
        return real_set(path, data, **kwargs)

    store._set = counting_set
    try:

        @transactional
        def body(transaction, ref):
            attempts.append(1)
            transaction.get(ref)
            if len(attempts) == 1:
                rig['store'].set(rig['path'], {'n': 99, 'note': 'competitor'})
            for index in range(5):
                transaction.set(ref, {'n': index, 'note': 'winner'})

        body(rig['client'].transaction(), rig['client'].document(rig['path']))
    finally:
        store._set = real_set

    # First attempt: one write reaches the session, conflicts, and the remaining four are inert.
    # Second attempt: all five land. Without the short-circuit the first attempt would issue five.
    assert len(writes) == 6, f'expected 1 doomed write + 5 on the replay, got {len(writes)}'
    assert _stored(rig)['note'] == 'winner'
