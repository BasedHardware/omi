"""The strongest local lease proofs must have an automatic CI caller."""

from copy import deepcopy
from functools import lru_cache
import hashlib
import json
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
# Composite actions that render the lease keys into a workload, and their callers.
LEASE_COMPOSITES = {
    'deploy-backend-stack': {('gcp_backend.yml', 'deploy'), ('gcp_backend_auto_dev.yml', 'deploy')},
    'deploy-projection-pump': {('gcp_backend.yml', 'deploy-projection-pump')},
}
# Prod manifest surfaces that carry the lease keys, and the writer that renders them.
LEASE_SURFACES = {
    ('cloud_run', 'backend'): 'deploy-backend-stack',
    ('cloud_run', 'backend-sync'): 'deploy-backend-stack',
    ('cloud_run', 'backend-sync-backfill'): 'deploy-backend-stack',
    ('cloud_run', 'backend-integration'): 'deploy-backend-stack',
    ('cloud_run', 'backend-projection-pump'): 'deploy-projection-pump',
    ('gke', 'backend-listen'): 'gcp_backend_listen_helm.yml',
    ('gke', 'pusher'): 'gcp_backend_pusher.yml',
    ('gke', 'config_map'): 'deploy-backend-stack',
}
# gcp_backend.yml jobs that write externally before or beside the stack composite on
# a deploy run (audit issue, Cloud Run). firestore_readiness must bind before them.
GCP_BACKEND_DEPLOY_WRITERS = ('record_break_glass', 'deploy', 'deploy-projection-pump')


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


@lru_cache(maxsize=None)
def _action(name='deploy-backend-stack'):
    return yaml.safe_load((ROOT / '.github/actions' / name / 'action.yml').read_text())


def _action_binding(name='deploy-backend-stack'):
    return next(step for step in _action(name)['runs']['steps'] if step.get('name') == BINDING)


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
    binding = _action_binding()
    assert 'GITHUB_ENV' in binding['run']
    for composite in LEASE_COMPOSITES:
        action = _action(composite)
        step = _action_binding(composite)
        # One binding text everywhere: the executed tests below cover every writer.
        assert step['run'] == binding['run'], composite
        assert step['env']['RECORD_TOKEN_LEASE_ENVIRONMENT'] == '${{ inputs.environment }}', composite
        for key in KEYS:
            name = key.lower()
            assert step['env'][key] == '${{ inputs.' + name + ' }}', composite
            # An omitted input must reach the binding empty, so prod fails instead of defaulting.
            assert action['inputs'][name]['default'] == '', composite
    for workflow in (*STANDALONE_WRITERS, 'gcp_backend.yml'):
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


# Step markers for external writes: registry, GitHub, Secret Manager, ConfigMap, Helm, Cloud Run.
WRITE_MARKERS = (
    'docker push',
    'helm ',
    'gh issue create',
    'gh label create',
    'kubectl apply',
    'deploy-backend-config.sh',
    'gcloud run',
    'gcloud secrets',
    'deploy-cloudrun',
    'deploy-backend-stack',
    'deploy-projection-pump',
)


def _writes(step):
    text = f"{step.get('uses', '')}\n{step.get('run', '')}"
    return any(marker in text for marker in WRITE_MARKERS)


# SCA-3748 r4 finding 2: the steps allowed ahead of a binding are an allowlist, not
# a write denylist. Besides an actions/checkout with no run, only these named,
# read-only steps may precede it, pinned by the sha256 of their canonical JSON.
# Changing one fails here: review that it still writes nothing, then re-pin.
READ_ONLY_PREFIX = {
    # Listen: refuses a non-main dispatch and an unknown environment before checkout.
    'Validate Environment Input': 'b1efd21eba390130b5c4f4c650cd86c548a83412a348a4a4e59e530c87aef7f4',
    # Listen: compares the checked-out SHA with the requested control SHA.
    'Verify exact listen control SHA': '1510d34ccc2e960ccec706233ec53f29113d28d14939c74224a50283c1916995',
    # Listen: validates the image-only admission inputs (no deploy runs it after a bind).
    'Validate image-only Listen admission': '83d3800a70336bc50b822a17cfdb014ebf48805b9f5be16a560b48094092d315',
}
# The only conditions a job binding may carry, each true on every run that reaches
# that job's lease write. None means unconditional.
BIND_CONDITIONS = {
    ('gcp_backend_pusher.yml', 'deploy'): None,
    # Listen writes lease env only in deploy mode, which is exactly this condition.
    ('gcp_backend_listen_helm.yml', 'helm-upgrade'): (
        "${{ inputs.mode != 'evidence' && ((github.event.inputs.mode || 'deploy') == 'deploy') }}"
    ),
    # The worker Helm upgrade's own condition (pinned equal below), plus its service.
    ('gcp_diarizer.yml', 'deploy'): (
        "env.SERVICE == 'batch-pipeline-worker' && inputs.mode != 'worker-depth-only' && "
        'inputs.preserve_live_worker != true && inputs.worker_dry_run != true'
    ),
    # Deploy mode; the deploy-mode writers need firestore_readiness to succeed.
    ('gcp_backend.yml', 'firestore_readiness'): "github.event.inputs.mode == 'deploy'",
}


