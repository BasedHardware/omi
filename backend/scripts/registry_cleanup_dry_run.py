#!/usr/bin/env python3
"""Render a local Artifact Registry dry-run proposal. No cloud IO or apply path."""

import argparse
import datetime as dt
import json
import re
from pathlib import Path

REPOSITORY = 'projects/based-hardware/locations/us-central1/repositories/cloud-run-source-deploy'
COVERAGE = ('cloud_run_revisions', 'gke_workloads_both_projects', 'cloud_run_jobs', 'rollback_receipts_30d')


def render(snapshot: dict, now: dt.datetime | None = None) -> dict:
    """Incomplete coverage keeps everything; invalid or stale evidence is rejected."""
    if snapshot.get('repository') != REPOSITORY:
        raise ValueError('only the prod regional source-deploy repository is in scope')
    observed = dt.datetime.fromisoformat(snapshot['observed_at'].replace('Z', '+00:00'))
    now = now or dt.datetime.now(dt.timezone.utc)
    if observed.tzinfo is None or not dt.timedelta(0) <= now - observed <= dt.timedelta(hours=24):
        raise ValueError('snapshot must be timezone-aware, not future-dated, and at most 24 hours old')
    digests = snapshot.get('protected_digests')
    if not isinstance(digests, list) or not digests:
        raise ValueError('a nonempty protected digest inventory is required')
    if any(not isinstance(d, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', d) for d in digests):
        raise ValueError('protected digests must be full sha256 values')
    coverage = snapshot.get('coverage', {})
    if not isinstance(coverage, dict):
        raise ValueError('coverage must be an object')
    policies = {
        'old-source-builds': {
            'action': 'DELETE',
            'condition': {'tagState': 'ANY', 'olderThan': '2592000s', 'packageNamePrefixes': ['omi/omi']},
        },
        'keep-latest-100': {'action': 'KEEP', 'mostRecentVersions': {'keepCount': 100}},
        'keep-release-tags': {
            'action': 'KEEP',
            'condition': {'tagState': 'TAGGED', 'tagPrefixes': ['release', 'v', 'stable', 'prod', 'latest']},
        },
        'keep-protected-digests': {
            'action': 'KEEP',
            'condition': {'tagState': 'ANY', 'versionNamePrefixes': sorted(set(digests))},
        },
    }
    if not all(coverage.get(key) is True for key in COVERAGE):
        policies['hold-incomplete-inventory'] = {'action': 'KEEP', 'condition': {'tagState': 'ANY'}}
    return {'name': REPOSITORY, 'cleanupPolicyDryRun': True, 'cleanupPolicies': policies}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path, help='local protected-image snapshot JSON')
    args = parser.parse_args()
    try:
        result = render(json.loads(args.snapshot.read_text()))
    except (KeyError, ValueError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
