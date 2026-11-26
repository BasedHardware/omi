"""Source overlays must compose exactly to the checked-in deploy manifest."""

import runpy
import json
from pathlib import Path

import yaml
import pytest

ROOT = Path(__file__).resolve().parents[3]
SAFE_LOADER = getattr(yaml, 'CSafeLoader', yaml.SafeLoader)
COMPOSER = runpy.run_path(str(ROOT / 'backend/deploy/compose_runtime_env.py'))


def test_checked_in_manifest_matches_sources():
    manifest = yaml.load((ROOT / 'backend/deploy/runtime_env.yaml').read_text(), Loader=SAFE_LOADER)
    assert COMPOSER['compose_manifest']() == manifest


def test_derived_service_forbidden_env_removes_inherited_values_and_keeps_inherited_forbidden():
    config = {
        'cloud_run': {
            'services': {
                'backend-integration': {
                    'env': {
                        'INTEGRATION_ONLY': {'value': 'true'},
                        'SHARED': {'value': 'present'},
                    },
                    'forbidden_env': ['SOURCE_FORBIDDEN'],
                },
                'backend-projection-pump': {
                    'derive_from': 'backend-integration',
                    'forbidden_env': ['INTEGRATION_ONLY'],
                },
            }
        }
    }

    COMPOSER['_resolve_derived_services'](config)

    pump = config['cloud_run']['services']['backend-projection-pump']
    assert pump['env'] == {'SHARED': {'value': 'present'}}
    assert pump['forbidden_env'] == ['SOURCE_FORBIDDEN', 'INTEGRATION_ONLY']


def test_docket_retirements_have_no_source_bindings():
    registry = yaml.load((ROOT / 'config/feature-flags.yaml').read_text(), Loader=SAFE_LOADER)
    retired = {row['key'] for row in registry['retired'] if 'David flag docket 2026-11-09' in row.get('reason', '')}
    assert retired

    def mapping_keys(value):
        if isinstance(value, dict):
            yield from value
            for child in value.values():
                yield from mapping_keys(child)
        elif isinstance(value, list):
            for child in value:
                yield from mapping_keys(child)

    for name in ('_base.yaml', 'dev.overlay.yaml', 'prod.overlay.yaml'):
        source = yaml.load((ROOT / 'backend/deploy/runtime_env' / name).read_text(), Loader=SAFE_LOADER)
        assert retired.isdisjoint(mapping_keys(source)), name


@pytest.mark.parametrize(
    'mapping',
    [
        "AUDIO_ARCHIVE_STOP_PCM_PERCENT:\n  value: '0'\n  value: '0'\n",
        "AUDIO_ARCHIVE_STOP_PCM_PERCENT:\n  category: rollout\n  category: rollout\n",
        "AUDIO_ARCHIVE_STOP_PCM_PERCENT: {value: '0', value: '1'}\n",
    ],
)
def test_runtime_env_composer_rejects_duplicate_mapping_keys(tmp_path, mapping):
    composer = runpy.run_path(str(ROOT / 'backend/deploy/compose_runtime_env.py'))
    source = tmp_path / 'duplicate.yaml'
    source.write_text(mapping)
    with pytest.raises(ValueError, match='duplicate YAML mapping key'):
        composer['_load_yaml'](source)


@pytest.mark.parametrize('prod_enabled', [None, False, True])
def test_go_queue_erase_setting_is_shared_by_deletion_runtimes(tmp_path, prod_enabled):
    runtime_env = ROOT / 'backend/deploy/runtime_env'
    for name in ('dev', 'prod', 'staging'):
        overlay = yaml.load((runtime_env / f'{name}.overlay.yaml').read_text(), Loader=SAFE_LOADER)
        if name == 'prod' and prod_enabled is not None:
            overlay['overlay']['go_queue_erase_required'] = prod_enabled
        (tmp_path / f'{name}.overlay.yaml').write_text(yaml.safe_dump(overlay, sort_keys=False))

    environments = COMPOSER['compose_manifest'](runtime_env_dir=tmp_path)['environments']
    environments['staging'] = COMPOSER['compose_staging'](
        runtime_env_dir=tmp_path, inputs={'STAGING_REDIS_HOST': '10.0.0.7'}
    )
    for name, env in environments.items():
        expected = str(prod_enabled).lower() if name == 'prod' and prod_enabled is not None else None
        assert all(
            service['env'].get('GO_QUEUE_ERASE_REQUIRED', {}).get('value') == expected
            for service in env['cloud_run']['services'].values()
        )
        if name != 'staging':
            entry = env['gke']['config_map']['entries'].get('GO_QUEUE_ERASE_REQUIRED', {})
            assert entry.get('value') == expected


