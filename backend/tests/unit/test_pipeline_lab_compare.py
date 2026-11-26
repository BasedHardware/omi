"""Pipeline-lab ``scenario compare``: conversation diffs, compare.json and exit codes (no stack)."""

from __future__ import annotations

from contextlib import contextmanager
import json

import pytest

from testing.pipeline_lab import cli
from testing.pipeline_lab.scenario import compare, stack

CONV = {
    'handle': 'aaaa1111',
    'recordings': ['A', 'F'],
    'words': 120,
    'visible': True,
    'hidden_reason': None,
    'manual_end': True,
    'deleted': False,
    'started_at': '2026-03-14T09:00:00Z',
}


def test_same_conversations_with_different_handles_do_not_differ():
    assert compare.diff_conversations([CONV], [{**CONV, 'handle': 'bbbb2222'}]) == []


def test_a_changed_field_and_a_missing_conversation_are_listed():
    other = {**CONV, 'recordings': ['B'], 'words': 10}
    rows = compare.diff_conversations([CONV, other], [{**CONV, 'visible': False, 'hidden_reason': 'too_short'}])
    assert rows == [
        {
            'key': 'A+F',
            'base': {k: CONV[k] for k in compare.COMPARED},
            'head': {**{k: CONV[k] for k in compare.COMPARED}, 'visible': False, 'hidden_reason': 'too_short'},
            'fields': ['hidden_reason', 'visible'],
        },
        {'key': 'B', 'base': {k: other[k] for k in compare.COMPARED}, 'head': None, 'fields': ['present']},
    ]


def test_deleted_conversations_are_ignored_and_repeated_keys_are_numbered():
    deleted = {**CONV, 'deleted': True, 'words': 1}
    assert compare.diff_conversations([CONV, deleted], [CONV]) == []
    assert list(compare._keyed([CONV, {**CONV, 'started_at': '2026-03-14T10:00:00Z'}])) == ['A+F', 'A+F#2']


def test_compare_results_flags_outcome_changes():
    rows = compare.compare_results(
        {'s': {'conversations': [CONV]}}, {'s': {'conversations': [CONV]}}, {'s': ('passed', 'failed')}
    )
    assert rows == [{'name': 's', 'base': 'passed', 'head': 'failed', 'differs': True, 'conversations': []}]


@pytest.fixture
def fake_sides(monkeypatch, tmp_path):
    """Two sides whose run_one returns per-side canned results; no worktree, no stack."""
    heads: dict[str, list] = {'base': [], 'head': []}
    seen_arms = []

    def run_one(path, out, peers, *, timeout, clock='frozen', isolation=None, arm=None, stt_args=()):
        side = out.relative_to(out.parents[1]).parts[0]
        seen_arms.append((side, arm))
        conv = heads[side].pop(0) if heads[side] else CONV
        row = {'scenario': path.stem, 'outcome': 'passed', 'checks': [], 'conversations': [conv], 'seconds': 1.0}
        (out / 'result.json').write_text(json.dumps(row))
        return row

    @contextmanager
    def local_stack(work):
        yield stack.Peers('127.0.0.1:1', '127.0.0.1:2', 'given')

    class Slots:
        databases = 16

        def __init__(self, *_):
            self.n = 0

        def claim(self, run_id, ttl):
            self.n += 1
            return self.n

        def release(self, db, run_id):
            return True

    def side(repo, ref, vendor_root):
        if ref is None:
            return None, {'ref': 'worktree', 'sha': 'h' * 40, 'backend_tree': 't2', 'dirty': True}
        return stack.Arm(backend=tmp_path, vendor=vendor_root), {
            'ref': ref,
            'sha': 'b' * 40,
            'backend_tree': 't1',
            'dirty': False,
        }

    monkeypatch.setattr(stack, 'run_one', run_one)
    monkeypatch.setattr(stack, 'RedisSlots', Slots)
    monkeypatch.setattr(stack, 'delete_project', lambda host, project: None)
    monkeypatch.setattr(stack, 'local_stack', local_stack)
    monkeypatch.setattr(compare, '_side', side)
    return heads, seen_arms


