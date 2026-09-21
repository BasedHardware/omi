"""Independent default-off switches for the three PR #14165 basic-plan gates.

Import-light: readers and composed YAML only. Behavioral OFF/ON coverage for
each gate lives next to the existing #14165 tests (those files already pay for
the heavy router / coordinator imports in module-scoped fixtures).
"""

from __future__ import annotations

import copy
import functools
from pathlib import Path

import pytest
import yaml

from config.free_tier_rollout import validate_free_tier_deploy_value
from scripts.runtime_env_capability_contracts import validate_free_tier_deploy_contract
from utils.free_tier_basic_gates import (
    BASIC_PLAN_GATE_EAGER_EXTRACTION_ENABLED,
    BASIC_PLAN_GATE_PROACTIVITY_ENABLED,
    BASIC_PLAN_GATE_PROXY_EMBED_ENABLED,
    basic_plan_gate_eager_extraction_enabled,
    basic_plan_gate_proactivity_enabled,
    basic_plan_gate_proxy_embed_enabled,
)
from utils.free_tier_cohort import EMERGENCY_STOP_ENV_VAR, parse_cohort

BACKEND = Path(__file__).resolve().parents[2]
_READERS = (
    (BASIC_PLAN_GATE_PROACTIVITY_ENABLED, basic_plan_gate_proactivity_enabled),
    (BASIC_PLAN_GATE_PROXY_EMBED_ENABLED, basic_plan_gate_proxy_embed_enabled),
    (BASIC_PLAN_GATE_EAGER_EXTRACTION_ENABLED, basic_plan_gate_eager_extraction_enabled),
)


@functools.cache
def _composed() -> dict:
    return yaml.safe_load((BACKEND / 'deploy/runtime_env.yaml').read_text(encoding='utf-8'))


@pytest.fixture(autouse=True)
def _clear_gate_env(monkeypatch):
    for name, _reader in _READERS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv(EMERGENCY_STOP_ENV_VAR, raising=False)


# red-proof: treat ``'1'`` / ``'yes'`` / ``'on'`` as on
@pytest.mark.parametrize('name, reader', _READERS)
@pytest.mark.parametrize(
    'value, expected',
    [
        ('true', True),
        ('TRUE', True),
        ('True', True),
        ('false', False),
        ('1', False),
        ('yes', False),
        ('on', False),
        ('', False),
        (None, False),
    ],
)
def test_env_parse_accepts_only_true_case_insensitive(monkeypatch, name, reader, value, expected) -> None:
    if value is None:
        monkeypatch.delenv(name, raising=False)
    else:
        monkeypatch.setenv(name, value)
    assert reader() is expected


@pytest.mark.parametrize('name, reader', _READERS)
def test_emergency_stop_revokes_a_lit_gate(monkeypatch, name, reader) -> None:
    monkeypatch.setenv(name, 'true')
    assert reader() is True
    monkeypatch.setenv(EMERGENCY_STOP_ENV_VAR, 'true')
    assert reader() is False


def test_the_three_switches_are_independent(monkeypatch) -> None:
    """Lighting one gate does not light the other two."""
    monkeypatch.setenv(BASIC_PLAN_GATE_PROACTIVITY_ENABLED, 'true')
    assert basic_plan_gate_proactivity_enabled() is True
    assert basic_plan_gate_proxy_embed_enabled() is False
    assert basic_plan_gate_eager_extraction_enabled() is False

    monkeypatch.delenv(BASIC_PLAN_GATE_PROACTIVITY_ENABLED)
    monkeypatch.setenv(BASIC_PLAN_GATE_PROXY_EMBED_ENABLED, 'true')
    assert basic_plan_gate_proactivity_enabled() is False
    assert basic_plan_gate_proxy_embed_enabled() is True
    assert basic_plan_gate_eager_extraction_enabled() is False

    monkeypatch.delenv(BASIC_PLAN_GATE_PROXY_EMBED_ENABLED)
    monkeypatch.setenv(BASIC_PLAN_GATE_EAGER_EXTRACTION_ENABLED, 'true')
    assert basic_plan_gate_proactivity_enabled() is False
    assert basic_plan_gate_proxy_embed_enabled() is False
    assert basic_plan_gate_eager_extraction_enabled() is True