def test_go_queue_erase_setting_rejects_service_override():
    env = {'cloud_run': {'services': {'backend': {'env': {'GO_QUEUE_ERASE_REQUIRED': {'value': 'true'}}}}}}
    with pytest.raises(ValueError, match='at environment scope'):
        COMPOSER['_apply_go_queue_erase_setting'](env)


def test_conversations_v3_stage_is_shared_across_creator_finalizer_readers():
    manifest = COMPOSER['compose_manifest']()
    for env in manifest['environments'].values():
        for service in env['cloud_run']['services'].values():
            assert service['env']['CONVERSATIONS_V3_STAGE']['value'] == 'all'
        for job in env['cloud_run'].get('jobs', {}).values():
            if isinstance(job, dict):
                assert job['env']['CONVERSATIONS_V3_STAGE']['value'] == 'all'
        for name in ('backend-listen', 'pusher'):
            assert env['gke'][name]['env']['CONVERSATIONS_V3_STAGE']['config_map']['key'] == 'CONVERSATIONS_V3_STAGE'
        assert env['gke']['config_map']['entries']['CONVERSATIONS_V3_STAGE']['value'] == 'all'


def test_one_stage_source_moves_all_runtime_roles(tmp_path):
    base = ROOT / 'backend/deploy/runtime_env/_base.yaml'
    expanded = tmp_path / 'base.yaml'
    expanded.write_text(base.read_text().replace('conversations_v3_stage: all', 'conversations_v3_stage: beta'))
    manifest = COMPOSER['compose_manifest'](base_path=expanded)
    for env in manifest['environments'].values():
        assert all(s['env']['CONVERSATIONS_V3_STAGE']['value'] == 'beta' for s in env['cloud_run']['services'].values())
        assert all(
            j['env']['CONVERSATIONS_V3_STAGE']['value'] == 'beta'
            for j in env['cloud_run'].get('jobs', {}).values()
            if isinstance(j, dict)
        )
        assert env['gke']['config_map']['entries']['CONVERSATIONS_V3_STAGE']['value'] == 'beta'


@pytest.mark.parametrize('name', ['CONVERSATIONS_V3_STAGE', 'CONVERSATIONS_V3_FIRST_APP_BUILD'])
def test_shared_v3_settings_are_public_runtime_configuration(name):
    policy = json.loads((ROOT / 'config/deployment-setting-classification.json').read_text())
    assert name in policy['kinds']['config']
    assert name not in policy['kinds']['secret']
    manifest = COMPOSER['compose_manifest']()
    for env in manifest['environments'].values():
        for service in env['cloud_run']['services'].values():
            assert name in service['env']
            assert name not in service.get('secrets', {})


def test_prod_v3_kill_switch_reaches_every_writer():
    manifest = COMPOSER['compose_manifest']()
    prod = manifest['environments']['prod']
    values = {service['env']['CONVERSATIONS_V3']['value'] for service in prod['cloud_run']['services'].values()}
    for job in prod['cloud_run'].get('jobs', {}).values():
        if isinstance(job, dict):
            values.add(job['env']['CONVERSATIONS_V3']['value'])
    values.add(prod['gke']['config_map']['entries']['CONVERSATIONS_V3']['value'])
    assert len(values) == 1 and values <= {'on', 'off'}
    assert 'CONVERSATIONS_V3' not in manifest['environments']['dev']['gke']['config_map']['entries']