def test_compare_writes_both_layouts_and_exits_zero_when_equal(tmp_path, fake_sides, capsys):
    _, arms = fake_sides
    out = tmp_path / 'cmp'
    code = cli.main(['scenario', 'compare', 'main', '--scenario', 'finish_single_recording_fast', '--keep', str(out)])
    assert code == 0
    report = json.loads((out / 'compare.json').read_text())
    assert report['differs'] is False and report['base']['ref'] == 'main' and report['head']['ref'] == 'worktree'
    for side in ('base', 'head'):
        assert (out / side / 'run.json').exists() and (out / side / 'verdict.json').exists()
        assert (out / side / 'finish_single_recording_fast' / 'scenario.json').exists()
    assert [a is None for _, a in arms] == [False, True]  # base ran in an arm, head in this tree


def test_compare_exits_one_when_a_conversation_differs(tmp_path, fake_sides, capsys):
    heads, _ = fake_sides
    heads['head'].append({**CONV, 'words': 3, 'visible': False, 'hidden_reason': 'too_short'})
    out = tmp_path / 'cmp'
    code = cli.main(
        [
            'scenario',
            'compare',
            'main',
            '--worktree',
            '--scenario',
            'finish_single_recording_fast',
            '--keep',
            str(out),
            '--json',
        ]
    )
    assert code == 1
    printed = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    (row,) = printed['scenarios']
    assert row['differs'] and row['conversations'][0]['fields'] == ['hidden_reason', 'visible', 'words']


def test_compare_refuses_head_and_worktree_together(tmp_path, fake_sides, capsys):
    assert cli.main(['scenario', 'compare', 'main', 'other', '--worktree', '--keep', str(tmp_path / 'c')]) == 2


# ---- arms: {name, ref, overlay, env} ------------------------------------------------------------------


def test_arm_specs_parse_json_and_shorthand(tmp_path):
    arm = compare.parse_arm_spec('{"name": "t5", "env": {"CONVERSATIONS_V3_X": "5"}}')
    assert (arm.name, arm.ref, dict(arm.env)) == ('t5', None, {'CONVERSATIONS_V3_X': '5'})
    assert compare.parse_arm_spec('old@main') == compare.ArmSpec('old', 'main')
    assert compare.parse_arm_spec('here') == compare.ArmSpec('here', None)
    assert compare.parse_arm_spec('here').effective_overlay() is None  # nothing to apply: today's behaviour
    for bad in (
        '{"name": "x", "threshold": 5}',  # unknown key
        '{"name": "../x"}',
        '{"name": "x", "env": {"A": 5}}',  # env values are strings
        '{"name": "x", "ref": "--upload-pack=y"}',
        '{"name": "x", "overlay": "missing.json"}',
        '{"name": "x", "env": {"CONVERSATIONS_V3_SERVE_PERCENT": "5"}}',  # cohorts go through overlay "serving"
        'x@',
    ):
        with pytest.raises(stack.ScenarioError):
            compare.parse_arm_spec(bad)


def test_arms_file_resolves_overlays_beside_it_and_names_the_baseline(tmp_path):
    (tmp_path / 'ov.json').write_text(json.dumps({'name': 'ov', 'env': {'A': '1', 'B': '1'}, 'serving': {'S': True}}))
    (tmp_path / 'arms.json').write_text(
        json.dumps(
            {
                'baseline': 'off',
                'arms': [
                    {'name': 'on', 'overlay': 'ov.json', 'env': {'B': '2'}},
                    {'name': 'off', 'ref': None},
                ],
            }
        )
    )
    arms, baseline = compare.load_arms(str(tmp_path / 'arms.json'))
    assert baseline == 'off' and [a.name for a in arms] == ['on', 'off']
    effective = arms[0].effective_overlay()
    assert effective['env'] == {'A': '1', 'B': '2'} and effective['serving'] == {'S': True}  # env wins
    described = arms[0].describe()
    assert described['overlay']['file'] == 'ov.json' and described['overlay']['env_keys'] == ['A', 'B']
    assert compare.check_arms(arms, baseline) == 'off'
    with pytest.raises(stack.ScenarioError):
        compare.check_arms(arms, 'nope')
    with pytest.raises(stack.ScenarioError):
        compare.check_arms(arms[:1], None)
    with pytest.raises(stack.ScenarioError):
        compare.check_arms([arms[0], arms[0]], None)


def test_arm_env_redacts_secret_shaped_values():
    arm = compare.parse_arm_spec('{"name": "a", "env": {"SOME_API_KEY": "sk-123", "LEVEL": "3"}}')
    env = arm.describe()['env']
    assert env['LEVEL'] == '3' and env['SOME_API_KEY'].startswith('redacted:')


