#!/usr/bin/env python3
"""Read-only deployment diff by default; explicit validation/apply for the operator.

Never reads secrets or customer documents. Reconciles only the declared messaging
job or uniquely named alert policies. Scheduler stays under scheduler_reconcile.py.
"""

import argparse
import copy
import json
from pathlib import Path
import re

import subprocess
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import AuthorizedSession

ROOT = Path(__file__).resolve().parents[1] / 'deploy' / 'messaging'
PROJECT = 'based-hardware'


def contains(actual, expected):
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(contains(actual.get(k), v) for k, v in expected.items())
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(contains(a, e) for a, e in zip(actual, expected))
        )
    return actual == expected


def request(session, method, url, **kwargs):
    response = session.request(method, url, timeout=60, **kwargs)
    if response.status_code == 404 and method == 'GET':
        return None
    if not response.ok:
        # Provider errors may contain credentials or user data. Only status is emitted.
        raise RuntimeError(f'{method} operation failed HTTP {response.status_code}')
    value = response.json()
    if value.get('error'):
        raise RuntimeError('Remote operation returned an error')
    return value


def desired_job(image):
    if not re.fullmatch(
        r'(?:gcr.io|[a-z0-9-]+-docker.pkg.dev)/based-hardware/[a-zA-Z0-9_./-]+@sha256:[a-f0-9]{64}', image
    ):
        raise ValueError('An admitted production image pinned by sha256 is required')
    job = json.loads((ROOT / 'maintenance-job.json').read_text())
    job['template']['template']['containers'][0]['image'] = image
    return job


def reconcile_job(session, image, mode):
    body = desired_job(image)
    url = 'https://run.googleapis.com/v2/' + body['name']
    current = request(session, 'GET', url)
    if current is not None and contains(current, body):
        print('MATCH messaging-maintenance-job')
        return False
    print('DIFF messaging-maintenance-job')
    if mode == 'check':
        return True
    params = {'validateOnly': 'true' if mode == 'validate' else 'false'}
    if current is None:
        params['jobId'] = 'messaging-maintenance-job'
        request(session, 'POST', url.rsplit('/', 1)[0], params=params, json=body)
    else:
        # v2 UpdateJobRequest contains Job + validate_only + allow_missing, no
        # update_mask. Send the complete declared Job (this tool owns its config).
        # https://docs.cloud.google.com/run/docs/reference/rest/v2/projects.locations.jobs/patch
        request(session, 'PATCH', url, params=params, json=body)
    # Cloud Run returns an asynchronous operation. No execution is started here.
    print('VALIDATED' if mode == 'validate' else 'SUBMITTED; rerun --check after operation completion')
    return False


def desired_alerts(channels):
    if (
        not channels
        or len(channels) != len(set(channels))
        or any(not re.fullmatch(r'projects/based-hardware/notificationChannels/[0-9]+', c) for c in channels)
    ):
        raise ValueError('Distinct approved production notification channel resource names are required')
    bodies = json.loads((ROOT / 'alert-policies.json').read_text())
    for body in bodies:
        body['notificationChannels'] = sorted(channels)
    return bodies


def normalize_log_metric(value):
    # Proto JSON may omit default false and the STRING=0 label enum.
    value.setdefault('disabled', False)
    for label in value.get('metricDescriptor', {}).get('labels', []):
        label.setdefault('valueType', 'STRING')
    return value


def reconcile_log_metrics(session, mode):
    if mode == 'validate':
        raise ValueError('Logging has no validateOnly API; use --check to review the diff')
    bodies = json.loads((ROOT / 'log-metrics.json').read_text())
    url = f'https://logging.googleapis.com/v2/projects/{PROJECT}/metrics/'
    planned = []
    for body in bodies:
        current = request(session, 'GET', url + body['name'])
        if current is not None:
            normalize_log_metric(current)
            descriptor = current.get('metricDescriptor', {})
            expected = body['metricDescriptor']
            expected_labels = {label['key']: label for label in expected.get('labels', [])}
            # Logging cannot change kind/type or remove existing metric labels.
            if any(descriptor.get(k) != expected[k] for k in ('metricKind', 'valueType')) or not {
                label['key'] for label in descriptor.get('labels', [])
            }.issubset(expected_labels):
                raise RuntimeError('Existing log metric schema differs; refusing incompatible update')
            if any(
                label.get('valueType', 'STRING') != expected_labels[label['key']]['valueType']
                for label in descriptor.get('labels', [])
            ):
                raise RuntimeError('Existing log metric schema differs; refusing incompatible update')
        if current is not None and contains(current, body):
            print('MATCH ' + body['name'])
        else:
            planned.append(body)
            print('DIFF ' + body['name'])
    if mode == 'check':
        return bool(planned)
    for body in planned:
        target = url + body['name']
        # Logging metrics.update is PUT/upsert, not PATCH, and has no field mask.
        request(session, 'PUT', target, json=body)
        verified = request(session, 'GET', target)
        if verified is None:
            raise RuntimeError('Log metric missing during verification')
        normalize_log_metric(verified)
        if not contains(verified, body):
            raise RuntimeError('Log metric verification failed')
        print('VERIFIED ' + body['name'])
    return bool(planned)


