"""Custody-preserving regressions for receipt recovery review findings."""

from dataclasses import asdict, replace
from types import SimpleNamespace

import pytest

from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_sync_receipt_clock_anchor import anchors, units, RECEIVED, FUTURE
from tests.unit.test_sync_cross_job_assignment import intake as assign, conversations, load_dependencies
from utils.batch_pipeline import artifact_reupload, projection
from utils.batch_pipeline.contracts import WorkItem, Priority, ProjectionBinding
from utils.batch_pipeline.projection_parts import split_result
from utils.sync import future_capture_request
from utils.sync.receipt_clock import POLICY


def test_disconnected_recovery_parts_retain_both_transcripts_and_replay():
    item = WorkItem(
        'segment',
        'u',
        RECEIVED - 200,
        'gs://synthetic/audio',
        200,
        Priority.DEEP,
        conversation_id='receipt-source',
        capture_time_trust='untrusted',
    )
    binding = ProjectionBinding('u', 'job', 'content', ('segment',))
    payload = {
        'audio_seconds': 200,
        'speech_seconds': 4,
        'speech_spans': [{'start': 0, 'end': 2}, {'start': 180, 'end': 182}],
        'words': [
            {'word': 'First distinct speech region.', 'timestamp': [0, 2]},
            {'word': 'Second distinct speech region.', 'timestamp': [180, 182]},
        ],
        'diarization': {'turns': [{'start': 0, 'end': 200, 'speaker': 'SPEAKER_00'}]},
    }
    parts = split_result(item, payload)
    assert len(parts) == 2
    store = StrictFirestore()
    for part, result in parts:
        assign(store, projection.build_incoming(part, binding, result))
    rows = conversations(store)
    assert len(rows) == 2
    assert {s['text'] for row in rows for s in row['transcript_segments']} == {
        'First distinct speech region.',
        'Second distinct speech region.',
    }
    ids = {row['id'] for row in rows}
    # A changed upload bundle changes segment IDs, never source/part identities.
    retry_parts = split_result(replace(item, segment_id='another-bundle-segment'), payload)
    for part, result in retry_parts:
        assign(store, projection.build_incoming(part, binding, result))
    assert {row['id'] for row in conversations(store)} == ids
    assert sum(len(row['transcript_segments']) for row in conversations(store)) == 2
    # Provider word edges may move while the admitted unit and VAD groups do not.
    changed = {**payload, 'words': [{**payload['words'][0], 'timestamp': [0, 2.1]}, payload['words'][1]]}
    assert [part.conversation_id for part, _ in split_result(item, changed)] == [
        part.conversation_id for part, _ in parts
    ]


@pytest.mark.asyncio
async def test_missing_recovered_audio_repair_decodes_original_receipt_clock(anchors, tmp_path, monkeypatch):
    [original] = units(tmp_path / 'original', [FUTURE], run=None)
    from tests.unit.test_batch_pipeline_audio import pcm
    from pathlib import Path

    path = Path(pcm(tmp_path, int(FUTURE), 16000)).rename(tmp_path / f'audio_omi_pcm16_16000_u0_{int(FUTURE)}.bin')
    item = WorkItem(
        'segment',
        'synthetic',
        original.stored_capture_at,
        'gs://missing/audio',
        original.duration_seconds,
        Priority.DEEP,
        conversation_id=original.recovery_id,
        capture_time_trust='untrusted',
    )
    binding = ProjectionBinding('synthetic', 'job', 'content', ('segment',))
    snapshots = {'segment': {'generation': 1}}
    monkeypatch.setattr(artifact_reupload, '_repair_plan', lambda *a: (object(), (binding, [asdict(item)], snapshots)))
    monkeypatch.setattr(
        artifact_reupload,
        '_repair_evidence',
        lambda *a: (
            {'capture_clock_policy': POLICY, 'capture_received_at': RECEIVED},
            {'segment': {'stt_language': 'en'}},
        ),
    )
    staged = []

    def stage(work, wav):
        staged.append(work)
        return 'gs://restored/audio'

    monkeypatch.setattr(artifact_reupload, '_commit_restore', lambda *a: 'job')

    @future_capture_request.observe_upload
    async def repair_request():
        future_capture_request.classify_upload([path.name], RECEIVED)
        result = await artifact_reupload.restore_upload(
            object(),
            'synthetic',
            'content',
            [str(path)],
            source='omi',
            should_lock=False,
            conversation_id=None,
            client_device_id=None,
            client_platform=None,
            intake_context={},
            artifacts=SimpleNamespace(stage_audio=stage),
        )
        future_capture_request.mark(future_capture_request.Outcome.PRIOR_CUSTODY)
        return result

    reached = future_capture_request._OUTCOMES.labels(outcome='reached_offsets')
    before = reached._value.get()
    result = await repair_request()
    assert reached._value.get() == before + 1
    assert result == 'job' and len(staged) == 1
    assert staged[0].capture_at == original.stored_capture_at
    assert staged[0].conversation_id == original.recovery_id


