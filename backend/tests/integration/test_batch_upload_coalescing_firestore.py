"""Owned loopback Firestore + encrypted synthetic object IO. No paid inference."""

import json
import os
import struct
import time
import asyncio
import io
import hashlib
import wave
from dataclasses import fields
from uuid import uuid4

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def runtime(monkeypatch):
    if not os.getenv('FIRESTORE_EMULATOR_HOST', '').startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('owned loopback Firestore required; no cloud fallback')
    from database.batch_pipeline_store import FirestoreStore
    from tests.unit.test_batch_pipeline_artifacts import ObjectClient
    from utils.batch_pipeline.artifact_policy import create_artifact_store
    from utils.batch_pipeline import intake

    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '100')
    monkeypatch.setenv('BATCH_PIPELINE_UPLOAD_COALESCING_ENABLED', 'true')
    client = firestore.Client(project='demo-sca1800', credentials=AnonymousCredentials())
    store = FirestoreStore('batch_pipeline_test_' + uuid4().hex, firestore_client=client)
    uid = 'synthetic-' + uuid4().hex
    cid = 'recording-' + uuid4().hex
    user = client.collection('users').document(uid)
    user.set(
        {
            'data_protection_level': 'standard',
            'private_cloud_sync_enabled': False,
            'language': 'en',
            'transcription_preferences': {'single_language_mode': True},
        }
    )
    user.collection('conversations').document(cid).set({'id': cid, 'language': 'en', 'source': 'omi'})
    objects = ObjectClient()
    artifacts = create_artifact_store(
        store, objects, 'synthetic-batch-bucket', b'synthetic-master-key-0123456789012345'
    )
    monkeypatch.setattr(intake, 'FirestoreStore', lambda *a, **k: store)
    monkeypatch.setattr(intake, 'artifacts_for', lambda _: artifacts)
    # Exact route isolation, not a fake inference/quality result: supported
    # English declaration needs no provider probe and makes no network call.
    monkeypatch.setattr(intake.legacy_dark, 'current_mode', lambda _: intake.LegacySyncMode.DARK)
    from database.batch_pipeline_coalescing import note_scan

    note_scan(store, time.time(), producer_enabled=True)
    return store, artifacts, objects, uid, cid


def upload_args(root, uid, cid, index):
    folder = root / str(index)
    folder.mkdir()
    timestamp = 1700000000 + index
    path = folder / f'audio_synthetic_pcm16_16000_1_fs160_{timestamp}.bin'
    frame = struct.pack('<h', 1000 + index) * 160
    data = (struct.pack('<I', len(frame)) + frame) * 100
    path.write_bytes(data)
    content = f'synthetic-content-{index}'
    return {
        'uid': uid,
        'job_id': content,
        'content_id': content,
        'paths': [str(path)],
        'lane': 'fresh',
        'recording_age_seconds': 1,
        'source': 'omi',
        'should_lock': False,
        'conversation_id': cid,
        'client_device_id': 'synthetic-device',
        'client_platform': 'ios',
        'intake_context': {'recording_session_id': 'synthetic-session', 'geolocation': None},
    }, data


