"""WQ17 counts physical resolver reads in real invocation/executor scopes."""

import asyncio
from contextvars import copy_context
from unittest.mock import AsyncMock

import pytest

from database import sync_conversation_snapshot as snapshots
from database import sync_snapshot_resolve_cache as cache
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument
from utils.executors import db_executor, run_blocking

UID = 'wq17-owner'
SOURCE = ('users', UID, 'conversations', 'source')
MARKER = ('users', UID, 'deleted_conversations', 'source')


@pytest.fixture
def world(monkeypatch):
    monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)
    db = StrictFirestore({SOURCE: {'id': 'source', 'owner_uid': UID, 'transcript_segments': [{'text': 'Synthetic'}]}})
    reads = []
    original = StrictFirestoreDocument.get

    def get(reference, *args, **kwargs):
        reads.append(reference.path)
        return original(reference, *args, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    return db, reads


def enable(monkeypatch):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"sync_snapshot_resolve_cache":100}')


def resolve(db, uid=UID, conversation_id='source', max_hops=16):
    return snapshots.resolve_snapshot(uid, conversation_id, client_factory=lambda: db, max_hops=max_hops)


@pytest.fixture
def sync_routes():
    from routers import sync

    return sync


@pytest.mark.asyncio
@pytest.mark.parametrize('raw', [None, '{}', '{"sync_snapshot_resolve_cache":0}'])
async def test_off_preserves_read_order_results_and_fresh_deletion(world, monkeypatch, raw):
    db, reads = world
    if raw is not None:
        monkeypatch.setenv('FIRESTORE_READ_LEVERS', raw)

    @cache.sync_snapshot_resolve_job
    async def job():
        first = resolve(db)
        assert resolve(db).to_dict() == first.to_dict()
        assert reads == [MARKER, SOURCE] * 2
        db.rows[MARKER] = {}
        assert resolve(db) is None
        assert cache._memo.get().entries == {}

    await job()
    assert reads == [MARKER, SOURCE] * 2 + [MARKER]
    assert cache._memo.get() is None


@pytest.mark.asyncio
async def test_hit_across_real_executor_leaves_single_flight_and_detached_content(world, monkeypatch):
    db, reads = world
    enable(monkeypatch)

    @cache.sync_snapshot_resolve_job
    async def job():
        results = await asyncio.gather(*(run_blocking(db_executor, resolve, db) for _ in range(12)))
        assert all(result is results[0] for result in results)
        data = results[0].to_dict()
        data['transcript_segments'][0]['text'] = 'caller mutation'
        assert resolve(db).to_dict()['transcript_segments'][0]['text'] == 'Synthetic'

    await job()
    assert reads == [MARKER, SOURCE]
    assert cache._memo.get() is None


@pytest.mark.asyncio
async def test_new_invocations_and_calls_outside_job_reload(world, monkeypatch):
    db, reads = world
    enable(monkeypatch)

    @cache.sync_snapshot_resolve_job
    async def job():
        return resolve(db)

    assert await job() is not None
    db.rows[MARKER] = {}
    assert await job() is None
    db.rows.pop(MARKER)
    assert resolve(db) is not None
    assert resolve(db) is not None
    assert reads == [MARKER, SOURCE, MARKER, MARKER, SOURCE, MARKER, SOURCE]


@pytest.mark.asyncio
async def test_key_separates_owner_client_source_and_hop_budget(world, monkeypatch):
    db, reads = world
    enable(monkeypatch)
    db.rows[SOURCE].update(deleted=True, sync_merged_into='target')
    target = ('users', UID, 'conversations', 'target')
    db.rows[target] = {'id': 'target'}
    other = StrictFirestore({SOURCE: {'id': 'source'}})

    @cache.sync_snapshot_resolve_job
    async def job():
        assert resolve(db, max_hops=1) is None
        assert resolve(db).conversation_id == 'target'
        assert resolve(db, conversation_id='target').conversation_id == 'target'
        assert resolve(other).conversation_id == 'source'
        assert resolve(db, uid='other') is None
        count = len(reads)
        assert resolve(db, max_hops=1) is None  # Absence is memoized too.
        assert resolve(db).conversation_id == 'target'
        assert len(reads) == count

    await job()
    assert len(reads) == 12


