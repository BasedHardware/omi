import pytest

from config import object_lake
from config.policy.batch import cohort_bucket


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in (
        'BUCKET_OBJECT_LAKE',
        'OBJECT_LAKE_KMS_KEY',
        'OBJECT_LAKE_WRITE_ENABLED',
        'OBJECT_LAKE_WRITE_PERCENT',
        'OBJECT_LAKE_READ_ENABLED',
        'OBJECT_LAKE_INLINE_MAX_BYTES',
        'OBJECT_LAKE_RELEASE',
        'OBJECT_LAKE_KEY_CACHE_TTL_SECONDS',
        'OMI_ENV_STAGE',
    ):
        monkeypatch.delenv(name, raising=False)


def test_defaults():
    assert object_lake.bucket() == object_lake.kms_key() == ''
    assert not object_lake.write_enabled()
    assert object_lake.write_percent() == 0
    assert object_lake.read_enabled()
    assert object_lake.inline_max_bytes() == 4096
    assert object_lake.key_cache_ttl_seconds() == 86400
    assert object_lake.release() == 'v1'
    assert not object_lake.write_admitted('s')
    assert object_lake.put_deadline_seconds() == 5


@pytest.mark.parametrize('raw', ['bad', '-1', '101', 'nan', 'inf', ''])
def test_bad_percent_admits_nobody(monkeypatch, raw):
    monkeypatch.setenv('OBJECT_LAKE_WRITE_ENABLED', 'true')
    monkeypatch.setenv('OBJECT_LAKE_WRITE_PERCENT', raw)
    assert object_lake.write_percent() == 0
    assert not any(object_lake.write_admitted(str(i)) for i in range(100))


def test_deterministic_separate_salt_and_master_gate(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'offline')
    monkeypatch.setenv('BUCKET_OBJECT_LAKE', 'test-lake')
    monkeypatch.setenv('OBJECT_LAKE_KMS_KEY', 'test-key')
    monkeypatch.setenv('OBJECT_LAKE_WRITE_ENABLED', 'true')
    monkeypatch.setenv('OBJECT_LAKE_WRITE_PERCENT', '42.5')
    first = [object_lake.write_admitted(str(i)) for i in range(200)]
    assert first == [object_lake.write_admitted(str(i)) for i in range(200)]
    assert first == [cohort_bucket(str(i), 'object-lake', bits=64) < 42.5 for i in range(200)]
    assert any(first) and not all(first)
    monkeypatch.setenv('OBJECT_LAKE_WRITE_PERCENT', '0')
    assert not any(object_lake.write_admitted(str(i)) for i in range(200))
    monkeypatch.setenv('OBJECT_LAKE_WRITE_PERCENT', '100')
    assert object_lake.write_admitted('s') and not object_lake.write_admitted('')
    monkeypatch.setenv('OBJECT_LAKE_WRITE_ENABLED', 'false')
    assert not object_lake.write_admitted('s')


def test_env_is_read_at_call_time(monkeypatch):
    monkeypatch.setenv('BUCKET_OBJECT_LAKE', ' dev-lake ')
    monkeypatch.setenv('OBJECT_LAKE_KMS_KEY', ' dev-key ')
    monkeypatch.setenv('OBJECT_LAKE_RELEASE', 'v2')
    monkeypatch.setenv('OBJECT_LAKE_READ_ENABLED', 'false')
    monkeypatch.setenv('OBJECT_LAKE_INLINE_MAX_BYTES', '17')
    assert object_lake.bucket() == 'dev-lake' and object_lake.kms_key() == 'dev-key'
    assert object_lake.release() == 'v2' and not object_lake.read_enabled()
    assert object_lake.inline_max_bytes() == 17
    monkeypatch.setenv('OBJECT_LAKE_INLINE_MAX_BYTES', '-1')
    assert object_lake.inline_max_bytes() == 4096


@pytest.mark.parametrize('stage', ['', 'prod', 'staging', 'unknown'])
@pytest.mark.parametrize('enabled,percent', [('true', '0'), ('false', '1'), ('true', '100')])
def test_deployed_write_settings_blocked_until_c4(monkeypatch, stage, enabled, percent):
    monkeypatch.setenv('OMI_ENV_STAGE', stage)
    monkeypatch.setenv('BUCKET_OBJECT_LAKE', 'bound-lake')
    monkeypatch.setenv('OBJECT_LAKE_KMS_KEY', 'projects/p/locations/l/keyRings/r/cryptoKeys/k')
    monkeypatch.setenv('OBJECT_LAKE_WRITE_ENABLED', enabled)
    monkeypatch.setenv('OBJECT_LAKE_WRITE_PERCENT', percent)
    errors = object_lake.validate_write_settings(stage, enabled, percent)
    assert errors and all('C4 wipe-coverage' in error for error in errors)
    # Runtime admission refuses too, so drifted settings that skip deploy validation cannot write.
    assert not object_lake.write_admitted('owner')


def test_dev_writes_admitted_with_real_bindings(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('BUCKET_OBJECT_LAKE', 'bound-lake')
    monkeypatch.setenv('OBJECT_LAKE_KMS_KEY', 'projects/p/locations/l/keyRings/r/cryptoKeys/k')
    monkeypatch.setenv('OBJECT_LAKE_WRITE_ENABLED', 'true')
    monkeypatch.setenv('OBJECT_LAKE_WRITE_PERCENT', '100')
    assert object_lake.validate_write_settings('dev', 'true', '100') == []
    assert object_lake.write_admitted('owner')
    assert not object_lake.fake_kms_allowed()
    for name in ('BUCKET_OBJECT_LAKE', 'OBJECT_LAKE_KMS_KEY', 'OBJECT_LAKE_RELEASE'):
        with monkeypatch.context() as context:
            context.setenv(name, '')
            assert not object_lake.write_admitted('owner')


@pytest.mark.parametrize('stage', ['local', 'offline', ' LOCAL '])
def test_local_write_settings_remain_available(monkeypatch, stage):
    monkeypatch.setenv('OMI_ENV_STAGE', stage)
    monkeypatch.setenv('BUCKET_OBJECT_LAKE', 'local-lake')
    monkeypatch.setenv('OBJECT_LAKE_WRITE_ENABLED', 'true')
    monkeypatch.setenv('OBJECT_LAKE_WRITE_PERCENT', '100')
    assert object_lake.validate_write_settings(stage, 'true', '100') == []
    assert object_lake.write_admitted('owner')
