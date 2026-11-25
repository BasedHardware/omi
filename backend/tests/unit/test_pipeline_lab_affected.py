"""``affected``: changed paths -> earliest lab stage and scenarios, from import closures, an explicit
table and a conservative default; plus a runtime trace that keeps the lanes' product scope honest."""

import fnmatch
import json
import sys
import threading
import wave
from pathlib import Path

import numpy as np
import pytest

from testing.pipeline_lab import affected, cli
from testing.pipeline_lab.contracts import STAGES

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / 'backend'


@pytest.fixture(scope='module')
def stage_map():
    """One map for the module: the product import closures (~1,400 files parsed) are built here, once."""
    built = affected.StageMap(affected.DiskSource(REPO))
    for stage in STAGES:
        built.reach(stage)
    built.in_scenarios('backend/utils/llm/goals.py')
    built.world()
    return built


@pytest.fixture(scope='module')
def report(stage_map):

    def classify(*paths):
        out = affected.affected(REPO, 'HEAD', paths=list(paths), stage_map=stage_map)
        return out, {row['path']: row for row in out['paths']}

    return classify


def test_self_check_passes_and_covers_every_contract_stage():
    assert affected.self_check(REPO) == []
    assert set(affected.STAGE_ROOTS) == set(STAGES)


def test_self_check_fails_when_a_stage_has_no_entry(monkeypatch):
    roots = dict(affected.STAGE_ROOTS)
    roots.pop('goals')
    monkeypatch.setattr(affected, 'STAGE_ROOTS', roots)
    assert affected.self_check() == ['stage goals has no STAGE_ROOTS entry']
    with pytest.raises(ValueError, match='self-check failed'):
        affected.affected(REPO, 'HEAD', paths=[])


def test_self_check_fails_on_a_root_without_a_file(monkeypatch):
    roots = dict(affected.STAGE_ROOTS, notes=('testing.pipeline_lab.no_such_module',))
    monkeypatch.setattr(affected, 'STAGE_ROOTS', roots)
    assert affected.self_check(REPO) == ['notes: root testing.pipeline_lab.no_such_module names no file']


@pytest.mark.parametrize(
    'path, stage, rule',
    [
        ('backend/utils/llm/goals.py', 'discard', 'closure'),  # product code the chain reaches
        ('backend/utils/conversations/process_conversation.py', 'discard', 'closure'),
        ('backend/utils/sync/pipeline.py', 'transcribe', 'closure'),  # the sync lane's product scope
        ('backend/utils/stt/local_vad.py', 'ingest', 'closure'),  # timeline VAD
        ('backend/testing/pipeline_lab/lanes/sync.py', 'transcribe', 'closure'),
        ('backend/testing/pipeline_lab/timeline/build.py', 'ingest', 'closure'),
        ('backend/testing/pipeline_lab/lanes/plugin.py', 'ingest', 'table'),
        ('backend/testing/pipeline_lab/chain/driver.py', 'discard', 'closure'),
        ('backend/testing/pipeline_lab/day/run.py', 'daily_summary', 'closure'),  # refined
        ('backend/testing/pipeline_lab/orchestrator.py', 'ingest', 'table'),
        ('backend/pylock.toml', 'ingest', 'table'),
        ('backend/deploy/runtime_env.yaml', 'discard', 'table'),
        ('backend/routers/no_such_router.py', 'ingest', 'default'),  # unmapped: run everything
        ('backend/some/new/config.yaml', 'ingest', 'default'),
        ('backend/testing/pipeline_lab/inspector/server.py', None, 'table'),
        ('backend/testing/pipeline_lab/ideal/runs.py', None, 'table'),
        ('backend/tests/unit/test_pipeline_lab_affected.py', None, 'table'),
        ('backend/testing/pipeline_lab/README.md', None, 'table'),
        ('app/lib/main.dart', None, 'outside'),
        ('desktop/macos/Sources/App.swift', None, 'outside'),
    ],
)
def test_path_classification(report, path, stage, rule):
    _, rows = report(path)
    assert (rows[path]['stage'], rows[path]['rule']) == (stage, rule), rows[path]


