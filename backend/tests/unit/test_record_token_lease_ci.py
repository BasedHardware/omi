"""The strongest local lease proofs must have an automatic CI caller."""

from functools import lru_cache
from pathlib import Path
import subprocess

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


LEASE_FALLBACKS = {
    'RECORD_TOKEN_LEASE_MODE': 'off',
    'RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT': '0',
    'RECORD_TOKEN_LEASE_SECONDS': '3600',
    'RECORD_TOKEN_LEASE_DEPLOYED_AT': '0',
}


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


def test_every_deploy_backend_stack_caller_passes_the_shared_lease_vector():
    # SCA-3748: a caller that omits these inputs gets the composite defaults,
    # so an ordinary backend deploy silently resets the production lease ramp.
    callers = _deploy_backend_stack_callers()
    assert {name for name, *_ in callers} >= {'gcp_backend.yml', 'gcp_backend_auto_dev.yml'}
    for name, job_name, job, step in callers:
        where = f'{name}:{job_name}'
        # Protected environment variables only resolve once the job declares its environment.
        assert job.get('environment'), where
        inputs = step.get('with') or {}
        for key, fallback in LEASE_FALLBACKS.items():
            assert inputs.get(key.lower()) == f"${{{{ vars.{key} || '{fallback}' }}}}", where


def test_stack_callers_use_the_same_lease_expressions_as_listen_and_pusher():
    callers = _deploy_backend_stack_callers()
    for workflow in ('gcp_backend_pusher.yml', 'gcp_backend_listen_helm.yml'):
        config = _workflow(workflow)
        bindings = [
            step['env']
            for job in config['jobs'].values()
            for step in job.get('steps', [])
            if step.get('name') == 'Bind shared record token lease rollout inputs'
        ]
        assert bindings, workflow
        for env in bindings:
            for name, job_name, _, step in callers:
                for key in LEASE_FALLBACKS:
                    assert step['with'][key.lower()] == env[key], f'{name}:{job_name} vs {workflow} {key}'


# SCA-4463: Pusher-only lease vector. Container env replaces the four shared
# ConfigMap references on the Pusher alone; backend-listen and the shared
# ConfigMap source never see it.
SHADOW_OVERRIDE = {'mode': 'shadow', 'servePercent': '0', 'seconds': '3600', 'deployedAt': '1795662310'}
LEASE_ENV_NAMES = tuple(LEASE_FALLBACKS)
RENDER_DIGEST = 'sha256:' + 'a' * 64
PUSHER_WORKFLOW = 'gcp_backend_pusher.yml'


def _override_module():
    from scripts import pusher_record_token_lease_override as override

    return override


def _helm(*args):
    result = subprocess.run(['helm', 'template', *args], capture_output=True, text=True, check=False, cwd=ROOT)
    return result


def _render_pusher(*extra):
    chart = ROOT / 'backend/charts/pusher'
    result = _helm(
        'prod-omi-pusher',
        str(chart),
        '-f',
        str(chart / 'prod_omi_pusher_values.yaml'),
        '--set-string',
        'image.repository=gcr.io/based-hardware/pusher',
        '--set-string',
        f'image.digest={RENDER_DIGEST}',
        '--set-string',
        'image.tag=',
        '--set-string',
        'image.pullPolicy=IfNotPresent',
        *extra,
    )
    return result


def _documents(text):
    return [item for item in yaml.safe_load_all(text) if isinstance(item, dict)]


def _pusher_container(text):
    return _override_module().pusher_container(_documents(text))


def _override_file(tmp_path, vector=SHADOW_OVERRIDE, raw=None):
    path = tmp_path / 'pusher-record-token-lease-override.yaml'
    path.write_text(raw if raw is not None else _override_module().values_document(vector))
    return path


def test_pusher_chart_without_override_keeps_shared_configmap_references():
    values = yaml.safe_load((ROOT / 'backend/charts/pusher/values.yaml').read_text())
    assert values['recordTokenLeaseOverride'] == {}
    plain = _render_pusher()
    assert plain.returncode == 0, plain.stderr
    explicit_empty = _render_pusher('--set-json', 'recordTokenLeaseOverride={}')
    assert explicit_empty.stdout == plain.stdout
    container = _pusher_container(plain.stdout)
    env = {item['name']: item for item in container['env']}
    for name in LEASE_ENV_NAMES:
        assert env[name] == {
            'name': name,
            'valueFrom': {'configMapKeyRef': {'name': 'prod-omi-backend-config', 'key': name}},
        }
    assert container['envFrom'] == [{'configMapRef': {'name': 'prod-omi-backend-config'}}]


