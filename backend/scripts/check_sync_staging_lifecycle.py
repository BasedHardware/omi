"""Read-only release prerequisite: accepted staging must not age out in GCS.

Reads bucket metadata only, never objects, IAM policies or secret payloads.
Output contains aggregate policy receipts, never bucket/env values or prefixes.

A bucket named in deploy/storage-lifecycle/retention_contract.json is judged by
its floor there (a Delete may not reach a protected prefix sooner than the
longest hold plus margin; noncurrent-only deletes keep the live object), and its
ceiling findings are reported without changing PASS/FAIL. Any other bucket
keeps the strict rule: any lifecycle Delete fails.
"""

import argparse
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import quote

from google.auth.transport import requests
from google.oauth2 import service_account

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import retention_contract  # noqa: E402


def read_bucket_metadata(name: str) -> dict[str, Any]:
    # No ADC fallback to an interactive human login. The sourced read-only
    # tier supplies this agent key; the OAuth scope is read-only as well.
    credentials = service_account.Credentials.from_service_account_file(
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'], scopes=['https://www.googleapis.com/auth/devstorage.read_only']
    )
    with requests.AuthorizedSession(credentials) as session:
        response = session.get(
            f'https://storage.googleapis.com/storage/v1/b/{quote(name, safe="")}',
            params={
                'fields': 'metageneration,lifecycle,defaultEventBasedHold,retentionPolicy,softDeletePolicy,versioning'
            },
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
    soft_delete = payload.get('softDeletePolicy')
    versioning = payload.get('versioning')
    return {
        'metageneration': payload.get('metageneration'),
        'lifecycle': payload.get('lifecycle'),
        'default_event_based_hold': payload.get('defaultEventBasedHold'),
        'retention_period': retention.get('retentionPeriod'),
        # Ceiling inputs only; a missing policy reads as unknown, never as zero.
        'soft_delete_seconds': soft_delete.get('retentionDurationSeconds') if isinstance(soft_delete, dict) else None,
        'versioning': bool(versioning.get('enabled')) if isinstance(versioning, dict) else False,
    }


def _metageneration(metadata: dict[str, Any]) -> str | None:
    generation = metadata.get('metageneration')
    if isinstance(generation, bool) or not isinstance(generation, (int, str)):
        return None
    value = str(generation)
    return value if re.fullmatch(r'[1-9][0-9]*', value) else None


def policy_failure(
    metadata: dict[str, Any], bucket: str | None = None, contract: dict[str, Any] | None = None
) -> str | None:
    if _metageneration(metadata) is None:
        return 'invalid_metadata'
    if metadata.get('default_event_based_hold') or metadata.get('retention_period') not in (None, 0):
        return 'privacy_blocking_retention'
    lifecycle = metadata.get('lifecycle')
    if lifecycle is None:
        lifecycle = {}
    if not isinstance(lifecycle, dict) or not isinstance(lifecycle.get('rule', []), list):
        return 'invalid_metadata'
    governed = _governed(contract, bucket)
    for rule in lifecycle.get('rule', []):
        if not isinstance(rule, dict) or not isinstance(rule.get('action'), dict):
            return 'invalid_metadata'
        action = rule['action'].get('type')
        if action == 'Delete' and governed is None:
            return 'lifecycle_delete'
        if action not in {'Delete', 'SetStorageClass', 'AbortIncompleteMultipartUpload'}:
            return 'unsupported_lifecycle_action'
    if governed is not None and retention_contract.floor_violations(governed[0], governed[1], lifecycle):
        return 'lifecycle_delete'
    return None


def _governed(contract: dict[str, Any] | None, bucket: str | None) -> tuple[dict[str, Any], str] | None:
    """(contract, bucket) when the contract names the bucket, else None (strict any-Delete rule)."""
    if contract is None or bucket is None or bucket not in contract.get('buckets', {}):
        return None
    return contract, bucket


def audit(
    names: Sequence[str],
    reader: Callable[[str], dict[str, Any]] = read_bucket_metadata,
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    targets = []
    for index, name in enumerate(names, start=1):
        try:
            metadata = reader(name)
            reason = policy_failure(metadata, name, contract)
            governed = _governed(contract, name)
            receipt = {
                'target': index,
                'metageneration': _metageneration(metadata),
                'policy_sha256': hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest(),
                'reason': reason,
                'contract': governed is not None,
                # Report-only: ceilings never change PASS/FAIL here.
                'ceilings': retention_contract.ceiling_findings(*governed, metadata) if governed is not None else [],
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
    result = audit(names, reader, retention_contract.load())
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
