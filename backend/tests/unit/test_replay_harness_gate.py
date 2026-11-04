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
    expected = 'PASS' if target and before == 'stopped' and after == 'pass' else 'FAIL'
    if not target and not (before == 'pass' and after == 'stopped'):
        expected = 'REGRESSION_ONLY'
    assert result['verdict'] == expected


def test_new_exception_is_checked_in_every_observation_even_minority(case):
    old = outcome(exception_type='ValueError', site='product.old')
    new = outcome(exception_type='TypeError', site='product.old')
    new['stages'][0]['observations'] = [{'exception_type': 'ValueError', 'site': 'product.new'}]
    case = replace(case, corpus={'admission': {'drainers': 8}})
    result = gate.compare([case], {'baseline': [[old] * 3], 'candidate': [[old, old, new]]})
    assert result['cases'][0]['classification'] == 'still_failing'
    assert result['verdict'] == 'FAIL'
    assert result['new_exception_sites'] == [
        {'exception_type': 'TypeError', 'site': 'product.old'},
        {'exception_type': 'ValueError', 'site': 'product.new'},
    ]


@pytest.mark.parametrize('mixed_side', ['baseline', 'candidate', 'both'])
def test_mixed_stress_outcomes_are_unstable_not_regressions(case, mixed_side):
    case = replace(case, corpus={'admission': {'drainers': 8}})
    before, after = outcome(), outcome('pass')
    assert gate.unanimous([before, after, after]) is None
    assert gate.unanimous([before] * 3) == before
    reports = {'baseline': [[before] * 3], 'candidate': [[before] * 3]}
    for side in ('baseline', 'candidate'):
        if mixed_side in (side, 'both'):
            reports[side] = [[before, after, after]]
    result = gate.compare([case], reports)
    assert result['cases'][0]['classification'] == 'unstable'
    asymmetric = mixed_side == 'candidate'
    assert result['verdict'] == ('INCONCLUSIVE' if asymmetric else 'REGRESSION_ONLY')
    assert result['cases'][0]['inconclusive'] == asymmetric
    assert gate.exit_code(result['verdict'], regression_only=True) == int(asymmetric)
    assert len(result['cases'][0]['baseline']['outcomes']) == len(result['cases'][0]['candidate']['outcomes']) == 3


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
    sanitized = asyncio.run(gate_worker.replay([{'path': str(directory), 'scopes': [None]}]))
    assert private_id not in json.dumps(sanitized) and private_text not in json.dumps(sanitized)

    @contextmanager
    def snapshot(*_):
        yield tmp_path

    monkeypatch.setattr(gate, 'backend_snapshot', snapshot)
    monkeypatch.setattr(gate, 'resolve_refs', lambda *_: {'candidate': 'a' * 40, 'baseline': 'b' * 40})
    monkeypatch.setattr(gate, 'run_side', lambda *_: sanitized)
    monkeypatch.setattr(gate, 'adapter_digest', lambda: 'c' * 64)
    output = tmp_path / 'output'
    assert gate.gate(tmp_path, [directory], 'REF', 'BASE', output, regression_only=True) == 0
    exposed = (
        ''.join(p.read_text() for p in output.rglob('*') if p.name != 'identity.key' and p.is_file())
        + capsys.readouterr().out
    )
    assert private_id not in exposed and private_text not in exposed
    assert set(p.name for p in output.iterdir()) == {'gate.json', 'gate.md', 'identity.key'}
    import hashlib, hmac, stat

    key = (output / 'identity.key').read_bytes()
    row = json.loads((output / 'gate.json').read_text())['cases'][0]
    assert row['case_id'] == hmac.new(key, private_id.encode(), hashlib.sha256).hexdigest()
    assert 'corpus_sha256' not in row
    assert hashlib.sha256(private_id.encode()).hexdigest() not in exposed
    assert gate.case_digest(case) not in exposed
    other = tmp_path / 'other'
    assert gate.gate(tmp_path, [directory], 'REF', 'BASE', other, regression_only=True) == 0
    assert json.loads((other / 'gate.json').read_text())['cases'][0]['case_id'] != row['case_id']
    for path in output.iterdir():
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


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


@pytest.mark.parametrize(
    'before,after',
    [
        (outcome(stage='titling'), outcome(stage='admission')),
        (outcome(stage='admission'), outcome(stage='titling')),
        (outcome(), outcome(reason='different')),
    ],
)
def test_changed_reason_fails_closed_in_both_directions(case, before, after):
    result = gate.compare([case], {'baseline': [[before]], 'candidate': [[after]]})
    assert result['cases'][0]['classification'] == 'changed_reason'
    assert result['verdict'] == 'FAIL'
    assert gate.exit_code(result['verdict'], regression_only=True) != 0