def test_pusher_override_replaces_only_the_four_lease_entries_and_keeps_envfrom(tmp_path):
    plain = _render_pusher()
    overridden = _render_pusher('-f', str(_override_file(tmp_path)))
    assert overridden.returncode == 0, overridden.stderr
    container = _pusher_container(overridden.stdout)
    assert _override_module().check_rendered(container, SHADOW_OVERRIDE, config_map='prod-omi-backend-config') == []
    # Precedence: the literal container env entry is present, and envFrom still
    # attaches the shared ConfigMap (whose own lease keys the env entry outranks).
    env = [item for item in container['env'] if item['name'] in LEASE_ENV_NAMES]
    assert env == [
        {'name': 'RECORD_TOKEN_LEASE_MODE', 'value': 'shadow'},
        {'name': 'RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', 'value': '0'},
        {'name': 'RECORD_TOKEN_LEASE_SECONDS', 'value': '3600'},
        {'name': 'RECORD_TOKEN_LEASE_DEPLOYED_AT', 'value': '1795662310'},
    ]
    assert container['envFrom'] == [{'configMapRef': {'name': 'prod-omi-backend-config'}}]
    # Everything else in the release renders exactly as without the override.
    plain_docs, override_docs = _documents(plain.stdout), _documents(overridden.stdout)
    for documents in (plain_docs, override_docs):
        target = _override_module().pusher_container(documents)
        target['env'] = [item for item in target['env'] if item['name'] not in LEASE_ENV_NAMES]
    assert override_docs == plain_docs


def test_listen_chart_render_is_byte_identical_with_the_override(tmp_path):
    override_file = _override_file(tmp_path)
    chart = ROOT / 'backend/charts/backend-listen'
    listen = [
        'prod-omi-backend-listen',
        str(chart),
        '-f',
        str(chart / 'prod_omi_backend_listen_values.yaml'),
        '--set-string',
        'image.tag=abc1234',
    ]
    plain = _helm(*listen)
    assert plain.returncode == 0, plain.stderr
    # Even a mis-passed override file cannot reach the listen chart: it has no such block.
    mispassed = _helm(*listen, '-f', str(override_file))
    assert mispassed.stdout == plain.stdout
    assert 'recordTokenLeaseOverride' not in (chart / 'templates').joinpath('deployment.yaml').read_text()


@pytest.fixture
def shared_config_map_source(monkeypatch):
    """Parse the real runtime manifest once, in setup, and bind its prod ConfigMap inputs."""
    from scripts import render_gke_backend_config as config_renderer

    manifest = config_renderer._load_yaml(config_renderer.DEFAULT_MANIFEST)
    monkeypatch.setattr(config_renderer, '_load_yaml', lambda path: manifest)
    entries = manifest['environments']['prod']['gke']['config_map']['entries']
    for key, entry in entries.items():
        if entry.get('source') == 'environment':
            monkeypatch.setenv(key, str(entry.get('default') or 'synthetic-gke-value'))
    for key, value in LEASE_FALLBACKS.items():
        monkeypatch.setenv(key, value)
    return config_renderer, entries


def test_shared_configmap_source_is_byte_identical_with_the_bound_override(
    monkeypatch, tmp_path, shared_config_map_source
):
    config_renderer, entries = shared_config_map_source
    assert not [key for key in entries if 'OVERRIDE' in key and 'LEASE' in key]

    def rendered():
        name, values = config_renderer.config_map_entries('prod')
        return name, ''.join(f'{key}={values[key]}\n' for key in sorted(values))

    before = rendered()
    # Replay the bind step's real job-environment exports, then render again.
    github_env = tmp_path / 'github-env'
    inputs = dict(zip(_override_module().INPUT_ENV.values(), SHADOW_OVERRIDE.values()))
    _override_module().bind('prod', 'pusher', tmp_path / 'bound.yaml', inputs, github_env)
    exports = dict(line.split('=', 1) for line in github_env.read_text().splitlines())
    assert exports['PUSHER_RECORD_TOKEN_LEASE_OVERRIDE'] == 'active'
    for key, value in {**inputs, **exports}.items():
        monkeypatch.setenv(key, value)
    after = rendered()
    assert after == before
    assert 'RECORD_TOKEN_LEASE_MODE=off\n' in after[1]


