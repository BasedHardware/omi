"""Read-only release prerequisite: accepted staging must not age out in GCS.

Reads bucket metadata only, never objects, IAM policies or secret payloads.
Output contains aggregate policy receipts, never bucket/env values or prefixes.
"""

import argparse
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from typing import Any
from urllib.parse import quote

from google.auth.transport import requests
from google.oauth2 import service_account


def read_bucket_metadata(name: str) -> dict[str, Any]:
    # No ADC fallback to an interactive human login. The sourced read-only
    # tier supplies this agent key; the OAuth scope is read-only as well.
    credentials = service_account.Credentials.from_service_account_file(
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'], scopes=['https://www.googleapis.com/auth/devstorage.read_only']
    )
    with requests.AuthorizedSession(credentials) as session:
        response = session.get(
            f'https://storage.googleapis.com/storage/v1/b/{quote(name, safe="")}',
            params={'fields': 'metageneration,lifecycle,defaultEventBasedHold,retentionPolicy'},
            timeout=20,
        )
        if response.status_code != 200:
            raise RuntimeError('bucket metadata unavailable')
        payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError('invalid bucket metadata')
    retention = payload.get('retentionPolicy')
    if retention is None:
        retention = {}
    if not isinstance(retention, dict):
        raise ValueError('invalid retention metadata')
    # Keep raw actions: the storage SDK lifecycle iterator drops unknown
    # actions with a warning, which could otherwise turn uncertainty into PASS.
    return {
        'metageneration': payload.get('metageneration'),
        'lifecycle': payload.get('lifecycle'),
        'default_event_based_hold': payload.get('defaultEventBasedHold'),
        'retention_period': retention.get('retentionPeriod'),
    }


def _metageneration(metadata: dict[str, Any]) -> str | None:
    generation = metadata.get('metageneration')
    if isinstance(generation, bool) or not isinstance(generation, (int, str)):
        return None
    value = str(generation)
    return value if re.fullmatch(r'[1-9][0-9]*', value) else None


def policy_failure(metadata: dict[str, Any]) -> str | None:
    if _metageneration(metadata) is None:
        return 'invalid_metadata'
    if metadata.get('default_event_based_hold') or metadata.get('retention_period') not in (None, 0):
        return 'privacy_blocking_retention'
    lifecycle = metadata.get('lifecycle')
    if lifecycle is None:
        lifecycle = {}
    if not isinstance(lifecycle, dict) or not isinstance(lifecycle.get('rule', []), list):
        return 'invalid_metadata'
    for rule in lifecycle.get('rule', []):
        if not isinstance(rule, dict) or not isinstance(rule.get('action'), dict):
            return 'invalid_metadata'
        action = rule['action'].get('type')
        if action == 'Delete':
            return 'lifecycle_delete'
        if action not in {'SetStorageClass', 'AbortIncompleteMultipartUpload'}:
            return 'unsupported_lifecycle_action'
    return None


def audit(names: Sequence[str], reader: Callable[[str], dict[str, Any]] = read_bucket_metadata) -> dict[str, Any]:
    targets = []
    for index, name in enumerate(names, start=1):
        try:
            metadata = reader(name)
            reason = policy_failure(metadata)
            receipt = {
                'target': index,
                'metageneration': _metageneration(metadata),
                'policy_sha256': hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest(),
                'reason': reason,
            }
        except Exception:
            # Provider errors can contain URLs or identifiers; never echo them.
            receipt = {'target': index, 'reason': 'metadata_unavailable'}
        targets.append(receipt)
    return {
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'status': 'PASS' if targets and all(row['reason'] is None for row in targets) else 'FAIL',
        'targets_checked': len(targets),
        'targets': targets,
    }


def main(argv: Sequence[str] | None = None, *, reader: Callable[[str], dict[str, Any]] = read_bucket_metadata) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bucket', action='append', default=[], help='Audit every staging target; repeat as needed')
    args = parser.parse_args(argv)
    if os.getenv('GCP_AGENT_TIER') not in {'ro-prod', 'ro-dev'}:
        print(json.dumps({'status': 'FAIL', 'reason': 'read_only_agent_tier_required'}))
        return 2
    # Explicit targets supplement, rather than hide, configured regional targets.
    raw = [
        os.getenv('BUCKET_TEMPORAL_SYNC_LOCAL'),
        os.getenv('BUCKET_AUDIO_DERIVED'),
        os.getenv('BUCKET_BATCH_PIPELINE'),
        *args.bucket,
    ]
    names = list(dict.fromkeys(value.removeprefix('gs://').rstrip('/') for value in raw if value))
    if not names or any(not re.fullmatch(r'[a-z0-9][a-z0-9._-]{1,220}[a-z0-9]', name) for name in names):
        print(json.dumps({'status': 'FAIL', 'reason': 'invalid_or_missing_targets'}))
        return 2
    result = audit(names, reader)
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