@pytest.mark.asyncio
@pytest.mark.parametrize('off', [False, True])
async def test_real_admission_receipts_drainer_and_off_preserve_every_original(
    runtime, tmp_path, monkeypatch, off, record_property
):
    from utils.batch_pipeline import intake
    from utils.batch_pipeline.upload_coalescing import drain_group
    from database import batch_pipeline_coalescing as rows

    store, artifacts, objects, uid, cid = runtime
    first, original1 = upload_args(tmp_path, uid, cid, 0)
    second, original2 = upload_args(tmp_path, uid, cid, 1)
    responses = [await intake.accept_upload(**args) for args in (first, second)]
    assert [response.status_code for response in responses] == [202, 202]
    ids = [json.loads(response.body)['job_id'] for response in responses]
    holds = list(store.client.collection(store.namespace + '_coalesce_groups').stream())
    assert len(holds) == 1
    group = holds[0].to_dict()
    assert len(group['members']) == 2
    assert list(store.client.collection(store.namespace + '_jobs').stream()) == []
    assert intake.durable_status(store, uid, ids[0])['status'] == 'queued'
    assert __import__('pathlib').Path(first['paths'][0]).read_bytes() == original1
    assert __import__('pathlib').Path(second['paths'][0]).read_bytes() == original2
    if off:
        monkeypatch.delenv('BATCH_PIPELINE_UPLOAD_COALESCING_ENABLED')
    else:
        rows.release_for_open(store, uid, ids[0], time.time())
    assert await drain_group(store, artifacts, holds[0].id)
    jobs = list(store.client.collection(store.namespace + '_jobs').stream())
    assert len(jobs) == (2 if off else 1)
    assert sum(job.to_dict()['duration_seconds'] for job in jobs) == 2
    from utils.batch_pipeline.contracts import WorkItem

    decoded_pcm = b''
    for snapshot in sorted(jobs, key=lambda job: job.to_dict()['capture_at']):
        data = snapshot.to_dict()
        work = WorkItem(**{field.name: data[field.name] for field in fields(WorkItem) if field.name in data})
        with wave.open(io.BytesIO(artifacts.fetch_audio(work)), 'rb') as audio:
            decoded_pcm += audio.readframes(audio.getnframes())
    assert decoded_pcm == (struct.pack('<h', 1000) * 16000 + struct.pack('<h', 1001) * 16000)
    assert sum(member['source_frames'] for member in group['members']) == 32000
    record_property('original_uploads', 2)
    record_property('source_frames', 32000)
    record_property('source_rate_hz', 16000)
    record_property(
        'original_raw_sha256',
        json.dumps([hashlib.sha256(original1).hexdigest(), hashlib.sha256(original2).hexdigest()]),
    )
    record_property('created_units', len(jobs))
    record_property('sample_conservation', 'PASS')
    record_property('persisted_units', 'NOT_MEASURED: admission-only rehearsal')
    for public in ids:
        status = intake.durable_status(store, uid, public)
        assert status['status'] == 'queued' and status['job_id'] == public
    assert store.run(lambda tx: tx.get('coalesce_quota', 'global'))['groups'] == 0
    # A redelivery/restart never emits more units.
    assert not await drain_group(store, artifacts, holds[0].id)
    assert len(list(store.client.collection(store.namespace + '_jobs').stream())) == len(jobs)
    assert objects.downloads >= 2  # Explicit artifact-observation denominator, not true units.


@pytest.mark.asyncio
async def test_held_source_is_not_reaped_and_explicit_erasure_unlinks_all_custody(runtime, tmp_path):
    from datetime import datetime, timedelta, timezone
    from database.batch_pipeline_staging import reap_one
    from database.batch_pipeline_purge import purge_batch_owner
    from utils.batch_pipeline import intake

    store, artifacts, objects, uid, cid = runtime
    args, _ = upload_args(tmp_path, uid, cid, 0)
    assert (await intake.accept_upload(**args)).status_code == 202
    artifact_docs = list(store.client.collection(store.namespace + '_artifacts').stream())
    assert len(artifact_docs) == 1
    assert not reap_one(store, artifact_docs[0].id, datetime.now(timezone.utc) + timedelta(days=3))
    deleted = []
    purge_batch_owner(
        uid,
        firestore_client=store.client,
        namespaces=(store.namespace,),
        delete_uri=lambda owner, uri: deleted.append((owner, uri)),
    )
    assert deleted
    for table in ('coalesce_groups', 'coalesce_sources', 'coalesce_heads', 'intakes'):
        assert list(store.client.collection(f'{store.namespace}_{table}').stream()) == []
    assert store.run(lambda tx: tx.get('coalesce_quota', 'global'))['groups'] == 0