@pytest.mark.parametrize(
    'raw',
    [
        'recordTokenLeaseOverride:\n  mode: "typo"\n  servePercent: "0"\n  seconds: "3600"\n  deployedAt: "1"\n',
        'recordTokenLeaseOverride:\n  mode: "shadow"\n  servePercent: "101"\n  seconds: "3600"\n  deployedAt: "1"\n',
        'recordTokenLeaseOverride:\n  mode: "shadow"\n  servePercent: "0"\n  seconds: "1799"\n  deployedAt: "1"\n',
        'recordTokenLeaseOverride:\n  mode: "shadow"\n  servePercent: "0"\n  seconds: "7201"\n  deployedAt: "1"\n',
        'recordTokenLeaseOverride:\n  mode: "shadow"\n  servePercent: "0"\n  seconds: "3600"\n  deployedAt: "0"\n',
        'recordTokenLeaseOverride:\n  mode: "shadow"\n  servePercent: "0"\n  seconds: "3600"\n  deployedAt: "-1"\n',
        # Numbers are refused so YAML cannot reformat an epoch into 1.79566231e+09.
        'recordTokenLeaseOverride:\n  mode: "shadow"\n  servePercent: 0\n  seconds: 3600\n  deployedAt: 1795662310\n',
        'recordTokenLeaseOverride:\n  mode: "shadow"\n  servePercent: "0"\n  seconds: "3600"\n',
        'recordTokenLeaseOverride:\n  mode: "off"\n  servePercent: "0"\n  seconds: "3600"\n  deployedAt: "0"\n  x: "1"\n',
        'recordTokenLeaseOverride: shadow\n',
        # Serve is reached only through the coordinated shared ramp (SCA-4463).
        'recordTokenLeaseOverride:\n  mode: "serve"\n  servePercent: "1"\n  seconds: "3600"\n  deployedAt: "1"\n',
        'recordTokenLeaseOverride:\n  mode: "serve"\n  servePercent: "0"\n  seconds: "3600"\n  deployedAt: "1"\n',
        'recordTokenLeaseOverride:\n  mode: "shadow"\n  servePercent: "1"\n  seconds: "3600"\n  deployedAt: "1"\n',
        'recordTokenLeaseOverride:\n  mode: "off"\n  servePercent: "100"\n  seconds: "3600"\n  deployedAt: "0"\n',
        'recordTokenLeaseOverride:\n  mode: "shadow"\n  servePercent: "00"\n  seconds: "3600"\n  deployedAt: "1"\n',
    ],
)
def test_pusher_chart_refuses_an_invalid_override(tmp_path, raw):
    assert _render_pusher('-f', str(_override_file(tmp_path, raw=raw))).returncode != 0


def test_pusher_chart_accepts_an_off_override_with_a_zero_epoch(tmp_path):
    vector = {'mode': 'off', 'servePercent': '0', 'seconds': '3600', 'deployedAt': '0'}
    result = _render_pusher('-f', str(_override_file(tmp_path, vector)))
    assert result.returncode == 0, result.stderr
    container = _pusher_container(result.stdout)
    assert _override_module().check_rendered(container, vector, config_map='prod-omi-backend-config') == []


def _shared_binding_code():
    action = yaml.safe_load((ROOT / '.github/actions/deploy-backend-stack/action.yml').read_text())
    step = next(
        step for step in action['runs']['steps'] if step.get('name') == 'Bind shared record token lease rollout inputs'
    )
    code = step['run'].split("python3 - <<'PYTHON'\n", 1)[1].rsplit('PYTHON', 1)[0]
    return code


@pytest.mark.parametrize(
    'vector,valid',
    [
        (('shadow', '0', '3600', '1795662310'), True),
        (('shadow', '0', '1800', '2000000000'), True),
        (('off', '0', '7200', '0'), True),
        (('shadow', '0', '3600', '0'), False),
        (('typo', '0', '3600', '1'), False),
        (('shadow', '101', '3600', '1'), False),
        (('shadow', '0', '1799', '1'), False),
        (('shadow', '0', '7201', '1'), False),
        (('shadow', '0', '3600', 'nan'), False),
        (('shadow', '+5', '3600', '1'), False),
        (('shadow', '0', '3600', '1.5'), False),
        (('shadow', '0', '', '1'), False),
        (('none', '0', '', ''), False),
    ],
)
def test_override_vector_uses_the_shared_binding_rules_strictly(monkeypatch, tmp_path, vector, valid):
    override = _override_module()
    if not valid:
        with pytest.raises(override.OverrideError):
            override.parse_vector(*vector)
        return
    parsed = override.parse_vector(*vector)
    assert parsed == dict(zip(override.INPUT_ENV, vector))
    # Every accepted override is also accepted, and materialized identically, by
    # the shared ConfigMap binding the backend stack and listen use.
    for key, value in zip(LEASE_ENV_NAMES, vector):
        monkeypatch.setenv(key, value)
    target = tmp_path / 'shared-env'
    monkeypatch.setenv('GITHUB_ENV', str(target))
    exec(compile(_shared_binding_code(), '<shared binding>', 'exec'), {})
    assert dict(line.split('=', 1) for line in target.read_text().splitlines()) == dict(zip(LEASE_ENV_NAMES, vector))


