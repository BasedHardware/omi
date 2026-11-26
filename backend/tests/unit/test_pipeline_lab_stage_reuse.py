"""Stage outputs are stored and reused: an unchanged re-run is all cache hits, a changed input re-runs
that stage and everything downstream (and nothing upstream), ``--from-stage`` inside the chain unit
re-runs the unit, and the transcribe lane's artifacts come back from the cache.

Hermetic: synthetic snapshot, the lab's scripted fake LLM upstream behind the real proxy, the
``fake`` chain engine (no Firestore emulator).
"""

import json

import pytest

from testing.pipeline_lab import cli, orchestrator
from testing.pipeline_lab.contracts import STAGES
from testing.pipeline_lab.lanes import plugin as lanes_plugin
from testing.pipeline_lab.llm_proxy.fake_upstream import FakeUpstream
from testing.pipeline_lab.registry import Registry
from testing.pipeline_lab.seed.synthetic import write_synthetic_snapshot
from testing.pipeline_lab.store import Store

DAY = '2026-03-14'
CHAIN = ('discard', 'notes', 'memories', 'tasks', 'notifications', 'goals', 'daily_summary', 'chat_index')
LANES = ('ingest', 'transcribe', 'boundaries', 'speakers')


@pytest.fixture()
def lab(tmp_path, monkeypatch):
    root, verdicts = tmp_path / 'store', tmp_path / 'verdicts'
    monkeypatch.setenv('OMI_PIPELINE_LAB_ROOT', str(root))
    monkeypatch.setenv('OMI_PIPELINE_LAB_VERDICTS', str(verdicts))
    upstream = FakeUpstream().start()
    snap = write_synthetic_snapshot(tmp_path / 'snap', day=DAY)
    code = cli.main(['--json', 'corpus', 'add-day', '--snapshot', str(snap), '--date', DAY, '--timezone', 'UTC'])
    assert code == 0
    yield {'root': root, 'up': upstream, 'tmp': tmp_path}
    upstream.stop()


def run(capsys, lab, *extra):
    argv = ['--json', 'run', '--day', DAY, '--ref', 'HEAD', '--in-place', '--engine', 'fake']
    argv += ['--llm-upstream', lab['up'].url, '--budget-usd', '1', *extra]
    capsys.readouterr()
    code = cli.main(argv)
    lines = capsys.readouterr().out.strip().splitlines()
    body = json.loads(lines[-1])
    assert code == 0, body
    return body


def caches(body):
    return {stage: body['stages'][stage]['report']['cache'] for stage in STAGES}


@pytest.mark.slow  # whole lab pipeline runs; over the fast-unit CPU limit on CI runners
def test_unchanged_rerun_is_all_cache_hits_and_says_so(lab, capsys):
    cold = run(capsys, lab)
    assert caches(cold) == dict.fromkeys(STAGES, 'miss')
    report = cold['stage_report']
    assert report['ran'] == 12 and report['hits'] == 0 and not report['all_cached']
    assert report['llm_calls'] == report['llm_upstream'] > 0
    assert cold['stages']['notes']['report']['llm_calls'] == 3  # one fake notes call per conversation
    assert cold['stages']['daily_summary']['report']['llm_calls'] == 1
    assert cold['stages']['discard']['report']['llm_calls'] == 0
    assert all(cold['stages'][s]['unit'] == 'chain' for s in CHAIN)
    breakdown = cold['stages']['discard']['report']['breakdown']
    assert {'entry_total', 'process_wall', 'process_overhead', 'baseline_view'} <= set(breakdown)

    warm = run(capsys, lab)
    assert caches(warm) == dict.fromkeys(STAGES, 'hit')
    assert all(warm['stages'][s]['status'] == 'cached' for s in STAGES)
    report = warm['stage_report']
    assert report['all_cached'] and report['hits'] == 12 and report['llm_calls'] == 0
    assert report['line'].startswith('stage cache: all 12 stages served from the cache')
    assert report['saved_llm_calls'] == cold['stage_report']['llm_calls']
    assert warm['stages']['notes']['report']['cached_from'] == cold['run_id']
    assert warm['spend_usd'] == 0 and warm['pipeline'] == 'classic' and warm['stt'] == cold['stt']
    # the stored artifacts were written back into the new run
    cold_dir, warm_dir = lab['root'] / 'runs' / cold['run_id'], lab['root'] / 'runs' / warm['run_id']
    assert not (warm_dir / 'llm_calls.jsonl').exists()
    for name in ('chain.json', 'day.json', 'chain_entry.json', 'baseline.json'):
        assert (warm_dir / name).read_bytes() == (cold_dir / name).read_bytes(), name
    assert sorted(p.name for p in (warm_dir / 'conversations').glob('*.json')) == sorted(
        p.name for p in (cold_dir / 'conversations').glob('*.json')
    )
    stored = json.loads((warm_dir / 'run.json').read_text())
    assert stored['stage_report']['all_cached'] and stored['stages']['tasks']['report']['cache'] == 'hit'


