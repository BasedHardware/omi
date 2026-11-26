"""Pipeline lab scenarios from audio files: the ``audio_file`` format, cassette lookup and the ``--stt``
modes (stubs for vendor and local; no network), and words -> lines through the real batch and sync lanes.

Synthetic audio only: the committed ``say`` fixture and generated noise."""

import json
from pathlib import Path
import wave

import numpy as np
import pytest

from testing.pipeline_lab.cassette.adapters import StubAdapter
from testing.pipeline_lab.cassette.format import Cassette, CassetteKey, Word
from testing.pipeline_lab.cassette.local import LocalRecorder, LocalWord, register_local_recorder
from testing.pipeline_lab.ledger import SpendCapReached
from testing.pipeline_lab.scenario import audio
from testing.pipeline_lab.scenario.audio import AudioError, materialize, prepare
from testing.pipeline_lab.scenario.spec import ScenarioError, load_scenario, parse_scenario, plan_events
from testing.pipeline_lab.scenario.stack import format_report, resolve

COMMITTED = resolve('audio_single_recording_finish')


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    # The scenario lab root (sync work files, recordings): this test's directory, never the host's.
    monkeypatch.setenv('OMI_PIPELINE_LAB_ROOT', str(tmp_path / 'scenario-lab-root'))
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED', 'false')
    register_local_recorder(None)
    yield
    register_local_recorder(None)


