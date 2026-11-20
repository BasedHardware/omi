"""Pipeline-lab CLI and run orchestration with fake stage drivers. Synthetic only."""

import json

import pytest

from testing.pipeline_lab import cli, orchestrator
from testing.pipeline_lab import contracts as c
from testing.pipeline_lab.ledger import SpendCapReached
from testing.pipeline_lab.registry import DriverNotRegistered, Registry, StageResult, load_plugins
from testing.pipeline_lab.store import Store

TREE = 'f' * 40


class FakeDriver:
    def __init__(self, stage, calls, *, cacheable=True, fail=None, salt=''):
        self.stage = stage
        self.calls = calls
        self.cacheable = cacheable
        self.fail = fail
        self.salt = salt
        self.restored = []

    def inputs(self, ctx):
        return {'salt': self.salt} if self.salt else {}

    def run(self, ctx):
        self.calls.append(self.stage)
        if self.fail == 'spend':
            ctx.ledger.reserve(ctx.ledger.budget_usd + 1)
        if self.fail == 'boom':
            raise RuntimeError('synthetic failure')
        ctx.decision(f'{self.stage}_mode', 'serve', 'test')
        if self.stage == 'notes':
            ctx.store.write_conversation(ctx.run_id, c.ConversationRecord(id='conv-1', started_at='t'))
        return StageResult(output={'stage': self.stage, 'upstream': sorted(ctx.upstream)}, cache_misses=1)

    def restore(self, ctx, output):
        self.restored.append(output)


def registry_with(stages, calls, **kwargs):
    registry = Registry()
    drivers = {}
    for stage in stages:
        drivers[stage] = FakeDriver(stage, calls, **kwargs.get(stage, {}))
        registry.add_stage(drivers[stage])
    return registry, drivers


@pytest.fixture
def lab(tmp_path):
    store = Store.open(tmp_path / 'root', tmp_path / 'verdicts')
    store.write_day(c.CorpusDay(day_id='d1', date='2026-01-15', timezone='UTC', start_state_snapshot='synthetic'))
    return store


CHAIN = ['discard', 'notes', 'memories']


def _request(**kwargs):
    return orchestrator.RunRequest(day_id='d1', ref='main', stages=CHAIN, **kwargs)


def test_run_walks_stages_in_order_and_records_status(lab):
    calls = []
    registry, _ = registry_with(['memories', 'notes', 'discard'], calls)
    outcome = orchestrator.run_pipeline(lab, _request(), registry, backend_tree=TREE)
    assert outcome.exit_code == 0
    assert calls == CHAIN
    run = lab.read_run(outcome.run.run_id)
    assert run.status == 'complete' and run.finished_at and run.backend_tree == TREE
    assert [run.stages[s].status for s in CHAIN] == ['complete'] * 3
    assert set(run.timings) == set(CHAIN)
    assert run.start_state == 'approximate'
    assert [d.name for d in lab.read_decisions(run.run_id)] == ['discard_mode', 'notes_mode', 'memories_mode']


def test_second_run_is_served_from_the_stage_cache(lab):
    calls = []
    registry, drivers = registry_with(CHAIN, calls)
    orchestrator.run_pipeline(lab, _request(), registry, backend_tree=TREE)
    calls.clear()
    outcome = orchestrator.run_pipeline(lab, _request(), registry, backend_tree=TREE)
    assert calls == []
    run = lab.read_run(outcome.run.run_id)
    assert [run.stages[s].status for s in CHAIN] == ['cached'] * 3
    assert run.stages['notes'].cache_hits == 1
    assert drivers['notes'].restored == [{'stage': 'notes', 'upstream': ['discard']}]


def test_from_stage_reruns_that_stage_and_after(lab):
    calls = []
    registry, _ = registry_with(CHAIN, calls)
    orchestrator.run_pipeline(lab, _request(), registry, backend_tree=TREE)
    calls.clear()
    orchestrator.run_pipeline(lab, _request(from_stage='notes'), registry, backend_tree=TREE)
    assert calls == ['notes', 'memories']


def test_upstream_change_invalidates_downstream_only(lab):
    calls = []
    registry, _ = registry_with(CHAIN, calls)
    orchestrator.run_pipeline(lab, _request(), registry, backend_tree=TREE)
    calls.clear()
    registry2, _ = registry_with(CHAIN, calls, notes={'salt': 'new prompt'})
    orchestrator.run_pipeline(lab, _request(), registry2, backend_tree=TREE)
    # notes' own input changed; its output is identical, so memories' key is unchanged.
    assert calls == ['notes']
    calls.clear()
    orchestrator.run_pipeline(lab, _request(), registry, backend_tree='e' * 40)
    assert calls == CHAIN  # a different backend tree invalidates everything


