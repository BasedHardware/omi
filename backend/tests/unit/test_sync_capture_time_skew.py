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
import hashlib
from pathlib import Path
from unittest.mock import MagicMock, Mock, call, patch
from prometheus_client import REGISTRY

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse

from routers import sync as router
from utils.observability.reasons import SyncCaptureTimeReason
from utils.request_validation import parse_sync_filename_timestamp
from utils.transcription_allowance import TranscriptionAllowance
import utils.subscription as subscription
from utils.sync import capture_clock, lanes, pipeline
from utils.sync.capture_clock import CaptureTimeWindowError, SyncCaptureTimeRejected, capture_time_rejection
from utils.sync.clock_run import clock_run_from_path
from utils.sync.empty_upload import nonempty_manifest_claims
from utils.sync.files import get_timestamp_from_path
from utils.sync.pipeline import _retrieve_file_paths_v2
from utils.sync.upload_names import canonical_sync_upload_filenames
from utils.sync.content_id import compute_sync_content_id


def _capture_time_counter(outcome: str) -> float:
    return REGISTRY.get_sample_value('omi_sync_capture_time_total', {'outcome': outcome}) or 0.0


def _filename(seconds_from_now: float) -> str:
    stamp = (datetime.now(timezone.utc) + timedelta(seconds=seconds_from_now)).timestamp()
    return f'audio_omi_opus_16000_1_fs160_{stamp:.0f}.bin'


@pytest.fixture(autouse=True)
def _default_skew(monkeypatch):
    monkeypatch.delenv('SYNC_CAPTURE_MAX_FUTURE_SKEW_SECONDS', raising=False)
    monkeypatch.delenv('SYNC_EARLY_CAPTURE_CLAMP_ENABLED', raising=False)


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
    # Kill switch restores the original refusal policy at every admission seam.
    with patch.dict('os.environ', {'SYNC_EARLY_CAPTURE_CLAMP_ENABLED': 'false'}):
        _assert_pre_2024_rejected()


def _assert_pre_2024_rejected():
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
    monkeypatch.setenv('SYNC_EARLY_CAPTURE_CLAMP_ENABLED', 'false')
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
    monkeypatch.setattr(
        router,
        'resolve_transcription_allowance',
        lambda _: Mock(managed=False, reason='plan_allowance_exhausted'),
    )
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


def _set_single_resolve_lever(monkeypatch, percentage):
    if percentage is None:
        monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)
    else:
        monkeypatch.setenv('FIRESTORE_READ_LEVERS', f'{{"sync_allowance_single_resolve": {percentage}}}')


def _capture_allowance_dispatch(monkeypatch, dispatch):
    from config.policy import BatchUnitPolicy

    monkeypatch.setattr(router.legacy_dark, 'current_mode', lambda *_: router.legacy_dark.LegacySyncMode.ON)
    monkeypatch.setattr(router, 'ramp_admission_policy', lambda *_a, **_kw: BatchUnitPolicy())
    monkeypatch.setattr(router, 'claim_sync_content', lambda *_a: {'outcome': 'owned'})

    async def legacy_route(**_kwargs):
        return router.RecordUploadRoute.LEGACY

    async def shadow(**_kwargs):
        return None

    monkeypatch.setattr(router, 'registered_record_response', legacy_route)
    monkeypatch.setattr(router, '_offer_shadow_upload', shadow)

    dispatched = {}
    if dispatch == 'cloud_tasks':
        monkeypatch.setattr(router, 'is_cloud_tasks_dispatch_enabled', lambda: True)

        async def staged(_paths):
            return None

        def enqueue(payload):
            dispatched['should_lock'] = payload['should_lock']

        monkeypatch.setattr(router, '_stage_files_to_gcs_with_hold_recheck', staged)
        monkeypatch.setattr(router, 'enqueue_sync_job', enqueue)
    else:

        def pipeline(*args, **_kwargs):
            dispatched['should_lock'] = args[4]
            return Mock()

        monkeypatch.setattr(router, 'try_acquire_sync_job_run_lock', lambda _: 'inline-token')
        monkeypatch.setattr(router, 'bind_or_converge_sync_ledger_completion', lambda **_kwargs: None)
        monkeypatch.setattr(router, 'run_full_pipeline_background_async', pipeline)
        monkeypatch.setattr(router, 'start_background_task', Mock())
    return dispatched


def _assert_queued_response(response):
    assert response.status_code == 202, response.text
    assert {key: value for key, value in response.json().items() if key != 'job_id'} == {
        'status': 'queued',
        'total_files': 1,
        'total_segments': 0,
        'poll_after_ms': 3000,
        'lane': 'fresh',
    }