@pytest.mark.parametrize(
    'vector,message',
    [
        (('serve', '1', '3600', '1795662310'), 'cannot serve'),
        (('serve', '0', '3600', '1795662310'), 'cannot serve'),
        (('serve', '100', '1800', '2000000000'), 'cannot serve'),
        (('shadow', '1', '3600', '1795662310'), 'exactly 0'),
        (('shadow', '100', '3600', '1795662310'), 'exactly 0'),
        (('off', '50', '3600', '0'), 'exactly 0'),
        (('shadow', '00', '3600', '1795662310'), 'exactly 0'),
    ],
)
def test_override_refuses_pusher_only_serve(tmp_path, vector, message):
    """SCA-4463: a Pusher-only serve would turn on prepare_recovery for Pusher's
    cohort while the other readers are off; serve is shared-ramp only."""
    override = _override_module()
    with pytest.raises(override.OverrideError, match=message):
        override.parse_vector(*vector)
    github_env = tmp_path / 'github-env'
    github_env.write_text('PREVIOUS=kept\n')
    environ = dict(zip(override.INPUT_ENV.values(), vector))
    with pytest.raises(override.OverrideError, match=message):
        override.bind('prod', 'pusher', tmp_path / 'serve.yaml', environ, github_env)
    assert github_env.read_text() == 'PREVIOUS=kept\n'
    assert not (tmp_path / 'serve.yaml').exists()


def test_no_override_binds_nothing_and_an_override_binds_a_rendered_values_file(tmp_path):
    override = _override_module()
    github_env = tmp_path / 'github-env'
    message = override.bind(
        'prod', 'pusher', tmp_path / 'none.yaml', {'PUSHER_LEASE_OVERRIDE_MODE': 'none'}, github_env
    )
    assert 'keep their shared ConfigMap references' in message
    assert github_env.read_text() == 'PUSHER_RECORD_TOKEN_LEASE_OVERRIDE=absent\n'
    assert not (tmp_path / 'none.yaml').exists()

    github_env.write_text('')
    output = tmp_path / 'bound.yaml'
    environ = {name: value for name, value in zip(override.INPUT_ENV.values(), SHADOW_OVERRIDE.values())}
    message = override.bind('prod', 'pusher', output, environ, github_env)
    assert yaml.safe_load(output.read_text()) == {'recordTokenLeaseOverride': SHADOW_OVERRIDE}
    assert github_env.read_text() == (
        f'PUSHER_RECORD_TOKEN_LEASE_OVERRIDE=active\nPUSHER_RECORD_TOKEN_LEASE_OVERRIDE_VALUES={output}\n'
    )
    assert 'RECORD_TOKEN_LEASE_MODE=shadow' in message and 'is not written' in message


def test_bind_fails_closed_for_another_service_or_a_chart_that_ignores_the_override(monkeypatch, tmp_path):
    override = _override_module()
    environ = {name: value for name, value in zip(override.INPUT_ENV.values(), SHADOW_OVERRIDE.values())}
    github_env = tmp_path / 'github-env'
    github_env.write_text('PREVIOUS=kept\n')
    with pytest.raises(override.OverrideError, match='only to the pusher service'):
        override.bind('dev', 'llm-gateway', tmp_path / 'x.yaml', environ, github_env)
    # A pinned runtime source whose chart predates the block renders the shared references.
    monkeypatch.setattr(override, 'render', lambda environment, values_file: _documents(_render_pusher().stdout))
    with pytest.raises(override.OverrideError, match='does not honor the override'):
        override.bind('prod', 'pusher', tmp_path / 'y.yaml', environ, github_env)
    assert github_env.read_text() == 'PREVIOUS=kept\n'


