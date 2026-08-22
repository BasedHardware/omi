"""Dual-backend contract for the memory ledger (ADR-0044 facade + ADR-0002 store port).

`database/memory_ledger.py` is a content-addressed, append-only history: a commit's id is a hash of
its parent and its mutations, and `users/{uid}/memory_state/head` names the current tip. Everything
that keeps that history linear is one shape.

    transaction   `_append_commit_transaction` reads the head AND the candidate commit inside the
                  transaction, then refuses on `HeadConflict` if the head has moved since the caller
                  read it. Two consequences if the read is not part of the write:
                    - two concurrent appends both succeed and one silently overwrites the other's
                      head, so a branch of the user's memory history is orphaned — the commits still
                      exist, nothing points at them, and no error is raised anywhere;
                    - a retried append re-writes a commit that already exists instead of reporting
                      `applied: False`, and the caller re-runs its side effects.

The module also encodes a **Firestore-specific ordering rule** that our port has to honor: every
transactional read is issued before any write, because Firestore raises `ReadAfterWriteError`
otherwise (its own comment says so twice). That constraint has no equivalent on Mongo, which makes it
exactly the kind of thing that rots unnoticed on a single-backend suite. Both legs run here.

What this suite does NOT hold, measured rather than assumed. Moving the head read out of the
transaction (`state_ref.get()` instead of `state_ref.get(transaction=transaction)`) SURVIVES every
test here, and it cannot be otherwise: catching it needs a genuine concurrent write between the read
and the commit, and the two backends disagree about what happens then — Firestore aborts the
transaction that only READ the row, Mongo commits it with the stale read (measured, ADR-0070, table in
`deploy/onprem/SELFHOST_NOTES.md`). A contract suite asserts the intersection, so what is held here is
head-conflict detection by VALUE comparison, which both backends do honor. Lock semantics under
contention belong to `run_with_transaction_contention_retry` and its own tests.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

COMMIT_TIME = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)


def _client():
    """The client this backend deploys, resolved through the accessor ``bind_store`` patched."""
    from database import _client as client_module

    return client_module.get_firestore_client()


@pytest.fixture
def ledger(bind_store):
    run = uuid.uuid4().hex[:8]
    uid = f'ledger-{run}'

    yield {'uid': uid, 'run': run, 'store': bind_store}

    for document in bind_store.query(f'users/{uid}/memory_commits'):
        bind_store.delete(document.path)
    for document in bind_store.query(f'users/{uid}/memory_state'):
        bind_store.delete(document.path)
    for document in bind_store.query(f'users/{uid}/memory_projection_repairs'):
        bind_store.delete(document.path)


def _append(ledger, parent, mutations, **kwargs):
    import database.memory_ledger as ledger_db

    return ledger_db.append_commit(
        ledger['uid'], parent, mutations, commit_time=COMMIT_TIME, firestore_client=_client(), **kwargs
    )


def _fact(name: str):
    import database.memory_ledger as ledger_db

    return ledger_db.add_fact({'id': name, 'text': f'the user likes {name}'})


def _head(ledger):
    stored = ledger['store'].get(f"users/{ledger['uid']}/memory_state/head")
    return stored.data.get('current_head_commit_id') if stored is not None and stored.exists else None


# --- transaction: the head advances ---------------------------------------------------------------


def test_the_first_commit_becomes_the_head(ledger):
    result = _append(ledger, None, [_fact('coffee')])

    assert result['applied'] is True
    assert _head(ledger) == result['commit']['commit_id']
    assert result['commit']['parent_commit_id'] is None


def test_a_commit_on_the_current_head_extends_the_chain(ledger):
    first = _append(ledger, None, [_fact('coffee')])
    second = _append(ledger, first['commit']['commit_id'], [_fact('tea')])

    assert second['applied'] is True
    assert second['commit']['parent_commit_id'] == first['commit']['commit_id']
    assert _head(ledger) == second['commit']['commit_id']


def test_use_current_head_appends_without_the_caller_naming_the_parent(ledger):
    first = _append(ledger, None, [_fact('coffee')])
    second = _append(ledger, None, [_fact('tea')], use_current_head=True)

    assert second['commit']['parent_commit_id'] == first['commit']['commit_id']
    assert _head(ledger) == second['commit']['commit_id']


def test_the_commit_and_the_head_are_written_together(ledger):
    """Both writes are staged on the same transaction. A head pointing at a commit that was never
    stored is a history the reader cannot walk."""
    result = _append(ledger, None, [_fact('coffee')])

    stored = ledger['store'].get(f"users/{ledger['uid']}/memory_commits/{result['commit']['commit_id']}")
    assert stored.exists
    assert stored.data['commit_id'] == _head(ledger)


# --- transaction: the head refuses to move under someone else ------------------------------------


def test_appending_onto_a_parent_that_is_no_longer_the_head_is_refused(ledger):
    """The conflict the in-transaction read exists for.

    Two writers read the same head; the first commits, the second must lose. Without the read the
    second write lands anyway and the first writer's commit is orphaned — it stays in
    `memory_commits`, nothing points at it, and neither caller is told.
    """
    import database.memory_ledger as ledger_db

    first = _append(ledger, None, [_fact('coffee')])
    winner = _append(ledger, first['commit']['commit_id'], [_fact('tea')])

    with pytest.raises(ledger_db.HeadConflict) as conflict:
        _append(ledger, first['commit']['commit_id'], [_fact('cocoa')])

    assert conflict.value.current_head == winner['commit']['commit_id']
    assert _head(ledger) == winner['commit']['commit_id'], 'the loser must not move the head'


def test_a_first_commit_against_a_ledger_that_is_no_longer_empty_is_refused(ledger):
    """The same conflict at the boundary that is easiest to get wrong: parent `None` means "I believe
    this ledger is empty". Once it is not, that belief is stale like any other."""
    import database.memory_ledger as ledger_db

    existing = _append(ledger, None, [_fact('coffee')])

    with pytest.raises(ledger_db.HeadConflict):
        _append(ledger, None, [_fact('tea')])

    assert _head(ledger) == existing['commit']['commit_id']