@pytest.fixture
def arm_runs(monkeypatch, fake_sides, tmp_path):
    """Every arm on this tree: run_one answers per arm name and records the arguments each arm ran with."""
    convs: dict[str, dict] = {}
    seen: dict[str, list] = {}

    def run_one(path, out, peers, *, timeout, clock='frozen', isolation=None, arm=None, stt_args=()):
        name = out.relative_to(out.parents[1]).parts[0]
        seen.setdefault(name, []).append(list(stt_args))
        outcome = 'error' if convs.get(name) == 'error' else 'passed'
        conv = convs.get(name) if isinstance(convs.get(name), dict) else CONV
        ops = {'reads': 10 + len(name), 'writes': 4, 'vendor_calls': {'stt': 1, 'llm': 2}}
        row = {'scenario': path.stem, 'outcome': outcome, 'checks': [], 'conversations': [conv], 'ops': ops}
        (out / 'result.json').write_text(json.dumps(row))
        return row

    monkeypatch.setattr(stack, 'run_one', run_one)
    return convs, seen


def compare_cli(tmp_path, *args):
    return cli.main(
        ['scenario', 'compare', *args, '--scenario', 'finish_single_recording_fast', '--keep', str(tmp_path / 'c')]
    )


def test_n_arms_on_one_tree_differ_by_env_and_compare_with_the_baseline(tmp_path, arm_runs, capsys):
    convs, seen = arm_runs
    convs['hi'] = {**CONV, 'visible': False, 'hidden_reason': 'too_short'}
    code = compare_cli(
        tmp_path,
        '--arm',
        'lo',
        '--arm',
        '{"name": "mid", "env": {"CONVERSATIONS_V3_WORD_FLOOR": "8"}}',
        '--arm',
        '{"name": "hi", "env": {"CONVERSATIONS_V3_WORD_FLOOR": "30"}}',
        '--json',
    )
    assert code == 1  # hi differs from lo
    out = tmp_path / 'c'
    report = json.loads((out / 'compare.json').read_text())
    assert report['schema'] == compare.SCHEMA and report['baseline'] == 'lo'
    assert [a['name'] for a in report['arms']] == ['lo', 'mid', 'hi']
    assert report['arms'][2]['env'] == {'CONVERSATIONS_V3_WORD_FLOOR': '30'}
    (row,) = report['scenarios']
    assert row['outcomes'] == {'lo': 'passed', 'mid': 'passed', 'hi': 'passed'}
    assert not row['arms']['mid']['differs'] and row['arms']['hi']['differs']
    assert row['arms']['hi']['conversations'][0]['fields'] == ['hidden_reason', 'visible']
    # The arm with no env runs exactly as today; the others pass their overlay to each scenario process.
    assert seen['lo'] == [['--stt', 'replay']]
    flag, path = seen['hi'][0][2:]
    assert flag == '--arm-overlay' and json.loads(open(path).read())['env'] == {'CONVERSATIONS_V3_WORD_FLOOR': '30'}
    for arm in ('lo', 'mid', 'hi'):
        assert (out / arm / 'verdict.json').exists()
    # The built-in metrics: a table per arm and deltas against the baseline.
    metrics = report['metrics']
    assert {'ops', 'outcomes'} <= set(metrics['extractors'])
    assert metrics['values']['lo']['ops.reads'] == 12 and metrics['values']['mid']['ops.reads'] == 13
    assert metrics['deltas']['mid']['ops.reads'] == 1 and metrics['deltas']['hi']['ops.writes'] == 0
    assert 'lo' not in metrics['deltas'] and metrics['errors'] == {}


def test_baseline_flag_picks_the_arm_compared_against(tmp_path, arm_runs, capsys):
    convs, _ = arm_runs
    convs['b'] = {**CONV, 'words': 1}
    assert compare_cli(tmp_path, '--arm', 'a', '--arm', 'b', '--arm', 'c', '--baseline', 'b') == 1
    report = json.loads((tmp_path / 'c' / 'compare.json').read_text())
    assert report['baseline'] == 'b' and set(report['scenarios'][0]['arms']) == {'a', 'c'}
    text = capsys.readouterr().out
    assert 'a vs b: conversation A+F: words' in text and 'metrics (' in text


def test_an_erroring_arm_exits_two(tmp_path, arm_runs, capsys):
    convs, _ = arm_runs
    convs['b'] = 'error'
    assert compare_cli(tmp_path, '--arm', 'a', '--arm', 'b') == 2


