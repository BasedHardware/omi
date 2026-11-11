"""Custody admission rejects erased owners before raw staging or other writes."""

from copy import deepcopy
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from google.api_core.exceptions import FailedPrecondition
from starlette.responses import JSONResponse

from database import record_custody_append as custody
from database.batch_pipeline_privacy import BatchPrivacyBlocked, privacy_owner_key
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_record_token_lease import PATH, ROW
from utils.sync import record_token_lease as request


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    store = StrictFirestore(
        {('users', 'synthetic'): {'private_cloud_sync_enabled': True}, PATH: {**ROW, 'record_upload_sessions': {}}}
    )
    monkeypatch.setattr(custody, 'get_firestore_client', lambda: store)
    return store


def deny(store, reason, monkeypatch):
    if reason == 'missing_owner':
        store.rows.pop(('users', 'synthetic'))
    elif reason == 'erasure':
        store.rows['account_deletions', 'synthetic'] = {'wipe_status': 'in_progress'}
    elif reason in {'blocked', 'purging'}:
        store.rows['batch_pipeline_privacy', privacy_owner_key('synthetic')] = {'generation': 1, reason: True}
    elif reason == 'privacy_declined':
        store.rows[PATH]['private_cloud_sync_enabled'] = False
    elif reason == 'protected_owner':
        store.rows['users', 'synthetic']['data_protection_level'] = 'e2ee'
    elif reason == 'missing_row':
        store.rows.pop(PATH)
    elif reason == 'precondition':
        monkeypatch.setattr(custody, 'assert_batch_write_allowed', Mock(side_effect=FailedPrecondition('synthetic')))
    else:
        raise AssertionError(reason)


DENIALS = (
    'missing_owner',
    'erasure',
    'blocked',
    'purging',
    'privacy_declined',
    'protected_owner',
    'missing_row',
    'precondition',
)


@pytest.mark.parametrize('reason', DENIALS)
async def test_denied_admission_never_reaches_archive_or_creates_metadata(client, monkeypatch, reason):
    deny(client, reason, monkeypatch)
    before = deepcopy(client.rows)
    archive = Mock(return_value=['synthetic-object'])

    @request.custody_upload
    async def upload():
        await request.begin_upload('synthetic', 'record', 'synthetic-request')
        paths = await request.archive(archive, 'synthetic', ['synthetic-audio'], {})
        request.stored(['synthetic-audio'], paths)
        return JSONResponse(status_code=202, content={'status': 'queued'})

    with pytest.raises(HTTPException) as error:
        await upload()
    assert error.value.status_code == 503
    archive.assert_not_called()
    assert client.rows == before
    assert not any(tx.has_written for tx in client.transactions)
    assert request._upload.get() is None


@pytest.mark.parametrize('owner', [{}, {'private_cloud_sync_enabled': True}])
@pytest.mark.parametrize('lane', [None, 'batch_live_v1', 'batch_sync_v1'])
def test_existing_owner_defaults_and_valid_lane_admission_remain_supported(client, owner, lane):
    client.rows['users', 'synthetic'] = owner
    client.rows[PATH]['record_lane_owner'] = lane
    assert custody.begin('synthetic', 'record', 'custody:valid', firestore_client=client)
    assert 'custody:valid' in client.rows[PATH]['record_upload_sessions']


@pytest.mark.parametrize('reason', ['erasure', 'blocked', 'purging', 'missing_owner'])
def test_sync_opt_out_never_bypasses_owner_erasure(client, monkeypatch, reason):
    client.rows['users', 'synthetic']['private_cloud_sync_enabled'] = False
    deny(client, reason, monkeypatch)
    before = deepcopy(client.rows)
    with pytest.raises(BatchPrivacyBlocked):
        custody.begin('synthetic', 'record', 'custody:opt-out', firestore_client=client)
    assert client.rows == before
    assert not any(tx.has_written for tx in client.transactions)


def test_sync_opt_out_keeps_existing_no_custody_admission(client):
    client.rows['users', 'synthetic']['private_cloud_sync_enabled'] = False
    before = deepcopy(client.rows)
    assert not custody.begin('synthetic', 'record', 'custody:opt-out', firestore_client=client)
    assert client.rows == before
    assert not any(tx.has_written for tx in client.transactions)


@pytest.mark.parametrize('mode', ['off', 'shadow'])
def test_non_serving_begin_preserves_no_metadata_io(client, monkeypatch, mode):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', mode)
    forbidden = Mock(side_effect=AssertionError('non-serving admission performed metadata IO'))
    monkeypatch.setattr(custody, 'get_firestore_client', forbidden)
    assert not custody.begin('synthetic', 'record', 'custody:off')
    forbidden.assert_not_called()
    assert client.transactions == []


