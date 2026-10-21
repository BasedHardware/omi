"""S1 upload identities survive authenticated queue context and projection."""

import json
from unittest.mock import Mock

import pytest

from utils.batch_pipeline.audio import audio_unit, read_context, with_context
from utils.batch_pipeline.context import resolve_context
from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem
from utils.sync import recording_lineage


def upload(count):
    files = [
        {
            'name': 'audio_omi' + str(i) + 'x' * 45 + '_opus_16000_1_fs320_1234567890.bin',
            'capture_root': '11111111-2222-4333-8444-555555555555',
            'clock_epoch': 0,
            'source_frame_start': i * 3000,
            'frame_count': 3000,
            'rate_hz': 16000,
            'codec': 'opus',
            'channel': 'mono',
        }
        for i in range(count)
    ]
    return json.dumps({'version': 1, 'files': files}, separators=(',', ':')), [f['name'] for f in files]


@pytest.mark.parametrize('archives', [[], ['gs://synthetic/' + 'a' * 64 + '.bin']])
@pytest.mark.parametrize('count', [1, 15])
def test_upload_claims_bind_after_queue_roundtrip_without_archive_names(monkeypatch, archives, count):
    monkeypatch.setenv('SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST', '')
    monkeypatch.delenv('SYNC_LINEAGE_RESOLVE_ENABLED', raising=False)
    header, filenames = upload(count)
    claims = recording_lineage.parse_s1_upload_claims(header, filenames)
    assert len(claims) == count
    if count == 15:
        assert len(header.encode()) == 3996
        inflated = json.dumps({'version': 1, 'files': [dict(c, name=n) for n, c in claims.items()]})
        assert len(inflated.encode()) == 4238
    item = WorkItem('segment', 'synthetic-owner', 1000, 'gs://synthetic/unit.wav', 10, Priority.FRESH)
    binding = ProjectionBinding('synthetic-owner', 'job', 'content', ('segment',), source='omi')
    context = {
        'owner_id': item.owner_id,
        'job_id': binding.job_id,
        'content_id': binding.content_id,
        'segment_id': item.segment_id,
        'capture_at': item.capture_at,
        'source': binding.source,
        'should_lock': binding.is_locked,
        'client_device_id': binding.client_device_id,
        'client_platform': binding.client_platform,
        'conversation_id': binding.target_conversation_id,
        'recording_session_id': 'synthetic-recording',
        'audio_start_seconds': 1000,
        'audio_end_seconds': 1010,
        'filenames': filenames,
        'capture_evidence_claims': claims,
        'raw_capture_paths': archives,
    }
    # Intake freezes exactly these fields inside the encrypted staged WAV;
    # projection reads them after the queue has delivered the work item.
    frozen = with_context(audio_unit(1000, b'\0' * 320).wav, context)
    planner = Mock(return_value={'segment': 'live-target'})
    monkeypatch.setattr(recording_lineage, 'plan_segment_targets', planner)
    resolved = resolve_context(item, binding, read_context(frozen), None)
    assert resolved.target_id == 'live-target'
    planner.assert_called_once()


def test_incomplete_upload_set_is_still_refused_at_projection(monkeypatch, caplog):
    monkeypatch.setenv('SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST', '')
    header, filenames = upload(1)
    claims = recording_lineage.parse_s1_upload_claims(header, filenames)
    with caplog.at_level('INFO', logger=recording_lineage.__name__):
        assert not recording_lineage.lineage_resolution_requested(
            'synthetic-owner',
            'synthetic-recording',
            1000,
            1010,
            capture_evidence_claims=claims,
            filenames=filenames + ['missing.bin'],
            stage='batch_projection',
        )
    assert 'reason=count_mismatch stage=batch_projection claim_count_bucket=1 file_count_bucket=2_5' in caplog.text
    assert filenames[0] not in caplog.text and 'missing.bin' not in caplog.text