@pytest.mark.asyncio
async def test_restart_after_unit_commit_before_fanout_and_off_does_not_duplicate(runtime, tmp_path, monkeypatch):
    from utils.batch_pipeline import intake
    from utils.batch_pipeline.upload_coalescing import drain_group
    from database import batch_pipeline_coalescing as rows
    from config import batch_pipeline_coalescing as config

    store, artifacts, objects, uid, cid = runtime
    args, _ = upload_args(tmp_path, uid, cid, 0)
    assert (await intake.accept_upload(**args)).status_code == 202
    snapshot = next(store.client.collection(store.namespace + '_coalesce_groups').stream())
    rows.release_for_open(store, uid, 'bp_' + args['job_id'], time.time())
    monkeypatch.setattr(config, 'LEASE_SECONDS', 1.0)
    finish = rows.finish

    def crash(*args):
        raise RuntimeError('synthetic crash before receipt fanout')

    monkeypatch.setattr(rows, 'finish', crash)
    with pytest.raises(RuntimeError, match='synthetic crash'):
        await drain_group(store, artifacts, snapshot.id)
    assert len(list(store.client.collection(store.namespace + '_jobs').stream())) == 1
    monkeypatch.setattr(rows, 'finish', finish)
    monkeypatch.setenv('BATCH_PIPELINE_UPLOAD_COALESCING_ENABLED', 'false')
    await asyncio.sleep(1.05)
    assert await drain_group(store, artifacts, snapshot.id)
    assert len(list(store.client.collection(store.namespace + '_jobs').stream())) == 1
    assert store.run(lambda tx: tx.get('coalesce_groups', snapshot.id))['mode'] == 'merged'


@pytest.mark.asyncio
async def test_revocation_during_decryption_never_creates_a_unit(runtime, tmp_path):
    from database.batch_pipeline_privacy import BatchPrivacyBlocked
    from utils.batch_pipeline import intake
    from utils.batch_pipeline.upload_coalescing import drain_group
    from database import batch_pipeline_coalescing as rows

    store, artifacts, objects, uid, cid = runtime
    args, _ = upload_args(tmp_path, uid, cid, 0)
    assert (await intake.accept_upload(**args)).status_code == 202
    snapshot = next(store.client.collection(store.namespace + '_coalesce_groups').stream())
    rows.release_for_open(store, uid, 'bp_' + args['job_id'], time.time())
    objects.after_download = (
        lambda: store.client.collection('users').document(uid).update({'data_protection_level': 'e2ee'})
    )
    with pytest.raises((BatchPrivacyBlocked, PermissionError)):
        await drain_group(store, artifacts, snapshot.id)
    assert list(store.client.collection(store.namespace + '_jobs').stream()) == []
    assert store.run(lambda tx: tx.get('intakes', 'bp_' + args['job_id']))['coalesce_group'] == snapshot.id


