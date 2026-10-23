"""Negative cases for the staging isolation fence: one per contract (i) bullet, plus the clean case."""

import hashlib

import pytest

from database import _client
from utils import staging_fence
from utils.staging_fence import (
    PROD_DATA_PLANE_HASHES,
    StagingFenceError,
    assert_staging_isolation,
    staging_violations,
)


def _clean_env() -> dict[str, str]:
    return {
        'OMI_DEPLOYMENT': 'staging',
        'OMI_ENV_STAGE': 'prod',
        'OMI_CUSTOMER_DATA_PROJECT': 'based-hardware-dev',
        'GOOGLE_CLOUD_PROJECT': 'based-hardware-dev',
        'FIRESTORE_DATABASE_ID': 'staging',
        'FIREBASE_AUTH_PROJECT_ID': 'based-hardware-dev',
        'FIREBASE_SIGNER_SERVICE_ACCOUNT': 'staging-runtime@based-hardware-dev.iam.gserviceaccount.com',
        'REDIS_DB_HOST': '10.128.0.42',
        'REDIS_DB_PORT': '6379',
        'BUCKET_TEMPORAL_SYNC_LOCAL': 'based-hardware-dev-staging-sync',
        'BUCKET_BATCH_PIPELINE': 'based-hardware-dev-staging-batch',
        'BUCKET_PRIVATE_CLOUD_SYNC': 'based-hardware-dev-staging-sync',
        'MCP_AUTHORIZATION_SERVER_URL': 'https://backend-staging-dt5lrfkkoa-uc.a.run.app',
        'LIFECYCLE_EMAIL_FROM_ADDRESS': 'staging-no-send@based-hardware-dev.invalid',
        'SHARE_EMAIL_FROM_ADDRESS': 'staging-no-send@based-hardware-dev.invalid',
        'SYNC_TASKS_QUEUE': 'staging-sync-jobs',
        'BATCH_PIPELINE_API_URL': 'https://backend-sync-staging-dt5lrfkkoa-uc.a.run.app',
    }


def _reasons(env: dict[str, str]) -> set[str]:
    return {reason for reason, _ in staging_violations(env)}


def test_clean_staging_env_passes():
    env = _clean_env()
    assert staging_violations(env) == []
    assert_staging_isolation(env)


def test_non_staging_deployment_is_a_noop():
    env = {'OMI_CUSTOMER_DATA_PROJECT': 'based-hardware', 'REDIS_DB_HOST': 'redis.example.com'}
    assert staging_violations(env) == []
    assert_staging_isolation(env)


# Bullet 1: customer-data / compute / data-plane project must be based-hardware-dev.
@pytest.mark.parametrize(
    'name', ['OMI_CUSTOMER_DATA_PROJECT', 'GOOGLE_CLOUD_PROJECT', 'OMI_FIRESTORE_DATA_PLANE_PROJECT']
)
def test_prod_project_is_refused(name):
    env = _clean_env()
    env[name] = 'based-hardware'
    assert ('project', name) in staging_violations(env)
    with pytest.raises(StagingFenceError):
        assert_staging_isolation(env)


def test_missing_customer_project_is_refused():
    env = _clean_env()
    del env['OMI_CUSTOMER_DATA_PROJECT']
    assert ('project', 'OMI_CUSTOMER_DATA_PROJECT') in staging_violations(env)


def test_mounted_key_credential_is_refused():
    env = _clean_env()
    env['SERVICE_ACCOUNT_JSON'] = '{"project_id": "based-hardware-dev"}'
    assert ('key_credential', 'SERVICE_ACCOUNT_JSON') in staging_violations(env)


# Bullet 2: database, Firebase auth project, signer SA.
def test_default_database_is_refused():
    env = _clean_env()
    env['FIRESTORE_DATABASE_ID'] = '(default)'
    assert ('database', 'FIRESTORE_DATABASE_ID') in staging_violations(env)


def test_missing_database_is_refused():
    env = _clean_env()
    del env['FIRESTORE_DATABASE_ID']
    assert 'database' in _reasons(env)


def test_prod_auth_project_is_refused():
    env = _clean_env()
    env['FIREBASE_AUTH_PROJECT_ID'] = 'based-hardware'
    assert ('auth_project', 'FIREBASE_AUTH_PROJECT_ID') in staging_violations(env)


def test_prod_signer_is_refused():
    env = _clean_env()
    env['FIREBASE_SIGNER_SERVICE_ACCOUNT'] = 'backend-runtime@based-hardware.iam.gserviceaccount.com'
    assert ('signer', 'FIREBASE_SIGNER_SERVICE_ACCOUNT') in staging_violations(env)


# Bullet 3: Redis host hash in PROD_DATA_PLANE_HASHES, and the private-address rule.
def test_prod_hash_listed_value_is_refused(monkeypatch):
    fake_prod_redis = '10.9.9.9'
    monkeypatch.setattr(
        staging_fence,
        'PROD_DATA_PLANE_HASHES',
        PROD_DATA_PLANE_HASHES | {hashlib.sha256(fake_prod_redis.encode()).hexdigest()},
    )
    env = _clean_env()
    env['REDIS_DB_HOST'] = fake_prod_redis
    assert ('prod_hash', 'REDIS_DB_HOST') in staging_violations(env)


