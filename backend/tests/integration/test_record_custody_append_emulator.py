"""Real custody observations and finish receipts after committed reply loss."""

import hashlib
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import Mock
from types import SimpleNamespace

from google.api_core.exceptions import ServiceUnavailable
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest
from starlette.responses import JSONResponse

from config.record_audio import record_identity
from database import record_custody_append as custody, record_token_lease_metrics as metrics, record_audio
from database.batch_pipeline_record_lease_recovery import recovery_segment
from database.batch_pipeline_store import promote_record_recoveries
from database.batch_pipeline_privacy import BatchPrivacyBlocked, privacy_owner_key
from database import record_recovery_gate, record_custody_receipts as receipts
from utils.batch_pipeline.record_seal_budget import SweepBudget
from utils.sync.stage import collection_name
from utils.sync import record_token_lease as request

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv('FIRESTORE_EMULATOR_HOST', '').startswith(('127.0.0.1:', 'localhost:')),
        reason='isolated loopback Firestore emulator required',
    ),
]


def _emulator_client():
    # Match the configured isolated project: a second project can require a
    # cold database bootstrap after the CLI has reported the emulator ready.
    project = os.environ.get('GOOGLE_CLOUD_PROJECT') or 'demo-omi-listen-stack'
    if not project.startswith('demo-'):
        raise ValueError('custody emulator proofs require a demo project')
    return firestore.Client(project=project, credentials=AnonymousCredentials())


@pytest.mark.parametrize('lose_reply', [False, True])
@pytest.mark.parametrize('seal', ['open', 'closed', 'partial'])
async def test_finish_receipt_survives_a_real_committed_transaction(monkeypatch, tmp_path, lose_reply, seal):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    client = _emulator_client()
    uid, cid, session = 'synthetic-r4-' + uuid.uuid4().hex, 'record', 'custody:ambiguous'
    user = client.collection('users').document(uid)
    row = user.collection('conversations').document(cid)
    receipt = row.collection('record_custody_recoveries').document(hashlib.sha256(session.encode()).hexdigest())
    user.set({'private_cloud_sync_enabled': True})
    row.set(
        {
            'record_lane_owner': 'batch_live_v1',
            'status': 'completed',
            'private_cloud_sync_enabled': True,
            'record_audio_closed': seal == 'closed',
            'record_audio_partial': {'version': 1, 'upload_revision': 7} if seal == 'partial' else None,
            'record_upload_revision': 7,
            'record_upload_sessions': {},
            'finished_at': datetime.now(timezone.utc),
        }
    )
    monkeypatch.setattr(custody, 'get_firestore_client', lambda: client)
    recovery = Mock(side_effect=AssertionError('committed finish was recovered a second time'))
    monkeypatch.setattr(custody, 'recover_committed', recovery)
    original_commit = client._firestore_api.commit
    lost = []

    def commit_then_lose_reply(*args, **kwargs):
        result = original_commit(*args, **kwargs)
        rpc = kwargs.get('request') or args[0]
        if lose_reply and not lost and any(write.update.name.endswith('/' + receipt.path) for write in rpc['writes']):
            # The real emulator has committed both the revision and receipt.
            # Only the response is lost; run_transactional must re-read them.
            assert receipt.get().exists
            lost.append(True)
            raise ServiceUnavailable('synthetic response lost after real commit')
        return result

    monkeypatch.setattr(client._firestore_api, 'commit', commit_then_lose_reply)
    counter = metrics.LATE_APPEND._value.get()
    response = JSONResponse(status_code=202, content={'status': 'queued'})
    artifact = tmp_path / 'committed-audio'

    @request.custody_upload
    async def upload():
        await request.begin_upload(uid, cid, 'ambiguous')
        artifact.write_bytes(b'synthetic retained audio')
        request.stored(['local-audio'], [str(artifact)])
        return response

    try:
        assert await upload() is response
        current = row.get().to_dict()
        assert current['record_upload_revision'] == 8
        assert not current['record_upload_sessions']
        assert bool(current.get('record_audio_partial')) is (seal != 'open')
        assert receipt.get().to_dict()['upload_revision'] == 8
        assert receipt.get().to_dict()['late'] is (seal != 'open')
        continuation = client.collection('batch_pipeline_dev_jobs').document(recovery_segment(uid, cid)).get()
        assert continuation.exists is (seal != 'open')
        continuation_before = continuation.to_dict()
        assert lost == ([True] if lose_reply else [])
        assert artifact.read_bytes() == b'synthetic retained audio'
        assert custody.finish(uid, cid, session, accepted=True, firestore_client=client) is (seal != 'open')
        assert row.get().to_dict() == current
        assert continuation.reference.get().to_dict() == continuation_before
        recovery.assert_not_called()
        assert metrics.LATE_APPEND._value.get() == counter + (seal != 'open')
    finally:
        # Only this test's exact synthetic owner and document ids are removed.
        for job_id in (record_identity(uid, cid)[1], recovery_segment(uid, cid)):
            ref = client.collection('batch_pipeline_dev_jobs').document(job_id)
            if (ref.get().to_dict() or {}).get('owner_id') == uid:
                ref.delete()
        receipt.delete()
        row.delete()
        user.delete()
        client.close()


