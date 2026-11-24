"""Future-only run anchors retain chronology and fail closed at account bounds."""

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import struct
from types import SimpleNamespace

import pytest

from database import sync_capture_clock as database
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_batch_pipeline_audio import pcm
from utils.batch_pipeline.future_capture_decode import decode_future_units
from utils.sync import receipt_clock
from utils.capture import coverage
from models.capture_coverage import FrameRange

RECEIVED = datetime(2026, 11, 15, tzinfo=timezone.utc).timestamp()
FUTURE = datetime(2038, 1, 19, tzinfo=timezone.utc).timestamp()
OUTCOMES = ('anchored', 'anchor_pending', 'identity_required', 'anchor_error', 'refused')


def recovery_counts():
    metric = receipt_clock._recovery_counter()
    return {outcome: metric.labels(outcome=outcome)._value.get() for outcome in OUTCOMES}


@pytest.fixture
def anchors(monkeypatch):
    store = StrictFirestore()
    monkeypatch.setattr(receipt_clock, 'time', lambda: RECEIVED)
    monkeypatch.setattr(receipt_clock, 'account_created_at', lambda _: RECEIVED - 4000)

    def transactional(fn):
        def commit(tx):
            with store.lock:
                value = fn(tx)
                tx._commit()
                return value

        return commit

    monkeypatch.setattr(database.firestore, 'transactional', transactional)
    monkeypatch.setattr(database, 'get_firestore_client', lambda: store)
    return store


def units(directory, starts, *, received=RECEIVED, device='ios_abcd1234', owner='synthetic', run='one', context=None):
    directory.mkdir()
    paths = []
    for stamp in starts:
        source = Path(pcm(directory, int(stamp), 16000))
        name = f'audio_omi_pcm16_16000_u0_{"clke" + run + "_" if run else ""}{int(stamp)}.bin'
        target = source.with_name(name)
        source.rename(target)
        paths.append(str(target))
    return list(decode_future_units(paths, received_at=received, uid=owner, device_id=device, coverage_context=context))


def test_newest_first_requests_preserve_order_gaps_and_nonoverlap(anchors, tmp_path):
    before_counts = recovery_counts()
    newer = units(tmp_path / 'newer', [FUTURE + 600, FUTURE + 610])
    assert recovery_counts() == {**before_counts, 'anchored': before_counts['anchored'] + 1}
    before = deepcopy(anchors.rows)
    older = units(tmp_path / 'older', [FUTURE, FUTURE + 10], received=RECEIVED + 2)
    all_units = sorted(older + newer, key=lambda unit: unit.capture_at)
    assert anchors.rows == before
    assert recovery_counts() == {**before_counts, 'anchored': before_counts['anchored'] + 2}
    assert [u.stored_capture_at for u in all_units] == [RECEIVED - 611, RECEIVED - 601, RECEIVED - 11, RECEIVED - 1]
    for left, right in zip(all_units, all_units[1:]):
        assert left.stored_capture_at + left.duration_seconds <= right.stored_capture_at
        assert right.stored_capture_at - left.stored_capture_at == right.capture_at - left.capture_at


def test_devices_owners_and_runs_have_distinct_anchors(anchors, tmp_path, monkeypatch):
    monkeypatch.setenv('SYNC_CLOCK_RUN_PARTITION_ENABLED', 'false')
    scopes = [
        ('ios_aabbccdd', 'one', 'a'),
        ('ios_11223344', 'one', 'a'),
        ('ios_aabbccdd', 'two', 'a'),
        ('ios_aabbccdd', 'one', 'b'),
    ]
    for index, (device, run, owner) in enumerate(scopes):
        [unit] = units(
            tmp_path / str(index), [FUTURE], received=RECEIVED + index * 10, device=device, run=run, owner=owner
        )
        assert unit.stored_capture_at == RECEIVED + index * 10 - 1
    assert len(anchors.rows) == 4


def test_admission_switch_cannot_change_an_admitted_anchor(anchors, tmp_path, monkeypatch):
    units(tmp_path / 'first', [FUTURE + 100])
    before = deepcopy(anchors.rows)
    monkeypatch.setenv('SYNC_FUTURE_CAPTURE_CLAMP_ENABLED', 'false')
    [unit] = units(tmp_path / 'later', [FUTURE], received=RECEIVED + 100)
    assert unit.stored_capture_at == RECEIVED - 101
    assert anchors.rows == before


