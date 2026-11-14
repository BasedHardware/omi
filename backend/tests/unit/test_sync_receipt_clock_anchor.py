"""Newest-first requests retain device/run chronology through immutable anchors."""

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from database import sync_capture_clock as database
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_batch_pipeline_audio import pcm
from utils.batch_pipeline.capture_decode import decode_units
from utils.sync import receipt_clock
from utils.capture import coverage
from models.capture_coverage import FrameRange

RECEIVED = datetime(2026, 11, 15, tzinfo=timezone.utc).timestamp()
FUTURE = datetime(2038, 1, 19, tzinfo=timezone.utc).timestamp()


@pytest.fixture
def anchors(monkeypatch):
    store = StrictFirestore()

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


def units(directory, starts, *, received=RECEIVED, device='ios_abcd1234', owner='synthetic', run=None):
    directory.mkdir()
    paths = []
    for stamp in starts:
        source = Path(pcm(directory, int(stamp), 16000))
        name = f'audio_omi_pcm16_16000_{"clke" + run + "_" if run else ""}{int(stamp)}_u0.bin'
        target = source.with_name(name)
        source.rename(target)
        paths.append(str(target))
    return list(decode_units(paths, received_at=received, clock_context={'uid': owner, 'device_id': device}))


@pytest.mark.parametrize('clock', [FUTURE, 788918400.0], ids=['future', 'early'])
def test_newest_first_requests_preserve_order_gaps_and_nonoverlap(anchors, tmp_path, clock):
    newer = units(tmp_path / 'newer', [clock + 600, clock + 610])
    before = deepcopy(anchors.rows)
    older = units(tmp_path / 'older', [clock, clock + 10], received=RECEIVED + 2)
    all_units = sorted(older + newer, key=lambda unit: unit.capture_at)
    assert anchors.rows == before  # Offset never moves on a later request.
    assert [u.stored_capture_at for u in all_units] == [RECEIVED - 611, RECEIVED - 601, RECEIVED - 11, RECEIVED - 1]
    for left, right in zip(all_units, all_units[1:]):
        assert left.stored_capture_at + left.duration_seconds <= right.stored_capture_at
        assert right.stored_capture_at - left.stored_capture_at == right.capture_at - left.capture_at
    assert all(u.stored_capture_at + u.duration_seconds <= RECEIVED for u in all_units)


def test_devices_owners_and_runs_have_distinct_anchors(anchors, tmp_path, monkeypatch):
    monkeypatch.setenv('SYNC_CLOCK_RUN_PARTITION_ENABLED', 'false')
    scopes = [
        ('ios_aabbccdd', 'one', 'owner-a'),
        ('ios_11223344', 'one', 'owner-a'),
        ('ios_aabbccdd', 'two', 'owner-a'),
        ('ios_aabbccdd', 'one', 'owner-b'),
    ]
    for index, (device, run, owner) in enumerate(scopes):
        [unit] = units(
            tmp_path / str(index), [FUTURE], received=RECEIVED + index * 10, device=device, run=run, owner=owner
        )
        assert unit.stored_capture_at == RECEIVED + index * 10 - 1
    assert len(anchors.rows) == 4


def test_admission_kill_switch_cannot_change_a_retained_anchor(anchors, tmp_path, monkeypatch):
    units(tmp_path / 'first', [FUTURE + 100])
    before = deepcopy(anchors.rows)
    monkeypatch.setenv('SYNC_FUTURE_CAPTURE_CLAMP_ENABLED', 'false')
    [unit] = units(tmp_path / 'later', [FUTURE], received=RECEIVED + 100)
    assert unit.stored_capture_at == RECEIVED - 101
    assert anchors.rows == before


def test_newer_clock_jump_waits_instead_of_moving_or_clamping_an_anchor(anchors, tmp_path):
    units(tmp_path / 'first', [FUTURE])
    before = deepcopy(anchors.rows)
    with pytest.raises(HTTPException) as error:
        units(tmp_path / 'jump', [FUTURE + 1000], received=RECEIVED + 1)
    assert error.value.status_code == 503
    assert error.value.detail == 'capture_clock_anchor_pending'
    assert anchors.rows == before


def test_derived_source_preserves_the_original_run_scope(anchors):
    path = 'audio_omi_pcm16_16000_clkeabc_2147472000_u0.wav'
    offsets = receipt_clock.receipt_clock_offsets(
        [(path, FUTURE, 10)], uid='synthetic', device_id='phone', received_at=RECEIVED
    )
    scope = receipt_clock.clock_scope(path, FUTURE, 'phone')
    derivative = 'unrelated_2147472005.wav'
    inherited = receipt_clock.inherited_offsets(
        [(derivative, FUTURE + 5, 2)],
        scope_offsets={scope: offsets[path]},
        device_id='phone',
        source_starts={derivative: FUTURE},
        source_paths={derivative: path},
    )
    assert inherited[derivative] == offsets[path]


def test_missing_device_cannot_create_an_account_wide_anchor(anchors):
    with pytest.raises(HTTPException, match='capture_clock_identity_required'):
        receipt_clock.receipt_clock_offsets(
            [('file.wav', FUTURE, 1)], uid='synthetic', device_id='', received_at=RECEIVED
        )
    assert not anchors.rows


def test_trimmed_collision_upload_keeps_original_run_and_full_decode_anchor(anchors, tmp_path, monkeypatch):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE_SERVE_PERCENT', '100')
    monkeypatch.setenv('SYNC_CLOCK_RUN_PARTITION_ENABLED', 'false')
    source = Path(pcm(tmp_path, int(FUTURE), 16000))
    target = source.with_name(f'audio_omi_pcm16_16000_clkeone_{int(FUTURE)}_u0.bin')
    target.write_bytes(source.read_bytes() * 2)  # Two one-second source frames.
    source.unlink()
    claim = {
        'capture_root': '123e4567-e89b-12d3-a456-426614174000',
        'clock_epoch': 1,
        'source_frame_start': 0,
        'frame_count': 2,
        'rate_hz': 16000,
        'codec': 'pcm16',
        'channel': 'mono',
    }
    monkeypatch.setattr(
        coverage, 'admit', lambda *args, **kwargs: SimpleNamespace(covered=[FrameRange(start=1, end=2)])
    )
    [unit] = list(
        decode_units(
            [str(target)],
            received_at=RECEIVED,
            clock_context={'uid': 'synthetic', 'device_id': 'phone'},
            coverage_context={
                'uid': 'synthetic',
                'client_device_id': 'phone',
                'capture_evidence_claims': {target.name: claim},
            },
        )
    )
    assert unit.duration_seconds == 1
    assert unit.capture_at == FUTURE and unit.stored_capture_at == RECEIVED - 2
    assert unit.coverage_runs[0]['start'] == 0 and unit.coverage_runs[0]['end'] == 1
    before = deepcopy(anchors.rows)
    [older] = units(tmp_path / 'older', [FUTURE - 10], device='phone', run='one')
    assert older.stored_capture_at == RECEIVED - 12
    assert anchors.rows == before and len(before) == 1