@pytest.mark.parametrize('single_resolve_percentage', [None, 100, 0], ids=['default', 'explicit-on', 'rollback'])
@pytest.mark.parametrize('dispatch', ['cloud_tasks', 'inline'])
@pytest.mark.parametrize(
    'allowance,expected_lock',
    [
        pytest.param(
            TranscriptionAllowance('managed', 600, 'plan_within_allowance', 18_000), False, id='free-available'
        ),
        pytest.param(
            TranscriptionAllowance('managed', 600, 'plan_within_allowance', 90_000), False, id='paid-available'
        ),
        pytest.param(
            TranscriptionAllowance('on_device', 0, 'plan_allowance_exhausted', 18_000), True, id='free-exhausted'
        ),
        pytest.param(
            TranscriptionAllowance('on_device', 0, 'plan_allowance_exhausted', 90_000), True, id='paid-exhausted'
        ),
        pytest.param(TranscriptionAllowance('on_device', 0, 'subscription_inactive'), True, id='inactive'),
        pytest.param(
            TranscriptionAllowance('on_device', 0, 'usage_budget_exhausted', None), False, id='budget-exhausted'
        ),
        *(
            pytest.param(TranscriptionAllowance('managed', None, reason, None), False, id=reason)
            for reason in ('plan_unlimited', 'byok', 'marketplace_reviewer', 'release_probe', 'usage_budget_available')
        ),
        *(
            pytest.param(TranscriptionAllowance('on_device', 0, reason), False, id=reason)
            for reason in sorted(subscription.TRANSCRIPTION_ALLOWANCE_TRANSIENT_REASONS)
        ),
    ],
)
def test_v2_one_allowance_drives_lock_and_both_dispatch_paths(
    client, monkeypatch, dispatch, allowance, expected_lock, single_resolve_percentage
):
    """Stable free/paid answers preserve the response and lock; rollback uses the real legacy wrapper."""
    _set_single_resolve_lever(monkeypatch, single_resolve_percentage)
    resolver = Mock(return_value=allowance)
    credits = Mock(wraps=subscription.has_transcription_credits)
    monkeypatch.setattr(subscription, 'resolve_transcription_allowance', resolver)
    monkeypatch.setattr(router, 'resolve_transcription_allowance', resolver)
    monkeypatch.setattr(router, 'has_transcription_credits', credits)
    dispatched = _capture_allowance_dispatch(monkeypatch, dispatch)
    fallback = Mock()
    monkeypatch.setattr(router, 'record_fallback', fallback)
    attempts_before = (
        REGISTRY.get_sample_value('omi_sync_dispatch_attempts_total', {'mode': 'inline', 'app_build': 'unknown'}) or 0.0
    )

    response = _post_sync(client, _filename(0))

    _assert_queued_response(response)
    assert dispatched['should_lock'] is expected_lock
    if single_resolve_percentage == 0:
        credits.assert_called_once_with('synthetic-uid')
        expected_calls = [call('synthetic-uid', None)]
        if not allowance.managed:
            expected_calls.append(call('synthetic-uid'))
        assert resolver.call_args_list == expected_calls
    else:
        credits.assert_not_called()
        resolver.assert_called_once_with('synthetic-uid')
    if dispatch == 'inline':
        fallback.assert_called_once_with(
            component='sync_dispatch',
            from_mode='cloud_tasks',
            to_mode='inline',
            reason='dispatch_disabled',
            outcome='recovered',
        )
        attempts_after = REGISTRY.get_sample_value(
            'omi_sync_dispatch_attempts_total', {'mode': 'inline', 'app_build': 'unknown'}
        )
        assert attempts_after == attempts_before + 1
    else:
        fallback.assert_not_called()


def _allowance(managed, reason):
    return TranscriptionAllowance(
        mode='managed' if managed else 'on_device',
        remaining_seconds=60 if managed else 0,
        reason=reason,
        limit_seconds=60,
    )


@pytest.mark.parametrize('single_resolve_percentage', [None, 0], ids=['default', 'rollback'])
@pytest.mark.parametrize('dispatch', ['cloud_tasks', 'inline'])
@pytest.mark.parametrize(
    'first,second,default_lock,rollback_lock',
    [
        (
            _allowance(False, 'plan_allowance_exhausted'),
            _allowance(False, 'allowance_unavailable'),
            True,
            False,
        ),
        (
            _allowance(False, 'allowance_unavailable'),
            _allowance(False, 'plan_allowance_exhausted'),
            False,
            True,
        ),
        (
            _allowance(False, 'allowance_unavailable'),
            _allowance(True, 'plan_within_allowance'),
            False,
            True,
        ),
    ],
    ids=['persistent-then-transient', 'transient-then-persistent', 'nonmanaged-then-managed'],
)
def test_v2_allowance_sequence_races_and_rollback(
    client, monkeypatch, dispatch, first, second, default_lock, rollback_lock, single_resolve_percentage
):
    """Real allowance objects distinguish the deliberate single-answer behavior from the legacy race."""
    _set_single_resolve_lever(monkeypatch, single_resolve_percentage)
    resolver = Mock(side_effect=[first, second])
    credits = Mock(wraps=subscription.has_transcription_credits)
    monkeypatch.setattr(subscription, 'resolve_transcription_allowance', resolver)
    monkeypatch.setattr(router, 'resolve_transcription_allowance', resolver)
    monkeypatch.setattr(router, 'has_transcription_credits', credits)
    dispatched = _capture_allowance_dispatch(monkeypatch, dispatch)

    response = _post_sync(client, _filename(0))

    _assert_queued_response(response)
    expected_lock = rollback_lock if single_resolve_percentage == 0 else default_lock
    assert dispatched['should_lock'] is expected_lock
    if single_resolve_percentage == 0:
        credits.assert_called_once_with('synthetic-uid')
        assert resolver.call_args_list == [call('synthetic-uid', None), call('synthetic-uid')]
    else:
        credits.assert_not_called()
        resolver.assert_called_once_with('synthetic-uid')


@pytest.mark.parametrize('single_resolve_percentage', [None, 0], ids=['default', 'rollback'])
def test_v2_resolver_exception_never_durably_locks(client, monkeypatch, single_resolve_percentage):
    _set_single_resolve_lever(monkeypatch, single_resolve_percentage)
    answers = []
    real_resolve = subscription.resolve_transcription_allowance

    def resolve(uid, source=None):
        answer = real_resolve(uid, source)
        answers.append(answer)
        return answer

    resolver = Mock(side_effect=resolve)
    credits = Mock(wraps=subscription.has_transcription_credits)
    monkeypatch.setattr(subscription, 'resolve_transcription_allowance', resolver)
    monkeypatch.setattr(subscription, 'is_marketplace_reviewer', lambda _: False)
    monkeypatch.setattr(
        subscription.users_db, 'is_byok_active', Mock(side_effect=RuntimeError('synthetic lookup failure'))
    )
    monkeypatch.setattr(router, 'resolve_transcription_allowance', resolver)
    monkeypatch.setattr(router, 'has_transcription_credits', credits)
    dispatched = _capture_allowance_dispatch(monkeypatch, 'cloud_tasks')

    response = _post_sync(client, _filename(0))

    _assert_queued_response(response)
    assert dispatched['should_lock'] is False
    assert [answer.reason for answer in answers] == ['allowance_unavailable'] * (
        2 if single_resolve_percentage == 0 else 1
    )
    assert all(isinstance(answer, TranscriptionAllowance) for answer in answers)