@pytest.mark.slow  # whole lab pipeline runs; over the fast-unit CPU limit on CI runners
def test_text_mode_prints_the_stage_table(lab, capsys):
    argv = ['run', '--day', DAY, '--ref', 'HEAD', '--in-place', '--engine', 'fake', '--llm-upstream', lab['up'].url]
    capsys.readouterr()
    assert cli.main(argv) == 0
    err = capsys.readouterr().err.splitlines()
    assert err[0].startswith('stage cache: 0 hit, 12 ran') and err[1].split() == [
        'stage',
        'cache',
        'unit',
        'seconds',
        'llm',
        'upstr',
        'pcache',
    ]
    assert [line.split()[0] for line in err[2:14]] == list(STAGES)
    assert cli.main(argv) == 0
    assert capsys.readouterr().err.startswith('stage cache: all 12 stages served from the cache')


@pytest.mark.slow  # whole lab pipeline runs; over the fast-unit CPU limit on CI runners
def test_changed_chain_input_reruns_chain_only(lab, capsys):
    run(capsys, lab)
    raw = lab['root'] / 'corpus' / DAY / 'baseline' / 'raw_conversations.jsonl'
    rows = [json.loads(line) for line in raw.read_text().splitlines()]
    rows[0]['transcript_segments'][0]['text'] += ' and one more sentence'
    raw.write_text(''.join(json.dumps(row) + '\n' for row in rows))

    after = run(capsys, lab)
    assert {s: caches(after)[s] for s in LANES} == dict.fromkeys(LANES, 'hit')
    assert {s: caches(after)[s] for s in CHAIN} == dict.fromkeys(CHAIN, 'miss')
    notes = after['stages']['notes']['report']
    # the edited conversation's notes call is new; the other two are served by the proxy cache
    assert notes['llm_calls'] == 3 and notes['llm_upstream'] == 1 and notes['llm_proxy_cache'] == 2


@pytest.mark.slow  # whole lab pipeline runs; over the fast-unit CPU limit on CI runners
def test_changed_stt_selection_reruns_transcribe_and_downstream_not_ingest(lab, capsys):
    run(capsys, lab)
    overlay = lab['tmp'] / 'overlay.json'
    overlay.write_text(json.dumps({'model_config': {'stt': {'provider': 'stub', 'model': 'stub-2'}}}))
    after = run(capsys, lab, '--overlay', str(overlay))
    # boundaries and speakers come after transcribe in stage order, so they re-run too
    assert caches(after) == {'ingest': 'hit', **{s: 'miss' for s in STAGES[1:]}}


@pytest.mark.slow  # whole lab pipeline runs; over the fast-unit CPU limit on CI runners
def test_from_stage_inside_the_chain_unit_reruns_the_unit_and_serves_upstream(lab, capsys):
    run(capsys, lab)
    again = run(capsys, lab, '--from-stage', 'goals')
    assert {s: caches(again)[s] for s in LANES} == dict.fromkeys(LANES, 'hit')
    assert {s: caches(again)[s] for s in CHAIN} == dict.fromkeys(CHAIN, 'miss')
    assert any('inside unit chain' in w and 're-runs from discard' in w for w in again['warnings'])
    # every chain call is now a proxy-cache hit: nothing upstream changed
    report = again['stage_report']
    assert report['llm_calls'] > 0 and report['llm_upstream'] == 0 and report['llm_proxy_cache'] == report['llm_calls']