def test_readers_re_read_env_at_call_time(monkeypatch) -> None:
    assert basic_plan_gate_proactivity_enabled() is False
    monkeypatch.setenv(BASIC_PLAN_GATE_PROACTIVITY_ENABLED, 'true')
    assert basic_plan_gate_proactivity_enabled() is True
    monkeypatch.setenv(BASIC_PLAN_GATE_PROACTIVITY_ENABLED, 'false')
    assert basic_plan_gate_proactivity_enabled() is False


def _literal(env_map: dict, key: str) -> str:
    entry = env_map.get(key) or {}
    return str(entry.get('value') or '')


def test_dev_lights_each_gate_on_the_identities_that_run_its_code_path() -> None:
    dev = _composed()['environments']['dev']
    desktop = dev['desktop_backend']['env']
    backend = dev['cloud_run']['services']['backend']['env']
    assert _literal(desktop, BASIC_PLAN_GATE_PROACTIVITY_ENABLED) == 'true'
    assert _literal(desktop, BASIC_PLAN_GATE_PROXY_EMBED_ENABLED) == 'true'
    assert _literal(backend, BASIC_PLAN_GATE_PROXY_EMBED_ENABLED) == 'true'
    assert _literal(backend, BASIC_PLAN_GATE_EAGER_EXTRACTION_ENABLED) == 'true'


def test_prod_states_all_three_gates_false_on_every_identity_that_declares_them() -> None:
    prod = _composed()['environments']['prod']
    desktop = prod['desktop_backend']['env']
    backend = prod['cloud_run']['services']['backend']['env']
    listen = prod['gke']['backend-listen']['env']
    pusher = prod['gke']['pusher']['env']
    sync = prod['cloud_run']['services']['backend-sync']['env']
    assert _literal(desktop, BASIC_PLAN_GATE_PROACTIVITY_ENABLED) == 'false'
    assert _literal(desktop, BASIC_PLAN_GATE_PROXY_EMBED_ENABLED) == 'false'
    assert _literal(backend, BASIC_PLAN_GATE_PROXY_EMBED_ENABLED) == 'false'
    for env_map in (listen, pusher, backend, sync):
        assert _literal(env_map, BASIC_PLAN_GATE_EAGER_EXTRACTION_ENABLED) == 'false'


def test_proactivity_is_not_declared_on_process_conversation_hosts() -> None:
    """desktop_proactivity.router is mounted only by desktop_backend.py."""
    prod = _composed()['environments']['prod']
    for env_map in (
        prod['gke']['backend-listen']['env'],
        prod['gke']['pusher']['env'],
        prod['cloud_run']['services']['backend']['env'],
        prod['cloud_run']['services']['backend-sync']['env'],
    ):
        assert BASIC_PLAN_GATE_PROACTIVITY_ENABLED not in env_map


def test_each_gate_site_calls_only_its_own_reader() -> None:
    proactivity = (BACKEND / 'routers/desktop_proactivity.py').read_text(encoding='utf-8')
    proxy = (BACKEND / 'routers/desktop_proxy.py').read_text(encoding='utf-8')
    coordinator = (BACKEND / 'utils/conversations/process_conversation.py').read_text(encoding='utf-8')
    assert 'basic_plan_gate_proactivity_enabled()' in proactivity
    assert 'basic_plan_gate_proxy_embed_enabled' not in proactivity
    assert 'basic_plan_gate_eager_extraction_enabled' not in proactivity
    assert 'basic_plan_gate_proxy_embed_enabled()' in proxy
    assert 'basic_plan_gate_proactivity_enabled' not in proxy
    assert 'basic_plan_gate_eager_extraction_enabled' not in proxy
    assert 'basic_plan_gate_eager_extraction_enabled()' in coordinator
    assert 'basic_plan_gate_proactivity_enabled' not in coordinator
    assert 'basic_plan_gate_proxy_embed_enabled' not in coordinator


