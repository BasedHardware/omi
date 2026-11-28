"""Real custody metadata transactions around accepted/refused storage requests."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import threading
from unittest.mock import Mock

import anyio
import pytest
from fastapi import HTTPException
from google.api_core.exceptions import ServiceUnavailable
from starlette.responses import JSONResponse

from database import record_custody_append as database
from database import record_token_lease_metrics as metrics, record_audio
from config.record_audio import record_identity
from config import record_seal_rules as lease
from database.batch_pipeline_record_lease_recovery import recovery_segment
from database.batch_pipeline_privacy import BatchPrivacyBlocked, privacy_owner_key
from utils.sync import record_token_lease as request
from tests.unit.test_record_token_lease import PATH, ROW, NOW
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreTransaction
from utils.batch_pipeline.record_producer_proof import producer_tokens_dead
from utils.batch_pipeline.record_seal_repair import seal_refusal


def custody_client(rows):
    return StrictFirestore({('users', 'synthetic'): {'private_cloud_sync_enabled': True}, **rows})


@pytest.mark.parametrize('existing_token', [False, True])
@pytest.mark.parametrize('authority', ['missing_user', 'blocked', 'purging'])
def test_begin_refuses_missing_owner_or_active_erasure_without_writing(monkeypatch, authority, existing_token):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    session = 'custody:erasure'
    sessions = {session: {'signal_source': 'custody_append'}} if existing_token else {}
    client = custody_client({PATH: {**ROW, 'record_upload_sessions': sessions}})
    if authority == 'missing_user':
        client.rows.pop(('users', 'synthetic'))
    else:
        client.rows['batch_pipeline_privacy', privacy_owner_key('synthetic')] = {'generation': 1, authority: True}
    before = deepcopy(client.rows)

    with pytest.raises(BatchPrivacyBlocked):
        database.begin('synthetic', 'record', session, firestore_client=client)

    assert client.rows == before
    assert not any(tx.has_written for tx in client.transactions)


@pytest.mark.parametrize('status,durable', [(202, True), (409, True), (503, True), (202, False)])
@pytest.mark.parametrize('mode', ['off', 'shadow', 'serve'])
async def test_response_storage_and_kill_switch_matrix(monkeypatch, status, durable, mode):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', mode)
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setattr(database.time, 'time', lambda: NOW)
    client = custody_client({PATH: ROW, ('users', 'synthetic'): {'private_cloud_sync_enabled': True}})
    monkeypatch.setattr(database, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(record_audio, 'get_firestore_client', lambda: client)
    counter = metrics.LATE_APPEND._value.get()
    before = deepcopy(client.rows)
    stored = []

    @request.custody_upload
    async def upload():
        await request.begin_upload('synthetic', 'record', 'request')
        row = client.rows[PATH]
        assert row['record_upload_revision'] == 7
        assert 'custody:request' in row['record_upload_sessions']
        if durable:
            archived = await request.archive(
                lambda *args: stored.append(args) or ['durable-archive'], 'synthetic', ['local'], {}
            )
            request.stored(['local'], archived)
        return JSONResponse(status_code=status, content={'status': 'synthetic'})

    if mode != 'serve':
        # Kill switch: refuse before any storage or metadata write. There is no
        # unfenced append to fall back to; the phone retains its audio.
        with pytest.raises(HTTPException) as failure:
            await upload()
        assert failure.value.status_code == 503
        assert failure.value.detail.startswith('Retain local audio')
        assert not stored
        assert client.rows == before
        assert not any(tx.has_written for tx in client.transactions)
        assert metrics.LATE_APPEND._value.get() == counter
        assert request._upload.get() is None
        return
    if status == 202 and not durable:
        with pytest.raises(HTTPException) as failure:
            await upload()
        assert failure.value.status_code == 503
    else:
        assert (await upload()).status_code == status
    accepted = status == 202 and durable
    assert 'custody:request' not in client.rows[PATH]['record_upload_sessions']
    assert client.rows[PATH]['record_upload_revision'] == 7 + accepted
    assert metrics.LATE_APPEND._value.get() == counter + accepted
    assert request._upload.get() is None


async def test_memoized_wait_before_begin_has_zero_metadata_io(monkeypatch):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    forbidden = Mock(side_effect=AssertionError('memoized retry performed metadata IO'))
    monkeypatch.setattr(database, 'get_firestore_client', forbidden)

    @request.custody_upload
    async def upload():
        # The endpoint returns its memoized response before begin_upload.
        return JSONResponse(status_code=503, content={'code': 'record_jobs_missing'})

    assert (await upload()).status_code == 503
    forbidden.assert_not_called()


async def test_storage_exception_clears_only_own_fence_without_revision_or_counter(monkeypatch):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    client = custody_client({PATH: ROW})
    monkeypatch.setattr(database, 'get_firestore_client', lambda: client)
    before = deepcopy(client.rows)
    counter = metrics.LATE_APPEND._value.get()

    @request.custody_upload
    async def upload():
        await request.begin_upload('synthetic', 'record', 'failed')
        raise OSError('synthetic archive failure')

    with pytest.raises(OSError):
        await upload()
    assert client.rows[PATH] == before[PATH]
    assert not next(value for path, value in client.rows.items() if path[-2] == 'record_custody_recoveries')['accepted']
    assert metrics.LATE_APPEND._value.get() == counter


async def test_failed_job_202_is_a_refusal_without_bump_or_late_count(monkeypatch):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    client = custody_client({PATH: ROW})
    monkeypatch.setattr(database, 'get_firestore_client', lambda: client)
    before = deepcopy(client.rows)
    counter = metrics.LATE_APPEND._value.get()

    @request.custody_upload
    async def upload():
        await request.begin_upload('synthetic', 'record', 'capped')
        request.stored(['local'], ['archive'])
        return JSONResponse(status_code=202, content={'status': 'failed'})

    assert (await upload()).status_code == 202
    assert client.rows[PATH] == before[PATH]
    assert not next(value for path, value in client.rows.items() if path[-2] == 'record_custody_recoveries')['accepted']
    assert metrics.LATE_APPEND._value.get() == counter


async def test_same_job_retry_after_refusal_clears_token_and_records_recovery(monkeypatch):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setattr(database.time, 'time', lambda: NOW)
    client = custody_client({PATH: {**ROW, 'record_upload_sessions': {}, 'record_audio_closed': True}})
    monkeypatch.setattr(database, 'get_firestore_client', lambda: client)
    session = 'custody:retry-refused-job'
    receipt = (*PATH, 'record_custody_recoveries', hashlib.sha256(session.encode()).hexdigest())
    recovery_path = ('batch_pipeline_dev_jobs', recovery_segment('synthetic', 'record'))
    counter = metrics.LATE_APPEND._value.get()

    @request.custody_upload
    async def upload(status):
        await request.begin_upload('synthetic', 'record', 'retry-refused-job')
        assert session in client.rows[PATH]['record_upload_sessions']
        request.stored(['local'], ['archive'])
        return JSONResponse(status_code=202, content={'status': status})

    assert (await upload('failed')).status_code == 202
    assert client.rows[receipt]['accepted'] is False
    assert not client.rows[PATH]['record_upload_sessions']
    assert client.rows[PATH]['record_upload_revision'] == 7
    assert recovery_path not in client.rows
    assert metrics.LATE_APPEND._value.get() == counter

    assert (await upload('queued')).status_code == 202
    assert not client.rows[PATH]['record_upload_sessions']
    assert client.rows[PATH]['record_upload_revision'] == 8
    assert client.rows[receipt]['accepted'] is True
    assert client.rows[receipt]['upload_revision'] == 8
    assert client.rows[receipt]['late'] is True
    assert client.rows[PATH]['record_audio_partial']['upload_revision'] == 8
    assert client.rows[recovery_path]['partial_coordinator']
    assert client.rows[recovery_path]['state'] == 'record_pending'
    assert metrics.LATE_APPEND._value.get() == counter + 1
    before = deepcopy(client.rows)
    assert database.begin('synthetic', 'record', session, firestore_client=client)
    assert database.finish('synthetic', 'record', session, accepted=True, firestore_client=client)
    assert client.rows == before
    assert metrics.LATE_APPEND._value.get() == counter + 1


@pytest.mark.parametrize('status', ['completed', 'processing', 'recording'])
@pytest.mark.parametrize('final_mode', ['off', 'shadow', 'serve'])
async def test_captured_input_recovery_survives_status_and_rollback(monkeypatch, status, final_mode):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setattr(database.time, 'time', lambda: NOW)
    content, segment = record_identity('synthetic', 'record')
    client = custody_client(
        {
            PATH: {**ROW, 'status': status, 'record_audio_closed': False, 'record_upload_sessions': {}},
            ('users', 'synthetic'): {'private_cloud_sync_enabled': True},
            ('batch_pipeline_dev_jobs', segment): {
                'segment_id': segment,
                'owner_id': 'synthetic',
                'conversation_id': 'record',
                'record_content_id': content,
                'record_input_upload_revision': 7,
                'state': 'ready',
            },
        }
    )
    monkeypatch.setattr(database, 'get_firestore_client', lambda: client)
    counter = metrics.LATE_APPEND._value.get()

    @request.custody_upload
    async def upload():
        await request.begin_upload('synthetic', 'record', 'rollback')
        monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', final_mode)
        request.stored(['local'], ['committed-object'])
        return JSONResponse(status_code=202, content={'status': 'queued'})

    assert (await upload()).status_code == 202
    assert client.rows[PATH]['record_upload_revision'] == 8
    recovery = client.rows['batch_pipeline_dev_jobs', recovery_segment('synthetic', 'record')]
    assert recovery['partial_coordinator'] and recovery['state'] == 'record_recovery_waiting'
    assert client.rows[PATH]['record_audio_partial']['upload_revision'] == 8
    assert client.rows[PATH]['status'] == status
    assert metrics.LATE_APPEND._value.get() == counter + 1


@pytest.mark.parametrize('disabled_at_begin', [False, True])
async def test_disabled_archive_preserves_original_response_without_append(monkeypatch, disabled_at_begin):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    client = custody_client({PATH: ROW, ('users', 'synthetic'): {'private_cloud_sync_enabled': not disabled_at_begin}})
    monkeypatch.setattr(database, 'get_firestore_client', lambda: client)
    before = deepcopy(client.rows[PATH])
    counter = metrics.LATE_APPEND._value.get()
    response = JSONResponse(status_code=202, content={'status': 'queued', 'job_id': 'original'})

    @request.custody_upload
    async def upload():
        await request.begin_upload('synthetic', 'record', 'no-archive')
        assert ('custody:no-archive' in client.rows[PATH]['record_upload_sessions']) is not disabled_at_begin
        # The archive deliberately returns no paths after consent is disabled.
        archived = await request.archive(lambda *args: [], 'synthetic', ['local'], {})
        request.stored(['local'], archived)
        return response

    assert await upload() is response
    assert client.rows[PATH] == before
    assert metrics.LATE_APPEND._value.get() == counter
    assert not any(row.get('partial_coordinator') for row in client.rows.values())


@pytest.mark.parametrize('lose_fence', [False, True])
@pytest.mark.parametrize('final_mode', ['serve', 'off'])
async def test_durable_archive_outlives_old_lease_and_recovers_a_lost_fence(monkeypatch, lose_fence, final_mode):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_SECONDS', '3600')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = [NOW]
    monkeypatch.setattr(database.time, 'time', lambda: clock[0])
    content, original = record_identity('synthetic', 'record')
    client = custody_client(
        {
            PATH: {**ROW, 'record_upload_sessions': {}, 'record_audio_closed': False},
            ('users', 'synthetic'): {'private_cloud_sync_enabled': True},
            ('batch_pipeline_dev_jobs', original): {
                'segment_id': original,
                'owner_id': 'synthetic',
                'conversation_id': 'record',
                'record_content_id': content,
                'record_input_upload_revision': 7,
                'state': 'ready',
            },
        }
    )
    monkeypatch.setattr(database, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(request.record_audio, 'get_firestore_client', lambda: client)
    session = 'custody:long-archive'
    committed = {}
    counter = metrics.LATE_APPEND._value.get()
    response = JSONResponse(status_code=202, content={'status': 'queued'})

    def archive(uid, paths, metadata):
        # One operation cannot heartbeat while blocked. Repair still sees a
        # live uploader past the old default lease, including after rollback.
        clock[0] = NOW + lease.token_lease_seconds() + 1
        monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', final_mode)
        row = client.rows[PATH]
        assert row['record_upload_sessions'][session]['lease_expires_at'] > clock[0]
        assert not producer_tokens_dead(row['record_upload_sessions'], None, uid=uid, row=row)
        committed['object'] = b'new interior audio'
        if lose_fence:
            # Simulate a competing repair/old pod clearing custody and sealing
            # old input immediately before the successful object commit returns.
            row['record_upload_sessions'].pop(session)
            row['record_audio_closed'] = True
        return ['committed-object']

    @request.custody_upload
    async def upload():
        await request.begin_upload('synthetic', 'record', 'long-archive')
        token = client.rows[PATH]['record_upload_sessions'][session]
        assert token['lease_expires_at'] - token['last_signal_at'] == lease.custody_token_lease_seconds()
        archived = await request.archive(archive, 'synthetic', ['local-audio'], {})
        request.stored(['local-audio'], archived)
        return response

    assert await upload() is response
    row = client.rows[PATH]
    assert row['record_upload_revision'] == 8
    assert not row['record_audio_closed'] and not row['record_upload_sessions']
    assert row['record_audio_partial']['upload_revision'] == 8
    recovery = client.rows['batch_pipeline_dev_jobs', recovery_segment('synthetic', 'record')]
    assert recovery['partial_coordinator'] and recovery['state'] == 'record_recovery_waiting'
    assert committed == {'object': b'new interior audio'}
    assert metrics.LATE_APPEND._value.get() == counter + 1
    if lose_fence:
        receipt = (*PATH, 'record_custody_recoveries', hashlib.sha256(session.encode()).hexdigest())
        assert client.rows[receipt]['upload_revision'] == 8
        before = deepcopy(client.rows)
        assert not database.recover_committed('synthetic', 'record', session, firestore_client=client)
        assert client.rows == before
        assert not client.transactions[-1].updates
        assert metrics.LATE_APPEND._value.get() == counter + 1
    assert request._upload.get() is None


async def test_session_only_upload_fences_resolved_target_for_the_whole_archive(monkeypatch):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_SECONDS', '3600')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    clock = [NOW]
    monkeypatch.setattr(database.time, 'time', lambda: clock[0])
    client = custody_client(
        {PATH: ROW, ('users', 'synthetic', 'recording_sessions', 'capture'): {'conversation_id': 'record'}}
    )
    monkeypatch.setattr(database, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(request.record_audio, 'get_firestore_client', lambda: client)
    session = 'custody:session-only'
    response = JSONResponse(status_code=202, content={'status': 'queued'})

    def archive(uid, paths, metadata):
        row = client.rows[PATH]
        assert session in row['record_upload_sessions']
        clock[0] = NOW + lease.token_lease_seconds() + 1
        assert row['record_upload_sessions'][session]['lease_expires_at'] > clock[0]
        assert (
            seal_refusal({'state': 'record_pending', 'record_content_id': 'synthetic', 'owner_id': uid}, row)
            == 'upload_pending'
        )
        assert not row.get('record_audio_closed')
        return ['committed-object']

    @request.custody_upload
    async def upload():
        await request.begin_upload('synthetic', None, 'session-only', recording_session_id='capture')
        archived = await request.archive(archive, 'synthetic', ['local'], {})
        request.stored(['local'], archived)
        return response

    assert await upload() is response
    assert client.rows[PATH]['record_upload_revision'] == 8
    assert session not in client.rows[PATH]['record_upload_sessions']


async def test_unresolved_session_keeps_original_response_without_custody_append(monkeypatch):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    client = custody_client({PATH: ROW})
    monkeypatch.setattr(database, 'get_firestore_client', lambda: client)
    forbidden = Mock(side_effect=AssertionError('unresolved target acquired custody'))
    monkeypatch.setattr(database, 'begin', forbidden)
    before = deepcopy(client.rows)
    response = JSONResponse(status_code=202, content={'status': 'queued'})

    @request.custody_upload
    async def upload():
        await request.begin_upload('synthetic', None, 'unresolved', recording_session_id='missing')
        archived = await request.archive(lambda *args: ['archive'], 'synthetic', ['local'], {})
        request.stored(['local'], archived)
        return response

    assert await upload() is response
    forbidden.assert_not_called()
    assert client.rows == before


@pytest.mark.parametrize('mode', ['serve', 'off', 'shadow', ''])
async def test_session_registered_after_admission_is_fenced_or_killed_when_routing_resolves_it(monkeypatch, mode):
    # Race: Sync admission resolves the recording session before registration
    # lands, so it acquires no fence. Record routing then resolves the same
    # session after staging. Routing must apply the same gate before writing.
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', mode)
    monkeypatch.setenv('RECORD_TOKEN_LEASE_SECONDS', '3600')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setattr(database.time, 'time', lambda: NOW)
    client = custody_client({PATH: ROW})
    monkeypatch.setattr(database, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(request.record_audio, 'get_firestore_client', lambda: client)
    session = 'custody:late-registration'
    stored = []

    def archive(uid, paths, metadata):
        assert session in client.rows[PATH]['record_upload_sessions']
        stored.append(paths)
        return ['committed-object']

    @request.custody_upload
    async def upload():
        await request.begin_upload('synthetic', None, 'late-registration', recording_session_id='capture')
        assert 'session' not in request._upload.get()
        # Registration lands between admission's resolve and routing's resolve.
        client.rows['users', 'synthetic', 'recording_sessions', 'capture'] = {'conversation_id': 'record'}
        target = database.resolve_target('synthetic', None, 'capture', firestore_client=client)
        await request.bind_upload_target('synthetic', target)
        archived = await request.archive(archive, 'synthetic', ['local'], {})
        request.stored(['local'], archived)
        return JSONResponse(status_code=202, content={'status': 'queued'})

    if mode != 'serve':
        before = deepcopy(client.rows)
        with pytest.raises(HTTPException) as refused:
            await upload()
        assert refused.value.status_code == 503
        assert refused.value.detail == 'Retain local audio; record custody is paused'
        assert not stored
        # Only the synthetic registration changed; custody wrote nothing.
        registration = ('users', 'synthetic', 'recording_sessions', 'capture')
        assert {k: v for k, v in client.rows.items() if k != registration} == before
        assert not any(tx.has_written for tx in client.transactions)
    else:
        assert (await upload()).status_code == 202
        assert stored == [['local']]
        assert client.rows[PATH]['record_upload_revision'] == 8
        assert session not in client.rows[PATH]['record_upload_sessions']
    assert request._upload.get() is None


async def test_routing_cannot_rebind_an_admitted_upload_to_another_target(monkeypatch):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setattr(database.time, 'time', lambda: NOW)
    client = custody_client({PATH: ROW})
    monkeypatch.setattr(database, 'get_firestore_client', lambda: client)
    archive = Mock(return_value=['object'])

    @request.custody_upload
    async def upload():
        await request.begin_upload('synthetic', 'record', 'rebind')
        # The same target is a no-op; a different one is refused before writes.
        await request.bind_upload_target('synthetic', 'record')
        await request.bind_upload_target('synthetic', 'other-record')
        await request.archive(archive, 'synthetic', ['local'], {})
        return JSONResponse(status_code=202, content={'status': 'queued'})

    with pytest.raises(HTTPException) as refused:
        await upload()
    assert refused.value.status_code == 503
    archive.assert_not_called()
    # The admitted fence is released as an unaccepted upload.
    assert 'custody:rebind' not in client.rows[PATH]['record_upload_sessions']
    assert client.rows[PATH]['record_upload_revision'] == 7


class _HeldBegin:
    """begin/finish doubles that hold begin on its worker thread until released."""

    def __init__(self, monkeypatch, acquired: bool):
        self.acquired = acquired
        self.tokens: dict[str, dict[str, str]] = {}
        self.finishes: list[bool] = []
        self.started, self.release, self.done, self.finished = (threading.Event() for _ in range(4))
        monkeypatch.setattr(database, 'begin', self.begin)
        monkeypatch.setattr(database, 'finish', self.finish)

    def begin(self, uid, cid, session):
        self.started.set()
        assert self.release.wait(5)
        if self.acquired:
            self.tokens[session] = {'signal_source': 'custody_append'}
        self.done.set()
        return self.acquired

    def finish(self, uid, cid, session, *, accepted, late_observed=False):
        # Records whether the token was already committed when cleanup ran.
        self.finishes.append(session in self.tokens)
        self.tokens.pop(session, None)
        self.finished.set()
        return False


async def _thread_wait(event: threading.Event, timeout: float) -> bool:
    return await asyncio.get_running_loop().run_in_executor(None, event.wait, timeout)


def _custody_request(first_bind: str, archive: Mock):
    @request.custody_upload
    async def upload():
        if first_bind == 'admission':
            await request.begin_upload('synthetic', 'record', 'cancelled')
        else:
            # The session resolves only in routing, which binds the fence late.
            await request.begin_upload('synthetic', None, 'cancelled')
            await request.bind_upload_target('synthetic', 'record')
        await request.archive(archive, 'synthetic', ['local'], {})
        return JSONResponse(status_code=202, content={'status': 'queued'})

    return upload


@pytest.mark.parametrize('acquired', [True, False])
@pytest.mark.parametrize('first_bind', ['admission', 'routing'])
@pytest.mark.parametrize('cancel', ['single', 'double', 'anyio_scope'])
async def test_cancel_during_fence_acquisition_never_holds_the_handler_or_strands_the_token(
    monkeypatch, first_bind, acquired, cancel
):
    # SCA-3748 r3/r4: begin commits on a worker thread a cancelled request cannot
    # stop. Waiting for it in cleanup held the handler (single cancel) and was
    # itself interrupted by a second cancel or an AnyIO scope, stranding the
    # token. The handler must exit at once and the acquisition clean up itself.
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    held = _HeldBegin(monkeypatch, acquired)
    archive = Mock(return_value=['object'])
    upload = _custody_request(first_bind, archive)
    scopes: list[anyio.CancelScope] = []

    async def handler():
        if cancel != 'anyio_scope':
            return await upload()
        with anyio.CancelScope() as scope:
            scopes.append(scope)
            return await upload()

    task = asyncio.ensure_future(handler())
    try:
        assert await _thread_wait(held.started, 5)
        if cancel == 'anyio_scope':
            scopes[0].cancel()
        else:
            task.cancel()
            if cancel == 'double':
                # Let cleanup start, then cancel whatever it is awaiting.
                for _ in range(3):
                    await asyncio.sleep(0)
                task.cancel()
        # The handler exits while begin is still committing on its thread.
        done, _ = await asyncio.wait({task}, timeout=2)
        assert done == {task}
        assert not held.done.is_set()
        assert held.finishes == []
    finally:
        held.release.set()
    if cancel == 'anyio_scope':
        assert task.result() is None  # The scope absorbs its own cancellation.
    else:
        assert task.cancelled()
    assert await _thread_wait(held.done, 5)
    if acquired:
        # The acquisition thread finished its own token, exactly once.
        assert await _thread_wait(held.finished, 5)
    else:
        # A refused acquisition (sync opt-out) leaves nothing to finish.
        assert not await _thread_wait(held.finished, 0.2)
    archive.assert_not_called()
    assert held.finishes == ([True] if acquired else [])
    assert held.tokens == {}
    assert request._upload.get() is None


async def test_anyio_scope_cancel_after_acquisition_still_finishes_the_owned_token(monkeypatch):
    # Once begin has returned the request owns finish. An AnyIO scope redelivers
    # cancellation at every await, so that finish must not depend on this await.
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    held = _HeldBegin(monkeypatch, True)
    held.release.set()
    finish_entered, release_finish = threading.Event(), threading.Event()
    finish = held.finish

    def slow_finish(*args, **kwargs):
        finish_entered.set()
        assert release_finish.wait(5)
        return finish(*args, **kwargs)

    monkeypatch.setattr(database, 'finish', slow_finish)
    archived, release_archive = asyncio.Event(), asyncio.Event()

    @request.custody_upload
    async def upload():
        await request.begin_upload('synthetic', 'record', 'cancelled')
        archived.set()
        await release_archive.wait()
        return JSONResponse(status_code=202, content={'status': 'queued'})

    scopes: list[anyio.CancelScope] = []

    async def handler():
        with anyio.CancelScope() as scope:
            scopes.append(scope)
            return await upload()

    task = asyncio.ensure_future(handler())
    try:
        await asyncio.wait_for(archived.wait(), 5)
        scopes[0].cancel()
        assert await _thread_wait(finish_entered, 5)
        done, _ = await asyncio.wait({task}, timeout=2)
        assert done == {task}
    finally:
        release_finish.set()
    assert await _thread_wait(held.finished, 5)
    assert held.finishes == [True]
    assert held.tokens == {}


class _RecordedFinish:
    """finish double recording each outcome and whether the archive had committed."""

    def __init__(self, monkeypatch, held: _HeldBegin, committed: threading.Event):
        self.calls: list[tuple[bool, bool]] = []
        self.finished = threading.Event()
        self._held, self._committed = held, committed
        monkeypatch.setattr(database, 'finish', self.finish)

    def finish(self, uid, cid, session, *, accepted, late_observed=False):
        self.calls.append((accepted, self._committed.is_set()))
        self._held.tokens.pop(session, None)
        self.finished.set()
        return False


@pytest.mark.parametrize('cancel', ['single', 'double', 'anyio_scope'])
async def test_cancel_during_archive_holds_the_fence_until_the_commit_then_finishes_accepted(monkeypatch, cancel):
    # SCA-3748 r5: cancellation cleared the fence while the archive write was
    # still running, so a Pusher drain could seal with the old revision. The
    # fence must stay held until the archive commits, then finish accepted.
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    held = _HeldBegin(monkeypatch, True)
    held.release.set()
    entered, release_archive, committed = threading.Event(), threading.Event(), threading.Event()
    finish = _RecordedFinish(monkeypatch, held, committed)
    renewals = []
    monkeypatch.setattr(
        request.record_audio, 'renew_record_token_lease', lambda *args, **kwargs: renewals.append(kwargs) or True
    )

    def archive(uid, paths, metadata):
        entered.set()
        assert release_archive.wait(5)
        committed.set()
        return ['object']

    @request.custody_upload
    async def upload():
        await request.begin_upload('synthetic', 'record', 'archiving')
        archived = await request.archive(archive, 'synthetic', ['local'], {})
        request.stored(['local'], archived)
        return JSONResponse(status_code=202, content={'status': 'queued'})

    scopes: list[anyio.CancelScope] = []

    async def handler():
        if cancel != 'anyio_scope':
            return await upload()
        with anyio.CancelScope() as scope:
            scopes.append(scope)
            return await upload()

    task = asyncio.ensure_future(handler())
    try:
        assert await _thread_wait(entered, 5)
        if cancel == 'anyio_scope':
            scopes[0].cancel()
        else:
            task.cancel()
            if cancel == 'double':
                for _ in range(3):
                    await asyncio.sleep(0)
                task.cancel()
        # The handler exits at once; the archive is still writing on its thread.
        done, _ = await asyncio.wait({task}, timeout=2)
        assert done == {task}
        # The fence is still held: nothing finished it while the write runs.
        assert not await _thread_wait(finish.finished, 0.2)
        assert finish.calls == []
        assert 'custody:archiving' in held.tokens
    finally:
        release_archive.set()
    assert await _thread_wait(finish.finished, 5)
    # Finished once, after the commit, with the true (accepted) outcome.
    assert finish.calls == [(True, True)]
    assert held.tokens == {}
    assert [call['session'] for call in renewals] == ['custody:archiving']
    assert request._upload.get() is None


def test_loop_shutdown_with_a_queued_finish_still_finishes_the_token(monkeypatch):
    # SCA-3748 r5: a detached completion task queued its finish behind a busy
    # DB pool; shutting the event loop down cancelled that task, which also
    # cancelled the queued finish and stranded the token. Finish must belong to
    # the pool, not to a loop task.
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    held = _HeldBegin(monkeypatch, True)
    held.release.set()
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='test-custody-db')
    monkeypatch.setattr(request, 'db_executor', pool)
    busy, release_pool = threading.Event(), threading.Event()
    signals: dict[str, asyncio.Event] = {}

    @request.custody_upload
    async def upload():
        await request.begin_upload('synthetic', 'record', 'shutdown')
        signals['acquired'].set()
        await asyncio.Event().wait()

    async def main():
        signals['acquired'] = asyncio.Event()
        task = asyncio.ensure_future(upload())
        await asyncio.wait_for(signals['acquired'].wait(), 5)
        # Occupy the only DB worker so the finish has to queue.
        pool.submit(lambda: busy.set() or release_pool.wait(10))
        assert busy.wait(5)
        task.cancel()
        for _ in range(3):
            await asyncio.sleep(0)
        task.cancel()  # Interrupt whatever cleanup awaits, detaching it.
        await asyncio.wait({task}, timeout=2)
        assert task.done()
        # Returning shuts the loop down and cancels every remaining task.

    try:
        asyncio.run(main())
        assert held.finishes == []
        release_pool.set()
        assert held.finished.wait(5)
        assert held.finishes == [True]
        assert held.tokens == {}
    finally:
        release_pool.set()
        pool.shutdown(wait=True)


async def test_ambiguous_begin_commit_with_opt_out_on_retry_still_clears_the_token(monkeypatch):
    # SCA-3748 r5: begin's commit landed but its reply was lost, and the owner
    # opted out of sync before the retry. The retry returned False, so the
    # request skipped finish and stranded its token. The retry must recognize
    # its own exact token and report it held, so finish clears it.
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setattr(database.time, 'time', lambda: NOW)
    client = custody_client({PATH: {**ROW, 'record_upload_sessions': {}}})
    monkeypatch.setattr(database, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(record_audio, 'get_firestore_client', lambda: client)
    session = 'custody:ambiguous-opt-out'
    original_commit = StrictFirestoreTransaction._commit
    lost = []

    def commit_then_lose_reply(tx):
        original_commit(tx)
        if not lost and any(session in (patch.get('record_upload_sessions') or {}) for _, patch in tx.updates):
            lost.append(True)
            client.rows['users', 'synthetic']['private_cloud_sync_enabled'] = False
            raise ServiceUnavailable('synthetic begin response lost after commit')

    monkeypatch.setattr(StrictFirestoreTransaction, '_commit', commit_then_lose_reply)

    @request.custody_upload
    async def upload():
        await request.begin_upload('synthetic', 'record', 'ambiguous-opt-out')
        assert request.owns_upload('synthetic', 'record')
        # Opted out: the route stores nothing and refuses.
        return JSONResponse(status_code=409, content={'code': 'synthetic_refusal'})

    assert (await upload()).status_code == 409
    assert lost == [True]
    assert session not in client.rows[PATH]['record_upload_sessions']
    assert client.rows[PATH]['record_upload_revision'] == 7
    assert request._upload.get() is None


def test_begin_retry_without_its_own_token_still_honors_opt_out(monkeypatch):
    # The retry check is exact: another request's token is not this one's.
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    client = custody_client(
        {PATH: {**ROW, 'record_upload_sessions': {'custody:other': {'signal_source': 'custody_append'}}}}
    )
    allowed = database.assert_batch_write_allowed
    failed = []

    def fail_once_before_any_write(*args, **kwargs):
        if not failed:
            failed.append(True)
            client.rows['users', 'synthetic']['private_cloud_sync_enabled'] = False
            raise ServiceUnavailable('synthetic transient failure before any write')
        return allowed(*args, **kwargs)

    monkeypatch.setattr(database, 'assert_batch_write_allowed', fail_once_before_any_write)
    before = deepcopy(client.rows)
    before['users', 'synthetic']['private_cloud_sync_enabled'] = False
    assert not database.begin('synthetic', 'record', 'custody:mine', firestore_client=client)
    assert failed == [True]
    assert client.rows == before
    assert not any(tx.has_written for tx in client.transactions)


@pytest.mark.parametrize('owner', ['opted_out', 'opted_out_and_purging', 'conversation_declined'])
def test_unaccepted_finish_after_owner_opt_out_clears_only_its_own_token(owner):
    # An owner's opt-out refuses every conversation write, which stranded the
    # request's own token. Begin's opt-out rule clears exactly that token, and
    # still refuses on erasure or a conversation-level privacy decline.
    client = custody_client(
        {PATH: {**ROW, 'record_upload_sessions': {'custody:other': {'signal_source': 'custody_append'}}}}
    )
    session = 'custody:opted-out'
    assert database.begin('synthetic', 'record', session, firestore_client=client)
    if owner == 'conversation_declined':
        client.rows[PATH]['private_cloud_sync_enabled'] = False
    else:
        client.rows['users', 'synthetic']['private_cloud_sync_enabled'] = False
    if owner == 'opted_out_and_purging':
        client.rows['batch_pipeline_privacy', privacy_owner_key('synthetic')] = {'generation': 1, 'purging': True}
    before = deepcopy(client.rows)
    if owner != 'opted_out':
        with pytest.raises(BatchPrivacyBlocked):
            database.finish('synthetic', 'record', session, accepted=False, firestore_client=client)
        assert client.rows == before
        return
    with pytest.raises(BatchPrivacyBlocked):
        # Accepted bytes never bypass the conversation checks.
        database.finish('synthetic', 'record', session, accepted=True, firestore_client=client)
    assert client.rows == before
    assert database.finish('synthetic', 'record', session, accepted=False, firestore_client=client) is False
    expected = deepcopy(before)
    expected[PATH]['record_upload_sessions'].pop(session)
    assert client.rows == expected
    assert not any(path[-2] == 'record_custody_recoveries' for path in client.rows)


@pytest.mark.parametrize('late', [False, True])
def test_finish_receipt_makes_repeated_completion_read_only(monkeypatch, late):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    row = {**ROW, 'record_upload_sessions': {}, 'record_audio_closed': late}
    client = custody_client({PATH: row, ('users', 'synthetic'): {'private_cloud_sync_enabled': True}})
    session = 'custody:repeat'
    assert database.begin('synthetic', 'record', session, firestore_client=client)
    counter = metrics.LATE_APPEND._value.get()
    assert database.finish('synthetic', 'record', session, accepted=True, firestore_client=client) is late
    assert client.rows[PATH]['record_upload_revision'] == 8
    before = deepcopy(client.rows)
    assert database.finish('synthetic', 'record', session, accepted=True, firestore_client=client) is late
    assert not database.recover_committed('synthetic', 'record', session, firestore_client=client)
    assert client.rows == before
    assert not client.transactions[-1].has_written
    assert metrics.LATE_APPEND._value.get() == counter + int(late)


def test_begin_after_accepted_finish_replays_without_fencing_seal(monkeypatch):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setattr(database.time, 'time', lambda: NOW)
    client = custody_client({PATH: {**ROW, 'record_upload_sessions': {}}})
    session = 'custody:retry-job'
    job = {'state': 'record_pending', 'record_content_id': 'synthetic', 'owner_id': 'synthetic'}

    assert database.begin('synthetic', 'record', session, firestore_client=client)
    assert seal_refusal(job, client.rows[PATH]) == 'upload_pending'
    assert not database.finish('synthetic', 'record', session, accepted=True, firestore_client=client)
    assert not client.rows[PATH]['record_upload_sessions']
    assert seal_refusal(job, client.rows[PATH]) is None
    before = deepcopy(client.rows)
    counter = metrics.LATE_APPEND._value.get()

    assert database.begin('synthetic', 'record', session, firestore_client=client)
    assert not client.transactions[-1].has_written
    assert not database.finish('synthetic', 'record', session, accepted=True, firestore_client=client)
    assert not client.transactions[-1].has_written
    assert client.rows == before
    assert not client.rows[PATH]['record_upload_sessions']
    assert client.rows[PATH]['record_upload_revision'] == 8
    assert seal_refusal(job, client.rows[PATH]) is None
    assert metrics.LATE_APPEND._value.get() == counter


@pytest.mark.parametrize('transition_after_begin', [False, True])
@pytest.mark.parametrize('seal', ['open', 'closed', 'partial'])
async def test_finish_commit_succeeded_but_response_lost_does_not_recover_twice(
    monkeypatch, seal, transition_after_begin
):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    row = {**ROW, 'record_upload_sessions': {}, 'record_audio_closed': seal == 'closed' and not transition_after_begin}
    if seal == 'partial' and not transition_after_begin:
        row['record_audio_partial'] = {'version': 1, 'upload_revision': 7}
    client = custody_client({PATH: row, ('users', 'synthetic'): {'private_cloud_sync_enabled': True}})
    monkeypatch.setattr(database, 'get_firestore_client', lambda: client)
    recovery = Mock(side_effect=AssertionError('committed finish was misclassified as lost custody'))
    monkeypatch.setattr(database, 'recover_committed', recovery)
    original_commit = StrictFirestoreTransaction._commit
    lost = []

    def commit_then_lose_reply(tx):
        original_commit(tx)
        if not lost and any(path[-2] == 'record_custody_recoveries' for path, _ in tx.sets):
            lost.append(True)
            raise ServiceUnavailable('synthetic response lost after commit')

    monkeypatch.setattr(StrictFirestoreTransaction, '_commit', commit_then_lose_reply)
    counter = metrics.LATE_APPEND._value.get()

    @request.custody_upload
    async def upload():
        await request.begin_upload('synthetic', 'record', 'ambiguous')
        if transition_after_begin:
            client.rows[PATH]['record_audio_closed'] = seal == 'closed'
            if seal == 'partial':
                client.rows[PATH]['record_audio_partial'] = {'version': 1, 'upload_revision': 7}
        request.stored(['local'], ['committed-object'])
        return JSONResponse(status_code=202, content={'status': 'queued'})

    assert (await upload()).status_code == 202
    assert lost == [True]
    assert client.rows[PATH]['record_upload_revision'] == 8
    assert not client.rows[PATH]['record_upload_sessions']
    assert bool(client.rows[PATH].get('record_audio_partial')) is (seal != 'open')
    jobs = [value for path, value in client.rows.items() if path[0] == 'batch_pipeline_dev_jobs']
    assert len(jobs) == (seal != 'open')
    before = deepcopy(client.rows)
    assert database.finish('synthetic', 'record', 'custody:ambiguous', accepted=True, firestore_client=client) is (
        seal != 'open'
    )
    assert client.rows == before
    receipt = next(value for path, value in client.rows.items() if path[-2] == 'record_custody_recoveries')
    assert receipt['late'] is (seal != 'open')
    recovery.assert_not_called()
    assert metrics.LATE_APPEND._value.get() == counter + (seal != 'open')
    assert not client.transactions[-1].has_written


@pytest.mark.parametrize('lose_reply', [False, True])
def test_recovery_receipt_counts_once_after_a_committed_reply_is_lost(monkeypatch, lose_reply):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    client = custody_client(
        {
            PATH: {**ROW, 'record_audio_closed': True, 'record_upload_sessions': {}},
            ('users', 'synthetic'): {'private_cloud_sync_enabled': True},
        }
    )
    original_commit = StrictFirestoreTransaction._commit
    lost = []

    def commit_then_lose_reply(tx):
        original_commit(tx)
        if lose_reply and not lost and any(path[-2] == 'record_custody_recoveries' for path, _ in tx.sets):
            lost.append(True)
            raise ServiceUnavailable('synthetic recovery response lost after commit')

    monkeypatch.setattr(StrictFirestoreTransaction, '_commit', commit_then_lose_reply)
    counter = metrics.LATE_APPEND._value.get()
    assert database.recover_committed('synthetic', 'record', 'custody:lost', firestore_client=client)
    before = deepcopy(client.rows)
    assert not database.recover_committed('synthetic', 'record', 'custody:lost', firestore_client=client)
    assert client.rows == before
    assert client.rows[PATH]['record_upload_revision'] == 8
    assert len([path for path in client.rows if path[0] == 'batch_pipeline_dev_jobs']) == 1
    assert lost == ([True] if lose_reply else [])
    assert metrics.LATE_APPEND._value.get() == counter + 1
    assert not client.transactions[-1].has_written


@pytest.mark.parametrize('transition', ['none', 'closed', 'partial', 'lapsed'])
@pytest.mark.parametrize('lose_reply', [False, True])
async def test_post_storage_late_observation_survives_repair_and_renewal_reply_loss(
    monkeypatch, transition, lose_reply
):
    monkeypatch.delenv('RECORD_TOKEN_LEASE_MODE', raising=False)
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setattr(database.time, 'time', lambda: NOW)
    client = custody_client(
        {
            PATH: {**ROW, 'record_audio_closed': False, 'record_upload_sessions': {}},
            ('users', 'synthetic'): {'private_cloud_sync_enabled': True},
        }
    )
    monkeypatch.setattr(database, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(record_audio, 'get_firestore_client', lambda: client)
    counter = metrics.LATE_APPEND._value.get()
    objects = []
    lost = []
    original_commit = StrictFirestoreTransaction._commit

    def commit_then_lose_renewal_reply(tx):
        original_commit(tx)
        if lose_reply and objects and not lost:
            lost.append(True)
            raise ServiceUnavailable('synthetic renewal response lost after commit')

    monkeypatch.setattr(StrictFirestoreTransaction, '_commit', commit_then_lose_renewal_reply)

    def archive(uid, paths, metadata):
        assert metrics.LATE_APPEND._value.get() == counter
        row = client.rows[PATH]
        if transition == 'closed':
            row['record_audio_closed'] = True
        elif transition == 'partial':
            row['record_audio_partial'] = {'version': 1, 'upload_revision': 7}
        elif transition == 'lapsed':
            row['record_upload_sessions']['older'] = deepcopy(ROW['record_upload_sessions']['s'])
        objects.extend(paths)  # The durable commit precedes the renewal transaction.
        return ['archive:' + path for path in paths]

    @request.custody_upload
    async def upload():
        await request.begin_upload('synthetic', 'record', 'post-storage')
        paths = ['local-a', 'local-b']
        archived = await request.archive(archive, 'synthetic', paths, {})
        request.stored(paths, archived)
        assert metrics.LATE_APPEND._value.get() == counter
        return JSONResponse(status_code=202, content={'status': 'queued'})

    assert (await upload()).status_code == 202
    assert objects == ['local-a', 'local-b']
    assert lost == ([True] if lose_reply else [])
    assert metrics.LATE_APPEND._value.get() == counter + (transition != 'none')
    before = deepcopy(client.rows)
    assert database.finish(
        'synthetic', 'record', 'custody:post-storage', accepted=True, late_observed=True, firestore_client=client
    ) is (transition != 'none')
    assert client.rows == before
    assert metrics.LATE_APPEND._value.get() == counter + (transition != 'none')


@pytest.mark.parametrize('failure', ['archive', 'partial_archive', 'refused'])
async def test_post_storage_observation_never_counts_failed_or_refused_append(monkeypatch, failure):
    monkeypatch.delenv('RECORD_TOKEN_LEASE_MODE', raising=False)
    monkeypatch.setattr(database.time, 'time', lambda: NOW)
    client = custody_client({PATH: {**ROW, 'record_audio_closed': False, 'record_upload_sessions': {}}})
    monkeypatch.setattr(database, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(record_audio, 'get_firestore_client', lambda: client)
    counter = metrics.LATE_APPEND._value.get()

    committed = []

    def archive(uid, paths, metadata):
        client.rows[PATH]['record_audio_closed'] = True
        if failure == 'partial_archive' and 'local-a' in paths:
            committed.append('archive:local-a')
        if failure == 'archive' or (failure == 'partial_archive' and 'local-b' in paths):
            raise OSError('synthetic durable commit failed')
        return ['archive:local-a'] if failure == 'partial_archive' else ['archive:' + path for path in paths]

    @request.custody_upload
    async def upload():
        await request.begin_upload('synthetic', 'record', 'refused')
        paths = ['local-a', 'local-b']
        archived = await request.archive(archive, 'synthetic', paths, {})
        request.stored(paths, archived)
        return JSONResponse(status_code=202, content={'status': 'failed' if failure == 'refused' else 'queued'})

    if failure in {'archive', 'partial_archive'}:
        with pytest.raises(OSError):
            await upload()
    else:
        assert (await upload()).status_code == 202
    assert client.rows[PATH]['record_upload_revision'] == 7
    assert metrics.LATE_APPEND._value.get() == counter
    if failure == 'partial_archive':
        assert committed == ['archive:local-a']


def test_finish_observes_its_own_lapsed_lease_after_durable_acceptance(monkeypatch):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setattr(database.time, 'time', lambda: NOW)
    client = custody_client({PATH: {**ROW, 'record_upload_sessions': {}, 'record_audio_closed': False}})
    assert database.begin('synthetic', 'record', 'custody:late', firestore_client=client)
    client.rows[PATH]['record_upload_sessions']['custody:late'].update(
        last_signal_at=NOW - 7200, lease_expires_at=NOW - 1
    )
    counter = metrics.LATE_APPEND._value.get()
    assert database.finish('synthetic', 'record', 'custody:late', accepted=True, firestore_client=client)
    assert client.rows[PATH]['record_upload_revision'] == 8
    assert metrics.LATE_APPEND._value.get() == counter + 1
