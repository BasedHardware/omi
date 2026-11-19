"""SCA-3120: backend-projection-pump is an explicit-only, dark, internal fifth Cloud Run target.

Offline: these tests read the checked-in workflow, composite, manifest and scripts, and run
the boundary shell with fixture inputs. Nothing here calls a cloud API.
"""

from __future__ import annotations

import copy
import json
import os
import runpy
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts import resolve_service_images as images
from scripts import verify_backend_release_vector as vector
from scripts import verify_projection_pump_shape as shape
from scripts.cloud_run_scope import PROJECTION_PUMP, SELECTABLE, SERVICES, selected

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / 'backend'
WORKFLOW = yaml.safe_load((ROOT / '.github/workflows/gcp_backend.yml').read_text())
PUMP_ACTION = yaml.safe_load((ROOT / '.github/actions/deploy-projection-pump/action.yml').read_text())
STACK_ACTION_TEXT = (ROOT / '.github/actions/deploy-backend-stack/action.yml').read_text()
MANIFEST = yaml.safe_load((BACKEND / 'deploy/runtime_env.yaml').read_text())
COMPOSER = runpy.run_path(str(BACKEND / 'deploy/compose_runtime_env.py'))
RENDERER = runpy.run_path(str(BACKEND / 'scripts/render_backend_runtime_env.py'), run_name='render_pump_fixture')
STAGING_INPUTS = {'STAGING_REDIS_HOST': '10.0.0.7'}
FOUR = ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration')
DARK_OVERRIDES = {
    'BATCH_PIPELINE_SERVING_ENABLED': 'false',
    'BATCH_PIPELINE_PROJECTION_PUMP_ENABLED': 'false',
    'BATCH_PIPELINE_PUMP_SWEEP_PAGES': '1',
    'BATCH_PIPELINE_PUMP_TICK_SECONDS': '2',
    'BATCH_PIPELINE_MAX_OWNER_DRAINS': '8',
    'FIRESTORE_READ_LEDGER_SERVICE': 'backend-projection-pump',
}


def _prod_services():
    return MANIFEST['environments']['prod']['cloud_run']['services']


# --- selection boundary -------------------------------------------------------------------


def test_all_still_selects_exactly_the_four_services():
    assert SERVICES == FOUR
    assert selected() == FOUR
    assert selected('all') == FOUR
    assert PROJECTION_PUMP not in selected('all')
    assert SELECTABLE == (*FOUR, PROJECTION_PUMP)


def test_projection_pump_is_a_singleton_selection():
    assert selected(PROJECTION_PUMP) == (PROJECTION_PUMP,)
    with pytest.raises(ValueError):
        selected('backend-projection-pumps')


def _boundary(tmp_path, **overrides):
    script = WORKFLOW['jobs']['validate-production-boundary']['steps'][0]['run']
    script = script.replace('${{ github.event.inputs.deploy_gateway }}', 'false')
    assert '${{' not in script
    output = tmp_path / 'outputs'
    env = dict(
        os.environ,
        DEPLOY_ENVIRONMENT='prod',
        DEPLOY_TARGETS='cloud-run-only',
        WORKFLOW_MODE='deploy',
        CLOUD_RUN_SERVICE=PROJECTION_PUMP,
        SERVICE_IMAGES='',
        REQUESTED_BY='fixture',
        RELEASE_SHA='a' * 40,
        SKIP_ELIGIBILITY='false',
        BREAK_GLASS_LOCK='false',
        GITHUB_OUTPUT=str(output),
    )
    env.update(overrides)
    return subprocess.run(['bash', '-c', script], env=env, text=True, capture_output=True, timeout=10), output


def test_boundary_admits_the_pump_for_a_manual_prod_cloud_run_only_deploy(tmp_path):
    result, output = _boundary(tmp_path)
    assert result.returncode == 0, result.stderr
    assert 'integration_only=false' in output.read_text()