# #14316's explicit per-host rollout contract, extended for AFM-only Stage 1.
# This independent roster also catches omissions from the deploy validator.
_FREE_TIER_HOST_PATHS = (
    ('gke', 'backend-listen'),
    ('gke', 'pusher'),
    ('cloud_run', 'services', 'backend'),
    ('cloud_run', 'services', 'backend-sync'),
    ('cloud_run', 'services', 'backend-sync-backfill'),
    ('cloud_run', 'services', 'backend-integration'),
    ('desktop_backend',),
)
_FREE_TIER_KEYS = ('FREE_TIER_LOCAL_PROCESSING', 'FREE_TIER_LOCAL_PROCESSING_COHORT', 'FREE_TIER_EMERGENCY_STOP')


def _host_env(config, path):
    for part in path:
        config = config[part]
    return config['env']


@pytest.mark.parametrize('environment', ('dev', 'prod'))
@pytest.mark.parametrize('path', _FREE_TIER_HOST_PATHS)
def test_local_processing_deploy_values_and_memory_suppression_stays_unset(environment, path):
    entries = _host_env(_composed()['environments'][environment], path)
    assert entries['FREE_TIER_LOCAL_PROCESSING']['value'] == ('true' if environment == 'dev' else 'false')
    assert entries['FREE_TIER_EMERGENCY_STOP']['value'] == 'false'
    cohort = entries['FREE_TIER_LOCAL_PROCESSING_COHORT']
    if environment == 'prod':
        assert cohort == {'category': 'rollout', 'value': ''}
    elif path[0] == 'gke':
        assert cohort['config_map'] == {'name': 'dev-omi-backend-config', 'key': 'FREE_TIER_LOCAL_PROCESSING_COHORT'}
    else:
        assert cohort == {'category': 'rollout', 'env_var': 'FREE_TIER_LOCAL_PROCESSING_COHORT', 'default': ''}
    assert 'FREE_TIER_MEMORY_SUPPRESSION' not in entries
    assert 'FREE_TIER_MEMORY_SUPPRESSION_COHORT' not in entries


@pytest.mark.parametrize('environment', ('dev', 'prod'))
@pytest.mark.parametrize('path', _FREE_TIER_HOST_PATHS)
@pytest.mark.parametrize('key', _FREE_TIER_KEYS)
def test_free_tier_deploy_validator_rejects_missing_key(environment, path, key, monkeypatch):
    config = copy.deepcopy(_composed()['environments'][environment])
    monkeypatch.delenv('FREE_TIER_LOCAL_PROCESSING_COHORT', raising=False)
    assert validate_free_tier_deploy_contract(environment, config) == []
    del _host_env(config, path)[key]
    assert any(key in error.message for error in validate_free_tier_deploy_contract(environment, config))


@pytest.mark.parametrize('value', ['', ' ', 'uid:fixture-a', 'uid:fixture-a,uid:fixture-b', ' UID : fixture:a '])
def test_deploy_uid_grammar_matches_runtime_subset(value):
    validate_free_tier_deploy_value('FREE_TIER_LOCAL_PROCESSING_COHORT', value)
    parsed = parse_cohort(value)
    if value.strip():
        assert parsed is not None
        assert parsed.uids
        assert parsed.pct == 0
    else:
        assert parsed is None


