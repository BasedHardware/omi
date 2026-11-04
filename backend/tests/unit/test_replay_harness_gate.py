"""Fast differential-gate contracts; no emulator or product imports."""

from contextlib import contextmanager
from dataclasses import replace
import json
from pathlib import Path

import jsonschema
import pytest

from testing.replay_harness import gate
from testing.replay_harness.manifest import JSON_SCHEMA, load_case, validate_manifest
from testing.replay_harness.report import StageResult, item_report

FIXTURES = Path(__file__).resolve().parents[2] / 'testing/replay_harness/fixtures'


def outcome(status='stopped', stage='admission', reason='expected', **kwargs):
    return {'stages': [vars(StageResult(stage, status, reason=reason if status != 'pass' else None, **kwargs))]}


@pytest.fixture
def case():
    value = load_case(FIXTURES / 'admission-not-durable')
    manifest = replace(
        value.manifest, stages={'admission': {'expect_stop_stage': 'admission', 'expect_reason': '^expected$'}}
    )
    return replace(value, manifest=manifest)


@pytest.mark.parametrize(
    'before,after,classification',
    [
        (outcome(), outcome('pass'), 'fixed'),
        (outcome(), outcome(), 'still_failing'),
        (outcome('pass'), outcome(), 'regressed'),
        (outcome(), outcome(reason='different'), 'changed_reason'),
        (outcome(), outcome(stage='titling'), 'changed_reason'),
        (outcome('pass'), outcome('pass'), 'unchanged_pass'),
        (outcome(reason='unexpected'), outcome('pass'), 'changed_reason'),
    ],
)
def test_classification_table(case, before, after, classification):
    assert gate.classify(before, after, case.manifest) == classification


def test_fix_passes_expected_stage_even_if_later_stage_stops(case):
    after = {'stages': outcome('pass')['stages'] + outcome(stage='titling')['stages']}
    assert gate.classify(outcome(), after, case.manifest) == 'fixed'


def test_expected_reason_uses_runner_static_alias():
    case = load_case(FIXTURES / 'admission-not-durable')
    before = outcome(
        reason='admission:ValueError:utils.batch_pipeline.live.admit_recording:retained_capture_not_durable'
    )
    assert gate.classify(before, outcome('pass'), case.manifest) == 'fixed'


@pytest.mark.parametrize('target', [False, True])
@pytest.mark.parametrize(
    'before,after', [('stopped', 'stopped'), ('stopped', 'pass'), ('pass', 'stopped'), ('pass', 'pass')]
)
def test_verdict_rules(case, target, before, after):
    case = replace(case, manifest=replace(case.manifest, gate={'fixed_by_ref': target}))
    result = gate.compare([case], {'baseline': [[outcome(before)]], 'candidate': [[outcome(after)]]})
    assert (result['verdict'] == 'PASS') == (
        before == 'stopped' and after == 'pass' if target else not (before == 'pass' and after == 'stopped')
    )


def test_new_exception_is_checked_in_every_observation_even_minority(case):
    old = outcome(exception_type='ValueError', site='product.old')
    new = outcome(exception_type='TypeError', site='product.old')
    new['stages'][0]['observations'] = [{'exception_type': 'ValueError', 'site': 'product.new'}]
    result = gate.compare([case], {'baseline': [[old] * 3], 'candidate': [[old, old, new]]})
    assert result['cases'][0]['classification'] == 'still_failing'
    assert result['verdict'] == 'FAIL'
    assert result['new_exception_sites'] == [
        {'exception_type': 'TypeError', 'site': 'product.old'},
        {'exception_type': 'ValueError', 'site': 'product.new'},
    ]


def test_majority_and_no_majority_fail_closed(case):
    before, after = outcome(), outcome('pass')
    assert gate.majority([before, after, after]) == after
    assert gate.majority([before, after]) is None
    result = gate.compare([case], {'baseline': [[before, after]], 'candidate': [[after]]})
    assert result['verdict'] == 'FAIL' and result['cases'][0]['inconclusive']
    assert len(result['cases'][0]['baseline']['outcomes']) == 2


@pytest.mark.parametrize('status', ['not_implemented', 'invalid'])
def test_incomplete_replay_fails(case, status):
    result = gate.compare([case], {'baseline': [[outcome(status)]], 'candidate': [[outcome(status)]]})
    assert result['verdict'] == 'FAIL'


@pytest.mark.parametrize('block', [{}, {'fixed_by_ref': True}, {'fixed_by_ref': False}])
def test_gate_manifest_v1_roundtrip(block):
    value = load_case(FIXTURES / 'admission-not-durable').manifest.to_dict()
    value['gate'] = block
    jsonschema.Draft202012Validator(JSON_SCHEMA).validate(value)
    assert validate_manifest(value).to_dict() == value


@pytest.mark.parametrize('block', [None, [], True, {'fixed_by_ref': 1}, {'fixed_by_ref': 'true'}, {'unknown': True}])
def test_gate_manifest_validation(block):
    value = load_case(FIXTURES / 'admission-not-durable').manifest.to_dict()
    value['gate'] = block
    with pytest.raises(ValueError, match='gate'):
        validate_manifest(value)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(JSON_SCHEMA).validate(value)


def test_target_requires_expected_stop():
    value = load_case(FIXTURES / 'admission-control').manifest.to_dict()
    value['gate'] = {'fixed_by_ref': True}
    with pytest.raises(ValueError, match='expected failing stop'):
        validate_manifest(value)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(JSON_SCHEMA).validate(value)


