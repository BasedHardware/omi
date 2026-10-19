"""Registration contract for the sync VAD cache TTL setting."""

import json
from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
EXPECTED_SERVICES = {'backend', 'backend-sync', 'backend-sync-backfill'}
EXPECTED_TTLS = {
    'dev': {'backend': '86400', 'backend-sync': '86400', 'backend-sync-backfill': '86400'},
    'prod': {'backend': '86400', 'backend-sync': '7200', 'backend-sync-backfill': '7200'},
}


def _load_yaml(path: Path) -> dict:
    loader = getattr(yaml, 'CSafeLoader', yaml.SafeLoader)
    return yaml.load(path.read_text(), Loader=loader)


def test_sync_vad_services_keep_the_configured_ttl_in_dev_and_prod():
    manifest = _load_yaml(REPOSITORY_ROOT / 'backend/deploy/runtime_env.yaml')

    for environment in ('dev', 'prod'):
        services = manifest['environments'][environment]['cloud_run']['services']
        declared = {name for name, service in services.items() if 'VAD_CACHE_TTL_SECONDS' in service.get('env', {})}
        assert declared == EXPECTED_SERVICES
        for service_name in EXPECTED_SERVICES:
            assert (
                services[service_name]['env']['VAD_CACHE_TTL_SECONDS']['value']
                == EXPECTED_TTLS[environment][service_name]
            )


def test_sync_vad_cache_ttl_is_registered_as_nonsecret_config_and_documented():
    classification = json.loads((REPOSITORY_ROOT / 'config/deployment-setting-classification.json').read_text())
    assert 'VAD_CACHE_TTL_SECONDS' in classification['kinds']['config']
    assert 'VAD_CACHE_TTL_SECONDS' not in classification['kinds']['secret']

    feature_flags = _load_yaml(REPOSITORY_ROOT / 'config/feature-flags.yaml')
    rows = [row for row in feature_flags['flags'] if row['key'] == 'VAD_CACHE_TTL_SECONDS']
    assert len(rows) == 1
    assert rows[0]['lifecycle'] == 'config_switch'

    env_template = (REPOSITORY_ROOT / 'backend/.env.template').read_text()
    assert 'VAD_CACHE_TTL_SECONDS=86400' in env_template
    registry = (REPOSITORY_ROOT / 'backend/docs/feature-flag-registry.md').read_text()
    assert '| `VAD_CACHE_TTL_SECONDS` |' in registry
    pipeline_docs = (REPOSITORY_ROOT / 'backend/docs/listen_pusher_pipeline.mdx').read_text()
    assert '`VAD_CACHE_TTL_SECONDS` is read when each cache entry is written' in pipeline_docs
