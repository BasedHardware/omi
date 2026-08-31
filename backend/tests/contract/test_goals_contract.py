"""Dual-backend contract for goals (ADR-0044 facade + ADR-0002 store port).

`database/goals.py` is the user's own list of what they are trying to achieve, and every state change
to it is one shape:

    transaction   create, idempotent create, focus, unfocus, lifecycle transition and progress append
                  all open `client.transaction()` and run a read-decide-write body. Nothing is written
                  without first reading the documents the decision depends on — the account-generation
                  fence, the idempotency receipt, the currently focused SET, the related tasks, the
                  goal's own progress counter.

The concrete damage a wrong translation does, per fence:

  *The focus list stops being a list.* `focus_goal` reads every focused goal inside the transaction
  and picks the first free `focus_rank` from what it read. If that read is wrong the user ends up with
  two goals at rank 0 — the focus screen orders by rank, so which one is "first" becomes arbitrary and
  changes between refreshes — or with more focused goals than `focus_cap`, which is the one number the
  feature exists to hold. Replacing a focused goal is two writes (demote the incumbent, promote the
  challenger) that must land together or the user is left with two focused goals, or none.

  *A retried request applies twice.* Every fenced mutation reads a receipt derived from
  (uid, generation, operation, idempotency key) and returns the stored answer instead of re-running.
  A phone on a bad connection retries; without the receipt read the retry re-focuses a goal the user
  has since put back in the background, or mints a second copy of a goal they created once. The
  receipt is written by `create` in the SAME commit as the mutation, so a receipt can never outlive a
  mutation that did not happen.

  *Tasks keep pointing at a goal that ended.* Abandoning a goal with `detach` reads the related
  action_items and workstreams inside the transaction and clears their `goal_id` in the same commit as
  the goal's own status change. This is the exact read the facade used to accept and DROP (the port
  docstring names "the relationship detach in goals.py"), and a task left holding a dead goal_id is
  the stale-pointer failure the folders module records as 500ing every later move.

  *The progress timeline loses its order.* A progress event takes `sequence = latest + 1` from the
  goal document read in the same transaction, then writes the event and the new counter together. Two
  events at the same sequence make the history unorderable; a counter that advances without its event
  leaves a permanent gap.

  *A create that becomes an overwrite eats a goal.* Goals are written with `write_transaction.create`,
  never `set`. A backend that translated the precondition away would let a re-issued create replace a
  goal the user has been tracking for months, along with its created_at and its progress counter.

Not covered, and why: cross-transaction conflict detection under real concurrency. `focus_goal` keeps
a `focus_reservation` document precisely because the two backends differ there — Firestore locks its
read set, Mongo takes a snapshot and no read lock (ADR-0070) — and a same-outcome assertion for two
racing callers would be asserting something the port does not promise. Measured, not assumed: passing
`transaction=None` to the focused-set `.stream(...)` in `focus_goal` — the read leaving the
transaction entirely — leaves this suite green on both backends, because a sequential caller reads the
same committed state either way. That is exactly the blind spot a concurrency test would have to
close, and the one the port declines to underwrite.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

GENERATION = 1
RECEIPTS = 'workflow_mutation_receipts'


def _goal_data(title: str, **overrides):
    data = {'title': title, 'desired_outcome': f'{title} achieved', 'source': 'user'}
    data.update(overrides)
    return data


@pytest.fixture
def goals(bind_store):
    """One account at generation 1 with two background goals, plus a task and a workstream on the first."""
    run = uuid.uuid4().hex[:8]
    uid = f'goal-{run}'
    first, second = f'g1-{run}', f'g2-{run}'
    task_id, workstream_id = f't1-{run}', f'w1-{run}'
    seeded = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)

    bind_store.set(
        f'users/{uid}/task_intelligence_control/state',
        {'workflow_mode': 'write', 'account_generation': GENERATION},
    )

    import database.goals as goals_db

    for goal_id, title in ((first, 'Ship the release'), (second, 'Learn to swim')):
        goals_db.create_goal(uid, _goal_data(title, goal_id=goal_id))
    bind_store.set(
        f'users/{uid}/action_items/{task_id}',
        {'id': task_id, 'description': 'Cut the tag', 'goal_id': first, 'updated_at': seeded},
    )
    bind_store.set(
        f'users/{uid}/workstreams/{workstream_id}',
        {'workstream_id': workstream_id, 'title': 'Release work', 'goal_id': first, 'updated_at': seeded},
    )

    yield {
        'uid': uid,
        'run': run,
        'first': first,
        'second': second,
        'task': task_id,
        'workstream': workstream_id,
        'store': bind_store,
    }

    for collection in ('goals', 'action_items', 'workstreams', 'task_intelligence_control', RECEIPTS):
        for document in bind_store.query(f'users/{uid}/{collection}'):
            if collection == 'goals':
                for child in ('events', 'goal_history'):
                    for grandchild in bind_store.query(f'{document.path}/{child}'):
                        bind_store.delete(grandchild.path)
            bind_store.delete(document.path)


def _doc(goals, path):
    stored = goals['store'].get(f"users/{goals['uid']}/{path}")
    return stored.data if stored is not None and stored.exists else None


def _goal(goals, goal_id):
    return _doc(goals, f'goals/{goal_id}')


def _focused(goals) -> dict[str, int]:
    """{goal_id: focus_rank} for every goal the store says is focused."""
    return {
        document.id: (document.data or {}).get('focus_rank')
        for document in goals['store'].query(f"users/{goals['uid']}/goals")
        if (document.data or {}).get('status') == 'focused'
    }


def _receipts(goals) -> list[str]:
    return [document.id for document in goals['store'].query(f"users/{goals['uid']}/{RECEIPTS}")]


def _events(goals, goal_id) -> list[dict]:
    rows = [document.data for document in goals['store'].query(f"users/{goals['uid']}/goals/{goal_id}/events")]
    return sorted(rows, key=lambda row: row['sequence'])


# --- transaction: creating a goal -------------------------------------------------------------------


def test_a_new_goal_is_stamped_with_the_generation_read_in_its_transaction(goals):
    """The control document is read in the same transaction that writes the goal. A goal stamped with
    the wrong generation is refused by every later fenced mutation — the user can see it and can no
    longer change it."""
    import database.goals as goals_db

    created = goals_db.create_goal(goals['uid'], _goal_data('Run a marathon', goal_id=f"g3-{goals['run']}"))

    assert created['status'] == 'background'
    assert _goal(goals, f"g3-{goals['run']}")['account_generation'] == GENERATION


def test_creating_a_goal_that_already_exists_does_not_overwrite_it(goals):
    """`write_transaction.create`, not `set`. Both backends must refuse identically: a re-issued create
    that overwrote instead would replace a goal the user has been tracking, discarding its created_at
    and its progress counter with no error anywhere."""
    from google.api_core import exceptions as google_exceptions

    import database.goals as goals_db

    before = _goal(goals, goals['first'])

    with pytest.raises(google_exceptions.AlreadyExists):
        goals_db.create_goal(goals['uid'], _goal_data('Something else entirely', goal_id=goals['first']))

    after = _goal(goals, goals['first'])
    assert after['title'] == before['title']
    assert after['created_at'] == before['created_at']


def test_an_idempotent_create_answers_a_retry_from_its_receipt(goals):
    """One key, one goal. Without the in-transaction receipt read a client retrying a flaky POST ends
    up with two identical goals in its list and no way to tell them apart."""
    import database.goals as goals_db

    key = f"create-{goals['run']}"
    payload = _goal_data('Write the book')
    first = goals_db.create_goal_idempotent(goals['uid'], payload, idempotency_key=key, account_generation=GENERATION)
    second = goals_db.create_goal_idempotent(goals['uid'], payload, idempotency_key=key, account_generation=GENERATION)

    assert second['id'] == first['id']
    titles = [(document.data or {}).get('title') for document in goals['store'].query(f"users/{goals['uid']}/goals")]
    assert titles.count('Write the book') == 1
    assert len(_receipts(goals)) == 1, 'the receipt is written once, in the same commit as the goal'


def test_an_idempotency_key_reused_for_different_content_is_refused(goals):
    """Same key, different goal: the caller is told rather than quietly served the wrong row."""
    import database.goals as goals_db

    key = f"create-{goals['run']}"
    goals_db.create_goal_idempotent(
        goals['uid'], _goal_data('Write the book'), idempotency_key=key, account_generation=GENERATION
    )

    with pytest.raises(goals_db.GoalConflictError):
        goals_db.create_goal_idempotent(
            goals['uid'], _goal_data('Sell the book'), idempotency_key=key, account_generation=GENERATION
        )


def test_a_colliding_idempotent_create_leaves_no_receipt_behind(goals):
    """The two writes of an idempotent create — the goal and its receipt — are one commit or neither.

    Reaching the collision needs the receipt out of the way, since the receipt is exactly what normally
    hides it; here it is deleted, the way a retention sweep or a partial restore would. The retry then
    finds the goal already there. What must NOT happen is a receipt for a mutation that did not land:
    that receipt would answer every future retry with 'already done' for a goal this call never wrote.
    The two backends reach it differently — Firestore buffers the create and fails the whole commit,
    Mongo raises on the operation and aborts the session — and must end in the same place.
    """
    from google.api_core import exceptions as google_exceptions

    import database.goals as goals_db

    key = f"create-{goals['run']}"
    payload = _goal_data('Write the book')
    created = goals_db.create_goal_idempotent(goals['uid'], payload, idempotency_key=key, account_generation=GENERATION)
    for receipt_id in _receipts(goals):
        goals['store'].delete(f"users/{goals['uid']}/{RECEIPTS}/{receipt_id}")

    with pytest.raises(google_exceptions.AlreadyExists):
        goals_db.create_goal_idempotent(goals['uid'], payload, idempotency_key=key, account_generation=GENERATION)

    assert _receipts(goals) == [], 'a receipt outlived the mutation it was supposed to record'
    assert _goal(goals, created['id'])['title'] == 'Write the book'


def test_a_mutation_from_a_withdrawn_generation_writes_nothing(goals):
    """The generation fence is read inside the transaction, before the receipt and before the write. A
    worker still holding the old generation must not add a goal to an account that has since been
    reset — that goal would be unreachable by every later fenced mutation."""
    import database.goals as goals_db

    with pytest.raises(goals_db.GoalConflictError):
        goals_db.create_goal_idempotent(
            goals['uid'],
            _goal_data('Ghost goal'),
            idempotency_key=f"stale-{goals['run']}",
            account_generation=GENERATION + 1,
        )

    titles = [(document.data or {}).get('title') for document in goals['store'].query(f"users/{goals['uid']}/goals")]
    assert 'Ghost goal' not in titles
    assert _receipts(goals) == []


# --- transaction: the focused set -------------------------------------------------------------------


def _focus(goals, goal_id, *, key=None, **kwargs):
    import database.goals as goals_db

    return goals_db.focus_goal(
        goals['uid'],
        goal_id,
        idempotency_key=key or f'focus-{goal_id}',
        account_generation=GENERATION,
        **kwargs,
    )


def test_the_first_focused_goal_takes_the_first_rank(goals):
    assert _focus(goals, goals['first'])['focus_rank'] == 0
    assert _focused(goals) == {goals['first']: 0}


def test_a_second_focus_reads_the_occupied_rank_and_takes_the_next(goals):
    """The focused-set read is what makes the ranks distinct. Two goals at rank 0 make the focus screen
    order itself differently on every refresh, for no reason the user can see."""
    _focus(goals, goals['first'])
    _focus(goals, goals['second'])

    assert _focused(goals) == {goals['first']: 0, goals['second']: 1}


def test_focusing_past_the_cap_is_refused_instead_of_silently_widening_it(goals):
    """`focus_cap` is the whole feature: a bounded set of things the user is actually working on. The
    cap can only be enforced against the focused set read in the same transaction."""
    import database.goals as goals_db

    _focus(goals, goals['first'], focus_cap=1)

    with pytest.raises(goals_db.GoalConflictError):
        _focus(goals, goals['second'], focus_cap=1)

    assert _focused(goals) == {goals['first']: 0}
    assert _goal(goals, goals['second'])['status'] == 'background'


def test_a_replacement_demotes_the_incumbent_and_promotes_the_challenger_together(goals):
    """Two documents, one commit. Half of it is either two focused goals in a cap-of-one, or a focus
    slot the user paid for and cannot see."""
    _focus(goals, goals['first'], focus_cap=1)

    _focus(goals, goals['second'], focus_cap=1, replacement_goal_id=goals['first'])

    assert _focused(goals) == {goals['second']: 0}
    assert _goal(goals, goals['first'])['focus_rank'] is None


def test_naming_a_goal_that_is_not_focused_as_the_replacement_is_refused(goals):
    """The replacement is checked against the focused set that was read, not taken on trust."""
    import database.goals as goals_db

    third = f"g3-{goals['run']}"
    goals_db.create_goal(goals['uid'], _goal_data('Third', goal_id=third))
    _focus(goals, goals['first'], focus_cap=1)

    with pytest.raises(goals_db.GoalConflictError):
        _focus(goals, goals['second'], focus_cap=1, replacement_goal_id=third)

    assert _focused(goals) == {goals['first']: 0}


def test_an_explicitly_requested_rank_that_is_taken_is_refused(goals):
    """The fixtures differ only in which rank is asked for: rank 2 is free for the first goal and taken
    for the second. A backend that lost the occupancy read would put both goals on rank 2."""
    import database.goals as goals_db

    _focus(goals, goals['first'], focus_rank=2)

    with pytest.raises(goals_db.GoalConflictError):
        _focus(goals, goals['second'], focus_rank=2)

    assert _focused(goals) == {goals['first']: 2}


def test_unfocusing_frees_the_rank_for_the_next_goal(goals):
    """The rank must come back, or the focus set slowly fills up with slots nothing can occupy."""
    import database.goals as goals_db

    _focus(goals, goals['first'], focus_rank=0)
    goals_db.unfocus_goal(
        goals['uid'], goals['first'], idempotency_key=f"unfocus-{goals['run']}", account_generation=GENERATION
    )

    assert _focused(goals) == {}
    assert _focus(goals, goals['second'])['focus_rank'] == 0


def test_a_replayed_focus_is_answered_from_its_receipt_and_not_re_applied(goals):
    """The scenario only the receipt catches. The user focuses a goal, changes their mind and unfocuses
    it, and the original request is then retried by a client that never saw the first response. The
    retry must be answered from the receipt — re-applying it would resurrect a state the user has
    already undone, which reads as the app fighting them.
    """
    import database.goals as goals_db

    key = f"focus-once-{goals['run']}"
    original = _focus(goals, goals['first'], key=key)
    goals_db.unfocus_goal(
        goals['uid'], goals['first'], idempotency_key=f"unfocus-{goals['run']}", account_generation=GENERATION
    )

    replay = _focus(goals, goals['first'], key=key)

    assert replay['status'] == original['status'] == 'focused', 'the retry gets the original answer'
    assert _goal(goals, goals['first'])['status'] == 'background', 'and the stored goal is not re-focused'


# --- transaction: ending a goal and its relationships -----------------------------------------------


def _transition(goals, goal_id, status, disposition, *, key=None):
    import database.goals as goals_db
    from models.goal import GoalRelationshipDisposition, GoalStatus

    return goals_db.transition_goal_lifecycle(
        goals['uid'],
        goal_id,
        status=GoalStatus(status),
        relationship_disposition=GoalRelationshipDisposition(disposition),
        idempotency_key=key or f'end-{goal_id}',
        account_generation=GENERATION,
    )


def test_abandoning_a_goal_with_detach_clears_every_relationship_in_the_same_commit(goals):
    """The read the facade used to accept and drop. A task or workstream left holding the id of an
    abandoned goal is a dangling pointer the user meets later as a broken screen."""
    _transition(goals, goals['first'], 'abandoned', 'detach')

    assert _goal(goals, goals['first'])['status'] == 'abandoned'
    assert _doc(goals, f"action_items/{goals['task']}")['goal_id'] is None
    assert _doc(goals, f"workstreams/{goals['workstream']}")['goal_id'] is None


def test_retaining_leaves_the_relationships_pointing_at_the_ended_goal(goals):
    """Same transition, same fixtures, one word different: `retain` keeps the history the user asked to
    keep. If detach and retain behave the same, one of the two promises is broken."""
    _transition(goals, goals['first'], 'achieved', 'retain')

    assert _goal(goals, goals['first'])['status'] == 'achieved'
    assert _doc(goals, f"action_items/{goals['task']}")['goal_id'] == goals['first']
    assert _doc(goals, f"workstreams/{goals['workstream']}")['goal_id'] == goals['first']


def test_ending_a_goal_drops_it_out_of_the_focus_set(goals):
    """Focus rank and active flag are cleared with the status, in one commit — otherwise the focus
    screen keeps a slot for a goal that is over."""
    _focus(goals, goals['first'])

    _transition(goals, goals['first'], 'achieved', 'retain')

    assert _focused(goals) == {}
    assert _goal(goals, goals['first'])['is_active'] is False


def test_ending_a_goal_that_is_not_there_writes_no_receipt(goals):
    """The existence read is inside the transaction with the receipt write, so a failed transition
    cannot leave a receipt that makes the retry look already-done."""
    import database.goals as goals_db

    with pytest.raises(goals_db.GoalNotFoundError):
        _transition(goals, f"ghost-{goals['run']}", 'abandoned', 'detach')

    assert _receipts(goals) == []


# --- transaction: the progress journal --------------------------------------------------------------


def _append(goals, goal_id, summary, *, key, kind='evidence', metric=None):
    import database.goals as goals_db
    from models.goal import GoalProgressEventCreate

    return goals_db.append_goal_progress_event(
        goals['uid'],
        goal_id,
        GoalProgressEventCreate(kind=kind, summary=summary, metric=metric),
        idempotency_key=key,
        account_generation=GENERATION,
    )


def test_each_progress_event_takes_the_sequence_after_the_one_it_read(goals):
    """`sequence = latest_progress_sequence + 1`, read from the goal in the same transaction that
    writes both the event and the new counter. Two events sharing a sequence make the progress history
    unorderable, and the client de-duplicates them into one."""
    first = _append(goals, goals['first'], 'started', key=f"e1-{goals['run']}")
    second = _append(goals, goals['first'], 'kept going', key=f"e2-{goals['run']}")

    assert (first.sequence, second.sequence) == (1, 2)
    assert [row['sequence'] for row in _events(goals, goals['first'])] == [1, 2]
    assert _goal(goals, goals['first'])['latest_progress_sequence'] == 2


def test_a_replayed_progress_event_does_not_advance_the_sequence(goals):
    """A retried append must return the event it already wrote. Advancing anyway leaves a gap the
    history renders as a missing entry."""
    key = f"e1-{goals['run']}"
    first = _append(goals, goals['first'], 'started', key=key)
    replay = _append(goals, goals['first'], 'started', key=key)

    assert replay.event_id == first.event_id
    assert replay.sequence == 1
    assert len(_events(goals, goals['first'])) == 1
    assert _goal(goals, goals['first'])['latest_progress_sequence'] == 1


def test_a_progress_key_reused_with_different_content_is_refused(goals):
    """Two different things cannot be the same entry in the user's history."""
    import database.goals as goals_db

    key = f"e1-{goals['run']}"
    _append(goals, goals['first'], 'started', key=key)

    with pytest.raises(goals_db.GoalConflictError):
        _append(goals, goals['first'], 'something else', key=key)

    assert len(_events(goals, goals['first'])) == 1


def test_a_metric_carrying_event_moves_the_goal_and_the_journal_together(goals):
    """One commit, two documents. If they can come apart, the progress feed says the user is at 7 and
    the goal badge still says 0 — or the badge moves with nothing in the history to explain why."""
    from models.goal import GoalMetric, GoalType

    metric = GoalMetric(type=GoalType.numeric, current=7.0, target=10.0)
    _append(goals, goals['first'], 'measured', key=f"m1-{goals['run']}", kind='metric_update', metric=metric)

    stored = _goal(goals, goals['first'])
    assert stored['metric']['current'] == 7.0
    assert stored['current_value'] == 7.0, 'the released numeric alias moves with the metric'
    assert _events(goals, goals['first'])[0]['metric']['current'] == 7.0


def test_a_progress_event_for_a_missing_goal_writes_nothing(goals):
    """The goal existence read is in the transaction with the event write: no orphan events under an id
    that has no goal."""
    import database.goals as goals_db

    ghost = f"ghost-{goals['run']}"
    with pytest.raises(goals_db.GoalNotFoundError):
        _append(goals, ghost, 'started', key=f"e1-{goals['run']}")

    assert _events(goals, ghost) == []
