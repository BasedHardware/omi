"""The strongest local lease proofs must have an automatic CI caller."""

from pathlib import Path
import yaml
import pytest

ROOT = Path(__file__).resolve().parents[3]


def test_transaction_and_lifecycle_proofs_are_in_the_emulator_ci_lane():
    runner = (ROOT / 'backend/scripts/run-emulator-proofs.sh').read_text()
    workflow = yaml.safe_load((ROOT / '.github/workflows/backend-emulator-proofs.yml').read_text())
    # YAML 1.1 parses Actions' unquoted `on` as True.
    events = workflow.get('on', workflow.get(True))
    files = [
        'backend/tests/integration/test_record_custody_append_emulator.py',
        'backend/tests/unit/test_record_seal_nojob_emulator.py',
    ]
    for path in files:
        assert path.removeprefix('backend/') in runner
        for event in ('push', 'pull_request'):
            assert path in events[event]['paths']
    assert '"$PYTHON" -m testing.lifecycle_sim.run' in runner
    assert '--extra-test-module testing/lifecycle_properties/test_properties.py' in runner
    # These proofs must execute before the long legacy corpus consumes the
    # existing advisory job's deadline; keep its runner and timeout unchanged.
    assert runner.index('"$PYTHON" -m testing.lifecycle_sim.run') < runner.index('run_proof "sync/live overlap')
    assert all(
        'backend/testing/lifecycle_properties/**' in events[event]['paths'] for event in ('push', 'pull_request')
    )
    steps = workflow['jobs']['emulator-proofs']['steps']
    assert any('redis-server' in step.get('run', '') and 'ffmpeg' in step.get('run', '') for step in steps)
    assert any('run-emulator-proofs.sh' in step.get('run', '') for step in steps)


def test_real_promql_proof_is_required_in_local_and_ci_manifests():
    checks = yaml.safe_load((ROOT / '.github/checks-manifest.yaml').read_text())['checks']
    check = next(item for item in checks if item['id'] == 'record-token-lease-promql')
    assert set(check['lanes']) == {'local', 'ci'}
    assert 'backend/charts/monitoring/**' in check['triggers']
    assert check['command'] == [
        'bash',
        'scripts/dev-harness/run-python.sh',
        'backend/scripts/check_record_token_lease_promql.py',
    ]
    script = (ROOT / 'backend/scripts/check_record_token_lease_promql.py').read_text()
    assert 'hashlib.sha256' in script and 'checksum mismatch' in script
    assert 'runpy.run_path' in script and 'tests/promql/record_token_lease.py' in script


def test_standalone_and_stack_deploys_bind_the_same_rollout_inputs():
    keys = (
        'RECORD_TOKEN_LEASE_MODE',
        'RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT',
        'RECORD_TOKEN_LEASE_SECONDS',
        'RECORD_TOKEN_LEASE_DEPLOYED_AT',
    )
    action = yaml.safe_load((ROOT / '.github/actions/deploy-backend-stack/action.yml').read_text())
    binding = next(
        step for step in action['runs']['steps'] if step.get('name') == 'Bind shared record token lease rollout inputs'
    )
    assert 'GITHUB_ENV' in binding['run']
    for workflow in ('gcp_backend_pusher.yml', 'gcp_backend_listen_helm.yml'):
        config = yaml.safe_load((ROOT / '.github/workflows' / workflow).read_text())
        # Protected environment variables become available after the runner
        # declares the environment. Workflow-scope defaults can mask the ramp.
        assert not set(keys).intersection(config['env'])
        writers = 0
        for job in config['jobs'].values():
            steps = job.get('steps', [])
            writes = [
                i for i, step in enumerate(steps) if 'backend/scripts/deploy-backend-config.sh' in step.get('run', '')
            ]
            if not writes:
                continue
            writers += 1
            assert job['environment']
            index, actual = next((i, step) for i, step in enumerate(steps) if step.get('name') == binding['name'])
            assert index < min(writes)
            assert actual['run'] == binding['run']
            for key in keys:
                assert 'vars.' + key in actual['env'][key]
                name = key.lower()
                assert binding['env'][key] == '${{ inputs.' + name + ' }}'
                assert (
                    action['inputs'][name]['default']
                    == {
                        'RECORD_TOKEN_LEASE_MODE': 'off',
                        'RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT': '0',
                        'RECORD_TOKEN_LEASE_SECONDS': '3600',
                        'RECORD_TOKEN_LEASE_DEPLOYED_AT': '0',
                    }[key]
                )
        assert writers, 'standalone workflow no longer exercises the runtime ConfigMap writer'


@pytest.mark.parametrize('mode,epoch', [(None, None), ('off', '0'), ('shadow', '2000000000'), ('serve', '2000000000')])
def test_shared_binding_materializes_the_validated_vector(monkeypatch, tmp_path, mode, epoch):
    action = yaml.safe_load((ROOT / '.github/actions/deploy-backend-stack/action.yml').read_text())
    step = next(
        step for step in action['runs']['steps'] if step.get('name') == 'Bind shared record token lease rollout inputs'
    )
    values = {
        'RECORD_TOKEN_LEASE_MODE': mode,
        'RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT': '10',
        'RECORD_TOKEN_LEASE_SECONDS': '3600',
        'RECORD_TOKEN_LEASE_DEPLOYED_AT': epoch,
    }
    if mode is None:
        values = {key: action['inputs'][key.lower()]['default'] for key in values}
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    target = tmp_path / 'github-env'
    monkeypatch.setenv('GITHUB_ENV', str(target))
    code = step['run'].split("python3 - <<'PYTHON'\n", 1)[1].rsplit('PYTHON', 1)[0]
    exec(compile(code, '<actual composite binding step>', 'exec'), {})
    assert dict(line.split('=', 1) for line in target.read_text().splitlines()) == values


@pytest.mark.parametrize(
    'key,value',
    [
        ('RECORD_TOKEN_LEASE_MODE', 'typo'),
        ('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '101'),
        ('RECORD_TOKEN_LEASE_SECONDS', '1'),
        ('RECORD_TOKEN_LEASE_DEPLOYED_AT', '0'),
        ('RECORD_TOKEN_LEASE_DEPLOYED_AT', 'nan'),
    ],
)
def test_invalid_rollout_vector_cannot_partially_write_job_env(monkeypatch, tmp_path, key, value):
    action = yaml.safe_load((ROOT / '.github/actions/deploy-backend-stack/action.yml').read_text())
    step = next(
        step for step in action['runs']['steps'] if step.get('name') == 'Bind shared record token lease rollout inputs'
    )
    values = {
        'RECORD_TOKEN_LEASE_MODE': 'serve',
        'RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT': '10',
        'RECORD_TOKEN_LEASE_SECONDS': '3600',
        'RECORD_TOKEN_LEASE_DEPLOYED_AT': '2000000000',
        key: value,
    }
    for name, raw in values.items():
        monkeypatch.setenv(name, raw)
    target = tmp_path / 'github-env'
    target.write_text('PREVIOUS=kept\n')
    monkeypatch.setenv('GITHUB_ENV', str(target))
    code = step['run'].split("python3 - <<'PYTHON'\n", 1)[1].rsplit('PYTHON', 1)[0]
    with pytest.raises(ValueError):
        exec(compile(code, '<actual composite binding step>', 'exec'), {})
    assert target.read_text() == 'PREVIOUS=kept\n'