def test_compare_cli_refuses_mixed_forms(tmp_path, arm_runs, capsys):
    assert compare_cli(tmp_path, 'main', '--arm', 'a', '--arm', 'b') == 2
    assert compare_cli(tmp_path, '--arm', 'a') == 2  # one arm
    assert compare_cli(tmp_path, 'main', '--baseline', 'base') == 2
    assert compare_cli(tmp_path) == 2  # nothing to compare
    (tmp_path / 'arms.json').write_text('[{"name": "a"}, {"name": "b"}]')
    assert compare_cli(tmp_path, '--arms', str(tmp_path / 'arms.json'), '--arm', 'c') == 2


# ---- the metric registry -----------------------------------------------------------------------------


@pytest.fixture
def scratch_metric():
    from testing.pipeline_lab.scenario import metrics

    names = []

    def add(name, fn):
        metrics.register_metric(name, fn)
        names.append(name)

    yield add
    for name in names:
        metrics.unregister_metric(name)


def test_a_registered_metric_reaches_the_report_without_touching_compare(tmp_path, arm_runs, scratch_metric, capsys):
    from testing.pipeline_lab.scenario import metrics

    def lengths(run_dir):
        return {'name_len': len(run_dir.name), 'mode': 'long' if len(run_dir.name) > 2 else 'short'}

    scratch_metric('scratch', lengths)
    assert compare_cli(tmp_path, '--arm', 'ab', '--arm', 'abcd', '--metric', 'scratch') == 0
    report = json.loads((tmp_path / 'c' / 'compare.json').read_text())
    assert report['metrics']['extractors'] == ['scratch']
    assert report['metrics']['values'] == {
        'ab': {'scratch.mode': 'short', 'scratch.name_len': 2},
        'abcd': {'scratch.mode': 'long', 'scratch.name_len': 4},
    }
    assert report['metrics']['deltas'] == {'abcd': {'scratch.mode': 'changed', 'scratch.name_len': 2}}
    text = capsys.readouterr().out
    assert 'scratch.name_len' in text and '4 (+2)' in text
    assert metrics.delta(1.5, 1.25) == -0.25 and metrics.delta('a', 1) is None and metrics.delta(None, 1) is None


def test_a_failing_or_malformed_metric_exits_two(tmp_path, arm_runs, scratch_metric, capsys):
    def boom(run_dir):
        raise RuntimeError('no speakers file')

    scratch_metric('boom', boom)
    assert compare_cli(tmp_path, '--arm', 'a', '--arm', 'b', '--metric', 'boom') == 2
    report = json.loads((tmp_path / 'c' / 'compare.json').read_text())
    assert report['errored'] and report['metrics']['errors']['a']['boom'].startswith('RuntimeError')
    scratch_metric('text', lambda run_dir: {'title': 'x' * 200})  # text, not a label
    scratch_metric('flag', lambda run_dir: {'on': True})
    for name in ('text', 'flag'):
        assert compare_cli(tmp_path, '--arm', 'a', '--arm', 'b', '--metric', name) == 2
    assert compare_cli(tmp_path, '--arm', 'a', '--arm', 'b', '--metric', 'not_registered') == 2


def test_metric_registration_rules():
    from testing.pipeline_lab.scenario import metrics

    with pytest.raises(metrics.MetricError):
        metrics.register_metric('ops', lambda run_dir: {})  # taken by the built-in
    with pytest.raises(metrics.MetricError):
        metrics.register_metric('a.b', lambda run_dir: {})


def test_metric_modules_are_discovered_by_file_name_and_env(tmp_path):
    from testing.pipeline_lab.scenario import metrics

    (tmp_path / 'speakers').mkdir()
    (tmp_path / 'speakers' / 'compare_metrics.py').write_text('')
    (tmp_path / 'scenario' / 'deep').mkdir(parents=True)
    (tmp_path / 'scenario' / 'deep' / 'compare_metrics.py').write_text('')
    (tmp_path / 'speakers' / 'metrics.py').write_text('')  # not the convention: not imported
    found = metrics.metric_modules({metrics.METRICS_ENV: 'my.module, '}, lab_dir=tmp_path)
    assert found == [
        'testing.pipeline_lab.scenario.deep.compare_metrics',
        'testing.pipeline_lab.speakers.compare_metrics',
        'my.module',
    ]
    with pytest.raises(metrics.MetricError):
        metrics.load_metric_modules(['testing.pipeline_lab.no_such_metrics_module'])


# ---- the harness report ----------------------------------------------------------------------------