@pytest.mark.parametrize('single_resolve_percentage', [0, 100])
@pytest.mark.parametrize('execution_managed', [False, True])
async def test_capture_hold_resolves_independently_of_admission_lever(
    tmp_path, monkeypatch, single_resolve_percentage, execution_managed
):
    from models.conversation_enums import ConversationSource
    from unittest.mock import AsyncMock
    from utils.sync import cap_hold

    _set_single_resolve_lever(monkeypatch, single_resolve_percentage)
    admission_resolver = Mock(side_effect=AssertionError('hold reused admission resolver'))
    monkeypatch.setattr(router, 'resolve_transcription_allowance', admission_resolver)
    monkeypatch.setattr(cap_hold, 'enabled', lambda *_: True)
    reason = 'plan_within_allowance' if execution_managed else 'plan_allowance_exhausted'
    execution_resolver = Mock(return_value=_allowance(execution_managed, reason))
    monkeypatch.setattr(cap_hold, 'funded_allowance', execution_resolver)
    hold = AsyncMock()
    monkeypatch.setattr(cap_hold, '_hold_capture', hold)
    admission = {}

    held = await cap_hold.hold_capture_if_exhausted(
        'synthetic-uid', [str(tmp_path / '1792152000.wav')], ConversationSource.omi, admission=admission
    )

    assert held is (not execution_managed)
    execution_resolver.assert_called_once_with('synthetic-uid', lane='sync')
    admission_resolver.assert_not_called()
    if execution_managed:
        hold.assert_not_awaited()
        assert admission == {}
    else:
        hold.assert_awaited_once()
        assert admission == {'reason': reason}


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


EARLY_NAME = 'audio_omi_opus_16000_1_fs160_788918400.bin'  # 1995-01-01


def test_1995_capture_is_admitted_with_closed_metric_and_content_free_log(tmp_path, monkeypatch, caplog):
    monkeypatch.chdir(tmp_path)
    before = _capture_time_counter('accepted_early_clamped')
    with caplog.at_level('INFO'):
        paths = _retrieve_file_paths_v2([_Upload(EARLY_NAME)], 'synthetic-sensitive-owner', 'job')
    assert Path(paths[0]).name == EARLY_NAME
    assert parse_sync_filename_timestamp(EARLY_NAME) == 788918400
    assert capture_clock.clamp_capture_time(788918400, now=1800000000) == 1800000000
    assert capture_clock.clamp_capture_time(788918400, now=1800000000, allow_early_clamp=False) == 788918400
    assert _capture_time_counter('accepted_early_clamped') == before + 1
    lines = [r.getMessage() for r in caplog.records if 'event=sync_capture_time' in r.getMessage()]
    assert len(lines) == 1 and 'outcome=accepted_early_clamped' in lines[0]
    assert 'synthetic-sensitive-owner' not in lines[0] and EARLY_NAME not in lines[0]


def test_early_clock_uses_paced_recovery_without_expiring_bogus_age():
    now = int(datetime.now(timezone.utc).timestamp())
    decision = lanes.classify_sync_lane([EARLY_NAME], client_device_id='pendant', now=now)
    assert decision.lane is lanes.SyncLane.BACKFILL
    assert decision.trust is lanes.CaptureTimeTrust.UNTRUSTED
    assert decision.automatic_recovery_allowed
    assert decision.oldest_capture_at == decision.newest_capture_at == now
    sibling = f'audio_omi_opus_16000_1_fs160_{now - 31 * 86400}.bin'
    mixed = lanes.classify_sync_lane([EARLY_NAME, sibling], client_device_id='pendant', now=now)
    assert not mixed.automatic_recovery_allowed and mixed.reason == 'lookback_exceeded'


def test_v2_1995_clock_kill_switch_restores_typed_400(client, monkeypatch):
    monkeypatch.setenv('SYNC_EARLY_CAPTURE_CLAMP_ENABLED', 'false')
    response = _post_sync(client, EARLY_NAME)
    assert response.status_code == 400, response.text
    assert response.json()['code'] == 'invalid_capture_time'


def test_v2_early_clamp_does_not_admit_malformed_marker(client):
    before = _capture_time_counter('rejected_malformed')
    response = _post_sync(client, 'audio_omi_opus_16000_1_fs160_sd-marker.bin')
    assert response.status_code == 400, response.text
    assert response.json()['code'] == 'invalid_capture_time'
    assert _capture_time_counter('rejected_malformed') == before + 1


def test_early_retry_keeps_raw_name_content_identity_and_reuses_receipt(client, monkeypatch):
    monkeypatch.setattr(router, 'compute_sync_content_id', compute_sync_content_id)
    claims = Mock(side_effect=[{'outcome': 'held', 'result': {}}, {'outcome': 'completed', 'result': {}}])
    monkeypatch.setattr(router, 'claim_sync_content', claims)
    first = _post_sync(client, EARLY_NAME)
    retry = _post_sync(client, EARLY_NAME)
    assert first.status_code == retry.status_code == 202
    assert claims.call_count == 2
    assert claims.call_args_list[0].args[1] == claims.call_args_list[1].args[1]
    assert first.json()['status'] == retry.json()['status'] == 'completed'


