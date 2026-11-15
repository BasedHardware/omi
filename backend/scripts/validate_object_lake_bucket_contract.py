#!/usr/bin/env python3
"""Offline object-lake policy and service-binding validation; never calls GCP."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from collections.abc import Mapping
import sys

import yaml

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from config.object_lake import validate_write_settings  # noqa: E402

EXPECTED_SERVICES = (
    ('gke', 'backend-listen'),
    ('gke', 'pusher'),
    ('cloud_run', 'backend'),
    ('cloud_run', 'backend-sync'),
)


def validate_contract_document(contract: Mapping) -> list[str]:
    errors = []
    required = {
        'release': 'v1',
        'newBucketOnly': True,
        'bucket_env_var': 'BUCKET_OBJECT_LAKE',
        'location': 'us-central1',
        'storageClass': 'STANDARD',
        'uniformBucketLevelAccess': True,
        'publicAccessPrevention': 'enforced',
        'versioning': {'enabled': False},
        'softDeletePolicy': {'retentionDurationSeconds': '0'},
        'dataAccessAuditLogs': {'required': True},
    }
    for key, expected in required.items():
        if json.dumps(contract.get(key), sort_keys=True) != json.dumps(expected, sort_keys=True):
            errors.append(f'{key} must be {expected!r}')
    rules = contract.get('lifecycle', {})
    rules = rules.get('rule') if isinstance(rules, Mapping) else None
    if not isinstance(rules, list) or not rules:
        errors.append('lifecycle.rule must contain the release-scoped Nearline policy')
        rules = []
    for rule in rules:
        if not isinstance(rule, Mapping):
            errors.append('lifecycle rule must be a mapping')
            continue
        action, condition = rule.get('action', {}), rule.get('condition', {})
        if action != {'type': 'SetStorageClass', 'storageClass': 'NEARLINE'}:
            errors.append('only SetStorageClass NEARLINE is permitted; no Delete or cold tiers')
        if not isinstance(condition, Mapping) or condition.get('matchesPrefix') != ['v1/spaces/']:
            errors.append('every rule must be scoped to v1/spaces/')
        if (
            not isinstance(condition, Mapping)
            or type(condition.get('age')) is not int
            or condition['age'] < 30
            or condition.get('matchesStorageClass') != ['STANDARD']
        ):
            errors.append('Nearline rules require age >= 30 and STANDARD source class')
    tiers = contract.get('dataClassTiers', {})
    transcript = tiers.get('transcript', {}) if isinstance(tiers, Mapping) else {}
    if not isinstance(transcript, Mapping) or transcript.get('allowed') != ['STANDARD', 'NEARLINE']:
        errors.append('transcript allowed tiers must be STANDARD/NEARLINE')
    if not isinstance(transcript, Mapping) or transcript.get('forbidden') != ['COLDLINE', 'ARCHIVE']:
        errors.append('transcript must forbid COLDLINE/ARCHIVE')
    return errors


def validate_runtime_binding(document: Mapping, contract: Mapping) -> list[str]:
    errors = []
    environments = document.get('environments', {})
    if not isinstance(environments, Mapping) or not {'dev', 'prod'} <= environments.keys():
        return ['runtime manifest must declare dev and prod environments']
    for env_name, env in environments.items():
        errors.extend(validate_write_admission(env_name, env))
        for plane, service in EXPECTED_SERVICES:
            try:
                services = env[plane]['services'] if plane == 'cloud_run' else env[plane]
                bindings = services[service]['env']
            except (KeyError, TypeError):
                errors.append(f'{env_name}/{service} missing lake bindings')
                continue
            for name in (contract.get('bucket_env_var'), 'OBJECT_LAKE_KMS_KEY'):
                if name not in bindings or not isinstance(bindings[name], Mapping):
                    errors.append(f'{env_name}/{service} must declare {name}')
    return errors


def _zero_percent(percent) -> bool:
    """A numerically zero cohort ('0', '0.0', ' 0 ') admits no writes; unparseable values do."""
    try:
        return float(str(percent).strip()) == 0
    except ValueError:
        return False


def validate_write_admission(stage: str, environment: Mapping) -> list[str]:
    """Check every host, including hosts outside the initial lake rollout."""
    hosts = list(environment.get('gke', {}).items())
    cloud_run = environment.get('cloud_run', {})
    hosts.extend(cloud_run.get('services', {}).items())
    hosts.extend(cloud_run.get('jobs', {}).items())
    hosts.extend((name, environment.get(name, {})) for name in ('desktop_backend', 'llm_gateway'))
    errors = []
    for name, host in hosts:
        if not isinstance(host, Mapping):
            continue
        bindings = host.get('env', {})
        enabled = bindings.get('OBJECT_LAKE_WRITE_ENABLED', {}).get('value', 'false')
        percent = bindings.get('OBJECT_LAKE_WRITE_PERCENT', {}).get('value', '0')
        errors.extend(f'{stage}/{name} {error}' for error in validate_write_settings(stage, enabled, percent))
        # Shared with runtime manifest validation: empty bindings are permitted
        # only while writes are off, including hosts outside the initial rollout.
        if str(enabled).strip().lower() in ('true', '1', 'on', 'yes') and not _zero_percent(percent):
            for binding in ('BUCKET_OBJECT_LAKE', 'OBJECT_LAKE_KMS_KEY'):
                if not str(bindings.get(binding, {}).get('value') or '').strip():
                    errors.append(f'{stage}/{name} enabled writes require a real {binding}')
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-only', action='store_true', help='Offline mode (also the default)')
    parser.add_argument('--runtime-env', type=Path)
    parser.add_argument('--contract', type=Path, default=BACKEND / 'deploy/storage-lifecycle/lake-forward.json')
    args = parser.parse_args()
    try:
        contract = json.loads(args.contract.read_text())
        if not isinstance(contract, Mapping):
            raise ValueError('contract must be a JSON object')
        errors = validate_contract_document(contract)
        if args.runtime_env:
            document = yaml.load(args.runtime_env.read_text(), Loader=getattr(yaml, 'CSafeLoader', yaml.SafeLoader))
            if not isinstance(document, Mapping):
                raise ValueError('runtime manifest must be a mapping')
            errors.extend(validate_runtime_binding(document, contract))
    except (OSError, ValueError, yaml.YAMLError) as error:
        errors = [str(error)]
    for error in errors:
        print(f'ERROR: {error}')
    if errors:
        return 1
    print('object-lake bucket contract passed (source only; no resources inspected)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
