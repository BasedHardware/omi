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
        doc['overlay'] = {'cloud_run': {'services': {'backend': {'env': {'BATCH_PIPELINE_PERCENT': {'value': '7'}}}}}}

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
        del doc['cloud_run']['queue_map']['sync-jobs']

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