@pytest.mark.parametrize('stamp', [788918400])
def test_early_clock_never_gets_a_future_anchor(anchors, tmp_path, stamp):
    with pytest.raises(receipt_clock.FutureCaptureRefused) as error:
        units(tmp_path / 'unmarked', [stamp], run=None)
    assert error.value.status_code == 400 and error.value.detail['code'] == 'invalid_capture_time'
    assert not anchors.rows


def test_discontinuous_forward_run_requires_a_new_token(anchors, tmp_path):
    units(tmp_path / 'first', [FUTURE])
    before = deepcopy(anchors.rows)
    with pytest.raises(receipt_clock.FutureCaptureRefused):
        units(tmp_path / 'reset', [FUTURE + 90000], received=RECEIVED + 1)
    assert anchors.rows == before
    [unit] = units(tmp_path / 'new-run', [FUTURE + 90000], received=RECEIVED + 1, run='two')
    assert unit.stored_capture_at == RECEIVED


def test_pending_frozen_mapping_can_drain_when_server_clock_catches_up(anchors, tmp_path, monkeypatch):
    units(tmp_path / 'first', [FUTURE])
    before = deepcopy(anchors.rows)
    with pytest.raises(receipt_clock.FutureCaptureRetry) as error:
        units(tmp_path / 'pending', [FUTURE + 1000], received=RECEIVED + 1)
    assert error.value.detail['code'] == 'capture_clock_anchor_pending'
    monkeypatch.setattr(receipt_clock, 'time', lambda: RECEIVED + 1001)
    [unit] = units(tmp_path / 'retry', [FUTURE + 1000], received=RECEIVED + 1)
    assert unit.stored_capture_at == RECEIVED + 999 and anchors.rows == before


def test_account_bound_refuses_a_wide_gap_before_creating_an_anchor(anchors, tmp_path):
    with pytest.raises(receipt_clock.FutureCaptureRefused):
        units(tmp_path / 'too-old', [FUTURE - 10000, FUTURE])
    assert not anchors.rows


def test_account_bound_also_checks_later_requests_without_moving_anchor(anchors, tmp_path):
    units(tmp_path / 'first', [FUTURE])
    before = deepcopy(anchors.rows)
    with pytest.raises(receipt_clock.FutureCaptureRefused):
        units(tmp_path / 'older', [FUTURE - 10000])
    assert anchors.rows == before


def test_exhausted_anchor_transaction_is_retryable_without_alternate_offset(anchors, tmp_path, monkeypatch):
    def exhausted(*args, **kwargs):
        raise ValueError('Failed to commit transaction in 5 attempts')

    monkeypatch.setattr(receipt_clock, 'frozen_offset', exhausted)
    before_counts = recovery_counts()
    with pytest.raises(receipt_clock.FutureCaptureRetry) as error:
        units(tmp_path / 'contended', [FUTURE])
    assert error.value.status_code == 503
    assert error.value.headers == {'Retry-After': '30'}
    assert not anchors.rows
    assert recovery_counts() == {**before_counts, 'anchor_error': before_counts['anchor_error'] + 1}


@pytest.mark.parametrize(
    'outcome,status,code',
    [
        ('anchor_pending', 503, 'capture_clock_anchor_pending'),
        ('identity_required', 503, 'capture_clock_identity_required'),
        ('anchor_error', 503, 'capture_clock_anchor_unavailable'),
        ('refused', 400, 'invalid_capture_time'),
    ],
)
def test_offset_exit_is_counted_once_and_preserves_response(anchors, monkeypatch, outcome, status, code):
    def unavailable(_uid):
        raise RuntimeError('account creation read unavailable')

    span = (f'audio_omi_pcm16_16000_u0_clkeone_{int(FUTURE)}.wav', FUTURE, 1.0)
    spans = [span]
    device = 'ios_abcd1234'
    if outcome == 'anchor_pending':
        receipt_clock.receipt_clock_offsets(spans, uid='synthetic', device_id=device, received_at=RECEIVED)
        path, start, duration = span
        spans = [(path, start + 10, duration)]
    elif outcome == 'identity_required':
        device = None
    elif outcome == 'anchor_error':
        monkeypatch.setattr(receipt_clock, 'account_created_at', unavailable)
    else:
        spans = []

    before_counts = recovery_counts()
    before_rows = deepcopy(anchors.rows)
    error_type = receipt_clock.FutureCaptureRetry if status == 503 else receipt_clock.FutureCaptureRefused
    with pytest.raises(error_type) as caught:
        receipt_clock.receipt_clock_offsets(spans, uid='synthetic', device_id=device, received_at=RECEIVED)

    expected = error_type(code) if status == 503 else error_type()
    assert caught.value.status_code == status
    assert caught.value.detail == expected.detail
    assert caught.value.headers == expected.headers
    assert anchors.rows == before_rows
    assert recovery_counts() == {**before_counts, outcome: before_counts[outcome] + 1}