def _step_digest(step):
    return hashlib.sha256(json.dumps(step, sort_keys=True).encode()).hexdigest()


def _assert_read_only_prefix(steps, where):
    for step in steps:
        label = f"{where}: {step.get('name') or step.get('uses')}"
        if 'uses' in step:
            assert step['uses'].startswith('actions/checkout@'), label
            assert 'run' not in step, label
            continue
        assert step.get('name') in READ_ONLY_PREFIX, f'{label} is not an allowlisted read-only step'
        assert _step_digest(step) == READ_ONLY_PREFIX[step['name']], f'{label} changed; review and re-pin'


def _assert_binding_runs(step, where, condition):
    # A failed binding must stop the job: no continue-on-error, and no condition
    # other than the pinned one that holds on every run reaching the lease write.
    assert 'continue-on-error' not in step, where
    assert step.get('if') == condition, where


def _assert_write_boundary(workflow, config):
    first = {'gcp_diarizer.yml', 'gcp_backend_pusher.yml', 'gcp_backend.yml'}
    bound = [
        (job_name, job, index)
        for job_name, job in config['jobs'].items()
        for index, step in enumerate(job.get('steps', []))
        if step.get('name') == BINDING
    ]
    assert bound, workflow
    for job_name, job, index in bound:
        where = f'{workflow}:{job_name}'
        assert (workflow, job_name) in BIND_CONDITIONS, where
        # A job-level continue-on-error would report a failed binding as success.
        assert 'continue-on-error' not in job, where
        _assert_binding_runs(job['steps'][index], where, BIND_CONDITIONS[workflow, job_name])
        if workflow in first:
            assert index == 0, where
        _assert_read_only_prefix(job['steps'][:index], where)
        # The classifier must still see this job's writes, all after the binding.
        assert any(_writes(step) for step in job['steps'][index + 1 :]) or job_name == 'firestore_readiness', where


def test_every_lease_writer_binds_before_any_write():
    # SCA-3748 r3 finding 1: the worker pushed its image, and the backend opened its
    # break-glass issue, before a missing prod vector failed the run. The binding
    # now precedes every external write in each job and composite that writes the
    # lease env: first in the worker, Pusher, firestore_readiness and both
    # composites; Listen keeps its pinned validate/checkout/exact-control prefix.
    for workflow in (*STANDALONE_WRITERS, 'gcp_backend.yml'):
        _assert_write_boundary(workflow, _workflow(workflow))
    for composite, callers in LEASE_COMPOSITES.items():
        steps = _action(composite)['runs']['steps']
        assert steps[0].get('name') == BINDING, composite
        _assert_binding_runs(steps[0], composite, None)
        assert any(_writes(step) for step in steps[1:]), composite
        for workflow, job_name in callers:
            caller_steps = _workflow(workflow)['jobs'][job_name]['steps']
            index = next(i for i, s in enumerate(caller_steps) if f'actions/{composite}' in s.get('uses', ''))
            # Only local checkouts may precede the composite's own first-step binding.
            assert all(s.get('uses', '').startswith('actions/checkout@') for s in caller_steps[:index])
            _assert_read_only_prefix(caller_steps[:index], f'{workflow}:{job_name}')


def _mutated(workflow, job_name, mutate):
    config = deepcopy(_workflow(workflow))
    mutate(config['jobs'][job_name]['steps'])
    return config


def _bind_index(steps):
    return next(i for i, s in enumerate(steps) if s.get('name') == BINDING)


WRITE_BOUNDARY_MUTATIONS = {
    # Reviewer mutation: a ConfigMap patch the old write denylist did not know.
    'kubectl_patch_before_listen_bind': (
        'gcp_backend_listen_helm.yml',
        'helm-upgrade',
        lambda steps: steps.insert(
            _bind_index(steps),
            {'name': 'Patch config', 'run': 'kubectl -n prod-omi-backend patch configmap backend-config -p "{}"'},
        ),
    ),
    # Reviewer mutation: the Pusher binding disabled while its writes still run.
    'pusher_bind_if_false': (
        'gcp_backend_pusher.yml',
        'deploy',
        lambda steps: steps[_bind_index(steps)].update({'if': False}),
    ),
    'allowlisted_name_with_new_run': (
        'gcp_backend_listen_helm.yml',
        'helm-upgrade',
        lambda steps: steps[0].update({'run': steps[0]['run'] + '\nkubectl apply -f config.yaml\n'}),
    ),
    'non_checkout_action_before_bind': (
        'gcp_backend_listen_helm.yml',
        'helm-upgrade',
        lambda steps: steps.insert(1, {'name': 'Auth', 'uses': 'google-github-actions/auth@v2'}),
    ),
    'bind_continue_on_error': (
        'gcp_diarizer.yml',
        'deploy',
        lambda steps: steps[_bind_index(steps)].update({'continue-on-error': True}),
    ),
    'bind_condition_widened': (
        'gcp_backend.yml',
        'firestore_readiness',
        lambda steps: steps[_bind_index(steps)].update({'if': "github.event.inputs.mode == 'build-only'"}),
    ),
}