def test_a_conflicting_append_writes_nothing_at_all(ledger):
    """The refusal must be atomic, not partial: a commit document left behind by a rejected append is
    an unreferenced object that a later garbage collection has to reason about."""
    first = _append(ledger, None, [_fact('coffee')])
    _append(ledger, first['commit']['commit_id'], [_fact('tea')])

    before = {document.id for document in ledger['store'].query(f"users/{ledger['uid']}/memory_commits")}
    with pytest.raises(Exception):
        _append(ledger, first['commit']['commit_id'], [_fact('cocoa')])
    after = {document.id for document in ledger['store'].query(f"users/{ledger['uid']}/memory_commits")}

    assert after == before


# --- transaction: the same commit twice ----------------------------------------------------------


def test_re_appending_an_identical_commit_is_reported_as_not_applied(ledger):
    """Content addressing plus the in-transaction existence read. A retried append — the ordinary case
    after a timeout — must be recognised, not re-run: the caller keys its side effects on `applied`,
    so a second `True` re-emits every projection and outbox event the first one already did.
    """
    first = _append(ledger, None, [_fact('coffee')])
    replay = _append(ledger, None, [_fact('coffee')], use_current_head=False)

    assert first['applied'] is True
    assert replay['applied'] is False
    assert replay['commit']['commit_id'] == first['commit']['commit_id']
    assert _head(ledger) == first['commit']['commit_id']


def test_the_replay_returns_the_stored_commit_not_the_recomputed_one(ledger):
    """It hands back what is on disk, which is the only version later readers will see."""
    first = _append(ledger, None, [_fact('coffee')])
    replay = _append(ledger, None, [_fact('coffee')])

    stored = ledger['store'].get(f"users/{ledger['uid']}/memory_commits/{first['commit']['commit_id']}")
    assert replay['commit']['commit_id'] == stored.data['commit_id']
    assert replay['commit']['parent_commit_id'] == stored.data['parent_commit_id']


# --- transaction: reads before writes -------------------------------------------------------------


def test_a_projection_writer_runs_inside_the_same_transaction(ledger):
    """The caller stages its own projection writes on the ledger's transaction so the projection and
    the commit cannot disagree. It runs AFTER every read for a reason — see the next test."""
    written = []

    def projection_writer(transaction):
        written.append(True)

    result = _append(ledger, None, [_fact('coffee')], projection_writer=projection_writer)

    assert written == [True]
    assert result['applied'] is True


def test_every_transactional_read_happens_before_the_first_write(ledger):
    """The Firestore ordering rule the module's own comment records twice, held as behavior.

    Firestore raises `ReadAfterWriteError` if a transaction reads after it has staged a write; Mongo
    does not care. So this constraint is invisible on a Mongo-only suite and fatal in production — the
    class of bug the conftest docstring describes, where a facade configuration nothing deploys hid a
    transaction failure for months. Here a projection writer that stages a write is followed by the
    module's own reads, and the append must still succeed on BOTH legs.

    Measured: reordering the module so the head payload (which may read `apply_control`) is built after
    the first `transaction.set` fails eleven tests — and every one of them on the FIRESTORE leg only.
    The Mongo leg passes the reordered code without complaint, which is precisely why the rule needs a
    test on the backend that enforces it rather than a comment.
    """
    result = _append(
        ledger,
        None,
        [_fact('coffee')],
        projection_writer=lambda transaction: transaction.set(
            _client().document(f"users/{ledger['uid']}/memory_projection_repairs/probe"),
            {'probe': True},
        ),
    )

    assert result['applied'] is True
    assert ledger['store'].get(f"users/{ledger['uid']}/memory_projection_repairs/probe").exists