@pytest.mark.parametrize(
    'value',
    [
        'uid:',
        'uid: ',
        'fixture-a',
        ',uid:fixture-a',
        'uid:fixture-a,',
        'uid:fixture-a,,uid:fixture-b',
        'pct:1',
        'uid:fixture-a,pct:0',
        'uid:fixture-a\nINJECTED=true',
    ],
)
def test_deploy_rejects_malformed_or_percentage_cohorts_without_logging_accounts(value):
    with pytest.raises(ValueError) as error:
        validate_free_tier_deploy_value('FREE_TIER_LOCAL_PROCESSING_COHORT', value)
    assert 'fixture-a' not in str(error.value)


@pytest.mark.parametrize('key', ('FREE_TIER_LOCAL_PROCESSING', 'FREE_TIER_EMERGENCY_STOP'))
@pytest.mark.parametrize('value', ['true', 'false', 'TRUE', '1', 'on', '', ' true '])
def test_deploy_booleans_require_exact_literals(key, value):
    if value in {'true', 'false'}:
        validate_free_tier_deploy_value(key, value)
    else:
        with pytest.raises(ValueError, match="must be exactly 'true' or 'false'"):
            validate_free_tier_deploy_value(key, value)


@pytest.mark.parametrize('environment', ('dev', 'prod'))
def test_helm_source_values_carry_every_free_tier_binding(environment):
    """Static chart-input contract; no Helm or cluster access is needed."""
    for service, stem in [('backend-listen', 'backend_listen'), ('pusher', 'pusher')]:
        values = yaml.safe_load((BACKEND / f'charts/{service}/{environment}_omi_{stem}_values.yaml').read_text())
        entries = {entry['name']: entry for entry in values['env']}
        assert entries['FREE_TIER_LOCAL_PROCESSING']['value'] == ('true' if environment == 'dev' else 'false')
        assert entries['FREE_TIER_EMERGENCY_STOP']['value'] == 'false'
        cohort = entries['FREE_TIER_LOCAL_PROCESSING_COHORT']
        if environment == 'dev':
            # `optional` is load-bearing: a pod that starts before the backend lane has
            # written the key must start dark (unset == admit nobody), not fail to start.
            assert cohort['valueFrom']['configMapKeyRef'] == {
                'name': 'dev-omi-backend-config',
                'key': 'FREE_TIER_LOCAL_PROCESSING_COHORT',
                'optional': True,
            }
        else:
            assert cohort['value'] == ''