@pytest.mark.parametrize('detail', ['unstructured retry', {}, {'code': []}, {'code': 'unrecognized'}])
def test_unclassified_retry_detail_preserves_original_exception(monkeypatch, detail):
    retry = receipt_clock.FutureCaptureRetry()
    retry.detail = detail

    def unavailable(*args, **kwargs):
        raise retry

    monkeypatch.setattr(receipt_clock, '_resolve_receipt_clock_offsets', unavailable)
    before_counts = recovery_counts()
    with pytest.raises(receipt_clock.FutureCaptureRetry) as caught:
        receipt_clock.receipt_clock_offsets([], uid='synthetic', device_id=None, received_at=RECEIVED)
    assert caught.value is retry
    assert caught.value.detail == detail
    assert caught.value.headers == {'Retry-After': '30'}
    assert recovery_counts() == {**before_counts, 'anchor_error': before_counts['anchor_error'] + 1}


def test_metrics_failure_preserves_offsets_and_retry(anchors, monkeypatch):
    class BrokenCounter:
        def labels(self, *, outcome):
            return self

        def inc(self):
            raise RuntimeError('metrics unavailable')

    monkeypatch.setattr(receipt_clock, '_recovery_counter', BrokenCounter)
    path = f'audio_omi_pcm16_16000_u0_clkeone_{int(FUTURE)}.wav'
    spans = [(path, FUTURE, 1.0)]
    assert receipt_clock.receipt_clock_offsets(
        spans, uid='synthetic', device_id='ios_abcd1234', received_at=RECEIVED
    ) == {path: FUTURE + 1 - RECEIVED}
    with pytest.raises(receipt_clock.FutureCaptureRetry) as caught:
        receipt_clock.receipt_clock_offsets(spans, uid='synthetic', device_id=None, received_at=RECEIVED)
    assert caught.value.status_code == 503
    assert caught.value.detail['code'] == 'capture_clock_identity_required'
    assert caught.value.headers == {'Retry-After': '30'}
    assert len(anchors.rows) == 1


def test_coverage_trim_inherits_full_decode_anchor_and_retains_source_proof(anchors, tmp_path, monkeypatch):
    monkeypatch.setenv('SYNC_FUTURE_CAPTURE_CLAMP_ENABLED', 'false')  # Accepted audio still drains after rollback.
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    monkeypatch.setenv('CAPTURE_COVERAGE_PERCENT', '100')
    monkeypatch.setattr(coverage, 'admit', lambda *_a, **_k: SimpleNamespace(covered=[FrameRange(start=0, end=1)]))
    directory = tmp_path / 'trim'
    directory.mkdir()
    path = Path(pcm(directory, int(FUTURE), 32000)).rename(
        directory / f'audio_omi_pcm16_16000_u0_clkeone_{int(FUTURE)}.bin'
    )
    path.write_bytes(b''.join(struct.pack('<I', 32000) + struct.pack('<h', sample) * 16000 for sample in (1, 2)))
    claim = {
        'capture_root': '123e4567-e89b-12d3-a456-426614174000',
        'clock_epoch': 1,
        'source_frame_start': 0,
        'frame_count': 2,
        'rate_hz': 16000,
        'codec': 'pcm16',
        'channel': 'mono',
    }
    [unit] = list(
        decode_future_units(
            [str(path)],
            received_at=RECEIVED,
            uid='synthetic',
            device_id='ios_abcd1234',
            coverage_context={
                'uid': 'synthetic',
                'capture_evidence_claims': {path.name: claim},
                'client_device_id': 'ios_abcd1234',
            },
        )
    )
    assert unit.capture_at == FUTURE + 1 and unit.stored_capture_at == RECEIVED - 1
    assert unit.coverage_runs and unit.coverage_runs[0]['start'] == 1


