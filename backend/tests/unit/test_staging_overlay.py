"""Staging overlay composition (contract (i)): prod plus an allowlisted, fence-clean diff."""

import shutil
from pathlib import Path

import pytest
import yaml

from scripts.cross_service_checks import staging as staging_check

ROOT = Path(__file__).resolve().parents[3]
RUNTIME_ENV = ROOT / 'backend' / 'deploy' / 'runtime_env'
INPUTS = {'STAGING_REDIS_HOST': '10.0.0.7'}


@pytest.fixture(scope='module')
def composer():
    return staging_check._load_composer(ROOT)


def _copy_tree(tmp_path: Path) -> Path:
    """A throwaway repo root with the runtime_env sources and the composer."""
    target = tmp_path / 'backend' / 'deploy'
    shutil.copytree(RUNTIME_ENV, target / 'runtime_env')
    shutil.copy(ROOT / 'backend' / 'deploy' / 'compose_runtime_env.py', target / 'compose_runtime_env.py')
    return tmp_path


def _edit_staging_overlay(root: Path, mutate) -> None:
    path = root / 'backend' / 'deploy' / 'runtime_env' / 'staging.overlay.yaml'
    doc = yaml.safe_load(path.read_text())
    mutate(doc)
    path.write_text(yaml.safe_dump(doc, sort_keys=False))


def test_staging_composes_and_passes_the_fence(composer):
    staging = composer.compose_staging(inputs=INPUTS)
    services = staging['cloud_run']['services']
    assert set(services) == {'backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration'}
    for name, config in services.items():
        assert config['deploy_name'] == f'{name}-staging'
        assert config['service_account'].startswith('staging-runtime@based-hardware-dev.')
        env = {key: entry['value'] for key, entry in config['env'].items()}
        assert env['OMI_DEPLOYMENT'] == 'staging'
        assert env['OMI_ENV_STAGE'] == 'prod'
        assert env['FIRESTORE_DATABASE_ID'] == 'staging'
        assert env['REDIS_DB_HOST'] == '10.0.0.7'
        assert all(entry['secret'].startswith('staging-') for entry in config['secrets'].values())
        for key, value in env.items():
            if key.endswith('_QUEUE'):
                assert value.startswith('staging-'), key
    assert composer.staging_fence_errors(staging) == []


def test_staging_enrichment_routes_to_its_queue_on_backend_sync(composer):
    # Plan C3 'staging at M2': new sr- obligations go to staging-enrichment, served and verified by backend-sync.
    services = composer.compose_staging(inputs=INPUTS)['cloud_run']['services']
    for config in services.values():
        env = config['env']
        assert env['ENRICHMENT_ROUTE']['value'] == 'enrichment_queue'
        assert env['ENRICHMENT_TASKS_QUEUE']['value'] == 'staging-enrichment'
        handler = env['ENRICHMENT_TASKS_HANDLER_URL']['value']
        assert handler.startswith('https://backend-sync-staging-') and handler.endswith('/v2/enrichment/run')
        assert env['ENRICHMENT_TASKS_OIDC_AUDIENCE']['value'] == handler


def test_staging_services_idle_at_min_zero_after_right_sizing(composer):
    # 2026-10-24 right-sizing (lead's live change, mirrored): staging idles at min 0
    # everywhere. The serving loop (reconcile, projection, recovery) still runs only
    # on backend-integration; a replay window warms it with --warm.
    services = composer.compose_staging(inputs=INPUTS)['cloud_run']['services']
    assert services['backend-integration']['env']['BATCH_PIPELINE_SERVING_ENABLED']['value'] == 'true'
    for name in ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration'):
        assert services[name]['flags']['--min-instances'] == '0'


def test_staging_backfill_service_owns_its_sync_tasks_audience(composer):
    # Prod's deploy gives backend-sync-backfill its own sync-jobs URL. With backend-sync's, the
    # backfill service rejected its own Cloud Tasks: 403, wrong OIDC audience.
    services = composer.compose_staging(inputs=INPUTS)['cloud_run']['services']
    for service in ('backend-sync', 'backend-sync-backfill'):
        env = services[service]['env']
        own = f'https://{service}-staging-'
        assert env['SYNC_TASKS_HANDLER_URL']['value'].startswith(own)
        assert env['SYNC_TASKS_OIDC_AUDIENCE']['value'] == env['SYNC_TASKS_HANDLER_URL']['value']
    assert services['backend-sync']['env']['SYNC_BACKFILL_TASKS_OIDC_AUDIENCE']['value'].startswith(
        'https://backend-sync-backfill-staging-'
    )


