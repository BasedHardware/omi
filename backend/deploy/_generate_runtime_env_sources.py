#!/usr/bin/env python3
"""One-shot generator: split monolithic runtime_env.yaml into base + overlays.

Run from repo root:
  python3 backend/deploy/_generate_runtime_env_sources.py
"""

from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
MONOLITH = ROOT / 'backend/deploy/runtime_env.yaml'
OUT_DIR = ROOT / 'backend/deploy/runtime_env'

ConfigDict = dict[str, Any]

# Keys written to the GKE backend ConfigMap (non-secret runtime config).
GKE_CONFIG_MAP_KEYS_BASE = [
    'CONVERSATION_SUMMARIZED_APP_IDS',
    'GOOGLE_CLIENT_ID',
    'MCP_AUTHORIZATION_SERVER_URL',
    'MCP_OAUTH_CHATGPT_CLIENT_ID',
    'MCP_OAUTH_CHATGPT_REDIRECT_URIS',
    'MCP_OAUTH_PUBLIC_CLIENT_ID',
    'MCP_OAUTH_PUBLIC_REDIRECT_URIS',
    'MCP_RESOURCE_URL',
    'RAPID_API_HOST',
    'REDIS_DB_HOST',
    'STT_PRERECORDED_MODEL',
    'STT_SERVICE_MODELS',
    'TYPESENSE_HOST',
    'TWILIO_ACCOUNT_SID',
    'TWILIO_API_KEY_SID',
    'TWILIO_TWIML_APP_SID',
    'X_OAUTH_CLIENT_ID',
    'X_OAUTH_REDIRECT_URI',
]
GKE_CONFIG_MAP_KEYS_PROD_ONLY = [
    'ACCOUNT_DELETION_HANDLER_URL',
    'MCP_OAUTH_CLAUDE_CLIENT_ID',
    'MCP_OAUTH_CLAUDE_CLIENT_NAME',
    'MCP_OAUTH_CLAUDE_REDIRECT_URIS',
    'SYNC_TASKS_HANDLER_URL',
    'SYNC_TASKS_INVOKER_SA',
]

STT_LITERALS = {
    'STT_PRERECORDED_MODEL': 'parakeet,modulate-velma-2',
    'STT_SERVICE_MODELS': 'modulate-velma-2,parakeet',
}


def _load_yaml(path: Path) -> ConfigDict:
    with path.open('r', encoding='utf-8') as handle:
        loaded = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f'{path} must contain a YAML mapping')
    return loaded


def _normalize(obj: object, env: str) -> object:
    if isinstance(obj, str):
        text = obj
        text = text.replace(f'{env}-omi-backend', '{env}-omi-backend')
        text = text.replace(f'{env}_omi', '{env}_omi')
        if env == 'dev':
            text = text.replace('based-hardware-dev', '{compute_project}')
            text = text.replace('based-hardware', '{data_plane_project}')
        else:
            text = text.replace('based-hardware', '{compute_project}')
        text = re.sub(r'\bdev\b', '{env}', text)
        text = re.sub(r'\bprod\b', '{env}', text)
        return text
    if isinstance(obj, dict):
        return {key: _normalize(value, env) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_normalize(item, env) for item in obj]
    return obj


def _extract_common(first: object, second: object) -> object | None:
    if isinstance(first, dict) and isinstance(second, dict):
        common: ConfigDict = {}
        for key in first:
            if key not in second:
                continue
            child = _extract_common(first[key], second[key])
            if child is not None:
                common[key] = child
        return common if common else None
    if first == second:
        return deepcopy(first)
    return None


def _deep_merge(base: object, overlay: object) -> object:
    if isinstance(base, dict) and isinstance(overlay, dict):
        merged = deepcopy(base)
        for key, value in overlay.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key] = _deep_merge(merged[key], value)
            else:
                merged[key] = deepcopy(value)
        return merged
    return deepcopy(overlay)


def _subtract_common(common: object, full: object) -> object | None:
    if common == full:
        return None
    if isinstance(common, dict) and isinstance(full, dict):
        delta: ConfigDict = {}
        for key, value in full.items():
            if key not in common:
                delta[key] = deepcopy(value)
            else:
                child = _subtract_common(common[key], value)
                if child is not None:
                    delta[key] = child
        return delta if delta else None
    return deepcopy(full)