def test_account_lower_bound_uses_auth_creation_metadata(monkeypatch):
    monkeypatch.setattr(
        database.auth, 'get_user', lambda _: SimpleNamespace(user_metadata=SimpleNamespace(creation_timestamp=100_000))
    )
    assert database.account_created_at('synthetic') == 100


def test_unmarked_files_have_independent_receipt_dates_without_guessing_order(anchors, tmp_path):
    # Newest-first raw order, different request receipt times: no ordering claim.
    [newer] = units(tmp_path / 'newer', [FUTURE + 600], run=None, device=None)
    [older] = units(tmp_path / 'older', [FUTURE], received=RECEIVED + 10, run=None, device=None)
    assert newer.stored_capture_at == RECEIVED - 1
    assert older.stored_capture_at == RECEIVED + 9
    assert newer.recovery_id != older.recovery_id
    assert len(anchors.rows) == 2


def test_unmarked_replay_freezes_date_and_source_identity_across_bundles(anchors, tmp_path):
    [first] = units(tmp_path / 'first', [FUTURE], run=None)
    before = deepcopy(anchors.rows)
    retry = units(tmp_path / 'retry', [FUTURE, FUTURE + 100], received=RECEIVED + 1000, run=None)
    replay = next(u for u in retry if u.capture_at == FUTURE)
    assert replay.stored_capture_at == first.stored_capture_at
    assert replay.recovery_id == first.recovery_id
    assert all(anchors.rows[key] == value for key, value in before.items())
    assert len(anchors.rows) == 2


def test_distinct_unmarked_bytes_with_identical_raw_stamp_never_share_identity(anchors, tmp_path):
    [first] = units(tmp_path / 'first', [FUTURE], run=None)
    directory = tmp_path / 'other'
    directory.mkdir()
    path = Path(pcm(directory, int(FUTURE), 16000)).rename(directory / f'audio_omi_pcm16_16000_u0_{int(FUTURE)}.bin')
    path.write_bytes(struct.pack('<I', 32000) + struct.pack('<h', 7) * 16000)
    [other] = list(decode_future_units([str(path)], uid='synthetic', device_id=None, received_at=RECEIVED))
    assert other.capture_at == first.capture_at
    assert other.recovery_id != first.recovery_id
    assert len(anchors.rows) == 2


@pytest.mark.parametrize('ahead', [86401, 90000])
def test_unmarked_clock_beyond_day_is_receipt_recovered(anchors, tmp_path, ahead):
    [unit] = units(tmp_path / str(ahead), [RECEIVED + ahead], run=None, device=None)
    assert unit.stored_capture_at == RECEIVED - 1


def test_unmarked_retry_after_switch_off_preserves_original_anchor_and_source_identity(anchors, tmp_path, monkeypatch):
    [original] = units(tmp_path / 'original', [FUTURE], run=None)
    before = deepcopy(anchors.rows)
    monkeypatch.setenv('SYNC_FUTURE_CAPTURE_CLAMP_ENABLED', 'false')
    [retry] = units(tmp_path / 'retry', [FUTURE], run=None, received=RECEIVED + 100)
    assert retry.stored_capture_at == original.stored_capture_at
    assert retry.recovery_id == original.recovery_id and anchors.rows == before


def test_mixed_bundle_recovers_only_future_sources_and_preserves_ordinary_clock(anchors, tmp_path):
    recovered = units(tmp_path / 'mixed', [RECEIVED - 10, FUTURE], run=None)
    ordinary = next(unit for unit in recovered if unit.capture_at == RECEIVED - 10)
    future = next(unit for unit in recovered if unit.capture_at == FUTURE)
    assert ordinary.stored_capture_at is None and ordinary.recovery_id is None
    assert future.stored_capture_at == RECEIVED - 1 and future.recovery_id
    assert len(anchors.rows) == 1
