#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import yaml


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

    for error in errors:
        print(f'ERROR: {error}')
    return 1 if errors else 0


def _load_yaml(path: Path) -> dict | None:
    try:
        with path.open('r', encoding='utf-8') as handle:
            loaded = yaml.safe_load(handle)
    except OSError as exc:
        print(f'ERROR: could not read {path}: {exc}')
        return None
    except yaml.YAMLError as exc:
        print(f'ERROR: invalid YAML in {path}: {exc}')
        return None
    return loaded if isinstance(loaded, dict) else {}


def _env_map(values: dict) -> dict[str, dict]:
    env = values.get('env', [])
    if not isinstance(env, list):
        return {}
    result: dict[str, dict] = {}
    for item in env:
        if isinstance(item, dict) and isinstance(item.get('name'), str):
            result[item['name']] = item
    return result


def _has_value(entry: dict) -> bool:
    """Check whether an env var has an actual value or a valid secret reference."""
    if entry.get('value') not in (None, ''):
        return True
    value_from = entry.get('valueFrom')
    if isinstance(value_from, dict):
        secret_ref = value_from.get('secretKeyRef')
        if isinstance(secret_ref, dict) and secret_ref.get('name') and secret_ref.get('key'):
            return True
        config_ref = value_from.get('configMapKeyRef')
        if isinstance(config_ref, dict) and config_ref.get('name') and config_ref.get('key'):
            return True
    return False


def _require(needle: str, env_map: dict[str, dict], errors: list[str], label: str) -> None:
    entry = env_map.get(needle)
    if entry is None:
        errors.append(f'{label} has no {needle} env')
    elif not _has_value(entry):
        errors.append(f'{label} has {needle} env but no value or valid secret reference')


if __name__ == '__main__':
    raise SystemExit(main())