def test_overlay_change_invalidates_and_secrets_are_redacted(lab):
    calls = []
    registry, _ = registry_with(CHAIN, calls)
    orchestrator.run_pipeline(lab, _request(), registry, backend_tree=TREE)
    calls.clear()
    overlay = {
        'env': {'NOTES_MODE': 'shadow', 'OMI_LLM_GATEWAY_SERVICE_TOKEN': 'not-a-real-token'},
        'serving': {'NOTES': True},
    }
    outcome = orchestrator.run_pipeline(lab, _request(overlay=overlay), registry, backend_tree=TREE)
    assert calls == CHAIN
    run = lab.read_run(outcome.run.run_id)
    assert run.overlay['env']['NOTES_MODE'] == 'shadow'
    assert run.overlay['env']['OMI_LLM_GATEWAY_SERVICE_TOKEN'].startswith('redacted:')
    assert 'not-a-real-token' not in (lab.run_dir(run.run_id) / 'run.json').read_text()
    assert run.overlay['serving'] == {'NOTES': True}


def test_overlay_uses_one_schema(lab):
    registry, _ = registry_with(CHAIN, [])
    with pytest.raises(ValueError, match='serving'):
        orchestrator.run_pipeline(lab, _request(overlay={'pins': {'notes': 'all'}}), registry, backend_tree=TREE)
    with pytest.raises(ValueError, match='serving'):
        orchestrator.run_pipeline(
            lab, _request(overlay={'env': {'NOTES_SERVE_PERCENT': '100'}}), registry, backend_tree=TREE
        )


def test_from_stage_skips_uncached_earlier_stages(lab):
    calls = []
    registry, _ = registry_with(CHAIN, calls)
    outcome = orchestrator.run_pipeline(lab, _request(from_stage=CHAIN[1]), registry, backend_tree=TREE)
    assert calls == CHAIN[1:]
    assert outcome.run.stages[CHAIN[0]].status == 'skipped'
    assert outcome.exit_code == 0


def test_uncacheable_driver_always_runs(lab):
    calls = []
    registry, _ = registry_with(CHAIN, calls, notes={'cacheable': False})
    orchestrator.run_pipeline(lab, _request(), registry, backend_tree=TREE)
    calls.clear()
    orchestrator.run_pipeline(lab, _request(), registry, backend_tree=TREE)
    assert calls == ['notes']


def test_missing_driver_fails_before_creating_a_run(lab):
    calls = []
    registry, _ = registry_with(['discard'], calls)
    with pytest.raises(DriverNotRegistered, match='stage driver not registered: notes, memories'):
        orchestrator.run_pipeline(lab, _request(), registry, backend_tree=TREE)
    assert lab.list_runs() == []
    outcome = orchestrator.run_pipeline(lab, _request(allow_missing=True), registry, backend_tree=TREE)
    assert outcome.exit_code == 0
    assert outcome.run.stages['notes'].status == 'not_registered'


def test_spend_stop_and_failure_exit_codes(lab):
    calls = []
    registry, _ = registry_with(CHAIN, calls, notes={'fail': 'spend'})
    outcome = orchestrator.run_pipeline(lab, _request(), registry, backend_tree=TREE)
    assert outcome.exit_code == orchestrator.EXIT_SPEND
    assert lab.read_run(outcome.run.run_id).status == 'stopped'
    assert calls == ['discard', 'notes']

    calls.clear()
    registry, _ = registry_with(CHAIN, calls, notes={'fail': 'boom'})
    outcome = orchestrator.run_pipeline(lab, _request(no_cache=True), registry, backend_tree=TREE)
    assert outcome.exit_code == orchestrator.EXIT_ERROR
    run = lab.read_run(outcome.run.run_id)
    assert run.status == 'failed' and run.stages['notes'].status == 'failed'
    assert 'synthetic failure' in (lab.run_dir(run.run_id) / 'errors.log').read_text()


def test_spend_cap_reached_is_exported():
    assert issubclass(SpendCapReached, Exception)


# ---- CLI -----------------------------------------------------------------------------


def run_cli(lab, *argv, registry=None):
    return cli.main(
        ['--root', str(lab.root), '--verdicts', str(lab.verdicts_root), *argv], registry=registry or Registry()
    )


def test_cli_sample_run_list_show_and_verdicts(lab, capsys):
    assert run_cli(lab, 'sample-run', '--json') == 0
    sample = json.loads(capsys.readouterr().out)
    run_id = sample['run_id']

    assert run_cli(lab, 'corpus', 'list', '--json') == 0
    assert {d['day_id'] for d in json.loads(capsys.readouterr().out)} == {'d1', 'sample-day'}

    assert run_cli(lab, 'runs', '--json') == 0
    assert json.loads(capsys.readouterr().out)[0]['run_id'] == run_id

    assert run_cli(lab, 'show', run_id, '--json', '--calls') == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown['conversations']['total'] == 3 and shown['conversations']['discarded'] == 1
    assert shown['llm_calls']['total'] == 3 and len(shown['calls']) == 3
    assert shown['day']['daily_summary']

    conv = lab.read_conversation(run_id, 'sample-c0')
    key = conv.action_items[0].key
    assert (
        run_cli(
            lab,
            'verdicts',
            'add',
            '--run',
            run_id,
            '--conversation',
            'sample-c0',
            '--kind',
            'task',
            '--key',
            key,
            '--mark',
            'good',
            '--json',
        )
        == 0
    )
    capsys.readouterr()
    assert (
        run_cli(
            lab,
            'verdicts',
            'add',
            '--run',
            run_id,
            '--conversation',
            'sample-c0',
            '--kind',
            'task',
            '--key',
            key,
            '--mark',
            'bad',
            '--note',
            'wrong',
            '--json',
        )
        == 0
    )
    capsys.readouterr()
    assert run_cli(lab, 'verdicts', 'list', '--json', '--latest') == 0
    latest = json.loads(capsys.readouterr().out)
    assert [(v['mark'], v['note']) for v in latest] == [('bad', 'wrong')]
    assert run_cli(lab, 'verdicts', 'export') == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 2 and json.loads(lines[0])['item_key'] == key


