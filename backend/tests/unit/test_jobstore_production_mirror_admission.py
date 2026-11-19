"""Production mirror admission never turns the existing namespace-only seam into a production copier."""

import pytest

from utils.staging_fence import jobstore_production_mirror_configured, jobstore_shadow_admits

NAMESPACE = 'batch_pipeline_prod'
OWNER = 'a' * 64


def _production_env():
    return {
        'OMI_DEPLOYMENT': 'prod',
        'OMI_ENV_STAGE': 'prod',
        'GOOGLE_CLOUD_PROJECT': 'based-hardware',
        'OMI_CUSTOMER_DATA_PROJECT': 'based-hardware',
        'OMI_FIRESTORE_DATA_PLANE_PROJECT': 'based-hardware',
        'FIRESTORE_DATABASE_ID': '(default)',
        'JOBSTORE_SHADOW_NAMESPACES': NAMESPACE,
        'JOBSTORE_PRODUCTION_MIRROR': 'on',
        'JOBSTORE_PRODUCTION_MIRROR_SAMPLE_BPS': '10000',
        'JOBSTORE_PG_HOST': '10.1.2.3',
        'JOBSTORE_PG_DATABASE': 'synthetic-jobstore',
        'JOBSTORE_PG_USER': 'synthetic-runtime',
    }


def test_configured_production_still_refuses_every_namespace_only_caller():
    env = _production_env()
    assert jobstore_production_mirror_configured(env)
    assert not jobstore_shadow_admits(NAMESPACE, env)
    assert jobstore_shadow_admits(NAMESPACE, env, owner_key=OWNER)


@pytest.mark.parametrize('name', tuple(_production_env()))
def test_every_missing_production_setting_refuses_an_owner(name):
    env = _production_env()
    del env[name]
    assert not jobstore_production_mirror_configured(env)
    assert not jobstore_shadow_admits(NAMESPACE, env, owner_key=OWNER)


@pytest.mark.parametrize(
    ('name', 'value'),
    [
        ('OMI_DEPLOYMENT', 'dev'),
        ('OMI_DEPLOYMENT', 'production'),
        ('OMI_DEPLOYMENT', ' prod'),
        ('OMI_ENV_STAGE', 'dev'),
        ('OMI_ENV_STAGE', 'prod '),
        ('GOOGLE_CLOUD_PROJECT', 'based-hardware-dev'),
        ('OMI_CUSTOMER_DATA_PROJECT', 'based-hardware-dev'),
        ('OMI_FIRESTORE_DATA_PLANE_PROJECT', 'based-hardware-dev'),
        ('FIRESTORE_DATABASE_ID', ''),
        ('FIRESTORE_DATABASE_ID', 'staging'),
        ('FIRESTORE_DATABASE_ID', 'prod'),
        ('FIRESTORE_EMULATOR_HOST', '127.0.0.1:8080'),
        ('GCLOUD_PROJECT', 'based-hardware-dev'),
        ('GCP_PROJECT', 'based-hardware-dev'),
        ('FIREBASE_PROJECT_ID', 'based-hardware-dev'),
        ('JOBSTORE_SHADOW_NAMESPACES', '*'),
        ('JOBSTORE_SHADOW_NAMESPACES', 'batch_pipeline_dev'),
        ('JOBSTORE_SHADOW_NAMESPACES', 'batch_pipeline_prod_extra'),
        ('JOBSTORE_PRODUCTION_MIRROR', 'off'),
        ('JOBSTORE_PRODUCTION_MIRROR', 'ON'),
        ('JOBSTORE_PRODUCTION_MIRROR', 'true'),
        ('JOBSTORE_PRODUCTION_MIRROR', '1'),
        ('JOBSTORE_PRODUCTION_MIRROR', ' on'),
        ('JOBSTORE_PG_HOST', ' '),
        ('JOBSTORE_PG_DATABASE', ''),
        ('JOBSTORE_PG_USER', ''),
    ],
)
def test_misconfigured_production_refuses_an_owner(name, value):
    env = {**_production_env(), name: value}
    assert not jobstore_production_mirror_configured(env)
    assert not jobstore_shadow_admits(NAMESPACE, env, owner_key=OWNER)