@pytest.mark.parametrize('mutation', sorted(WRITE_BOUNDARY_MUTATIONS))
def test_write_boundary_check_rejects_each_mutation(mutation):
    workflow, job_name, mutate = WRITE_BOUNDARY_MUTATIONS[mutation]
    _assert_write_boundary(workflow, _workflow(workflow))  # The real workflow passes.
    with pytest.raises(AssertionError):
        _assert_write_boundary(workflow, _mutated(workflow, job_name, mutate))


def test_backend_deploy_run_validates_the_vector_before_the_break_glass_audit_issue():
    jobs = _workflow('gcp_backend.yml')['jobs']
    ((job_name, job, index, step),) = _job_bindings('gcp_backend.yml')
    assert (job_name, index) == ('firestore_readiness', 0)
    # Deploy mode only: build-only and workerd runs write no lease env.
    assert step['if'] == "github.event.inputs.mode == 'deploy'"
    assert 'deploy' in job['if']
    for writer in GCP_BACKEND_DEPLOY_WRITERS:
        needs = jobs[writer]['needs']
        assert 'firestore_readiness' in ([needs] if isinstance(needs, str) else needs), writer
    # Every deploy-mode writer requires firestore_readiness to have succeeded.
    for writer in ('deploy', 'deploy-projection-pump'):
        assert "needs.firestore_readiness.result == 'success'" in jobs[writer]['if'], writer
    assert jobs['record_break_glass']['if'] == "${{ needs.firestore_readiness.outputs.break_glass == 'true' }}"


def test_projection_pump_caller_passes_the_raw_lease_vars():
    # SCA-3748 r3 finding 2: the pump rendered the inherited lease keys from manifest
    # defaults without ever reading the four variables.
    step = next(
        s
        for s in _workflow('gcp_backend.yml')['jobs']['deploy-projection-pump']['steps']
        if s.get('uses') == './.github/actions/deploy-projection-pump'
    )
    assert _workflow('gcp_backend.yml')['jobs']['deploy-projection-pump']['environment'] == 'prod'
    for key in KEYS:
        assert step['with'][key.lower()] == '${{ vars.' + key + ' }}'
    assert step['with']['environment'] == '${{ github.event.inputs.environment }}'


def test_every_manifest_surface_with_lease_keys_has_a_bound_writer():
    # A service or job that inherits the lease keys must be rendered by a writer
    # that binds the four variables; otherwise it would deploy manifest defaults.
    loader = getattr(yaml, 'CSafeLoader', yaml.SafeLoader)
    manifest = yaml.load((ROOT / 'backend/deploy/runtime_env.yaml').read_text(), Loader=loader)
    prod = manifest['environments']['prod']
    found = set()
    for name, service in (prod['cloud_run'].get('services') or {}).items():
        if 'RECORD_TOKEN_LEASE_MODE' in (service.get('env') or {}):
            found.add(('cloud_run', name))
    for name, job in (prod['cloud_run'].get('jobs') or {}).items():
        assert not set(KEYS).intersection(job.get('env') or {}), f'Cloud Run job {name} has no lease binding'
    for name, workload in prod['gke'].items():
        entries = workload.get('env') or workload.get('entries') or {}
        if 'RECORD_TOKEN_LEASE_MODE' in entries:
            found.add(('gke', name))
    assert not set(KEYS).intersection(prod.get('desktop_backend', {}).get('env') or {})
    assert found == set(LEASE_SURFACES)
    for writer in set(LEASE_SURFACES.values()):
        if writer.endswith('.yml'):
            assert _job_bindings(writer), writer
        else:
            assert _action(writer)['runs']['steps'][0].get('name') == BINDING, writer


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
    for path in sorted((ROOT / '.github/actions').glob('*/action.y*ml')):
        text = path.read_text()
        # A composite that renders the backend runtime manifest renders the lease keys.
        if 'RECORD_TOKEN_LEASE_' in text or 'render_backend_runtime_env.py' in text:
            assert path.parent.name in LEASE_COMPOSITES, f'{path.parent.name} renders lease env outside the binding'


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
