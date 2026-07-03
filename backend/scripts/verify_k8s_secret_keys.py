#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import yaml


def main() -> int:
    parser = argparse.ArgumentParser(description='Verify expected Kubernetes Secret keys without printing values.')
    parser.add_argument('values_file', type=Path)
    parser.add_argument('--secret-json', type=Path, help='Kubernetes Secret JSON. Defaults to stdin.')
    args = parser.parse_args()

    expected = expected_keys(args.values_file)
    secret = load_json(args.secret_json)
    present = set((secret.get('data') or {}).keys())
    missing = sorted(expected - present)
    if missing:
        print(f'ERROR: Kubernetes Secret is missing expected key(s): {", ".join(missing)}', file=sys.stderr)
        return 1
    print(f'Kubernetes Secret key presence OK: {len(expected)} expected key(s) present')
    return 0


def expected_keys(values_file: Path) -> set[str]:
    with values_file.open('r', encoding='utf-8') as handle:
        values = yaml.safe_load(handle)
    keys = values.get('externalSecret', {}).get('secretKeys', []) if isinstance(values, dict) else []
    expected = {entry.get('secretKey') for entry in keys if isinstance(entry, dict) and entry.get('secretKey')}
    if not expected:
        raise ValueError(f'{values_file} does not define externalSecret.secretKeys')
    return {str(key) for key in expected}


def load_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        loaded = json.load(sys.stdin)
    else:
        with path.open('r', encoding='utf-8') as handle:
            loaded = json.load(handle)
    if not isinstance(loaded, dict):
        raise ValueError('secret JSON must be an object')
    return loaded


if __name__ == '__main__':
    raise SystemExit(main())