def test_scenarios_follow_their_closure_and_their_own_file(report):
    names = affected.scenario_names(affected.DiskSource(REPO), REPO)
    assert names and all((REPO / affected.SCENARIO_DIR / f'{n}.json').is_file() for n in names)
    scenario_file = f'{affected.SCENARIO_DIR}/{names[0]}.json'
    out, rows = report(scenario_file, 'backend/testing/pipeline_lab/scenario/ops.py', 'backend/utils/llm/goals.py')
    assert rows[scenario_file]['scenarios'] == [names[0]] and rows[scenario_file]['stage'] is None
    assert rows['backend/testing/pipeline_lab/scenario/ops.py']['scenarios'] == names
    assert rows['backend/utils/llm/goals.py']['scenarios'] == names  # measured: every scenario calls it
    _, rows = report('backend/testing/pipeline_lab/timeline/build.py')
    assert rows['backend/testing/pipeline_lab/timeline/build.py']['scenarios'] == []


AUDIO_SCENARIOS = ['audio_single_recording_finish']


@pytest.mark.parametrize(
    'path, expected, reason',
    [
        # the product areas every scenario exercises by design
        ('backend/utils/conversations/v3/visibility.py', 'all', 'visibility'),
        ('backend/utils/conversations/v3/finish.py', 'all', 'Finish'),
        ('backend/utils/conversations/v3/fast_finish.py', 'all', 'fast finish'),
        ('backend/routers/conversations.py', 'all', 'Home routes'),
        ('backend/deploy/runtime_env.yaml', 'all', 'production profile'),
        # the scenario harness and view
        ('backend/testing/pipeline_lab/scenario/spec.py', 'all', 'scenario harness'),
        ('backend/testing/pipeline_lab/inspector/scenario_view.py', 'all', 'scenario view'),
        ('backend/testing/pipeline_lab/inspector/static/scenario.js', 'all', 'scenario view page'),
        # audio words: only the scenarios with an audio_file
        ('backend/testing/pipeline_lab/cassette/player.py', AUDIO_SCENARIOS, 'STT cassettes'),
        ('backend/testing/pipeline_lab/scenario/audio.py', AUDIO_SCENARIOS, 'audio_file'),
        ('backend/testing/pipeline_lab/scenario/fixtures/audio/synthetic_two_voices.wav', AUDIO_SCENARIOS, 'names it'),
        ('backend/diarizer/batch_pipeline.py', AUDIO_SCENARIOS, 'measured'),  # the batch lane, audio only
        # not part of any scenario
        ('backend/testing/pipeline_lab/scenario/IMPORTER.md', [], 'documentation'),
        ('backend/utils/llm/notes_agent_prompt.py', [], 'no committed scenario calls it'),
        ('backend/testing/pipeline_lab/timeline/build.py', [], ''),
        ('app/lib/main.dart', [], ''),
    ],
)
def test_scenario_world_names_the_right_scenarios(report, path, expected, reason):
    names = affected.scenario_names(affected.DiskSource(REPO), REPO)
    _, rows = report(path)
    assert rows[path]['scenarios'] == (names if expected == 'all' else expected), rows[path]
    assert reason in rows[path]['scenario_reason']


def test_scenario_reach_is_current():
    """reach.json measures every committed scenario and names only files that exist. Re-measure with
    ``scenario run --trace-calls --keep DIR`` then ``scenario reach DIR`` (scenario/reach.py)."""
    world = affected.ScenarioWorld.read(affected.DiskSource(REPO))
    assert set(world.reach) == set(world.names), 'scenario reach.json is missing or has extra scenarios'
    missing = sorted({rel for files in world.reach.values() for rel in files if not (REPO / rel).is_file()})
    assert not missing, f'reach.json names files that no longer exist: {missing[:10]}'
    assert world.audio == set(AUDIO_SCENARIOS)