def git_repo(tmp_path):
    import subprocess

    repo = tmp_path / 'repo'
    lab = repo / compare.HARNESS
    (lab / 'scenario' / 'scenarios').mkdir(parents=True)
    (lab / 'scenario' / 'scenarios' / 's.json').write_text('{"budget": {"reads": 10}}')
    (lab / 'scenario' / 'checks.py').write_text('STRICT = True\n')

    def run(*args):
        return subprocess.run(
            ['git', '-c', 'user.name=t', '-c', 'user.email=t@example.com', *args],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    run('init', '-q')
    run('add', '-A')
    run('commit', '-qm', 'one')
    return repo, lab, run


def test_harness_report_flags_a_ref_whose_harness_differs_from_the_one_that_ran(tmp_path):
    repo, lab, run = git_repo(tmp_path)
    old = run('rev-parse', 'HEAD')
    (lab / 'scenario' / 'scenarios' / 's.json').write_text('{"budget": {"reads": 99}}')  # a weaker budget
    run('commit', '-qam', 'two')
    (lab / 'scenario' / 'scenarios' / 'new.json').write_text('{}')  # untracked: it runs too
    identities = {
        'base': {'ref': 'main~1', 'sha': old, 'ref_given': True},
        'head': {'ref': 'worktree', 'sha': run('rev-parse', 'HEAD'), 'ref_given': False},
    }
    report = compare.harness_report(repo, identities, ['base', 'head'], 'base')
    assert report['drift'] and report['refs_differ'] and report['ran']['dirty']
    assert report['arms']['base']['changed'] == {
        'scenarios': ['scenario/scenarios/new.json', 'scenario/scenarios/s.json']
    }
    assert not report['arms']['base']['same_as_ran'] and report['arms']['head']['same_as_ran']
    assert not report['arms']['head']['same_as_baseline']
    lines = '\n'.join(compare.harness_lines(report))
    assert "every arm ran this checkout's" in lines and 'WARNING: arm base (main~1)' in lines
    assert 'scenarios: scenario/scenarios/new.json' in lines

    # The same commit on both arms, nothing modified: no drift, no warning.
    (lab / 'scenario' / 'scenarios' / 'new.json').unlink()
    head = run('rev-parse', 'HEAD')
    same = {name: {'ref': name, 'sha': head, 'ref_given': True} for name in ('a', 'b')}
    report = compare.harness_report(repo, same, ['a', 'b'], 'a')
    assert not report['drift'] and not report['refs_differ']
    assert 'WARNING' not in '\n'.join(compare.harness_lines(report))


def test_harness_report_degrades_to_a_warning_outside_git(tmp_path):
    report = compare.harness_report(tmp_path, {'a': {'ref_given': False}, 'b': {'ref_given': False}}, ['a', 'b'], 'a')
    assert report['drift'] is None and 'error' in report
    assert compare.harness_lines(report)[0].startswith('  WARNING: harness check failed')


def test_an_arm_overlay_lands_on_top_of_the_scenario_env(monkeypatch):
    from testing.pipeline_lab.scenario.run import scenario_overlay
    from testing.pipeline_lab.scenario.spec import load_scenario
    from testing.pipeline_lab.stack import runtime_env

    # The production profile itself is not under test (parsing it costs seconds): a small stand-in.
    profile = {'name': 'prod', 'env': {'PROFILE_FLAG': 'on'}, 'serving': {'PROFILE_SERVE': True}}
    monkeypatch.setattr(runtime_env, 'overlay_from_runtime_env', lambda *a, **k: (dict(profile), {}))
    scenario = load_scenario(stack.SCENARIO_DIR / 'finish_single_recording_fast.json')
    plain = scenario_overlay(scenario)
    arm = {'name': 'hi', 'env': {'PIPELINE_LAB_ARM_PROBE': '30'}, 'serving': {'PIPELINE_LAB_PROBE': True}}
    applied = scenario_overlay(scenario, arm=arm)
    assert applied.env == {**plain.env, 'PIPELINE_LAB_ARM_PROBE': '30'}
    assert applied.serving == {'PROFILE_SERVE': True, 'PIPELINE_LAB_PROBE': True}
    assert applied.name.endswith('+hi')
    # The arm's env wins over the profile's and the scenario's own (a sweep overrides what they pin).
    for pinned in ('PROFILE_FLAG', 'CONVERSATIONS_V3_FAST_FINISH'):
        assert scenario_overlay(scenario, arm={'name': 'x', 'env': {pinned: 'arm'}}).env[pinned] == 'arm'