def test_zero_targets_is_regression_only_with_explicit_exit_opt_in(case):
    result = gate.compare([case], {'baseline': [[outcome()]], 'candidate': [[outcome()]]})
    assert result['verdict'] == 'REGRESSION_ONLY'
    assert gate.exit_code(result['verdict']) != 0
    assert gate.exit_code(result['verdict'], regression_only=True) == 0


@pytest.mark.parametrize('repeats', [1, 2])
def test_low_k_never_passes_ship_or_regression_mode(case, repeats):
    case = replace(
        case, corpus={'admission': {'drainers': 8}}, manifest=replace(case.manifest, gate={'fixed_by_ref': True})
    )
    result = gate.compare(
        [case], {'baseline': [[outcome()] * repeats], 'candidate': [[outcome('pass')] * repeats]}, repeats=repeats
    )
    assert result['verdict'] == 'DIAGNOSTIC'
    assert gate.exit_code(result['verdict']) != 0
    assert gate.exit_code(result['verdict'], regression_only=True) != 0


@pytest.mark.parametrize('mode', [0o755, 0o777, 0o750])
def test_output_refuses_existing_public_directory(tmp_path, mode):
    from testing.replay_harness.gate_resources import prepare_output

    tmp_path.chmod(mode)
    with pytest.raises(ValueError, match='0700'):
        prepare_output(tmp_path)


def test_output_refuses_wrong_owner_and_symlink(tmp_path, monkeypatch):
    from testing.replay_harness import gate_resources

    root = tmp_path / 'private'
    gate_resources.prepare_output(root)
    link = tmp_path / 'link'
    link.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError):
        gate_resources.prepare_output(link)
    monkeypatch.setattr(gate_resources.os, 'getuid', lambda: -1)
    with pytest.raises(ValueError):
        gate_resources.prepare_output(root)


def test_private_receipt_replaces_symlinks_without_touching_target(tmp_path):
    from testing.replay_harness.gate_resources import private_write
    import stat

    victim = tmp_path / 'victim'
    victim.write_text('unchanged')
    receipt = tmp_path / 'gate.json'
    receipt.symlink_to(victim)
    private_write(receipt, b'private receipt')
    assert victim.read_text() == 'unchanged'
    assert not receipt.is_symlink()
    assert stat.S_IMODE(receipt.stat().st_mode) == 0o600


def test_journal_precedes_commit_and_retains_names_only(tmp_path):
    from types import SimpleNamespace
    from testing.replay_harness.gate_resources import DOCUMENT_PREFIX, journal_writes

    name = DOCUMENT_PREFIX + 'batch_pipeline_test_owned_jobs/unit'
    ledger = tmp_path / 'documents.jsonl'
    calls = []

    def commit(request):
        assert json.loads(ledger.read_text()) == name
        calls.append(request)

    api = SimpleNamespace(commit=commit, batch_write=commit)
    client = SimpleNamespace(_firestore_api=api)
    with journal_writes(client, {'root': str(tmp_path)}):
        request = {'writes': [{'update': {'name': name, 'fields': {'text': 'PRIVATE-PAYLOAD-CANARY'}}}]}
        api.commit(request=request)
        api.batch_write(request=request)
    assert len(calls) == 2
    assert ledger.read_text() == json.dumps(name) + '\n'
    assert 'PRIVATE-PAYLOAD-CANARY' not in ledger.read_text()