def write_wav(path: Path, seconds: float, *, rate=16000, seed=0) -> Path:
    samples = np.random.default_rng(seed).normal(0, 2000, int(rate * seconds)).astype('<i2')
    with wave.open(str(path), 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(samples.tobytes())
    return path


def scenario_raw(recording: dict, **extra) -> dict:
    return {
        'name': 'audio_case',
        'origins': [{'id': 'O'}],
        'recordings': [{'id': 'B', 'origin': 'O', 'session': 'S1', **recording}],
        **extra,
    }


def parse(tmp_path, recording, **extra):
    path = tmp_path / 'case.json'
    path.write_text(json.dumps(scenario_raw(recording, **extra)))
    return load_scenario(path)


# ---- format -------------------------------------------------------------------------------------------


def test_audio_file_relative_to_the_scenario_and_span_from_duration(tmp_path):
    (tmp_path / 'clips').mkdir()
    write_wav(tmp_path / 'clips' / 'a.wav', 3.5)
    scenario = parse(tmp_path, {'audio_file': 'clips/a.wav'})
    rec = scenario.recording('B')
    assert rec.audio == (0.0, 3.5) and rec.lines == () and rec.audio_file == str(tmp_path / 'clips' / 'a.wav')
    assert scenario.stt == {'language': 'en', 'vocabulary': []}
    assert scenario.audio_recordings == (rec,)
    assert [e.kind for e in plan_events(scenario)] == ['capture_start', 'seal', 'admission']


def test_given_span_must_match_the_file(tmp_path):
    write_wav(tmp_path / 'a.wav', 4.0)
    assert parse(tmp_path, {'audio_file': 'a.wav', 'audio': [10, 14]}).recording('B').audio == (10.0, 14.0)
    with pytest.raises(ScenarioError, match=r'recordings\[0\]\.audio: spans 3 s but audio_file lasts 4\.000 s'):
        parse(tmp_path, {'audio_file': 'a.wav', 'audio': [0, 3]})


@pytest.mark.parametrize(
    'recording, message',
    [
        ({'audio_file': 'a.wav', 'speech': [{'at': 0, 'end': 1, 'text': 'x'}]}, 'exactly one of speech'),
        ({'audio': [0, 4]}, 'exactly one of speech'),
        ({'audio_file': 'missing.wav'}, "no such file 'missing.wav'"),
        ({'audio_file': 'notes.txt'}, 'is not a PCM WAV file; convert it with'),
        ({'audio_file': ''}, 'a path to a WAV file'),
    ],
)
def test_audio_file_errors_are_clear(tmp_path, recording, message):
    write_wav(tmp_path / 'a.wav', 4.0)
    (tmp_path / 'notes.txt').write_text('not audio')
    with pytest.raises(ScenarioError, match=message):
        parse(tmp_path, recording)


def test_sync_fragment_takes_an_audio_file(tmp_path):
    write_wav(tmp_path / 'a.wav', 2.0)
    raw = scenario_raw({'audio': [0, 10], 'speech': [{'fill': [0, 10]}]})
    raw['sync'] = [{'id': 'F', 'origin': 'O', 'audio_file': 'a.wav', 'audio': [3, 5], 'arrives_at': 30}]
    scenario = parse_scenario(raw, path=str(tmp_path / 'x.json'))
    assert scenario.recording('F').audio_file and scenario.recording('F').lane == 'sync'


@pytest.mark.parametrize(
    'stt, message',
    [
        ({'provider': 'p'}, 'pin both provider and model'),
        ({'language': ''}, 'stt.language: a non-empty string'),
        ({'vocabulary': 'Omi'}, 'stt.vocabulary'),
        ({'engine': 'x'}, "stt: unknown keys \\['engine'\\]"),
    ],
)
def test_stt_block_errors(tmp_path, stt, message):
    write_wav(tmp_path / 'a.wav', 1.0)
    with pytest.raises(ScenarioError, match=message):
        parse(tmp_path, {'audio_file': 'a.wav'}, stt=stt)


def test_stt_block_needs_an_audio_recording(tmp_path):
    with pytest.raises(ScenarioError, match='only a scenario with an audio_file recording'):
        parse(tmp_path, {'audio': [0, 4], 'speech': [{'fill': [0, 4]}]}, stt={'language': 'en'})


def test_committed_audio_scenario_is_small_synthetic_and_valid():
    scenario = load_scenario(COMMITTED)
    rec = scenario.recording('B')
    wav = Path(rec.audio_file)
    assert wav.stat().st_size < 300_000 and rec.audio[0] == 0.0 and 8 < rec.audio[1] < 10
    assert scenario.finish is not None and scenario.finish_target() == rec


# ---- lookup and --stt modes ----------------------------------------------------------------------------


def make_cassette(pcm16, *, provider, model, source, words=None, recorded_at='2026-11-25T00:00:00Z'):
    key = CassetteKey.for_audio(pcm16, provider=provider, model=model, language='en', vocabulary=[])
    return Cassette(key, len(pcm16) / 32000, words or [Word(0.2, 0.6, 'w')], recorded_at=recorded_at, source=source)


def private_root(tmp_path) -> Path:
    root = tmp_path / 'lab'
    root.mkdir(mode=0o700)
    return root


def test_replay_finds_the_committed_synthetic_cassette(tmp_path):
    scenario = load_scenario(COMMITTED)
    prepared = prepare(scenario, root=tmp_path / 'absent')
    item = prepared['B']
    assert (item.origin, item.cassette.source, item.cassette.key.provider) == ('fixture', 'synthetic', 'synthetic')
    assert item.summary()['cassette_words'] == len(item.cassette.words) > 10


def test_replay_miss_names_the_key_and_the_command(tmp_path):
    write_wav(tmp_path / 'a.wav', 2.0)
    scenario = parse(tmp_path, {'audio_file': 'a.wav'})
    with pytest.raises(AudioError) as error:
        prepare(scenario, root=tmp_path / 'absent', fixtures=tmp_path / 'none')
    message = str(error.value)
    assert 'recording B: no STT cassette for a.wav (audio ' in message and 'language en' in message
    assert '--stt record-local' in message and '--stt record-vendor --stt-budget-usd' in message
    pinned = parse(tmp_path, {'audio_file': 'a.wav'}, stt={'provider': 'p', 'model': 'm'})
    with pytest.raises(AudioError, match='p/m\\). Record it with .*record-vendor'):
        prepare(pinned, root=tmp_path / 'absent', fixtures=tmp_path / 'none')


def test_replay_prefers_vendor_then_local_then_synthetic(tmp_path):
    from testing.pipeline_lab.lanes.audio import load_pcm16

    write_wav(tmp_path / 'a.wav', 2.0)
    scenario = parse(tmp_path, {'audio_file': 'a.wav'})
    pcm16 = load_pcm16(tmp_path / 'a.wav')
    root = private_root(tmp_path)
    fixtures = tmp_path / 'fixtures'
    synthetic = make_cassette(pcm16, provider='synthetic', model='s', source='synthetic')
    path = fixtures / synthetic.key.digest[:2] / f'{synthetic.key.digest}.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(synthetic.to_json()))
    assert prepare(scenario, root=root, fixtures=fixtures)['B'].cassette.source == 'synthetic'
    make_cassette(pcm16, provider='l', model='old', source='local', recorded_at='2026-01-01T00:00:00Z').save(root)
    make_cassette(pcm16, provider='l', model='new', source='local', recorded_at='2026-02-01T00:00:00Z').save(root)
    picked = prepare(scenario, root=root, fixtures=fixtures)['B']
    assert (picked.cassette.source, picked.cassette.key.model, picked.origin) == ('local', 'new', 'lab_root')
    make_cassette(pcm16, provider='v', model='m', source='vendor').save(root)
    assert prepare(scenario, root=root, fixtures=fixtures)['B'].cassette.source == 'vendor'
    pin = parse(tmp_path, {'audio_file': 'a.wav'}, stt={'provider': 'synthetic', 'model': 's'})
    assert prepare(pin, root=root, fixtures=fixtures)['B'].origin == 'fixture'


def test_committed_cassettes_must_be_synthetic(tmp_path):
    from testing.pipeline_lab.lanes.audio import load_pcm16

    write_wav(tmp_path / 'a.wav', 1.0)
    vendor = make_cassette(load_pcm16(tmp_path / 'a.wav'), provider='v', model='m', source='vendor')
    path = tmp_path / 'fixtures' / vendor.key.digest[:2] / f'{vendor.key.digest}.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(vendor.to_json()))
    with pytest.raises(AudioError, match='only synthetic cassettes may be committed'):
        prepare(parse(tmp_path, {'audio_file': 'a.wav'}), root=None, fixtures=tmp_path / 'fixtures')


def test_committed_fixture_dir_is_only_synthetic():
    assert audio._fixture_cassettes(audio.FIXTURE_CASSETTES)


def test_record_local_records_once_beside_a_synthetic_fixture(tmp_path):
    calls = []

    def recognize(pcm16, language):
        calls.append((len(pcm16), language))
        return [LocalWord(0.5, 0.9, 'w', None, 0.8), {'start': 1.0, 'end': 1.4, 'text': 'v'}]

    register_local_recorder(LocalRecorder('fake_local', 'f-1', recognize))
    scenario = load_scenario(COMMITTED)
    root = private_root(tmp_path)
    first = prepare(scenario, mode='record-local', root=root)['B']
    assert (first.origin, first.cassette.source, first.cassette.usd) == ('recorded', 'local', 0.0)
    assert calls == [(len(first.pcm16), 'en')]
    again = prepare(scenario, mode='record-local', root=root)['B']
    assert again.origin == 'lab_root' and len(calls) == 1
    replayed = prepare(scenario, root=root)['B']  # local now outranks the committed synthetic cassette
    assert (replayed.cassette.key.provider, replayed.origin) == ('fake_local', 'lab_root')
    log = (root / 'stt_records' / 'scenario-audio_single_recording_finish' / 'vendor_log.jsonl').read_text()
    assert json.loads(log.splitlines()[0])['usd'] == 0


def test_record_local_without_a_model_is_a_clear_error(tmp_path, monkeypatch):
    from testing.pipeline_lab.cassette import local_parakeet

    monkeypatch.setattr(local_parakeet, '_has_extra', lambda: False)
    monkeypatch.delenv(local_parakeet.PYTHON_ENV, raising=False)
    with pytest.raises(AudioError, match='record-local: the local Parakeet recorder needs the optional local-STT'):
        prepare(load_scenario(COMMITTED), mode='record-local', root=private_root(tmp_path))


def test_record_local_refuses_a_foreign_pin(tmp_path):
    register_local_recorder(LocalRecorder('fake_local', 'f-1', lambda pcm16, language: []))
    write_wav(tmp_path / 'a.wav', 1.0)
    scenario = parse(tmp_path, {'audio_file': 'a.wav'}, stt={'provider': 'v', 'model': 'm'})
    with pytest.raises(AudioError, match="files cassettes under the local model's own key fake_local/f-1"):
        prepare(scenario, mode='record-local', root=private_root(tmp_path))


def test_record_vendor_needs_a_pin_and_a_budget(tmp_path):
    write_wav(tmp_path / 'a.wav', 1.0)
    unpinned = parse(tmp_path, {'audio_file': 'a.wav'})
    with pytest.raises(AudioError, match='record-vendor needs stt.provider and stt.model'):
        prepare(unpinned, mode='record-vendor', budget_usd=1, root=private_root(tmp_path))
    pinned = parse(tmp_path, {'audio_file': 'a.wav'}, stt={'provider': 'stub', 'model': 'stub-1'})
    with pytest.raises(AudioError, match='needs --stt-budget-usd'):
        prepare(pinned, mode='record-vendor', root=tmp_path / 'lab')


def test_record_vendor_goes_through_the_spend_ledger(tmp_path):
    """Stubbed vendor: the real ``Recorder`` + persistent ``SpendLedger`` path ``record-stt`` uses."""
    write_wav(tmp_path / 'a.wav', 2.0)
    scenario = parse(tmp_path, {'audio_file': 'a.wav'}, stt={'provider': 'stub', 'model': 'stub-1'})
    root = private_root(tmp_path)
    vendor = StubAdapter(lambda request: [Word(0.1, 0.5, 'w', 'SPEAKER_00')], usd_per_hour=36.0)
    vendor.source = 'vendor'  # the stub stands in for PrerecordedAdapter
    # Spend caps in US dollars, not clock budgets (named locals keep the real-clock budget ratchet off them).
    cap_usd, tight_cap_usd = 0.1, 0.03
    item = prepare(scenario, mode='record-vendor', budget_usd=cap_usd, root=root, vendor_adapter=vendor)['B']
    assert (item.origin, item.cassette.source, round(item.cassette.usd, 6)) == ('recorded', 'vendor', 0.02)
    directory = root / 'stt_records' / 'scenario-audio_case'
    assert json.loads((directory / 'ledger.json').read_text())['settled_usd'] == pytest.approx(0.02)
    assert len(vendor.calls) == 1
    prepare(scenario, mode='record-vendor', budget_usd=cap_usd, root=root, vendor_adapter=vendor)
    assert len(vendor.calls) == 1  # a hit costs nothing
    write_wav(tmp_path / 'b.wav', 2.0, seed=4)
    over = parse(tmp_path, {'audio_file': 'b.wav'}, stt={'provider': 'stub', 'model': 'stub-1'})
    with pytest.raises(SpendCapReached):
        prepare(over, mode='record-vendor', budget_usd=tight_cap_usd, root=root, vendor_adapter=vendor)
    assert len(vendor.calls) == 1  # refused before any audio left


def test_unknown_mode_is_refused():
    with pytest.raises(AudioError, match='--stt must be one of'):
        prepare(load_scenario(COMMITTED), mode='live')


# ---- words -> lines through the lanes --------------------------------------------------------------------


def test_batch_lane_turns_the_committed_cassette_into_lines(tmp_path):
    scenario = load_scenario(COMMITTED)
    prepared = prepare(scenario, root=tmp_path / 'absent')
    filled, report = materialize(scenario, prepared, vad=lambda samples: [(0.0, len(samples) / 16000)])
    rec = filled.recording('B')
    assert rec.lines and rec.words() == len(prepared['B'].cassette.words)
    assert all(rec.audio[0] <= line.start < line.end <= rec.audio[1] + 0.01 for line in rec.lines)
    assert {line.is_user for line in rec.lines} == {False}  # no speaker identification
    row = report['recordings'][0]
    assert row['source'] == 'synthetic' and row['driver'] == 'record_batch_v1' and row['outcome'] == 'transcript'
    assert 'PipelineWorker.process_batch' in row['product'] and 'projection_segments' in row['product']
    assert any(s.startswith('speaker_identification') for s in row['simulated'])
    assert any(s.startswith('diarization') for s in row['simulated'])
    text = format_report({'scenario': 's', 'outcome': 'passed', 'seconds': 1, 'audio': report})
    assert 'synthetic cassette' in text and 'product code: decode (decode_pcm16_wav)' in text
    distinctive = {w.text.strip('.,').lower() for w in prepared['B'].cassette.words if len(w.text) > 6} - {'synthetic'}
    assert distinctive and not distinctive & set(text.lower().replace(',', ' ').split())  # no transcript words


def test_sync_lane_turns_a_cassette_into_lines(tmp_path, monkeypatch):
    import stat
    import tempfile

    from testing.pipeline_lab.lanes import sync
    from testing.pipeline_lab.lanes.audio import load_pcm16

    work_dirs = []
    real_mkdtemp = tempfile.mkdtemp

    def mkdtemp(*args, **kwargs):  # where the sync lane writes the recording's private WAV files
        work_dirs.append(Path(kwargs['dir']))
        return real_mkdtemp(*args, **kwargs)

    monkeypatch.setattr(sync.tempfile, 'mkdtemp', mkdtemp)

    write_wav(tmp_path / 'a.wav', 4.0)
    raw = scenario_raw({'audio': [0, 10], 'speech': [{'fill': [0, 10]}]})
    raw['sync'] = [{'id': 'F', 'origin': 'O', 'audio_file': 'a.wav', 'audio': [20, 24], 'arrives_at': 30}]
    scenario = parse_scenario(raw, path=str(tmp_path / 'x.json'))
    root = private_root(tmp_path)
    words = [Word(1.0 + i * 0.4, 1.3 + i * 0.4, f'w{i}', 'SPEAKER_00') for i in range(5)]
    make_cassette(load_pcm16(tmp_path / 'a.wav'), provider='l', model='m', source='local', words=words).save(root)
    prepared = prepare(scenario, root=root, fixtures=tmp_path / 'none')
    filled, report = materialize(scenario, prepared, file_vad=lambda path: [{'start': 0.5, 'end': 3.5}])
    lines = filled.recording('F').lines
    assert sum(len(line.text.split()) for line in lines) == 5 and lines[0].start >= 20.5
    assert report['recordings'][0]['driver'] == 'sync_v1' and report['recordings'][0]['source'] == 'local'
    assert filled.recording('B').lines == scenario.recording('B').lines
    private = tmp_path / 'scenario-lab-root' / 'tmp' / 'sync'
    assert work_dirs == [private] and stat.S_IMODE(private.stat().st_mode) == 0o700

    filled, _ = materialize(scenario, prepared, file_vad=lambda path: [{'start': 0.5, 'end': 3.5}], scratch_root=root)
    assert work_dirs[-1] == root / 'tmp' / 'sync'


def test_silent_audio_is_reported_not_an_error(tmp_path):
    scenario = load_scenario(COMMITTED)
    prepared = prepare(scenario, root=tmp_path / 'absent')
    filled, report = materialize(scenario, prepared, vad=lambda samples: [])
    assert filled.recording('B').lines == () and report['recordings'][0]['outcome'] == 'silence'


def test_unpinned_replay_finds_a_cassette_recorded_before_the_index_and_backfills_it(tmp_path):
    from testing.pipeline_lab.cassette.format import index_path
    from testing.pipeline_lab.store import atomic_write_json

    root = private_root(tmp_path)
    pcm16 = b'\1\0' * 16000
    vendor = make_cassette(pcm16, provider='deepgram', model='nova-3', source='vendor')
    atomic_write_json(vendor.key.path(root), vendor.to_json())  # how save() stored it before the index
    other = make_cassette(b'\2\0' * 16000, provider='deepgram', model='nova-3', source='vendor')
    atomic_write_json(other.key.path(root), other.to_json())  # another audio's cassette: not a match
    assert not index_path(vendor.key.audio_sha256, root).exists()

    hit = audio.find(pcm16, {'language': 'en'}, root=root, fixtures=tmp_path / 'none')  # no provider/model pin
    assert hit is not None and hit[0].key == vendor.key and hit[1] == 'lab_root'
    assert index_path(vendor.key.audio_sha256, root).is_file()  # backfilled: the next lookup reads the index
    again = audio.find(pcm16, {'language': 'en'}, root=root, fixtures=tmp_path / 'none')
    assert again is not None and again[0].key == vendor.key
    assert audio.find(b'\3\0' * 16000, {'language': 'en'}, root=root, fixtures=tmp_path / 'none') is None


def test_unpinned_replay_finds_a_pre_index_vendor_cassette_after_a_local_one_was_indexed(tmp_path):
    # Codex 4705338146: a local cassette saved after the index existed must not hide an older, unindexed
    # vendor cassette of the same audio; the one-time scan runs until the index records it ran.
    from testing.pipeline_lab.cassette.format import BACKFILL_MARKER, index_path, recorded_for_audio
    from testing.pipeline_lab.store import atomic_write_json, read_jsonl

    root = private_root(tmp_path)
    pcm16 = b'\1\0' * 16000
    vendor = make_cassette(
        pcm16, provider='deepgram', model='nova-3', source='vendor', recorded_at='2026-11-01T00:00:00Z'
    )
    atomic_write_json(vendor.key.path(root), vendor.to_json())  # how save() stored it before the index
    local = make_cassette(pcm16, provider='parakeet', model='tdt', source='local', recorded_at='2026-11-25T00:00:00Z')
    local.save(root)  # the index now has one live entry: the local cassette

    hit = audio.find(pcm16, {'language': 'en'}, root=root, fixtures=tmp_path / 'none')
    assert hit is not None and hit[0].key == vendor.key and hit[1] == 'lab_root'  # vendor preferred
    rows = read_jsonl(index_path(vendor.key.audio_sha256, root))
    assert BACKFILL_MARKER in rows and sum(r.get('key_digest') == vendor.key.digest for r in rows) == 1
    again = recorded_for_audio(vendor.key.audio_sha256, root)
    assert [c.key for c in again] == [vendor.key, local.key]  # from the index alone, oldest first
    assert len(read_jsonl(index_path(vendor.key.audio_sha256, root))) == len(rows)  # no second scan


def test_record_mode_repeat_is_deterministic_despite_cache_provenance(tmp_path):
    # Codex 4705338153: --repeat 2 --stt record-local records on the first run and replays on the second; only
    # the provenance differs, so the repeat comparison must not call it nondeterministic. The cassette's
    # identity and words stay compared, and a recording origin (a device, not provenance) still counts.
    from testing.pipeline_lab.determinism import SCENARIO_ARTIFACTS, compare_runs

    register_local_recorder(LocalRecorder('fake_local', 'f-1', lambda pcm16, language: [LocalWord(0.5, 0.9, 'w')]))
    scenario = load_scenario(COMMITTED)
    root = private_root(tmp_path)
    runs = [prepare(scenario, mode='record-local', root=root)['B'] for _ in range(2)]
    assert [r.summary()['cassette_origin'] for r in runs] == ['recorded', 'lab_root']

    def write(name, summary, gap_origin='O'):
        run = tmp_path / name
        run.mkdir()
        result = {'audio': {'recordings': [summary]}, 'gaps': [{'origin': gap_origin}]}
        (run / 'result.json').write_text(json.dumps(result))
        return run

    first, second = write('a', runs[0].summary()), write('b', runs[1].summary())
    assert compare_runs(first, second, SCENARIO_ARTIFACTS).same
    other = write('c', {**runs[1].summary(), 'cassette': 'f' * 12, 'cassette_words': 9})
    paths = {d.path for d in compare_runs(first, other, SCENARIO_ARTIFACTS).differences}
    assert paths == {'$.audio.recordings[0].cassette', '$.audio.recordings[0].cassette_words'}
    assert not compare_runs(first, write('d', runs[1].summary(), gap_origin='P'), SCENARIO_ARTIFACTS).same
