#!/usr/bin/env python3
"""Reconcile the prod Grafana external health check and Cloud Monitoring policy.

Uses the Monitoring v3 REST API with the workflow's gcloud identity. Stable
unique display names select resources; duplicates fail closed. Updates preserve
resource and condition IDs and unchanged runs perform no writes. No deletes or
blind retries of creates (a lost response is recovered by the next run's list).
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CONFIG = Path(__file__).resolve().parents[2] / 'backend/deploy/monitoring/grafana-deadman.json'


class MonitoringAPI:
    def __init__(self) -> None:
        result = subprocess.run(
            ['gcloud', 'auth', 'print-access-token'], text=True, capture_output=True, check=False
        )
        if result.returncode or not result.stdout.strip():
            raise RuntimeError('Unable to obtain workflow Monitoring credentials')
        self.token = result.stdout.strip()

    def __call__(self, method: str, path: str, body: dict | None = None, **query: str) -> dict:
        url = 'https://monitoring.googleapis.com/v3/' + path
        if query:
            url += '?' + urlencode(query)
        request = Request(
            url,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Authorization': f'Bearer {self.token}', 'Content-Type': 'application/json'},
            method=method,
        )
        try:
            with urlopen(request, timeout=60) as response:
                return json.load(response)
        except HTTPError as exc:
            # Do not print request headers, tokens, or unbounded server bodies.
            raise RuntimeError(f'Monitoring {method} {path} failed: HTTP {exc.code}') from exc
        except URLError as exc:
            raise RuntimeError(f'Monitoring {method} {path} transport failed') from exc


def _channels(project: str, value: str) -> list[str]:
    channels = [entry.strip() for entry in value.split(',')]
    if not all(re.fullmatch(rf'projects/{re.escape(project)}/notificationChannels/[^/\s]+', c) for c in channels):
        raise ValueError(
            'MONITORING_DEADMAN_NOTIFICATION_CHANNELS must be set to comma-separated '
            f'projects/{project}/notificationChannels/<id> resource names without empty entries'
        )
    if len(channels) != len(set(channels)):
        raise ValueError('MONITORING_DEADMAN_NOTIFICATION_CHANNELS contains duplicates')
    return sorted(channels)


def _matches(actual: object, expected: object) -> bool:
    """Compare managed fields, tolerating API output-only fields and defaults."""
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(_matches(actual.get(k), v) for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(
            _matches(a, e) for a, e in zip(actual, expected)
        )
    return actual == expected or (actual is None and expected in (False, 0, ''))


def _find(api, collection: str, key: str, display_name: str) -> dict | None:
    matches = []
    token = ''
    while True:
        page = api('GET', collection, **({'pageToken': token} if token else {}))
        matches.extend(item for item in page.get(key, []) if item.get('displayName') == display_name)
        token = page.get('nextPageToken', '')
        if not token:
            break
    if len(matches) > 1:
        raise RuntimeError(f'Duplicate {display_name} resources; reconcile manually')
    return matches[0] if matches else None


def _reconcile(api, collection: str, key: str, body: dict) -> dict:
    existing = _find(api, collection, key, body['displayName'])
    if existing is None:
        result = api('POST', collection, body)
    else:
        name = existing['name']
        existing = api('GET', name)
        if key == 'alertPolicies':
            conditions = existing.get('conditions', [])
            if len(conditions) != 1 or not conditions[0].get('name'):
                raise RuntimeError('Existing dead-man policy must have one named condition')
            body['conditions'][0]['name'] = conditions[0]['name']
        # These API arrays are sets; ordering is not drift.
        for field in ('selectedRegions', 'notificationChannels'):
            if field in existing:
                existing[field] = sorted(existing[field])
        if _matches(existing, body):
            return existing
        body['name'] = name
        result = api('PATCH', name, body, updateMask=','.join(k for k in body if k != 'name'))
    name = result.get('name')
    if not name:
        raise RuntimeError('Monitoring write returned no resource name; re-run to reconcile')
    verified = api('GET', name)
    for field in ('selectedRegions', 'notificationChannels'):
        if field in verified:
            verified[field] = sorted(verified[field])
    if not _matches(verified, body):
        raise RuntimeError(f'Monitoring managed configuration drift after write: {name}')
    return verified


def ensure_deadman(*, project: str, notification_channels: str, api=None) -> tuple[str, str]:
    if not re.fullmatch(r'[a-z][a-z0-9-]+', project):
        raise ValueError('project must be a GCP project ID')
    channels = _channels(project, notification_channels)  # Validate before credentials or any writes.
    config = json.loads(CONFIG.read_text(encoding='utf-8'))
    check = copy.deepcopy(config['uptimeCheck'])
    check['monitoredResource']['labels']['project_id'] = project
    check['selectedRegions'].sort()
    api = api if api is not None else MonitoringAPI()
    check = _reconcile(api, f'projects/{project}/uptimeCheckConfigs', 'uptimeCheckConfigs', check)
    policy = copy.deepcopy(config['alertPolicy'])
    policy['notificationChannels'] = channels
    threshold = policy['conditions'][0]['conditionThreshold']
    threshold['filter'] = threshold['filter'].replace('${CHECK_ID}', check['name'].rsplit('/', 1)[1])
    policy = _reconcile(api, f'projects/{project}/alertPolicies', 'alertPolicies', policy)
    return check['name'], policy['name']


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--notification-channels', required=True)
    args = parser.parse_args()
    try:
        for name in ensure_deadman(project=args.project, notification_channels=args.notification_channels):
            print(name)
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