@pytest.mark.asyncio
async def test_errors_retry_without_caching_partial_resolution(world, monkeypatch):
    db, reads = world
    enable(monkeypatch)
    original = StrictFirestoreDocument.get
    failed = []

    def fail_once(reference, *args, **kwargs):
        if reference.path == SOURCE and not failed:
            failed.append(True)
            raise RuntimeError('synthetic unavailable')
        return original(reference, *args, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', fail_once)

    @cache.sync_snapshot_resolve_job
    async def job():
        with pytest.raises(RuntimeError, match='synthetic unavailable'):
            resolve(db)
        assert resolve(db) is not None
        assert resolve(db) is not None

    await job()
    assert reads == [MARKER, MARKER, SOURCE]


@pytest.mark.asyncio
@pytest.mark.parametrize('exit_kind', ['success', 'error', 'cancel'])
async def test_scope_closes_in_copied_callback_context_on_every_exit(world, monkeypatch, exit_kind):
    db, reads = world
    enable(monkeypatch)
    contexts = []

    @cache.sync_snapshot_resolve_job
    async def job():
        assert resolve(db) is not None
        contexts.append(copy_context())
        if exit_kind == 'error':
            raise RuntimeError('synthetic failure')
        if exit_kind == 'cancel':
            raise asyncio.CancelledError()

    if exit_kind == 'success':
        await job()
    else:
        with pytest.raises(RuntimeError if exit_kind == 'error' else asyncio.CancelledError):
            await job()
    assert cache._memo.get() is None
    old_memo = contexts[0].get(cache._memo)
    assert old_memo.closed and old_memo.entries == {}
    db.rows[MARKER] = {}
    assert contexts[0].run(resolve, db) is None
    assert reads == [MARKER, SOURCE, MARKER]


@pytest.mark.asyncio
async def test_concurrent_and_nested_jobs_do_not_share_results(world, monkeypatch):
    db, reads = world
    enable(monkeypatch)

    @cache.sync_snapshot_resolve_job
    async def job(nested=False):
        result = resolve(db)
        await asyncio.sleep(0)
        if nested:
            assert await job() is not result
        assert resolve(db) is result
        return result

    first, second = await asyncio.gather(job(nested=True), job())
    assert first is not second
    assert reads == [MARKER, SOURCE] * 3


@pytest.mark.asyncio
async def test_capacity_bypasses_cache_without_changing_resolution(world, monkeypatch):
    db, reads = world
    enable(monkeypatch)
    monkeypatch.setattr(cache, 'MAX_ENTRIES', 1)

    @cache.sync_snapshot_resolve_job
    async def job():
        assert resolve(db) is not None
        for _ in range(2):
            assert resolve(db, conversation_id='missing') is None
        assert len(cache._memo.get().entries) == 1
        assert resolve(db) is not None

    await job()
    assert len(reads) == 6


@pytest.mark.asyncio
async def test_invalid_path_retains_lazy_client_behavior(monkeypatch):
    enable(monkeypatch)

    def unexpected():
        pytest.fail('invalid input initialized a client')

    @cache.sync_snapshot_resolve_job
    async def job():
        for source, hops in [('invalid/path', 16), ('', 16), ('source', 0)]:
            assert snapshots.resolve_snapshot(UID, source, client_factory=unexpected, max_hops=hops) is None

    await job()


@pytest.mark.asyncio
async def test_real_sync_job_route_scopes_reprocess_deliveries(world, monkeypatch, sync_routes):
    from database.sync_jobs import SyncLedgerFenceMode
    from starlette.requests import Request

    routes = sync_routes
    db, reads = world
    enable(monkeypatch)
    monkeypatch.setattr(routes.uid_sequencer, 'production_fence_mode', lambda: SyncLedgerFenceMode.LEGACY)
    monkeypatch.setattr(routes, 'warm_rollout_cohorts', AsyncMock())

    async def enrich(payload):
        first = await run_blocking(db_executor, resolve, db)
        assert await run_blocking(db_executor, resolve, db) is first
        return first

    monkeypatch.setattr(routes, 'enrichment_response', enrich)
    request = Request({'type': 'http'})
    monkeypatch.setattr(request, 'json', AsyncMock(return_value={'kind': 'sync_reprocess', 'uid': UID}))
    assert await routes.run_sync_job(request, task_retry_count=0) is not None
    assert reads == [MARKER, SOURCE]
    db.rows[MARKER] = {}
    assert await routes.run_sync_job(request, task_retry_count=1) is None
    assert reads == [MARKER, SOURCE, MARKER]