def test_recovery_provenance_survives_skew_window_in_changed_bundle(anchors, tmp_path):
    stamp = RECEIVED + 86400 + 300
    [original] = units(tmp_path / 'original', [stamp], run=None)
    retry = units(tmp_path / 'retry', [stamp, RECEIVED + 90000], run=None, received=RECEIVED + 90010)
    recovered = next(unit for unit in retry if unit.capture_at == stamp)
    assert recovered.recovery_id == original.recovery_id
    assert recovered.stored_capture_at == original.stored_capture_at
    ordinary = next(unit for unit in retry if unit.capture_at == RECEIVED + 90000)
    assert ordinary.recovery_id is None and ordinary.stored_capture_at is None


def test_recovery_defaults_off_until_readers_are_upgraded(monkeypatch):
    from utils.sync.capture_clock import future_capture_clamp_enabled

    monkeypatch.delenv('SYNC_FUTURE_CAPTURE_CLAMP_ENABLED', raising=False)
    assert not future_capture_clamp_enabled()


@pytest.mark.parametrize('ahead', [601, 3600, 86400])
def test_normal_skew_to_day_band_stays_refused(monkeypatch, ahead):
    from datetime import datetime, timezone
    from utils.sync.capture_clock import capture_time_rejection
    from utils.observability.reasons import SyncCaptureTimeReason

    monkeypatch.setenv('SYNC_FUTURE_CAPTURE_CLAMP_ENABLED', 'true')
    now = datetime.fromtimestamp(RECEIVED, timezone.utc)
    stamp = datetime.fromtimestamp(RECEIVED + ahead, timezone.utc)
    assert capture_time_rejection(stamp, now=now) is SyncCaptureTimeReason.REJECTED_FUTURE


def test_repair_boundary_compares_stored_capture_instead_of_raw_filename(anchors, tmp_path):
    [unit] = units(tmp_path / 'source', [FUTURE], run=None)
    job = {'capture_at': unit.stored_capture_at, 'duration_seconds': unit.duration_seconds}
    assert artifact_reupload._original_unit([job], 0, unit) is job


def test_retained_provenance_batchget_does_not_pass_an_inactive_sdk_transaction(monkeypatch):
    from unittest.mock import MagicMock
    from google.cloud.firestore_v1 import _helpers
    from database import sync_capture_clock

    client = MagicMock()
    client.transaction.return_value = SimpleNamespace(in_progress=False)

    def batchget(refs, *, transaction=None):
        # Exercise the SDK's real local request guard without credentials/RPCs.
        assert _helpers.get_transaction_id(transaction) is None
        return []

    client.get_all.side_effect = batchget
    monkeypatch.setattr(sync_capture_clock, 'get_firestore_client', lambda: client)
    assert sync_capture_clock.retained_offsets('synthetic', ['scope']) == {}
    client.transaction.assert_not_called()