def reconcile_alerts(session, channels, mode):
    if mode == 'validate':
        raise ValueError('Monitoring has no validateOnly API; use --check to review the diff')
    metrics_drift = reconcile_log_metrics(session, 'check')
    if mode == 'apply' and metrics_drift:
        raise RuntimeError('Log metrics must MATCH before alert policy writes; apply log-metrics first')
    url = f'https://monitoring.googleapis.com/v3/projects/{PROJECT}/alertPolicies'
    policies = []
    token = None
    while True:
        page = request(session, 'GET', url, params={'pageToken': token} if token else {})
        if page is None:
            raise RuntimeError('Alert policy collection unavailable')
        policies.extend(page.get('alertPolicies', []))
        token = page.get('nextPageToken')
        if not token:
            break
    bodies = desired_alerts(channels)
    for body in bodies:
        if sum(p['displayName'] == body['displayName'] for p in policies) > 1:
            raise RuntimeError('Duplicate managed policy name; refusing writes')
    drift = metrics_drift
    for desired in bodies:
        matches = [p for p in policies if p['displayName'] == desired['displayName']]
        if len(matches) > 1:
            raise RuntimeError('Duplicate managed policy name; refusing writes')
        current = copy.deepcopy(matches[0]) if matches else None
        if current is not None:
            current['notificationChannels'] = sorted(current.get('notificationChannels', []))
        if current is not None and contains(current, desired):
            print('MATCH ' + desired['displayName'])
            continue
        drift = True
        print('DIFF ' + desired['displayName'])
        if mode == 'check':
            continue
        if current is not None:
            names = {c['displayName']: c['name'] for c in current['conditions']}
            if set(names) != {c['displayName'] for c in desired['conditions']}:
                raise RuntimeError('Existing condition identities differ; refusing replacement')
            for c in desired['conditions']:
                c['name'] = names[c['displayName']]
            desired['name'] = current['name']
            target = 'https://monitoring.googleapis.com/v3/' + current['name']
            request(
                session,
                'PATCH',
                target,
                params={'updateMask': ','.join(k for k in desired if k != 'name')},
                json=desired,
            )
        else:
            created = request(session, 'POST', url, json=desired)
            if created is None:
                raise RuntimeError('Policy create returned no resource')
            target = 'https://monitoring.googleapis.com/v3/' + created['name']
        verified = request(session, 'GET', target)
        if verified is None:
            raise RuntimeError('Created policy missing during verification')
        verified['notificationChannels'] = sorted(verified.get('notificationChannels', []))
        if not contains(verified, desired):
            raise RuntimeError('Policy verification failed')
        print('VERIFIED ' + desired['displayName'])
    return drift


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('resource', choices=('job', 'log-metrics', 'alerts'))
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--check', action='store_true')
    modes.add_argument('--validate', action='store_true')
    modes.add_argument('--apply', action='store_true')
    parser.add_argument('--image', default='')
    parser.add_argument('--notification-channels', nargs='+', default=[])
    args = parser.parse_args()
    mode = 'apply' if args.apply else 'validate' if args.validate else 'check'
    # Validate inputs before authenticating or contacting GCP.
    if args.resource == 'job':
        desired_job(args.image)
    elif args.resource == 'alerts':
        desired_alerts(args.notification_channels)
    # Honor gcp-agent-env's selected gcloud identity, including human IAM/operator
    # sessions, rather than silently falling through to a different ADC account.
    token = subprocess.run(
        ['gcloud', 'auth', 'print-access-token', '--quiet'], capture_output=True, text=True, timeout=60
    )
    if token.returncode or not token.stdout.strip():
        raise RuntimeError('Selected gcloud identity has no usable access token')
    session = AuthorizedSession(Credentials(token=token.stdout.strip()))
    if args.resource == 'job':
        drift = reconcile_job(session, args.image, mode)
    elif args.resource == 'log-metrics':
        drift = reconcile_log_metrics(session, mode)
    else:
        drift = reconcile_alerts(session, args.notification_channels, mode)
    return 1 if mode == 'check' and drift else 0


if __name__ == '__main__':
    raise SystemExit(main())
