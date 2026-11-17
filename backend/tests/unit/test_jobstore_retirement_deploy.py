"""Prepared target identity, dark activation and staging render isolation."""

from pathlib import Path
import runpy

import yaml

from tests.unit.test_batch_pipeline_chart import CHART, enabled_arguments, render

ROOT = Path(__file__).resolve().parents[3]
OPTIONAL_PROJECTS = ('OMI_FIRESTORE_DATA_PLANE_PROJECT', 'GCLOUD_PROJECT', 'GCP_PROJECT', 'FIREBASE_PROJECT_ID')


def test_cloud_run_and_listen_deletion_executors_have_complete_dark_target_context():
    manifest = yaml.load((ROOT / 'backend/deploy/runtime_env.yaml').read_text(), Loader=yaml.CSafeLoader)[
        'environments'
    ]['prod']
    from utils.staging_fence import _PRODUCTION_MIRROR_CONTEXT

    required = {
        **_PRODUCTION_MIRROR_CONTEXT,
        'JOBSTORE_PG_HOST': '172.25.29.2',
        'JOBSTORE_PG_DATABASE': 'jobstore_prod',
        'JOBSTORE_SHADOW_NAMESPACES': 'batch_pipeline_prod',
        'JOBSTORE_PRODUCTION_MIRROR': 'off',
        'BATCH_JOBSTORE_MODE': 'firestore',
    }
    for name in ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration'):
        env = manifest['cloud_run']['services'][name]['env']
        assert all(env[key]['value'] == value for key, value in required.items())
        assert all(env[key]['value'] == 'based-hardware' for key in OPTIONAL_PROJECTS if key in env)
        assert env['JOBSTORE_PG_USER']['value'] == 'backend-runtime@based-hardware.iam'
    env = manifest['gke']['backend-listen']['env']
    assert all(env[key]['value'] == value for key, value in required.items())
    assert env['JOBSTORE_PG_USER']['value'] == 'backend-listen-runtime@based-hardware.iam'
    assert (
        manifest['cloud_run']['services']['backend-integration']['env']['BATCH_PIPELINE_SERVING_ENABLED']['value']
        == 'true'
    )


def test_prod_worker_target_is_optional_in_shared_chart_and_matches_pod_identity():
    result = render(
        '-f', str(CHART / 'prod_omi_batch-pipeline-worker_values.yaml'), '--set', 'image.digest=sha256:' + 'a' * 64
    )
    assert result.returncode == 0, result.stderr
    workers = 0
    for doc in yaml.safe_load_all(result.stdout):
        if not doc or doc['kind'] != 'Deployment':
            continue
        pod = doc['spec']['template']['spec']
        if pod['containers'][0]['name'] != 'worker':
            continue
        workers += 1
        entries = pod['containers'][0]['env']
        assert len(entries) == len({entry['name'] for entry in entries})
        env = {entry['name']: entry.get('value') for entry in entries}
        assert env['JOBSTORE_PG_USER'] == 'batch-pipeline-worker@based-hardware.iam'
        assert env['JOBSTORE_PG_HOST'] == '172.25.29.2'
        assert env['JOBSTORE_PRODUCTION_MIRROR'] == 'off' and env['BATCH_JOBSTORE_MODE'] == 'firestore'
        assert env['GOOGLE_CLOUD_PROJECT'] == env['OMI_CUSTOMER_DATA_PROJECT'] == 'based-hardware'
        assert env['OMI_DEPLOYMENT'] == 'prod' and env['FIRESTORE_DATABASE_ID'] == '(default)'
    assert workers >= 1


def test_staging_post_render_has_no_duplicate_target_names_or_production_target():
    result = render(*enabled_arguments())
    assert result.returncode == 0, result.stderr
    post = runpy.run_path(str(ROOT / 'backend/deploy/staging/worker_post_render.py'))
    docs = list(yaml.safe_load_all(result.stdout))
    post['patch'](docs, post['_env_entries'](ROOT / 'backend/deploy/staging/worker_env.yaml', []))
    deployment = next(doc for doc in docs if doc and doc['kind'] == 'Deployment')
    entries = deployment['spec']['template']['spec']['containers'][0]['env']
    assert len(entries) == len({entry['name'] for entry in entries})
    env = {entry['name']: entry.get('value') for entry in entries}
    assert env['JOBSTORE_PG_HOST'] != '172.25.29.2'
    assert env['JOBSTORE_PG_USER'] == 'staging-worker@based-hardware-dev.iam'
