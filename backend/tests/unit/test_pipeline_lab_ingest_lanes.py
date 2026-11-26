"""Pipeline lab ingest: record/batch and sync lane drivers over production code, STT from cassettes.

Synthetic noise audio and scripted stub words only; no vendor, network or store.
"""

import json
import wave

import numpy as np
import pytest

from testing.pipeline_lab.cassette.adapters import StubAdapter
from testing.pipeline_lab.cassette.format import Cassette, CassetteKey, Word
from testing.pipeline_lab.cassette.player import PlaybackConfig, Player, SpanSource
from testing.pipeline_lab.cassette.recorder import InMemoryLedger, Recorder
from testing.pipeline_lab.lanes.batch import BatchConversation, replay_record_lane
from testing.pipeline_lab.lanes.day import STTSelection, record_day_cassettes, replay_day
from testing.pipeline_lab.lanes.sync import SyncConversation, replay_sync_lane
from testing.pipeline_lab.timeline.build import build_day_timeline

START = '2026-01-02T10:00:00Z'


@pytest.fixture(autouse=True)
def _private_lab_root(tmp_path, monkeypatch):
    """The sync lane's work files default to the lab root; keep them in this test's directory."""
    monkeypatch.setenv('OMI_PIPELINE_LAB_ROOT', str(tmp_path / 'default-lab-root'))


