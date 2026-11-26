"""Stand-in lines are worded from the run's own counters (``scenario/standins.py``), and the measured
scenario reach (``scenario/reach.py``) is built from ``called_files.json``. Pure; no stack."""

import json

from testing.pipeline_lab.scenario import reach, standins
from testing.pipeline_lab.scenario.verdict import scenario_verdict

AUDIO_ROW = {
    'label': 'B',
    'lane': 'batch',
    'audio_file': 'synthetic_two_voices.wav',
    'source': 'synthetic',
    'provider': 'synthetic',
    'model': 'macos-say-script-v1',
    'product': ['decode_pcm16_wav', 'PipelineWorker.process_batch', 'projection_segments'],
    'simulated': [
        'unit_cut',
        'dispatch_admission(allow)',
        'vad(local silero, prod: gpu pyannote)',
        'asr(cassette)',
        'diarization(cassette)',
        'speaker_identification(not run: no voiceprints; projection marks every segment is_user=false)',
    ],
}


def _notes(result):
    return {row['name']: row['text'] for row in standins.stand_in_notes(result)}


def test_scripted_run_says_scripted_lines():
    result = {
        'stand_ins': {'record_admission': 1, 'batch_projection': 1},
        'stand_in_sources': {'record_admission': {'scripted': 1}, 'batch_projection': {'scripted': 1}},
    }
    notes = _notes(result)
    assert "STT returned the scenario's scripted lines" in notes['record_admission']
    assert "Its segments were the scenario's scripted lines" in notes['batch_projection']
    assert 'cassette' not in notes['record_admission'] + notes['batch_projection']
    assert standins.audio_steps(result) == []


def test_audio_run_says_cassette_words_through_the_real_batch_lane():
    result = {
        'stand_ins': {'record_admission': 1, 'batch_projection': 1, 'capture_close': 1},
        'stand_in_sources': {'record_admission': {'synthetic': 1}, 'batch_projection': {'synthetic': 1}},
        'audio': {'recordings': [AUDIO_ROW]},
    }
    notes = _notes(result)
    for name in ('record_admission', 'batch_projection'):
        assert 'scripted' not in notes[name]
        assert 'synthetic STT cassette' in notes[name] and 'PipelineWorker and projection_segments' in notes[name]
    assert 'projection transaction' in notes['batch_projection']  # the landing still is a stand-in
    (step,) = standins.audio_steps(result)
    assert step['product'] == [
        'decode (decode_pcm16_wav)',
        'windows and packing (PipelineWorker.process_batch)',
        'segments (projection_segments)',
    ]
    for stand_in in ('local Silero VAD', 'cassette words', 'cassette speaker labels', 'no speaker identification'):
        assert any(s.startswith(stand_in) for s in step['stand_ins']), stand_in
    assert 'synthetic/macos-say-script-v1' in step['text']


def test_mixed_sources_and_old_runs_without_source_counts():
    mixed = {
        'stand_ins': {'batch_projection': 2},
        'stand_in_sources': {'batch_projection': {'scripted': 1, 'local': 1}},
    }
    text = _notes(mixed)['batch_projection']
    assert 'scripted lines' in text and 'local STT cassette' in text
    old_audio = {'stand_ins': {'batch_projection': 1}, 'audio': {'recordings': [AUDIO_ROW]}}
    assert 'predates per-source counts' in _notes(old_audio)['batch_projection']
    old_scripted = {'stand_ins': {'batch_projection': 1}}
    assert 'scripted lines' in _notes(old_scripted)['batch_projection']


def test_verdict_rows_carry_the_worded_stand_ins():
    result = {
        'outcome': 'passed',
        'stand_ins': {'record_admission': 1},
        'stand_in_sources': {'record_admission': {'synthetic': 1}},
        'audio': {'recordings': [AUDIO_ROW]},
    }
    row = scenario_verdict('x', result)
    assert row['stand_ins'] == ['record_admission']
    assert any('synthetic STT cassette' in line for line in row['stand_in_notes'])
    assert len(row['audio_steps']) == 1 and row['audio_steps'][0].startswith('Audio B (batch lane')
    assert any(line.startswith('audio to words: ') for line in standins.lines(result))