def _substitute_placeholders(obj: object, *, env: str, compute_project: str, data_plane_project: str) -> object:
    if isinstance(obj, str):
        return (
            obj.replace('{env}', env)
            .replace('{compute_project}', compute_project)
            .replace('{data_plane_project}', data_plane_project)
        )
    if isinstance(obj, dict):
        return {
            key: _substitute_placeholders(
                value,
                env=env,
                compute_project=compute_project,
                data_plane_project=data_plane_project,
            )
            for key, value in obj.items()
        }
    if isinstance(obj, list):
        return [
            _substitute_placeholders(
                item,
                env=env,
                compute_project=compute_project,
                data_plane_project=data_plane_project,
            )
            for item in obj
        ]
    return obj


def _build_config_map_section(env: str) -> ConfigDict:
    keys = list(GKE_CONFIG_MAP_KEYS_BASE)
    if env == 'prod':
        keys.extend(GKE_CONFIG_MAP_KEYS_PROD_ONLY)
    entries: ConfigDict = {}
    for key in keys:
        if key in STT_LITERALS:
            entries[key] = {'source': 'literal', 'value': STT_LITERALS[key]}
        else:
            entries[key] = {'source': 'environment'}
    return {
        'name': f'{env}-omi-backend-config',
        'entries': entries,
    }


def _project_fields(env: str, env_config: ConfigDict) -> ConfigDict:
    compute = str(env_config['gcp_project'])
    data_plane = str(env_config.get('runtime_gcp_project', compute))
    return {
        'compute_project': compute,
        'data_plane_project': data_plane,
    }


def _inject_config_map(env_config: ConfigDict, env: str) -> ConfigDict:
    result = deepcopy(env_config)
    gke = result.setdefault('gke', {})
    if not isinstance(gke, dict):
        return result
    gke['config_map'] = _build_config_map_section(env)
    return result


def _strip_legacy_project_keys(env_config: ConfigDict) -> ConfigDict:
    result = deepcopy(env_config)
    result.pop('gcp_project', None)
    result.pop('runtime_gcp_project', None)
    return result


def main() -> int:
    monolith = _load_yaml(MONOLITH)
    dev = monolith['environments']['dev']
    prod = monolith['environments']['prod']

    norm_dev = _normalize(dev, 'dev')
    norm_prod = _normalize(prod, 'prod')
    shared = _extract_common(norm_dev, norm_prod) or {}

    dev_substituted = _substitute_placeholders(
        shared,
        env='dev',
        compute_project=str(dev['gcp_project']),
        data_plane_project=str(dev.get('runtime_gcp_project', dev['gcp_project'])),
    )
    prod_substituted = _substitute_placeholders(
        shared,
        env='prod',
        compute_project=str(prod['gcp_project']),
        data_plane_project=str(prod.get('runtime_gcp_project', prod['gcp_project'])),
    )

    dev_overlay_body = _subtract_common(dev_substituted, _strip_legacy_project_keys(dev)) or {}
    prod_overlay_body = _subtract_common(prod_substituted, _strip_legacy_project_keys(prod)) or {}

    # Ensure config_map sections live in overlays (env-specific names).
    dev_overlay_body = _deep_merge(dev_overlay_body, {'gke': {'config_map': _build_config_map_section('dev')}})
    prod_overlay_body = _deep_merge(prod_overlay_body, {'gke': {'config_map': _build_config_map_section('prod')}})

    base = {
        'schema_version': monolith['schema_version'],
        'environment_shared': shared,
    }
    dev_overlay = {
        'environment': 'dev',
        **_project_fields('dev', dev),
        'overlay': dev_overlay_body,
    }
    prod_overlay = {
        'environment': 'prod',
        **_project_fields('prod', prod),
        'overlay': prod_overlay_body,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, payload in (
        ('_base.yaml', base),
        ('dev.overlay.yaml', dev_overlay),
        ('prod.overlay.yaml', prod_overlay),
    ):
        path = OUT_DIR / name
        with path.open('w', encoding='utf-8') as handle:
            handle.write(
                '# Generated by _generate_runtime_env_sources.py — edit compose inputs, then re-run compose.\n'
            )
            yaml.safe_dump(payload, handle, sort_keys=False, default_flow_style=False, allow_unicode=True)

    print(f'Wrote {OUT_DIR}/_base.yaml, dev.overlay.yaml, prod.overlay.yaml')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
