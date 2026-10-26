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
from unittest.mock import Mock
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
