"""Broken future clocks reuse receipt recovery without claiming wall-clock proof."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import io
import wave

import pytest
from fastapi.responses import JSONResponse

from tests.unit.test_sync_capture_time_skew import (
    client,
    _default_skew,
    _post_sync,
    _Upload,
)
from tests.unit.test_batch_pipeline_audio import pcm
from tests.unit.test_sync_cross_job_assignment import chunk, conversations, intake
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.batch_pipeline import capture_decode
from utils.batch_pipeline.contracts import WorkItem, Priority
from utils.sync import capture_clock, lanes
from utils.sync import legacy_segment_core as pipeline
from utils.sync.live_overlap import compatible_capture
from utils.observability.reasons import SyncCaptureTimeReason
from utils.sync.files import get_timestamp_from_path
from utils.sync.content_id import compute_sync_content_id
from routers import sync as router

# Future-window cases move with the clock instead of expiring in 2038.
FUTURE = int(datetime.now(timezone.utc).timestamp()) + 12 * 365 * 86400
NAME = f'audio_omi_pcm16_16000_clkeone_{int(FUTURE)}.bin'


@pytest.mark.parametrize(
    'ahead,accepted', [(170, True), (600, True), (601, False), (3600, False), (86400, False), (86401, True)]
)
def test_future_recovery_only_beyond_day_and_retains_normal_skew_refusal(ahead, accepted):
    now = datetime(2026, 11, 15, tzinfo=timezone.utc)
    reason = capture_clock.capture_time_rejection(now + timedelta(seconds=ahead), now=now)
    assert reason is (None if accepted else SyncCaptureTimeReason.REJECTED_FUTURE)
    assert capture_clock.maximum_future_skew_seconds() == 600


@pytest.fixture(autouse=True)
def enable_future_recovery(_default_skew, monkeypatch):
    monkeypatch.setenv('SYNC_FUTURE_CAPTURE_CLAMP_ENABLED', 'true')


def test_future_staging_keeps_filename_bytes_and_identity(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    upload = _Upload(NAME)
    original = upload.file.getvalue()
    [path] = pipeline._retrieve_file_paths_v2([upload], 'synthetic', 'job')
    assert Path(path).name == NAME and Path(path).read_bytes() == original
    assert get_timestamp_from_path(NAME) == FUTURE


def test_future_recovery_is_untrusted_backfill_and_historical_siblings_keep_lookback():
    now = datetime.now(timezone.utc).timestamp()
    decision = lanes.classify_sync_lane([NAME], client_device_id='pendant', now=now, allow_legacy_fresh=True)
    assert decision.lane is lanes.SyncLane.BACKFILL
    assert decision.trust is lanes.CaptureTimeTrust.UNTRUSTED
    assert decision.reason == 'future_capture_clamped'
    assert decision.oldest_capture_at == decision.newest_capture_at == now
    assert decision.maximum_age_seconds is None and decision.automatic_recovery_allowed
    stale = f'audio_omi_pcm16_16000_{int(now - 31 * 86400)}.bin'
    mixed = lanes.classify_sync_lane([NAME, stale], client_device_id='pendant', now=now)
    assert not mixed.automatic_recovery_allowed and mixed.reason == 'lookback_exceeded'


@pytest.mark.parametrize('off', ['false', '0', 'off', 'no'])
def test_kill_switch_restores_typed_400_for_new_future_uploads(client, monkeypatch, off):
    monkeypatch.setenv('SYNC_FUTURE_CAPTURE_CLAMP_ENABLED', off)
    response = _post_sync(client, NAME)
    assert response.status_code == 400, response.text
    assert response.json()['code'] == 'invalid_capture_time'


def test_future_batch_admission_freezes_receipt_and_discards_session_clock_bounds(client, monkeypatch):
    captured = {}

    async def batch_route(**kwargs):
        return router.RecordUploadRoute.BATCH

    async def accept(**kwargs):
        captured.update(kwargs)
        return JSONResponse(status_code=202, content={'job_id': 'future', 'status': 'queued'})

    monkeypatch.setattr(router, 'registered_record_response', batch_route)
    monkeypatch.setattr(router, 'accept_batch_upload', accept)
    start = datetime.now(timezone.utc).timestamp()
    response = client.post(
        '/v2/sync-local-files',
        headers={'X-App-Platform': 'ios', 'X-Device-Id-Hash': 'abcd1234'},
        params={
            'recording_session_id': 'future-recording',
            'audio_start_seconds': FUTURE,
            'audio_end_seconds': FUTURE + 1,
        },
        files=[('files', (NAME, b'\x00' * 32, 'application/octet-stream'))],
    )
    assert response.status_code == 202, response.text
    assert captured['lane'] == 'backfill' and captured['recording_age_seconds'] is None
    context = captured['intake_context']
    assert start <= context['capture_received_at'] <= datetime.now(timezone.utc).timestamp()
    assert context['audio_start_seconds'] is context['audio_end_seconds'] is None
    assert context['filenames'] == [NAME]
    assert context['capture_clock_policy'] == 'future_device_offset_v1'


def test_future_recovery_without_device_identity_keeps_phone_custody(client):
    response = _post_sync(client, NAME)
    assert response.status_code == 503
    assert response.json()['code'] == 'capture_clock_identity_required'


@pytest.mark.parametrize('ahead,untrusted', [(170, False), (5 * 365 * 86400, True)])
def test_combined_suffix_and_future_route_uses_main_normalizer_and_content_identity(
    client, monkeypatch, tmp_path, ahead, untrusted
):
    captured = {}

    async def batch_route(**kwargs):
        return router.RecordUploadRoute.BATCH

    async def accept(**kwargs):
        captured.update(kwargs)
        return JSONResponse(status_code=202, content={'job_id': 'combined', 'status': 'queued'})

    monkeypatch.setattr(router, 'registered_record_response', batch_route)
    monkeypatch.setattr(router, 'accept_batch_upload', accept)
    raw = int(datetime.now(timezone.utc).timestamp()) + ahead
    filename = f'audio_omi_pcm16_16000_clkeone_{raw}_u0.bin'
    canonical = f'audio_omi_pcm16_16000_u0_clkeone_{raw}.bin'
    expected = tmp_path / canonical
    expected.write_bytes(b'\x00' * 32)
    expected_content_id = compute_sync_content_id('synthetic-uid', [str(expected)])
    monkeypatch.setattr(router, 'compute_sync_content_id', compute_sync_content_id)
    response = client.post(
        '/v2/sync-local-files',
        headers={'X-App-Platform': 'ios', 'X-Device-Id-Hash': 'abcd1234'},
        files=[('files', (filename, b'\x00' * 32, 'application/octet-stream'))],
    )
    assert response.status_code == 202, response.text
    assert captured['intake_context']['filenames'] == [canonical]
    assert captured['content_id'] == expected_content_id
    assert Path(captured['paths'][0]).name == canonical
    assert pipeline.get_timestamp_from_path(captured['paths'][0]) == raw
    assert captured['intake_context']['capture_clock_policy'] == (
        'future_device_offset_v1' if untrusted else 'estimated_source_isolated_v1'
    )
    assert captured['lane'] == 'backfill'


@pytest.mark.parametrize('untrusted_first', [False, True])
def test_assignment_blocks_time_only_binding_in_both_directions_and_replays_identity(untrusted_first):
    store = StrictFirestore()
    trusted, untrusted = chunk('trusted', 1800000000), chunk('untrusted', 1800000000)
    untrusted['capture_time_trust'] = 'untrusted'
    first, second = (untrusted, trusted) if untrusted_first else (trusted, untrusted)
    intake(store, first)
    before = deepcopy(store.rows[('users', 'u', 'conversations', first['id'])])
    assigned, created, _ = intake(store, second, candidate_id=first['id'])
    assert created and assigned['id'] == second['id']
    assert store.rows[('users', 'u', 'conversations', first['id'])] == before
    assert len(conversations(store)) == 2
    replayed, created, _ = intake(store, untrusted)
    assert not created and replayed['id'] == untrusted['id']


def test_batch_job_freezes_untrusted_time_even_without_manifest_or_compute_admission():
    item = WorkItem(
        'segment', 'synthetic', 1800000000, 'gs://synthetic/audio', 2, Priority.DEEP, capture_time_trust='untrusted'
    )
    assert WorkItem(**item.to_dict()).capture_time_trust == 'untrusted'
    assert replace(item, capture_at=item.capture_at + 1).capture_time_trust == 'untrusted'
    assert not item.requires_compute_admission
    assert 'capture_time_trust' not in replace(item, capture_time_trust=None).to_dict()
    with pytest.raises(ValueError, match='capture_time_trust'):
        replace(item, capture_time_trust='device_bound')


def test_unmarked_future_file_is_accepted_without_device_or_run_identity(client, monkeypatch):
    captured = {}

    async def route(**kwargs):
        return router.RecordUploadRoute.BATCH

    async def accept(**kwargs):
        captured.update(kwargs)
        return JSONResponse(status_code=202, content={'job_id': 'unmarked', 'status': 'queued'})

    monkeypatch.setattr(router, 'registered_record_response', route)
    monkeypatch.setattr(router, 'accept_batch_upload', accept)
    response = _post_sync(client, f'audio_omi_pcm16_16000_{int(FUTURE)}.bin')
    assert response.status_code == 202, response.text
    assert captured['intake_context']['capture_clock_policy'] == 'future_device_offset_v1'
    assert captured['client_device_id'] is None


def test_future_upload_cannot_fall_through_to_legacy(client, monkeypatch):
    async def legacy(**kwargs):
        return router.RecordUploadRoute.LEGACY

    monkeypatch.setattr(router, 'registered_record_response', legacy)
    response = client.post(
        '/v2/sync-local-files',
        headers={'X-App-Platform': 'ios', 'X-Device-Id-Hash': 'abcd1234'},
        files=[('files', (NAME, b'\x00' * 32, 'application/octet-stream'))],
    )
    assert response.status_code == 400 and response.json()['code'] == 'invalid_capture_time'


def test_requeued_estimate_cannot_fall_through_to_legacy(client, monkeypatch):
    async def legacy(**kwargs):
        return router.RecordUploadRoute.LEGACY

    monkeypatch.setattr(router, 'registered_record_response', legacy)
    stamp = int(router.time.time()) - 10
    response = _post_sync(client, f'audio_omi_pcm16_16000_clkerequeued_{stamp}.bin')
    assert response.status_code == 503 and response.json()['code'] == 'sync_batch_unavailable'


def test_requeued_estimate_ignores_explicit_target_without_legacy_fallback(client, monkeypatch):
    async def declined(**kwargs):
        return None

    monkeypatch.setattr(router, 'accept_batch_upload', declined)
    stamp = int(router.time.time()) - 10
    response = client.post(
        '/v2/sync-local-files',
        params={'conversation_id': 'neighbour'},
        files=[
            ('files', (f'audio_omi_pcm16_16000_clkerequeued_{stamp}.bin', b'\x00' * 32, 'application/octet-stream'))
        ],
    )
    assert response.status_code == 503 and response.json()['code'] == 'sync_batch_unavailable'