@pytest.mark.parametrize('operation', ['finish_accepted', 'finish_refused', 'recover_committed'])
@pytest.mark.parametrize('reason', ['missing_owner', 'erasure', 'purging', 'privacy_declined'])
def test_finish_and_recovery_still_refuse_privacy_changes_without_writes(client, monkeypatch, operation, reason):
    assert custody.begin('synthetic', 'record', 'custody:acquired', firestore_client=client)
    deny(client, reason, monkeypatch)
    before = deepcopy(client.rows)
    count = len(client.transactions)
    with pytest.raises(BatchPrivacyBlocked):
        if operation == 'recover_committed':
            custody.recover_committed('synthetic', 'record', 'custody:acquired', firestore_client=client)
        else:
            custody.finish(
                'synthetic',
                'record',
                'custody:acquired',
                accepted=operation == 'finish_accepted',
                firestore_client=client,
            )
    assert client.rows == before
    assert not any(tx.has_written for tx in client.transactions[count:])


@pytest.fixture
def sync_router(monkeypatch):
    # Reuse the established real-router harness, retaining the real custody
    # decorator/transaction while replacing external services with synthetic stubs.
    from tests.unit.test_sync_v2 import TestV2EndpointExecution as Harness
    from services import summary_debt_repair  # noqa: F401 - retain real imports across legacy package stubs

    saved, _, _ = Harness._build_test_app()
    try:
        spec = importlib.util.spec_from_file_location(
            'custody_privacy_sync_router', Path(__file__).parents[2] / 'routers/sync.py'
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        monkeypatch.setattr(module, 'custody_lease', request)
        module.prepare_sync_uploads = lambda files, uid: files
        module.memoized_record_wait = AsyncMock(return_value=None)
        module.get_sync_ledger_fence_mode = lambda: module.SyncLedgerFenceMode.ACTIVE
        module.resolve_client_device = lambda **kw: SimpleNamespace(
            client_device_id='synthetic-device', platform='synthetic', device_hash='synthetic', app_version='synthetic'
        )
        module.verify_capture_manifest = lambda *a: None
        module.classify_sync_lane = lambda *a, **kw: SimpleNamespace(
            lane=module.SyncLane.FRESH,
            trust=SimpleNamespace(value='device_bound'),
            maximum_age_seconds=0,
            reason='synthetic',
            oldest_capture_at=1760000000.0,
            automatic_recovery_allowed=True,
        )
        module.get_hard_restriction_status = lambda uid: (False, None)
        module.is_daily_audio_ceiling_exceeded = lambda uid: False
        module.has_transcription_credits = lambda uid: True
        module.has_byok_keys = lambda: False
        module.is_cloud_tasks_dispatch_enabled = lambda: True

        async def blocking(executor, fn, *args, **kwargs):
            return fn(*args, **kwargs)

        module.run_blocking = blocking
        monkeypatch.setattr(request, 'run_blocking', blocking)
        yield module
    finally:
        Harness._cleanup_modules(saved)


@pytest.mark.parametrize('reason', DENIALS + ('purge_after_lookup',))
@pytest.mark.parametrize('session_only', [False, True])
async def test_real_sync_endpoint_refuses_before_raw_gcs_or_admission_write(
    client, sync_router, monkeypatch, reason, session_only
):
    module = sync_router
    client.rows['users', 'synthetic', 'recording_sessions', 'synthetic-session'] = {'conversation_id': 'record'}
    before = {}
    if reason == 'purge_after_lookup':

        def early_lookup():
            deny(client, 'purging', monkeypatch)
            before.update(deepcopy(client.rows))
            return module.SyncLedgerFenceMode.ACTIVE

        module.get_sync_ledger_fence_mode = early_lookup
    else:
        deny(client, reason, monkeypatch)
        before.update(deepcopy(client.rows))
    forbidden = {}
    for name in (
        '_retrieve_file_paths_v2',
        '_stage_files_to_gcs',
        'registered_record_response',
        'accept_batch_upload',
        'create_sync_job',
        'claim_sync_content',
        'start_background_task',
        'record_product_event',
    ):
        forbidden[name] = Mock(side_effect=AssertionError('denied upload reached ' + name))
        monkeypatch.setattr(module, name, forbidden[name])
    with pytest.raises(HTTPException) as error:
        await module.sync_local_files_v2(
            files=[SimpleNamespace(filename='synthetic-1760000000.bin')],
            uid='synthetic',
            conversation_id=None if session_only else 'record',
            recording_session_id='synthetic-session' if session_only else None,
        )
    assert error.value.status_code == 503
    for call in forbidden.values():
        call.assert_not_called()
    assert client.rows == before
    assert not any(tx.has_written for tx in client.transactions)
    assert request._upload.get() is None
