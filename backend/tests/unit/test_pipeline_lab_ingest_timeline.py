"""Pipeline lab ingest: day timeline from a synthetic corpus day."""

import json
import wave

import numpy as np
import pytest

from testing.pipeline_lab.timeline.build import (
    AudioEntry,
    build_day_timeline,
    build_gaps,
    build_islands,
    classify_lane,
)
from testing.pipeline_lab.contracts import parse_time

DAY = 'day-synthetic'


def t(clock):
    return f'2026-01-02T{clock}Z'


def write_wav(path, seconds):
    samples = np.random.default_rng(0).normal(0, 1000, int(16000 * seconds)).astype('<i2')
    with wave.open(str(path), 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(samples.tobytes())


@pytest.fixture
def corpus(tmp_path):
    root = tmp_path / 'lab'
    day = root / 'corpus' / DAY
    (day / 'audio').mkdir(parents=True)
    (day / 'baseline').mkdir()
    (day / 'day.json').write_text(json.dumps({'day_id': DAY, 'date': '2026-01-02', 'timezone': 'UTC', 'keep': 1}))
    baseline = [
        # record lane, inside a long island: audio covers 120 s on both sides
        {
            'id': 'c-rec',
            'started_at': t('10:05:00'),
            'finished_at': t('10:10:00'),
            'record_lane_owner': 'batch_live_v1',
        },
        # sync lane, clip only covers itself
        {'id': 'c-sync', 'started_at': t('12:00:00'), 'finished_at': t('12:00:30'), 'sync_merged_from': ['x']},
        # no marker -> streaming by default; no audio
        {'id': 'c-live', 'started_at': t('15:00:00'), 'finished_at': t('15:01:00'), 'discarded': True},
    ]
    (day / 'baseline' / 'conversations.jsonl').write_text('\n'.join(json.dumps(r) for r in baseline) + '\n')
    index = [
        {'conversation_id': 'c-pre', 'path': 'c-pre.wav', 'start': t('10:00:00'), 'end': t('10:05:00.5')},
        {'conversation_id': 'c-rec', 'path': 'c-rec.wav', 'start': t('10:05:00'), 'end': t('10:10:00')},
        {'conversation_id': 'c-post', 'path': 'c-post.wav', 'start': t('10:10:00'), 'end': t('10:15:00')},
        {'conversation_id': 'c-sync', 'path': 'c-sync.wav', 'start': t('12:00:00'), 'end': t('12:00:30')},
    ]
    (day / 'audio' / 'index.json').write_text(json.dumps(index))
    for entry in index:
        write_wav(day / 'audio' / entry['path'], 1)
    return root


def test_lane_rules():
    assert classify_lane({'record_lane_owner': 'batch_live_v1'})['lane'] == 'record'
    assert classify_lane({'server_batch_audio_start': 1})['lane'] == 'record'
    assert classify_lane({'sync_live_target': True})['lane'] == 'sync'
    assert classify_lane({'source': 'sdcard'})['lane'] == 'sync'
    default = classify_lane({'source': 'omi'})
    assert default == {'lane': 'streaming', 'evidence': 'no record/sync marker', 'confidence': 'default'}


def test_islands_join_touching_clips_and_gaps_are_unknown():
    entries = [
        AudioEntry('a', 'a', parse_time(t('01:00:00')), parse_time(t('01:01:00'))),
        AudioEntry('b', 'b', parse_time(t('01:01:00.8')), parse_time(t('01:02:00'))),
        AudioEntry('c', 'c', parse_time(t('02:00:00')), parse_time(t('02:00:10'))),
    ]
    islands = build_islands(entries)
    assert [(i['start'], i['end'], i['conversation_ids']) for i in islands] == [
        (t('01:00:00'), t('01:02:00'), ['a', 'b']),
        (t('02:00:00'), t('02:00:10'), ['c']),
    ]
    gaps = build_gaps(islands, parse_time(t('00:00:00')), parse_time(t('03:00:00')))
    assert [(g['start'], g['end']) for g in gaps] == [
        (t('00:00:00'), t('01:00:00')),
        (t('01:02:00'), t('02:00:00')),
        (t('02:00:10'), t('03:00:00')),
    ]
    assert {g['kind'] for g in gaps} == {'unknown'}


def test_build_day_timeline_writes_coverage_and_evaluability(corpus):
    timeline = build_day_timeline(DAY, root=corpus, vad=lambda entry: [{'start': 0.0, 'end': 0.5}])
    by_id = {c['id']: c for c in timeline['conversations']}
    assert by_id['c-rec']['lane'] == 'record' and by_id['c-rec']['evaluable'] == {
        'boundaries': True,
        'reason': 'audio_covers_margin',
    }
    assert by_id['c-sync']['lane'] == 'sync' and by_id['c-sync']['evaluable']['reason'] == 'gap_before'
    assert by_id['c-live']['lane'] == 'streaming' and by_id['c-live']['evaluable']['reason'] == 'no_audio'
    assert timeline['orphan_audio_conversation_ids'] == ['c-post', 'c-pre']
    assert timeline['window'] == {'start': t('00:00:00'), 'end': '2026-01-03T00:00:00Z'}
    assert timeline['vad'][0]['speech'] == [{'start': t('10:00:00'), 'end': t('10:00:00.500000')}]

    day = json.loads((corpus / 'corpus' / DAY / 'day.json').read_text())
    assert day['keep'] == 1
    coverage = day['coverage']
    assert coverage['conversations'] == 3 and coverage['with_audio'] == 2
    assert coverage['lanes'] == {'record': 1, 'sync': 1, 'streaming': 1}
    assert coverage['audio_seconds'] == pytest.approx(15 * 60 + 0.5 + 30)
    assert [g['start'] for g in coverage['gaps']] == [t('00:00:00'), t('10:15:00'), t('12:00:30')]
    assert (corpus / 'corpus' / DAY / 'timeline.json').exists()


def test_local_silero_vad_map_runs_on_clip(corpus):
    timeline = build_day_timeline(DAY, root=corpus, vad=True, write=False)
    assert len(timeline['vad']) == 4
    assert all(isinstance(v['speech'], list) for v in timeline['vad'])
