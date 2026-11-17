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


def test_conversations_v3_stage_is_shared_across_creator_finalizer_readers():
    manifest = COMPOSER['compose_manifest']()
    for env in manifest['environments'].values():
        for service in env['cloud_run']['services'].values():
            assert service['env']['CONVERSATIONS_V3_STAGE']['value'] == 'beta'
        for name in ('backend-listen', 'pusher'):
            assert env['gke'][name]['env']['CONVERSATIONS_V3_STAGE']['config_map']['key'] == 'CONVERSATIONS_V3_STAGE'
        assert env['gke']['config_map']['entries']['CONVERSATIONS_V3_STAGE']['value'] == 'beta'


def test_one_stage_source_moves_all_runtime_roles(tmp_path):
    base = ROOT / 'backend/deploy/runtime_env/_base.yaml'
    expanded = tmp_path / 'base.yaml'
    expanded.write_text(base.read_text().replace('conversations_v3_stage: beta', 'conversations_v3_stage: all'))
    manifest = COMPOSER['compose_manifest'](base_path=expanded)
    for env in manifest['environments'].values():
        assert all(s['env']['CONVERSATIONS_V3_STAGE']['value'] == 'all' for s in env['cloud_run']['services'].values())
        assert env['gke']['config_map']['entries']['CONVERSATIONS_V3_STAGE']['value'] == 'all'


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
