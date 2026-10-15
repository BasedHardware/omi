from copy import deepcopy
from types import SimpleNamespace

import pytest

from tests.unit.test_sync_live_dedupe_replay_tool import AUDIO_ROOT, decisions, run_replay
from utils.capture_evidence import SourcePositionMap


def _committed_payload(covered=7):
    source = SourcePositionMap(committed=True)
    for index in range(10):
        source.accept(
            {'capture_root': AUDIO_ROOT, 'clock_epoch': 0, 'source_frame': index},
            sample_start=index * 8000,
            sample_count=8000,
            rate_hz=16000,
            payload=b'\x01\x00' * 8000,
            receipt_wall_time=1000.0 + (index + 1) * 0.5,
        )
    source.remember_transcripts([{'id': 'fresh', '_capture_word_ranges': ((0, covered * 8000),)}])
    proof = source.committed_snapshot(
        'owner', [SimpleNamespace(id='fresh', text='synthetic committed speech', start=0.0, end=covered * 0.5)]
    )
    assert proof is not None and proof['proof'] == 'committed_transcript_v1'
    return {
        'live_segments': [],
        'sync_segments': [
            {
                'start': 1000.0 + index * 0.5,
                'end': 1000.0 + (index + 1) * 0.5,
                'text': f'synthetic frame {index}',
                'wal_index': 0,
                'source_frame_start': index,
                'source_frame_end': index + 1,
            }
            for index in range(10)
        ],
        'audio_coverage': {
            'live_received_ranges': [proof],
            'wal_frames': [
                {
                    'capture_root': AUDIO_ROOT,
                    'clock_epoch': 0,
                    'source_frame_start': 0,
                    'rate_hz': 16000,
                    'channel': 'mono',
                    'codec': 'pcm16',
                    'frame_count': 10,
                    'frame_samples': [8000] * 10,
                    'wal_start_seconds': 1000.0,
                }
            ],
        },
    }


def test_committed_replay_suppresses_only_saved_frames_and_keeps_new_speech(tmp_path):
    result = run_replay(tmp_path, _committed_payload())
    assert result.returncode == 0, result.stderr
    output = decisions(result)
    assert output['audio_coverage']['files'][0]['kept_frame_ranges'] == [[7, 10]]
    assert output['audio_coverage']['totals'] == {'kept_seconds': 1.5, 'dropped_seconds': 3.5, 'context_seconds': 0.0}
    assert [row['decision'] for row in output['segments']] == ['dropped'] * 7 + ['kept'] * 3
    assert [row['segment_count'] for row in output['intakes']] == [2, 3, 5]


def test_committed_replay_full_coverage_drops_audio_candidates(tmp_path):
    result = run_replay(tmp_path, _committed_payload(10))
    assert result.returncode == 0, result.stderr
    output = decisions(result)
    assert output['audio_coverage']['files'][0]['kept_frame_ranges'] == []
    assert output['audio_coverage']['totals'] == {'kept_seconds': 0.0, 'dropped_seconds': 5.0, 'context_seconds': 0.0}
    assert [row['decision'] for row in output['segments']] == ['dropped'] * 10


@pytest.mark.parametrize('wall_start', [None, 87400.0])
def test_committed_replay_missing_or_cross_lifetime_context_keeps_speech(tmp_path, wall_start):
    payload = _committed_payload(10)
    payload['audio_coverage']['wal_frames'][0]['wal_start_seconds'] = wall_start
    result = run_replay(tmp_path, payload)
    assert result.returncode == 0, result.stderr
    output = decisions(result)
    assert output['audio_coverage']['files'][0]['kept_frame_ranges'] == [[0, 10]]
    assert output['audio_coverage']['totals'] == {'kept_seconds': 5.0, 'dropped_seconds': 0.0, 'context_seconds': 0.0}
    assert [row['decision'] for row in output['segments']] == ['kept'] * 10


def test_committed_replay_one_cross_lifetime_wal_abstains_whole_batch(tmp_path):
    payload = _committed_payload(10)
    stale = deepcopy(payload['audio_coverage']['wal_frames'][0])
    stale['wal_start_seconds'] = 87400.0
    payload['audio_coverage']['wal_frames'].append(stale)
    result = run_replay(tmp_path, payload)
    assert result.returncode == 0, result.stderr
    output = decisions(result)
    assert [row['kept_frame_ranges'] for row in output['audio_coverage']['files']] == [[[0, 10]], [[0, 10]]]
    assert [row['decision'] for row in output['audio_coverage']['files']] == ['abstained', 'abstained']
    assert output['audio_coverage']['totals'] == {'kept_seconds': 10.0, 'dropped_seconds': 0.0, 'context_seconds': 0.0}


@pytest.mark.parametrize('wall_start', [True, float('nan'), float('inf'), -1.0, 0.0, '1000'])
def test_committed_replay_invalid_wall_anchor_rejects_without_content_leak(tmp_path, wall_start):
    payload = _committed_payload(10)
    payload['audio_coverage']['wal_frames'][0]['wal_start_seconds'] = wall_start
    result = run_replay(tmp_path, payload)
    assert result.returncode == 2
    for forbidden in ('synthetic frame', AUDIO_ROOT, 'input.json'):
        assert forbidden not in result.stdout and forbidden not in result.stderr