@pytest.mark.slow  # whole lab pipeline runs; over the fast-unit CPU limit on CI runners
def test_partial_unit_selection_is_not_cached(lab, capsys):
    body = run(capsys, lab, '--stages', 'discard,notes')
    assert {s: body['stages'][s]['report']['cache'] for s in ('discard', 'notes')} == {'discard': 'off', 'notes': 'off'}
    assert any('only partly selected' in w for w in body['warnings'])


@pytest.mark.slow  # whole lab pipeline runs; over the fast-unit CPU limit on CI runners
def test_no_cache_flag_runs_everything(lab, capsys):
    run(capsys, lab)
    body = run(capsys, lab, '--no-cache')
    assert set(caches(body).values()) == {'off'}


# ---- transcribe: stored artifacts ---------------------------------------------------------------


def _replay_writer(calls):
    """Stands in for ``lanes.__main__.main`` (the replay command): writes ingest results the way it does."""
    from testing.pipeline_lab.lanes.output import IngestResult, write_results

    def main(argv):
        run_id = argv[argv.index('--run') + 1]
        calls.append(argv)
        results = [
            IngestResult('conv-1', 'record', None, None, 'transcript', segments=[{'start': 0.0, 'text': 'hi'}]),
            IngestResult('conv-2', 'sync', None, None, 'failed', error='cassette_miss'),
        ]
        write_results(run_id, results)
        return 0

    return main


@pytest.fixture()
def audio_day(tmp_path, monkeypatch):
    from testing.pipeline_lab.contracts import AudioIndexEntry, CorpusDay
    from testing.pipeline_lab.lanes import __main__ as lanes_main

    root = tmp_path / 'store'
    monkeypatch.setenv('OMI_PIPELINE_LAB_ROOT', str(root))
    store = Store.open(root, tmp_path / 'verdicts')
    store.write_day(CorpusDay(day_id='d1', date='2026-01-02', timezone='UTC'))
    store.write_audio_index(
        'd1',
        [AudioIndexEntry('conv-1', 'conv-1.wav', '2026-01-02T10:00:00Z', '2026-01-02T10:00:20Z', 'pcm', 16000)],
    )
    (store.audio_dir('d1') / 'conv-1.wav').write_bytes(b'RIFF' + b'\0' * 64)
    (store.day_dir('d1') / 'timeline.json').write_text(json.dumps({'coverage': {'with_audio': 1}, 'conversations': []}))
    calls = []
    monkeypatch.setattr(lanes_main, 'main', _replay_writer(calls))
    registry = Registry()
    lanes_plugin.register(registry)
    return {'store': store, 'registry': registry, 'calls': calls}


def _transcribe(audio_day, model='stub-1'):
    request = orchestrator.RunRequest(
        day_id='d1',
        ref='HEAD',
        overlay={'model_config': {'stt': {'provider': 'stub', 'model': model}}},
        stages=list(LANES),
    )
    outcome = orchestrator.run_pipeline(audio_day['store'], request, audio_day['registry'], backend_tree='t' * 40)
    assert outcome.exit_code == 0, outcome.error
    return outcome.run


def test_transcribe_is_cached_with_its_artifacts(audio_day):
    store = audio_day['store']
    first = _transcribe(audio_day)
    assert first.stages['transcribe'].extra['report']['cache'] == 'miss' and len(audio_day['calls']) == 1
    assert first.extra['stt'] == 'prerecorded stub/stub-1'

    second = _transcribe(audio_day)
    assert len(audio_day['calls']) == 1  # served from the stage cache: the replay did not run
    assert {s: second.stages[s].extra['report']['cache'] for s in LANES} == dict.fromkeys(LANES, 'hit')
    assert second.extra['stt'] == 'prerecorded stub/stub-1' and second.extra['stage_report']['all_cached']
    a, b = store.run_dir(first.run_id) / 'ingest', store.run_dir(second.run_id) / 'ingest'
    assert sorted(p.name for p in b.iterdir()) == ['conv-1.json', 'conv-2.json', 'index.json']
    for name in ('conv-1.json', 'conv-2.json', 'index.json'):
        assert (a / name).read_bytes() == (b / name).read_bytes()


