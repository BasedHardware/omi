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
    _run_skewed_segment,
    _capture_time_counter,
    _Upload,
)
from tests.unit.test_batch_pipeline_audio import pcm
from tests.unit.test_sync_cross_job_assignment import chunk, conversations, intake
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.batch_pipeline import capture_decode
from utils.batch_pipeline.contracts import WorkItem, Priority
from utils.sync import capture_clock, lanes, pipeline
from utils.sync.live_overlap import compatible_capture
from utils.observability.reasons import SyncCaptureTimeReason
from utils.request_validation import parse_sync_filename_timestamp
from routers import sync as router

FUTURE = datetime(2038, 1, 19, tzinfo=timezone.utc).timestamp()
NAME = f'audio_omi_pcm16_16000_{int(FUTURE)}.bin'


@pytest.mark.parametrize('ahead,accepted', [(170, True), (601, False), (3600, False), (86400, False), (86401, True)])
def test_future_recovery_has_a_wide_closed_margin(ahead, accepted):
    now = datetime(2026, 11, 15, tzinfo=timezone.utc)
    reason = capture_clock.capture_time_rejection(now + timedelta(seconds=ahead), now=now)
    assert reason is (None if accepted else SyncCaptureTimeReason.REJECTED_FUTURE)
    assert capture_clock.maximum_future_skew_seconds() == 600


def test_future_staging_keeps_filename_bytes_identity_and_closed_metric(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    before = _capture_time_counter('accepted_future_clamped')
    upload = _Upload(NAME)
    original = upload.file.getvalue()
    [path] = pipeline._retrieve_file_paths_v2([upload], 'synthetic', 'job')
    assert Path(path).name == NAME and Path(path).read_bytes() == original
    assert parse_sync_filename_timestamp(NAME) == FUTURE
    assert _capture_time_counter('accepted_future_clamped') == before + 1


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


@pytest.mark.parametrize('off', [False, True])
def test_admitted_future_decode_keeps_raw_order_pcm_and_receipt_after_kill_switch(tmp_path, monkeypatch, off):
    if off:
        monkeypatch.setenv('SYNC_FUTURE_CAPTURE_CLAMP_ENABLED', 'false')
    receipt = 1800000000.0
    paths = [pcm(tmp_path, int(FUTURE) + 100, 16000, sample=2), pcm(tmp_path, int(FUTURE), 16000, sample=1)]
    units = list(capture_decode.decode_units(paths, received_at=receipt, max_seconds=1))
    assert [u.capture_at for u in units] == [FUTURE, FUTURE + 100]
    assert [u.stored_capture_at for u in units] == [receipt - 2, receipt - 1]
    for index, unit in enumerate(units):
        with wave.open(io.BytesIO(unit.wav)) as wav:
            assert wav.readframes(16000) == bytes([index + 1, 0]) * 16000


def test_mixed_future_and_trusted_audio_keep_separate_clock_policies(tmp_path):
    receipt = 1800000000.0
    paths = [pcm(tmp_path, int(FUTURE), 16000), pcm(tmp_path, int(receipt) - 10, 16000)]
    trusted, untrusted = list(capture_decode.decode_units(paths, received_at=receipt))
    assert trusted.capture_at == receipt - 10 and trusted.stored_capture_at is None
    assert untrusted.capture_at == FUTURE and untrusted.stored_capture_at == receipt - 1


@pytest.mark.asyncio
async def test_future_vad_uses_frozen_receive_clock_after_real_time_catches_up(tmp_path, monkeypatch):
    receipt = 1800000000.0
    source = str(tmp_path / f'audio_omi_pcm16_16000_{int(FUTURE)}.wav')
    pipeline.AudioSegment.silent(duration=2000, frame_rate=16000).export(source, format='wav')

    async def inline(_executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setenv('SYNC_FUTURE_CAPTURE_CLAMP_ENABLED', 'false')
    monkeypatch.setattr(capture_clock.time, 'time', lambda: FUTURE + 86400)
    monkeypatch.setattr(pipeline, 'run_blocking', inline)
    monkeypatch.setattr(pipeline, 'vad_is_empty', lambda *_a, **_k: [{'start': 0, 'end': 2}])
    segments, origins = set(), {}
    errors, _ = await pipeline._run_sync_vad_phase(
        [source], segments, early_segment_times=origins, capture_received_at=receipt
    )
    assert not errors and set(origins) == segments
    assert list(origins.values()) == [FUTURE]
    offsets = capture_clock.early_capture_clock_offsets(
        [(path, pipeline.get_timestamp_from_path(path), 2) for path in segments], now=receipt, source_starts=origins
    )
    assert all(pipeline.get_timestamp_from_path(path) - offsets[path] == receipt - 2 for path in segments)


def test_receipt_clock_segment_never_uses_closest_conversation_and_retains_raw_identity():
    receipt = datetime.now(timezone.utc).timestamp()
    offset = capture_clock.early_capture_clock_offsets([('seg', FUTURE, 10)], now=receipt)['seg']
    store, response, closest, _ = _run_skewed_segment(FUTURE, offset, True, receipt_clock=True)
    assert closest == {} and not response['updated_memories']
    rows = conversations(store)
    assert len(rows) == 2
    [stored] = [row for row in rows if row['id'] != 'live']
    assert stored['capture_time_trust'] == 'untrusted'
    assert stored['started_at'].timestamp() == pytest.approx(receipt - 10, abs=0.01)
    assert stored['finished_at'].timestamp() == pytest.approx(receipt, abs=0.01)
    assert not compatible_capture(stored, rows[0] if rows[0]['id'] == 'live' else rows[1])


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