def test_parent_cleanup_deletes_only_journaled_documents(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from testing.replay_harness import gate_resources

    scope = tmp_path / 'scope'
    scope.mkdir()
    name = gate_resources.DOCUMENT_PREFIX + 'users/synthetic-owner/conversations/unit'
    (scope / 'documents.jsonl').write_text(json.dumps(name) + '\n')
    requests = []

    def connection(host, port, timeout):
        assert (host, port, timeout) == ('127.0.0.1', 8085, 10)
        return SimpleNamespace(
            request=lambda method, path, headers: requests.append((method, path, headers)),
            getresponse=lambda: SimpleNamespace(status=200),
            close=lambda: None,
        )

    monkeypatch.setattr(gate_resources, 'HTTPConnection', connection)
    gate_resources.cleanup_scopes(tmp_path, '127.0.0.1:8085')
    assert requests == [('DELETE', f'/v1/{name}', {'Authorization': 'Bearer owner'})]
    with pytest.raises(RuntimeError, match='loopback'):
        gate_resources.cleanup_scopes(tmp_path, 'production.invalid:443')
    assert len(requests) == 1


@pytest.mark.parametrize('mixed_side', ['baseline', 'candidate', 'both'])
def test_unstable_target_is_inconclusive(case, mixed_side):
    case = replace(
        case, corpus={'admission': {'drainers': 8}}, manifest=replace(case.manifest, gate={'fixed_by_ref': True})
    )
    reports = {'baseline': [[outcome()] * 5], 'candidate': [[outcome('pass')] * 5]}
    for side in ('baseline', 'candidate'):
        if mixed_side in (side, 'both'):
            reports[side] = [[outcome(), outcome('pass'), outcome(), outcome('pass'), outcome('pass')]]
    result = gate.compare([case], reports, repeats=5)
    assert result['cases'][0]['classification'] == 'unstable'
    assert result['verdict'] == 'INCONCLUSIVE'
    assert gate.exit_code(result['verdict']) != 0
    assert gate.exit_code(result['verdict'], regression_only=True) != 0


@pytest.mark.parametrize('repeats', [1, 2, 3, 4, 5])
def test_stress_target_fix_requires_five_unanimous_runs(case, repeats):
    case = replace(
        case, corpus={'admission': {'drainers': 8}}, manifest=replace(case.manifest, gate={'fixed_by_ref': True})
    )
    result = gate.compare(
        [case], {'baseline': [[outcome()] * repeats], 'candidate': [[outcome('pass')] * repeats]}, repeats=repeats
    )
    assert result['cases'][0]['classification'] == ('fixed' if repeats >= 5 else 'insufficient_repeats')
    assert result['verdict'] == ('PASS' if repeats >= 5 else 'DIAGNOSTIC')


@pytest.mark.parametrize(
    'baseline_mixed,retry_status,classification,verdict',
    [
        (False, 'mixed', 'unstable', 'INCONCLUSIVE'),
        (False, 'stopped', 'still_failing', 'PASS'),
        (False, 'pass', 'unstable', 'INCONCLUSIVE'),
        (True, None, 'unstable', 'PASS'),
    ],
)
def test_asymmetric_stress_retry_in_ship_gate(
    case, tmp_path, monkeypatch, baseline_mixed, retry_status, classification, verdict
):
    target = replace(case, manifest=replace(case.manifest, gate={'fixed_by_ref': True}))
    stress = replace(
        case, corpus={'admission': {'drainers': 8}}, manifest=replace(case.manifest, id='synthetic-stress')
    )
    mixed = [outcome(), outcome('pass'), outcome('pass')]
    before = mixed if baseline_mixed else [outcome()] * 3
    after = mixed
    retry = mixed if retry_status == 'mixed' else [outcome(retry_status)] * 3
    responses = [[[outcome()], before], [[outcome('pass')], after]]
    if not baseline_mixed:
        responses.append([retry])
    calls, active = [], []

    @contextmanager
    def snapshot(repo, sha, output, label):
        active.append(label)
        yield tmp_path / label
        active.pop()

    def run_side(backend, cases, repeats, timeout):
        calls.append(([c.manifest.id for c in cases], repeats, timeout))
        assert active == ['baseline' if len(calls) == 1 else 'candidate']
        assert backend == tmp_path / active[0]
        return responses.pop(0)

    monkeypatch.setattr(gate, 'load_case', lambda path: target if path == 'target' else stress)
    monkeypatch.setattr(gate, 'backend_snapshot', snapshot)
    monkeypatch.setattr(gate, 'run_side', run_side)
    monkeypatch.setattr(gate, 'resolve_refs', lambda *_: {'baseline': 'b' * 40, 'candidate': 'a' * 40})
    output = tmp_path / 'output'
    assert gate.gate(tmp_path, ['target', 'stress'], 'REF', 'BASE', output, worker_timeout=123) == (
        0 if verdict == 'PASS' else 1
    )
    result = json.loads((output / 'gate.json').read_text())
    assert [r['classification'] for r in result['cases']] == ['fixed', classification]
    assert result['verdict'] == verdict
    row = result['cases'][1]
    assert row['inconclusive'] == (verdict == 'INCONCLUSIVE')
    assert row['candidate']['outcomes'] == after + ([] if baseline_mixed else retry)
    assert row['candidate']['retry_start'] == (None if baseline_mixed else 3)
    assert len(calls) == (2 if baseline_mixed else 3) and not responses
    assert all(k == 3 and timeout == 123 for _, k, timeout in calls)
    if not baseline_mixed:
        assert calls[-1][0] == [stress.manifest.id]


@pytest.mark.parametrize('exception_batch', ['initial', 'retry'])
def test_retry_never_hides_new_exception(case, exception_batch):
    case = replace(case, corpus={'admission': {'drainers': 8}})
    after = [outcome(), outcome('pass'), outcome('pass')]
    retry = [outcome()] * 3
    rare = outcome(exception_type='TypeError', site='product.new')
    (after if exception_batch == 'initial' else retry)[0] = rare
    result = gate.compare([case], {'baseline': [[outcome()] * 3], 'candidate': [after], 'candidate_retry': {0: retry}})
    assert result['cases'][0]['classification'] == 'still_failing'
    assert len(result['cases'][0]['candidate']['outcomes']) == 6
    assert result['verdict'] == 'FAIL'
    assert result['new_exception_sites'] == [{'exception_type': 'TypeError', 'site': 'product.new'}]


def test_retry_does_not_combine_small_batches_into_ship_sample(case):
    case = replace(case, corpus={'admission': {'drainers': 8}})
    result = gate.compare(
        [case],
        {
            'baseline': [[outcome()] * 2],
            'candidate': [[outcome(), outcome('pass')]],
            'candidate_retry': {0: [outcome()] * 2},
        },
        repeats=2,
    )
    assert result['verdict'] == 'DIAGNOSTIC'
    assert result['cases'][0]['insufficient_repeats']


def test_unanimous_passing_baseline_accepts_equal_retry(case):
    case = replace(case, corpus={'admission': {'drainers': 8}})
    result = gate.compare(
        [case],
        {
            'baseline': [[outcome('pass')] * 3],
            'candidate': [[outcome(), outcome('pass'), outcome('pass')]],
            'candidate_retry': {0: [outcome('pass')] * 3},
        },
    )
    assert result['cases'][0]['classification'] == 'unchanged_pass'
    assert result['verdict'] == 'REGRESSION_ONLY'


def test_mixed_target_cannot_be_proven_fixed_by_unanimous_passing_retry(case):
    case = replace(
        case, corpus={'admission': {'drainers': 8}}, manifest=replace(case.manifest, gate={'fixed_by_ref': True})
    )
    result = gate.compare(
        [case],
        {
            'baseline': [[outcome()] * 5],
            'candidate': [[outcome(), *[outcome('pass')] * 4]],
            'candidate_retry': {0: [outcome('pass')] * 5},
        },
        repeats=5,
    )
    assert result['cases'][0]['classification'] == 'unstable'
    assert result['verdict'] == 'INCONCLUSIVE'


def test_unstable_still_rejects_new_exception_from_any_run(case):
    case = replace(case, corpus={'admission': {'drainers': 8}})
    rare = outcome(reason='new exception', exception_type='TypeError', site='product.new')
    result = gate.compare([case], {'baseline': [[outcome()] * 3], 'candidate': [[outcome(), outcome('pass'), rare]]})
    assert result['cases'][0]['classification'] == 'unstable'
    assert result['verdict'] == 'FAIL'
    assert result['new_exception_sites'] == [{'exception_type': 'TypeError', 'site': 'product.new'}]


def test_stress_fix_requires_full_ref_pass_not_a_later_stop(case):
    case = replace(
        case, corpus={'admission': {'drainers': 8}}, manifest=replace(case.manifest, gate={'fixed_by_ref': True})
    )
    after = {'stages': outcome('pass')['stages'] + outcome(stage='titling')['stages']}
    result = gate.compare([case], {'baseline': [[outcome()] * 5], 'candidate': [[after] * 5]}, repeats=5)
    assert result['cases'][0]['classification'] != 'fixed'
    assert result['verdict'] == 'FAIL'


def test_missing_stress_runs_fail_instead_of_becoming_unstable(case):
    case = replace(case, corpus={'admission': {'drainers': 8}})
    result = gate.compare([case], {'baseline': [[outcome(), outcome('pass')]], 'candidate': [[outcome()] * 3]})
    assert result['verdict'] == 'FAIL' and result['cases'][0]['incomplete']


@pytest.mark.parametrize('matching_indices', [{0}, {4}, {0, 1, 2, 3, 4}])
def test_every_base_run_must_reproduce_observation_only_expected_stop(case, matching_indices):
    case = replace(
        case, corpus={'admission': {'drainers': 8}}, manifest=replace(case.manifest, gate={'fixed_by_ref': True})
    )
    baseline = []
    for index in range(5):
        row = outcome(reason='primary')
        row['stages'][0]['observations'] = [{'reason': 'expected'}] if index in matching_indices else []
        baseline.append(row)
    result = gate.compare([case], {'baseline': [baseline], 'candidate': [[outcome('pass')] * 5]}, repeats=5)
    if len(matching_indices) == 5:
        assert result['verdict'] == 'PASS' and result['cases'][0]['classification'] == 'fixed'
    else:
        assert result['verdict'] == 'INCONCLUSIVE' and result['cases'][0]['classification'] == 'unstable'
