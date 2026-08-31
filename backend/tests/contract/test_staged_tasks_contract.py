"""Dual-backend contract for staged tasks (ADR-0044 facade + ADR-0002 store port).

`database/staged_tasks.py` carries three shapes, and its projection is the one variant that has a real
consequence attached:

    projection    `.select([])` behind a `completed == False` filter, used to pre-resolve which ids are
                  still active BEFORE a batch update — the module's own docstring says why: a stale id
                  from the client would make `batch.update()` raise NotFound and take the whole batch
                  down with it
    batch         batch_update_staged_scores and clear_staged_tasks write many documents per commit,
                  re-opening a batch every BATCH_LIMIT documents
    cursor        restore_legacy_conversation_items orders by `__name__` and resumes with
                  `start_after({'__name__': <doc ref>})` — a document-name keyset, not a field cursor

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

NOW = datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def staged(bind_store):
    """Five staged tasks: three active, two already completed."""
    run = uuid.uuid4().hex[:8]
    uid = f'st-{run}'
    ids = [f's{i}-{run}' for i in range(5)]
    paths = [f'users/{uid}/staged_tasks/{task_id}' for task_id in ids]

    for index, task_id in enumerate(ids):
        bind_store.set(
            f'users/{uid}/staged_tasks/{task_id}',
            {
                'id': task_id,
                'description': f'task {index}',
                'completed': index >= 3,
                'relevance_score': 0.0,
                'created_at': NOW,
                'updated_at': NOW,
            },
        )

    yield {'uid': uid, 'ids': ids, 'active': ids[:3], 'done': ids[3:], 'store': bind_store, 'run': run}

    for path in paths:
        bind_store.delete(path)


def _doc(staged, task_id, collection='staged_tasks'):
    stored = staged['store'].get(f"users/{staged['uid']}/{collection}/{task_id}")
    return stored.data if stored is not None and stored.exists else None


# --- projection behind a filter ---------------------------------------------------------------------


def test_a_score_update_reaches_every_active_task(staged):
    """The ids-only projection resolves who is active, then the batch writes them."""
    import database.staged_tasks as staged_db

    staged_db.batch_update_staged_scores(
        staged['uid'], [{'id': task_id, 'relevance_score': 0.5} for task_id in staged['active']]
    )

    for task_id in staged['active']:
        assert _doc(staged, task_id)['relevance_score'] == 0.5


def test_a_stale_id_is_filtered_out_instead_of_failing_the_batch(staged):
    """The reason the projection exists, in the module's own words: a client can send an id that has
    since been deleted or promoted, and `batch.update()` on a missing document raises NotFound — taking
    every OTHER score in the same commit down with it. The pre-filter must drop it silently."""
    import database.staged_tasks as staged_db

    scores = [{'id': task_id, 'relevance_score': 0.7} for task_id in staged['active']]
    scores.append({'id': f"ghost-{staged['run']}", 'relevance_score': 0.7})

    staged_db.batch_update_staged_scores(staged['uid'], scores)

    for task_id in staged['active']:
        assert _doc(staged, task_id)['relevance_score'] == 0.7, 'the good ids must still have landed'


def test_a_completed_task_is_not_in_the_active_projection(staged):
    """`completed == False` is pushed into the projected query. A backend that ignored the filter would
    let a finished task be re-scored and reappear in the user's candidate list."""
    import database.staged_tasks as staged_db

    staged_db.batch_update_staged_scores(
        staged['uid'], [{'id': task_id, 'relevance_score': 0.9} for task_id in staged['done']]
    )

    for task_id in staged['done']:
        assert _doc(staged, task_id)['relevance_score'] == 0.0, 'a completed task must not be re-scored'


# --- batch --------------------------------------------------------------------------------------


def test_clearing_deletes_the_active_tasks_and_keeps_the_history(staged):
    """Scoped to completed==False on purpose: promotion history must survive a clear."""
    import database.staged_tasks as staged_db

    deleted = staged_db.clear_staged_tasks(staged['uid'])

    assert deleted == 3
    for task_id in staged['active']:
        assert _doc(staged, task_id) is None
    for task_id in staged['done']:
        assert _doc(staged, task_id) is not None, 'completed tasks are the history, and must remain'


def test_clearing_a_user_with_nothing_active_is_a_no_op(staged):
    """An empty batch must not be committed as something. Both backends must return 0 rather than raise
    on a commit with no writes."""
    import database.staged_tasks as staged_db

    staged_db.clear_staged_tasks(staged['uid'])

    assert staged_db.clear_staged_tasks(staged['uid']) == 0


