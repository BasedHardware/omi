"""Pin the forward-only policy and reject unsafe lifecycle/deploy mutations."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from scripts import validate_object_lake_bucket_contract as validator
from scripts.cross_service_checks import staging as staging_check

BACKEND = Path(__file__).resolve().parents[2]
ROOT = BACKEND.parent
CONTRACT = BACKEND / 'deploy/storage-lifecycle/lake-forward.json'


def contract():
    return json.loads(CONTRACT.read_text())


def runtime():
    return yaml.load((BACKEND / 'deploy/runtime_env.yaml').read_text(), Loader=yaml.CSafeLoader)


def test_policy_pinned_and_retention_registry_matches():
    data = contract()
    assert validator.validate_contract_document(data) == []
    assert data['lifecycle']['rule'] == [
        {
            'action': {'type': 'SetStorageClass', 'storageClass': 'NEARLINE'},
            'condition': {'age': 90, 'matchesPrefix': ['v1/spaces/'], 'matchesStorageClass': ['STANDARD']},
        }
    ]
    registry = json.loads((CONTRACT.parent / 'retention_contract.json').read_text())
    assert registry['holds']['lake_space_content']['days'] is None
    lake = registry['buckets']['object-lake (BUCKET_OBJECT_LAKE, not provisioned)']
    assert lake['provisioned'] is False
    assert lake['env'] == 'BUCKET_OBJECT_LAKE'
    assert lake['protected_prefixes'] == ['v1/spaces/']
    assert lake['holds'] == ['lake_space_content']
    assert lake['ceiling'] == {'soft_delete_seconds_max': 0, 'versioning': False, 'source': ['lake_forward']}
    assert 'data-access audit logs required' in registry['ceiling_sources']['lake_forward']


@pytest.mark.parametrize(
    'path,value',
    [
        (('lifecycle', 'rule', 0, 'action'), {'type': 'Delete'}),
        (('lifecycle', 'rule', 0, 'action', 'storageClass'), 'COLDLINE'),
        (('lifecycle', 'rule', 0, 'action', 'storageClass'), 'ARCHIVE'),
        (('lifecycle', 'rule', 0, 'condition', 'matchesPrefix'), []),
        (('lifecycle', 'rule', 0, 'condition', 'matchesPrefix'), ['v1/']),
        (('lifecycle', 'rule', 0, 'condition', 'matchesPrefix'), ['v1/spaces/', 'legacy/']),
        (('lifecycle', 'rule', 0, 'condition', 'age'), 1),
        (('versioning', 'enabled'), True),
        (('softDeletePolicy', 'retentionDurationSeconds'), '604800'),
        (('dataAccessAuditLogs', 'required'), False),
        (('dataClassTiers', 'transcript', 'allowed'), ['STANDARD', 'ARCHIVE']),
        (('dataClassTiers', 'transcript', 'forbidden'), []),
        (('newBucketOnly',), False),
        (('location',), 'US'),
        (('uniformBucketLevelAccess',), False),
        (('publicAccessPrevention',), 'inherited'),
        (('lifecycle', 'rule'), None),
    ],
)
def test_validator_rejects_each_policy_violation(path, value):
    data = contract()
    parent = data
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = value
    assert validator.validate_contract_document(data)


def test_validator_requires_audit_declaration():
    data = contract()
    del data['dataAccessAuditLogs']
    assert validator.validate_contract_document(data)


def test_runtime_bindings_are_inert_and_helm_matches():
    document = runtime()
    assert validator.validate_runtime_binding(document, contract()) == []
    for env_name in ('dev', 'prod'):
        env = document['environments'][env_name]
        for plane, service in validator.EXPECTED_SERVICES:
            services = env[plane]['services'] if plane == 'cloud_run' else env[plane]
            bindings = services[service]['env']
            values = {
                name: bindings[name]['value']
                for name in (
                    'BUCKET_OBJECT_LAKE',
                    'OBJECT_LAKE_KMS_KEY',
                    'OBJECT_LAKE_WRITE_ENABLED',
                    'OBJECT_LAKE_WRITE_PERCENT',
                    'OBJECT_LAKE_READ_ENABLED',
                    'OBJECT_LAKE_INLINE_MAX_BYTES',
                )
            }
            assert values['OBJECT_LAKE_WRITE_ENABLED'] == 'false' and values['OBJECT_LAKE_WRITE_PERCENT'] == '0'
            assert values['OBJECT_LAKE_READ_ENABLED'] == 'true' and values['OBJECT_LAKE_INLINE_MAX_BYTES'] == '4096'
            if env_name == 'prod':
                assert values['BUCKET_OBJECT_LAKE'] == values['OBJECT_LAKE_KMS_KEY'] == ''
            if plane == 'gke':
                chart_name = 'omi_pusher' if service == 'pusher' else 'omi_backend_listen'
                chart = yaml.safe_load((BACKEND / f'charts/{service}/{env_name}_{chart_name}_values.yaml').read_text())
                # Helm values keep env bindings in the chart's env list.
                env_list = chart['env']
                helm_values = {row['name']: row.get('value') for row in env_list}
                assert {k: helm_values[k] for k in values} == values


@pytest.mark.parametrize('plane,service', validator.EXPECTED_SERVICES)
def test_missing_service_binding_is_rejected(plane, service):
    document = runtime()
    env = document['environments']['prod'][plane]
    if plane == 'cloud_run':
        env = env['services']
    del env[service]['env']['BUCKET_OBJECT_LAKE']
    assert validator.validate_runtime_binding(document, contract())


@pytest.mark.parametrize('enabled', ['true', 'TRUE', True, 'on', '1', 'yes', ' TRUE ', ' YES '])
def test_enabled_write_requires_real_bindings(enabled):
    document = runtime()
    bindings = document['environments']['prod']['gke']['pusher']['env']
    bindings['OBJECT_LAKE_WRITE_ENABLED']['value'] = enabled
    bindings['OBJECT_LAKE_WRITE_PERCENT']['value'] = '1'
    errors = validator.validate_runtime_binding(document, contract())
    assert any('OBJECT_LAKE_WRITE_ENABLED' in error and 'C4 wipe-coverage' in error for error in errors)
    assert any('OBJECT_LAKE_WRITE_PERCENT' in error and 'C4 wipe-coverage' in error for error in errors)
    for name in ('BUCKET_OBJECT_LAKE', 'OBJECT_LAKE_KMS_KEY'):
        assert any(f'enabled writes require a real {name}' in error for error in errors)


@pytest.mark.parametrize(
    'percent,needs_bindings', [('0', False), ('0.0', False), (' 0 ', False), ('0.01', True), ('bad', True)]
)
def test_enabled_write_binding_check_parses_percent_numerically(percent, needs_bindings):
    document = runtime()
    bindings = document['environments']['dev']['gke']['pusher']['env']
    bindings['OBJECT_LAKE_WRITE_ENABLED']['value'] = 'true'
    bindings['OBJECT_LAKE_WRITE_PERCENT']['value'] = percent
    for name in ('BUCKET_OBJECT_LAKE', 'OBJECT_LAKE_KMS_KEY'):
        bindings[name]['value'] = ''
    errors = validator.validate_write_admission('dev', document['environments']['dev'])
    missing = [error for error in errors if 'enabled writes require a real' in error]
    assert bool(missing) is needs_bindings


@pytest.mark.parametrize('stage', ['dev', 'prod'])
@pytest.mark.parametrize('plane,service', validator.EXPECTED_SERVICES)
@pytest.mark.parametrize('enabled,percent', [('true', '0'), ('false', '0.01'), ('true', '100')])
def test_provisioned_deploy_bindings_allow_dev_but_require_c4_for_prod(stage, plane, service, enabled, percent):
    document = runtime()
    env = document['environments'][stage][plane]
    bindings = (env['services'] if plane == 'cloud_run' else env)[service]['env']
    bindings['BUCKET_OBJECT_LAKE']['value'] = 'bound-lake'
    bindings['OBJECT_LAKE_KMS_KEY']['value'] = 'projects/p/locations/l/keyRings/r/cryptoKeys/k'
    bindings['OBJECT_LAKE_WRITE_ENABLED']['value'] = enabled
    bindings['OBJECT_LAKE_WRITE_PERCENT']['value'] = percent
    errors = validator.validate_runtime_binding(document, contract())
    if stage == 'dev':
        assert errors == []
    else:
        assert any('C4 wipe-coverage' in error for error in errors)


def test_validator_cli_is_offline_by_default_and_rejects_mutations(tmp_path):
    command = [
        sys.executable,
        str(BACKEND / 'scripts/validate_object_lake_bucket_contract.py'),
        '--runtime-env',
        str(BACKEND / 'deploy/runtime_env.yaml'),
        '--contract',
        str(CONTRACT),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    bad = deepcopy(contract())
    bad['versioning']['enabled'] = True
    mutated = tmp_path / 'unsafe.json'
    mutated.write_text(json.dumps(bad))
    command[-1] = str(mutated)
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert result.returncode == 1 and 'versioning' in result.stdout


def test_staging_keeps_lake_bindings_on_the_same_services_as_prod():
    composer = staging_check._load_composer(ROOT)
    staging = composer.compose_staging(inputs={'STAGING_REDIS_HOST': '10.0.0.7'})
    names = {
        'BUCKET_OBJECT_LAKE',
        'OBJECT_LAKE_KMS_KEY',
        'OBJECT_LAKE_WRITE_ENABLED',
        'OBJECT_LAKE_WRITE_PERCENT',
        'OBJECT_LAKE_READ_ENABLED',
        'OBJECT_LAKE_INLINE_MAX_BYTES',
    }
    for service, config in staging['cloud_run']['services'].items():
        bindings = config['env']
        if service in ('backend', 'backend-sync'):
            assert names <= bindings.keys()
            assert bindings['BUCKET_OBJECT_LAKE']['value'] == ''
            assert bindings['OBJECT_LAKE_KMS_KEY']['value'] == ''
            assert bindings['OBJECT_LAKE_WRITE_ENABLED']['value'] == 'false'
            assert bindings['OBJECT_LAKE_WRITE_PERCENT']['value'] == '0'
        else:
            assert names.isdisjoint(bindings)