def test_build_reach_unions_repeats_and_splits_common(tmp_path):
    for name, files in (('a', ['backend/x.py', 'backend/y.py']), ('b', ['backend/x.py'])):
        (tmp_path / name).mkdir()
        (tmp_path / name / reach.CALLED_FILE).write_text(json.dumps(files))
    (tmp_path / 'b' / 'repeat-2').mkdir()
    (tmp_path / 'b' / 'repeat-2' / reach.CALLED_FILE).write_text(json.dumps(['backend/z.py']))
    (tmp_path / 'run.json').write_text(json.dumps({'sha': 'abc', 'dirty': False}))
    value = reach.build_reach(tmp_path)
    assert value['common'] == ['backend/x.py'] and value['ref'] == 'abc'
    assert value['scenarios'] == {'a': ['backend/y.py'], 'b': ['backend/z.py']}
    loaded = reach.load_reach(lambda rel: json.dumps(value), 'reach.json')
    assert loaded == {'a': {'backend/x.py', 'backend/y.py'}, 'b': {'backend/x.py', 'backend/z.py'}}


def test_call_trace_records_functions_not_module_bodies(tmp_path):
    backend = tmp_path / 'backend'
    (backend / 'pkg').mkdir(parents=True)
    called, imported = backend / 'pkg' / 'called.py', backend / 'pkg' / 'imported.py'
    called.write_text('def f():\n    return 1\n')
    imported.write_text('X = 1\n')
    namespace: dict = {}
    trace = reach.CallTrace(backend).start()
    try:
        for path in (called, imported):  # module bodies run: not recorded
            exec(compile(path.read_text(), str(path), 'exec'), namespace)
        namespace['f']()
    finally:
        files = trace.stop()
    assert files == ['backend/pkg/called.py']


def test_markdown_summary_lists_outcomes_and_failed_labels_only(tmp_path):
    from testing.pipeline_lab.scenario.verdict import markdown_summary, write_json

    rows = [
        {
            'name': 'a',
            'outcome': 'passed',
            'seconds': 3,
            'checks': [{'label': 'x', 'passed': True}],
            'transcripts': {'B': 'synthetic'},
        },
        {
            'name': 'b',
            'outcome': 'failed',
            'seconds': 4,
            'checks': [{'label': 'y', 'passed': False}],
            'differences': ['result.json $.t'],
        },
    ]
    write_json(tmp_path / 'verdict.json', {'outcome': 'failed', 'scenarios': rows})
    write_json(
        tmp_path / 'run.json', {'sha': 'abcdef1234567890', 'repeat': 2, 'jobs': 4, 'stt': 'replay', 'seconds': 9}
    )
    text = markdown_summary(tmp_path)
    assert text.startswith('**Pipeline lab scenarios: failed** (2 scenario(s) x2, jobs 4, stt replay')
    assert '| a | passed | 1/1 | 3 | synthetic |' in text and '- b: failed checks: y' in text
    assert 'differs between repeats at: result.json $.t' in text and f'testing.pipeline_lab view {tmp_path}' in text


def test_local_stack_uses_a_given_redis_and_starts_only_the_emulator(tmp_path, monkeypatch):
    from testing.pipeline_lab.scenario import stack

    seen = {}

    def start(work, redis=None):
        seen['redis'] = redis
        return [], 9001, 6379

    monkeypatch.setattr(stack, '_start_peers', start)
    monkeypatch.setattr(stack, 'stack_status', lambda: {'running': False})
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    monkeypatch.setenv('OMI_PIPELINE_LAB_REDIS', '127.0.0.1:6379')
    with stack.local_stack(tmp_path) as peers:
        assert (peers.firestore, peers.redis, peers.mode) == ('127.0.0.1:9001', '127.0.0.1:6379', 'started-firestore')
    assert seen['redis'] == '127.0.0.1:6379'


def test_firebase_is_found_off_path_in_the_repo_pin_or_the_user_npm_prefix(tmp_path, monkeypatch):
    from testing.pipeline_lab.scenario import stack

    tool = tmp_path / 'firebase'
    tool.write_text('#!/bin/sh\n')
    tool.chmod(0o755)
    monkeypatch.setattr(stack.shutil, 'which', lambda name: None)
    monkeypatch.setattr(stack, 'FIREBASE_FALLBACKS', (tmp_path / 'absent', tool))
    assert stack.firebase_binary() == str(tool)
    monkeypatch.setattr(stack, 'FIREBASE_FALLBACKS', (tmp_path / 'absent',))
    assert stack.firebase_binary() is None