def test_digest_stability_and_sensitivity(tmp_path):
    root = tmp_path / 'one'
    root.mkdir()
    (root / 'manifest.json').write_text('{}')
    (root / 'corpus.json').write_text('{}')
    case = type('Case', (), {'directory': root})()
    first = gate.case_digest(case)
    relocated = tmp_path / 'two'
    root.rename(relocated)
    case.directory = relocated
    assert gate.case_digest(case) == first
    (relocated / 'corpus.json').write_text('{"changed": true}')
    assert gate.case_digest(case) != first
    second = gate.case_digest(case)
    (relocated / 'cassettes').mkdir()
    (relocated / 'cassettes/one').write_text('ciphertext')
    assert gate.case_digest(case) != second
    assert gate.digest_files(
        [('a', relocated / 'manifest.json'), ('b', relocated / 'corpus.json')]
    ) == gate.digest_files([('b', relocated / 'corpus.json'), ('a', relocated / 'manifest.json')])


def test_repetition_detects_shape_not_case_name(case):
    assert gate.repeats_for(case, 5) == 1
    assert gate.repeats_for(replace(case, corpus={'admission': {'drainers': 8}}), 5) == 5


def test_tier_c_privacy_canary(tmp_path, monkeypatch, capsys):
    from testing.replay_harness import gate_worker
    import asyncio

    private_id, private_text = 'CUSTOMER-CANARY-ID', 'Private customer transcript text CANARY'
    directory = tmp_path / private_id
    directory.mkdir()
    value = load_case(FIXTURES / 'admission-control').manifest.to_dict()
    value.update(id=private_id, tier='C', scrub=private_text, notes=private_text, prod_evidence={'text': private_text})
    (directory / 'manifest.json').write_text(json.dumps(value))
    (directory / 'corpus.json').write_text(json.dumps({'text': private_text}))
    case = load_case(directory)
    raw_item = item_report(case.manifest, [StageResult('admission', 'pass')])

    async def fake_run_cases(_):
        return [raw_item]

    from testing.replay_harness import runner

    monkeypatch.setattr(runner, 'run_cases', fake_run_cases)
    sanitized = asyncio.run(gate_worker.replay([{'path': str(directory), 'repeats': 1}]))
    assert private_id not in json.dumps(sanitized) and private_text not in json.dumps(sanitized)

    @contextmanager
    def snapshot(*_):
        yield tmp_path

    monkeypatch.setattr(gate, 'backend_snapshot', snapshot)
    monkeypatch.setattr(gate, 'resolve_refs', lambda *_: {'candidate': 'a' * 40, 'baseline': 'b' * 40})
    monkeypatch.setattr(gate, 'run_side', lambda *_: sanitized)
    monkeypatch.setattr(gate, 'adapter_digest', lambda: 'c' * 64)
    output = tmp_path / 'output'
    assert gate.gate(tmp_path, [directory], 'REF', 'BASE', output) == 0
    exposed = ''.join(p.read_text() for p in output.rglob('*') if p.is_file()) + capsys.readouterr().out
    assert private_id not in exposed and private_text not in exposed
    assert set(p.name for p in output.iterdir()) == {'gate.json', 'gate.md'}


def test_cli_error_does_not_print_path_or_manifest_content(tmp_path, capsys):
    assert (
        gate.main(['--case', str(tmp_path / 'PRIVATE-ID'), '--ref', 'bad', '--base', 'bad', '--output', str(tmp_path)])
        == 2
    )
    assert capsys.readouterr().out == 'Replay gate: ERROR (FileNotFoundError)\n'


def test_worker_pins_adapter_while_product_imports_come_from_snapshot(tmp_path):
    import subprocess
    import sys

    worker = Path(gate.__file__).with_name('gate_worker.py')
    (tmp_path / 'testing').mkdir()
    (tmp_path / 'testing/__init__.py').write_text('raise AssertionError("snapshot adapter loaded")')
    (tmp_path / 'product_probe.py').write_text('PROBE = "snapshot-product"')
    program = (
        'import importlib.util, pathlib; '
        f'spec = importlib.util.spec_from_file_location("worker", {str(worker)!r}); '
        'worker = importlib.util.module_from_spec(spec); spec.loader.exec_module(worker); '
        f'worker.configure_imports(pathlib.Path({str(tmp_path)!r})); '
        'import testing.replay_harness.runner, product_probe; '
        f'assert pathlib.Path(testing.replay_harness.runner.__file__).parent == pathlib.Path({str(worker.parent)!r}); '
        'assert product_probe.PROBE == "snapshot-product"'
    )
    subprocess.run([sys.executable, '-I', '-c', program], check=True, capture_output=True, timeout=10)


def test_snapshot_archive_is_immutable_and_removed_on_error(tmp_path):
    import subprocess
    from testing.replay_snapshot import backend_snapshot, resolve_refs

    repo = tmp_path / 'repo'
    repo.mkdir()
    subprocess.run(['git', 'init', '--quiet', str(repo)], check=True)
    (repo / 'backend').mkdir()
    source = repo / 'backend/product.py'
    source.write_text('original product')
    subprocess.run(['git', '-C', str(repo), 'add', 'backend'], check=True)
    subprocess.run(
        [
            'git',
            '-C',
            str(repo),
            '-c',
            'user.name=Replay unit',
            '-c',
            'user.email=replay@example.invalid',
            'commit',
            '--quiet',
            '-m',
            'fixture',
        ],
        check=True,
    )
    sha = resolve_refs(repo, 'HEAD', 'HEAD')['candidate']
    source.write_text('uncommitted product')
    output = tmp_path / 'out'
    output.mkdir()
    with pytest.raises(RuntimeError):
        with backend_snapshot(repo, sha, output, 'test') as backend:
            assert (backend / 'product.py').read_text() == 'original product'
            raise RuntimeError('synthetic runner error')
    assert not list(output.iterdir())
    assert source.read_text() == 'uncommitted product'
    assert resolve_refs(repo, 'HEAD', 'HEAD')['candidate'] == sha
