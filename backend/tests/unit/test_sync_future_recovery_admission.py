"""Original refused WALs get durable jobs, isolated source rows and stable re-ACKs."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config.policy import BatchUnitPolicy
from models.conversation import Conversation
from database.batch_pipeline_staging import artifact_id
from tests.unit.test_batch_pipeline_audio import pcm
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_sync_capture_time_skew import client, _default_skew
from tests.unit.test_sync_receipt_clock_anchor import anchors, RECEIVED
from utils.batch_pipeline import intake, projection
from utils.batch_pipeline.artifacts import ProtectionContext
from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem
from utils.conversations.recorded_time import write_span
from utils.stt import batch_language
from utils.sync import legacy_dark, live_overlap
from utils.sync.content_id import compute_sync_content_id
from routers import sync as router

FUTURE = datetime(2038, 1, 19, tzinfo=timezone.utc).timestamp()


@pytest.fixture
def admission(client, anchors, monkeypatch):
    import time as system_time
    from utils.sync import lanes

    # Pin the receive clock alongside the immutable anchor fixture: calendar
    # dates here must never age into a different admission/retention population.
    clock = SimpleNamespace(time=lambda: RECEIVED, monotonic=system_time.monotonic)
    monkeypatch.setattr(router, 'time', clock)
    monkeypatch.setattr(lanes, 'time', clock)
    monkeypatch.setenv('SYNC_FUTURE_CAPTURE_CLAMP_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_UPLOAD_COALESCING_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_LANGUAGE_INHERITANCE_ENABLED', 'false')
    monkeypatch.setenv('SYNC_RECORD_DECODE_FAILURE_MEMO', 'false')
    store = MemoryStore()
    store.namespace = 'batch_pipeline_dev'
    monkeypatch.setattr(intake, 'FirestoreStore', lambda *a: store)
    monkeypatch.setattr(intake, 'current_stage', lambda: 'dev')
    monkeypatch.setattr(intake, 'serving_for', lambda *a, **k: False)
    monkeypatch.setattr(intake, 'admission_language_exclusion_enabled', lambda: False)
    monkeypatch.setattr(intake, 'language_guard_enabled', lambda: False)
    monkeypatch.setattr(intake, 'resolve_batch_policy', lambda *a: BatchUnitPolicy(batch_enabled=True))
    monkeypatch.setattr(router, 'compute_sync_content_id', compute_sync_content_id)
    from utils.sync.receipt_clock import retained_source_offsets

    monkeypatch.setattr(router, 'retained_source_offsets', retained_source_offsets)
    monkeypatch.setattr(router, 'resolve_batch_policy', lambda *a: BatchUnitPolicy(batch_enabled=True))
    monkeypatch.setattr(legacy_dark, 'current_mode', lambda *a: legacy_dark.LegacySyncMode.ON)
    monkeypatch.setattr(
        intake, 'provider_config', lambda: SimpleNamespace(pool_kind='dedicated_batch', max_unit_seconds=600)
    )
    monkeypatch.setattr(
        batch_language,
        'resolve_language',
        lambda *a, **k: SimpleNamespace(
            language='en', parakeet_safe=True, evidence=None, confidence=1.0, probe_seconds=0.0
        ),
    )

    def authorize(_store, _work, snapshots):
        snapshots['user'] = {'language': 'en'}
        snapshots['conversations'] = {}
        return ProtectionContext('standard', 0)

    monkeypatch.setattr(intake, 'batch_artifact_authorize', authorize)
    staged = []

    def stage(item, wav):
        staged.append((item, wav))
        uri = 'gs://synthetic/audio#1'
        store.rows['artifacts', artifact_id(item.segment_id, uri)] = {
            'owner_id': item.owner_id,
            'privacy_generation': item.privacy_generation,
            'uri': uri,
        }
        return uri

    monkeypatch.setattr(intake, 'artifacts_for', lambda *a: SimpleNamespace(stage_audio=stage))

    async def batch_route(**kwargs):
        return router.RecordUploadRoute.BATCH

    monkeypatch.setattr(router, 'registered_record_response', batch_route)
    monkeypatch.setattr(router, 'accept_batch_upload', intake.accept_upload)
    return client, store, anchors, staged


def upload(client, name, payload):
    return client.post('/v2/sync-local-files', files=[('files', (name, payload, 'application/octet-stream'))])


@pytest.mark.parametrize('stamp', [1956528000, 2114380800, 2147472000])
def test_previously_refused_original_name_is_admitted_and_retries_reack_existing_job(
    admission, tmp_path, monkeypatch, stamp
):
    client, store, anchors, staged = admission
    path = Path(pcm(tmp_path, stamp, 16000))
    payload, name = path.read_bytes(), path.name
    monkeypatch.setenv('SYNC_FUTURE_CAPTURE_CLAMP_ENABLED', 'false')
    refused = upload(client, name, payload)
    assert refused.status_code == 400 and refused.json()['code'] == 'invalid_capture_time'
    assert not store.rows and not anchors.rows
    monkeypatch.setenv('SYNC_FUTURE_CAPTURE_CLAMP_ENABLED', 'true')
    accepted = upload(client, name, payload)
    assert accepted.status_code == 202, accepted.text
    result = accepted.json()
    assert result['job_id'] and result['status'] == 'queued' and result['total_files'] == 1
    jobs = {key: row for (table, key), row in store.rows.items() if table == 'jobs'}
    assert len(jobs) == 1 and all(row['capture_time_trust'] == 'untrusted' for row in jobs.values())
    before, anchor_before = deepcopy(jobs), deepcopy(anchors.rows)
    reack = upload(client, name, payload)
    assert reack.status_code == 202 and reack.json()['job_id'] == result['job_id']
    assert {key: row for (table, key), row in store.rows.items() if table == 'jobs'} == before
    assert anchors.rows == anchor_before and len(staged) == 1
    assert path.read_bytes() == payload


def test_committed_admission_with_lost_response_does_not_create_twin(admission, tmp_path, monkeypatch):
    client, store, anchors, staged = admission
    path = Path(pcm(tmp_path, int(FUTURE), 16000))
    status = intake.durable_status
    monkeypatch.setattr(intake, 'durable_status', Mock(side_effect=RuntimeError('synthetic lost response')))
    assert upload(client, path.name, path.read_bytes()).status_code == 503
    assert len([1 for table, _ in store.rows if table == 'jobs']) == 1
    before = deepcopy(anchors.rows)
    monkeypatch.setattr(intake, 'durable_status', status)
    response = upload(client, path.name, path.read_bytes())
    assert response.status_code == 202, response.text
    assert len([1 for table, _ in store.rows if table == 'jobs']) == 1
    assert len(staged) == 1 and anchors.rows == before


def test_recovered_projection_uses_source_identity_and_exposes_unknown_date():
    item = WorkItem(
        'segment',
        'synthetic',
        1800000000,
        'gs://synthetic/audio',
        2,
        Priority.DEEP,
        conversation_id='receipt-source',
        capture_time_trust='untrusted',
    )
    binding = ProjectionBinding('synthetic', 'job', 'content', ('segment',))
    payload = {
        'audio_seconds': 2,
        'speech_seconds': 1,
        'words': [{'word': 'A recovered recording.', 'timestamp': [0, 1]}],
        'diarization': {'turns': [{'start': 0, 'end': 1, 'speaker': 'SPEAKER_00'}]},
    }
    first = projection.build_incoming(item, binding, payload)
    later = projection.build_incoming(replace(item, capture_at=item.capture_at + 100), binding, payload)
    assert first['id'] == later['id'] == 'receipt-source'
    assert first['capture_time_trust'] == 'untrusted' and first['clock'] == 'imported'
    span_patch = write_span({**first, 'sync_content_revision': 1, 'sync_bridge_pending': {'expires_at': 123}})
    assert span_patch['clock'] == 'imported'
    assert set(span_patch) == {'recorded_start', 'recorded_end', 'arrival_at', 'clock'}
    assert first['sync_clock_run'] == later['sync_clock_run'] == first['id']
    assert Conversation.model_validate(first).model_dump()['capture_time_trust'] == 'untrusted'
    neighbour = {**first, 'id': 'neighbour', 'sync_clock_run': 'receipt-other'}
    assert not live_overlap.compatible_capture(first, neighbour)
    # Old row readers already partition on sync_clock_run even without trust.
    assert first['sync_clock_run'] != neighbour['sync_clock_run']


def test_mixed_http_bundle_keeps_trust_per_original_file(admission, tmp_path):
    client, store, anchors, staged = admission
    now = int(router.time.time())
    paths = [Path(pcm(tmp_path, stamp, 16000)) for stamp in [now - 10, int(FUTURE)]]
    response = client.post(
        '/v2/sync-local-files', files=[('files', (p.name, p.read_bytes(), 'application/octet-stream')) for p in paths]
    )
    assert response.status_code == 202, response.text
    items = [item for item, _ in staged]
    assert len(items) == 2
    assert sorted(item.capture_time_trust or 'trusted' for item in items) == ['trusted', 'untrusted']
    future = next(item for item in items if item.capture_time_trust)
    assert future.conversation_id.startswith('receipt-')


@pytest.mark.slow
def test_547_synthetic_refusals_replay_original_names_without_negative_cache(admission, tmp_path, monkeypatch):
    """Synthetic filenames, not the owner's unavailable request payloads."""
    client, store, anchors, staged = admission
    uploads = []
    for index in range(547):
        stamp = [1956528000, 2114380800, 2147472000][index % 3] + index
        path = Path(pcm(tmp_path, stamp, 160))
        uploads.append(('files', (path.name, path.read_bytes(), 'application/octet-stream')))
    batches = [uploads[start : start + 16] for start in range(0, len(uploads), 16)]
    monkeypatch.setenv('SYNC_FUTURE_CAPTURE_CLAMP_ENABLED', 'false')
    for file in uploads:
        refused = client.post('/v2/sync-local-files', files=[file])
        assert refused.status_code == 400 and refused.json()['code'] == 'invalid_capture_time', refused.text
    assert not store.rows and not anchors.rows
    monkeypatch.setenv('SYNC_FUTURE_CAPTURE_CLAMP_ENABLED', 'true')
    receipts = []
    for files in batches:
        response = client.post('/v2/sync-local-files', files=files)
        assert response.status_code == 202, response.text
        receipts.append(response.json()['job_id'])
    jobs = {key: row for (table, key), row in store.rows.items() if table == 'jobs'}
    assert len(jobs) == len(staged) == len(anchors.rows) == 547
    assert len({row['conversation_id'] for row in jobs.values()}) == 547
    for files, job_id in zip(batches, receipts):
        response = client.post('/v2/sync-local-files', files=files)
        assert response.status_code == 202 and response.json()['job_id'] == job_id
    assert len(staged) == 547
    assert {key: row for (table, key), row in store.rows.items() if table == 'jobs'} == jobs


