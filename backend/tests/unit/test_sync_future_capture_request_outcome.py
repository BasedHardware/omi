"""Request telemetry counts router and decoder boundaries without changing upload results."""

from pathlib import Path
from unittest.mock import AsyncMock, Mock

from fastapi.responses import JSONResponse
import pytest

from config.policy import BatchUnitPolicy
from routers import sync as router
from tests.unit.test_batch_pipeline_audio import pcm
from tests.unit.test_sync_capture_time_skew import client, _post_sync
from tests.unit.test_sync_future_capture_recovery import FUTURE, NAME, _default_skew, enable_future_recovery
from utils.batch_pipeline import future_capture_decode, intake
from utils.sync import future_capture_request as telemetry
from utils.sync.receipt_clock import FutureCaptureRetry


def _counts():
    return {outcome: telemetry._OUTCOMES.labels(outcome=outcome)._value.get() for outcome in telemetry.Outcome}


def _assert_increment(before, expected=None):
    assert _counts() == {outcome: total + (outcome == expected) for outcome, total in before.items()}


def test_mixed_bundle_counts_identity_refusal_once(client):
    before = _counts()
    response = client.post(
        '/v2/sync-local-files',
        files=[
            ('files', (NAME, b'\x00' * 32)),
            ('files', (f'audio_omi_pcm16_16000_clkeone_{FUTURE + 1}.bin', b'\x00' * 32)),
            ('files', (f'audio_omi_pcm16_16000_{int(router.time.time()) + 170}.bin', b'\x00' * 32)),
        ],
    )
    assert response.status_code == 503 and response.headers['Retry-After'] == '30'
    assert response.json()['code'] == 'capture_clock_identity_required'
    _assert_increment(before, 'identity_required')


@pytest.mark.parametrize(
    'scenario, outcome, status, code',
    [
        ('paused', 'preflight_refused', 503, 'backfill_capacity'),
        ('disabled', None, 400, 'invalid_capture_time'),
        ('ineligible', 'route_declined', 400, 'invalid_capture_time'),
        ('stage_error', 'pre_offset_error', 500, None),
    ],
)
def test_router_early_exits(client, monkeypatch, scenario, outcome, status, code):
    if scenario == 'paused':
        monkeypatch.setenv('SYNC_BACKFILL_ENABLED', 'false')
    elif scenario == 'disabled':
        monkeypatch.setenv('SYNC_FUTURE_CAPTURE_CLAMP_ENABLED', 'false')
    elif scenario == 'ineligible':
        # No durable batch owner and a policy outside the batch cohort: the future
        # capture cannot fall through to a reader (legacy admission is deleted).
        monkeypatch.setattr(router, 'registered_record_response', AsyncMock(return_value=None))
        monkeypatch.setattr(router, 'resolve_batch_policy', lambda _: BatchUnitPolicy(batch_enabled=False))
    elif scenario == 'stage_error':
        monkeypatch.setattr(router, '_retrieve_file_paths_v2', Mock(side_effect=OSError('stage failed')))
    before = _counts()
    # An unmarked far-future file passes the separate clock-identity gate.
    response = _post_sync(client, f'audio_omi_pcm16_16000_{FUTURE}.bin')
    assert response.status_code == status, response.text
    assert response.json().get('code') == code
    _assert_increment(before, outcome)


def test_metric_failure_preserves_identity_retry(client, monkeypatch):
    monkeypatch.setattr(telemetry, '_OUTCOMES', Mock(**{'labels.side_effect': RuntimeError('metric failed')}))
    response = _post_sync(client, NAME)
    assert response.status_code == 503
    assert response.headers['Retry-After'] == '30'
    assert response.json()['code'] == 'capture_clock_identity_required'


async def _send_to_intake(**kwargs):
    return await intake.accept_upload(**kwargs)


def _use_real_intake(monkeypatch, previous=None):
    monkeypatch.setattr(router, 'accept_batch_upload', _send_to_intake)
    monkeypatch.setattr(router, 'resolve_batch_policy', lambda _: BatchUnitPolicy(batch_enabled=True))
    monkeypatch.setattr(intake, 'shadow_from_env', lambda store: store)
    monkeypatch.setattr(intake, 'FirestoreStore', Mock(return_value=Mock(run=Mock(return_value=previous or {}))))
    monkeypatch.setattr(intake.legacy_dark, 'current_mode', lambda _: intake.LegacySyncMode.ON)

    def authorize(*args, snapshots, **kwargs):
        snapshots['user'] = {'language': 'en'}
        return object()

    monkeypatch.setattr(intake, 'batch_artifact_authorize', authorize)
    monkeypatch.setattr(intake, 'artifacts_for', Mock())
    monkeypatch.setattr(intake, '_coalescing_try_offer', AsyncMock(return_value=None))


def test_existing_batch_receipt_counts_prior_custody(client, monkeypatch):
    _use_real_intake(monkeypatch, previous={'dispatch_protocol': 'batch_v1', 'job_id': 'bp_existing'})
    monkeypatch.setattr(
        intake,
        'durable_status',
        Mock(
            return_value={
                'job_id': 'bp_existing',
                'status': 'queued',
                'total_files': 1,
                'total_segments': 0,
                'poll_after_ms': 3000,
                'lane': 'backfill',
            }
        ),
    )
    before = _counts()
    response = _post_sync(client, f'audio_omi_pcm16_16000_{FUTURE}.bin')
    assert response.status_code == 202 and response.json()['job_id'] == 'bp_existing'
    _assert_increment(before, 'prior_custody')


@pytest.mark.parametrize(
    'scenario, outcome, code',
    [
        ('memo_hit', 'decode_memo_hit', 'sync_batch_unavailable'),
        ('bad_frame', 'decode_failed', 'sync_batch_unavailable'),
        ('pending', 'reached_offsets', 'capture_clock_anchor_pending'),
    ],
)
def test_decode_outcome_at_offset_boundary(client, monkeypatch, tmp_path, scenario, outcome, code):
    _use_real_intake(monkeypatch)
    monkeypatch.setattr(intake, '_cached_decode_refusal', AsyncMock(return_value=(None, scenario == 'memo_hit')))
    resolve_offsets = Mock(side_effect=FutureCaptureRetry('capture_clock_anchor_pending'))
    monkeypatch.setattr(future_capture_decode, 'receipt_clock_offsets', resolve_offsets)
    path = Path(pcm(tmp_path, FUTURE))
    body = b'\x00' * 32 if scenario == 'bad_frame' else path.read_bytes()
    before = _counts()
    response = client.post('/v2/sync-local-files', files=[('files', (path.name, body))])
    assert response.status_code == 503, response.text
    assert response.headers['Retry-After'] == '30'
    assert response.json()['code'] == code
    assert resolve_offsets.call_count == (scenario == 'pending')
    _assert_increment(before, outcome)
