#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import binascii
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, cast

import yaml

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
from scripts.private_cohort_secrets import (
    PRIVATE_COHORT_ENV_NAMES,
    pinned_secret_version,
    valid_private_cohort_payload,
)  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description='Verify expected Kubernetes Secret keys without printing values.')
    parser.add_argument('values_file', type=Path)
    parser.add_argument('--secret-json', type=Path, help='Kubernetes Secret JSON. Defaults to stdin.')
    args = parser.parse_args()

    expected = expected_keys(args.values_file)
    secret = load_json(args.secret_json)
    data_raw = secret.get('data')
    data = cast(Dict[str, Any], data_raw) if isinstance(data_raw, dict) else {}
    present = set(data.keys())
    missing = sorted(expected - present)
    if missing:
        print(f'ERROR: Kubernetes Secret is missing expected key(s): {", ".join(missing)}', file=sys.stderr)
        return 1
    invalid = []
    for name in sorted(expected & PRIVATE_COHORT_ENV_NAMES):
        try:
            payload = base64.b64decode(data[name], validate=True).decode('utf-8')
        except (ValueError, TypeError, UnicodeError, binascii.Error):
            invalid.append(name)
            continue
        if not valid_private_cohort_payload(name, payload):
            invalid.append(name)
    if invalid:
        print(
            f'ERROR: Kubernetes Secret has empty or invalid private cohort key(s): {", ".join(invalid)}',
            file=sys.stderr,
        )
        return 1
    print(f'Kubernetes Secret key presence OK: {len(expected)} expected key(s) present')
    return 0


def expected_keys(values_file: Path) -> set[str]:
    with values_file.open('r', encoding='utf-8') as handle:
        loaded: object = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f'{values_file} must contain a YAML object')
    values: Dict[str, Any] = cast(Dict[str, Any], loaded)
    external_secret_raw = values.get('externalSecret')
    if not isinstance(external_secret_raw, dict):
        raise ValueError(f'{values_file} does not define externalSecret.secretKeys')
    external_secret: Dict[str, Any] = cast(Dict[str, Any], external_secret_raw)
    raw_keys = external_secret.get('secretKeys', [])
    if not isinstance(raw_keys, list):
        raise ValueError(f'{values_file} does not define externalSecret.secretKeys')
    keys: List[Any] = cast(List[Any], raw_keys)
    expected: set[str] = set()
    for entry in keys:
        if isinstance(entry, dict):
            entry_dict: Dict[str, Any] = cast(Dict[str, Any], entry)
            secret_key = entry_dict.get('secretKey')
            if isinstance(secret_key, str) and secret_key:
                if secret_key in PRIVATE_COHORT_ENV_NAMES and not pinned_secret_version(
                    str(entry_dict.get('version', ''))
                ):
                    raise ValueError('Private cohort ExternalSecret requires an immutable numeric version')
                expected.add(secret_key)
    if not expected:
        raise ValueError(f'{values_file} does not define externalSecret.secretKeys')
    return expected


def load_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        loaded = json.load(sys.stdin)
    else:
        with path.open('r', encoding='utf-8') as handle:
            loaded = json.load(handle)
    if not isinstance(loaded, dict):
        raise ValueError('secret JSON must be an object')
    return cast(dict[str, Any], loaded)


if __name__ == '__main__':
    raise SystemExit(main())
