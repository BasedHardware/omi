"""A2b schema and typed-cell commit contracts, with disposable local Postgres."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Event
from pathlib import Path
import re
import subprocess
import sys
from uuid import uuid4

import pytest
import fakeredis
from pydantic import BaseModel

from database import action_item_versions, action_items_cache

from database.cells import store as cell_store_module
from database.cells.adapters import space_store
from database.cells.adapters._base import event_payloads
from database.cells.adapters.space_store import CellSpaceTx
from database.cells.store import CellTransaction
from database.cells.errors import BaseRevisionMismatch
from database.ports.base import MutationConflict, RevisionConflict
from database.jobstore.connection import configure, dial
from database.jobstore.migrate import load, migrate
from database.ports.action_items import ActionItemDraft
from database.ports.folders import FolderCreate
from database.ports.goals import GoalCreate, GoalUpdate
from database.ports.people import PersonDraft
from database.ports.workstreams import WorkstreamCreate, WorkstreamUpdate
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
    assert [m.version for m in migrations] == [1, 2, 3, 4]
    assert migrations[1].name == 'write_fence'
    assert migrations[2].name == 'revision_timestamps'
    assert migrations[3].name == 'task_workflow_typed'
    sql = migrations[3].sql
    assert 'depends on B2 0002_write_fence.sql' in sql
    assert 'GENERATED ALWAYS AS' in sql
    assert len(re.findall(r'ALTER\s+TABLE\s+cell_docs', sql, re.IGNORECASE)) == 1
    assert len(re.findall(r'ADD\s+COLUMN', sql, re.IGNORECASE)) == 10
    assert 'ACCESS EXCLUSIVE' in sql
    assert migrations[3].checksum == '6fa2c33f3b437a22030994d346bd401f8148f2bbcb8758d11f4e3b168e012493'
    for migration in migrations[1:]:
        # Inspect statements, not the descriptive comments or string literals.
        statements = re.sub(r"--[^\n]*|'(?:''|[^'])*'", '', migration.sql)
        assert not re.search(r'\b(DROP|RENAME)\b', statements, re.IGNORECASE)
        for statement in statements.split(';'):
            if re.match(r'\s*ALTER\b', statement, re.IGNORECASE):
                assert re.match(r'\s*ALTER\s+TABLE\s+\w+\s+ADD\s+COLUMN\b', statement, re.IGNORECASE)


def test_fresh_apply_reapply_and_codec_query_columns(pg):
    schema = 'a2b_' + uuid4().hex
    with configure(dial(cells_dsn())) as conn:
        conn.execute(f'CREATE SCHEMA {schema}')
        try:
            conn.execute(f'SET search_path TO {schema}, public')
            assert migrate(conn, MIGRATIONS) == [1, 2, 3, 4]
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


def test_timestamp_decoder_excludes_parallel_workers(pg):
    with configure(dial(cells_dsn())) as conn:
        setting = conn.execute(
            "SELECT name FROM pg_settings WHERE name IN ('debug_parallel_query', 'force_parallel_mode')"
        ).fetchone()[0]
        conn.execute(f'SET {setting}=on')
        query = (
            "SELECT cell_query_timestamp(jsonb_build_object("
            "'$datetime', '2026-11-07T00:00:00+00:00', 'input', g)) FROM generate_series(1, 2) g"
        )
        # A PARALLEL SAFE declaration produces a Gather and fails in its worker:
        # the decoder's EXCEPTION block needs a subtransaction even for valid input.
        plan = conn.execute('EXPLAIN ' + query).fetchall()
        assert not any('Gather' in row[0] for row in plan)
        rows = conn.execute(query).fetchall()
        assert rows == [(datetime(2026, 11, 7, tzinfo=timezone.utc),)] * 2


@pytest.mark.parametrize('offset', ['+99:99', '+24:00', '-99:99', '-24:00'])
@pytest.mark.parametrize('tagged', [False, True])
def test_timestamp_decoder_invalid_offsets_yield_null(pg, offset, tagged):
    sid = pg.space('invalid-offset')
    pg.store(sid)
    value = f'"2026-11-01T00:00:00{offset}"'
    if tagged:
        value = '{"$datetime":' + value + '}'
    with configure(dial(cells_dsn())) as conn:
        assert conn.execute('SELECT cell_query_timestamp(%s::jsonb)', (value,)).fetchone()[0] is None
        # Exercise the STORED columns too: malformed legacy rows must be writable.
        conn.execute(
            "INSERT INTO cell_docs (space_id, entity, entity_id, doc, rev, author_id, updated_at) "
            "VALUES (%s, 'action_items', 'legacy', jsonb_build_object('due_at', %s::jsonb), 1, %s, 0)",
            (sid, value, sid),
        )
        assert conn.execute('SELECT q_due_at FROM cell_docs WHERE space_id=%s', (sid,)).fetchone()[0] is None


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


def test_folder_keyset_preserves_legacy_scalar_order(pg):
    sid = pg.space('scalar-order')
    for key, value in [
        ('null', None),
        ('false', False),
        ('true', True),
        ('zero', 0),
        ('number', 3),
        ('date', datetime(2026, 1, 1, tzinfo=timezone.utc)),
        ('text', 'a'),
    ]:
        pg.seed(sid, 'folders', key, {'name': key, 'order': value})
    repo = pg.folders(sid)
    expected = ['null', 'false', 'true', 'zero', 'number', 'date', 'text']
    assert [row.id for row in repo.list().items] == expected
    ids, cursor = [], None
    while True:
        page = repo.list(limit=2, cursor=cursor)
        ids.extend(row.id for row in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break
    assert ids == expected


@pytest.mark.parametrize('values', [[['a'], ['b']], [{'a': 0}, {'b': 0}], [{'b': 0}, {'aa': 0, 'z': 0}]])
@pytest.mark.parametrize('limit', [1, 2])
@pytest.mark.parametrize('pending', [False, True])
def test_folder_keyset_preserves_legacy_json_order(pg, values, limit, pending):
    sid = pg.space('json-order')
    # Equal order values also exercise the document-key tiebreak at a boundary.
    rows = [(key, {'name': key, 'order': values[i]}) for i in range(2) for key in (f'{i}-a', f'{i}-z')]
    store = pg.store(sid)
    if not pending:
        for key, row in rows:
            pg.seed(sid, 'folders', key, row)

    def body(tx):
        if pending:
            for key, row in rows:
                tx.state['folders'][key] = row
        repo = tx.folders
        expected = [key for key, _ in rows]
        assert [row.id for row in repo.list().items] == expected
        ids, cursor = [], None
        for _ in rows:
            page = repo.list(limit=limit, cursor=cursor)
            ids.extend(row.id for row in page.items)
            cursor = page.next_cursor
            if cursor is None:
                break
        assert cursor is None
        assert ids == expected

    store.run(body)


@pytest.mark.parametrize(
    'domain, index', [('action_items', 'cell_docs_ai_list'), ('folders', 'cell_docs_folder_order')]
)
def test_list_order_is_supplied_by_its_index(pg, monkeypatch, domain, index):
    store = pg.store(pg.space('list-index'))
    plans = []
    query = CellSpaceTx.query

    def explain(tx, entity, *args, **kwargs):
        if entity == domain:
            # With sequential/bitmap scans disabled, a mismatched index still
            # requires Sort. Explain the actual adapter SQL, including filters.
            execute = tx.raw.conn.execute

            def record(sql, params):
                plans.extend(row[0] for row in execute('EXPLAIN ' + sql, params).fetchall())
                return execute(sql, params)

            with monkeypatch.context() as patch:
                patch.setattr(tx.raw.conn, 'execute', record)
                return query(tx, entity, *args, **kwargs)
        return query(tx, entity, *args, **kwargs)

    monkeypatch.setattr(CellSpaceTx, 'query', explain)

    def body(tx):
        tx.raw.conn.execute('SET LOCAL enable_seqscan=off')
        tx.raw.conn.execute('SET LOCAL enable_bitmapscan=off')
        getattr(tx, domain).list(limit=2)

    store.run(body)
    assert any(index in line for line in plans), plans
    assert not any('Sort' in line for line in plans), plans


def test_reserved_task_create_records_noop_mutation_without_cache_bump(pg, monkeypatch):
    sid = pg.space('reserved-receipt')
    repo = pg.action_items(sid)
    repo.create(ActionItemDraft(data={'description': 'Original'}), document_id='reserved')
    bumps = []
    monkeypatch.setattr(space_store, 'bump_action_items_list_version', bumps.append)
    draft = ActionItemDraft(data={'description': 'Retry'})
    assert repo.create(draft, document_id='reserved', mutation_id='occupied') == 'reserved'
    assert repo.create(draft, document_id='reserved', mutation_id='occupied') == 'reserved'
    with pytest.raises(MutationConflict):
        repo.create(ActionItemDraft(data={'description': 'Changed'}), document_id='reserved', mutation_id='occupied')
    assert repo.get('reserved').description == 'Original'
    assert bumps == []


def test_scalar_type_updates_are_not_lost_to_python_equality(pg):
    repo = pg.action_items(pg.space('scalar-types'))
    tid = repo.create(ActionItemDraft(data={'description': 'Typed', 'extension': 1}))
    for value in (True, 1, 1.0):
        assert repo.update(tid, {'extension': value})
        saved = repo.get(tid).model_extra['extension']
        assert type(saved) is type(value) and saved == value


def test_related_domain_task_patches_pass_the_codec(pg, monkeypatch):
    sid = pg.space('link-codec')
    goal = pg.goals(sid).create(GoalCreate(data={'title': 'Goal'}))
    tid = pg.action_items(sid).create(ActionItemDraft(data={'description': 'Linked', 'goal_id': goal.id}))
    before = pg.action_items(sid).get(tid).updated_at
    calls = []
    original = space_store.prepare_action_item_for_write

    def prepare(data, *, partial=False):
        calls.append((data.copy(), partial))
        return original(data, partial=partial)

    monkeypatch.setattr(space_store, 'prepare_action_item_for_write', prepare)
    pg.goals(sid).transition_lifecycle(
        goal.id, status='abandoned', relationship_disposition='detach', idempotency_key='detach', account_generation=0
    )
    assert any(partial and data.get('goal_id', 'missing') is None for data, partial in calls)
    saved = pg.action_items(sid).get(tid)
    assert saved.goal_id is None and saved.updated_at > before
    assert pg.goals(sid).get(goal.id).model_extra['ended_at'] is not None


def test_cell_package_defers_domain_composition_until_requested():
    script = """