def test_public_redis_host_is_refused():
    env = _clean_env()
    env['REDIS_DB_HOST'] = 'redis-13151.c1.us-central1-2.gce.cloud.redislabs.com'
    assert ('redis_host', 'REDIS_DB_HOST') in staging_violations(env)


def test_prod_bucket_by_hash_is_refused():
    env = _clean_env()
    env['BUCKET_BATCH_PIPELINE'] = 'based-hardware-dev-batch-pipeline-staging'  # dev's bucket, listed by hash
    assert ('prod_hash', 'BUCKET_BATCH_PIPELINE') in staging_violations(env)


def test_hashes_are_hex_digests_not_values():
    assert all(len(h) == 64 and int(h, 16) >= 0 for h in PROD_DATA_PLANE_HASHES)


# Bullet 4: any based-hardware (non -dev) URL, bucket or index name anywhere in the env.
@pytest.mark.parametrize(
    'value',
    [
        'https://backend-sync-hhibjajaja-uc.a.run.app',
        'based-hardware-audio-derived',
        'projects/based-hardware/secrets/X',
        'https://api.omi.me/v1',
        'http://parakeet.omi.me',
        'omi.me',
    ],
)
def test_prod_reference_anywhere_is_refused(value):
    env = _clean_env()
    env['SOME_URL'] = value
    assert 'prod_reference' in _reasons(env) or 'prod_hash' in _reasons(env)


# M1 review L02-1: prod ILBs (Parakeet, diarizer) and prod external LB addresses.
@pytest.mark.parametrize(
    'value', ['http://172.16.160.20/diarizer', 'http://172.16.160.20/diarizer-batch', '172.16.128.250', '34.54.223.100']
)
def test_prod_network_address_anywhere_is_refused(value):
    env = _clean_env()
    env['HOSTED_SPEAKER_EMBEDDING_API_URL'] = value
    assert _reasons(env) == {'prod_address'}


@pytest.mark.parametrize(
    'value', ['http://127.0.0.1:9', 'http://172.16.48.49/diarizer', '172.16.63.67', '172.20.207.3', 'nomi.mesh.dev']
)
def test_dev_and_blackhole_addresses_are_allowed(value):
    env = _clean_env()
    env['HOSTED_PARAKEET_API_URL'] = value
    assert staging_violations(env) == []


def test_dev_references_are_allowed():
    env = _clean_env()
    env['X'] = 'gs://based-hardware-dev-staging-mirror/a'
    env['Y'] = 'staging-runtime@based-hardware-dev.iam.gserviceaccount.com'
    assert staging_violations(env) == []


def test_error_never_contains_values():
    env = _clean_env()
    secret_looking = 'redis-13151.c1.example.cloud.redislabs.com'
    env['REDIS_DB_HOST'] = secret_looking
    with pytest.raises(StagingFenceError) as excinfo:
        assert_staging_isolation(env)
    assert secret_looking not in str(excinfo.value)
    assert 'REDIS_DB_HOST' in str(excinfo.value)


def test_process_env_check_is_cached(monkeypatch):
    staging_fence.reset_for_tests()
    monkeypatch.setenv('OMI_DEPLOYMENT', 'staging')
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'based-hardware')
    with pytest.raises(StagingFenceError):
        assert_staging_isolation()
    staging_fence.reset_for_tests()
    monkeypatch.delenv('OMI_DEPLOYMENT')
    assert_staging_isolation()  # non-staging: no-op, then cached
    monkeypatch.setenv('OMI_DEPLOYMENT', 'staging')
    assert_staging_isolation()  # cached: does not re-evaluate
    staging_fence.reset_for_tests()


# database/_client.py named-DB allowance (contract (i)).
def _set_env(monkeypatch, env: dict[str, str]) -> None:
    import os

    # The fence scans the whole process env: drop ambient prod-looking values
    # (e.g. an agent shell's CLOUDSDK_CORE_PROJECT) so only the fixture is judged.
    for name in list(os.environ):
        if staging_violations({**_clean_env(), name: os.environ[name]}):
            monkeypatch.delenv(name)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    staging_fence.reset_for_tests()


def test_client_allows_staging_db_only_for_staging_in_dev_project(monkeypatch):
    _set_env(monkeypatch, _clean_env())
    assert _client._firestore_database_id('based-hardware-dev') == 'staging'
    with pytest.raises(RuntimeError, match='restricted'):
        _client._firestore_database_id('based-hardware')
    with pytest.raises(RuntimeError, match='restricted'):
        _client._firestore_database_id(None)
    staging_fence.reset_for_tests()