@pytest.mark.parametrize(
    'extra',
    [
        {'DEPLOY_ENVIRONMENT': 'development'},
        {'DEPLOY_TARGETS': 'all'},
        {'WORKFLOW_MODE': 'build-only'},
        {'BREAK_GLASS_LOCK': 'true'},
        {'SKIP_ELIGIBILITY': 'true'},
        {'SERVICE_IMAGES': f'{PROJECTION_PUMP}=gcr.io/based-hardware/backend@sha256:' + 'a' * 64},
        {'SERVICE_IMAGES': 'integration-canary=gcr.io/based-hardware/backend@sha256:' + 'a' * 64},
    ],
)
def test_boundary_refuses_every_other_pump_dispatch_before_side_effects(tmp_path, extra):
    result, output = _boundary(tmp_path, **extra)
    assert result.returncode != 0
    assert not output.exists()


def test_workflow_input_offers_the_pump_but_defaults_to_all():
    choice = WORKFLOW[True]['workflow_dispatch']['inputs']['cloud_run_service']
    assert choice['default'] == 'all'
    assert choice['options'] == ['all', *FOUR, PROJECTION_PUMP]


def test_stack_deploy_job_never_runs_for_the_pump_and_the_pump_job_is_prod_only():
    jobs = WORKFLOW['jobs']
    stack = ' '.join(jobs['deploy']['if'].split())
    assert "github.event.inputs.cloud_run_service != 'backend-projection-pump'" in stack
    pump = jobs['deploy-projection-pump']
    condition = ' '.join(pump['if'].split())
    assert "github.event.inputs.cloud_run_service == 'backend-projection-pump'" in condition
    assert "github.event.inputs.environment == 'prod'" in condition
    assert "github.event.inputs.mode == 'deploy'" in condition
    assert "github.ref == 'refs/heads/main'" in condition
    assert pump['needs'] == jobs['deploy']['needs']
    assert pump['environment'] == 'prod'
    assert [step.get('uses') for step in pump['steps']] == [
        'actions/checkout@v7',
        './.github/actions/deploy-projection-pump',
    ]
    # Same workflow-level prod-train concurrency group as every other deploy job.
    assert 'concurrency' not in pump


def test_four_service_stack_composite_never_names_the_pump():
    assert PROJECTION_PUMP not in STACK_ACTION_TEXT
    assert 'projection_pump' not in STACK_ACTION_TEXT


# --- image and release vector ---------------------------------------------------------------


def _resolve(service, raw=''):
    return images.resolve(
        raw,
        project='based-hardware',
        short_sha='aaaaaaa',
        admitted_sha='a' * 40,
        deploy_targets='cloud-run-only',
        deploy_gateway=False,
        cloud_run_service=service,
        registry={'services': {}},
        inspect=lambda _ref: pytest.fail('the pump never inspects a role image'),
    )


def test_pump_image_is_the_admitted_fat_image_and_all_keys_are_unchanged():
    pump = _resolve(PROJECTION_PUMP)
    assert pump['backend_projection_pump'] == 'gcr.io/based-hardware/backend:aaaaaaa'
    assert pump['opted_in'] == '' and pump['release_vector_args'] == ''
    assert 'backend_projection_pump' not in _resolve('all')
    assert 'backend_projection_pump' not in _resolve('backend-integration')


def test_pump_refuses_role_image_pairs():
    raw = 'backend-integration=gcr.io/based-hardware/backend@sha256:' + 'a' * 64
    with pytest.raises(images.ServiceImageError):
        _resolve(PROJECTION_PUMP, raw)


def test_release_vector_expects_only_the_pump_revision():
    expectation = vector.build_expectation(
        commit_sha='a' * 40,
        deploy_run_id='17',
        deploy_run_attempt='1',
        project='based-hardware',
        region='us-central1',
        environment='prod',
        cloud_run_service=PROJECTION_PUMP,
    )
    assert expectation.revisions == {PROJECTION_PUMP: 'backend-projection-pump-aaaaaaa-17-1'}
    assert expectation.image == 'gcr.io/based-hardware/backend:aaaaaaa'


# --- manifest composition -------------------------------------------------------------------