def test_receipt_render_and_config_parity_follow_the_bound_override(tmp_path):
    from scripts import pusher_release_receipt as receipt

    override_file = _override_file(tmp_path)
    documents = receipt.rendered_chart_documents(
        'prod', 'gcr.io/based-hardware/pusher', RENDER_DIGEST, extra_values=override_file
    )
    container = _override_module().pusher_container(documents)
    assert _override_module().check_rendered(container, SHADOW_OVERRIDE, config_map='prod-omi-backend-config') == []
    assert receipt.rendered_chart_fingerprint(
        'prod', 'gcr.io/based-hardware/pusher', RENDER_DIGEST
    ) != receipt.rendered_chart_fingerprint(
        'prod', 'gcr.io/based-hardware/pusher', RENDER_DIGEST, extra_values=override_file
    )

    live = {'metadata': {'name': 'prod-omi-backend-config'}, 'data': {'RECORD_TOKEN_LEASE_MODE': 'off'}}
    qualified = receipt.config_fingerprint(live, expected_name='prod-omi-backend-config')
    assert (
        receipt.verify_config_matches_receipt(
            live, {'config_sha256': qualified}, expected_name='prod-omi-backend-config'
        )
        == qualified
    )
    drifted = {**live, 'data': {'RECORD_TOKEN_LEASE_MODE': 'shadow'}}
    with pytest.raises(receipt.ReceiptError, match='differs from the canary-qualified ConfigMap'):
        receipt.verify_config_matches_receipt(
            drifted, {'config_sha256': qualified}, expected_name='prod-omi-backend-config'
        )
    with pytest.raises(receipt.ReceiptError, match='no config_sha256'):
        receipt.verify_config_matches_receipt(live, {}, expected_name='prod-omi-backend-config')


def _pusher_deploy_steps():
    steps = _workflow(PUSHER_WORKFLOW)['jobs']['deploy']['steps']
    return {step['name']: (index, step) for index, step in enumerate(steps)}


def test_pusher_workflow_threads_the_override_into_every_pusher_render_and_skips_the_shared_writer():
    config = _workflow(PUSHER_WORKFLOW)
    inputs = config[True]['workflow_dispatch']['inputs']
    assert inputs['pusher_record_token_lease_override_mode']['default'] == 'none'
    assert inputs['pusher_record_token_lease_override_mode']['options'] == ['none', 'off', 'shadow']
    for suffix in ('serve_percent', 'seconds', 'deployed_at'):
        assert inputs[f'pusher_record_token_lease_override_{suffix}']['default'] == ''
    steps = _pusher_deploy_steps()
    admit, _ = steps['Admit checked-out production source and image identity']
    bind_index, bind = steps['Bind Pusher-scoped record token lease override']
    assert admit < bind_index and 'if' not in bind
    # Free-text inputs reach the step only through env, never inline interpolation.
    assert '${{' not in bind['run'].replace('${{ vars.ENV }}', '').replace('${{ env.SERVICE }}', '')
    assert 'pusher_record_token_lease_override.py bind' in bind['run']
    values = 'PUSHER_RECORD_TOKEN_LEASE_OVERRIDE_VALUES'
    users = {
        'Create isolated production Pusher and listener canary': 2,
        'Verify live Pusher surge capacity and digest render': 1,
        'Deploy Pusher to GKE cluster using Helm': 1,
        'Record exact live production Pusher deployment receipt': 1,
    }
    for name, count in users.items():
        index, step = steps[name]
        assert bind_index < index, name
        assert step['run'].count(f'"${values}"') == count, name
    canary_run = steps['Create isolated production Pusher and listener canary'][1]['run']
    assert '"${lease_override_values[@]}"' in canary_run.split('kubectl -n prod-omi-backend rollout status')[0]
    assert values not in canary_run.split('pusher_prod_canary.py create-listener')[1]
    # The shared ConfigMap writer is the only one skipped; the isolated canary map
    # is still rendered from the same shared vector.
    shared_index, shared = steps['Apply non-secret pusher runtime config']
    assert shared['if'].endswith("&& env.PUSHER_RECORD_TOKEN_LEASE_OVERRIDE != 'active'")
    canary_config = steps['Create isolated proposed production Pusher ConfigMap'][1]
    assert 'OVERRIDE' not in str(canary_config['if']) and values not in canary_config['run']
    parity_index, parity = steps['Verify the kept shared ConfigMap is the canary-qualified ConfigMap']
    helm_index, _ = steps['Deploy Pusher to GKE cluster using Helm']
    assert shared_index < parity_index < helm_index
    assert parity['if'].endswith("&& env.PUSHER_RECORD_TOKEN_LEASE_OVERRIDE == 'active'")
    assert 'verify-config' in parity['run'] and 'pusher-prod-canary-deployment-receipt.json' in parity['run']
    # Listen never reads the Pusher override.
    assert 'record_token_lease_override' not in (ROOT / '.github/workflows/gcp_backend_listen_helm.yml').read_text()
