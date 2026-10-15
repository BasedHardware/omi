#!/usr/bin/env python3
"""Exercise fleet ingestion using the existing release-probe token, on dev only."""

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import urllib.error
import urllib.parse
import urllib.request


def verify_dev_candidate(url, service):
    """Only allow a URL read back from the dev project's actual backend service."""
    parsed = urllib.parse.urlsplit(url)
    urls = [service.get('status', {}).get('url', '')]
    urls.extend(row.get('url', '') for row in service.get('status', {}).get('traffic', []))
    hosts = {urllib.parse.urlsplit(item).netloc for item in urls if item}
    if parsed.scheme != 'https' or not parsed.hostname or not parsed.hostname.endswith('.run.app'):
        raise ValueError('fleet probe requires a dev Cloud Run URL')
    if parsed.netloc not in hosts or parsed.path not in ('', '/') or parsed.query or parsed.fragment:
        raise ValueError('fleet probe URL is not the dev backend candidate')


def payload():
    now = datetime.now(timezone.utc)
    return {
        'schema_version': 1,
        'platform': 'linux',
        'build_channel': 'dev',
        'app_version': 'release-probe',
        'window_start': (now - timedelta(minutes=15)).isoformat(),
        'window_end': now.isoformat(),
        'counters': [{'event': 'App Startup Timing', 'outcome': 'observed', 'count': 1}],
        'histograms': [
            {
                'name': 'app_startup_duration_seconds',
                'buckets': [{'le': edge, 'count': 1} for edge in (0.05, 0.1, 0.5, 1, 5, 15, 60, 300, 600, '+Inf')],
            }
        ],
    }


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def post(url, token=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    request = urllib.request.Request(
        url.rstrip('/') + '/v1/telemetry/fleet', data=json.dumps(payload()).encode(), headers=headers
    )
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=20) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, {}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-api-url', required=True)
    parser.add_argument('--bearer-token-file', type=Path, required=True)
    args = parser.parse_args()
    service = json.loads(
        subprocess.run(
            [
                'gcloud',
                'run',
                'services',
                'describe',
                'backend',
                '--project=based-hardware-dev',
                '--region=us-central1',
                '--format=json',
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    verify_dev_candidate(args.candidate_api_url, service)
    if post(args.candidate_api_url)[0] != 401:
        raise SystemExit('dev fleet unauthenticated probe did not return 401')
    status, body = post(args.candidate_api_url, args.bearer_token_file.read_text().strip())
    if status == 429:
        # Do not retry the shared UID or report an unaccepted summary as proof.
        raise SystemExit('Dev fleet acceptance incomplete: release-probe UID budget exhausted (429)')
    elif status == 200 and body == {'schema_version': 1, 'accepted': True, 'clamped': False}:
        print('Dev fleet probe: auth enforced; counter and fixed histogram summary accepted (200)')
    else:
        raise SystemExit(f'dev fleet summary probe failed (status={status})')


if __name__ == '__main__':
    main()
