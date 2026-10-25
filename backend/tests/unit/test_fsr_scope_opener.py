"""Exercise the task-attempt opener with real historical scans and executor contexts."""

import asyncio
import copy
import json
from contextlib import nullcontext
from contextvars import copy_context
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from config.firestore_read_levers import lever_enabled
from database import memories
from routers import sync
from utils.executors import db_executor, run_blocking


class _Query:
    """One-document SDK boundary: count physical streams and documents read."""

    def __init__(self):
        self.reads = 0
        self.scans = 0
        self.row = {'content': 'before', 'updated_at': datetime(2026, 1, 1, tzinfo=timezone.utc)}

    def collection(self, name):
        return self

    def document(self, name):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, count):
        return self

    def stream(self, **kwargs):
        self.scans += 1
        self.reads += 1
        row = copy.deepcopy(self.row)
        return iter([SimpleNamespace(id='memory', to_dict=lambda: copy.deepcopy(row))])

    def update(self, fields):
        self.row.update(fields)


def _scan(db, uid):
    return memories.scan_memories_updated_at_page(uid, limit=2, firestore_client=db)


@pytest.fixture
def attempt(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"historical_scan_memo":5}')
    # Select real stable cohorts rather than bypassing percentage gating.
    uid = next(f'scope-user-{i}' for i in range(1000) if lever_enabled('historical_scan_memo', f'scope-user-{i}'))
    off_uid = next(
        f'scope-user-{i}' for i in range(1000) if not lever_enabled('historical_scan_memo', f'scope-user-{i}')
    )
    monkeypatch.setattr(sync, 'run_blocking', run_blocking)
    job = {'status': 'processing', 'lane': 'fresh'}
    effects = {}
    for name, value in (
        ('get_sync_ledger_fence_mode', sync.SyncLedgerFenceMode.LEGACY),
        ('get_sync_job', job),
        ('sync_job_uses_ledger_fence', False),
        ('try_acquire_job_run_lock', 'lock-token'),
        ('release_job_run_lock', None),
        ('should_skip_background_account_mutation', False),
        ('_download_staged_files', True),
        ('release_backfill_slot', None),
        ('get_sync_tasks_max_attempts', 3),
        ('mark_job_queued_for_retry', job),
    ):
        effects[name] = MagicMock(return_value=value)
        monkeypatch.setattr(sync, name, effects[name])
    cleanup = AsyncMock()
    monkeypatch.setattr(sync, '_delete_staged_blobs_async', cleanup)
    request = SimpleNamespace(
        json=AsyncMock(return_value={'job_id': 'job', 'uid': uid, 'raw_blob_paths': ['staged/audio'], 'lane': 'fresh'})
    )
    return SimpleNamespace(uid=uid, off_uid=off_uid, request=request, db=_Query(), effects=effects, cleanup=cleanup)


@pytest.mark.asyncio
@pytest.mark.parametrize('lane', ['fresh', 'backfill'])
@pytest.mark.parametrize('mode', ['on', 'unset', 'outside_cohort', 'no_opener'])
async def test_task_attempt_two_scans_read_once_only_in_enabled_scope(monkeypatch, attempt, lane, mode):
    if mode == 'unset':
        monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)

        def forbidden(*args):
            pytest.fail('off path must not allocate a memo')

        monkeypatch.setattr(memories, '_HistoricalScanMemo', forbidden)
    uid = attempt.off_uid if mode == 'outside_cohort' else attempt.uid
    attempt.request.json.return_value.update(uid=uid, lane=lane)
    if mode == 'no_opener':
        monkeypatch.setattr(sync, 'historical_scan_memo_scope', lambda uid: nullcontext())
    pages = []

    async def pipeline(*args, **kwargs):
        assert kwargs['sync_lane'] == lane
        for _ in range(2):
            pages.append(await run_blocking(db_executor, _scan, attempt.db, uid))

    monkeypatch.setattr(sync, '_run_full_pipeline_background_async', pipeline)
    response = await sync._run_sync_job_body(attempt.request, 0)
    assert (response.status_code, json.loads(response.body)) == (200, {'status': 'done'})
    assert pages[0] == pages[1]
    assert (attempt.db.scans, attempt.db.reads) == ((1, 1) if mode == 'on' else (2, 2))
    assert attempt.effects['get_sync_job'].call_args_list == [call('job'), call('job')]
    attempt.effects['try_acquire_job_run_lock'].assert_called_once_with('job')
    attempt.effects['release_job_run_lock'].assert_called_once_with('job', 'lock-token')
    if lane == 'backfill':
        attempt.effects['_download_staged_files'].assert_called_once_with(['staged/audio'], bounded_backfill=True)
    else:
        attempt.effects['_download_staged_files'].assert_called_once_with(['staged/audio'])
    attempt.cleanup.assert_awaited_once_with(['staged/audio'], uid=uid, content_id=None, job_id='job')
    assert attempt.effects['release_backfill_slot'].call_count == (1 if lane == 'backfill' else 0)
    assert memories._historical_scan_memo.get() is None


