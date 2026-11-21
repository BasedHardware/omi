"""Read the effective production summary gates before the Home operator admits debt."""

import json
from pathlib import Path
import re
import subprocess
import time

from config.refactor_modes import CAPTURE_COVERAGE_MODE_ENV
from config.summary_guarantee import repair_enabled
from utils.conversations.summary_delivery import PROJECTION_DEBT_ENV, projection_debt_enabled

PRODUCTION_PROJECT = 'based-hardware'
REPAIR_SERVICE = 'backend-integration'
REGION = 'us-central1'
FLAGS = frozenset({CAPTURE_COVERAGE_MODE_ENV, 'SUMMARY_DEBT_REPAIR_ENABLED', PROJECTION_DEBT_ENV})
RELEASE_SHA = 'OMI_BACKEND_RELEASE_SHA'


def _describe(kind, name, *, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError('serving policy deadline')
    env_script = Path.home() / '.local/bin/gcp-agent-env.sh'
    response = subprocess.run(
        [
            'bash',
            '-c',
            'source "$1" ro-prod >/dev/null 2>&1 && [ "$GCP_AGENT_TIER" = ro-prod ] && '
            'export CLOUDSDK_CORE_ACCOUNT=read-only-bot-account@based-hardware.iam.gserviceaccount.com && '
            'shift && exec gcloud "$@"',
            'home-health-runtime',
            str(env_script),
            'run',
            kind,
            'describe',
            name,
            '--project',
            PRODUCTION_PROJECT,
            '--region',
            REGION,
            '--format=json',
            '--quiet',
        ],
        capture_output=True,
        check=True,
        text=True,
        timeout=min(remaining, 15),
    )
    return json.loads(response.stdout)


def _receiving(service):
    traffic = {}
    for entry in service['status']['traffic']:
        percent = entry.get('percent', 0)
        if type(percent) is not int or not 0 <= percent <= 100:
            raise ValueError('invalid traffic allocation')
        if not percent:
            continue
        revision = entry['revisionName']
        if not re.fullmatch(r'backend-integration-[a-z0-9-]+', revision) or revision in traffic:
            raise ValueError('unexpected traffic revision')
        traffic[revision] = percent
    if sum(traffic.values()) != 100:
        raise ValueError('incomplete traffic allocation')
    return traffic


def _enabled(revision, name):
    if revision['metadata']['name'] != name:
        return False
    values = {}
    for entry in revision['spec']['containers'][0].get('env', []):
        flag = entry['name']
        if flag not in FLAGS and flag != RELEASE_SHA:
            continue
        value = entry.get('value')
        if flag in values or not isinstance(value, str):
            return False
        values[flag] = value
    return bool(
        re.fullmatch(r'[0-9a-f]{40}', values.get(RELEASE_SHA, ''))
        and repair_enabled(environ=values)
        and projection_debt_enabled(environ=values)
    )


def serving_allows_repair(*, deadline):
    """Check each receiving revision and reject a traffic move during verification."""
    try:
        before = _receiving(_describe('services', REPAIR_SERVICE, deadline=deadline))
        if not all(_enabled(_describe('revisions', name, deadline=deadline), name) for name in before):
            return False
        return before == _receiving(_describe('services', REPAIR_SERVICE, deadline=deadline))
    except (OSError, subprocess.SubprocessError, KeyError, IndexError, TypeError, ValueError):
        # Transport errors can include configuration values. Keep the receipt
        # limited to the caller's single closed failure category.
        return False