def test_unmeasured_scenario_is_named_for_anything_the_runner_imports(stage_map, monkeypatch):
    world = stage_map.world()
    names = [*world.names, 'zz_new_scenario']
    monkeypatch.setattr(stage_map, '_world', affected.ScenarioWorld(names, world.texts, world.audio, world.reach))
    found, why = stage_map.scenarios_for('backend/utils/llm/notes_agent_prompt.py')  # imported, never called
    assert found == ['zz_new_scenario'] and 'not measured yet' in why
    found, _ = stage_map.scenarios_for('backend/diarizer/batch_pipeline.py')
    assert found == [*AUDIO_SCENARIOS, 'zz_new_scenario']


def test_report_names_the_unit_and_the_command(report):
    out, _ = report('backend/utils/llm/goals.py', 'backend/testing/pipeline_lab/inspector/views.py')
    assert out['earliest_stage'] == 'discard'
    assert out['rerun_stages'] == list(STAGES[STAGES.index('discard') :])
    assert out['units'] == [
        {'unit': 'chain', 'stages': list(STAGES[4:]), 'why': 'one process_conversation per conversation'}
    ]
    assert out['commands'][0].endswith('--in-place --from-stage discard')
    # a late refined stage still starts at its unit's first stage
    out, _ = report('backend/testing/pipeline_lab/day/run.py')
    assert out['earliest_stage'] == 'daily_summary' and out['commands'][0].endswith('--from-stage discard')
    out, _ = report('backend/testing/pipeline_lab/inspector/views.py')
    assert out['earliest_stage'] is None and out['rerun_stages'] == [] and out['commands'] == []
    assert 'no lab stage can see these changes' in affected.format_text(out)


def test_removed_file_is_looked_up_on_the_base_side():
    class Head(affected.DiskSource):
        def exists(self, rel):
            return rel != 'backend/testing/pipeline_lab/lanes/batch.py' and super().exists(rel)

    rel = 'backend/testing/pipeline_lab/lanes/batch.py'
    head = Head(REPO)
    assert affected.StageMap(head, affected.DiskSource(REPO)).earliest_reach(rel) == 'transcribe'
    alone = affected.StageMap(head)  # without the base side, the head's lab closures do not hold it
    assert not any(alone.in_reach(head, stage, rel) for stage in ('ingest', 'transcribe'))


def test_cli_affected_json_for_an_empty_range(tmp_path, capsys):
    root, verdicts = tmp_path / 'store', tmp_path / 'verdicts'
    code = cli.main(['--root', str(root), '--verdicts', str(verdicts), '--json', 'affected', 'HEAD..HEAD'])
    body = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert code == 0 and body['changed'] == 0 and body['earliest_stage'] is None
    code = cli.main(['--root', str(root), '--verdicts', str(verdicts), 'affected', 'HEAD..HEAD'])
    text = capsys.readouterr().out
    assert code == 0 and text.startswith('affected HEAD..HEAD: 0 changed paths')


def test_closure_ignores_type_checking_imports_and_follows_module_strings(tmp_path):
    pkg = tmp_path / 'backend' / 'pkg'
    pkg.mkdir(parents=True)
    (pkg / '__init__.py').write_text('')
    (pkg / 'a.py').write_text(
        'from typing import TYPE_CHECKING\n'
        'if TYPE_CHECKING:\n    from pkg import typed\n'
        "ENTRY = 'pkg.entry'\n"
        'def f():\n    from . import lazy\n'
    )
    for name in ('typed', 'entry', 'lazy'):
        (pkg / f'{name}.py').write_text('')
    reached = affected.closure(affected.DiskSource(tmp_path), ['pkg.a'])
    assert reached == {f'backend/pkg/{n}.py' for n in ('__init__', 'a', 'entry', 'lazy')}


# ---- the lanes' product scope, checked by tracing a replay -----------------------------------------


