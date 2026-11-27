"""The strongest local lease proofs must have an automatic CI caller."""

from functools import lru_cache
from pathlib import Path
import yaml
import pytest

ROOT = Path(__file__).resolve().parents[3]

KEYS = (
    'RECORD_TOKEN_LEASE_MODE',
    'RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT',
    'RECORD_TOKEN_LEASE_SECONDS',
    'RECORD_TOKEN_LEASE_DEPLOYED_AT',
)
# SCA-3748: only development may fill a missing variable. GitHub renders a
# missing and an empty variable identically, so prod refuses both.
DEVELOPMENT_DEFAULTS = dict(zip(KEYS, ('serve', '100', '3600', '1795662310')))
BINDING = 'Bind shared record token lease rollout inputs'
JOB_ENVIRONMENT = "${{ github.event.inputs.environment == 'prod' && 'prod' || 'development' }}"
# Every workflow that writes lease env to a prod workload. A new writer must be
# added here and bind the same step, or the discovery test below fails.
STANDALONE_WRITERS = ('gcp_backend_pusher.yml', 'gcp_backend_listen_helm.yml', 'gcp_diarizer.yml')
STACK_CALLERS = ('gcp_backend.yml', 'gcp_backend_auto_dev.yml')


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


def _action():
    return yaml.safe_load((ROOT / '.github/actions/deploy-backend-stack/action.yml').read_text())


def _action_binding():
    return next(step for step in _action()['runs']['steps'] if step.get('name') == BINDING)


def _job_bindings(workflow):
    config = _workflow(workflow)
    return [
        (job_name, job, index, step)
        for job_name, job in config['jobs'].items()
        for index, step in enumerate(job.get('steps', []))
        if step.get('name') == BINDING
    ]


def _run_binding(monkeypatch, tmp_path, environment, values):
    code = _action_binding()['run'].split("python3 - <<'PYTHON'\n", 1)[1].rsplit('PYTHON', 1)[0]
    for key in KEYS:
        monkeypatch.delenv(key, raising=False)
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    if environment is None:
        monkeypatch.delenv('RECORD_TOKEN_LEASE_ENVIRONMENT', raising=False)
    else:
        monkeypatch.setenv('RECORD_TOKEN_LEASE_ENVIRONMENT', environment)
    target = tmp_path / 'github-env'
    target.write_text('PREVIOUS=kept\n')
    monkeypatch.setenv('GITHUB_ENV', str(target))
    exec(compile(code, '<actual composite binding step>', 'exec'), {})
    lines = target.read_text().splitlines()[1:]
    return dict(line.split('=', 1) for line in lines)


def test_every_prod_lease_writer_binds_all_four_from_vars_with_no_fallback():
    action = _action()
    binding = _action_binding()
    assert 'GITHUB_ENV' in binding['run']
    assert binding['env']['RECORD_TOKEN_LEASE_ENVIRONMENT'] == '${{ inputs.environment }}'
    for key in KEYS:
        name = key.lower()
        assert binding['env'][key] == '${{ inputs.' + name + ' }}'
        # An omitted input must reach the binding empty, so prod fails instead of defaulting.
        assert action['inputs'][name]['default'] == ''
    for workflow in STANDALONE_WRITERS:
        config = _workflow(workflow)
        # Protected environment variables become available after the runner
        # declares the environment. Workflow-scope defaults can mask the ramp.
        assert not set(KEYS).intersection(config.get('env') or {}), workflow
        bindings = _job_bindings(workflow)
        assert bindings, workflow
        for job_name, job, _, step in bindings:
            where = f'{workflow}:{job_name}'
            assert job['environment'] == JOB_ENVIRONMENT, where
            assert step['run'] == binding['run'], where
            # Strictness follows the job's own environment, never a separate input.
            assert step['env']['RECORD_TOKEN_LEASE_ENVIRONMENT'] == JOB_ENVIRONMENT, where
            for key in KEYS:
                assert step['env'][key] == '${{ vars.' + key + ' }}', where


def test_standalone_writers_bind_before_their_runtime_config_writer():
    for workflow in ('gcp_backend_pusher.yml', 'gcp_backend_listen_helm.yml'):
        writers = 0
        for job in _workflow(workflow)['jobs'].values():
            steps = job.get('steps', [])
            writes = [i for i, s in enumerate(steps) if 'backend/scripts/deploy-backend-config.sh' in s.get('run', '')]
            if not writes:
                continue
            writers += 1
            index = next(i for i, s in enumerate(steps) if s.get('name') == BINDING)
            assert index < min(writes)
        assert writers, f'{workflow} no longer exercises the runtime ConfigMap writer'


def test_worker_helm_upgrade_passes_the_bound_vector_for_seal_worker_and_repair():
    # SCA-3748 r2 finding 1: the worker Helm upgrade wrote record-seal-worker and
    # record-seal-repair lease env from a literal in prod values.
    ((job_name, job, bind_index, bind),) = _job_bindings('gcp_diarizer.yml')
    steps = job['steps']
    helm_index, helm = next(
        (i, s) for i, s in enumerate(steps) if s.get('name') == 'Deploy Diarizer to GKE cluster using Helm'
    )
    assert bind_index < helm_index
    # The binding runs on every path that reaches the worker Helm upgrade.
    assert bind['if'] == "env.SERVICE == 'batch-pipeline-worker' && " + helm['if']
    branch = helm['run'].split('if [[ "$SERVICE" == "batch-pipeline-worker" ]]; then', 1)[1].split('elif', 1)[0]
    assert 'helm -n "$DEPLOY_NAMESPACE" upgrade --install' in branch
    for value, key in zip(('mode', 'servePercent', 'seconds', 'deployedAt'), KEYS):
        assert f'--set-string "recordTokenLease.{value}=${{{key}:?bind step did not run}}"' in branch


