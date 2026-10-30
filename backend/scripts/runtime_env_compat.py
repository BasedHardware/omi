"""Deterministic migrations for already-released backend runtime manifests."""

from copy import deepcopy
from typing import Any, cast

ConfigDict = dict[str, Any]
VOICE_STAGING_BUCKET_ENV = 'BUCKET_TEMPORAL_SYNC_LOCAL'
VOICE_STAGING_BUCKETS = {'dev': 'syncing-local-development', 'prod': 'syncing-local'}


def _mapping(value: object) -> ConfigDict:
    return cast(ConfigDict, value) if isinstance(value, dict) else {}


def normalize_runtime_manifest(manifest: ConfigDict) -> ConfigDict:
    """Materialize v1's inherited voice bucket; v2 must declare it explicitly.

    Only a missing v1 binding is migrated. Explicit wrong/blank bindings stay
    visible to admission, and the caller's parsed document remains unchanged.
    Non-manifest YAML (charts/workflows) passes through this shared loader.
    """
    if not isinstance(manifest.get('environments'), dict):
        return manifest
    version = manifest.get('schema_version', 1)
    if type(version) is not int or version not in (1, 2):
        raise ValueError('Unsupported backend runtime manifest schema_version')
    if version == 2:
        return manifest
    normalized = deepcopy(manifest)
    environments = _mapping(normalized.get('environments'))
    for environment, bucket in VOICE_STAGING_BUCKETS.items():
        config = _mapping(environments.get(environment))
        services = _mapping(_mapping(config.get('cloud_run')).get('services'))
        backend = services.get('backend')
        if not isinstance(backend, dict):
            continue
        entries = backend.setdefault('env', {})
        if isinstance(entries, dict):
            entries.setdefault(VOICE_STAGING_BUCKET_ENV, {'value': bucket, 'category': 'storage_retention'})
    return normalized