@pytest.mark.parametrize('lose_reply', [False, True])
@pytest.mark.parametrize('transition', ['none', 'closed', 'lapsed'])
async def test_shadow_observes_post_storage_state_through_real_renewal_reply_loss(
    monkeypatch, tmp_path, lose_reply, transition
):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'shadow')
    client = _emulator_client()
    uid, cid = 'synthetic-post-storage-' + uuid.uuid4().hex, 'record'
    user = client.collection('users').document(uid)
    row = user.collection('conversations').document(cid)
    user.set({'private_cloud_sync_enabled': True})
    row.set(
        {
            'record_lane_owner': 'batch_live_v1',
            'record_audio_closed': False,
            'record_upload_revision': 7,
            'record_upload_sessions': {},
        }
    )
    monkeypatch.setattr(record_audio, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(custody, 'get_firestore_client', lambda: client)
    original_commit = client._firestore_api.commit
    artifact = tmp_path / 'durable-shadow-audio'
    lost = []

    def commit_then_lose_reply(*args, **kwargs):
        result = original_commit(*args, **kwargs)
        if lose_reply and artifact.exists() and not lost:
            lost.append(True)
            raise ServiceUnavailable('synthetic renewal response lost after real commit')
        return result

    monkeypatch.setattr(client._firestore_api, 'commit', commit_then_lose_reply)
    counter = metrics.LATE_APPEND._value.get()

    def archive(owner, paths, metadata):
        if transition == 'closed':
            row.update({'record_audio_closed': True})  # Repair wins before bytes land.
        elif transition == 'lapsed':
            now = datetime.now(timezone.utc).timestamp()
            row.update(
                {
                    'record_upload_sessions': {
                        'older': {
                            'pod': 'synthetic-pusher',
                            'process_started_at': now - 86400,
                            'last_signal_at': now - 7200,
                            'lease_expires_at': now - 3600,
                            'signal_source': 'frames',
                        }
                    }
                }
            )
        artifact.write_bytes(b'synthetic durable shadow bytes')
        assert metrics.LATE_APPEND._value.get() == counter
        return [str(artifact)]

    @request.custody_upload
    async def upload():
        await request.begin_upload(uid, cid, 'shadow')
        paths = ['local-audio']
        archived = await request.archive(archive, uid, paths, {})
        request.stored(paths, archived)
        assert metrics.LATE_APPEND._value.get() == counter
        return JSONResponse(status_code=202, content={'status': 'queued'})

    try:
        assert (await upload()).status_code == 202
        assert lost == ([True] if lose_reply else [])
        assert artifact.read_bytes() == b'synthetic durable shadow bytes'
        assert metrics.LATE_APPEND._value.get() == counter + (transition != 'none')
        assert row.get().to_dict()['record_upload_revision'] == 7
    finally:
        # Exact synthetic owner only; this view creates no receipts or jobs.
        monkeypatch.setattr(client._firestore_api, 'commit', original_commit)
        row.delete()
        user.delete()
        client.close()


@pytest.mark.parametrize('mode', ['off', 'shadow', 'serve'])
@pytest.mark.parametrize('has_intake', [False, True])
def test_old_worker_cannot_run_recovery_before_original_publication(monkeypatch, mode, has_intake):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    client = _emulator_client()
    uid, cid = 'synthetic-gate-' + uuid.uuid4().hex, 'record'
    user = client.collection('users').document(uid)
    row = user.collection('conversations').document(cid)
    content, original = record_identity(uid, cid)
    original_ref = client.collection('batch_pipeline_dev_jobs').document(original)
    recovery_ref = client.collection('batch_pipeline_dev_jobs').document(recovery_segment(uid, cid))
    intake = client.collection('batch_pipeline_dev_intakes').document('bp_' + content)
    ledger = user.collection(collection_name('sync_content_ledger')).document(content)
    receipt = row.collection('record_custody_recoveries').document(hashlib.sha256(b'custody:gate').hexdigest())
    now = 2_000_000_000.0
    monkeypatch.setattr(custody, 'time', SimpleNamespace(time=lambda: now))
    user.set({'private_cloud_sync_enabled': True})
    row.set(
        {
            'status': 'processing',
            'record_lane_owner': 'batch_live_v1',
            'private_cloud_sync_enabled': True,
            'finished_at': datetime.now(timezone.utc),
            'record_audio_closed': False,
            'record_upload_revision': 7,
            'record_upload_sessions': {},
        }
    )
    original_ref.set({'state': 'committed' if has_intake else 'ready', 'record_input_upload_revision': 7})
    if has_intake:
        intake.set({'content_id': content})
        ledger.set({'status': 'processing'})
    try:
        assert custody.begin(uid, cid, 'custody:gate', firestore_client=client)
        custody.finish(uid, cid, 'custody:gate', accepted=True, firestore_client=client)
        assert recovery_ref.get().to_dict()['state'] == record_recovery_gate.WAITING_STATE
        monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', mode)
        # Same bounded promotion entrypoint as the active production repair CronJob.
        assert promote_record_recoveries(client, 'batch_pipeline_dev', now + 1, 10) == 0
        # Literal old-worker query: it has no lease_recovery check and sees no
        # runnable obligation, even if the current worker image rolls back.
        old_due = client.collection('batch_pipeline_dev_jobs').where('state', '==', 'record_pending').stream()
        assert recovery_ref.id not in [doc.id for doc in old_due]
        if has_intake:
            ledger.update({'status': 'completed'})
        else:
            original_ref.update({'state': 'committed'})
        assert promote_record_recoveries(client, 'batch_pipeline_dev', now + 62, 10) == 1
        assert recovery_ref.get().to_dict()['state'] == 'record_pending'
    finally:
        for ref in (receipt, recovery_ref, original_ref, intake, ledger, row, user):
            ref.delete()
        client.close()


@pytest.mark.parametrize('operation', ['finish_refused', 'finish_accepted', 'recover_committed'])
def test_finish_after_erasure_enumeration_cannot_create_an_orphan_receipt(monkeypatch, operation):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    client = _emulator_client()
    uid, cid, session = 'synthetic-erase-' + uuid.uuid4().hex, 'record', 'custody:erasure'
    user = client.collection('users').document(uid)
    row = user.collection('conversations').document(cid)
    receipt = row.collection('record_custody_recoveries').document(hashlib.sha256(session.encode()).hexdigest())
    privacy = client.collection('batch_pipeline_privacy').document(privacy_owner_key(uid))
    user.set({'private_cloud_sync_enabled': True})
    # No finished_at: prepare_recovery returns before its own privacy walk.
    row.set(
        {
            'record_lane_owner': 'batch_live_v1',
            'private_cloud_sync_enabled': True,
            'record_upload_revision': 7,
            'record_upload_sessions': {},
        }
    )
    assert custody.begin(uid, cid, session, firestore_client=client)
    # Real erasure fences the owner BEFORE enumerating/deleting children. An
    # already-begun upload may finish after that enumeration, while the parent
    # still exists; it must not create an unseen receipt beneath that parent.
    privacy.set({'generation': 1, 'blocked': True, 'purging': True})
    assert list(row.collections()) == []
    try:
        with pytest.raises(BatchPrivacyBlocked):
            if operation == 'recover_committed':
                row.update({'record_upload_sessions': {}})
                custody.recover_committed(uid, cid, session, firestore_client=client)
            else:
                custody.finish(uid, cid, session, accepted=operation == 'finish_accepted', firestore_client=client)
        assert row.get().to_dict()['record_upload_revision'] == 7
        row.delete()
        user.delete()
        assert not receipt.get().exists
        assert privacy.get().to_dict()['blocked']  # The erasure authority intentionally survives.
    finally:
        # Main's privacy write fence forbids deleting an erasure authority.
        # This synthetic owner's tombstone dies with the isolated emulator.
        for ref in (receipt, row, user):
            ref.delete()
        client.close()


def test_frame_registration_committed_reply_loss_preserves_append_late(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    client = _emulator_client()
    uid, cid = 'synthetic-register-' + uuid.uuid4().hex, 'record'
    user = client.collection('users').document(uid)
    row = user.collection('conversations').document(cid)
    now = datetime.now(timezone.utc).timestamp()
    user.set({'private_cloud_sync_enabled': True})
    row.set(
        {
            'record_lane_owner': 'batch_live_v1',
            'record_upload_revision': 7,
            'record_upload_sessions': {
                'old': {
                    'pod': 'old',
                    'process_started_at': now - 8000,
                    'last_signal_at': now - 7200,
                    'lease_expires_at': now - 3600,
                    'signal_source': 'frames',
                }
            },
        }
    )
    commit = client._firestore_api.commit
    lost = []

    def lose_reply(*args, **kwargs):
        result = commit(*args, **kwargs)
        if not lost:
            lost.append(True)
            raise ServiceUnavailable('committed frame registration response lost')
        return result

    monkeypatch.setattr(client._firestore_api, 'commit', lose_reply)
    observed = {}
    try:
        assert record_audio.set_record_upload_pending(
            uid,
            cid,
            'new',
            True,
            producer={'pod': 'new', 'process_started_at': now},
            late_observation=observed,
            firestore_client=client,
        )
        assert lost == [True] and observed == {'late': True}
        assert row.get().to_dict()['record_upload_revision'] == 8
        assert row.get().to_dict()['record_upload_sessions']['new']['append_late']
    finally:
        monkeypatch.setattr(client._firestore_api, 'commit', commit)
        row.delete()
        user.delete()
        client.close()


def test_expiry_prunes_only_receipts_and_keeps_audio_and_recovery(monkeypatch, tmp_path):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'off')  # Rollback does not disable expiry.
    client = _emulator_client()
    uid, cid = 'synthetic-expiry-' + uuid.uuid4().hex, 'record'
    user = client.collection('users').document(uid)
    row = user.collection('conversations').document(cid)
    expired = row.collection('record_custody_recoveries').document('expired')
    live_receipt = row.collection('record_custody_recoveries').document('active')
    recovery = client.collection('batch_pipeline_dev_jobs').document(recovery_segment(uid, cid))
    audio = tmp_path / 'raw-audio'
    audio.write_bytes(b'synthetic retained audio')
    now = datetime.now(timezone.utc).timestamp()
    row.set({'raw_audio': str(audio), 'record_upload_revision': 8})
    expired.set({'recorded_at': now - receipts.RETENTION_SECONDS - 1, 'accepted': True})
    live_receipt.set({'recorded_at': now, 'expires_at': receipts.expires_at(now), 'accepted': True})
    recovery.set({'state': 'record_recovery_waiting', 'owner_id': uid})
    before = row.get().to_dict(), recovery.get().to_dict()
    try:
        assert receipts.prune(client, now=now, budget=SweepBudget(30)) == 1
        assert not expired.get().exists and live_receipt.get().exists
        assert (row.get().to_dict(), recovery.get().to_dict()) == before
        assert audio.read_bytes() == b'synthetic retained audio'
    finally:
        for ref in (expired, live_receipt, recovery, row, user):
            ref.delete()
        client.close()


def test_parked_recovery_has_a_real_privacy_blocked_exit(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    client = _emulator_client()
    uid, cid, session = 'synthetic-gate-privacy-' + uuid.uuid4().hex, 'record', 'custody:privacy-gate'
    user = client.collection('users').document(uid)
    row = user.collection('conversations').document(cid)
    _, original = record_identity(uid, cid)
    original_ref = client.collection('batch_pipeline_dev_jobs').document(original)
    recovery = client.collection('batch_pipeline_dev_jobs').document(recovery_segment(uid, cid))
    receipt = row.collection('record_custody_recoveries').document(hashlib.sha256(session.encode()).hexdigest())
    privacy = client.collection('batch_pipeline_privacy').document(privacy_owner_key(uid))
    user.set({'private_cloud_sync_enabled': True})
    row.set(
        {
            'record_lane_owner': 'batch_live_v1',
            'private_cloud_sync_enabled': True,
            'finished_at': datetime.now(timezone.utc),
            'record_upload_revision': 7,
            'record_upload_sessions': {},
        }
    )
    original_ref.set({'state': 'ready', 'record_input_upload_revision': 7})
    try:
        assert custody.begin(uid, cid, session, firestore_client=client)
        custody.finish(uid, cid, session, accepted=True, firestore_client=client)
        assert recovery.get().to_dict()['state'] == record_recovery_gate.WAITING_STATE
        privacy.set({'generation': 1, 'blocked': True, 'purging': True})
        assert not record_recovery_gate.promote(
            client, 'batch_pipeline_dev', recovery.id, datetime.now(timezone.utc).timestamp()
        )
        assert recovery.get().to_dict()['state'] == 'privacy_blocked'
    finally:
        for ref in (receipt, recovery, original_ref, row, user):
            ref.delete()
        client.close()  # The synthetic erasure authority intentionally survives until emulator shutdown.


@pytest.mark.parametrize(
    'reason', ['missing_owner', 'erasure', 'blocked', 'purging', 'privacy_declined', 'missing_row']
)
async def test_admission_refuses_before_any_synthetic_archive(monkeypatch, reason):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    client = _emulator_client()
    uid = 'synthetic-admission-' + uuid.uuid4().hex
    user = client.collection('users').document(uid)
    row = user.collection('conversations').document('record')
    privacy = client.collection('batch_pipeline_privacy').document(privacy_owner_key(uid))
    deletion = client.collection('account_deletions').document(uid)
    user.set({'private_cloud_sync_enabled': True})
    original = {'record_lane_owner': 'batch_live_v1', 'private_cloud_sync_enabled': True, 'record_upload_sessions': {}}
    row.set(original)
    if reason == 'missing_owner':
        user.delete()
    elif reason == 'erasure':
        deletion.set({'wipe_status': 'in_progress'})
    elif reason in {'blocked', 'purging'}:
        privacy.set({'generation': 1, 'blocked': reason == 'blocked', 'purging': reason == 'purging'})
    elif reason == 'privacy_declined':
        row.update({'private_cloud_sync_enabled': False})
    else:
        row.delete()
    monkeypatch.setattr(custody, 'get_firestore_client', lambda: client)
    before = row.get().to_dict()
    archive = Mock(return_value=['synthetic-object'])

    @request.custody_upload
    async def upload():
        await request.begin_upload(uid, 'record', 'denied')
        paths = await request.archive(archive, uid, ['synthetic-audio'], {})
        request.stored(['synthetic-audio'], paths)
        return JSONResponse(status_code=202, content={'status': 'queued'})

    try:
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as error:
            await upload()
        assert error.value.status_code == 503
        archive.assert_not_called()
        assert row.get().to_dict() == before
        assert list(row.collections()) == []
    finally:
        # The synthetic authority is retained until isolated emulator shutdown.
        row.delete()
        user.delete()
        deletion.delete()
        client.close()