def test_cli_verdict_export_refuses_git_paths(lab, tmp_path, capsys):
    (tmp_path / 'repo' / '.git').mkdir(parents=True)
    assert run_cli(lab, 'verdicts', 'export', '--out', str(tmp_path / 'repo' / 'v.jsonl'), '--json') == 2
    assert 'outside every git worktree' in json.loads(capsys.readouterr().out)['error']
    assert run_cli(lab, 'verdicts', 'export', '--format', 'json', '--out', str(tmp_path / 'v.json'), '--json') == 0
    assert json.loads((tmp_path / 'v.json').read_text()) == []


@pytest.mark.parametrize(
    'argv, name',
    [
        (['corpus', 'add-day', '--snapshot', 'x'], 'corpus-add-day'),
        (['record-stt'], 'record-stt'),
        (['serve', '--port', '0'], 'serve'),
    ],
)
def test_cli_foreign_engines_fail_clearly_until_registered(lab, capsys, argv, name):
    assert run_cli(lab, *argv, '--json') == 2
    error = json.loads(capsys.readouterr().out)
    assert error['kind'] == 'DriverNotRegistered' and f'tool not registered: {name}' in error['error']


def test_cli_dispatches_to_a_registered_tool(lab, capsys):
    registry = Registry()
    seen = {}

    def add_day(ctx):
        seen['argv'] = ctx.argv
        return {'added': 'd2'}

    registry.add_tool('corpus-add-day', add_day)
    assert run_cli(lab, 'corpus', 'add-day', '--snapshot', 'label', '--json', registry=registry) == 0
    assert json.loads(capsys.readouterr().out) == {'added': 'd2'}
    assert seen['argv'] == ['--snapshot', 'label']


def test_cli_run_without_drivers_names_the_missing_stages(lab, capsys):
    assert run_cli(lab, 'run', '--day', 'd1', '--ref', 'HEAD', '--json') == 2
    error = json.loads(capsys.readouterr().out)
    assert 'stage driver not registered: ingest, transcribe' in error['error']


def test_cli_stages_and_doctor(lab, capsys):
    calls = []
    registry, _ = registry_with(['notes'], calls)
    assert run_cli(lab, 'stages', '--json', registry=registry) == 0
    described = json.loads(capsys.readouterr().out)
    assert list(described['stages']) == list(c.STAGES)
    assert described['stages']['notes'] == 'FakeDriver' and described['stages']['ingest'] is None
    assert run_cli(lab, '--json', 'doctor', registry=registry) == 0
    assert json.loads(capsys.readouterr().out)['root'] == str(lab.root)


def test_plugin_loading_skips_absent_lanes_and_surfaces_broken_ones(tmp_path, monkeypatch):
    registry = load_plugins(Registry(), ['testing.pipeline_lab.no_such_lane.plugin'])
    assert registry.plugins == []
    package = tmp_path / 'labplugin_fixture'
    package.mkdir()
    (package / '__init__.py').write_text('')
    (package / 'good.py').write_text(
        'class D:\n    stage = "goals"\n    def run(self, ctx):\n        return None\n'
        'def register(registry):\n    registry.add_stage(D())\n'
    )
    (package / 'broken.py').write_text('import labplugin_missing_dependency\n')
    monkeypatch.syspath_prepend(str(tmp_path))
    registry = load_plugins(Registry(), ['labplugin_fixture.good'])
    assert 'goals' in registry.stages and registry.plugins == ['labplugin_fixture.good']
    with pytest.raises(ModuleNotFoundError):
        load_plugins(Registry(), ['labplugin_fixture.broken'])


def test_a_proxy_that_cannot_start_leaves_the_run_failed_not_running(lab):
    registry, _ = registry_with(CHAIN, [])
    with pytest.raises(ValueError):
        orchestrator.run_pipeline(lab, _request(llm_upstream='http://gateway.example'), registry, backend_tree=TREE)
    (run,) = lab.list_runs('d1')
    assert run.status == c.RunStatus.FAILED.value and run.finished_at