def test_prod_pump_is_integration_plus_the_dark_overrides():
    services = _prod_services()
    integration, pump = services['backend-integration'], services[PROJECTION_PUMP]
    assert list(services)[: len(FOUR)] == list(FOUR)
    assert pump['secrets'] == integration['secrets']
    assert pump['flags'] == integration['flags']
    assert pump['forbidden_env'] == integration['forbidden_env']
    assert pump['service_account'] == integration['service_account']
    overridden = set(DARK_OVERRIDES) | {'BATCH_PIPELINE_INDEPENDENT_LANGUAGE_RECOVERY_ENABLED'}
    assert set(pump['env']) - set(integration['env']) <= overridden
    for name in set(integration['env']) - overridden:
        assert pump['env'][name] == integration['env'][name], name
    for name, value in DARK_OVERRIDES.items():
        assert pump['env'][name]['value'] == value, name
    assert pump['env']['BATCH_PIPELINE_INDEPENDENT_LANGUAGE_RECOVERY_ENABLED']['value'] == 'false'


def test_pump_is_prod_only_and_staging_excludes_it_explicitly():
    assert PROJECTION_PUMP not in MANIFEST['environments']['dev']['cloud_run']['services']
    assert COMPOSER['STAGING_EXCLUDED_SERVICES'] == (PROJECTION_PUMP,)
    staging = COMPOSER['compose_staging'](inputs=STAGING_INPUTS)
    assert set(staging['cloud_run']['services']) == set(FOUR)


def test_staging_refuses_a_derived_service_it_does_not_exclude(tmp_path):
    runtime_env = tmp_path / 'runtime_env'
    runtime_env.mkdir()
    for path in (BACKEND / 'deploy/runtime_env').glob('*.yaml'):
        (runtime_env / path.name).write_text(path.read_text())
    prod = yaml.safe_load((runtime_env / 'prod.overlay.yaml').read_text())
    prod['overlay']['cloud_run']['services']['backend-shadow'] = {'derive_from': 'backend-integration'}
    (runtime_env / 'prod.overlay.yaml').write_text(yaml.safe_dump(prod, sort_keys=False))
    with pytest.raises(COMPOSER['StagingComposeError'], match='backend-shadow'):
        COMPOSER['compose_staging'](runtime_env_dir=runtime_env, inputs=STAGING_INPUTS)


def _env_config(services):
    return {'cloud_run': {'services': services}}


def test_derive_from_merges_own_keys_over_the_composed_source():
    config = _env_config(
        {
            'src': {'env': {'A': {'value': '1'}, 'B': {'value': '2'}}, 'secrets': {'S': {'secret': 'S'}}},
            'derived': {'derive_from': 'src', 'env': {'B': {'value': '3'}}},
        }
    )
    COMPOSER['_resolve_derived_services'](config)
    derived = config['cloud_run']['services']['derived']
    assert derived == {'env': {'A': {'value': '1'}, 'B': {'value': '3'}}, 'secrets': {'S': {'secret': 'S'}}}
    assert config['cloud_run']['services']['src']['env']['B'] == {'value': '2'}


@pytest.mark.parametrize(
    'services',
    [
        {'derived': {'derive_from': 'missing'}},
        {'a': {}, 'b': {'derive_from': 'a'}, 'c': {'derive_from': 'b'}},
        {'a': {}, 'c': {'derive_from': 'b'}, 'b': {'derive_from': 'a'}},
    ],
)
def test_derive_from_refuses_unknown_sources_and_chains(services):
    with pytest.raises(ValueError):
        COMPOSER['_resolve_derived_services'](_env_config(copy.deepcopy(services)))


# --- rendered env and deploy step ------------------------------------------------------------


@pytest.fixture
def prod_state(monkeypatch):
    # Deploy-time values (network, client IDs) come from the job environment; give fixtures.
    def walk(value):
        if isinstance(value, dict):
            if isinstance(value.get('env_var'), str):
                monkeypatch.setenv(value['env_var'], str(value.get('default', 'fixture-value')))
            for child in value.values():
                walk(child)

    walk(MANIFEST['environments']['prod']['cloud_run'])
    return RENDERER['_render_cloud_run_state'](MANIFEST['environments']['prod'])


