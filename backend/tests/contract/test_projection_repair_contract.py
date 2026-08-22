"""Dual-backend contract for the projection-repair queue (ADR-0044 facade + ADR-0002 store port).

`database/projection_repair.py` is the durable to-do list that keeps the memory VECTOR index honest
with the fact store. When a commit retracts a fact, tombstones its evidence, or invalidates it, the
projection built from that fact is now wrong — the vector is still searchable and the user keeps being
shown, and reasoned at from, something the system has been told is no longer true. Each affected fact
gets a queued repair, and a worker later drains the queue and re-projects or deletes.

    batch      enqueue_projection_repairs writes every repair for one commit in a single commit, after
               probing each id with a point read so an existing repair is skipped. Both halves are
               user-visible:

               completeness — a repair the batch drops is a retracted fact whose vector is never
               deleted. Nothing retries it: the function returns the full list of repair ids either
               way, so the caller believes the whole commit is queued. The stale vector keeps
               surfacing in semantic search and in the context handed to the model.

               skip-if-present — the probe is what makes re-processing a commit safe. A repair that
               has already reached `repaired` (or `dead_letter`, after exhausting its retries) must
               NOT be reset to `queued` with a fresh attempt count; a backend whose point read
               reported "missing" for a document that exists would resurrect every finished repair on
               every replay, and a dead-lettered repair would loop forever instead of staying parked
               for a human.

The drain side (`process_projection_repairs`) is covered with it, because it is the only way to observe
what the batch actually wrote and because it is what enforces the queue's terminal states: it reads only
`queued` and `failed`, bounded by a limit, and each outcome is written back through the reference the
query handed it. If the status filter or the write-back is mistranslated, either a finished repair is
done again (the vector delete replays, harmlessly, but the queue never empties) or a failing repair
never reaches `dead_letter` and retries forever.

Not covered here, and why: the module's pure helpers (`affected_fact_ids`, `repair_reason`,
`projection_metadata_for_fact`, `projection_action_for_fact`, `reconcile_memory_projection`) touch no
store at all, so running them twice against two backends would prove nothing this suite is for; they
belong to the unit suite. `enqueue_projection_repairs` also has no chunk rollover — one commit per
call, however many facts the commit touched — so there is no oversized-batch case to hold here.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid

import pytest


def _commit(commit_id: str, mutations):
    return {'commit_id': commit_id, 'mutations': mutations}


@pytest.fixture
def repairs(bind_store):
    """One user with an empty repair queue; everything the tests write is cleaned up by path."""
    run = uuid.uuid4().hex[:8]
    uid = f'repair-{run}'

    yield {'uid': uid, 'run': run, 'store': bind_store}

    for document in bind_store.query(f'users/{uid}/projection_repairs'):
        bind_store.delete(document.path)


def _queue(repairs) -> dict:
    """The whole queue for this user, keyed by document id."""
    return {
        document.id: document.data for document in repairs['store'].query(f"users/{repairs['uid']}/projection_repairs")
    }


def _ok_repair(_uid, _fact):
    return 'upsert'


def _boom(_uid, _fact):
    raise RuntimeError('vector index unreachable')


def _no_fact(_fact_id):
    return None


# --- batch: enqueueing --------------------------------------------------------------------------------


def test_every_affected_fact_is_queued_by_the_one_commit(repairs):
    """Three mutations over two facts: one repair per FACT, both written by the same batch, both
    readable back. A fact left unqueued is a vector that stays searchable after the fact behind it was
    retracted."""
    import database.projection_repair as repair_db

    commit_id = f"c1-{repairs['run']}"
    fact_a, fact_b = f"fa-{repairs['run']}", f"fb-{repairs['run']}"

    repair_ids = repair_db.enqueue_projection_repairs(
        repairs['uid'],
        _commit(
            commit_id,
            [
                {'type': 'update_fact', 'fact_id': fact_a},
                {'type': 'retract_fact', 'fact_id': fact_a, 'reason': 'source_tombstoned'},
                {'type': 'update_fact', 'fact': {'id': fact_b}},
            ],
        ),
    )

    assert repair_ids == [f'{commit_id}:{fact_a}', f'{commit_id}:{fact_b}']

    queue = _queue(repairs)
    assert set(queue) == set(repair_ids), 'the batch has to leave every repair it reported as queued'
    assert queue[f'{commit_id}:{fact_a}']['fact_id'] == fact_a
    assert queue[f'{commit_id}:{fact_a}']['status'] == 'queued'
    assert queue[f'{commit_id}:{fact_a}']['source_commit_id'] == commit_id
    assert queue[f'{commit_id}:{fact_a}']['projection_version'] == repair_db.PROJECTION_VERSION


def test_the_reasons_for_one_fact_are_collected_onto_its_single_repair(repairs):
    """Two mutations, one fact, one repair — carrying both reasons, de-duplicated and in order. The
    reasons are how the drain decides what to do; losing one turns a retraction into a plain re-upsert."""
    import database.projection_repair as repair_db

    commit_id = f"c2-{repairs['run']}"
    fact = f"f-{repairs['run']}"

    repair_db.enqueue_projection_repairs(
        repairs['uid'],
        _commit(
            commit_id,
            [
                {'type': 'update_fact', 'fact_id': fact},
                {'type': 'update_fact', 'fact_id': fact},
                {'type': 'tombstone_evidence', 'fact_id': fact},
            ],
        ),
    )

    stored = _queue(repairs)[f'{commit_id}:{fact}']
    assert stored['reasons'] == ['update_fact', 'tombstone_evidence']
    assert stored['dangerous'] is True, 'tombstoning evidence is one of the reasons a human must see'


def test_an_ordinary_update_is_not_flagged_dangerous(repairs):
    """The flag is the queue's triage signal. Marking everything dangerous is as useless as marking
    nothing: the operator stops reading it."""
    import database.projection_repair as repair_db

    commit_id = f"c3-{repairs['run']}"
    fact = f"f-{repairs['run']}"
    repair_db.enqueue_projection_repairs(repairs['uid'], _commit(commit_id, [{'type': 'update_fact', 'fact_id': fact}]))

    assert _queue(repairs)[f'{commit_id}:{fact}']['dangerous'] is False


def test_a_commit_that_touches_no_fact_writes_nothing(repairs):
    import database.projection_repair as repair_db

    assert repair_db.enqueue_projection_repairs(repairs['uid'], None) == []
    assert repair_db.enqueue_projection_repairs(repairs['uid'], _commit(f"c4-{repairs['run']}", [])) == []
    assert (
        repair_db.enqueue_projection_repairs(repairs['uid'], _commit(f"c4-{repairs['run']}", [{'type': 'noop'}])) == []
    )
    assert _queue(repairs) == {}


def test_replaying_a_commit_does_not_resurrect_a_repair_that_is_already_done(repairs):
    """The point of the point read before the batch, and the only way to see it.

    A repair that has already run is re-enqueued by an at-least-once caller. The probe must find it and
    the batch must leave it alone: asserting "one document under one id" would pass for a build that
    overwrote it, so what is asserted here is that the FINISHED state survives. Under a blind write the
    repair goes back to `queued` with its attempt count cleared, the worker re-runs it, and a
    dead-lettered repair — the one a human was supposed to look at — silently re-enters the loop.
    """
    import database.projection_repair as repair_db

    commit_id = f"c5-{repairs['run']}"
    fact = f"f-{repairs['run']}"
    repair_id = f'{commit_id}:{fact}'
    mutations = [{'type': 'retract_fact', 'fact_id': fact}]

    repair_db.enqueue_projection_repairs(repairs['uid'], _commit(commit_id, mutations))
    repair_db.process_projection_repairs(repairs['uid'], fact_loader=_no_fact, repair_func=_ok_repair)
    assert _queue(repairs)[repair_id]['status'] == 'repaired', 'precondition'

    assert repair_db.enqueue_projection_repairs(repairs['uid'], _commit(commit_id, mutations)) == [repair_id]

    stored = _queue(repairs)[repair_id]
    assert stored['status'] == 'repaired', 'a replayed commit must not put a finished repair back on the queue'
    assert stored['repair_action'] == 'upsert', 'the record of what was done must survive the replay'


def test_a_replay_that_brings_a_new_fact_queues_only_that_fact(repairs):
    """Mixed replay: the batch skips what exists and writes what does not, in the same commit."""
    import database.projection_repair as repair_db

    commit_id = f"c6-{repairs['run']}"
    fact_a, fact_b = f"fa-{repairs['run']}", f"fb-{repairs['run']}"

    repair_db.enqueue_projection_repairs(
        repairs['uid'], _commit(commit_id, [{'type': 'update_fact', 'fact_id': fact_a}])
    )
    repairs['store'].set(
        f"users/{repairs['uid']}/projection_repairs/{commit_id}:{fact_a}",
        {**_queue(repairs)[f'{commit_id}:{fact_a}'], 'status': 'dead_letter'},
    )

    repair_db.enqueue_projection_repairs(
        repairs['uid'],
        _commit(commit_id, [{'type': 'update_fact', 'fact_id': fact_a}, {'type': 'retract_fact', 'fact_id': fact_b}]),
    )

    queue = _queue(repairs)
    assert queue[f'{commit_id}:{fact_a}']['status'] == 'dead_letter', 'the parked repair stays parked'
    assert queue[f'{commit_id}:{fact_b}']['status'] == 'queued'
    assert queue[f'{commit_id}:{fact_b}']['dangerous'] is True


def test_one_commit_queues_every_one_of_its_facts(repairs):
    """A wide commit — 120 facts in one batch. Completeness again, at the size where a per-write loop
    and a batched commit stop looking the same."""
    import database.projection_repair as repair_db

    commit_id = f"wide-{repairs['run']}"
    fact_ids = [f"w{i}-{repairs['run']}" for i in range(120)]

    repair_ids = repair_db.enqueue_projection_repairs(
        repairs['uid'], _commit(commit_id, [{'type': 'retract_fact', 'fact_id': fact_id} for fact_id in fact_ids])
    )

    assert len(repair_ids) == 120
    assert set(_queue(repairs)) == set(repair_ids)


def test_repairs_are_scoped_to_the_user_that_owns_the_commit(repairs):
    """One user's queue must never be drained by another's worker — a repair applied under the wrong uid
    deletes a vector belonging to someone else."""
    import database.projection_repair as repair_db

    other = f"other-{repairs['run']}"
    commit_id = f"c7-{repairs['run']}"
    fact = f"f-{repairs['run']}"
    repair_db.enqueue_projection_repairs(other, _commit(commit_id, [{'type': 'update_fact', 'fact_id': fact}]))
    try:
        assert _queue(repairs) == {}
        assert repair_db.process_projection_repairs(repairs['uid'], fact_loader=_no_fact, repair_func=_ok_repair) == {
            'repaired': [],
            'failed': [],
            'processed': 0,
        }
    finally:
        for document in repairs['store'].query(f'users/{other}/projection_repairs'):
            repairs['store'].delete(document.path)


# --- draining the queue -------------------------------------------------------------------------------


def test_a_drained_repair_records_what_the_worker_did(repairs):
    """The write-back goes through the reference the query returned. A repair left at `queued` after a
    successful run is a vector delete that will be replayed on every subsequent drain, forever."""
    import database.projection_repair as repair_db

    commit_id = f"d1-{repairs['run']}"
    fact = f"f-{repairs['run']}"
    repair_db.enqueue_projection_repairs(repairs['uid'], _commit(commit_id, [{'type': 'update_fact', 'fact_id': fact}]))

    seen = []

    def loader(fact_id):
        seen.append(fact_id)
        return {'id': fact_id}

    outcome = repair_db.process_projection_repairs(
        repairs['uid'], fact_loader=loader, repair_func=lambda uid, fact: 'delete'
    )

    assert outcome == {'repaired': [f'{commit_id}:{fact}'], 'failed': [], 'processed': 1}
    assert seen == [fact], 'the fact id has to survive the round trip through storage'
    stored = _queue(repairs)[f'{commit_id}:{fact}']
    assert stored['status'] == 'repaired'
    assert stored['repair_action'] == 'delete'


def test_a_finished_repair_is_never_picked_up_again(repairs):
    """Only `queued` and `failed` are processable. A drain that also matched `repaired` would never
    terminate: every pass would re-run the whole history of the queue."""
    import database.projection_repair as repair_db

    commit_id = f"d2-{repairs['run']}"
    fact = f"f-{repairs['run']}"
    repair_db.enqueue_projection_repairs(repairs['uid'], _commit(commit_id, [{'type': 'update_fact', 'fact_id': fact}]))
    repair_db.process_projection_repairs(repairs['uid'], fact_loader=_no_fact, repair_func=_ok_repair)

    calls = []

    second = repair_db.process_projection_repairs(
        repairs['uid'], fact_loader=_no_fact, repair_func=lambda uid, fact: calls.append(fact) or 'upsert'
    )

    assert second == {'repaired': [], 'failed': [], 'processed': 0}
    assert calls == [], 'the worker must not touch the vector index for a repair already done'


def test_a_failing_repair_is_retried_and_then_parked_for_a_human(repairs):
    """Failure, retry, dead letter — the attempt count is the state that has to survive between drains.
    A backend that lost it would retry a permanently broken repair on every pass; one that inflated it
    would park a repair that only hit a transient outage, and the stale vector stays for good."""
    import database.projection_repair as repair_db

    commit_id = f"d3-{repairs['run']}"
    fact = f"f-{repairs['run']}"
    repair_id = f'{commit_id}:{fact}'
    repair_db.enqueue_projection_repairs(
        repairs['uid'], _commit(commit_id, [{'type': 'retract_fact', 'fact_id': fact}])
    )

    first = repair_db.process_projection_repairs(
        repairs['uid'], fact_loader=_no_fact, repair_func=_boom, max_attempts=2
    )
    assert first == {'repaired': [], 'failed': [repair_id], 'processed': 1}
    stored = _queue(repairs)[repair_id]
    assert stored['status'] == 'failed'
    assert stored['attempt_count'] == 1
    assert 'vector index unreachable' in stored['error']

    second = repair_db.process_projection_repairs(
        repairs['uid'], fact_loader=_no_fact, repair_func=_boom, max_attempts=2
    )
    assert second['failed'] == [repair_id], 'a failed repair is picked up again'
    assert _queue(repairs)[repair_id]['status'] == 'dead_letter'
    assert _queue(repairs)[repair_id]['attempt_count'] == 2

    third = repair_db.process_projection_repairs(
        repairs['uid'], fact_loader=_no_fact, repair_func=_boom, max_attempts=2
    )
    assert third == {'repaired': [], 'failed': [], 'processed': 0}, 'a dead letter stays parked'


def test_a_failed_repair_that_later_succeeds_leaves_the_queue(repairs):
    """The retry path has to be able to finish, or a transient outage is permanent."""
    import database.projection_repair as repair_db

    commit_id = f"d4-{repairs['run']}"
    fact = f"f-{repairs['run']}"
    repair_id = f'{commit_id}:{fact}'
    repair_db.enqueue_projection_repairs(repairs['uid'], _commit(commit_id, [{'type': 'update_fact', 'fact_id': fact}]))

    repair_db.process_projection_repairs(repairs['uid'], fact_loader=_no_fact, repair_func=_boom, max_attempts=5)
    assert _queue(repairs)[repair_id]['status'] == 'failed', 'precondition'

    outcome = repair_db.process_projection_repairs(repairs['uid'], fact_loader=_no_fact, repair_func=_ok_repair)

    assert outcome['repaired'] == [repair_id]
    assert _queue(repairs)[repair_id]['status'] == 'repaired'


def test_one_failure_does_not_stop_the_rest_of_the_drain(repairs):
    """Per-repair error handling. A backend that let the first exception escape would leave the whole
    queue behind whenever one fact is unrepairable."""
    import database.projection_repair as repair_db

    commit_id = f"d5-{repairs['run']}"
    good, bad = f"good-{repairs['run']}", f"bad-{repairs['run']}"
    repair_db.enqueue_projection_repairs(
        repairs['uid'],
        _commit(commit_id, [{'type': 'update_fact', 'fact_id': good}, {'type': 'update_fact', 'fact_id': bad}]),
    )

    def repair_func(_uid, fact):
        if fact and fact['id'] == bad:
            raise RuntimeError('nope')
        return 'upsert'

    outcome = repair_db.process_projection_repairs(
        repairs['uid'], fact_loader=lambda fact_id: {'id': fact_id}, repair_func=repair_func
    )

    assert outcome['processed'] == 2
    assert outcome['repaired'] == [f'{commit_id}:{good}']
    assert outcome['failed'] == [f'{commit_id}:{bad}']
    queue = _queue(repairs)
    assert queue[f'{commit_id}:{good}']['status'] == 'repaired'
    assert queue[f'{commit_id}:{bad}']['status'] == 'failed'


def test_the_drain_is_bounded_by_its_limit(repairs):
    """The bound is what keeps one worker pass finite. A backend that ignored `limit` would pull the
    whole queue into one pass and hold the vector index for as long as it takes.

    The bound is enforced TWICE — `.limit(limit)` on the query and a `len(docs) >= limit` break in the
    accumulator — and either one alone produces the right answer, so removing only the query bound
    survives this test (verified by mutation; removing both goes red). What is held here is the number
    of repairs a pass processes, which is what a user or operator can observe; the extra rows a
    limit-less query would read are a cost, not a behaviour.
    """
    import database.projection_repair as repair_db

    commit_id = f"d6-{repairs['run']}"
    fact_ids = [f"l{i}-{repairs['run']}" for i in range(5)]
    repair_db.enqueue_projection_repairs(
        repairs['uid'], _commit(commit_id, [{'type': 'update_fact', 'fact_id': fact_id} for fact_id in fact_ids])
    )

    outcome = repair_db.process_projection_repairs(
        repairs['uid'], fact_loader=_no_fact, repair_func=_ok_repair, limit=2
    )

    assert outcome['processed'] == 2
    assert len([data for data in _queue(repairs).values() if data['status'] == 'queued']) == 3


def test_a_drain_of_an_empty_queue_is_a_no_op(repairs):
    import database.projection_repair as repair_db

    assert repair_db.process_projection_repairs(repairs['uid'], fact_loader=_no_fact, repair_func=_ok_repair) == {
        'repaired': [],
        'failed': [],
        'processed': 0,
    }


def test_a_nonsensical_bound_is_refused_before_anything_is_read(repairs):
    """`limit=0` would silently drain nothing forever; `max_attempts=0` would dead-letter on the first
    try. Both are refused rather than obeyed."""
    import database.projection_repair as repair_db

    with pytest.raises(ValueError):
        repair_db.process_projection_repairs(repairs['uid'], fact_loader=_no_fact, repair_func=_ok_repair, limit=0)
    with pytest.raises(ValueError):
        repair_db.process_projection_repairs(
            repairs['uid'], fact_loader=_no_fact, repair_func=_ok_repair, max_attempts=0
        )
