"""Sync uploads whose capture clock runs ahead of the server stay admissible.

Prod evidence (24h to 2026-10-26): real phone live-capture uploads carried
filename timestamps a median 171 s / max 349 s ahead of the server clock and
were rejected with 400 ``invalid timestamp`` — released clients treat that as
terminal. The app names segments after the audio START, so the skew is plain
phone-clock error; admission now tolerates it through the shared
``SYNC_CAPTURE_MAX_FUTURE_SKEW_SECONDS`` bound, clamps stored times to now,
keeps refusing implausible stamps (years ahead, pre-2024) with a typed 400,
and counts every disposition in ``omi_sync_capture_time_total``.
"""

from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
from prometheus_client import REGISTRY

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import sync as router
from utils.observability.reasons import SyncCaptureTimeReason
from utils.request_validation import parse_sync_filename_timestamp
from utils.sync import capture_clock, lanes
from utils.sync.capture_clock import CaptureTimeWindowError, SyncCaptureTimeRejected, capture_time_rejection
from utils.sync.pipeline import _retrieve_file_paths_v2


def _capture_time_counter(outcome: str) -> float:
    return REGISTRY.get_sample_value('omi_sync_capture_time_total', {'outcome': outcome}) or 0.0


def _filename(seconds_from_now: float) -> str:
    stamp = (datetime.now(timezone.utc) + timedelta(seconds=seconds_from_now)).timestamp()
    return f'audio_omi_opus_16000_1_fs160_{stamp:.0f}.bin'


@pytest.fixture(autouse=True)
def _default_skew(monkeypatch):
    monkeypatch.delenv('SYNC_CAPTURE_MAX_FUTURE_SKEW_SECONDS', raising=False)


# --- shared window ---


def test_within_tolerance_future_capture_time_is_admissible():
    assert parse_sync_filename_timestamp(_filename(170)) > datetime.now(timezone.utc).timestamp()
    assert capture_time_rejection(datetime.now(timezone.utc) + timedelta(seconds=170)) is None


def test_beyond_tolerance_future_capture_time_is_rejected_with_closed_reason():
    five_years_ahead = datetime.now(timezone.utc) + timedelta(days=5 * 365)
    assert capture_time_rejection(five_years_ahead) is SyncCaptureTimeReason.REJECTED_FUTURE
    with pytest.raises(CaptureTimeWindowError) as exc_info:
        parse_sync_filename_timestamp(_filename(5 * 365 * 86400))
    assert exc_info.value.capture_time_reason is SyncCaptureTimeReason.REJECTED_FUTURE
    assert str(exc_info.value) == 'invalid timestamp'


def test_pre_2024_capture_time_is_rejected_with_closed_reason():
    assert capture_time_rejection(datetime(2023, 12, 31, tzinfo=timezone.utc)) is SyncCaptureTimeReason.REJECTED_EARLY
    with pytest.raises(CaptureTimeWindowError) as exc_info:
        parse_sync_filename_timestamp('audio_omi_opus_16000_1_fs160_1704067199.bin')
    assert exc_info.value.capture_time_reason is SyncCaptureTimeReason.REJECTED_EARLY


def test_tolerance_is_one_shared_setting_for_parser_and_lane_guard(monkeypatch):
    assert capture_clock.maximum_future_skew_seconds() == 600
    assert lanes.maximum_future_skew_seconds() == 600
    monkeypatch.setenv('SYNC_CAPTURE_MAX_FUTURE_SKEW_SECONDS', '60')
    assert capture_clock.maximum_future_skew_seconds() == 60
    with pytest.raises(CaptureTimeWindowError):
        parse_sync_filename_timestamp(_filename(170))


# --- lane classification ---


def test_within_tolerance_skew_stays_fresh_and_clamps_decision_times():
    decision = lanes.classify_sync_lane([_filename(170)], client_device_id='dev-1')
    assert decision.lane is lanes.SyncLane.FRESH
    assert decision.trust is lanes.CaptureTimeTrust.DEVICE_BOUND
    assert decision.reason == 'recent_capture'
    server_now = datetime.now(timezone.utc).timestamp()
    assert decision.newest_capture_at <= server_now
    assert decision.oldest_capture_at <= server_now