def test_requeued_estimate_with_run_token_meets_existing_upload_contract(admission, tmp_path, monkeypatch):
    client, store, anchors, staged = admission
    monkeypatch.setenv('BATCH_PIPELINE_UPLOAD_COALESCING_ENABLED', 'false')
    stamp = int(router.time.time()) - 10
    path = Path(pcm(tmp_path, stamp, 16000)).rename(tmp_path / f'audio_omi_pcm16_16000_clkerequeued_{stamp}.bin')
    response = client.post(
        '/v2/sync-local-files',
        headers={'X-App-Platform': 'ios', 'X-Device-Id-Hash': 'abcd1234'},
        files=[('files', (path.name, path.read_bytes(), 'application/octet-stream'))],
    )
    assert response.status_code == 202, response.text
    result = response.json()
    assert result['job_id'] and result['status'] == 'queued' and result['total_files'] == 1
    assert result['total_segments'] == 1 and result['poll_after_ms'] > 0
    assert staged[0][0].capture_time_trust == 'untrusted'
    assert staged[0][0].conversation_id.startswith('receipt-')
    assert staged[0][0].capture_at == stamp
    assert result['lane'] == 'backfill'
    assert not anchors.rows  # The client's estimate is not replaced by a future-clock anchor.


@pytest.mark.parametrize('enabled', ['true', 'false'])
def test_changed_bundle_after_future_skew_clears_keeps_recovery_identity(admission, tmp_path, monkeypatch, enabled):
    import time as system_time
    from utils.sync import lanes

    client, store, anchors, staged = admission
    received = int(system_time.time())
    clock = SimpleNamespace(time=lambda: received, monotonic=system_time.monotonic)
    monkeypatch.setattr(router, 'time', clock)
    monkeypatch.setattr(lanes, 'time', clock)
    first = Path(pcm(tmp_path, received + 86400 + 300, 16000))
    assert upload(client, first.name, first.read_bytes()).status_code == 202
    original = staged[0][0]
    monkeypatch.setattr(router, 'time', SimpleNamespace(time=lambda: received + 700, monotonic=system_time.monotonic))
    monkeypatch.setattr(lanes, 'time', SimpleNamespace(time=lambda: received + 700))
    monkeypatch.setenv('SYNC_FUTURE_CAPTURE_CLAMP_ENABLED', enabled)
    sibling = Path(pcm(tmp_path, received + 690, 16000))
    response = client.post(
        '/v2/sync-local-files',
        files=[('files', (p.name, p.read_bytes(), 'application/octet-stream')) for p in (first, sibling)],
    )
    assert response.status_code == 202, response.text
    recovered = next(item for item, _ in staged[1:] if item.capture_time_trust == 'untrusted')
    assert recovered.capture_at == original.capture_at
    assert recovered.conversation_id == original.conversation_id
    assert response.json()['lane'] == 'backfill'


@pytest.mark.parametrize('token', [False, True])
def test_recovery_discards_stale_legacy_conversation_target(admission, tmp_path, monkeypatch, token):
    client, store, anchors, staged = admission
    verified_targets = []

    def verify(_token, _uid, _device, target, _names):
        verified_targets.append(target)
        return None

    monkeypatch.setattr(router, 'verify_capture_manifest', verify)
    stamp = int(FUTURE) if not token else int(router.time.time()) - 10
    path = Path(pcm(tmp_path, stamp, 16000))
    if token:
        path = path.rename(tmp_path / f'audio_omi_pcm16_16000_clkerequeued_{stamp}.bin')
    response = client.post(
        '/v2/sync-local-files?conversation_id=stale-live-conversation',
        files=[('files', (path.name, path.read_bytes(), 'application/octet-stream'))],
    )
    assert response.status_code == 202, response.text
    assert staged[0][0].capture_time_trust == 'untrusted'
    assert staged[0][0].conversation_id.startswith('receipt-')
    assert staged[0][0].conversation_id != 'stale-live-conversation'
    assert verified_targets == ['stale-live-conversation']