def test_rendered_pump_env_is_dark_and_keeps_only_the_required_secrets(prod_state):
    state = prod_state
    pump = state['services'][PROJECTION_PUMP]
    rendered = {entry['name']: entry.get('value') for entry in pump['env'] if 'value' in entry}
    for name, value in DARK_OVERRIDES.items():
        assert rendered[name] == value, name
    assert shape.expected_env(state) == {
        'BATCH_PIPELINE_PROJECTION_PUMP_ENABLED': 'false',
        'FIRESTORE_READ_LEDGER_SERVICE': PROJECTION_PUMP,
    }
    secret_names = {entry['name'] for entry in pump['env'] if 'value' not in entry}
    integration = state['services']['backend-integration']
    assert secret_names == {entry['name'] for entry in integration['env'] if 'value' not in entry}
    # main.py startup's streaming STT validation requires SONIOX_API_KEY on every
    # Cloud Run role whose default streaming models include soniox.
    assert 'SONIOX_API_KEY' in secret_names
    forbidden = set(_prod_services()[PROJECTION_PUMP]['forbidden_env'])
    assert forbidden and forbidden.isdisjoint(rendered)


def _deploy_step():
    return next(s for s in PUMP_ACTION['runs']['steps'] if s.get('id') == 'deploy-backend-projection-pump')


def test_deploy_step_fixes_size_and_keeps_the_service_internal():
    step = _deploy_step()
    assert step['uses'] == 'google-github-actions/deploy-cloudrun@v3'
    assert step['with']['service'] == PROJECTION_PUMP
    flags = step['with']['flags'].split()
    for flag in (
        '--cpu=2',
        '--memory=4Gi',
        '--min-instances=4',
        '--max-instances=4',
        '--no-cpu-throttling',
        '--ingress=internal',
        '--no-allow-unauthenticated',
    ):
        assert flag in flags, flag
    assert '--allow-unauthenticated' not in flags
    assert '${{ steps.runtime-env.outputs.backend_projection_pump_identity_flags }}' in step['with']['flags']
    assert '${{ steps.runtime-env.outputs.backend_projection_pump_env_vars }}' in step['with']['env_vars']
    assert step['with']['secrets'] == '${{ steps.runtime-env.outputs.backend_projection_pump_secrets }}'
    assert '--timeout' not in step['with']['flags'].replace('cloud_run_flags', '')
    assert str(_prod_services()[PROJECTION_PUMP]['flags']['--timeout']) == '3600s'


def test_pump_composite_never_builds_pushes_or_grants_an_invoker():
    text = (ROOT / '.github/actions/deploy-projection-pump/action.yml').read_text()
    for forbidden in (
        'docker push',
        'docker build',
        'add-iam-policy-binding',
        'set-iam-policy',
        '--allow-unauthenticated',
    ):
        assert forbidden not in text.replace('--no-allow-unauthenticated', ''), forbidden
    names = [s.get('id') for s in PUMP_ACTION['runs']['steps']]
    assert 'runtime-env' in names
    assert names.index('runtime-env') < names.index('deploy-backend-projection-pump')


# --- shape readback ---------------------------------------------------------------------------


def _live(**changes):
    service = {
        'metadata': {'name': PROJECTION_PUMP, 'annotations': {'run.googleapis.com/ingress': 'internal'}},
        'spec': {
            'template': {
                'metadata': {
                    'name': 'backend-projection-pump-aaaaaaa-17-1',
                    'annotations': {
                        'autoscaling.knative.dev/minScale': '4',
                        'autoscaling.knative.dev/maxScale': '4',
                        'run.googleapis.com/cpu-throttling': 'false',
                    },
                },
                'spec': {
                    'timeoutSeconds': 3600,
                    'containers': [
                        {
                            'name': PROJECTION_PUMP,
                            'env': [
                                {'name': 'BATCH_PIPELINE_SERVING_ENABLED', 'value': 'false'},
                                {'name': 'BATCH_PIPELINE_PROJECTION_PUMP_ENABLED', 'value': 'false'},
                                {'name': 'FIRESTORE_READ_LEDGER_SERVICE', 'value': PROJECTION_PUMP},
                                {'name': 'SONIOX_API_KEY', 'valueFrom': {'secretKeyRef': {'name': 'x'}}},
                            ],
                        },
                        {'name': 'collector'},
                    ],
                },
            }
        },
    }
    for mutate in changes.values():
        mutate(service)
    return service


MANIFEST_ENV = {'BATCH_PIPELINE_PROJECTION_PUMP_ENABLED': 'false', 'FIRESTORE_READ_LEDGER_SERVICE': PROJECTION_PUMP}
PRIVATE = {'bindings': [{'role': 'roles/run.invoker', 'members': ['serviceAccount:x@y.iam.gserviceaccount.com']}]}