def test_beyond_tolerance_skew_is_untrusted_backfill():
    decision = lanes.classify_sync_lane([_filename(5 * 365 * 86400)], client_device_id='dev-1')
    assert decision.lane is lanes.SyncLane.BACKFILL
    assert decision.trust is lanes.CaptureTimeTrust.UNTRUSTED
    assert decision.reason == 'invalid_capture_time'


# --- v2 admission gate ---


class _Upload:
    def __init__(self, filename: str):
        self.filename = filename
        self.file = BytesIO(b'\x00' * 32)


def test_retrieve_file_paths_v2_accepts_and_stages_within_tolerance_skew(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    before = _capture_time_counter('accepted_future_skew')
    filename = _filename(170)

    paths = _retrieve_file_paths_v2([_Upload(filename)], 'u1', 'job-1')

    assert paths == [f'syncing/u1/job-1/{filename}']
    assert Path(paths[0]).exists()
    assert _capture_time_counter('accepted_future_skew') == before + 1


@pytest.mark.parametrize(
    'filename,expected_outcome',
    [
        (_filename(5 * 365 * 86400), 'rejected_future'),
        ('audio_omi_opus_16000_1_fs160_1685577600.bin', 'rejected_early'),  # 2023-06-01
    ],
)
def test_retrieve_file_paths_v2_rejects_implausible_times_typed(tmp_path, monkeypatch, filename, expected_outcome):
    monkeypatch.chdir(tmp_path)
    before = _capture_time_counter(expected_outcome)

    with pytest.raises(SyncCaptureTimeRejected) as exc_info:
        _retrieve_file_paths_v2([_Upload(filename)], 'u1', 'job-1')

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == 'Invalid sync file format: invalid timestamp'
    assert _capture_time_counter(expected_outcome) == before + 1
    staged = list(Path('syncing').rglob('*.bin')) if Path('syncing').exists() else []
    assert staged == []


def test_retrieve_file_paths_v2_counts_malformed_timestamps_separately(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    before = _capture_time_counter('rejected_malformed')

    with pytest.raises(SyncCaptureTimeRejected):
        _retrieve_file_paths_v2([_Upload('audio_omi_opus_16000_1_fs160_not-a-number.bin')], 'u1', 'job-1')

    assert _capture_time_counter('rejected_malformed') == before + 1


# --- typed v2 route contract ---


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setattr(router, 'get_sync_ledger_fence_mode', lambda: router.SyncLedgerFenceMode.ACTIVE)
    monkeypatch.setattr(router, 'get_hard_restriction_status', lambda _: (False, None))
    monkeypatch.setattr(router, 'is_daily_audio_ceiling_exceeded', lambda _: False)
    monkeypatch.setattr(router, 'has_transcription_credits', lambda _: False)
    monkeypatch.setattr(router, 'resolve_transcription_allowance', lambda _: Mock(reason='plan_allowance_exhausted'))
    monkeypatch.setattr(router, 'archive_mobile_batch_raw_files', lambda *_a, **_k: [])
    monkeypatch.setattr(router, '_cleanup_files', Mock())
    monkeypatch.setattr(router, 'is_cloud_tasks_dispatch_enabled', lambda: False)
    monkeypatch.setattr(router, 'has_byok_keys', lambda: False)
    from config.policy import BatchUnitPolicy

    monkeypatch.setattr(router, 'resolve_batch_policy', lambda _: BatchUnitPolicy())
    monkeypatch.setattr(router, 'compute_sync_content_id', lambda *_a: 'content-1')
    monkeypatch.setattr(router, 'create_sync_job', Mock())
    monkeypatch.setattr(router, 'claim_sync_content', lambda *_a: {'outcome': 'held', 'result': {}})
    monkeypatch.setattr(router, 'mark_job_completed', Mock())

    app = FastAPI()
    app.include_router(router.router)
    app.dependency_overrides[router.auth.get_current_user_uid] = lambda: 'synthetic-uid'
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def _post_sync(client, filename):
    return client.post(
        '/v2/sync-local-files',
        files=[('files', (filename, b'\x00' * 32, 'application/octet-stream'))],
    )


def test_v2_route_accepts_capture_time_ahead_of_server_within_tolerance(client):
    response = _post_sync(client, _filename(170))

    assert response.status_code == 202, response.text
    assert response.json()['status'] == 'completed'


def test_v2_route_rejects_five_year_future_stamp_with_typed_400(client):
    before = _capture_time_counter('rejected_future')
    response = _post_sync(client, _filename(5 * 365 * 86400))

    assert response.status_code == 400, response.text
    assert response.json() == {'code': 'invalid_capture_time', 'detail': 'Invalid sync file format: invalid timestamp'}
    assert _capture_time_counter('rejected_future') == before + 1


# --- stored-time clamping ---


def test_clamp_capture_time_moves_only_future_times():
    now = datetime.now(timezone.utc).timestamp()
    assert capture_clock.clamp_capture_time(now - 10, now=now) == now - 10
    assert capture_clock.clamp_capture_time(now + 170, now=now) == now


# --- one request-wide server-clock offset (fix round) ---


def test_capture_clock_offset_moves_only_time_ahead_of_server():
    now = datetime.now(timezone.utc).timestamp()
    assert capture_clock.capture_clock_offset(now + 180.5, now=now) == 180.5
    assert capture_clock.capture_clock_offset(now - 30, now=now) == 0


def test_internal_wal_clock_read_allows_derived_offsets_beyond_the_window():
    """Admission validates the source capture time once; derived names ride along.

    ``retrieve_vad_segments`` names each WAV after source capture time + speech
    offset, so a name derived from an admitted near-tolerance source can sit
    beyond the window; internal clock math (sorting, identity, the request
    offset) must still read it. The admission parser keeps refusing it.
    """
    from utils.sync.files import get_timestamp_from_path

    derived = _filename(650)  # e.g. an admitted +590 s source plus 60 s of speech offset

    with pytest.raises(CaptureTimeWindowError):
        parse_sync_filename_timestamp(derived)
    assert get_timestamp_from_path(derived) > datetime.now(timezone.utc).timestamp() + 600
    with pytest.raises(ValueError):
        get_timestamp_from_path('audio_omi_opus_16000_1_fs160_not-a-number.bin')


def test_offset_shifted_session_bounds_bind_the_live_conversation():
    """A +171 s skewed live capture must keep targeting its live conversation.

    The raw phone-clock audio bounds miss the 60 s trailing allowance in
    ``select_recording_session_target``; the same bounds on the server clock
    (the router shifts them by the one request offset) bind.
    """
    from utils.sync.recording_session_target import select_recording_session_target

    server_now = datetime.now(timezone.utc).timestamp()
    row = {
        'id': 'live',
        'started_at': datetime.fromtimestamp(server_now - 60, tz=timezone.utc),
        'finished_at': datetime.fromtimestamp(server_now - 10, tz=timezone.utc),
        'source': 'omi',
        'client_device_id': 'pendant',
        'external_data': {'recording_session_id': 'rec-live'},
    }
    raw_start, raw_end = server_now + 111, server_now + 161  # phone clock +171 s

    assert (
        select_recording_session_target(
            [row],
            'rec-live',
            source='omi',
            client_device_id='pendant',
            is_locked=False,
            audio_start_seconds=raw_start,
            audio_end_seconds=raw_end,
        )
        is None
    )

    offset = capture_clock.capture_clock_offset(raw_end)
    assert (
        select_recording_session_target(
            [row],
            'rec-live',
            source='omi',
            client_device_id='pendant',
            is_locked=False,
            audio_start_seconds=raw_start - offset,
            audio_end_seconds=raw_end - offset,
        )
        == 'live'
    )


def test_v2_route_shifts_recording_session_bounds_to_server_clock(client, monkeypatch):
    """The router applies the one offset before the bounds enter any dispatch."""
    from fastapi.responses import JSONResponse

    captured = {}

    async def fake_record_response(**_kwargs):
        return router.RecordUploadRoute.BATCH

    async def fake_accept_batch_upload(**kwargs):
        captured.update(kwargs)
        return JSONResponse(status_code=202, content={'job_id': 'j', 'status': 'queued'})

    monkeypatch.setattr(router, 'registered_record_response', fake_record_response)
    monkeypatch.setattr(router, 'accept_batch_upload', fake_accept_batch_upload)

    server_now = datetime.now(timezone.utc).timestamp()
    raw_end = server_now + 161  # phone clock +171 s over a conversation that ended 10 s ago
    raw_start = raw_end - 50
    filename = _filename(160)  # file start strictly inside the claimed audio interval

    response = client.post(
        '/v2/sync-local-files',
        params={
            'recording_session_id': 'rec-live',
            'audio_start_seconds': raw_start,
            'audio_end_seconds': raw_end,
        },
        files=[('files', (filename, b'\x00' * 32, 'application/octet-stream'))],
    )

    assert response.status_code == 202, response.text
    intake = captured['intake_context']
    offset = capture_clock.capture_clock_offset(raw_end)
    assert intake['audio_start_seconds'] == pytest.approx(raw_start - offset, abs=1.0)
    assert intake['audio_end_seconds'] == pytest.approx(raw_end - offset, abs=1.0)
    assert intake['audio_end_seconds'] <= server_now + 1.0


@patch('utils.sync.pipeline.get_syncing_file_temporal_signed_url', return_value='url')
@patch('utils.sync.pipeline.prerecorded', return_value=(['word'], 'en'))
@patch('utils.sync.pipeline.postprocess_words')
@patch('utils.sync.pipeline.get_timestamp_from_path')
def _run_skewed_segment(
    raw_start, request_offset, bind_closest, mock_timestamp, mock_postprocess, _mock_prerecorded, _mock_signed_url
):
    """Run process_segment for a skewed-stamped file with the request offset applied.

    ``raw_start`` is the raw filename timestamp (capture clock), ``request_offset``
    the one request-wide offset the coordinator computed, and ``bind_closest``
    whether the closest-conversation lookup returns the seeded live row.
    Returns (store, response, errors, closest_seen, now_test); the live
    conversation runs on the server clock, 60 s back.
    """
    from copy import deepcopy
    from unittest.mock import MagicMock

    from models.transcript_segment import TranscriptSegment

    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
    from tests.unit.test_sync_cross_job_assignment import chunk, intake
    from utils.sync import pipeline

    now_test = datetime.now(timezone.utc).timestamp()
    mock_timestamp.return_value = raw_start
    mock_postprocess.return_value = [
        TranscriptSegment(text='Skewed capture speech', start=0.0, end=10.0, is_user=False)
    ]
    store = StrictFirestore()
    live = None
    if bind_closest:
        live = chunk('live', now_test - 60)
        live['sync_content_revision'] = 1  # discovered candidates must stay auto-mergeable
        store.rows[('users', 'u', 'conversations', 'live')] = deepcopy(live)
    closest_seen = {}

    def fake_closest(_uid, start, end, **_kwargs):
        closest_seen.update(start=start, end=end)
        return live if bind_closest else None

    response = {'new_memories': set(), 'updated_memories': set()}
    errors: list = []
    with patch('utils.sync.pipeline.get_closest_conversation_to_timestamps', side_effect=fake_closest), patch(
        'utils.conversations.lifecycle.ingest_sync_conversation',
        side_effect=lambda uid, incoming, **kw: intake(store, incoming, **kw),
    ), patch('utils.sync.pipeline.identify_speakers_for_segments'), patch(
        'utils.sync.pipeline.conversations_db.get_manual_speaker_receipt', return_value={}
    ), patch(
        'utils.sync.pipeline.get_wav_duration', return_value=10
    ):
        result = pipeline.process_segment(
            'seg_123.wav',
            'u',
            response,
            MagicMock(),
            errors,
            client_device_id='pendant',
            capture_time_offset=request_offset,
        )
    assert result and errors == []
    return store, response, closest_seen, now_test


def test_skewed_segment_merges_into_live_conversation_through_closest_lookup():
    """The ±120 s window must compare server-clock times, not the raw +171 s stamp."""
    from tests.unit.test_sync_cross_job_assignment import conversations

    now_test = datetime.now(timezone.utc).timestamp()
    store, _response, closest_seen, now_test = _run_skewed_segment(now_test + 171, 181.0, True)

    assert closest_seen['start'] == pytest.approx(now_test - 10, abs=1.0)
    assert closest_seen['end'] == pytest.approx(now_test, abs=1.0)
    # The skewed upload merged into the existing conversation; none was created.
    assert len(conversations(store)) == 1
    assert conversations(store)[0]['id'] == 'live'


def test_skewed_segment_stores_the_full_duration_pair():
    """A 10 s segment stamped +171 s keeps its 10 s duration and finishes by now."""
    from tests.unit.test_sync_cross_job_assignment import conversations

    now_test = datetime.now(timezone.utc).timestamp()
    store, _response, _closest_seen, now_test = _run_skewed_segment(now_test + 171, 181.0, False)

    (stored,) = conversations(store)
    duration = (stored['finished_at'] - stored['started_at']).total_seconds()
    assert duration == pytest.approx(10.0, abs=0.05)
    assert stored['started_at'].timestamp() == pytest.approx(now_test - 10, abs=1.0)
    assert stored['finished_at'].timestamp() <= datetime.now(timezone.utc).timestamp()


@patch('utils.sync.pipeline.get_syncing_file_temporal_signed_url', return_value='url')
@patch('utils.sync.pipeline.prerecorded', return_value=(['word'], 'en'))
@patch('utils.sync.pipeline.postprocess_words')
@patch('utils.sync.pipeline.get_timestamp_from_path')
def test_minimal_redrive_attach_lookup_compares_on_server_clock(
    mock_timestamp, mock_postprocess, _mock_prerecorded, _mock_signed_url
):
    """The attach-first fallback lookup also receives server-clock bounds."""
    from models.transcript_segment import TranscriptSegment

    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
    from tests.unit.test_sync_cross_job_assignment import conversations, intake
    from utils.sync import pipeline

    now_test = datetime.now(timezone.utc).timestamp()
    mock_timestamp.return_value = now_test + 171
    mock_postprocess.return_value = [
        TranscriptSegment(text='Skewed capture speech', start=0.0, end=10.0, is_user=False)
    ]
    attached = {}

    def fake_attach(_uid, start, end, _capture):
        attached.update(start=start, end=end)
        return None

    response = {'new_memories': set(), 'updated_memories': set()}
    errors: list = []
    store = StrictFirestore()
    with patch.object(
        pipeline.minimal_redrive, 'select_service', lambda *a, **k: ('modulate', 'multi', 'velma-2')
    ), patch.object(pipeline.minimal_redrive, 'attach_target', fake_attach), patch(
        'utils.conversations.lifecycle.ingest_sync_conversation',
        side_effect=lambda uid, incoming, **kw: intake(store, incoming, **kw),
    ), patch(
        'utils.sync.pipeline.get_closest_conversation_to_timestamps', return_value=None
    ), patch(
        'utils.sync.pipeline.identify_speakers_for_segments'
    ), patch(
        'utils.sync.pipeline.conversations_db.get_manual_speaker_receipt', return_value={}
    ), patch(
        'utils.sync.pipeline.get_wav_duration', return_value=10
    ):
        result = pipeline.process_segment(
            'seg_123.wav',
            'u',
            response,
            MagicMock(),
            errors,
            redrive_mode='minimal',
            capture_time_offset=181.0,
        )
    assert result and errors == []
    assert attached['start'] == pytest.approx(now_test - 10, abs=1.0)
    assert attached['end'] == pytest.approx(now_test, abs=1.0)
    assert len(conversations(store)) == 1
