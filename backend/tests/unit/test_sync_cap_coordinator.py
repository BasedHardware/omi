"""Exercise real v2 coordination: coverage precedes custody and late holds do not bill."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from database import sync_cap_holds
from utils.sync import cap_hold
from tests.unit.test_wal_audio_coverage_pipeline import (
    coordinator,
    _wire,
    _coverage_env,
    _committed_envelope,
    _claim,
    _read_payload,
    _write_labeled_wav,
    _frame_bytes,
    FRAME_SAMPLES,
    BIN_NAME,
    ORIGIN,
    generation,
)


async def _run(module, tmp_path):
    await module._run_full_pipeline_background_async(
        'job-coverage',
        'uid',
        [f'/tmp/{BIN_NAME}'],
        'omi',
        False,
        str(tmp_path / 'job'),
        client_device_id='pendant',
        recording_session_id=ORIGIN,
        task_mode=True,
        content_id='content',
        capture_evidence_claims={BIN_NAME: _claim()},
    )


def _ledger(pipeline, monkeypatch):
    pipeline.get_sync_content_partial_result = Mock(return_value={})
    pipeline.get_processed_sync_segment_ids = Mock(return_value=set())
    pipeline.compute_sync_segment_id = lambda uid, path: Path(path).name
    pipeline.checkpoint_sync_content_partial_result = Mock(return_value=True)
    pipeline.mark_sync_content_completed = Mock(return_value=True)
    writer = Mock(return_value=True)
    monkeypatch.setattr(sync_cap_holds, 'mark_content_held', writer)
    return writer


async def test_full_hold_contains_only_wal_audio_not_already_committed(coordinator, monkeypatch, tmp_path):
    module, stubs = coordinator
    pipeline = stubs['pipeline']
    _coverage_env(monkeypatch)
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    state = _wire(
        pipeline,
        monkeypatch,
        tmp_path,
        lineage_rows=[generation(1, capture_evidence=_committed_envelope(range(7)))],
    )
    writer = _ledger(pipeline, monkeypatch)
    monkeypatch.setattr(
        cap_hold, 'funded_allowance', lambda uid: SimpleNamespace(managed=False, reason='plan_allowance_exhausted')
    )
    retained = []

    async def retain(uid, path, metadata, reason, receipt):
        retained.append((_read_payload(path), metadata))
        receipt.update(id='held-source', seconds=1.5)

    monkeypatch.setattr(cap_hold, '_hold_capture', retain)
    await _run(module, tmp_path)
    assert len(retained) == 1
    assert retained[0][0] == b''.join(_frame_bytes(v, FRAME_SAMPLES) for v in (7, 8, 9))
    assert retained[0][1]['source_frame_map']['claim']['source_frame_start'] == 7
    assert retained[0][1]['recording_session_id'] == ORIGIN
    assert state.vad_seen == state.processed == []
    pipeline.record_usage.assert_not_called()
    pipeline.mark_sync_content_completed.assert_not_called()
    assert writer.call_args.args[3]['held_audio'] is True
    assert writer.call_args.kwargs['hold_ids'] == ['held-source']


async def test_late_hold_reports_custody_and_charges_only_dispatched_speech(coordinator, monkeypatch, tmp_path):
    module, stubs = coordinator
    pipeline = stubs['pipeline']
    _coverage_env(monkeypatch)
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    _wire(pipeline, monkeypatch, tmp_path, lineage_rows=[])
    writer = _ledger(pipeline, monkeypatch)
    monkeypatch.setattr(cap_hold, 'funded_allowance', lambda uid: SimpleNamespace(managed=True, reason='available'))
    paths = [tmp_path / '1760000000.wav', tmp_path / '1760000002.5.wav']
    for path in paths:
        _write_labeled_wav(path, range(5))
    pipeline.retrieve_vad_segments = lambda path, segments, errors, **kw: segments.update(map(str, paths))

    def process(path, uid, response, lock, errors, *args, **kwargs):
        if path == str(paths[0]):
            response['updated_memories'].add('accepted')
            return True
        response['_cap_holds'] = {'late': {'id': 'late', 'seconds': 2.5}}
        kwargs['deferred_outcome']['cap_held'] = True
        return False

    pipeline.process_segment = process
    await _run(module, tmp_path)
    pipeline.mark_sync_content_completed.assert_not_called()
    result = writer.call_args.args[3]
    assert result['held_audio'] is True
    assert result['failed_segments'] == 0
    assert result['updated_memories'] == ['accepted']
    assert writer.call_args.kwargs['hold_ids'] == ['late']
    assert pipeline.record_usage.call_args.kwargs['transcription_seconds'] == 2
    assert pipeline.record_usage.call_args.kwargs['speech_seconds'] == 2