def test_transcribe_key_follows_cassettes_audio_and_stt_but_ingest_does_not(audio_day):
    from testing.pipeline_lab.cassette.format import STAGE_DIR

    store = audio_day['store']
    _transcribe(audio_day)
    cassette = store.root / 'cache' / STAGE_DIR / 'ab' / ('ab' * 32 + '.json')
    cassette.parent.mkdir(parents=True)
    cassette.write_text('{}')  # a newly recorded cassette
    run = _transcribe(audio_day)
    assert run.stages['ingest'].extra['report']['cache'] == 'hit'
    assert run.stages['transcribe'].extra['report']['cache'] == 'miss' and len(audio_day['calls']) == 2

    (store.audio_dir('d1') / 'conv-1.wav').write_bytes(b'RIFF' + b'\1' * 80)  # re-exported audio
    run = _transcribe(audio_day)
    assert run.stages['transcribe'].extra['report']['cache'] == 'miss' and len(audio_day['calls']) == 3

    run = _transcribe(audio_day, model='stub-2')
    assert {s: run.stages[s].extra['report']['cache'] for s in LANES} == {
        'ingest': 'hit',
        'transcribe': 'miss',
        'boundaries': 'miss',
        'speakers': 'miss',
    }


def test_missing_artifacts_turn_a_hit_into_a_rerun(audio_day):
    store = audio_day['store']
    first = _transcribe(audio_day)
    key = first.stages['transcribe'].extra['key']
    (store.cache_files_dir('transcribe', key) / 'ingest' / 'conv-1.json').unlink()
    second = _transcribe(audio_day)
    assert second.stages['transcribe'].extra['report']['cache'] == 'miss' and len(audio_day['calls']) == 2
    assert any('missing stored artifacts' in w for w in second.warnings)


# ---- code keys ------------------------------------------------------------------------------------


def test_code_keys_scope_lane_stages_and_fold_in_dirty_edits():
    from pathlib import Path

    from testing.pipeline_lab.affected import CodeState

    repo = Path(__file__).resolve().parents[3]
    code = CodeState(repo)
    transcribe, ingest, tree = code.stage_key(['transcribe']), code.stage_key(['ingest']), code.tree_key()
    code.blobs['backend/utils/llm/goals.py'] = 'edited'  # chain-only product code
    assert code.stage_key(['transcribe']) == transcribe and code.stage_key(['ingest']) == ingest
    code.blobs['backend/utils/sync/pipeline.py'] = 'edited'  # what the sync lane runs
    assert code.stage_key(['transcribe']) != transcribe and code.stage_key(['ingest']) == ingest
    code.blobs['backend/testing/pipeline_lab/timeline/build.py'] = 'edited'
    assert code.stage_key(['ingest']) != ingest
    code.dirty['backend/utils/llm/goals.py'] = 'sha256:00'
    assert code.tree_key() != tree and code.tree_key().startswith('dirty:')


def test_chain_call_attribution_by_feature_then_tag():
    from testing.pipeline_lab.chain.plugin import attribute_call

    assert attribute_call({'stage': 'finalize', 'feature': 'conv_structure'}) == 'notes'
    assert attribute_call({'stage': 'finalize', 'feature': 'goals'}) == 'goals'
    assert attribute_call({'stage': 'open_loops', 'feature': 'open_loop_daily'}) == 'daily_summary'
    assert attribute_call({'stage': 'notes', 'feature': 'pipeline_lab_fake_notes'}) == 'notes'
    assert attribute_call({'stage': 'finalize', 'feature': 'something_new'}) == 'discard'
    assert attribute_call({'feature': 'something_new'}) is None  # the executing stage keeps it


