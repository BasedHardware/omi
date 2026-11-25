"""Pipeline-lab scenario run directory: verdict.json, run.json, the layout contract, and --repeat (no stack)."""

from __future__ import annotations

from contextlib import contextmanager
import copy
import json

import pytest

from testing.pipeline_lab import cli
from testing.pipeline_lab.scenario import stack, verdict as verdicts
from testing.pipeline_lab.scenario.spec import load_scenario

FAST = stack.SCENARIO_DIR / 'finish_single_recording_fast.json'
CONV = {
    'handle': 'd66c3117',
    'recordings': ['B'],
    'words': 100,
    'visible': True,
    'hidden_reason': 'manual_end',
    'manual_end': True,
    'kind': 'conversation',
    'status': 'completed',
    'deleted': False,
    'started_at': '2026-03-14T09:00:00Z',
}


def result(handle: str = 'd66c3117', seconds: float = 12.5, **changes) -> dict:
    conv = {**CONV, 'handle': handle}
    row = {
        'scenario': 'finish_single_recording_fast',
        'timings': {'environment': 3.0, 'driver': seconds},
        'outcome': 'passed',
        'finish_target': 'B',
        'checks': [
            {'check': 'c0', 'ok': True, 'detail': f'B in {handle}'},
            {'check': 'c1', 'ok': True, 'detail': f'B in {handle}'},
            {'check': 'c2', 'ok': True, 'detail': 'none hidden'},
        ],
        'conversations': [conv],
        'checkpoints': {'0': {'t': 60.0, 'conversations': [conv]}},
        'stand_ins': {'record_admission': 1, 'capture_close': 1},
        'seconds': seconds,
    }
    row.update(changes)
    return row


def test_scenario_verdict_rows_carry_expected_and_actual():
    row = verdicts.scenario_verdict('finish_single_recording_fast', result(), load_scenario(FAST))
    assert row['outcome'] == 'passed' and row['error'] is None
    assert row['stand_ins'] == ['capture_close', 'record_admission']
    first, final, hidden = row['checks']
    assert first['at'] == 60.0 and final['at'] is None
    assert first['expected'] == {'conversation_of': '@finish', 'recordings': ['B'], 'visible': True, 'manual_end': True}
    assert first['actual']['conversation']['words'] == 100
    assert 'handle' not in first['actual']['conversation']
    assert hidden['expected'] == {'no_hidden_with': 'B'} and hidden['actual']['hidden'] == []


def test_scenario_verdict_of_an_error_has_no_checks():
    row = verdicts.scenario_verdict('x', {'outcome': 'error', 'error': 'RuntimeError', 'seconds': 1.0})
    assert row == {
        'name': 'x',
        'outcome': 'error',
        'seconds': 1.0,
        'checks': [],
        'stand_ins': [],
        'transcripts': {},
        'error': 'RuntimeError',
    }


@pytest.mark.parametrize(
    'outcomes, overall, code',
    [
        (['passed', 'xfail'], 'passed', 0),
        (['passed', 'xpass'], 'failed', 1),
        (['nondeterministic'], 'failed', 1),
        (['failed', 'error'], 'error', 2),
        ([], 'passed', 0),
    ],
)
def test_overall_outcome(outcomes, overall, code):
    assert verdicts.overall_outcome(outcomes) == overall
    assert verdicts.exit_code(outcomes) == code


def _write(tmp_path, name, payload, home=None):
    out = tmp_path / name
    out.mkdir()
    (out / 'result.json').write_text(json.dumps(payload))
    if home is not None:
        (out / 'home.json').write_text(json.dumps(home))
    return out


def test_repeat_differences_drop_wall_clock_through_determinism(tmp_path):
    """One allowlist (determinism.SCENARIO_ARTIFACTS): seconds, timings, log, Home's updated_at."""
    home = {'snapshots': [{'label': 'final', 'response': [{'id': 'd66c3117-x', 'updated_at': '2026-11-25T21:07:18Z'}]}]}
    later = copy.deepcopy(home)
    later['snapshots'][0]['response'][0]['updated_at'] = '2026-11-25T21:08:02Z'
    a = _write(tmp_path, 'a', {**result(seconds=12.5), 'log': '/tmp/a/scenario_error.log'}, home)
    b = _write(tmp_path, 'b', {**result(seconds=40.1), 'log': '/tmp/b/scenario_error.log'}, later)
    assert verdicts.repeat_differences([a, b]) == []
    drifted = result()
    drifted['conversations'] = [{**CONV, 'words': 90}]
    c = _write(tmp_path, 'c', drifted, home)
    assert verdicts.repeat_differences([a, b, c]) == ['result.json $.conversations[0].words']
    retitled = copy.deepcopy(home)
    retitled['snapshots'][0]['response'][0]['title'] = 'other'
    d = _write(tmp_path, 'd', result(), retitled)
    assert verdicts.repeat_differences([a, d]) == ['home.json $.snapshots[0].response[0].title']


def test_transcript_sources_per_recording():
    payload = result(
        recordings=[{'label': 'A', 'stt': 'synthetic'}, {'label': 'B'}],
        audio={'recordings': [{'label': 'A', 'source': 'synthetic'}]},
    )
    assert verdicts.transcript_sources(payload) == {'A': 'synthetic', 'B': 'scripted'}
    assert verdicts.scenario_verdict('x', payload)['transcripts'] == {'A': 'synthetic', 'B': 'scripted'}