def test_no_other_workflow_writes_lease_env_or_upgrades_the_worker_chart():
    known = set(STANDALONE_WRITERS) | set(STACK_CALLERS)
    for path in sorted((ROOT / '.github/workflows').glob('*.y*ml')):
        text = path.read_text()
        if 'RECORD_TOKEN_LEASE_' in text or 'recordTokenLease' in text:
            assert path.name in known, f'{path.name} writes lease env outside the strict binding'
        # The worker chart renders the seal readers' lease env; only the bound path may install it.
        if 'charts/batch-pipeline-worker' in text:
            assert path.name == 'gcp_diarizer.yml', f'{path.name} installs the worker chart outside the binding'


@pytest.mark.parametrize('environment', ['prod', None, '', 'staging-typo'])
@pytest.mark.parametrize('blank', ['', '   '])
@pytest.mark.parametrize('key', KEYS)
def test_prod_binding_refuses_a_missing_or_empty_variable(monkeypatch, tmp_path, environment, blank, key):
    # SCA-3748 r2 finding 3: `vars.X || 'serve'` rendered an empty variable as
    # serve while the runtime treats blank as the kill. Prod now fails loudly,
    # and any environment other than development fails closed the same way.
    values = {**DEVELOPMENT_DEFAULTS, key: blank}
    with pytest.raises(ValueError, match=key):
        _run_binding(monkeypatch, tmp_path, environment, values)
    assert (tmp_path / 'github-env').read_text() == 'PREVIOUS=kept\n'


def test_prod_binding_refuses_all_variables_unset(monkeypatch, tmp_path):
    with pytest.raises(ValueError, match='set non-empty Actions variables before a prod deploy'):
        _run_binding(monkeypatch, tmp_path, 'prod', {})
    assert (tmp_path / 'github-env').read_text() == 'PREVIOUS=kept\n'


def test_development_binding_fills_only_the_missing_defaults(monkeypatch, tmp_path):
    assert _run_binding(monkeypatch, tmp_path, 'development', {}) == DEVELOPMENT_DEFAULTS
    values = {'RECORD_TOKEN_LEASE_MODE': 'shadow', 'RECORD_TOKEN_LEASE_DEPLOYED_AT': '2000000000'}
    assert _run_binding(monkeypatch, tmp_path, 'development', values) == {**DEVELOPMENT_DEFAULTS, **values}


@pytest.mark.parametrize('mode,epoch', [('off', '0'), ('shadow', '2000000000'), ('serve', '2000000000')])
def test_prod_binding_materializes_the_validated_vector(monkeypatch, tmp_path, mode, epoch):
    values = {
        'RECORD_TOKEN_LEASE_MODE': mode,
        'RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT': '10',
        'RECORD_TOKEN_LEASE_SECONDS': '3600',
        'RECORD_TOKEN_LEASE_DEPLOYED_AT': epoch,
    }
    assert _run_binding(monkeypatch, tmp_path, 'prod', values) == values


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
    values = {
        'RECORD_TOKEN_LEASE_MODE': 'serve',
        'RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT': '10',
        'RECORD_TOKEN_LEASE_SECONDS': '3600',
        'RECORD_TOKEN_LEASE_DEPLOYED_AT': '2000000000',
        key: value,
    }
    with pytest.raises(ValueError):
        _run_binding(monkeypatch, tmp_path, 'prod', values)
    assert (tmp_path / 'github-env').read_text() == 'PREVIOUS=kept\n'


@lru_cache(maxsize=None)
def _workflow(name):
    return yaml.safe_load((ROOT / '.github/workflows' / name).read_text())


@lru_cache(maxsize=1)
def _deploy_backend_stack_callers():
    # Text prefilter keeps this inside the per-test CPU budget: only workflows
    # that mention the composite are parsed; the parsed step is authoritative.
    callers = []
    for path in sorted((ROOT / '.github/workflows').glob('*.y*ml')):
        if 'actions/deploy-backend-stack' not in path.read_text():
            continue
        config = _workflow(path.name)
        for job_name, job in (config.get('jobs') or {}).items():
            for step in job.get('steps', []):
                if step.get('uses') == './.github/actions/deploy-backend-stack':
                    callers.append((path.name, job_name, job, step))
    return callers


def test_every_deploy_backend_stack_caller_passes_the_raw_lease_vars():
    # SCA-3748: a caller that omits these inputs, or wraps them in a fallback,
    # would hide a missing prod variable behind a literal vector.
    callers = _deploy_backend_stack_callers()
    assert {name for name, *_ in callers} == set(STACK_CALLERS)
    for name, job_name, job, step in callers:
        where = f'{name}:{job_name}'
        # Protected environment variables only resolve once the job declares its environment.
        assert job.get('environment'), where
        inputs = step.get('with') or {}
        for key in KEYS:
            assert inputs.get(key.lower()) == '${{ vars.' + key + ' }}', where
