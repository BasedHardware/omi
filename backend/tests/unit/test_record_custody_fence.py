"""SCA-3748: the custody fence's lifetime belongs to the storage work, not to the request.

Only the fence's own worker-side completion releases the token, after every
started storage step settled, with the true storage outcome. Every fenced
commit starts within a budget and is bounded well under the custody lease.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import threading
import time
from types import SimpleNamespace

import anyio
import pytest
import requests
from google.api_core.exceptions import PreconditionFailed, ServiceUnavailable
from starlette.responses import JSONResponse

from config import record_seal_rules as lease
from config.record_gap_fill import LEASE_MARGIN_SECONDS
from database import record_custody_append as database
from database import record_audio
from utils.batch_pipeline import record_gap_fill as gap
from utils.batch_pipeline import record_lease_append as append
from utils.other import storage
from utils.sync import record_token_lease as request
from tests.unit.test_record_token_lease import PATH, ROW
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreTransaction

ROW_FREE = {**ROW, 'record_upload_sessions': {}}


def serving_world(monkeypatch, row=ROW_FREE):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    client = StrictFirestore({('users', 'synthetic'): {'private_cloud_sync_enabled': True}, PATH: deepcopy(row)})
    monkeypatch.setattr(database, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(record_audio, 'get_firestore_client', lambda: client)
    return client


def sessions(client):
    return client.rows[PATH]['record_upload_sessions']


def receipts(client):
    return [value['accepted'] for path, value in client.rows.items() if path[-2] == 'record_custody_recoveries']


def wait_until(predicate, seconds=5.0):
    deadline = time.monotonic() + seconds
    while not predicate():
        assert time.monotonic() < deadline, 'condition never held'
        time.sleep(0.005)


async def until(predicate, seconds=5.0):
    deadline = time.monotonic() + seconds
    while not predicate():
        assert time.monotonic() < deadline, 'condition never held'
        await asyncio.sleep(0.005)


class Held:
    """A real executor worker held at one point of its step."""

    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()

    def hold(self):
        self.entered.set()
        assert self.release.wait(10), 'test never released the worker'


def sealable(client):
    return record_audio.seal_record_audio('synthetic', 'record', firestore_client=client) != 'producer_pending'


def journal(monkeypatch):
    """Record completion order and that it never runs on the event-loop thread."""
    events = []
    original = database.finish

    def finish(*args, **kwargs):
        events.append(('finish', kwargs['accepted'], threading.current_thread() is threading.main_thread()))
        return original(*args, **kwargs)

    monkeypatch.setattr(database, 'finish', finish)
    return events


def upload_with(job, archive_fn, events, paths=('local-1', 'local-2')):
    @request.custody_upload
    async def upload():
        try:
            await request.begin_upload('synthetic', 'record', job)
            archived = await request.archive(archive_fn, 'synthetic', list(paths), {})
            request.stored(list(paths), archived)
            return JSONResponse(status_code=202, content={'status': 'queued'})
        finally:
            # The route's temp-file cleanup, exactly as sync.py hands it over.
            request.after_storage(lambda: events.append(('cleanup',)))

    return upload


async def cancel(task, canceller, scopes):
    if canceller == 'anyio_scope':
        scopes[0].cancel()
    else:
        task.cancel()
    await asyncio.sleep(0.05)
    if canceller == 'twice':
        task.cancel()
        await asyncio.sleep(0.05)


def start(upload, canceller):
    scopes: list[anyio.CancelScope] = []

    async def scoped():
        with anyio.CancelScope() as scope:
            scopes.append(scope)
            await upload()

    return asyncio.create_task(scoped() if canceller == 'anyio_scope' else upload()), scopes


async def settled_task(task, canceller):
    if canceller == 'anyio_scope':
        await task  # The scope absorbs its own cancellation.
    else:
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.parametrize('canceller', ['once', 'twice', 'anyio_scope'])
@pytest.mark.parametrize('phase', ['before_commit', 'after_commit'])
async def test_cancel_during_archive_holds_fence_until_worker_settles_then_finishes_true_outcome(
    monkeypatch, phase, canceller
):
    client = serving_world(monkeypatch)
    events = journal(monkeypatch)
    held = Held()
    written = []

    def archive_fn(uid, paths, metadata):
        if phase == 'before_commit':
            held.hold()  # GCS has not committed yet when the request is cancelled.
        written.extend(paths)
        return ['gs://synthetic/' + path for path in paths]

    if phase == 'after_commit':
        # The bytes are durable; the request is cancelled during its renewal.
        renew = record_audio.renew_record_token_lease

        def held_renewal(*args, **kwargs):
            held.hold()
            return renew(*args, **kwargs)

        monkeypatch.setattr(record_audio, 'renew_record_token_lease', held_renewal)

    task, scopes = start(upload_with(f'{phase}-{canceller}', archive_fn, events), canceller)
    await until(held.entered.is_set)
    await cancel(task, canceller, scopes)

    # The started worker is live: the fence holds, Pusher cannot seal, files stay.
    assert f'custody:{phase}-{canceller}' in sessions(client)
    assert not sealable(client)
    assert events == []

    held.release.set()
    await settled_task(task, canceller)
    await until(lambda: f'custody:{phase}-{canceller}' not in sessions(client))
    # The started file committed and the next one never started.
    assert written == ['local-1']
    # Worker-side completion: cleanup first, then finish with the true outcome.
    assert events == [('cleanup',), ('finish', True, False)]
    assert receipts(client) == [True]
    assert client.rows[PATH]['record_upload_revision'] == 8
    assert request._upload.get() is None


@pytest.mark.parametrize('failure', ['client_timeout', 'budget_spent'])
async def test_storage_write_that_times_out_finishes_unaccepted_well_before_the_lease(monkeypatch, failure):
    client = serving_world(monkeypatch)
    events = journal(monkeypatch)
    monkeypatch.setattr(lease, 'CUSTODY_STORAGE_BUDGET_SECONDS', 0.5)
    held = Held()

    def archive_fn(uid, paths, metadata):
        held.hold()
        if failure == 'client_timeout':
            raise requests.exceptions.ReadTimeout('synthetic GCS write timeout')
        time.sleep(0.55)
        # The storage writer's own pre-commit check (archive_capture_bytes).
        lease.check_custody_write_deadline()
        raise AssertionError('a commit started after its fence deadline')

    started = time.monotonic()
    task, scopes = start(upload_with(f'timeout-{failure}', archive_fn, events), 'once')
    await until(held.entered.is_set)
    await cancel(task, 'once', scopes)
    assert f'custody:timeout-{failure}' in sessions(client)
    held.release.set()
    await settled_task(task, 'once')
    await until(lambda: f'custody:timeout-{failure}' not in sessions(client))
    # Finished by its own worker as not accepted, long before lease repair.
    assert time.monotonic() - started < lease.custody_token_lease_seconds() / 2
    assert events == [('cleanup',), ('finish', False, False)]
    assert receipts(client) == [False]
    assert client.rows[PATH]['record_upload_revision'] == 7


@pytest.mark.parametrize('configured', [None, '1800', '3600', '7200'])
def test_bounded_custody_writes_stay_well_under_half_the_configured_lease(monkeypatch, configured):
    if configured is None:
        monkeypatch.delenv('RECORD_TOKEN_LEASE_SECONDS', raising=False)
    else:
        monkeypatch.setenv('RECORD_TOKEN_LEASE_SECONDS', configured)
    calls = []

    class Blob:
        metadata: dict = {}

        def upload_from_string(self, payload, **kwargs):
            calls.append(kwargs)

    bucket = SimpleNamespace(blob=lambda path: Blob())
    gap.create_gap_fill_chunk(b'\0\0', 'synthetic', 'record', 100.0, 'standard', {}, bucket=bucket)
    gap_fill = calls[-1]['timeout'] + calls[-1]['retry']._timeout
    assert gap_fill == LEASE_MARGIN_SECONDS / 3 + LEASE_MARGIN_SECONDS / 2
    archive = 10  # archive_capture_bytes: timeout=10, retry=None (proved below).
    assert max(gap_fill, archive) <= lease.CUSTODY_WRITE_SECONDS
    # The last commit lands before half the lease; repair cannot race it.
    assert lease.CUSTODY_STORAGE_BUDGET_SECONDS + lease.CUSTODY_WRITE_SECONDS < lease.custody_token_lease_seconds() / 2


@pytest.mark.parametrize('case', ['unfenced', 'fenced', 'fenced_collision', 'deadline_passed'])
def test_fenced_archive_commit_is_bounded_and_never_starts_after_its_deadline(monkeypatch, case):
    raw = b'synthetic-audio'
    calls = []

    class Blob:
        metadata: dict = {}
        generation = 1

        def upload_from_string(self, payload, **kwargs):
            calls.append(('upload', kwargs))
            if case == 'fenced_collision' or case == 'unfenced':
                raise PreconditionFailed('exists')

        def reload(self, **kwargs):
            calls.append(('reload', kwargs))
            self.metadata = {'sha256': storage.hashlib.sha256(raw).hexdigest()}

    bucket = SimpleNamespace(blob=lambda path: Blob())
    monkeypatch.setattr(storage, '_get_storage_client', lambda: SimpleNamespace(bucket=lambda name: bucket))
    monkeypatch.setattr(storage.users_db, 'get_data_protection_level', lambda uid: 'standard')

    def write():
        return storage.archive_capture_bytes('synthetic', raw, 'raw-sync', 'local', {})

    if case == 'unfenced':
        write()
        # Unchanged outside a fence: the same bounded upload, the same reload.
        assert (calls[0][1]['timeout'], calls[0][1]['retry']) == (10, None)
        assert calls[1] == ('reload', {})
        return
    deadline = time.monotonic() + (-1 if case == 'deadline_passed' else 60)
    with lease.bound_custody_writes(deadline):
        if case == 'deadline_passed':
            with pytest.raises(lease.CustodyWriteDeadline):
                write()
            assert calls == []
            return
        write()
    upload = calls[0][1]
    assert (upload['timeout'], upload['retry']) == (10, None)
    if case == 'fenced_collision':
        assert calls[1] == ('reload', {'timeout': 10, 'retry': None})


async def test_cancel_during_retained_copy_chunk_write_holds_fence(monkeypatch):
    client = serving_world(monkeypatch)
    events = journal(monkeypatch)
    held = Held()
    seen = []

    def retain(uid, cid, row, paths):
        # The chunk writer receives this fence's commit deadline on its worker.
        seen.append(lease.custody_write_deadline())
        held.hold()

    async def rearm(*args):
        return None

    monkeypatch.setattr(append, 'retain', retain)
    monkeypatch.setattr(append, 'retention_window', lambda row: (0.0, 1.0))
    monkeypatch.setattr(append, 'rearm_partial', rearm)

    @request.custody_upload
    async def upload():
        try:
            await request.begin_upload('synthetic', 'record', 'retain')
            archived = await request.archive(lambda *args: ['durable-archive'], 'synthetic', ['local'], {})
            request.stored(['local'], archived)
            await append.retain_upload('synthetic', 'record', {}, ['local'], None)
            return JSONResponse(status_code=202, content={'status': 'queued'})
        finally:
            request.after_storage(lambda: events.append(('cleanup',)))

    task = asyncio.create_task(upload())
    await until(held.entered.is_set)
    task.cancel()
    await asyncio.sleep(0.05)
    assert 'custody:retain' in sessions(client)
    assert not sealable(client)
    assert events == []
    held.release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    await until(lambda: 'custody:retain' not in sessions(client))
    assert seen and seen[0] is not None
    assert events == [('cleanup',), ('finish', True, False)]
    assert receipts(client) == [True]
    assert client.rows[PATH]['record_upload_revision'] == 8


@pytest.mark.parametrize('outcome', ['accepts', 'fails'])
async def test_live_response_waits_for_a_queued_finish_and_matches_its_recorded_outcome(monkeypatch, outcome):
    client = serving_world(monkeypatch)
    pool = ThreadPoolExecutor(max_workers=1)
    monkeypatch.setattr(request, 'db_executor', pool)
    # Far shorter than the queue wait: the response never answers on a timer.
    monkeypatch.setattr(lease, 'custody_token_lease_seconds', lambda: 0.05)
    blocker, occupied = threading.Event(), threading.Event()
    if outcome == 'fails':

        def unavailable(*args, **kwargs):
            raise ServiceUnavailable('synthetic finish outage')

        monkeypatch.setattr(database, 'finish', unavailable)

    def occupy():
        occupied.set()
        assert blocker.wait(10)

    @request.custody_upload
    async def upload():
        await request.begin_upload('synthetic', 'record', 'queued')
        archived = await request.archive(lambda *args: ['durable-archive'], 'synthetic', ['local'], {})
        request.stored(['local'], archived)
        # Occupy the only DB worker so this request's finish queues behind it.
        pool.submit(occupy)
        return JSONResponse(status_code=202, content={'status': 'queued'})

    task = asyncio.create_task(upload())
    await until(occupied.is_set)
    await asyncio.sleep(0.2)
    assert not task.done()
    blocker.set()
    try:
        status = (await task).status_code
    except request.HTTPException as error:
        status = error.status_code
    pool.shutdown(wait=True)
    if outcome == 'accepts':
        assert status == 202
        assert receipts(client) == [True]
        assert 'custody:queued' not in sessions(client)
    else:
        # Never a 503 over an accepted receipt: finish did not record one.
        assert status == 503
        assert receipts(client) == []
        assert 'custody:queued' in sessions(client)


async def test_queued_completion_at_executor_shutdown_leaves_the_token_for_lease_repair(monkeypatch):
    client = serving_world(monkeypatch)
    events = journal(monkeypatch)
    pool = ThreadPoolExecutor(max_workers=1)
    monkeypatch.setattr(request, 'db_executor', pool)
    held = Held()

    def archive_fn(uid, paths, metadata):
        held.hold()
        return ['durable-archive']

    task = asyncio.create_task(upload_with('shutdown', archive_fn, events, paths=('local',))())
    await until(held.entered.is_set)
    task.cancel()
    await asyncio.sleep(0.05)
    pool.shutdown(wait=True)
    held.release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    await until(lambda: events == [('cleanup',)])
    # No finish could run: the token waits for lease expiry, never early.
    assert 'custody:shutdown' in sessions(client)
    assert receipts(client) == []


def test_loop_shutdown_mid_archive_leaves_completion_to_the_worker(monkeypatch):
    client = serving_world(monkeypatch)
    events = journal(monkeypatch)
    held = Held()

    def archive_fn(uid, paths, metadata):
        held.hold()
        return ['durable-archive']

    tasks = []

    async def main():
        tasks.append(asyncio.create_task(upload_with('loop', archive_fn, events, paths=('local',))()))
        while not held.entered.is_set():
            await asyncio.sleep(0.005)

    # asyncio.run cancels the still-running request, then closes its loop.
    asyncio.run(main())
    assert tasks[0].cancelled()
    assert 'custody:loop' in sessions(client)
    assert events == []
    held.release.set()
    wait_until(lambda: 'custody:loop' not in sessions(client))
    assert events == [('cleanup',), ('finish', True, False)]
    assert receipts(client) == [True]


async def test_request_cancelled_during_begin_clears_the_token_begin_committed(monkeypatch):
    client = serving_world(monkeypatch)
    held = Held()
    original = database.begin

    def held_begin(*args, **kwargs):
        held.hold()
        return original(*args, **kwargs)

    monkeypatch.setattr(database, 'begin', held_begin)
    task = asyncio.create_task(upload_with('begin-cancelled', lambda *args: ['x'], [])())
    await until(held.entered.is_set)
    task.cancel()
    await asyncio.sleep(0.05)
    held.release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    await until(lambda: receipts(client) == [False])
    assert 'custody:begin-cancelled' not in sessions(client)
    assert client.rows[PATH]['record_upload_revision'] == 7


@pytest.mark.parametrize('retry_sees', ['opted_out', 'ineligible', 'eligible'])
async def test_ambiguous_begin_retry_never_writes_to_a_refused_conversation(monkeypatch, retry_sees):
    client = serving_world(monkeypatch)
    original_commit = StrictFirestoreTransaction._commit
    lost = []

    def commit_then_lose_reply(tx):
        original_commit(tx)
        if not lost and any(
            'custody:ambiguous' in (data.get('record_upload_sessions') or {}) for _, data in tx.updates
        ):
            lost.append(True)
            if retry_sees == 'opted_out':
                client.rows['users', 'synthetic']['private_cloud_sync_enabled'] = False
            elif retry_sees == 'ineligible':
                client.rows[PATH]['record_lane_owner'] = 'legacy_final_pass_v1'
            raise ServiceUnavailable('synthetic response lost after begin committed')

    monkeypatch.setattr(StrictFirestoreTransaction, '_commit', commit_then_lose_reply)
    owned = []

    @request.custody_upload
    async def upload():
        await request.begin_upload('synthetic', 'record', 'ambiguous')
        owned.append(request.owns_upload('synthetic', 'record'))
        return JSONResponse(status_code=202, content={'status': 'failed'})

    assert (await upload()).status_code == 202
    assert lost == [True]
    if retry_sees == 'eligible':
        # The retry found its own token; the request owned and finished it.
        assert owned == [True]
        assert 'custody:ambiguous' not in sessions(client)
        assert receipts(client) == [False]
        return
    # Zero writes after the lost begin: the token expires on its lease instead.
    assert owned == [False]
    assert [tx.has_written for tx in client.transactions].count(True) == 1
    assert 'custody:ambiguous' in sessions(client)
    assert receipts(client) == []


async def test_lease_config_is_never_read_on_the_event_loop(monkeypatch):
    client = serving_world(monkeypatch)
    readers = []
    original = lease.custody_token_lease_seconds

    def observed():
        readers.append(threading.current_thread() is threading.main_thread())
        return original()

    monkeypatch.setattr(lease, 'custody_token_lease_seconds', observed)
    held = Held()

    def archive_fn(uid, paths, metadata):
        held.hold()
        return ['durable-archive']

    task = asyncio.create_task(upload_with('cold', archive_fn, [], paths=('local',))())
    await until(held.entered.is_set)
    task.cancel()
    await asyncio.sleep(0.05)
    held.release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    await until(lambda: 'custody:cold' not in sessions(client))
    assert readers and not any(readers)
