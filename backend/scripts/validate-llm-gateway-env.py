#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, cast

import yaml

ConfigDict = dict[str, Any]
EnvMap = dict[str, ConfigDict]


def _as_config_dict(value: object) -> ConfigDict | None:
    return cast(ConfigDict, value) if isinstance(value, dict) else None


def _as_config_list(value: object) -> list[Any] | None:
    return cast(list[Any], value) if isinstance(value, list) else None


def main() -> int:
    if len(sys.argv) != 3:
        print('usage: validate-llm-gateway-env.py <backend-listen-values.yaml> <llm-gateway-values.yaml>')
        return 2

    backend_values = _load_yaml(Path(sys.argv[1]))
    gateway_values = _load_yaml(Path(sys.argv[2]))
    if backend_values is None or gateway_values is None:
        return 1
    errors: list[str] = []

    backend_env = _env_map(backend_values)
    gateway_env = _env_map(gateway_values)

    if 'OMI_LLM_GATEWAY_URL' in backend_env:
        _require('OMI_LLM_GATEWAY_SERVICE_TOKEN', backend_env, errors, 'backend')

    token_entry = gateway_env.get('OMI_LLM_GATEWAY_SERVICE_TOKEN') or gateway_env.get('LLM_GATEWAY_SERVICE_TOKEN')
    if token_entry is None:
        errors.append('gateway has no service token env')
    elif not _has_value(token_entry):
        errors.append('gateway service token env has no value or valid secret reference')

    _require('OPENAI_API_KEY', gateway_env, errors, 'gateway')
    _require('ANTHROPIC_API_KEY', gateway_env, errors, 'gateway')

    for error in errors:
        print(f'ERROR: {error}')
    return 1 if errors else 0


def _load_yaml(path: Path) -> ConfigDict | None:
    try:
        with path.open('r', encoding='utf-8') as handle:
            loaded = yaml.safe_load(handle)
    except OSError as exc:
        print(f'ERROR: could not read {path}: {exc}')
        return None
    except yaml.YAMLError as exc:
        print(f'ERROR: invalid YAML in {path}: {exc}')
        return None
    return cast(ConfigDict, loaded) if isinstance(loaded, dict) else {}


def _env_map(values: ConfigDict) -> EnvMap:
    env = _as_config_list(values.get('env'))
    if env is None:
        return {}
    result: EnvMap = {}
    for item in env:
        item_dict = _as_config_dict(item)
        if item_dict is not None and isinstance(item_dict.get('name'), str):
            result[item_dict['name']] = item_dict
    return result


def _has_value(entry: ConfigDict) -> bool:
    """Check whether an env var has an actual value or a valid secret reference."""
    if entry.get('value') not in (None, ''):
        return True
    value_from = _as_config_dict(entry.get('valueFrom'))
    if value_from is not None:
        secret_ref = _as_config_dict(value_from.get('secretKeyRef'))
        if secret_ref is not None and secret_ref.get('name') and secret_ref.get('key'):
            return True
        config_ref = _as_config_dict(value_from.get('configMapKeyRef'))
        if config_ref is not None and config_ref.get('name') and config_ref.get('key'):
            return True
    return False


def _require(needle: str, env_map: EnvMap, errors: list[str], label: str) -> None:
    entry = env_map.get(needle)
    if entry is None:
        errors.append(f'{label} has no {needle} env')
    elif not _has_value(entry):
        errors.append(f'{label} has {needle} env but no value or valid secret reference')


if __name__ == '__main__':
    raise SystemExit(main())