def test_early_request_offset_preserves_capture_order_and_duration():
    receipt = 1800000000.0
    # Distinct reset dates cannot preserve bogus decades of wall-clock gap.
    spans = [('later', 1685577600.0, 10.0), ('first', 788918400.0, 10.0)]
    offsets = capture_clock.early_capture_clock_offsets(spans, now=receipt)
    assert 788918400.0 - offsets['first'] == receipt - 20
    assert 1685577600.0 - offsets['later'] == receipt - 10
    assert (1685577610.0 - offsets['later']) == receipt


def test_early_offsets_follow_original_files_when_trimming_reverses_derived_starts():
    receipt = 1800000000.0
    spans = [('older-tail', 1704067209.0, 1.0), ('newer', 1704067195.0, 1.0)]
    offsets = capture_clock.early_capture_clock_offsets(
        spans, now=receipt, source_starts={'older-tail': 1704067190.0, 'newer': 1704067195.0}
    )
    assert 1704067209.0 - offsets['older-tail'] == receipt - 2
    assert 1704067195.0 - offsets['newer'] == receipt - 1


@pytest.mark.asyncio
async def test_vad_segments_inherit_early_source_clock_even_after_crossing_floor(monkeypatch, tmp_path):
    source = str(tmp_path / 'audio_omi_opus_16000_1_fs160_1704067199.wav')
    derived = str(tmp_path / '1704067201.0.wav')
    pipeline.AudioSegment.silent(duration=4000, frame_rate=16000).export(source, format='wav')

    async def inline(_executor, function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(pipeline, 'run_blocking', inline)
    monkeypatch.setattr(pipeline, 'vad_is_empty', lambda *_a, **_k: [{'start': 2.0, 'end': 4.0}])
    segments, early = set(), {}
    errors, _elapsed = await pipeline._run_sync_vad_phase([source], segments, early_segment_times=early)
    assert not errors and segments == set(early) == {derived}
    assert early[derived] == 1704067199
    receipt = 1800000000.0
    offsets = capture_clock.early_capture_clock_offsets(
        [(derived, 1704067201.0, 2.0)], now=receipt, source_starts=early
    )
    assert 1704067201.0 - offsets[derived] == receipt - 2


@pytest.mark.asyncio
@pytest.mark.parametrize('retrim', [False, True])
async def test_coverage_derivatives_keep_original_early_clock_through_vad(monkeypatch, tmp_path, retrim):
    from utils.sync.wal_audio_coverage import apply_wal_audio_coverage, build_sync_source_frame_maps

    source = str(tmp_path / 'audio_omi_pcm16_16000_1704067199.wav')
    pipeline.AudioSegment.silent(duration=4000, frame_rate=16000).export(source, format='wav')
    claim = {
        'capture_root': '123e4567-e89b-12d3-a456-426614174000',
        'clock_epoch': 1,
        'source_frame_start': 0,
        'frame_count': 4,
        'rate_hz': 16000,
        'codec': 'pcm16',
        'channel': 'mono',
    }
    mapping = build_sync_source_frame_maps(
        {Path(source).name.replace('.wav', '.bin'): claim}, [source], {source: [16000] * 4}
    )[source]
    trimmed = apply_wal_audio_coverage(source, claim, [16000] * 4, [(2, 4)], frame_map=mapping)
    assert trimmed is not None
    if retrim:
        [path] = trimmed['wav_paths']
        mapping = trimmed['frame_maps'][path]
        trimmed = apply_wal_audio_coverage(path, mapping['claim'], [16000] * 2, [(3, 4)], frame_map=mapping)
        assert trimmed is not None

    async def inline(_executor, function, *args, **kwargs):
        return function(*args, **kwargs)

    duration = 1 if retrim else 2
    monkeypatch.setattr(pipeline, 'run_blocking', inline)
    monkeypatch.setattr(pipeline, 'vad_is_empty', lambda *_a, **_k: [{'start': 0, 'end': duration}])
    segments, early = set(), {}
    errors, _ = await pipeline._run_sync_vad_phase(trimmed['wav_paths'], segments, trimmed['frame_maps'], {}, early)
    assert not errors and segments == set(early) and len(early) == 1
    [path] = segments
    stamp = pipeline.get_timestamp_from_path(path)
    assert stamp >= capture_clock.EARLIEST_CAPTURE_TIME.timestamp()
    offsets = capture_clock.early_capture_clock_offsets(
        [(path, stamp, duration)], now=1800000000.0, source_starts=early
    )
    assert stamp - offsets[path] == 1800000000.0 - duration


def test_early_clock_does_not_forward_untrusted_client_session_bounds(client, monkeypatch):
    captured = {}

    async def batch_route(**_kwargs):
        return router.RecordUploadRoute.BATCH

    async def accept(**kwargs):
        captured.update(kwargs)
        return JSONResponse(status_code=202, content={'job_id': 'early', 'status': 'queued'})

    monkeypatch.setattr(router, 'registered_record_response', batch_route)
    monkeypatch.setattr(router, 'accept_batch_upload', accept)
    response = client.post(
        '/v2/sync-local-files',
        params={'recording_session_id': 'reset', 'audio_start_seconds': 788918400, 'audio_end_seconds': 1685577601},
        files=[('files', (EARLY_NAME, b'\x00' * 32, 'application/octet-stream'))],
    )
    assert response.status_code == 202, response.text
    assert captured['intake_context']['audio_start_seconds'] is None
    assert captured['intake_context']['audio_end_seconds'] is None


@pytest.mark.parametrize('delta', [None, -10, 170], ids=['early', 'normal', 'future-skew'])
def test_only_reset_clock_uploads_add_receipt_metadata_to_batch_context(client, monkeypatch, delta):
    captured = {}

    async def batch_route(**_kwargs):
        return router.RecordUploadRoute.BATCH

    async def accept(**kwargs):
        captured.update(kwargs)
        return JSONResponse(status_code=202, content={'job_id': 'receipt', 'status': 'queued'})

    monkeypatch.setattr(router, 'registered_record_response', batch_route)
    monkeypatch.setattr(router, 'accept_batch_upload', accept)
    response = _post_sync(client, EARLY_NAME if delta is None else _filename(delta))
    assert response.status_code == 202, response.text
    context = captured['intake_context']
    assert ('capture_received_at' in context) is (delta is None)
    if delta is None:
        assert context['capture_received_at'] > capture_clock.EARLIEST_CAPTURE_TIME.timestamp()


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
    # Admitted data only: the offset comes from the staged filename starts,
    # not the claimed end (round-2 fix), so the whole claimed interval moves
    # by the filename-starts offset.
    from utils.sync.files import get_timestamp_from_path

    offset = capture_clock.capture_clock_offset(get_timestamp_from_path(filename))
    assert intake['audio_start_seconds'] == pytest.approx(raw_start - offset, abs=2.0)
    assert intake['audio_end_seconds'] == pytest.approx(raw_end - offset, abs=2.0)
    assert intake['audio_end_seconds'] <= server_now + 2.0


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


def test_1995_segment_stores_receipt_clock_pair_without_losing_duration():
    from tests.unit.test_sync_cross_job_assignment import conversations

    receipt = datetime.now(timezone.utc).timestamp()
    raw = 788918400.0
    offset = capture_clock.early_capture_clock_offsets([('seg', raw, 10.0)], now=receipt)['seg']
    store, _response, closest_seen, _now_test = _run_skewed_segment(raw, offset, False)
    (stored,) = conversations(store)
    assert stored['started_at'].timestamp() == pytest.approx(receipt - 10, abs=0.01)
    assert stored['finished_at'].timestamp() == pytest.approx(receipt, abs=0.01)
    assert (stored['finished_at'] - stored['started_at']).total_seconds() == pytest.approx(10)
    assert closest_seen['start'] == pytest.approx(receipt - 10, abs=0.01)


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


# --- fix round 2: v1 staging keeps the pre-PR zero future tolerance ---


def test_capture_time_rejection_supports_a_stricter_caller_tolerance():
    """``future_skew_seconds`` lets v1 staging keep its pre-PR zero tolerance."""
    ahead = datetime.now(timezone.utc) + timedelta(seconds=170)
    assert capture_time_rejection(ahead) is None  # shared window admits skew
    assert capture_time_rejection(ahead, future_skew_seconds=0) is SyncCaptureTimeReason.REJECTED_FUTURE
    assert capture_time_rejection(datetime.now(timezone.utc) - timedelta(seconds=10), future_skew_seconds=0) is None


def test_v1_staging_rejects_any_future_capture_time(tmp_path, monkeypatch):
    """V1 (and the chat seams sharing ``retrieve_file_paths``) reject future stamps.

    The v1 inline pipeline runs ``process_segment`` at capture-time offset 0
    and is deprecated, so it keeps the simpler pre-PR contract — any future
    time is the legacy 400 — instead of propagating the request offset. V2
    owns skew admission and normalization.
    """
    from fastapi import HTTPException

    from utils.sync.files import retrieve_file_paths

    monkeypatch.chdir(tmp_path)
    with pytest.raises(HTTPException) as exc_info:
        retrieve_file_paths([_Upload(_filename(171))], 'u1')

    assert exc_info.value.status_code == 400
    assert 'invalid timestamp' in exc_info.value.detail

    past = _filename(-3600)
    assert retrieve_file_paths([_Upload(past)], 'u1') == [f'syncing/u1/{past}']


# --- fix round 2: the lineage planner compares on the server clock ---


def test_lineage_planner_binds_skewed_segment_on_server_clock(monkeypatch):
    """A +171 s raw span must bind its server-clock generation, not miss it.

    The planner's comparison spans and the ``started_before``/``finished_after``
    query bounds shift by the request offset; span keys keep the raw
    capture-clock segment identity. Without the shift the same span misses the
    server-clock row and falls through unbound.
    """
    from utils.sync import recording_lineage

    server_now = datetime.now(timezone.utc).timestamp()
    row = {
        'id': 'gen-live',
        'started_at': datetime.fromtimestamp(server_now - 70, tz=timezone.utc),
        'finished_at': datetime.fromtimestamp(server_now - 10, tz=timezone.utc),
        'source': 'omi',
        'client_device_id': 'pendant',
        'external_data': {'recording_session_id': 'rec-live'},
    }
    captured: dict = {}

    def fake_load_lineage(_uid, _origin, started_before, _client, finished_after, **_kwargs):
        captured['started_before'] = started_before.timestamp()
        captured['finished_after'] = finished_after.timestamp()
        return [dict(row)], None, False

    monkeypatch.setattr(recording_lineage, '_load_lineage', fake_load_lineage)

    raw_start = server_now + 101  # phone clock +171 s over the row's start
    duration = 30.0

    reasons: dict = {}
    targets = recording_lineage.plan_segment_targets(
        ['segment.wav'],
        lambda _p: raw_start,
        lambda _p: duration,
        'u',
        'rec-live',
        None,
        'omi',
        'pendant',
        False,
        'job-1',
        reasons,
        capture_time_offset=171.0,
    )

    assert targets['segment.wav'] == 'gen-live'
    assert reasons['segment.wav'] == 'bound'
    assert captured['finished_after'] == pytest.approx(server_now - 70, abs=1.0)
    assert captured['started_before'] == pytest.approx(server_now - 40 + recording_lineage.START_SKEW_SECONDS, abs=1.0)

    unshifted_reasons: dict = {}
    unshifted_targets = recording_lineage.plan_segment_targets(
        ['segment.wav'],
        lambda _p: raw_start,
        lambda _p: duration,
        'u',
        'rec-live',
        None,
        'omi',
        'pendant',
        False,
        'job-1',
        unshifted_reasons,
    )

    assert unshifted_targets['segment.wav'] is None
    assert unshifted_reasons['segment.wav'] == 'unbound'


@patch('utils.sync.pipeline.get_syncing_file_temporal_signed_url', return_value='url')
@patch('utils.sync.pipeline.prerecorded', return_value=(['word'], 'en'))
@patch('utils.sync.pipeline.postprocess_words')
@patch('utils.sync.pipeline.get_timestamp_from_path')
def test_lineage_bound_skewed_segment_never_consults_the_closest_lookup(
    mock_timestamp, mock_postprocess, _mock_prerecorded, _mock_signed_url
):
    """A lineage-bound target is explicit: the unqualified closest lookup stays out."""
    from models.transcript_segment import TranscriptSegment

    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
    from tests.unit.test_sync_cross_job_assignment import chunk, conversations, intake
    from utils.sync import pipeline

    now_test = datetime.now(timezone.utc).timestamp()
    mock_timestamp.return_value = now_test + 171
    mock_postprocess.return_value = [
        TranscriptSegment(text='Skewed capture speech', start=0.0, end=10.0, is_user=False)
    ]
    live = chunk('live', now_test - 60)
    live['sync_content_revision'] = 1
    store = StrictFirestore()
    store.rows[('users', 'u', 'conversations', 'live')] = dict(live)
    response = {'new_memories': set(), 'updated_memories': set()}
    errors: list = []
    with patch('utils.sync.pipeline.get_closest_conversation_to_timestamps') as mock_closest, patch(
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
            # What the offset-shifted lineage planner produced for this span.
            target_conversation_id='live',
            client_device_id='pendant',
            capture_time_offset=181.0,
        )

    assert result and errors == []
    mock_closest.assert_not_called()
    assert len(conversations(store)) == 1
    assert conversations(store)[0]['id'] == 'live'


# --- fix round 2: the request offset derives from admitted data only ---


def test_v2_route_offset_ignores_inflated_claimed_end(client, monkeypatch):
    """An inflated ``audio_end_seconds`` can neither grow the offset nor the span.

    The offset comes from the staged filename starts alone (decode has not run
    at the seam), and the claimed end is clamped to the admitted span plus one
    chunk of trailing slack — so wildly different inflated claims leave the
    session matching interval in the same place.
    """
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
    filename = _filename(111)  # newest admitted file starts +111 s (phone clock)
    raw_start = server_now + 111

    intervals = []
    for inflated_end in (server_now + 900, server_now + 1800):
        captured.clear()
        response = client.post(
            '/v2/sync-local-files',
            params={
                'recording_session_id': 'rec-live',
                'audio_start_seconds': raw_start,
                'audio_end_seconds': inflated_end,
            },
            files=[('files', (filename, b'\x00' * 32, 'application/octet-stream'))],
        )
        assert response.status_code == 202, response.text
        intake = captured['intake_context']
        intervals.append((intake['audio_start_seconds'], intake['audio_end_seconds']))

    # The interval is identical for both inflated claims: bounded by the
    # admitted span (max filename start + trailing slack), shifted by the
    # filename-starts offset alone.
    assert intervals[0] == pytest.approx(intervals[1], abs=1.0)
    start_seconds, end_seconds = intervals[0]
    assert start_seconds == pytest.approx(server_now, abs=3.0)  # +111 shifted by the +111 offset
    assert end_seconds == pytest.approx(server_now + router.SESSION_CLAIM_TRAILING_SLACK_SECONDS, abs=3.0)


# --- fix round 2: retained chunks persist their playback timing ---


def test_skewed_chunk_metadata_round_trips_playback_start():
    """The write seam stamps the normalized start; the parser rehydrates it.

    ``v2_playback_start`` only moves a start back onto the server clock, so a
    value ahead of the raw span start (or non-finite) is ignored and the span
    stays on the capture clock.
    """
    from database.audio_timeline import parse_span_blob_metadata

    raw_start = datetime.now(timezone.utc).timestamp() + 171
    normalized = raw_start - 171

    written = {
        'v2_start': repr(raw_start),
        'v2_samples': '160000',
        'v2_sample_rate': '16000',
        'v2_playback_start': repr(normalized),
    }
    assert parse_span_blob_metadata(written) == {
        'start': raw_start,
        'samples': 160000,
        'sample_rate': 16000,
        'playback_start': normalized,
    }

    ignored = dict(written, v2_playback_start=repr(raw_start + 1))
    assert 'playback_start' not in parse_span_blob_metadata(ignored)
    malformed = dict(written, v2_playback_start='not-a-number')
    assert 'playback_start' not in parse_span_blob_metadata(malformed)
    legacy = {'v2_start': repr(raw_start), 'v2_samples': '160000', 'v2_sample_rate': '16000'}
    assert 'playback_start' not in parse_span_blob_metadata(legacy)


def test_store_sync_audio_chunk_passes_playback_start_to_the_upload():
    """The store chain forwards the normalized start beside the raw chunk key."""
    from utils.sync.merge_audio import store_sync_audio_chunk

    uploaded: list[dict] = []

    def fake_upload(pcm, uid, conversation_id, timestamp, data_protection_level, playback_start=None):
        uploaded.append({'timestamp': timestamp, 'playback_start': playback_start, 'bytes': pcm})
        return 'chunks/u/c/1.0.opus'

    raw_start = datetime.now(timezone.utc).timestamp() + 171

    store_sync_audio_chunk(
        'u',
        'c',
        raw_start,
        b'wav-bytes',
        None,
        playback_start=raw_start - 171,
        decode_audio=lambda _b: b'\x00' * 3200,
        upload_audio=fake_upload,
    )

    assert uploaded == [{'timestamp': raw_start, 'playback_start': raw_start - 171, 'bytes': b'\x00' * 3200}]


@patch('utils.sync.pipeline.get_syncing_file_temporal_signed_url', return_value='url')
@patch('utils.sync.pipeline.prerecorded', return_value=(['word'], 'en'))
@patch('utils.sync.pipeline.postprocess_words')
@patch('utils.sync.pipeline.get_timestamp_from_path')
def test_skewed_private_cloud_chunk_persist_normalized_playback_start(
    mock_timestamp, mock_postprocess, _mock_prerecorded, _mock_signed_url
):
    """process_segment hands retained audio its server-clock playback basis."""
    from models.transcript_segment import TranscriptSegment

    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
    from tests.unit.test_sync_cross_job_assignment import intake
    from utils.sync import pipeline

    now_test = datetime.now(timezone.utc).timestamp()
    mock_timestamp.return_value = now_test + 171
    mock_postprocess.return_value = [
        TranscriptSegment(text='Skewed capture speech', start=0.0, end=10.0, is_user=False)
    ]
    stored: list[dict] = []

    def fake_store_intake_audio(*_args, **kwargs):
        stored.append(kwargs)

    response = {'new_memories': set(), 'updated_memories': set()}
    errors: list = []
    store = StrictFirestore()
    with patch('utils.sync.pipeline._store_intake_audio', side_effect=fake_store_intake_audio), patch(
        # The bridge finalize follows a real private-cloud conversation; the
        # store-chain kwargs under test are already captured by then.
        'utils.sync.pipeline.finish_sync_segment'
    ), patch(
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
    ), patch(
        'utils.sync.pipeline._download_audio_bytes', return_value=b'wav'
    ):
        result = pipeline.process_segment(
            'seg_123.wav',
            'u',
            response,
            MagicMock(),
            errors,
            private_cloud_sync_enabled=True,
            capture_time_offset=181.0,
        )

    assert result and errors == []
    assert stored, 'retained audio must reach the store chain'
    assert stored[0]['playback_clock_offset'] == pytest.approx(181.0)
    # The raw +171 s stamp shifted by the request offset lands at the stored
    # pair's server-clock start (clamped to now at latest).
    assert stored[0]['playback_start'] == pytest.approx(now_test - 10, abs=1.0)
    assert stored[0]['playback_start'] <= datetime.now(timezone.utc).timestamp()


@pytest.mark.parametrize('payload', [b'', b'\x01', b'\x01\x00\x00\x00'])
def test_v2_empty_or_torn_header_is_noop_even_with_invalid_clock(client, payload):
    response = client.post('/v2/sync-local-files', files=[('files', (_filename(5 * 365 * 86400), payload))])
    assert response.status_code == 200
    assert response.json() == {'new_memories': [], 'updated_memories': []}
    router.create_sync_job.assert_not_called()


def test_v2_mixed_empty_invalid_clock_and_valid_audio_keeps_audio(client):
    response = client.post(
        '/v2/sync-local-files',
        files=[
            ('files', (_filename(5 * 365 * 86400), b'')),
            ('files', (_filename(-10), b'\x01\x00\x00\x00\x42')),
        ],
    )
    assert response.status_code == 202
    router.create_sync_job.assert_called_once()


def test_v2_invalid_filename_returns_closed_code_with_legacy_string_detail(client):
    response = client.post('/v2/sync-local-files', files=[('files', ('audio.mp3', b'12345'))])
    assert response.status_code == 400
    assert response.json() == {'code': 'invalid_file', 'detail': 'Invalid sync file format'}


def test_v2_non400_http_failures_keep_original_status(client, monkeypatch):
    def denied(*_args):
        raise HTTPException(status_code=403, detail='Synthetic denial')

    monkeypatch.setattr(router, '_retrieve_file_paths_v2', denied)
    response = _post_sync(client, _filename(-10))
    assert response.status_code == 403
    assert response.json() == {'detail': 'Synthetic denial'}


def test_mixed_empty_clip_preserves_manifest_proof_for_remaining_audio(client, monkeypatch):
    empty_name, audio_name = _filename(5 * 365 * 86400), _filename(-10)
    audio = b'\x01\0\0\0\x42'
    claims = [
        {'name': empty_name, 'sha256': hashlib.sha256(b'').hexdigest()},
        {'name': audio_name, 'sha256': hashlib.sha256(audio).hexdigest()},
    ]
    seen_names = []

    def verified(_token, _uid, _device, _conversation, filenames):
        seen_names.extend(filenames)
        return claims

    monkeypatch.setattr(router, 'verify_capture_manifest', verified)
    monkeypatch.setattr(router, '_capture_matches_server_conversation', lambda *_a, **_k: True)
    response = client.post('/v2/sync-local-files', files=[('files', (empty_name, b'')), ('files', (audio_name, audio))])
    assert response.status_code == 202, response.text
    assert seen_names == [empty_name, audio_name]


# --- trailing collision sequence (released apps: `<stem>_<ts>_u<n>.bin`) ---
#
# Prod 10-31 18Z..11-01 18Z: 4,374 of 12,531 invalid_capture_time refusals
# (~367 of 428 users) were `rejected_malformed`, and their claimed audio start
# sat days in the past: a sound clock, refused only because the name ends in
# `u<n>`. Same file, same refusal, on every retry.


def _collided(seconds_from_now: float, run: str = '') -> str:
    stamp = (datetime.now(timezone.utc) + timedelta(seconds=seconds_from_now)).timestamp()
    clock = f'_clke{run}' if run else ''
    return f'audio_omi_opus_16000_1_fs160{clock}_{stamp:.0f}_u3.bin'


@pytest.mark.parametrize(
    'name, expected',
    [
        ('audio_omi_opus_16000_1_fs160_1761955200_u3.bin', 'audio_omi_opus_16000_1_fs160_u3_1761955200.bin'),
        (
            'audio_omi_opus_16000_1_fs160_clkeab12cd_1761955200_u0.bin',
            'audio_omi_opus_16000_1_fs160_u0_clkeab12cd_1761955200.bin',
        ),
        ('audio_omi_opus_16000_1_fs160_1761955200.5_u12.bin', 'audio_omi_opus_16000_1_fs160_u12_1761955200.5.bin'),
        # Already canonical, ordinary, or not a collision tail: untouched.
        ('audio_omi_opus_16000_1_fs160_u3_1761955200.bin', 'audio_omi_opus_16000_1_fs160_u3_1761955200.bin'),
        ('audio_omi_opus_16000_1_fs160_1761955200.bin', 'audio_omi_opus_16000_1_fs160_1761955200.bin'),
        ('audio_omi_opus_16000_1_fs160_not-a-number.bin', 'audio_omi_opus_16000_1_fs160_not-a-number.bin'),
        ('audio_omi_opus_16000_1_fs160_1761955200_ux.bin', 'audio_omi_opus_16000_1_fs160_1761955200_ux.bin'),
        ('', ''),
    ],
)
def test_canonical_name_moves_trailing_collision_sequence_before_capture_time(name, expected):
    assert canonical_sync_upload_filenames([name]) == [expected]


def test_canonical_name_keeps_capture_time_and_clock_run():
    original = 'audio_omi_opus_16000_1_fs160_clkeab12cd_1761955200_u3.bin'
    [canonical] = canonical_sync_upload_filenames([original])

    assert get_timestamp_from_path(canonical) == 1761955200
    assert clock_run_from_path(canonical) == 'ab12cd'
    with pytest.raises(ValueError):
        get_timestamp_from_path(original)


def test_canonical_names_never_collapse_two_uploads_into_one_staged_file():
    names = ['audio_omi_opus_16000_1_fs160_u3_1761955200.bin', 'audio_omi_opus_16000_1_fs160_1761955200_u3.bin']

    assert canonical_sync_upload_filenames(names) == names


def test_v2_route_admits_collision_suffixed_upload_with_sound_clock(client, monkeypatch):
    staged = []
    real_retrieve = router._retrieve_file_paths_v2

    def capture(files, uid, job_id):
        staged.extend(f.filename for f in files)
        return real_retrieve(files, uid, job_id)

    monkeypatch.setattr(router, '_retrieve_file_paths_v2', capture)
    before = _capture_time_counter('rejected_malformed')
    name = _collided(-10)

    response = _post_sync(client, name)

    assert response.status_code == 202, response.text
    assert staged == [name.replace('_u3.bin', '.bin').replace('_fs160_', '_fs160_u3_')]
    assert _capture_time_counter('rejected_malformed') == before


def test_manifest_claim_follows_its_file_to_the_canonical_name():
    collided, plain = 'audio_omi_opus_16000_1_fs160_1761955200_u3.bin', 'audio_omi_opus_16000_1_fs160_1761955300.bin'
    claims = [{'name': collided, 'sha256': 'a'}, {'name': plain, 'sha256': 'b'}]
    staged = canonical_sync_upload_filenames([collided, plain])

    assert nonempty_manifest_claims(claims, staged) == [
        {'name': plain, 'sha256': 'b'},
        {'name': 'audio_omi_opus_16000_1_fs160_u3_1761955200.bin', 'sha256': 'a'},
    ]
    # Unrenamed requests keep the verified claims exactly as before.
    assert nonempty_manifest_claims(claims, [collided, plain]) == claims


def test_v2_route_keeps_manifest_proof_for_collision_suffixed_upload(client, monkeypatch):
    collided, plain = _collided(-20), _filename(-10)
    audio_a, audio_b = b'\x01\0\0\0\x42', b'\x01\0\0\0\x43'
    claims = sorted(
        [
            {'name': collided, 'sha256': hashlib.sha256(audio_a).hexdigest()},
            {'name': plain, 'sha256': hashlib.sha256(audio_b).hexdigest()},
        ],
        key=lambda item: item['name'],
    )
    seen_names = []

    def verified(_token, _uid, _device, _conversation, filenames):
        seen_names.extend(filenames)
        return claims

    monkeypatch.setattr(router, 'verify_capture_manifest', verified)
    monkeypatch.setattr(router, '_capture_matches_server_conversation', lambda *_a, **_k: True)
    response = client.post('/v2/sync-local-files', files=[('files', (collided, audio_a)), ('files', (plain, audio_b))])

    assert response.status_code == 202, response.text
    assert seen_names == [collided, plain]


def test_v2_route_still_refuses_collision_suffixed_upload_with_broken_clock(client):
    before = _capture_time_counter('rejected_future')

    response = _post_sync(client, _collided(5 * 365 * 86400, run='ab12cd'))

    assert response.status_code == 400, response.text
    assert response.json()['code'] == 'invalid_capture_time'
    assert _capture_time_counter('rejected_future') == before + 1
