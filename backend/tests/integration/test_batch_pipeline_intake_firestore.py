"""Actual encrypted intake -> automatic RPC gate -> compute -> ordered projection.

All identities/storage/model outputs are synthetic; Firestore is loopback only.
"""

from dataclasses import asdict
from io import BytesIO
import json
import os
import struct
import time
from types import SimpleNamespace
from uuid import uuid4

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_accepted_upload_drains_after_rollback_with_encrypted_context_and_accounting(tmp_path, monkeypatch):
    if not os.getenv('FIRESTORE_EMULATOR_HOST', '').startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('owned loopback emulator required; no cloud fallback')
    import fakeredis
    from database import _client, conversations, llm_usage
    from database.batch_pipeline_store import FirestoreStore
    from tests.unit.test_batch_pipeline_artifacts import ObjectClient
    from utils import fair_use
    from utils.batch_pipeline import admission, intake, pump as pump_module
    from utils.batch_pipeline.artifact_policy import create_artifact_store
    from utils.batch_pipeline.audio import read_context
    from utils.batch_pipeline.compute_client import ComputeClient
    from utils.batch_pipeline.contracts import PoolCapacity, WorkResult
    from utils.batch_pipeline.projection import Projector
    from utils.batch_pipeline.scheduler import Scheduler
    from utils.sync import reprocess

    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '100')
    client = firestore.Client(project=f'demo-pr1-a-intake-{uuid4().hex[:8]}', credentials=AnonymousCredentials())
    store = FirestoreStore(f'batch_pipeline_test_{uuid4().hex}', firestore_client=client)
    uid = f'synthetic-intake-{uuid4().hex}'
    user = client.collection('users').document(uid)
    user.set({'data_protection_level': 'standard', 'private_cloud_sync_enabled': False})
    monkeypatch.setattr(_client, '_firestore_client', client)
    monkeypatch.setattr(llm_usage, 'resolve_usage_plan_id', lambda *a, **kw: 'pro')
    monkeypatch.setattr(fair_use, 'redis_client', fakeredis.FakeRedis())
    monkeypatch.setattr(fair_use, 'FAIR_USE_ENABLED', True)
    for name in (
        'invalidate_people_stats_cache',
        '_sync_conversation_search_index',
        '_delete_conversation_search_index',
    ):
        monkeypatch.setattr(conversations, name, lambda *a, **kw: None)
    monkeypatch.setattr(
        conversations,
        'get_conversation',
        lambda owner, cid: user.collection('conversations').document(cid).get().to_dict(),
    )
    monkeypatch.setattr(reprocess, '_enqueue', lambda row: None)
    artifacts = create_artifact_store(
        store, ObjectClient(), 'synthetic-batch-bucket', b'synthetic-master-key-0123456789012345'
    )
    monkeypatch.setattr(intake, 'FirestoreStore', lambda *a, **kw: store)
    monkeypatch.setattr(intake, 'artifacts_for', lambda _: artifacts)
    path = tmp_path / 'audio_omi_pcm16_16000_1750000100.bin'
    frame = b'\x01\x00' * 16000
    path.write_bytes((struct.pack('<I', len(frame)) + frame) * 4)
    response = await intake.accept_upload(
        uid=uid,
        job_id=uuid4().hex,
        content_id=uuid4().hex,
        paths=[str(path)],
        lane='backfill',
        recording_age_seconds=10,
        source='omi',
        should_lock=False,
        conversation_id=None,
        client_device_id=None,
        client_platform='ios',
        intake_context={'geolocation': None},
    )
    assert response.status_code == 202
    job_id = json.loads(response.body)['job_id']
    state = intake.durable_status(store, uid, job_id)
    assert state['status'] == 'queued'
    segment = store.run(lambda tx: tx.get('intakes', job_id))['segment_ids'][0]
    record = store.run(lambda tx: tx.get('jobs', segment))
    assert record['requires_compute_admission'] and record['audio_uri'].endswith('#1')
    assert 'geolocation' not in record
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'false')
    monkeypatch.setattr(admission, 'reserve_backfill_speech', lambda *a: SimpleNamespace(allowed=True))

    def send(request, **kwargs):
        body = json.loads(request.data)
        return BytesIO(json.dumps(admission.authorize(store, body['leases'])).encode())

    monkeypatch.setattr(
        pump_module,
        'compute_client_from_env',
        lambda: ComputeClient(
            'https://synthetic.invalid', 'synthetic-audience', 'dev', token=lambda: 'synthetic-service-token', send=send
        ),
    )

    class Worker:
        calls = 0

        def process_batch(self, items):
            self.calls += 1
            work = items[0]
            context = read_context(artifacts.fetch_audio(work))
            assert context['job_id'] == job_id and context['owner_id'] == uid
            payload = {
                'words': [
                    {'word': word, 'timestamp': [index * 0.2, (index + 1) * 0.2]}
                    for index, word in enumerate(['We', 'discussed', 'the', 'project.'])
                ],
                'diarization': {'turns': [{'start': 0, 'end': 1, 'speaker': 'SPEAKER_00'}]},
                'audio_seconds': 4,
                'speech_seconds': 1,
                'speech_spans': [{'start': 0, 'end': 1}],
                'words_provider': 'parakeet',
            }
            return [WorkResult(work.segment_id, artifacts.persist_result(work, payload))]

    worker = Worker()
    pump = pump_module.Pump(Scheduler(store), worker, capacity=lambda: PoolCapacity(time.time(), 1))
    assert await pump.run_once() == 1
    assert worker.calls == 1
    assert intake.durable_status(store, uid, job_id)['status'] == 'processing'
    projector = Projector(store, artifacts.load_result, fetch_audio=artifacts.fetch_audio, publish=lambda *a: None)
    result = projector.project(segment)
    assert result['failed_segments'] == 0 and len(result['new_memories']) == 1
    assert intake.durable_status(store, uid, job_id)['status'] == 'completed'
    assert projector.project(segment) == result
    assert len(list(user.collection('conversations').stream())) == 1
    # A device can later upload older retained audio. The shipping app accepts202
    # and keeps its WAL until this same durable projection reports completed.
    from utils.batch_pipeline.scheduler import owner_key

    owner_before = store.run(lambda tx: tx.get('owners', owner_key(uid)))
    first_segment = segment
    late_path = tmp_path / 'audio_omi_pcm16_16000_1750000000.bin'
    late_path.write_bytes((struct.pack('<I', len(frame)) + frame) * 4)
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    late_response = await intake.accept_upload(
        uid=uid,
        job_id=uuid4().hex,
        content_id=uuid4().hex,
        paths=[str(late_path)],
        lane='backfill',
        recording_age_seconds=110,
        source='omi',
        should_lock=False,
        conversation_id=None,
        client_device_id=None,
        client_platform='ios',
        intake_context={'geolocation': None},
    )
    assert late_response.status_code == 202
    job_id = json.loads(late_response.body)['job_id']
    segment = store.run(lambda tx: tx.get('intakes', job_id))['segment_ids'][0]
    assert intake.durable_status(store, uid, job_id)['status'] == 'queued'
    late_job = store.run(lambda tx: tx.get('jobs', segment))
    assert late_job['late_capture'] and late_job['capture_at'] == 1750000000
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'false')
    assert await pump.run_once() == 1
    entry = store.run(lambda tx: tx.get('results', segment))
    assert entry['previous_segment_id'] == first_segment
    assert entry['capture_at'] == 1750000000 and entry['late_capture']
    late_result = projector.project(segment)
    assert late_result['failed_segments'] == 0
    assert intake.durable_status(store, uid, job_id)['status'] == 'completed'
    assert projector.project(segment) == late_result
    owner_after = store.run(lambda tx: tx.get('owners', owner_key(uid)))
    assert owner_after['watermark'] == owner_before['watermark']
    assert owner_after['log_tail'] == segment
    assert owner_after['projection_watermark'] == segment
    client.close()
