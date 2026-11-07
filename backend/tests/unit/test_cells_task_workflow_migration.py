"""A2b schema and typed-cell commit contracts, with disposable local Postgres."""

from datetime import timezone
from pathlib import Path
from uuid import uuid4

import pytest
import fakeredis

from database import action_item_versions, action_items_cache

from database.cells.adapters import space_store
from database.cells.adapters.space_store import CellSpaceTx
from database.cells.store import CellTransaction
from database.cells.errors import BaseRevisionMismatch
from database.ports.base import RevisionConflict
from database.jobstore.connection import configure, dial
from database.jobstore.migrate import load, migrate
from database.ports.action_items import ActionItemDraft
from database.ports.folders import FolderCreate
from database.ports.goals import GoalCreate
from database.ports.workstreams import WorkstreamCreate
from testing.cells_fixtures import cells_dsn
from testing.domain_fixtures import build_backend
from testing.store_fixtures import BackendUnavailable, required_backends

MIGRATIONS = Path(__file__).resolve().parents[2] / 'database/cells/migrations'


@pytest.fixture
def pg(monkeypatch):
    redis = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(action_item_versions, '_redis', lambda: redis)
    monkeypatch.setattr(action_items_cache, '_redis', lambda: redis)
    try:
        harness = build_backend('postgres')
    except BackendUnavailable as exc:
        if 'postgres' in required_backends():
            pytest.fail(str(exc))
        pytest.skip(str(exc))
    try:
        yield harness
    finally:
        harness.close()


def test_expand_only_numbering_and_b2_dependency():
    migrations = load(MIGRATIONS)
    assert [m.version for m in migrations] == [1, 2, 3]
    assert migrations[1].name == 'write_fence'
    assert migrations[2].name == 'task_workflow_typed'
    sql = migrations[2].sql
    assert 'depends on B2 0002_write_fence.sql' in sql
    assert 'GENERATED ALWAYS AS' in sql
    assert 'ACCESS EXCLUSIVE' in sql
    assert migrations[2].checksum == '2b3a8b455d4f27a3bc1835257003b25050f93632e23ecaa202f98aaf8fa520c8'


def test_fresh_apply_reapply_and_codec_query_columns(pg):
    schema = 'a2b_' + uuid4().hex
    with configure(dial(cells_dsn())) as conn:
        conn.execute(f'CREATE SCHEMA {schema}')
        try:
            conn.execute(f'SET search_path TO {schema}, public')
            assert migrate(conn, MIGRATIONS) == [1, 2, 3]
            assert migrate(conn, MIGRATIONS) == []
            timestamp = conn.execute(
                "SELECT cell_query_timestamp(%s::jsonb)", ('{"$datetime":"2026-11-01T07:00:00+07:00"}',)
            ).fetchone()[0]
            assert timestamp.astimezone(timezone.utc).isoformat() == '2026-11-01T00:00:00+00:00'
            for malformed in ['"yesterday"', '{"$datetime":"bad"}', '{"$datetime":"2026-99-01T00:00:00+00:00"}']:
                assert conn.execute('SELECT cell_query_timestamp(%s::jsonb)', (malformed,)).fetchone()[0] is None
        finally:
            conn.execute('SET search_path TO public')
            conn.execute(f'DROP SCHEMA {schema} CASCADE')


def test_one_bump_per_uow_and_no_bump_for_reads_or_replay(pg, monkeypatch):
    sid = pg.space('bumps')
    store = pg.store(sid)
    bumps, tickets = [], []
    monkeypatch.setattr(space_store, 'bump_action_items_list_version', bumps.append)
    monkeypatch.setattr(space_store.ActionItemCommitFence, 'before_commit', lambda self: tickets.append('begin'))
    monkeypatch.setattr(
        space_store.ActionItemCommitFence, 'after_commit', lambda self, ok: tickets.append(('finish', ok))
    )

    def body(tx):
        tx.action_items.create(ActionItemDraft(data={'description': 'First'}), mutation_id='one')
        tx.action_items.create(ActionItemDraft(data={'description': 'Second'}), mutation_id='two')

    store.run(body)
    assert bumps == [sid]
    assert tickets == ['begin', ('finish', True)]
    store.run(body)
    store.run(lambda tx: tx.action_items.read_control())
    assert bumps == [sid]
    with store.pool.connection() as conn:
        assert conn.execute('SELECT count(*) FROM mutation_receipts WHERE space_id=%s', (sid,)).fetchone()[0] == 2
        assert (
            conn.execute(
                "SELECT count(*) FROM change_log WHERE space_id=%s AND entity='action_items'", (sid,)
            ).fetchone()[0]
            == 2
        )