@pytest.mark.parametrize('bps', ['', '0', '-1', '10001', '01', '+1', '1.0', 'all', ' 1', '1 ', '١'])
def test_malformed_sample_size_cannot_admit_a_production_owner(bps):
    env = {**_production_env(), 'JOBSTORE_PRODUCTION_MIRROR_SAMPLE_BPS': bps}
    assert not jobstore_production_mirror_configured(env)
    assert not jobstore_shadow_admits(NAMESPACE, env, owner_key=OWNER)


@pytest.mark.parametrize(
    'owner', [None, '', 'synthetic-user', 'a' * 63, 'a' * 65, 'A' * 64, 'g' * 64, ' ' + OWNER, OWNER + ' ']
)
def test_only_a_canonical_resolved_owner_can_be_sampled(owner):
    assert not jobstore_shadow_admits(NAMESPACE, _production_env(), owner_key=owner)


@pytest.mark.parametrize(('owner', 'bucket'), [('0' * 64, 9711), ('a' * 64, 6563), ('f' * 64, 1328)])
def test_versioned_cohort_has_stable_owner_boundary_vectors(owner, bucket):
    env = {**_production_env(), 'JOBSTORE_PRODUCTION_MIRROR_SAMPLE_BPS': str(bucket)}
    assert not jobstore_shadow_admits(NAMESPACE, env, owner_key=owner)
    env['JOBSTORE_PRODUCTION_MIRROR_SAMPLE_BPS'] = str(bucket + 1)
    assert jobstore_shadow_admits(NAMESPACE, env, owner_key=owner)
    # Raising the threshold only adds owners; each owner's entire row family shares the decision.
    env['JOBSTORE_PRODUCTION_MIRROR_SAMPLE_BPS'] = '10000'
    assert jobstore_shadow_admits(NAMESPACE, env, owner_key=owner)


@pytest.mark.parametrize(
    'namespace', [' batch_pipeline_prod', 'batch_pipeline_prod ', 'batch_pipeline_prod_extra', '*', '']
)
def test_namespace_input_is_not_normalized_into_production(namespace):
    assert not jobstore_shadow_admits(namespace, _production_env(), owner_key=OWNER)


def test_staging_production_namespace_admission_keeps_its_existing_contract():
    env = {
        'OMI_DEPLOYMENT': 'staging',
        'FIRESTORE_DATABASE_ID': 'staging',
        'JOBSTORE_SHADOW_NAMESPACES': NAMESPACE,
    }
    assert jobstore_shadow_admits(NAMESPACE, env)
    assert not jobstore_production_mirror_configured(env)
    # Production opt-in can never let a staging process point at the production database.
    env = {**_production_env(), 'OMI_DEPLOYMENT': 'staging'}
    assert not jobstore_shadow_admits(NAMESPACE, env, owner_key=OWNER)


def test_other_explicitly_admitted_namespaces_keep_their_existing_contract():
    assert jobstore_shadow_admits('batch_pipeline_dev', {'JOBSTORE_SHADOW_NAMESPACES': 'batch_pipeline_dev'})
    assert jobstore_shadow_admits(
        'batch_pipeline_test_example', {'JOBSTORE_SHADOW_NAMESPACES': 'batch_pipeline_test_example'}
    )


def test_process_environment_is_checked_at_each_call(monkeypatch):
    for name in ('FIRESTORE_EMULATOR_HOST', 'GCLOUD_PROJECT', 'GCP_PROJECT', 'FIREBASE_PROJECT_ID'):
        monkeypatch.delenv(name, raising=False)
    for name, value in _production_env().items():
        monkeypatch.setenv(name, value)
    assert jobstore_shadow_admits(NAMESPACE, owner_key=OWNER)
    monkeypatch.setenv('JOBSTORE_PRODUCTION_MIRROR', 'off')
    assert not jobstore_shadow_admits(NAMESPACE, owner_key=OWNER)