def test_staging_sync_services_dispatch_through_cloud_tasks(composer):
    # Prod sets these per service outside runtime_env.yaml. Inline sync dispatch makes the backfill
    # lane fail closed (sync_backfill_dispatch_unavailable, upload 503) for owners not on batch.
    services = composer.compose_staging(inputs=INPUTS)['cloud_run']['services']
    mode = {name: config['env'].get('SYNC_DISPATCH_MODE', {}).get('value') for name, config in services.items()}
    assert mode == {
        'backend': None,
        'backend-sync': 'cloud_tasks',
        'backend-sync-backfill': 'cloud_tasks',
        'backend-integration': None,
    }
    for config in services.values():
        assert config['env']['ACCOUNT_DELETION_DISPATCH_MODE']['value'] == 'cloud_tasks'
        assert config['env']['ACCOUNT_DELETION_TASKS_QUEUE']['value'].startswith('staging-')


def test_staging_services_run_the_a2_jobstore_shadow_as_their_own_identity(composer):
    for config in composer.compose_staging(inputs=INPUTS)['cloud_run']['services'].values():
        env = {key: entry['value'] for key, entry in config['env'].items()}
        assert env['BATCH_JOBSTORE_MODE'] == 'shadow'
        assert env['JOBSTORE_SHADOW_WRITES'] == 'on'
        assert env['JOBSTORE_PG_DATABASE'] == 'jobstore_staging'
        assert env['JOBSTORE_PG_USER'] == config['service_account'].removesuffix('.gserviceaccount.com')


def test_staging_hosted_speech_endpoints_never_reach_prod(composer):
    services = composer.compose_staging(inputs=INPUTS)['cloud_run']['services']
    for config in services.values():
        for name in ('HOSTED_PARAKEET_API_URL', 'HOSTED_DIARIZATION_API_URL', 'HOSTED_SPEAKER_EMBEDDING_API_URL'):
            if name in config['env']:
                assert config['env'][name]['value'] == 'http://127.0.0.1:9', name
        assert not any(
            'omi.me' in str(entry.get('value', '')) or '172.16.160.' in str(entry.get('value', ''))
            for entry in config['env'].values()
        )


def test_prod_speech_endpoint_left_in_place_fails_compose(tmp_path):
    root = _copy_tree(tmp_path)

    def mutate(doc):
        for env in doc['overlay']['cloud_run']['services'].values():
            env['env'].pop('HOSTED_PARAKEET_API_URL')
            env['env'].pop('HOSTED_SPEAKER_EMBEDDING_API_URL')

    _edit_staging_overlay(root, mutate)
    problems = staging_check.staging_diff(root)
    assert problems and all(scope == 'compose' for scope, _, _ in problems)
    assert any('HOSTED_PARAKEET_API_URL' in problem for _, _, problem in problems)
    assert any('HOSTED_SPEAKER_EMBEDDING_API_URL' in problem for _, _, problem in problems)


def test_staging_requires_the_redis_input(composer):
    with pytest.raises(composer.StagingComposeError, match='STAGING_REDIS_HOST'):
        composer.compose_staging(inputs={})


def test_staging_does_not_change_runtime_env_yaml(composer):
    assert set(composer.compose_manifest()['environments']) == {'dev', 'prod'}


def test_current_tree_mirrors_prod():
    assert staging_check.staging_diff(ROOT) == []


def test_non_allowlisted_difference_is_reported(tmp_path):
    root = _copy_tree(tmp_path)

    def mutate(doc):
        doc['overlay']['cloud_run']['services']['backend']['env']['BATCH_PIPELINE_PERCENT'] = {'value': '7'}

    _edit_staging_overlay(root, mutate)
    problems = staging_check.staging_diff(root)
    assert ('backend', 'BATCH_PIPELINE_PERCENT', 'env value differs from prod') in problems or (
        'backend',
        'BATCH_PIPELINE_PERCENT',
        'env only in staging',
    ) in problems


def test_prod_bucket_left_in_place_fails_compose(tmp_path):
    root = _copy_tree(tmp_path)

    def mutate(doc):
        del doc['cloud_run']['env_all']['BUCKET_BATCH_PIPELINE']

    _edit_staging_overlay(root, mutate)
    problems = staging_check.staging_diff(root)
    assert problems and all(scope == 'compose' for scope, _, _ in problems)
    assert any('BUCKET_BATCH_PIPELINE' in problem for _, _, problem in problems)


def test_unmapped_queue_fails_compose(tmp_path):
    root = _copy_tree(tmp_path)

    def mutate(doc):
        # Prod's SYNC_TASKS_QUEUE moved to sync-jobs-fresh (#22460); unmap both legacy names.
        for queue in ('sync-jobs', 'sync-jobs-fresh'):
            doc['cloud_run']['queue_map'].pop(queue, None)

    _edit_staging_overlay(root, mutate)
    problems = staging_check.staging_diff(root)
    assert any('SYNC_TASKS_QUEUE has no staging mapping' in problem for _, _, problem in problems)


def test_non_staging_secret_binding_is_reported(tmp_path):
    root = _copy_tree(tmp_path)

    def mutate(doc):
        doc['cloud_run']['secret_map']['ENCRYPTION_SECRET'] = 'ENCRYPTION_SECRET'

    _edit_staging_overlay(root, mutate)
    problems = staging_check.staging_diff(root)
    assert any(name == 'ENCRYPTION_SECRET' and 'staging-*' in problem for _, name, problem in problems)