import sys
from database.jobstore.connection import Pool

def forbidden_pool(*args, **kwargs):
    raise AssertionError('import constructed a pool')

Pool.__init__ = forbidden_pool
import database.cells
assert 'database.cells.adapters.space_store' not in sys.modules
from database.cells.adapters import CellSpaceStore
assert CellSpaceStore.__module__ == 'database.cells.adapters.space_store'
"""
    subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[2], check=True, timeout=120)


def test_legacy_workstream_cell_views_project_key_without_rewriting_payload(pg):
    sid = pg.space('legacy-workstream-views')
    pg.seed(
        sid,
        'workstreams',
        'ws-key',
        {
            'workstream_id': 'ws-key',
            'title': 'Legacy',
            'objective': 'Finish',
            'status': 'open',
            'goal_id': 'goal-key',
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc),
        },
    )
    repo = pg.workstreams(sid)
    assert repo.get('ws-key').id == 'ws-key'
    assert repo.list_open()[0].id == 'ws-key'
    assert repo.list_for_goal('goal-key')[0].id == 'ws-key'
    assert (
        repo.update(
            'ws-key',
            WorkstreamUpdate(data={'title': 'Changed'}),
            idempotency_key='change',
            account_generation=0,
        ).id
        == 'ws-key'
    )
    assert 'id' not in pg.read(sid, 'workstreams', 'ws-key')


@pytest.mark.parametrize('buffered_only', [False, True])
@pytest.mark.parametrize('existing', [False, True])
def test_raw_and_typed_writers_lock_rows_before_head(pg, monkeypatch, buffered_only, existing):
    sid = pg.space('shared-lock-order')
    store = pg.store(sid)
    if existing:
        pg.seed(sid, 'folders', 'shared', {'name': 'Shared', 'counter': 0})
    raw_locked, typed_reading = Event(), Event()
    # Deliberately instrument the actual row-lock boundary, including flush.
    original = CellTransaction._lock_read  # pyright: ignore[reportPrivateUsage]
    pids = {}
    # No retry may hide a deadlock or lock timeout. Both real connections have
    # a bounded PostgreSQL wait, in addition to bounded Python coordination.
    monkeypatch.setattr(cell_store_module, 'MAX_SERIALIZATION_RETRIES', 1)
    monkeypatch.setattr(cell_store_module, 'LOCK_TIMEOUT', '1s')

    def lock_read(tx, entity, entity_id):
        address = (entity, entity_id)
        first = address not in tx.cache
        raw = tx.actor_uid == 'raw-writer'
        if first and not raw:
            pids['typed'] = tx.conn.info.backend_pid
            typed_reading.set()
        result = original(tx, entity, entity_id)
        if first and raw:
            pids['raw'] = tx.conn.info.backend_pid
            raw_locked.set()
            assert typed_reading.wait(timeout=5), 'typed writer could not reach its row read'
        return result

    monkeypatch.setattr(CellTransaction, '_lock_read', lock_read)

    def raw_body(tx):
        if not buffered_only:
            tx.get('folders', 'shared')
        tx.put('folders', 'shared', {'name': 'Shared', 'counter': 1})

    def typed_body(tx):
        row = tx.state['folders']['shared']
        row['counter'] += 1

    with ThreadPoolExecutor(max_workers=2) as executor:
        raw = executor.submit(store.cell.run, sid, raw_body, actor_uid='raw-writer', now=0)
        try:
            assert raw_locked.wait(timeout=5)
            typed = executor.submit(store.run, typed_body)
            raw.result(timeout=10)
            typed.result(timeout=10)
        finally:
            # Also release the raw body if launching/asserting the peer failed.
            typed_reading.set()
    assert pids['raw'] != pids['typed']
    assert store.cell.read_doc(sid, 'folders', 'shared')['counter'] == 2
    assert store.cell.head(sid) == (3 if existing else 2, 1)


@pytest.mark.parametrize(
    'sequence, accepted',
    [
        (-9223372036854775809, False),
        (-1e25, False),
        (-9223372036854775808, True),
        (9223372036854775807, True),
        (9223372036854775808, False),
        (1e25, False),
        ('-9223372036854775809', True),
        ('9223372036854775808', True),
    ],
)
def test_event_decoder_signed_bigint_bounds_after_jsonb(pg, sequence, accepted):
    class EventPayload(BaseModel):
        sequence: int

    # JSONB loses the float type of integral doubles on both sides of bigint.
    # Use a model without ge=1 to isolate the decoder's numeric storage guard.
    from database.jobstore.codec import dumps

    with pg._pool.connection() as conn:
        row = conn.execute('SELECT %s::jsonb', (dumps({'sequence': sequence}),)).fetchone()[0]
    if isinstance(sequence, float):
        assert type(row['sequence']) is int
    expected = [{'sequence': int(sequence)}] if accepted else []
    assert list(event_payloads(EventPayload, [('event', row)])) == expected


@pytest.mark.parametrize('case,generation', [(0, 'legacy'), (1, True), (2, '1'), (3, None)])
def test_wrong_typed_workstream_generation_is_a_nonmatch(pg, case, generation):
    sid = pg.space(f'legacy-generation-{case}')
    now = datetime.now(timezone.utc)
    base = {'title': 'Legacy', 'objective': 'Finish', 'status': 'open', 'created_at': now, 'updated_at': now}
    pg.seed(sid, 'workstreams', 'ws-bad', {**base, 'workstream_id': 'ws-bad', 'account_generation': generation})
    pg.seed(sid, 'workstreams', 'ws-one', {**base, 'workstream_id': 'ws-one', 'account_generation': 1})
    pg.seed(sid, 'workstreams', 'ws-missing', {**base, 'workstream_id': 'ws-missing'})
    repo = pg.workstreams(sid)
    assert [row.id for row in repo.list_open(account_generation=1)] == ['ws-one']
    assert [row.id for row in repo.list_open(account_generation=0)] == ['ws-missing']


@pytest.mark.parametrize('case,generation', [(0, True), (1, '1'), (2, None)])
def test_wrong_typed_workstream_generation_refuses_mutation(pg, case, generation):
    from database.ports.workstreams import WorkstreamGenerationMismatchError

    sid = pg.space(f'legacy-generation-guard-{case}')
    now = datetime.now(timezone.utc)
    row = {'workstream_id': 'ws-bad', 'title': 'Legacy', 'objective': 'Finish', 'status': 'open'}
    pg.seed(
        sid, 'workstreams', 'ws-bad', {**row, 'created_at': now, 'updated_at': now, 'account_generation': generation}
    )
    repo = pg.workstreams(sid)
    with pytest.raises(WorkstreamGenerationMismatchError):
        repo.update('ws-bad', WorkstreamUpdate(data={'title': 'Changed'}), idempotency_key='g', account_generation=1)


@pytest.mark.parametrize('case,generation', [(0, False), (1, 'legacy'), (2, 0.5)])
def test_wrong_typed_generation_refuses_task_goal_links(pg, case, generation):
    # Python treats False as 0, so equality alone would let a boolean
    # generation pass the generation-0 link guards.
    from database.ports.action_items import TaskRelationshipConflictError
    from database.ports.workstreams import WorkstreamGenerationMismatchError

    sid = pg.space(f'legacy-generation-links-{case}')
    now = datetime.now(timezone.utc)
    goal = {'title': 'Goal', 'desired_outcome': 'Done', 'created_at': now, 'updated_at': now}
    task = {'description': 'Task', 'completed': False, 'created_at': now, 'updated_at': now}
    pg.seed(sid, 'goals', 'g-bad', {**goal, 'account_generation': generation})
    pg.seed(sid, 'goals', 'g-ok', goal)
    pg.seed(sid, 'action_items', 't-bad', {**task, 'account_generation': generation})
    pg.seed(sid, 'action_items', 't-ok', task)
    repo = pg.workstreams(sid)
    with pytest.raises(WorkstreamGenerationMismatchError):
        repo.resolve_work_intent({'origin': 'task', 'task_id': 't-bad'}, idempotency_key='i1', account_generation=0)
    with pytest.raises(TaskRelationshipConflictError):
        repo.resolve_work_intent(
            {'origin': 'goal', 'goal_id': 'g-bad', 'anchor_task_description': 'A'},
            idempotency_key='i2',
            account_generation=0,
        )
    result = repo.import_task_goal_links(
        {'links': [{'task_id': 't-ok', 'goal_id': 'g-bad'}, {'task_id': 't-bad', 'goal_id': 'g-ok'}]},
        idempotency_key='i3',
        account_generation=0,
    )
    assert result['failed'] == 2 and sorted(result['failure_task_ids']) == ['t-bad', 't-ok']


def test_numeric_legacy_idempotency_key_does_not_match_string_request(pg):
    sid = pg.space('legacy-numeric-idempotency')
    now = datetime.now(timezone.utc)
    pg.seed(
        sid,
        'action_items',
        't-legacy',
        {'description': 'Legacy', 'completed': False, 'idempotency_key': 123, 'created_at': now, 'updated_at': now},
    )
    created = pg.action_items(sid).create(ActionItemDraft(data={'description': 'New'}), idempotency_key='123')
    assert created != 't-legacy'
    assert pg.action_items(sid).create(ActionItemDraft(data={'description': 'Again'}), idempotency_key='123') == created


def test_pending_overlay_keeps_numeric_idempotency_key_typed(pg):
    # A same-UoW edit routes the legacy row through the overlay, which must
    # project keys exactly as migration 0004's generated columns do.
    sid = pg.space('legacy-numeric-idempotency-overlay')
    now = datetime.now(timezone.utc)
    pg.seed(
        sid,
        'action_items',
        't-legacy',
        {'description': 'Legacy', 'completed': False, 'idempotency_key': 123, 'created_at': now, 'updated_at': now},
    )

    def body(tx):
        tx.action_items.update('t-legacy', {'description': 'Edited'})
        return tx.action_items.create(ActionItemDraft(data={'description': 'New'}), idempotency_key='123')

    assert pg.store(sid).run(body) != 't-legacy'


def test_folder_order_index_rebuilds_under_restricted_search_path(pg):
    # PostgreSQL 17 runs index builds with search_path = pg_catalog, pg_temp;
    # the order key must still resolve the timestamp decoder.
    with dial(cells_dsn()) as conn:
        conn.execute('SET search_path = pg_catalog, pg_temp')
        conn.execute('REINDEX INDEX public.cell_docs_folder_order')


def test_multi_row_bodies_lock_rows_in_flush_order(pg, monkeypatch):
    # Caller order b, a must still lock a before b, matching flush's sorted
    # raw-write locks, so the two paths cannot deadlock each other.
    sid = pg.space('lock-order')
    now = datetime.now(timezone.utc)
    for entity_id in ('a', 'b'):
        pg.seed(sid, 'action_items', entity_id, {'description': entity_id, 'created_at': now, 'updated_at': now})
    seen = []
    original = CellTransaction.get

    def record(self, entity, entity_id, *args, **kwargs):
        if entity == 'action_items':
            seen.append(entity_id)
        return original(self, entity, entity_id, *args, **kwargs)

    monkeypatch.setattr(CellTransaction, 'get', record)
    store = pg.store(sid)
    store.run(lambda tx: tx.action_items.get_by_ids(['b', 'a']))
    store.run(lambda tx: tx.action_items.delete_batch(['b', 'a']))
    assert seen[:2] == ['a', 'b'] and seen[2:4] == ['a', 'b']


@pytest.mark.parametrize('backend', ['postgres', 'sim'])
def test_goal_update_replays_saved_none_after_goal_appears(pg, backend):
    # A missing-goal update saves a None result; retrying the same mutation id
    # after the goal exists must replay None, not apply the old patch.
    harness = pg if backend == 'postgres' else build_backend('sim')
    store = harness.store(harness.space('none-receipt'))
    patch = GoalUpdate(data={'title': 'Patched'})
    assert store.run(lambda tx: tx.goals.update('goal_late', patch, mutation_id='late-update')) is None
    store.run(lambda tx: tx.goals.create(GoalCreate(data={'goal_id': 'goal_late', 'title': 'Original'})))
    assert store.run(lambda tx: tx.goals.update('goal_late', patch, mutation_id='late-update')) is None
    assert store.run(lambda tx: tx.goals.get('goal_late')).title == 'Original'
    if harness is not pg:
        harness.close()


@pytest.mark.parametrize('backend', ['postgres', 'sim'])
@pytest.mark.parametrize('field', ['id', 'goal_id', 'account_generation'])
def test_goal_update_rejects_identity_and_generation_fields(pg, backend, field):
    harness = pg if backend == 'postgres' else build_backend('sim')
    try:
        store = harness.store(harness.space('goal-identity'))
        store.run(lambda tx: tx.goals.create(GoalCreate(data={'goal_id': 'goal_fixed', 'title': 'Original'})))
        with pytest.raises(ValueError, match=field):
            store.run(lambda tx: tx.goals.update('goal_fixed', GoalUpdate(data={field: 'other', 'title': 'X'})))
        goal = store.run(lambda tx: tx.goals.get('goal_fixed'))
        assert goal.title == 'Original' and goal.goal_id == 'goal_fixed'
    finally:
        if harness is not pg:
            harness.close()


@pytest.mark.parametrize('backend', ['postgres', 'sim'])
def test_person_create_replay_survives_deleted_person(pg, backend):
    # Firestore replays a receipt whose person is gone as {'id': receipt id}.
    harness = pg if backend == 'postgres' else build_backend('sim')
    try:
        store = harness.store(harness.space('person-replay'))
        draft = PersonDraft(id='person_gone', name='Gone')
        created = store.run(lambda tx: tx.people.get_or_create_by_name(draft, mutation_id='person-once'))

        def delete(tx):
            del tx.people.store.state['people'][created.id]

        store.run(delete)
        replay = store.run(lambda tx: tx.people.get_or_create_by_name(draft, mutation_id='person-once'))
        assert replay.id == 'person_gone'
    finally:
        if harness is not pg:
            harness.close()


def test_cross_domain_bodies_lock_in_flush_order(pg, monkeypatch):
    # Goal detach, folder delete and folder moves touch several collections;
    # each must take first locks in flush's sorted (entity, id) order.
    sid = pg.space('cross-lock')
    now = datetime.now(timezone.utc)
    pg.seed(sid, 'action_items', 't1', {'description': 't1', 'goal_id': 'g1', 'created_at': now, 'updated_at': now})
    pg.seed(sid, 'workstreams', 'w1', {'title': 'w1', 'objective': 'w1', 'goal_id': 'g1', 'updated_at': now})
    for cid in ('c1', 'c2'):
        pg.seed(sid, 'conversations', cid, {'folder_id': 'f1', 'discarded': False})
    for fid in ('f1', 'f2'):
        pg.seed(sid, 'folders', fid, {'name': fid, 'order': 0, 'conversation_count': 0})
    store = pg.store(sid)
    generation = store.run(lambda tx: tx.goals._generation())
    store.run(lambda tx: tx.goals.create(GoalCreate(data={'goal_id': 'g1', 'title': 'g1'})))
    seen = []
    original = CellTransaction.get

    def record(self, entity, entity_id, *args, **kwargs):
        seen.append((entity, entity_id))
        return original(self, entity, entity_id, *args, **kwargs)

    def first_locks():
        first = list(
            dict.fromkeys(
                a for a in seen if a[0] in ('action_items', 'goals', 'workstreams', 'conversations', 'folders')
            )
        )
        seen.clear()
        return first

    monkeypatch.setattr(CellTransaction, 'get', record)
    store.run(
        lambda tx: tx.goals.transition_lifecycle(
            'g1', status='paused', relationship_disposition='detach', idempotency_key='k', account_generation=generation
        )
    )
    order = first_locks()
    assert order == sorted(order) and ('action_items', 't1') in order
    store.run(lambda tx: tx.folders.bulk_move_conversations(['c2', 'c1'], 'f2'))
    order = first_locks()
    assert order == sorted(order) and ('conversations', 'c1') in order
    store.run(lambda tx: tx.folders.reorder(['f2', 'f1']))
    order = first_locks()
    assert order == sorted(order) and ('folders', 'f1') in order
    store.run(lambda tx: tx.goals.create(GoalCreate(data={'goal_id': 'g0', 'title': 'g0'})))
    seen.clear()
    store.run(lambda tx: tx.goals.focus('g1', idempotency_key='f', account_generation=generation))
    order = first_locks()
    assert order == sorted(order) and ('goals', 'g0') in order
    store.run(lambda tx: tx.folders.delete('f2', move_to_folder_id='f1'))
    order = first_locks()
    assert order == sorted(order) and ('conversations', 'c1') in order


def test_inverted_lock_order_deadlock_is_detected_and_retried(pg):
    # Data-dependent bodies cannot always lock in flush order. Correctness rests
    # on PostgreSQL deadlock detection plus the store's bounded body retry:
    # force two bodies to lock a/b in opposite orders; both must commit.
    sid = pg.space('deadlock-retry')
    for entity_id in ('a', 'b'):
        pg.seed(sid, 'folders', entity_id, {'name': entity_id, 'counter': 0})
    store = pg.store(sid)
    first_locked = {'ab': Event(), 'ba': Event()}
    attempts = {'ab': 0, 'ba': 0}

    def body(order):
        def run(tx):
            attempts[order] += 1
            tx.get('folders', order[0])
            if attempts[order] == 1:
                first_locked[order].set()
                other = 'ba' if order == 'ab' else 'ab'
                assert first_locked[other].wait(timeout=5)
            for entity_id in order:
                doc = tx.get('folders', entity_id)
                tx.put('folders', entity_id, {**doc, 'counter': doc['counter'] + 1})

        return run

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(store.cell.run, sid, body(order), actor_uid=f'raw-{order}', now=0) for order in ('ab', 'ba')
        ]
        for future in futures:
            future.result(timeout=30)
    assert attempts['ab'] + attempts['ba'] >= 3
    for entity_id in ('a', 'b'):
        assert store.cell.read_doc(sid, 'folders', entity_id)['counter'] == 2
