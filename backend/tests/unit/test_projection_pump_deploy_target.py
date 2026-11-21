"""SCA-3120: backend-projection-pump is an explicit-only, dark, internal fifth Cloud Run target.

Offline: these tests read the checked-in workflow, composite, manifest and scripts, and run
the boundary shell with fixture inputs. Nothing here calls a cloud API.
"""

from __future__ import annotations

import copy
import io
import json
import os
import re
import runpy
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import pytest
import yaml

from scripts import resolve_service_images as images
from scripts import verify_backend_release_vector as vector
from scripts import verify_projection_pump_shape as shape
from scripts.cloud_run_scope import PROJECTION_PUMP, SELECTABLE, SERVICES, selected

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / 'backend'
# Match direct execution of the workflow script without changing pytest's search path.
sys.path.insert(0, str(BACKEND / 'scripts'))
try:
    import recover_projection_pump_cap as recovery
finally:
    sys.path.pop(0)

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
    'OMI_PROCESS_ROLE': 'projection_pump',
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
        GITHUB_STEP_SUMMARY=str(tmp_path / 'summary'),
        GITHUB_SHA='b' * 40,
        WORKFLOW_CONTROL_SHA='b' * 40,
        PUMP_CONTROL_SHA='b' * 40,
        PUMP_RELEASE_DISPOSITION='',
    )
    env.update(overrides)
    return subprocess.run(['bash', '-c', script], env=env, text=True, capture_output=True, timeout=10), output


def test_boundary_admits_the_pump_for_a_manual_prod_cloud_run_only_deploy(tmp_path):
    result, output = _boundary(tmp_path, PUMP_RELEASE_DISPOSITION=INVERSE_RECEIPT)
    assert result.returncode == 0, result.stderr
    assert 'integration_only=false' in output.read_text()
    assert INVERSE_RECEIPT in (tmp_path / 'summary').read_text()