# CodeQL clear-text logging: neither output can carry a payload, only names and staging-* references.
def _render_module():
    import importlib.util

    path = ROOT / 'backend' / 'deploy' / 'staging' / 'render_cloud_run.py'
    spec = importlib.util.spec_from_file_location('_staging_render_cloud_run', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rendered_flags_carry_only_validated_mount_references(composer):
    import re

    render = _render_module()
    staging = composer.compose_staging(inputs=INPUTS)
    for service in staging['cloud_run']['services']:
        env, flags = render.render(staging, service, release_sha='a' * 40, release_tree='b' * 40)
        mounts = [flag for flag in flags if flag.startswith('--set-secrets=')]
        assert len(mounts) == 1
        for ref in mounts[0].removeprefix('--set-secrets=').split(','):
            assert re.fullmatch(r'[A-Z][A-Z0-9_]*=staging-[a-z0-9-]+:(latest|[0-9]+)', ref), ref
            assert ref.split('=')[0] not in env  # a mounted name never also travels as a literal value


def test_payload_shaped_mount_reference_is_refused():
    render = _render_module()
    payload = 'sk_live_' + 'x' * 24
    config = {'secrets': {'STRIPE_API_KEY': {'secret': payload}}}
    with pytest.raises(SystemExit) as excinfo:
        render.mount_refs(config)
    assert payload not in str(excinfo.value)


def test_diff_summary_prints_names_and_counts_only():
    lines = staging_check.summary(
        [('backend', 'ENCRYPTION_SECRET', 'staging secret binding is not a staging-* secret')]
    )
    assert lines[-1] == '1 difference(s) outside STAGING_DIFF_ALLOWLIST'
    assert 'backend/ENCRYPTION_SECRET' in lines[0] and ': 1 (' in lines[0]


def _post_render_module():
    import importlib.util

    path = ROOT / 'backend' / 'deploy' / 'staging' / 'worker_post_render.py'
    spec = importlib.util.spec_from_file_location('_staging_worker_post_render', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _worker_doc():
    return {
        'kind': 'Deployment',
        'spec': {
            'template': {
                'spec': {
                    'containers': [
                        {
                            'name': 'worker',
                            'command': ['python', '-m', 'diarizer.batch_pipeline_runtime'],
                            'env': [{'name': 'BUCKET_BATCH_PIPELINE', 'value': 'based-hardware-dev-staging-batch'}],
                        }
                    ]
                }
            }
        },
    }


def test_worker_post_render_env_sources_and_probe(tmp_path):
    render = _post_render_module()
    env_file = tmp_path / 'worker_env.yaml'
    env_file.write_text(
        "JOBSTORE_MODE: shadow\nJOBSTORE_PW:\n  secretKeyRef: {name: staging-jobstore, key: password}\n"
    )
    entries = render._env_entries(env_file, ['BATCH_PIPELINE_ASR_LEFT_CONTEXT_SECONDS=8'])
    (doc,) = render.patch([_worker_doc()], entries, 'staging-asrctx-probe')
    container = doc['spec']['template']['spec']['containers'][0]
    env = {e['name']: e for e in container['env']}
    assert env['OMI_DEPLOYMENT']['value'] == 'staging'
    assert env['JOBSTORE_PW'] == {
        'name': 'JOBSTORE_PW',
        'valueFrom': {'secretKeyRef': {'name': 'staging-jobstore', 'key': 'password'}},
    }
    assert env['BATCH_PIPELINE_ASR_LEFT_CONTEXT_SECONDS']['value'] == '8'
    assert container['command'] == ['python', '/asrctx-probe/asrctx_probe.py']


def test_worker_post_render_refuses_redefinition_and_inline_mappings(tmp_path):
    render = _post_render_module()
    with pytest.raises(SystemExit):
        render.patch([_worker_doc()], render._env_entries(None, ['BUCKET_BATCH_PIPELINE=other']))
    bad = tmp_path / 'worker_env.yaml'
    bad.write_text("X_PW:\n  value: inline\n")
    with pytest.raises(SystemExit):
        render._env_entries(bad, [])


def test_worker_post_render_sets_on_demand_replicas():
    render = _post_render_module()
    entries = render._env_entries(None, [])
    (doc,) = render.patch([_worker_doc()], entries, replicas=0)
    assert doc['spec']['replicas'] == 0
    (doc,) = render.patch([_worker_doc()], entries, replicas=2)
    assert doc['spec']['replicas'] == 2
    (doc,) = render.patch([_worker_doc()], entries)
    assert 'replicas' not in doc['spec']
    with pytest.raises(SystemExit):
        render.patch([_worker_doc()], entries, replicas=-1)
    with pytest.raises(SystemExit):
        render.patch([{'kind': 'HorizontalPodAutoscaler'}, _worker_doc()], entries, replicas=0)