@pytest.mark.slow  # whole lab pipeline runs; over the fast-unit CPU limit on CI runners
def test_refresh_mode_reruns_and_failed_chain_results_are_not_stored(lab, capsys):
    from testing.pipeline_lab.chain.plugin import ChainStage

    run(capsys, lab)
    refreshed = run(capsys, lab, '--llm-mode', 'refresh')
    assert set(caches(refreshed).values()) == {'miss'}
    stage = ChainStage('discard', None)
    assert stage.cache_ok({'discard': {'failed': 0}, 'daily_summary': {'status': 'ok'}}) is None
    assert stage.cache_ok({'discard': {'failed': 2}}) == '2 conversations failed to finalize'
    assert stage.cache_ok({'discard': {}, 'daily_summary': {'status': 'failed'}}) == 'daily summary failed'
    # A v3 replay whose arrival or reconcile event raised finishes partial with no failed conversation: not stored.
    partial = {'failed': 0, 'v3': {'driver_status': 'partial', 'driver_failed': 1}}
    assert stage.cache_ok({'discard': partial, 'daily_summary': {'status': 'ok'}}) == (
        'v3 driver partial (1 events failed)'
    )
    clean = {'failed': 0, 'v3': {'driver_status': 'ok', 'driver_failed': 0}}
    assert stage.cache_ok({'discard': clean, 'daily_summary': {'status': 'ok'}}) is None


def test_discard_summary_carries_the_v3_driver_status(tmp_path):
    import json as _json

    from testing.pipeline_lab.chain.plugin import stage_summary

    entry = {
        'pipeline': 'v3',
        'driver': {'summary': {'status': 'partial', 'failed': 2, 'counts': {'arrival': {'error': 2}}}},
    }
    (tmp_path / 'chain_entry.json').write_text(_json.dumps(entry))
    out, _ = stage_summary('discard', tmp_path)
    assert out['v3']['driver_status'] == 'partial'
    assert out['v3']['driver_failed'] == 2
    assert out['v3']['driver'] == {'arrival': {'error': 2}}


def test_harness_identity_changes_with_lab_code_and_ignores_bytecode(tmp_path, monkeypatch):
    from testing.pipeline_lab import orchestrator, worktrees

    pkg = tmp_path / 'pipeline_lab'
    (pkg / 'scenario').mkdir(parents=True)
    (pkg / 'scenario' / 'ops.py').write_text('A = 1\n')
    monkeypatch.setattr(worktrees, 'harness_package_dir', lambda: pkg)
    first = orchestrator.harness_identity()
    (pkg / '__pycache__').mkdir()
    (pkg / '__pycache__' / 'ops.cpython-311.pyc').write_bytes(b'bytecode')
    assert orchestrator.harness_identity() == first  # bytecode is not the harness
    (pkg / 'scenario' / 'ops.py').write_text('A = 2\n')
    assert orchestrator.harness_identity() != first  # a changed stand-in or driver must miss the cache


def test_transcribe_with_transient_replay_failures_is_not_stored():
    from testing.pipeline_lab.lanes.plugin import TranscribeStage, _deterministic_failure

    stage = TranscribeStage()
    assert stage.cache_ok({'transcribe': {'outcomes': {'transcript': 3}, 'failed_transient': 0}}) is None
    assert stage.cache_ok({'transcribe': {'source': 'stored'}}) is None  # nothing replayed
    # a cassette miss is keyed by the cassette inventory: stored; a worker or VAD error is not
    assert stage.cache_ok({'transcribe': {'outcomes': {'failed': 1}, 'failed_transient': 0}}) is None
    assert stage.cache_ok({'transcribe': {'outcomes': {'failed': 2}, 'failed_transient': 1}}) == (
        '1 conversations failed to replay'
    )
    assert _deterministic_failure('cassette_miss') and _deterministic_failure('lane_not_replayed:streaming')
    assert not _deterministic_failure('vad_failed') and not _deterministic_failure(None)