def test_client_refuses_staging_db_outside_staging(monkeypatch):
    monkeypatch.delenv('OMI_DEPLOYMENT', raising=False)
    monkeypatch.setenv('FIRESTORE_DATABASE_ID', 'staging')
    staging_fence.reset_for_tests()
    with pytest.raises(RuntimeError, match='restricted'):
        _client._firestore_database_id('based-hardware-dev')
    staging_fence.reset_for_tests()


def test_client_runs_fence_before_building_a_client(monkeypatch):
    env = _clean_env()
    env['OMI_CUSTOMER_DATA_PROJECT'] = 'based-hardware'
    _set_env(monkeypatch, env)
    with pytest.raises(StagingFenceError):
        _client._firestore_database_id('based-hardware')
    staging_fence.reset_for_tests()


# Regression (lane 4 m1p1, 11:29Z): every Firestore client seam must build on the staging DB under the
# staging env. The data-plane seam resolved the named DB before falling back to the default client,
# without a project, and every authenticated request failed closed (account_deletion_state_unavailable).
@pytest.mark.parametrize('data_plane_project', [None, 'based-hardware-dev'])
def test_every_client_seam_builds_on_the_staging_db(monkeypatch, data_plane_project):
    built: list[dict] = []

    class _FakeClient:
        def __init__(self, **kwargs):
            built.append(kwargs)

    env = _clean_env()
    if data_plane_project:
        env['OMI_FIRESTORE_DATA_PLANE_PROJECT'] = data_plane_project
    else:
        monkeypatch.delenv('OMI_FIRESTORE_DATA_PLANE_PROJECT', raising=False)
    _set_env(monkeypatch, env)
    for name in (
        'SERVICE_ACCOUNT_JSON',
        'GOOGLE_APPLICATION_CREDENTIALS',
        'FIREBASE_AUTH_CREDENTIALS_PATH',
        'FIRESTORE_EMULATOR_HOST',
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(_client.firestore, 'Client', _FakeClient)
    monkeypatch.setattr(_client, '_firestore_client', None)

    _client._build_firestore_client()
    _client._build_customer_firestore_client()
    _client._build_data_plane_firestore_client()

    assert built, 'no client was built'
    for kwargs in built:
        assert kwargs.get('database') == 'staging'
        assert kwargs.get('project') == 'based-hardware-dev'
    staging_fence.reset_for_tests()


# L02-2: staging keeps the worker namespace batch_pipeline_prod, so the A2 job-store shadow gate keys on
# the deployment and the Firestore database, not on the namespace alone.


def test_jobstore_shadow_refuses_the_prod_namespace_in_prod():
    assert not staging_fence.jobstore_shadow_admits('batch_pipeline_prod', {'OMI_ENV_STAGE': 'prod'})
    assert not staging_fence.jobstore_shadow_admits('batch_pipeline_prod', {'FIRESTORE_DATABASE_ID': 'staging'})


def test_jobstore_shadow_admits_the_prod_namespace_in_staging_on_the_staging_db():
    assert staging_fence.jobstore_shadow_admits('batch_pipeline_prod', _clean_env())


@pytest.mark.parametrize('database_id', [None, '', '(default)', 'prod'])
def test_jobstore_shadow_refuses_the_staging_flag_on_a_non_staging_db(database_id):
    env = _clean_env()
    if database_id is None:
        env.pop('FIRESTORE_DATABASE_ID')
    else:
        env['FIRESTORE_DATABASE_ID'] = database_id
    assert not staging_fence.jobstore_shadow_admits('batch_pipeline_prod', env)


def test_jobstore_shadow_admits_other_namespaces():
    assert staging_fence.jobstore_shadow_admits('batch_pipeline_dev', {})


def test_unset_key_with_a_prod_code_default_is_refused():
    # utils/other/storage.py falls back to the prod private-cloud-sync bucket when this is unset.
    env = _clean_env()
    del env['BUCKET_PRIVATE_CLOUD_SYNC']
    assert ('prod_default', 'BUCKET_PRIVATE_CLOUD_SYNC') in staging_violations(env)
    with pytest.raises(StagingFenceError):
        assert_staging_isolation(env)


def test_prod_private_cloud_sync_bucket_is_refused():
    env = _clean_env()
    env['BUCKET_PRIVATE_CLOUD_SYNC'] = 'omi-private-cloud-sync'
    assert ('prod_hash', 'BUCKET_PRIVATE_CLOUD_SYNC') in staging_violations(env)


@pytest.mark.parametrize(
    'name', ['MCP_AUTHORIZATION_SERVER_URL', 'LIFECYCLE_EMAIL_FROM_ADDRESS', 'SHARE_EMAIL_FROM_ADDRESS']
)
def test_unset_omi_me_defaults_are_refused(name):
    env = _clean_env()
    del env[name]
    assert ('prod_default', name) in staging_violations(env)


def test_mcp_authorization_server_on_api_omi_me_is_refused():
    env = _clean_env()
    env['MCP_AUTHORIZATION_SERVER_URL'] = 'https://api.omi.me'
    assert ('prod_reference', 'MCP_AUTHORIZATION_SERVER_URL') in staging_violations(env)
