"""Measure accepted uploads and authenticated batch status polls over real HTTP routes."""

import os
from pathlib import Path
import shutil
import struct
import time
from urllib.parse import urlsplit
from uuid import uuid4

import fakeredis
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from database import _client, redis_db, sync_jobs
from database.batch_pipeline_privacy import advance_privacy_generation, finish_privacy_purge
from database.batch_pipeline_store import FirestoreStore
from routers import sync
from testing.firestore_read_budget import assert_read_budget, delta_reads, reads_for_caller, snapshot_reads
from tests.unit.test_batch_pipeline_artifacts import ObjectClient
from utils import fair_use
from utils.batch_pipeline import intake
from utils.batch_pipeline.artifact_policy import create_artifact_store
from utils.sync import legacy_dark

pytestmark = pytest.mark.integration
PRIVACY_CALLER = 'database.batch_pipeline_privacy:read'


@pytest.fixture
def sync_http(tmp_path, monkeypatch):
    host = os.getenv('FIRESTORE_EMULATOR_HOST', '')
    if not host:
        pytest.skip('requires a dedicated loopback Firestore emulator')
    assert urlsplit(f'http://{host}').hostname in {'127.0.0.1', 'localhost', '::1'}
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '100')
    # Match the batch privacy memo switches on the observed backend-sync
    # revision. Leave the other read levers at their source defaults.
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"bpp_generation_memo":100,"bpp_owner_memo_enforce":100}')
    monkeypatch.setattr(legacy_dark, 'current_mode', lambda uid=None: legacy_dark.LegacySyncMode.DRAINING)

    uid = f'synthetic-sync-owner-{uuid4().hex}'
    client = firestore.Client(project=f'demo-sync-budget-{uuid4().hex[:8]}', credentials=AnonymousCredentials())
    monkeypatch.setattr(_client, '_firestore_client', client)
    monkeypatch.setattr(_client, '_customer_firestore_client', client)
    monkeypatch.setattr(_client, '_data_plane_firestore_client', client)
    client.collection('users').document(uid).set(
        {'data_protection_level': 'standard', 'private_cloud_sync_enabled': False}
    )
    generation = advance_privacy_generation(client, uid, blocked=False)
    finish_privacy_purge(client, uid, generation)
    store = FirestoreStore('batch_pipeline_dev', firestore_client=client)
    redis = fakeredis.FakeRedis()
    monkeypatch.setattr(redis_db, 'r', redis)
    monkeypatch.setattr(sync_jobs, 'r', redis)
    monkeypatch.setattr(fair_use, 'redis_client', redis)

    def archive(_uid, paths, _metadata):
        archive_dir = tmp_path / 'archive'
        archive_dir.mkdir(exist_ok=True)
        return [shutil.copyfile(path, str(archive_dir / Path(path).name)) for path in paths]

    artifacts = create_artifact_store(
        store, ObjectClient(), 'synthetic-budget-bucket', b'synthetic-key-32-bytes-exactly-00'
    )
    monkeypatch.setattr(intake, 'artifacts_for', lambda _: artifacts)
    monkeypatch.setattr(sync, 'archive_mobile_batch_raw_files', archive)
    monkeypatch.setattr(sync.auth, 'verify_token', lambda token: uid if token == 'synthetic-token' else None)

    app = FastAPI()
    app.include_router(sync.router)
    try:
        with TestClient(app, headers={'Authorization': 'Bearer synthetic-token'}) as http:
            yield http, store, uid
    finally:
        client.close()


def _upload(http):
    frame = b'\x01\x00' * 16000
    pcm = (struct.pack('<I', len(frame)) + frame) * 4
    name = f'audio_omi_pcm16_16000_{int(time.time()) - 3 * 3600}.bin'
    response = http.post('/v2/sync-local-files', files={'files': (name, pcm, 'application/octet-stream')})
    assert response.status_code == 202, response.text
    job_id = response.json()['job_id']
    assert job_id.startswith('bp_'), response.text
    return job_id


def _report_and_check(scenario, delta, *, state=''):
    privacy = reads_for_caller(delta, PRIVACY_CALLER)
    print(f'{scenario} {state}: total={delta.reads:g}, privacy={privacy:g}')
    assert delta.reads > 0 and privacy > 0, delta
    assert_read_budget(scenario, delta.reads, delta)


def test_sync_upload_accept_and_request_privacy(sync_http):
    http, store, uid = sync_http
    before = snapshot_reads()
    job_id = _upload(http)
    delta = delta_reads(before)

    receipt = store.run(lambda tx: tx.get('intakes', job_id))
    assert receipt['owner_id'] == uid and len(receipt['segment_ids']) == 1
    for scenario in ('sync_upload_accept', 'sync_request_privacy'):
        _report_and_check(scenario, delta)


def test_sync_job_status_poll(sync_http):
    http, store, uid = sync_http
    job_id = _upload(http)
    path = f'/v2/sync-local-files/{job_id}'
    assert http.get(path, headers={'Authorization': ''}).status_code == 401

    def poll(expected):
        before = snapshot_reads()
        response = http.get(path)
        delta = delta_reads(before)
        assert response.status_code == 200, response.text
        assert response.json()['status'] == expected, response.text
        _report_and_check('sync_job_status_poll', delta, state=expected)
        return response.json()

    poll('queued')

    # Seed the durable state that the projection writer leaves when one unit
    # completes. The poll must read its result and re-check the published ID.
    target = 'synthetic-projected-conversation'
    store.client.collection('users').document(uid).collection('conversations').document(target).set(
        {'status': 'completed'}
    )

    def mark_completed(tx):
        receipt = tx.get('intakes', job_id)
        key = f"{uid}/{receipt['content_id']}"
        ledger = tx.get('content', key)
        segment = receipt['segment_ids'][0]
        job = tx.get('jobs', segment)
        tx.put('jobs', segment, dict(job, state='committed'))
        tx.put(
            'content',
            key,
            dict(
                ledger,
                status='completed',
                result={
                    'total_segments': 1,
                    'failed_segments': 0,
                    'errors': [],
                    'new_memories': [target],
                    'updated_memories': [],
                },
            ),
        )

    store.run(mark_completed)
    completed = poll('completed')
    assert completed['result']['new_memories'] == [target]