def test_a_clear_larger_than_one_batch_deletes_everything(bind_store):
    """More documents than BATCH_LIMIT, so the module rolls over into a second batch.

    What this can prove is completeness and the returned count. It CANNOT prove the chunking itself:
    neither the emulator nor Mongo enforces Firestore's 500-writes-per-commit limit, so a build that
    never rolled over would still pass here — verified by mutation. The rollover is guarded by the unit
    suite; this holds the property a user would notice.
    """
    import database.staged_tasks as staged_db

    run = uuid.uuid4().hex[:8]
    uid = f'st-bulk-{run}'
    total = staged_db.BATCH_LIMIT + 25
    for index in range(total):
        bind_store.set(
            f'users/{uid}/staged_tasks/b{index}-{run}',
            {'id': f'b{index}-{run}', 'description': f't{index}', 'completed': False, 'created_at': NOW},
        )

    try:
        assert staged_db.clear_staged_tasks(uid) == total
        assert list(bind_store.query(f'users/{uid}/staged_tasks')) == []
    finally:
        for index in range(total):
            bind_store.delete(f'users/{uid}/staged_tasks/b{index}-{run}')


# --- cursor over a document-name keyset -----------------------------------------------------------


@pytest.fixture
def legacy(bind_store):
    """Four rows the retired desktop migration moved, ordered by document id."""
    run = uuid.uuid4().hex[:8]
    uid = f'st-legacy-{run}'
    ids = [f'm{i}-{run}' for i in range(4)]
    for task_id in ids:
        bind_store.set(
            f'users/{uid}/staged_tasks/{task_id}',
            {
                'id': task_id,
                'description': f'legacy {task_id}',
                'completed': False,
                'source': 'conversation_migration',
                'created_at': NOW,
            },
        )

    yield {'uid': uid, 'ids': sorted(ids), 'store': bind_store}

    for task_id in ids:
        bind_store.delete(f'users/{uid}/staged_tasks/{task_id}')
        bind_store.delete(f'users/{uid}/action_items/{task_id}')


def test_the_recovery_pages_by_document_name(legacy):
    """Two pages of two restore all four."""
    import database.staged_tasks as staged_db

    first = staged_db.restore_legacy_conversation_items(legacy['uid'], limit=2)

    assert first['restored'] == 2
    assert first['next_cursor'], 'a bounded page must say where to resume'

    second = staged_db.restore_legacy_conversation_items(legacy['uid'], limit=2, cursor=first['next_cursor'])

    assert second['restored'] == 2
    for task_id in legacy['ids']:
        stored = legacy['store'].get(f"users/{legacy['uid']}/action_items/{task_id}")
        assert stored is not None and stored.exists, f'{task_id} was never restored'


def test_a_row_that_cannot_be_restored_does_not_starve_the_rest(legacy):
    """What the cursor is actually FOR, and the only way to observe it.

    A restored row is deleted as it moves, so re-reading from the top would still make progress — the
    cursor looks decorative until a row cannot be consumed. It happens for real: when an action item
    with that id already exists the batch raises AlreadyExists and the staged row is deliberately KEPT
    ("preserves both copies for the next recovery pass"). Without `start_after`, every page would begin
    at that same stuck row and the rest would never be reached.

    Here the FIRST row by document id is pre-collided, then the sweep is paged one at a time.
    """
    import database.staged_tasks as staged_db

    blocked = legacy['ids'][0]
    legacy['store'].set(f"users/{legacy['uid']}/action_items/{blocked}", {'id': blocked, 'description': 'mine'})

    first = staged_db.restore_legacy_conversation_items(legacy['uid'], limit=1)

    assert first['restored'] == 0, 'the collided row cannot be restored'
    assert first['skipped_existing'] == 1
    assert first['next_cursor'] == blocked, 'and the cursor must point PAST it'

    second = staged_db.restore_legacy_conversation_items(legacy['uid'], limit=1, cursor=first['next_cursor'])

    assert second['restored'] == 1, 'the next page must move on instead of retrying the stuck row'
    stored = legacy['store'].get(f"users/{legacy['uid']}/action_items/{legacy['ids'][1]}")
    assert stored is not None and stored.exists
    assert legacy['store'].get(f"users/{legacy['uid']}/staged_tasks/{blocked}").exists, 'the blocked row stays'


def test_the_recovery_ignores_rows_it_did_not_move(legacy):
    """Only `source == 'conversation_migration'` qualifies. A backend that dropped the filter would
    resurrect ordinary staged tasks as action items."""
    import database.staged_tasks as staged_db

    other = f"other-{legacy['uid']}"
    legacy['store'].set(
        f"users/{legacy['uid']}/staged_tasks/{other}",
        {'id': other, 'description': 'not migrated', 'completed': False, 'source': 'screen', 'created_at': NOW},
    )
    try:
        result = staged_db.restore_legacy_conversation_items(legacy['uid'], limit=10)

        assert result['restored'] == 4, 'only the four migration rows'
        assert not legacy['store'].get(f"users/{legacy['uid']}/action_items/{other}").exists
    finally:
        legacy['store'].delete(f"users/{legacy['uid']}/staged_tasks/{other}")
        legacy['store'].delete(f"users/{legacy['uid']}/action_items/{other}")
