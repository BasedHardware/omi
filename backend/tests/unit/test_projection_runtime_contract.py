"""Projection API and cron surfaces share one explicit production storage contract."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / 'backend' / 'deploy' / 'runtime_env.yaml'


def test_api_and_cron_receive_the_same_projection_bucket_contract():
    manifest = yaml.safe_load(MANIFEST.read_text())

    for environment in ('dev', 'prod'):
        cloud_run = manifest['environments'][environment]['cloud_run']
        api_env = cloud_run['services']['backend']['env']
        job = cloud_run['jobs']['notifications-job']
        job_env = job['env']

        assert api_env['BUCKET_PROJECTION_IMAGES'] == {
            'env_var': 'BUCKET_PROJECTION_IMAGES',
            'category': 'projection_rollout',
        }
        assert job_env['BUCKET_PROJECTION_IMAGES'] == api_env['BUCKET_PROJECTION_IMAGES']
        assert job_env['PROJECTION_ENABLED_USERS']['env_var'] == 'PROJECTION_ENABLED_USERS'
        assert job_env['PROJECTION_ENABLED_USERS']['default'] == ''
        assert job_env['OMI_LLM_GATEWAY_URL']['env_var'] == 'OMI_LLM_GATEWAY_URL'
        assert job_env['REDIS_DB_HOST']['env_var'] == 'REDIS_DB_HOST'
        assert {'OMI_LLM_GATEWAY_SERVICE_TOKEN', 'REDIS_DB_PASSWORD'} <= set(job['secrets'])


def test_deploy_workflows_forward_projection_runtime_variables():
    backend_workflow = (ROOT / '.github' / 'workflows' / 'gcp_backend.yml').read_text()
    automatic_dev_workflow = (ROOT / '.github' / 'workflows' / 'gcp_backend_auto_dev.yml').read_text()
    notifications_workflow = (ROOT / '.github' / 'workflows' / 'gcp_notifications_job.yml').read_text()

    assert 'BUCKET_PROJECTION_IMAGES: ${{ vars.BUCKET_PROJECTION_IMAGES }}' in backend_workflow
    assert 'BUCKET_PROJECTION_IMAGES: ${{ vars.BUCKET_PROJECTION_IMAGES }}' in automatic_dev_workflow
    for expected in (
        'BUCKET_PROJECTION_IMAGES: ${{ vars.BUCKET_PROJECTION_IMAGES }}',
        'OMI_LLM_GATEWAY_URL: ${{ vars.OMI_LLM_GATEWAY_URL }}',
        'PROJECTION_ENABLED_USERS: ${{ vars.PROJECTION_ENABLED_USERS }}',
        'REDIS_DB_HOST: ${{ vars.REDIS_DB_HOST }}',
    ):
        assert expected in notifications_workflow


def test_runtime_documentation_pins_private_and_local_fallback_behavior():
    documentation = (ROOT / 'backend' / 'docs' / 'projections.md').read_text()

    assert 'public access prevention' in documentation
    assert 'deterministic Firestore ID' in documentation
    assert 'Hosted runtimes refuse this fallback' in documentation


def test_projection_deployment_settings_are_classified_as_non_secret_config():
    classification = yaml.safe_load((ROOT / 'config' / 'deployment-setting-classification.json').read_text())

    configured = set(classification['kinds']['config'])
    assert {'BASE_API_URL', 'BUCKET_PROJECTION_IMAGES', 'PROJECTION_ENABLED_USERS'} <= configured