def _product_calls(fn):
    """Backend product files (outside ``testing/``) with a function called while ``fn`` runs."""
    seen: set[str] = set()
    prefix = str(BACKEND) + '/'

    def profile(frame, event, arg):
        if event == 'call':
            name = frame.f_code.co_filename
            rel = name[len(prefix) :]
            if name.startswith(prefix) and not rel.startswith(('testing/', 'tests/', '.venv/')):
                if frame.f_code.co_name != '<module>':
                    seen.add('backend/' + rel)

    sys.setprofile(profile)
    threading.setprofile(profile)
    try:
        fn()
    finally:
        sys.setprofile(None)
        threading.setprofile(None)  # type: ignore[arg-type]
    return seen


def _write_wav(path, data):
    with wave.open(str(path), 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        out.writeframes(data)


def test_lane_product_calls_stay_inside_the_declared_scope(tmp_path, monkeypatch):
    from testing.pipeline_lab.cassette.adapters import StubAdapter
    from testing.pipeline_lab.cassette.format import Word
    from testing.pipeline_lab.cassette.recorder import InMemoryLedger, Recorder
    from testing.pipeline_lab.lanes.day import STTSelection, record_day_cassettes, replay_day
    from testing.pipeline_lab.timeline.build import build_day_timeline

    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED', 'false')
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
    ]
    (day / 'baseline' / 'conversations.jsonl').write_text('\n'.join(json.dumps(r) for r in rows))
    index = [
        {'conversation_id': 'rec', 'path': 'rec.wav', 'start': '2026-01-02T10:00:00Z', 'end': '2026-01-02T10:00:20Z'},
        {'conversation_id': 'syn', 'path': 'syn.wav', 'start': '2026-01-02T11:00:00Z', 'end': '2026-01-02T11:00:30Z'},
    ]
    (day / 'audio' / 'index.json').write_text(json.dumps(index))
    for i, (entry, seconds) in enumerate(zip(index, (20, 30))):
        data = np.random.default_rng(i).normal(0, 3000, int(16000 * seconds)).astype('<i2').tobytes()
        _write_wav(day / 'audio' / entry['path'], data)

    def script(request):
        count = 8
        return [
            Word(1.0 + j * 0.5, 1.3 + j * 0.5, f'w{j}', 'SPEAKER_00' if j < count // 2 else 'SPEAKER_01')
            for j in range(count)
        ]

    adapter = StubAdapter(script, provider='stub', model='stub-1')
    recorder = Recorder(adapter, InMemoryLedger(1.0), vendor_log=root / 'vendor_log.jsonl', root=root)
    file_vad = lambda path: [{'start': 2.0, 'end': 9.0}]  # noqa: E731
    lanes = {'sync_exact': True, 'lanes': ('record', 'sync')}

    def ingest():
        build_day_timeline(day_id, root=root)

    def transcribe():
        replay_day(
            day_id,
            'run-1',
            STTSelection('stub', 'stub-1', 'en'),
            root=root,
            sync_mode='exact',
            vad=lambda samples: [(0.0, len(samples) / 16000)],
            file_vad=file_vad,
        )

    ingest()
    record_day_cassettes(day_id, recorder, language='en', root=root, file_vad=file_vad, **lanes)
    transcribe()  # warm: imports and module bodies run here, outside the trace
    results = json.loads((root / 'runs' / 'run-1' / 'ingest' / 'index.json').read_text())['conversations']
    assert {r['outcome'] for r in results} == {'transcript'}

    for stage, fn in (('ingest', ingest), ('transcribe', transcribe)):
        called = _product_calls(fn)
        scope = affected.PRODUCT_SCOPE[stage]
        outside = sorted(rel for rel in called if not any(fnmatch.fnmatch(rel, p) for p in scope))
        assert not outside, f'{stage} calls product code outside PRODUCT_SCOPE: {outside}'
        if stage == 'transcribe':
            assert any(rel.startswith('backend/utils/sync/') for rel in called)  # the trace saw the lane