@pytest.mark.parametrize(
    'extra',
    [
        {'DEPLOY_ENVIRONMENT': 'development'},
        {'DEPLOY_TARGETS': 'all'},
        {'WORKFLOW_MODE': 'build-only'},
        {'BREAK_GLASS_LOCK': 'true'},
        {'SKIP_ELIGIBILITY': 'true'},
        {'PUMP_CONTROL_SHA': 'c' * 40},
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
    assert set(pump['forbidden_env']) == set(integration['forbidden_env']) | {'HOME_FEED_ENABLED'}
    assert pump['service_account'] == integration['service_account']
    train_pins = {'BATCH_ACCOUNT_PRIVACY_WRITER_ENABLED', 'BATCH_PROJECTION_OUTBOX'}
    overridden = (
        set(DARK_OVERRIDES) | {'BATCH_PIPELINE_INDEPENDENT_LANGUAGE_RECOVERY_ENABLED', 'HOME_FEED_ENABLED'} | train_pins
    )
    assert set(pump['env']) - set(integration['env']) <= overridden
    assert integration['env']['HOME_FEED_ENABLED'] == {'value': 'false', 'category': 'ops_kill'}
    assert 'HOME_FEED_ENABLED' not in pump['env']
    for name in set(integration['env']) - overridden:
        assert pump['env'][name] == integration['env'][name], name
    for name, value in DARK_OVERRIDES.items():
        assert pump['env'][name]['value'] == value, name
    for name in train_pins:
        assert integration['env'][name]['value'] == 'false', name
        assert services['backend-sync-backfill']['env'][name]['value'] == 'false', name
        assert pump['env'][name]['value'] == 'false', name  # SCA-3318: inherited, custody off
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


def test_derive_from_excludes_env_and_guards_removal_from_the_live_service():
    config = _env_config(
        {
            'src': {
                'env': {'A': {'value': '1'}, 'B': {'value': '2'}},
                'forbidden_env': ['OLD_KEY'],
            },
            'derived': {'derive_from': 'src', 'exclude_env': ['A']},
        }
    )
    COMPOSER['_resolve_derived_services'](config)
    derived = config['cloud_run']['services']['derived']
    assert derived['env'] == {'B': {'value': '2'}}
    assert derived['forbidden_env'] == ['OLD_KEY', 'A']
    assert 'derive_from' not in derived and 'exclude_env' not in derived


@pytest.mark.parametrize(
    'services',
    [
        {'derived': {'derive_from': 'missing'}},
        {'a': {}, 'b': {'derive_from': 'a'}, 'c': {'derive_from': 'b'}},
        {'a': {}, 'c': {'derive_from': 'b'}, 'b': {'derive_from': 'a'}},
        {'src': {}, 'derived': {'derive_from': 'src', 'exclude_env': 'A'}},
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
        'OMI_PROCESS_ROLE': 'projection_pump',
    }
    assert 'OMI_PROCESS_ROLE' not in {
        entry['name'] for entry in state['services']['backend-integration']['env'] if 'value' in entry
    }
    secret_names = {entry['name'] for entry in pump['env'] if 'value' not in entry}
    integration = state['services']['backend-integration']
    assert secret_names == {entry['name'] for entry in integration['env'] if 'value' not in entry}
    # main.py startup's streaming STT validation requires SONIOX_API_KEY on every
    # Cloud Run role whose default streaming models include soniox.
    assert 'SONIOX_API_KEY' in secret_names
    forbidden = set(_prod_services()[PROJECTION_PUMP]['forbidden_env'])
    assert forbidden and forbidden.isdisjoint(rendered)
    assert 'HOME_FEED_ENABLED' in forbidden
    assert 'HOME_FEED_ENABLED' not in rendered


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


def test_pump_composite_orders_the_live_checks_before_mutation_and_snapshot():
    steps = PUMP_ACTION['runs']['steps']
    ids = [s.get('id') for s in steps]
    names = [s['name'] for s in steps]
    assert ids.index('pump-service') < ids.index('deploy-backend-projection-pump')
    assert ids.index('pump-service') < names.index('Probe LLM gateway from the Cloud Run VPC before promotion')
    assert names.index('Verify a newly created projection pump base before pinning') + 1 == names.index(
        'Pin a newly created projection pump service to its base revision'
    )
    assert names.index('Verify the pinned first projection pump base') + 1 == names.index(
        'Attach revision-aware Managed Prometheus to the projection pump candidate'
    )
    assert ids.index('pump-traffic-snapshot') < ids.index('shift-projection-pump-traffic')
    assert 'verify_projection_pump_inverse.py' in steps[ids.index('pump-traffic-snapshot')]['run']


def test_pump_composite_deploys_and_verifies_the_resolved_digest_not_the_tag():
    text = (ROOT / '.github/actions/deploy-projection-pump/action.yml').read_text()
    steps = PUMP_ACTION['runs']['steps']
    ids = [s.get('id') for s in steps]
    resolve = steps[ids.index('published-image')]
    assert 'ref=${IMAGE%:*}@${digest}' in resolve['run']
    deploy = steps[ids.index('deploy-backend-projection-pump')]
    assert deploy['with']['image'] == '${{ steps.published-image.outputs.ref }}'
    assert ids.index('published-image') < ids.index('deploy-backend-projection-pump')
    assert text.count('--expected-image "${{ steps.published-image.outputs.ref }}"') == 2
    # The tag is read exactly once, by the step that resolves it.
    assert text.count('${{ steps.service-images.outputs.backend_projection_pump }}') == 1


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
                    'containerConcurrency': 80,
                    'containers': [
                        {
                            'name': PROJECTION_PUMP,
                            'resources': {'limits': {'cpu': '2', 'memory': '4Gi'}},
                            'env': [
                                {'name': 'BATCH_PIPELINE_SERVING_ENABLED', 'value': 'false'},
                                {'name': 'BATCH_PIPELINE_PROJECTION_PUMP_ENABLED', 'value': 'false'},
                                {'name': 'FIRESTORE_READ_LEDGER_SERVICE', 'value': PROJECTION_PUMP},
                                {'name': 'OMI_PROCESS_ROLE', 'value': 'projection_pump'},
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


MANIFEST_ENV = {
    'BATCH_PIPELINE_PROJECTION_PUMP_ENABLED': 'false',
    'FIRESTORE_READ_LEDGER_SERVICE': PROJECTION_PUMP,
    'OMI_PROCESS_ROLE': 'projection_pump',
}
PRIVATE = {'bindings': [{'role': 'roles/run.viewer', 'members': ['serviceAccount:x@y.iam.gserviceaccount.com']}]}


def _evaluate(service, iam=PRIVATE, env=MANIFEST_ENV):
    return shape.evaluate(service, iam, revision='backend-projection-pump-aaaaaaa-17-1', manifest_env=env)


def test_shape_readback_accepts_the_intended_service():
    assert _evaluate(_live()) == []
    assert _evaluate(_live(), iam={}) == []


INVERSE_REVISION = f'{PROJECTION_PUMP}-aaaaaaa-17-1-base'
INVERSE_IMAGE = 'gcr.io/based-hardware/backend@sha256:' + 'b' * 64
INVERSE_RECEIPT = f'01a1f818-f3a6-7183-bd19-9bd0f7e7bb75 {INVERSE_REVISION} {"a" * 40} {INVERSE_IMAGE}'


@pytest.fixture
def inverse_readback():
    service = _live()
    revision = copy.deepcopy(service['spec']['template'])
    revision['metadata'].update(name=INVERSE_REVISION, labels={'serving.knative.dev/service': PROJECTION_PUMP})
    revision['status'] = {'conditions': [{'type': 'Ready', 'status': 'True'}], 'imageDigest': INVERSE_IMAGE}
    app = revision['spec']['containers'][0]
    app['image'] = INVERSE_IMAGE
    app['env'].append({'name': 'OMI_BACKEND_RELEASE_SHA', 'value': 'a' * 40})
    revision['spec']['containers'].pop()  # The first deploy stopped before adding the sidecar.
    route = {'traffic': [{'revisionName': INVERSE_REVISION, 'percent': 100}]}
    service['spec'].update(copy.deepcopy(route))
    service['status'] = copy.deepcopy(route)
    # Cloud Run may have a newer no-traffic template. Use the receiving Revision.
    return service, revision, copy.deepcopy(PRIVATE)


def _run_inverse_step(tmp_path, step, documents, receipt=INVERSE_RECEIPT):
    service, revision, iam = documents
    fixtures = {
        'services list': [service],
        f'services describe {PROJECTION_PUMP}': service,
        f'revisions describe {INVERSE_REVISION}': revision,
        f'services get-iam-policy {PROJECTION_PUMP}': iam,
    }
    (tmp_path / 'fixtures.json').write_text(json.dumps(fixtures))
    gcloud = tmp_path / 'gcloud'
    gcloud.write_text(
        f'#!{sys.executable}\n'
        'import json, sys\n'
        'from pathlib import Path\n'
        'assert sys.argv[1] == "run"\n'
        'key = " ".join(arg for arg in sys.argv[2:] if not arg.startswith("--"))\n'
        'path = Path(__file__).with_name("fixtures.json")\n'
        'fixtures = json.loads(path.read_text())\n'
        'if key.startswith("services update-traffic"):\n'
        '    with Path(__file__).with_name("writes.log").open("a") as log:\n'
        '        log.write(" ".join(sys.argv[2:]) + "\\n")\n'
        '    target = next(a.split("=", 1)[1] for a in sys.argv if a.startswith("--to-revisions="))\n'
        '    name, percent = target.rsplit("=", 1)\n'
        '    service = fixtures["services describe ' + PROJECTION_PUMP + '"]\n'
        '    for section in ("spec", "status"):\n'
        '        service[section]["traffic"] = [{"revisionName": name, "percent": int(percent)}]\n'
        '    fixtures["services list"] = [service]\n'
        '    path.write_text(json.dumps(fixtures))\n'
        '    sys.exit(0)\n'
        'print(json.dumps(fixtures[key]))\n'
    )
    gcloud.chmod(0o755)
    script = step['run'].replace('${{ inputs.project_id }}', 'based-hardware')
    script = script.replace('${{ inputs.region }}', 'us-central1')
    script = script.replace('${{ inputs.admitted_sha }}', 'a' * 40)
    script = script.replace('${{ steps.image-tag.outputs.revision_suffix }}', 'aaaaaaa-17-1')
    script = script.replace('${{ steps.published-image.outputs.ref }}', INVERSE_IMAGE)
    script = re.sub(r'\$\{\{ [^}]+ }}', 'unused-first-create-input', script)
    env = dict(
        os.environ,
        PATH=f'{tmp_path}{os.pathsep}{Path(sys.executable).parent}{os.pathsep}{os.environ["PATH"]}',
        RELEASE_DISPOSITION=receipt,
        GITHUB_OUTPUT=str(tmp_path / 'steps.out'),
        DEPLOY_CONTROL_SCRIPTS=str(BACKEND / 'scripts'),
        PUMP_EXISTS='true',
    )
    return subprocess.run(['bash', '-c', script], cwd=tmp_path, env=env, text=True, capture_output=True, timeout=10)


@pytest.mark.parametrize(
    'break_readback',
    [
        lambda s, r, i: r['status']['conditions'][0].update(status='False'),
        lambda s, r, i: r['spec']['containers'][0]['env'][-1].update(value='c' * 40),
        lambda s, r, i: r['spec']['containers'][0].update(image=INVERSE_IMAGE[:-1] + 'c'),
        lambda s, r, i: r['status'].update(imageDigest='sha256:' + 'c' * 64),
        lambda s, r, i: r['spec']['containers'][0]['env'][0].update(value='true'),
        lambda s, r, i: r['spec']['containers'][0]['env'][1].update(value='true'),
        lambda s, r, i: r['spec']['containers'][0]['env'][3].update(value='all'),
        lambda s, r, i: r['spec'].update(containerConcurrency=81),
        lambda s, r, i: s['metadata']['annotations'].update({'run.googleapis.com/ingress': 'all'}),
        lambda s, r, i: s['metadata']['annotations'].update({'run.googleapis.com/invoker-iam-disabled': 'true'}),
        lambda s, r, i: i['bindings'].append({'role': 'roles/run.invoker', 'members': ['allUsers']}),
        lambda s, r, i: i['bindings'].append({'role': 'roles/run.servicesInvoker', 'members': ['user:x@example.com']}),
        lambda s, r, i: s['status']['traffic'][0].update(latestRevision=True),
        lambda s, r, i: s['spec']['traffic'][0].update(revisionName=PROJECTION_PUMP + '-elsewhere'),
    ],
)
def test_pinned_but_unverified_base_blocks_retry_and_inverse(tmp_path, inverse_readback, break_readback):
    break_readback(*inverse_readback)
    for name in (
        'Verify existing projection pump, pinning a LATEST-routed base, before deploy mutations',
        'Reverify the projection pump inverse and capture its traffic snapshot',
    ):
        result = _run_inverse_step(tmp_path, _step_named(name), inverse_readback)
        assert result.returncode != 0, result.stdout
    assert not (tmp_path / 'steps.out').exists()
    assert not (tmp_path / 'artifacts/projection-pump-pre-promotion-traffic-snapshot.json').exists()


def test_pinned_base_requires_release_disposition_and_live_proof(tmp_path, inverse_readback):
    step = _step_named('Verify existing projection pump, pinning a LATEST-routed base, before deploy mutations')
    result = _run_inverse_step(tmp_path, step, inverse_readback, receipt='')
    assert result.returncode != 0 and 'recorded Release disposition' in result.stderr
    assert not (tmp_path / 'steps.out').exists()

    result = _run_inverse_step(tmp_path, step, inverse_readback)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / 'steps.out').read_text() == 'exists=true\n'
    assert INVERSE_IMAGE in result.stdout

    snapshot_step = _step_named('Reverify the projection pump inverse and capture its traffic snapshot')
    result = _run_inverse_step(tmp_path, snapshot_step, inverse_readback)
    assert result.returncode == 0, result.stderr
    snapshot = json.loads((tmp_path / 'artifacts/projection-pump-pre-promotion-traffic-snapshot.json').read_text())
    assert snapshot['services'][PROJECTION_PUMP]['spec']['traffic'] == [
        {'revisionName': INVERSE_REVISION, 'percent': 100}
    ]


def test_latest_is_allowed_only_for_the_new_base_before_its_first_pin(tmp_path, inverse_readback):
    service, _, _ = inverse_readback
    service['spec']['traffic'] = [{'percent': 100, 'latestRevision': True}]
    service['status']['traffic'][0]['latestRevision'] = True
    service['status'].update(latestReadyRevisionName=INVERSE_REVISION, latestCreatedRevisionName=INVERSE_REVISION)

    existing = _step_named('Verify existing projection pump, pinning a LATEST-routed base, before deploy mutations')
    # SCA-3318 changed this boundary: an existing service still on LATEST (live 2026-11-21, its
    # first pin never ran) may be pinned, but only to the disposition's base that LATEST resolves to.
    other_base = f'{PROJECTION_PUMP}-bbbbbbb-18-1-base'
    receipt = f'01a1f818-f3a6-7183-bd19-9bd0f7e7bb75 {other_base} {"a" * 40} {INVERSE_IMAGE}'
    assert _run_inverse_step(tmp_path, existing, inverse_readback, receipt=receipt).returncode != 0
    assert not (tmp_path / 'writes.log').exists()
    before_pin = _step_named('Verify a newly created projection pump base before pinning')
    result = _run_inverse_step(tmp_path, before_pin, inverse_readback, receipt='')
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('workflow_sha', ['a' * 40, 'b' * 40])
def test_control_boundary_requires_the_reviewed_dispatch_sha(workflow_sha):
    script = _step_named('Validate projection pump deploy boundary')['run']
    for name, value in {
        'environment': 'prod',
        'runtime_env': 'prod',
        'project_id': 'based-hardware',
        'region': 'us-central1',
        'admitted_sha': 'c' * 40,
    }.items():
        script = script.replace('${{ inputs.' + name + ' }}', value)
    env = dict(os.environ, GITHUB_SHA=workflow_sha, WORKFLOW_CONTROL_SHA=workflow_sha, REVIEWED_CONTROL_SHA='a' * 40)
    result = subprocess.run(['bash', '-c', script], env=env, text=True, capture_output=True, timeout=10)
    assert (result.returncode == 0) == (workflow_sha == env['REVIEWED_CONTROL_SHA']), result.stderr


def _set_template_annotation(key, value):
    return lambda s: s['spec']['template']['metadata']['annotations'].__setitem__(key, value)


def _set_env(name, value):
    def mutate(service):
        for entry in service['spec']['template']['spec']['containers'][0]['env']:
            if entry['name'] == name:
                entry['value'] = value

    return mutate


def _drop_env(name):
    def mutate(service):
        container = service['spec']['template']['spec']['containers'][0]
        container['env'] = [entry for entry in container['env'] if entry['name'] != name]

    return mutate


def _set_limit(name, value):
    return lambda s: s['spec']['template']['spec']['containers'][0]['resources']['limits'].__setitem__(name, value)


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
        (_set_env('OMI_PROCESS_ROLE', 'all'), 'OMI_PROCESS_ROLE'),
        (_set_env('OMI_PROCESS_ROLE', ''), 'OMI_PROCESS_ROLE'),
        (_drop_env('OMI_PROCESS_ROLE'), 'OMI_PROCESS_ROLE'),
        (lambda s: s['spec']['template']['spec']['containers'].append({'name': 'extra'}), 'application container'),
        (_set_limit('cpu', '1'), 'limits'),
        (_set_limit('memory', '2Gi'), 'limits'),
        (lambda s: s['spec']['template']['spec']['containers'][0].pop('resources'), 'limits'),
    ],
)
def test_shape_readback_refuses_drift(mutate, fragment):
    errors = _evaluate(_live(m=mutate))
    assert any(fragment in error for error in errors), errors


@pytest.mark.parametrize('member', ['allUsers', 'allAuthenticatedUsers'])
def test_shape_readback_refuses_a_public_invoker(member):
    iam = {'bindings': [{'role': 'roles/run.invoker', 'members': [member]}]}
    assert any('public members' in error for error in _evaluate(_live(), iam=iam))


def test_shape_readback_refuses_a_private_invoker():
    iam = {'bindings': [{'role': 'roles/run.invoker', 'members': ['serviceAccount:x@y.iam.gserviceaccount.com']}]}
    assert any('roles/run.invoker must have no members' in error for error in _evaluate(_live(), iam=iam))


def test_shape_readback_refuses_a_manifest_that_names_another_ledger():
    env = {**MANIFEST_ENV, 'FIRESTORE_READ_LEDGER_SERVICE': 'backend-integration'}
    service = _live(m=_set_env('FIRESTORE_READ_LEDGER_SERVICE', 'backend-integration'))
    assert any('rendered FIRESTORE_READ_LEDGER_SERVICE' in error for error in _evaluate(service, env=env))


def test_shape_readback_refuses_a_manifest_without_the_pump_role():
    for value in ('', 'all'):
        env = {**MANIFEST_ENV, 'OMI_PROCESS_ROLE': value}
        service = _live(m=_set_env('OMI_PROCESS_ROLE', value))
        errors = _evaluate(service, env=env)
        assert any('rendered OMI_PROCESS_ROLE' in error for error in errors), errors
        assert any("OMI_PROCESS_ROLE must be 'projection_pump'" in error for error in errors), errors


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


# --- base revision naming -------------------------------------------------------------------

BASE_REVISION = 'backend-projection-pump-${{ steps.image-tag.outputs.revision_suffix }}-base'


def _step_named(name):
    return next(s for s in PUMP_ACTION['runs']['steps'] if s.get('name') == name)


def test_deploy_pin_and_sidecar_steps_name_the_same_base_revision():
    deploy = _deploy_step()
    suffix = BASE_REVISION.removeprefix(f'{deploy["with"]["service"]}-')
    assert deploy['with']['flags'].startswith(f'--revision-suffix={suffix} ')
    pin = _step_named('Pin a newly created projection pump service to its base revision')
    assert f'--to-revisions="{BASE_REVISION}=100"' in pin['run']
    attach = _step_named('Attach revision-aware Managed Prometheus to the projection pump candidate')
    assert f'--base-revision="{BASE_REVISION}"' in attach['run']
    text = (ROOT / '.github/actions/deploy-projection-pump/action.yml').read_text()
    assert set(re.findall(r'backend-projection-pump-\$\{\{[^}]*\}\}-base', text)) == {BASE_REVISION}


# SCA-3318 recovery uses the interrupted base, with one service-cap mismatch.
def _recovery_fixture(inverse_readback, etag='approved-version'):
    service, revision, policy = inverse_readback
    before = {
        'name': recovery.RESOURCE,
        'uid': 'pump-uid',
        'generation': '7',
        'observedGeneration': '7',
        'etag': etag,
        'terminalCondition': {'state': 'CONDITION_SUCCEEDED'},
        'scaling': {'maxInstanceCount': 20},
        'template': copy.deepcopy(revision['spec']),
        'traffic': [{'type': 'TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST', 'percent': 100}],
    }
    service['metadata']['uid'] = before['uid']
    policy['etag'] = 'policy-version'
    for section in ('spec', 'status'):
        service[section]['traffic'][0].update(latestRevision=True, revisionName=recovery.BASE.revision)
    service['status'].update(
        latestReadyRevisionName=recovery.BASE.revision, latestCreatedRevisionName=recovery.BASE.revision
    )
    revision['metadata']['name'] = recovery.BASE.revision
    revision['status']['imageDigest'] = recovery.BASE.image
    app = revision['spec']['containers'][0]
    app['image'] = recovery.BASE.image
    app['env'][-1]['value'] = recovery.BASE.source

    class FakeRun:
        def __init__(self):
            self.state = before
            self.cap_requests = []
            self.validation_error = None
            self.interrupted = False
            self.drift_after_validation = False
            self.drift_after_write = False
            self.permission_denied = False

        def permission_check(self):
            if self.permission_denied:
                raise ValueError('missing permission')

        def service(self):
            return copy.deepcopy(self.state)

        def read(self, noun, verb, _name):
            if noun == 'revisions':
                return copy.deepcopy(revision)
            if verb == 'get-iam-policy':
                return copy.deepcopy(policy)
            document = copy.deepcopy(service)
            document['metadata']['annotations'][recovery.CAP_ANNOTATION] = str(
                self.state['scaling']['maxInstanceCount']
            )
            return document

        def patch(self, etag, cap, *, validate_only):
            self.cap_requests.append((etag, cap, validate_only))
            assert etag == self.state['etag']
            if validate_only:
                if len(self.cap_requests) == self.validation_error:
                    raise ValueError('validation rejected')
                if len(self.cap_requests) == 2 and self.drift_after_validation:
                    self.state['etag'] = 'drifted'
                return {}
            self.state.update(etag='new-version', generation='8', observedGeneration='8')
            self.state['scaling']['maxInstanceCount'] = cap
            if self.drift_after_write:
                self.state['template'] = {}
            if self.interrupted:
                raise TimeoutError('simulated lost response after submit')
            return {}

        def complete(self, _operation, _cap, *, submitted):
            pass

    return FakeRun()


def test_cap_recovery_writes_once_and_validates_the_post_write_inverse(inverse_readback):
    api = _recovery_fixture(inverse_readback)
    recovery.recover(api, api.read, 'approved-version')
    assert api.cap_requests == [
        ('approved-version', 4, True),
        ('approved-version', 20, True),
        ('approved-version', 4, False),
        ('new-version', 20, True),
    ]


@pytest.mark.parametrize('failure', ['permission', 'etag', 'drift', 'forward', 'inverse', 'shape'])
def test_cap_recovery_refuses_before_submit(inverse_readback, failure):
    api = _recovery_fixture(inverse_readback)
    etag = 'approved-version'
    if failure == 'permission':
        api.permission_denied = True
    elif failure == 'etag':
        etag = 'wrong-version'
    elif failure == 'drift':
        api.drift_after_validation = True
    elif failure in ('forward', 'inverse'):
        api.validation_error = 1 if failure == 'forward' else 2
    else:
        inverse_readback[1]['status']['conditions'][0]['status'] = 'False'
    with pytest.raises(ValueError):
        recovery.recover(api, api.read, etag)
    assert all(validate for _, _, validate in api.cap_requests)


@pytest.mark.parametrize('failure', ['interruption', 'post_write_shape', 'post_write_inverse'])
def test_cap_recovery_requires_reconciliation_after_any_ambiguous_write(inverse_readback, failure):
    api = _recovery_fixture(inverse_readback)
    api.interrupted = failure == 'interruption'
    api.drift_after_write = failure == 'post_write_shape'
    api.validation_error = 4 if failure == 'post_write_inverse' else None
    with pytest.raises(ValueError, match='independent Release reconciliation'):
        recovery.recover(api, api.read, 'approved-version')
    with pytest.raises(ValueError):
        recovery.recover(api, api.read, 'approved-version')
    assert [item for item in api.cap_requests if not item[2]] == [('approved-version', 4, False)]


def test_cap_recovery_requests_only_the_one_field(monkeypatch):
    api = recovery.RunAPI('fixture-token')
    requests = []
    monkeypatch.setattr(api, 'request', lambda *args: requests.append(args))
    api.patch('fixture-etag', 4, validate_only=False)
    assert requests == [
        (
            'PATCH',
            recovery.RESOURCE + '?updateMask=scaling.maxInstanceCount&validateOnly=false',
            {'name': recovery.RESOURCE, 'etag': 'fixture-etag', 'scaling': {'maxInstanceCount': 4}},
        )
    ]


@pytest.mark.parametrize(
    'operation',
    [
        {},
        {'name': 'projects/other/locations/us-central1/operations/abc'},
        {'done': True, 'error': {'code': 10}},
        {'done': True, 'response': {'name': 'wrong-service'}},
    ],
)
def test_cap_recovery_refuses_bad_operation(operation):
    operation.setdefault('name', recovery.OPERATIONS + 'operation')
    api = recovery.RunAPI('fixture-token')
    if not operation.get('done') and operation['name'].startswith(recovery.OPERATIONS):
        api.request = lambda *_args: {'name': recovery.OPERATIONS + 'wrong-operation'}
    with pytest.raises(ValueError):
        api.complete(operation, 4, submitted=True, sleep=lambda _: None)


def test_cap_recovery_checks_server_response_cap():
    api = recovery.RunAPI('fixture-token')
    response = {
        '@type': 'type.googleapis.com/google.cloud.run.v2.Service',
        'name': recovery.RESOURCE,
        'scaling': {'maxInstanceCount': 4},
    }
    operation = {'done': True, 'response': response}
    api.complete(operation, 4, submitted=False)
    with pytest.raises(ValueError, match='exact pump service and cap'):
        api.complete(operation, 20, submitted=False)


def test_cap_validation_accepts_only_completed_typed_empty_response():
    api = recovery.RunAPI('fixture-token')
    operation = {'done': True, 'response': {'@type': recovery.SERVICE_TYPE}}
    api.complete(operation, 4, submitted=False)
    with pytest.raises(ValueError):
        api.complete({'done': True}, 4, submitted=False)


def test_cap_recovery_polls_numeric_project_operation(monkeypatch):
    api = recovery.RunAPI('fixture-token')
    name = recovery.OPERATIONS.replace(recovery.PROJECT, recovery.PROJECT_NUMBER) + 'operation'
    resource = recovery.RESOURCE.replace(recovery.PROJECT, recovery.PROJECT_NUMBER)

    def complete(method, path):
        assert (method, path) == ('GET', name)
        return {
            'name': name,
            'done': True,
            'response': {'@type': recovery.SERVICE_TYPE, 'name': resource, 'scaling': {'maxInstanceCount': 4}},
        }

    monkeypatch.setattr(api, 'request', complete)
    api.complete({'name': name}, 4, submitted=True, sleep=lambda _: None)


def test_cap_validation_never_polls_an_unpersisted_operation(monkeypatch, capsys):
    """Run 44862200539: a validate-only operation name is not readable (404); never GET it."""
    api = recovery.RunAPI('fixture-token')

    def missing(*_args, **_kwargs):
        raise AssertionError('validate-only operations must not be polled')

    monkeypatch.setattr(api.opener, 'open', missing)
    # Without an exact Service preview it is still not validation success.
    with pytest.raises(ValueError, match='no exact pump service preview'):
        api.complete({'name': recovery.OPERATIONS + 'operation'}, 4, submitted=False, sleep=lambda _: None)
    out = capsys.readouterr().out
    assert 'PUMP_CAP_VALIDATE_SHAPE keys=name done=False metadata_type=absent' in out
    assert recovery.OPERATIONS not in out  # key names only, never values


@pytest.mark.parametrize(
    'metadata',
    [
        {'@type': recovery.SERVICE_TYPE, 'name': recovery.RESOURCE, 'scaling': {'maxInstanceCount': 20}},
        {'@type': 'type.googleapis.com/other', 'name': recovery.RESOURCE, 'scaling': {'maxInstanceCount': 4}},
        {'@type': recovery.SERVICE_TYPE, 'name': recovery.RESOURCE + '-x', 'scaling': {'maxInstanceCount': 4}},
        'not-a-dict',
        {'@type': recovery.SERVICE_TYPE, 'name': recovery.RESOURCE, 'scaling': None},
    ],
)
def test_cap_validation_preview_must_name_the_exact_service_and_cap(monkeypatch, metadata):
    api = recovery.RunAPI('fixture-token')
    monkeypatch.setattr(api.opener, 'open', lambda *_a, **_k: pytest.fail('must not poll'))
    with pytest.raises(ValueError):
        api.complete({'name': recovery.OPERATIONS + 'op', 'metadata': metadata}, 4, submitted=False)


@pytest.mark.parametrize('resource', sorted(recovery.RESOURCE_NAMES))
def test_cap_validation_accepts_the_exact_unfinished_preview(monkeypatch, resource):
    api = recovery.RunAPI('fixture-token')
    monkeypatch.setattr(api.opener, 'open', lambda *_a, **_k: pytest.fail('must not poll'))
    metadata = {'@type': recovery.SERVICE_TYPE, 'name': resource, 'scaling': {'maxInstanceCount': 4}}
    api.complete({'name': recovery.OPERATIONS + 'op', 'metadata': metadata}, 4, submitted=False)


def test_cap_validation_error_is_still_a_failure(monkeypatch):
    api = recovery.RunAPI('fixture-token')
    metadata = {'@type': recovery.SERVICE_TYPE, 'name': recovery.RESOURCE, 'scaling': {'maxInstanceCount': 4}}
    with pytest.raises(ValueError, match='reported failure'):
        api.complete(
            {'name': recovery.OPERATIONS + 'op', 'metadata': metadata, 'error': {'code': 3}}, 4, submitted=False
        )


def test_submitted_operation_404_is_still_a_refusal(monkeypatch, capsys):
    api = recovery.RunAPI('fixture-token')

    def missing(*_args, **_kwargs):
        raise HTTPError('private', 404, 'private', None, None)

    monkeypatch.setattr(api.opener, 'open', missing)
    with pytest.raises(ValueError):
        api.complete({'name': recovery.OPERATIONS + 'operation'}, 4, submitted=True, sleep=lambda _: None)
    assert capsys.readouterr().err == 'PUMP_CAP_API_ERROR stage=operation-read status=404\n'


def test_cap_recovery_uses_existing_approval_and_lock():
    job = WORKFLOW['jobs']['recover-projection-pump-cap']
    assert job['environment'] == 'prod'
    assert job['needs'] == 'validate-production-boundary'
    assert job['permissions'] == {'contents': 'read', 'id-token': 'write'}
    assert "inputs.mode == 'recover-pump-cap'" in job['if']
    assert "!inputs.break_glass_lock" in job['if']
    assert "refs/heads/main" in job['if']
    assert job['steps'][0]['with']['ref'] == '${{ github.workflow_sha }}'
    assert 'prod-train' in WORKFLOW['concurrency']['group']
    assert WORKFLOW['concurrency']['cancel-in-progress'] is False


def _cap_recovery_preapproval(tmp_path, override):
    step = WORKFLOW['jobs']['validate-production-boundary']['steps'][1]
    event = tmp_path / 'event.json'
    summary = tmp_path / 'summary'
    inputs = {
        'break_glass_lock': 'false',
        'skip_eligibility_proof': 'false',
        'deploy_gateway': 'false',
        'requested_by': 'release-owner',
        'pump_recovery_etag': 'AQ==',
    }
    env = {
        **os.environ,
        'GITHUB_EVENT_NAME': 'workflow_dispatch',
        'GITHUB_REF': 'refs/heads/main',
        'GITHUB_REPOSITORY': 'BasedHardware/omi',
        'GITHUB_RUN_ATTEMPT': '1',
        'DEPLOY_ENVIRONMENT': 'prod',
        'DEPLOY_TARGETS': 'cloud-run-only',
        'CLOUD_RUN_SERVICE': 'backend-projection-pump',
        'CONTROL_SHA': 'a' * 40,
        'WORKFLOW_CONTROL_SHA': 'a' * 40,
        'GITHUB_SHA': 'a' * 40,
        'RELEASE_SHA': 'f7060aa1a0c9e3481790d497140096ae99f9b062',
        'GITHUB_EVENT_PATH': str(event),
        'GITHUB_STEP_SUMMARY': str(summary),
    }
    for key, value in override.items():
        (inputs if key in inputs else env)[key] = value
    event.write_text(json.dumps({'inputs': inputs}))
    dispatch_inputs = json.loads(event.read_text())['inputs']
    assert step['env']['APPROVED_ETAG'] == '${{ inputs.pump_recovery_etag }}'
    env['APPROVED_ETAG'] = dispatch_inputs['pump_recovery_etag']
    run = subprocess.run(['bash', '-c', step['run']], env=env, capture_output=True, text=True, timeout=10)
    return run, summary, dispatch_inputs


@pytest.mark.parametrize(
    'override',
    [
        {},
        {'GITHUB_RUN_ATTEMPT': '2'},
        {'GITHUB_REF': 'refs/heads/topic'},
        {'CONTROL_SHA': 'b' * 40},
        {'pump_recovery_etag': ''},
        {'pump_recovery_etag': '""'},
        {'pump_recovery_etag': '"AQ=='},
        {'pump_recovery_etag': 'AQ=="'},
        {'pump_recovery_etag': '"AQ="="'},
        {'pump_recovery_etag': '"AQ=="\n'},
        {'pump_recovery_etag': '"' + 'A' * 201 + '"'},
        {'CLOUD_RUN_SERVICE': 'backend-sync'},
        {'break_glass_lock': 'true'},
        {'skip_eligibility_proof': 'true'},
        {'deploy_gateway': 'true'},
    ],
)
def test_cap_recovery_preapproval_boundary(tmp_path, override):
    run, summary, inputs = _cap_recovery_preapproval(tmp_path, override)
    assert (run.returncode == 0) is (not override), run.stderr
    assert summary.exists() is (not override)
    if not override:
        assert json.loads(summary.read_text())['etag'] == inputs['pump_recovery_etag']


@pytest.mark.parametrize('dispatch_etag', ['"A+B/c_d-e=="', '"stale-version"', 'A+B/c_d-e=='])
def test_cap_recovery_quoted_etag_round_trip(tmp_path, monkeypatch, inverse_readback, dispatch_etag):
    live_etag = '"A+B/c_d-e=="'
    run, summary, inputs = _cap_recovery_preapproval(tmp_path, {'pump_recovery_etag': dispatch_etag})
    assert run.returncode == 0, run.stderr
    assert json.loads(summary.read_text())['etag'] == dispatch_etag

    step = WORKFLOW['jobs']['recover-projection-pump-cap']['steps'][-1]
    assert step['env']['APPROVED_ETAG'] == '${{ inputs.pump_recovery_etag }}'
    # Capture the workflow shell's argv with a stand-in for the Python executable.
    command_output = subprocess.check_output(
        ['bash', '-c', 'python3() { printf "%s\\0" "$@"; }\n' + step['run']],
        env={**os.environ, 'APPROVED_ETAG': inputs['pump_recovery_etag']},
        timeout=10,
    )
    argv = command_output.decode().split('\0')[:-1]
    assert argv[0] == 'backend/scripts/recover_projection_pump_cap.py'
    monkeypatch.setattr(sys, 'argv', argv)

    fixture = _recovery_fixture(inverse_readback, etag=live_etag)
    api = recovery.RunAPI('fixture-token')
    monkeypatch.setattr(api, 'permission_check', fixture.permission_check)
    monkeypatch.setattr(api, 'service', fixture.service)
    monkeypatch.setattr(api, 'complete', fixture.complete)

    def open_patch(request, *, timeout):
        assert request.method == 'PATCH'
        url = urlsplit(request.full_url)
        assert url.path == '/v2/' + recovery.RESOURCE
        query = parse_qs(url.query)
        assert query['updateMask'] == ['scaling.maxInstanceCount']
        body = json.loads(request.data)
        assert body['name'] == recovery.RESOURCE
        result = fixture.patch(
            body['etag'], body['scaling']['maxInstanceCount'], validate_only=query['validateOnly'] == ['true']
        )
        return io.BytesIO(json.dumps(result).encode())

    monkeypatch.setattr(api.opener, 'open', open_patch)
    monkeypatch.setattr(recovery, 'RunAPI', lambda _token: api)
    monkeypatch.setattr(recovery, '_read', lambda _project, _region, *args: fixture.read(*args))
    monkeypatch.setattr(
        recovery.subprocess, 'run', lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, 'token')
    )
    if dispatch_etag == live_etag:
        assert recovery.main() == 0
        assert fixture.cap_requests == [
            (live_etag, 4, True),
            (live_etag, 20, True),
            (live_etag, 4, False),
            ('new-version', 20, True),
        ]
    else:
        assert recovery.main() == 1
        assert fixture.cap_requests == []


def test_claimed_sibling_skip_ships_dark_on_integration_until_activation():
    """SCA-3544: #25920 is default-on in code; prod integration (and the pump derived from it) pin it false."""
    services = _prod_services()
    for name in ('backend-integration', PROJECTION_PUMP):
        assert services[name]['env']['BATCH_PIPELINE_FOLLOWUP_CLAIMED_SIBLING_SKIP_ENABLED']['value'] == 'false', name


def test_existing_latest_routed_pump_is_pinned_inside_the_locked_deploy():
    """SCA-3318: a pump created but never pinned (100% via LATEST) is pinned by name, pre-pin verified."""
    steps = {step.get('id') or step.get('name'): step for step in PUMP_ACTION['runs']['steps']}
    script = steps['pump-service']['run']
    existing = script[script.index('          1)') if '          1)' in script else script.index('1)') :]
    pin = existing.index('update-traffic backend-projection-pump')
    assert existing.index('--before-first-pin') < pin
    assert existing.index('latestRevision') < existing.index('--before-first-pin')
    assert '--to-revisions="$base=100"' in existing
    assert pin < existing.rindex('--disposition="$RELEASE_DISPOSITION"')
    pre_pin = existing[existing.index('latestRevision') : pin]
    assert '--disposition="$RELEASE_DISPOSITION"' in pre_pin and '--before-first-pin' in pre_pin
    assert '--new-base' not in pre_pin


@pytest.mark.parametrize(
    'disposition',
    [
        # UUID missing (three fields), malformed UUID, and a non-base revision.
        f'{BASE_REVISION} {"a" * 40} gcr.io/based-hardware/backend@sha256:{"b" * 64}',
        f'not-a-uuid {BASE_REVISION} {"a" * 40} gcr.io/based-hardware/backend@sha256:{"b" * 64}',
        f'01a1fd00-0000-7000-8000-000000000000 backend-projection-pump-x {"a" * 40} '
        f'gcr.io/based-hardware/backend@sha256:{"b" * 64}',
    ],
)
def test_pre_pin_disposition_is_fully_validated_before_any_read(monkeypatch, disposition):
    """#25945 panel F1: the LATEST pin path must reject a bad disposition before touching traffic."""
    inverse = sys.modules[recovery.verify.__module__]

    monkeypatch.setattr(inverse, '_read', lambda *a, **k: pytest.fail('read before validation'))
    monkeypatch.setattr(
        sys,
        'argv',
        ['verify', '--project=p', '--region=r', f'--disposition={disposition}', '--before-first-pin'],
    )
    assert inverse.main() != 0


@pytest.mark.parametrize('route', ['latest', 'pinned'])
def test_existing_pump_step_pins_only_a_latest_routed_base(tmp_path, inverse_readback, route):
    """#25945 panel F1/F5: execute the step; a LATEST route is pre-pin verified, then pinned by name."""
    service, revision, iam = inverse_readback
    if route == 'latest':
        for section in ('spec', 'status'):
            service[section]['traffic'] = [{'latestRevision': True, 'percent': 100, 'revisionName': INVERSE_REVISION}]
        service['status'].update(latestReadyRevisionName=INVERSE_REVISION, latestCreatedRevisionName=INVERSE_REVISION)
    step = _step_named('Verify existing projection pump, pinning a LATEST-routed base, before deploy mutations')
    result = _run_inverse_step(tmp_path, step, (service, revision, iam))
    assert result.returncode == 0, result.stderr
    writes = (tmp_path / 'writes.log').read_text().splitlines() if (tmp_path / 'writes.log').exists() else []
    if route == 'latest':
        assert len(writes) == 1 and f'--to-revisions={INVERSE_REVISION}=100' in writes[0]
        assert (tmp_path / 'artifacts' / 'projection-pump-existing-latest-readback.txt').exists()
    else:
        assert writes == []


def test_cap_recovery_waits_for_post_write_reconciliation(inverse_readback, monkeypatch, capsys):
    """Run 44900134239: the write landed, but the first post-write read was still reconciling."""
    api = _recovery_fixture(inverse_readback)
    original_patch, reads = api.patch, {'n': 0}

    def patch(etag, cap, *, validate_only):
        result = original_patch(etag, cap, validate_only=validate_only)
        if not validate_only:
            api.state['reconciling'] = True
        return result

    original_service = api.service

    def service():
        if api.state.get('reconciling'):
            reads['n'] += 1
            if reads['n'] >= 3:
                api.state['reconciling'] = False
        return original_service()

    api.patch, api.service = patch, service
    sleeps = []
    monkeypatch.setattr(recovery.time, 'sleep', sleeps.append)
    recovery.recover(api, api.read, 'approved-version')
    assert [item for item in api.cap_requests if not item[2]] == [('approved-version', 4, False)]
    assert reads['n'] >= 3
    assert sleeps and set(sleeps) == {5}
    out = capsys.readouterr().out
    assert 'PUMP_CAP_SETTLING attempt=1' in out and f'PUMP_CAP_SETTLED attempts={len(sleeps) + 1}' in out


def test_cap_recovery_settle_wait_is_bounded(inverse_readback, monkeypatch, capsys):
    api = _recovery_fixture(inverse_readback)
    original_patch = api.patch

    def patch(etag, cap, *, validate_only):
        result = original_patch(etag, cap, validate_only=validate_only)
        if not validate_only:
            api.state['reconciling'] = True  # never settles
        return result

    api.patch = patch
    now = {'t': 0.0}
    monkeypatch.setattr(recovery.time, 'sleep', lambda s: now.__setitem__('t', now['t'] + s))
    monkeypatch.setattr(recovery.time, 'monotonic', lambda: now['t'])
    with pytest.raises(ValueError, match='independent Release reconciliation'):
        recovery.recover(api, api.read, 'approved-version')
    assert [item for item in api.cap_requests if not item[2]] == [('approved-version', 4, False)]
    assert 'PUMP_CAP_SETTLE_TIMEOUT' in capsys.readouterr().err


@pytest.mark.parametrize('case', ['transient_read', 'terminal_failure'])
def test_cap_recovery_settle_retries_reads_but_not_a_failed_condition(inverse_readback, monkeypatch, capsys, case):
    """#25948 panel F1/F2: a transient GET is retried; a failed terminal condition refuses at once."""
    api = _recovery_fixture(inverse_readback)
    original_patch, original_service, calls = api.patch, api.service, {'n': 0, 'written': False}

    def patch(etag, cap, *, validate_only):
        result = original_patch(etag, cap, validate_only=validate_only)
        calls['written'] = calls['written'] or not validate_only
        if not validate_only and case == 'terminal_failure':
            api.state['terminalCondition'] = {'state': 'CONDITION_FAILED'}
        return result

    def service():
        if calls['written'] and case == 'transient_read' and calls['n'] < 2:
            calls['n'] += 1
            raise ValueError('Cloud Run request failed or response was unreadable')
        return original_service()

    api.patch, api.service = patch, service
    sleeps = []
    monkeypatch.setattr(recovery.time, 'sleep', sleeps.append)
    if case == 'transient_read':
        recovery.recover(api, api.read, 'approved-version')
        assert sleeps == [5, 5]
    else:
        with pytest.raises(ValueError, match='independent Release reconciliation'):
            recovery.recover(api, api.read, 'approved-version')
        assert sleeps == []
        assert 'PUMP_CAP_SETTLE_FAILED' in capsys.readouterr().err
    assert [item for item in api.cap_requests if not item[2]] == [('approved-version', 4, False)]


def test_truncated_response_is_a_safe_api_error(monkeypatch, capsys):
    """#25948 panel F1: http.client errors take the safe PUMP_CAP_API_ERROR path, never a traceback."""
    import http.client

    class Opener:
        def open(self, *_args, **_kwargs):
            raise http.client.IncompleteRead(b'partial')

    api = recovery.RunAPI('fixture-token')
    api.opener = Opener()
    with pytest.raises(ValueError):
        api.service()
    assert 'PUMP_CAP_API_ERROR stage=service-read status=unconfirmed' in capsys.readouterr().err