class _Slots:
    databases = 16

    def __init__(self, *_):
        self.n = 0

    def claim(self, run_id, ttl):
        self.n += 1
        return self.n

    def release(self, db, run_id):
        return True


@pytest.fixture
def fake_runs(monkeypatch):
    """run_one writes result.json like scenario/run.py; one canned result per call, in order."""
    queue: list[dict] = []
    calls: list[dict] = []

    def run_one(path, out, peers, *, timeout, clock='frozen', isolation=None, arm=None, stt_args=()):
        row = queue.pop(0) if queue else result()
        calls.append({'out': out, 'isolation': isolation, 'arm': arm})
        (out / 'result.json').write_text(json.dumps(row))
        (out / 'v3_tasks.jsonl').write_text('')
        (out / 'decisions.jsonl').write_text('')
        return row

    @contextmanager
    def local_stack(work):
        yield stack.Peers('127.0.0.1:1', '127.0.0.1:2', 'given')

    monkeypatch.setattr(stack, 'run_one', run_one)
    monkeypatch.setattr(stack, 'RedisSlots', _Slots)
    monkeypatch.setattr(stack, 'delete_project', lambda host, project: None)
    monkeypatch.setattr(stack, 'local_stack', local_stack)
    return queue, calls


def test_run_dir_layout_contract(tmp_path, fake_runs, capsys):
    _, calls = fake_runs
    out = tmp_path / 'run'
    code = cli.main(['scenario', 'run', str(FAST), '--keep', str(out), '--json'])
    assert code == 0
    printed = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    on_disk = json.loads((out / 'verdict.json').read_text())
    assert printed == on_disk and on_disk['schema'] == 1 and on_disk['outcome'] == 'passed'
    assert set(on_disk['scenarios'][0]) == {'name', 'outcome', 'seconds', 'checks', 'stand_ins', 'transcripts', 'error'}
    assert set(on_disk['scenarios'][0]['checks'][0]) == {'label', 'passed', 'expected', 'actual', 'at'}
    run = json.loads((out / 'run.json').read_text())
    assert {'schema', 'backend_tree', 'ref', 'started_at', 'seconds', 'scenarios', 'isolation'} <= set(run)
    assert run['scenarios'] == ['finish_single_recording_fast']
    (iso,) = run['isolation']['runs']
    assert iso['project_id'].startswith('demo-lab-') and iso['redis_db'] == 1
    assert calls[0]['isolation'].project_id == iso['project_id']
    names = sorted(p.name for p in (out / 'finish_single_recording_fast').iterdir())
    assert names == ['decisions.jsonl', 'result.json', 'scenario.json', 'v3_tasks.jsonl']  # no home.json here
    assert (out / 'finish_single_recording_fast' / 'scenario.json').read_bytes() == FAST.read_bytes()


def test_failed_exit_code_and_outcome(tmp_path, fake_runs, capsys):
    queue, _ = fake_runs
    queue.append(result(outcome='failed'))
    assert cli.main(['scenario', 'run', str(FAST), '--keep', str(tmp_path / 'r')]) == 1
    assert json.loads((tmp_path / 'r' / 'verdict.json').read_text())['outcome'] == 'failed'


def test_repeat_passes_when_only_wall_clock_differs(tmp_path, fake_runs, capsys):
    queue, calls = fake_runs
    queue.extend([result(seconds=10.0), result(seconds=20.0), result(seconds=30.0)])
    out = tmp_path / 'r'
    assert cli.main(['scenario', 'run', str(FAST), '--keep', str(out), '--repeat', '3', '--jobs', '2']) == 0
    row = json.loads((out / 'verdict.json').read_text())['scenarios'][0]
    assert row['outcome'] == 'passed' and row['repeats'] == 3 and row['differences'] == []
    assert sorted(str(c['out'].relative_to(out)) for c in calls) == [
        'finish_single_recording_fast',
        'finish_single_recording_fast/repeat-2',
        'finish_single_recording_fast/repeat-3',
    ]
    assert len({c['isolation'].run_id for c in calls}) == 3


def test_repeat_that_differs_is_nondeterministic(tmp_path, fake_runs, capsys):
    queue, _ = fake_runs
    drifted = result()
    drifted['conversations'] = [{**CONV, 'visible': False, 'hidden_reason': 'too_short'}]
    queue.extend([result(), drifted])
    out = tmp_path / 'r'
    assert cli.main(['scenario', 'run', str(FAST), '--keep', str(out), '--repeat', '2']) == 1
    verdict = json.loads((out / 'verdict.json').read_text())
    assert verdict['outcome'] == 'failed'
    assert verdict['scenarios'][0]['outcome'] == 'nondeterministic'
    assert verdict['scenarios'][0]['differences'] == [
        'result.json $.conversations[0].hidden_reason',
        'result.json $.conversations[0].visible',
    ]
    assert 'differs between repeats at: result.json $.conversations[0].hidden_reason' in capsys.readouterr().out


def test_jobs_and_repeat_must_be_positive(tmp_path, fake_runs, capsys):
    assert cli.main(['scenario', 'run', str(FAST), '--keep', str(tmp_path / 'r'), '--jobs', '0']) == 2


def test_duplicate_scenarios_are_refused(tmp_path, fake_runs, capsys):
    copy_path = tmp_path / 'copy.json'
    copy_path.write_text(copy.deepcopy(FAST.read_text()))
    assert cli.main(['scenario', 'run', str(FAST), str(copy_path), '--keep', str(tmp_path / 'r')]) == 2