@pytest.fixture(autouse=True)
def _batch_env(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED', 'false')


def pcm(seconds, seed=0):
    return np.random.default_rng(seed).normal(0, 3000, int(16000 * seconds)).astype('<i2').tobytes()


def two_speakers(start, count, step=0.5):
    return [
        Word(start + i * step, start + i * step + 0.3, f'w{i}', 'SPEAKER_00' if i < count // 2 else 'SPEAKER_01')
        for i in range(count)
    ]


def cassette_for(audio, words):
    key = CassetteKey.for_audio(audio, provider='stub', model='stub-1', language='en', vocabulary=[])
    return Cassette(key, len(audio) / 32000, words)


def test_record_lane_runs_real_worker_and_projection():
    audio = pcm(20)
    result = replay_record_lane(
        BatchConversation('c1', audio, START, '2026-01-02T10:00:20Z', 'en'),
        SpanSource(cassette_for(audio, two_speakers(1.0, 20))),
        vad=lambda samples: [(0.5, 18.0)],
    )
    assert result.outcome == 'transcript' and result.lane == 'record'
    assert [(s['speaker'], s['start'], s['end']) for s in result.segments] == [
        ('SPEAKER_00', 1.0, 5.8),
        ('SPEAKER_01', 6.0, 10.8),
    ]
    assert result.segments[0]['text'].startswith('W0 w1')  # production grouper capitalizes
    assert result.driver['units'][0]['outcome'] == 'success'
    assert 'PipelineWorker.process_batch' in result.driver['production']
    assert result.driver['unlocated_windows'] == 0
    assert result.to_json()['speakers'] == ['SPEAKER_00', 'SPEAKER_01']


def test_record_lane_splits_units_on_production_unit_length(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_UNIT_SECONDS', '10')
    audio = pcm(20)
    words = [Word(2.0, 2.4, 'first', 'SPEAKER_00'), Word(14.0, 14.4, 'second', 'SPEAKER_00')]
    result = replay_record_lane(
        BatchConversation('c2', audio, START, None, 'en'),
        SpanSource(cassette_for(audio, words)),
        vad=lambda samples: [(0.0, len(samples) / 16000)],
    )
    assert [u['start'] for u in result.driver['units']] == [0.0, 10.0]
    assert [(s['text'], s['start']) for s in result.segments] == [('First', 2.0), ('Second', 14.0)]


def test_record_lane_vad_silence_is_silence_not_failure():
    audio = pcm(5)
    result = replay_record_lane(
        BatchConversation('c3', audio, START, None, 'en'),
        SpanSource(cassette_for(audio, two_speakers(1.0, 4))),
        vad=lambda samples: [],
    )
    assert result.outcome == 'silence' and result.segments == [] and result.error is None
    assert result.driver['units'][0]['outcome'] == 'silence'


def segment_script(request):
    duration = request.audio_seconds
    return [Word(0.5, 0.9, 'hello', 'SPEAKER_00'), Word(duration - 1.0, duration - 0.6, 'bye', 'SPEAKER_01')]


SPANS = [{'start': 1.0, 'end': 5.0}, {'start': 20.0, 'end': 25.0}, {'start': 146.0, 'end': 149.0}]


def test_sync_lane_records_exact_segments_then_replays_them(tmp_path):
    root = tmp_path / 'lab'
    audio = pcm(150)
    conversation = SyncConversation('s1', audio, START, None, 'en')
    adapter = StubAdapter(segment_script, provider='stub', model='stub-1')
    recorder = Recorder(adapter, InMemoryLedger(1.0), vendor_log=root / 'runs/r/vendor_log.jsonl', root=root)
    recorded = replay_sync_lane(conversation, recorder=recorder, file_vad=lambda path: SPANS, scratch=tmp_path)
    # Production merge_and_cap joins spans < 120 s apart: two files, so two vendor calls.
    assert [len(c.pcm16) / 32000 for c in adapter.calls] == [24.0, 3.0]
    assert len((root / 'runs/r/vendor_log.jsonl').read_text().splitlines()) == 2

    player = Player(PlaybackConfig('stub', 'stub-1', 'en'), root=root)
    replayed = replay_sync_lane(conversation, player=player, file_vad=lambda path: SPANS, scratch=tmp_path)
    assert replayed.segments == recorded.segments and len(adapter.calls) == 2
    assert replayed.outcome == 'transcript' and replayed.stt['mode'] == 'exact'
    # File offset + first-word offset + segment clock: 1.0+0.5 and 146.0+0.5.
    assert [(s['text'], s['start']) for s in replayed.segments] == [
        ('Hello', 1.5),
        ('Bye', 24.0),
        ('Hello', 146.5),
        ('Bye', 148.0),
    ]
    assert [f['offset'] for f in replayed.driver['files']] == [1.0, 146.0]
    assert not list(tmp_path.glob('plab-sync-*')), 'scratch audio must be removed'


def test_sync_lane_cassette_miss_fails_without_calling_anything(tmp_path):
    player = Player(PlaybackConfig('stub', 'stub-1', 'en'), root=tmp_path / 'lab')
    result = replay_sync_lane(
        SyncConversation('s2', pcm(10), START, None, 'en'), player=player, file_vad=lambda p: [SPANS[0]]
    )
    assert result.outcome == 'failed' and result.error == 'cassette_miss'


def test_sync_lane_span_mode_uses_conversation_cassette(tmp_path):
    audio = pcm(30)
    words = [Word(2.0, 2.4, 'inside', 'SPEAKER_00'), Word(12.0, 12.4, 'dropped', 'SPEAKER_00')]
    result = replay_sync_lane(
        SyncConversation('s3', audio, START, None, 'en'),
        span=SpanSource(cassette_for(audio, words)),
        file_vad=lambda p: [{'start': 1.0, 'end': 5.0}],
    )
    # Words outside every VAD file are not sent in production, so they vanish here too.
    assert [(s['text'], s['start']) for s in result.segments] == [('Inside', 2.0)]


def write_wav(path, audio):
    with wave.open(str(path), 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(audio)


def test_day_record_then_replay_end_to_end(tmp_path):
    root, day_id = tmp_path / 'lab', 'day-1'
    day = root / 'corpus' / day_id
    (day / 'audio').mkdir(parents=True)
    (day / 'baseline').mkdir()
    rows = [
        {
            'id': 'rec',
            'started_at': '2026-01-02T09:59:58Z',
            'finished_at': '2026-01-02T10:00:20Z',
            'record_lane_owner': 'batch_live_v1',
        },
        {
            'id': 'syn',
            'started_at': '2026-01-02T11:00:00Z',
            'finished_at': '2026-01-02T11:00:30Z',
            'sync_live_target': True,
        },
        {'id': 'live', 'started_at': '2026-01-02T12:00:00Z', 'finished_at': '2026-01-02T12:00:10Z'},
    ]
    (day / 'baseline' / 'conversations.jsonl').write_text('\n'.join(json.dumps(r) for r in rows))
    index = [
        {'conversation_id': 'rec', 'path': 'rec.wav', 'start': '2026-01-02T10:00:00Z', 'end': '2026-01-02T10:00:20Z'},
        {'conversation_id': 'syn', 'path': 'syn.wav', 'start': '2026-01-02T11:00:00Z', 'end': '2026-01-02T11:00:30Z'},
        {'conversation_id': 'live', 'path': 'live.wav', 'start': '2026-01-02T12:00:00Z', 'end': '2026-01-02T12:00:10Z'},
    ]
    (day / 'audio' / 'index.json').write_text(json.dumps(index))
    for i, (entry, seconds) in enumerate(zip(index, (20, 30, 10))):
        write_wav(day / 'audio' / entry['path'], pcm(seconds, seed=i))
    build_day_timeline(day_id, root=root)

    def script(request):
        return two_speakers(1.0, 8) if request.audio_seconds >= 20 else segment_script(request)

    file_vad = lambda path: [{'start': 2.0, 'end': 9.0}]  # noqa: E731
    adapter = StubAdapter(script, provider='stub', model='stub-1')
    recorder = Recorder(adapter, InMemoryLedger(1.0), vendor_log=root / 'runs/run-1/vendor_log.jsonl', root=root)
    # Exact per-VAD-file sync cassettes and no streaming recording (the defaults are span and all
    # lanes since RULINGS 13/14); this test exercises the exact path.
    exact = {'sync_exact': True, 'lanes': ('record', 'sync')}
    summary = record_day_cassettes(day_id, recorder, language='en', root=root, file_vad=file_vad, **exact)
    assert summary == {'conversations': 2, 'hits': 0, 'misses': 2}
    again = record_day_cassettes(day_id, recorder, language='en', root=root, file_vad=file_vad, **exact)
    assert again['misses'] == 0 and len(adapter.calls) == 2

    results = replay_day(
        day_id,
        'run-1',
        STTSelection('stub', 'stub-1', 'en'),
        root=root,
        vad=lambda samples: [(0.0, len(samples) / 16000)],
        file_vad=file_vad,
    )
    by_id = {r.id: r for r in results}
    assert by_id['rec'].outcome == 'transcript'
    # Audio starts 2 s after the baseline conversation: segments move onto its clock.
    assert by_id['rec'].segments[0]['start'] == pytest.approx(3.0)
    assert by_id['syn'].outcome == 'transcript' and by_id['syn'].segments[0]['start'] == pytest.approx(2.5)
    assert by_id['live'].outcome == 'failed' and by_id['live'].error == 'lane_not_replayed:streaming'

    out = root / 'runs' / 'run-1' / 'ingest'
    written = json.loads((out / 'rec.json').read_text())
    assert written['schema'] == 'pipeline_lab.ingest/v1' and written['lane'] == 'record'
    assert written['boundaries']['source'] == 'baseline'
    assert {c['id'] for c in json.loads((out / 'index.json').read_text())['conversations']} == {'rec', 'syn', 'live'}

    stand_in = replay_day(
        day_id,
        'run-2',
        STTSelection('stub', 'stub-1', 'en'),
        root=root,
        streaming_via='record',
        only=['live'],
        vad=lambda samples: [(0.0, len(samples) / 16000)],
        write=False,
    )
    assert stand_in[0].error == 'cassette_miss'  # replay never records
    assert len(adapter.calls) == 2