def _evaluate(service, iam=PRIVATE, env=MANIFEST_ENV):
    return shape.evaluate(service, iam, revision='backend-projection-pump-aaaaaaa-17-1', manifest_env=env)


def test_shape_readback_accepts_the_intended_service():
    assert _evaluate(_live()) == []
    assert _evaluate(_live(), iam={}) == []


def _set_template_annotation(key, value):
    return lambda s: s['spec']['template']['metadata']['annotations'].__setitem__(key, value)


def _set_env(name, value):
    def mutate(service):
        for entry in service['spec']['template']['spec']['containers'][0]['env']:
            if entry['name'] == name:
                entry['value'] = value

    return mutate


@pytest.mark.parametrize(
    'mutate, fragment',
    [
        (lambda s: s['metadata']['annotations'].__setitem__('run.googleapis.com/ingress', 'all'), 'ingress'),
        (_set_template_annotation('autoscaling.knative.dev/maxScale', '8'), 'maxScale'),
        (_set_template_annotation('autoscaling.knative.dev/minScale', '0'), 'minScale'),
        (_set_template_annotation('run.googleapis.com/cpu-throttling', 'true'), 'cpu-throttling'),
        (lambda s: s['metadata']['annotations'].__setitem__('run.googleapis.com/maxScale', '10'), 'service-level'),
        (lambda s: s['spec']['template']['spec'].__setitem__('timeoutSeconds', 300), 'timeoutSeconds'),
        (lambda s: s['spec']['template']['metadata'].__setitem__('name', 'other'), 'template revision'),
        (_set_env('BATCH_PIPELINE_SERVING_ENABLED', 'true'), 'BATCH_PIPELINE_SERVING_ENABLED'),
        (_set_env('BATCH_PIPELINE_PROJECTION_PUMP_ENABLED', 'true'), 'BATCH_PIPELINE_PROJECTION_PUMP_ENABLED'),
        (_set_env('FIRESTORE_READ_LEDGER_SERVICE', 'backend-integration'), 'FIRESTORE_READ_LEDGER_SERVICE'),
        (lambda s: s['spec']['template']['spec']['containers'].append({'name': 'extra'}), 'application container'),
    ],
)
def test_shape_readback_refuses_drift(mutate, fragment):
    errors = _evaluate(_live(m=mutate))
    assert any(fragment in error for error in errors), errors


@pytest.mark.parametrize('member', ['allUsers', 'allAuthenticatedUsers'])
def test_shape_readback_refuses_a_public_invoker(member):
    iam = {'bindings': [{'role': 'roles/run.invoker', 'members': [member]}]}
    assert any('public members' in error for error in _evaluate(_live(), iam=iam))


def test_shape_readback_refuses_a_manifest_that_names_another_ledger():
    env = {**MANIFEST_ENV, 'FIRESTORE_READ_LEDGER_SERVICE': 'backend-integration'}
    service = _live(m=_set_env('FIRESTORE_READ_LEDGER_SERVICE', 'backend-integration'))
    assert any('rendered FIRESTORE_READ_LEDGER_SERVICE' in error for error in _evaluate(service, env=env))


def test_shape_readback_cli_exit_codes(tmp_path, prod_state):
    state = prod_state
    (tmp_path / 'state.json').write_text(json.dumps(state))
    (tmp_path / 'iam.json').write_text(json.dumps(PRIVATE))
    (tmp_path / 'service.json').write_text(json.dumps(_live()))
    argv = [
        '--service',
        str(tmp_path / 'service.json'),
        '--iam-policy',
        str(tmp_path / 'iam.json'),
        '--revision',
        'backend-projection-pump-aaaaaaa-17-1',
        '--expected-env-state',
        str(tmp_path / 'state.json'),
    ]
    assert shape.main(argv) == 0
    (tmp_path / 'iam.json').write_text(json.dumps({'bindings': [{'role': 'r', 'members': ['allUsers']}]}))
    assert shape.main(argv) == 1
    (tmp_path / 'state.json').write_text('{}')
    assert shape.main(argv) == 1