@pytest.mark.asyncio
async def test_retry_closes_failed_attempt_and_reads_fresh_pages(monkeypatch, attempt):
    memos = []
    contents = []

    async def pipeline(*args, **kwargs):
        memos.append(memories._historical_scan_memo.get())
        page = await run_blocking(db_executor, _scan, attempt.db, attempt.uid)
        contents.append(page[0][0]['content'])
        assert page == await run_blocking(db_executor, _scan, attempt.db, attempt.uid)
        if len(memos) == 1:
            raise TimeoutError('retry')

    monkeypatch.setattr(sync, '_run_full_pipeline_background_async', pipeline)
    failed = await sync._run_sync_job_body(attempt.request, 0)
    assert (failed.status_code, json.loads(failed.body)) == (500, {'status': 'retry'})
    assert memos[0].closed and not memos[0].entries
    assert memories._historical_scan_memo.get() is None
    attempt.cleanup.assert_not_awaited()
    attempt.db.row['content'] = 'after'
    succeeded = await sync._run_sync_job_body(attempt.request, 1)
    assert succeeded.status_code == 200
    assert contents == ['before', 'after']
    assert memos[0] is not memos[1]
    assert all(memo.closed and not memo.entries for memo in memos)
    assert (attempt.db.scans, attempt.db.reads) == (2, 2)


@pytest.mark.asyncio
async def test_executor_sees_memo_and_retained_context_is_closed_after_exit(monkeypatch, attempt):
    retained = []

    def leaf():
        memo = memories._active_historical_scan_memo(attempt.uid)
        assert memo is not None
        retained.append((memo, copy_context()))
        return _scan(attempt.db, attempt.uid)

    async def pipeline(*args, **kwargs):
        owner = memories._historical_scan_memo.get()
        assert owner.owner_task is asyncio.current_task()
        assert await run_blocking(db_executor, leaf) == await run_blocking(db_executor, leaf)
        assert all(memo is owner for memo, _ in retained)
        # A raw executor submission gets no context, even after prior leaf work.
        assert await asyncio.get_running_loop().run_in_executor(db_executor, memories._historical_scan_memo.get) is None

    monkeypatch.setattr(sync, '_run_full_pipeline_background_async', pipeline)
    assert (await sync._run_sync_job_body(attempt.request, 0)).status_code == 200
    assert attempt.db.scans == 1
    memo, ctx = retained[0]
    assert memo.closed and not memo.entries
    assert ctx.run(memories._active_historical_scan_memo, attempt.uid) is None
    # Even a delayed call with the inherited context must perform a live read.
    ctx.run(_scan, attempt.db, attempt.uid)
    ctx.run(_scan, attempt.db, attempt.uid)
    assert attempt.db.scans == 3
    assert await run_blocking(db_executor, memories._historical_scan_memo.get) is None


@pytest.mark.asyncio
async def test_cancellation_closes_scope_and_preserves_run_lock(monkeypatch, attempt):
    memos = []

    async def pipeline(*args, **kwargs):
        memos.append(memories._historical_scan_memo.get())
        await run_blocking(db_executor, _scan, attempt.db, attempt.uid)
        raise asyncio.CancelledError()

    monkeypatch.setattr(sync, '_run_full_pipeline_background_async', pipeline)
    with pytest.raises(asyncio.CancelledError):
        await sync._run_sync_job_body(attempt.request, 0)
    assert memos[0].closed and not memos[0].entries
    assert memories._historical_scan_memo.get() is None
    attempt.effects['release_job_run_lock'].assert_not_called()
    attempt.cleanup.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('early_exit', ['locked', 'terminal', 'expired_audio'])
async def test_scope_excludes_admission_and_early_exits(monkeypatch, attempt, early_exit):
    opener = MagicMock(side_effect=AssertionError('no pipeline, no scope'))
    monkeypatch.setattr(sync, 'historical_scan_memo_scope', opener)
    if early_exit == 'locked':
        attempt.effects['try_acquire_job_run_lock'].return_value = None
    elif early_exit == 'terminal':
        attempt.effects['get_sync_job'].return_value = {'status': 'completed'}
    else:
        attempt.effects['_download_staged_files'].return_value = False
        monkeypatch.setattr(sync, '_finalize_sync_job_failure', AsyncMock())
    response = await sync._run_sync_job_body(attempt.request, 0)
    assert response.status_code == (409 if early_exit == 'locked' else 200)
    opener.assert_not_called()


@pytest.mark.asyncio
async def test_existing_memory_write_fence_invalidates_attempt_pages(monkeypatch, attempt):
    async def pipeline(*args, **kwargs):
        first = await run_blocking(db_executor, _scan, attempt.db, attempt.uid)
        await run_blocking(
            db_executor,
            memories._update_memory_if_exists,
            attempt.uid,
            'memory',
            {'content': 'changed'},
            'test',
            firestore_client=attempt.db,
        )
        second = await run_blocking(db_executor, _scan, attempt.db, attempt.uid)
        assert first[0][0]['content'] == 'before'
        assert second[0][0]['content'] == 'changed'
        assert second == await run_blocking(db_executor, _scan, attempt.db, attempt.uid)

    monkeypatch.setattr(sync, '_run_full_pipeline_background_async', pipeline)
    assert (await sync._run_sync_job_body(attempt.request, 0)).status_code == 200
    assert (attempt.db.scans, attempt.db.reads) == (2, 2)
