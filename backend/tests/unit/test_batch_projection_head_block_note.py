"""The head-block stamp runs through ProjectionStore.run as a real transaction.

Regression: the Projector passed an undecorated callable to ``run``, whose
``run_transactional`` hands it a raw, unbegun transaction. Every stamp failed
with ``ValueError`` (prod: ~48/min on backend-integration, 2026-11-17), so
``projection_blocked_since`` never landed and the 24 h head bound never began.
"""

from types import SimpleNamespace

from database.batch_pipeline_projection import ProjectionStore
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.batch_pipeline import projection

KEY = ('batch_pipeline_dev_results', 'head')


def _store(state='pending', **row):
    client = StrictFirestore({KEY: {'projection_state': state, **row}}, require_begun=True)
    return client, ProjectionStore(SimpleNamespace(client=client, namespace='batch_pipeline_dev'))


def test_stamp_lands_once_per_episode_through_a_real_transaction():
    client, store = _store()
    assert store.note_head_blocked('head', 1000.0, 'SyncAssignmentConflict') is True
    row = client.rows[KEY]
    assert row[projection.PROJECTION_HEAD_BLOCKED_SINCE] == 1000.0
    assert row[projection.PROJECTION_HEAD_BLOCK_TYPE] == 'SyncAssignmentConflict'
    assert store.note_head_blocked('head', 2000.0, 'TimeoutError') is False
    assert row[projection.PROJECTION_HEAD_BLOCKED_SINCE] == 1000.0


def test_an_undecorated_callable_fails_as_the_sdk_does():
    """The pre-fix shape: ``run`` hands a plain callable an unbegun transaction."""
    import pytest

    client, store = _store()

    def plain(transaction):
        return store.ref('results', 'head').get(transaction=transaction).to_dict()

    with pytest.raises(ValueError, match='Transaction not in progress'):
        store.run(plain)


def test_stamp_never_touches_a_row_that_left_the_assignment_states():
    client, store = _store(state='completed')
    assert store.note_head_blocked('head', 1000.0, 'TimeoutError') is False
    assert projection.PROJECTION_HEAD_BLOCKED_SINCE not in client.rows[KEY]


def test_projector_stamp_reaches_the_store_and_starts_the_bound():
    client, store = _store()
    projector = projection.Projector(SimpleNamespace(), lambda *_: {}, projection_store=store, clock=lambda: 1000.0)
    projector._note_head_blocked('head', TimeoutError('synthetic'))
    entry = dict(client.rows[KEY])
    assert entry[projection.PROJECTION_HEAD_BLOCKED_SINCE] == 1000.0
    assert not projection.head_retry_bound_exceeded(entry, 1000.0 + projection.PROJECTION_HEAD_RETRY_SECONDS)
    assert projection.head_retry_bound_exceeded(entry, 1001.0 + projection.PROJECTION_HEAD_RETRY_SECONDS)


def test_projector_never_runs_store_transactions_itself():
    """Projector callables reach ProjectionStore.run undecorated by mistake;
    keep every projection transaction inside ProjectionStore, where each one
    is a @firestore.transactional method."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(projection))
    direct = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == 'run'
        and (
            (isinstance(node.func.value, ast.Attribute) and node.func.value.attr == 'store')
            or (isinstance(node.func.value, ast.Name) and node.func.value.id == 'store')
        )
    ]
    assert direct == [], f'store.run called from utils/batch_pipeline/projection.py lines {direct}'


def _live_target_chain(monkeypatch, fail_first_n):
    from tests.unit.test_batch_pipeline_owner_chain_projection import (
        BURST,
        ResultLog,
        SUCCESS_PAYLOAD,
        patch_conversation_assignment,
        projector_for,
    )
    from utils.sync.assignment_errors import SyncAssignmentConflictReason

    log = ResultLog()
    ids = [f'lt-{n}' for n in range(3)]
    for sid in ids:
        # ResultLog stamps capture_at from its clock (1, 2, 3) with a 1 s duration.
        log.commit(BURST, 'lt', sid, [sid], fresh_capture=False, outcome='success')
    patch_conversation_assignment(
        monkeypatch, SyncAssignmentConflictReason.LIVE_TARGET_NOT_PERSISTED, fail_first_n=fail_first_n
    )
    return log, ids, projector_for(log, lambda item, uri: dict(SUCCESS_PAYLOAD))


def test_old_backfill_head_awaiting_a_live_target_holds_on_the_age_gate(monkeypatch):
    """An awaiting-writer head captured over 6 h ago holds on first failure."""
    from tests.unit.test_batch_pipeline_owner_chain_projection import BURST
    from utils.batch_pipeline.projection_hold_policy import AWAITING_WRITER_AGE_SECONDS
    from utils.batch_pipeline.scheduler import owner_key

    log, ids, projector = _live_target_chain(monkeypatch, fail_first_n=1)
    projector.clock = lambda: 10 + AWAITING_WRITER_AGE_SECONDS
    projector.project_owner(BURST)
    assert log.results[ids[0]]['projection_state'] == 'quarantine_held'
    assert log.projection_watermark(owner_key(BURST)) == ids[-1]


def test_a_head_failing_transiently_is_stamped_then_held_after_the_bound(monkeypatch):
    """The path this PR repairs: a head failing on infrastructure waits, is stamped
    on its first failure, and the 24 h bound later holds it and frees the chain."""
    from tests.unit.test_batch_pipeline_owner_chain_projection import BURST
    from utils.batch_pipeline.projection import PROJECTION_HEAD_BLOCKED_SINCE, PROJECTION_HEAD_RETRY_SECONDS
    from utils.batch_pipeline.scheduler import owner_key

    import database.conversations as conversations

    log, ids, projector = _live_target_chain(monkeypatch, fail_first_n=0)
    # Infrastructure trouble, not an awaiting-writer conflict: the 6 h capture
    # age gate cannot decide it, so only the durable 24 h bound holds the head.
    assign, failures = conversations.assign_sync_conversation, {'left': 3}

    def flaky(*args, **kwargs):
        if failures['left']:
            failures['left'] -= 1
            raise TimeoutError('synthetic datastore timeout')
        return assign(*args, **kwargs)

    monkeypatch.setattr('database.conversations.assign_sync_conversation', flaky)
    now = {'t': 100.0}
    projector.clock = lambda: now['t']
    projector.project_owner(BURST)
    head = log.results[ids[0]]
    assert head['projection_state'] == 'pending'
    assert head[PROJECTION_HEAD_BLOCKED_SINCE] == 100.0
    assert log.projection_watermark(owner_key(BURST)) != ids[-1]
    now['t'] = 100.0 + PROJECTION_HEAD_RETRY_SECONDS - 1
    projector.project_owner(BURST)
    assert log.results[ids[0]]['projection_state'] == 'pending', 'the bound, not the age gate, decides'
    now['t'] = 100.0 + PROJECTION_HEAD_RETRY_SECONDS + 1
    projector.project_owner(BURST)
    assert log.results[ids[0]]['projection_state'] == 'quarantine_held'
    assert log.projection_watermark(owner_key(BURST)) == ids[-1]