def test_fences_span_flush_failure_retry_and_commit(pg, monkeypatch):
    sid = pg.space('retry')
    store = pg.store(sid)
    events, bumps = [], []
    original = CellTransaction.flush
    attempts = 0

    class SerializationFailure(Exception):
        sqlstate = '40001'

    def flush(tx):
        nonlocal attempts
        events.append('flush')
        attempts += 1
        if attempts == 1:
            raise SerializationFailure()
        return original(tx)

    class Fence:
        def before_commit(self):
            events.append('begin')

        def after_commit(self, committed):
            events.append(('finish', committed))

    monkeypatch.setattr(CellTransaction, 'flush', flush)
    monkeypatch.setattr(space_store, 'bump_action_items_list_version', bumps.append)

    def body(tx):
        tx.register_commit_fence(Fence())
        return tx.action_items.create(ActionItemDraft(data={'description': 'retry'}), document_id='task')

    assert store.run(body) == 'task'
    assert events[:4] == ['begin', 'flush', 'begin', 'flush']
    assert sorted(v[1] for v in events if isinstance(v, tuple)) == [False, True]
    assert bumps == [sid]
    assert store.action_items.get('task') is not None


def test_limited_lists_never_enumerate_collections_and_read_pending_writes(pg, monkeypatch):
    sid = pg.space('limits')
    store = pg.store(sid)
    seen = []
    query = CellSpaceTx.query

    def record(tx, entity, *args, **kwargs):
        rows = query(tx, entity, *args, **kwargs)
        seen.append((entity, kwargs.get('limit'), len(rows)))
        return rows

    monkeypatch.setattr(CellSpaceTx, 'query', record)

    def body(tx):
        for i in range(12):
            tx.action_items.create(ActionItemDraft(data={'description': str(i)}), document_id=str(i))
            tx.goals.create(GoalCreate(data={'title': str(i)}))
            tx.workstreams.create(WorkstreamCreate(data={'title': str(i)}))
            tx.folders.create(FolderCreate(name=str(i)))
        seen.clear()
        assert len(tx.action_items.list(limit=2).items) == 2
        assert len(tx.folders.list(limit=2).items) == 2
        assert len(tx.goals.get_all(limit=2)) == 2
        assert len(tx.workstreams.list_open(limit=2)) == 2

    store.run(body)
    assert all(limit is not None and count <= limit for _, limit, count in seen)
    assert {entity for entity, _, _ in seen} == {'action_items', 'folders', 'goals', 'workstreams'}


def test_native_revision_conflict_preserves_address_and_finishes_ticket(pg, monkeypatch):
    sid = pg.space('native-conflict')
    store = pg.store(sid)
    store.action_items.create(ActionItemDraft(data={'description': 'Before'}), document_id='task')
    events, bumps = [], []
    monkeypatch.setattr(space_store.ActionItemCommitFence, 'before_commit', lambda self: events.append('begin'))
    monkeypatch.setattr(space_store.ActionItemCommitFence, 'after_commit', lambda self, ok: events.append(ok))
    monkeypatch.setattr(space_store, 'bump_action_items_list_version', bumps.append)
    original = CellTransaction.flush

    def failed_flush(tx):
        raise BaseRevisionMismatch(sid, 7)

    monkeypatch.setattr(CellTransaction, 'flush', failed_flush)
    with pytest.raises(RevisionConflict) as error:
        store.action_items.update('task', {'description': 'After'}, expected_revision=1)
    assert (error.value.space_id, error.value.entity, error.value.entity_id, error.value.current_revision) == (
        sid,
        'action_items',
        'task',
        7,
    )
    assert events == ['begin', False] and bumps == []
    monkeypatch.setattr(CellTransaction, 'flush', original)
    assert store.action_items.get('task').description == 'Before'
