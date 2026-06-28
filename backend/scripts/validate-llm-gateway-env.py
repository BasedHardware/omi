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
    errors: list[str] = []

    backend_env = _env_map(backend_values)
    gateway_env = _env_map(gateway_values)

    if 'OMI_LLM_GATEWAY_URL' in backend_env and 'OMI_LLM_GATEWAY_SERVICE_TOKEN' not in backend_env:
        errors.append('backend has OMI_LLM_GATEWAY_URL but no OMI_LLM_GATEWAY_SERVICE_TOKEN')
    if 'OMI_LLM_GATEWAY_SERVICE_TOKEN' not in gateway_env and 'LLM_GATEWAY_SERVICE_TOKEN' not in gateway_env:
        errors.append('gateway has no service token env')
    if 'OPENAI_API_KEY' not in gateway_env:
        errors.append('gateway has no OPENAI_API_KEY env')

    for error in errors:
        print(f'ERROR: {error}')
    return 1 if errors else 0


def _load_yaml(path: Path) -> dict:
    with path.open('r', encoding='utf-8') as handle:
        loaded = yaml.safe_load(handle)
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


if __name__ == '__main__':
    raise SystemExit(main())