@pytest.mark.asyncio
async def test_release_endpoint_auth_owner_scope_and_rate_limit(runtime, tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from database import batch_pipeline_store
    from database.batch_pipeline_coalescing import note_scan
    from routers import sync
    from utils.batch_pipeline import intake

    store, artifacts, objects, uid, cid = runtime
    args, _ = upload_args(tmp_path, uid, cid, 0)
    # Cold route imports may outlive the five-second drainer heartbeat from
    # fixture setup. This auth test needs an active synthetic drainer at admission.
    note_scan(store, time.time(), producer_enabled=True)
    assert (await intake.accept_upload(**args)).status_code == 202
    snapshot = next(store.client.collection(store.namespace + '_coalesce_groups').stream())
    initial_deadline = snapshot.to_dict()['release_by']
    app = FastAPI()
    app.add_api_route('/release/{job_id}', sync.release_sync_upload_hold, methods=['POST'])
    monkeypatch.setattr(batch_pipeline_store, 'FirestoreStore', lambda *a, **k: store)
    monkeypatch.setattr(sync, 'admit_sync_job_poll', lambda _: True)
    with TestClient(app) as client:
        assert client.post('/release/bp_' + args['job_id']).status_code in {401, 403}
        app.dependency_overrides[sync.auth.get_current_user_uid] = lambda: 'foreign-synthetic-owner'
        assert client.post('/release/bp_' + args['job_id']).json() == {'accepted': True}
        assert snapshot.reference.get().to_dict()['release_by'] == initial_deadline
        app.dependency_overrides[sync.auth.get_current_user_uid] = lambda: uid
        assert client.post('/release/bp_' + args['job_id']).json() == {'accepted': True}
        assert snapshot.reference.get().to_dict()['release_by'] < initial_deadline
        monkeypatch.setattr(sync, 'admit_sync_job_poll', lambda _: False)
        assert client.post('/release/bp_' + args['job_id']).status_code == 429


@pytest.mark.asyncio
@pytest.mark.parametrize('off', [False, True])
async def test_denied_full_page_cannot_starve_other_owners_after_restart(runtime, tmp_path, monkeypatch, off):
    from database import batch_pipeline_coalescing as rows
    from database.batch_pipeline_store import FirestoreStore
    from utils.batch_pipeline import intake, upload_coalescing, artifact_policy

    store, artifacts, objects, uid, cid = runtime
    monkeypatch.setattr(artifact_policy, 'artifacts_for', lambda _: artifacts)
    denied = []
    for index in range(8):
        owner = f'{uid}-denied-{index // 2}'
        user = store.client.collection('users').document(owner)
        user.set({'language': 'en', 'data_protection_level': 'standard', 'private_cloud_sync_enabled': False})
        user.collection('conversations').document(cid).set({'id': cid, 'language': 'en', 'source': 'omi'})
        args, _ = upload_args(tmp_path, owner, cid, index)
        args['intake_context']['recording_session_id'] = f'synthetic-recording-{index}'
        rows.note_scan(store, time.time(), producer_enabled=True)
        assert (await intake.accept_upload(**args)).status_code == 202
        rows.release_for_open(store, owner, 'bp_' + args['job_id'], time.time())
        denied.append(owner)
    args, _ = upload_args(tmp_path, uid, cid, 8)
    rows.note_scan(store, time.time(), producer_enabled=True)
    assert (await intake.accept_upload(**args)).status_code == 202
    rows.release_for_open(store, uid, 'bp_' + args['job_id'], time.time())
    for owner in set(denied):
        # Model the durable refusal while a separately authorized purge is pending.
        store.client.collection('users').document(owner).update({'data_protection_level': 'e2ee'})
    if off:
        monkeypatch.setenv('BATCH_PIPELINE_UPLOAD_COALESCING_ENABLED', 'false')
    await upload_coalescing.drain(store)
    assert list(store.client.collection(store.namespace + '_jobs').stream()) == []
    epoch, boundary = rows.scan_position(store)
    assert epoch == 1 and boundary is not None
    restarted = FirestoreStore(store.namespace, firestore_client=store.client)
    await upload_coalescing.drain(restarted)
    jobs = list(store.client.collection(store.namespace + '_jobs').stream())
    assert len(jobs) == 1 and jobs[0].to_dict()['owner_id'] == uid
    quota = store.run(lambda tx: tx.get('coalesce_quota', 'global'))
    assert quota['groups'] == 8 and max(quota['owners'].values()) == 2
    for snapshot in store.client.collection(store.namespace + '_coalesce_groups').stream():
        held = snapshot.to_dict()
        if held['owner_id'] in denied:
            assert held['state'] == 'holding' and 'expires_at' not in held
    # The cursor is values, not a live snapshot: erasure of its boundary is safe.
    boundary_row = store.run(lambda tx: tx.get('coalesce_groups', boundary['id']))
    rows.purge_group(store.client, store.namespace, boundary['id'], boundary_row['owner_id'])
    assert rows.due(store.client, store.namespace, time.time(), producer_enabled=not off, after=boundary) == []
    await upload_coalescing.drain(restarted)  # End-of-range wraps durably.
    assert rows.scan_position(restarted)[1] is None


@pytest.mark.asyncio
@pytest.mark.parametrize('revoke', [False, True])
async def test_projection_completes_unpolled_originals_before_target_ttl(runtime, tmp_path, monkeypatch, revoke):
    from database import batch_pipeline_coalescing as rows
    from database.batch_pipeline_projection import ProjectionStore
    from database.batch_pipeline_projection_protocol import normalized_binding
    from database.batch_pipeline_privacy import BatchPrivacyBlocked
    from database.sync_ledger import sync_content_ledger_ref
    from utils.batch_pipeline import intake
    from utils.batch_pipeline.upload_coalescing import drain_group
    from utils.batch_pipeline.scheduler import owner_key

    store, artifacts, objects, uid, cid = runtime
    uploads = [upload_args(tmp_path, uid, cid, index)[0] for index in (0, 40)]
    for args in uploads:
        rows.note_scan(store, time.time(), producer_enabled=True)
        assert (await intake.accept_upload(**args)).status_code == 202
    held = next(store.client.collection(store.namespace + '_coalesce_groups').stream())
    rows.release_for_open(store, uid, 'bp_' + uploads[0]['job_id'], time.time())
    assert await drain_group(store, artifacts, held.id)
    jobs = list(store.client.collection(store.namespace + '_jobs').stream())
    assert len(jobs) == 2  # Gap >30s preserves distinct decoder units.
    binding = normalized_binding(jobs[0].to_dict()['projection_binding'])
    projector = ProjectionStore(store)

    def ready(snapshot):
        job = snapshot.to_dict()
        payload = {'outcome': 'expected_silence'}
        snapshot.reference.update({'result': payload})
        projector.ref('results', snapshot.id).set(
            {
                'protocol_version': 1,
                'owner_key': owner_key(uid),
                'segment_id': snapshot.id,
                'capture_at': job['capture_at'],
                'result': payload,
                'previous_segment_id': None,
                'projection_state': 'ready',
                'projection': {'state': 'ready', 'conversation_id': None, 'created': False, 'speech_seconds': 0.0},
            }
        )

    ready(jobs[0])
    assert projector.complete(jobs[0].id, binding, time.time(), {'seconds': 0.0, 'updates': {}}) is None
    originals = [sync_content_ledger_ref(store.client, uid, args['content_id']) for args in uploads]
    assert all(ref.get().to_dict()['status'] == 'processing' for ref in originals)
    ready(jobs[1])
    if revoke:
        store.client.collection('users').document(uid).update({'data_protection_level': 'e2ee'})
        with pytest.raises(BatchPrivacyBlocked):
            projector.complete(jobs[0].id, binding, time.time(), {'seconds': 0.0, 'updates': {}})
        assert all(ref.get().to_dict()['status'] == 'processing' for ref in originals)
        return
    assert projector.complete(jobs[0].id, binding, time.time(), {'seconds': 0.0, 'updates': {}}) is not None
    saved = [ref.get().to_dict() for ref in originals]
    assert all(row['status'] == 'completed' and row['result']['total_segments'] == 1 for row in saved)
    assert all('expires_at' in row for row in saved)
    # No original poll preceded completion. Model target TTL deleting before
    # original TTL (Firestore TTL deletion order is not guaranteed).
    projector.ref('intakes', binding.job_id).delete()
    sync_content_ledger_ref(store.client, uid, binding.content_id).delete()
    for snapshot in jobs:
        snapshot.reference.delete()
        projector.ref('results', snapshot.id).delete()
    for args, expected in zip(uploads, saved):
        assert intake.durable_status(store, uid, 'bp_' + args['job_id'])['status'] == 'completed'
        replay = await intake.accept_upload(**args)
        assert replay.status_code == 202 and json.loads(replay.body)['status'] == 'completed'
        assert (
            sync_content_ledger_ref(store.client, uid, args['content_id']).get().to_dict()['expires_at']
            == expected['expires_at']
        )
    assert list(store.client.collection(store.namespace + '_jobs').stream()) == []