def test_actions_variable_reaches_renderers_and_desktop_deploy_without_shell_interpolation():
    """Static wiring tripwire extending #14316's deployment assertions."""
    repo = BACKEND.parent
    key = 'FREE_TIER_LOCAL_PROCESSING_COHORT'
    binding = '${{ vars.DEV_FREE_TIER_LOCAL_PROCESSING_COHORT }}'
    action = yaml.safe_load((repo / '.github/actions/deploy-backend-stack/action.yml').read_text())
    steps = {step['name']: step for step in action['runs']['steps']}
    # A composite action cannot read `vars`; referencing it makes the action fail to
    # LOAD, which stopped every backend deploy on 2026-09-21. It takes an input, and
    # only the calling workflows read the variable.
    action_binding = '${{ inputs.dev_free_tier_local_processing_cohort }}'
    assert action['inputs']['dev_free_tier_local_processing_cohort']['default'] == ''
    for name in (
        'Render backend runtime env',
        'Validate backend runtime env before deploy',
        'Apply non-secret backend runtime config',
    ):
        assert steps[name]['env'][key] == action_binding
    callers = {
        'gcp_backend_auto_dev.yml': binding,
        'gcp_backend.yml': "${{ github.event.inputs.environment == 'development' && vars.DEV_FREE_TIER_LOCAL_PROCESSING_COHORT || '' }}",
    }
    for filename, expected in callers.items():
        workflow = yaml.safe_load((repo / '.github/workflows' / filename).read_text())
        uses = [
            step
            for job in workflow['jobs'].values()
            for step in job.get('steps', [])
            if step.get('uses') == './.github/actions/deploy-backend-stack'
        ]
        assert uses
        for step in uses:
            assert step['with']['dev_free_tier_local_processing_cohort'] == expected
    for filename in ('gcp_backend_listen_helm.yml', 'gcp_backend_pusher.yml'):
        workflow = yaml.safe_load((repo / '.github/workflows' / filename).read_text())
        config_steps = [
            step
            for job in workflow['jobs'].values()
            for step in job.get('steps', [])
            if any(
                line.strip().endswith('backend/scripts/deploy-backend-config.sh')
                for line in step.get('run', '').splitlines()
            )
        ]
        assert config_steps
        for step in config_steps:
            assert step['env'][key] == binding
    for environment, filename in [('dev', 'desktop_backend_auto_dev.yml'), ('prod', 'desktop_backend_prod.yml')]:
        workflow = yaml.safe_load((repo / '.github/workflows' / filename).read_text())
        steps = [step for job in workflow['jobs'].values() for step in job.get('steps', [])]
        renderer = next(step for step in steps if step.get('id') == 'desktop-expected-env')
        deploy = next(step for step in steps if 'google-github-actions/deploy-cloudrun@' in step.get('uses', ''))
        assert steps.index(renderer) < steps.index(deploy)
        if environment == 'dev':
            assert renderer['env'][key] == binding
        else:
            # `vars` falls back from environment to repository scope, so production
            # must not read a cohort variable at all, under any name.
            assert key not in renderer.get('env', {})
            assert 'FREE_TIER_LOCAL_PROCESSING_COHORT }}' not in (repo / '.github/workflows' / filename).read_text()
        assert '"$GITHUB_OUTPUT"' in renderer['run']
        deployed = dict(line.strip().split('=', 1) for line in deploy['with']['env_vars'].splitlines() if '=' in line)
        assert deployed['FREE_TIER_LOCAL_PROCESSING'] == ('true' if environment == 'dev' else 'false')
        assert deployed['FREE_TIER_EMERGENCY_STOP'] == 'false'
        assert deployed[key] == (
            '${{ steps.desktop-expected-env.outputs.free_tier_local_processing_cohort }}'
            if environment == 'dev'
            else ''
        )
        assert 'FREE_TIER_MEMORY_SUPPRESSION' not in deployed


@pytest.mark.parametrize('path', _FREE_TIER_HOST_PATHS)
@pytest.mark.parametrize(
    'key,value', [('FREE_TIER_LOCAL_PROCESSING', 'true'), ('FREE_TIER_LOCAL_PROCESSING_COHORT', 'uid:fixture-a')]
)
def test_production_admission_rejects_activation_on_any_host(path, key, value):
    config = copy.deepcopy(_composed()['environments']['prod'])
    _host_env(config, path)[key]['value'] = value
    assert any(
        'must remain dark in prod' in error.message for error in validate_free_tier_deploy_contract('prod', config)
    )


def test_no_composite_action_reads_a_context_it_cannot_access():
    """`vars` and `secrets` do not exist inside a composite action.

    GitHub rejects the whole action at load time ("Unrecognized named-value"), so the
    failure is not the step that used it but every workflow that calls the action.
    YAML parsing and string-level wiring tests both pass on such a file.
    """
    import re

    repo = BACKEND.parent
    offenders = []
    for path in sorted((repo / '.github/actions').glob('*/action.y*ml')):
        action = yaml.safe_load(path.read_text())
        if (action.get('runs') or {}).get('using') != 'composite':
            continue
        for number, line in enumerate(path.read_text().splitlines(), 1):
            for expression in re.findall(r'\$\{\{(.*?)\}\}', line):
                if re.search(r'(?<![\w.])(vars|secrets)\.', expression):
                    offenders.append(f'{path.relative_to(repo)}:{number}: {expression.strip()}')
    assert not offenders, 'composite actions cannot read vars/secrets; pass an input instead:\n' + '\n'.join(offenders)
